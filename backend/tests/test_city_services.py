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
        assert len(settled) == 6
        assert set(settled) == {"西安", "成都", "北京", "上海", "杭州", "重庆"}

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
        monkeypatch.setattr(resolver, "_amap_district", lambda city: ("532900", True))
        r = resolver.resolve_city("大理")
        assert r["level"] == "B"
        assert r["city"] == "大理"
        assert r["adcode"] == "532900"

    def test_level_c_insufficient_data(self, monkeypatch):
        monkeypatch.setattr(resolver, "_amap_district", lambda city: ("", False))
        r = resolver.resolve_city("桃花源")
        assert r["level"] == "C"
