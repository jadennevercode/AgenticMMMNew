# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An **AI-Native Marketing Mix Modeling (MMM) platform**: a Workflow-style multi-agent
system (5 agents × 4 delivery stages) that runs the full MMM pipeline end-to-end on a
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
# .env holds only operational knobs (timeouts, paths) — copy from .env.example.
# LLM/ASR credentials (key, base URL, model) are entered once in the app's global
# Settings screen and stored in data/model_service.json (gitignored), shared by all
# projects. The seeded Danone case needs the LLM configured there before it runs.
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
  than fabricating input. The S2 data gate (2.1 Data Processing) carries `requiresMapping` **and**
  `requiresManifest`: it clears when the **FactorTree↔DataAssets mapping** is fully resolved —
  every active factor row is either supplied by ≥1 published coverage record or explicitly
  **ignored** (`ProjectState.factor_map_ignores`, rowId→note) — **OR** the legacy per-L3 manifest
  validates (slot-upload projects). `app/dataeng/mapping.py::resolve_factor_map` / `mapping_complete`
  derive per-row status (mapped/ignored/pending) from the coverage records publish attaches to
  factor rows; `engine.data_intake_ready` combines the two paths. When no factor tree exists it
  degrades to the `requiresUpload` file-presence check. Endpoints: `GET /factor-map`,
  `PUT /factor-map/ignore` (re-renders `a-data-processing`).

**The Factor Tree IS the indicator catalog.** An `Indicator` is a *projection* of an active
factor row (`app/dataeng/indicators.py`), never an entity the data manufactures. It exists the
moment the tree is confirmed — the Data Engine shows the collection target before the first
upload — and publishing only attaches an `IndicatorCoverage` ("this asset's metric supplies this
row", `service.claim_published_metrics`). Three rules:

- **Derive, don't store.** `ProjectState.indicators` is legacy, drained by `heal_state`
  (`_migrate_indicators_to_coverage` carries every `bound_by="human"` binding across — dropping
  those is the one irreversible failure here). Persisted state is `factor_tree` (the definition)
  + `indicator_coverage` (the supply). Same rule as the ledger, for the same reason: a stored
  copy eventually disagrees with the tree it was copied from.
- **A metric no factor asked for is an orphan** (`tree_row_id == ""`), listed apart and resolved
  by adoption into the tree (`source="data_upload"`, accepted on the spot — the S1 gates are
  long closed) or dismissal (`app/dataeng/orphans.py`). It is never presented as a project
  indicator; that is exactly what the old `treeGrounded=False` row did.
- **One row may be supplied by several sources** (TV spend split across two files); one
  published metric supplies at most one row, and at most one *human pin* per row represents it.

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
app/dataeng/indicators.py  the indicator catalog, DERIVED from the factor tree × coverage
app/dataeng/orphans.py     adopt a supplied-but-undeclared metric into the tree, or dismiss it
app/agents/sources.py  grounding resolver: uploaded Project-Folder files only (S1 has no fallback)
app/agents/validation_rules.py  S1 preliminary data checks (completeness/granularity/volatility/YoY)
app/domain/            models.py (Pydantic, mirror frontend types.ts) · blueprint.py (the DAG) ·
                       industries.py (L1–L3 industry taxonomy, mirrors lib/industries.ts)
app/store/state.py     ProjectState (+ profile / factor_tree) + ProjectStore (per-project JSON);
                       heal_state() back-fills new blueprint tasks onto saved projects
app/store/files.py     per-project Project Folder: real upload+storage+parse under
                       data/projects/{id}/files/{category}/ (+ _index.json)
app/store/templates.py editable per-industry Factor-Tree & Interview templates, seeded from
                       Assets/ workbooks (template_seed.py) under data/templates/
app/tools/             the analysis-tool registry: registry.py (8 ToolSpecs + thin `run`
                       wrappers) · tracing.py (`tool_run` / `traced` → ToolInvocation)
app/llm/volcano.py     Volcano Ark client + robust JSON parse/repair
```

**Tools — the S2 checks are registered, explicitly-called tools.** The four quality
dimensions (2.2), the three statistical tests (2.4) and the OLS fit (2.5/2.5r) are each a
registered `Tool` (`app/tools/registry.py`) rather than an anonymous helper. Two rules:

- The wrappers are **identity wrappers** over the existing implementations
  (`quality_scoring._*_subs`, `data_rules.reference_cv` / `vif_all`, `stat_scoring.pearson`,
  `mmm.engine.run_mmm`). Registering a computation must never change its numbers —
  `app/tools/_test_tools.py` asserts wrapper == direct call cell for cell, including the
  tool-composed 2.2 scorecard vs `score_quality`. If it fails, the tool layer has started
  doing arithmetic; revert rather than update the expectation.
- Every call goes through `tracing.traced` / `tool_run`, which records a `ToolInvocation`
  (args/result summary, status, real duration) onto `ProjectState.tool_invocations` and emits
  a `tool` event. Granularity is **one call per tool per task run** (batched over series),
  except `model.ols` which is one per model object. All tracing params (`eng`, `task_id`) are
  optional and default to untraced, so secondary paths (`ols_review._stat_index`, the
  `fit=False` setup pass) don't manufacture phantom invocations.

Each tool documents itself in the registry entry — `scenario` / `method` / `logic` / `params`
live next to the wrapper so the docs cannot drift from the code, and the **source is not
duplicated**: `registry.detail()` reads it off the live function with `inspect.getsource`.
Keep the catalog **flat** (no category grouping in the UI) — a tool may be called from several
steps and the category list is open-ended; `category` is a badge, not a hierarchy.

Endpoints: `GET /api/tools` (light catalog), `GET /api/tools/{toolId}` (full page + source),
`GET /api/projects/{id}/tool-invocations` (`?taskId=&toolId=`). Front end:
`components/tools/ToolsView.tsx` is the flat list, `ToolDetailView.tsx` the per-tool page
(Overview / Implementation / API / Trace tabs), and `ToolTrace.tsx` renders the per-step chips
inside each artifact's Build process — shown even when the step is collapsed, each linking
into its tool page.

**Data Engine — two execution paths, one compiler.** `dbt build` (real dbt Fusion binary on
DuckDB) is the **authoritative** path: it runs the quality tests and is what Publish gates on.
It is also a subprocess over the whole DAG, far too slow to answer "what does this step do to my
rows?" while someone edits. So the editor has a second, fast path:

- `dbt/compiler.py` compiles the step DAG **twice from the same per-step SQL templates** —
  `compile_pipeline()` → dbt models (`{{ ref }}`, enum maps as seeds); `compile_preview_sql()` →
  one self-contained `WITH` query (plain names, enum maps inlined as `VALUES`) covering only the
  target step's *ancestors*. Because both walk `_compile_step`, a preview cannot show a shape the
  build would not produce — `app/dataeng/_test_preview.py` asserts the two agree cell for cell.
- `duck.py::run_preview()` runs that query in the locked-down sandbox and profiles the result via
  DuckDB's own `SUMMARIZE` (+ value counts / histograms) → the stats the grid renders per column.
- `preview.py` is the orchestration (raw frames memoised per project/asset/source-set;
  `invalidate()` on source change). `POST .../pipeline/preview` carries the **in-editor**
  pipeline, so unsaved edits render immediately.
- `cluster.py` groups near-duplicate raw spellings with OpenRefine's key-collision method
  (fingerprint + n-gram fingerprint, merged transitively via union-find). It is a *proposal*:
  nothing enters the enum map until a human accepts a group. `POST .../pipeline/cluster-enum`.

Front end: `components/dataeng/grid/DataGrid.tsx` (TanStack Table + Virtual — sorting, filtering,
row windowing, profiled headers) is the one grid every surface uses. The transform screen is
**grid-first** — step rail · live preview · step inspector, with the React Flow DAG as a toggled
"Graph" view — and `usePipelinePreview.ts` re-runs the preview as you type (debounced, newest
response wins). Do not reintroduce hand-rolled `<table>` data views.

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

**S2 · Data Intake & Validation** (merged former "Data Intake & Quality" + "Validation &
Hypotheses"; stage ids are now s1, s2, s4, s5). Six artifacts, **fifteen tasks** — every artifact
is an AI-proposes → human-reviews → gate Process, not a single step:

```
2.1  Data Processing    (H)  a-data-processing  AI proposes a published indicator per unmatched
                                                factor; you accept / remap / ignore
2.2  Data Quality Score (A)  a-quality-scorecard  10 subchecks + AI 4-dimension scoring
2.2d Review verdicts    (H)  panel:quality-review   → d-2.2
2.3  Business Validation(C)  a-business-validation  per-L3 charts vs sell-out
2.3a Explain anomalies  (A)  panel:anomaly-review   AI hypothesis + handling per anomaly
2.3s Client sign-off    (H)                         → d-2.3
2.4  Statistical Score  (A)  a-stat-tests           CV/Pearson/VIF + AI per-row case
2.4d Review verdicts    (H)  panel:stat-review      → d-2.4
2.5  OLS per channel×product (M) a-ols-test        N×M fits, every surviving variable in each
2.5d Review range verdicts (H) panel:ols-factor-tree accept/reject per fitted factor vs its KB
                                                    band; saving re-fits → d-2.5
2.6  Assemble master    (M)  a-master-data          adopted indicators → feature wide table
2.6d Lock master data   (H)                         → d-2.6   (`3.1` depends on `2.6d`)
```

**The indicator lifecycle ledger (`app/agents/ledger.py`) is S2's spine.** Six layers rule in
order — mapping (2.1) → quality (2.2d) → signoff (2.3) → statistical (2.4d) → selection (2.5)
→ range (2.5d) — and **a rejection at any layer is inherited by every later one**: the indicator
is not re-scored, not re-offered, and never reaches the model. The ledger stores nothing; it
*derives* each indicator's fate from the layers' own records (the three scorecards, the
sign-offs and `ols_config`), so it cannot disagree with them. Two rules matter:

- `model_selection(st) -> ModelSelection{exclude, include, y, params}` is the **one** resolved
  selection every downstream fit must use — `2.5r`, `2.6` **and `3.2` training**. Re-deriving it
  at a call site is exactly how S4 came to train on unfiltered data.
- `drops_before(st, layer)` gives a layer everything earlier layers rejected — never hand-union
  drop sets (a layer must inherit every earlier verdict and never its own).

Indicator keys are `(norm_l4, norm_metric)` — `build_model_frame`'s own key space.

**The `range` layer is a stored scorecard, not a re-derivation** (`app/agents/ols_scorecard.py`,
`ProjectState.ols_scorecard`). 2.5 proposes accept/reject per fitted factor from the KB band
plus the benchmark review; 2.5d is where a human changes any of it. Three rules:

- **`decided_by="human"` pins a row against every later re-fit.** The recommendation keeps being
  recomputed and shown; the human's verdict is what rules. Overwriting it on refresh silently
  reverts the reviewer.
- **A rejected row is carried forward even though the new fit no longer mentions it** — it was
  excluded, so it cannot appear. Dropping rows the tree stops mentioning deletes the very
  verdict that removed them. This is also why `d-2.5` no longer has to **freeze** its drops
  onto its own resolution (`ledger.freeze_range_drops` survives only for projects resolved
  before the scorecard existed): a stored verdict persists because it was written down.
- **`apply_ols_config` re-fits to a fixed point.** The fit runs on the selection as it stood and
  the sheet is derived *from that fit*, so a newly out-of-range factor is rejected only after
  the model containing it was rendered. One pass leaves the artifact showing a model its own
  verdicts reject; it settles in one extra pass (`_SETTLE_REFITS` is a backstop).

`2.3a` handlings actually bite (`ledger.anomaly_effects`): accepted `event` → a dummy control over
the window, `cap` → the response is winsorized there, `raw` → a caveat only. Pending/rejected
cards do nothing. (This replaced `ai-2.3`, which recorded a choice nothing ever read.)

`a-master-data` is format `masterData`: the artifact carries the funnel + dimensions + every
indicator's verdict chain; the wide table itself is queried live per product × channel × region
(`POST /master-data/table`, `app/agents/master_data.py`) against the 2.24 long-table schema.
Endpoints: `GET /indicator-ledger`, `PUT /anomaly-review`, `PUT /factor-map/bind`.

**`master_data.adopted_indicators(st)` is the one answer to "what is the model built on".**
The granularity reference, the Data Station, the export and 2.6's factor-tree close-out all
ask that question, and they used to answer it three different ways (7 / 5 / 8 on the drill
case). Two rules, each a fixed bug:

- **The response is part of the model input.** No layer rules on Y — the drivers explain it —
  so it has no ledger row, and every surface that filtered on the ledger silently dropped it.
  The exported 2.32 "model input" shipped without its dependent variable.
- **A national row belongs to every model, so it follows the model that kept it.** Screening
  rows with no channel against the *union* of every object's excludes reads as the safe
  direction and is not: TT was fitted with 温度 at 43% contribution while the master table
  deleted it because MT and EC had rejected it. `adopted_mask(..., scope=[obj])` narrows it,
  and each per-object export sheet selects rows with `model_objects.object_mask` — the same
  predicate the **fit** uses. Slicing by brand + channel_type instead looks equivalent and
  drops exactly the shared national and competitor rows the model is fitted on.

The per-factor industry ROI/contribution ranges are meant to be maintained in Knowledge; today
they load from the reference rule library (`data_rules.match_factor_range`). See
`docs/agent-design/02-data-agent.md` for the original design (pre-merge task ids 2.0a–2.34).

**S2 scores and fits the assembled data — nothing is aggregated first (2026-07-27).** This
replaced the 2026-07-23 "national TOTAL" roll-up, which collapsed channel, product and region
into one series *before* 2.2, 2.4 and the OLS ever saw the data. Three consequences, and each
is the reason for a rule:

- **Nothing is required to have a channel.** A row with a blank `channel_type` is
  *national* — media bought once for the country — and is shared into **every**
  model object, exactly as a brand no product model can claim is. Requiring a
  channel is what made per-channel modeling delete national media: on the synthetic
  case every model went from 17 drivers to 6.
- **A model object is one `(channel_type, brand)` cell** — `app/agents/model_objects.py`,
  id `"MT::MIZONE"`, label `"MT · MIZONE"`. N channels × M products = N×M models. A cell
  qualifies only if it carries **both** a response and a driver; cells with a response but no
  drivers (a competitor's sell-out) are reported by `skipped_objects`, never modeled. A brand
  that carries no response is *market context*: its rows are **shared into every product's
  model in that channel**, because competitor spend drives all of them and belongs to none.
  The id is opaque everywhere downstream (`ModelSelection`, `OlsConfig`, the `olsTree` body,
  React) — only `pivot._resolve_object_filter` parses it. It contains `::`, so
  `ledger._parse_signoff_key` splits on the **last** colon.
- **2.2 scores the published rows; 2.4 scores a panel.** 2.2's granularity/caliber/completeness
  subchecks were literally unable to fail under the roll-up (one source, one region, one
  channel, NaNs dropped while summing). 2.4 stacks one row per `(model object, month)` — YoY
  differencing runs **within** each object (`_panel_yoy`), never down the stack. Both now record
  **one row per indicator** under `OBJECT_ANY`: an indicator is judged once, on all the evidence,
  and every model inherits the verdict. Region and L5–L8 still roll up *inside* a cell with that
  indicator's 2.1 aggregation — indicators disagree about how deep they report, so a panel keyed
  on them would leave two indicators sharing no rows and correlate them on nothing.
- **2.5 has no indicator search.** The per-L4 coordinate descent (寻优, up to 96 trial fits,
  keeping whichever assignment landed the most factors in a Knowledge band) is gone: a benchmark
  is compared against, never tuned towards. Every surviving variable enters its model at once.
  The **only** thing that holds one out is `ols_review.affordable_drivers` — the identifiability
  limit `n_months - controls - 1 - MIN_RESIDUAL_DF`, since OLS with p ≥ n has no solution at
  all. The surplus is left unticked, ranked by |r| with Y, labelled a degrees-of-freedom limit
  rather than a verdict, and reported as a finding. `app/agents/ols_summary.py` then has the AI
  summarise each fitted model; its `keyDrivers` list is **computed** (significant drivers by
  contribution) and the LLM explains that list rather than choosing it.

**The Factor Tree is S2's spine, and `app/agents/factor_link.py` is what makes that true.**
Business Understanding's tree declares what to collect; the data delivers metrics under
whatever label the source file used. Those two key spaces — `(l4, indicator)` and
`(l4, metric)` — had nothing joining them, so on the reference case 123 factor rows the
human had *ignored* at 2.1 matched **zero** data keys: `drops_before` was a filter that
never filtered, and a factor you rejected went on being scored, screened and fitted. The
join already existed unread in `IndicatorCoverage` (publish records metric → factor row).
Rules:

- **Key through `factor_link`, never by name.** `row_for(l4, metric)` gives the factor a
  data indicator supplies (`""` = orphan — real data the tree never asked for, which 2.2
  still scores and the Data Engine offers to adopt). `ignored_data_keys(st)` translates a
  factor-level rejection into the space the later layers filter on.
- **An explicit 2.1 ignore outranks the automatic mapping** (`mapping.resolve_factor_map`).
  The other way round, a factor *with* data could not be rejected at 2.1 at all — the
  ignore was only reachable for rows nothing supplied, so "leave this out" evaporated the
  moment an asset covered it.
- **Every scorecard row carries `treeRowId`** (2.2 `QualityRow`, 2.4 `StatScoreRow`), so
  the chain is inspectable rather than inferred.
- **2.6 closes the tree out**: `factor_tree_verdicts(st)` emits *every* active factor row
  with `adopted | partial | rejected | notModeled | notSupplied`, the **earliest** stage
  that rejected it, and the per-object breakdown when models disagree. `notSupplied`
  (no data ever arrived) is deliberately distinct from `rejected` (someone judged it),
  and the response is `adopted` with `role="response"` — it has no ledger row because it
  is never a *driver*, and without that it read as "no data supplies this factor" for the
  one factor the model is built on.

**`scripts/make_synthetic_case.py` is the "does this work on someone else's data" test.**
It seeds project `aurelia-skincare`: skincare not beverage, English taxonomy whose L1
labels are none of `KPI / MARKETING FACTOR / COMMERCIAL FACTOR`, roles carried only by
the documented `metric_type ∈ {Y, spending, X}` contract, 2 products × 4 channels ×
36 months, national media with no channel, a competitor brand with no response, a
known contribution per driver (so a fit can be *checked*, not just run), and a real
2023 supply disruption for 2.3/2.3a. The reference case cannot test any of this —
every default in the codebase was written against it. Run it before believing S2
works. It has already caught, in one pass: national media deleted by the channel
filter; the AI review zeroing every indicator off an *advisory* subcheck; a Danone
ROI band applied to skincare; the anomaly detector summing °C into RMB; and 2.4's
panel correlations attenuated to nothing by cross-sectional scale.

**Per-project modeling (Y/X tagging).** `data_binding._metric_type` tags each bound metric:
`Y` (本品销量/KPI — the response), `spending` (花费/spend — ROI-eligible X), else `X`. The OLS
engine (`mmm/pivot.py`) is now `metric_type`-aware — `_is_y_row` accepts an explicit `Y` tag and
X-driver selection accepts `{x,driver,spending,spend}` tags, in addition to the reference taxonomy
(`l1` = KPI / MARKETING FACTOR / COMMERCIAL FACTOR). `build_model_frame` caps drivers at
`MAX_DRIVERS=12` (most Y-correlated) to keep the OLS identified (p<n) on wide per-project uploads
— but only on the legacy auto-select path: once 2.5 passes an explicit `include`, the human's
selection wins and `ols_review.affordable_drivers` is what bounds it.
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

- **Grounding material is budgeted once, and truncation is loud.** `Settings.grounding_max_chars`
  (default 100k, `.env`-overridable) replaces the dozen hardcoded `[:6000]`/`9000`/`12000` slices
  S1 used to apply silently — a 200-page deck and its first six thousand characters produced
  indistinguishable deliverables. Clip through `agents.common.clip()` and emit
  `truncation_finding()` when anything is dropped; never reintroduce a bare slice on grounding
  text. Display limits (`evidence[:200]`, `title[:120]`) are not grounding and stay as they are.
- **Backend numbers come from `app/mmm`**, not the LLM. The assistant/report prompts are
  explicitly told the computed `MODEL RESULTS` line is authoritative; keep it that way — don't
  let narrative agents invent metrics.
- **G4 model selection never auto-picks a model silently** in the product design (presents
  Pareto candidates); honor this when touching the model agent / gates.
- Model-service secrets (LLM/ASR API keys) live only in the global model config the user
  enters in Settings, persisted plaintext to `data/model_service.json` (gitignored, one for
  all projects — see `app/store/model_service.py`). `backend/.env` holds no credentials.
  `get_llm()` / `get_asr()` resolve from that global config; there is no per-project or
  env-var-name model config anymore. Never commit `data/model_service.json`.
- `docs/agent-design/` holds the per-agent design specs (00–08) — the product spec behind the
  blueprint. Read these before changing agent behavior or the task matrix.
