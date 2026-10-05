# ============================================
# 城市覆盖注册表（city_registry_service）
# 职责：城市名称规范化 + 覆盖等级判断的"事实来源"
# 原理：
#   - 复用 guide_catalog 的沉淀城市清单（6 城 + 别名）
#   - normalize：别名/大小写/空白 → 标准城市名
#   - 判断输入是不是"省级/直辖市级"（无法规划具体城市 → 不支持）
# ============================================
import re

from app.rag import guide_catalog


def normalize_city(raw: str) -> str:
    """名称规范化：去空白、别名/行政后缀 → 标准名；不认识的原样返回（视为动态城市）。"""
    name = re.sub(r"\s+", "", raw or "").strip()
    guide = guide_catalog.get_guide(name)
    if guide:
        return guide.city
    # 剥行政后缀再试："成都市"→"成都"（攻略里有）、"大理市"→"大理"（动态）、"大理白族自治州"→"大理"
    base = re.sub(r"(市|州|地区|盟|县)$", "", name)
    if base and base != name:
        guide = guide_catalog.get_guide(base)
        if guide:
            return guide.city
        return base
    return name


def is_settled(name: str) -> bool:
    """是否有本地攻略（A 级）。"""
    return guide_catalog.is_settled_city(name)


def all_settled() -> list[str]:
    """全部沉淀城市。"""
    return guide_catalog.all_settled_cities()


def get_guide(name: str):
    """取攻略信息（供 fallback 用）。"""
    return guide_catalog.get_guide(name)


# 省级 / 直辖市级输入特征（"四川省""陕西省""直辖市"等 → 无法规划具体城市）
_PROVINCE_PATTERNS = [
    r".+省$",
    r".+自治区$",
    r".+特别行政区$",
    r"^直辖市$",
]


def is_province_level(name: str) -> bool:
    """判断是否为省级输入（应提示用户选具体城市）。"""
    if name.endswith(("省", "自治区", "特别行政区")):
        return True
    # 直辖市名单（规划需具体区，但可作目的地……先按不支持处理）
    if name in {"北京市", "上海市", "天津市", "重庆市"}:
        return False  # 直辖市本身就是可规划的城市（重庆在攻略里）
    return any(re.match(p, name) for p in _PROVINCE_PATTERNS)
