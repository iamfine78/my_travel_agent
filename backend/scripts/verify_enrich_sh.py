# 复现上海 9 景点 enrich，检查第 7 个为什么没车程
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import map_service

spots = [
    '外滩', '南京东路步行街', '豫园', '城隍庙商圈', '浦江夜游轮',
    '外滩观景平台', '武康路—安福路梧桐区', '武康大楼周边咖啡小憩', '上海博物馆（人民广场馆）',
]
itinerary = {'days': [{'day': 1, 'morning': [{'place': s} for s in spots], 'afternoon': [], 'evening': []}]}
out = map_service.enrich_itinerary(itinerary, '上海')
for i, a in enumerate(out['days'][0]['morning'], 1):
    r = a.get('route_to_here')
    print(f"  {i}. {a['place']} | 坐标 {a.get('location', '无')[:22]} | 车程 {r['duration_min'] if r else '—'}分钟 | 地址 {a.get('address', '')[:15]}")
