# Materials-grounded factor baseline + interview-driven data-request review — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (Phase 1) reconcile the factor-tree template baseline against the uploaded materials in `derive_factor_tree`; (Phase 2) let the interview minutes propose per-L4 data-request indicator add/removes that the user approves before they apply — with no new DAG gate.

**Architecture:** All backend logic lives in `backend/app/agents/business.py`. Phase 1 splits the reconcile into a pure verdict→rows mapper (`_apply_reconcile_verdicts`) plus an LLM wrapper (`_reconcile_baseline_with_materials`) with a verbatim-baseline fallback, wired into `derive_factor_tree`'s template path. Phase 2 adds a backend edit-store (`data_request_field_edits` on `ProjectState`, mirroring `factor_map_ignores`), an LLM proposal extractor over the minutes, a pure field-edit applier in `gen_data_request`, a `PUT /data-request/review` endpoint, and a `DataRequestReviewPanel` (mirroring `AnomalyReviewPanel`).

**Tech Stack:** Python 3.12 / FastAPI (dependency-light, runnable `_test_*` scripts — no pytest), Volcano Ark LLM for grounded verdicts/proposals, React/Vite/TS frontend.

## Global Constraints

- **No mock data.** Reconcile verdicts ground on the uploaded materials; data-request proposals ground on the uploaded `interview_minutes`. No inputs → no reconcile / no proposals (never fabricate).
- **No new DAG gate or task.** `blueprint.py` / `scenario.ts` are UNCHANGED. Phase 1 downgraded rows surface at the existing **d-1.21**; Phase 2 approvals commit at the existing **1.5d** signoff. `heal_state` needs no task change.
- **Phase 2 touches ONLY the data-request fields — never the factor tree.** A `remove` does not reject the factor; it only drops the requested column.
- **Reconcile robustness:** LLM unavailable/empty → fall back to the verbatim template baseline (today's behavior). The tree is never blocked or emptied.
- **Backend numbers/derivations come from code, not the LLM.** The LLM returns only per-row verdicts (Phase 1) and per-L4 field proposals (Phase 2); the pure mappers build the rows/columns.
- **Git is initialized** (create a feature branch `feature/s1-materials-grounding`). Each task ends by running its verification gate green and committing (message trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`).
- **Tests are runnable scripts** (`PYTHONPATH=. .venv/bin/python -m <module>` from `backend/`; venv `backend/.venv`).
- **Contract sync:** `ProjectState` edit-stores like `factor_map_ignores` are NOT mirrored in `frontend/src/lib/types.ts`; `data_request_field_edits` follows suit (backend-only, surfaced via the artifact + endpoint). Only a small proposal-item type is added to types.ts for the panel.
- Existing shapes: a `FactorRow` has `id, l1, l2, l3, l4, indicator, dimension, source, status, rationale, evidence`; `source ∈ {template, ai, interview, manual, upload}`; `status ∈ {baseline, accepted, proposed, rejected}`. The data-request artifact `a-data-request` is a generic `{"sheets": [...]}` body.

---

### Task 1: Phase 1 — pure reconcile verdict→rows mapper

**Files:**
- Modify: `backend/app/agents/business.py` (add `_apply_reconcile_verdicts` near `_baseline_rows_from_template` ~236)
- Test: `backend/app/agents/_test_factor_reconcile.py` (create)

**Interfaces:**
- Produces: `_apply_reconcile_verdicts(template_rows: list[FactorRow], verdicts: dict[int, dict]) -> list[FactorRow]` — `verdicts` keyed by 1-based template-row index; each verdict `{"decision": "keep|rename|downgrade", "indicator": <new name, rename only>, "rationale": str}`. Returns adjusted rows: keep → unchanged; rename → `indicator` replaced, `status="baseline"`, `rationale="命名对齐材料"`, `evidence="materials reconciliation"`; downgrade → `status="proposed"`, `rationale="待确认：材料未提及/矛盾"`, `evidence="materials reconciliation"`. A row with no/invalid verdict defaults to keep (verbatim).

- [ ] **Step 1: Write the failing test** — create `backend/app/agents/_test_factor_reconcile.py`:

```python
"""Runnable checks for the factor-tree template↔materials reconcile (no LLM)."""
from app.domain.models import FactorRow
from app.agents import business as B

def _row(i, ind):
    return FactorRow(id=f"ft-tpl-{i}", l1="生意", l2="外部", l3="品类", l4="规模",
                     indicator=ind, dimension="", source="template", status="baseline")

def test_apply_reconcile_verdicts():
    rows = [_row(0, "市场规模"), _row(1, "GDP增速"), _row(2, "竞品数")]
    verdicts = {
        1: {"decision": "keep"},
        2: {"decision": "rename", "indicator": "宏观GDP同比"},
        3: {"decision": "downgrade", "rationale": "材料未提及"},
    }
    out = B._apply_reconcile_verdicts(rows, verdicts)
    assert out[0].status == "baseline" and out[0].indicator == "市场规模"
    assert out[1].status == "baseline" and out[1].indicator == "宏观GDP同比"
    assert out[1].rationale == "命名对齐材料"
    assert out[2].status == "proposed" and out[2].indicator == "竞品数"
    assert "待确认" in out[2].rationale
    # rows keep their identity/source
    assert all(r.source == "template" for r in out)
    print("OK apply_reconcile_verdicts")

def test_missing_verdict_defaults_to_keep():
    rows = [_row(0, "市场规模")]
    out = B._apply_reconcile_verdicts(rows, {})   # no verdicts at all
    assert out[0].status == "baseline" and out[0].indicator == "市场规模"
    print("OK missing_verdict_defaults_to_keep")

def main():
    test_apply_reconcile_verdicts()
    test_missing_verdict_defaults_to_keep()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it, verify it FAILS**

Run (from `backend/`): `PYTHONPATH=. .venv/bin/python -m app.agents._test_factor_reconcile`
Expected: AttributeError — `_apply_reconcile_verdicts` not defined.

- [ ] **Step 3: Implement the pure mapper** (place after `_baseline_rows_from_template`):

```python
def _apply_reconcile_verdicts(template_rows: list[FactorRow],
                              verdicts: dict[int, dict]) -> list[FactorRow]:
    """Apply per-row keep/rename/downgrade verdicts to the template baseline.
    Verdicts are keyed by 1-based row index; an absent/invalid verdict = keep."""
    out: list[FactorRow] = []
    for i, r in enumerate(template_rows, 1):
        v = verdicts.get(i) if isinstance(verdicts, dict) else None
        decision = str(v.get("decision", "keep")).lower() if isinstance(v, dict) else "keep"
        if decision == "rename" and isinstance(v, dict) and str(v.get("indicator", "")).strip():
            out.append(r.model_copy(update={
                "indicator": str(v["indicator"]).strip(), "status": "baseline",
                "rationale": "命名对齐材料", "evidence": "materials reconciliation"}))
        elif decision == "downgrade":
            out.append(r.model_copy(update={
                "status": "proposed", "rationale": "待确认：材料未提及/矛盾",
                "evidence": "materials reconciliation"}))
        else:  # keep (default)
            out.append(r)
    return out
```

- [ ] **Step 4: Run the test, verify it PASSES**

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_factor_reconcile`
Expected: both OK lines.

- [ ] **Step 5: Run the smoke gate + commit**

Run: `PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py` (expect pass). Commit `business.py` + the new test.

---

### Task 2: Phase 1 — LLM reconcile wrapper wired into `derive_factor_tree`

**Files:**
- Modify: `backend/app/agents/business.py` (`_reconcile_baseline_with_materials` after Task 1's helper; call site in `derive_factor_tree` ~512-530)
- Test: `backend/app/agents/_test_factor_reconcile.py` (extend)

**Interfaces:**
- Consumes: `_apply_reconcile_verdicts` (Task 1), `sources.category_text`, `get_llm().json`, `_paths_block`.
- Produces: `async _reconcile_baseline_with_materials(st, template_rows) -> list[FactorRow]` — grounds on `industry_reference` materials; returns reconciled rows; **verbatim `template_rows` when materials empty OR the LLM errors/returns nothing**. `derive_factor_tree` calls it on the **template baseline path only** (not when the user's own uploaded tree is the baseline).

- [ ] **Step 1: Write the failing test** — add to `_test_factor_reconcile.py` (tests the no-materials fallback without any LLM):

```python
import asyncio
from app.store.state import ProjectState
from app.domain.models import ProjectMeta, Industry

def _bare_state():
    meta = ProjectMeta(id="t", name="t", brand="b",
                       industry=Industry(l1="beverage", l2="functional", l3="sports"))
    return ProjectState(meta=meta)

def test_reconcile_falls_back_without_materials():
    st = _bare_state()   # no uploaded materials in this project
    rows = [_row(0, "市场规模"), _row(1, "GDP增速")]
    out = asyncio.run(B._reconcile_baseline_with_materials(st, rows))
    assert [r.indicator for r in out] == ["市场规模", "GDP增速"]
    assert all(r.status == "baseline" for r in out)   # untouched verbatim
    print("OK reconcile_falls_back_without_materials")
```

and call it from `main()`.

- [ ] **Step 2: Run it, verify it FAILS**

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_factor_reconcile`
Expected: AttributeError — `_reconcile_baseline_with_materials` not defined.

- [ ] **Step 3: Implement the wrapper**:

```python
async def _reconcile_baseline_with_materials(st: ProjectState,
                                             template_rows: list[FactorRow]) -> list[FactorRow]:
    """Reconcile the template baseline against the uploaded materials: keep the
    factors the materials support, rename to align wording, downgrade the ones the
    materials don't mention to 'proposed' (user decides at d-1.21). Verbatim
    fallback when there are no materials or the LLM yields nothing."""
    if not template_rows:
        return template_rows
    materials = sources.category_text(st.project_id, "industry_reference")
    if not materials.strip():
        return template_rows
    numbered = "\n".join(
        f"{i}. {r.l1}/{r.l2}/{r.l3}/{r.l4} · {r.indicator}" for i, r in enumerate(template_rows, 1))
    try:
        obj = await get_llm().json(
            system=agent_system("business", st),
            user=(
                "You are reconciling a standard industry factor-tree template against a "
                "brand's uploaded materials. For EACH numbered template factor, decide:\n"
                "- keep: the materials support this factor as-is.\n"
                "- rename: the materials cover this factor but use different wording — give the "
                "aligned 'indicator' name (keep l1-l4).\n"
                "- downgrade: the materials do NOT mention it or contradict it (do not delete — "
                "it will be offered for the analyst to confirm).\n"
                "Judge against the materials; when unsure, keep. Return JSON: "
                "{\"verdicts\":[{\"n\":int,\"decision\":\"keep|rename|downgrade\","
                "\"indicator\":str,\"rationale\":str}]}\n\n"
                f"TEMPLATE FACTORS:\n{numbered}\n\nMATERIALS:\n{materials[:6000]}"
            ),
        )
    except Exception:  # noqa: BLE001
        obj = {}
    recs = obj.get("verdicts", []) if isinstance(obj, dict) else []
    verdicts: dict[int, dict] = {}
    for rec in recs:
        if not isinstance(rec, dict):
            continue
        try:
            verdicts[int(rec.get("n", 0))] = rec
        except (TypeError, ValueError):
            continue
    if not verdicts:
        return template_rows   # nothing usable → verbatim
    return _apply_reconcile_verdicts(template_rows, verdicts)
```

- [ ] **Step 4: Wire into `derive_factor_tree`** — reconcile the template baseline on the non-upload path. Replace the `else:` baseline assignment (~525-530) so `baseline` is reconciled:

```python
    else:
        if use_upload and not uploaded:
            eng.add_findings(st, task["id"], [_unreadable_upload_finding("a-factor-tree", "Factor Tree")])
        baseline = await _reconcile_baseline_with_materials(st, template_rows)
```

Leave the upload path (`baseline = uploaded`) unchanged. The existing materials AI-add step already computes `existing` from `baseline + supplement`, so renamed baseline rows feed its semantic dedup — no separate dedup needed.

- [ ] **Step 5: Run tests + smoke + build; commit**

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_factor_reconcile` (all OK), `PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py` (pass). From `frontend/`: `npm run build`. Commit.

---

### Task 3: Phase 2 — `data_request_field_edits` store + applied in `gen_data_request`

**Files:**
- Modify: `backend/app/domain/models.py` (add field to `ProjectState` near `factor_map_ignores` ~122)
- Modify: `backend/app/agents/business.py` (`_apply_field_edits` helper + call it inside `gen_data_request` ~1138-1145 grouping)
- Test: `backend/app/agents/_test_datareq_review.py` (create)

**Interfaces:**
- Produces: `ProjectState.data_request_field_edits: dict[str, dict[str, list[str]]]` (alias `dataRequestFieldEdits`) — keyed by an L4 key `"{l3}||{l4}"` → `{"added": [indicator,...], "removed": [indicator,...], "rejected": ["{op}:{indicator}",...]}`. `added`/`removed` are accepted edits applied to the request; `rejected` records dismissed proposals so they are not re-offered (populated by Task 5; `_apply_field_edits` ignores it).
- Produces: `_apply_field_edits(by_l3: dict, edits: dict) -> dict` — given the `by_l3` L3→L4→[indicators] map `gen_data_request` builds, returns a new map with each L4's accepted `added` appended (deduped) and accepted `removed` dropped. Reads only `added`/`removed` (robust to a missing `rejected` key).

- [ ] **Step 1: Write the failing test** — create `backend/app/agents/_test_datareq_review.py`:

```python
"""Runnable checks for interview-driven data-request field edits (no LLM)."""
from app.agents import business as B

def test_apply_field_edits():
    by_l3 = {"品类": {"规模": ["市场规模", "增速"]}, "媒介": {"TV": ["TV花费"]}}
    edits = {
        "品类||规模": {"added": ["季节指数"], "removed": ["增速"]},
        "媒介||TV": {"added": [], "removed": []},
    }
    out = B._apply_field_edits(by_l3, edits)
    assert out["品类"]["规模"] == ["市场规模", "季节指数"], out["品类"]["规模"]  # removed 增速, added 季节指数
    assert out["媒介"]["TV"] == ["TV花费"]                                    # untouched
    # idempotent: a duplicate add is not doubled
    out2 = B._apply_field_edits(out, {"品类||规模": {"added": ["季节指数"], "removed": []}})
    assert out2["品类"]["规模"].count("季节指数") == 1, out2["品类"]["规模"]
    print("OK apply_field_edits")

def main():
    test_apply_field_edits()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it, verify it FAILS**

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_datareq_review`
Expected: AttributeError — `_apply_field_edits` not defined.

- [ ] **Step 3: Add the model field** in `backend/app/domain/models.py` beside `factor_map_ignores`:

```python
    data_request_field_edits: dict[str, dict[str, list[str]]] = Field(
        default_factory=dict, alias="dataRequestFieldEdits")
```

- [ ] **Step 4: Implement `_apply_field_edits`** in `business.py` (above `gen_data_request`):

```python
def _dr_key(l3: str, l4: str) -> str:
    return f"{l3}||{l4}"

def _apply_field_edits(by_l3: dict, edits: dict) -> dict:
    """Apply accepted per-L4 indicator add/removes to the L3→L4→[indicators] map."""
    out: dict = {}
    for l3, l4s in by_l3.items():
        out[l3] = {}
        for l4, indicators in l4s.items():
            e = edits.get(_dr_key(l3, l4), {}) if isinstance(edits, dict) else {}
            removed = set(e.get("removed", []) or [])
            cols = [i for i in indicators if i not in removed]
            for add in e.get("added", []) or []:
                if add and add not in cols:
                    cols.append(add)
            out[l3][l4] = cols
    return out
```

- [ ] **Step 5: Call it in `gen_data_request`** right after the `by_l3` grouping loop is built (~1145, before `index_rows`):

```python
    by_l3 = _apply_field_edits(by_l3, st.data_request_field_edits)
```

- [ ] **Step 6: Run tests + smoke; commit**

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_datareq_review` (OK), `PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py` (pass). Commit `models.py`, `business.py`, the test.

---

### Task 4: Phase 2 — minutes→proposals extraction + attached to the artifact

**Files:**
- Modify: `backend/app/agents/business.py` (`_datareq_proposals` LLM extractor + `_datareq_review_sheet` pure renderer; call both in `gen_data_request`)
- Test: `backend/app/agents/_test_datareq_review.py` (extend)

**Interfaces:**
- Produces: `async _datareq_proposals(st, by_l3) -> list[dict]` — grounds on uploaded `interview_minutes`; each proposal `{"op":"add|remove","l3":str,"l4":str,"indicator":str,"rationale":str,"quote":str}`. Empty list when no minutes or LLM yields nothing. Filters out proposals already **accepted** (indicator in the L4 key's `added`/`removed`) **or rejected** (`"{op}:{indicator}"` in `rejected`) so re-runs never re-offer a decided proposal.
- Produces: `_datareq_review_sheet(proposals: list[dict]) -> dict | None` — a `{"name": "Interview-driven changes (proposed)", "columns": [...], "rows": [...]}` sheet, or `None` when no proposals. Stored on the artifact; `gen_data_request` appends it and also stashes the raw proposals in `st.analysis["data_request_proposals"]` for the review endpoint.

- [ ] **Step 1: Write the failing test** — add to `_test_datareq_review.py` (pure renderer + already-accepted filter; no LLM):

```python
def test_datareq_review_sheet():
    props = [{"op": "add", "l3": "品类", "l4": "规模", "indicator": "季节指数",
              "rationale": "访谈提到", "quote": "我们看季节性"},
             {"op": "remove", "l3": "媒介", "l4": "TV", "indicator": "TV花费",
              "rationale": "不单独跟踪", "quote": "TV没细分"}]
    sheet = B._datareq_review_sheet(props)
    assert sheet is not None and sheet["name"] == "Interview-driven changes (proposed)"
    assert len(sheet["rows"]) == 2
    assert B._datareq_review_sheet([]) is None
    print("OK datareq_review_sheet")
```

and call it from `main()`.

- [ ] **Step 2: Run it, verify it FAILS** (AttributeError).

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_datareq_review`

- [ ] **Step 3: Implement `_datareq_review_sheet`** (pure):

```python
_DR_REVIEW_COLUMNS = ["Op", "L3", "L4", "Indicator", "Rationale", "Quote"]

def _datareq_review_sheet(proposals: list[dict]) -> dict | None:
    if not proposals:
        return None
    rows = [[str(p.get("op", "")), str(p.get("l3", "")), str(p.get("l4", "")),
             str(p.get("indicator", "")), str(p.get("rationale", "")), str(p.get("quote", ""))]
            for p in proposals]
    return {"name": "Interview-driven changes (proposed)", "columns": _DR_REVIEW_COLUMNS, "rows": rows}
```

- [ ] **Step 4: Implement `_datareq_proposals`** (LLM, grounded on minutes, uses `_minutes_files`):

```python
async def _datareq_proposals(st: ProjectState, by_l3: dict) -> list[dict]:
    """From the interview minutes, propose per-L4 data-request indicator add/removes.
    Empty when no minutes. Skips proposals already recorded in data_request_field_edits."""
    files = _minutes_files(st)
    if not files:
        return []
    structure = "\n".join(
        f"- {l3} / {l4}: {', '.join(inds) or '—'}" for l3, l4s in by_l3.items() for l4, inds in l4s.items())
    minutes = "\n\n".join(f"[{fn}]\n{tx}" for fn, tx in files)[:8000]
    try:
        obj = await get_llm().json(
            system=agent_system("business", st),
            user=(
                "Given the DATA REQUEST structure (L3/L4 → indicators to collect) and the interview "
                "minutes, propose indicator FIELD changes ONLY (not factor changes):\n"
                "- add: the minutes say a metric is needed/available for an L4 that the request lacks.\n"
                "- remove: the minutes say a listed indicator is NOT available / not tracked.\n"
                "Each l3/l4/indicator must match the structure's wording (for 'add', a new indicator "
                "under an existing l3/l4). Ground every proposal in a verbatim quote. Return JSON: "
                "{\"proposals\":[{\"op\":\"add|remove\",\"l3\":str,\"l4\":str,\"indicator\":str,"
                "\"rationale\":str,\"quote\":str}]}\n\n"
                f"DATA REQUEST STRUCTURE:\n{structure}\n\nINTERVIEW MINUTES:\n{minutes}"
            ),
        )
    except Exception:  # noqa: BLE001
        obj = {}
    raw = obj.get("proposals", []) if isinstance(obj, dict) else []
    edits = st.data_request_field_edits
    out: list[dict] = []
    for p in raw:
        if not isinstance(p, dict) or str(p.get("op", "")) not in ("add", "remove"):
            continue
        key = _dr_key(str(p.get("l3", "")), str(p.get("l4", "")))
        ind = str(p.get("indicator", "")).strip()
        acc = edits.get(key, {}) if isinstance(edits, dict) else {}
        if ind in (acc.get("added", []) or []) or ind in (acc.get("removed", []) or []):
            continue   # already accepted
        if f"{p['op']}:{ind}" in (acc.get("rejected", []) or []):
            continue   # already rejected — don't re-offer (sticky reject)
        out.append({"op": str(p["op"]), "l3": str(p.get("l3", "")), "l4": str(p.get("l4", "")),
                    "indicator": ind, "rationale": str(p.get("rationale", "")), "quote": str(p.get("quote", ""))})
    return out
```

- [ ] **Step 5: Wire both into `gen_data_request`** — after `by_l3 = _apply_field_edits(...)` (Task 3) and before the final `eng.produce`:

```python
    proposals = await _datareq_proposals(st, by_l3)
    eng.set_analysis(st, "data_request_proposals", proposals)
    review_sheet = _datareq_review_sheet(proposals)
    if review_sheet is not None:
        sheets.append(review_sheet)
```

- [ ] **Step 6: Run tests + smoke; commit**

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_datareq_review` (all OK), smoke pass. Commit.

---

### Task 5: Phase 2 — `PUT /data-request/review` endpoint + client method

**Files:**
- Modify: `backend/app/main.py` (new endpoint near the anomaly-review handler ~1020)
- Modify: `frontend/src/api/client.ts` (a `reviewDataRequest` method near `updateAnomalyReview` ~210)
- Test: `backend/app/agents/_test_datareq_review.py` (extend with an endpoint-level control-flow check via the engine, no HTTP)

**Interfaces:**
- Consumes: `st.data_request_field_edits` (Task 3), `_apply_field_edits`/`gen_data_request` re-render.
- Produces: `PUT /api/projects/{project_id}/data-request/review` — body `{op, l3, l4, indicator, accept: bool}`. On `accept=true`: record the indicator under the L4 key's `added` (op=add) or `removed` (op=remove) in `data_request_field_edits`. On `accept=false`: no edit recorded (the proposal is simply dismissed). Then re-run the `1.5` producer so `a-data-request` re-renders, save, and return the refreshed edit-store.

- [ ] **Step 1: Write the failing test** — add a control-flow test that records an accept and asserts the column appears after a re-render. Add to `_test_datareq_review.py`:

```python
def test_record_edit_then_rerender_applies():
    # Simulate the endpoint's core: record an accepted 'add' then re-derive columns.
    st = None  # built inline below
    from app.store.state import ProjectState
    from app.domain.models import ProjectMeta, Industry
    st = ProjectState(meta=ProjectMeta(id="t", name="t", brand="b",
        industry=Industry(l1="beverage", l2="functional", l3="sports")))
    st.data_request_field_edits.setdefault("品类||规模", {"added": [], "removed": []})
    st.data_request_field_edits["品类||规模"]["added"].append("季节指数")
    by_l3 = {"品类": {"规模": ["市场规模"]}}
    applied = B._apply_field_edits(by_l3, st.data_request_field_edits)
    assert applied["品类"]["规模"] == ["市场规模", "季节指数"]
    print("OK record_edit_then_rerender_applies")
```

and call it from `main()`. (The HTTP endpoint itself is exercised by the smoke test's app import; this pins the record→apply contract the endpoint relies on.)

- [ ] **Step 2: Run it, verify it FAILS or PASSES** — this asserts existing `_apply_field_edits` (Task 3) over a manually-recorded edit; it should PASS once Task 3 is in. If Task 5 is implemented in isolation, run to confirm green before touching the endpoint (it guards the contract the endpoint depends on).

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_datareq_review`

- [ ] **Step 3: Add the endpoint** in `main.py` (mirror `update_anomaly_review`; the re-render uses the exact same mechanism as the `factor-map/ignore` handler — `await _engine.handlers["<id>"](_engine, st, bp.TASK_MAP["<id>"])` guarded on the artifact existing). `_engine`, `bp`, `_require_state`, `get_store` are already in scope in `main.py`:

```python
class DataRequestReviewBody(BaseModel):
    op: str            # "add" | "remove"
    l3: str
    l4: str
    indicator: str
    accept: bool

@app.put("/api/projects/{project_id}/data-request/review")
async def review_data_request(project_id: str, body: DataRequestReviewBody) -> dict:
    """Accept/reject one interview-driven data-request field proposal. Accept records
    the add/remove in data_request_field_edits and re-renders a-data-request; reject
    dismisses it. Never touches the factor tree."""
    st = _require_state(project_id)
    if body.op in ("add", "remove") and body.indicator.strip():
        key = f"{body.l3}||{body.l4}"
        entry = st.data_request_field_edits.setdefault(key, {"added": [], "removed": [], "rejected": []})
        entry.setdefault("rejected", [])
        if body.accept:
            bucket = "added" if body.op == "add" else "removed"
            if body.indicator not in entry[bucket]:
                entry[bucket].append(body.indicator)
        else:  # sticky reject — record so _datareq_proposals never re-offers it
            tag = f"{body.op}:{body.indicator}"
            if tag not in entry["rejected"]:
                entry["rejected"].append(tag)
    # Re-render a-data-request if it exists (same mechanism as factor-map/ignore → 2.1).
    if st.artifact("a-data-request") is not None:
        await _engine.handlers["1.5"](_engine, st, bp.TASK_MAP["1.5"])
    get_store().save(project_id)
    return {"dataRequestFieldEdits": st.data_request_field_edits}
```

Both accept and reject are sticky: accept records the add/remove (applied by `_apply_field_edits`), reject records `"{op}:{indicator}"` in the L4 key's `rejected` bucket, and `_datareq_proposals` (Task 4) filters both out so a decided proposal never re-appears.

- [ ] **Step 4: Add the client method** in `frontend/src/api/client.ts` beside `updateAnomalyReview`:

```typescript
  reviewDataRequest: (projectId: string, body: { op: string; l3: string; l4: string; indicator: string; accept: boolean }) =>
    req<{ dataRequestFieldEdits: Record<string, { added: string[]; removed: string[] }> }>(
      `${p(projectId)}/data-request/review`, { method: 'PUT', body: JSON.stringify(body) }),
```

- [ ] **Step 5: Run gates; commit**

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_datareq_review` (OK), `PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py` (pass — the app imports with the new route). From `frontend/`: `npm run build`. Commit.

---

### Task 6: Phase 2 — data-request review panel (frontend)

**Files:**
- Create: `frontend/src/components/project/panels/DataRequestReviewPanel.tsx` (mirror `AnomalyReviewPanel.tsx`)
- Modify: the artifact/task panel that renders `a-data-request` (find where `AnomalyReviewPanel` is mounted — `TaskStepPanel.tsx` / `ArtifactDetail.tsx` — and mount `DataRequestReviewPanel` for the `1.5` / `a-data-request` context)
- Modify: `frontend/src/lib/types.ts` (a minimal `DataRequestProposal` type for the panel props)

**Interfaces:**
- Consumes: the pending proposals (from the re-rendered `a-data-request` "Interview-driven changes (proposed)" sheet, or a dedicated `state.analysis` read if the panel is wired to state) and `api.reviewDataRequest` (Task 5).
- Produces: a per-row Accept/Reject panel; on click it calls `reviewDataRequest` and refreshes.

- [ ] **Step 1: Read the mirror** — read `frontend/src/components/project/panels/AnomalyReviewPanel.tsx` fully and how it is mounted (grep `AnomalyReviewPanel` under `frontend/src/components`). Reproduce its structure: list items, per-item Accept/Reject buttons, an API call, a refresh.

- [ ] **Step 2: Add the `DataRequestProposal` type** to `frontend/src/lib/types.ts`:

```typescript
export interface DataRequestProposal {
  op: 'add' | 'remove'
  l3: string
  l4: string
  indicator: string
  rationale: string
  quote: string
}
```

- [ ] **Step 3: Create `DataRequestReviewPanel.tsx`** — a list of the pending `DataRequestProposal`s, each with its `op`/`l3`/`l4`/`indicator`/`rationale`/`quote` and Accept / Reject buttons that call `api.reviewDataRequest(projectId, { op, l3, l4, indicator, accept })` then trigger the store's project refresh (mirror how `AnomalyReviewPanel` refreshes after `updateAnomalyReview`). Source the proposals the same way `AnomalyReviewPanel` sources its anomalies (read the mirror to see whether it reads from the artifact body or from state, and match it).

- [ ] **Step 4: Mount it** where the `a-data-request` artifact / `1.5` task renders — the same host that mounts `AnomalyReviewPanel` for its task. Gate its visibility on there being pending proposals.

- [ ] **Step 5: Run gates; commit**

Run (from `frontend/`): `npm run build` (tsc + vite) and `npm run lint`. Commit.

---

## Self-Review

**Spec coverage:**
- Phase 1 reconcile (keep/rename/downgrade, verbatim fallback, d-1.21 reuse) → Tasks 1-2. ✅
- Phase 1 dedup against AI factors → Task 2 Step 4 note (existing AI-add prompt sees renamed baseline via `existing`). ✅
- Phase 2 proposal extraction from minutes, not auto-applied → Task 4. ✅
- Phase 2 edit-store + apply into request → Task 3. ✅
- Phase 2 review endpoint (accept→record, reject→dismiss, re-render) + client → Task 5. ✅
- Phase 2 review panel → Task 6. ✅
- No new gate / blueprint unchanged / factor-tree untouched → enforced in Global Constraints and Task 5's scope note. ✅
- types.ts only gains a small proposal type → Task 6 Step 2. ✅

**Placeholder scan:** One deliberate placeholder remains — Task 5 Step 3's `<re-run the 1.5 producer>` — because the exact re-render call must be copied from the project's existing `factor-map/ignore` handler rather than guessed; the step names that source file and the mechanism to copy. All other steps carry real code.

**Type consistency:** `_dr_key(l3, l4)` → `"{l3}||{l4}"` used identically in Tasks 3, 4, 5. `data_request_field_edits` shape `{key: {"added": [], "removed": []}}` consistent across model (Task 3), extractor filter (Task 4), endpoint (Task 5). Proposal dict keys `{op,l3,l4,indicator,rationale,quote}` consistent Tasks 4-6. `_apply_field_edits(by_l3, edits)` and `_apply_reconcile_verdicts(template_rows, verdicts)` signatures match their call sites.
