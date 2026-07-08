"""Unit tests for the KB-sourced data-agent scoring rules (2.11 / 2.33).

Locks the band boundaries to the knowledge base so a threshold can't drift
silently. Runnable with pytest or plain python (asserts run under __main__).
"""
from __future__ import annotations

from app.agents.data_rules import (
    MetricStats,
    _parse_range,
    factor_ranges,
    in_range,
    match_factor_range,
    score_statistical,
    score_validation,
    statistical_rule_rows,
    validation_rule_rows,
)


def _stats(months: int, span: int, nonneg: float, regions: int, channels: int,
           monthly: bool = True) -> MetricStats:
    return MetricStats(n=months, months=months, span_months=span, nonneg_ratio=nonneg,
                       regions=regions, channels=channels, monthly=monthly)


def test_validation_full_pass() -> None:
    sc = score_validation(_stats(36, 36, 1.0, 5, 6))
    assert (sc.consistency, sc.accuracy, sc.completeness, sc.granularity) == (1.0, 1.0, 1.0, 1.0)
    assert sc.total == 4.0 and sc.verdict == "pass"


def test_validation_borderline_short_coverage() -> None:
    # 12 months → completeness 0.5; national-only → granularity 0.5; 92% valid → accuracy 0.5
    sc = score_validation(_stats(12, 12, 0.92, 1, 1))
    assert (sc.completeness, sc.granularity, sc.accuracy) == (0.5, 0.5, 0.5)
    assert sc.total == 2.5 and sc.verdict == "borderline"


def test_validation_unusable_low_coverage_gappy() -> None:
    # 4 months over a 12-month span (gappy) + yearly → low on every dim
    sc = score_validation(_stats(4, 12, 0.8, 1, 1, monthly=False))
    assert sc.completeness == 0.0 and sc.granularity == 0.0 and sc.consistency == 0.0
    assert sc.verdict == "unusable"


def test_validation_continuity_band() -> None:
    assert score_validation(_stats(24, 24, 1.0, 2, 2)).consistency == 1.0   # 1.0 ratio
    assert score_validation(_stats(20, 24, 1.0, 2, 2)).consistency == 0.5   # 0.83 ratio
    assert score_validation(_stats(12, 24, 1.0, 2, 2)).consistency == 0.0   # 0.5 ratio


def test_statistical_bands() -> None:
    assert [score_statistical(cv, 0.4, 2).cv_score for cv in (0.04, 0.07, 0.15, 0.5)] == [0.0, 0.5, 1.0, 2.0]
    assert [score_statistical(0.3, r, 2).pearson_score for r in (0.05, 0.2, 0.4, 0.8)] == [0.0, 0.5, 1.0, 2.0]
    assert [score_statistical(0.3, 0.4, v).vif_score for v in (1, 3, 7, 12)] == [0.0, 0.5, 1.0, 2.0]


def test_statistical_verdict_thresholds() -> None:
    assert score_statistical(0.5, 0.8, 1).verdict == "Good"          # 2+2+0 = 4
    assert score_statistical(0.15, 0.2, 3).verdict == "Acceptable"   # 1+0.5+0.5 = 2
    assert score_statistical(0.04, 0.05, 1).verdict == "unconsiderable"  # 0


def test_statistical_severe_collinearity_drops_despite_high_total() -> None:
    sc = score_statistical(0.3, 0.8, 12)  # strong signal but VIF 12 → severe collinearity
    assert sc.total >= 3.0 and sc.verdict == "Good"
    assert sc.drop is True


def test_rule_rows_load_from_kb() -> None:
    assert len(validation_rule_rows()) >= 8   # 4 dims, multiple subchecks
    assert len(statistical_rule_rows()) >= 9  # 3 tests, 3-4 bands each


def test_parse_range() -> None:
    assert _parse_range("0%~1.5%") == (0.0, 1.5)
    assert _parse_range("-5%~5%") == (-5.0, 5.0)
    assert _parse_range("0.8~1.3") == (0.8, 1.3)
    assert _parse_range("/") is None
    assert _parse_range(None) is None


def test_factor_range_match() -> None:
    assert len(factor_ranges()) >= 15
    dd = match_factor_range("Digital Display")
    assert dd is not None and dd.roi == (0.8, 1.3) and dd.contribution == (0.0, 1.5)
    assert match_factor_range("社媒").roi == (1.5, 6.0)
    assert match_factor_range("一个不存在的因子") is None


def test_in_range() -> None:
    assert in_range(1.0, (0.8, 1.3)) is True
    assert in_range(2.0, (0.8, 1.3)) is False
    assert in_range(1.0, None) is False


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all data_rules tests passed")
