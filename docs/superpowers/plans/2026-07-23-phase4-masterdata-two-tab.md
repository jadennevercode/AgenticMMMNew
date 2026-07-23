# Phase 4 — MasterData Two-Tab (Data + per-Channel Factor Tree) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rebuild the `a-master-data` (2.6) view into two tabs — Tab 1 "Data" (filter + wide table + xlsx export), Tab 2 "Factor Tree" (full tree with a per-Channel-Type status chip + expandable reason chain) — using data already in the Phase 2 `byObject` payload.

**Architecture:** A tab shell over the existing sub-components; a new backend `master-data/export` endpoint (uncapped xlsx, per-channel sheets) reusing the `data_request` xlsx writer; Tab 2 renders the factor tree via Phase 1's shared horizontal canvas with per-channel status-chip columns.

**Tech Stack:** React 19 + TS, FastAPI, xlsx via the existing writer. Build: `cd frontend && npm run build`. Backend: `PYTHONPATH=. .venv/bin/python -m <module>` / `-m pytest tests/ -q`.

## Global Constraints

- **Depends on Phase 1** (shared horizontal `FactorTreeCanvas` for Tab 2). Phase 1 must be merged/available in the worktree first.
- **No hardcoded channel names** — Tab 1 options from `dimensions.channelType`; Tab 2 channel columns from `Object.keys(data.byObject)`.
- **Export is the full uncapped adopted table**, one sheet per Channel Type — NOT the 400×60 display slice.
- **All Tab 2 data already exists** in `data.byObject` / `data.funnel.byObject` — no new screening logic.
- English-only chrome; no page-level horizontal scroll (canvas/table box scrolls). `npm run build` clean; no new lint errors.
- Un-migrated artifacts lack `byObject` (optional) — Tab 2 degrades to the flat lists with a note.

---

## File Structure

- `backend/app/agents/master_data.py` — `build_export(st, filters) -> bytes` (xlsx).
- `backend/app/main.py` — `GET /master-data/export`.
- `backend/app/agents/_test_master_export.py` — **new** runnable test.
- `frontend/src/api/client.ts` — `exportMasterData(projectId, query)`.
- `frontend/src/components/project/canvas/MasterDataView.tsx` — tab shell + Tab 1 + Tab 2.
- `frontend/src/components/project/canvas/masterdata/` — extract `DataTab.tsx`, `FactorTreeTab.tsx` (keep files focused).

---

## Task 1: Backend full-table export endpoint

**Files:**
- Modify: `backend/app/agents/master_data.py` (add `build_export`)
- Modify: `backend/app/main.py` (add `GET /master-data/export`)
- Create: `backend/app/agents/_test_master_export.py`

**Interfaces:**
- Consumes: `adopted_mask` (per-object), `_adopted_df`, the `data_request` xlsx writer (inspect `app/agents/data_request.py::build_export_zip` for the writer used — reuse `openpyxl`/SheetJS-equivalent).
- Produces: `master_data.build_export(st, *, brand, province_group, channel_type, channel, grain) -> bytes` — a full (uncapped) xlsx: for each channel type in scope, one sheet named by the channel, columns = that channel's adopted indicators (+ KPI + Period), rows = all periods (no 400/60 cap). `GET /api/projects/{id}/master-data/export?...` returns it as `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` with a filename header.

- [ ] **Step 1: Write the failing test**

```python
"""Full uncapped per-channel master-data export. Run:
PYTHONPATH=. .venv/bin/python -m app.agents._test_master_export"""
from __future__ import annotations
import io, sys
from app.agents._test_per_channel import make_two_channel_state
from app.agents.master_data import build_export

def test_export_has_a_sheet_per_channel():
    st = make_two_channel_state("t-master-export")
    data = build_export(st)  # no filters → all channels
    assert isinstance(data, (bytes, bytearray)) and len(data) > 0
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data))
    # one sheet per model object (MT, TT); a sheet has a Period col + >=1 indicator
    assert set(wb.sheetnames) >= {"MT", "TT"}, wb.sheetnames
    ws = wb["MT"]
    header = [c.value for c in next(ws.iter_rows(max_row=1))]
    assert header and header[0] == "Period", header
    print(f"  export ok: sheets={wb.sheetnames}")

if __name__ == "__main__":
    fns=[v for k,v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed=0
    for fn in fns:
        try: fn()
        except Exception as e: failed+=1; print(f"  FAIL {fn.__name__}: {e}")
    print(f"{len(fns)-failed}/{len(fns)} passed"); sys.exit(1 if failed else 0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_master_export`
Expected: FAIL — `build_export` undefined. (Confirm `openpyxl` is importable; the `data_request` export already uses an xlsx writer — reuse the same library.)

- [ ] **Step 3: Implement `build_export`**

Read `app/agents/data_request.py::build_export_zip` for the xlsx idiom. Implement `build_export`: resolve `_adopted_df(st)`, apply the dim filters, determine channel types in scope (`model_objects` intersected with the `channel_type` filter or all), and for each build the full per-channel wide table (reuse `master_table`'s pivot logic but WITHOUT `MAX_ROWS`/`MAX_COLS` truncation — factor the pivot into a helper `_wide_frame(df, grain)` shared by `master_table` and `build_export`, with a `cap: bool` flag). Write each channel's frame to its own sheet via `openpyxl`. Return `wb` saved to a `BytesIO`.

- [ ] **Step 4: Endpoint**

In `main.py`, add:
```python
@app.get("/api/projects/{project_id}/master-data/export")
async def export_master_data(project_id: str, brand: str = "", channelType: str = "", channel: str = "", provinceGroup: str = "", grain: str = "month"):
    st = _require_state(project_id)
    data = master_data.build_export(st, brand=[brand] if brand else None, channel_type=[channelType] if channelType else None, channel=[channel] if channel else None, province_group=[provinceGroup] if provinceGroup else None, grain=grain)
    from fastapi import Response
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="master-data-{project_id}.xlsx"'})
```
(Match the codebase's existing query-param + Response style; check `data-request/export` at main.py:316 for the exact pattern.)

- [ ] **Step 5: Run to verify + regression**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_master_export && PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py && PYTHONPATH=. .venv/bin/python -m pytest tests/ -q`
Expected: export test passes; smoke green; pytest 131/3 pre-existing.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/master_data.py backend/app/main.py backend/app/agents/_test_master_export.py
git commit -m "feat(2.6): full uncapped per-channel master-data xlsx export endpoint"
```

---

## Task 2: Client export method + tab shell

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/project/canvas/MasterDataView.tsx`
- Create: `frontend/src/components/project/canvas/masterdata/DataTab.tsx`, `FactorTreeTab.tsx`

**Interfaces:**
- Produces: `api.exportMasterData(projectId, query): Promise<Blob>`; `MasterDataView` becomes a 2-tab shell rendering `<DataTab>` / `<FactorTreeTab>`.

- [ ] **Step 1: Client method**

In `client.ts`, add `exportMasterData(projectId, query: MasterTableQuery): Promise<Blob>` — a GET to `/master-data/export` with the query as search params, returning `res.blob()`. (Follow the existing `data-request/export` client call if one exists; else use `fetch` + `res.blob()`.)

- [ ] **Step 2: Tab shell**

Refactor `MasterDataView`: keep `data = asMasterData(inst.body)` + `projectId`; add `const [tab, setTab] = useState<'data'|'tree'>('data')`; render a designed tab control (`Data` | `Factor Tree`) with active/hover/focus states; render `<DataTab data={data} projectId={projectId} />` or `<FactorTreeTab data={data} />`. Move the existing filter/table/ObjectCards/funnel code into `DataTab`; leave a compact object-summary strip above the tabs if useful.

- [ ] **Step 3: Type-check**

Run: `cd frontend && npm run build` — clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/components/project/canvas/MasterDataView.tsx frontend/src/components/project/canvas/masterdata/
git commit -m "feat(2.6): MasterData two-tab shell + exportMasterData client method"
```

---

## Task 3: Tab 1 "Data" — filter + wide table + export

**Files:**
- Modify: `frontend/src/components/project/canvas/masterdata/DataTab.tsx`

**Interfaces:**
- Consumes: `api.masterTable`, `api.exportMasterData`, `ChannelTypeSelect` (Phase 1), `data.dimensions`.

- [ ] **Step 1: Filter bar + table**

In `DataTab`: the existing `DimSelect`s for Brand/Province/Channel Type/Channel/Grain (Channel Type via `ChannelTypeSelect` bound to `dimensions.channelType`); the `useEffect` calling `api.masterTable(projectId, query)`; the existing `WideTable`. Keep the KPI-first, sticky-header table. Remove the funnel + rejected list + object cards from this tab (they move to Tab 2 / the summary strip).

- [ ] **Step 2: Export button**

Add an "Export .xlsx" button that calls `api.exportMasterData(projectId, query)` → `downloadBlob(blob, 'master-data.xlsx')` (reuse `export.ts::downloadBlob`). Disabled while a fetch is in flight; surface errors via the store's error channel.

- [ ] **Step 3: Verify slice-by-channel changes columns**

Run: `cd frontend && npm run build`. With a running server + a per-channel project, confirm selecting a Channel Type changes the wide-table columns to that channel's surviving indicators (backend `adopted_mask` is per-object).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/project/canvas/masterdata/DataTab.tsx
git commit -m "feat(2.6): Tab 1 Data — filter + wide table + xlsx export"
```

---

## Task 4: Tab 2 "Factor Tree" — per-channel status matrix

**Files:**
- Modify: `frontend/src/components/project/canvas/masterdata/FactorTreeTab.tsx`

**Interfaces:**
- Consumes: `FactorTreeCanvas` (Phase 1), `data.byObject`, `data.funnel.byObject`, `LedgerVerdict`.

- [ ] **Step 1: Build the full-tree rows with per-channel status columns**

From `data.byObject` + the flat `adopted`/`rejected`, build the union of all indicators (grouped L1–L4). Channel columns = `Object.keys(data.byObject).sort()`. For each indicator row, `columns = channels`, and `cells[i]` = a status token for `channels[i]`: `Accepted` if the indicator is in `byObject[ch].adopted`, `Rejected@<layer>` if in `byObject[ch].rejected` (use `rejectedAt`), else `Pending`. Feed as `FactorCanvasRow[]` to `<FactorTreeCanvas rows columns={channels}>`; map the status token to a tone/chip in the canvas cell (a compact colored chip, not raw text) — pass a custom cell renderer if the canvas supports it, else encode tone in the cell string + a legend.

- [ ] **Step 2: Expandable per-layer reason chain**

Clicking a status chip opens that channel's `verdicts` chain for the indicator (from `byObject[ch].adopted|rejected[*].verdicts`) — reuse the `RejectedRow` chip+chain rendering (status color per `layer/status`, showing `label/task/note`). A small per-channel funnel strip (`data.funnel.byObject[ch]`) is optional.

- [ ] **Step 3: Degrade gracefully**

If `data.byObject` is absent (un-migrated artifact), render the flat adopted/rejected lists with a "Re-run 2.6 for the per-channel view" note.

- [ ] **Step 4: Verify**

Run: `cd frontend && npm run build`. On a 7-channel project confirm 7 status columns + the reason chain expands per channel; on the synthetic 2-channel confirm divergence shows (Accepted in one, Rejected@ in the other).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/project/canvas/masterdata/FactorTreeTab.tsx
git commit -m "feat(2.6): Tab 2 Factor Tree — per-channel status matrix + reason chain"
```

---

## Task 5: Visual-regression + export correctness

- [ ] **Step 1: Screenshot both tabs at 320/768/1024/1440, both themes** — no page-level horizontal scroll; the tree box scrolls with many channel columns.
- [ ] **Step 2: Export correctness** — download the xlsx for a per-channel project; open it and confirm one sheet per Channel Type, each carrying that channel's full (uncapped) adopted columns, row counts matching the raw adopted long table (spot-check against `master_table` totals × the uncapping).
- [ ] **Step 3: Commit any fixes**

```bash
git add -A frontend/ && git commit -m "test(visual): MasterData two-tab regression + export check"
```

---

## Self-Review

**Spec coverage:** §3 tab shell → Task 2. §4 Tab 1 (filter+table+export) → Tasks 1–3. §5 Tab 2 (per-channel matrix + reason chain) → Task 4. §6 export endpoint → Task 1. Success criteria 1–5 → Tasks 3/4 + Task 5.

**Placeholder scan:** Task 1 Step-3/4 reference "inspect `data_request` for the xlsx idiom / exact Response pattern" — a deliberate reuse instruction (the writer already exists), not a TODO; the endpoint behavior + test are fully specified.

**Type consistency:** `exportMasterData(projectId, query)` consistent Tasks 2–3; `build_export` signature consistent Tasks 1/backend; `DataTab`/`FactorTreeTab` props (`data`, `projectId`) consistent Tasks 2–4; reuses Phase 1's `FactorTreeCanvas`/`ChannelTypeSelect`.

**Dependency:** Task 4 requires Phase 1 Task 3's horizontal `FactorTreeCanvas` (and its custom-cell/tone support). Sequence Phase 1 before Phase 4.
