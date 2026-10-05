# ============================================
# 攻略文件目录（guide_catalog）
# 职责：维护"目的地 → 攻略文件"的映射与攻略元信息
# 原理：把 data/*_guide.md 的清单集中在一处管理，
#       城市解析服务(A/B 分级)用这里的沉淀城市列表判断"有没有攻略"
# ============================================
from pathlib import Path

from app.config import settings

# 攻略数据目录：backend/data/
DATA_DIR = Path(settings.BASE_DIR) / "data"


class GuideInfo:
    """一份攻略的元信息。"""

    def __init__(self, city: str, file_name: str, alias: list[str] | None = None):
        self.city = city            # 标准城市名（沉淀城市）
        self.file_name = file_name  # 攻略文件名
        self.alias = alias or []    # 别名/常用称呼（如"西安"别名"长安"）
        self.path = DATA_DIR / file_name

    @property
    def exists(self) -> bool:
        return self.path.exists()


# 沉淀城市清单（A 级：有本地攻略的城市）
# 别名用于 city_resolver 的名称规范化匹配
GUIDE_CATALOG: list[GuideInfo] = [
    GuideInfo("西安", "xian_guide.md", ["长安", "古都西安"]),
    GuideInfo("成都", "chengdu_guide.md", ["蓉城"]),
    GuideInfo("北京", "beijing_guide.md", ["帝都", "京城"]),
    GuideInfo("上海", "shanghai_guide.md", ["魔都", "沪"]),
    GuideInfo("杭州", "hangzhou_guide.md", ["临安", "钱塘"]),
    GuideInfo("重庆", "chongqing_guide.md", ["山城", "渝"]),
]

# 城市名 → 攻略信息 的快速索引（含别名）
_CITY_INDEX: dict[str, GuideInfo] = {}
for _g in GUIDE_CATALOG:
    _CITY_INDEX[_g.city] = _g
    for _a in _g.alias:
        _CITY_INDEX[_a] = _g


def is_settled_city(name: str) -> bool:
    """判断某城市是否为'沉淀城市'（有攻略覆盖）。"""
    return name in _CITY_INDEX


def get_guide(name: str) -> GuideInfo | None:
    """按城市名（含别名）取攻略信息；没有返回 None。"""
    return _CITY_INDEX.get(name)


def all_settled_cities() -> list[str]:
    """返回全部沉淀城市名，供城市解析展示覆盖范围。"""
    return [g.city for g in GUIDE_CATALOG]


def load_guide_text(name: str) -> str:
    """读取某城市攻略全文（入库与检索用）。"""
    guide = get_guide(name)
    if guide is None or not guide.exists:
        return ""
    return guide.path.read_text(encoding="utf-8")
