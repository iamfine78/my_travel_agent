# ============================================
# M2 测试：LLM 结构化行程生成（真实调用 deepseek-flash）
# 运行：.venv\Scripts\python.exe -X utf8 backend/scripts/test_m2.py
# 注意：会消耗少量 deepseek API 额度
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)

print("== 1. 健康检查 ==")
assert client.get("/api/health").status_code == 200
print("  ✅ 后端正常")

print("== 2. 真实 LLM 行程生成（西安 3 天 亲子 2000）==")
r = client.post(
    "/api/trip/plan",
    json={
        "destination": "西安",
        "days": 3,
        "budget": 2000,
        "companions": "亲子",
        "preferences": "喜欢人文景点，节奏轻松",
    },
)
print(f"  状态码: {r.status_code}")
if r.status_code != 200:
    print(f"  ❌ 失败: {r.text[:300]}")
    sys.exit(1)

body = r.json()
itinerary = body["itinerary"]
days = itinerary.get("days", [])
split = itinerary.get("budget_split", {})

print("== 3. 结构校验 ==")
checks = [
    ("行程天数 = 3", len(days) == 3),
    ("每天含 3 个时段", all(d.get("morning") and d.get("afternoon") and d.get("evening") for d in days)),
    ("预算拆分含 5 项", all(k in split for k in ("transport", "lodging", "food", "tickets", "other"))),
    ("有摘要", bool(itinerary.get("summary"))),
]
for name, ok in checks:
    print(f"  {'✅' if ok else '❌'} {name}")

print("== 4. 内容预览 ==")
print(f"  摘要: {itinerary['summary']}")
for d in days:
    acts = [a["place"] for a in (d["morning"] + d["afternoon"] + d["evening"])]
    print(f"  第{d['day']}天: {' → '.join(acts)}")
total = sum(float(v or 0) for v in split.values())
print(f"  预算拆分: {split}  合计={total:.0f}元")

fail = not all(ok for _, ok in checks)
print(f"\n结果: {'通过' if not fail else '失败'}")
sys.exit(0 if not fail else 1)
