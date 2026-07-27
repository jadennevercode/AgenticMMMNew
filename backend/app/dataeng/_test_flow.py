"""End-to-end Data Engine flow over the real HTTP API.

Pins the behaviour the editor depends on, in the order a user hits it:

1. an uploaded workbook is a selectable raw source **immediately** — no build first;
2. the enum editor can read a field's real values through the pipeline;
3. AI suggestion reads the *renamed* column downstream of a field map (the raw-file
   scan returned nothing there and the editor read that as "clear the map");
4. an unconfirmed proposal does not reach the data.

Run: ``PYTHONPATH=. .venv/bin/python -m app.dataeng._test_flow``
"""
from __future__ import annotations

import io
import shutil

import pandas as pd
from fastapi.testclient import TestClient

from app.config import get_settings
from app.dataeng.dbt import pipeline_ai
from app.main import app
from app.domain.models import IndustryRef
from app.store.state import get_store

PROJECT_ID = "_test_flow"


def _xlsx() -> bytes:
    df = pd.DataFrame({
        "Ch": ["TMALL", "tmall ", "JD.com", "京东"] * 6,
        "V": [float(i + 1) for i in range(24)],
        "M": [y * 100 + m for y in (2022, 2023) for m in range(1, 13)],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Sheet1", index=False)
    return buf.getvalue()


def main() -> int:
    settings = get_settings()
    shutil.rmtree(settings.data_path / "projects" / PROJECT_ID, ignore_errors=True)
    store = get_store()
    meta = store.create(name="Flow test", brand="Acme",
                        industry=IndustryRef(l1="beauty", l2="skincare", l3="sunscreen"))
    pid = meta.id
    client = TestClient(app)
    try:
        # ── 1. upload → the file is a raw source with no build in between ──
        r = client.post(f"/api/projects/{pid}/files",
                        data={"category": "raw_data"},
                        files={"file": ("sales.xlsx", _xlsx(),
                                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200, r.text
        file_id = r.json()["id"]

        asset = client.post(f"/api/projects/{pid}/data-assets",
                            json={"name": "Sales", "sourceFileIds": [file_id]}).json()
        aid = asset["id"]

        status = client.get(f"/api/projects/{pid}/data-assets/{aid}/dbt/status").json()
        assert status["sources"] == ["sales"], status["sources"]
        assert status["sourceIssues"] == [], status["sourceIssues"]
        assert status["sourceTables"][0]["rowCount"] == 24, status["sourceTables"]
        print(f"[1] upload → sources={status['sources']} with no build")

        # ── 2. enum values read through the pipeline ──
        pipeline = {
            "steps": [
                {"id": "s1", "kind": "field_map", "name": "rename",
                 "inputs": ["source:sales"],
                 "fieldMap": [{"source": "Ch", "target": "raw_channel"},
                              {"source": "V", "target": "value"},
                              {"source": "M", "target": "month"}]},
                {"id": "s2", "kind": "enum_map", "name": "channels", "inputs": ["s1"],
                 "enumField": "raw_channel", "enumMap": []},
            ],
            "outputStep": "s2",
        }
        r = client.post(f"/api/projects/{pid}/data-assets/{aid}/pipeline/column-values",
                        json={"pipeline": pipeline, "stepId": "s2", "column": "raw_channel"}).json()
        assert r["ok"], r
        got = {v for v, _ in r["values"]}
        assert got == {"TMALL", "tmall ", "JD.com", "京东"}, got
        print(f"[2] column-values on the renamed column: {sorted(got)}")

        # ── 3. AI suggest sees the renamed column (heuristic path — no LLM needed) ──
        client.put(f"/api/projects/{pid}/target-schema", json=[
            {"name": "month", "kind": "time", "label": "", "definition": "",
             "required": True, "standardValues": []},
            {"name": "value", "kind": "value", "label": "", "definition": "",
             "required": True, "standardValues": []},
            {"name": "raw_channel", "kind": "dimension", "label": "", "definition": "",
             "required": False, "standardValues": ["TMALL", "京东"]},
        ])
        r = client.post(f"/api/projects/{pid}/data-assets/{aid}/pipeline/suggest-enum",
                        json={"pipeline": pipeline, "stepId": "s2",
                              "field": "raw_channel", "targetColumn": "raw_channel"}).json()
        assert r["ok"], r
        entries = r["entries"]
        # Every value reaching the step gets a row — the point of the editor is that
        # the work to do is visible, not discovered later from a failing build.
        assert {e["raw"] for e in entries} == {"TMALL", "tmall ", "JD.com", "京东"}, entries
        by_raw = {e["raw"]: e for e in entries}
        assert by_raw["TMALL"]["canonical"] == "TMALL", by_raw["TMALL"]
        # The confidence→status rule, asserted rather than any particular match: the
        # suggester runs an LLM when one is configured and a heuristic when not, so
        # which values it is sure of varies — that it only auto-accepts what it is
        # sure of must not.
        for e in entries:
            confident = bool(e["canonical"].strip()) and e["confidence"] >= 0.85
            assert e["status"] == ("accepted" if confident else "proposed"), e
        print(f"[3] suggest-enum: {sum(1 for e in entries if e['status'] == 'accepted')} accepted, "
              f"{sum(1 for e in entries if e['status'] == 'proposed')} awaiting confirmation")

        # ── 4. a proposal is inert until confirmed ──
        proposed_only = {**pipeline}
        proposed_only["steps"] = [
            pipeline["steps"][0],
            {**pipeline["steps"][1], "enumMap": [
                {"raw": "tmall ", "canonical": "TMALL", "confidence": 0.6,
                 "by": "ai", "status": "proposed"}]},
        ]
        r = client.post(f"/api/projects/{pid}/data-assets/{aid}/pipeline/preview",
                        json={"pipeline": proposed_only, "stepId": "s2"}).json()
        assert not r["ok"] and "awaiting confirmation" in r["error"], r
        confirmed = {**proposed_only}
        confirmed["steps"] = [
            proposed_only["steps"][0],
            {**proposed_only["steps"][1], "enumMap": [
                {"raw": "tmall ", "canonical": "TMALL", "confidence": 1.0,
                 "by": "human", "status": "accepted"}]},
        ]
        r = client.post(f"/api/projects/{pid}/data-assets/{aid}/pipeline/preview",
                        json={"pipeline": confirmed, "stepId": "s2"}).json()
        assert r["ok"], r["error"]
        col = r["columns"].index("raw_channel")
        assert "tmall " not in {row[col] for row in r["rows"]}
        print("[4] proposal blocked until confirmed, then applied")

        # ── 5. `source` is a system column: re-asserted even when a PUT omits it,
        #      and stamped onto every row without anyone configuring it ──
        schema = client.get(f"/api/projects/{pid}/target-schema").json()
        src_col = next((c for c in schema if c["name"] == "source"), None)
        assert src_col and src_col["system"] is True, schema
        r = client.post(f"/api/projects/{pid}/data-assets/{aid}/pipeline/preview",
                        json={"pipeline": confirmed, "stepId": "s2"}).json()
        assert "source" in r["columns"], r["columns"]
        si = r["columns"].index("source")
        assert {row[si] for row in r["rows"]} == {"sales.xlsx"}, r["rows"][:2]
        print("[5] source column restored by the engine and stamped 'sales.xlsx'")

        # ── 6. the field-map editor can see what there is to map ──
        r = client.post(f"/api/projects/{pid}/data-assets/{aid}/pipeline/input-columns",
                        json={"pipeline": pipeline, "stepId": "s1"}).json()
        assert r["ok"] and r["columns"] == ["Ch", "V", "M"], r
        print(f"[6] input-columns for the field map: {r['columns']}")

        # ── 7. the whole pipeline compiles to one exportable statement ──
        r = client.post(f"/api/projects/{pid}/data-assets/{aid}/pipeline/full-sql",
                        json={"pipeline": confirmed}).json()
        assert r["ok"], r["error"]
        assert "sales.xlsx" in r["sql"] and "with " in r["sql"].lower(), r["sql"][:300]
        # What is exported must be what runs: the same statement, through the sandbox.
        assert client.post(f"/api/projects/{pid}/data-assets/{aid}/pipeline/preview",
                           json={"pipeline": confirmed, "stepId": "s2"}).json()["ok"]
        print(f"[7] full-sql: {len(r['sql'].splitlines())} lines, header names the source file")

        # ── 8. an AI field map never overwrites a human row or double-books a target ──
        human = {**pipeline["steps"][0],
                 "fieldMap": [{"source": "M", "target": "month", "by": "human"}]}
        with_human = {**pipeline, "steps": [human, pipeline["steps"][1]]}
        r = client.post(f"/api/projects/{pid}/data-assets/{aid}/pipeline/suggest-field-map",
                        json={"pipeline": with_human, "stepId": "s1"}).json()
        assert r["ok"], r["error"]
        entries = r["entries"]
        assert {"source": "M", "target": "month"}.items() <= entries[0].items(), entries[0]
        assert entries[0]["by"] == "human", entries[0]
        targets = [e["target"] for e in entries if e["target"]]
        assert len(targets) == len(set(targets)), targets
        assert all(e["source"] in {"Ch", "V", "M"} for e in entries if e["source"]), entries
        print(f"[8] suggest-field-map kept the human row, {len(entries)} mapping(s), no duplicate targets")

        # ── 9. generated SQL is validated before it can reach the data ──
        sql_pipe = {"steps": [pipeline["steps"][0],
                              {"id": "s3", "kind": "custom_sql", "name": "reshape",
                               "inputs": ["s1"], "sql": "select * from input_1"}],
                    "outputStep": "s3"}
        original = pipeline_ai.suggest_sql

        def _drafts(sql: str) -> None:
            """Stand in for the model, so the *validation* is what is under test."""
            async def _stub(instruction, input_columns, target_columns, target_doc=None):
                return sql, ""
            pipeline_ai.suggest_sql = _stub

        try:
            for sql, should_pass in [
                ("drop table sales", False),                      # not read-only
                ("select * from no_such_cte", False),             # does not run
                ('select "raw_channel", "month" from input_1', True),
            ]:
                _drafts(sql)
                r = client.post(f"/api/projects/{pid}/data-assets/{aid}/pipeline/suggest-sql",
                                json={"pipeline": sql_pipe, "stepId": "s3",
                                      "instruction": "keep channel and month"}).json()
                assert r["ok"] is should_pass, (sql, r)
                # A rejected draft must hand back nothing at all — a step that stored
                # unvalidated model output would run it on the next preview.
                assert bool(r["sql"]) is should_pass, (sql, r)
        finally:
            pipeline_ai.suggest_sql = original
        print("[9] generated SQL: DDL and bad references rejected, valid SELECT accepted")
    finally:
        client.close()
        store.delete(pid)
        shutil.rmtree(settings.data_path / "projects" / pid, ignore_errors=True)
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
