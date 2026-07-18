"""Unit checks for the dbt service's pure logic — no dbt binary or file store needed.

Run:  PYTHONPATH=. .venv/bin/python -m app.dataeng.dbt._test_service
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd

from app.dataeng.dbt import service, target_schema


def test_target_schema_default() -> None:
    cols = target_schema.default_target_schema()
    names = [c.name for c in cols]
    assert "brand" in names and "metric" in names and "value" in names, names
    assert next(c for c in cols if c.name == "value").required is True
    assert next(c for c in cols if c.name == "l5").required is False
    # columns_and_docs falls back to the default when st has no custom schema
    st = SimpleNamespace(target_schema=None)
    columns, docs = target_schema.columns_and_docs(st)
    assert columns == names
    assert "[required]" in docs["brand"]
    print(f"[schema] default has {len(cols)} columns, required flags correct")


def test_extract_desc() -> None:
    sql = "-- desc: Standardise channels and sum sales.\nselect 1"
    assert service._extract_desc(sql) == "Standardise channels and sum sales."
    assert service._extract_desc("select 1") == ""
    print("[desc] leading -- desc: comment extracted")


def test_register_indicators() -> None:
    df = pd.DataFrame({
        "brand": ["M"] * 4,
        "channel": ["天猫", "京东", "天猫", "京东"],
        "year": [2023, 2024, 2023, 2024],
        "month": [202301, 202401, 202301, 202401],
        "l1": ["KPI"] * 4, "l2": ["Sell-out"] * 4, "l3": ["Volume"] * 4, "l4": [""] * 4,
        "metric_type": ["Y", "Y", "Y", "Y"],
        "metric": ["sell-out volume", "sell-out volume", "tv grp", "tv grp"],
        "value": [100.0, 80.0, 5.0, 6.0],
    })
    st = SimpleNamespace(indicators=[])
    asset = SimpleNamespace(id="da-x", name="Channel Sales")
    made = service.register_indicators(st, asset, df)
    by_metric = {i.metric: i for i in made}
    assert set(by_metric) == {"sell-out volume", "tv grp"}, by_metric
    so = by_metric["sell-out volume"]
    assert so.metric_type == "Y" and so.l1 == "KPI" and so.l3 == "Volume"
    assert so.coverage_start == "202301" and so.coverage_end == "202401"
    assert so.rows == 2 and so.asset_name == "Channel Sales"
    # re-registering replaces this asset's indicators (no duplicates)
    again = service.register_indicators(st, asset, df)
    assert len(st.indicators) == len(again) == 2, st.indicators
    print(f"[indicators] {len(made)} registered, coverage + replace-on-rerun correct")


def test_conformance() -> None:
    from app.domain.models import TargetColumn

    class FakeWS:
        warehouse_path = __import__("pathlib").Path("/tmp")
        df: pd.DataFrame

        def read_relation(self, _m):
            return self.df

    st = SimpleNamespace(target_schema=[
        TargetColumn(name="channel", kind="dimension", required=True,
                     standardValues=["天猫", "京东"]),
        TargetColumn(name="region", kind="dimension", required=False),  # no std values
        TargetColumn(name="value", kind="value", required=True),
    ])
    ws = FakeWS()
    # conformant: required present, enum in-vocab, period_date allowed as extra
    ws.df = pd.DataFrame({"channel": ["天猫", "京东"], "region": ["E", "N"],
                          "value": [1.0, 2.0], "period_date": [None, None]})
    c = service._check_conformance(st, ws, "mart")
    assert c.ok and c.checked and not c.missing_required and not c.extra, c
    assert c.unenforced_dimensions == ["region"], c.unenforced_dimensions
    # non-conformant: missing required 'value', enum violation, stray column
    ws.df = pd.DataFrame({"channel": ["天猫", "拼多多"], "stray": [9, 9]})
    c = service._check_conformance(st, ws, "mart")
    assert not c.ok and c.missing_required == ["value"], c
    assert c.enum_violations and c.enum_violations[0].values == ["拼多多"], c
    assert c.extra == ["stray"], c.extra
    print("[conformance] required-field + enum + stray checks correct")


def main() -> int:
    test_target_schema_default()
    test_extract_desc()
    test_register_indicators()
    test_conformance()
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
