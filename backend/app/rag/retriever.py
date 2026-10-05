# ============================================
# 检索器：向量召回 + Rerank + 缓存
# 职责：RAG 在线链路的"出口"——返回排好序、带分数的检索结果
# 流程：改写后的 query → 向量召回 top_k*2 → Rerank（deepseek-flash
#       LLM 重排，失败降级规则打分）→ 取 top_n → 结果缓存 Redis
# ============================================
import json
import logging
import re

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.rag import vector_db
from app.services import cache_service

logger = logging.getLogger(__name__)

RERANK_SYSTEM_PROMPT = """你是旅行攻略检索的精排助手。用户会给出一个查询和若干攻略片段，请判断每个片段与查询的相关性并排序。
输出必须是合法 JSON，不要任何额外文字，格式：
{"ranked": [{"index": 0, "score": 8, "reason": "一句话理由"}]}
规则：index 必须是输入片段的下标；score 0-10 整数，越高越相关；按相关度从高到低排列，覆盖全部输入片段。
"""

_rerank_llm = None


def _get_rerank_llm() -> ChatOpenAI:
    global _rerank_llm
    if _rerank_llm is None:
        _rerank_llm = ChatOpenAI(
            model=settings.DEEPSEEK_MODEL_ID,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=settings.LLM_TIMEOUT,
            temperature=0.0,  # 精排要稳定，温度必须为 0
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    return _rerank_llm


def retrieve_and_rerank(
    query: str,
    city: str | None = None,
    top_k: int | None = None,
    rerank_top_k: int | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """完整检索链：召回 → 重排 → 返回 [{content, score, reason, city}]。

    结果缓存：同一城市+查询在 TTL 内直接命中缓存（减少 LLM 重排调用）。
    use_cache=False：绕过缓存（评估 Latency/真实链路时用）。
    """
    k = top_k or settings.RAG_TOP_K
    rk = rerank_top_k or settings.RERANK_TOP_K

    cache_key = f"rag:{city or 'all'}:{query}"
    if use_cache:
        cached = cache_service.cache_get(cache_key)
        if cached:
            return cached

    # 1) 向量召回（多召回一些给重排留余地）
    docs = vector_db.retrieve(query, top_k=max(k * 2, 6), city=city)
    if not docs:
        return []

    # 2) 重排：专用模型 → LLM 打分 → 规则打分，逐级降级
    ranked = rerank(query, docs)

    # 3) 组装结果 + 缓存
    result = []
    for idx, score, reason in ranked[:rk]:
        d = docs[idx]
        result.append(
            {
                "content": d.page_content[:400],  # 控制注入上下文的长度
                "score": score,
                "reason": reason,
                "city": d.metadata.get("city", city),
            }
        )
    if use_cache:
        cache_service.cache_set(cache_key, result)
    return result


# ---------- Rerank 实现（三级降级：专用模型 → LLM 打分 → 规则） ----------
def rerank(query: str, docs: list) -> list[tuple[int, int, str]]:
    """对召回片段排序，返回 [(下标, 分数, 理由)]，分数从高到低。

    逐级降级，任一环节失败都不影响出结果，只是排序质量下降：
      1) 配置了 RERANK_MODEL → dashscope 专用精排（cross-encoder）
      2) 失败 → 让 LLM 读片段打分（原方案）
      3) 再失败 → 规则打分（关键词命中 + 城市匹配）
    """
    if settings.RERANK_MODEL:
        ranked = _dashscope_rerank(query, docs)
        if ranked:
            logger.info(f"Rerank：dashscope 专用精排（{settings.RERANK_MODEL}）")
            return ranked
    ranked = _llm_rerank(query, docs)
    if ranked:
        logger.info("Rerank：LLM 打分（专用精排不可用）")
        return ranked
    logger.info("Rerank：规则打分（专用精排与 LLM 均不可用）")
    return _rule_score(query, docs)


def _dashscope_rerank(query: str, docs: list) -> list[tuple[int, int, str]] | None:
    """dashscope 专用精排（qwen3-rerank 等）；失败返回 None 交给下一级降级。

    请求 / 响应形状由 scripts/probe_rerank_api.py 实测确认：
      请求 {"model", "input": {"query", "documents"}, "parameters": {"top_n", ...}}
      响应 {"output": {"results": [{"index", "relevance_score"}, ...]}}
    """
    if not settings.RERANK_API_KEY:
        return None
    try:
        resp = httpx.post(
            settings.RERANK_API_URL,
            headers={
                "Authorization": f"Bearer {settings.RERANK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.RERANK_MODEL,
                "input": {
                    "query": query,
                    # 截断控制 token；比原来 200 字宽，避免丢掉片段后半的关键信息
                    "documents": [d.page_content[:400] for d in docs],
                },
                "parameters": {"return_documents": False, "top_n": len(docs)},
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"dashscope 精排失败，走降级: {e}")
        return None

    results = (data.get("output") or {}).get("results") or []
    ranked: list[tuple[int, int, str]] = []
    for item in results:
        idx = int(item.get("index", -1))
        if not (0 <= idx < len(docs)):
            continue  # 越界下标直接丢弃，避免 IndexError
        score01 = float(item.get("relevance_score", 0) or 0)
        # 统一到 0-10 整数，与 LLM/规则打分同量纲，便于日志与阈值比较
        ranked.append((idx, round(score01 * 10), f"精排 {score01:.2f}"))
    if not ranked:
        return None
    # 分数可能并列：按下标二次排序，保证结果可复现
    ranked.sort(key=lambda x: (-x[1], x[0]))
    _record_rerank_tokens(data)
    return ranked


def _record_rerank_tokens(data: dict) -> None:
    """把精排消耗计入 Token 观测。

    dashscope 精排只返回 total_tokens（不区分 prompt/completion），
    统一记到 prompt 一侧——精排确实是「只读输入」的调用。
    """
    total = int((data.get("usage") or {}).get("total_tokens", 0) or 0)
    if not total:
        return
    from app.services.token_tracker import token_tracker

    token_tracker.record(
        "rerank",
        {"token_usage": {"prompt_tokens": total, "completion_tokens": 0, "total_tokens": total}},
    )


def _llm_rerank(query: str, docs: list) -> list[tuple[int, int, str]] | None:
    """LLM 打分重排（降级方案）：让 deepseek 给每个片段打分。失败返回 None。"""
    # 片段太长会超 token，每个截断到 400 字
    candidates = "\n\n".join(
        f"[{i}] {d.page_content[:400]}" for i, d in enumerate(docs)
    )
    user_text = f"查询：{query}\n\n候选片段：\n{candidates}"
    try:
        resp = _get_rerank_llm().invoke(
            [
                SystemMessage(content=RERANK_SYSTEM_PROMPT),
                HumanMessage(content=user_text),
            ]
        )
        from app.services.token_tracker import token_tracker

        token_tracker.record("rerank", resp.response_metadata)  # Token 观测
        data = json.loads(resp.content)
        ranked = data.get("ranked", [])
        # 安全校验：index 必须在合法范围内，score 转 int
        pairs = []
        for item in ranked:
            idx = int(item.get("index", -1))
            if 0 <= idx < len(docs):
                pairs.append((idx, int(item.get("score", 0)), str(item.get("reason", ""))))
        if pairs:
            return sorted(pairs, key=lambda x: -x[1])  # 分数从高到低
    except Exception as e:
        logger.warning(f"LLM 重排失败，走规则打分: {e}")
    return None


def _rule_score(query: str, docs: list) -> list[tuple[int, int, str]]:
    """规则级兜底打分：查询关键词在片段中的命中次数 + 城市匹配加分。

    简单有效：攻略片段里出现查询词的次数越多越相关。
    """
    query_terms = {t for t in re.split(r"[\s,，。、]+", query) if len(t) >= 2}
    scored = []
    for i, d in enumerate(docs):
        content = d.page_content
        # 词命中计数（含子串匹配，如"西安"命中"西安城墙"）
        hits = sum(1 for t in query_terms if t in content)
        # 城市匹配：片段城市与查询城市一致加分（防止跨城市污染）
        city_bonus = 3 if d.metadata.get("city") in query else 0
        scored.append((i, hits * 2 + city_bonus, "规则打分"))
    return sorted(scored, key=lambda x: -x[1])


def format_context(hits: list[dict]) -> str:
    """把检索结果拼成注入 LLM 的上下文文本。"""
    if not hits:
        return ""
    parts = []
    for h in hits:
        parts.append(f"【{h['city']}攻略·相关度{h['score']}】{h['content']}")
    return "\n\n".join(parts)
