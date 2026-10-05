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

    def test_refresh_maps_amap_failure_to_502(self, client, monkeypatch):
        """补全失败要说清楚，不能返回一份没变的行程假装成功。"""
        from app.services import map_service

        trip_id = _save(client).json()["trip_id"]

        def boom(*a, **k):
            raise RuntimeError("高德挂了")

        monkeypatch.setattr(map_service, "enrich_itinerary", boom)
        r = client.post(f"/api/trip/{trip_id}/refresh")
        assert r.status_code == 502
        assert "高德服务暂时不可用" in r.json()["detail"]


class TestHistoryTotal:
    def test_total_is_real_count_not_page_size(self, client):
        for _ in range(25):
            assert _save(client).status_code == 201

        page1 = client.get("/api/trip/history", params={"limit": 20, "offset": 0}).json()
        assert page1["total"] == 25, "total 应是总数，而不是当页条数"
        assert len(page1["records"]) == 20

        page2 = client.get("/api/trip/history", params={"limit": 20, "offset": 20}).json()
        assert page2["total"] == 25
        assert len(page2["records"]) == 5


class TestEditPersists:
    def test_edit_writes_back_to_storage(self, client, monkeypatch):
        """回归：编辑后的行程曾不回写存储 —— 页面变了，历史里还是旧的。"""
        from app.services import map_service, trip_service

        trip_id = _save(client).json()["trip_id"]
        edited = {
            "destination": "西安",
            "days": [{"day": 1, "morning": [], "afternoon": [], "evening": []}],
            "budget_split": {"transport": 100},
            "summary": "改过的摘要",
        }
        # 编辑链路会调 LLM 与高德，离线测试里都替换掉
        monkeypatch.setattr(trip_service.planner_agent, "edit_trip", lambda current, req: edited)
        monkeypatch.setattr(map_service, "enrich_itinerary", lambda itin, city: itin)

        r = client.post(f"/api/trip/{trip_id}/edit", json={"instruction": "换成轻松点的"})
        assert r.status_code == 200
        assert r.json()["itinerary"]["summary"] == "改过的摘要"

        detail = client.get(f"/api/trip/{trip_id}").json()
        assert detail["itinerary"]["summary"] == "改过的摘要"

    def test_edit_continues_when_map_enrich_fails(self, client, monkeypatch):
        """高德补全失败不应让编辑整体失败。"""
        from app.services import map_service, trip_service

        trip_id = _save(client).json()["trip_id"]
        edited = {"destination": "西安", "days": [], "budget_split": {}, "summary": "照样改"}
        monkeypatch.setattr(trip_service.planner_agent, "edit_trip", lambda current, req: edited)

        def boom(itin, city):
            raise RuntimeError("高德不可用")

        monkeypatch.setattr(map_service, "enrich_itinerary", boom)

        r = client.post(f"/api/trip/{trip_id}/edit", json={"instruction": "随便改"})
        assert r.status_code == 200
        assert r.json()["itinerary"]["summary"] == "照样改"


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
