# ============================================
# 预算模型与确定性校准测试（离线）
# 覆盖：BudgetBreakdown 宽松解析、比例缩放、normalize_budget 四类边界
# ============================================
import pytest

from app.models.schemas import BudgetBreakdown
from app.services.trip_service import normalize_budget

KEYS = {"transport", "lodging", "food", "tickets", "other"}


class TestBudgetBreakdown:
    def test_from_raw_coerces_strings_and_missing(self):
        b = BudgetBreakdown.from_raw({"transport": "500", "lodging": None, "food": "不便宜"})
        assert b.transport == 500.0
        assert b.lodging == 0.0
        assert b.food == 0.0          # 转不动按 0
        assert b.tickets == 0.0       # 缺项补 0

    def test_from_raw_clamps_negatives(self):
        b = BudgetBreakdown.from_raw({"transport": -100, "food": 200})
        assert b.transport == 0.0
        assert b.food == 200.0

    def test_from_raw_handles_none_and_garbage(self):
        assert BudgetBreakdown.from_raw(None).total == 0.0
        assert BudgetBreakdown.from_raw({"transport": []}).total == 0.0

    def test_total(self):
        assert BudgetBreakdown(transport=1.5, food=2.5).total == 4.0

    def test_scaled_to_hits_target_exactly(self):
        scaled = BudgetBreakdown(transport=100, lodging=100, food=100).scaled_to(1000)
        assert sum(scaled.values()) == 1000.0            # 零头补到最大项，和值精确
        assert scaled["transport"] == pytest.approx(333.34, abs=0.02)

    def test_scaled_to_returns_zeros_when_nothing_to_scale(self):
        assert BudgetBreakdown().scaled_to(1000) == {k: 0.0 for k in KEYS}


class TestNormalizeBudget:
    # 五项和恰好 2000
    FULL = {"transport": 500, "lodging": 600, "food": 400, "tickets": 300, "other": 200}

    def test_exact_match_unchanged(self):
        assert normalize_budget(self.FULL, 2000) == {k: float(v) for k, v in self.FULL.items()}

    def test_missing_keys_filled_with_zero(self):
        out = normalize_budget({"transport": 500}, 500)
        assert set(out) == KEYS
        assert out["lodging"] == 0.0

    def test_small_deviation_within_tolerance_untouched(self):
        # 和 2000 对总预算 2050：偏差 2.4% < 5% → 不动用户的数
        assert normalize_budget(self.FULL, 2050)["transport"] == 500.0

    def test_large_deviation_scaled_to_total(self):
        raw = {k: 1000 for k in KEYS}          # 和 5000
        out = normalize_budget(raw, 2000)
        assert sum(out.values()) == 2000.0
        assert out["transport"] == 400.0

    def test_garbage_and_negative_sanitized(self):
        out = normalize_budget({"transport": "500元", "lodging": -100, "food": 100}, 100)
        assert out["transport"] == 0.0
        assert out["lodging"] == 0.0
        assert sum(out.values()) == 100.0

    def test_empty_raw_with_total_returns_zeros(self):
        assert normalize_budget(None, 2000) == {k: 0.0 for k in KEYS}

    @pytest.mark.parametrize("bad_total", [0, -1, None])
    def test_invalid_total_keeps_parsed_values(self, bad_total):
        # 没有有效的总预算可校准，保留解析出来的值（总比清成 0 好）
        assert normalize_budget({"transport": 500}, bad_total)["transport"] == 500.0
