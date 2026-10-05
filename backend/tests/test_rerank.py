# ============================================
# 重排链路测试（离线）
# 覆盖：三级降级调度（专用模型 → LLM → 规则）、dashscope 响应解析与容错
# 真实端点形状由 scripts/probe_rerank_api.py 实测确认（见 _dashscope_rerank 注释）
# ============================================
import pytest
from langchain_core.documents import Document

from app.rag import retriever

DOCS = [
    Document(page_content="西安城墙 门票 54 元", metadata={"city": "西安"}),
    Document(page_content="成都火锅 推荐", metadata={"city": "成都"}),
    Document(page_content="陕西历史博物馆 需预约", metadata={"city": "西安"}),
]


class TestRerankDispatcher:
    def test_uses_dashscope_when_model_configured(self, monkeypatch):
        monkeypatch.setattr(retriever.settings, "RERANK_MODEL", "qwen3-rerank")
        monkeypatch.setattr(retriever, "_dashscope_rerank", lambda q, d: [(2, 9, "精排 0.93")])
        assert retriever.rerank("西安 历史", DOCS)[0][0] == 2

    def test_skips_dashscope_when_model_not_configured(self, monkeypatch):
        called = []
        monkeypatch.setattr(retriever.settings, "RERANK_MODEL", "")
        monkeypatch.setattr(retriever, "_dashscope_rerank", lambda q, d: called.append(1))
        monkeypatch.setattr(retriever, "_llm_rerank", lambda q, d: [(0, 5, "LLM")])
        retriever.rerank("x", DOCS)
        assert called == [], "未配置 RERANK_MODEL 时不应调用专用精排"

    def test_falls_back_to_llm_when_dashscope_fails(self, monkeypatch):
        monkeypatch.setattr(retriever.settings, "RERANK_MODEL", "qwen3-rerank")
        monkeypatch.setattr(retriever, "_dashscope_rerank", lambda q, d: None)
        monkeypatch.setattr(retriever, "_llm_rerank", lambda q, d: [(1, 8, "LLM")])
        assert retriever.rerank("x", DOCS) == [(1, 8, "LLM")]

    def test_falls_back_to_rules_when_llm_fails(self, monkeypatch):
        monkeypatch.setattr(retriever.settings, "RERANK_MODEL", "")
        monkeypatch.setattr(retriever, "_llm_rerank", lambda q, d: None)
        ranked = retriever.rerank("西安 门票", DOCS)
        assert ranked[0][0] == 0                 # 规则打分命中关键词的片段排第一
        assert ranked[0][2] == "规则打分"

    def test_rule_fallback_always_returns_something(self, monkeypatch):
        monkeypatch.setattr(retriever.settings, "RERANK_MODEL", "")
        monkeypatch.setattr(retriever, "_llm_rerank", lambda q, d: None)
        assert len(retriever.rerank("随便什么", DOCS)) == len(DOCS)


class TestDashscopeRerank:
    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    def _patch(self, monkeypatch, payload, key="test-key"):
        monkeypatch.setattr(retriever.settings, "RERANK_MODEL", "qwen3-rerank")
        monkeypatch.setattr(retriever.settings, "RERANK_API_KEY", key)
        monkeypatch.setattr(retriever.httpx, "post", lambda *a, **k: self._Resp(payload))

    def test_parses_and_sorts_by_score(self, monkeypatch):
        self._patch(monkeypatch, {
            "output": {"results": [
                {"index": 2, "relevance_score": 0.93},
                {"index": 0, "relevance_score": 0.51},
            ]},
            "usage": {"total_tokens": 30},
        })
        ranked = retriever._dashscope_rerank("西安 历史", DOCS)
        assert ranked == [(2, 9, "精排 0.93"), (0, 5, "精排 0.51")]

    def test_out_of_range_index_is_dropped(self, monkeypatch):
        self._patch(monkeypatch, {"output": {"results": [
            {"index": 99, "relevance_score": 0.9},
            {"index": 1, "relevance_score": 0.4},
        ]}})
        assert retriever._dashscope_rerank("q", DOCS) == [(1, 4, "精排 0.40")]

    def test_empty_results_returns_none(self, monkeypatch):
        self._patch(monkeypatch, {"output": {"results": []}})
        assert retriever._dashscope_rerank("q", DOCS) is None

    def test_http_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(retriever.settings, "RERANK_MODEL", "qwen3-rerank")
        monkeypatch.setattr(retriever.settings, "RERANK_API_KEY", "test-key")

        def boom(*a, **k):
            raise RuntimeError("网络炸了")

        monkeypatch.setattr(retriever.httpx, "post", boom)
        assert retriever._dashscope_rerank("q", DOCS) is None

    def test_missing_key_returns_none_without_request(self, monkeypatch):
        called = []
        self._patch(monkeypatch, {"output": {"results": []}}, key="")
        monkeypatch.setattr(retriever.httpx, "post", lambda *a, **k: called.append(1))
        assert retriever._dashscope_rerank("q", DOCS) is None
        assert called == []
