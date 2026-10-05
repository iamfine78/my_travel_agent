# 验证新字段：真实生成一次，检查 play_guide（怎么玩）+ lodging（住宿）是否输出
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)

r = client.post(
    "/api/trip/plan",
    json={"destination": "重庆", "days": 1, "budget": 800, "companions": "2人", "preferences": "节奏：轻松；住宿：舒适型；旅行偏好：美食、夜景"},
)
print(f"状态: {r.status_code}")
if r.status_code != 200:
    print(r.text[:500])
    sys.exit(1)

body = r.json()
itin = body["itinerary"]
acts = [a for d in itin.get("days", []) for k in ("morning", "afternoon", "evening") for a in d.get(k, [])]
play_ok = sum(1 for a in acts if a.get("play_guide"))
lodging_ok = sum(1 for d in itin.get("days", []) if d.get("lodging"))
print(f"景点数: {len(acts)} | 有游玩建议: {play_ok}/{len(acts)} | 有住宿安排: {lodging_ok}/{len(itin.get('days', []))} 天")

# 展示前 3 个景点
print("\n示例：")
for d in itin.get("days", []):
    print(f"  第{d['day']}天 住宿: {d.get('lodging', '')[:60]}")
    for k in ("morning", "afternoon", "evening"):
        for a in d.get(k, [])[:1]:
            print(f"    {a['place']} | 怎么玩: {a.get('play_guide', '')[:50]}")
