# S1: materials-grounded factor baseline + interview-driven data-request field review

**Date:** 2026-07-28
**Status:** Approved (user, 2026-07-28) — proceed to writing-plans.
Two independent S1 (Business Understanding) changes, one spec, two phases. Both
ground a template-derived deliverable on the project's real uploaded content.

## Why (client feedback)

1. **Factor tree — the non-AI (template) baseline ignores the uploaded materials.**
   `_baseline_rows_from_template` copies the industry factor-tree template verbatim
   as auto-active `baseline` rows, independent of the uploaded materials. So the
   template can carry factors that don't apply to this brand, or names that clash
   with the materials — a conflict against the material-grounded AI additions.
   Want: reconcile the template baseline against the materials.
2. **Data request — ignores the interview minutes.** `gen_data_request` projects the
   accepted factor tree into a workbook (indicators → columns) and never reads the
   minutes. Want: from the minutes, propose per-L4 **indicator field** add/removes,
   list them for the user to approve, apply only the approved ones.

## Current flow (as-is)

- **1.21 `derive_factor_tree`:** `template_rows` (verbatim template, `source=template
  status=baseline`, auto-active) → optionally supplemented by AI-selected missing
  template rows (upload path) → an LLM adds materials-justified factors
  (`source=ai status=proposed`). Gate **d-1.21** accepts proposed template/ai rows.
- **1.5 `gen_data_request`:** groups factor rows with `status ∈ {baseline, accepted}`
  by L3→L4, indicators become columns; emits `a-data-request` (generic `sheets`).
  Gate **d-1.5 (1.5d)** is a **signoff** that closes Business Understanding.
- Interview→**factor** influence already flows in via **1.4/d-1.4** (interview factor
  changes → proposed rows → accepted → appear in the request). Phase 2 is a **distinct
  layer** (data-request *fields*), not a re-run of the factor gate.

## Design decisions (locked with user)

- **No new gate for either phase.** Reuse the existing gates:
  Phase 1 downgraded rows surface at **d-1.21**; Phase 2 approvals happen on an
  interactive review panel and commit at the existing **1.5d** sign-off — mirroring
  the established `factor_map_ignores` / `anomaly-review` accept-on-artifact pattern.
- **Phase 2 touches ONLY the data-request fields, never the factor tree.**

---

## Phase 1 — Reconcile the template baseline against the materials (option A)

Add an AI reconciliation step inside `derive_factor_tree`, applied to the template
baseline **before** the existing materials-driven AI-add step. It runs only when a
template baseline is in play (the default non-upload path; skip when the user's own
uploaded tree is the baseline).

### Behavior
A new grounded LLM call takes the template rows + the uploaded materials and returns,
per template row, a verdict:

- **keep** (materials support it) → stays `source=template status=baseline` (auto-active).
- **rename** (materials use different wording) → renamed in place, still `baseline`,
  `rationale="命名对齐材料"`, `evidence="materials reconciliation"`.
- **downgrade** (materials don't mention it / contradict it) → `status=proposed`,
  `rationale="待确认：材料未提及/矛盾"` — **not hard-deleted**; the user decides at the
  existing **d-1.21** gate whether to keep or reject it.

Then the reconciled template rows are **deduped against the AI materials factors** (the
existing add step) by concept, so the same factor doesn't appear twice under different
wording (the AI-add step already guards exact-key dups; extend it to also skip a concept
the reconciled/renamed baseline now covers).

### Robustness
LLM unavailable or empty response → **fall back to the verbatim template baseline**
(today's behavior), so the tree is never blocked or emptied. This mirrors
`_ai_template_supplement`'s deterministic fallback.

### Provenance / review
- Auto-active set = `keep` + `rename` baseline rows (materials-confirmed).
- Review set = `downgrade` proposed rows, shown at d-1.21 alongside AI proposals.
- No new store or gate; `derive_factor_tree` just emits the adjusted row set.

---

## Phase 2 — Interview-driven data-request indicator review (no new gate)

`gen_data_request` (1.5) keeps building the base workbook from the factor tree, and
**additionally** proposes per-L4 indicator field changes from the interview minutes;
the user approves/rejects each; approved ones apply to the request; 1.5d signs off.

### Proposal extraction (at 1.5)
A grounded LLM pass over the uploaded `interview_minutes`, given the factor tree's L4
structure, proposes:
- **add** — an indicator the interview says is needed/available for an L4 that the
  request doesn't already carry;
- **remove** — an indicator (a factor-derived request field) the interview says is
  **not available / not tracked**, so it should not be requested.
Each proposal carries `{op, l3, l4, indicator, rationale, quote}`. Proposals are **not
auto-applied**. No minutes → no proposals (nothing fabricated).

### Review + apply (mirror `factor_map_ignores` / `anomaly-review`)
- Store the accepted edits on `ProjectState` — a new field, e.g.
  `data_request_field_edits` (per-L4 `added` indicators + `removed` indicators),
  analogous to `factor_map_ignores`. Proposals (pending) live on the artifact / analysis.
- New endpoint `PUT /api/projects/{id}/data-request/review` resolves one proposal
  (accept → record the add/remove in `data_request_field_edits`; reject → keep as-is),
  then **re-renders `a-data-request`**.
- `gen_data_request` **applies `data_request_field_edits`** when composing each L4
  sheet's columns: add the accepted `added` indicators, drop the accepted `removed`
  ones. The pending proposals render as a visible review section on the artifact.
- **1.5d (existing signoff) is the commit point** — unchanged decision, closes S1.

### Scope guard
Phase 2 mutates **only** the data-request fields. A `remove` does **not** reject the
factor in the tree; the factor stays (and if it then has no requested data, S2's 2.1
mapping `ignore` handles it). Do not touch the factor tree, d-1.21, d-1.4, or d-1.5.

---

## Contracts to keep in sync

| Change | Sync points |
|---|---|
| Phase 1 | Backend-only (`derive_factor_tree` + a new reconcile helper in `business.py`); no blueprint/scenario/types change (row shape unchanged; `status`/`rationale` reused). |
| Phase 2 store | `ProjectState.data_request_field_edits` in `domain/models.py` ↔ `lib/types.ts` (camelCase alias). |
| Phase 2 endpoint | new `PUT /data-request/review` in `main.py`; a client method in `api/client.ts`; a review panel in the data-request artifact UI. |
| No new tasks/gates | blueprint/scenario **unchanged** for the DAG; `heal_state` unaffected (no new task id). |

## Testing / verification (gates green)

- Phase 1: a runnable `_test` for the reconcile helper — given synthetic template rows
  + a materials string, assert keep→baseline, rename→renamed baseline, downgrade→proposed,
  and dedup against AI factors; LLM-absent → verbatim baseline fallback.
- Phase 2: a runnable `_test` — given synthetic proposals + `data_request_field_edits`,
  assert `gen_data_request` adds the accepted `added` columns and drops the accepted
  `removed` ones, and that pending proposals render; the review endpoint records/rejects
  and re-renders.
- `PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py`; `npm run build`.
- E2E: `danone-mizone` needs real materials + interview minutes uploaded to exercise
  both phases end-to-end — **no fabricated inputs**; note E2E pending real uploads.

## Out of scope

- Any new DAG gate/task (explicitly rejected — reuse d-1.21 and 1.5d).
- Phase 2 changing the factor tree, granularity/dimension columns, or caliber/source
  annotations (only indicator field add/remove).
- Hard-deleting downgraded template factors (they become `proposed`, user-reviewed).
