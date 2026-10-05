# ============================================
# 业务异常体系测试（离线）
# 覆盖：异常类型的状态码约定、经 api/main.py 的 handler 映射成 HTTP 响应
# ============================================
import pytest

from app.core import errors


class TestErrorTypes:
    @pytest.mark.parametrize(
        "exc_cls,expected_status",
        [
            (errors.PlanningError, 400),
            (errors.UnsupportedDestinationError, 400),
            (errors.TripNotFoundError, 404),
            (errors.ItineraryGenerationError, 502),
        ],
    )
    def test_status_code_contract(self, exc_cls, expected_status):
        exc = exc_cls("出错了")
        assert exc.status_code == expected_status
        assert exc.message == "出错了"
        assert str(exc) == "出错了"

    def test_subclasses_are_catchable_as_base(self):
        for exc_cls in (errors.UnsupportedDestinationError, errors.TripNotFoundError):
            assert issubclass(exc_cls, errors.PlanningError)


class TestErrorMapping:
    """业务异常应被 api/main.py 的 handler 转成对应状态码，而不是 500。"""

    def test_province_input_maps_to_400(self, client):
        # D 级拦截发生在调高德之前，所以这条是离线的
        r = client.post("/api/trip/plan", json={"destination": "四川省", "days": 3})
        assert r.status_code == 400
        assert "具体城市" in r.json()["detail"]

    def test_edit_missing_trip_maps_to_404(self, client):
        r = client.post("/api/trip/根本不存在的ID/edit", json={"instruction": "改一下"})
        assert r.status_code == 404
        assert r.json()["detail"] == "行程不存在"
