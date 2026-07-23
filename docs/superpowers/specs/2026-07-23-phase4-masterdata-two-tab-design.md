# Design: Phase 4 — MasterData Two-Tab (Data + per-Channel Factor Tree)

**Date:** 2026-07-23
**Status:** Approved (pending plan)
**Depends on:** Phase 2 (`MasterData.byObject` payload) merged; Phase 1 (shared horizontal canvas) for Tab 2's tree rendering.
**Scope:** rebuild the `a-master-data` (2.6) artifact view into two tabs; add a full-table export capability. Frontend-led, one new backend export endpoint.

---

## 1. Problem

Requirement #4: "MasterData 的主要作用就是组装数据，分成两个 Tab。Tab1：Filter + 明细数据 + 导出；Tab2：完整 FactorTree 显示被过滤还是接受 + 原因。"

Today `MasterDataView.tsx` is a **single scroll column** (header → object cards → filter funnel → rejected list → wide table). It has no tabs, the wide feature table **cannot be exported** (export falls back to Markdown without the table), and the full per-layer verdict chain — though present in the payload — is shown only as a flat rejected list, not grouped by the factor tree, and not per Channel Type.

## 2. Goals

- **Tab 1 "Data":** the assembly view — dimension Filter (including the dynamic Channel Type selector) + the wide detail table + **Export**. Nothing else. Move the object cards / funnel out of this tab.
- **Tab 2 "Factor Tree":** the full factor tree (Phase 1's horizontal canvas), each indicator row followed by **one status chip per Channel Type** (Accepted / Rejected@layer / Pending), each chip expandable to that channel's per-layer verdict chain + reason.
- **Export** the actual feature matrix (not just Markdown), not subject to the display cap.

All data for both tabs already exists in the Phase 2 artifact body — no new screening logic, only presentation + export.

## 3. Tab shell

`MasterDataView` becomes a two-tab shell (`Data` | `Factor Tree`). All existing sub-components (`FunnelBar`, `RejectedRow`, `ObjectCard`, `DimSelect`, `WideTable`) are already isolated and reused across the tabs. Tab state is component-local `useState<'data'|'tree'>('data')`. Design: a real tab control (not a link row) with a designed active/hover/focus state; the two tabs are visually distinct surfaces, not one scroll split by a heading.

## 4. Tab 1 — Data

- **Filter bar:** the existing `DimSelect`s for Brand / Province / Channel Type / Channel / Grain, driven by `data.dimensions` (options data-derived). The Channel Type selector is the same `ChannelTypeSelect` component from Phase 1, bound here to `dimensions.channelType`. Selecting a Channel Type slices the wide table to that channel — and because `adopted_mask` is per-object (Phase 2), the **column set is that channel's own surviving indicators** (different channels → different columns).
- **Detail table:** the live `api.masterTable(projectId, query)` result (`MasterTable{columns, rows, kpi, grain, truncated}`), rendered by the existing `WideTable` (KPI column highlighted, sticky header/first-col) — or optionally `DataGrid` (TanStack virtual/sort/filter) with cell stringification; `WideTable` is the low-risk default, `DataGrid` a stretch.
- **Export:** a new **backend** endpoint `GET /api/projects/{id}/master-data/export` that streams the **full** adopted feature table for the current filter as `.xlsx` — NOT capped at the 400×60 display limit. Modeled on the existing `data-request/export` (`main.py:316`, `data_request.build_export_zip`) using the same xlsx writer. Single Channel Type → one sheet; multiple/all → one sheet per Channel Type. Front end: an Export button in Tab 1 calling `api.exportMasterData(projectId, query)` → `downloadBlob`. (Client-side `export.ts::exportTable` from the live `MasterTable` is the fallback if a backend endpoint is out of scope, but it inherits the 400×60 cap — the backend endpoint is preferred precisely to avoid that.)
- The object cards + funnel are **removed from Tab 1** (they belong to the assembly/diagnostic story, surfaced in Tab 2 or a compact strip above the tabs).

## 5. Tab 2 — Factor Tree (per-channel verdict matrix)

- Render the **full** factor tree via Phase 1's shared horizontal canvas (all adopted + rejected indicators, grouped/merged L1–L4).
- For each indicator row, inject **one extension column per Channel Type** — a status chip:
  - **Accepted** (green) — the indicator is in `data.byObject[channel].adopted`.
  - **Rejected@layer** (red) — it is in `data.byObject[channel].rejected` (chip shows the `rejectedAt` layer label).
  - **Pending** (muted) — absent from both for that channel.
- Clicking a chip expands that channel's **per-layer verdict chain** — reusing the existing `LedgerVerdict[]` chip+chain UI from `RejectedRow` (status color per `layer/task/label/status/note`). Adopted rows now carry `verdicts` too (Phase 2), so "why accepted" is shown, not only "why rejected".
- A per-channel **funnel** (`data.funnel.byObject[channel]`) is available for a compact "N in → M survive" strip per channel.
- The channel columns are data-derived from `Object.keys(data.byObject)` — never hardcoded.

This turns the flat rejected list into a one-screen "which channels did this indicator survive in, and why" matrix — the requirement's Tab 2.

## 6. Backend

- New `GET /api/projects/{id}/master-data/export?brand=&channelType=&…` → `master_data.build_export(st, filters) -> bytes` (xlsx), uncapped, per-channel sheets. Reuse the xlsx writer already used by `data_request.build_export_zip`. Adopted-only columns per channel (via `adopted_mask`).
- No change to `assemble_master_data` / `byObject` (already sufficient). No change to `/master-data/table`.

## 7. Contracts

`lib/types.ts` MasterData already carries `byObject`, `funnel.byObject`, `dimensions.channelType` (Phase 2 Task 9). Only the export endpoint + `api.exportMasterData` client method are new. No blueprint/model change.

## 8. Risks

- **MEDIUM — export endpoint** must produce the full uncapped table correctly per channel (not the 400×60 display slice); verify row/col counts against the raw adopted long table. Reuse the tested `data_request` xlsx path.
- **MEDIUM — Tab 2 wide with many channels** (7 for Danone): 7 status-chip columns + 5 factor columns → horizontal scroll in the canvas box (Phase 1 handles overflow). Keep chips compact.
- **LOW — un-migrated artifacts** lack `byObject` (optional); Tab 2 degrades to the flat adopted/rejected lists with a "re-run 2.6 for per-channel view" note.
- **LOW — tab state** resets on artifact/project change.

## 9. Success criteria

1. `a-master-data` renders two tabs; Tab 1 = filter + wide table + working xlsx export; Tab 2 = full factor tree with a per-Channel-Type status chip per indicator + expandable reason chain.
2. Selecting a Channel Type in Tab 1 slices the table to that channel's own surviving columns (columns differ across channels).
3. Tab 2's channel columns and Tab 1's channel options come only from data (`byObject`/`dimensions`) — no hardcoded channel list.
4. Export downloads the **full** adopted feature matrix (uncapped), one sheet per Channel Type.
5. `npm run build` clean; visual-regression at standard breakpoints, both themes.
