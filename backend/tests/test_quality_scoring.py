"""Unit tests for the 2.2 Data Quality Score subcheck scorer (app.agents.quality_scoring).

Builds tiny long-table series exercising each 2.11 subcheck band and asserts the
deterministic score, then the product Total / verdict. No LLM, no reference data. Run:
    PYTHONPATH=. .venv/bin/python tests/test_quality_scoring.py
(pytest optional; the asserts also run under plain python via __main__.)
"""
from __future__ import annotations

import pandas as pd

from app.agents.quality_scoring import (
    FieldContext,
    compute_series_evidence,
    score_quality,
)

_COLS = ["province_group", "channel", "year", "month", "source",
         "l5", "l6", "l7", "l8", "metric_type", "value"]


def _series(values, *, months, regions=1, channels=1, source="sys", metric_type="X",
            drilldown=0, year_of=None) -> pd.DataFrame:
    """Build one metric series. `months` are yyyymm ints aligned with `values`."""
    rows = []
    for i, (m, v) in enumerate(zip(months, values)):
        rows.append({
            "province_group": f"R{i % regions}" if regions else "R0",
            "channel": f"C{i % channels}" if channels else "C0",
            "year": (year_of[i] if year_of else m // 100),
            "month": m,
            "source": source[i] if isinstance(source, list) else source,
            "l5": "d5" if drilldown >= 1 else "",
            "l6": "d6" if drilldown >= 2 else "",
            "l7": "d7" if drilldown >= 3 else "",
            "l8": "",
            "metric_type": metric_type,
            "value": v,
        })
    return pd.DataFrame(rows, columns=_COLS)


def _months(start_yyyymm: int, n: int) -> list[int]:
    out, y, m = [], start_yyyymm // 100, start_yyyymm % 100
    for _ in range(n):
        out.append(y * 100 + m)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _sub(result, key):
    return next(s for s in result.subs if s.key == key)


PERF = FieldContext(has_spend=True, has_performance=True)


def test_clean_series_passes():
    m = _months(202301, 30)  # 30 months, 2yr+
    r = score_quality(compute_series_evidence(
        _series([100 + i for i in range(30)], months=m, regions=2, channels=2,
                metric_type="spending", drilldown=3)), PERF)
    assert r.consistency == 1.0 and r.accuracy == 1.0
    assert r.completeness == 1.0 and r.granularity == 1.0
    assert r.total == 1.0 and r.verdict == "pass"


def test_short_coverage_is_unusable():
    m = _months(202401, 8)  # only 8 months span (<1yr)
    r = score_quality(compute_series_evidence(
        _series([100] * 8, months=m, metric_type="spending")), PERF)
    assert _sub(r, "completeness.data").score == 0.0
    assert r.completeness == 0.0 and r.total == 0.0 and r.verdict == "unusable"


def test_one_to_two_years_is_half_coverage():
    m = _months(202401, 15)  # 15 months span (1–2yr)
    r = score_quality(compute_series_evidence(
        _series([100 + i for i in range(15)], months=m, regions=2, channels=2,
                metric_type="spending")), PERF)
    assert _sub(r, "completeness.data").score == 0.5
    assert r.completeness == 0.5 and r.total == 0.5 and r.verdict == "pass"


def test_source_change_big_yoy_breaks_caliber():
    # two years, source switches at the boundary, +200% YoY jump.
    m = _months(202301, 24)
    vals = [100] * 12 + [300] * 12
    src = ["A"] * 12 + ["B"] * 12
    r = score_quality(compute_series_evidence(
        _series(vals, months=m, regions=2, channels=2, source=src,
                metric_type="spending")), PERF)
    assert _sub(r, "consistency.caliber").score == 0.0
    assert r.consistency == 0.0 and r.total == 0.0 and r.verdict == "unusable"


def test_source_change_small_yoy_is_borderline_caliber():
    m = _months(202301, 24)
    vals = [100 + (i % 3) for i in range(24)]  # tiny variation → small YoY
    src = ["A"] * 12 + ["B"] * 12
    r = score_quality(compute_series_evidence(
        _series(vals, months=m, regions=2, channels=2, source=src,
                metric_type="spending")), PERF)
    assert _sub(r, "consistency.caliber").score == 0.5
    assert r.consistency == 0.5 and r.total == 0.5 and r.verdict == "pass"


def test_sub_monthly_breaks_granularity():
    # yearly-only rows: month is NA → not monthly.
    df = _series([100, 110, 120], months=[202312, 202412, 202512], metric_type="spending")
    df["month"] = pd.NA
    r = score_quality(compute_series_evidence(df), PERF)
    assert _sub(r, "granularity.time").score == 0.0
    assert r.granularity == 0.0 and r.verdict == "unusable"


def test_illegal_negatives_break_accuracy_for_spend():
    m = _months(202301, 24)
    vals = [-5 if i < 4 else 100 for i in range(24)]  # ~17% negative spend
    r = score_quality(compute_series_evidence(
        _series(vals, months=m, regions=2, channels=2, metric_type="spending")), PERF)
    assert _sub(r, "accuracy.numeric").score == 0.0
    assert r.accuracy == 0.0 and r.verdict == "unusable"


def test_negatives_allowed_for_non_nonneg_metric():
    # temperature (X driver) legitimately goes negative — not an error.
    m = _months(202301, 24)
    vals = [-5 if i < 8 else 20 for i in range(24)]  # 33% negative but valid
    r = score_quality(compute_series_evidence(
        _series(vals, months=m, regions=2, channels=2, metric_type="X")), PERF)
    assert _sub(r, "accuracy.numeric").score == 1.0
    assert r.accuracy == 1.0


def test_spend_without_performance_is_half_field():
    m = _months(202301, 30)
    ctx = FieldContext(has_spend=True, has_performance=False)
    r = score_quality(compute_series_evidence(
        _series([100] * 30, months=m, regions=2, channels=2, metric_type="spending")), ctx)
    assert _sub(r, "completeness.field").score == 0.5
    assert r.completeness == 0.5


def test_flighted_gaps_do_not_reject():
    # 2yr+ span with real off-months (flighted media, active Apr–Sep each year):
    # coverage passes, continuity is advisory only, so the metric is not rejected.
    m = [y * 100 + mo for y in (2023, 2024, 2025) for mo in range(4, 10)]  # 18 mo over a 30 mo span
    r = score_quality(compute_series_evidence(
        _series([100 + i for i in range(len(m))], months=m, regions=2, channels=2,
                metric_type="spending")), PERF)
    assert _sub(r, "completeness.data").score == 1.0          # coverage OK
    assert _sub(r, "consistency.continuity").score == 0.5     # advisory flag
    assert not _sub(r, "consistency.continuity").blocking
    assert r.consistency == 1.0 and r.total == 1.0 and r.verdict == "pass"


def test_drilldown_is_advisory_not_blocking():
    m = _months(202301, 30)
    r = score_quality(compute_series_evidence(
        _series([100 + i for i in range(30)], months=m, regions=2, channels=2,
                metric_type="spending", drilldown=0)), PERF)
    drill = _sub(r, "granularity.drilldown")
    assert drill.score == 0.0 and drill.blocking is False
    assert r.granularity == 1.0  # not dragged down by the missing drilldown


def test_two_half_dimensions_is_borderline():
    # coverage 0.5 (1–2yr) × caliber 0.5 (source change small YoY) = 0.25 → borderline.
    m = _months(202401, 15)
    vals = [100 + (i % 2) for i in range(15)]
    src = ["A"] * 7 + ["B"] * 8
    r = score_quality(compute_series_evidence(
        _series(vals, months=m, regions=2, channels=2, source=src,
                metric_type="spending")), PERF)
    assert r.completeness == 0.5 and r.consistency == 0.5
    assert r.total == 0.25 and r.verdict == "borderline"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"all {len(fns)} quality-scoring tests passed")


if __name__ == "__main__":
    _run_all()
