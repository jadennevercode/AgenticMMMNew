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
    apply_factor_tree,
    apply_ols_config,
    apply_profile,
    apply_proposal,
    apply_quality_scorecard,
    apply_stat_scorecard,
    draft_edit,
)
from app.agents.common import agent_system, artifact_text
from app.agents.registry import build_engine
from app.domain import blueprint as bp
from app.domain import industries as ind
from app.domain.models import (
    AnomalyReview,
    ArtifactEditProposal,
    FactorTree,
    GlobalModelConfig,
    IndustryRef,
    KnowledgeTemplate,
    OlsConfig,
    ProjectProfile,
    QualityScorecard,
    StatScorecard,
    TargetColumn,
    TimeWindow,
    TransformPipeline,
)
from app.llm.volcano import get_llm
from app.orchestrator.runner import run_until_blocked
from app.store.files import get_files
from app.store.state import ProjectState, get_store, project_summary
from app.store.templates import get_templates
from app.tools import registry as tools

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


# ── analysis tools (cross-project registry) ──────────────
@app.get("/api/tools")
async def list_tools() -> list[dict]:
    """The tool catalog — every check a task can explicitly call."""
    return [s.model_dump(by_alias=True) for s in tools.list_specs()]


@app.get("/api/tools/{tool_id}")
async def tool_detail(tool_id: str) -> dict:
    """One tool's full page: scenario, method, bands, live source, API surface."""
    try:
        return tools.detail(tool_id).model_dump(by_alias=True)
    except KeyError:
        raise HTTPException(404, "unknown tool") from None


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


@app.get("/api/projects/{project_id}/tool-invocations")
async def tool_invocations(project_id: str, taskId: Optional[str] = None,
                           toolId: Optional[str] = None) -> list[dict]:
    """This project's tool-call trace, newest first (optionally per task / tool)."""
    st = _require_state(project_id)
    items = [v for v in st.tool_invocations
             if (taskId is None or v.task_id == taskId)
             and (toolId is None or v.tool_id == toolId)]
    return [v.model_dump(by_alias=True) for v in items]


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
    from app.dataeng import preview
    st = _require_state(project_id)
    if not get_files().delete(project_id, file_id):
        raise HTTPException(404, "file not found")
    # A data asset still listing this file must re-read its sources, or the editor
    # keeps previewing a table whose file is gone.
    for asset in st.data_assets:
        if file_id in asset.source_file_ids:
            preview.invalidate(project_id, asset.id)
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


# ── time windows (FND-002: comparable-period definitions, reused by BV + Reporting) ──
@app.get("/api/projects/{project_id}/time-windows")
async def get_time_windows(project_id: str) -> list[dict]:
    st = _require_state(project_id)
    return [w.model_dump(by_alias=True) for w in st.time_windows]


@app.put("/api/projects/{project_id}/time-windows")
async def update_time_windows(project_id: str, body: list[TimeWindow]) -> list[dict]:
    """Replace the project's time-window set. Each window's comparison bounds are
    normalised (a yoy window gets its comparison window derived as the same months
    one year earlier) so callers can save just the current window + type."""
    from app.agents.time_windows import normalize_window
    st = _require_state(project_id)
    st.time_windows = [normalize_window(w) for w in body]
    get_store().save(project_id)
    return [w.model_dump(by_alias=True) for w in st.time_windows]


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


# ── statistical score (S2 · 2.4 · per-indicator disposition) ─
@app.put("/api/projects/{project_id}/stat-scorecard")
async def update_stat_scorecard(project_id: str, body: StatScorecard) -> dict:
    st = _require_state(project_id)
    apply_stat_scorecard(st, body)
    get_store().save(project_id)
    return body.model_dump(by_alias=True)


# ── OLS setup (S2 · 2.5 · confirmed Y / X / params — re-fits on save) ─
@app.put("/api/projects/{project_id}/ols-config")
async def update_ols_config(project_id: str, body: OlsConfig) -> dict:
    st = _require_state(project_id)
    apply_ols_config(st, body)
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
        from app.dataeng import preview
        preview.invalidate(project_id, asset.id)
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


# ── dbt workspace (the transform path: typed pipeline → dbt) ──────────
@app.get("/api/projects/{project_id}/data-assets/{asset_id}/dbt/status")
async def dbt_status(project_id: str, asset_id: str) -> dict:
    """dbt binary availability + this asset's workspace model files."""
    from app.dataeng.dbt import binary, service
    _, asset = _require_asset(project_id, asset_id)
    ok, msg = binary.available()
    return {"available": ok, "message": msg, **service.list_models(project_id, asset)}


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/dbt/build")
async def dbt_build(project_id: str, asset_id: str) -> dict:
    from app.dataeng.dbt import service
    st, asset = _require_asset(project_id, asset_id)
    try:
        service.build(st, project_id, asset)
    except service.DbtServiceError as e:
        raise HTTPException(409, str(e)) from e
    get_store().save(project_id)
    return asset.model_dump(by_alias=True)


class GenerateBody(BaseModel):
    instruction: str = ""


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/dbt/generate")
async def dbt_generate(project_id: str, asset_id: str, body: GenerateBody | None = None) -> dict:
    """AI-draft or adjust the asset's transform pipeline (structured steps)."""
    from app.dataeng.dbt import service
    st, asset = _require_asset(project_id, asset_id)
    try:
        await service.ai_pipeline(st, project_id, asset, (body.instruction if body else ""))
    except service.DbtServiceError as e:
        raise HTTPException(409, str(e)) from e
    get_store().save(project_id)
    return asset.model_dump(by_alias=True)


@app.get("/api/projects/{project_id}/data-assets/{asset_id}/pipeline")
async def get_pipeline(project_id: str, asset_id: str) -> dict:
    from app.dataeng import preview
    from app.dataeng.sources import heal_pipeline_inputs
    _, asset = _require_asset(project_id, asset_id)
    pipe = asset.pipeline or TransformPipeline()
    # Persist the one-off re-pointing of inputs stranded by the pre-stable raw
    # table naming, so the editor loads a pipeline that actually compiles.
    if heal_pipeline_inputs(pipe, preview.cached_sources(project_id, asset).tables):
        asset.pipeline = pipe
        get_store().save(project_id)
    return pipe.model_dump(by_alias=True)


@app.put("/api/projects/{project_id}/data-assets/{asset_id}/pipeline")
async def put_pipeline(project_id: str, asset_id: str, body: TransformPipeline) -> dict:
    st, asset = _require_asset(project_id, asset_id)
    asset.pipeline = body
    get_store().save(project_id)
    return body.model_dump(by_alias=True)


class SuggestEnumBody(BaseModel):
    """Ground the suggestion on the values reaching the step, not on the raw files:
    an enum step usually sits downstream of a rename, so the column it standardises
    exists only in the pipeline stream."""
    pipeline: Optional[TransformPipeline] = None
    stepId: str = ""
    field: str
    targetColumn: str


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/pipeline/suggest-enum")
async def pipeline_suggest_enum(project_id: str, asset_id: str, body: SuggestEnumBody) -> dict:
    from app.dataeng.dbt import service
    st, asset = _require_asset(project_id, asset_id)
    if not body.field.strip():
        raise HTTPException(422, "field is required")
    pipe = body.pipeline if body.pipeline is not None else asset.pipeline
    upstream, err = _upstream_of(pipe, body.stepId)
    if err:
        return {"ok": False, "error": err, "entries": []}
    step = next((s for s in (pipe.steps if pipe else []) if s.id == body.stepId), None)
    entries, error = await service.suggest_enum_map(
        st, project_id, asset, pipe, upstream, body.field.strip(), body.targetColumn,
        existing=(step.enum_map if step else []))
    if error:
        return {"ok": False, "error": error, "entries": []}
    return {"ok": True, "error": "", "entries": [e.model_dump(by_alias=True) for e in entries]}


class PreviewBody(BaseModel):
    """Preview the pipeline as it stands in the editor — the pipeline travels with
    the request so an unsaved edit renders without a save/build round trip."""
    pipeline: Optional[TransformPipeline] = None
    stepId: str = ""            # a step id, or 'source:<table>'; '' = the output step
    limit: int = 200


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/pipeline/preview")
async def pipeline_preview(project_id: str, asset_id: str, body: PreviewBody) -> dict:
    """Run the pipeline prefix ending at one step in the DuckDB sandbox."""
    from app.dataeng import preview
    st, asset = _require_asset(project_id, asset_id)
    pipe = body.pipeline if body.pipeline is not None else asset.pipeline
    res = preview.preview_step(st, project_id, asset, pipe, body.stepId, limit=body.limit)
    return {
        "ok": res.ok, "error": res.error, "columns": res.columns,
        "rows": res.rows, "rowCount": res.row_count,
        "stats": [
            {"name": s.name, "type": s.type, "nullPct": s.null_pct,
             "distinct": s.distinct, "min": s.min, "max": s.max,
             "top": [[v, n] for v, n in s.top], "histogram": s.histogram}
            for s in res.stats
        ],
    }


class InputColumnsBody(BaseModel):
    """Columns available at a step — the field-map editor cannot ask a person to
    name source columns it has never shown them."""
    pipeline: Optional[TransformPipeline] = None
    stepId: str = ""            # the step whose *input* is read, or 'source:<table>'


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/pipeline/input-columns")
async def pipeline_input_columns(project_id: str, asset_id: str, body: InputColumnsBody) -> dict:
    from app.dataeng import preview
    st, asset = _require_asset(project_id, asset_id)
    pipe = body.pipeline if body.pipeline is not None else asset.pipeline
    upstream, err = _upstream_of(pipe, body.stepId)
    if err:
        return {"ok": False, "error": err, "columns": []}
    columns, error = preview.input_columns(st, project_id, asset, pipe, upstream)
    return {"ok": not error, "error": error, "columns": columns}


class SuggestFieldMapBody(BaseModel):
    pipeline: Optional[TransformPipeline] = None
    stepId: str = ""


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/pipeline/suggest-field-map")
async def pipeline_suggest_field_map(project_id: str, asset_id: str,
                                     body: SuggestFieldMapBody) -> dict:
    from app.dataeng.dbt import service
    st, asset = _require_asset(project_id, asset_id)
    pipe = body.pipeline if body.pipeline is not None else asset.pipeline
    upstream, err = _upstream_of(pipe, body.stepId)
    if err:
        return {"ok": False, "error": err, "entries": []}
    step = next((s for s in (pipe.steps if pipe else []) if s.id == body.stepId), None)
    entries, error = await service.suggest_field_map(
        st, project_id, asset, pipe, upstream, existing=(step.field_map if step else []))
    if error:
        return {"ok": False, "error": error, "entries": []}
    return {"ok": True, "error": "", "entries": [e.model_dump(by_alias=True) for e in entries]}


class SuggestSqlBody(BaseModel):
    pipeline: Optional[TransformPipeline] = None
    stepId: str = ""
    instruction: str


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/pipeline/suggest-sql")
async def pipeline_suggest_sql(project_id: str, asset_id: str, body: SuggestSqlBody) -> dict:
    """Draft a custom_sql step from plain English (validated in the sandbox first)."""
    from app.dataeng.dbt import service
    st, asset = _require_asset(project_id, asset_id)
    pipe = body.pipeline if body.pipeline is not None else asset.pipeline
    sql, error = await service.suggest_sql(
        st, project_id, asset, pipe, body.stepId, body.instruction)
    return {"ok": not error, "error": error, "sql": sql}


class ColumnValuesBody(BaseModel):
    """Distinct values of one column as they reach a step — the enum editor's
    ground truth. Like the preview, the pipeline travels with the request so an
    unsaved rewiring is reflected immediately."""
    pipeline: Optional[TransformPipeline] = None
    stepId: str = ""            # the step whose *input* is read, or 'source:<table>'
    column: str
    limit: int = 500


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/pipeline/column-values")
async def pipeline_column_values(project_id: str, asset_id: str, body: ColumnValuesBody) -> dict:
    from app.dataeng import preview
    st, asset = _require_asset(project_id, asset_id)
    if not body.column.strip():
        raise HTTPException(422, "column is required")
    pipe = body.pipeline if body.pipeline is not None else asset.pipeline
    upstream, err = _upstream_of(pipe, body.stepId)
    if err:
        return {"ok": False, "error": err, "values": []}
    values, error = preview.column_values(
        st, project_id, asset, pipe, upstream, body.column.strip(), limit=body.limit)
    if error:
        return {"ok": False, "error": error, "values": []}
    return {"ok": True, "error": "", "values": [[v, n] for v, n in values]}


def _upstream_of(pipe, step_id: str) -> tuple[str, str]:
    """Resolve what a step *reads* — its first input, or the source token itself.

    Enum standardisation is decided against the values arriving at a step, never
    the ones it has already rewritten, so both the value list and the clustering
    key on the upstream rather than the step.
    """
    if step_id.startswith("source:"):
        return step_id, ""
    step = next((s for s in (pipe.steps if pipe else []) if s.id == step_id), None)
    if step is None:
        return "", f"step {step_id!r} is not in this pipeline"
    if not step.inputs:
        return "", "Connect an input to this step first."
    return step.inputs[0], ""


class ClusterEnumBody(BaseModel):
    """Cluster the values reaching an enum_map step, so near-duplicate spellings
    are reviewed as one decision instead of row by row."""
    pipeline: Optional[TransformPipeline] = None
    stepId: str = ""            # the enum_map step (its input is clustered), or 'source:<t>'
    field: str


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/pipeline/cluster-enum")
async def pipeline_cluster_enum(project_id: str, asset_id: str, body: ClusterEnumBody) -> dict:
    from app.dataeng import cluster, preview
    st, asset = _require_asset(project_id, asset_id)
    if not body.field.strip():
        raise HTTPException(422, "field is required")
    pipe = body.pipeline if body.pipeline is not None else asset.pipeline

    upstream, err = _upstream_of(pipe, body.stepId)
    if err:
        return {"ok": False, "error": err, "values": 0, "clusters": []}

    values, error = preview.column_values(
        st, project_id, asset, pipe, upstream, body.field.strip())
    if error:
        return {"ok": False, "error": error, "values": 0, "clusters": []}
    clusters = cluster.cluster_values(values)
    return {
        "ok": True, "error": "", "values": len(values),
        "clusters": [
            {"key": c.key, "method": c.method, "suggestion": c.suggestion,
             "rows": c.rows, "values": [[v, n] for v, n in c.values]}
            for c in clusters
        ],
    }


class WriteModel(BaseModel):
    layer: str
    name: str
    sql: str


@app.put("/api/projects/{project_id}/data-assets/{asset_id}/dbt/model")
async def dbt_write_model(project_id: str, asset_id: str, body: WriteModel) -> dict:
    from app.dataeng.dbt import service
    st, asset = _require_asset(project_id, asset_id)
    service.write_model(project_id, asset, body.layer, body.name, body.sql)
    get_store().save(project_id)
    return service.list_models(project_id, asset)


class WriteSeed(BaseModel):
    name: str
    csv: str


@app.put("/api/projects/{project_id}/data-assets/{asset_id}/dbt/seed")
async def dbt_write_seed(project_id: str, asset_id: str, body: WriteSeed) -> dict:
    from app.dataeng.dbt import service
    st, asset = _require_asset(project_id, asset_id)
    service.write_seed(project_id, asset, body.name, body.csv)
    get_store().save(project_id)
    return service.list_models(project_id, asset)


@app.get("/api/projects/{project_id}/data-assets/{asset_id}/dbt/preview")
async def dbt_preview(project_id: str, asset_id: str, model: str, limit: int = 50) -> dict:
    from app.dataeng.dbt import service
    _, asset = _require_asset(project_id, asset_id)
    try:
        return service.preview(project_id, asset, model, limit=limit)
    except service.DbtServiceError as e:
        raise HTTPException(409, str(e)) from e


@app.get("/api/projects/{project_id}/data-assets/{asset_id}/raw-preview")
async def raw_preview(project_id: str, asset_id: str, table: str, limit: int = 50) -> dict:
    """Preview a raw source table (before any transform) straight from the files."""
    from app.dataeng import preview
    from app.dataeng.dbt.service import _df_payload
    _, asset = _require_asset(project_id, asset_id)
    tables = preview.cached_sources(project_id, asset).tables
    if table not in tables:
        raise HTTPException(404, f"raw table {table!r} not found")
    return _df_payload(tables[table], cap=limit)




class FullSqlBody(BaseModel):
    """Compile the whole pipeline to one SQL statement. The pipeline may travel with
    the request so the editor can show the compiled result before saving."""
    pipeline: Optional[TransformPipeline] = None


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/pipeline/full-sql")
async def pipeline_full_sql(project_id: str, asset_id: str,
                            body: FullSqlBody | None = None) -> dict:
    from app.dataeng.dbt import service
    st, asset = _require_asset(project_id, asset_id)
    sql, error = service.full_sql(st, project_id, asset, body.pipeline if body else None)
    return {"ok": not error, "error": error, "sql": sql}


@app.post("/api/projects/{project_id}/data-assets/{asset_id}/dbt/publish")
async def dbt_publish(project_id: str, asset_id: str) -> dict:
    from app.dataeng.dbt import service
    st, asset = _require_asset(project_id, asset_id)
    try:
        service.publish(project_id, st, asset)
    except service.DbtServiceError as e:
        raise HTTPException(409, str(e)) from e
    get_store().save(project_id)
    return asset.model_dump(by_alias=True)


# ── target schema + indicator catalog ────────────────────
@app.get("/api/projects/{project_id}/target-schema")
async def get_target_schema(project_id: str) -> list[dict]:
    from app.dataeng.dbt import target_schema
    st = _require_state(project_id)
    return [c.model_dump(by_alias=True) for c in target_schema.schema_for(st)]


@app.put("/api/projects/{project_id}/target-schema")
async def put_target_schema(project_id: str, body: list[TargetColumn]) -> list[dict]:
    from app.dataeng.dbt import target_schema
    st = _require_state(project_id)
    # Re-assert the engine-owned columns: dropping `source` here would silently turn
    # off per-row provenance for every asset in the project.
    st.target_schema = target_schema._with_system_columns(list(body))
    get_store().save(project_id)
    return [c.model_dump(by_alias=True) for c in st.target_schema]


@app.get("/api/projects/{project_id}/indicators")
async def get_indicators(project_id: str) -> list[dict]:
    """The data target list: every confirmed factor row, plus orphan metrics."""
    from app.dataeng.indicators import derive_indicators
    st = _require_state(project_id)
    return [i.model_dump(by_alias=True) for i in derive_indicators(st)]


# ── Business Validation live series (task 2.3) ───────────
class ValidationSeriesQuery(BaseModel):
    l3: str
    l4: str = ""
    l5: str = ""   # DATA-004: L4–L8 cascade drilldown
    l6: str = ""
    l7: str = ""
    l8: str = ""
    indicators: list[str] = []
    grain: str = "month"
    sources: list[str] = []
    brand: list[str] = []
    channelType: list[str] = []
    provinceGroup: list[str] = []
    timeWindowId: str = ""   # DATA-005: scope + comparison against a saved time window
    kpiMetric: str = ""      # explorer-only override; the 2.3 chart never sends one
    yoyMonth: int = 0        # 1–12 → same-month YoY in the table; 0 = full year


@app.post("/api/projects/{project_id}/validation/series")
async def post_validation_series(project_id: str, body: ValidationSeriesQuery) -> dict:
    """KPI area + per-L3 overlay series + yearly/YoY table, computed live from the
    modeling long table so the Business Validation filters resolve on real rows."""
    from app.agents.time_windows import resolve_window
    from app.dataeng import validation_query
    st = _require_state(project_id)
    return validation_query.validation_series(
        st, l3=body.l3, l4=body.l4 or None, l5=body.l5 or None, l6=body.l6 or None,
        l7=body.l7 or None, l8=body.l8 or None, indicators=body.indicators or None,
        grain=body.grain, sources=body.sources or None, brand=body.brand or None,
        channel_type=body.channelType or None, province_group=body.provinceGroup or None,
        window=resolve_window(st, body.timeWindowId), kpi_metric_req=body.kpiMetric or None,
        yoy_month=body.yoyMonth,
    )


class ValidationAnalysisQuery(ValidationSeriesQuery):
    """A series query plus a regenerate flag."""
    force: bool = False


# A chart analysis is cheap to keep but unbounded in the number of filter
# permutations a user can produce, so the map is capped and evicted oldest-first.
_MAX_CHART_ANALYSES = 200


@app.post("/api/projects/{project_id}/validation/chart-analysis")
async def post_validation_chart_analysis(project_id: str, body: ValidationAnalysisQuery) -> dict:
    """The AI's reading of exactly the chart these filters produce.

    Cached per filter state and validated against a digest of the plotted numbers:
    a cached analysis whose digest no longer matches the freshly-computed series is
    regenerated rather than shown, because it is a reading of numbers that moved.
    """
    from datetime import datetime, timezone

    from app.agents import validation_analysis as va
    from app.agents.time_windows import resolve_window
    from app.dataeng import validation_query

    st = _require_state(project_id)
    query = body.model_dump(by_alias=True)
    res = validation_query.validation_series(
        st, l3=body.l3, l4=body.l4 or None, l5=body.l5 or None, l6=body.l6 or None,
        l7=body.l7 or None, l8=body.l8 or None, indicators=body.indicators or None,
        grain=body.grain, sources=body.sources or None, brand=body.brand or None,
        channel_type=body.channelType or None, province_group=body.provinceGroup or None,
        window=resolve_window(st, body.timeWindowId), kpi_metric_req=body.kpiMetric or None,
        yoy_month=body.yoyMonth,
    )

    key = va.analysis_key(query)
    digest = va.series_digest(res)
    cached = (st.validation_chart_analyses or {}).get(key)
    if cached and not body.force and cached.get("seriesDigest") == digest:
        return cached

    analysis = await va.analyze_chart(
        res, query, now=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    store = st.validation_chart_analyses or {}
    store[key] = analysis.model_dump(by_alias=True)
    if len(store) > _MAX_CHART_ANALYSES:
        for stale in sorted(store, key=lambda k: store[k].get("generatedAt", ""))[
                :len(store) - _MAX_CHART_ANALYSES]:
            store.pop(stale, None)
    st.validation_chart_analyses = store
    get_store().save(project_id)
    return store[key]


@app.get("/api/projects/{project_id}/validation-dataset")
async def get_validation_dataset(project_id: str) -> dict:
    """Flat validation dataset (long-table rows + column metadata) for the explorer."""
    from app.dataeng.validation_dataset import build_validation_dataset
    st = _require_state(project_id)
    return build_validation_dataset(st)


@app.get("/api/projects/{project_id}/validation-specs")
async def get_validation_specs(project_id: str) -> dict:
    """Saved explorer check specs, or `{}` if none have been saved yet."""
    st = _require_state(project_id)
    return st.validation_specs or {}


@app.put("/api/projects/{project_id}/validation-specs")
async def put_validation_specs(project_id: str, body: dict) -> dict:
    """Persist the explorer's current check specs."""
    st = _require_state(project_id)
    try:
        version = int(body.get("version", 1))
    except (TypeError, ValueError):
        version = 1
    st.validation_specs = {"specs": body.get("specs", []), "version": version}
    get_store().save(project_id)
    return st.validation_specs


@app.post("/api/projects/{project_id}/validation-insight")
async def post_validation_insight(project_id: str, body: dict) -> dict:
    """LLM-grounded narrative insight for a single explorer check's result rows."""
    from app.dataeng.validation_insight import generate_insight
    _require_state(project_id)  # 404s an unknown project
    text = await generate_insight(body.get("spec", {}), body.get("rows", []))
    return {"insight": text}


# ── anomaly review (S2 · 2.3a · per-anomaly handling) ────
@app.put("/api/projects/{project_id}/anomaly-review")
async def update_anomaly_review(project_id: str, body: AnomalyReview) -> dict:
    """Persist the human's ruling on each anomaly hypothesis.

    The accepted handling is read back at fit time (`ledger.anomaly_effects`), so
    saving here changes what the model is actually fitted on — an event dummy, a
    winsorized window, or nothing but a caveat.
    """
    st = _require_state(project_id)
    st.anomaly_review = body
    get_store().save(project_id)
    return body.model_dump(by_alias=True)


class SignoffBody(BaseModel):
    """One sign-off verdict. Supply `l4` + `indicator` for a single indicator,
    `pairs` (each `{"l4", "indicator"}`) for an explicit set — this is what a
    card's "Accept all" / "Deny all" should send, so the write matches exactly
    what the card rendered — or `l3` alone as a fallback that fans the verdict
    over every indicator the ledger's universe currently attributes to that
    factor. An empty `verdict` clears the entry back to un-reviewed.

    `object` names the model object (channel type) the verdict applies to;
    left empty (the default) it applies to every channel — see
    `ledger.OBJECT_ANY`."""
    l3: str = ""
    l4: str = ""
    indicator: str = ""
    pairs: list[dict] = []
    verdict: str = ""  # "yes" | "no" | ""
    object: str = ""


@app.put("/api/projects/{project_id}/signoff")
async def put_signoff(project_id: str, body: SignoffBody) -> dict:
    """Record the client's business-validation sign-off at 2.3s.

    This is a *decision*, not an artifact edit: an explicit "no" excludes the
    indicator (or, given `pairs`/`l3`, every indicator named) from the model,
    inherited by every later ledger layer. It therefore lives on ProjectState
    — the artifact body is patched in place (see `refresh_signoff_in_artifact`),
    never regenerated, so a verdict stored there always survives.

    A project saved before sign-off became indicator-granular can carry a
    legacy whole-factor verdict (``ledger.stale_factor_keys``). Writing or
    clearing at a finer grain here always clears that legacy key for the same
    L3 too — the human has now spoken at a finer grain, so the coarse legacy
    verdict must not keep silently overriding them.
    """
    from app.agents import ledger
    from app.agents.data import refresh_signoff_in_artifact

    verdict = body.verdict.strip().lower()
    if verdict not in ("", "yes", "no"):
        raise HTTPException(422, "verdict must be 'yes', 'no' or ''")
    st = _require_state(project_id)

    stale_l3s: set[str] = set()
    if body.pairs:
        # Explicit pair list (e.g. a card's "Deny all") — write exactly what
        # was displayed, not a re-derived (and possibly mismatched) set.
        rows = ledger.indicator_ledger(st)
        keys: list[str] = []
        for p in body.pairs:
            l4 = str(p.get("l4", "")) if isinstance(p, dict) else ""
            indicator = str(p.get("indicator", "")) if isinstance(p, dict) else ""
            if not indicator and not l4:
                continue
            keys.append(ledger.signoff_key(l4, indicator, body.object))
            target_l4, target_ind = l4.strip().lower(), indicator.strip().lower()
            row = next((r for r in rows if r.l4.strip().lower() == target_l4
                        and r.indicator.strip().lower() == target_ind), None)
            if row is not None and row.l3:
                stale_l3s.add(row.l3)
    elif body.l4 or body.indicator:
        keys = [ledger.signoff_key(body.l4, body.indicator, body.object)]
        target_l4 = body.l4.strip().lower()
        target_ind = body.indicator.strip().lower()
        row = next((r for r in ledger.indicator_ledger(st)
                    if r.l4.strip().lower() == target_l4
                    and r.indicator.strip().lower() == target_ind), None)
        if row is not None and row.l3:
            stale_l3s.add(row.l3)
    elif body.l3:
        # Fallback fan-out for callers that do not send `pairs`. Uses the same
        # fixed (l4, metric) universe as every other layer (post-C1), so this
        # now matches what the card displays instead of an arbitrary-L4 collapse.
        target = body.l3.strip().lower()
        rows = ledger.indicator_ledger(st)
        keys = [ledger.signoff_key(r.l4, r.indicator, body.object) for r in rows
                if r.l3.strip().lower() == target]
        stale_l3s.add(body.l3)
    else:
        raise HTTPException(422, "supply l4+indicator, pairs, or l3")

    keys = list(dict.fromkeys(keys))  # de-dupe, preserve order
    for key in keys:
        if verdict:
            st.signoffs[key] = verdict
        else:
            st.signoffs.pop(key, None)
    for l3 in stale_l3s:
        for stale_key in ledger.stale_factor_keys(st, l3):
            st.signoffs.pop(stale_key, None)

    # Patch the existing deck in place — never re-run 2.3 here (see I2): that
    # would redo the LLM narration, bump the version, and un-confirm the deck.
    refresh_signoff_in_artifact(st)
    get_store().save(project_id)
    return {"signoffs": dict(st.signoffs), "written": len(keys)}


# ── Master Data live slice (task 2.6) ────────────────────
class MasterTableQuery(BaseModel):
    brand: list[str] = []
    provinceGroup: list[str] = []
    channelType: list[str] = []
    channel: list[str] = []
    indicators: list[str] = []
    grain: str = "month"


@app.post("/api/projects/{project_id}/master-data/table")
async def post_master_table(project_id: str, body: MasterTableQuery) -> dict:
    """The adopted feature wide table for one product × channel × region slice.

    Computed live: the artifact carries the funnel and the dimensions, not every
    slice of the table (which would be enormous, and stale the moment a verdict
    changes).
    """
    from app.agents import master_data
    st = _require_state(project_id)
    return master_data.master_table(
        st, brand=body.brand or None, province_group=body.provinceGroup or None,
        channel_type=body.channelType or None, channel=body.channel or None,
        indicators=body.indicators or None, grain=body.grain,
    )


@app.get("/api/projects/{project_id}/master-data/data-station")
async def get_data_station(project_id: str, limit: int = 5000) -> dict:
    """The D.Data Station sheet (2.32): the adopted indicators' raw long rows at
    their native channel/region/time granularity."""
    from app.agents import master_data
    st = _require_state(project_id)
    return master_data.data_station(st, limit=limit)


@app.get("/api/projects/{project_id}/master-data/export")
async def export_master_data(project_id: str) -> Response:
    """Download the 2.32 ``model input`` deliverable as xlsx — two sheets:
    模型颗粒度参考表 (per-indicator 渠道×区域 granularity) and D.Data Station (the
    adopted indicators' raw long rows), uncapped."""
    from app.agents import master_data
    st = _require_state(project_id)
    data = master_data.build_export(st)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="model-input-{project_id}.xlsx"'},
    )


# ── Indicator lifecycle ledger (S2 · every layer's verdict) ─
@app.get("/api/projects/{project_id}/indicator-ledger")
async def get_indicator_ledger(project_id: str) -> dict:
    """Where every indicator stands, and which layer rejected the ones that died.

    Derived from the layers' own records — the ledger stores nothing itself, so
    it can never disagree with the scorecards, the sign-offs or the OLS setup.
    """
    from app.agents import ledger
    from app.agents.dataset_cache import model_objects
    from app.agents.ledger import OBJECT_ANY
    st = _require_state(project_id)
    rows = ledger.indicator_ledger(st)
    # interim: dedup by indicator key — one verdict per indicator until the
    # Phase 1 object-aware ledger index. `indicator_ledger` now returns one row
    # PER model object (channel type); this view serializes no `object` field,
    # so without dedup the response would carry 7x duplicate rows (Danone case)
    # and inflated adopted/rejected counts.
    seen: set[tuple[str, str]] = set()
    deduped = []
    for r in rows:
        if r.key in seen:
            continue
        seen.add(r.key)
        deduped.append(r)

    def _row(r):
        return {
            "object": r.object, "l1": r.l1, "l2": r.l2, "l3": r.l3, "l4": r.l4,
            "indicator": r.indicator, "adopted": r.adopted, "rejectedAt": r.rejected_at,
            "reason": r.reason,
            "verdicts": [{"layer": v.layer, "task": v.task, "label": v.label,
                          "status": v.status, "note": v.note} for v in r.verdicts],
        }

    objs = model_objects(st) or [OBJECT_ANY]
    rows_by_object = {o: [_row(r) for r in rows if r.object in (o, OBJECT_ANY)] for o in objs}
    return {
        "layers": [{"layer": lid, "task": task, "label": label}
                   for lid, task, label in ledger.LAYERS],
        "rows": [{
            "l1": r.l1, "l2": r.l2, "l3": r.l3, "l4": r.l4, "indicator": r.indicator,
            "adopted": r.adopted, "rejectedAt": r.rejected_at, "reason": r.reason,
            "verdicts": [{"layer": v.layer, "task": v.task, "label": v.label,
                          "status": v.status, "note": v.note} for v in r.verdicts],
        } for r in deduped],
        "rowsByObject": rows_by_object,
        # TODO(Task 7): serialize the per-object funnel; for now the combined
        # rollup keeps this endpoint's response shape unchanged.
        "funnel": ledger.funnel(st)["combined"],
        "adopted": sum(1 for r in deduped if r.adopted),
        "rejected": sum(1 for r in deduped if not r.adopted),
    }


# ── FactorTree ↔ DataAssets mapping (2.1 Data Processing gate) ────
def _factor_map_payload(st) -> dict:
    from app.dataeng.mapping import resolve_factor_map
    from app.dataeng import mapping_suggest
    fmap = resolve_factor_map(st)
    # Pending rows carry ranked AI suggestions so the human reviews a proposal
    # instead of hunting the whole indicator catalog by hand.
    sugg = mapping_suggest.suggest_all(st)
    return {
        "rows": [{
            "rowId": r.row_id, "l1": r.l1, "l2": r.l2, "l3": r.l3, "l4": r.l4,
            "indicator": r.indicator, "status": r.status,
            "assetId": r.asset_id, "assetName": r.asset_name, "metric": r.metric,
            "coverageStart": r.coverage_start, "coverageEnd": r.coverage_end,
            "ignoreNote": r.ignore_note,
            "metricType": r.metric_type, "aggregation": r.aggregation,
            "coverages": [{
                "coverageId": c.coverage_id, "assetId": c.asset_id,
                "assetName": c.asset_name, "metric": c.metric,
                "coverageStart": c.coverage_start, "coverageEnd": c.coverage_end,
                "rows": c.rows, "boundBy": c.bound_by,
            } for c in r.coverages],
            "suggestions": [{
                "indicatorId": s.indicator_id, "metric": s.metric,
                "assetId": s.asset_id, "assetName": s.asset_name, "unit": s.unit,
                "coverageStart": s.coverage_start, "coverageEnd": s.coverage_end,
                "score": s.score, "reason": s.reason,
            } for s in sugg.get(r.row_id, [])],
        } for r in fmap.rows],
        "total": fmap.total, "mapped": fmap.mapped, "ignored": fmap.ignored,
        "pending": fmap.pending, "complete": fmap.complete,
        "suggested": sum(1 for r in fmap.rows if sugg.get(r.row_id)),
        # The 2.1 gate verdict, from the same judge the engine uses. The UI renders
        # `ready` and `blockers` directly instead of re-deriving readiness from
        # Project-Folder file counts (which disagreed with the server).
        "intake": _intake_payload(st),
    }


def _intake_payload(st) -> dict:
    from app.agents.intake_status import intake_status
    asg = bp.TASK_MAP["2.1"].get("assignment") or {}
    return intake_status(st, asg).to_payload()


@app.get("/api/projects/{project_id}/factor-map")
async def get_factor_map(project_id: str) -> dict:
    """Per active factor-tree row: mapped to a published asset, ignored, or pending."""
    return _factor_map_payload(_require_state(project_id))


class FactorMapIgnoreBody(BaseModel):
    rowId: str
    ignored: bool
    note: str = ""


@app.put("/api/projects/{project_id}/factor-map/ignore")
async def put_factor_map_ignore(project_id: str, body: FactorMapIgnoreBody) -> dict:
    """Mark a factor row ignored (no data source) or restore it to pending. A mapped
    row cannot be ignored — the published indicator is authoritative."""
    st = _require_state(project_id)
    if body.ignored:
        st.factor_map_ignores[body.rowId] = body.note
    else:
        st.factor_map_ignores.pop(body.rowId, None)
    # Re-render a-data-processing if it already exists so the matrix stays live.
    if st.artifact("a-data-processing") is not None:
        await _engine.handlers["2.1"](_engine, st, bp.TASK_MAP["2.1"])
    get_store().save(project_id)
    return _factor_map_payload(st)


class FactorMapIgnoreBulkBody(BaseModel):
    rowIds: list[str]
    note: str = ""


@app.put("/api/projects/{project_id}/factor-map/ignore-bulk")
async def put_factor_map_ignore_bulk(project_id: str, body: FactorMapIgnoreBulkBody) -> dict:
    """Ignore many factor rows in one request (e.g. "Ignore all pending").

    Applies every row, then re-renders `a-data-processing` and saves the project
    **once** — the single-row endpoint's handler + save runs once per call, which
    turns one button press into dozens of sequential heavy 2.1 recomputes."""
    st = _require_state(project_id)
    for row_id in body.rowIds:
        st.factor_map_ignores[row_id] = body.note
    if st.artifact("a-data-processing") is not None:
        await _engine.handlers["2.1"](_engine, st, bp.TASK_MAP["2.1"])
    get_store().save(project_id)
    return _factor_map_payload(st)


class FactorMapBindBody(BaseModel):
    rowId: str
    """Empty releases whatever is bound to the row (remap / undo)."""
    indicatorId: str = ""


@app.put("/api/projects/{project_id}/factor-map/bind")
async def put_factor_map_bind(project_id: str, body: FactorMapBindBody) -> dict:
    """Accept an AI mapping suggestion (or release a row to remap it).

    Binding sets the indicator's `treeRowId`, which the resolver already treats
    as the strongest coverage signal — so this adds a way to *accept* a match,
    not a second notion of what "mapped" means.
    """
    from app.dataeng import mapping_suggest
    st = _require_state(project_id)
    if body.indicatorId:
        if not mapping_suggest.bind(st, body.rowId, body.indicatorId):
            raise HTTPException(404, f"indicator {body.indicatorId} not found")
    else:
        mapping_suggest.unbind(st, body.rowId)
    if st.artifact("a-data-processing") is not None:
        await _engine.handlers["2.1"](_engine, st, bp.TASK_MAP["2.1"])
    get_store().save(project_id)
    return _factor_map_payload(st)


class FactorMapMetricTypeBody(BaseModel):
    l4: str
    metric: str
    """The user's model role: "Y" (response) / "X" (driver) / "excluded"."""
    metricType: str


@app.put("/api/projects/{project_id}/factor-map/metric-type")
async def put_factor_map_metric_type(project_id: str, body: FactorMapMetricTypeBody) -> dict:
    """Set an indicator's model role (Y / X / excluded), maintained in 2.1.

    Keyed by ``indicator_key(l4, metric)``. Choosing a new Y demotes every other
    current Y to X, so the model always has exactly one response. The change is
    applied at the ``model_df`` seam, so screening / OLS / charts / master data all
    see it consistently; the dataset cache is invalidated so they recompute."""
    from app.agents.indicator_metadata import indicator_key
    from app.agents.dataset_cache import invalidate_project
    from app.agents.overrides import METRIC_ROLE_Y, _VALID_ROLES
    if body.metricType not in _VALID_ROLES:
        raise HTTPException(422, f"metricType must be one of {sorted(_VALID_ROLES)}")
    st = _require_state(project_id)
    key = indicator_key(body.l4, body.metric)
    if body.metricType == METRIC_ROLE_Y:
        # Single-Y invariant: demote any indicator currently tagged Y to X.
        for k, v in list(st.metric_type_overrides.items()):
            if v == METRIC_ROLE_Y and k != key:
                st.metric_type_overrides[k] = "X"
    st.metric_type_overrides[key] = body.metricType
    invalidate_project(project_id)
    if st.artifact("a-data-processing") is not None:
        await _engine.handlers["2.1"](_engine, st, bp.TASK_MAP["2.1"])
    get_store().save(project_id)
    return _factor_map_payload(st)


class FactorMapAggregationBody(BaseModel):
    l4: str
    metric: str
    aggregation: str


@app.put("/api/projects/{project_id}/factor-map/aggregation")
async def put_factor_map_aggregation(project_id: str, body: FactorMapAggregationBody) -> dict:
    """Set an indicator's aggregation method, maintained in 2.1.

    The user-facing vocabulary is deliberately just SUM / AVG — the two choices
    that answer "does this indicator add up across periods and dimensions, or
    average?". Every roll-up in the pipeline honours it (national collapse, 2.2
    subchecks, 2.3 series and yearly table, 2.4 screen, 2.5 design matrix, 2.6
    master table) via ``overrides.resolve_aggregation``.

    Legacy saved values (``weighted_average``/``min``/``max``/count variants) are
    still *read* — ``national._agg_group`` keeps their branches — they just can no
    longer be set."""
    from app.agents.indicator_metadata import indicator_key
    from app.agents.dataset_cache import invalidate_project
    valid = {"sum", "average"}
    if body.aggregation not in valid:
        raise HTTPException(422, f"aggregation must be one of {sorted(valid)}")
    st = _require_state(project_id)
    st.aggregation_overrides[indicator_key(body.l4, body.metric)] = body.aggregation
    invalidate_project(project_id)
    if st.artifact("a-data-processing") is not None:
        await _engine.handlers["2.1"](_engine, st, bp.TASK_MAP["2.1"])
    get_store().save(project_id)
    return _factor_map_payload(st)


@app.get("/api/projects/{project_id}/target-schema/collect")
async def collect_schema_values(project_id: str, column: str, limit: int = 50) -> dict:
    """Distinct values of a target column observed in this project's data — from
    published asset parquets first, else raw uploads sharing the column name."""
    from app.dataeng import assets as asset_svc
    from app.dataeng.sources import asset_tables
    st = _require_state(project_id)
    values: list[str] = []

    def take(series) -> None:
        for v in series.dropna().astype(str).unique().tolist():
            if v and v not in values:
                values.append(v)

    for df in asset_svc.published_frames(project_id, st):
        if column in df.columns:
            take(df[column])
    if not values:
        for asset in st.data_assets:
            for _, df in asset_tables(project_id, asset).items():
                if column in df.columns:
                    take(df[column])
    return {"column": column, "values": values[:limit]}


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


class ChatMention(BaseModel):
    """An object the user pinned as the subject of a question.

    ``payload`` carries the ``ValidationSeriesQuery`` that produced a chart, so the
    backend re-resolves the rows itself rather than trusting numbers from the client.
    """
    kind: str          # 'chartTable' | 'chartAnalysis' | 'artifact'
    refId: str
    label: str = ""
    payload: dict = {}


class AskWithMentions(AskBody):
    mentions: list[ChatMention] = []


@app.get("/api/projects/{project_id}/mentionables")
async def mentionables(project_id: str, q: str = "") -> list[dict]:
    """Everything the chat can `@`-mention: artifacts, chart tables, AI analyses."""
    from app.agents.mentions import catalogue
    items = catalogue(_require_state(project_id))
    needle = q.strip().lower()
    if needle:
        items = [i for i in items if needle in i["label"].lower()]
    return items[:60]


@app.post("/api/projects/{project_id}/assistant")
async def assistant(project_id: str, body: AskWithMentions) -> dict:
    from app.agents.mentions import resolve as resolve_mentions

    store = get_store()
    st = _require_state(project_id)
    mentions = [m.model_dump() for m in body.mentions]
    st.assistant.append({"role": "user", "text": body.text,  # type: ignore[arg-type]
                         "mentions": [{"kind": m["kind"], "refId": m["refId"],
                                       "label": m["label"]} for m in mentions]})
    # Prioritize result-bearing artifacts, then the rest.
    priority = ["a-decomp-results", "a-tech-review", "a-final-report", "a-model-candidates",
                "a-stat-tests", "a-quality-scorecard", "a-factor-tree"]
    present = [a.id for a in st.artifacts if not a.internal]
    visible = [aid for aid in priority if aid in present] + [a for a in present if a not in priority]
    # With a mention the subject is already pinned, so the artifacts are background:
    # carry far fewer of them. Sixteen artifacts plus a chart's own table overran
    # the model's budget and came back empty.
    ctx = artifact_text(st, visible[:6 if body.mentions else 16])
    # Compact real model results from the analysis blackboard (authoritative numbers).
    picked = st.analysis.get("picked", {})
    results = "; ".join(
        f"{o}: R²={c.get('r2'):.3f}, MAPE={c.get('mape'):.1f}%, baseline={c.get('baseline_pct'):.1f}%, "
        f"flags={len(c.get('red_flags', []))}" for o, c in picked.items()
    ) or "no model results yet"
    mention_text, mention_labels = resolve_mentions(st, mentions)
    system = (agent_system("control")
              + " Answer the user's question about the MMM project grounded ONLY in the real "
              "results and artifacts below. The MODEL RESULTS line holds the authoritative "
              "computed numbers.")
    user = f"MODEL RESULTS: {results}\n\n"
    if mention_text:
        system += (" MENTIONED CONTEXT is the specific subject of this question — answer about "
                   "it first and cite its own numbers; the artifacts are background. If it does "
                   "not contain what is being asked, say so instead of answering from the "
                   "artifacts as if it did.")
        user += f"MENTIONED CONTEXT:\n{mention_text}\n\n"
    user += f"ARTIFACTS:\n{ctx}\n\nQUESTION: {body.text}"
    try:
        answer = await get_llm().chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], temperature=0.3, max_tokens=2048)
    except Exception as e:  # noqa: BLE001
        answer = f"(assistant unavailable: {e})"
    # An empty reply is a failure, not an answer — returning "" rendered as a blank
    # bubble with nothing to retry from.
    if not answer.strip():
        answer = ("(the assistant returned nothing — the question plus its context may "
                  "have exceeded the model's limit. Try mentioning fewer objects, or "
                  "narrowing the chart's filters before asking.)")
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
