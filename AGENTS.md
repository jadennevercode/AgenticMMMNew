# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this is

An **AI-Native Marketing Mix Modeling (MMM) platform**: a Workflow-style multi-agent
system (5 agents × 5 delivery stages) that runs the full MMM pipeline end-to-end on a
real client case (Danone China Mizone), with human-in-the-loop (HITL) quality gates.

Two halves, one product:

- `backend/` — **real** Python/FastAPI engine: ingests the actual reference files, runs a
  dependency-light OLS MMM (adstock + Hill saturation + regression), and uses the Volcano
  Ark LLM (`ark-code-latest`, OpenAI-compatible) for the cognitive/narrative agent steps.
  **No mock data.**
- `frontend/` — React 19 + Vite + TypeScript Mission Control UI. Originally a self-contained
  mock prototype (`useSimStore` tick engine); now backend-driven — the store polls the
  FastAPI `/api/state` and renders live workflow state.

The `frontend/README.md` still describes the original in-browser mock prototype. The mock
tick-engine has been replaced by `src/api/client.ts` + a polling store; treat the backend as
the source of truth for runtime content.

## Commands

### Backend (`backend/`)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# .env holds VOLCANO_API_KEY etc. (gitignored) — copy from .env.example
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Drive a full autopilot run on the real case (~8 min; LLM latency dominates). The
API is multi-project: routes are scoped to `/api/projects/{id}/...`. The Danone
case seeds as project id `danone-mizone`.

```bash
curl localhost:8000/api/projects                       # registry (list)
P=danone-mizone
curl -XPOST localhost:8000/api/projects/$P/reset
curl -XPOST localhost:8000/api/projects/$P/run -H 'content-type: application/json' -d '{"autopilot":true}'
curl localhost:8000/api/projects/$P/run/status         # poll
curl localhost:8000/api/projects/$P/state              # full project state (camelCase, matches frontend types)

# Create a new project (industry codes from app/domain/industries.py):
curl -XPOST localhost:8000/api/projects -H 'content-type: application/json' \
  -d '{"name":"Acme Q3","brand":"Acme","industry":{"l1":"beauty","l2":"skincare","l3":"sunscreen"}}'
```

Tests (no pytest harness — these are runnable scripts):

```bash
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py   # control-flow smoke test
.venv/bin/python -m app.mmm._test_synthetic             # OLS correctness on known data
.venv/bin/python -m app.mmm._test_real                  # MMM on the real dataset
.venv/bin/python -m app.ingest._smoke                   # all real-data loaders
```

### Frontend (`frontend/`)

```bash
npm install
npm run dev      # http://localhost:5173 (reads VITE_API_BASE, default http://localhost:8000)
npm run build    # tsc -b && vite build
npm run lint     # eslint
node scripts/visual-check.mjs   # Playwright E2E walk-through (needs a running dev server)
```

## Architecture

### The workflow is configuration; the content is computed

The MMM workflow itself — task DAG, dependencies, human gates, decision option sets — is a
**fixed product blueprint**, defined twice in parallel and kept in sync:

- `backend/app/domain/blueprint.py` — `STAGES`, `AGENTS`, `ARTIFACTS`, `TASKS` (the
  authoritative server-side blueprint; ported from the frontend scenario).
- `frontend/src/lib/scenario.ts` + `artifacts-data.ts` — the original frontend definitions.

Artifact **content** and decision **recommendations** are NEVER hardcoded — they are produced
at runtime by real computation (deterministic) or grounded LLM calls. When changing workflow
structure (tasks, deps, gates), update the blueprint, not the agent handlers.

### Task classes (`klass`)

Each task has a collaboration/execution class that determines who runs it:

- **M** (Delegate / mechanical) — deterministic computation (ETL, OLS fit, scorecards).
- **A / C** (Augment / Assist) — an LLM call grounded in real artifacts (narratives, KBQs).
- **H** (HITL) — human upload assignments or decision gates. The UI runs **interactive by
  default** (`autopilot=false`): the run loop drives the automated M/A/C tasks but **stops at
  every upload and decision node**, and each human action (submit/resolve) auto-advances to
  the next gate. An **Autopilot** toggle (header) flips to `autopilot=true`, which auto-resolves
  decisions and auto-submits uploads to drive the whole case end-to-end. In **either** mode the
  S1 upload gates (1.0a / 1.1a / 1.4a) carry `requiresUpload` and block until real parsed files
  exist in their Project-Folder category (no reference fallback) — autopilot skips them rather
  than fabricating input. The S2 data gate (2.0a) carries `requiresUpload` **and**
  `requiresManifest`: it blocks until the data-request manifest reports every L3 slot validated
  (per-L3 coverage against the factor tree, not just any file). When no manifest exists (no factor
  tree) it degrades to the `requiresUpload` file-presence check.

### Backend execution flow

```
app/main.py            FastAPI REST API (CORS-locked to localhost:5173)
  └─ build_engine()    registry.py wires each producing task id → its handler
app/orchestrator/
  engine.py            DAG engine: next_actionable() → run_task() → produce artifacts,
                       emit events, add findings/proposals/insights; resolve_* for HITL
  runner.py            run_until_blocked(): the autopilot loop — generates LLM decision
                       recommendations, auto-submits uploads, auto-resolves gates, steps tasks
app/agents/            per-task handlers, grouped by agent:
                       business.py · data.py · model.py · report.py · uploads.py
                       (common.py = shared LLM prompt/grounding helpers; registry.py = wiring)
app/mmm/               OLS MMM engine: transforms (adstock/Hill) · ols · pivot · engine
app/ingest/            real reference-data parsers (xlsx/xlsm/docx): dataset, factor_tree,
                       business, interviews, data_dictionary, validation, reference ·
                       extract.py = generic uploaded-file extractor (pdf/pptx/docx/xlsx/csv)
app/agents/sources.py  grounding resolver: prefer uploaded Project-Folder files, else reference
app/agents/validation_rules.py  S1 preliminary data checks (completeness/granularity/volatility/YoY)
app/domain/            models.py (Pydantic, mirror frontend types.ts) · blueprint.py (the DAG) ·
                       industries.py (L1–L3 industry taxonomy, mirrors lib/industries.ts)
app/store/state.py     ProjectState (+ profile / factor_tree) + ProjectStore (per-project JSON);
                       heal_state() back-fills new blueprint tasks onto saved projects
app/store/files.py     per-project Project Folder: real upload+storage+parse under
                       data/projects/{id}/files/{category}/ (+ _index.json)
app/store/templates.py editable per-industry Factor-Tree & Interview templates, seeded from
                       Assets/ workbooks (template_seed.py) under data/templates/
app/llm/volcano.py     Volcano Ark client + robust JSON parse/repair
```

**Business Understanding (S1) deepening.** The S1 stage is document-grounded and editable:
the **Project Folder** (bottom-right dock) stores real uploads by category; S1 agents ground
**strictly on the user's uploaded files** for their category — **no Danone-reference fallback**.
The upstream upload gate blocks (`requiresUpload`) until real parsed files exist, so a producing
S1 handler always has genuine input; with nothing uploaded the deliverable is not produced. (The
seeded `danone-mizone` case therefore needs its SOW/materials/minutes uploaded before S1 will
run.) `ProjectProfile` (parsed intro + time granularity +
model-scope matrix) and `FactorTree` (per-node template/AI/interview rows with accept/reject
`status`) live on `ProjectState` and are edited via `PUT /profile` and `PUT /factor-tree`
(re-rendering `a-scope` / `a-factor-tree`). New S1 tasks: `1.5v` preliminary validation
(`a-data-validation`) and `1.7` BU summary (`a-bu-summary`). Knowledge templates are editable
per-industry and CRUD'd at `/api/templates`. Every S1 deliverable is exportable
(`lib/export.ts`: sheets→.xlsx via lazy SheetJS, others→.md). When changing S1, keep the four
contracts in sync: `blueprint.py`/`scenario.ts`, `models.py`/`types.ts`.

**Multi-project.** Each project is an isolated `ProjectState` blackboard with its own JSON file
and its own run guard (`_runs[project_id]`); projects can run concurrently. The registry
(`/api/projects`) lists project metadata (`ProjectMeta`: name, brand, industry L1–L3). New
projects are created from the landing page; the Danone case seeds as `danone-mizone` (migrated
from a legacy `data/project_state.json` on first run). `/api/projects/{id}/run` launches the
runner as a background `asyncio` task; state is saved to JSON after each step and human action.

**Per-project data binding (S2).** `app/agents/data_binding.py` parses the project's slot-bound
data uploads (one workbook per L3, one sheet per L4, granularity columns + indicator columns) into
the unified long table (the 2.21 schema). `app/agents/dataset_cache.py::model_df(st)` returns that
per-project table when bindable data exists, else falls back to the Danone **reference** dataset —
so the seeded demo and any project without uploads keep working. The cache is per-project and
invalidated on data upload (`invalidate_project`). All S2–S5 data/model handlers take `st` and
resolve via `model_df(st)` / `model_objects(st)`.

**S2 is artifact-driven** (segments delimited by their output artifact): 2.1 Validation (2.11
validation standard → 2.12 quality score), 2.2 Process (2.21 wide-table schema → 2.22 processing
logic → 2.23 data dictionary → 2.24 master dataset), 2.3 Cross-Validation (2.31 business rules &
drill → 2.32 data review + client Q&A → 2.33 statistical screening → 2.34 indicator selection).
Each Input-standard and Output-deliverable is its own task/artifact; see `docs/agent-design/02-data-agent.md`.

**Per-project modeling (Y/X tagging).** `data_binding._metric_type` tags each bound metric:
`Y` (本品销量/KPI — the response), `spending` (花费/spend — ROI-eligible X), else `X`. The OLS
engine (`mmm/pivot.py`) is now `metric_type`-aware — `_is_y_row` accepts an explicit `Y` tag and
X-driver selection accepts `{x,driver,spending,spend}` tags, in addition to the reference taxonomy
(`l1` = KPI / MARKETING FACTOR / COMMERCIAL FACTOR). `build_model_frame` caps drivers at
`MAX_DRIVERS=12` (most Y-correlated) to keep the OLS identified (p<n) on wide per-project uploads.
The data-request **export template carries no KPI** (Y is the dependent variable, not a factor), so
uploaded data must include a `本品销量`-type metric for S3–S5 to fit; `make_sample_uploads.py` emits a
`KPI_本品销量.xlsx` workbook (Y correlated with drivers via a shared seasonal signal) for this.

**Constraint:** the reference loaders are Danone-specific (one `REFERENCE_DIR`). When per-project
uploads lack a usable Y/time axis the binding returns `None` and the reference fallback applies.

### Frontend ↔ backend contract

The backend serializes Pydantic models **`by_alias=True`** so JSON is camelCase and matches
`frontend/src/lib/types.ts` exactly. `src/api/client.ts` is the single API surface; the Zustand
store (`src/store/useSimStore.ts`) holds an `activeProjectId`, hydrates via
`loadProject(id)`, then polls `/api/projects/{id}/state` until the run completes. The landing
page (`components/projects/`) lists the registry and creates projects. When you change a domain
model field, update both `domain/models.py` and `lib/types.ts`.

### Real reference data

`reference/` (gitignored — large cloud-synced binaries: the 23.8k-row Danone modeling dataset,
factor tree, KBQs, validation rules, data dictionary, 12 interview transcripts) is the real case
the pipeline runs on. Path is configurable via `REFERENCE_DIR` in `backend/.env`. If
`reference/` is absent, the ingest loaders and real-data tests will fail.

## Conventions

- **Backend numbers come from `app/mmm`**, not the LLM. The assistant/report prompts are
  explicitly told the computed `MODEL RESULTS` line is authoritative; keep it that way — don't
  let narrative agents invent metrics.
- **G4 model selection never auto-picks a model silently** in the product design (presents
  Pareto candidates); honor this when touching the model agent / gates.
- Secrets live only in `backend/.env` (`VOLCANO_API_KEY`). Rotate periodically; never commit.
- `docs/agent-design/` holds the per-agent design specs (00–08) — the product spec behind the
  blueprint. Read these before changing agent behavior or the task matrix.
