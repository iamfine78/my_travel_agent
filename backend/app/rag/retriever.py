# ============================================
# 检索器：向量召回 + Rerank + 缓存
# 职责：RAG 在线链路的"出口"——返回排好序、带分数的检索结果
# 流程：改写后的 query → 向量召回 top_k*2 → Rerank（deepseek-flash
#       LLM 重排，失败降级规则打分）→ 取 top_n → 结果缓存 Redis
# ============================================
import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.rag import vector_db
from app.services import cache_service

logger = logging.getLogger(__name__)

RERANK_SYSTEM_PROMPT = """你是旅行攻略检索的精排助手。用户会给出一个查询和若干攻略片段，请判断每个片段与查询的相关性并排序。
输出必须是合法 JSON，不要任何额外文字，格式：
{"ranked": [{"index": 0, "score": 8, "reason": "一句话理由"}]}
规则：index 必须是输入片段的下标；score 0-10 整数，越高越相关；按相关度从高到低排列；最多输出 3 条。
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

    # 2) 重排：LLM 优先，失败降级规则打分
    ranked = _llm_rerank(query, docs) or _rule_score(query, docs)

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


# ---------- Rerank 实现 ----------
def _llm_rerank(query: str, docs: list) -> list[tuple[int, int, str]] | None:
    """deepseek-flash 重排：给每个片段打分排序。失败返回 None。"""
    # 片段太长会超 token，每个截断到 200 字
    candidates = "\n\n".join(
        f"[{i}] {d.page_content[:200]}" for i, d in enumerate(docs)
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
