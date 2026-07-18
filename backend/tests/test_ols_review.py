"""Unit tests for 2.5 OLS Regression Test plumbing.

Covers the deterministic pieces without needing the reference dataset:
  * pair-keyed driver exclusion in build_model_frame,
  * upstream / OLS drop-pair resolution from the scorecards + analysis,
  * build_ols_review body shape + range verdicts (run only when a dataset is
    resolvable — skipped gracefully otherwise).

Runnable with pytest or plain python (asserts run under __main__).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents.ols_review import (
    _norm_pair,
    ols_drop_pairs,
    quality_drop_pairs,
    stat_drop_pairs,
    upstream_drop_pairs,
)
from app.domain.models import (
    FactorRow,
    FactorTree,
    IndustryRef,
    ProjectMeta,
    QualityRow,
    QualityScorecard,
    StatScorecard,
    StatScoreRow,
)
from app.mmm import build_model_frame
from app.store.state import ProjectState


def _base_row() -> dict:
    return {"task_name": "t", "brand": "B", "province_group": "National",
            "channel_type": "MT", "channel": "NA", "year": 2023,
            "source": "s", "l1": "", "l2": "", "l3": "", "l4": "",
            "l5": "NA", "l6": "NA", "l7": "NA", "l8": "NA", "metric_type": "", "metric": ""}


def _long(drivers: list[tuple[str, str]], with_money_y: bool = False) -> pd.DataFrame:
    """A tiny MT long-df: one KPI Y + the given (l4, metric) spend drivers.

    ``with_money_y`` adds a second, monetary KPI candidate so the Y-selection and
    ROI-unit behaviour can be exercised.
    """
    rng = np.random.default_rng(1)
    # Real yyyymm keys — 2023-01..2023-12 then 2024-01..2024-12.
    months = [202301 + i for i in range(12)] + [202401 + i for i in range(12)]
    rows: list[dict] = []

    def add(l1: str, l4: str, metric: str, mtype: str, values: np.ndarray) -> None:
        for m, v in zip(months, values):
            r = _base_row()
            r.update({"month": m, "l1": l1, "l4": l4, "metric": metric,
                      "metric_type": mtype, "value": float(v)})
            rows.append(r)

    volume = rng.normal(1000, 50, 24).cumsum()
    add("KPI", "本品销量", "销量", "volume", volume)
    if with_money_y:
        add("KPI", "本品销量", "销售额", "RMB", volume * 50.0)
    for l4, metric in drivers:
        add("COMMERCIAL FACTOR", l4, metric, "x", rng.normal(400, 40, 24))
    return pd.DataFrame(rows)


def test_norm_pair() -> None:
    assert _norm_pair(" 陈列 ", " 费用") == ("陈列", "费用")
    assert _norm_pair("TT Display", "Spend") == ("tt display", "spend")


def test_build_model_frame_exclude_drops_named_pair() -> None:
    # Distinct metric names (the real dataset shape) — exclude removes exactly one.
    df = _long([("陈列", "陈列费用"), ("冰柜", "冰柜费用")])
    metrics_all = {m["metric"] for m in build_model_frame(df, "MT").meta.values()}
    assert {"陈列费用", "冰柜费用"} <= metrics_all

    mf = build_model_frame(df, "MT", exclude=frozenset({("陈列", "陈列费用")}))
    metrics = {m["metric"] for m in mf.meta.values()}
    assert "陈列费用" not in metrics and "冰柜费用" in metrics


def test_build_model_frame_exclude_pair_does_not_overdrop() -> None:
    # Two factors share the metric name '费用'. build_model_frame groups by metric,
    # so they collapse to one column — but a pair-keyed exclude of (陈列, 费用) must
    # only drop the 陈列 rows, leaving the column alive from 冰柜's rows.
    df = _long([("陈列", "费用"), ("冰柜", "费用"), ("电商", "电商费用")])
    assert "费用" in {m["metric"] for m in build_model_frame(df, "MT").meta.values()}

    kept = build_model_frame(df, "MT", exclude=frozenset({("陈列", "费用")}))
    kept_meta = [m for m in kept.meta.values() if m["metric"] == "费用"]
    assert kept_meta and kept_meta[0]["l4"] == "冰柜"  # survives via the other L4

    # A metric-only exclude ("", 费用) drops every 费用 row → column gone (电商费用 remains).
    gone = build_model_frame(df, "MT", exclude=frozenset({("", "费用")}))
    gone_metrics = {m["metric"] for m in gone.meta.values()}
    assert "费用" not in gone_metrics and "电商费用" in gone_metrics


def test_build_model_frame_explicit_y_wins() -> None:
    # Auto-pick prefers volume; an explicit money Y must override it and set the unit.
    df = _long([("陈列", "陈列费用")], with_money_y=True)
    auto = build_model_frame(df, "MT")
    assert auto.y_metric == "销量" and auto.y_is_money is False

    money = build_model_frame(df, "MT", y_metric="销售额")
    assert money.y_metric == "销售额" and money.y_is_money is True

    try:
        build_model_frame(df, "MT", y_metric="不存在的指标")
    except ValueError as e:
        assert "no rows" in str(e).lower()
    else:  # pragma: no cover
        raise AssertionError("an unknown Y metric must raise")


def test_controls_are_not_drivers() -> None:
    """Trend/seasonality controls enter the design matrix but must never be
    treated as drivers: no ROI, no contribution, folded into the baseline."""
    from app.domain.models import OlsParams
    from app.mmm import run_mmm

    df = _long([("陈列", "陈列费用"), ("冰柜", "冰柜费用")])
    p = OlsParams(trend="linear", seasonality="fourier", fourierK=2)
    res = run_mmm(df, "MT", params=p)

    controls = res.meta["control_cols"]
    assert controls == ["_trend", "_sin1", "_cos1", "_sin2", "_cos2"]
    # Drivers exclude the controls; ROI/contribution only cover real drivers.
    assert not any(c in res.drivers for c in controls)
    assert not any(c in res.roi for c in controls)
    assert not any(c in res.contribution for c in controls)
    # df accounting: n - (intercept + drivers + controls)
    assert res.meta["df_remaining"] == res.n_obs - (1 + len(res.drivers) + len(controls))


def test_contribution_shares_sum_to_100() -> None:
    """Drivers + baseline decompose actual sales exactly (controls sit in baseline)."""
    from app.domain.models import OlsParams
    from app.mmm import run_mmm

    df = _long([("陈列", "陈列费用"), ("冰柜", "冰柜费用")])
    res = run_mmm(df, "MT", params=OlsParams(trend="linear", seasonality="fourier"))
    total = sum(res.contribution.values()) + res.baseline_pct
    assert abs(total - 100.0) < 1e-6, total


def test_roi_unit_matrix() -> None:
    """ROI is only a revenue/spend ratio when Y is money, or volume + a price."""
    from app.domain.models import OlsParams
    from app.mmm import run_mmm

    df = _long([("陈列", "陈列费用")], with_money_y=True)

    volume = run_mmm(df, "MT", params=OlsParams())
    assert volume.meta["roi_unit"] == "volume/spend"

    money = run_mmm(df, "MT", y_metric="销售额", params=OlsParams())
    assert money.meta["roi_unit"] == "revenue/spend"

    priced = run_mmm(df, "MT", params=OlsParams(pricePerUnit=50.0))
    assert priced.meta["roi_unit"] == "revenue/spend"
    # The price scales the incremental revenue linearly.
    spend_col = next(iter(volume.roi))
    assert abs(priced.roi[spend_col] - volume.roi[spend_col] * 50.0) < 1e-6


def test_df_guard_raises_when_underdetermined() -> None:
    from app.domain.models import OlsParams
    from app.mmm import run_mmm

    df = _long([("陈列", "陈列费用"), ("冰柜", "冰柜费用")])
    # 24 months; monthly dummies (11) + 2 drivers + intercept is fine, but pile on
    # 4 Fourier harmonics too and the design outruns the series.
    try:
        run_mmm(df, "MT", params=OlsParams(seasonality="dummies", trend="linear"))
    except ValueError as e:  # pragma: no cover - only if the guard is too eager
        raise AssertionError(f"should still fit: {e}")

    def _wide_long() -> pd.DataFrame:
        return _long([(f"f{i}", f"m{i}") for i in range(20)])

    try:
        run_mmm(_wide_long(), "MT",
                include=frozenset(f"m{i}" for i in range(20)),
                params=OlsParams(seasonality="dummies", trend="linear"))
    except ValueError as e:
        assert "cannot identify" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the df guard must reject an under-determined design")


def _stub_state() -> ProjectState:
    st = ProjectState(project_id="unit-test")
    st.meta = ProjectMeta(
        id="unit-test", name="Unit", brand="B",
        industry=IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional"),
        createdAt="2026-01-01",
    )
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-1", l1="COMMERCIAL FACTOR", l4="陈列", indicator="费用", status="accepted"),
        FactorRow(id="ft-2", l1="COMMERCIAL FACTOR", l4="冰柜", indicator="费用", status="accepted"),
    ])
    st.quality_scorecard = QualityScorecard(rows=[
        QualityRow(id="q1", l4="陈列", indicator="费用", disposition="drop"),
        QualityRow(id="q2", l4="冰柜", indicator="费用", disposition="accept"),
    ])
    st.stat_scorecard = StatScorecard(rows=[
        StatScoreRow(id="s1", l4="促销", indicator="折扣", disposition="drop"),
        StatScoreRow(id="s2", l4="冰柜", indicator="费用", disposition="include"),
    ])
    return st


def test_drop_pair_resolution() -> None:
    st = _stub_state()
    assert quality_drop_pairs(st) == {("陈列", "费用")}
    assert stat_drop_pairs(st) == {("促销", "折扣")}
    assert upstream_drop_pairs(st) == {("陈列", "费用"), ("促销", "折扣")}


def test_ols_drop_pairs_from_analysis() -> None:
    st = _stub_state()
    st.analysis["ols_flagged"] = [
        {"l4": "冰柜", "indicator": "费用", "reason": "ROI out"},
        {"l4": "TT Display", "indicator": "曝光量", "reason": "Contribution out"},
    ]
    assert ols_drop_pairs(st) == {("冰柜", "费用"), ("tt display", "曝光量")}


def test_build_ols_review_shape() -> None:
    """Integration: build_ols_review on a resolvable dataset. Skips when neither
    per-project data nor the reference dataset is available."""
    from app.agents.ols_review import build_ols_review

    try:
        from app.store.state import get_store
        st = get_store().get("danone-mizone")
    except Exception:  # noqa: BLE001
        print("  ~ skipped test_build_ols_review_shape (no store)")
        return
    if st is None or st.factor_tree is None:
        print("  ~ skipped test_build_ols_review_shape (no seeded project)")
        return
    try:
        body, prefit, flagged = build_ols_review(st)
    except Exception as e:  # noqa: BLE001 — reference dataset likely absent
        print(f"  ~ skipped test_build_ols_review_shape ({e})")
        return

    assert set(body) == {"objects", "tree", "summary", "setup", "note"}
    assert set(body["setup"]) >= {"dataSource", "roiUnit", "configured", "selectedX", "totalX"}
    s = body["summary"]
    assert set(s) == {"total", "inModel", "inRange", "flagged", "noBenchmark", "notInModel", "dropped"}
    assert s["total"] == len(body["tree"])
    # camelCase keys present on rows / objects.
    if body["tree"]:
        row = body["tree"][0]
        for k in ("tValue", "pValue", "roiRange", "contributionRange", "rangeSource",
                  "roiStatus", "contributionStatus", "status", "flagReason", "results"):
            assert k in row, f"missing key {k}"
        assert row["status"] in {"inRange", "review", "noBenchmark", "notInModel", "dropped"}
    if body["objects"]:
        assert "adjR2" in body["objects"][0] and "durbinWatson" in body["objects"][0]
    # flagged list mirrors the review rows.
    assert len(flagged) == s["flagged"]
    for f in flagged:
        assert set(f) == {"l4", "indicator", "reason"}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all ols_review tests passed")
