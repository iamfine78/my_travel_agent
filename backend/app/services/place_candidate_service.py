# ============================================
# 动态城市候选池服务（place_candidate_service）
# 职责：B 级城市（无攻略）→ 从高德拉真实 POI 候选池，
#       生成时只允许 Planner 从候选池里选（POI ID 白名单，防幻觉）
# 原理：
#   1. 按类型搜 POI（景点/餐饮/住宿），city 限定避免跨城污染
#   2. 过滤：跨城市、无坐标、重复名称
#   3. 校验最低候选覆盖（不够则记录，前端/日志可见）
# ============================================
import logging

from app.services import map_service

logger = logging.getLogger(__name__)

# 高德 POI 类型 → 我们的分类
PLACE_TYPES = {
    "scenic": "风景名胜",   # 景点
    "food": "餐饮服务",     # 餐饮
    "lodging": "住宿服务",  # 住宿
}

# 最低候选覆盖：不足说明高德对该城数据少，降级处理
MIN_COVERAGE = {"scenic": 4, "food": 4, "lodging": 2}

# 餐饮候选反向过滤：高德"餐饮服务"类目偶尔混入酒店民宿
_FOOD_EXCLUDE = ("酒店", "民宿", "客栈", "宾馆", "旅店", "招待所")


def get_candidates(city: str) -> dict:
    """拉取某城市三类候选池。返回 {"scenic": [...], "food": [...], "lodging": [...]}。

    候选条目：{poi_id, name, address, location, image_url, type}
    """
    pool = {}
    for key, poi_type in PLACE_TYPES.items():
        items = _search_and_filter(city, poi_type, is_food=(key == "food"))
        pool[key] = items
        if len(items) < MIN_COVERAGE[key]:
            logger.warning(f"候选池不足: {city}/{key} 仅 {len(items)} 个（最低 {MIN_COVERAGE[key]}）")
    return pool


def _search_and_filter(city: str, poi_type: str, is_food: bool = False) -> list[dict]:
    """搜索 + 过滤：跨城市 / 无坐标 / 重复名称 / 餐饮池剔除酒店。"""
    pois = map_service.search_poi(keywords=city, city=city, poi_type=poi_type, limit=20)

    seen: set[str] = set()
    result: list[dict] = []
    for p in pois:
        if not p.get("location"):
            continue
        # 跨城市过滤：POI 所在城市必须匹配目标城市（防"大理"搜出"大理州其他县"）
        cityname = p.get("cityname") or p.get("adname") or ""
        if cityname and city not in cityname:
            continue
        name = p.get("name", "")
        if not name or name in seen:
            continue
        if is_food and any(w in name for w in _FOOD_EXCLUDE):
            continue
        seen.add(name)
        result.append(
            {
                "poi_id": p.get("poi_id", ""),
                "name": name,
                "address": p.get("address", ""),
                "location": p.get("location", ""),
                "image_url": p.get("image_url", ""),
                "type": poi_type,
            }
        )
    return result


def format_candidates(pool: dict) -> str:
    """把候选池格式化成给 LLM 的文本（带编号，方便引用 POI ID）。"""
    lines = ["以下是从真实地图数据中获取的候选地点，只能从中选择："]
    for key, label in [("scenic", "景点"), ("food", "餐饮"), ("lodging", "住宿")]:
        items = pool.get(key, [])
        lines.append(f"【{label}候选】")
        for i, it in enumerate(items, 1):
            addr = it["address"] or ""
            lines.append(f"{i}. {it['name']}（POI_ID: {it['poi_id']}，地址：{addr}）")
        if not items:
            lines.append("（无候选）")
    return "\n".join(lines)


def is_valid_poi(pool: dict, poi_id: str, name: str = "") -> bool:
    """校验一个 POI 是否在候选池内（白名单命中）。

    命中条件二选一：POI ID 与池内条目相同，或名称与池内条目相同
    （LLM 有时不带 ID，但名字对得上也算命中）。
    注意：判空不能提前 return——否则「只有名字、没有 ID」的调用永远命中不了。
    """
    for key in pool:
        for it in pool[key]:
            if poi_id and it["poi_id"] == poi_id:
                return True
            if name and it["name"] == name:
                return True
    return False
