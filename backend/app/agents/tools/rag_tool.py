# ============================================
# RAG 在线阶段：查询改写工具（rag_tool）
# 职责：把用户口语化查询改写成"更容易命中攻略"的检索词
# 原理：两级策略，LLM 优先，规则兜底：
#   1) LLM-based（deepseek-flash）：一次调用，输出规范化 query + 关键词列表
#   2) 规则级 fallback：retrieval_rules.json 里把口语词映射为攻略关键词
#   结果缓存进 Redis（同一查询不重复改写）
# ============================================
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.services import cache_service

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = """你是旅行检索的查询改写助手。用户会给出一个旅行规划相关的需求，请把它改写成更适合检索攻略的查询。
输出必须是合法 JSON，不要任何额外文字，格式：
{"query": "改写后的单一检索句", "keywords": ["关键词1", "关键词2", "关键词3"]}
要求：query 包含目的地与核心意图；keywords 抽取 2-4 个攻略中可能出现的名词。
"""

# 模块级 LLM 实例（与主规划 Agent 共用同一模型，独立实例避免耦合）
_rewrite_llm = None


def _get_llm() -> ChatOpenAI:
    global _rewrite_llm
    if _rewrite_llm is None:
        _rewrite_llm = ChatOpenAI(
            model=settings.DEEPSEEK_MODEL_ID,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=settings.LLM_TIMEOUT,
            temperature=0.2,  # 改写任务低温度，输出更稳定
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    return _rewrite_llm


def rewrite_query(raw_query: str, city: str | None = None) -> dict:
    """改写用户查询。返回 {"query": ..., "keywords": [...]}。

    city 仅用于缓存 key 区分（同一查询不同城市改写可能不同）。
    """
    cache_key = f"rewrite:{city or 'all'}:{raw_query}"
    cached = cache_service.cache_get(cache_key)
    if cached:
        return cached

    result = _llm_rewrite(raw_query) or _rule_rewrite(raw_query)
    cache_service.cache_set(cache_key, result, ttl=86400)  # 改写结果一天内有效
    return result


def _llm_rewrite(raw_query: str) -> dict | None:
    """deepseek-flash 改写；解析失败返回 None（交给规则兜底）。"""
    try:
        resp = _get_llm().invoke(
            [
                SystemMessage(content=REWRITE_SYSTEM_PROMPT),
                HumanMessage(content=raw_query),
            ]
        )
        from app.services.token_tracker import token_tracker

        token_tracker.record("rewrite", resp.response_metadata)  # Token 观测
        data = json.loads(resp.content)
        # 结构校验：query 必须有，keywords 至少 1 个
        if data.get("query") and data.get("keywords"):
            return {"query": data["query"], "keywords": data["keywords"]}
    except Exception as e:
        logger.warning(f"LLM 改写失败，走规则兜底: {e}")
    return None


def _rule_rewrite(raw_query: str) -> dict:
    """规则级兜底：在 retrieval_rules.json 里找口语词，替换为攻略关键词。"""
    import json as _json
    from pathlib import Path

    rules_path = Path(settings.BASE_DIR) / "data" / "retrieval_rules.json"
    try:
        rules = _json.loads(rules_path.read_text(encoding="utf-8"))["rules"]
    except Exception:
        rules = []

    expanded = list(raw_query)
    keywords: list[str] = []
    for rule in rules:
        if rule["raw"] in raw_query:
            keywords.extend(rule["expanded"])
    # 去重保序
    seen = set()
    keywords = [k for k in keywords if not (k in seen or seen.add(k))]
    return {"query": raw_query, "keywords": keywords}
