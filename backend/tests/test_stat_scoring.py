"""2.4 Statistical Score — band scoring, reference CV, indicator-granular VIF,
and the end-to-end scorecard on the real reference dataset.

Run: PYTHONPATH=. .venv/bin/python tests/test_stat_scoring.py
"""
from __future__ import annotations

import numpy as np

from app.agents.data_rules import (
    STAT_GOOD,
    VIF_MAX,
    reference_cv,
    score_statistical,
    vif_all,
)
from app.agents.stat_scoring import (
    STAT_COLUMNS,
    accepted_stat_labels,
    build_stat_scorecard,
    stat_sheet,
)
from app.store.state import ProjectState


def _approx(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def test_band_boundaries() -> None:
    for cv, want in [(0.0, 0.0), (0.05, 0.0), (0.06, 0.5), (0.099, 0.5), (0.1, 1.0), (9.9, 1.0)]:
        got = score_statistical(cv, 0.0, 1.0).cv_score
        assert got == want, f"cv={cv} → {got}, want {want}"
    for r, want in [(0.0, 0.0), (-0.09, 0.0), (0.1, 0.5), (-0.29, 0.5), (0.3, 1.0), (-0.99, 1.0)]:
        got = score_statistical(0.0, r, 1.0).pearson_score
        assert got == want, f"r={r} → {got}, want {want}"
    for vif, want in [(1.0, 1.0), (1.01, 0.5), (4.99, 0.5), (5.0, 0.0), (99.0, 0.0)]:
        got = score_statistical(0.0, 0.0, vif).vif_score
        assert got == want, f"vif={vif} → {got}, want {want}"
    print("✓ band boundaries")


def test_verdict_thresholds() -> None:
    """Total = CV x Pearson x VIF; only an all-pass product (1.0) is Good."""
    assert score_statistical(0.2, 0.6, 1.0).verdict == "Good"
    ac = score_statistical(0.07, 0.4, 1.0)          # 0.5 * 1 * 1
    assert ac.total == 0.5 and ac.verdict == "Acceptable"
    un = score_statistical(0.04, 0.2, 2.0)          # 0 * 0.5 * 0.5
    assert un.total == 0.0 and un.verdict == "unconsiderable"
    assert STAT_GOOD == 0.5
    print("✓ verdict thresholds")


def test_reference_cv() -> None:
    """CV = variance/mean AFTER min-max scaling to [0,1]; degenerate → 0."""
    assert reference_cv(np.array([])) == 0.0
    assert reference_cv(np.array([5.0, 5.0, 5.0])) == 0.0  # constant → no volatility
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    scaled = (x - x.min()) / (x.max() - x.min())  # 0,.25,.5,.75,1
    want = float(np.var(scaled) / np.mean(scaled))
    assert _approx(reference_cv(x), want), f"{reference_cv(x)} != {want}"
    # NaNs are ignored, not propagated.
    assert reference_cv(np.array([0.0, np.nan, 4.0])) > 0.0
    print("✓ reference CV")


def test_vif_identified_vs_underdetermined() -> None:
    """VIF is per-column: exact when n > p+1, pairwise-max proxy when p ≥ n."""
    rng = np.random.RandomState(0)
    # Identified: 200 obs, 3 independent columns → VIF ≈ 1.
    n = 200
    a = rng.normal(size=n)
    b = rng.normal(size=n)
    c = rng.normal(size=n)
    vifs = vif_all(np.column_stack([a, b, c]))
    assert all(0.9 < v < 1.6 for v in vifs), f"independent cols should be ~1, got {vifs}"
    # Identified with a near-duplicate column → that column's VIF is large.
    d = a + 1e-3 * rng.normal(size=n)
    vifs2 = vif_all(np.column_stack([a, b, d]))
    assert vifs2[0] > 5 and vifs2[2] > 5, f"collinear pair should inflate, got {vifs2}"
    assert 0.9 < vifs2[1] < 1.6
    # Under-determined (p ≥ n): still one value per column, floored ≥ 1, capped.
    wide = rng.normal(size=(5, 20))
    vifs3 = vif_all(wide)
    assert vifs3.shape == (20,)
    assert all(1.0 <= v <= VIF_MAX for v in vifs3)
    print("✓ VIF identified + under-determined proxy")


def test_yoy_removes_level_trend_and_season() -> None:
    """A pure seasonal-plus-trend series carries no year-over-year signal beyond its
    growth — which is exactly the confound that made every indicator correlate."""
    from app.agents.stat_scoring import _yoy

    t = np.arange(24, dtype=float)
    season = np.sin(2 * np.pi * t / 12.0)
    a = 100.0 + 3.0 * t + 10.0 * season          # level + linear trend + seasonality
    d = _yoy(a)
    assert d.shape[0] == 12, "24 monthly points yield 12 year-over-year differences"
    # Trend growth over 12 months is constant (3 * 12) and the seasonal term cancels.
    assert np.allclose(d, 36.0, atol=1e-9), f"expected a flat 36.0, got {d[:3]}"
    # Too short to difference → returned unchanged rather than emptied.
    short = np.arange(8, dtype=float)
    assert np.array_equal(_yoy(short), short)
    print("✓ YoY differencing removes level, trend and seasonality")


def test_yoy_guards_on_result_size_not_input_size() -> None:
    """A 13-14 month project must not be differenced down to 1-2 rows -- that
    starves Pearson's `mask.sum() < 3` guard and silently drops everything with
    nothing explaining why."""
    from app.agents.stat_scoring import MIN_DETRENDED_POINTS, _yoy

    assert MIN_DETRENDED_POINTS == 6
    # 14 months would difference down to 2 rows (14-12) -- below the minimum,
    # so it must come back unchanged rather than starved.
    a14 = np.arange(14, dtype=float)
    assert np.array_equal(_yoy(a14), a14)
    # 18 months differences down to exactly 6 rows -- right at the threshold,
    # so it must still detrend.
    a18 = np.arange(18, dtype=float)
    d18 = _yoy(a18)
    assert d18.shape[0] == 6
    assert not np.array_equal(d18, a18)
    print("✓ YoY guards on the RESULT size, not the input size")


def test_reindex_onto_complete_calendar_pairs_correct_months() -> None:
    """A month missing anywhere in the panel must not turn `a[12:] - a[:-12]`
    into a '12 rows ago' difference across the discontinuity."""
    import pandas as pd

    from app.agents.stat_scoring import _complete_month_index, _yoy

    # Two years of months with March 2024 (202403) missing from the raw panel.
    months = [202401, 202402, 202404, 202405, 202406, 202407, 202408, 202409,
              202410, 202411, 202412,
              202501, 202502, 202503, 202504, 202505, 202506, 202507, 202508,
              202509, 202510, 202511, 202512]
    values = pd.Series(range(len(months)), index=months, dtype=float)

    # Without the calendar reindex, "12 rows ago" is not "12 months ago" once a
    # month is missing: position 12 in the raw (gapped) array is Feb-2025, not
    # Jan-2025 -- an off-by-one diff across the March-2024 discontinuity.
    assert months[12] == 202502
    d_raw = _yoy(values.to_numpy(dtype=float))
    assert d_raw[0] == values.loc[202502] - values.loc[202401]  # the bug this fixes

    full_idx = _complete_month_index(values.index)
    assert 202403 in full_idx and len(full_idx) == 24
    reindexed = values.reindex(full_idx, fill_value=0.0)
    d_fixed = _yoy(reindexed.to_numpy(dtype=float))
    assert d_fixed.shape[0] == 12
    # Position 0 of the fixed differences is now truly Jan-2025 minus Jan-2024.
    assert d_fixed[0] == values.loc[202501] - values.loc[202401]
    print("✓ reindexing onto the complete calendar range keeps YoY differencing "
          "paired on real calendar months across a gap")


def test_detrending_makes_the_screening_discriminate() -> None:
    """The regression this task exists to prevent: on raw levels every indicator
    passed CV and Pearson and failed VIF, so every total was 0 and 2.4 dropped
    everything. After detrending the verdicts must actually vary."""
    from app.agents.stat_scoring import build_stat_scorecard
    from app.store.state import danone_meta, initial_state

    card = build_stat_scorecard(initial_state(danone_meta()))
    assert card.rows, "the reference dataset must yield scored indicators"
    verdicts = {r.auto_verdict for r in card.rows}
    assert len(verdicts) > 1, f"screening must discriminate, got only {verdicts}"
    assert any(r.total > 0 for r in card.rows), "not every indicator can score zero"
    vifs = [r.vif for r in card.rows]
    assert min(vifs) < 5.0, f"detrended VIF should not start at {min(vifs):.1f}"
    print(f"✓ screening discriminates — verdicts {sorted(verdicts)}, "
          f"median VIF {float(np.median(vifs)):.2f}")


def test_end_to_end_reference() -> None:
    """The scorecard scores every indicator on the real reference dataset."""
    st = ProjectState()  # no project data → reference fallback
    card = build_stat_scorecard(st)
    assert card.rows, "expected scored indicators on the reference dataset"
    for r in card.rows:
        assert r.indicator, "each row names an indicator"
        assert 0.0 <= r.cv_score <= 1.0
        assert 0.0 <= r.pearson_score <= 1.0
        assert 0.0 <= r.vif_score <= 1.0
        assert _approx(r.total, r.cv_score * r.pearson_score * r.vif_score)
        assert r.auto_verdict in ("Good", "Acceptable", "unconsiderable")
        assert r.disposition in ("include", "review", "drop")
    # Worst-first ordering.
    totals = [r.total for r in card.rows]
    assert totals == sorted(totals), "rows should be worst-first by total"
    # Kept set excludes dropped.
    kept = accepted_stat_labels(card)
    dropped = [r for r in card.rows if r.disposition == "drop"]
    assert len(kept) == len(card.rows) - len(dropped)
    # Artifact body: two sheets (rules + per-indicator results), every column rendered.
    body = stat_sheet(card)
    assert [s["name"] for s in body["sheets"]] == ["Scoring rules", "Statistical score"]
    assert body["sheets"][1]["columns"] == STAT_COLUMNS
    assert len(body["sheets"][1]["rows"]) == len(card.rows)
    assert all(len(r) == len(STAT_COLUMNS) for r in body["sheets"][1]["rows"])
    print(f"✓ end-to-end reference — {len(card.rows)} indicators scored, {len(kept)} kept")


if __name__ == "__main__":
    test_band_boundaries()
    test_verdict_thresholds()
    test_reference_cv()
    test_vif_identified_vs_underdetermined()
    test_yoy_removes_level_trend_and_season()
    test_yoy_guards_on_result_size_not_input_size()
    test_reindex_onto_complete_calendar_pairs_correct_months()
    test_detrending_makes_the_screening_discriminate()
    test_end_to_end_reference()
    print("\nall statistical-score tests passed")
