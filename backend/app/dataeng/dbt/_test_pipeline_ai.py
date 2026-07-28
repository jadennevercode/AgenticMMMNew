"""Pipeline-AI checks: draft/repair loop with a stub drafter + heuristic suggesters.

Run:  PYTHONPATH=. .venv/bin/python -m app.dataeng.dbt._test_pipeline_ai
"""
from __future__ import annotations

import asyncio
import shutil
import sys

import pandas as pd

from app.dataeng.dbt import binary, pipeline_ai
from app.dataeng.dbt.pipeline_ai import DraftContext
from app.dataeng.dbt.workspace import Workspace
from app.domain.models import (
    FieldMapEntry, TargetColumn, TransformPipeline, TransformStep,
)

PROJECT_ID = "_dbt_pipeai_test"


def test_suggesters() -> None:
    entries = pipeline_ai.suggest_enum_map_heuristic(
        ["TMALL", "tmall ", "JD.com", "拼多多"], ["TMALL", "JD"])
    by_raw = {e.raw: e for e in entries}
    assert by_raw["TMALL"].canonical == "TMALL" and by_raw["TMALL"].confidence >= 0.9
    assert by_raw["tmall "].canonical == "TMALL"          # normalised match
    assert by_raw["JD.com"].canonical == "JD"             # containment match
    assert by_raw["拼多多"].canonical == "" and by_raw["拼多多"].confidence == 0.0  # unmapped
    fm = pipeline_ai.suggest_field_map_heuristic(["Brand ", "GMV", "mystery"],
                                                 ["brand", "value"])
    assert {(m.source, m.target) for m in fm} == {("Brand ", "brand")}
    print("[suggesters] enum + field heuristics behave")


def test_parse_rejects_garbage() -> None:
    for bad in ({}, {"steps": []}, {"steps": [{"id": "a"}]}, "not json at all {"):
        try:
            pipeline_ai.parse_pipeline(bad)
            raise AssertionError(f"accepted invalid pipeline {bad!r}")
        except (ValueError, Exception):
            pass
    print("[parse] invalid pipeline JSON rejected")


def _good_pipe() -> TransformPipeline:
    return TransformPipeline(steps=[
        TransformStep(id="m", kind="field_map", name="map", inputs=["source:sales"],
                      fieldMap=[FieldMapEntry(source="Ch", target="channel"),
                                FieldMapEntry(source="V", target="value", cast="double"),
                                FieldMapEntry(source="M", target="month", cast="integer")]),
    ], outputStep="m")


def _bad_pipe() -> TransformPipeline:
    return TransformPipeline(steps=[
        TransformStep(id="m", kind="field_map", name="map", inputs=["source:sales"],
                      fieldMap=[FieldMapEntry(source="Nope", target="channel")]),
    ], outputStep="m")


def test_draft_repair_loop() -> int:
    ok, msg = binary.available()
    print(f"[binary] {msg}")
    if not ok:
        print("SKIP: dbt binary unavailable")
        return 0
    ws = Workspace(PROJECT_ID)
    shutil.rmtree(ws.dir, ignore_errors=True)
    ws.ensure()
    months = [y * 100 + m for y in (2022, 2023) for m in range(1, 13)]
    ws.load_raw({"sales": pd.DataFrame(
        {"Ch": ["A", "B"] * 12, "V": [float(i + 1) for i in range(24)], "M": months})})

    calls = {"n": 0}

    async def stub(ctx, error, previous):
        calls["n"] += 1
        if calls["n"] == 1:
            return _bad_pipe()
        assert error and previous is not None, "repair round missing context"
        return _good_pipe()

    schema = [TargetColumn(name="channel", kind="dimension"),
              TargetColumn(name="month", kind="time"),
              TargetColumn(name="value", kind="value")]
    ctx = DraftContext(raw_tables=ws.raw_tables_info(), profiles_text="(stub)",
                       target_columns=["channel", "month", "value"], target_doc={},
                       standard_values={}, mart_name="asset_pipe")
    res = asyncio.run(pipeline_ai.draft(ws, ctx, schema, drafter=stub))
    assert res.ok and res.rounds == 2 and calls["n"] == 2, (res.ok, res.rounds, res.error)
    assert res.pipeline is not None and res.pipeline.output_step == "m"
    df = ws.read_relation("asset_pipe")
    assert "period_date" in df.columns and len(df) == 24
    print(f"[draft] repair loop fixed the pipeline on round {res.rounds}")
    return 0


def main() -> int:
    test_suggesters()
    test_parse_rejects_garbage()
    rc = test_draft_repair_loop()
    print("PASS")
    return rc


if __name__ == "__main__":
    sys.exit(main())
