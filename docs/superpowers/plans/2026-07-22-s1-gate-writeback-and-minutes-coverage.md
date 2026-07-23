# S1 Gate Writeback + Minutes Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two S1 BREAKs found in the E2E run — (1) approving the factor-tree gates (`d-1.21`/`d-1.4`) now writes `accepted` status back so AI/interview factors reach the 2.1 mapping; (2) interview digestion runs per-transcript so all uploaded minutes are used, not just the first ~5 that fit under a shared character cap.

**Architecture:** BREAK 1 is two pure `(st, option_id)` decision effects registered on the engine exactly like the existing `d-2.5` effect — no data-model change, since `FactorStatus` already has `accepted` and `mapping._ACTIVE_STATUSES` already includes it. BREAK 2 replaces the concatenate-then-truncate minutes path with per-file extraction + one combined LLM call per transcript + a pure merge, so 12 transcripts cost 12 requests and every one reaches the model.

**Tech Stack:** Python 3.14, FastAPI backend under `backend/app`. Tests are runnable scripts in `backend/tests/` (bare `assert` inside `def test_*()` functions, run by a `__main__` loop). No pytest dependency, no new packages.

**Spec:** `docs/superpowers/specs/2026-07-22-s1-gate-writeback-and-minutes-coverage-design.md`

## Global Constraints

- **Run tests from `backend/`** as `PYTHONPATH=. .venv/bin/python tests/<file>.py`. Each test file ends with a `__main__` block that runs every `test_*` in module globals and prints `ok  <name>`.
- **No data-model changes.** `FactorStatus = Literal["baseline","proposed","accepted","rejected"]` and `mapping._ACTIVE_STATUSES = ("baseline","accepted")` already exist. Do not touch `models.py` / `types.ts`.
- **Decision effects have signature `DecisionEffect = Callable[[ProjectState, str], None]`** — they receive `(st, option_id)` only, never the engine. Mutate `st` in place.
- **Only `proposed` rows flip.** Never touch a row a human set to `rejected`. Never touch `baseline` rows.
- **Never silent.** The minutes path must `eng.emit` a finding reporting `files_used/total` and `answered/28`, and flag partial coverage. A failed per-file call returns `{}` and is skipped, never raised.
- **Out of scope (do not implement):** the docx-table drop in `app/ingest/extract.py`; the artifact-state GAP (`a-scope` etc. showing `proposed` after approval); the Y-mislabel BLOCKER. These are separate concerns named in the spec.

## File Structure

| Path | Change | Responsibility |
|---|---|---|
| `backend/app/agents/business.py` | Modify | Add `accept_factor_rows` + `confirm_tree_effect` + `confirm_interview_effect` (Task 1); add `_minutes_files`, `_digest_transcript`, `_merge_minutes_digests`, constants (Task 2); rewrite `writeback_minutes`, delete `_load_minutes_text`/`_minutes_answers`/`_minutes_factor_changes` (Task 3). |
| `backend/app/agents/registry.py` | Modify | Register the two new decision effects (Task 1). |
| `backend/app/store/files.py` | Modify | Add `extract_category_files` (per-file extraction) (Task 2). |
| `backend/app/agents/sources.py` | Modify | Add `category_files` wrapper (Task 2). |
| `backend/tests/test_factor_gate_effects.py` | Create | Unit-test the two effects + their effect on the 2.1 map (Task 1). |
| `backend/tests/test_minutes_merge.py` | Create | Unit-test `_merge_minutes_digests` + `_minutes_files` (Task 2). |

---

## Task 1: Factor-tree gate writeback (BREAK 1)

**Files:**
- Modify: `backend/app/agents/business.py` (add three functions near the other S1 business helpers)
- Modify: `backend/app/agents/registry.py:36` (register two effects)
- Create: `backend/tests/test_factor_gate_effects.py`

**Interfaces:**
- Consumes: `st.factor_tree.rows` (`list[FactorRow]`, each with `.status` and `.source`), `st.artifact("a-factor-tree")`, existing `_factor_tree_sheet(ft: FactorTree) -> dict`.
- Produces:
  - `business.accept_factor_rows(st: ProjectState, sources: set[str]) -> None`
  - `business.confirm_tree_effect(st: ProjectState, option_id: str) -> None`
  - `business.confirm_interview_effect(st: ProjectState, option_id: str) -> None`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_factor_gate_effects.py`:

```python
"""Gate approval writes accepted status back onto the factor tree.

The two S1 factor-tree gates (d-1.21 / d-1.4) promise "write back into the
factor tree", but until now approving them changed no row: the AI/interview
rows stayed `proposed`, and mapping._ACTIVE_STATUSES excludes `proposed`, so
they never reached the 2.1 factor map. These tests pin that approving each gate
flips exactly its own source-set's still-proposed rows to `accepted`, leaves
manually-rejected rows alone, and thereby lets those rows into the map.

Run: PYTHONPATH=. .venv/bin/python tests/test_factor_gate_effects.py
"""
from __future__ import annotations

from app.agents.business import (
    accept_factor_rows,
    confirm_interview_effect,
    confirm_tree_effect,
)
from app.dataeng.mapping import resolve_factor_map
from app.domain.models import ArtifactInstance, FactorRow, FactorTree
from app.store.state import danone_meta, initial_state


def _state_with_tree() -> "object":
    st = initial_state(danone_meta())
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="r-base", l1="A", l2="B", l3="C", l4="D", indicator="base",
                  source="template", status="baseline"),
        FactorRow(id="r-ai", l1="A", l2="B", l3="C", l4="D", indicator="ai-ind",
                  source="ai", status="proposed"),
        FactorRow(id="r-tpl", l1="A", l2="B", l3="C", l4="D", indicator="tpl-ind",
                  source="template", status="proposed"),
        FactorRow(id="r-iv", l1="A", l2="B", l3="C", l4="D", indicator="iv-ind",
                  source="interview", status="proposed"),
        FactorRow(id="r-rej", l1="A", l2="B", l3="C", l4="D", indicator="rej-ind",
                  source="ai", status="rejected"),
    ])
    st.artifacts.append(ArtifactInstance(
        id="a-factor-tree", name="Factor Tree", taskRef="1.21",
        type="master-data", stage="s1", format="sheet", body={"stale": True}))
    return st


def _status(st, row_id: str) -> str:
    return next(r.status for r in st.factor_tree.rows if r.id == row_id)


def test_confirm_tree_flips_ai_and_template_only() -> None:
    st = _state_with_tree()
    confirm_tree_effect(st, "approve")
    assert _status(st, "r-ai") == "accepted", "ai proposed should be accepted"
    assert _status(st, "r-tpl") == "accepted", "template proposed should be accepted"
    assert _status(st, "r-iv") == "proposed", "interview belongs to d-1.4, not d-1.21"
    assert _status(st, "r-rej") == "rejected", "manual reject must be respected"
    assert _status(st, "r-base") == "baseline", "baseline is untouched"
    # The a-factor-tree sheet was re-rendered (no longer the stale placeholder).
    assert st.artifact("a-factor-tree").body != {"stale": True}


def test_confirm_interview_flips_interview_only() -> None:
    st = _state_with_tree()
    confirm_interview_effect(st, "approve")
    assert _status(st, "r-iv") == "accepted", "interview proposed should be accepted"
    assert _status(st, "r-ai") == "proposed", "ai belongs to d-1.21, not d-1.4"
    assert _status(st, "r-rej") == "rejected"


def test_rework_changes_nothing() -> None:
    st = _state_with_tree()
    before = {r.id: r.status for r in st.factor_tree.rows}
    confirm_tree_effect(st, "rework")
    confirm_interview_effect(st, "rework")
    after = {r.id: r.status for r in st.factor_tree.rows}
    assert before == after, "rework must not flip any status"


def test_flipped_rows_enter_the_2_1_map() -> None:
    st = _state_with_tree()
    before = resolve_factor_map(st).total
    confirm_tree_effect(st, "approve")
    confirm_interview_effect(st, "approve")
    after = resolve_factor_map(st).total
    # Before: only the baseline row is active/in the map. After: baseline + the
    # three flipped rows (ai, template, interview). The rejected row stays out.
    assert after == before + 3, f"expected 3 rows to enter the map, got {after - before}"


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("\nAll factor-gate-effect tests passed.")
```

- [ ] **Step 2: Run test to verify it fails**

Run from `backend/`:
```bash
PYTHONPATH=. .venv/bin/python tests/test_factor_gate_effects.py
```
Expected: `ImportError: cannot import name 'accept_factor_rows' from 'app.agents.business'`

- [ ] **Step 3: Add the three functions to `business.py`**

In `backend/app/agents/business.py`, immediately **before** `async def writeback_minutes` (currently line 883), insert:

```python
def accept_factor_rows(st: ProjectState, sources: set[str]) -> None:
    """Flip this gate's still-proposed rows to accepted; respect manual rejects.

    `proposed` is excluded by mapping._ACTIVE_STATUSES, so a row only reaches the
    2.1 factor map once accepted. Approving a factor-tree gate means "accept the
    proposals I did not manually reject" — so only `proposed` rows of the gate's
    own source-set flip; `rejected` and `baseline` rows are left alone.
    """
    if st.factor_tree is None:
        return
    for r in st.factor_tree.rows:
        if r.status == "proposed" and r.source in sources:
            r.status = "accepted"
    art = st.artifact("a-factor-tree")
    if art is not None:
        art.body = _factor_tree_sheet(st.factor_tree)


def confirm_tree_effect(st: ProjectState, option_id: str) -> None:
    """d-1.21 effect: approving 'Confirm the factor tree' accepts the 1.21 rows."""
    if option_id == "approve":
        accept_factor_rows(st, {"ai", "template"})


def confirm_interview_effect(st: ProjectState, option_id: str) -> None:
    """d-1.4 effect: approving 'write back into the factor tree' accepts the
    interview-sourced rows 1.4 proposed."""
    if option_id == "approve":
        accept_factor_rows(st, {"interview"})
```

- [ ] **Step 4: Register the effects in `registry.py`**

In `backend/app/agents/registry.py`, find the existing line (36):

```python
    eng.register_decision("d-2.5", ledger.freeze_range_drops)
```

Insert immediately **after** it:

```python
    # S1 factor-tree gates write accepted status back so AI/interview rows reach
    # the 2.1 mapping (until now approval changed no row — they stayed proposed).
    eng.register_decision("d-1.21", business.confirm_tree_effect)
    eng.register_decision("d-1.4", business.confirm_interview_effect)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
PYTHONPATH=. .venv/bin/python tests/test_factor_gate_effects.py
```
Expected: four `ok  test_*` lines and `All factor-gate-effect tests passed.`, exit 0.

If `test_flipped_rows_enter_the_2_1_map` reports a delta other than 3, print `[(r.id, r.status) for r in st.factor_tree.rows]` after the flips and check the source-set membership — do not change the assertion.

- [ ] **Step 6: Verify no regression in the wiring**

```bash
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py
```
Expected: the smoke test's existing final line (control-flow OK), exit 0. This proves `build_engine()` still wires up with the two new `register_decision` calls. Note: the smoke run has no LLM configured, so task 1.21's `proposed` rows (which come from an LLM call that returns `{}` on failure) are never created — the new effects are no-ops there and cannot change the 2.1 gate outcome. Their real behavior is unit-tested in Step 5 and E2E-verified in Task 4.

- [ ] **Step 7: Commit**

```bash
git add backend/app/agents/business.py backend/app/agents/registry.py backend/tests/test_factor_gate_effects.py
git commit -m "fix(s1): factor-tree gates write accepted status back (BREAK 1)"
```

---

## Task 2: Per-file minutes extraction + merge (BREAK 2, plumbing)

**Files:**
- Modify: `backend/app/store/files.py` (add `extract_category_files` after `extract_category_text`, ~line 182)
- Modify: `backend/app/agents/sources.py` (add `category_files` after `category_text`, ~line 18)
- Modify: `backend/app/agents/business.py` (add constants + `_minutes_files` + `_merge_minutes_digests`)
- Create: `backend/tests/test_minutes_merge.py`

**Interfaces:**
- Consumes: `get_files()` (`FileStore` with `_read_index`, `get_path`, `extract_document`), `st.project_id`.
- Produces:
  - `FileStore.extract_category_files(project_id: str, category: FileCategory, per_file_cap: int = 12000) -> list[tuple[str, str]]`
  - `sources.category_files(project_id: str, category, per_file_cap: int = 12000) -> list[tuple[str, str]]`
  - `business._MINUTES_PER_FILE_CHARS: int = 12000`, `business._MAX_INSIGHTS: int = 3`
  - `business._minutes_files(st: ProjectState) -> list[tuple[str, str]]`
  - `business._merge_minutes_digests(results: list[dict]) -> dict` → `{"answers": dict[int, dict], "factor_changes": list[dict], "insights": list[dict]}`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_minutes_merge.py`:

```python
"""Per-file interview digests merge without dropping or duplicating.

BREAK 2 replaced the concatenate-then-truncate minutes path (which used only the
first ~5 of 12 transcripts) with one call per transcript + a pure merge. These
tests pin the merge: answers fill-first per question number, factor changes
dedup by their identity key, insights cap. The live per-file LLM call is covered
by the E2E run, not here.

Run: PYTHONPATH=. .venv/bin/python tests/test_minutes_merge.py
"""
from __future__ import annotations

from app.agents.business import _MAX_INSIGHTS, _merge_minutes_digests


def _change(op, l4, indicator):
    return {"op": op, "l1": "A", "l2": "B", "l3": "C", "l4": l4,
            "indicator": indicator, "rationale": "r", "quote": "q"}


def test_answers_fill_first_across_files() -> None:
    # File A answers 1 and 3; B answers 3 (ignored, already filled) and 5;
    # C answers 5 (ignored) and 8.
    results = [
        {"answers": [{"n": 1, "answer": "a1", "source": "GM"},
                     {"n": 3, "answer": "a3-A", "source": "GM"}]},
        {"answers": [{"n": 3, "answer": "a3-B", "source": "Media"},
                     {"n": 5, "answer": "a5", "source": "Media"}]},
        {"answers": [{"n": 5, "answer": "a5-C", "source": "EC"},
                     {"n": 8, "answer": "a8", "source": "EC"}]},
    ]
    merged = _merge_minutes_digests(results)
    ans = merged["answers"]
    assert set(ans.keys()) == {1, 3, 5, 8}, set(ans.keys())
    assert ans[3]["answer"] == "a3-A", "first non-empty answer wins"
    assert ans[5]["answer"] == "a5", "first non-empty answer wins"


def test_empty_answers_are_skipped() -> None:
    results = [
        {"answers": [{"n": 2, "answer": "  ", "source": "x"}]},
        {"answers": [{"n": 2, "answer": "real", "source": "y"}]},
    ]
    merged = _merge_minutes_digests(results)
    assert merged["answers"][2]["answer"] == "real", "blank answer must not claim the slot"


def test_factor_changes_dedup_by_identity() -> None:
    results = [
        {"factor_changes": [_change("add", "D1", "ind1"), _change("add", "D2", "ind2")]},
        {"factor_changes": [_change("add", "D1", "ind1"),   # dup of the first
                            _change("modify", "D1", "ind1")]},  # same path, diff op → kept
    ]
    merged = _merge_minutes_digests(results)
    keys = {(c["op"], c["l4"], c["indicator"]) for c in merged["factor_changes"]}
    assert keys == {("add", "D1", "ind1"), ("add", "D2", "ind2"),
                    ("modify", "D1", "ind1")}, keys
    assert len(merged["factor_changes"]) == 3


def test_insights_capped() -> None:
    results = [{"insights": [{"kind": "connection", "title": f"t{i}",
                             "finding": "f", "confidence": 0.7}]} for i in range(6)]
    merged = _merge_minutes_digests(results)
    assert len(merged["insights"]) == _MAX_INSIGHTS, len(merged["insights"])


def test_non_dict_results_ignored() -> None:
    merged = _merge_minutes_digests([{}, None, "oops", {"answers": [{"n": 1, "answer": "ok"}]}])
    assert merged["answers"][1]["answer"] == "ok"
    assert merged["factor_changes"] == []


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("\nAll minutes-merge tests passed.")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. .venv/bin/python tests/test_minutes_merge.py
```
Expected: `ImportError: cannot import name '_MAX_INSIGHTS' from 'app.agents.business'`

- [ ] **Step 3: Add `extract_category_files` to `files.py`**

In `backend/app/store/files.py`, immediately **after** the `extract_category_text` method (ends ~line 182), add:

```python
    def extract_category_files(self, project_id: str, category: FileCategory,
                               per_file_cap: int = 12000) -> list[tuple[str, str]]:
        """Per-file extracted text: [(filename, text), ...] for each parsed file.

        Unlike extract_category_text (which concatenates every file then truncates
        the whole to one cap — starving all but the first few), this keeps each
        file separate and caps each independently, so a caller can process every
        file instead of only the ones that fit under a shared budget.
        """
        with self._lock:
            records = [f for f in self._read_index(project_id)
                       if f.category == category and f.parsed]
            out: list[tuple[str, str]] = []
            for rec in records:
                found = self.get_path(project_id, rec.id)
                if found is None:
                    continue
                result = extract_document(found[1])
                if result.text:
                    out.append((rec.filename, result.text[:per_file_cap]))
            return out
```

- [ ] **Step 4: Add `category_files` to `sources.py`**

In `backend/app/agents/sources.py`, immediately **after** the `category_text` function (~line 18), add:

```python
def category_files(project_id: str, category: FileCategory,
                   per_file_cap: int = 12000) -> list[tuple[str, str]]:
    """Per-file extracted text for a project-folder category (uploads only)."""
    return get_files().extract_category_files(project_id, category,
                                              per_file_cap=per_file_cap)
```

- [ ] **Step 5: Add constants, `_minutes_files`, and `_merge_minutes_digests` to `business.py`**

In `backend/app/agents/business.py`, replace the whole `_load_minutes_text` function (currently lines 825–831, from `def _load_minutes_text` through its `return "", "none"`) with the new per-file loader, constants, and merge:

```python
_MINUTES_PER_FILE_CHARS = 12000   # single-file cap; real transcripts are 1–9k
_MAX_INSIGHTS = 3                  # merged insight cap (was [:2] on one call)


def _minutes_files(st: ProjectState) -> list[tuple[str, str]]:
    """Per-file interview text — uploaded interview_minutes only, no reference.

    Each transcript is extracted and capped independently so every one reaches
    the model, not just the first few that fit under a shared budget.
    """
    return sources.category_files(st.project_id, "interview_minutes",
                                  per_file_cap=_MINUTES_PER_FILE_CHARS)


def _merge_minutes_digests(results: list[dict]) -> dict:
    """Merge per-transcript digests. Answers fill-first per question number, factor
    changes dedup by (op, l1..l4, indicator), insights cap at _MAX_INSIGHTS."""
    answers: dict[int, dict] = {}
    changes: list[dict] = []
    change_keys: set[tuple] = set()
    insights: list[dict] = []
    for res in results:
        if not isinstance(res, dict):
            continue
        for a in res.get("answers", []) or []:
            if not isinstance(a, dict):
                continue
            try:
                n = int(a.get("n", 0))
            except (TypeError, ValueError):
                continue
            if n <= 0 or n in answers:
                continue
            if str(a.get("answer", "")).strip():
                answers[n] = a
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
    return {"answers": answers, "factor_changes": changes, "insights": insights}
```

Note: `_minutes_answers` and `_minutes_factor_changes` (lines 833–882) are left untouched for now — Task 3 deletes them when it rewrites `writeback_minutes`. Leaving them means the module still imports cleanly after this task.

- [ ] **Step 6: Run test to verify it passes**

```bash
PYTHONPATH=. .venv/bin/python tests/test_minutes_merge.py
```
Expected: five `ok  test_*` lines and `All minutes-merge tests passed.`, exit 0.

- [ ] **Step 7: Verify the module still imports (old writeback still references removed name)**

`writeback_minutes` still calls `_load_minutes_text`, which this task deleted. Confirm that is the only dangling reference and it is Task 3's job:
```bash
PYTHONPATH=. .venv/bin/python -c "import ast; ast.parse(open('app/agents/business.py').read()); print('parses OK')"
grep -n "_load_minutes_text" app/agents/business.py
```
Expected: `parses OK`, and the only remaining `_load_minutes_text` hit is its call inside `writeback_minutes` (line ~884) — which Task 3 replaces. Do **not** run `test_api_smoke.py` here; it exercises the run loop and would hit the dangling call. The import-and-parse check is the gate for this task.

- [ ] **Step 8: Commit**

```bash
git add backend/app/store/files.py backend/app/agents/sources.py backend/app/agents/business.py backend/tests/test_minutes_merge.py
git commit -m "feat(s1): per-file minutes extraction + digest merge (BREAK 2 plumbing)"
```

---

## Task 3: Wire `writeback_minutes` to per-file digestion (BREAK 2)

**Files:**
- Modify: `backend/app/agents/business.py` (rewrite `writeback_minutes`; add `_digest_transcript`; delete `_minutes_answers` + `_minutes_factor_changes`)

**Interfaces:**
- Consumes: `business._minutes_files`, `business._merge_minutes_digests`, `business._MINUTES_LLM_TIMEOUT`, `get_llm().json(...)`, `agent_system("business", st)`, existing `atomic_factor_rows`, `_default_dimension`, `_refresh_factor_analysis`, `_factor_tree_sheet`, `_flatten_targets`, `_interview_sheets`.
- Produces: rewritten `async def writeback_minutes(eng, st, task)` and `async def _digest_transcript(filename, text, qlist, st) -> dict`.

- [ ] **Step 1: Add `_digest_transcript` and delete the two old split calls**

In `backend/app/agents/business.py`, delete `_minutes_answers` (lines ~833–849) and `_minutes_factor_changes` (lines ~851–882) entirely, and replace them with a single combined per-transcript call:

```python
async def _digest_transcript(filename: str, text: str, qlist: str,
                             st: ProjectState) -> dict:
    """One combined LLM call over ONE transcript → {answers, factor_changes, insights}.

    Combined (not two split calls) so N transcripts cost N requests, not 2N — the
    endpoint rate-limits and the client paces requests. Fault isolation is per
    file: a bad transcript returns {} and is skipped, losing only itself. The
    call sees ALL outline questions but only this transcript, and answers only
    what this transcript actually covers; the merge fills across files.
    """
    try:
        obj = await get_llm().json(
            system=agent_system("business", st),
            user=(
                "You are given ONE interview transcript and the full outline of questions. "
                "Using ONLY this transcript, do BOTH tasks:\n"
                "(1) ANSWERS — for each outline question this transcript actually addresses, "
                "write the final answer with its source. Skip questions it does not cover.\n"
                "(2) FACTOR CHANGES — propose the factor-tree changes this transcript implies "
                "(add a new factor, or modify an existing factor's indicator / granularity / "
                "channel caliber), each traced to a verbatim quote; plus up to 2 cross-source "
                "insights.\n"
                "Each of l1/l2/l3/l4 and indicator must be a SINGLE atomic value — never combine "
                "several (no 'TV/OTV/OOH', no 'A、B'); emit a separate change per combination. "
                "Every emitted value must have BALANCED punctuation — any bracket or quote （）()「」\"\" "
                "opened must also be closed; never leave a dangling '（' or '）'. When several sub-items "
                "share a prefix, write 'PREFIX（a/b/c）' — the system expands that into one COMPLETE "
                "value per item — or emit each as its own complete value. "
                "Return JSON: {\"answers\":[{\"n\":int,\"answer\":str,\"source\":str}],"
                "\"factor_changes\":[{\"op\":\"add|modify\",\"l1\":str,\"l2\":str,\"l3\":str,"
                "\"l4\":str,\"indicator\":str,\"granularity\":str,\"rationale\":str,\"quote\":str}],"
                "\"insights\":[{\"kind\":\"connection|gap|conflict|reference\",\"title\":str,"
                "\"finding\":str,\"confidence\":0-1}]}\n\n"
                f"OUTLINE:\n{qlist}\n\nTRANSCRIPT ({filename}):\n{text}"
            ),
            timeout=_MINUTES_LLM_TIMEOUT,
        )
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}
```

- [ ] **Step 2: Rewrite `writeback_minutes`**

Replace the entire `async def writeback_minutes(eng, st, task)` body (currently lines ~883–980, through the final `insights` loop that adds `Insight` objects) with:

```python
async def writeback_minutes(eng: Engine, st: ProjectState, task: dict) -> None:
    files = _minutes_files(st)
    targets = st.analysis.get("interview_targets", [])
    # Collect references to the REAL business-question dicts (the flattened
    # interview_questions are copies). Data-team items are confirmed by the data
    # team, not covered by stakeholder minutes — skip them. Cap at 28.
    biz: list[tuple[dict, str]] = []
    for t in targets:
        if t.get("layer") == "data":
            continue
        label = t.get("team") or t.get("layer", "")
        for q in t.get("questions", []):
            biz.append((q, label))
    biz = biz[:28]
    qlist = "\n".join(f"{i + 1}. [{label}] {q['question']}" for i, (q, label) in enumerate(biz))

    if not files:
        eng.emit(st, "business", "finding",
                 "No interview minutes uploaded — nothing to write back.", task["id"])
        return

    # One combined call per transcript, run concurrently (the client paces them);
    # every transcript reaches the model instead of only the first few.
    results = await asyncio.gather(
        *(_digest_transcript(fn, tx, qlist, st) for fn, tx in files))
    files_used = sum(1 for r in results if isinstance(r, dict) and r)
    merged = _merge_minutes_digests(results)

    # ── Issue 1: write the AI-parsed final answers back as a COLUMN on each
    # existing question row (not a separate sheet). ──
    answers = merged["answers"]
    answered = 0
    for i, (q, _label) in enumerate(biz):
        a = answers.get(i + 1)
        ans_text = str(a.get("answer", "")).strip() if isinstance(a, dict) else ""
        if ans_text:
            q["finalAnswer"] = ans_text
            q["answerSource"] = str(a.get("source", "")).strip() if isinstance(a, dict) else ""
            answered += 1
    if targets:
        eng.set_analysis(st, "interview_targets", targets)
        eng.set_analysis(st, "interview_questions", _flatten_targets(targets))
        eng.produce(st, "a-interview", body=_interview_sheets(targets), state="draft", agent="business")
    eng.emit(st, "business", "info",
             f"Interview digest: {files_used}/{len(files)} transcripts used, "
             f"{answered}/{len(biz)} business questions answered.", task["id"])
    if files_used < len(files):
        eng.emit(st, "business", "finding",
                 f"Only {files_used}/{len(files)} interview transcripts produced a usable "
                 f"digest — the rest failed (timeout or parse error); re-run to cover them.",
                 task["id"])

    # ── Issue 2: interview-driven factor changes → 'proposed' rows on the factor
    # tree (user accepts at gate 1.4d) + proposals. ──
    changes = merged["factor_changes"]
    if not changes:
        eng.emit(st, "business", "finding",
                 "No interview-driven factor changes were extracted from the minutes — "
                 "review the minutes or re-run if the model timed out.", task["id"])
    elif st.factor_tree is None:
        eng.emit(st, "business", "finding",
                 f"{len(changes)} interview factor changes extracted but no factor tree "
                 f"exists to attach them to.", task["id"])
    else:
        new_rows = [
            FactorRow(
                id=f"ft-iv-{st.tick}-{i}", l1=str(ch.get("l1", "")), l2=str(ch.get("l2", "")),
                l3=str(ch.get("l3", "")), l4=str(ch.get("l4", "")), indicator=str(ch.get("indicator", "")),
                dimension=_default_dimension(st),
                source="interview", status="proposed",
                rationale=f"{ch.get('op', 'add')} · {ch.get('rationale', '')} · granularity: {ch.get('granularity', '—')}",
                evidence=str(ch.get("quote", ""))[:200])
            for i, ch in enumerate(changes)
        ]
        existing_keys = {(r.l1, r.l2, r.l3, r.l4, r.indicator) for r in st.factor_tree.rows}
        atomic = [r for r in atomic_factor_rows(new_rows)
                  if (r.l1, r.l2, r.l3, r.l4, r.indicator) not in existing_keys]
        st.factor_tree.rows.extend(atomic)
        _refresh_factor_analysis(eng, st)
        eng.produce(st, "a-factor-tree", body=_factor_tree_sheet(st.factor_tree),
                    state="proposed", agent="business")
        eng.emit(st, "business", "info",
                 f"{len(atomic)} interview-sourced factor rows proposed on the factor tree "
                 f"(source=interview, pending accept/reject).", task["id"])
    for i, ch in enumerate(changes):
        eng.add_proposal(st, Proposal(
            id=f"p-1.4-{i}", targetArtifactId="a-factor-tree",
            title=f"{ch.get('op', 'add')}: {ch.get('l4') or ch.get('l3') or 'factor'}"[:120],
            summary=str(ch.get("rationale", "")),
            diff=[DiffLine(kind="add", text=f"{ch.get('l3','')}/{ch.get('l4','')} — {ch.get('indicator','')}")],
            evidence=[EvidenceRef(artifactId="a-interview", note=str(ch.get("quote", ""))[:120])],
            confidence=0.7, sourceAgent="business", sourceMode="pipeline", afterTask="1.4"))
    for i, ins in enumerate(merged["insights"]):
        if not isinstance(ins, dict):
            continue
        eng.add_insight(st, Insight(
            id=f"i-1.4-{i}", kind=ins.get("kind", "connection"),
            title=str(ins.get("title", "Insight"))[:120], finding=str(ins.get("finding", "")),
            evidence=[EvidenceRef(artifactId="a-interview")],
            confidence=float(ins.get("confidence", 0.7)),
            actions=[InsightAction(kind="open_asset", label="Open Interview", artifactId="a-interview")],
            afterTask="1.4"))
```

- [ ] **Step 3: Verify no dangling references and the module parses**

```bash
PYTHONPATH=. .venv/bin/python -c "import app.agents.business; print('imports OK')"
grep -n "_load_minutes_text\|_minutes_answers\|_minutes_factor_changes" app/agents/business.py
```
Expected: `imports OK`, and the `grep` prints **nothing** (all three old helpers gone, no caller left).

- [ ] **Step 4: Verify the earlier unit tests still pass**

```bash
PYTHONPATH=. .venv/bin/python tests/test_minutes_merge.py
PYTHONPATH=. .venv/bin/python tests/test_factor_gate_effects.py
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py
```
Expected: all three exit 0 — `api_smoke` now passes again because `writeback_minutes` no longer calls the deleted `_load_minutes_text`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/business.py
git commit -m "fix(s1): digest every interview transcript per-file, not just the first 5 (BREAK 2)"
```

---

## Task 4: End-to-end verification on a real run

**Files:** none (verification only). Uses `backend/scripts/e2e_case.py` and a running backend.

- [ ] **Step 1: Run the full unit suite**

```bash
cd backend
PYTHONPATH=. .venv/bin/python tests/test_factor_gate_effects.py
PYTHONPATH=. .venv/bin/python tests/test_minutes_merge.py
PYTHONPATH=. .venv/bin/python tests/test_ledger.py
PYTHONPATH=. .venv/bin/python tests/test_mapping_suggest.py
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py
PYTHONPATH=. .venv/bin/python -m app.tools._test_tools
```
Expected: every one exits 0. The ledger/mapping/tools suites prove the S2 spine and the tool layer are unaffected.

- [ ] **Step 2: Drive a fresh case and confirm both fixes land**

Start the backend if not already up (`.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010`), then in a Python shell using the e2e helpers (`PYTHONPATH=. .venv/bin/python`):

```python
from scripts.e2e_case import (new_project, upload_s1_docs, drive, state,
                              task_summary, pending_gates)
pid = new_project("Mizone MMM E2E v3 (gate+minutes fix)")
upload_s1_docs(pid)
drive(pid, max_rounds=14)   # runs S1 through its gates
s = state(pid)

# BREAK 1: after d-1.21 + d-1.4 approve, the AI/interview rows are accepted and
# in the map — not stranded at proposed.
from collections import Counter
rows = s["factor_tree"]["rows"]
print("status:", Counter(r["status"] for r in rows))
active = sum(1 for r in rows if r["status"] in ("baseline", "accepted"))
print(f"active {active}/{len(rows)}  (was 135/255 before the fix)")

# BREAK 2: the 1.4 info line reports all transcripts used and answers > 0.
for e in s["events"]:
    if e.get("taskId") == "1.4" and e.get("type") in ("info", "finding"):
        print("1.4:", e["message"])
```

Expected:
- `active` is now well above the pre-fix 135 (every non-rejected proposed row flipped) — the exact number depends on the live LLM output, but the ratio is no longer stuck at "only template rows".
- The `1.4` info line reads `Interview digest: N/N transcripts used, M/28 business questions answered` with `N` = the uploaded transcript count (12 for the seeded docs) and `M > 0`.

- [ ] **Step 3: Record the outcome in the findings log**

Append a short "Verified 2026-07-22" note to `restored/model-input-2.32/qa/e2e-findings.md` under each of the two BREAK sections, stating the observed `active/total` and `transcripts used / answered` from Step 2. Commit:

```bash
git add restored/model-input-2.32/qa/e2e-findings.md
git commit -m "docs: record E2E verification of the two S1 BREAK fixes"
```

---

## Verification Summary

After Task 4, all of this holds from `backend/`:

```bash
PYTHONPATH=. .venv/bin/python tests/test_factor_gate_effects.py   # BREAK 1 unit
PYTHONPATH=. .venv/bin/python tests/test_minutes_merge.py         # BREAK 2 unit
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py             # wiring intact
PYTHONPATH=. .venv/bin/python tests/test_ledger.py                # S2 spine unaffected
PYTHONPATH=. .venv/bin/python -m app.tools._test_tools            # tool layer unaffected
```

- BREAK 1: approving `d-1.21`/`d-1.4` flips the gate's own `proposed` rows to `accepted`, respects manual `rejected`, and the rows enter the 2.1 factor map.
- BREAK 2: every uploaded transcript is digested (per-file), answers merge across files, and coverage is reported in a finding — never silently truncated to the first few.
