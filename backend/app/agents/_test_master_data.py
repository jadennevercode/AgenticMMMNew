"""DATA-011 / DATA-012 acceptance: master wide table + per-channel model objects.

Run: PYTHONPATH=. .venv/bin/python -m app.agents._test_master_data
"""
import pandas as pd

from app.mmm.pivot import build_model_frame


def _long_df():
    """Synthetic long table: KPI-Volume + KPI-Value, a spend driver and a rate
    (NDWD) driver, across 3 channels × 2 geos × 24 months."""
    rows = []
    for ch in ("MT", "TT", "EC"):
        for geo in ("East", "West"):
            for y in (2024, 2025):
                for mo in range(1, 13):
                    ym = y * 100 + mo
                    base = dict(brand="b", province_group=geo, channel_type=ch, channel=ch,
                                year=y, month=ym, source="up", l2="x", l5="", l6="", l7="", l8="")
                    rows += [
                        {**base, "l1": "KPI", "l3": "Volume", "l4": "", "metric": "本品销量",
                         "metric_type": "Y", "value": 1000.0 + mo},
                        {**base, "l1": "KPI", "l3": "Value", "l4": "", "metric": "本品销售额",
                         "metric_type": "Y", "value": (1000.0 + mo) * 3.5},
                        {**base, "l1": "MARKETING FACTOR", "l3": "投放", "l4": "信息流",
                         "metric": "投放花费", "metric_type": "spending", "value": 100.0 * mo},
                        {**base, "l1": "COMMERCIAL FACTOR", "l3": "渠道", "l4": "商超",
                         "metric": "NDWD覆盖率", "metric_type": "X", "value": 60.0},
                    ]
    return pd.DataFrame(rows)


def test_per_channel_model_objects():
    """DATA-012: each first-level channel is its own model object with its own
    Y/X, and channels don't cross into each other."""
    df = _long_df()
    for ch in ("MT", "TT", "EC"):
        mf = build_model_frame(df, ch)
        assert mf.y_metric == "本品销量", f"{ch}: default Y should be Volume, got {mf.y_metric}"
        assert mf.n_obs == 24, f"{ch}: expected 24 monthly obs, got {mf.n_obs}"
    # isolation: MT's frame is built only from MT rows (n_obs stays 24, not 72).
    assert build_model_frame(df, "MT").n_obs == 24


def test_master_table_acceptance():
    """DATA-011: unique period key, rate averaged (not summed), drop traceable."""
    import types

    import app.agents.dataset_cache as dc
    import app.agents.master_data as md

    df = _long_df()
    dc._PROJECT_CACHE["mock-test"] = df
    st = types.SimpleNamespace(project_id="mock-test", indicators=[])

    # No drops → all four indicators adopted; period key unique; NDWD averaged.
    from app.agents.ledger import ModelSelection
    md.model_selection = lambda s: ModelSelection()
    mt = md.master_table(st, brand=["b"], channel_type=["MT"], grain="month")
    periods = [r[0] for r in mt["rows"]]
    assert len(periods) == len(set(periods)), "period key must be unique per row"
    assert mt["kpi"] == "本品销量", "primary KPI should be Volume (matches OLS default Y)"
    ndwd_i = mt["columns"].index("NDWD覆盖率")
    # East+West both 60 → averaged 60, NOT summed 120.
    assert abs(mt["rows"][0][ndwd_i] - 60.0) < 0.1, f"rate must average, got {mt['rows'][0][ndwd_i]}"
    spend_i = mt["columns"].index("投放花费")
    assert mt["rows"][0][spend_i] > 120, "spend must still sum across the two geos"

    # Drop traceability: a ledger exclusion removes the indicator from the table.
    md.model_selection = lambda s: ModelSelection(exclude=frozenset([("", "投放花费")]))
    dropped = md.master_table(st, brand=["b"], channel_type=["MT"], grain="month")
    assert "投放花费" not in dropped["columns"], "a rejected indicator must not reach the table"

    dc._PROJECT_CACHE.pop("mock-test", None)


if __name__ == "__main__":
    test_per_channel_model_objects()
    test_master_table_acceptance()
    print("DATA-011/012 master data + per-channel model objects: ALL PASS")
