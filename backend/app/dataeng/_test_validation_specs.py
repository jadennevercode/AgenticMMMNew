"""Run: PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_specs.py"""
import pandas as pd

from app.dataeng.validation_specs import default_specs


class _St:
    factor_tree = None


def _fake_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "l1": ["KPI", "MARKETING", "MARKETING"],
            "l2": ["Sales", "Media", "Media"],
            "l3": ["Sell-out", "TV", "TV"],
            "l4": ["", "TV spend", "TV grp"],
            "metric": ["销量", "花费", "grp"],
            "metric_type": ["Y", "spending", "X"],
            "value": [1000.0, 200.0, 50.0],
            "year": [2025, 2025, 2025],
            "month": [202501, 202501, 202501],
            "source": ["d"] * 3, "brand": ["M"] * 3,
            "channel_type": ["TV"] * 3, "province_group": ["E"] * 3,
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
    print("OK validation_specs")


if __name__ == "__main__":
    main()
