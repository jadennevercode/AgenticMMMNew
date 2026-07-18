"""End-to-end check of the dbt engine foundation on messy multi-source data.

Run:  PYTHONPATH=. .venv/bin/python -m app.dataeng.dbt._test_engine

Proves the full vertical slice through the real app modules (not just raw dbt):
two differently-shaped raw uploads → pre-loaded as sources → union in staging →
enum-standardised against a seed → aggregated in a mart → data tests → read back.
"""
from __future__ import annotations

import shutil
import sys

import pandas as pd

from app.dataeng.dbt import binary, executor
from app.dataeng.dbt.workspace import ModelFile, Workspace

PROJECT_ID = "_dbt_engine_test"


def _fixtures() -> dict[str, pd.DataFrame]:
    # Two messy sources: different column names, channel spellings, and grain.
    src_a = pd.DataFrame({
        "Channel": ["TMALL", "Tmall", "JD"],
        "Month": ["2023-01", "2023-02", "2023-01"],
        "GMV": [100.0, 120.0, 80.0],
    })
    src_b = pd.DataFrame({
        "渠道": ["天猫超市", "jingdong"],
        "月份": ["2023-03", "2023-03"],
        "销售额": [50.0, 40.0],
    })
    return {"sales_a": src_a, "sales_b": src_b}


def _build_models(ws: Workspace) -> None:
    ws.write_seed("master_channel", (
        "raw_channel,channel_std\n"
        "TMALL,天猫\nTmall,天猫\n天猫超市,天猫\n"
        "JD,京东\njingdong,京东\n"
    ))
    ws.write_model(ModelFile("staging", "stg_sales_a",
        "select \"Channel\" as raw_channel, \"Month\" as ym, \"GMV\" as sales "
        "from {{ source('raw','sales_a') }}"))
    ws.write_model(ModelFile("staging", "stg_sales_b",
        "select \"渠道\" as raw_channel, \"月份\" as ym, \"销售额\" as sales "
        "from {{ source('raw','sales_b') }}"))
    ws.write_model(ModelFile("intermediate", "int_sales_union",
        "select * from {{ ref('stg_sales_a') }} "
        "union all select * from {{ ref('stg_sales_b') }}"))
    ws.write_model(ModelFile("marts", "asset_sales", (
        "{{ config(materialized='table') }}\n"
        "select coalesce(m.channel_std, u.raw_channel) as channel, u.ym, "
        "sum(u.sales) as sales\n"
        "from {{ ref('int_sales_union') }} u\n"
        "left join {{ ref('master_channel') }} m on u.raw_channel = m.raw_channel\n"
        "group by 1, 2")))
    ws.write_schema_yml(
        "version: 2\n"
        "models:\n"
        "  - name: asset_sales\n"
        "    columns:\n"
        "      - name: channel\n"
        "        tests:\n"
        "          - not_null\n"
        "          - accepted_values:\n"
        "              arguments:\n"
        "                values: ['天猫', '京东']\n"
        "      - name: sales\n"
        "        tests:\n"
        "          - not_null\n"
    )


def main() -> int:
    ok, msg = binary.available()
    print(f"[binary] {msg}")
    if not ok:
        print("SKIP: dbt binary unavailable")
        return 0

    ws = Workspace(PROJECT_ID)
    shutil.rmtree(ws.dir, ignore_errors=True)
    ws.ensure()

    loaded = ws.load_raw(_fixtures())
    print(f"[raw] loaded sources: {loaded}")
    _build_models(ws)

    res = executor.build(ws)
    print(f"[build] ok={res.ok} rc={res.returncode} cmd='{res.command}'")
    for n in res.nodes:
        extra = f" failures={n.failures}" if n.resource_type == "test" else ""
        print(f"    {n.status:8} {n.resource_type:6} {n.name}{extra}")
    if not res.ok:
        print("ERROR:", res.error)
        print(res.stdout_tail)
        return 1

    df = ws.read_relation("asset_sales").sort_values(["channel", "ym"])
    print("[mart] asset_sales:")
    print(df.to_string(index=False))

    # Assertions: 5 raw rows → 5 (channel, ym) groups (天猫 2023-01/02/03, 京东
    # 2023-01/03), channel fully standardised, 天猫 2023-03 = 天猫超市(50).
    by = {(r.channel, r.ym): r.sales for r in df.itertuples()}
    assert set(df["channel"]) == {"天猫", "京东"}, f"channels not standardised: {set(df['channel'])}"
    assert float(by[("天猫", "2023-01")]) == 100.0, by
    assert float(by[("天猫", "2023-03")]) == 50.0, by
    assert float(by[("京东", "2023-03")]) == 40.0, by
    assert len(df) == 5, f"expected 5 grouped rows, got {len(df)}"
    tests = res.tests
    assert tests and all(t.ok for t in tests), "data tests did not all pass"
    print(f"[tests] {len(tests)} passed")
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
