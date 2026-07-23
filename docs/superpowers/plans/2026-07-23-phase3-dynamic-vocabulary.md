# Phase 3 — Dynamic Channel/Factor Vocabulary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Move the hardcoded Y/X/spend/money/volume keyword banks + L1 taxonomy literals in `pivot.py` and the interview role tokens behind a per-industry Knowledge resolver, with the current constants as a **byte-identical** fallback — changing no current number when no override exists.

**Architecture:** A `Vocab` frozen dataclass + `build_vocab(industry)` resolver (mirroring `build_range_index`): a `rules`-kind Knowledge template's optional `vocab` payload → else `DEFAULT_VOCAB` (the exact current constants). Thread `vocab` (defaulted) through the `pivot.py` predicates; resolve it once at the S2/S4 entry points from `st.meta.industry`. Interview role tokens read from the interview template with the current list as default.

**Tech Stack:** Python 3, FastAPI, Pydantic. Backend only. Tests: `PYTHONPATH=. .venv/bin/python -m <module>` / `-m pytest tests/ -q` from `backend/`.

## Global Constraints

- **BYTE-PARITY IS THE LOAD-BEARING CONSTRAINT.** With no Knowledge override, every `pivot.py` predicate and the full OLS pipeline must produce **identical** output/numbers to before (R² unchanged). `DEFAULT_VOCAB` = the exact current constant values. If any number drifts, revert — do not update the expectation.
- **Backward-compatible signatures:** new `vocab` param is last and defaulted to `DEFAULT_VOCAB`, so untraced/secondary call sites are untouched.
- **Already done (do NOT redo):** `model_objects` data-derived ordering (Phase 2); the ROI/contribution Knowledge-first range path (`build_range_index` → `RangeIndex.match`, sole consumer `ols_review.py`).
- No hardcoded classification vocabulary may remain as the *only* source (constants survive as defaults). English-only strings. No Pydantic alias on `ProjectState`-serialized fields.
- `tests/test_data_rules.py:97-102` (range values) must stay untouched and green.

---

## File Structure

- `backend/app/agents/vocabulary.py` — **new**: `Vocab` dataclass, `DEFAULT_VOCAB`, `build_vocab(l1, l2)`.
- `backend/app/mmm/pivot.py` — predicates take `vocab: Vocab = DEFAULT_VOCAB`; constants move into `vocabulary.py` (re-exported or referenced).
- `backend/app/domain/models.py` — optional `VocabRules` payload on `KnowledgeTemplate` (or a new field).
- `backend/app/store/template_seed.py` — seed the beverage `rules.vocab` = defaults (documentation).
- `backend/app/ingest/interviews.py` — `_parse_layer_role` reads role tokens from the interview template, default `_ROLE_TOKENS`.
- `backend/app/mmm/_test_vocab_parity.py` — **new** byte-parity test.

---

## Task 1: Capture the pre-refactor predicate outputs (the parity baseline)

**Files:**
- Create: `backend/app/mmm/_test_vocab_parity.py`

**Interfaces:**
- Produces: a runnable test that builds a fixture DataFrame covering every classification token (a Y箱数 row, offtake/sales/gmv rows, spending/花费 rows, rmb/value/gmv money rows, volume 箱/unit rows, `KPI`/`MARKETING FACTOR`/`COMMERCIAL FACTOR` L1 rows, tag rows `metric_type` ∈ {y,kpi,x,driver,spending,spend}) and asserts the current `_is_y_row`/`is_driver_row`/`is_volume_metric_type`/`is_money_metric`/`_is_spend`/`_pick_y_metric` outputs. **Written and committed BEFORE the refactor**, so it captures today's behavior as the frozen expectation.

- [ ] **Step 1: Write the parity test against the CURRENT code**

Build the token-covering fixture and assert the exact current outputs (run each predicate, record the boolean/series result per row, hardcode those as the expected values). Include `_pick_y_metric` on a multi-Y frame. Example skeleton:

```python
"""Byte-parity guard for the pivot classification predicates. Run:
PYTHONPATH=. .venv/bin/python -m app.mmm._test_vocab_parity"""
from __future__ import annotations
import sys
import pandas as pd
from app.mmm.pivot import _is_y_row, is_driver_row, is_volume_metric_type, is_money_metric, _is_spend

def _fixture() -> pd.DataFrame:
    rows = [
        {"l1":"KPI","metric_type":"Y","metric":"销量箱数","value":1.0},
        {"l1":"MARKETING FACTOR","metric_type":"spending","metric":"广告花费","value":1.0},
        {"l1":"COMMERCIAL FACTOR","metric_type":"x","metric":"渠道库存","value":1.0},
        {"l1":"","metric_type":"kpi","metric":"offtake","value":1.0},
        {"l1":"","metric_type":"value","metric":"GMV","value":1.0},
        # …one row per token bank member (箱数/offtake/sales/gmv/出货/完成/volume/箱; spend/投放/费用/金额/promotion; rmb/value/元)…
    ]
    df = pd.DataFrame(rows)
    for c in ("l2","l3","l4","channel_type","month","year","channel","province_group","source"):
        if c not in df: df[c] = ""
    return df

def test_is_y_row_parity():
    df=_fixture(); got=list(_is_y_row(df))
    assert got == [True, False, False, True, False, /*…fill from a real run…*/], got
    print("  _is_y_row parity")
# …one test per predicate; is_volume_metric_type/is_money_metric/_is_spend take strings/series per their signatures…

if __name__ == "__main__":
    fns=[v for k,v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed=0
    for fn in fns:
        try: fn()
        except Exception as e: failed+=1; print(f"  FAIL {fn.__name__}: {e}")
    print(f"{len(fns)-failed}/{len(fns)} passed"); sys.exit(1 if failed else 0)
```

To fill the expected lists: run each predicate on the fixture in a scratch REPL against the CURRENT code and paste the actual outputs as the expectations. The test MUST pass on the unmodified code before you touch anything else.

- [ ] **Step 2: Run to confirm it passes on current code**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.mmm._test_vocab_parity`
Expected: all pass (this is the frozen baseline; it must be green BEFORE the refactor).

- [ ] **Step 3: Commit**

```bash
git add backend/app/mmm/_test_vocab_parity.py
git commit -m "test(pivot): byte-parity baseline for classification predicates"
```

---

## Task 2: `Vocab` dataclass + `DEFAULT_VOCAB` + `build_vocab`

**Files:**
- Create: `backend/app/agents/vocabulary.py`

**Interfaces:**
- Produces: `Vocab` (frozen dataclass: `y_metric_types, y_keywords, y_tags, driver_tags, spend_types, spend_keywords, volume_keywords, money_keywords: frozenset[str]`, `y_l1_labels, driver_l1_labels: frozenset[str]`), `DEFAULT_VOCAB: Vocab` (the exact current `pivot.py` constant values + `{"KPI"}` / `{"MARKETING FACTOR","COMMERCIAL FACTOR"}`), `build_vocab(l1: str|None, l2: str|None) -> Vocab`.

- [ ] **Step 1: Write the failing test**

Add to `_test_vocab_parity.py`:
```python
def test_default_vocab_matches_pivot_constants():
    from app.agents.vocabulary import DEFAULT_VOCAB
    from app.mmm import pivot
    assert DEFAULT_VOCAB.y_metric_types == pivot._Y_METRIC_TYPES
    assert DEFAULT_VOCAB.y_keywords == frozenset(pivot._Y_KEYWORDS)
    assert DEFAULT_VOCAB.spend_keywords == frozenset(pivot._SPEND_KEYWORDS)
    assert DEFAULT_VOCAB.driver_l1_labels == frozenset({"MARKETING FACTOR","COMMERCIAL FACTOR"})
    assert DEFAULT_VOCAB.y_l1_labels == frozenset({"KPI"})
    print("  DEFAULT_VOCAB == current pivot constants")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.mmm._test_vocab_parity`
Expected: FAIL — `vocabulary` module doesn't exist.

- [ ] **Step 3: Implement `vocabulary.py`**

Define `Vocab` (frozen dataclass), `DEFAULT_VOCAB` with the exact current values copied from `pivot.py` (L55-68 + the L1 literal sets), and `build_vocab(l1, l2)`:
```python
def build_vocab(l1, l2):
    try:
        from app.store.templates import get_templates
        tpl = get_templates().best_match("rules", l1, l2)
        vr = getattr(tpl, "vocab", None) if tpl else None
        if vr:
            return _merge(DEFAULT_VOCAB, vr)   # override only the fields the template sets
    except Exception:
        pass
    return DEFAULT_VOCAB
```
`_merge` returns a new `Vocab` taking each field from `vr` when non-empty, else the default.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.mmm._test_vocab_parity`
Expected: PASS (DEFAULT_VOCAB matches; `build_vocab(None,None)` returns DEFAULT_VOCAB since no template `vocab` exists yet).

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/vocabulary.py backend/app/mmm/_test_vocab_parity.py
git commit -m "feat(vocab): Vocab dataclass + DEFAULT_VOCAB + build_vocab resolver"
```

---

## Task 3: Thread `vocab` through the `pivot.py` predicates (byte-parity)

**Files:**
- Modify: `backend/app/mmm/pivot.py`

**Interfaces:**
- Consumes: `Vocab`, `DEFAULT_VOCAB`.
- Produces: `_is_y_row(df, vocab=DEFAULT_VOCAB)`, `is_driver_row(df, vocab=DEFAULT_VOCAB)`, `is_volume_metric_type(x, vocab=DEFAULT_VOCAB)`, `is_money_metric(x, vocab=DEFAULT_VOCAB)`, `_is_spend(df/row, vocab=DEFAULT_VOCAB)`, `_pick_y_metric(rows, vocab=DEFAULT_VOCAB)` — each reading the vocab's sets instead of module constants; the `"KPI"`/`"MARKETING FACTOR"`/`"COMMERCIAL FACTOR"` literals read `vocab.y_l1_labels`/`vocab.driver_l1_labels`.

- [ ] **Step 1: Refactor predicates to read `vocab`**

Change each predicate to accept `vocab=DEFAULT_VOCAB` and reference `vocab.<field>` in place of the module constants (keep the constants defined for `DEFAULT_VOCAB`/imports, or import them from `vocabulary`). Replace the inline `["MARKETING FACTOR","COMMERCIAL FACTOR"]` (L146) with `list(vocab.driver_l1_labels)`, `l1.eq("KPI")` (L132) with membership in `vocab.y_l1_labels`, and the inline volume tokens in `_pick_y_metric` (L186) with `vocab.volume_keywords`.

- [ ] **Step 2: Run the parity test (must stay green)**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.mmm._test_vocab_parity`
Expected: PASS — the default-arg path is byte-identical.

- [ ] **Step 3: Run the number-stability suites**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.mmm._test_synthetic && PYTHONPATH=. .venv/bin/python -m app.tools._test_tools && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel && PYTHONPATH=. .venv/bin/python -m pytest tests/ -q`
Expected: `_test_synthetic` 9/9 (R² identical), `_test_tools` identity green, per-channel green, pytest 131/3 pre-existing. If any number changed, a predicate diverged — fix the threading, do not update the expectation.

- [ ] **Step 4: Commit**

```bash
git add backend/app/mmm/pivot.py
git commit -m "refactor(pivot): predicates read a Vocab (DEFAULT_VOCAB default — byte-identical)"
```

---

## Task 4: Resolve `build_vocab(industry)` at the S2/S4 entry points

**Files:**
- Modify: `backend/app/mmm/pivot.py` (`build_model_frame`, `driver_candidates_by_l4`, `y_candidates`) and `backend/app/agents/stat_scoring.py` (`_monthly_y`) — pass an industry-resolved vocab down.

**Interfaces:**
- Consumes: `st.meta.industry` (l1/l2), `build_vocab`.
- Produces: the project-scoped entry points resolve `vocab = build_vocab(industry.l1, industry.l2)` once and thread it into the predicates they call; other call sites keep the default.

- [ ] **Step 1: Write the override test**

Add to `_test_vocab_parity.py` a test that seeds a `Vocab` override (via a fake template or by calling the predicate with an explicit `vocab`) reclassifying a metric — e.g. a `Vocab` whose `driver_l1_labels` also includes `"MY FACTOR"` makes an `l1="MY FACTOR"` row a driver, which `DEFAULT_VOCAB` does not. Assert the override changes `is_driver_row` output while `DEFAULT_VOCAB` does not.

- [ ] **Step 2: Run to verify it fails / behaves**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.mmm._test_vocab_parity`
Expected: the override test passes only once predicates honor an explicit `vocab` (they do after Task 3) — this test mainly guards that the override path is real.

- [ ] **Step 3: Thread industry-resolved vocab**

In `build_model_frame`/`driver_candidates_by_l4`/`y_candidates` (they receive `df` + an object; add an optional `industry`/`vocab` param or resolve from a passed `st` if available — inspect the call chain from `ols_review`/`ledger`/`stat_scoring` to see what context is threadable) resolve `build_vocab(...)` from the project's industry and pass it to the predicates. Where `st` isn't available at a call site, leave the default (safe — documented). Keep signatures backward-compatible.

- [ ] **Step 4: Run all suites (numbers stable)**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.mmm._test_synthetic && PYTHONPATH=. .venv/bin/python -m app.agents._test_real_per_channel && PYTHONPATH=. .venv/bin/python -m pytest tests/ -q`
Expected: identical numbers; per-channel + real green; pytest 131/3.

- [ ] **Step 5: Commit**

```bash
git add backend/app/mmm/pivot.py backend/app/agents/stat_scoring.py backend/app/mmm/_test_vocab_parity.py
git commit -m "feat(vocab): S2/S4 entry points resolve industry vocab (default unchanged)"
```

---

## Task 5: `rules.vocab` template payload + seed + interview role tokens

**Files:**
- Modify: `backend/app/domain/models.py` (`VocabRules` payload on `KnowledgeTemplate`)
- Modify: `backend/app/store/template_seed.py` (seed beverage `rules.vocab` = defaults)
- Modify: `backend/app/ingest/interviews.py` (`_parse_layer_role` reads template roles, default `_ROLE_TOKENS`)

**Interfaces:**
- Produces: `KnowledgeTemplate.vocab: Optional[VocabRules]` (all fields optional lists); `build_vocab` reads it (Task 2 already calls `getattr(tpl,"vocab",None)`); interview parsing reads `role_tokens` from the interview template with `_ROLE_TOKENS` default.

- [ ] **Step 1: Add the `VocabRules` model + template field**

`VocabRules(CamelModel)` with the eight token lists + two L1-label lists, all `list[str] = []`. Add `vocab: Optional[VocabRules] = None` to `KnowledgeTemplate`. Bump the beverage `rules` builtin version so `_ensure_seeded` heals existing stores.

- [ ] **Step 2: Seed beverage `vocab` = defaults**

In `template_seed.py`, set `tpl-bev-rules.vocab` to the DEFAULT_VOCAB values (documentation that the pack owns them). Add a test asserting `build_vocab("food-bev","beverage")` equals `DEFAULT_VOCAB` (seeded = defaults → no behavior change) AND that an edited override reclassifies.

- [ ] **Step 3: Interview role tokens from template**

`_parse_layer_role` resolves role tokens via `get_templates().best_match("interview", l1, l2)` (distinct `role`s from `interview_questions`, or a new `role_tokens` field), falling back to `_ROLE_TOKENS`. Add a test that the default parse is unchanged and a template override adds a role.

- [ ] **Step 4: Run all suites**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.mmm._test_vocab_parity && PYTHONPATH=. .venv/bin/python -m app.ingest._smoke && PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py && PYTHONPATH=. .venv/bin/python -m pytest tests/ -q`
Expected: all green; seeded-beverage vocab == defaults (numbers unchanged); pytest 131/3.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/models.py backend/app/store/template_seed.py backend/app/ingest/interviews.py backend/app/mmm/_test_vocab_parity.py
git commit -m "feat(vocab): rules.vocab template payload + seed + template-driven interview roles"
```

---

## Self-Review

**Spec coverage:** §3.1 resolver → Task 2. §3.2 Knowledge source → Task 5. §3.3 threading → Tasks 3–4. §3.4 interview roles → Task 5. §4 byte-parity → Tasks 1–3 (baseline captured first). Success criteria 1–4 → all tasks.

**Placeholder scan:** Task 1's expected-list values and Task 4's threading-context ("inspect the call chain") are executor-fills-from-real-code, flagged inline — the test intent + behavior are specified; the executor pastes actual current outputs (Task 1) and threads from the real call sites (Task 4). No silent TODOs.

**Type consistency:** `Vocab`/`DEFAULT_VOCAB`/`build_vocab` names consistent Tasks 2–5; `VocabRules` payload consistent Tasks 2/5; predicates' `vocab=DEFAULT_VOCAB` default consistent Tasks 3–4.

**Critical:** Task 1 (parity baseline) MUST be green on unmodified code before Task 3 touches anything — it is the only guard that the refactor changed no number.
