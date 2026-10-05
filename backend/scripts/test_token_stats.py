# ============================================
# Token 观测测试：生成（分项 token）→ 保存 → /trip/stats 汇总
# 用法：& $py -X utf8 backend/scripts/test_token_stats.py *> _token_out.txt
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)

# 1) 生成行程（西安，A 级 RAG：rewrite + rerank + planner 三阶段都耗 token）
r = client.post("/api/trip/plan", json={
    "destination": "西安", "days": 1, "budget": 500,
    "preferences": "节奏：轻松；旅行偏好：美食、人文",
})
print(f"plan 状态: {r.status_code}")
body = r.json()
tu = body.get("token_usage", {})
print("plan 响应 token_usage:")
for phase, d in tu.items():
    if d.get("total"):
        print(f"  {phase:<8} prompt={d['prompt']} completion={d['completion']} total={d['total']}")

# 2) 保存行程（携带 token_usage 存档）
r2 = client.post("/api/trip", json={
    "destination": body["destination"],
    "summary": body["itinerary"].get("summary", ""),
    "itinerary_json": body["itinerary"],
    "token_usage": tu,
})
print(f"\nsave 状态: {r2.status_code}, trip_id={r2.json().get('trip_id', '')[:12]}...")

# 3) /trip/stats 汇总
r3 = client.get("/api/trip/stats")
print(f"\nstats 状态: {r3.status_code}")
stats = r3.json()
print("session（进程累计，本次生成）:")
for phase, d in stats["session"]["by_phase"].items():
    if d["total"]:
        print(f"  {phase:<8} total={d['total']}（{stats['session']['requests'][phase]} 次）")
print(f"  session 合计: {stats['session']['total']} tokens")
print("saved（已保存行程累计）:")
for phase, d in stats["saved"]["by_phase"].items():
    if d["total"]:
        print(f"  {phase:<8} total={d['total']}（{stats['saved']['requests'][phase]} 次）")
print(f"  saved 合计: {stats['saved']['total']} tokens")
