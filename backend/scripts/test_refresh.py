# 验证 refresh 接口：造一条缺车程的旧数据 → 调用 refresh → 检查补全
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.api.main import app
from app.services import storage_service

client = TestClient(app)

# 1. 保存一条"旧数据"（景点只有名字，没有坐标/车程——模拟修复前的旧版本）
old_itinerary = {
    "destination": "杭州",
    "summary": "旧版本测试",
    "days": [
        {
            "day": 1,
            "morning": [{"place": "灵隐寺·飞来峰"}, {"place": "雷峰塔"}, {"place": "净慈寺"}],
            "afternoon": [],
            "evening": [],
        }
    ],
}
r = client.post("/api/trip", json={"destination": "杭州", "summary": "旧版本测试", "itinerary_json": old_itinerary})
assert r.status_code == 201, r.text
trip_id = r.json()["trip_id"]
print(f"已保存旧数据 trip_id={trip_id[:8]}")

# 2. 补全前检查：无坐标/车程
before = client.get(f"/api/trip/{trip_id}").json()
b0 = before["itinerary"]["days"][0]["morning"]
print(f"补全前: 第1个景点 location={bool(b0[0].get('location'))}, route={bool(b0[1].get('route_to_here'))}")

# 3. 调用 refresh
r2 = client.post(f"/api/trip/{trip_id}/refresh")
assert r2.status_code == 200, r2.text
after = r2.json()
acts = after["itinerary"]["days"][0]["morning"]
print("补全后:")
for i, a in enumerate(acts, 1):
    rt = a.get("route_to_here")
    print(f"  {i}. {a['place']} | 坐标 {a.get('location','无')[:22]} | 车程 {rt['duration_min'] if rt else '—'}分钟")

# 4. 验证数据库已更新（重新 GET 确认持久化）
after_get = client.get(f"/api/trip/{trip_id}").json()
a2 = after_get["itinerary"]["days"][0]["morning"]
persisted = all(a.get("location") for a in a2) and bool(a2[1].get("route_to_here"))
print(f"持久化验证: {'✅ 已写入数据库' if persisted else '❌ 未持久化'}")

# 5. 清理
client.delete(f"/api/trip/{trip_id}")
print("测试数据已清理")
