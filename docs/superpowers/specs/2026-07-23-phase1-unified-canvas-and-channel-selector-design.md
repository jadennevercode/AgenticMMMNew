# Design: Phase 1 — Unified Horizontal FactorTree Canvas + Dynamic Channel Type Selector

**Date:** 2026-07-23
**Status:** Approved (pending plan)
**Depends on:** Phase 2 (per-channel screening) — merged in this worktree.
**Scope:** the shared FactorTree canvas, its S2 consumers, the OLS tree, the Indicator Catalog, and a data-driven Channel Type selector across the per-channel S2 surfaces. Frontend-led, with one backend change (object-aware ledger).

---

## 1. Problem

Two defects from the user's requirement #1 ("FactorTree 的 Canvas 全部横向展开 L1–L4+Indicator，展示语言一致") and the cross-cutting selector ask:

1. **Inconsistent factor rendering.** Seven surfaces render the factor hierarchy in three different ways. Only the two editors use true horizontal L1–L4 columns; the shared `FactorTreeCanvas` and the OLS/Catalog surfaces use an `L1›L2›L3` breadcrumb group + merged `L4·Indicator` cell.
2. **No way to see/screen per channel in the UI.** Phase 2 made screening per Channel Type in the backend (`object` on quality/stat/ols rows, `MasterData.byObject`), but the frontend has no Channel Type selector and its ledger index collapses per-object verdicts to one.

## 2. Goals

- **One horizontal canvas.** `FactorTreeCanvas` becomes a true `L1 | L2 | L3 | L4 | Indicator | …ext | Status | Action` column table (repeated parent values blanked/merged vertically), keeping collapse, the tone/chip system, consumer-injected columns/actions, and English chrome. Wide content scrolls inside its own `overflow-x:auto` box.
- **Every factor surface uses it.** Migrate `OlsTreeView`, `IndicatorCatalogPanel`, and align the S1 `FactorTreeEditor` styling. Keep the 3 current consumers (`DataProcessingCanvas`, `QualityCanvas`, `StatCanvas`) working through the new layout.
- **Dynamic Channel Type selector.** A selector, options populated from backend data (never a hardcoded channel array), scopes the per-channel S2 canvases (2.2 quality, 2.4 statistical, 2.5 OLS) to a chosen Channel Type or an "All channels" aggregate.
- **Consistent language.** All chrome English (fixed `L1/L2/L3/L4/Indicator` headers, one shared status-word constant table); Chinese factor/indicator values render verbatim.

## 3. The object-aware-ledger prerequisite (the one backend change)

`useLedgerIndex` (`frontend/src/components/project/factor-tree/useLedgerIndex.ts`) reads `GET /indicator-ledger` and keys a map strictly by `indicatorKey(l4, indicator)` — collapsing every channel's verdict onto one entry. `blockedBefore`/`ledgerOnlyRows` are therefore object-agnostic, so a per-channel canvas cannot show "blocked in TT but open in MT."

**Change:**
- Backend `GET /api/projects/{id}/indicator-ledger` (`main.py::get_indicator_ledger`) serializes an `object` field on each row (the endpoint already receives per-object `LedgerRow`s from Phase 2; Phase 2's fix deduped them to one-verdict-per-key for the *current* collapsed consumer — this change re-exposes the object dimension **additively**: keep the deduped `rows` for back-compat AND add `rowsByObject: Record<object, LedgerRow[]>`).
- `IndicatorLedger` type gains `rowsByObject?`. `useLedgerIndex` builds an **object-aware** index: `Map<"object|l4|indicator", row>` plus the existing collapsed map (unchanged for non-per-channel callers). A new `objectKey(object, l4, indicator)` in `keys.ts`.
- `blockedBefore(row, layer)` and `ledgerOnlyRows` gain an optional `object` param; when set they resolve that channel's verdict chain.

This is the smallest change that unblocks object-aware verdicts without disturbing the collapsed view the current S2 canvases render when "All channels" is selected.

## 4. The horizontal canvas

`FactorTreeCanvas.tsx` restructures from grouped-breadcrumb to a flat column table:

- Columns: fixed `L1 | L2 | L3 | L4 | Indicator`, then the consumer's injected `columns[]` (e.g. `['CV','Pearson','VIF','Total']`), then `Status`, then `Action`.
- **Vertical value merging:** within a run of rows sharing the same `L1` (then `L2`, then `L3`), render the value only on the first row of the run; blank (or a subtle rule) on the rest — the "editorial table" look, not a repeated-value grid. A run's first row can carry a collapse toggle on its L1/L2/L3 cell that hides the run.
- Keep `FactorCanvasRow` (add `object?: string`), `tone`, `statusLabel`, `blockedBy` lock badge, `cells[]`, `selectedKey`/`onSelect`, `actions`, `header`, `emptyHint`.
- Wrap the table in `<div style="overflow-x:auto">`; sticky header row; `min-width` so columns don't crush. Responsive: the box scrolls; the page never scrolls horizontally.
- Design direction: Swiss/editorial table — strong column hierarchy via type scale (L1 heaviest → Indicator lightest), hairline row rules, generous cell padding rhythm (not uniform), semantic status color (not decorative), designed hover/focus/selected row states. This satisfies ≥4 of the design-quality qualities.

The 3 current consumers change only their row construction (they already produce `FactorCanvasRow[]`); their injected columns/actions/tone maps are unchanged.

## 5. The dynamic Channel Type selector

- **Component:** a small `ChannelTypeSelect` reusing the proven `MultiMenu`/`SingleMenu` pattern from `BusinessValidationView` (single-select here: one channel or "All channels").
- **Options are data-driven:** sourced from the artifact/endpoint, never hardcoded. Quality/Stat canvases derive the channel list from the distinct `object` values on their own scorecard rows (`QualityRow.object`/`StatScoreRow.object`); the OLS tree from `OlsTreeRow.objects`. (Master data uses `dimensions.channelType` — Phase 4.) A channel absent from the data never appears; a new one appears with no code change.
- **Selection state:** a per-project store slice `s2ChannelFilter` on `useSimStore` (so the choice is consistent as the user moves between 2.2/2.4/2.5). No alias/URL convention exists in the app today; a shareable-URL variant is a noted future enhancement, not this phase.
- **Behavior:** "All channels" (default) → the canvas renders the collapsed view exactly as today (each indicator once, using the collapsed ledger). A concrete channel → rows are filtered to that `object`, and verdicts/`blockedBy` resolve via the object-aware ledger (§3). Row-level actions (Drop/tick) default to the **current channel**; a per-row/toolbar "apply to all channels" affordance is included so human effort doesn't scale ×N. (The write endpoints already accept per-object: quality/stat scorecard rows carry `object`; sign-off keys carry `object` from Phase 2 Task 4.)

## 6. Surface migrations

| Surface | Action |
|---|---|
| `DataProcessingCanvas`, `QualityCanvas`, `StatCanvas` | keep — new horizontal layout; Quality/Stat gain the Channel Type selector + object-aware verdicts |
| `OlsTreeView` (2.5, read-only) | migrate onto the shared canvas; its per-object `results` sub-table becomes the object-scoped view under the selector; keep the fit-metric `ObjectCard` strip |
| `IndicatorCatalogPanel` (Data-Engine) | migrate its flat `Factor path` table onto the shared canvas (columns Asset/Metric/Status), reusing DataProcessingCanvas's row logic |
| S1 `FactorTreeEditor` (editable) | align to the shared canvas's column styling for visual consistency (stays an editable input grid; not a full rewrite) |
| **`BusinessValidationView` sign-off list** | **DEFERRED — reconcile at merge.** The concurrent session rewrote BV into a two-tab Explore/Sign-off shell on the shared branch; migrating this worktree's old BV would be discarded at merge. Note in the plan; do NOT migrate here. |

## 7. Contracts to keep in sync

`domain/models.py` (LedgerRow already has `object`; the endpoint serialization is the change) ↔ `lib/types.ts` (`IndicatorLedger.rowsByObject`, `FactorCanvasRow.object`). No blueprint change.

## 8. Risks

- **HIGH — object-aware ledger correctness.** The endpoint/index change must not alter the collapsed "All channels" view (regression-test it) while adding the per-object view. Acceptance: a quality-dropped-in-TT indicator shows blocked in TT's canvas and open in MT's.
- **MEDIUM — canvas restructure regression** across the 3 current consumers (column/overflow/collapse), plus migrating OLS/Catalog. Visual-regression at 320/768/1024/1440 both themes.
- **MEDIUM — BusinessValidation merge conflict** (deferred, but flagged so merge reconciles the shared-branch rewrite with the object-aware sign-off).
- **LOW — selector store slice** must reset on project switch (mirror `activeProjectId`).

## 9. Success criteria

1. All migrated factor surfaces render one horizontal `L1|L2|L3|L4|Indicator` layout with English chrome and verbatim data values; no page-level horizontal scroll (wide tables scroll in-box).
2. The Channel Type selector's options come only from data; adding/removing a channel in the data changes the options with no code edit.
3. Selecting a channel scopes 2.2/2.4/2.5 to that channel's own verdicts; an indicator dropped in TT shows blocked in TT and open in MT; "All channels" reproduces today's collapsed view.
4. Row actions default to the current channel with an explicit apply-to-all.
5. `npm run build` clean; no new lint errors; visual-regression parity on the unchanged consumers.
