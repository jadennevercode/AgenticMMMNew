"""2.4 Statistical Score — band scoring, reference CV, indicator-granular VIF,
and the end-to-end scorecard on the real reference dataset.

Run: PYTHONPATH=. .venv/bin/python tests/test_stat_scoring.py
"""
from __future__ import annotations

import numpy as np

from app.agents.data_rules import (
    STAT_ACCEPTABLE,
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
    """CV / Pearson / VIF map to the 0 / 0.5 / 1 / 2 bands at the KB thresholds."""
    # CV bands (cv, expected cv_score) — boundaries are inclusive on the lower edge.
    for cv, want in [(0.04, 0.0), (0.05, 0.0), (0.07, 0.5), (0.1, 1.0),
                     (0.19, 1.0), (0.2, 2.0), (0.5, 2.0)]:
        got = score_statistical(cv, 0.0, 1.0).cv_score
        assert got == want, f"CV {cv}: got {got}, want {want}"
    # Pearson bands on |r|.
    for r, want in [(0.05, 0.0), (0.1, 0.5), (-0.2, 0.5), (0.3, 1.0),
                    (0.49, 1.0), (0.5, 2.0), (-0.9, 2.0)]:
        got = score_statistical(0.0, r, 1.0).pearson_score
        assert got == want, f"Pearson {r}: got {got}, want {want}"
    # VIF bands.
    for vif, want in [(1.0, 0.0), (2.0, 0.5), (4.9, 0.5), (5.0, 1.0),
                      (9.9, 1.0), (10.0, 2.0), (50.0, 2.0)]:
        got = score_statistical(0.0, 0.0, vif).vif_score
        assert got == want, f"VIF {vif}: got {got}, want {want}"
    print("✓ band boundaries")


def test_verdict_thresholds() -> None:
    """Total = CV+Pearson+VIF drives Good ≥ 3, Acceptable 1.5–3, else Unconsiderable."""
    # Good: 1 + 2 + 0 = 3.0
    assert score_statistical(0.1, 0.6, 1.0).verdict == "Good"
    # Acceptable: 0.5 + 1 + 0 = 1.5
    ac = score_statistical(0.07, 0.4, 1.0)
    assert _approx(ac.total, 1.5) and ac.verdict == "Acceptable"
    # Unconsiderable: 0 + 0.5 + 0.5 = 1.0
    un = score_statistical(0.04, 0.2, 2.0)
    assert _approx(un.total, 1.0) and un.verdict == "unconsiderable"
    assert STAT_ACCEPTABLE == 1.5 and STAT_GOOD == 3.0
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


def test_end_to_end_reference() -> None:
    """The scorecard scores every indicator on the real reference dataset."""
    st = ProjectState()  # no project data → reference fallback
    card = build_stat_scorecard(st)
    assert card.rows, "expected scored indicators on the reference dataset"
    for r in card.rows:
        assert r.indicator, "each row names an indicator"
        assert 0.0 <= r.cv_score <= 2.0
        assert 0.0 <= r.pearson_score <= 2.0
        assert 0.0 <= r.vif_score <= 2.0
        assert _approx(r.total, r.cv_score + r.pearson_score + r.vif_score)
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
    test_end_to_end_reference()
    print("\nall statistical-score tests passed")
