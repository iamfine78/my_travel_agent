# ============================================
# M1 骨架测试：健康检查 + 历史 CRUD（中文数据验证）
# 原理：FastAPI 的 TestClient 内置 HTTP 客户端，
#       不真开端口，直接内存里模拟请求，最适合单元测试
# 运行：.venv\Scripts\python.exe -X utf8 backend/scripts/test_m1.py
# ============================================
import sys
from pathlib import Path

# 把 backend/ 加入模块搜索路径（保证 from app.xxx import 可用）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)

ok = 0
fail = 0


def check(name: str, cond: bool, detail: str = ""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        fail += 1
        print(f"  ❌ {name}  {detail}")


print("== 1. 健康检查 ==")
r = client.get("/api/health")
check("health 返回 200", r.status_code == 200, str(r.status_code))
check("status=ok", r.json().get("status") == "ok")

print("== 2. 保存行程（中文） ==")
r = client.post(
    "/api/trip",
    json={
        "destination": "成都",
        "summary": "熊猫之旅",
        "itinerary_json": {"day1": {"景点": "熊猫基地", "餐饮": "火锅"}},
    },
)
body = r.json()
check("保存返回 201", r.status_code == 201, str(r.status_code))
check("trip_id 生成", len(body.get("trip_id", "")) == 32)
check("destination 中文正确", body.get("destination") == "成都", str(body.get("destination")))
check("summary 中文正确", body.get("summary") == "熊猫之旅", str(body.get("summary")))
check(
    "itinerary 中文正确",
    body.get("itinerary", {}).get("day1", {}).get("景点") == "熊猫基地",
    str(body.get("itinerary")),
)
trip_id = body.get("trip_id", "")

print("== 3. 历史列表 ==")
r = client.get("/api/trip/history")
records = r.json().get("records", [])
check("列表返回 200", r.status_code == 200)
check("列表包含刚存的行程", any(x["trip_id"] == trip_id for x in records))

print("== 4. 详情 ==")
r = client.get(f"/api/trip/{trip_id}")
check("详情返回 200", r.status_code == 200)
check("详情目的地正确", r.json().get("destination") == "成都")

print("== 5. 404 场景 ==")
r = client.get("/api/trip/not-exist-id")
check("不存在的行程返回 404", r.status_code == 404)

print("== 6. 删除 ==")
r = client.delete(f"/api/trip/{trip_id}")
check("删除返回 204", r.status_code == 204)
r = client.get(f"/api/trip/{trip_id}")
check("删除后查询 404", r.status_code == 404)

print(f"\n结果：通过 {ok} 项，失败 {fail} 项")
sys.exit(0 if fail == 0 else 1)
