# ============================================
# M4 测试：高德地图 + 天气 + 行程地理补全
# 验证：1) 天气接口（adcode 修复） 2) 行程景点补全 POI/坐标/图片 3) 路线耗时
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.api.main import app
from app.services import map_service

client = TestClient(app)
ok = fail = 0


def check(name: str, cond: bool, detail: str = ""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        fail += 1
        print(f"  ❌ {name}  {detail}")


print("== 1. 天气接口（西安，应解析为陕西而非黑龙江）==")
r = client.get("/api/weather/西安")
print(f"    状态: {r.status_code}")
if r.status_code == 200:
    body = r.json()
    check("adcode 为陕西西安 610100", body.get("adcode") == "610100", f"实际 {body.get('adcode')}")
    check("预报非空", len(body.get("forecasts", [])) >= 1, str(body.get("forecasts"))[:50])
    check("实时天气存在", bool(body.get("live", {}).get("weather")), str(body.get("live")))
    fc = body.get("forecasts", [])
    if fc:
        f = fc[0]
        print(f"    预报: 今日 {f.get('dayweather')} {f.get('daytemp')}~{f.get('nighttemp')}℃")
else:
    fail += 1
    print(f"    {r.text[:200]}")

print("== 2. 地理编码 ==")
g = map_service.geocode("大雁塔", "西安")
check("地理编码成功", g is not None)
if g:
    check("有经纬度", "," in g["location"], g.get("location", ""))

print("== 3. POI 搜索 ==")
pois = map_service.search_poi("西安城墙", "西安", limit=3)
check("POI 返回非空", len(pois) > 0)
if pois:
    p = pois[0]
    check("有 POI ID", bool(p["poi_id"]), str(p))
    check("有坐标", bool(p["location"]))
    print(f"    第一个: {p['name']} | POI_ID {p['poi_id']} | {p['location']}")

print("== 4. 路线规划 ==")
route = map_service.route_info("108.924306,34.258771", "109.281960,34.386214")
check("路线返回距离/耗时", route is not None and route["distance"] > 0)
if route:
    print(f"    驾车: {route['distance']/1000:.1f} km, 约 {route['duration']/60:.0f} 分钟")

print("== 5. A 级行程 + 高德补全（真实 LLM 生成）==")
r = client.post(
    "/api/trip/plan",
    json={"destination": "西安", "days": 1, "budget": 800, "companions": "独自", "preferences": "历史文化"},
)
print(f"    状态: {r.status_code}")
if r.status_code != 200:
    fail += 1
    print(f"    {r.text[:300]}")
else:
    body = r.json()
    itinerary = body["itinerary"]
    acts = [a for d in itinerary.get("days", []) for slot in ("morning", "afternoon", "evening") for a in d.get(slot, [])]
    enriched = [a for a in acts if a.get("poi_id")]
    with_loc = [a for a in acts if a.get("location")]
    with_img = [a for a in acts if a.get("image_url")]
    with_route = [a for a in acts if a.get("route_to_here")]
    check("响应含天气", body.get("weather") is not None)
    check(f"景点含 POI ID ({len(enriched)}/{len(acts)})", len(enriched) >= len(acts) * 0.5, str(acts)[:200])
    check(f"景点含坐标 ({len(with_loc)}/{len(acts)})", len(with_loc) >= len(acts) * 0.5)
    check("至少一个景点有图片", len(with_img) >= 1, f"实际 {len(with_img)}")
    check("至少一个景点有路线耗时", len(with_route) >= 1, f"实际 {len(with_route)}")
    for a in acts[:4]:
        print(f"    {a['place']} | POI {a.get('poi_id','')[:6]} | 图片 {'✅' if a.get('image_url') else '—'} | 路线 {a.get('route_to_here', {}).get('duration_min', '—')}分钟")

print(f"\n结果：通过 {ok} 项，失败 {fail} 项")
sys.exit(0 if fail == 0 else 1)
