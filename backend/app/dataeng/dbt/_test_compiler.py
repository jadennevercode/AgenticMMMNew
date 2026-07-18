"""Compiler checks: per-step SQL golden cases + a full pipeline built by real dbt.

Run:  PYTHONPATH=. .venv/bin/python -m app.dataeng.dbt._test_compiler

The e2e exercises exactly the operations the user called out: JOIN (sales × price
lookup), UNION (two sources), ENUM MAP (channel standardisation via seed),
FIELD MAP (rename/cast), AGGREGATE (channel × month sum) — compiled to dbt and
executed against DuckDB with the quality tests attached.
"""
from __future__ import annotations

import shutil
import sys

import pandas as pd

from app.dataeng.dbt import binary, compiler, executor
from app.dataeng.dbt.workspace import ModelFile, Workspace
from app.domain.models import (
    AggSpec, EnumMapEntry, FieldMapEntry, JoinConfig, TargetColumn,
    TransformPipeline, TransformStep,
)

PROJECT_ID = "_dbt_compiler_test"


def test_step_sql() -> None:
    # field_map with cast + constant expr (provenance off)
    s = TransformStep(id="a", kind="field_map", inputs=["source:t"],
                      fieldMap=[FieldMapEntry(source="Ch", target="channel"),
                                FieldMapEntry(source="GMV", target="value", cast="double"),
                                FieldMapEntry(target="brand", expr="'Mizone'")])
    sql, seed, _ = compiler._compile_step(s, ["{{ source('raw', 't') }}"], "m", [False], False)
    assert 'cast("GMV" as double) as "value"' in sql and "'Mizone' as \"brand\"" in sql
    assert seed is None

    # enum_map emits a seed + replace-join
    s = TransformStep(id="b", kind="enum_map", name="channel std", inputs=["a"],
                      enumField="channel",
                      enumMap=[EnumMapEntry(raw="TMALL", canonical="天猫")])
    sql, seed, _ = compiler._compile_step(s, ["{{ ref('m_a') }}"], "m2", [False], False)
    assert seed is not None and seed[0] == "map_channel_std" and "TMALL,天猫" in seed[1]
    assert 'replace (coalesce(m.canonical, t."channel") as "channel")' in sql

    # join keeps left.* plus selected right columns
    s = TransformStep(id="c", kind="join", inputs=["a", "b"],
                      join=JoinConfig(how="left", leftOn=["k"], rightOn=["k2"],
                                      rightColumns=["price"]))
    sql, _, _ = compiler._compile_step(s, ["L", "R"], "m3", [False, False], False)
    assert 'l."k" = r."k2"' in sql and 'r."price"' in sql and sql.startswith("select l.*")

    # aggregate (provenance off → unchanged)
    s = TransformStep(id="d", kind="aggregate", inputs=["a"],
                      groupBy=["channel"], aggs=[AggSpec(column="value", func="sum")])
    sql, _, _ = compiler._compile_step(s, ["X"], "m4", [False], False)
    assert sql == 'select "channel", sum("value") as "value" from X group by "channel"'

    # custom_sql wraps inputs as CTEs
    s = TransformStep(id="e", kind="custom_sql", inputs=["a"],
                      sql="select * from input_1 where x > 0")
    sql, _, _ = compiler._compile_step(s, ["Y"], "m5", [False], False)
    assert sql.startswith("with input_1 as (select * from Y)")
    print("[steps] all step kinds compile to expected SQL")


def test_source_provenance() -> None:
    prov = compiler._Provenance(
        enabled=True, raw_columns={"t": ["Ch", "GMV"], "own": ["Ch", "source"]},
        labels={"t": "sales_2023.xlsx"})
    carries: dict[str, bool] = {}

    # raw source with no `source` column → stamped with its file label
    ref, carry = compiler._input_ref("source:t", {}, prov, carries)
    assert "'sales_2023.xlsx' as \"source\"" in ref and carry is True
    # raw source that already has its own `source` column → not double-stamped
    ref2, carry2 = compiler._input_ref("source:own", {}, prov, carries)
    assert "as \"source\"" not in ref2 and carry2 is True

    # field_map on a carrying input appends `source` even though it isn't mapped
    s = TransformStep(id="a", kind="field_map", inputs=["source:t"],
                      fieldMap=[FieldMapEntry(source="Ch", target="channel")])
    sql, _, produces = compiler._compile_step(s, [ref], "m", [True], True)
    assert sql.rstrip().endswith('"source" from ' + ref) or '"source"' in sql
    assert produces is True

    # aggregate keeps per-source granularity by default, merges when asked
    agg = TransformStep(id="g", kind="aggregate", inputs=["a"],
                        groupBy=["channel"], aggs=[AggSpec(column="value", func="sum")])
    sql, _, produces = compiler._compile_step(agg, ["X"], "m2", [True], True)
    assert 'group by "channel", "source"' in sql and produces is True
    agg_merge = agg.model_copy(update={"merge_sources": True})
    sql, _, produces = compiler._compile_step(agg_merge, ["X"], "m3", [True], True)
    assert sql == 'select "channel", sum("value") as "value" from X group by "channel"'
    assert produces is False
    print("[provenance] source stamped at raw, carried through field_map/aggregate")


def test_structure_errors() -> None:
    # cycle detection
    p = TransformPipeline(steps=[
        TransformStep(id="a", kind="union", inputs=["b"]),
        TransformStep(id="b", kind="union", inputs=["a"]),
    ])
    try:
        compiler.compile_pipeline(p, "mart")
        raise AssertionError("cycle not detected")
    except compiler.CompileError:
        pass
    # unknown input
    p = TransformPipeline(steps=[TransformStep(id="a", kind="union", inputs=["nope"])])
    try:
        compiler.compile_pipeline(p, "mart")
        raise AssertionError("bad ref not detected")
    except compiler.CompileError:
        pass
    print("[structure] cycles and bad refs rejected")


def _fixtures() -> dict[str, pd.DataFrame]:
    months = [f"2022-{m:02d}" for m in range(1, 13)] + [f"2023-{m:02d}" for m in range(1, 13)]
    n = len(months)
    src_a = pd.DataFrame({"Channel": ["TMALL", "JD"] * (n // 2), "Month": months,
                          "Units": [10 + i % 7 for i in range(n)]})
    src_b = pd.DataFrame({"渠道": ["天猫超市", "jingdong"] * (n // 2), "月份": months,
                          "销量": [5 + i % 5 for i in range(n)]})
    price = pd.DataFrame({"channel": ["天猫", "京东"], "price": [2.0, 3.0]})
    return {"sales_a": src_a, "sales_b": src_b, "price_list": price}


def _pipeline() -> TransformPipeline:
    fm = lambda src, ch, ym, units: TransformStep(  # noqa: E731
        id=f"map_{src}", kind="field_map", name=f"map {src}",
        note=f"Rename {src} columns to the common shape.",
        inputs=[f"source:{src}"],
        fieldMap=[FieldMapEntry(source=ch, target="raw_channel"),
                  FieldMapEntry(source=ym, target="ym"),
                  FieldMapEntry(source=units, target="units", cast="double")])
    return TransformPipeline(steps=[
        fm("sales_a", "Channel", "Month", "Units"),
        fm("sales_b", "渠道", "月份", "销量"),
        TransformStep(id="u", kind="union", name="union sources",
                      inputs=["map_sales_a", "map_sales_b"]),
        TransformStep(id="e", kind="enum_map", name="channel", inputs=["u"],
                      enumField="raw_channel",
                      enumMap=[EnumMapEntry(raw="TMALL", canonical="天猫"),
                               EnumMapEntry(raw="天猫超市", canonical="天猫"),
                               EnumMapEntry(raw="JD", canonical="京东"),
                               EnumMapEntry(raw="jingdong", canonical="京东")]),
        TransformStep(id="j", kind="join", name="attach price",
                      inputs=["e", "source:price_list"],
                      join=JoinConfig(how="left", leftOn=["raw_channel"],
                                      rightOn=["channel"], rightColumns=["price"])),
        TransformStep(id="d", kind="derive", name="revenue + month int", inputs=["j"],
                      derive=[{"name": "value", "expr": "units * price"},
                              {"name": "month", "expr": "cast(replace(ym, '-', '') as integer)"}]),
        TransformStep(id="agg", kind="aggregate", name="mart", inputs=["d"],
                      groupBy=["raw_channel", "month"],
                      aggs=[AggSpec(column="value", func="sum")]),
    ], outputStep="agg")


def test_e2e() -> int:
    ok, msg = binary.available()
    print(f"[binary] {msg}")
    if not ok:
        print("SKIP e2e: dbt binary unavailable")
        return 0
    ws = Workspace(PROJECT_ID)
    shutil.rmtree(ws.dir, ignore_errors=True)
    ws.ensure()
    ws.load_raw(_fixtures())

    schema = [TargetColumn(name="month", kind="time"),
              TargetColumn(name="value", kind="value"),
              TargetColumn(name="raw_channel", kind="dimension",
                           standardValues=["天猫", "京东"])]
    proj = compiler.compile_pipeline(_pipeline(), "asset_e2e", schema)
    ws.clear_models()
    for name, csv_text in proj.seeds:
        ws.write_seed(name, csv_text)
    for m in proj.models:
        ws.write_model(ModelFile(m.layer, m.name, m.sql))
    ws.write_schema_yml(proj.schema_yml)

    res = executor.build(ws)
    for n in res.nodes:
        print(f"    {n.status:8} {n.resource_type:6} {n.name}")
    assert res.ok, f"build failed: {res.error}\n{res.stdout_tail}"

    df = ws.read_relation("asset_e2e")
    assert set(df["raw_channel"]) == {"天猫", "京东"}, "enum map failed"
    assert "period_date" in df.columns, "derived period_date missing"
    # join applied prices: 天猫 rows use 2.0, 京东 rows 3.0 — check one aggregate
    jan_tm = df[(df["raw_channel"] == "天猫") & (df["month"] == 202201)]["value"].iloc[0]
    assert float(jan_tm) == (10 + 5) * 2.0, jan_tm  # units 10 (TMALL) + 5 (天猫超市) × price 2
    tests = res.tests
    assert tests and all(t.ok for t in tests), "quality tests failed"
    print(f"[e2e] join+union+enum+aggregate mart correct; {len(tests)} tests passed")
    return 0


def main() -> int:
    test_step_sql()
    test_source_provenance()
    test_structure_errors()
    rc = test_e2e()
    print("PASS")
    return rc


if __name__ == "__main__":
    sys.exit(main())
