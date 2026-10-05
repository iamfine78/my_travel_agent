# 复现杭州景点 enrich，检查雷峰塔等为什么没车程
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import map_service

spots = [
    '灵隐寺·飞来峰', '龙井村茶田', '九溪烟树',
    '湖滨步行街·西湖音乐喷泉', '雷峰塔', '净慈寺', '苏堤春晓·花港观鱼',
]
itinerary = {'days': [{'day': 1, 'morning': [{'place': s} for s in spots], 'afternoon': [], 'evening': []}]}
out = map_service.enrich_itinerary(itinerary, '杭州')
for i, a in enumerate(out['days'][0]['morning'], 1):
    r = a.get('route_to_here')
    print(f"  {i}. {a['place']} | 坐标 {a.get('location', '无')[:22]} | 车程 {r['duration_min'] if r else '—'}分钟 | 地址 {a.get('address', '')[:18]}")
