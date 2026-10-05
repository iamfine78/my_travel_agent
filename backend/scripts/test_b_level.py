# ============================================
# B 级动态城市测试：城市分级 + 候选池 + POI ID 白名单防幻觉
# 用法：& $py -X utf8 backend/scripts/test_b_level.py *> _b_out.txt
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.schemas import TripPlanRequest
from app.services import city_resolver_service, place_candidate_service
from app.services import trip_service

# ---- Part 1: 城市分级 ----
print("=" * 40)
print("Part 1: 城市分级")
for raw in ["西安", "大理", "四川省", "四川省成都市", "不存在的城市xyz"]:
    r = city_resolver_service.resolve_city(raw)
    print(f"  {raw} → level={r['level']} city={r['city']} 理由={r['reason']}")

# ---- Part 2: B 级候选池 ----
print("=" * 40)
print("Part 2: B 级候选池（大理）")
pool = place_candidate_service.get_candidates("大理")
for key in ("scenic", "food", "lodging"):
    items = pool[key]
    print(f"  {key}: {len(items)} 个")
    for it in items[:3]:
        print(f"    {it['name']} | {it['poi_id']} | {it['address'][:30]}")

# ---- Part 3: 完整生成 + 池外校验 ----
print("=" * 40)
print("Part 3: 动态生成（大理 1 天）→ 校验池外拒绝")
req = TripPlanRequest(
    destination="大理", days=1, budget=600, companions="2人",
    preferences="节奏：轻松；住宿：舒适型；旅行偏好：洱海、古城、美食",
)
resp = trip_service.plan_trip(req)
print(f"来源: {resp.sources}")
print(f"目的地: {resp.destination}")
for d in resp.itinerary.get("days", []):
    print(f"  第{d['day']}天 住宿: {d.get('lodging', '')[:40]}")
    for k in ("morning", "afternoon", "evening"):
        for a in d.get(k, []):
            pid = a.get("poi_id", "无ID")
            in_pool = place_candidate_service.is_valid_poi(pool, pid, a.get("place", ""))
            flag = "✅池内" if in_pool else "❌池外"
            print(f"    [{flag}] {a['place']} (poi_id={pid[:20]})")
print("完成")
