# ============================================
# M2 补测：自然语言智能编辑（真实 LLM）
# 流程：保存一条行程 → 用一句话编辑 → 校验新结构
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)

print("== 1. 保存一条行程 ==")
r = client.post(
    "/api/trip",
    json={
        "destination": "成都",
        "summary": "2天美食之旅",
        "itinerary_json": {
            "destination": "成都",
            "days": [
                {
                    "day": 1,
                    "date_hint": "第1天",
                    "morning": [{"place": "宽窄巷子", "description": "逛古街"}],
                    "afternoon": [{"place": "人民公园", "description": "喝茶"}],
                    "evening": [{"place": "锦里", "description": "夜景"}],
                    "meals": ["火锅"],
                    "note": "",
                },
                {
                    "day": 2,
                    "date_hint": "第2天",
                    "morning": [{"place": "大熊猫基地", "description": "看熊猫"}],
                    "afternoon": [],
                    "evening": [],
                    "meals": [],
                    "note": "",
                },
            ],
            "budget_split": {"transport": 200, "lodging": 300, "food": 400, "tickets": 100, "other": 0},
            "summary": "2天美食之旅",
            "tips": [],
        },
    },
)
assert r.status_code == 201, r.text
trip_id = r.json()["trip_id"]
print(f"  ✅ 已保存 trip_id={trip_id[:8]}")

print("== 2. 自然语言编辑：第二天换轻松行程 ==")
r = client.post(
    f"/api/trip/{trip_id}/edit",
    json={"instruction": "第二天太累了，改成轻松一点的市区半日游，去掉大熊猫基地"},
)
print(f"  状态码: {r.status_code}")
if r.status_code != 200:
    print(f"  ❌ 失败: {r.text[:300]}")
    sys.exit(1)

body = r.json()
days = body["itinerary"].get("days", [])
print(f"  ✅ 编辑后仍为 {len(days)} 天")
for d in days:
    acts = [a["place"] for a in (d["morning"] + d["afternoon"] + d["evening"])]
    print(f"  第{d['day']}天: {' → '.join(acts) if acts else '(无活动)'}")

# 校验：第 2 天不应再有大熊猫基地（用户要求去掉）
day2 = [d for d in days if d["day"] == 2]
no_panda = not any("熊猫" in a["place"] for d in day2 for a in (d["morning"] + d["afternoon"] + d["evening"]))
print(f"  {'✅' if no_panda else '❌'} 第2天已去掉大熊猫基地")

print("== 3. 清理 ==")
r = client.delete(f"/api/trip/{trip_id}")
print(f"  {'✅' if r.status_code == 204 else '❌'} 已删除测试行程")

sys.exit(0 if no_panda else 1)
