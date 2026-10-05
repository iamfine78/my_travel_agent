# ============================================
# 城市分级与解析测试（离线）
# 覆盖：名称规范化/别名、沉淀城市判定、省级识别、A/B/C/D 四级分流
# ============================================
import pytest

from app.services import city_registry_service as registry
from app.services import city_resolver_service as resolver


class TestNormalizeCity:
    def test_alias_maps_to_standard_name(self):
        assert registry.normalize_city("长安") == "西安"
        assert registry.normalize_city("魔都") == "上海"
        assert registry.normalize_city("蓉城") == "成都"

    def test_strip_city_suffix(self):
        assert registry.normalize_city("成都市") == "成都"
        assert registry.normalize_city("上海市") == "上海"

    def test_strip_suffix_for_dynamic_city(self):
        # 无攻略的动态城市也要能剥掉行政后缀
        assert registry.normalize_city("大理市") == "大理"

    def test_unknown_city_passthrough(self):
        assert registry.normalize_city("大理") == "大理"
        assert registry.normalize_city("某个小城") == "某个小城"

    def test_blank_input(self):
        assert registry.normalize_city("") == ""
        assert registry.normalize_city(None) == ""

    def test_whitespace_removed(self):
        assert registry.normalize_city("  西 安 ") == "西安"


class TestSettledCity:
    def test_settled(self):
        assert registry.is_settled("西安") is True
        assert registry.is_settled("重庆") is True

    def test_not_settled(self):
        assert registry.is_settled("大理") is False

    def test_all_settled_is_six_cities(self):
        settled = registry.all_settled()
        assert len(settled) == 14
        assert set(settled) == {
            "西安", "成都", "北京", "上海", "杭州", "重庆",
            "南京", "苏州", "广州", "武汉", "长沙", "厦门", "青岛", "昆明",
        }

    def test_get_guide_returns_none_for_unknown(self):
        assert registry.get_guide("大理") is None
        assert registry.get_guide("成都").city == "成都"


class TestProvinceLevel:
    @pytest.mark.parametrize("name", ["四川省", "陕西省", "广西壮族自治区", "香港特别行政区"])
    def test_province_inputs(self, name):
        assert registry.is_province_level(name) is True

    @pytest.mark.parametrize("name", ["成都", "西安", "大理"])
    def test_city_inputs(self, name):
        assert registry.is_province_level(name) is False

    @pytest.mark.parametrize("name", ["北京市", "上海市", "天津市", "重庆市"])
    def test_municipalities_are_plannable(self, name):
        # 直辖市本身就是可规划城市（重庆在攻略里），不算省级输入
        assert registry.is_province_level(name) is False


class TestExtractCityName:
    def test_extract_after_province(self):
        assert resolver._extract_city_name("四川省成都市") == "成都市"
        assert resolver._extract_city_name("陕西省西安市") == "西安市"

    def test_plain_city_unchanged(self):
        assert resolver._extract_city_name("西安") == "西安"
        assert resolver._extract_city_name("大理白族自治州") == "大理白族自治州"

    def test_province_only_no_extract(self):
        # 只有省名、没有具体城市 → 原样返回（后面会被判为 D 级）
        assert resolver._extract_city_name("四川省") == "四川省"


class TestResolveCity:
    def test_level_a_settled_city(self):
        r = resolver.resolve_city("西安")
        assert r["level"] == "A"
        assert r["city"] == "西安"

    def test_level_a_via_alias(self):
        assert resolver.resolve_city("长安")["level"] == "A"

    def test_level_a_city_with_suffix(self):
        assert resolver.resolve_city("成都市")["level"] == "A"

    def test_level_d_province_rejected(self):
        r = resolver.resolve_city("四川省")
        assert r["level"] == "D"
        assert "具体城市" in r["reason"]

    def test_level_d_province_with_city_is_actually_a(self):
        # "四川省成都市" 应提取出成都市 → A 级
        r = resolver.resolve_city("四川省成都市")
        assert r["level"] == "A"
        assert r["city"] == "成都"

    def test_level_b_dynamic_city(self, monkeypatch):
        monkeypatch.setattr(resolver, "_amap_district", lambda city: resolver.DistrictResult("532901", True))
        r = resolver.resolve_city("大理")
        assert r["level"] == "B"
        assert r["city"] == "大理"
        assert r["adcode"] == "532901"

    def test_level_c_insufficient_data(self, monkeypatch):
        monkeypatch.setattr(resolver, "_amap_district", lambda city: resolver.DistrictResult("", False))
        r = resolver.resolve_city("桃花源")
        assert r["level"] == "C"
        assert "资料不足" in r["reason"]

    def test_amap_failure_is_reported_as_failure_not_missing(self, monkeypatch):
        """回归：高德调用失败曾与「确实查不到」返回同一个结果，
        真实城市会被静默说成资料不足（实测漏过咸阳）。"""
        monkeypatch.setattr(resolver, "_amap_district", lambda city: resolver.DistrictResult("", False, failed=True))
        r = resolver.resolve_city("咸阳")
        assert r["level"] == "C"
        assert "高德查询失败" in r["reason"]
        assert "资料不足" not in r["reason"]


class TestDistrictRequest:
    """回归：高德用 HTTP 200 + status=0 表达限流/鉴权错误，
    只看 HTTP 状态码会把它误读成「城市查不到」。"""

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    @pytest.mark.parametrize("payload", [
        {"status": "0", "info": "DAILY_QUERY_OVER_LIMIT"},
        {"status": "0", "info": "INVALID_USER_KEY"},
        {"info": "OK"},                     # 缺 status 字段
    ])
    def test_business_error_status_is_a_failure(self, monkeypatch, payload):
        monkeypatch.setattr(resolver.httpx, "get", lambda *a, **k: self._Resp(payload))
        monkeypatch.setattr(resolver.time, "sleep", lambda *_: None)
        assert resolver._district_request("丽江") is None

    def test_success_returns_payload(self, monkeypatch):
        payload = {"status": "1", "info": "OK", "districts": [{"name": "丽江市"}]}
        monkeypatch.setattr(resolver.httpx, "get", lambda *a, **k: self._Resp(payload))
        assert resolver._district_request("丽江") is payload

    def test_network_error_retries_once(self, monkeypatch):
        calls = []

        def boom(*a, **k):
            calls.append(1)
            raise RuntimeError("network down")

        monkeypatch.setattr(resolver.httpx, "get", boom)
        monkeypatch.setattr(resolver.time, "sleep", lambda *_: None)
        assert resolver._district_request("丽江") is None
        assert len(calls) == 2, "应重试一次再放弃"


class TestPickCityDistrict:
    """回归：高德对同一关键词会返回多条同名区县，不能盲取 districts[0]。"""

    def test_picks_real_city_over_same_named_districts(self):
        # 高德查「西安」的真实返回：两条吉林/黑龙江的「西安区」在前，「西安市」在后
        districts = [
            {"name": "西安区", "adcode": "220403", "level": "district"},
            {"name": "西安区", "adcode": "231005", "level": "district"},
            {"name": "西安市", "adcode": "610100", "level": "city"},
        ]
        assert resolver._pick_city_district(districts, "西安")["adcode"] == "610100"

    def test_prefers_city_over_prefecture(self):
        # 「大理」应先取「大理市」(532901)，而不是「大理白族自治州」(532900)，
        # 否则 adcode 过滤会放行州内其他县
        districts = [
            {"name": "大理白族自治州", "adcode": "532900", "level": "city"},
            {"name": "大理市", "adcode": "532901", "level": "district"},
        ]
        assert resolver._pick_city_district(districts, "大理")["adcode"] == "532901"

    def test_falls_back_to_prefecture_when_no_same_named_city(self):
        # 「阿坝」没有同名市，退回州级
        districts = [{"name": "阿坝藏族羌族自治州", "adcode": "513200", "level": "city"}]
        assert resolver._pick_city_district(districts, "阿坝")["adcode"] == "513200"

    def test_tolerates_input_with_admin_suffix(self):
        # 输入本身带后缀时，靠"去后缀比较"兜住（仅限城市级条目）
        districts = [{"name": "大理白族自治州", "adcode": "532900", "level": "city"}]
        assert resolver._pick_city_district(districts, "大理白族自治州")["adcode"] == "532900"

    def test_returns_none_for_empty_or_unknown(self):
        assert resolver._pick_city_district([], "西安") is None

    def test_never_picks_county_level_entry_as_city(self):
        """只有区县级同名条目时，不能把它当成城市 —— 这正是「西安」被误判的根因。"""
        only_districts = [{"name": "西安区", "adcode": "220403", "level": "district"}]
        assert resolver._pick_city_district(only_districts, "西安") is None
        # 但同时要保证：有真正的「西安市」时能选中它（见上一条用例）
