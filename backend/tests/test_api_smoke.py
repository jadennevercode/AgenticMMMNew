"""Smoke tests for the backend (no live LLM calls).

Covers: blueprint integrity, state initialization, DAG control flow with stubbed
handlers, and the JSON repair used for the reasoning-model output. Run:
    .venv/bin/python -m pytest tests/ -q
(pytest is optional; the asserts also run under plain python via __main__.)
"""
from __future__ import annotations

import asyncio

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
    (S1: background/reference/minutes; S2: the data gate 2.0a)."""
    csv = b"field,value\nObjective,Quantify ROI\nTime,Month\n"
    for cat in ("project_background", "industry_reference", "interview_minutes", "data"):
        get_files().add(project_id, cat, f"{cat}.csv", csv, content_type="text/csv")


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
    pid = "smoke-dag-complete"
    get_files().purge(pid)
    st = initial_state(_test_meta(pid))
    eng = _stub_engine()
    try:
        _seed_s1_uploads(pid)
        status = asyncio.run(run_until_blocked(eng, st, autopilot=True, max_steps=500))
        assert status["complete"], status
        assert status["tasks_done"] == len(bp.TASKS)
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
    """A slot-bound L3 workbook validates the 2.0a manifest gate and makes
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
    """With a factor tree but no slot-bound data, the 2.0a manifest gate stays shut."""
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


def test_validation_verdict_rollup() -> None:
    """2.12 final verdict = weakest of the four 0/0.5/1 dimensions (1→accept,
    0→unusable, 0.5→human)."""
    from app.agents.data_rules import final_verdict

    assert final_verdict(1, 1, 1, 1) == (1.0, "pass")
    assert final_verdict(1, 0.5, 1, 1) == (0.5, "borderline")     # one 0.5 → human
    assert final_verdict(1, 0.5, 0, 1) == (0.0, "unusable")       # any 0 → unusable
    assert final_verdict(0, 0, 0, 0) == (0.0, "unusable")


def test_validation_chain_shape() -> None:
    """2.1 Validation is standard(loaded) → AI score → human review: 2.12 has no
    gate, the verdict gate is d-2.13, and 2.21 waits on the human review."""
    assert bp.TASK_MAP["2.11"]["produces"] == ["a-validation-standard"]
    assert "decision" not in bp.TASK_MAP["2.12"] and bp.TASK_MAP["2.12"]["klass"] == "A"
    assert bp.TASK_MAP["2.13"]["decision"]["id"] == "d-2.13"
    assert bp.TASK_MAP["2.21"]["depends_on"] == ["2.13"]


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


if __name__ == "__main__":
    test_blueprint_integrity()
    test_initial_state()
    test_industry_taxonomy()
    test_json_repair()
    test_dag_runs_with_stub_handlers()
    test_s1_blocks_without_uploads()
    test_project_data_binding()
    test_data_gate_blocks_without_slot_coverage()
    test_validation_verdict_rollup()
    test_validation_chain_shape()
    test_rework_resets_downstream()
    test_model_service_config()
    print("all smoke tests passed")
