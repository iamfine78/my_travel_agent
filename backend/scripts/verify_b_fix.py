# 快速验证修复：分级 + 候选池过滤
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import city_resolver_service, place_candidate_service

print("--- 分级 ---")
for raw in ["西安", "成都市", "四川省成都市", "大理", "大理市", "四川省", "上海市", "不存在的城市xyz"]:
    r = city_resolver_service.resolve_city(raw)
    print(f"  {raw} → {r['level']} / {r['city']} / {r['reason']}")

print("--- 候选池（大理 food 过滤酒店）---")
pool = place_candidate_service.get_candidates("大理")
bad = [it["name"] for it in pool["food"] if any(w in it["name"] for w in ("酒店", "民宿", "客栈", "宾馆"))]
print(f"  food 候选数: {len(pool['food'])}，残留酒店类: {bad}")
print("  food 示例:", [it["name"] for it in pool["food"][:5]])
