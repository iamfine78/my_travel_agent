# ============================================
# 地图服务测试（离线）
# 覆盖：POI 返回契约、缺字段容错（曾因 formatted_address 缺键 KeyError）
# ============================================
import pytest

from app.services import map_service, weather_service


def _fake_poi(**overrides) -> dict:
    poi = {
        "poi_id": "P1",
        "name": "某景点",
        "address": "",
        "formatted_address": "",
        "image_url": "",
        "location": "108.9,34.2",
        "lng": "108.9",
        "lat": "34.2",
        "open_time": "",
        "rating": "",
        "cityname": "西安",
        "adname": "",
    }
    poi.update(overrides)
    return poi


class TestAmapBusinessErrors:
    """回归：高德用 HTTP 200 + status="0" 表达业务错误（Key 无效、配额超限），
    不检查业务状态位就会把「配额用完了」静默当成「这里没有数据」。"""

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    @pytest.mark.parametrize("payload", [
        {"status": "0", "info": "INVALID_USER_KEY"},
        {"status": "0", "info": "DAILY_QUERY_OVER_LIMIT"},
        {"info": "OK"},                       # 缺 status 字段
    ])
    @pytest.mark.parametrize("module", [map_service, weather_service])
    def test_business_error_raises(self, monkeypatch, module, payload):
        monkeypatch.setattr(module.httpx, "get", lambda *a, **k: self._Resp(payload))
        with pytest.raises(RuntimeError, match="高德业务错误"):
            module._amap_get("place/text", {})

    @pytest.mark.parametrize("module", [map_service, weather_service])
    def test_success_passes_through(self, monkeypatch, module):
        payload = {"status": "1", "pois": []}
        monkeypatch.setattr(module.httpx, "get", lambda *a, **k: self._Resp(payload))
        assert module._amap_get("place/text", {})["status"] == "1"


class TestSearchPoiCaching:
    """回归：空结果曾被写进缓存，把「兵马俑查不到」这种错误放大到整个 TTL。"""

    def test_empty_result_is_not_cached(self, monkeypatch, fake_cache):
        monkeypatch.setattr(map_service, "_amap_get", lambda *a, **k: {"status": "1", "pois": []})
        assert map_service.search_poi("查不到的地点", "测试城", limit=1) == []
        assert not [k for k in fake_cache.store if "查不到的地点" in k], "空结果不应进缓存"

    def test_non_empty_result_is_cached(self, monkeypatch, fake_cache):
        raw = [{"id": "P1", "name": "某景点", "address": "a", "location": "1,2",
                "photos": [], "biz_ext": {}}]
        monkeypatch.setattr(map_service, "_amap_get", lambda *a, **k: {"status": "1", "pois": raw})
        assert map_service.search_poi("某景点", "测试城", limit=1)
        assert [k for k in fake_cache.store if "某景点" in k], "有结果时应缓存"


class TestSearchPoiContract:
    def test_search_poi_provides_formatted_address(self, monkeypatch, fake_cache):
        """search_poi 的返回字典必须含 formatted_address —— 曾因缺此键导致下游 KeyError。"""
        raw = [{"id": "X", "name": "某景点", "address": "", "location": "1,2", "photos": [], "biz_ext": {}}]
        monkeypatch.setattr(map_service, "_amap_get", lambda *a, **k: {"pois": raw})
        pois = map_service.search_poi("某景点", "西安", limit=1)
        assert pois
        assert "formatted_address" in pois[0]


class TestEnrichActivity:
    def test_tolerates_empty_poi_address(self, monkeypatch):
        monkeypatch.setattr(map_service, "search_poi", lambda *a, **k: [_fake_poi()])
        activity = map_service.enrich_activity({"place": "某景点", "location": "108.9,34.2"}, "西安")
        assert activity["address"] == ""
        assert activity["poi_id"] == "P1"

    def test_tolerates_poi_dict_without_address_keys(self, monkeypatch):
        """POI 来源变化导致字典缺 address / formatted_address 时也不应崩。"""
        poi = {"poi_id": "P2", "name": "某景点", "image_url": "", "location": "1,2", "lng": "1", "lat": "2"}
        monkeypatch.setattr(map_service, "search_poi", lambda *a, **k: [poi])
        activity = map_service.enrich_activity({"place": "某景点", "location": "1,2"}, "西安")
        assert activity["address"] == ""
        assert activity["poi_id"] == "P2"

    def test_keeps_activity_when_no_poi_found(self, monkeypatch):
        monkeypatch.setattr(map_service, "search_poi", lambda *a, **k: [])
        original = {"place": "查不到的景点", "location": "1,2"}
        assert map_service.enrich_activity(original, "西安") == original

    def test_empty_place_returns_unchanged(self, monkeypatch):
        called = []
        monkeypatch.setattr(map_service, "search_poi", lambda *a, **k: called.append(1) or [])
        assert map_service.enrich_activity({"place": ""}, "西安") == {"place": ""}
        assert called == []  # 名称为空时不应发起检索
