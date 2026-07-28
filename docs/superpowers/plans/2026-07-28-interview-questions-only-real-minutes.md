# Interview Questions-Only + Real-Minutes Restructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the interview outline questions-only (drop AI pre-answers), and on minutes upload rebuild the interview into the client's real departments (from file names) with backfilled outline answers + extracted new questions — leaving the factor-tree writeback untouched.

**Architecture:** Change three seams in `backend/app/agents/business.py` plus the blueprint/scenario contract. (1) Remove task `1.3b` and its handler. (2) Add an `origin` field to interview-question dicts and simplify the sheet columns. (3) Replace the question-number merge in `writeback_minutes` with a per-file, per-department rebuild; extend the per-transcript LLM digest to also return `department`/`participants`/`new_questions`. Factor-change/insight extraction is refactored out unchanged.

**Tech Stack:** Python 3.12 / FastAPI backend (dependency-light, no pytest — runnable `_test_*` scripts), React/Vite/TS frontend (contract mirror only). Volcano Ark LLM for the digest call.

## Global Constraints

- **No mock data.** Every number/answer traces to a real uploaded transcript through the real path. Do not fabricate minutes to make a run pass. (Spec §Global.)
- **Factor-tree writeback is out of scope and must not change** — `factor_changes` → `proposed` rows → `d-1.4` gate → data request stay byte-for-byte behavior-equivalent.
- **`a-interview` is a generic `sheets` artifact — NO `frontend/src/lib/types.ts` change.** Column edits are backend-only.
- **Git is initialized for this run** (feature branch `feature/interview-questions-only`). Each task ends by running its verification gate green **and committing** the task's changes (`git add` the touched files, then a descriptive commit ending with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer).
- **Tests are runnable scripts**, not pytest. Backend scripts run from `backend/` as `PYTHONPATH=. .venv/bin/python -m <module>` or `.venv/bin/python -m <module>`.
- **Contract sync:** any blueprint task change in `app/domain/blueprint.py` must be mirrored in `frontend/src/lib/scenario.ts`.
- Interview runtime state is plain dicts in `st.analysis["interview_targets"]`; a question dict has keys `qType, question, relatedFactorPath, preAnswer, confidence, sources` and gains `finalAnswer, answerSource` during writeback. A target dict has keys `id, layer, layerZh, team, participants, schedule, durationMin, status, questions`.

---

### Task 1: Remove the AI pre-answer task (1.3b) end-to-end

**Files:**
- Modify: `backend/app/domain/blueprint.py` (task `1.3b` dict ~line 211-215; `1.4a` `depends_on` ~line 220)
- Modify: `backend/app/agents/registry.py:17` (`eng.register("1.3b", business.pre_answer)`)
- Modify: `backend/app/agents/business.py` (delete `pre_answer` ~800-822, `_fill_business_preanswers` ~754-786, `_fill_data_preanswers` ~789-797, `_source_labels` ~728-733, `_norm_confidence` ~749-751)
- Modify: `backend/app/store/state.py` (`heal_state` — dead-task pruning)
- Modify: `frontend/src/lib/scenario.ts` (mirrored `1.3b`; `1.4a` dependency)
- Test: `backend/tests/test_api_smoke.py` (existing — must still pass)

**Interfaces:**
- Consumes: nothing new.
- Produces: blueprint `TASKS` no longer contains `1.3b`; task `1.4a` `depends_on == ["1.3"]`. Registry no longer wires `pre_answer`.

- [ ] **Step 1: Write the failing test** — create `backend/app/domain/_test_blueprint_interview.py`:

```python
"""Structural assertions for the interview blueprint after 1.3b removal."""
from app.domain.blueprint import TASKS

def _by_id():
    return {t["id"]: t for t in TASKS}

def main():
    tasks = _by_id()
    assert "1.3b" not in tasks, "1.3b (pre-answer) must be removed"
    assert "1.4a" in tasks, "1.4a upload gate must remain"
    assert tasks["1.4a"]["depends_on"] == ["1.3"], \
        f'1.4a must depend on 1.3, got {tasks["1.4a"]["depends_on"]}'
    print("OK blueprint interview structure")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it, verify it FAILS**

Run (from `backend/`): `PYTHONPATH=. .venv/bin/python -m app.domain._test_blueprint_interview`
Expected: AssertionError on `"1.3b" not in tasks`.

- [ ] **Step 3: Remove `1.3b` from the blueprint and fix the `1.4a` dependency.**

In `app/domain/blueprint.py` delete the entire `{"id": "1.3b", ... "produces": []}` dict. In the `1.4a` dict change `"depends_on": ["1.3b"]` → `"depends_on": ["1.3"]`.

- [ ] **Step 4: Unwire and delete the handler.**

In `app/agents/registry.py` delete the line `eng.register("1.3b", business.pre_answer)`.
In `app/agents/business.py` delete these now-unused functions: `pre_answer`, `_fill_business_preanswers`, `_fill_data_preanswers`, `_source_labels`, `_norm_confidence`. Before deleting each, confirm it has no other caller:

Run (from `backend/`): `grep -nE "pre_answer|_fill_business_preanswers|_fill_data_preanswers|_source_labels|_norm_confidence" app -r | grep -v _pycache`
Expected after deletion: only the definitions are gone and no dangling references remain (empty or comment-only matches).

- [ ] **Step 5: Prune `1.3b` from saved projects in `heal_state`.**

Open `app/store/state.py`, find `heal_state`. It already reconciles saved projects against the current blueprint (the S2 revamp "prunes dead tasks"). Follow that existing pattern so a saved `danone-mizone.json` referencing `1.3b` (task status, events) heals without error. If `heal_state` derives task lists purely from the blueprint it may need no change — confirm by loading state in Step 7.

- [ ] **Step 6: Mirror the removal in the frontend scenario.**

In `frontend/src/lib/scenario.ts` delete the mirrored `1.3b` task object and change the `1.4a` task's `dependsOn` from `['1.3b']` to `['1.3']`. (Search the file for `1.3b`.)

- [ ] **Step 7: Run the gates.**

Run (from `backend/`):
```
PYTHONPATH=. .venv/bin/python -m app.domain._test_blueprint_interview   # expect: OK
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py                    # expect: pass
```
Run (from `frontend/`):
```
npm run build   # tsc + vite build; expect: success
```
Also load a project to confirm `heal_state` is clean:
```
cd backend && .venv/bin/python -c "from app.store.state import ProjectStore; s=ProjectStore(); [s.load(m.id) for m in s.registry()]; print('heal OK')"
```
Expected: all green. This is the task's completion checkpoint (no git commit — not a repo).

---

### Task 2: Interview sheet columns — add `Origin`, drop pre-answer columns

**Files:**
- Modify: `backend/app/agents/business.py` (`_IV_COLUMNS` ~611-612; `_interview_sheets` row builder ~719-724; question-dict factories `_data_questions` ~664-666 and `_build_targets` ~687-689)
- Test: `backend/app/agents/_test_interview.py` (create)

**Interfaces:**
- Consumes: target/question dicts from Task-1's unchanged factories.
- Produces: `_IV_COLUMNS == ["#", "Q Type", "Question", "Related Factor Path", "Origin", "访谈回答", "回答来源"]`. Every question dict carries `origin` (default `"提纲"`). `_interview_sheets(targets)` emits one row per question as `[idx, qType, question, relatedFactorPath, origin, finalAnswer, answerSource]`.

- [ ] **Step 1: Write the failing test** — create `backend/app/agents/_test_interview.py`:

```python
"""Runnable checks for the interview sheet + real-minutes rebuild (no LLM)."""
from app.agents import business as B

def test_columns_and_rows():
    q = {"qType": "business", "question": "渠道占比?", "relatedFactorPath": "",
         "origin": "提纲", "finalAnswer": "约40%", "answerSource": "市场部纪要"}
    t = B._make_target("management", "Marketing", [q])
    sheets = B._interview_sheets([t])
    iv = next(s for s in sheets["sheets"] if s["name"] != "Overview")
    assert iv["columns"] == ["#", "Q Type", "Question", "Related Factor Path",
                             "Origin", "访谈回答", "回答来源"], iv["columns"]
    row = iv["rows"][0]
    assert row == ["1", "business", "渠道占比?", "", "提纲", "约40%", "市场部纪要"], row
    print("OK columns_and_rows")

def main():
    test_columns_and_rows()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it, verify it FAILS**

Run (from `backend/`): `PYTHONPATH=. .venv/bin/python -m app.agents._test_interview`
Expected: AssertionError on the columns list (still has `AI Pre-Answer`/`Confidence`/`Sources`).

- [ ] **Step 3: Update `_IV_COLUMNS`.**

```python
_IV_COLUMNS = ["#", "Q Type", "Question", "Related Factor Path", "Origin",
               "访谈回答", "回答来源"]
```

- [ ] **Step 4: Update the `_interview_sheets` row builder** (replace the per-question row list comprehension ~719-722):

```python
        rows = [[str(i), q["qType"], q["question"], q.get("relatedFactorPath", ""),
                 q.get("origin", "提纲"), q.get("finalAnswer", ""), q.get("answerSource", "")]
                for i, q in enumerate(t["questions"], 1)]
```

- [ ] **Step 5: Add `origin` to the question-dict factories.**

In `_build_targets` (~687) the business-question dict and in `_data_questions` (~664) the data-question dict, drop `"preAnswer"/"confidence"/"sources"` and add `"origin": "提纲"`. E.g. business:

```python
            grouped[key].append({"qType": "business", "question": q.question.strip(),
                                 "relatedFactorPath": "", "origin": "提纲"})
```

and data:

```python
            out.append({"qType": "data", "question": f"[{path_arrow}] {subq}",
                        "relatedFactorPath": path_slash, "origin": "提纲"})
```

- [ ] **Step 6: Run the gate.**

Run (from `backend/`):
```
PYTHONPATH=. .venv/bin/python -m app.agents._test_interview   # expect: OK columns_and_rows
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py         # expect: pass
```
Expected: green.

---

### Task 3: `_department_from_filename` helper

**Files:**
- Modify: `backend/app/agents/business.py` (add helper near `_minutes_files` ~829)
- Test: `backend/app/agents/_test_interview.py` (extend)

**Interfaces:**
- Produces: `_department_from_filename(filename: str) -> str` — returns a human department label derived from the file name, stripping extension, an optional leading `LayerN_`/`第N层_` prefix, and a trailing `访谈`/`纪要`/`minutes`/`interview` token; returns `""` when nothing usable remains.

- [ ] **Step 1: Write the failing test** — add to `_test_interview.py`:

```python
def test_department_from_filename():
    f = B._department_from_filename
    assert f("市场部访谈.docx") == "市场部", f("市场部访谈.docx")
    assert f("Layer3_电商部_纪要.txt") == "电商部", f("Layer3_电商部_纪要.txt")
    assert f("Sales Dept interview.md") == "Sales Dept", f("Sales Dept interview.md")
    assert f("   .txt") == "", f("   .txt")
    print("OK department_from_filename")
```

and call `test_department_from_filename()` inside `main()`.

- [ ] **Step 2: Run it, verify it FAILS**

Run (from `backend/`): `PYTHONPATH=. .venv/bin/python -m app.agents._test_interview`
Expected: AttributeError — `business` has no `_department_from_filename`.

- [ ] **Step 3: Implement the helper** (place above `_minutes_files`):

```python
import os

_DEPT_STRIP = re.compile(r"(访谈|纪要|minutes|interview|记录)", re.IGNORECASE)
_DEPT_PREFIX = re.compile(r"^(layer\d+|第[0-9一二三四五六七八九十]+层)[ _-]+", re.IGNORECASE)

def _department_from_filename(filename: str) -> str:
    """Best-effort department label from an interview file name. Client file names
    clearly name the department (e.g. '市场部访谈.docx'); AI content inference is the
    fallback used by the digest, not here."""
    stem = os.path.splitext(os.path.basename(filename or ""))[0]
    stem = _DEPT_PREFIX.sub("", stem)
    stem = _DEPT_STRIP.sub("", stem)
    return re.sub(r"[ _\-·]+", " ", stem).strip()
```

- [ ] **Step 4: Run the test, verify it PASSES**

Run (from `backend/`): `PYTHONPATH=. .venv/bin/python -m app.agents._test_interview`
Expected: `OK department_from_filename` (and prior checks still OK).

---

### Task 4: Real-department rebuild + digest contract

**Files:**
- Modify: `backend/app/agents/business.py` (add `_make_real_target`, `_rebuild_targets_from_real_minutes`, `_merge_factor_side`; extend `_digest_transcript` prompt/return)
- Test: `backend/app/agents/_test_interview.py` (extend)

**Interfaces:**
- Consumes: `_department_from_filename` (Task 3); the flattened outline `biz: list[tuple[dict, str]]` (question dict + preset label) and `files: list[tuple[str, str]]` (filename, text) that `writeback_minutes` already builds.
- Produces:
  - `_make_real_target(department: str, participants: str, questions: list[dict]) -> dict` — target dict with `layer="field"`, `layerZh=department`, `team=department`, `participants=participants`, `status="completed"`, `durationMin=0`, `schedule=""`.
  - `_rebuild_targets_from_real_minutes(biz, files, results) -> list[dict]` — one target per file/department; rows = outline questions this file answered (`origin="提纲"`, `finalAnswer`/`answerSource` set, fill-first across files by question number) + new questions (`origin="新问题"`). Outline questions no file answered are omitted.
  - `_merge_factor_side(results: list[dict]) -> dict` — `{"factor_changes": [...deduped...], "insights": [...capped...]}`, same dedup/caps as the old `_merge_minutes_digests` (drop its `answers` handling).
  - `_digest_transcript(...)` return dict additionally carries `department: str`, `participants: str`, `new_questions: list[{"question","answer","source"}]`.

- [ ] **Step 1: Write the failing test** — add to `_test_interview.py`:

```python
def test_rebuild_targets():
    # outline: 2 business questions
    q1 = {"qType": "business", "question": "渠道占比?", "relatedFactorPath": "", "origin": "提纲"}
    q2 = {"qType": "business", "question": "新品节奏?", "relatedFactorPath": "", "origin": "提纲"}
    biz = [(q1, "Marketing"), (q2, "Management")]
    files = [("市场部访谈.docx", "..."), ("管理层访谈.docx", "...")]
    results = [
        {"department": "市场部", "participants": "张三",
         "answers": [{"n": 1, "answer": "约40%", "source": "市场部纪要"}],
         "new_questions": [{"question": "竞品促销力度?", "answer": "很强", "source": "市场部纪要"}]},
        {"department": "", "participants": "",
         "answers": [{"n": 2, "answer": "季度上新", "source": "管理层纪要"}],
         "new_questions": []},
    ]
    targets = B._rebuild_targets_from_real_minutes(biz, files, results)
    assert [t["layerZh"] for t in targets] == ["市场部", "管理层访谈".replace("访谈", "")], \
        [t["layerZh"] for t in targets]   # file-2 dept falls back to filename
    mkt = targets[0]
    origins = [(q["question"], q["origin"], q.get("finalAnswer", "")) for q in mkt["questions"]]
    assert ("渠道占比?", "提纲", "约40%") in origins, origins
    assert ("竞品促销力度?", "新问题", "很强") in origins, origins
    assert mkt["participants"] == "张三"
    print("OK rebuild_targets")

def test_merge_factor_side_keeps_changes():
    results = [{"factor_changes": [{"op": "add", "l1": "A", "l2": "", "l3": "", "l4": "",
                                    "indicator": "x", "quote": "q"}],
                "insights": [{"kind": "gap", "title": "t", "finding": "f", "confidence": 0.5}]}]
    merged = B._merge_factor_side(results)
    assert len(merged["factor_changes"]) == 1 and len(merged["insights"]) == 1
    print("OK merge_factor_side")
```

and call both inside `main()`.

- [ ] **Step 2: Run it, verify it FAILS**

Run (from `backend/`): `PYTHONPATH=. .venv/bin/python -m app.agents._test_interview`
Expected: AttributeError — helpers not defined yet.

- [ ] **Step 3: Implement `_make_real_target` and `_rebuild_targets_from_real_minutes`.**

```python
def _make_real_target(department: str, participants: str, questions: list[dict]) -> dict:
    return {
        "id": _target_id("field", department), "layer": "field", "layerZh": department,
        "team": department, "participants": participants or "", "schedule": "",
        "durationMin": 0, "status": "completed", "questions": questions,
    }

def _rebuild_targets_from_real_minutes(biz, files, results) -> list[dict]:
    """One target per uploaded minutes file, keyed by its real department.
    Outline questions are backfilled fill-first by question number; unanswered
    outline questions are dropped. New questions attach to the file that raised them."""
    claimed: set[int] = set()
    targets: list[dict] = []
    for (filename, _text), res in zip(files, results):
        res = res if isinstance(res, dict) else {}
        dept = str(res.get("department") or "").strip() or _department_from_filename(filename) or filename
        rows: list[dict] = []
        for a in res.get("answers", []) or []:
            if not isinstance(a, dict):
                continue
            try:
                n = int(a.get("n", 0))
            except (TypeError, ValueError):
                continue
            if n < 1 or n > len(biz) or n in claimed:
                continue
            ans = str(a.get("answer", "")).strip()
            if not ans:
                continue
            claimed.add(n)
            q0 = biz[n - 1][0]
            rows.append({**{k: q0.get(k, "") for k in ("qType", "question", "relatedFactorPath")},
                         "origin": "提纲", "finalAnswer": ans,
                         "answerSource": str(a.get("source", "")).strip()})
        for nq in res.get("new_questions", []) or []:
            if not isinstance(nq, dict) or not str(nq.get("question", "")).strip():
                continue
            rows.append({"qType": "business", "question": str(nq["question"]).strip(),
                         "relatedFactorPath": "", "origin": "新问题",
                         "finalAnswer": str(nq.get("answer", "")).strip(),
                         "answerSource": str(nq.get("source", "")).strip()})
        targets.append(_make_real_target(dept, str(res.get("participants") or ""), rows))
    return targets
```

- [ ] **Step 4: Add `_merge_factor_side`** (adapt the existing `_merge_minutes_digests` — keep the `factor_changes` dedup and `insights` cap exactly, drop the `answers` block):

```python
def _merge_factor_side(results: list[dict]) -> dict:
    changes: list[dict] = []
    change_keys: set[tuple] = set()
    insights: list[dict] = []
    for res in results:
        if not isinstance(res, dict):
            continue
        for ch in res.get("factor_changes", []) or []:
            if not isinstance(ch, dict):
                continue
            key = (str(ch.get("op", "add")), str(ch.get("l1", "")), str(ch.get("l2", "")),
                   str(ch.get("l3", "")), str(ch.get("l4", "")), str(ch.get("indicator", "")))
            if key in change_keys:
                continue
            change_keys.add(key)
            changes.append(ch)
        for ins in res.get("insights", []) or []:
            if isinstance(ins, dict) and len(insights) < _MAX_INSIGHTS:
                insights.append(ins)
    return {"factor_changes": changes, "insights": insights}
```

- [ ] **Step 5: Extend the `_digest_transcript` LLM contract.**

In `_digest_transcript`, add to the prompt (a) a task to report the department and participants of THIS transcript, and (b) a task to extract NEW questions the interviewees raised that are not in the outline, each with its answer + source. Update the returned JSON schema in the prompt to:

```
{"department":str,"participants":str,
 "answers":[{"n":int,"answer":str,"source":str}],
 "new_questions":[{"question":str,"answer":str,"source":str}],
 "factor_changes":[{...unchanged...}],
 "insights":[{...unchanged...}]}
```

Add two sentences to the instruction text: `"(0) CONTEXT — state the department/team this transcript is for and its participants."` and `"(3) NEW QUESTIONS — list questions the interviewees themselves raised that are NOT in the outline, each with the answer given and its source. Skip if none."` Widen `max_tokens` (e.g. add `max_tokens=4000`) since the call now returns a fourth family; keep `timeout=_MINUTES_LLM_TIMEOUT`. Do not change the `factor_changes`/`insights` instructions.

- [ ] **Step 6: Run the tests, verify they PASS**

Run (from `backend/`): `PYTHONPATH=. .venv/bin/python -m app.agents._test_interview`
Expected: `OK rebuild_targets`, `OK merge_factor_side` (and all earlier OK lines).

---

### Task 5: Rewire `writeback_minutes` to the real-minutes rebuild

**Files:**
- Modify: `backend/app/agents/business.py` (`writeback_minutes` ~948-end; delete now-dead `_merge_minutes_digests` ~839-872)
- Test: `backend/app/agents/_test_interview.py` (already covers the pure units); `backend/tests/test_api_smoke.py`

**Interfaces:**
- Consumes: `_rebuild_targets_from_real_minutes`, `_merge_factor_side` (Task 4).
- Produces: `writeback_minutes` rebuilds `interview_targets` from the real minutes, re-renders `a-interview`, and drives factor changes via `_merge_factor_side` (behavior-identical factor path).

- [ ] **Step 1: Replace the answer-backfill + merge block in `writeback_minutes`.**

Keep the front matter unchanged: `files = _minutes_files(st)`, building `biz` (cap 28) and `qlist`, the empty-`files` early return, and `results = await asyncio.gather(*(_digest_transcript(fn, tx, qlist, st) for fn, tx in files))`. Then replace the old `_merge_minutes_digests` + per-`biz` `finalAnswer` loop with:

```python
    files_used = sum(1 for r in results if isinstance(r, dict) and r)

    # ── Interview structure: rebuild into the client's REAL departments (from the
    # minutes) — backfilled outline answers + newly-raised questions. ──
    new_targets = _rebuild_targets_from_real_minutes(biz, files, results)
    answered = sum(1 for t in new_targets for q in t["questions"] if q.get("origin") == "提纲")
    emergent = sum(1 for t in new_targets for q in t["questions"] if q.get("origin") == "新问题")
    eng.set_analysis(st, "interview_targets", new_targets)
    eng.set_analysis(st, "interview_questions", _flatten_targets(new_targets))
    eng.produce(st, "a-interview", body=_interview_sheets(new_targets), state="draft", agent="business")
    eng.emit(st, "business", "info",
             f"Interview digest: {files_used}/{len(files)} transcripts used → "
             f"{len(new_targets)} departments · {answered} outline answers backfilled · "
             f"{emergent} new questions extracted.", task["id"])
    if files_used < len(files):
        eng.emit(st, "business", "finding",
                 f"Only {files_used}/{len(files)} interview transcripts produced a usable "
                 f"digest — the rest failed (timeout or parse error); re-run to cover them.",
                 task["id"])
```

- [ ] **Step 2: Point the factor-change block at `_merge_factor_side`.**

The existing "Issue 2" factor-change block reads `merged["factor_changes"]`. Change its source: `merged = _merge_factor_side(results)` computed just before the block (or inline `changes = _merge_factor_side(results)["factor_changes"]`). Leave the `FactorRow(...)` construction, dedup-by-existing-key, `proposed` status, and proposal emission **unchanged**.

- [ ] **Step 3: Delete the dead `_merge_minutes_digests`.**

Run (from `backend/`): `grep -n "_merge_minutes_digests" app -r | grep -v _pycache`
Expected: only its definition remains → delete it. Re-run grep; expect no matches.

- [ ] **Step 4: Run the backend gates.**

Run (from `backend/`):
```
PYTHONPATH=. .venv/bin/python -m app.agents._test_interview   # expect: all OK
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py         # expect: pass
```
Expected: green.

- [ ] **Step 5: Full verification (spec §Testing).**

Backend (from `backend/`):
```
PYTHONPATH=. .venv/bin/python -m app.ingest._smoke            # loaders unaffected
```
Frontend (from `frontend/`):
```
npm run build
```
E2E (needs the LLM configured in Settings + interview minutes uploaded to `danone-mizone`):
```
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000 &
P=danone-mizone
curl -XPOST localhost:8000/api/projects/$P/reset
# upload real interview_minutes files to category interview_minutes, then:
curl -XPOST localhost:8000/api/projects/$P/run -H 'content-type: application/json' -d '{"autopilot":true}'
curl localhost:8000/api/projects/$P/run/status   # poll to completion
curl localhost:8000/api/projects/$P/state | python3 -m json.tool | grep -iA2 interview
```
Expected: the run reaches `1.5`; `a-interview` shows real-department sheets with backfilled answers + `新问题` rows; the `1.4d`/factor path is unchanged. **Do not fabricate minutes** — if none are available, verify Tasks 1-5 via the unit scripts + build and note E2E is pending real uploads.

---

## Self-Review

**Spec coverage:**
- §Phase A (remove pre-answer) → Task 1 + Task 2 (columns). ✅
- §Phase B (real org from filenames, drop uncovered outline Qs) → Task 3 + Task 4 (`_rebuild_targets_from_real_minutes`) + Task 5. ✅
- §Phase C (backfill + new questions, one call/transcript, widen tokens) → Task 4 (digest contract) + Task 5 (rewire). ✅
- §Phase D (factor tree unchanged) → Task 4 `_merge_factor_side` + Task 5 Step 2 (block unchanged). ✅
- §Contracts (blueprint↔scenario, no types.ts, heal_state) → Task 1 Steps 3/5/6. ✅
- §Testing gates → Task 5 Step 5. ✅

**Placeholder scan:** No TBD/TODO; every code step carries real code. The only "unchanged" references (factor-change block, digest factor/insight instructions) point at existing code the task explicitly must not edit — not omitted new code.

**Type consistency:** `origin` values `"提纲"`/`"新问题"` used identically in Tasks 2, 4, 5. `_rebuild_targets_from_real_minutes(biz, files, results)`, `_merge_factor_side(results)`, `_make_real_target(department, participants, questions)`, `_department_from_filename(filename)` signatures match across their definition (Task 3/4) and call sites (Task 5). Question-dict keys (`qType, question, relatedFactorPath, origin, finalAnswer, answerSource`) match the `_interview_sheets` reader in Task 2.
