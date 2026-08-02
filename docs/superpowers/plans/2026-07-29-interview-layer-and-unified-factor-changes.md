# Interview layer-from-filename + unified factor-tree add/remove — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) derive the interview target's layer literally from the file name (blank if absent); (2) tag every factor-tree proposal with an add/remove direction, add interview-driven removal, make the gate auto-accept only add-rows, and split the editor into 全部/建议新增/建议删减 tabs; (3) remove the now-redundant data-request interview-review so the data request is a pure projection of the confirmed factor tree.

**Architecture:** Backend changes live in `backend/app/agents/business.py` + one field on `FactorRow` (`domain/models.py`); the frontend touches `FactorTreeEditor.tsx` + `lib/types.ts` and deletes the data-request review panel. No blueprint/scenario/DAG change; reuse the `proposed→accepted/rejected` status machine and the existing d-1.21/d-1.4 gates.

**Tech Stack:** Python 3.12 / FastAPI (runnable `_test_*` scripts, no pytest), React/Vite/TS frontend, Volcano Ark LLM.

## Global Constraints

- **No new status, gate, or DAG task.** `blueprint.py` / `scenario.ts` DAG unchanged. Reuse `proposed→accepted/rejected` and d-1.21/d-1.4.
- **`FactorRow.proposal_kind`** is `Literal["add","remove"] | None` (alias `proposalKind`); **`None`/absent ⇒ treated as `add`** (back-compat for saved projects — no migration).
- **Gate approve finalizes BOTH directions:** `accept_factor_rows` flips proposed rows of its source-set — **add-kind → `accepted`** (include) and **remove-kind → `rejected`** (confirm the removal, the user's chosen default-remove). Nothing is left `proposed` after approve. Per-row before approve the user can still set a remove row 保留→`accepted` (kept, then approve skips it since it's no longer proposed) or 确认删减→`rejected`.
- **Layer is literal** from the file name (`Layer\d+` / `第N层` / 高层·管理层·执行层·数据团队), blank when absent. No mapping.
- **Data request reverts to a pure factor-tree projection.** Remove ALL 2026-07-28 Phase-2 data-request-review machinery (no `data_request_field_edits`, no proposals, no review panel/endpoint).
- **Tests are runnable scripts** (`PYTHONPATH=. .venv/bin/python -m <module>` from `backend/`; venv `backend/.venv`).
- **Git is initialized**; create feature branch `feature/interview-layer-factor-changes`. Each task ends green + committed (trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`).
- Existing shapes: `FactorRow{id,l1,l2,l3,l4,indicator,dimension,source,status,rationale,evidence}`; a real-interview target dict `{id,layer,layerZh,team,participants,schedule,durationMin,status,questions}`.

---

### Task 1: Interview layer from the file name

**Files:**
- Modify: `backend/app/agents/business.py` (add `_layer_from_filename` near `_DEPT_TRAILING` ~840; update `_department_from_filename` ~842, `_make_real_target` ~865, `_rebuild_targets_from_real_minutes` ~888-919)
- Test: `backend/app/agents/_test_interview.py` (extend)

**Interfaces:**
- Produces: `_layer_from_filename(filename: str) -> str` — literal layer marker (`Layer\d+`, `第[0-9一二三四五六七八九十]+层`, or a Chinese layer word `高层|管理层|执行层|数据团队`) found in the name, else `""`.
- `_make_real_target(department, participants, questions, layer="")` — `layer` now a param; `layerZh = layer`, internal `layer` field also = the literal (or `""`); `team = department`.

- [ ] **Step 1: Write the failing test** — add to `_test_interview.py`:

```python
def test_layer_from_filename():
    f = B._layer_from_filename
    assert f("Layer3_电商部_纪要.txt") == "Layer3", f("Layer3_电商部_纪要.txt")
    assert f("第2层_管理层访谈.docx") == "第2层", f("第2层_管理层访谈.docx")
    assert f("管理层_商务部访谈.docx") == "管理层", f("管理层_商务部访谈.docx")
    assert f("商务部访谈.docx") == "", f("商务部访谈.docx")   # no layer marker → blank
    print("OK layer_from_filename")

def test_real_target_layer_and_dept():
    # filename with a layer marker: layer literal + clean department
    biz = []
    files = [("Layer3_电商部_纪要.txt", "..."), ("商务部访谈.docx", "...")]
    results = [{"department": "", "answers": [], "new_questions": []},
               {"department": "", "answers": [], "new_questions": []}]
    t = B._rebuild_targets_from_real_minutes(biz, files, results)
    assert t[0]["layerZh"] == "Layer3" and t[0]["team"] == "电商部", t[0]
    assert t[1]["layerZh"] == "" and t[1]["team"] == "商务部", t[1]   # no layer → blank
    print("OK real_target_layer_and_dept")
```

and call both from `main()`.

- [ ] **Step 2: Run it, verify it FAILS**

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_interview`
Expected: AttributeError (`_layer_from_filename`), and the target test fails (layerZh currently = department).

- [ ] **Step 3: Add `_layer_from_filename`** (next to `_DEPT_TRAILING`):

```python
_LAYER_IN_FILENAME = re.compile(
    r"(layer\d+|第[0-9一二三四五六七八九十]+层|高层|管理层|执行层|数据团队)", re.IGNORECASE)

def _layer_from_filename(filename: str) -> str:
    """The layer marker literally as written in the file name, else ''. No mapping."""
    stem = os.path.splitext(os.path.basename(filename or ""))[0]
    m = _LAYER_IN_FILENAME.search(stem)
    return m.group(1) if m else ""
```

- [ ] **Step 4: Strip the layer word in `_department_from_filename`** so the department stays clean when the layer is a Chinese word (the `Layer\d+`/`第N层` prefix is already stripped by `_DEPT_PREFIX`). After the `_DEPT_PREFIX.sub` line add a one-shot strip of a leading Chinese layer word:

```python
    stem = _DEPT_PREFIX.sub("", stem)
    stem = re.sub(r"^(?:高层|管理层|执行层|数据团队)[ _\-·]+", "", stem)   # layer word prefix
```

(leave the trailing-marker peel loop unchanged.)

- [ ] **Step 5: Thread the layer through** — change `_make_real_target` signature and the call site:

```python
def _make_real_target(department: str, participants: str, questions: list[dict], layer: str = "") -> dict:
    return {
        "id": _target_id(layer or "field", department), "layer": layer, "layerZh": layer,
        "team": department, "participants": participants or "", "schedule": "",
        "durationMin": 0, "status": "completed", "questions": questions,
    }
```

and in `_rebuild_targets_from_real_minutes`, compute the layer per file and pass it (the last line of the loop):

```python
        layer = _layer_from_filename(filename)
        targets.append(_make_real_target(dept, str(res.get("participants") or ""), rows, layer))
```

- [ ] **Step 6: Run tests + smoke; commit**

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_interview` (all OK) and `PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py` (pass). Commit.

---

### Task 2: `proposal_kind` on FactorRow + producers + gate direction

**Files:**
- Modify: `backend/app/domain/models.py` (`FactorRow` ~407-419)
- Modify: `frontend/src/lib/types.ts` (the `FactorRow` interface — add `proposalKind`)
- Modify: `backend/app/agents/business.py` (`_apply_reconcile_verdicts` ~239; the AI-add `FactorRow(...)` in `derive_factor_tree`; `_ai_template_supplement` + `_keydiff_supplement`; the interview `FactorRow(...)` ~1084-1093; `accept_factor_rows` ~1005-1007)
- Test: `backend/app/agents/_test_factor_reconcile.py` (extend)

**Interfaces:**
- Produces: `FactorRow.proposal_kind: Optional[Literal["add","remove"]]` (alias `proposalKind`, default `None`). Reconcile downgrade → `"remove"`; every other proposed producer (AI materials-add, template supplements, interview add/modify) → `"add"`.
- `accept_factor_rows(st, source_set)` flips proposed rows of its source-set: `proposal_kind == "remove"` → `rejected`; otherwise → `accepted`.

- [ ] **Step 1: Write the failing test** — add to `_test_factor_reconcile.py`:

```python
def test_downgrade_sets_remove_kind():
    rows = [_row(0, "天气温度指数")]
    out = B._apply_reconcile_verdicts(rows, {1: {"decision": "downgrade", "rationale": "材料未提及"}})
    assert out[0].status == "proposed" and out[0].proposal_kind == "remove", out[0]
    print("OK downgrade_sets_remove_kind")

def test_accept_factor_rows_direction():
    from app.store.state import ProjectState
    from app.domain.models import ProjectMeta, IndustryRef, FactorTree, FactorRow
    st = ProjectState(meta=ProjectMeta(id="t", name="t", brand="b", createdAt="2026-01-01T00:00:00+00:00",
        industry=IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional")))
    add = FactorRow(id="a", indicator="x", source="ai", status="proposed", proposalKind="add")
    rem = FactorRow(id="b", indicator="y", source="template", status="proposed", proposalKind="remove")
    st.factor_tree = FactorTree(rows=[add, rem])
    B.accept_factor_rows(st, {"ai", "template"})
    assert st.factor_tree.rows[0].status == "accepted", "add-kind → accepted"
    assert st.factor_tree.rows[1].status == "rejected", "remove-kind → rejected (confirm removal)"
    print("OK accept_factor_rows_direction")
```

and call both from `main()`.

- [ ] **Step 2: Run it, verify it FAILS**

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_factor_reconcile`
Expected: FAIL — `proposal_kind` not a field / `accept_factor_rows` accepts the remove row.

- [ ] **Step 3: Add the model field** in `domain/models.py` `FactorRow` (after `evidence`):

```python
    proposal_kind: Optional[Literal["add", "remove"]] = Field(default=None, alias="proposalKind")
```

(ensure `Optional`/`Literal` are imported — they are used elsewhere in the file.)

- [ ] **Step 4: Mirror in `frontend/src/lib/types.ts`** — add to the `FactorRow` interface: `proposalKind?: 'add' | 'remove'`.

- [ ] **Step 5: Set `proposal_kind` in every producer** (business.py):
  - `_apply_reconcile_verdicts` downgrade branch → add `"proposal_kind": "remove"` to the `model_copy(update={...})`.
  - The AI-add `FactorRow(...)` in `derive_factor_tree` (`source="ai", status="proposed"`) → add `proposal_kind="add"`.
  - `_ai_template_supplement` and `_keydiff_supplement` rows (`source="template", status="proposed"`) → add `proposal_kind="add"`.
  - The interview `FactorRow(...)` at ~1085 (`source="interview", status="proposed"`) → add `proposal_kind="add"` (Task 3 splits out the removes).

- [ ] **Step 6: Make the gate finalize by direction** — `accept_factor_rows` (~1005-1007):

```python
    for r in st.factor_tree.rows:
        if r.status == "proposed" and r.source in source_set:
            r.status = "rejected" if r.proposal_kind == "remove" else "accepted"
```

- [ ] **Step 7: Run tests + smoke + build; commit**

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_factor_reconcile` (all OK), `PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py` (pass); from `frontend/`: `npm run build`. Commit.

---

### Task 3: Interview-driven removal

**Files:**
- Modify: `backend/app/agents/business.py` (`_digest_transcript` prompt ~982; add `_apply_interview_removals`; split adds/removes in `writeback_minutes` ~1071-1105)
- Test: `backend/app/agents/_test_interview.py` (extend)

**Interfaces:**
- Consumes: `FactorRow.proposal_kind` (Task 2).
- Produces: `_apply_interview_removals(st, changes) -> int` — for each change with `op=="remove"`, demote matching existing tree rows (status `baseline`/`accepted`) to `status="proposed", source="interview", proposal_kind="remove"` with the change's rationale/quote; returns the count demoted. Match rule: a row matches when its `indicator` equals the change's `indicator` (case-insensitive, stripped) if the change gives one, else when `(l3,l4)` both match. No match → skip (never fabricate).

- [ ] **Step 1: Write the failing test** — add to `_test_interview.py`:

```python
def test_apply_interview_removals():
    from app.store.state import ProjectState
    from app.domain.models import ProjectMeta, IndustryRef, FactorTree, FactorRow
    st = ProjectState(meta=ProjectMeta(id="t", name="t", brand="b", createdAt="2026-01-01T00:00:00+00:00",
        industry=IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional")))
    keep = FactorRow(id="k", l3="电商", l4="平台", indicator="电商GMV", source="template", status="baseline")
    drop = FactorRow(id="d", l3="批发", l4="经销", indicator="经销商出货", source="template", status="accepted")
    st.factor_tree = FactorTree(rows=[keep, drop])
    n = B._apply_interview_removals(st, [{"op": "remove", "indicator": "经销商出货",
                                          "rationale": "没有月度台账", "quote": "经销出货没系统数据"}])
    assert n == 1, n
    d = next(r for r in st.factor_tree.rows if r.id == "d")
    assert d.status == "proposed" and d.proposal_kind == "remove" and d.source == "interview", d
    k = next(r for r in st.factor_tree.rows if r.id == "k")
    assert k.status == "baseline", "non-matching row untouched"
    # a remove with no matching row demotes nothing
    assert B._apply_interview_removals(st, [{"op": "remove", "indicator": "不存在指标"}]) == 0
    print("OK apply_interview_removals")
```

and call from `main()`.

- [ ] **Step 2: Run it, verify it FAILS** (AttributeError).

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_interview`

- [ ] **Step 3: Implement `_apply_interview_removals`** (place just above `writeback_minutes`):

```python
def _apply_interview_removals(st: ProjectState, changes: list[dict]) -> int:
    """Demote existing factor rows the interview says to drop → proposed + remove
    (source=interview), so they surface in the 建议删减 tab. Returns count demoted."""
    if st.factor_tree is None:
        return 0
    n = 0
    for ch in changes:
        if not isinstance(ch, dict) or str(ch.get("op", "")) != "remove":
            continue
        ind = str(ch.get("indicator", "")).strip().lower()
        l3, l4 = str(ch.get("l3", "")).strip(), str(ch.get("l4", "")).strip()
        for r in st.factor_tree.rows:
            if r.status not in ("baseline", "accepted"):
                continue
            hit = (ind and r.indicator.strip().lower() == ind) or \
                  (not ind and l3 and l4 and r.l3 == l3 and r.l4 == l4)
            if not hit:
                continue
            r.status = "proposed"
            r.source = "interview"
            r.proposal_kind = "remove"
            r.rationale = f"访谈建议删减 · {ch.get('rationale', '')}"
            r.evidence = str(ch.get("quote", ""))[:200]
            n += 1
    return n
```

- [ ] **Step 4: Extend the `_digest_transcript` prompt** (~982) to allow `op=remove`: change `"\"op\":\"add|modify\""` → `"\"op\":\"add|modify|remove\""`, and add one sentence to the FACTOR CHANGES instruction: `"Use op=remove ONLY when the interview explicitly says an existing factor should be dropped / is not needed / has no usable data — name its l3/l4/indicator."`

- [ ] **Step 5: Split adds vs removes in `writeback_minutes`** — where `changes = merged["factor_changes"]` is handled (~1074), partition and route:

```python
    changes = merged["factor_changes"]
    removes = [c for c in changes if isinstance(c, dict) and str(c.get("op", "")) == "remove"]
    adds = [c for c in changes if c not in removes]
    removed_n = _apply_interview_removals(st, removes)
    if removed_n:
        eng.produce(st, "a-factor-tree", body=_factor_tree_sheet(st.factor_tree),
                    state="proposed", agent="business")
        eng.emit(st, "business", "info",
                 f"{removed_n} factor(s) demoted to 建议删减 from the interviews.", task["id"])
    changes = adds   # the existing add/modify block below runs on adds only
```

Leave the existing add block (new `FactorRow(... proposal_kind="add" ...)`, dedup, produce, proposals) as-is but operating on `changes` (= adds). (The interview `FactorRow` already got `proposal_kind="add"` in Task 2 Step 5.)

- [ ] **Step 6: Run tests + smoke; commit**

Run: `PYTHONPATH=. .venv/bin/python -m app.agents._test_interview` (all OK), smoke pass. Commit.

---

### Task 4: Factor-tree editor — 全部 / 建议新增 / 建议删减 tabs

**Files:**
- Modify: `frontend/src/components/project/FactorTreeEditor.tsx`
- (consumes `FactorRow.proposalKind` from Task 2)

**Interfaces:** none downstream (leaf UI). Consumes `proposalKind` + existing `updateFactorTree`.

- [ ] **Step 1: Replace the filter state + derived groups.** Change `filter` from `'all' | 'proposed'` to `'all' | 'add' | 'remove'`. Classify a proposed row: `isRemove = r.status === 'proposed' && r.proposalKind === 'remove'`; `isAdd = r.status === 'proposed' && !isRemove`. Compute `addCount`/`removeCount`. `visible` = all rows (filter all) / add-proposed (filter add) / remove-proposed (filter remove).

- [ ] **Step 2: Replace the header badges + tab control.** Replace the single `{proposedCount} AI proposed` badge with two: `{addCount} 建议新增` and `{removeCount} 建议删减` (show each only when >0). Replace the two-button `All / AI only` group with three: `全部 / 建议新增 / 建议删减`. Change the subtitle from "accept or reject each AI recommendation" to `因子基线来自行业模板并与上传材料对账；下方按"新增/删减"确认每条建议。`.

- [ ] **Step 3: Direction-correct confirm buttons.** In the Confirm cell for a `proposed` row, branch on `r.proposalKind === 'remove'`:
  - remove-kind: **确认删减** button → `setStatus(r.id, 'rejected')`; **保留** button → `setStatus(r.id, 'accepted')`.
  - add-kind (else): keep the current **accept**(→`accepted`) / **reject**(→`rejected`) but relabel titles to `加入` / `忽略`.

- [ ] **Step 4: Show rationale for all proposed + mark remove rows.** Change the input `title` from `r.source === 'ai' ? r.rationale : undefined` to `r.status === 'proposed' ? r.rationale : undefined` (so conflict/removal reasons show). Give remove-kind rows an amber accent (e.g. add a `⚠` before the L1 cell or an amber row class) so they read as removals.

- [ ] **Step 5: Keep ONE bulk "approve", direction-aware.** Do NOT split into two buttons. Keep a single `全部确认` action (shown when any proposed rows exist) that applies every proposed row by direction — mirroring the gate `accept_factor_rows`:

```tsx
function approveAll() {
  commit(rows.map((r) =>
    r.status === 'proposed'
      ? { ...r, status: r.proposalKind === 'remove' ? 'rejected' : 'accepted' }
      : r))
}
```

i.e. 建议新增 → `accepted`(加入), 建议删减 → `rejected`(删除). Per-row buttons (Step 3) remain for overriding individual rows before clicking 全部确认.

- [ ] **Step 6: Build + lint; commit**

Run (from `frontend/`): `npm run build` (must pass) and `npm run lint` (no new errors). Commit.

---

### Task 5: Remove data-request interview-review (backend)

**Files:**
- Modify: `backend/app/agents/business.py` (delete `_dr_key` ~1193, `_apply_field_edits` ~1197, `_DR_REVIEW_COLUMNS` ~1218, `_datareq_review_sheet` ~1221, `_filter_proposals` ~1232, `_datareq_proposals` ~1256; and the calls in `gen_data_request` ~1310, ~1339-1343)
- Modify: `backend/app/store/state.py` (delete `data_request_field_edits`)
- Modify: `backend/app/main.py` (delete `review_data_request` endpoint + `DataRequestReviewBody`)
- Delete: `backend/app/agents/_test_datareq_review.py`

**Interfaces:** `gen_data_request` reverts to projecting `by_l3` straight from the factor tree (no field edits, no proposals, no review sheet).

- [ ] **Step 1: Revert `gen_data_request`.** Delete the `by_l3 = _apply_field_edits(...)` line (~1310) and the proposals/review-sheet block (~1339-1343: the `_datareq_proposals` call, `set_analysis("data_request_proposals", ...)`, `_datareq_review_sheet` append). The `eng.produce("a-data-request", ...)` + emit stay.

- [ ] **Step 2: Delete the now-unused helpers** `_dr_key`, `_apply_field_edits`, `_DR_REVIEW_COLUMNS`, `_datareq_review_sheet`, `_filter_proposals`, `_datareq_proposals` from business.py.

- [ ] **Step 3: Delete the state field** `data_request_field_edits` in `store/state.py`.

- [ ] **Step 4: Delete the endpoint** `review_data_request` + `DataRequestReviewBody` class in `main.py`.

- [ ] **Step 5: Delete the test file** `backend/app/agents/_test_datareq_review.py`.

- [ ] **Step 6: Confirm no dangling references.**

Run (from `backend/`): `grep -rnE "data_request_field_edits|_apply_field_edits|_datareq_proposals|_datareq_review_sheet|_filter_proposals|_dr_key|_DR_REVIEW_COLUMNS|review_data_request|DataRequestReviewBody|data_request_proposals" app | grep -v _pycache`
Expected: zero matches.

- [ ] **Step 7: Run gates; commit.**

Run: `PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py` (app imports with the route gone), `PYTHONPATH=. .venv/bin/python -m app.agents._test_interview` and `-m app.agents._test_factor_reconcile` (unaffected, pass). Commit.

---

### Task 6: Remove data-request interview-review (frontend)

**Files:**
- Modify: `frontend/src/api/client.ts` (delete `reviewDataRequest`)
- Delete: `frontend/src/components/project/panels/DataRequestReviewPanel.tsx`
- Modify: `frontend/src/components/project/ArtifactDetail.tsx` (remove the `DataRequestReviewPanel` import + mount)
- Modify: `frontend/src/lib/types.ts` (delete `DataRequestProposal`)

- [ ] **Step 1: Remove the mount + import** of `DataRequestReviewPanel` in `ArtifactDetail.tsx` (the `task.id === '1.5'` branch added for it).

- [ ] **Step 2: Delete** `DataRequestReviewPanel.tsx`, the `reviewDataRequest` client method, and the `DataRequestProposal` type.

- [ ] **Step 3: Confirm no dangling references.**

Run (from `frontend/`): `grep -rnE "reviewDataRequest|DataRequestReviewPanel|DataRequestProposal" src`
Expected: zero matches.

- [ ] **Step 4: Build + lint; commit.**

Run (from `frontend/`): `npm run build` (tsc + vite must pass — a dangling reference would fail tsc) and `npm run lint` (no new errors). Commit.

---

## Self-Review

**Spec coverage:**
- Feature 1 (layer from filename, literal/blank, clean dept) → Task 1. ✅
- Feature 2 backend (proposal_kind, producers, gate skips remove) → Task 2; interview removal → Task 3. ✅
- Feature 2 frontend (3 tabs, direction verbs, rationale for all, remove visual) → Task 4. ✅
- Feature 3 (remove data-request review, pure projection) → Task 5 (backend) + Task 6 (frontend). ✅
- Gate/bulk default-remove for un-actioned remove rows → Task 2 Step 6 (approve: add→accepted, remove→rejected) + Task 4 Step 5 (single `全部确认` mirrors it). ✅
- Back-compat (None→add) → Task 2 Step 3 default + Task 4 classification (`proposalKind === 'remove'` only). ✅

**Placeholder scan:** No TBD/TODO; every code step carries real code or an exact grep/edit. The `derive_factor_tree` AI-add and `_ai_template_supplement`/`_keydiff_supplement` edits (Task 2 Step 5) are described as "add `proposal_kind="add"` to the existing `FactorRow(...)`/`model_copy`" — concrete one-field additions to code already in the file, not new logic.

**Type consistency:** `proposal_kind`/`proposalKind` (`"add"|"remove"|None`) consistent across models.py (Task 2), types.ts (Task 2), producers (Task 2/3), `accept_factor_rows` (Task 2), and the editor classification (Task 4). `_apply_interview_removals(st, changes)->int`, `_layer_from_filename(filename)->str`, `_make_real_target(department, participants, questions, layer="")` signatures match their call sites.
