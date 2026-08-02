# S1: filename-derived interview layer + unified factor-tree add/remove (supersedes data-request review)

**Date:** 2026-07-29
**Status:** Approved (user, 2026-07-29) — proceed to writing-plans.
Refines the interview rebuild (2026-07-28) and **supersedes** the data-request
interview-review (2026-07-28 Phase 2): all interview-driven indicator changes now
flow through the factor tree, and the separate data-request review is removed.

## Why (user feedback)

1. **Interview layer should come from the file name, not inference.** The current
   rebuild uses the department as the layer when no layer is given, so a
   `商务部访谈.docx` shows layer = 商务部. Wanted: read the layer **from the file
   name** if present (`Layer3`, `第3层`, or a Chinese layer word), else leave it
   **blank** — kept **literally** (no mapping).
2. **Factor-tree reconcile conflicts are invisible / mis-framed.** The materials
   reconcile downgrades a conflicting template factor to `proposed` (kept
   `source="template"`), but the editor lumps ALL `proposed` under "AI proposed",
   hides the rationale for non-AI rows, and frames accept/reject as "accept AI rec".
   The user confirms factor changes on the canvas, so conflicts must be surfaced
   there as an explicit **keep/remove** decision. Since **interviews also add and
   remove**, group by **intent** (add vs remove), not by source.
3. **The data-request "Interview-driven changes (proposed)" review is redundant.**
   A data-request indicator column **is** a factor-tree indicator (the request is a
   projection of the factor tree). Confirming an add/remove in the factor tree is
   therefore equivalent to confirming it in the data request. There is **no
   data-request-only field** (user confirmed). So the interview→data-request review
   layer collapses into the factor tree, and the data request reverts to a pure
   projection of the confirmed tree.

## Design

### Feature 1 — Interview layer from the file name

- New `_layer_from_filename(filename) -> str`: return the **literal** layer marker
  found in the name — `Layer\d+` / `第[0-9一二三四五六七八九十]+层` / a Chinese layer
  word (`高层`/`管理层`/`执行层`/`数据团队`) — else `""`. No mapping (keep as written).
- `_department_from_filename`: also strip the layer marker so the department stays
  clean (`Layer3_电商部_纪要` → dept `电商部`, layer `Layer3`; `商务部访谈` → dept
  `商务部`, layer `""`).
- `_make_real_target(department, participants, questions, layer="")`: `layerZh =
  layer` (blank when none), `team = department`. Stop using the department as the layer.
- `_rebuild_targets_from_real_minutes`: pass `_layer_from_filename(filename)` per file.

### Feature 2 — Unified factor-tree add/remove (factors are the one confirmation surface)

**Backend — a direction flag on every proposal:**
- `FactorRow` gains `proposal_kind: Literal["add","remove"] | None` (alias
  `proposalKind`; `None`/absent ⇒ treated as `add` for back-compat). Producers set it:
  - AI materials-add, template supplements (`_ai_template_supplement`/`_keydiff_supplement`),
    interview **add/modify** → `add`.
  - Materials reconcile **downgrade** → `remove`.
  - Interview **remove** (new, below) → `remove`.

**Backend — interview-driven removal (new capability):**
- `_digest_transcript`'s `factor_changes` schema extends `op` to `add|modify|remove`;
  a `remove` means the minutes say an existing factor should be dropped.
- `writeback_minutes` handles `op=remove`: match the change to the existing tree
  row(s) by factor path / indicator and **demote them to `status="proposed",
  proposal_kind="remove"`** with the interview quote as rationale (mirrors the
  reconcile downgrade, but interview-sourced). No match → skip (don't fabricate).

**Backend — gate effects must respect direction:**
- `accept_factor_rows` (used by d-1.21 `confirm_tree_effect` and d-1.4
  `confirm_interview_effect`) must flip **only add-kind** proposed rows to
  `accepted`. A `remove`-kind proposed row is **left proposed** on a blanket
  gate-approve (proposed ⇒ not in the model's active set ⇒ effectively removed).
  Per-row the user still decides: 保留 → `accepted`, 确认删减 → `rejected`.

**Frontend — `FactorTreeEditor.tsx` three tabs by intent:**
- Tabs: **全部 / 建议新增 (proposed & kind≠remove) / 建议删减 (proposed & kind=remove)**,
  each with a count (replaces `全部 / AI only` and the "AI proposed" badge).
- Direction-correct actions (both write the same `accepted`/`rejected` status
  machine — only the labels/mapping differ):
  - 建议新增: **加入** → `accepted` · **忽略** → `rejected`.
  - 建议删减: **确认删减** → `rejected` · **保留** → `accepted`.
- Show the **rationale for every proposed row** (today only `source==='ai'`), so
  conflict/removal rows explain themselves (材料未提及/矛盾 · 访谈引用).
- Distinct visual for remove rows (⚠ / amber). Update the subtitle away from
  "accept or reject each AI recommendation".

### Feature 3 — Remove the data-request interview-review (revert to pure projection)

Delete the 2026-07-28 Phase 2 data-request-review machinery; `gen_data_request`
reverts to projecting the confirmed factor tree (baseline/accepted rows → columns).

Remove:
- **backend/business.py:** `_dr_key`, `_apply_field_edits`, `_datareq_proposals`,
  `_filter_proposals`, `_datareq_review_sheet`, `_DR_REVIEW_COLUMNS`, and their calls
  in `gen_data_request` (the `_apply_field_edits`, `_datareq_proposals`,
  `data_request_proposals` analysis set, and review-sheet append).
- **backend/store/state.py:** `data_request_field_edits` field.
- **backend/main.py:** `PUT /data-request/review` (`review_data_request`) +
  `DataRequestReviewBody`.
- **frontend:** `reviewDataRequest` (client.ts), `DataRequestReviewPanel.tsx` + its
  mount in `ArtifactDetail.tsx`, `DataRequestProposal` (types.ts).
- **tests:** `backend/app/agents/_test_datareq_review.py` (drop; add factor-tree
  proposal-kind tests instead).

The "add 会员复购率 / remove 经销商出货" data-availability signals now surface as
**interview-driven factor add/remove** on the tree (Feature 2). True "no data" for a
kept factor is already handled downstream at S2's 2.1 factor-map ignore.

## Contracts to keep in sync

| Change | Sync points |
|---|---|
| `FactorRow.proposal_kind` | `domain/models.py` ↔ `lib/types.ts` (camelCase `proposalKind`) |
| Factor-tree tabs/labels | `FactorTreeEditor.tsx` (frontend-only) |
| Interview layer/rebuild | `business.py` (`_layer_from_filename`, `_make_real_target`, rebuild) |
| Remove data-request review | business.py + state.py + main.py + client.ts + ArtifactDetail.tsx + types.ts |
| Back-compat | old saved FactorRows lack `proposalKind` → default `add`; no migration/gate change |

## Testing / verification

- `_test_interview.py`: extend for `_layer_from_filename` (literal Layer/第N层/中文
  layer word / blank) and that the rebuilt target's `layerZh` is the literal marker
  (or blank) with a clean department.
- New `_test_factor_kind.py` (or extend reconcile test): reconcile downgrade →
  `proposal_kind="remove"`; AI/template/interview add → `"add"`; `accept_factor_rows`
  flips only add-kind proposed → accepted, leaves remove-kind proposed untouched.
- Interview removal: given a synthetic transcript digest with `op=remove` matching an
  existing row, `writeback_minutes` demotes that row to proposed+remove (pure-function
  level where possible; LLM not mocked).
- `PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py`; `npm run build`; `npm run lint`.
- E2E: pending a working LLM (see Nike/Genki harness) — no fabricated inputs.

## Out of scope

- Any new status, gate, or DAG task (reuse `proposed→accepted/rejected`, d-1.21/d-1.4).
- Mapping `Layer1/2/3` to Chinese layers (user chose literal).
- Keeping any data-request-only review surface (user confirmed none needed).
