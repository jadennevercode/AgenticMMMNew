"""FastAPI app — the real Agentic MMM backend API consumed by the React frontend.

Multi-project: every project is an isolated state + run loop, addressed under
`/api/projects/{project_id}/...`. The project registry lives at `/api/projects`.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.agents.artifact_edit import (
    ArtifactEditError,
    apply_client_qa,
    apply_factor_tree,
    apply_profile,
    apply_proposal,
    apply_quality_scorecard,
    draft_edit,
)
from app.agents.common import agent_system, artifact_text
from app.agents.registry import build_engine
from app.domain import blueprint as bp
from app.domain import industries as ind
from app.domain.models import (
    ArtifactEditProposal,
    CleaningSpec,
    ClientQA,
    FactorTree,
    GlobalModelConfig,
    IndustryRef,
    KnowledgeTemplate,
    ProjectProfile,
    QualityScorecard,
)
from app.llm.volcano import get_llm
from app.orchestrator.runner import run_until_blocked
from app.store.files import get_files
from app.store.state import ProjectState, get_store, project_summary
from app.store.templates import get_templates

app = FastAPI(title="Agentic MMM Backend", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

_engine = build_engine()
# Per-project run guards: project_id -> {"running": bool, "last_status": dict | None}
_runs: dict[str, dict] = {}


def _run(project_id: str) -> dict:
    return _runs.setdefault(project_id, {"running": False, "last_status": None})


def _require_state(project_id: str) -> ProjectState:
    st = get_store().get(project_id)
    if st is None:
        raise HTTPException(404, "project not found")
    return st


# ── meta ─────────────────────────────────────────────────
@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "running": any(r["running"] for r in _runs.values())}


@app.get("/api/meta")
async def meta() -> dict:
    return {"stages": bp.STAGES, "agents": bp.AGENTS, "artifacts": bp.ARTIFACTS,
            "tasks": [{"id": t["id"], "name": t["name"], "agent": t["agent"], "stage": t["stage"],
                       "class": t["klass"], "dependsOn": t.get("depends_on", []),
                       "produces": t.get("produces", [])} for t in bp.TASKS]}


@app.get("/api/industries")
async def industries() -> dict:
    return {"tree": ind.INDUSTRY_TREE}


# ── knowledge templates (cross-project, editable) ────────
@app.get("/api/templates")
async def list_templates(kind: Optional[str] = None, industryL1: Optional[str] = None) -> list[dict]:
    items = get_templates().list(kind=kind, industry_l1=industryL1)  # type: ignore[arg-type]
    return [t.model_dump(by_alias=True) for t in items]


@app.get("/api/templates/{template_id}")
async def get_template(template_id: str) -> dict:
    tpl = get_templates().get(template_id)
    if tpl is None:
        raise HTTPException(404, "template not found")
    return tpl.model_dump(by_alias=True)


@app.post("/api/templates")
async def save_template(body: KnowledgeTemplate) -> dict:
    saved = get_templates().save(body)
    return saved.model_dump(by_alias=True)


@app.post("/api/templates/{template_id}/clone")
async def clone_template(template_id: str, body: Optional[dict] = None) -> dict:
    name = (body or {}).get("name") if isinstance(body, dict) else None
    cloned = get_templates().clone(template_id, name)
    if cloned is None:
        raise HTTPException(404, "template not found")
    return cloned.model_dump(by_alias=True)


@app.delete("/api/templates/{template_id}")
async def delete_template(template_id: str) -> dict:
    if not get_templates().delete(template_id):
        raise HTTPException(409, "cannot delete (built-in or not found)")
    return {"ok": True}


# ── project registry ─────────────────────────────────────
def _project_status(st: ProjectState, running: bool) -> str:
    done, total = project_summary(st)
    if total and done == total:
        return "complete"
    if running:
        return "running"
    if any(t.status == "awaiting_human" for t in st.tasks.values()):
        return "blocked"
    return "draft"


@app.get("/api/projects")
async def list_projects() -> list[dict]:
    store = get_store()
    items: list[dict] = []
    for m in store.list_meta():
        st = store.get(m.id)
        if st is None:
            continue
        done, total = project_summary(st)
        items.append({
            **m.model_dump(by_alias=True),
            "status": _project_status(st, _run(m.id)["running"]),
            "tasksDone": done,
            "tasksTotal": total,
        })
    # Newest first.
    items.sort(key=lambda i: i.get("createdAt", ""), reverse=True)
    return items


class CreateProject(BaseModel):
    name: str
    brand: str
    industry: IndustryRef
    kpi: str = "Sell-out Volume"


@app.post("/api/projects")
async def create_project(body: CreateProject) -> dict:
    if not body.name.strip():
        raise HTTPException(422, "project name is required")
    if not body.brand.strip():
        raise HTTPException(422, "brand name is required")
    if not ind.validate_industry(body.industry.l1, body.industry.l2, body.industry.l3):
        raise HTTPException(422, "invalid industry selection")
    meta = get_store().create(body.name, body.brand, body.industry, body.kpi)
    return meta.model_dump(by_alias=True)


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str) -> dict:
    if _run(project_id)["running"]:
        raise HTTPException(409, "cannot delete a running project")
    ok = get_store().delete(project_id)
    if not ok:
        raise HTTPException(404, "project not found")
    get_files().purge(project_id)
    _runs.pop(project_id, None)
    return {"ok": True}


# ── per-project state ────────────────────────────────────
@app.get("/api/projects/{project_id}/state")
async def state(project_id: str) -> dict:
    return _require_state(project_id).model_dump(by_alias=True)


@app.post("/api/projects/{project_id}/reset")
async def reset(project_id: str) -> dict:
    if get_store().reset(project_id) is None:
        raise HTTPException(404, "project not found")
    _run(project_id)["last_status"] = None
    return {"ok": True}


# ── execution ────────────────────────────────────────────
class RunRequest(BaseModel):
    autopilot: bool = True
    max_steps: int = 300


async def _run_job(project_id: str, autopilot: bool, max_steps: int) -> None:
    store = get_store()
    st = store.get(project_id)
    if st is None:
        _run(project_id)["running"] = False
        return
    try:
        status = await run_until_blocked(
            _engine, st, autopilot=autopilot, max_steps=max_steps,
            save=lambda: store.save(project_id),
        )
        _run(project_id)["last_status"] = status
    finally:
        store.save(project_id)
        _run(project_id)["running"] = False


@app.post("/api/projects/{project_id}/run")
async def run(project_id: str, req: RunRequest) -> dict:
    _require_state(project_id)
    guard = _run(project_id)
    if guard["running"]:
        return {"started": False, "reason": "already running"}
    guard["running"] = True
    asyncio.create_task(_run_job(project_id, req.autopilot, req.max_steps))
    return {"started": True, "autopilot": req.autopilot}


@app.get("/api/projects/{project_id}/run/status")
async def run_status(project_id: str) -> dict:
    guard = _run(project_id)
    return {"running": guard["running"], "status": guard["last_status"]}


# ── project folder (uploaded source files) ──────────────
_MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # 30 MB per file


@app.get("/api/projects/{project_id}/files")
async def list_files(project_id: str) -> list[dict]:
    _require_state(project_id)
    return [f.model_dump(by_alias=True) for f in get_files().list(project_id)]


@app.post("/api/projects/{project_id}/files")
async def upload_file(project_id: str, category: str = Form(...),
                      file: UploadFile = File(...),
                      slot: Optional[str] = Form(None)) -> dict:
    _require_state(project_id)
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file exceeds 30 MB limit")
    if not content:
        raise HTTPException(422, "empty file")
    try:
        record = get_files().add(
            project_id, category, file.filename or "upload", content,
            content_type=file.content_type or "", slot=slot or None,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if (category or "").strip() == "data":
        # Re-bind the project's long table on the next compute (per-project data).
        from app.agents.dataset_cache import invalidate_project
        invalidate_project(project_id)
    return record.model_dump(by_alias=True)


@app.get("/api/projects/{project_id}/data-request/manifest")
async def data_request_manifest(project_id: str) -> dict:
    st = _require_state(project_id)
    from app.agents.data_request import build_manifest
    return build_manifest(st).model_dump(by_alias=True)


@app.get("/api/projects/{project_id}/data-request/export")
async def data_request_export(project_id: str) -> Response:
    """Download the Data Request as a ZIP: one .xlsx workbook per L3, one sheet per L4."""
    st = _require_state(project_id)
    from app.agents.data_request import build_export_zip
    data = build_export_zip(st)
    return Response(
        content=data, media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="Data_Request.zip"'},
    )


@app.get("/api/projects/{project_id}/files/{file_id}")
async def download_file(project_id: str, file_id: str) -> FileResponse:
    _require_state(project_id)
    found = get_files().get_path(project_id, file_id)
    if found is None:
        raise HTTPException(404, "file not found")
    record, path = found
    return FileResponse(path, filename=record.filename)


@app.delete("/api/projects/{project_id}/files/{file_id}")
async def delete_file(project_id: str, file_id: str) -> dict:
    _require_state(project_id)
    if not get_files().delete(project_id, file_id):
        raise HTTPException(404, "file not found")
    return {"ok": True}


# ── project profile (editable granularity + scope) ──────
@app.put("/api/projects/{project_id}/profile")
async def update_profile(project_id: str, body: ProjectProfile) -> dict:
    st = _require_state(project_id)
    # apply_profile sets st.profile and re-renders the a-scope deliverable; it is
    # shared with the chat-edit apply path so both stay in lockstep.
    apply_profile(st, body)
    get_store().save(project_id)
    return body.model_dump(by_alias=True)


# ── global model-service config (LLM + ASR, one for all projects) ──
@app.get("/api/model-config")
async def get_model_config() -> dict:
    from app.store.model_service import get_model_service
    return get_model_service().model_dump(by_alias=True)


@app.put("/api/model-config")
async def update_model_config(body: GlobalModelConfig) -> dict:
    from app.store.model_service import save_model_service
    return save_model_service(body).model_dump(by_alias=True)


# ── factor tree (per-node accept / reject / edit) ───────
@app.put("/api/projects/{project_id}/factor-tree")
async def update_factor_tree(project_id: str, body: FactorTree) -> dict:
    st = _require_state(project_id)
    apply_factor_tree(st, body)
    get_store().save(project_id)
    return body.model_dump(by_alias=True)


class ApplyPack(BaseModel):
    industryL1: Optional[str] = None
    industryL2: Optional[str] = None


@app.post("/api/projects/{project_id}/apply-pack")
async def apply_pack(project_id: str, body: ApplyPack) -> dict:
    """Re-seed the project's factor tree from an industry knowledge pack,
    preserving accepted / rejected factors and AI/manual additions."""
    from app.agents.business import apply_pack_to_factor_tree

    st = _require_state(project_id)
    tree = apply_pack_to_factor_tree(st, body.industryL1 or "", body.industryL2)
    get_store().save(project_id)
    return tree.model_dump(by_alias=True)


# ── data quality scorecard (S2 · per-metric disposition) ─
@app.put("/api/projects/{project_id}/quality-scorecard")
async def update_quality_scorecard(project_id: str, body: QualityScorecard) -> dict:
    st = _require_state(project_id)
    apply_quality_scorecard(st, body)
    get_store().save(project_id)
    return body.model_dump(by_alias=True)


# ── client Q&A tracker (S2 · editable data/indicator questions) ─
@app.put("/api/projects/{project_id}/client-qa")
async def update_client_qa(project_id: str, body: ClientQA) -> dict:
    st = _require_state(project_id)
    apply_client_qa(st, body)
    get_store().save(project_id)
    return body.model_dump(by_alias=True)


# ── data engine (raw → review → clean → publish data asset) ─
class CreateAsset(BaseModel):
    name: str
    description: str = ""
    sourceFileIds: list[str] = []


class UpdateAsset(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sourceFileIds: Optional[list[str]] = None


class RunSql(BaseModel):
    sql: str


def _require_asset(project_id: str, asset_id: str):
    st = _require_state(project_id)
    asset = st.data_asset(asset_id)
    if asset is None:
        raise HTTPException(404, "data asset not found")
    return st, asset


@app.get("/api/projects/{project_id}/data-assets")
async def list_data_assets(project_id: str) -> list[dict]:
    st = _require_state(project_id)
    return [a.model_dump(by_alias=True) for a in st.data_assets]


@app.post("/api/projects/{project_id}/data-assets")
async def create_data_asset(project_id: str, body: CreateAsset) -> dict:
    from app.dataeng import assets as asset_svc
    st = _require_state(project_id)
    if not body.name.strip():
        raise HTTPException(422, "asset name is required")
    asset = asset_svc.create_asset(st, body.name, body.description, body.sourceFileIds)
    get_store().save(project_id)
    return asset.model_dump(by_alias=True)


@app.get("/api/projects/{project_id}/data-assets/{asset_id}")
async def get_data_asset(project_id: str, asset_id: str) -> dict:
    _, asset = _require_asset(project_id, asset_id)
    return asset.model_dump(by_alias=True)


@app.put("/api/projects/{project_id}/data-assets/{asset_id}")
async def update_data_asset(project_id: str, asset_id: str, body: UpdateAsset) -> dict:
    from app.dataeng import assets as asset_svc
    st, asset = _require_asset(project_id, asset_id)
    if body.name is not None:
        asset.name = body.name.strip() or asset.name
    if body.description is not None:
        asset.description = body.description
    if body.sourceFileIds is not None:
        asset.source_file_ids = body.sourceFileIds
    asset_svc.touch(asset)
    get_store().save(project_id)
    return asset.model_dump(by_alias=True)


@app.delete("/api/projects/{project_id}/data-assets/{asset_id}")
async def delete_data_asset(project_id: str, asset_id: str) -> dict:
    from app.dataeng import assets as asset_svc
    st = _require_state(project_id)
    if not asset_svc.delete_asset(project_id, st, asset_id):
        raise HTTPException(404, "data asset not found")
    get_store().save(project_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/review")
async def review_data_asset(project_id: str, asset_id: str) -> dict:
    from app.dataeng import assets as asset_svc
    from app.dataeng.profile import build_review_report
    st, asset = _require_asset(project_id, asset_id)
    asset.review = build_review_report(project_id, asset)
    asset.raw_tables = asset.review.tables
    if asset.status == "raw":
        asset.status = "reviewed"
    asset_svc.touch(asset)
    get_store().save(project_id)
    return asset.model_dump(by_alias=True)


@app.put("/api/projects/{project_id}/data-assets/{asset_id}/cleaning-spec")
async def update_cleaning_spec(project_id: str, asset_id: str, body: CleaningSpec) -> dict:
    from app.dataeng import assets as asset_svc
    st, asset = _require_asset(project_id, asset_id)
    asset.cleaning_spec = body
    if asset.status in ("raw", "reviewed"):
        asset.status = "spec"
    asset_svc.touch(asset)
    get_store().save(project_id)
    return asset.model_dump(by_alias=True)


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/sql/generate")
async def generate_asset_sql(project_id: str, asset_id: str) -> dict:
    from app.dataeng import assets as asset_svc
    from app.dataeng.sql_gen import generate_sql
    st, asset = _require_asset(project_id, asset_id)
    asset.sql_draft = await generate_sql(project_id, asset)
    if asset.sql_draft.status == "ok" and asset.status in ("raw", "reviewed", "spec"):
        asset.status = "cleaned"
    asset_svc.touch(asset)
    get_store().save(project_id)
    return asset.model_dump(by_alias=True)


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/sql/run")
async def run_asset_sql(project_id: str, asset_id: str, body: RunSql) -> dict:
    from app.dataeng import assets as asset_svc
    from app.dataeng.sql_gen import run_preview
    st, asset = _require_asset(project_id, asset_id)
    asset.sql_draft = run_preview(project_id, asset, body.sql)
    if asset.sql_draft.status == "ok" and asset.status in ("raw", "reviewed", "spec"):
        asset.status = "cleaned"
    asset_svc.touch(asset)
    get_store().save(project_id)
    return asset.model_dump(by_alias=True)


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/publish")
async def publish_data_asset(project_id: str, asset_id: str) -> dict:
    from app.dataeng import assets as asset_svc
    st, asset = _require_asset(project_id, asset_id)
    try:
        asset_svc.publish_asset(project_id, st, asset)
    except asset_svc.PublishError as e:
        raise HTTPException(409, str(e)) from e
    get_store().save(project_id)
    return asset.model_dump(by_alias=True)


# ── human actions ────────────────────────────────────────
class ResolveDecision(BaseModel):
    optionId: str
    note: str = ""


@app.post("/api/projects/{project_id}/decisions/{decision_id}/resolve")
async def resolve_decision(project_id: str, decision_id: str, body: ResolveDecision) -> dict:
    st = _require_state(project_id)
    if decision_id not in st.decisions:
        raise HTTPException(404, "decision not found")
    _engine.resolve_decision(st, decision_id, body.optionId, body.note)
    get_store().save(project_id)
    return {"ok": True}


class SubmitAssignment(BaseModel):
    note: str = ""
    choice: Optional[str] = None  # picked source-choice option id (e.g. 1.1a template/upload)


@app.post("/api/projects/{project_id}/assignments/{assignment_id}/submit")
async def submit_assignment(project_id: str, assignment_id: str, body: SubmitAssignment) -> dict:
    st = _require_state(project_id)
    if assignment_id not in st.assignments:
        raise HTTPException(404, "assignment not found")
    ok = await _engine.submit_assignment(st, assignment_id, body.note, choice=body.choice)
    if not ok:
        ar = st.assignments[assignment_id]
        where = f" ({ar.category})" if ar.category else ""
        raise HTTPException(
            409, f"Upload required: add the files to the Project Folder{where} before submitting. "
                 "This deliverable is parsed only from your real materials.")
    get_store().save(project_id)
    return {"ok": True}


class ResolveProposal(BaseModel):
    accept: bool


@app.post("/api/projects/{project_id}/proposals/{proposal_id}/resolve")
async def resolve_proposal(project_id: str, proposal_id: str, body: ResolveProposal) -> dict:
    st = _require_state(project_id)
    _engine.resolve_proposal(st, proposal_id, body.accept)
    get_store().save(project_id)
    return {"ok": True}


class ResolveInsight(BaseModel):
    actioned: bool


@app.post("/api/projects/{project_id}/insights/{insight_id}/resolve")
async def resolve_insight(project_id: str, insight_id: str, body: ResolveInsight) -> dict:
    st = _require_state(project_id)
    _engine.resolve_insight(st, insight_id, body.actioned)
    get_store().save(project_id)
    return {"ok": True}


class ChooseAi(BaseModel):
    optionId: str


@app.post("/api/projects/{project_id}/ai-choices/{set_id}")
async def choose_ai(project_id: str, set_id: str, body: ChooseAi) -> dict:
    st = _require_state(project_id)
    _engine.choose_ai_option(st, set_id, body.optionId)
    get_store().save(project_id)
    return {"ok": True}


# ── assistant ────────────────────────────────────────────
class AskBody(BaseModel):
    text: str


@app.post("/api/projects/{project_id}/assistant")
async def assistant(project_id: str, body: AskBody) -> dict:
    store = get_store()
    st = _require_state(project_id)
    st.assistant.append({"role": "user", "text": body.text})  # type: ignore[arg-type]
    # Prioritize result-bearing artifacts, then the rest.
    priority = ["a-decomp-results", "a-tech-review", "a-final-report", "a-model-candidates",
                "a-stat-tests", "a-quality-scorecard", "a-factor-tree"]
    present = [a.id for a in st.artifacts if not a.internal]
    visible = [aid for aid in priority if aid in present] + [a for a in present if a not in priority]
    ctx = artifact_text(st, visible[:16])
    # Compact real model results from the analysis blackboard (authoritative numbers).
    picked = st.analysis.get("picked", {})
    results = "; ".join(
        f"{o}: R²={c.get('r2'):.3f}, MAPE={c.get('mape'):.1f}%, baseline={c.get('baseline_pct'):.1f}%, "
        f"flags={len(c.get('red_flags', []))}" for o, c in picked.items()
    ) or "no model results yet"
    try:
        answer = await get_llm().chat([
            {"role": "system", "content": agent_system("control")
             + " Answer the user's question about the MMM project grounded ONLY in the real results and "
             "artifacts below. The MODEL RESULTS line holds the authoritative computed numbers."},
            {"role": "user", "content": f"MODEL RESULTS: {results}\n\nARTIFACTS:\n{ctx}\n\nQUESTION: {body.text}"},
        ], temperature=0.3, max_tokens=2048)
    except Exception as e:  # noqa: BLE001
        answer = f"(assistant unavailable: {e})"
    turn = {"role": "assistant", "text": answer.strip()}
    st.assistant.append(turn)  # type: ignore[arg-type]
    store.save(project_id)
    return turn


# ── chat-driven artifact editing (draft → preview → apply) ─
@app.post("/api/projects/{project_id}/artifacts/{artifact_id}/edit")
async def draft_artifact_edit(project_id: str, artifact_id: str, body: AskBody) -> dict:
    """Draft a proposed revision of an artifact from a natural-language request.

    Persists the chat turns; returns `{reply, proposal}` (proposal is null on a
    user-facing failure). Does NOT change the artifact — that happens on apply.
    """
    store = get_store()
    st = _require_state(project_id)
    art = st.artifact(artifact_id)
    if art is None:
        raise HTTPException(404, "artifact not found")
    thread = st.artifact_chats.setdefault(artifact_id, [])
    thread.append({"role": "user", "text": body.text})  # type: ignore[arg-type]
    proposal_payload: Optional[dict] = None
    try:
        proposal = await draft_edit(st, art, body.text)
        reply_text = proposal.summary
        proposal_payload = proposal.model_dump(by_alias=True)
    except ArtifactEditError as e:
        reply_text = str(e)
    except Exception as e:  # noqa: BLE001
        reply_text = f"(edit unavailable: {e})"
    thread.append({"role": "assistant", "text": reply_text})  # type: ignore[arg-type]
    store.save(project_id)
    return {"reply": {"role": "assistant", "text": reply_text}, "proposal": proposal_payload}


@app.post("/api/projects/{project_id}/artifacts/{artifact_id}/edit/apply")
async def apply_artifact_edit(project_id: str, artifact_id: str, body: ArtifactEditProposal) -> dict:
    """Apply a previously-drafted proposal, persisting the artifact change."""
    store = get_store()
    st = _require_state(project_id)
    if body.artifact_id != artifact_id:
        raise HTTPException(400, "artifact id mismatch")
    try:
        art = apply_proposal(st, body)
    except ArtifactEditError as e:
        raise HTTPException(400, str(e))
    thread = st.artifact_chats.setdefault(artifact_id, [])
    thread.append(  # type: ignore[arg-type]
        {"role": "assistant", "text": f"✓ Applied. “{art.name}” is now at v{art.version}."}
    )
    store.save(project_id)
    return art.model_dump(by_alias=True)
