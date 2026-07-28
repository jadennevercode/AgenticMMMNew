# Business Validation → Self-Serve Analysis Explorer

**Date:** 2026-07-22
**Status:** Design approved, pending spec review
**Area:** `frontend/` data module (task 2.3) + `backend/` data agent / dataeng

## Problem

The current Business Validation view (task 2.3, `BusinessValidationView.tsx` +
`ValidationChart.tsx`) renders one fixed chart per FactorTree L3: a constant
sell-out KPI area background with the factor's indicators overlaid. It is
**too rigid** to be a real analysis surface:

- Axis values / scales can't be adjusted (fixed dual `compact` Y axes).
- Chart form can't be changed (hard-coded area + bar/line composed chart).
- There are **nine filter controls** per card (grain, KPI switch, source, L4–L8
  cascade, indicator, brand, channel, region) — a filter wall, not exploration.

Every one of those controls is a hand-rolled patch working around the fact that
the chart itself is not configurable. This is the same situation that led the
Data Engine to replace hand-rolled `<table>` views with a real grid: a mature
component beats accreting bespoke controls.

## Goal

Turn 2.3 into a **self-serve analysis explorer** with a **default view per
factor** — each factor still opens on the current KPI-backdrop-plus-indicators
shape, but the user can freely change axes, chart type, aggregation, and
dimensions, or build entirely new charts. Add **AI-generated insights** grounded
in the chart's data.

## Key Decisions (from brainstorming)

1. **Sign-off is decoupled, not lost.** The 2.3 Y/N sign-off is indicator-ledger
   layer 3 (`ledger.py`) and gates `d-2.3` — it must not disappear. But it does
   **not** need to live inside the chart. Sign-off moves to a standalone
   FactorTree list where the user accepts/rejects indicators directly. The
   `signoffs` store, `setSignoff`, the `(l4, indicator)` key space, `pairVerdict`
   / `groupVerdict`, and `refresh_signoff_in_artifact` are all preserved
   unchanged — only the UI that drives them is relocated.

2. **Embed Graphic Walker**, not a hand-built config layer or a Lightdash
   sidecar. `@kanaries/graphic-walker` (MIT) is an embeddable React component:
   Tableau-style drag-and-drop of dimensions/measures onto encoding channels,
   switchable chart types, aggregation, dual axes; vega-lite + DuckDB-wasm
   underneath. It ingests/exports a `visSpec` JSON, so each factor's default view
   is just a preset spec. Trade-off accepted: GW owns its own UI look (limited
   deep customization) and ships a larger bundle (mitigated by dynamic import).

3. **Single GW instance, one chart tab per factor.** One Graphic Walker instance
   loads the whole published long table; each L3 factor is a preset chart tab
   (KPI backdrop + that factor's indicators, current default shape). Users edit
   any tab or add blank tabs. Avoids 17+ component instances; exploration isn't
   bounded by factor.

4. **AI Insight: pre-generate defaults + on-demand.** Default-view insights are
   pre-generated when task 2.3 runs (reuses today's `interpretation` mechanism).
   User-modified or new charts get an insight on demand via a "Generate Insight"
   button, cached on the tab by spec hash. Numbers are authoritative from the
   compute layer; the LLM only interprets (per the project-wide convention).

## Architecture

### Frontend

The 2.3 artifact page (`BusinessValidationView.tsx`) becomes a two-tab shell:

- **Explore tab** — a single dynamically-imported Graphic Walker instance.
  - Data source: the published long table fetched once from
    `GET /validation-dataset` (below), handed to GW as its dataset.
  - Chart tabs: one preset `visSpec` per L3 factor, generated from the 2.3
    artifact body. Default spec mirrors today's shape — X = time (month grain),
    KPI metric as an area/line backdrop, factor indicators as the overlay
    (bar for spend-type, line otherwise).
  - Users can reconfigure any tab (axes, chart type, aggregation, filters) or
    add new blank tabs. Specs persist via `PUT /validation-specs`; a
    "Reset to default" restores the generated preset.
  - **AI Insight panel** (side/below the canvas): shows the current tab's
    insight; "Generate Insight" triggers on-demand generation for edited/new
    charts. Result cached per spec hash on the tab.
- **Sign-off tab** — a FactorTree-structured list (L1 › L2 › L3 groups, rows =
  `(l4, indicator)` pairs) with per-row Accept/Deny and Accept-all/Deny-all per
  factor. Wraps the **existing** `signoffs` store and `setSignoff`; `pairVerdict`
  / `groupVerdict` reused verbatim. No change to ledger or `d-2.3` semantics.

**Retired:** `ValidationChart.tsx`, the nine-control filter bar, `MultiMenu` /
`SingleMenu` / `YearlyTable` / `ComparisonBlock` / `TimeWindowBar` /
`IndicatorSignoffList` / `FactorCard` as chart drivers. The sign-off list logic
survives in the new Sign-off tab. `recharts` may remain for other surfaces
(`ReviewCharts.tsx`), but 2.3 no longer uses it.

Dependency: add `@kanaries/graphic-walker`, loaded via dynamic `import()` so it
stays out of the initial bundle.

### Backend

Three new endpoints on the project router + one handler change:

- `GET /projects/{id}/validation-dataset` — serialize `model_df(st)` (the 2.24
  long table) with its indicator metadata (`metric_type`, `numberFormat`,
  `unit`, `aggregation`), the `source` provenance column, and **derived
  convenience columns**: `year`, period label, and `value_yoy` (so YoY is a
  drawable column, not a separate table). Guard with a row-count cap — Danone's
  ~23.8k rows are trivial for GW's client-side engine, but a very wide project
  upload should get a warning + a hint to pre-aggregate in the Data Engine
  rather than shipping millions of rows to the browser.
- `GET/PUT /projects/{id}/validation-specs` — persist the per-tab `visSpec` JSON
  on `ProjectState` (versioned; parse failure falls back to the generated
  default; supports "Reset to default").
- `POST /projects/{id}/validation-insight` — accept `{visSpec, aggregatedRows}`,
  run the existing Volcano LLM grounding flow (`_bv_narrate` pattern in
  `data.py`) to produce an insight string. LLM interprets; numbers stay
  authoritative from the aggregated rows the client sends.

Handler change: `data.business_validation` (2.3) generates the **default
`visSpec` set** (one per L3) in addition to / in place of today's `groups`
metadata, and continues to pre-generate the default-view interpretation via
`_bv_narrate`. The anomaly localization + findings/insight emission are kept.

Contract sync (per CLAUDE.md): new/changed types mirror in `domain/models.py`
and `frontend/src/lib/types.ts`; new client methods in `api/client.ts`.

## Data Flow

```
2.3 runs → business_validation():
    model_df(st) → default visSpec per L3 + pre-generated interpretation
    → a-business-validation body { kpiMetric, specs[], anomalies, note }

Open 2.3 page:
    GET /validation-dataset  → long table + derived cols → GW dataset
    GET /validation-specs    → persisted specs (or defaults from artifact)
    GW renders one tab per spec

User edits a chart:
    GW visSpec changes → debounced PUT /validation-specs
    "Generate Insight" → POST /validation-insight { spec, aggregatedRows }
                       → LLM interpretation → cached on tab by spec hash

Sign-off tab:
    Accept/Deny → setSignoff (existing) → ledger layer 3 → d-2.3 gate
```

## Error Handling & Edges

- No published data → Explore empty state (as today); Sign-off tab still lists
  factors if the factor tree exists.
- Insight LLM failure → retriable inside the panel; never blocks the gate.
- `visSpec` parse/version failure → fall back to the generated default + notice.
- Row-count over cap → warn + suggest Data-Engine pre-aggregation; do not ship
  an unbounded frame to the browser.
- GW's UI look is its own; approximate the app theme via its appearance/theme
  config and accept the residual mismatch. All in-product strings stay English.

## Testing

Backend (runnable scripts, matching existing `_test_*` convention):
- `/validation-dataset` contract: expected columns present, `value_yoy` correct
  against a known series.
- Default spec generation: one tab per L3, KPI encoded as backdrop, indicators
  encoded per spend/non-spend.
- `/validation-insight` smoke with a mocked LLM (no network).

Frontend:
- `npm run build` + `npm run lint` green.
- `scripts/visual-check.mjs`: extend the walk-through to the 2.3 page — GW loads,
  tab switch works, sign-off click toggles verdict, insight panel renders.

## Out of Scope (YAGNI)

- No enterprise DB pushdown (ClickHouse/Snowflake) — client-side GW engine only.
- No cross-factor saved dashboards beyond per-tab specs.
- No change to S2 ledger layers, gate semantics, or downstream model selection.
- Time-window comparison UI (`TimeWindowBar`) is dropped; YoY ships as a column
  instead. Revisit only if a user needs arbitrary A/B window comparison.

## References

- Graphic Walker: https://github.com/Kanaries/graphic-walker ·
  https://docs.kanaries.net/graphic-walker
- Perspective (evaluated, not chosen): https://github.com/perspective-dev/perspective
- Embedded BI comparison: https://embeddable.com/blog/top-self-serve-embedded-bi-analytics-tools
