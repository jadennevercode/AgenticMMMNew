"""Contract test for the Business Validation dataset feed. Run:
    PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_dataset.py
"""
import pandas as pd

from app.dataeng.validation_dataset import build_validation_dataset


class _St:
    """Minimal stand-in: build_validation_dataset only calls model_df(st)."""


def _fake_df() -> pd.DataFrame:
    # Two years of one metric so YoY is computable for the 2nd year.
    return pd.DataFrame(
        {
            "l1": ["MARKETING"] * 4,
            "l2": ["Media"] * 4,
            "l3": ["TV"] * 4,
            "l4": ["TV spend"] * 4,
            "metric": ["花费"] * 4,
            "metric_type": ["spending"] * 4,
            "value": [100.0, 200.0, 150.0, 260.0],
            "year": [2024, 2024, 2025, 2025],
            "month": [202401, 202402, 202501, 202502],
            "source": ["deck.xlsx"] * 4,
            "brand": ["Mizone"] * 4,
            "channel_type": ["TV"] * 4,
            "province_group": ["East"] * 4,
        }
    )


def main() -> None:
    import app.agents.dataset_cache as dc
    dc.model_df = lambda st=None: _fake_df()  # monkeypatch the cache

    out = build_validation_dataset(_St())

    fids = {c["fid"] for c in out["columns"]}
    assert {"l3", "metric", "value", "year", "period", "value_yoy"} <= fids, fids
    # value is a measure/quantitative; l3 is a dimension/nominal; period is temporal.
    by_fid = {c["fid"]: c for c in out["columns"]}
    assert by_fid["value"]["analyticType"] == "measure"
    assert by_fid["l3"]["analyticType"] == "dimension"
    assert by_fid["period"]["semanticType"] == "temporal"

    assert out["rowCount"] == 4 and out["capped"] is False

    # YoY for 2025-01 vs 2024-01 = (150-100)/100 = 50.0 ; 2024 rows have no prior → null
    rows = {r["month"]: r for r in out["rows"]}
    assert rows[202501]["value_yoy"] == 50.0, rows[202501]["value_yoy"]
    assert rows[202502]["value_yoy"] == 30.0, rows[202502]["value_yoy"]
    assert rows[202401]["value_yoy"] is None

    # Row cap trips capped=True and truncates.
    capped = build_validation_dataset(_St(), row_cap=2)
    assert capped["capped"] is True and capped["rowCount"] == 2
    print("OK validation_dataset")


if __name__ == "__main__":
    main()
