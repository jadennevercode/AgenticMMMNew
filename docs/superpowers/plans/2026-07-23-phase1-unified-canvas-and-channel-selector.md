# Phase 1 — Unified Horizontal FactorTree Canvas + Dynamic Channel Type Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render every S2 factor surface through one horizontal `L1|L2|L3|L4|Indicator` canvas with English chrome, and add a data-driven Channel Type selector that scopes 2.2/2.4/2.5 to a chosen channel's own per-channel verdicts.

**Architecture:** Restructure the shared `FactorTreeCanvas` from breadcrumb-group to a flat vertical-merge column table; add an object-aware ledger (backend `/indicator-ledger` gains `rowsByObject`; `useLedgerIndex`/`keys.ts` gain object variants); add a `ChannelTypeSelect` reusing the proven `MultiMenu` pattern + a per-project store slice; migrate `OlsTreeView` and `IndicatorCatalogPanel` onto the canvas. BusinessValidation is deferred (merge-reconcile).

**Tech Stack:** React 19 + Vite + TypeScript, Zustand store, FastAPI backend (one endpoint change). Frontend build: `cd frontend && npm run build` (tsc -b + vite). Backend tests: `PYTHONPATH=. .venv/bin/python -m <module>` / `-m pytest tests/ -q` from `backend/`.

## Global Constraints

- **English-only chrome; data values verbatim.** Fixed column headers `L1/L2/L3/L4/Indicator`; one shared status-word constant table; Chinese factor/indicator strings render as-is.
- **No hardcoded channel names anywhere.** The Channel Type selector's options come only from data (`QualityRow.object`/`StatScoreRow.object`/`OlsTreeRow.objects`/`dimensions.channelType`). Adding/removing a channel in data changes options with no code edit.
- **The "All channels" view must reproduce today's collapsed behavior byte-for-byte** — the object-aware ledger is additive; the collapsed map/endpoint field stays.
- **No page-level horizontal scroll** — wide tables scroll inside their own `overflow-x:auto` box; images/tables `max-width:100%`.
- **`ProjectState`-serialized backend fields carry no Pydantic alias.**
- Frontend: `npm run build` clean, no NEW lint errors in touched files (8 pre-existing lint errors in unrelated files are acceptable — do not fix them here).
- Do NOT migrate `BusinessValidationView` (deferred — the shared branch has a concurrent rewrite).

---

## File Structure

- `backend/app/main.py` — `get_indicator_ledger` serializes `rowsByObject` (additive).
- `backend/app/agents/_test_ledger_endpoint.py` — **new** runnable test for the endpoint shape.
- `frontend/src/lib/types.ts` — `IndicatorLedger.rowsByObject?`, `FactorCanvasRow.object?`.
- `frontend/src/components/project/factor-tree/keys.ts` — add `objectKey`.
- `frontend/src/components/project/factor-tree/useLedgerIndex.ts` — object-aware index + `blockedBefore(row, layer, object?)`.
- `frontend/src/components/project/factor-tree/FactorTreeCanvas.tsx` — horizontal column layout.
- `frontend/src/components/project/factor-tree/factor-tree.css` (or existing stylesheet) — column/merge/overflow styling.
- `frontend/src/store/useSimStore.ts` — `s2ChannelFilter` slice (per project).
- `frontend/src/components/project/factor-tree/ChannelTypeSelect.tsx` — **new** selector.
- `frontend/src/components/project/canvas/QualityCanvas.tsx`, `StatCanvas.tsx` — selector + object-aware verdicts.
- `frontend/src/components/project/canvas/OlsTreeView.tsx` — migrate onto the canvas.
- `frontend/src/components/dataeng/IndicatorCatalogPanel.tsx` — migrate onto the canvas.
- `frontend/src/components/project/FactorTreeEditor.tsx` — align column styling only.

---

## Task 1: Object-aware ledger endpoint (backend, additive)

**Files:**
- Modify: `backend/app/main.py` (`get_indicator_ledger`, ~lines 964-983)
- Create: `backend/app/agents/_test_ledger_endpoint.py`

**Interfaces:**
- Consumes: `ledger.indicator_ledger(st)` (returns per-`(object,l4,metric)` `LedgerRow`s), `ledger.OBJECT_ANY`.
- Produces: the endpoint JSON gains `rowsByObject: {object: [ledgerRowDict, ...]}` alongside the existing deduped `rows`/`adopted`/`rejected`. Each ledgerRowDict carries `object`, `l1..l4`, `indicator`, `adopted`, `rejectedAt`, `reason`, `verdicts:[{layer,task,label,status,note}]`.

- [ ] **Step 1: Write the failing test**

```python
"""GET /indicator-ledger exposes per-object rows additively. Run:
PYTHONPATH=. .venv/bin/python -m app.agents._test_ledger_endpoint"""
from __future__ import annotations
import sys
from app.agents._test_per_channel import make_two_channel_state
from app.agents.stat_scoring import build_stat_scorecard
from app.main import get_indicator_ledger
from app.store.state import get_store
import asyncio

def test_rows_by_object_present():
    st = make_two_channel_state("t-ledger-ep")
    st.stat_scorecard = build_stat_scorecard(st)
    for r in st.stat_scorecard.rows:
        if r.indicator == "渠道库存":
            r.disposition = "drop" if r.object == "TT" else "include"
    get_store()._states["t-ledger-ep"] = st  # seed for the handler; adapt to real store API
    out = asyncio.run(get_indicator_ledger("t-ledger-ep"))
    assert "rowsByObject" in out, out.keys()
    by = out["rowsByObject"]
    assert set(by) >= {"MT", "TT"}, list(by)
    tt = [r for r in by["TT"] if r["indicator"] == "渠道库存"]
    mt = [r for r in by["MT"] if r["indicator"] == "渠道库存"]
    assert tt and not tt[0]["adopted"] and tt[0]["rejectedAt"] == "statistical", tt
    assert mt and mt[0]["adopted"], mt
    # the collapsed `rows` view is unchanged (one row per key)
    keys = [(r["l4"], r["indicator"]) for r in out["rows"]]
    assert len(keys) == len(set(keys)), "collapsed rows must stay deduped"
    print("  rowsByObject present; collapsed rows unchanged")

if __name__ == "__main__":
    fns = [v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed=0
    for fn in fns:
        try: fn()
        except Exception as e: failed+=1; print(f"  FAIL {fn.__name__}: {e}")
    print(f"{len(fns)-failed}/{len(fns)} passed"); sys.exit(1 if failed else 0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_ledger_endpoint`
Expected: FAIL — `rowsByObject` not in the response. (If the store-seeding line errors, inspect `app/store/state.py::get_store` for the real "put a state" API — e.g. `get_store().save`/an internal dict — and adapt; the test's intent is: run the handler on a two-channel state.)

- [ ] **Step 3: Implement**

In `get_indicator_ledger`, after building the deduped `rows`, add a per-object grouping and serialize it. Read the current handler first; add (mirroring `data.py::_ledger_row_dict`):

```python
    from app.agents.ledger import OBJECT_ANY
    def _row(r):
        d = {"object": r.object, "l1": r.l1, "l2": r.l2, "l3": r.l3, "l4": r.l4,
             "indicator": r.indicator, "adopted": r.adopted, "rejectedAt": r.rejected_at,
             "reason": r.reason,
             "verdicts": [{"layer": v.layer, "task": v.task, "label": v.label,
                           "status": v.status, "note": v.note} for v in r.verdicts]}
        return d
    from app.agents.dataset_cache import model_objects
    objs = model_objects(st) or [OBJECT_ANY]
    rows_by_object = {o: [_row(r) for r in full_ledger if r.object in (o, OBJECT_ANY)] for o in objs}
```
where `full_ledger = ledger.indicator_ledger(st)` (the raw per-object rows, before dedup). Add `"rowsByObject": rows_by_object` to the returned dict. Keep the existing `rows`/`adopted`/`rejected` exactly as they are (the Phase-2 dedup stays for the collapsed consumer).

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_ledger_endpoint`
Expected: PASS.

- [ ] **Step 5: Regression**

Run: `cd backend && PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py && PYTHONPATH=. .venv/bin/python -m pytest tests/ -q`
Expected: smoke green; pytest 131 passed / 3 pre-existing failures (no new).

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/app/agents/_test_ledger_endpoint.py
git commit -m "feat(ledger): /indicator-ledger exposes rowsByObject (additive, collapsed view unchanged)"
```

---

## Task 2: Frontend ledger types + object-aware index

**Files:**
- Modify: `frontend/src/lib/types.ts` (`IndicatorLedger`, `FactorCanvasRow`)
- Modify: `frontend/src/components/project/factor-tree/keys.ts`
- Modify: `frontend/src/components/project/factor-tree/useLedgerIndex.ts`

**Interfaces:**
- Consumes: `IndicatorLedger.rowsByObject` from Task 1.
- Produces: `objectKey(object, l4, indicator): string`; `useLedgerIndex` returns `{ index, byObject, reload, blockedBefore }` where `byObject: Map<objectKey, IndicatorLedgerRow>`; `blockedBefore(row, layer, object?)` resolves the per-object chain when `object` is given, else the collapsed one. `FactorCanvasRow` gains `object?: string`.

- [ ] **Step 1: Add types**

In `types.ts`: add `object?: string` to `FactorCanvasRow`; add to `IndicatorLedger`:
```ts
  rowsByObject?: Record<string, IndicatorLedgerRow[]>
```
and `object?: string` to `IndicatorLedgerRow` (the per-object rows carry it; collapsed rows leave it undefined).

- [ ] **Step 2: Add `objectKey`**

In `keys.ts`, beside `indicatorKey`:
```ts
export const objectKey = (object: string, l4: string, indicator: string): string =>
  `${(object || '*').trim().toLowerCase()}|${indicatorKey(l4, indicator)}`
```

- [ ] **Step 3: Object-aware index in `useLedgerIndex`**

Build `byObject` from `data.rowsByObject` (flatten each object's rows into `Map<objectKey(obj, r.l4, r.indicator), row>`), keep the existing collapsed `index` from `data.rows` unchanged, and give `blockedBefore` an optional `object`:
```ts
function blockedBefore(row: IndicatorLedgerRow | undefined, layer: string): string { /* existing */ }
// new object-aware lookup helper returned from the hook:
const blockedBeforeFor = (l4: string, indicator: string, layer: string, object?: string): string => {
  const row = object ? byObject.get(objectKey(object, l4, indicator)) : index.get(indicatorKey(l4, indicator))
  return blockedBefore(row, layer)
}
```
Return `{ index, byObject, blockedBeforeFor, reload }` (keep `index`/`reload` for existing callers).

- [ ] **Step 4: Type-check**

Run: `cd frontend && npm run build`
Expected: `tsc -b` clean (no consumer uses the new fields yet).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/components/project/factor-tree/keys.ts frontend/src/components/project/factor-tree/useLedgerIndex.ts
git commit -m "feat(ledger-index): object-aware ledger index + objectKey (collapsed view intact)"
```

---

## Task 3: Restructure FactorTreeCanvas to a horizontal column table

**Files:**
- Modify: `frontend/src/components/project/factor-tree/FactorTreeCanvas.tsx`
- Modify/Create: its stylesheet (co-located CSS or the existing one it imports)

**Interfaces:**
- Consumes: `FactorCanvasRow[]` (unchanged shape + optional `object`), `columns?`, `selectedKey?`, `onSelect?`, `actions?`, `header?`, `emptyHint?`.
- Produces: same props; new rendering — a single table with columns `L1 | L2 | L3 | L4 | Indicator | …columns | Status | Action`, parent values vertically merged (blank on repeats within a run), collapse toggle on the first row of an `L1`/`L2`/`L3` run, `overflow-x:auto` wrapper, sticky header.

- [ ] **Step 1: Write a rendering smoke test (Playwright or a lightweight render assertion)**

If the repo has a component test harness, add one asserting: given rows spanning 2 L1 groups with a shared L2, the header shows exactly `L1,L2,L3,L4,Indicator,<injected>,Status,Action`, and a repeated `l1` value appears once per run. If no component-test harness exists, this task is verified by `npm run build` + the Task 8 visual-regression pass; note that and proceed to Step 2.

- [ ] **Step 2: Implement the horizontal layout**

Replace the grouped-breadcrumb body (`groupRows` + group header rows + merged `L4·Indicator` cell) with a flat rows render that:
1. Sorts/keeps rows in `l1,l2,l3,l4,indicator` order (consumers already sort; preserve input order otherwise).
2. Computes, per row, whether each of `l1/l2/l3` is the FIRST of its run (compare to the previous row's path prefix) — render the value only then, else an empty cell (with a left hairline to read as a continuation).
3. Renders `l4` and `indicator` always; then `columns.map` numeric cells from `row.cells`; then the Status chip (existing `TONE` map + `Denied @ blockedBy` badge); then `actions?.(row)`.
4. A collapse control on the first-of-run `l1`/`l2`/`l3` cell toggles hiding that run (local `Set<string>` of collapsed run-keys).
5. Wrap `<table>` in `<div class="factor-canvas-scroll">` with `overflow-x:auto`; `position:sticky` header; `min-width` per column so nothing crushes.

Keep `selectedKey`/`onSelect` (row click), `header`, `emptyHint`, and the muted/tone/lock semantics exactly.

- [ ] **Step 3: Style (design-quality)**

In the stylesheet: type-scale hierarchy (L1 heaviest → Indicator lightest), hairline row rules, non-uniform cell padding (breathing room on Indicator/Status), semantic status colors from the existing tone tokens, and designed `:hover`/`:focus-visible`/selected-row states. Theme-aware (light/dark) if the app supports both. No animation of layout-bound properties.

- [ ] **Step 4: Type-check + verify the 3 current consumers still render**

Run: `cd frontend && npm run build` (clean). Manually confirm (or via Task 8) that DataProcessing/Quality/Stat canvases render with the new columns.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/project/factor-tree/
git commit -m "feat(canvas): horizontal L1|L2|L3|L4|Indicator layout with vertical value merge"
```

---

## Task 4: `s2ChannelFilter` store slice + `ChannelTypeSelect`

**Files:**
- Modify: `frontend/src/store/useSimStore.ts`
- Create: `frontend/src/components/project/factor-tree/ChannelTypeSelect.tsx`

**Interfaces:**
- Produces: store `s2ChannelFilter: string` (`''` = All channels) + `setS2ChannelFilter(v)`, reset to `''` in `loadProject`. `ChannelTypeSelect({ options: string[], value: string, onChange })` — a single-select menu (reuse the `SingleMenu`/`MultiMenu` visual pattern from `BusinessValidationView`) with an "All channels" first option.

- [ ] **Step 1: Add the store slice**

In `useSimStore.ts`: add `s2ChannelFilter: ''` to state, `setS2ChannelFilter: (v: string) => set({ s2ChannelFilter: v })`, and set `s2ChannelFilter: ''` inside `loadProject` (so it resets per project). No alias/persistence.

- [ ] **Step 2: Build `ChannelTypeSelect`**

A small controlled component: an "All channels" option + one per `options` (data-derived, passed in). Reuse the existing menu styling from `BusinessValidationView`'s `SingleMenu`/`MultiMenu` (import or replicate the class names) so it matches. English label "Channel".

- [ ] **Step 3: Type-check**

Run: `cd frontend && npm run build` — clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/store/useSimStore.ts frontend/src/components/project/factor-tree/ChannelTypeSelect.tsx
git commit -m "feat(s2): s2ChannelFilter store slice + ChannelTypeSelect (data-driven options)"
```

---

## Task 5: Wire the selector + object-aware verdicts into QualityCanvas & StatCanvas

**Files:**
- Modify: `frontend/src/components/project/canvas/QualityCanvas.tsx`
- Modify: `frontend/src/components/project/canvas/StatCanvas.tsx`

**Interfaces:**
- Consumes: `s2ChannelFilter`/`setS2ChannelFilter`, `ChannelTypeSelect`, `blockedBeforeFor` (Task 2), `QualityRow.object`/`StatScoreRow.object`.

- [ ] **Step 1: Derive channel options + filter rows**

In each canvas: `const channels = [...new Set(rows.map(r => r.object).filter(Boolean))].sort()`. Render `<ChannelTypeSelect options={channels} value={s2ChannelFilter} onChange={setS2ChannelFilter} />` in the header. When `s2ChannelFilter` is set, `visibleRows = scorecardRows.filter(r => (r.object || '') === s2ChannelFilter)`; when empty, keep today's behavior — but note scorecard rows are now per-object, so "All channels" should DEDUP by `indicatorKey` (show each indicator once, first occurrence) to reproduce the pre-Phase-2 single-row view.

- [ ] **Step 2: Object-aware `blockedBy`**

Replace `blockedBefore(index.get(indicatorKey(r.l4,r.indicator)), 'quality')` with `blockedBeforeFor(r.l4, r.indicator, 'quality', s2ChannelFilter || undefined)` (and `'statistical'` for StatCanvas). So a channel-scoped view greys indicators blocked in THAT channel; "All channels" uses the collapsed chain.

- [ ] **Step 3: Row action default-to-channel + apply-to-all**

The disposition action already targets a specific scorecard row (which carries `object`), so a per-channel Drop/Include is automatic. Add an "apply to all channels" affordance (a small toolbar toggle or a per-row menu item) that, when used, writes the same disposition to every object's row for that `indicatorKey` before calling `updateQualityScorecard`/`updateStatScorecard`. Keep the default as current-channel-only.

- [ ] **Step 4: Type-check + manual render**

Run: `cd frontend && npm run build` — clean. Confirm selecting a channel filters the canvas and re-greys per that channel.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/project/canvas/QualityCanvas.tsx frontend/src/components/project/canvas/StatCanvas.tsx
git commit -m "feat(2.2/2.4): Channel Type selector + per-channel verdicts in quality/stat canvases"
```

---

## Task 6: Migrate OlsTreeView onto the shared canvas

**Files:**
- Modify: `frontend/src/components/project/canvas/OlsTreeView.tsx`

**Interfaces:**
- Consumes: `FactorTreeCanvas`, `ChannelTypeSelect`, `s2ChannelFilter`; `OlsTreeRow.objects`/`OlsRowResult` (already per-object).

- [ ] **Step 1: Build FactorCanvasRow[] from the olsTree body**

Map each tree row to a `FactorCanvasRow` (`key`, `l1..l4`, `indicator`, `tone` from the row status, `statusLabel`, `cells` = `[coef, t, p, roiBand, contributionBand]` formatted, `blockedBy` from `droppedBy`). When `s2ChannelFilter` is set, use that object's entry from `row.results` (per-object coef/t/p/ROI/contribution); else the row's aggregate. Columns = `['Coef','t','p','ROI','Contribution']`.

- [ ] **Step 2: Replace the hand-rolled table**

Render `<ChannelTypeSelect options={body.objects.map(o=>o.object)} .../>` + the fit-metric `ObjectCard` strip (keep) + `<FactorTreeCanvas rows={rows} columns={COLS} .../>`. Remove the bespoke grouped `<table>` and per-row expand sub-table (the selector replaces the expand; keep an optional per-row results popover if low-risk). Keep the status filter strip.

- [ ] **Step 3: Type-check + render**

Run: `cd frontend && npm run build` — clean. Confirm the 2.5 artifact renders through the canvas and the selector switches per-channel coef/ROI.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/project/canvas/OlsTreeView.tsx
git commit -m "feat(2.5): OlsTreeView renders through the shared horizontal canvas + channel selector"
```

---

## Task 7: Migrate IndicatorCatalogPanel + align S1 FactorTreeEditor styling

**Files:**
- Modify: `frontend/src/components/dataeng/IndicatorCatalogPanel.tsx`
- Modify: `frontend/src/components/project/FactorTreeEditor.tsx`

**Interfaces:**
- Consumes: `FactorTreeCanvas`; `api.getFactorMap` rows.

- [ ] **Step 1: Migrate the catalog's factor-map table**

Build `FactorCanvasRow[]` from `factorMap.rows` (columns `['Asset','Metric','Status']`, actions bind/ignore/accept — reuse DataProcessingCanvas's row logic). Replace the flat `Factor path` `<table>` with `<FactorTreeCanvas>`. Keep the separate "Published indicators" table as-is (out of scope) unless trivial.

- [ ] **Step 2: Align the S1 editor columns**

`FactorTreeEditor` already uses per-level columns; only align its column headers/styling to the shared canvas's `L1|L2|L3|L4|Indicator` visual (shared CSS classes / header labels). It stays an editable input grid — do NOT convert it to the read-only canvas.

- [ ] **Step 3: Type-check + render**

Run: `cd frontend && npm run build` — clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dataeng/IndicatorCatalogPanel.tsx frontend/src/components/project/FactorTreeEditor.tsx
git commit -m "feat(canvas): Indicator Catalog on shared canvas; S1 editor column styling aligned"
```

---

## Task 8: Visual-regression + accessibility pass

**Files:**
- Use: `frontend/scripts/visual-check.mjs` (Playwright walk-through) if present; else Playwright ad-hoc.

- [ ] **Step 1: Screenshot the S2 surfaces at 320/768/1024/1440, both themes**

Run the dev server, drive a project to S2, screenshot DataProcessing / Quality / Stat / OLS / MasterData(existing) / IndicatorCatalog. Confirm: no page-level horizontal scroll (the canvas box scrolls); headers `L1..Indicator` present; the Channel Type selector renders and switches views; Chinese values verbatim.

- [ ] **Step 2: Keyboard + reduced-motion + contrast**

Tab through the selector and a canvas; confirm focus-visible states, reduced-motion respected, status-color contrast adequate in both themes.

- [ ] **Step 3: Record findings + commit any fixes**

```bash
git add -A frontend/
git commit -m "test(visual): S2 unified-canvas + channel selector regression pass"
```

---

## Self-Review

**Spec coverage:** §3 object-aware ledger → Tasks 1–2. §4 horizontal canvas → Task 3. §5 selector → Tasks 4–5. §6 migrations → Tasks 5–7 (BV deferred per spec). §2 language consistency → Task 3 (English chrome constant) + all migrations. Success criteria 1–5 → Tasks 3/4/5 + Task 8.

**Placeholder scan:** Task 1's store-seeding line and Task 3's Step-1 test are conditional-on-repo-facts (the executor inspects `get_store`/component-test harness and adapts) — flagged inline, not silent TODOs; the assertions/behavior are fully specified.

**Type consistency:** `objectKey`/`blockedBeforeFor` names consistent across Tasks 2/5/6; `s2ChannelFilter`/`setS2ChannelFilter` consistent Tasks 4–7; `FactorCanvasRow.object?` added Task 2, consumed Tasks 5–7; `rowsByObject` shape consistent Tasks 1–2.

**Deferred:** BusinessValidationView migration (spec §6) — must be reconciled when this worktree merges with the shared branch's BV rewrite; not in this plan.
