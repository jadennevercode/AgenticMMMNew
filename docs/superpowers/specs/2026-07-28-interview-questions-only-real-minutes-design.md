# Interview: questions-only outline + real-minutes backfill & restructure

**Date:** 2026-07-28
**Status:** Approved (user, 2026-07-28) — proceed to writing-plans.
Touches S1 Business Understanding interview flow only. Factor-tree writeback and
the `1.4d` gate are explicitly **out of scope / unchanged**.

## Why (client feedback)

The client raised three problems with the current interview flow:

1. **AI pre-answers are bad.** Task `1.3b` (`pre_answer`) drafts a preliminary
   answer to every outline question before the interview. The quality is poor and
   the client does not want the AI guessing answers up front.
2. **Business doesn't interview from our outline.** Stakeholders ask their own
   questions in the real interviews. So after minutes are uploaded we must
   (a) backfill answers to the outline questions the minutes actually cover, and
   (b) **extract the new questions** the business raised that were not in our outline.
3. **Our preset org structure is fake.** The uploaded minutes are organized by the
   client's **real** organization (and the file name clearly says which department
   each interview is). The preset interview structure (Leadership / Management /
   Operation / Data + template business teams) must be replaced by the real one,
   derived from the uploaded minutes.

"Four-element" extraction (question / answer / open-item / action-item) was
considered and **dropped** — keep only **new questions + answers**.

## Current flow (as-is)

```
1.3   draft_interview   (A)  preset layered outline → a-interview (questions only)
1.3b  pre_answer        (C)  AI drafts preAnswer/confidence/sources per question   ← REMOVE
1.4a  upload minutes    (H)  interview_minutes uploads (requiresUpload)
1.4b  transcribe_audio  (M)  ASR for audio; text passes through
1.4   writeback_minutes (C)  per-transcript: fill finalAnswer + factor_changes + insights
1.4d  confirm changes   (H)  d-1.4 → accept interview-sourced factor rows
```

Runtime interview state lives in `st.analysis["interview_targets"]` (plain dicts);
`a-interview` is a **generic `sheets` artifact** rendered by `_interview_sheets`.
There is **no Pydantic/`types.ts` contract** on the per-question columns, and the
pre-answer fields (`preAnswer`/`confidence`/`sources`/`finalAnswer`/`answerSource`)
are consumed **only** in `business.py`. `bu_summary` (1.7) reads `a-interview` as
plain text via `artifact_text`, so column changes are safe.

---

## Design

### Phase A — Remove AI pre-answer (1.3b)

- **Blueprint** (`app/domain/blueprint.py`): delete task `1.3b`; change `1.4a`
  `depends_on` from `["1.3b"]` → `["1.3"]`.
- **Registry** (`app/agents/registry.py`): remove `eng.register("1.3b", business.pre_answer)`.
- **Frontend** (`frontend/src/lib/scenario.ts`): delete the mirrored `1.3b`; fix
  `1.4a` dependency. (Contract sync — blueprint ↔ scenario.)
- **heal_state** (`app/store/state.py`): prune `1.3b` (and any orphaned run state)
  from saved projects so existing `danone-mizone.json` heals cleanly.
- **business.py**: delete `pre_answer`, `_fill_business_preanswers`,
  `_fill_data_preanswers`, `_source_labels`, `_norm_confidence` (verify none are
  referenced elsewhere before removal).
- **Interview sheet columns** (`_IV_COLUMNS`): drop `AI Pre-Answer`, `Confidence`,
  `Sources`. New column set:
  `["#", "Q Type", "Question", "Related Factor Path", "Origin", "访谈回答", "回答来源"]`
  where **Origin** ∈ {`提纲` (outline), `新问题` (emergent)}. `_interview_sheets`
  row builder updated to match.

`1.3 draft_interview` is **unchanged** — it still produces the preset layered
outline so the business has a question list to bring to the interviews. The
outline only becomes "real" at `1.4` after minutes arrive.

### Phase B — Restructure to the real org from minutes (auto)

At `1.4`, the interview structure is **rebuilt from the uploaded minutes files**,
one real interview session per file, replacing the preset `interview_targets`.

- **Department name:** parse from the file name first (client file names clearly
  name the department, e.g. `市场部访谈.docx`). Fall back to AI inference from the
  transcript body only when the file name is uninformative.
- **Participants / layer:** inferred by the AI from the transcript content
  (returned by the per-transcript digest, Phase C).
- **Question reconciliation (client chose "real minutes are authoritative"):**
  - Each outline question the minutes answer is placed under the department that
    answered it, with its backfilled answer + source.
  - Outline questions **no transcript covers are dropped** — not carried as
    "uncovered". Only what really happened survives.
  - New (emergent) questions attach to the department that raised them.

The **Data-Team** target (templated data-availability questions, previously skipped
in writeback) is no longer synthesized as a preset target; data specs continue to
be confirmed in the S2 data flow, not here. (Confirm during planning that dropping
the preset Data target from `a-interview` doesn't strand a downstream reader — none
found so far; `bu_summary` reads text only.)

### Phase C — Per-transcript digest: backfill + new questions

Extend `_digest_transcript` (one combined LLM call per transcript, run
concurrently — unchanged batching) to return, using **only** that transcript:

```json
{
  "department": "string (falls back to filename-derived)",
  "participants": "string",
  "answers":       [{"n": int, "answer": str, "source": str}],
  "new_questions": [{"question": str, "answer": str, "source": str}],
  "factor_changes":[{...unchanged...}],
  "insights":      [{...unchanged...}]
}
```

- `answers` → backfill `finalAnswer`/`answerSource` on the matched outline
  question (existing behavior, kept).
- `new_questions` → **new** rows under that department, `Origin=新问题`, carrying
  their own answer + source. New questions are interview records, **not** outline
  questions — they get no `relatedFactorPath` unless the model supplies one.
- `factor_changes` + `insights` → **unchanged**; still flow to `proposed` factor
  rows and the `d-1.4` gate.

`writeback_minutes` rebuilds `interview_targets` as one target per real department,
each target's rows = covered outline questions (with answers) + emergent questions
(with answers), then re-renders `a-interview` via `_interview_sheets` and sets
`interview_targets` / `interview_questions` analysis.

**Token budget:** the digest now returns four result families in one call. Keep the
one-call-per-transcript design (concurrency covers wall-time) but widen
`max_tokens` and reuse the existing `_MINUTES_LLM_TIMEOUT`. Fault isolation stays
per file (a bad transcript returns `{}` and is skipped).

### Phase D — Factor tree: unchanged

`1.4` still emits `factor_changes` → `proposed` interview rows → `d-1.4` gate →
`confirm_interview_effect` → data request. **No change** to this path or to
`1.4d` / `1.5`.

---

## Contracts to keep in sync

| Change | Sync points |
|---|---|
| Remove `1.3b`, fix `1.4a` dep | `blueprint.py` ↔ `scenario.ts`; `heal_state` prunes it |
| Interview sheet columns | `_IV_COLUMNS` + `_interview_sheets` (backend only — `a-interview` is a generic sheet, **no `types.ts` change**) |
| Registry | remove `pre_answer` wiring |

## Testing / verification (gates must be green)

- `PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py` — control flow after
  task removal (task count drops by one; `1.4a` still reachable from `1.3`).
- New/updated business-handler check: given a small synthetic transcript set,
  `writeback_minutes` backfills ≥1 outline answer, extracts ≥1 new question, and
  rebuilds targets keyed by the filename department. (Add as a runnable script in
  the `_test`/`_smoke` style — no pytest harness.)
- `frontend/`: `npm run build` (tsc + prod build) — scenario edit compiles.
- E2E: `danone-mizone` autopilot **requires interview_minutes uploaded** to
  exercise `1.4`; confirm the run reaches `1.5` with a rebuilt real-department
  interview artifact. (No fabricated minutes — honors the no-mock-data constraint.)

## Out of scope

- Four-element (open-item / action-item) extraction — dropped.
- Any change to the factor-tree writeback, `d-1.4`, data request, or S2+.
- An org-structure human-confirmation gate — the restructure is fully automatic.
