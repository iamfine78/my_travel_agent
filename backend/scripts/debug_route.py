# ============================================
# 调试：为什么天坛/北海公园车程显示 "—"
# 验证：POI 匹配是否成功（有坐标？）→ 高德驾车路线是否返回
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import map_service

print("== 1. POI 匹配 ==")
for name in ["天坛公园", "北海公园", "奥林匹克公园（鸟巢·水立方外景）", "前门大街·大栅栏"]:
    pois = map_service.search_poi(name, "北京", limit=1)
    if pois:
        p = pois[0]
        print(f"  {name} → {p['name']} | {p['location']} | 地址: {p['address'][:20]}")
    else:
        print(f"  {name} → ❌ 无 POI 结果")

print("== 2. 高德驾车路线（模拟 enrich 的相邻计算）==")
# 用实际 POI 坐标复现：奥林匹克公园 → 天坛公园；前门 → 北海
olympic = map_service.search_poi("奥林匹克公园", "北京", limit=1)
tiantan = map_service.search_poi("天坛公园", "北京", limit=1)
qianmen = map_service.search_poi("前门大街", "北京", limit=1)
beihai = map_service.search_poi("北海公园", "北京", limit=1)

pairs = [
    ("奥林匹克公园 → 天坛公园", olympic, tiantan),
    ("前门大街 → 北海公园", qianmen, beihai),
    ("天坛公园 → 国家博物馆", tiantan, map_service.search_poi("国家博物馆", "北京", limit=1)),
]
for label, a, b in pairs:
    if not a or not b:
        print(f"  {label}: ❌ POI 缺失 a={bool(a)} b={bool(b)}")
        continue
    r = map_service.route_info(a[0]["location"], b[0]["location"])
    if r:
        print(f"  {label}: ✅ {r['distance']/1000:.1f}km / {r['duration']/60:.0f}分钟")
    else:
        print(f"  {label}: ❌ 路线返回 None（高德接口失败）")
        # 打印原始响应定位原因
        import httpx
        from app.config import settings
        resp = httpx.get(
            f"{settings.AMAP_BASE_URL}/direction/driving",
            params={"origin": a[0]["location"], "destination": b[0]["location"], "strategy": 10, "key": settings.AMAP_WEB_KEY},
            timeout=20,
        )
        raw = resp.json()
        print(f"     原始响应 status={raw.get('status')} info={raw.get('info')} 有route={bool(raw.get('route'))}")
