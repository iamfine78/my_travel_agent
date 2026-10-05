# ============================================
# 真实外部服务集成测试（默认跳过）
# 会真实调用 deepseek / 高德，消耗额度且依赖网络，故与离线测试隔离。
# 运行：
#   $env:RUN_LIVE_TESTS=1; .venv\Scripts\python.exe -m pytest backend -m live -v
# ============================================
import os

import pytest

pytestmark = pytest.mark.live

if os.getenv("RUN_LIVE_TESTS") != "1":
    pytest.skip("未设置 RUN_LIVE_TESTS=1，跳过真实外部服务集成测试", allow_module_level=True)


def test_plan_settled_city_with_rag(client):
    """A 级城市（有攻略）应走 RAG，生成结构化行程。"""
    r = client.post(
        "/api/trip/plan",
        json={"destination": "西安", "days": 2, "budget": 2000, "companions": "独自", "preferences": "人文"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["destination"] == "西安"
    assert len(data["itinerary"]["days"]) >= 1
    assert data["itinerary"]["days"][0]["morning"]


def test_province_input_rejected(client):
    """省级输入应返回 400（D 级）。"""
    r = client.post("/api/trip/plan", json={"destination": "四川省", "days": 3})
    assert r.status_code == 400
