# ============================================
# 规划主链路的降级测试（离线）
# 回归：高德/天气失败曾直接让 /api/trip/plan 抛异常 → 用户拿不到任何行程
# 原则：外部服务是「锦上添花」，失败要保留 LLM 原始输出并如实标注
# ============================================
import pytest

from app.models.schemas import TripPlanRequest
from app.services import trip_service


def _stub_llm(monkeypatch, itinerary: dict) -> None:
    monkeypatch.setattr(
        trip_service.planner_agent, "plan_trip",
        lambda req, extra_context="", mode="settled": itinerary,
    )


def _stub_settled_path(monkeypatch) -> None:
    """把 A 级（有攻略）的检索链路换成离线桩。"""
    monkeypatch.setattr(trip_service.rag_tool, "rewrite_query",
                        lambda q, city=None: {"query": q, "keywords": []})
    monkeypatch.setattr(trip_service.retriever, "retrieve_and_rerank", lambda *a, **k: [])
    monkeypatch.setattr(trip_service.fallback_candidates, "extract_from_guide", lambda c: ["兵马俑"])


def _boom(*a, **k):
    raise RuntimeError("高德挂了")


class TestPlanTripResilience:
    def test_amap_enrich_failure_returns_itinerary_with_note(self, monkeypatch):
        itin = {"destination": "西安", "days": [], "budget_split": {}, "summary": "s", "tips": []}
        _stub_llm(monkeypatch, itin)
        _stub_settled_path(monkeypatch)
        monkeypatch.setattr(trip_service.map_service, "enrich_itinerary", _boom)
        monkeypatch.setattr(trip_service.weather_service, "get_weather", lambda c: None)

        resp = trip_service.plan_trip(TripPlanRequest(destination="西安"))

        assert resp.destination == "西安"                      # 请求没崩
        assert any("高德地理信息补全失败" in s for s in resp.sources)

    def test_weather_failure_returns_itinerary_with_note(self, monkeypatch):
        itin = {"destination": "西安", "days": [], "budget_split": {}, "summary": "s", "tips": []}
        _stub_llm(monkeypatch, itin)
        _stub_settled_path(monkeypatch)
        monkeypatch.setattr(trip_service.map_service, "enrich_itinerary", lambda it, c: it)
        monkeypatch.setattr(trip_service.weather_service, "get_weather", _boom)

        resp = trip_service.plan_trip(TripPlanRequest(destination="西安"))

        assert resp.weather is None
        assert any("天气获取失败" in s for s in resp.sources)

    def test_candidate_pool_failure_degrades_and_keeps_itinerary(self, monkeypatch):
        """候选池拿不到时应降级为通用知识，且**不能**因池子为空把行程清光。"""
        itin = {
            "destination": "大理",
            "days": [{"day": 1, "morning": [{"place": "某个地点", "poi_id": "X"}],
                      "afternoon": [], "evening": []}],
            "budget_split": {}, "summary": "s", "tips": [],
        }
        _stub_llm(monkeypatch, itin)
        monkeypatch.setattr(trip_service.city_resolver_service, "resolve_city",
                            lambda c: {"city": "大理", "level": "B", "reason": "动态城市", "adcode": "532901"})
        monkeypatch.setattr(trip_service.place_candidate_service, "get_candidates", _boom)
        monkeypatch.setattr(trip_service.map_service, "enrich_itinerary", lambda it, c: it)
        monkeypatch.setattr(trip_service.weather_service, "get_weather", lambda c: None)

        resp = trip_service.plan_trip(TripPlanRequest(destination="大理"))

        assert any("候选池获取失败" in s for s in resp.sources)
        assert resp.itinerary["days"][0]["morning"], "降级后不应清空行程"

    def test_candidate_pool_failure_uses_fallback_mode(self, monkeypatch):
        """降级时不能让 LLM 继续按白名单模式生成（池子已经没了）。"""
        seen = {}

        def spy(req, extra_context="", mode="settled"):
            seen["mode"] = mode
            return {"destination": "大理", "days": [], "budget_split": {}, "summary": "s", "tips": []}

        monkeypatch.setattr(trip_service.planner_agent, "plan_trip", spy)
        monkeypatch.setattr(trip_service.city_resolver_service, "resolve_city",
                            lambda c: {"city": "大理", "level": "B", "reason": "动态城市", "adcode": "532901"})
        monkeypatch.setattr(trip_service.place_candidate_service, "get_candidates", _boom)
        monkeypatch.setattr(trip_service.map_service, "enrich_itinerary", lambda it, c: it)
        monkeypatch.setattr(trip_service.weather_service, "get_weather", lambda c: None)

        trip_service.plan_trip(TripPlanRequest(destination="大理"))

        assert seen["mode"] == "fallback"

    def test_pool_validation_still_runs_when_pool_ok(self, monkeypatch):
        """反面对照：候选池正常时仍要做池外校验（别把防幻觉一起关掉）。"""
        itin = {
            "destination": "大理",
            "days": [{"day": 1, "morning": [{"place": "编造的", "poi_id": "FAKE"}],
                      "afternoon": [], "evening": []}],
            "budget_split": {}, "summary": "s", "tips": [],
        }
        _stub_llm(monkeypatch, itin)
        monkeypatch.setattr(trip_service.city_resolver_service, "resolve_city",
                            lambda c: {"city": "大理", "level": "B", "reason": "动态城市", "adcode": "532901"})
        monkeypatch.setattr(trip_service.place_candidate_service, "get_candidates",
                            lambda city, adcode="": {"scenic": [], "food": [], "lodging": []})
        monkeypatch.setattr(trip_service.map_service, "enrich_itinerary", lambda it, c: it)
        monkeypatch.setattr(trip_service.weather_service, "get_weather", lambda c: None)

        resp = trip_service.plan_trip(TripPlanRequest(destination="大理"))

        # 池子存在但为空 → 池外地点被移除
        assert resp.itinerary["days"][0]["morning"] == []
        assert any("候选校验" in s for s in resp.sources)
