"""Run: PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_specs.py"""
import pandas as pd

from app.dataeng.validation_specs import default_specs


class _St:
    factor_tree = None


def _fake_df() -> pd.DataFrame:
    # l1/l2 columns end up StringDtype; pd.NA models a genuinely-missing L2 cell
    # (mirrors how the reference-dataset loader normalizes empty dimension columns).
    # "PR" recurs under two different L1/L2 branches to exercise the l3-only dedup.
    return pd.DataFrame(
        {
            "l1": ["KPI", "MARKETING", "MARKETING", "MARKETING", "COMMERCIAL", "COMMERCIAL"],
            "l2": ["Sales", "Media", "Media", pd.NA, "Trade", "Trade"],
            "l3": ["Sell-out", "TV", "TV", "Digital", "PR", "PR"],
            "l4": ["", "TV spend", "TV grp", "Digital spend", "PR spend", "PR spend"],
            "metric": ["销量", "花费", "grp", "花费", "花费", "花费"],
            "metric_type": ["Y", "spending", "X", "spending", "spending", "spending"],
            "value": [1000.0, 200.0, 50.0, 80.0, 30.0, 30.0],
            "year": [2025] * 6,
            "month": [202501] * 6,
            "source": ["d"] * 6, "brand": ["M"] * 6,
            "channel_type": ["TV"] * 6, "province_group": ["E"] * 6,
        }
    )


def main() -> None:
    import app.agents.dataset_cache as dc
    dc.model_df = lambda st=None: _fake_df()

    specs = default_specs(_St())
    # KPI factor is the backdrop, not its own overlay tab → one tab for "TV".
    tv = [s for s in specs if s["l3"] == "TV"]
    assert len(tv) == 1, [s["l3"] for s in specs]
    enc = tv[0]["encoding"]
    assert enc["x"] == "period"
    assert enc["yKpi"] == "销量"           # the Y-tagged metric is the backdrop
    assert "花费" in enc["yOverlay"]
    assert enc["overlayKind"] == "bar"     # spend-type factor → bars
    assert tv[0]["filter"]["l3"] == "TV"
    # Fix (kpiL3): the l3 filter must also admit the KPI's own l3 so the sell-out
    # backdrop survives the preset's l3 filter (it lives under a different l3).
    assert tv[0]["filter"]["kpiL3"] == "Sell-out"

    # Fix 1: a missing L2 (pd.NA) must not leak "nan" into the title.
    digital = [s for s in specs if s["l3"] == "Digital"]
    assert len(digital) == 1, [s["l3"] for s in specs]
    assert "nan" not in digital[0]["title"].lower()
    assert digital[0]["title"] == "Digital"

    # Fix 2: same L3 ("PR") recurs under a different L1/L2 branch — dedup on l3
    # alone must collapse it to exactly one spec, and every specId must be unique.
    pr = [s for s in specs if s["l3"] == "PR"]
    assert len(pr) == 1, [s["l3"] for s in specs]
    spec_ids = [s["specId"] for s in specs]
    assert len(spec_ids) == len(set(spec_ids)), spec_ids

    print("OK validation_specs")


if __name__ == "__main__":
    main()
