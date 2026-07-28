"""Unit assertions for the restore package's pure functions.

Run: PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units
"""
from __future__ import annotations

import sys

from app.ingest.dataset import COLUMN_NAMES
from scripts.restore import curated, factor_tree, raw_export, source, taxonomy


def test_load_station() -> None:
    df = source.load_station()
    assert len(df) == 23813, f"expected 23813 station rows, got {len(df)}"
    assert list(df.columns)[:8] == [
        "Task name", "品牌", "省份组别", "渠道类型", "渠道", "年", "月", "数据源",
    ], list(df.columns)[:8]
    assert source.LEVEL_COLS == [f"数据类型Level{i}" for i in range(1, 9)]
    assert set(source.LEVEL_COLS).issubset(df.columns)
    assert len(source.BUSINESS_COLS) == 19, source.BUSINESS_COLS
    # Dirty enum values must survive verbatim — the Data Engine cleans them, not us.
    brands = set(df["品牌"].dropna().unique())
    assert "NAB " in brands and "NAB" in brands, sorted(brands)
    assert str(df["月"].dtype) == "Int64", df["月"].dtype
    assert str(df["VALUE"].dtype) == "float64", df["VALUE"].dtype


def test_load_granularity() -> None:
    g = source.load_granularity()
    assert list(g.columns) == [
        "l1", "l2", "l3", "l4", "indicator", "channel", "region",
    ], list(g.columns)
    assert len(g) == 97, len(g)
    # 66, not 65: header=1 would silently eat the first data row (品类全渠道销量).
    assert g["indicator"].nunique() == 66, g["indicator"].nunique()
    assert "品类全渠道销量" in set(g["indicator"]), "the first data row was eaten"
    for col in ("l1", "l2", "l3", "l4"):
        assert g[col].isna().sum() == 0, f"{col} still has {g[col].isna().sum()} gaps"
    rain = g[g["indicator"] == "降水量"].iloc[0]
    assert (rain["l1"], rain["l2"], rain["l3"], rain["l4"]) == (
        "生意基本盘", "外部因素", "品类趋势", "季节性趋势",
    ), rain.to_dict()


def test_derive_taxonomy() -> None:
    tmap = taxonomy.derive(source.load_station())
    assert tmap.l1 == {
        "生意基本盘": "Baseline Factor",
        "渠道成交驱动": "Marketing Factor",
        "消费者需求驱动": "Marketing Factor",
        "促销优惠": "Commercial Factor",
        "KPI": "KPI",
    }, tmap.l1
    assert tmap.evidence["l1:渠道成交驱动"] == 519, tmap.evidence
    assert tmap.evidence["l1:KPI"] == 4459, tmap.evidence
    assert tmap.metric_type["花费"] == "Spending", tmap.metric_type
    assert tmap.metric_type["箱数"] == "箱数", tmap.metric_type


def test_taxonomy_rejects_uncovered_value() -> None:
    station = source.load_station()
    station.loc[0, "数据类型Level1"] = "全新的业务分类"
    try:
        taxonomy.derive(station)
    except taxonomy.TaxonomyError as exc:
        assert "全新的业务分类" in str(exc), str(exc)
    else:
        raise AssertionError("derive() accepted an L1 value with no derivable mapping")


def test_factor_tree_union() -> None:
    tree = factor_tree.build(source.load_station(), source.load_granularity())
    assert list(tree.columns) == [
        "id", "l1", "l2", "l3", "l4", "indicator", "dimension", "source",
        "status", "rationale", "evidence", "origin", "hasData", "rows",
        "monthsCovered",
    ], list(tree.columns)
    counts = tree["origin"].value_counts().to_dict()
    assert counts == {"both": 37, "planned": 29, "data": 19}, counts
    assert len(tree) == 85, len(tree)
    assert tree["id"].is_unique
    assert tree["indicator"].is_unique
    assert set(tree["source"]) == {"template"}, set(tree["source"])
    assert set(tree["status"]) == {"baseline"}, set(tree["status"])
    planned = tree[tree["origin"] == "planned"]
    assert (planned["rows"] == 0).all() and (~planned["hasData"]).all()
    withdata = tree[tree["origin"] != "planned"]
    assert (withdata["monthsCovered"] > 0).all(), \
        withdata[withdata["monthsCovered"] == 0]["indicator"].tolist()
    assert "KPI" not in set(tree["indicator"]), "KPI leaked into the factor tree"


def test_curated_long_table() -> None:
    station = source.load_station()
    tmap = taxonomy.derive(station)
    long = curated.build(station, tmap)
    assert list(long.columns) == COLUMN_NAMES, list(long.columns)
    assert len(long) == len(station), (len(long), len(station))
    assert set(long["l1"].dropna()) <= {
        "Baseline Factor", "Marketing Factor", "Commercial Factor", "KPI",
    }, set(long["l1"].dropna())
    assert "花费" not in set(long["metric_type"].dropna())
    assert "Spending" in set(long["metric_type"].dropna())
    assert "箱数" in set(long["metric_type"].dropna())
    kpi = long[long["l1"] == "KPI"]
    assert len(kpi) == 4462, len(kpi)
    assert {"箱数", "RMB"} <= set(kpi["metric_type"].dropna()), \
        set(kpi["metric_type"].dropna())
    assert "NAB " not in set(long["brand"].dropna()), sorted(set(long["brand"].dropna()))


def test_curated_finds_drivers_and_response() -> None:
    from app.mmm.pivot import _is_y_row, is_driver_row
    station = source.load_station()
    long = curated.build(station, taxonomy.derive(station))
    assert int(is_driver_row(long).sum()) > 0, "no driver rows — l1 taxonomy is wrong"
    assert int(_is_y_row(long).sum()) > 0, "no Y rows — the KPI l1 tag was lost"


def test_safe_name() -> None:
    assert raw_export.safe_name("Trade ANP 线下数据-Sandro") == "Trade ANP 线下数据-Sandro"
    assert raw_export.safe_name("a/b:c*d?e") == "a_b_c_d_e"
    assert len(raw_export.safe_name("x" * 60)) <= 31
    assert raw_export.safe_name("   ") == "unnamed"


TESTS = [
    test_load_station,
    test_load_granularity,
    test_derive_taxonomy,
    test_taxonomy_rejects_uncovered_value,
    test_factor_tree_union,
    test_curated_long_table,
    test_curated_finds_drivers_and_response,
    test_safe_name,
]


def main() -> int:
    failed = 0
    for fn in TESTS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
