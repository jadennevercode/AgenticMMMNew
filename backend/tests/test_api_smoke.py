"""Smoke tests for the backend (no live LLM calls).

Covers: blueprint integrity, state initialization, DAG control flow with stubbed
handlers, and the JSON repair used for the reasoning-model output. Run:
    .venv/bin/python -m pytest tests/ -q
(pytest is optional; the asserts also run under plain python via __main__.)
"""
from __future__ import annotations

import asyncio

from app.agents.registry import build_engine
from app.domain import blueprint as bp
from app.domain import industries as ind
from app.domain.models import IndustryRef, ProjectMeta
from app.llm.volcano import _extract_json, _repair_truncated
from app.orchestrator.engine import Engine
from app.orchestrator.runner import run_until_blocked
from app.store.files import get_files
from app.store.state import danone_meta, initial_state


def _test_meta(project_id: str) -> ProjectMeta:
    return ProjectMeta(
        id=project_id, name="Smoke", brand="B",
        industry=IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional"),
        kpi="Vol", createdAt="2026-01-01T00:00:00+00:00",
    )


def _seed_s1_uploads(project_id: str) -> None:
    """Put a parseable stub file in each upload-gate category so the gates open
    (S1: background/reference/minutes; S2: the data gate 2.1)."""
    csv = b"field,value\nObjective,Quantify ROI\nTime,Month\n"
    for cat in ("project_background", "industry_reference", "interview_minutes", "data"):
        get_files().add(project_id, cat, f"{cat}.csv", csv, content_type="text/csv")


def _seed_s2_intake(st) -> None:  # noqa: ANN001
    """Make the 2.1 data gate satisfiable: one active factor row, one published
    indicator covering it, and the reference table standing in for project data.

    The gate is deliberately strict now — an unmapped factor tree, an unbuildable
    manifest and a table with no modelable taxonomy all block. A control-flow test
    therefore has to look like a project that really did its data intake.
    """
    from app.config import get_settings
    from app.domain.models import FactorRow, FactorTree, IndicatorCoverage

    st.factor_tree = FactorTree(rows=[FactorRow(
        id="fr-1", l1="MARKETING FACTOR", l2="Media", l3="TV", l4="TV",
        indicator="TV spend", status="baseline",
    )])
    st.indicator_coverage = [IndicatorCoverage(
        id="cov-1", treeRowId="fr-1", metric="TV spend", metricType="spending",
        l1="MARKETING FACTOR", l2="Media", l3="TV", l4="TV",
        assetId="a-1", assetName="Media asset", boundBy="auto",
    )]
    # No published parquet in a stub run — let the reference table serve as the
    # project's data so the gate's modeling-readiness check has something real.
    get_settings().allow_reference_fallback = True


def test_blueprint_integrity() -> None:
    ids = {t["id"] for t in bp.TASKS}
    assert len(ids) == len(bp.TASKS), "duplicate task ids"
    for t in bp.TASKS:
        for dep in t.get("depends_on", []):
            assert dep in ids, f"{t['id']} depends on unknown {dep}"
        for aid in t.get("produces", []):
            assert aid in bp.ARTIFACT_MAP, f"{t['id']} produces unknown {aid}"


def test_initial_state() -> None:
    st = initial_state(danone_meta())
    assert len(st.tasks) == len(bp.TASKS)
    assert all(r.status == "pending" for r in st.tasks.values())
    assert st.tasks["1.0a"].status == "pending"
    assert st.meta is not None and st.meta.brand == "脉动 Mizone"


def test_industry_taxonomy() -> None:
    assert ind.validate_industry("food-bev", "beverage", "sports-functional")
    assert not ind.validate_industry("food-bev", "beverage", "nope")
    assert ind.industry_labels("food-bev", "beverage", "sports-functional") == (
        "食品饮料", "饮料", "功能/运动饮料",
    )


def test_json_repair() -> None:
    truncated = '{"sheets":[{"name":"a","columns":["x"],"rows":[["1"],["incomp'
    obj = _extract_json(truncated)
    assert obj["sheets"][0]["name"] == "a"
    assert _repair_truncated('{"a":[1,2').endswith("]}")


def _stub_engine() -> Engine:
    eng = Engine()

    async def noop(engine: Engine, state, task) -> None:  # noqa: ANN001
        for aid in task.get("produces", []):
            engine.produce(state, aid, body={"sheets": []}, agent=task["agent"])

    for t in bp.TASKS:
        eng.register(t["id"], noop)
    return eng


def test_dag_runs_with_stub_handlers() -> None:
    """The whole DAG completes in autopilot once the S1 upload gates have files."""
    from app.config import get_settings

    pid = "smoke-dag-complete"
    get_files().purge(pid)
    st = initial_state(_test_meta(pid))
    eng = _stub_engine()
    # `_seed_s2_intake` flips the process-wide (lru_cache'd) settings singleton
    # to let the reference table stand in for this stub's data; save/restore so
    # it doesn't leak the no-fallback rule off for every test that runs after
    # this one in the same process (I4).
    allowed = get_settings().allow_reference_fallback
    try:
        _seed_s1_uploads(pid)
        _seed_s2_intake(st)
        status = asyncio.run(run_until_blocked(eng, st, autopilot=True, max_steps=500))
        assert status["complete"], status
        assert status["tasks_done"] == len(bp.TASKS)
    finally:
        get_files().purge(pid)
        get_settings().allow_reference_fallback = allowed


def test_s2_blocks_without_data_intake() -> None:
    """2.1 blocks when the factor map is unresolved — even with files uploaded.

    Regression for the three escape hatches that used to open the gate on a
    project with no data at all: an empty manifest (`total == 0`), an unreadable
    manifest, and merely *having* published indicators.
    """
    pid = "smoke-s2-gate"
    get_files().purge(pid)
    st = initial_state(_test_meta(pid))
    eng = _stub_engine()
    try:
        _seed_s1_uploads(pid)  # S1 satisfied, S2 intake deliberately not seeded
        status = asyncio.run(run_until_blocked(eng, st, autopilot=True, max_steps=500))
        assert not status["complete"], status
        assert status["awaiting_human"] == ["2.1"], status

        from app.agents.intake_status import intake_status
        s = intake_status(st, bp.TASK_MAP["2.1"]["assignment"])
        assert not s.ready and s.path == "none"
        assert s.blockers, "a blocked gate must say why"
    finally:
        get_files().purge(pid)


def test_s1_blocks_without_uploads() -> None:
    """With no uploads, autopilot blocks at the first S1 upload gate (no fallback)."""
    pid = "smoke-dag-blocked"
    get_files().purge(pid)
    st = initial_state(_test_meta(pid))
    eng = _stub_engine()
    try:
        status = asyncio.run(run_until_blocked(eng, st, autopilot=True, max_steps=500))
        assert not status["complete"], status
        assert status["tasks_done"] == 0, status
        assert status["awaiting_human"] == ["1.0a"], status
        # Submitting the gate with no files is refused, leaving it open.
        ok = asyncio.run(eng.submit_assignment(st, "in-1.0a"))
        assert ok is False
    finally:
        get_files().purge(pid)


def test_project_data_binding() -> None:
    """A slot-bound L3 workbook validates the 2.1 manifest gate and makes
    `model_df` switch from the reference to the project's own long table."""
    import io

    import openpyxl

    from app.agents.data_request import build_manifest, manifest_satisfied
    from app.agents.dataset_cache import invalidate_project, model_df, uses_project_data
    from app.domain.models import FactorRow, FactorTree

    pid = "smoke-binding"
    get_files().purge(pid)
    st = initial_state(_test_meta(pid))
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="fr-1", l1="生意", l2="营销", l3="店内促销", l4="单品折扣", indicator="折扣率", status="baseline"),
        FactorRow(id="fr-2", l1="生意", l2="营销", l3="店内促销", l4="陈列", indicator="陈列占比", status="baseline"),
    ])
    # An L3 workbook in the data-request EXPORT format: one sheet per L4,
    # header = Time (Month) · Product · Channel · Platform & Region · indicators.
    wb = openpyxl.Workbook(); wb.remove(wb.active)
    for l4, ind in [("单品折扣", "折扣率"), ("陈列", "陈列占比")]:
        ws = wb.create_sheet(l4)
        ws.append(["Time (Month)", "Product", "Channel", "Platform & Region", ind])
        for mo in range(1, 25):
            ws.append([f"{2023 + mo // 13}-{(mo % 12) + 1:02d}", "Mizone", "MT", "华东", 0.1 * mo])
    buf = io.BytesIO(); wb.save(buf)
    try:
        get_files().add(pid, "data", "店内促销.xlsx", buf.getvalue(), content_type="xlsx", slot="店内促销")
        invalidate_project(pid)
        m = build_manifest(st)
        assert m.total == 1 and m.validated == 1, (m.total, m.validated)
        assert manifest_satisfied(st) is True
        df = model_df(st)
        assert uses_project_data(st) is True
        assert {"折扣率", "陈列占比"} <= set(df["metric"].dropna().astype(str)), "metrics not bound"
    finally:
        get_files().purge(pid)
        invalidate_project(pid)


def test_data_gate_blocks_without_slot_coverage() -> None:
    """With a factor tree but no slot-bound data, the 2.1 manifest gate stays shut."""
    from app.agents.data_request import manifest_satisfied
    from app.domain.models import FactorRow, FactorTree

    pid = "smoke-gate"
    get_files().purge(pid)
    st = initial_state(_test_meta(pid))
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="fr-1", l1="生意", l2="营销", l3="店内促销", l4="单品折扣", indicator="折扣率", status="baseline"),
    ])
    try:
        assert manifest_satisfied(st) is False  # L3 slot exists but unfilled
    finally:
        get_files().purge(pid)


def test_factor_map_gate() -> None:
    """2.1 Data Processing gate: blocks while any active factor row is unresolved,
    clears (on the mapping path) once every row is mapped (published indicator) or
    ignored, and re-blocks when an ignore is undone.

    Asserts `mapping_complete` plus `_mapping_status` — the mapping path's own
    verdict — rather than the composite `intake_status(...)`/`data_intake_ready`.
    The composite folds in a further modeling-readiness check (`_data_blockers`:
    is there an actual modelable table?), and resets its `path` to "none" whenever
    that later check fails — which this stub state always does (no bound/published
    data, only factor-tree + coverage metadata) even once the mapping itself is
    genuinely complete, so asserting the composite (or its `path`) would falsely
    fail here regardless of whether the mapping layer works.
    """
    from app.agents.intake_status import _mapping_status
    from app.dataeng.mapping import mapping_complete, resolve_factor_map
    from app.domain.models import FactorRow, FactorTree, IndicatorCoverage

    st = initial_state(_test_meta("smoke-factor-map"))
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="fr-1", l1="生意", l2="营销", l3="店内促销", l4="折扣", indicator="折扣率", status="baseline"),
        FactorRow(id="fr-2", l1="生意", l2="媒体", l3="社媒", l4="曝光", indicator="曝光量", status="baseline"),
    ])
    # unresolved → blocked
    assert mapping_complete(st) is False
    assert _mapping_status(st)[0] is False
    # map fr-1 via an exact tree_row_id, ignore fr-2 → mapping resolved
    st.indicator_coverage = [IndicatorCoverage(
        id="c1", treeRowId="fr-1", metric="折扣率", l1="生意", l2="营销", l3="店内促销",
        l4="折扣", assetId="a1", assetName="Promo", boundBy="auto")]
    st.factor_map_ignores = {"fr-2": "no reliable source"}
    fmap = resolve_factor_map(st)
    assert (fmap.mapped, fmap.ignored, fmap.pending) == (1, 1, 0)
    assert mapping_complete(st) is True
    assert _mapping_status(st)[0] is True
    # undo the ignore → pending again, gate re-blocks
    st.factor_map_ignores = {}
    assert mapping_complete(st) is False
    assert _mapping_status(st)[0] is False


def test_validation_verdict_rollup() -> None:
    """2.2 final verdict = weakest of the four 0/0.5/1 dimensions (1→accept,
    0→unusable, 0.5→human)."""
    from app.agents.data_rules import final_verdict

    assert final_verdict(1, 1, 1, 1) == (1.0, "pass")
    assert final_verdict(1, 0.5, 1, 1) == (0.5, "borderline")     # one 0.5 → human
    assert final_verdict(1, 0.5, 0, 1) == (0.0, "unusable")       # any 0 → unusable
    assert final_verdict(0, 0, 0, 0) == (0.0, "unusable")


def test_validation_chain_shape() -> None:
    """S2 is a six-artifact filter chain: 2.1 Processing (gate) → 2.2 AI quality
    score → 2.2d human review → 2.3 Business Validation → 2.4 Statistical Score
    → 2.5 OLS test → 2.6 Master Data, which Modeling (3.1) consumes."""
    assert bp.TASK_MAP["2.1"]["produces"] == ["a-data-processing"]
    assert bp.TASK_MAP["2.1"]["assignment"]["requiresManifest"] is True
    assert "decision" not in bp.TASK_MAP["2.2"] and bp.TASK_MAP["2.2"]["klass"] == "A"
    assert bp.TASK_MAP["2.2d"]["decision"]["id"] == "d-2.2"
    assert bp.TASK_MAP["2.3"]["depends_on"] == ["2.2d"]
    assert bp.TASK_MAP["2.3"]["produces"] == ["a-business-validation"]
    assert bp.TASK_MAP["2.4"]["produces"] == ["a-stat-tests"]
    assert bp.TASK_MAP["2.5"]["produces"] == ["a-ols-test"]
    # 2.5 renders the OLS factor-tree view, not a plain sheet.
    assert bp.ARTIFACT_MAP["a-ols-test"]["format"] == "olsTree"
    assert bp.TASK_MAP["2.6"]["produces"] == ["a-master-data"]
    assert bp.TASK_MAP["2.6"]["depends_on"] == ["2.5"]
    # 2.6 is a sliceable feature table, and locking it is a human act (2.6d).
    assert bp.ARTIFACT_MAP["a-master-data"]["format"] == "masterData"
    assert bp.TASK_MAP["2.6d"]["decision"]["id"] == "d-2.6"
    assert bp.TASK_MAP["2.6d"]["produces"] == []
    assert bp.TASK_MAP["3.1"]["depends_on"] == ["2.6d"]
    assert {s["id"] for s in bp.STAGES} == {"s1", "s2", "s4", "s5"}


def test_ols_search_single_task() -> None:
    """2.5 is now a single automated indicator search (寻优), not a five-step manual
    config: the AI searches each L4's candidate indicators over repeated fits and
    the human reviews the chosen selection at the one d-2.5 gate. The old
    2.5y/2.5x/2.5p/2.5r sub-tasks are gone."""
    t = bp.TASK_MAP["2.5"]
    assert t["klass"] == "M", "2.5 runs the search deterministically"
    assert t["produces"] == ["a-ols-test"]
    assert t["depends_on"] == ["2.4d"]
    assert t["decision"]["id"] == "d-2.5"          # the single review gate lives on 2.5
    assert any(o.get("recommended") for o in t["decision"]["options"])
    # The former sub-steps must be fully retired from the blueprint.
    for gone in ("2.5y", "2.5x", "2.5p", "2.5r"):
        assert gone not in bp.TASK_MAP, gone
    for gone in ("d-2.5y", "d-2.5x", "d-2.5p"):
        assert all(t.get("decision", {}).get("id") != gone for t in bp.TASKS), gone


def test_ols_gate_drop_feeds_master_data_exclusion() -> None:
    """The d-2.5 'drop' resolution is what 2.6 reads to physically exclude the
    OLS-flagged indicators (ols_drop_pairs)."""
    from app.agents.ols_review import ols_drop_pairs

    st = initial_state(danone_meta())
    st.analysis["ols_flagged"] = [{"l4": "冰柜", "indicator": "费用", "reason": "ROI out"}]
    assert ols_drop_pairs(st) == {("冰柜", "费用")}
    eng = build_engine()
    st.tasks["2.5"].status = "awaiting_human"
    st.decisions["d-2.5"].status = "open"
    eng.resolve_decision(st, "d-2.5", "drop", "drop flagged")
    assert (st.decisions["d-2.5"].resolution or {}).get("optionId") == "drop"


def test_range_gate_drop_survives_a_later_refit() -> None:
    """Dropping at d-2.5 must stick even though the next fit stops flagging.

    Once the flagged indicators are excluded they produce no records, so the
    re-fit reports nothing out of range. Re-deriving the verdict from that empty
    list would walk them straight back into the model, so the gate freezes what
    it dropped onto its own resolution.
    """
    from app.agents.ledger import range_drop_pairs

    st = initial_state(danone_meta())
    st.analysis["ols_flagged"] = [{"l4": "冰柜", "indicator": "费用", "reason": "ROI out"}]
    eng = build_engine()
    st.tasks["2.5"].status = "awaiting_human"
    st.decisions["d-2.5"].status = "open"
    eng.resolve_decision(st, "d-2.5", "drop", "drop flagged")

    assert (st.decisions["d-2.5"].resolution or {}).get("droppedPairs") == [["冰柜", "费用"]]
    # A re-fit clears the live flags; the frozen verdict must not move.
    st.analysis["ols_flagged"] = []
    assert range_drop_pairs(st) == {("冰柜", "费用")}


def test_rework_resets_downstream() -> None:
    st = initial_state(danone_meta())
    eng = Engine()
    # complete 1.0a and open 1.0's decision, then send back
    st.tasks["1.0a"].status = "done"
    st.tasks["1.0"].status = "awaiting_human"
    st.decisions["d-1.0"].status = "open"
    eng.resolve_decision(st, "d-1.0", "rework", "redo")
    # rework resets the task; it is re-promoted to ready since its dep (1.0a) is done
    assert st.tasks["1.0"].status in ("pending", "ready")
    assert st.tasks["1.0"].progress == 0.0
    assert st.decisions["d-1.0"].status == "idle"


def test_model_service_config() -> None:
    """Global model-service config round-trips and gates get_llm() until filled."""
    import app.store.model_service as ms
    from app.domain.models import GlobalModelConfig, ServiceCreds
    from app.llm.volcano import LLMError, get_llm

    path = ms._config_path()
    backup = path.read_text("utf-8") if path.exists() else None
    try:
        # Unconfigured → get_llm() raises (surfaced by the run-gate).
        if path.exists():
            path.unlink()
        ms._CACHE = None
        try:
            get_llm()
            raise AssertionError("get_llm() should raise when unconfigured")
        except LLMError:
            pass

        # Configured → the config round-trips and get_llm() builds a client.
        cfg = GlobalModelConfig(llm=ServiceCreds(api_key="k", base_url="https://x/v1", model="m"))
        ms.save_model_service(cfg)
        assert ms.get_model_service().llm.model == "m"
        assert get_llm()._model == "m"
    finally:
        if backup is not None:
            path.write_text(backup, "utf-8")
        elif path.exists():
            path.unlink()
        ms._CACHE = None


def test_tool_registry_and_trace() -> None:
    """The 8 tools are registered, and a traced call lands on the project state."""
    from app.domain import blueprint as bp
    from app.tools import get as get_tool, list_specs
    from app.tools.tracing import tool_run

    specs = list_specs()
    assert len(specs) == 8, len(specs)
    assert {s.category for s in specs} == {"quality", "statistical", "model"}
    # every tool names a real task as its caller
    task_ids = {t["id"] for t in bp.TASKS}
    for s in specs:
        assert s.used_by and set(s.used_by) <= task_ids, (s.id, s.used_by)
        assert get_tool(s.id).run is not None

    st = initial_state(_test_meta("smoke-tools"))
    with tool_run(None, st, "2.4", "stat.cv", "3 series") as h:
        h.result("CV 0.10-0.90")
    rec = st.tool_invocations[0]
    assert rec.status == "ok" and rec.task_id == "2.4" and rec.tool_id == "stat.cv"
    assert rec.duration_ms is not None and rec.result_summary == "CV 0.10-0.90"
    # /state must carry the trace to the frontend (snake_case, un-aliased)
    assert st.model_dump(by_alias=True)["tool_invocations"], "trace missing from /state"


if __name__ == "__main__":
    # Reflective: iterate every `test_*` defined in this module so a newly added
    # test can never again go undefined here (I3 — 4 of 18 tests were silently
    # never run this way).
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print(f"  ok  {_name}")
    print("all smoke tests passed")
