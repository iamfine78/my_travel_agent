# ============================================
# API 接口测试（离线，TestClient + 临时数据库）
# 覆盖：健康检查、行程历史 CRUD、Token 汇总、导出接口
# 注意：/api/trip/plan 需要真实 LLM，放在 test_live_integration.py
# ============================================
import pytest

from app.services.export_service import find_chinese_font


def _save(client, destination: str = "西安", **extra) -> dict:
    payload = {"destination": destination, "summary": "测试摘要", "itinerary_json": {"destination": destination, "days": []}}
    payload.update(extra)
    return client.post("/api/trip", json=payload)


class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestTripCrud:
    def test_save_returns_201_and_appears_in_history(self, client):
        r = _save(client)
        assert r.status_code == 201
        trip_id = r.json()["trip_id"]
        assert trip_id

        hist = client.get("/api/trip/history").json()
        assert hist["total"] == 1
        assert hist["records"][0]["trip_id"] == trip_id

    def test_detail_and_not_found(self, client):
        trip_id = _save(client).json()["trip_id"]
        assert client.get(f"/api/trip/{trip_id}").status_code == 200
        assert client.get("/api/trip/不存在的ID").status_code == 404

    def test_delete(self, client):
        trip_id = _save(client).json()["trip_id"]
        assert client.delete(f"/api/trip/{trip_id}").status_code == 204
        assert client.get(f"/api/trip/{trip_id}").status_code == 404
        assert client.delete(f"/api/trip/{trip_id}").status_code == 404

    def test_token_usage_is_persisted(self, client):
        usage = {"planner": {"prompt": 1, "completion": 2, "total": 3}}
        trip_id = _save(client, token_usage=usage).json()["trip_id"]
        detail = client.get(f"/api/trip/{trip_id}").json()
        assert detail["itinerary"]["_token_usage"]["planner"]["total"] == 3

    def test_stats_shape(self, client):
        _save(client)
        stats = client.get("/api/trip/stats").json()
        assert set(stats["session"]["by_phase"]) == {"rewrite", "rerank", "planner", "edit"}
        assert "saved" in stats and "total" in stats["saved"]

    def test_refresh_missing_trip_returns_404(self, client):
        assert client.post("/api/trip/不存在/refresh").status_code == 404


class TestExportEndpoints:
    def test_from_data_markdown(self, client, sample_itinerary):
        r = client.post(
            "/api/export/from-data?format=md",
            json={"destination": "西安", "itinerary": sample_itinerary},
        )
        assert r.status_code == 200
        assert "西安" in r.text

    def test_from_data_pdf(self, client, sample_itinerary):
        if not find_chinese_font():
            pytest.skip("未找到中文字体，跳过 PDF 导出")
        r = client.post(
            "/api/export/from-data?format=pdf",
            json={"destination": "西安", "itinerary": sample_itinerary},
        )
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_invalid_format_rejected(self, client, sample_itinerary):
        r = client.post(
            "/api/export/from-data?format=docx",
            json={"destination": "西安", "itinerary": sample_itinerary},
        )
        assert r.status_code == 422
