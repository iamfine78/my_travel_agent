# ============================================
# M3 测试：RAG 在线链路（真实调用：改写+检索+重排+生成）
# 验证：1) 向量库已入库  2) Query Rewrite  3) 检索+重排  4) A 级生成带攻略
# ============================================
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.api.main import app
from app.agents.tools import rag_tool
from app.rag import retriever, vector_db

client = TestClient(app)
ok = fail = 0


def check(name: str, cond: bool, detail: str = ""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        fail += 1
        print(f"  ❌ {name}  {detail}")


print("== 1. 向量库状态 ==")
count = len(vector_db.get_collection().get()["ids"])
check("向量库有 42 块攻略", count == 42, f"实际 {count}")

print("== 2. Query Rewrite（deepseek-flash）==")
rewritten = rag_tool.rewrite_query("西安旅行 亲子 3天 预算2000", city="西安")
print(f"    改写结果: {rewritten}")
check("改写返回 query", bool(rewritten.get("query")))
check("改写返回 keywords", len(rewritten.get("keywords", [])) >= 1)

print("== 3. 检索 + 重排（deepseek-flash LLM Rerank）==")
hits = retriever.retrieve_and_rerank("西安 兵马俑 华清宫 亲子 门票", city="西安")
print(f"    召回 {len(hits)} 条")
for h in hits[:3]:
    print(f"    [{h['score']}分] {h['reason']} | {h['content'][:40]}...")
check("召回非空", len(hits) >= 1)
check("最高分 >= 最低分", hits[0]["score"] >= hits[-1]["score"])
check("带 reason", all(h.get("reason") for h in hits))

print("== 4. Redis 缓存命中验证 ==")
hits2 = retriever.retrieve_and_rerank("西安 兵马俑 华清宫 亲子 门票", city="西安")
check("第二次调用返回相同条数", len(hits2) == len(hits))
from app.services import cache_service
cached = cache_service.cache_get(f"rag:西安:西安 兵马俑 华清宫 亲子 门票")
check("Redis 中已缓存 RAG 结果", cached is not None)

print("== 5. A 级行程生成（西安，应注入攻略上下文）==")
r = client.post(
    "/api/trip/plan",
    json={"destination": "西安", "days": 2, "budget": 1500, "companions": "亲子", "preferences": "想看兵马俑"},
)
print(f"    状态: {r.status_code}")
if r.status_code != 200:
    print(f"    ❌ {r.text[:300]}")
    fail += 1
else:
    body = r.json()
    check("sources 含攻略引用", any("攻略" in s for s in body.get("sources", [])), str(body.get("sources")))
    check("行程 2 天", len(body["itinerary"].get("days", [])) == 2)
    places = [a["place"] for d in body["itinerary"].get("days", []) for a in (d["morning"] + d["afternoon"] + d["evening"])]
    check("行程含兵马俑", any("兵马俑" in p for p in places), str(places))
    print(f"    来源: {body.get('sources')}")
    print(f"    景点: {' → '.join(places)}")

print(f"\n结果：通过 {ok} 项，失败 {fail} 项")
sys.exit(0 if fail == 0 else 1)
