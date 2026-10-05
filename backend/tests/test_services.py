# ============================================
# 基础服务测试（离线）
# 覆盖：Token 统计、Redis 缓存（含降级）、SQLite 存储 CRUD、Pydantic 模型校验
# ============================================
import json

import pytest
from pydantic import ValidationError

from app.models.schemas import Activity, Itinerary, ItineraryDay, TripPlanRequest
from app.services import cache_service
from app.services.token_tracker import PHASES, TokenTracker

_USAGE = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


class TestTokenTracker:
    def test_phases_are_four_stages(self):
        assert PHASES == ("rewrite", "rerank", "planner", "edit")

    def test_record_accumulates(self):
        t = TokenTracker()
        t.record("planner", _USAGE)
        t.record("planner", _USAGE)
        snap = t.snapshot()
        assert snap["by_phase"]["planner"] == {"prompt": 20, "completion": 10, "total": 30}
        assert snap["requests"]["planner"] == 2
        assert snap["total"] == 30

    def test_unknown_phase_ignored(self):
        t = TokenTracker()
        t.record("不存在的阶段", {"token_usage": {"total_tokens": 99}})
        assert t.snapshot()["total"] == 0

    def test_missing_metadata_is_safe(self):
        t = TokenTracker()
        t.record("planner", None)
        t.record("planner", {})
        assert t.snapshot()["total"] == 0

    def test_diff_computes_delta(self):
        t = TokenTracker()
        before = t.snapshot()
        t.record("rewrite", {"token_usage": {"prompt_tokens": 7, "completion_tokens": 3}})
        diff = t.diff(before, t.snapshot())
        assert diff["rewrite"] == {"prompt": 7, "completion": 3, "total": 10}
        assert diff["planner"]["total"] == 0

    def test_diff_never_negative(self):
        t = TokenTracker()
        t.record("planner", {"token_usage": {"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5}})
        before = t.snapshot()  # 已经计过 5
        earlier = TokenTracker().snapshot()  # 全 0
        diff = t.diff(before, earlier)
        assert diff["planner"]["total"] == 0


class TestCacheDegradation:
    """Redis 不可用时应「只变慢、不崩」——全部返回空值而非抛异常。"""

    def test_reads_return_none(self, monkeypatch):
        monkeypatch.setattr(cache_service, "_client", False)
        assert cache_service.cache_get("任意") is None

    def test_writes_return_false(self, monkeypatch):
        monkeypatch.setattr(cache_service, "_client", False)
        assert cache_service.cache_set("任意", {"a": 1}) is False
        assert cache_service.cache_delete("任意") is False


class TestCacheRoundtrip:
    def test_set_get_roundtrip(self, fake_cache):
        assert cache_service.cache_set("weather:西安", {"temp": 20}) is True
        assert cache_service.cache_get("weather:西安") == {"temp": 20}

    def test_miss_returns_none(self, fake_cache):
        assert cache_service.cache_get("不存在") is None

    def test_keys_are_prefixed(self, fake_cache):
        from app.config import settings

        cache_service.cache_set("k", 1)
        assert list(fake_cache.store)[0].startswith(f"{settings.REDIS_KEY_PREFIX}:")

    def test_delete(self, fake_cache):
        cache_service.cache_set("k", 1)
        assert cache_service.cache_delete("k") is True
        assert cache_service.cache_get("k") is None


class TestStorageCRUD:
    def test_create_returns_generated_id(self, tmp_storage):
        rec = tmp_storage.create_trip("西安", "摘要", {"days": []})
        assert len(rec.trip_id) == 32
        assert tmp_storage.get_trip(rec.trip_id).destination == "西安"

    def test_to_record_out_parses_json(self, tmp_storage):
        rec = tmp_storage.create_trip("成都", "s", {"destination": "成都", "days": [{"day": 1}]})
        out = tmp_storage.to_record_out(rec)
        assert out["itinerary"]["destination"] == "成都"
        assert out["destination"] == "成都"

    def test_get_missing_returns_none(self, tmp_storage):
        assert tmp_storage.get_trip("不存在") is None

    def test_none_itinerary_becomes_empty_dict(self, tmp_storage):
        rec = tmp_storage.create_trip("西安")
        assert tmp_storage.to_record_out(rec)["itinerary"] == {}

    def test_list_and_pagination(self, tmp_storage):
        for city in ("A城", "B城", "C城"):
            tmp_storage.create_trip(city)
        assert len(tmp_storage.list_trips(limit=2)) == 2
        assert len(tmp_storage.list_trips(limit=10, offset=2)) == 1

    def test_update_overwrites_itinerary(self, tmp_storage):
        rec = tmp_storage.create_trip("西安", "old", {"v": 1})
        updated = tmp_storage.update_trip(rec.trip_id, {"v": 2})
        assert json.loads(updated.itinerary_json) == {"v": 2}
        assert tmp_storage.update_trip("不存在", {}) is None

    def test_delete(self, tmp_storage):
        rec = tmp_storage.create_trip("西安")
        assert tmp_storage.delete_trip(rec.trip_id) is True
        assert tmp_storage.get_trip(rec.trip_id) is None
        assert tmp_storage.delete_trip(rec.trip_id) is False

    def test_chinese_is_preserved(self, tmp_storage):
        rec = tmp_storage.create_trip("重庆", "山城之旅", {"note": "轻轨穿楼"})
        out = tmp_storage.to_record_out(tmp_storage.get_trip(rec.trip_id))
        assert out["itinerary"]["note"] == "轻轨穿楼"


class TestSchemas:
    def test_plan_request_defaults(self):
        r = TripPlanRequest(destination="西安")
        assert r.days == 3
        assert r.budget == 2000.0
        assert r.companions == "独自"
        assert r.preferences == ""
        assert r.image_base64 is None

    @pytest.mark.parametrize("days", [0, 31, -1])
    def test_days_out_of_range_rejected(self, days):
        with pytest.raises(ValidationError):
            TripPlanRequest(destination="西安", days=days)

    def test_budget_must_be_positive(self):
        with pytest.raises(ValidationError):
            TripPlanRequest(destination="西安", budget=0)

    def test_destination_required(self):
        with pytest.raises(ValidationError):
            TripPlanRequest()

    def test_activity_cost_accepts_number_or_text(self):
        assert Activity(place="x", cost=120).cost == 120
        assert Activity(place="x", cost="成人120元，儿童免费").cost == "成人120元，儿童免费"
        assert Activity(place="x").cost == 0

    def test_itinerary_day_defaults(self):
        d = ItineraryDay(day=1)
        assert d.morning == []
        assert d.meals == []
        assert d.lodging == ""

    def test_day_requires_positive_number(self):
        with pytest.raises(ValidationError):
            ItineraryDay(day=0)

    def test_itinerary_requires_destination(self):
        with pytest.raises(ValidationError):
            Itinerary(days=[])
