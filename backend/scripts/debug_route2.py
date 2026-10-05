# 诊断：洪崖洞→磁器口、南山一棵树→三峡博物馆 两段路线为什么失败
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from app.config import settings
from app.services import map_service

pairs = [
    ("洪崖洞民俗风貌区", "磁器口古镇"),
    ("南山一棵树观景台", "重庆中国三峡博物馆"),
]

for a_name, b_name in pairs:
    a = map_service.search_poi(a_name, "重庆", limit=1)
    b = map_service.search_poi(b_name, "重庆", limit=1)
    if not a or not b:
        print(f"{a_name} → {b_name}: POI 缺失")
        continue
    aloc, bloc = a[0]["location"], b[0]["location"]
    print(f"\n{a_name}({aloc}) → {b_name}({bloc})")

    # 不同 strategy 都试试
    for strategy in [10, 0, 2, 3]:
        data = httpx.get(
            f"{settings.AMAP_BASE_URL}/direction/driving",
            params={"origin": aloc, "destination": bloc, "strategy": strategy, "key": settings.AMAP_WEB_KEY},
            timeout=20,
        ).json()
        paths = data.get("route", {}).get("paths") or []
        if paths:
            p = paths[0]
            print(f"  strategy={strategy}: ✅ {int(p['distance'])/1000:.1f}km / {int(p['duration'])/60:.0f}分钟")
        else:
            print(f"  strategy={strategy}: ❌ info={data.get('info')} message={data.get('message','')}")
