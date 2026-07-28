"""Sandbox preview: agreement with the dbt build, prefix scoping, and clustering.

Run: PYTHONPATH=. .venv/bin/python -m app.dataeng._test_preview

The load-bearing claim is the first test: the preview the editor shows must be the
same data ``dbt build`` would publish. It is checked by compiling the *same*
pipeline both ways and comparing the results row for row (the dbt half is skipped
when the binary is unavailable).
"""
from __future__ import annotations

import shutil
import sys

import pandas as pd

from app.dataeng import cluster, duck
from app.dataeng.dbt import binary, compiler, executor
from app.dataeng.dbt._test_compiler import _fixtures, _pipeline
from app.dataeng.dbt.workspace import ModelFile, Workspace
from app.domain.models import TargetColumn

PROJECT_ID = "__preview_test__"
SCHEMA = [TargetColumn(name="month", kind="time"),
          TargetColumn(name="value", kind="value"),
          TargetColumn(name="raw_channel", kind="dimension",
                       standardValues=["天猫", "京东"])]


def _preview(step_id: str = "", **kw) -> duck.PreviewResult:
    sql = compiler.compile_preview_sql(_pipeline(), step_id, target_schema=SCHEMA, **kw)
    return duck.run_preview(sql, _fixtures(), limit=500)


def test_preview_runs() -> None:
    res = _preview()
    assert res.ok, res.error
    # each month carries one channel per source, so the mart is one row per month
    assert res.row_count == 24, res.row_count
    assert set(res.columns) >= {"raw_channel", "month", "value", "period_date"}
    channels = {row[res.columns.index("raw_channel")] for row in res.rows}
    assert channels == {"天猫", "京东"}, channels        # inlined enum map applied
    print(f"[preview] output step: {res.row_count} rows, cols={res.columns}")


def test_prefix_scoping() -> None:
    """Previewing a mid-pipeline step compiles only that step's ancestors."""
    sql = compiler.compile_preview_sql(_pipeline(), "u", target_schema=SCHEMA)
    assert "attach_price" not in sql and "mart" not in sql, sql
    res = duck.run_preview(sql, _fixtures(), limit=500)
    assert res.ok, res.error
    assert res.row_count == 48 and "price" not in res.columns   # pre-join, pre-agg
    # the enum step has not run yet, so raw spellings are still present
    raw = {row[res.columns.index("raw_channel")] for row in res.rows}
    assert "TMALL" in raw and "天猫" not in raw, raw
    print(f"[preview] prefix at 'u': {res.row_count} raw rows, {len(raw)} spellings")


def test_column_stats() -> None:
    res = _preview()
    stats = {s.name: s for s in res.stats}
    channel, value = stats["raw_channel"], stats["value"]
    assert channel.distinct == 2 and channel.null_pct == 0.0
    assert set(dict(channel.top)) == {"天猫", "京东"}, channel.top
    assert sum(n for _, n in channel.top) == res.row_count
    assert value.histogram and sum(value.histogram) == res.row_count
    assert float(value.min) <= float(value.max)
    print(f"[stats] raw_channel top={channel.top} · value hist={value.histogram}")


def test_matches_dbt_build() -> int:
    """The preview and the dbt mart must agree — same steps, same data."""
    ok, msg = binary.available()
    if not ok:
        print(f"SKIP dbt agreement: {msg}")
        return 0
    ws = Workspace(PROJECT_ID)
    shutil.rmtree(ws.dir, ignore_errors=True)
    ws.ensure()
    ws.load_raw(_fixtures())
    proj = compiler.compile_pipeline(_pipeline(), "asset_preview", SCHEMA)
    ws.clear_models()
    ws.clear_seeds()
    for name, csv_text in proj.seeds:
        ws.write_seed(name, csv_text)
    for m in proj.models:
        ws.write_model(ModelFile(m.layer, m.name, m.sql))
    ws.write_schema_yml(proj.schema_yml)
    res = executor.build(ws)
    assert res.ok, f"build failed: {res.error}"

    built = ws.read_relation("asset_preview")
    prev = _preview()
    assert prev.ok, prev.error
    assert len(built) == prev.row_count, (len(built), prev.row_count)

    def key(df_like: list[tuple[str, str, float]]) -> dict:
        return {(c, m): round(float(v), 6) for c, m, v in df_like}

    from_dbt = key([(r["raw_channel"], str(r["month"]), r["value"])
                    for _, r in built.iterrows()])
    ci, mi, vi = (prev.columns.index(c) for c in ("raw_channel", "month", "value"))
    from_preview = key([(r[ci], r[mi], float(r[vi])) for r in prev.rows])
    assert from_dbt == from_preview, "preview diverged from the dbt build"
    shutil.rmtree(ws.dir, ignore_errors=True)
    print(f"[agreement] preview == dbt mart on all {len(from_dbt)} cells")
    return 0


def test_clustering() -> None:
    values = [("TMALL", 10), ("T-Mall", 4), ("tmall ", 2), ("JD", 7),
              ("jd.com", 3), ("京东 自营", 5), ("京东自营", 2), ("Walmart", 9)]
    groups = cluster.cluster_values(values)
    by_suggestion = {g.suggestion: {v for v, _ in g.values} for g in groups}
    assert "TMALL" in by_suggestion and by_suggestion["TMALL"] == {"TMALL", "T-Mall", "tmall "}
    assert any(set(v) == {"京东 自营", "京东自营"} for v in
               ({v for v, _ in g.values} for g in groups))
    assert all("Walmart" not in vs for vs in by_suggestion.values())  # collides with nothing
    assert groups[0].rows >= groups[-1].rows                          # ordered by impact
    print(f"[cluster] {len(groups)} groups; suggestions={list(by_suggestion)}")


def test_literals_not_scanned() -> None:
    """A banned keyword inside a quoted literal or identifier is inert data."""
    df = pd.DataFrame({"copy": [1, 2]})
    res = duck.run_preview("select 'sales copy.xlsx' as src, \"copy\" from t", {"t": df})
    assert res.ok, res.error
    assert res.rows[0][0] == "sales copy.xlsx"
    assert not duck.run_preview("select 1; select 2", {}).ok      # still one statement only
    assert not duck.run_preview("select * from read_csv('/etc/passwd')", {}).ok
    print("[safety] literals pass, real statements still blocked")


def main() -> int:
    test_preview_runs()
    test_prefix_scoping()
    test_column_stats()
    test_clustering()
    test_literals_not_scanned()
    rc = test_matches_dbt_build()
    print("PASS")
    return rc


if __name__ == "__main__":
    sys.exit(main())
