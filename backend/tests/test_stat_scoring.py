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


def test_panel_yoy_removes_level_trend_and_season() -> None:
    """A pure seasonal-plus-trend series carries no year-over-year signal beyond its
    growth — which is exactly the confound that made every indicator correlate."""
    import pandas as pd

    from app.agents.stat_scoring import _panel_yoy

    t = np.arange(24, dtype=float)
    season = np.sin(2 * np.pi * t / 12.0)
    a = 100.0 + 3.0 * t + 10.0 * season          # level + linear trend + seasonality
    idx = pd.MultiIndex.from_product([["MT::A"], _months(24)], names=["object", "month"])
    d = _panel_yoy(pd.Series(a, index=idx)).dropna()
    assert d.shape[0] == 12, "24 monthly points yield 12 year-over-year differences"
    # Trend growth over 12 months is constant (3 * 12) and the seasonal term cancels.
    assert np.allclose(d.to_numpy(), 36.0, atol=1e-9), f"expected a flat 36.0, got {d[:3]}"
    print("✓ YoY differencing removes level, trend and seasonality")


def test_panel_yoy_never_differences_across_a_model_object() -> None:
    """The panel stacks one channel × product after another. A positional diff down
    the stack would subtract one object's first months from the previous object's
    last ones at every boundary — a difference between two different models,
    reported as one model's year-over-year change."""
    import pandas as pd

    from app.agents.stat_scoring import _panel_yoy

    months = _months(24)
    # Two objects on wildly different scales: a boundary leak is unmistakable.
    idx = pd.MultiIndex.from_product([["MT::A", "TT::A"], months], names=["object", "month"])
    s = pd.Series(list(np.arange(24, dtype=float)) + list(np.arange(24, dtype=float) + 10_000),
                  index=idx)
    d = _panel_yoy(s)

    # Each object loses exactly its own first 12 months to the difference.
    for obj in ("MT::A", "TT::A"):
        own = d.loc[obj]
        assert own.iloc[:12].isna().all(), f"{obj} must not difference into thin air"
        assert np.allclose(own.iloc[12:].to_numpy(), 12.0), (
            f"{obj} should show its own +12 growth, got {own.iloc[12:].to_numpy()[:3]}")
    assert d.notna().sum() == 24, "12 usable differences per object, no boundary rows"
    print("✓ year-over-year differencing stays inside each model object")


def test_detrend_guard_is_on_the_result_size_not_the_input_size() -> None:
    """A 13-14 month project must not be differenced down to 1-2 rows -- that
    starves Pearson's `mask.sum() < 3` guard and silently drops everything with
    nothing explaining why."""
    from app.agents.stat_scoring import MIN_DETRENDED_POINTS, can_detrend

    assert MIN_DETRENDED_POINTS == 6
    # 14 months would difference down to 2 rows (14-12) -- below the minimum, so
    # the screening runs on levels instead of being starved.
    assert not can_detrend(14)
    # 18 months differences down to exactly 6 rows -- right at the threshold.
    assert can_detrend(18)
    print("✓ the detrend guard is on the RESULT size, not the input size")


def test_reindex_onto_complete_calendar_pairs_correct_months() -> None:
    """A month missing anywhere in the panel must not turn a 12-row difference
    into a '12 rows ago' one across the discontinuity."""
    import pandas as pd

    from app.agents.stat_scoring import _complete_month_index, _panel_yoy

    # Two years of months with March 2024 (202403) missing from the raw panel.
    months = [202401, 202402, 202404, 202405, 202406, 202407, 202408, 202409,
              202410, 202411, 202412,
              202501, 202502, 202503, 202504, 202505, 202506, 202507, 202508,
              202509, 202510, 202511, 202512]
    values = pd.Series(range(len(months)), index=months, dtype=float)

    def _stack(s: pd.Series) -> pd.Series:
        return pd.Series(s.to_numpy(), index=pd.MultiIndex.from_product(
            [["MT::A"], list(s.index)], names=["object", "month"]))

    # Without the calendar reindex, "12 rows ago" is not "12 months ago" once a
    # month is missing: position 12 in the raw (gapped) array is Feb-2025, not
    # Jan-2025 -- an off-by-one diff across the March-2024 discontinuity.
    assert months[12] == 202502
    d_raw = _panel_yoy(_stack(values)).dropna()
    assert d_raw.iloc[0] == values.loc[202502] - values.loc[202401]  # the bug this fixes

    full_idx = _complete_month_index(values.index)
    assert 202403 in full_idx and len(full_idx) == 24
    reindexed = values.reindex(full_idx, fill_value=0.0)
    d_fixed = _panel_yoy(_stack(reindexed)).dropna()
    assert d_fixed.shape[0] == 12
    # Position 0 of the fixed differences is now truly Jan-2025 minus Jan-2024.
    assert d_fixed.iloc[0] == values.loc[202501] - values.loc[202401]
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
    # Worst-first ordering, per model object: rows are grouped by object first
    # (`all_rows.sort(key=lambda r: (r.object, r.total, r.indicator))`, per-channel
    # screening screens each channel_type on its own data slice) and worst-first
    # by total within each group — not a single global total ordering across
    # every channel, which per-object grouping makes impossible to satisfy in
    # general (a later object's best row can easily beat an earlier object's
    # worst one).
    from itertools import groupby
    for _obj, rows in groupby(card.rows, key=lambda r: r.object):
        totals = [r.total for r in rows]
        assert totals == sorted(totals), "rows should be worst-first by total within each object"
    # Kept set excludes dropped. `card.rows` is per (object, indicator) — the
    # real reference dataset screens each channel_type on its own slice — but
    # `accepted_stat_labels` dedups to one verdict per distinct indicator
    # label (kept if kept in ANY channel), so "kept == rows - dropped" no
    # longer holds row-for-row. Assert the dedup invariant directly instead.
    from collections import defaultdict
    label_dispositions: dict[str, set[str]] = defaultdict(set)
    for r in card.rows:
        label = f"{r.l4 or r.l3} · {r.indicator}".strip(" ·")
        label_dispositions[label].add(r.disposition)
    kept = accepted_stat_labels(card)
    assert len(kept) == len(set(kept)), "kept labels must be deduped"
    expected_kept = {lbl for lbl, dispositions in label_dispositions.items()
                      if dispositions != {"drop"}}
    assert set(kept) == expected_kept
    # Artifact body: two sheets (rules + per-indicator results), every column rendered.
    body = stat_sheet(card)
    assert [s["name"] for s in body["sheets"]] == ["Scoring rules", "Statistical score"]
    assert body["sheets"][1]["columns"] == STAT_COLUMNS
    assert len(body["sheets"][1]["rows"]) == len(card.rows)
    assert all(len(r) == len(STAT_COLUMNS) for r in body["sheets"][1]["rows"])
    print(f"✓ end-to-end reference — {len(card.rows)} indicators scored, {len(kept)} kept")


# ── 2.4 correctness regressions (D1–D4) ─────────────────────────────────────
# Each of these fails on the pre-fix implementation. They are the record of what
# "the statistics look wrong" actually was.


def _panel(rows: list[dict]):
    """A minimal national long table + a state whose model_df is exactly it."""
    import types

    import pandas as pd

    import app.agents.dataset_cache as dc

    df = pd.DataFrame([{
        "task_name": "TOTAL", "brand": "b", "province_group": "National",
        "channel_type": "TOTAL", "channel": "TOTAL", "source": "up",
        "l5": "", "l6": "", "l7": "", "l8": "", **r,
    } for r in rows])
    pid = f"stat-test-{len(rows)}"
    dc.set_project_dataset(pid, df)
    st = types.SimpleNamespace(
        project_id=pid, indicators=[], metric_type_overrides={},
        aggregation_overrides={}, quality_scorecard=None, stat_scorecard=None,
    )
    return df, st, pid


def _months(n: int, start: int = 202201):
    y, m = divmod(start, 100)
    out = []
    for _ in range(n):
        out.append(y * 100 + m)
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def test_vif_band_matches_the_workbook() -> None:
    """The 2.33 band is the spec, verbatim: VIF <= 1 scores 1, 1 < VIF < 5 scores
    0.5, VIF >= 5 scores 0. An orthogonal driver must therefore be able to reach
    ``Good`` — `vif_all` floors at exactly 1.0, so the top band is attainable."""
    for vif, want in [(0.5, 1.0), (1.0, 1.0), (1.0001, 0.5), (2.0, 0.5),
                      (4.999, 0.5), (5.0, 0.0), (VIF_MAX, 0.0)]:
        got = score_statistical(0.0, 0.0, vif).vif_score
        assert got == want, f"vif={vif} → {got}, want {want}"

    rng = np.random.default_rng(7)
    orth = rng.normal(size=(60, 3))
    vifs = vif_all(orth)
    assert float(np.max(vifs)) < 5.0, f"independent columns should not be collinear: {vifs}"
    # A single column has no peers to be inflated by — VIF is exactly 1.
    assert vif_all(rng.normal(size=(60, 1))).tolist() == [1.0]
    good = score_statistical(0.4, 0.8, 1.0)
    assert good.verdict == "Good" and good.total == 1.0
    print("✓ VIF band matches the workbook and Good is reachable")


def test_gaps_are_not_zero_filled() -> None:
    """A late-starting indicator must be scored on the months it actually covers.

    Zero-filling turned "did not exist yet" into "was zero", which inflated CV,
    manufactured correlation against the KPI's trend, and made every short
    indicator look collinear with every other short one.
    """
    import app.agents.dataset_cache as dc
    from app.agents.stat_scoring import _indicator_series

    months = _months(36)
    rows = []
    for i, ym in enumerate(months):
        rows.append({"year": ym // 100, "month": ym, "l1": "KPI", "l2": "", "l3": "V",
                     "l4": "", "metric": "本品销量", "metric_type": "Y",
                     "value": 1000.0 + i})
        # A full-history driver, so the panel's own index spans all 36 months.
        rows.append({"year": ym // 100, "month": ym, "l1": "MARKETING FACTOR",
                     "l2": "", "l3": "投放", "l4": "长期因子", "metric": "长期曝光",
                     "metric_type": "X", "value": 400.0 + (i % 6) * 20})
        # A driver that only exists for the final 12 months.
        if i >= 24:
            rows.append({"year": ym // 100, "month": ym, "l1": "MARKETING FACTOR",
                         "l2": "", "l3": "投放", "l4": "信息流", "metric": "曝光量",
                         "metric_type": "X", "value": 500.0 + (i % 5) * 30})
    df, st, pid = _panel(rows)
    metas, wide = _indicator_series(df, st)
    late = next(m for m in metas if m["indicator"] == "曝光量")
    col = wide[late["col"]]

    assert late["months"] == 12, f"observed months should be 12, got {late['months']}"
    assert col.isna().sum() == 24, "the 24 months before the indicator existed must stay NaN"
    assert not (col.fillna(-1) == 0.0).any(), "no month may be silently zero-filled"
    # The zero-filled series would have had a far larger min-max span.
    assert reference_cv(col.to_numpy(dtype=float)) != reference_cv(
        col.fillna(0.0).to_numpy(dtype=float)), "CV must differ from the zero-filled CV"
    dc.invalidate_project(pid)
    print("✓ gaps stay NaN — CV/Pearson/VIF are not scoring the padding")


def test_short_coverage_is_scored_unconsiderable_with_a_reason() -> None:
    """An indicator below the coverage minimum is shown with its reason, not
    quietly dropped — the funnel must not lose rows it cannot explain."""
    import app.agents.dataset_cache as dc
    from app.agents.stat_scoring import MIN_SCORED_MONTHS, build_stat_scorecard

    months = _months(30)
    rows = []
    for i, ym in enumerate(months):
        rows.append({"year": ym // 100, "month": ym, "l1": "KPI", "l2": "", "l3": "V",
                     "l4": "", "metric": "本品销量", "metric_type": "Y",
                     "value": 1000.0 + (i % 7) * 40})
        rows.append({"year": ym // 100, "month": ym, "l1": "MARKETING FACTOR", "l2": "",
                     "l3": "投放", "l4": "长期因子", "metric": "长期曝光",
                     "metric_type": "X", "value": 300.0 + (i % 6) * 25})
        if i >= 24:  # 6 months only — below MIN_SCORED_MONTHS
            rows.append({"year": ym // 100, "month": ym, "l1": "MARKETING FACTOR",
                         "l2": "", "l3": "投放", "l4": "短期因子", "metric": "短期曝光",
                         "metric_type": "X", "value": 100.0 + i * 9})
    df, st, pid = _panel(rows)
    card = build_stat_scorecard(st)
    short = next(r for r in card.rows if r.indicator == "短期曝光")
    assert short.total == 0.0 and short.auto_verdict == "unconsiderable"
    assert short.disposition == "drop"
    assert str(MIN_SCORED_MONTHS) in short.rationale and "month" in short.rationale.lower()
    dc.invalidate_project(pid)
    print(f"✓ under-{MIN_SCORED_MONTHS}-month indicators are scored with an explicit reason")


def test_pearson_uses_the_y_chosen_at_2_1() -> None:
    """2.4 correlates against the response the user tagged at Data Processing,
    not against an independently auto-picked one."""
    import app.agents.dataset_cache as dc
    from app.agents.indicator_metadata import indicator_key
    from app.agents.stat_scoring import _monthly_y

    months = _months(24)
    rows = []
    for i, ym in enumerate(months):
        base = {"year": ym // 100, "month": ym, "l2": "", "l4": ""}
        rows.append({**base, "l1": "KPI", "l3": "Volume", "metric": "本品销量",
                     "metric_type": "Y", "value": 1000.0 + i * 10})
        rows.append({**base, "l1": "KPI", "l3": "Value", "metric": "本品销售额",
                     "metric_type": "Y", "value": 7000.0 - i * 5})
    df, st, pid = _panel(rows)

    # No override → the volume-preferring auto-pick, exactly as before.
    assert float(_monthly_y(df, st).iloc[0]) == 1000.0

    # The user picks the Value KPI at 2.1 → 2.4 must follow.
    st.metric_type_overrides = {indicator_key("", "本品销售额"): "Y"}
    y = _monthly_y(df, st)
    assert float(y.iloc[0]) == 7000.0, f"2.4 must score against the configured Y, got {y.iloc[0]}"
    dc.invalidate_project(pid)
    print("✓ Pearson is measured against the Y chosen at 2.1")


def test_average_metric_is_not_summed() -> None:
    """A rate split across sub-paths averages. Summing it produced a series with
    no meaning, and CV / Pearson / VIF were scoring that series."""
    import app.agents.dataset_cache as dc
    from app.agents.indicator_metadata import indicator_key
    from app.agents.stat_scoring import _indicator_series

    months = _months(24)
    rows = []
    for i, ym in enumerate(months):
        base = {"year": ym // 100, "month": ym, "l2": ""}
        rows.append({**base, "l1": "KPI", "l3": "V", "l4": "", "metric": "本品销量",
                     "metric_type": "Y", "value": 1000.0 + i})
        # One indicator, two L5 residual paths at the same month.
        for path in ("East", "West"):
            rows.append({**base, "l1": "COMMERCIAL FACTOR", "l3": "渠道", "l4": "商超",
                         "metric": "NDWD覆盖率", "metric_type": "X",
                         "value": 60.0 + (i % 4) * 2, "l5": path})
    df, st, pid = _panel(rows)
    df["l5"] = [r.get("l5", "") for r in rows]

    metas, wide = _indicator_series(df, st)
    ndwd = next(m for m in metas if m["indicator"] == "NDWD覆盖率")
    first = float(wide[ndwd["col"]].iloc[0])
    assert abs(first - 60.0) < 1e-6, f"a rate must average across paths, got {first}"

    # And an explicit SUM override at 2.1 must be obeyed just as literally.
    st.aggregation_overrides = {indicator_key("商超", "NDWD覆盖率"): "sum"}
    metas2, wide2 = _indicator_series(df, st)
    ndwd2 = next(m for m in metas2 if m["indicator"] == "NDWD覆盖率")
    assert abs(float(wide2[ndwd2["col"]].iloc[0]) - 120.0) < 1e-6
    dc.invalidate_project(pid)
    print("✓ the 2.1 aggregation choice governs the 2.4 monthly roll-up")


def test_vif_is_measured_against_a_model_not_the_whole_universe() -> None:
    """The root cause of "2.4 drops everything".

    VIF is a design-matrix property. Asking it of every candidate at once, on a
    panel with far fewer periods than candidates, puts `vif_all` in its
    pairwise-max proxy regime — and among many co-seasonal marketing series almost
    every one has a peer correlated above 0.89, so nearly all of them scored
    VIF >= 5 and the 2.33 band zeroed their total.

    The property asserted here is the one that is always true: the design-scoped
    measure runs in `vif_all`'s **identified** regime, so it is a real multivariate
    VIF, while the universe-wide call on the same panel is the pairwise-max proxy.
    Whether that comes out stricter or looser is data-dependent — on co-seasonal
    marketing series it is dramatically looser, on independent noise it is slightly
    stricter — so this deliberately does not assert a direction.
    """
    from app.agents.stat_scoring import SCREEN_DESIGN_COLS, _design_vifs

    rng = np.random.default_rng(11)
    n_periods, n_cols = 24, 60
    y = rng.normal(size=n_periods)
    # Every series rides one shared season, as real marketing series do, plus its
    # own idiosyncratic movement — the shape that makes the universe-wide proxy
    # condemn almost everything.
    season = np.sin(np.arange(n_periods) * 2 * np.pi / 12)
    detr = np.column_stack([season * rng.uniform(0.5, 3.0) + rng.normal(0, 0.6, n_periods)
                            for _ in range(n_cols)])
    r = [float(np.corrcoef(detr[:, i], y)[0, 1]) for i in range(n_cols)]

    universe = vif_all(detr)
    design, base = _design_vifs(detr, r)

    assert len(base) == min(SCREEN_DESIGN_COLS, n_cols)
    assert design.shape == universe.shape
    # The universe call is under-determined (p >= n) — a proxy, by construction.
    assert detr.shape[0] <= detr.shape[1] + 1
    # The design call is not: n > k + 1, so it is the exact inv(R) diagonal.
    assert n_periods > len(base) + 1
    # A real VIF is never below 1 and every column gets one.
    assert float(design.min()) >= 1.0
    print(f"✓ VIF scope — measured against a {len(base)}-driver design "
          f"(median {float(np.median(design)):.2f}) instead of all {n_cols} candidates "
          f"(proxy median {float(np.median(universe)):.2f})")


def test_reference_verdict_histogram_is_reported() -> None:
    """Print the reference verdict distribution so a band shift is visible in the
    log. With the workbook VIF band kept verbatim, ``Good`` can legitimately be
    empty on real data — the assertion is that the histogram covers every row,
    not that every band is populated."""
    card = build_stat_scorecard(ProjectState())
    hist = {v: sum(1 for r in card.rows if r.auto_verdict == v)
            for v in ("Good", "Acceptable", "unconsiderable")}
    assert sum(hist.values()) == len(card.rows)
    print(f"✓ reference verdict histogram — {hist}")


if __name__ == "__main__":
    test_band_boundaries()
    test_verdict_thresholds()
    test_reference_cv()
    test_vif_identified_vs_underdetermined()
    test_vif_band_matches_the_workbook()
    test_panel_yoy_removes_level_trend_and_season()
    test_panel_yoy_never_differences_across_a_model_object()
    test_detrend_guard_is_on_the_result_size_not_the_input_size()
    test_reindex_onto_complete_calendar_pairs_correct_months()
    test_gaps_are_not_zero_filled()
    test_short_coverage_is_scored_unconsiderable_with_a_reason()
    test_pearson_uses_the_y_chosen_at_2_1()
    test_average_metric_is_not_summed()
    test_detrending_makes_the_screening_discriminate()
    test_end_to_end_reference()
    test_vif_is_measured_against_a_model_not_the_whole_universe()
    test_reference_verdict_histogram_is_reported()
    print("\nall statistical-score tests passed")
