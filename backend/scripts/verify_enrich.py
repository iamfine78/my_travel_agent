# 验证 route 重试修复：完整模拟 enrich 北京 7 景点
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import map_service

spots = ['颐和园', '颐和园·昆明湖/西堤', '奥林匹克公园（鸟巢·水立方外景）', '天坛公园', '国家博物馆', '前门大街·大栅栏', '北海公园']
itinerary = {'days': [{'day': 1, 'morning': [{'place': s} for s in spots], 'afternoon': [], 'evening': []}]}
out = map_service.enrich_itinerary(itinerary, '北京')
for a in out['days'][0]['morning']:
    r = a.get('route_to_here')
    loc = a.get('location', '')
    print(f"  {a['place']} | 坐标 {loc[:25] or '无'} | 车程 {r['duration_min'] if r else '—'}分钟")
