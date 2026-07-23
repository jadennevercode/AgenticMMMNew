# Design: Per-Channel-Type Screening + Data Intake & Validation Optimization

**Date:** 2026-07-22
**Status:** Approved (pending implementation plan)
**Scope:** S2 (Data Intake & Validation), the OLS/ledger spine, MasterData (2.6), the shared FactorTree canvas, and the channel/factor dynamic-source cleanup.

---

## 1. Problem statement

Four defects in the Data Intake & Validation experience:

1. **FactorTree canvases are inconsistent.** Seven surfaces render the factor hierarchy; only two
   (the S1 `a-factor-tree` editor and the Knowledge-pack template editor) lay it out as true
   horizontal `L1 | L2 | L3 | L4 | Indicator` columns. The shared `FactorTreeCanvas` (used by 2.1
   / 2.2 / 2.4) and three other surfaces (OLS tree, 2.3 Business Validation, Indicator Catalog)
   each hand-roll a different `L1 › L2 › L3` breadcrumb pattern. Display language is inconsistent
   in chrome across surfaces.

2. **Indicator screening is pooled across channels.** Models are *already* fit one-per
   `channel_type` (`run_all_objects` over `dataset_cache.model_objects`), but the entire screening
   chain — data quality (2.2), statistical tests (2.4), sign-off (2.3), X selection (2.5x), range
   (2.5r) — is a **single global decision** keyed by `(l4, metric)`. Only the Y metric is
   per-object. A metric that is unusable in TT but fine in MT is dropped or kept for *all*
   channels together.

3. **Channel / factor lists are partly hardcoded.** Channel *coverage* is dynamic (from the data's
   `channel_type` column), but the channel *ordering* preference, the Y/X/spend classification
   keyword banks, the L1 taxonomy labels, and interview role tokens are hardcoded; and the
   industry ROI/contribution ranges still fall back to a reference JSON library rather than being
   sourced from Knowledge.

4. **MasterData is a single crowded page.** No tabs; the live wide feature table can be viewed but
   not exported (export falls back to Markdown without the table); the full per-layer verdict
   chain exists in the payload but is not shown grouped by factor tree.

### Confirmed intent (from user)

- **Each Channel Type is its own model group; data slicing AND indicator screening run
  independently per Channel Type.** The set of surviving indicators may differ across Channel
  Types, and that difference must propagate into how MasterData is assembled.
- **The frontend needs a Channel Type selector/filter**, and that selector must be **dynamically
  populated from the data** (never a hardcoded channel list).

---

## 2. Core design decision: widen the ledger key space

Today the S2 ledger — the spine that derives every indicator's fate — is keyed by
`(norm_l4, norm_metric)` globally. We widen it to **`(object, norm_l4, norm_metric)`**, where
`object` is the Channel Type (the existing `dataset_cache.model_objects` identity: MT / TT / AFH /
EC / O2O / WS / 社区团购 / …, dynamic from data).

The six filter layers re-anchor as follows:

| # | Layer | Task | Keying after change | Rationale |
|---|-------|------|---------------------|-----------|
| 1 | mapping | 2.1 | **Global** | Indicator↔DataAsset mapping is channel-independent; unmapped = no data anywhere. |
| 2 | quality | 2.2d | **Per Channel Type** | Completeness / volatility / granularity are computed on each channel's own slice. |
| 3 | signoff | 2.3 | **Per Channel Type, default-all** | Business validation charts gain a channel dimension; a human sign-off applies to all channels by default, overridable per channel — keeps human effort from scaling ×N. |
| 4 | statistical | 2.4d | **Per Channel Type** | CV / Pearson / VIF must run against each channel's own Y. |
| 5 | selection | 2.5x | **Per Channel Type** | Independent X ticking per channel. |
| 6 | range | 2.5r | **Per Channel Type** | ROI / contribution judged against each channel's own fit, not a cross-channel average. |

The inheritance rule ("a rejection at any layer is inherited by every later layer") now runs
**independently inside each Channel Type**. Mapping (layer 1) is the one shared gate: a mapping
rejection is inherited by all channels.

### Object identity

`object` remains `channel_type` (the current "model object" string). We do **not** split down to
the finer `channel` column — that was explicitly out of scope (sample sizes would collapse and the
OLS would become underdetermined). `dataset_cache.model_objects` stays the single source of the
object list; the hardcoded preferred-ordering list is replaced by a data-derived ordering
(Phase 3).

---

## 3. Backend changes

### 3.1 Ledger (`app/agents/ledger.py`) — the heart

- `ModelSelection` (`:108-122`): `include` and `exclude` become **`dict[object, frozenset[...]]`**
  (mirroring the existing per-object `y: dict[str, str]`). Add `include_for(obj)`,
  `exclude_for(obj)` accessors alongside the existing `y_for(obj)`.
- `model_selection(st)` (`:558-594`): derive per-object include/exclude sets from the per-object
  scorecards, sign-offs, `ols_config`, and the d-2.5 resolution.
- `indicator_ledger(st)` (`:418-547`): return per-`(object, l4, metric)` `LedgerRow`s. Each row's
  `verdicts` chain is derived from that object's own layer records.
- `drops_before(st, layer, object)`: add the object parameter; still forbids a layer from
  inheriting its own verdict — but now scoped to one channel.
- `funnel(st)` (`:623-642`): funnel counts become per-object (drives the per-channel MasterData
  funnel and the "which channels survived" matrix).
- Sign-off key scheme (`i:<l4>|<metric>`, `:148-158`): extend to carry the object, with a
  **default-all sentinel** so a single sign-off applies to every channel unless a per-channel
  override exists.
- **Mapping layer stays global** — its key remains `(l4, metric)`; the object dimension is applied
  only from layer 2 onward.

### 3.2 OLS proposal & review (`app/agents/ols_review.py`, `app/domain/models.py`)

- `OlsXCandidate` (`models.py:535-556`): add an `object` field (Y already has one via `OlsYChoice`).
- `build_ols_proposal` (`:164-192`): remove the cross-object `seen` dedupe (`:167-169`); build a
  per-`(obj, l4, metric)` candidate list with per-channel stats.
- `selected_x_metrics` (`:223-227`): return a **per-object map** instead of one flat `frozenset`.
- `_collect_records` (`:306`): key records by `(object, l4, metric)`; `_row_from_record` /
  `_nan_mean` (`:346-371`) stop averaging ROI/contribution across channels and report per channel.

### 3.3 Quality & statistical scorecards

- `quality_scoring` (2.2) and `stat_scoring` (2.4) run **once per model object** against that
  object's data slice. The Tool-registry wrappers stay **identity wrappers** (per
  `tools-registry` invariant) — they are simply invoked per channel and each invocation records
  its own `ToolInvocation`. Extend `app/tools/_test_tools.py` to assert per-object wrapper ==
  direct-call parity.

### 3.4 MMM engine / pivot — no granularity change

`build_model_frame`, `run_mmm`, `run_all_objects` already operate per object and take per-call
`include`/`exclude`. No change to model granularity; they now receive per-object selection via
`sel.include_for(obj)` / `sel.exclude_for(obj)`. `model.train_models` (S4 3.2, `model.py:45-47`)
switches to the per-object accessors — this closes the "S4 trains on unfiltered data" class of bug
at the per-channel level.

### 3.5 MasterData assembly (`app/agents/master_data.py`, `app/agents/data.py`)

- `adopted_mask` (`master_data.py:67-85`) becomes per-object: when the wide table is sliced to a
  Channel Type, its column set is exactly **that channel's surviving indicators** (different
  channels → different columns).
- `master_table` (`:111-196`) already accepts `channelType` — now the adopted-indicator set it
  pivots is object-scoped, not global.
- **New export endpoint** `GET /api/projects/{id}/master-data/export` — generates a full xlsx from
  the current filter (not subject to the 400×60 display cap); single channel → one sheet, multiple
  channels → one sheet per Channel Type.
- `assemble_master_data` (`data.py:974-1035`): serialize `verdicts` for **adopted** rows too
  (today only `rejected` rows carry the chain, `:1008-1015`); serialize `funnel`, `adopted`, and
  `rejected` **per object** so the frontend can render the per-channel decision matrix.

### 3.6 State migration (`heal_state`)

Old archived projects hold **global** verdicts (quality drops, sign-offs, 2.5x ticks, d-2.5
freeze). `heal_state` expands each global record into a per-object record applied to **all** current
channels, so legacy projects behave identically after the upgrade.

---

## 4. Frontend changes

### 4.1 Unified horizontal FactorTree canvas

Rework `FactorTreeCanvas.tsx` to a true **`L1 | L2 | L3 | L4 | Indicator | …ext cols | Status |
Action`** horizontal-column layout (same-level values merged/blanked vertically), keeping the
collapse behavior, tone/chip system, and consumer-injected extension columns. Wrap in an
`overflow-x: auto` container (wide tables must scroll inside their own box, never the page).

Migrate consumers to the shared canvas:
- Keep, refactor row-construction only: `DataProcessingCanvas`, `QualityCanvas`, `StatCanvas`.
- Move onto the shared canvas: `OlsTreeView`, the sign-off list inside `BusinessValidationView`
  (its charts stay), `IndicatorCatalogPanel`.

**Display language consistency:** all canvas chrome is English (fixed `L1/L2/L3/L4/Indicator`
headers, one shared status-word constant table). Data values (Chinese factor names) render
verbatim — consistent with the product-english-only constraint (chrome English, data as-is).

### 4.2 Channel Type filter — dynamic, data-driven (NEW requirement)

A **Channel Type selector** is a first-class control on every per-channel S2 surface (2.2d review,
2.4d review, 2.5x/2.5r OLS, MasterData). Requirements:

- **Options are populated dynamically from the data** — from `dataset_cache.model_objects(st)` /
  the artifact's `objects` list — never a hardcoded channel array. New/unknown-industry channels
  appear automatically; channels absent from the project never appear.
- Selector offers **each Channel Type + an "All channels" aggregate view** (aggregate shows a
  union / per-channel-status summary).
- Selecting a Channel Type re-scopes the canvas to that channel's own screening state. Row actions
  (Drop, tick) default to the **current channel**, with an explicit "apply to all channels" bulk
  action to contain human effort.
- Selection is **URL state** (search param) so a channel view is shareable and survives poll churn.

### 4.3 OLS surfaces (2.5)

`OlsTreeView` and the 2.5x tick panel group by Channel Type (tabs driven by the selector above).
2.5r shows each channel's own ROI/contribution range verdicts (no cross-channel averaging).

### 4.4 MasterData — two tabs

- **Tab 1 "Data":** dimension Filter (incl. the dynamic Channel Type selector) + wide detail table
  + **Export** (calls the new export endpoint). The object cards / funnel move out of this tab.
- **Tab 2 "Factor Tree":** the unified horizontal canvas rendering the **full** factor tree; each
  indicator row is followed by **one status chip per Channel Type** (Accepted / Rejected@layer /
  Pending). Clicking a chip expands that channel's per-layer verdict chain + reason — one screen to
  see "which channels this indicator survived in." Built on the per-object `adopted` / `rejected`
  payload from §3.5.

### 4.5 Contract sync

`domain/models.py` ↔ `lib/types.ts` (OlsXCandidate.object, per-object ModelSelection/masterData
payloads); `blueprint.py` ↔ `scenario.ts` if any task option sets change.

---

## 5. Dynamic-source cleanup (Phase 3)

- Delete the hardcoded channel ordering (`dataset_cache.py:150`); order by in-data spend/row-count,
  optionally overridable by a Knowledge `rules` template.
- Externalize the Y/X/spend keyword banks and L1 taxonomy labels (`pivot.py:56-68,132,146`) so a
  Knowledge `factor_tree` / `rules` template can override them; the reference constants degrade to a
  no-template fallback. Explicit per-project `metric_type` tags keep priority. Add a byte-for-byte
  fallback-parity test.
- Route all `match_factor_range` / `factor_ranges` callers through `build_range_index`
  (`data_rules.py:412-454`) — Knowledge-first, reference-fallback.
- Read interview role tokens (`interviews.py:19-22`) from the interview Knowledge template.

---

## 6. Risks

- **HIGH — S2 spine key-space rewrite.** Widening the ledger key touches `ledger.py`, both
  scorecards, the sign-off key scheme, d-2.5 freeze, and the `models.py`/`types.ts` contract. The
  entire S2 regression surface is in play. Acceptance = migration tests + a full end-to-end Danone
  case run green.
- **HIGH — human review effort ×channels.** Mitigated by "default-all sign-off + per-channel
  override" and "Drop defaults to current channel + apply-to-all bulk action."
- **MEDIUM — smaller per-channel slices** may need per-channel threshold calibration for 2.2/2.4;
  start with existing thresholds and observe the e2e output.
- **MEDIUM — canvas migration** (esp. Business Validation sign-off interaction) has a broad
  regression surface; column-width/overflow handling for many indicators × extension columns.
- **LOW — keyword-bank externalization** must be behavior-identical when no template exists
  (parity test).

---

## 7. Phases & order

Execution order: **Phase 2 → Phase 1 → Phase 4 → Phase 3.** Phase 2 is the semantic core (~half the
work) and produces the per-channel data that Phases 1/4 render.

| Phase | Content | Complexity | Depends on |
|-------|---------|------------|------------|
| 2 | Per-Channel-Type screening (ledger key space, scorecards, OLS review, selection, S4 training, migration) | HIGH | — |
| 1 | Unified horizontal FactorTree canvas + dynamic Channel Type selector | MEDIUM | — |
| 4 | MasterData two-tab (Data + per-channel Factor Tree matrix, export endpoint) | MEDIUM | Phase 1 (canvas), Phase 2 (per-object payload) |
| 3 | Dynamic channel ordering / keyword banks / Knowledge-first ranges / interview roles | MEDIUM | — |

### Success criteria

1. An indicator dropped in TT's 2.2/2.4 review still models in MT — verified by a ledger unit test
   ("channel A rejection does not affect channel B").
2. MasterData wide table sliced to a Channel Type shows exactly that channel's surviving columns.
3. MasterData Tab 2 shows, per indicator, one status chip per Channel Type with an expandable
   per-layer reason chain.
4. Every Channel Type selector on the frontend is populated from data (no hardcoded channel list);
   an added/removed channel in the data changes the options with no code edit.
5. The full Danone case runs end-to-end with no breakpoints and no fabricated data.
6. Legacy archived projects heal into per-object records and behave identically.
