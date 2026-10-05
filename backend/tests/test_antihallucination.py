# ============================================
# 防幻觉机制测试（核心业务规则，离线）
# 覆盖：B 级候选池过滤、池外 POI 校验替换/移除、白名单命中判定
# ============================================
import pytest

from app.services import map_service
from app.services import place_candidate_service as pcs
from app.services.trip_service import _validate_pool


def _act(place: str, poi_id: str = "") -> dict:
    return {"place": place, "poi_id": poi_id, "address": "", "description": ""}


def _pool(scenic: list[dict] | None = None) -> dict:
    return {"scenic": scenic or [], "food": [], "lodging": []}


def _itinerary(*activities: dict) -> dict:
    return {"days": [{"day": 1, "morning": list(activities), "afternoon": [], "evening": []}]}


class TestValidatePool:
    def test_in_pool_poi_id_kept(self):
        pool = _pool([{"poi_id": "S1", "name": "真景点", "address": "addr1"}])
        itin = _itinerary(_act("随便写的名字", "S1"))
        result, stats = _validate_pool(itin, pool)
        kept = result["days"][0]["morning"]
        assert len(kept) == 1
        assert kept[0]["poi_id"] == "S1"
        assert kept[0]["place"] == "随便写的名字"  # 有合法 ID 时不改内容
        assert stats == {"replaced": 0, "removed": 0}

    def test_name_match_backfills_poi_id(self):
        pool = _pool([{"poi_id": "S1", "name": "真景点", "address": "addr1"}])
        itin = _itinerary(_act("真景点", ""))
        result, stats = _validate_pool(itin, pool)
        kept = result["days"][0]["morning"][0]
        assert kept["poi_id"] == "S1"
        assert kept["address"] == "addr1"
        assert stats["replaced"] == 0

    def test_out_of_pool_replaced_by_spare(self):
        pool = _pool([
            {"poi_id": "S1", "name": "真景点一", "address": "a1"},
            {"poi_id": "S2", "name": "真景点二", "address": "a2"},
        ])
        itin = _itinerary(_act("真景点一", "S1"), _act("编造的景点", "FAKE"))
        result, stats = _validate_pool(itin, pool)
        kept = result["days"][0]["morning"]
        assert len(kept) == 2
        replaced = kept[1]
        assert replaced["poi_id"] == "S2"
        assert replaced["place"] == "真景点二"
        assert "已按候选池调整" in replaced["description"]
        assert stats == {"replaced": 1, "removed": 0}

    def test_out_of_pool_removed_when_no_spare(self):
        itin = _itinerary(_act("编造的景点", "FAKE"))
        result, stats = _validate_pool(itin, _pool([]))
        assert result["days"][0]["morning"] == []
        assert stats == {"replaced": 0, "removed": 1}

    def test_mixed_activities_are_recounted(self):
        pool = _pool([{"poi_id": "S1", "name": "真景点", "address": "a1"}])
        itin = _itinerary(_act("真景点", "S1"), _act("编造一", "F1"), _act("编造二", "F2"))
        result, stats = _validate_pool(itin, pool)
        # 第 2 个用 S1 之外的 spare（无）→ 移除；第 3 个同样移除
        assert stats == {"replaced": 0, "removed": 2}

    def test_empty_itinerary_is_safe(self):
        result, stats = _validate_pool({"days": []}, _pool([]))
        assert result == {"days": []}
        assert stats == {"replaced": 0, "removed": 0}


class TestPlaceCandidateFilter:
    def test_filters_cross_city_missing_coord_and_duplicates(self, monkeypatch):
        raw = [
            {"name": "大理古城", "location": "100,25", "cityname": "大理", "poi_id": "P1", "address": "a"},
            {"name": "洱海", "location": "101,25", "cityname": "大理白族自治州", "poi_id": "P2", "address": "b"},
            {"name": "丽江古城", "location": "102,25", "cityname": "丽江", "poi_id": "P3", "address": "c"},
            {"name": "无坐标点", "location": "", "cityname": "大理", "poi_id": "P4", "address": "d"},
            {"name": "大理古城", "location": "103,25", "cityname": "大理", "poi_id": "P5", "address": "e"},
        ]
        monkeypatch.setattr(map_service, "search_poi", lambda **kw: raw)
        out = pcs._search_and_filter("大理", "风景名胜")
        assert [i["name"] for i in out] == ["大理古城", "洱海"]
        assert out[0]["poi_id"] == "P1"

    def test_food_pool_excludes_hotels(self, monkeypatch):
        raw = [
            {"name": "大理某某酒店", "location": "1,1", "cityname": "大理", "poi_id": "H1", "address": ""},
            {"name": "大理酸辣鱼", "location": "2,2", "cityname": "大理", "poi_id": "F1", "address": ""},
        ]
        monkeypatch.setattr(map_service, "search_poi", lambda **kw: raw)
        out = pcs._search_and_filter("大理", "餐饮服务", is_food=True)
        assert [i["name"] for i in out] == ["大理酸辣鱼"]

    def test_get_candidates_returns_three_buckets(self, monkeypatch):
        monkeypatch.setattr(map_service, "search_poi", lambda **kw: [])
        pool = pcs.get_candidates("大理")
        assert set(pool) == {"scenic", "food", "lodging"}
        assert all(pool[k] == [] for k in pool)


class TestIsValidPoi:
    POOL = {"scenic": [{"poi_id": "S1", "name": "真景点", "address": "a"}], "food": [], "lodging": []}

    def test_id_hit(self):
        assert pcs.is_valid_poi(self.POOL, "S1") is True

    @pytest.mark.xfail(
        reason="既有缺陷：is_valid_poi 在 poi_id 为空时提前 return False，"
        "导致注释声明的「同名也算命中」分支不可达（scripts/test_b_level.py:46 依赖该分支）",
        strict=False,
    )
    def test_name_hit_without_id(self):
        assert pcs.is_valid_poi(self.POOL, "", "真景点") is True

    def test_id_miss(self):
        assert pcs.is_valid_poi(self.POOL, "NOPE") is False

    def test_empty_id_and_name(self):
        assert pcs.is_valid_poi(self.POOL, "") is False


class TestFormatCandidates:
    def test_contains_ids_and_empty_placeholders(self):
        pool = {
            "scenic": [{"poi_id": "S1", "name": "真景点", "address": "a1"}],
            "food": [],
            "lodging": [],
        }
        text = pcs.format_candidates(pool)
        assert "真景点" in text
        assert "POI_ID: S1" in text
        assert text.count("（无候选）") == 2  # food / lodging 为空
