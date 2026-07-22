# S2 FactorTree-Centred Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the FactorTree the shared canvas of all four S2 modules (2.1–2.4), turn the 2.1 mapping gate into a real decision, move business-validation sign-off to L4/indicator granularity, realign 2.4 scoring with the reference 2.33 workbook, and show tool calls as a live timeline.

**Architecture:** Backend changes are additive to existing seams — one new `ProjectState` field with one new PUT endpoint (following the `anomaly-review` shape), a banding change confined to `data_rules.py`, and one new blueprint decision task. Frontend adds one prop-driven shared component (`FactorTreeCanvas`) that four thin per-module canvases compose, routed by artifact **id** in `ArtifactCanvas`, plus an upgrade of `ToolTrace` into `ToolTimeline`.

**Tech Stack:** Python 3 / FastAPI / Pydantic v2 / pandas / numpy (backend); React 19 / TypeScript / Vite / Zustand / Tailwind (frontend).

**Spec:** `docs/superpowers/specs/2026-07-22-s2-factor-tree-canvas-redesign-design.md`

## Global Constraints

- **No pytest.** Backend tests are runnable scripts. Run one with
  `cd backend && PYTHONPATH=. .venv/bin/python tests/test_<name>.py`. Every test file ends
  with an `if __name__ == "__main__":` block calling each test and printing a summary line.
- **Frontend verification** is `cd frontend && npm run build` (runs `tsc -b && vite build`)
  and `npm run lint`. There is no unit-test runner; do not add one.
- **Product copy is English-only.** All user-visible strings in UI and in artifact bodies
  must be English. (Existing `summary` / `basis_note` fields in the blueprint contain Chinese;
  leave existing ones alone, but write new ones in English.)
- **`ProjectState`'s own fields are never aliased.** It is a plain `BaseModel`; an aliased
  field emits a camelCase key the frontend's snake_case reader silently misses. Nested models
  (which are `CamelModel`) do use aliases.
- **Tool wrappers stay identity wrappers.** `reference_cv`, `vif_all`, `pearson` are unchanged
  by this plan. `backend/app/tools/_test_tools.py` must keep passing untouched.
- **Rule JSON is `lru_cache`d.** `Assets/数据智能体知识库/机器可读/statistical-scoring.json` is
  loaded through `data_rules.load_rule` with `@lru_cache`; after editing it, restart the
  process (a fresh test-script run is a fresh process, so tests see the change).
- **Contracts move in pairs:** `domain/blueprint.py` ↔ `lib/scenario.ts`;
  `domain/models.py` ↔ `lib/types.ts`; `app/main.py` ↔ `api/client.ts`.
- **Commit after every task** with a conventional-commit message (`feat:` / `fix:` / `refactor:`).

## File Structure

**Backend — modified:**
- `app/agents/data_rules.py` — statistical bands + verdict (Task 1)
- `Assets/数据智能体知识库/机器可读/statistical-scoring.json` — the displayed rubric (Task 1)
- `app/agents/stat_scoring.py` — verdict → disposition map, rule sheet (Task 2)
- `app/agents/data.py` — zero-score warning finding, mapping gap finding, `_bv_groups` pairs (Tasks 2, 5, 6)
- `app/tools/registry.py` — `stat.*` documentation text (Task 2)
- `app/domain/models.py` — `BvSignoff` / `BvSignoffBook` (Task 3)
- `app/store/state.py` — `bv_signoff` field (Task 3)
- `app/main.py` — `PUT /bv-signoff` (Task 3)
- `app/agents/ledger.py` — pair-granular signoff layer (Task 4)
- `app/domain/blueprint.py` — task `2.1d`, `2.2` dependency (Task 6)

**Backend — tests modified/created:**
- `tests/test_data_rules.py`, `tests/test_stat_scoring.py` (Task 1)
- `tests/test_bv_signoff.py` — **new** (Tasks 3, 4)
- `tests/test_ledger.py` (Task 4)
- `tests/test_s2_roundtrip.py` (Task 6)

**Frontend — created:**
- `src/components/project/factor-tree/types.ts` — `FactorCanvasRow` (Task 7)
- `src/components/project/factor-tree/FactorTreeCanvas.tsx` — the shared tree (Task 7)
- `src/components/project/factor-tree/useLedgerIndex.ts` — ledger lookup hook (Task 7)
- `src/components/project/factor-tree/keys.ts` — `indicatorKey` normaliser (Task 7)
- `src/components/project/canvas/DataProcessingCanvas.tsx` (Task 8)
- `src/components/project/canvas/QualityCanvas.tsx` (Task 9)
- `src/components/project/canvas/StatCanvas.tsx` (Task 11)
- `src/components/tools/ToolTimeline.tsx` (Task 12)

**Frontend — modified:**
- `src/components/project/canvas/ArtifactCanvas.tsx` — id-keyed routing (Tasks 8, 9, 11)
- `src/components/project/ArtifactDetail.tsx` — drop redundant `STRUCTURED_EDITORS` entries, mount `ToolTimeline` (Tasks 9, 11, 12)
- `src/components/project/validation/BusinessValidationView.tsx` — pair sign-off (Task 10)
- `src/components/project/StatScoreEditor.tsx` — three-band legend (Task 11)
- `src/lib/types.ts`, `src/api/client.ts`, `src/store/useSimStore.ts`, `src/lib/scenario.ts`

---

## Task 1: Realign 2.4 statistical bands and total with reference 2.33

**Files:**
- Modify: `backend/app/agents/data_rules.py:32-35`, `:148-176`, `:244-262`, `:11-14`
- Modify: `Assets/数据智能体知识库/机器可读/statistical-scoring.json`
- Test: `backend/tests/test_data_rules.py:55-70`, `backend/tests/test_stat_scoring.py:31-63`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `score_statistical(cv: float, pearson: float, vif: float) -> StatScore` with
  `StatScore(cv_score, pearson_score, vif_score, total, verdict, drop)` where each band score is
  one of `0.0 | 0.5 | 1.0`, `total = cv_score * pearson_score * vif_score`, `verdict` is one of
  `"Good" | "Acceptable" | "unconsiderable"`, and `drop is True` exactly when `total == 0.0`.
  Module constant `STAT_GOOD = 0.5` (strictly above → Good). `STAT_ACCEPTABLE` and
  `STAT_SEVERE_VIF` are **removed**.

- [ ] **Step 1: Update the band tests to the new three-band rule**

In `backend/tests/test_data_rules.py`, replace the body of `test_statistical_bands`
(lines 55-58) and `test_statistical_verdict_thresholds` (lines 61-69) with:

```python
def test_statistical_bands() -> None:
    """2.33 bands are 0 / 0.5 / 1 per test. VIF is scored the workbook's way:
    VIF = 1 is the GOOD end (no collinearity), VIF >= 5 is the bad end."""
    assert [score_statistical(cv, 0.4, 1).cv_score for cv in (0.04, 0.07, 0.15, 0.5)] == [0.0, 0.5, 1.0, 1.0]
    assert [score_statistical(0.3, r, 1).pearson_score for r in (0.05, 0.2, 0.4, 0.8)] == [0.0, 0.5, 1.0, 1.0]
    assert [score_statistical(0.3, 0.4, v).vif_score for v in (1, 3, 7, 12)] == [1.0, 0.5, 0.0, 0.0]
    print("✓ statistical bands")


def test_statistical_verdict_thresholds() -> None:
    """Total is the PRODUCT of the three bands, so a single failing test zeroes it."""
    good = score_statistical(0.5, 0.8, 1)      # 1 * 1 * 1
    assert good.total == 1.0 and good.verdict == "Good" and not good.drop
    mid = score_statistical(0.15, 0.2, 3)      # 1 * 0.5 * 0.5
    assert mid.total == 0.25 and mid.verdict == "Acceptable" and not mid.drop
    dead = score_statistical(0.04, 0.8, 1)     # 0 * 1 * 1 — flat series
    assert dead.total == 0.0 and dead.verdict == "unconsiderable" and dead.drop
    print("✓ statistical verdict thresholds")


def test_severe_collinearity_zeroes_the_total() -> None:
    """A strong, volatile indicator still dies on collinearity — VIF >= 5 scores 0
    and the product carries that to the verdict without a separate override."""
    sc = score_statistical(0.3, 0.8, 12)
    assert sc.vif_score == 0.0 and sc.total == 0.0
    assert sc.verdict == "unconsiderable" and sc.drop
    print("✓ severe collinearity zeroes the total")
```

Then update the imports at the top of the file: remove `STAT_SEVERE_VIF` if imported, and
rename the old severe-VIF test in the `__main__` block to `test_severe_collinearity_zeroes_the_total`.

- [ ] **Step 2: Update the stat-scoring tests**

In `backend/tests/test_stat_scoring.py`, change the import block (lines 10-17) to drop
`STAT_ACCEPTABLE` and keep `STAT_GOOD`:

```python
from app.agents.data_rules import (
    STAT_GOOD,
    VIF_MAX,
    reference_cv,
    score_statistical,
    vif_all,
)
```

Replace `test_band_boundaries` (line 31) and `test_verdict_thresholds` (line 51) with:

```python
def test_band_boundaries() -> None:
    for cv, want in [(0.0, 0.0), (0.05, 0.0), (0.06, 0.5), (0.099, 0.5), (0.1, 1.0), (9.9, 1.0)]:
        got = score_statistical(cv, 0.0, 1.0).cv_score
        assert got == want, f"cv={cv} → {got}, want {want}"
    for r, want in [(0.0, 0.0), (-0.09, 0.0), (0.1, 0.5), (-0.29, 0.5), (0.3, 1.0), (-0.99, 1.0)]:
        got = score_statistical(0.0, r, 1.0).pearson_score
        assert got == want, f"r={r} → {got}, want {want}"
    for vif, want in [(1.0, 1.0), (1.01, 0.5), (4.99, 0.5), (5.0, 0.0), (99.0, 0.0)]:
        got = score_statistical(0.0, 0.0, vif).vif_score
        assert got == want, f"vif={vif} → {got}, want {want}"
    print("✓ band boundaries")


def test_verdict_thresholds() -> None:
    """Total = CV x Pearson x VIF; only an all-pass product (1.0) is Good."""
    assert score_statistical(0.2, 0.6, 1.0).verdict == "Good"
    ac = score_statistical(0.07, 0.4, 1.0)          # 0.5 * 1 * 1
    assert ac.total == 0.5 and ac.verdict == "Acceptable"
    un = score_statistical(0.04, 0.2, 2.0)          # 0 * 0.5 * 0.5
    assert un.total == 0.0 and un.verdict == "unconsiderable"
    assert STAT_GOOD == 0.5
    print("✓ verdict thresholds")
```

- [ ] **Step 3: Run both test files to verify they fail**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_data_rules.py
```

Expected: FAIL — `AssertionError` in `test_statistical_bands` (the VIF list comes back
`[0.0, 0.5, 1.0, 2.0]` instead of `[1.0, 0.5, 0.0, 0.0]`).

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_stat_scoring.py
```

Expected: FAIL — `ImportError: cannot import name 'STAT_GOOD'`… no; it imports fine but
`test_band_boundaries` fails on `cv=9.9 → 2.0, want 1.0`.

- [ ] **Step 4: Rewrite the bands and the verdict in `data_rules.py`**

Replace lines 32-35:

```python
# Statistical verdict thresholds — Total = CV x Pearson x VIF in [0, 1].
# Only an all-pass product (1.0) clears STAT_GOOD; a single failing test zeroes
# the product, which is exactly the strictness the 2.33 workbook intends.
STAT_GOOD = 0.5
```

Replace `_cv_band` / `_pearson_band` / `_vif_band` (lines 148-176):

```python
def _cv_band(cv: float) -> float:
    """2.33 volatility band. A near-flat series cannot explain KPI movement."""
    if cv <= 0.05:
        return 0.0
    if cv < 0.1:
        return 0.5
    return 1.0


def _pearson_band(r: float) -> float:
    """2.33 correlation band on |r| against the KPI."""
    a = abs(r)
    if a < 0.1:
        return 0.0
    if a < 0.3:
        return 0.5
    return 1.0


def _vif_band(vif: float) -> float:
    """2.33 collinearity band. Note the direction: VIF = 1 (no collinearity) is
    the GOOD end and scores 1; VIF >= 5 is明显共线性 and scores 0.

    The workbook writes the top band as "VIF = 1"; since ``vif_all`` floors its
    output at 1.0, this is implemented as ``vif <= 1.0`` — the same set of
    values, without a float-equality trap.
    """
    if vif >= 5.0:
        return 0.0
    if vif > 1.0:
        return 0.5
    return 1.0
```

Replace `score_statistical` (lines 244-262):

```python
def score_statistical(cv: float, pearson: float, vif: float) -> StatScore:
    """Score one variable on CV / Pearson / VIF per the 2.33 bands.

    Total is the **product** of the three bands, matching the workbook's
    ``Final score = 完整性*颗粒度*真实性*一致性`` form applied to the three
    statistical tests. A single failing test therefore zeroes the total, and a
    zero total is the drop condition — no separate severe-collinearity override
    is needed, because VIF >= 5 already scores 0 on its own.
    """
    cv_s = _cv_band(cv)
    pear_s = _pearson_band(pearson)
    vif_s = _vif_band(vif)
    total = round(cv_s * pear_s * vif_s, 4)
    if total > STAT_GOOD:
        verdict = "Good"
    elif total > 0.0:
        verdict = "Acceptable"
    else:
        verdict = "unconsiderable"
    return StatScore(cv_s, pear_s, vif_s, total, verdict, drop=total == 0.0)
```

Update the module docstring line 13-14:

```python
2.33 statistical screening — three tests, each 0 / 0.5 / 1:
    CV (volatility) · Pearson (vs KPI) · VIF (collinearity); Total = product.
```

- [ ] **Step 5: Update the rule JSON so the displayed rubric matches the code**

Replace the `tests` and `verdict` blocks of
`Assets/数据智能体知识库/机器可读/statistical-scoring.json` with:

```json
  "tests": {
    "cv": {
      "label": "波动性检验",
      "metric": "波动系数CV = 方差/均值 (数据先缩放到0-1)",
      "bands": [
        { "score": 0, "cond": "CV<=0.05", "meaning": "变异极小，强烈建议剔除或替代" },
        { "score": 0.5, "cond": "0.05<CV<0.1", "meaning": "变异弱，除非不可替代否则不入模" },
        { "score": 1, "cond": "CV>=0.1", "meaning": "变异高，波动较为明显" }
      ]
    },
    "pearson": {
      "label": "相关性检验",
      "metric": "Pearson r (因子 vs KPI, 单变量)",
      "bands": [
        { "score": 0, "cond": "|r|<0.1", "meaning": "基本不相关，不建议入模" },
        { "score": 0.5, "cond": "0.1<=|r|<0.3", "meaning": "弱相关，视因子数量/重要性决定" },
        { "score": 1, "cond": "|r|>=0.3", "meaning": "较为相关，建议入模" }
      ]
    },
    "vif": {
      "label": "共线性检验",
      "metric": "VIF (因子 vs 因子)",
      "bands": [
        { "score": 0, "cond": "VIF>=5", "meaning": "存在明显共线性，需要关注" },
        { "score": 0.5, "cond": "1<VIF<5", "meaning": "中等共线性，一般可接受" },
        { "score": 1, "cond": "VIF=1", "meaning": "该特征与其他特征无线性相关" }
      ],
      "note": "VIF越大共线性越严重；高VIF指标需降维/合并/剔除，结合业务取舍"
    }
  },
  "verdict": {
    "formula": "Total = CV × Pearson × VIF",
    "thresholds": [
      { "label": "Good", "cond": "Total>0.5" },
      { "label": "Acceptable", "cond": "0<Total<=0.5" },
      { "label": "unconsiderable", "cond": "Total=0" }
    ]
  },
```

- [ ] **Step 6: Run both test files to verify they pass**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_data_rules.py
```
Expected: PASS, ending with `all data-rule tests passed` (or the file's existing summary line).

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_stat_scoring.py
```
Expected: PASS, ending with `all statistical-score tests passed`.

- [ ] **Step 7: Verify the identity-wrapper contract still holds**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python app/tools/_test_tools.py
```
Expected: PASS. If it fails, the tool layer has started doing arithmetic — revert rather than
update the expectation.

- [ ] **Step 8: Commit**

```bash
git add backend/app/agents/data_rules.py backend/tests/test_data_rules.py \
        backend/tests/test_stat_scoring.py "Assets/数据智能体知识库/机器可读/statistical-scoring.json"
git commit -m "feat: realign 2.4 statistical scoring with reference 2.33 (three bands, multiplicative total)"
```

---

## Task 2: Propagate the new 2.4 scoring to text, findings and tool docs

**Files:**
- Modify: `backend/app/agents/stat_scoring.py:11-14`, `:192-216`
- Modify: `backend/app/agents/data.py:678-762`
- Modify: `backend/app/tools/registry.py:254-353`
- Test: `backend/tests/test_s2_roundtrip.py`

**Interfaces:**
- Consumes: `score_statistical` from Task 1 (bands `0 | 0.5 | 1`, product total, `drop == (total == 0)`).
- Produces: `stat_screening` emits a `TaskFinding` with `tone="flag"` naming every indicator
  whose total is 0 and which test zeroed it. No signature changes.

- [ ] **Step 1: Update the `stat_scoring.py` docstring and column header**

Replace lines 11-14 of `backend/app/agents/stat_scoring.py`:

```python
Each maps to a 0 / 0.5 / 1 band (``data_rules``); Total = CV × Pearson × VIF drives
the Good / Acceptable / Unconsiderable verdict — a single failing test zeroes the
product and drops the indicator. The result is a ``StatScorecard`` the human reviews
on the Canvas (per-indicator include / review / drop). Numbers are computed from the
real long table via pandas/numpy — never from the LLM.
```

`_DISPOSITION_DEFAULT` (lines 31-35) is unchanged — the verdict vocabulary is the same.

- [ ] **Step 2: Add the zero-score warning finding in `data.py`**

In `backend/app/agents/data.py`, inside `stat_screening` (starts line 694), just before the
existing `eng.add_findings(...)` call, add:

```python
    # A zero total means one test failed outright. Say WHICH one — "unconsiderable"
    # on its own gives the reviewer nothing to act on.
    def _zero_reason(r: StatScoreRow) -> str:
        failed = [name for name, score in
                  (("volatility", r.cv_score), ("correlation", r.pearson_score),
                   ("collinearity", r.vif_score)) if score == 0.0]
        return " and ".join(failed) or "screening"

    zeroed = [r for r in card.rows if r.total == 0.0]
    if zeroed:
        labels = [f"{_label(r)} (failed {_zero_reason(r)})" for r in zeroed]
        findings.append(TaskFinding(
            text="Zero statistical score — these indicators cannot enter the model: "
                 + "; ".join(labels[:5])
                 + (f" +{len(labels) - 5} more" if len(labels) > 5 else ""),
            tone="flag", evidence=[EvidenceRef(artifactId="a-stat-tests")]))
```

`_label` is the existing local helper at line 715; if it is defined **after** this point in the
function, move this block below its definition. `StatScoreRow`, `TaskFinding` and `EvidenceRef`
are already imported in this module.

- [ ] **Step 3: Update the `stat.*` tool documentation**

In `backend/app/tools/registry.py`, for `stat.cv` (line 255) replace `outputSummary`, the last
`logic` bullet, and `params`:

```python
        outputSummary="CV per indicator → the 0 / 0.5 / 1 volatility band",
```
```python
            "Band: CV ≤ 0.05 → 0 · CV < 0.1 → 0.5 · CV ≥ 0.1 → 1.",
        ],
        params=[
            ["band 0", "CV ≤ 0.05", "Effectively flat — cannot explain KPI movement"],
            ["band 0.5", "0.05 < CV < 0.1", "Low volatility"],
            ["band 1", "CV ≥ 0.1", "Adequate volatility"],
        ],
```

For `stat.pearson` (line 286):

```python
        outputSummary="Signed r per indicator → the 0 / 0.5 / 1 correlation band",
```
```python
            "Band on |r|: < 0.1 → 0 · < 0.3 → 0.5 · ≥ 0.3 → 1.",
        ],
        params=[
            ["band 0", "|r| < 0.1", "No usable relationship with the KPI"],
            ["band 0.5", "0.1 ≤ |r| < 0.3", "Weak relationship"],
            ["band 1", "|r| ≥ 0.3", "Moderate or strong relationship"],
            ["MIN_ABS_PEARSON", "0.1", "Below this the 2.5x proposal leaves the X unticked"],
        ],
```

For `stat.vif` (line 319) replace `outputSummary`, the `scenario` sentence about VIF ≥ 10, the
last `logic` bullet, and `params`:

```python
        outputSummary="VIF per indicator → the 0 / 0.5 / 1 collinearity band",
```
```python
        scenario=(
            "Runs inside step 2.4 ONCE across the whole candidate set — this is why rejected "
            "indicators must be filtered out before the call: a dead indicator's collinearity "
            "would inflate the VIF of the ones still in play. Note the band direction: VIF = 1 "
            "(no collinearity) is the GOOD end and scores 1, while VIF ≥ 5 scores 0 — and "
            "because the 2.4 Total is the product of the three bands, that zero drops the "
            "indicator no matter how well it scored on CV and Pearson."),
```
```python
            "Floor at 1.0, cap at VIF_MAX. Band: VIF ≥ 5 → 0 · 1 < VIF < 5 → 0.5 · VIF ≤ 1 → 1.",
        ],
        params=[
            ["VIF_MAX", "1000.0", "Display/scoring cap"],
            ["band 0", "VIF ≥ 5", "Clear collinearity — zeroes the 2.4 Total"],
            ["band 0.5", "1 < VIF < 5", "Mild collinearity, generally acceptable"],
            ["band 1", "VIF ≤ 1", "No linear relationship with the other indicators"],
        ],
```

- [ ] **Step 4: Run the S2 round-trip and tools tests**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python app/tools/_test_tools.py
```
Expected: PASS.

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_s2_roundtrip.py
```
Expected: PASS. This file asserts `"Acceptable" in st.decisions["d-2.4"].question` (line 100);
the runtime question rewrite in `stat_screening` still uses that word, so it should hold. If it
fails because zero indicators now land in the `Acceptable` bucket on the reference dataset,
adjust the assertion to check the question is non-empty and mentions the screening, and note
why in the commit message.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/stat_scoring.py backend/app/agents/data.py \
        backend/app/tools/registry.py backend/tests/test_s2_roundtrip.py
git commit -m "feat: warn on zero statistical scores and update stat tool docs for the 2.33 bands"
```

---

## Task 3: Persist business-validation sign-off at indicator granularity

**Files:**
- Modify: `backend/app/domain/models.py` (append near `AnomalyReview`)
- Modify: `backend/app/store/state.py:90` (add field after `anomaly_review`)
- Modify: `backend/app/main.py:784-795` (add endpoint after `update_anomaly_review`)
- Create: `backend/tests/test_bv_signoff.py`
- Modify: `frontend/src/lib/types.ts`, `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `BvSignoff` — Pydantic `CamelModel` with fields `l1, l2, l3, l4, indicator: str`,
    `status: str` (`"accepted" | "denied"`), `note: str`.
  - `BvSignoffBook` — `CamelModel` with `rows: list[BvSignoff] = []`.
  - `ProjectState.bv_signoff: Optional[BvSignoffBook] = None` (snake_case, **no alias**).
  - `PUT /api/projects/{project_id}/bv-signoff` accepting a `BvSignoffBook`, returning it.
  - TypeScript `BvSignoff` / `BvSignoffBook` and `api.updateBvSignoff(projectId, book)`.

> **Refinement vs the spec:** the spec sketched `bv_signoff` as a `dict[key → {...}]`. This plan
> uses a `rows` list instead, matching `QualityScorecard` / `StatScorecard` / `AnomalyReview`,
> which every other S2 slice already follows on both sides of the wire. The key space is
> unchanged — `(l4, indicator)` normalised the ledger's way.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_bv_signoff.py`:

```python
"""2.3 business-validation sign-off at (L4, indicator) granularity.

Sign-off used to live in the a-business-validation artifact body at L3 granularity,
so denying one chart killed every indicator under that factor. It is now project
state, keyed like every other S2 layer. Runnable: PYTHONPATH=. .venv/bin/python tests/test_bv_signoff.py
"""
from __future__ import annotations

from app.domain.models import BvSignoff, BvSignoffBook
from app.store.state import ProjectState, danone_meta, initial_state


def _state() -> ProjectState:
    return initial_state(danone_meta())


def test_state_defaults_to_no_signoff() -> None:
    st = _state()
    assert st.bv_signoff is None, "a fresh project has no sign-off recorded"
    print("✓ bv_signoff defaults to None")


def test_book_round_trips_through_json() -> None:
    """ProjectState serializes its own fields snake_case with no alias — if this
    key ever became `bvSignoff`, the frontend's snake_case reader would miss it."""
    st = _state()
    st.bv_signoff = BvSignoffBook(rows=[
        BvSignoff(l1="A", l2="B", l3="C", l4="TV", indicator="曝光量",
                  status="denied", note="Chart rejected by the client"),
        BvSignoff(l1="A", l2="B", l3="C", l4="TV", indicator="花费", status="accepted"),
    ])
    dumped = st.model_dump(by_alias=True)
    assert "bv_signoff" in dumped, "ProjectState fields must stay snake_case"
    rows = dumped["bv_signoff"]["rows"]
    assert len(rows) == 2
    assert rows[0]["status"] == "denied" and rows[0]["l4"] == "TV"
    restored = ProjectState.model_validate(dumped)
    assert restored.bv_signoff is not None
    assert [r.status for r in restored.bv_signoff.rows] == ["denied", "accepted"]
    print("✓ bv_signoff round-trips through JSON")


if __name__ == "__main__":
    test_state_defaults_to_no_signoff()
    test_book_round_trips_through_json()
    print("\nall bv-signoff tests passed")
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_bv_signoff.py
```
Expected: FAIL with `ImportError: cannot import name 'BvSignoff' from 'app.domain.models'`.

- [ ] **Step 3: Add the models**

In `backend/app/domain/models.py`, immediately after the `AnomalyReview` class, add:

```python
class BvSignoff(CamelModel):
    """One indicator's client sign-off at 2.3 Business Validation.

    Keyed by ``(l4, indicator)`` — the same key space the indicator ledger and every
    other S2 filter layer uses. ``denied`` is what rejects; anything else (including
    a missing row) means "not individually reviewed", which the d-2.3 gate covers.
    """

    l1: str = ""
    l2: str = ""
    l3: str = ""
    l4: str = ""
    indicator: str = ""
    status: str = "accepted"  # accepted | denied
    note: str = ""


class BvSignoffBook(CamelModel):
    rows: list[BvSignoff] = []
```

- [ ] **Step 4: Add the `ProjectState` field**

In `backend/app/store/state.py`, after the `anomaly_review` field (line 90), add:

```python
    # S2 · 2.3: the client's per-indicator sign-off, at (L4, metric) granularity.
    # A denied indicator is rejected by the ledger's signoff layer and inherited by
    # every later layer. Snake_case with no alias, like every ProjectState field.
    bv_signoff: Optional[BvSignoffBook] = None
```

Add `BvSignoffBook` to the `from app.domain.models import (...)` block at the top of the file.

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_bv_signoff.py
```
Expected: PASS, ending with `all bv-signoff tests passed`.

- [ ] **Step 6: Add the endpoint**

In `backend/app/main.py`, after `update_anomaly_review` (line 795), add:

```python
@app.put("/api/projects/{project_id}/bv-signoff")
async def update_bv_signoff(project_id: str, body: BvSignoffBook) -> dict:
    """Persist the client's per-indicator sign-off from 2.3 Business Validation.

    A denied indicator is rejected by the ledger's signoff layer, so saving here
    changes what 2.4 scores and what ever reaches the model. The a-business-validation
    artifact is not re-rendered — its body holds the charts, and the sign-off is read
    from project state, not from the body.
    """
    st = _require_state(project_id)
    st.bv_signoff = body
    ledger.invalidate_universe(project_id)
    get_store().save(project_id)
    return body.model_dump(by_alias=True)
```

Add `BvSignoffBook` to the `from app.domain.models import (...)` block, and confirm
`from app.agents import ledger` is already imported (it is, for `d-2.5`); if not, add it.

- [ ] **Step 7: Verify the API still starts and the smoke test passes**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py
```
Expected: PASS.

- [ ] **Step 8: Add the frontend types**

In `frontend/src/lib/types.ts`, immediately after the `AnomalyReview` interface, add:

```ts
export type BvSignoffStatus = 'accepted' | 'denied'

/** 2.3 client sign-off for one indicator, keyed by (l4, indicator). */
export interface BvSignoff {
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
  status: BvSignoffStatus
  note: string
}

export interface BvSignoffBook {
  rows: BvSignoff[]
}
```

- [ ] **Step 9: Add the API client method**

In `frontend/src/api/client.ts`, after `updateAnomalyReview` (line 195), add:

```ts
  updateBvSignoff: (projectId: string, book: BvSignoffBook) =>
    req<BvSignoffBook>(`${p(projectId)}/bv-signoff`, {
      method: 'PUT', body: JSON.stringify(book),
    }),
```

Add `BvSignoffBook` to the `import type { … } from '../lib/types'` block at the top.

- [ ] **Step 10: Type-check the frontend**

```bash
cd "frontend" && npm run build
```
Expected: build succeeds (no TypeScript errors).

- [ ] **Step 11: Commit**

```bash
git add backend/app/domain/models.py backend/app/store/state.py backend/app/main.py \
        backend/tests/test_bv_signoff.py frontend/src/lib/types.ts frontend/src/api/client.ts
git commit -m "feat: persist business-validation sign-off per indicator (bv_signoff + PUT endpoint)"
```

---

## Task 4: Make the ledger's signoff layer pair-granular

**Files:**
- Modify: `backend/app/agents/ledger.py:148-160`, `:215-225`, `:334-397`
- Test: `backend/tests/test_bv_signoff.py` (extend), `backend/tests/test_ledger.py`

**Interfaces:**
- Consumes: `BvSignoffBook` and `ProjectState.bv_signoff` from Task 3.
- Produces:
  - `signoff_denied_pairs(st) -> set[tuple[str, str]]` — the new pair-level source.
  - `signoff_drop_pairs(st) -> set[tuple[str, str]]` — unchanged signature; now the union of
    `signoff_denied_pairs` and the legacy L3 expansion.
  - `signoff_reject_l3(st)` — kept as the legacy reader, unchanged signature.
  - `drops_before(st, layer)` and `_LAYER_PAIRS` are unchanged; `indicator_ledger` now judges
    the signoff layer on pairs.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_bv_signoff.py` (before the `__main__` block), and add
`from app.agents.ledger import drops_before, indicator_ledger, signoff_drop_pairs` plus
`from app.domain.models import ArtifactInstance` to the imports:

```python
def test_denied_indicator_drops_only_itself() -> None:
    """The whole point of the change: denying one chart must not kill its siblings."""
    st = _state()
    rows = indicator_ledger(st)
    assert rows, "the reference dataset must yield indicators"
    victim = rows[0]
    sibling = next((r for r in rows
                    if r.l3 == victim.l3 and (r.l4, r.indicator) != (victim.l4, victim.indicator)),
                   None)
    st.bv_signoff = BvSignoffBook(rows=[BvSignoff(
        l1=victim.l1, l2=victim.l2, l3=victim.l3, l4=victim.l4,
        indicator=victim.indicator, status="denied", note="client rejected the chart")])
    dropped = signoff_drop_pairs(st)
    assert (victim.l4.strip().lower(), victim.indicator.strip().lower()) in dropped
    if sibling is not None:
        assert (sibling.l4.strip().lower(), sibling.indicator.strip().lower()) not in dropped, \
            "denying one indicator must not deny its L3 siblings"
    print("✓ a denied indicator drops only itself")


def test_denial_is_inherited_by_the_statistical_layer() -> None:
    st = _state()
    victim = indicator_ledger(st)[0]
    st.bv_signoff = BvSignoffBook(rows=[BvSignoff(
        l1=victim.l1, l2=victim.l2, l3=victim.l3, l4=victim.l4,
        indicator=victim.indicator, status="denied")])
    key = (victim.l4.strip().lower(), victim.indicator.strip().lower())
    assert key in drops_before(st, "statistical"), "2.4 must inherit the 2.3 denial"
    assert key not in drops_before(st, "signoff"), "a layer never inherits its own verdict"
    print("✓ denial is inherited by the statistical layer")


def test_legacy_l3_signoff_still_rejects() -> None:
    """Projects saved before this change stored sign-off in the artifact body."""
    st = _state()
    victim = indicator_ledger(st)[0]
    st.artifacts.append(ArtifactInstance(
        id="a-business-validation", name="Business Validation", type="report",
        stage="s2", format="validation", state="confirmed",
        body={"kpiMetric": "", "groups": [{"l3": victim.l3, "signoff": "no"}], "anomalies": []}))
    dropped = signoff_drop_pairs(st)
    assert (victim.l4.strip().lower(), victim.indicator.strip().lower()) in dropped, \
        "the legacy L3 sign-off path must keep working"
    print("✓ legacy L3 sign-off still rejects")
```

Register the three new tests in the `__main__` block.

- [ ] **Step 2: Run to verify the first test fails**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_bv_signoff.py
```
Expected: FAIL — `AssertionError` in `test_denied_indicator_drops_only_itself`, because
`signoff_drop_pairs` currently reads only the artifact body and returns an empty set.

> If `ArtifactInstance(...)` raises a validation error, read the model in
> `backend/app/domain/models.py` and supply the required fields; the field list above matches
> the fields the ledger reads plus the model's required ones.

- [ ] **Step 3: Add `signoff_denied_pairs` and widen `signoff_drop_pairs`**

In `backend/app/agents/ledger.py`, replace `signoff_drop_pairs` (lines 215-225) with:

```python
def signoff_denied_pairs(st: ProjectState) -> set[tuple[str, str]]:
    """Indicators the client explicitly denied at 2.3, in the (l4, metric) key space.

    Only ``denied`` rejects. A missing row means "not individually reviewed", which
    the global ``d-2.3`` gate covers — treating it as a rejection would empty the
    model before the human ever opened the deck.
    """
    book = getattr(st, "bv_signoff", None)
    if book is None:
        return set()
    return {_norm_pair(r.l4, r.indicator) for r in book.rows if _norm(r.status) == "denied"}


def signoff_drop_pairs(st: ProjectState) -> set[tuple[str, str]]:
    """Everything 2.3 rejected: per-indicator denials, plus the legacy per-L3 sign-off.

    Sign-off is now recorded per indicator (``ProjectState.bv_signoff``). Projects
    saved before that stored it in the a-business-validation body at L3 granularity;
    that path is still read and expanded against the indicator universe, so their
    verdicts survive.
    """
    pairs = signoff_denied_pairs(st)
    rejected_l3 = signoff_reject_l3(st)
    if rejected_l3:
        pairs |= {key for key, c in _universe(st).items()
                  if _norm(c.get("l3")) in rejected_l3}
    return pairs
```

- [ ] **Step 4: Judge the signoff layer on pairs inside `indicator_ledger`**

In `indicator_ledger`, replace the pre-computed `no_signoff = signoff_reject_l3(st)` line
(around line 345) with:

```python
    sign_drop = signoff_drop_pairs(st)
```

and replace the signoff branch (lines 392-397) with:

```python
        # 2.3 — the client's sign-off, per indicator (legacy projects: per L3).
        if _matches(key, sign_drop):
            rule("signoff", STATUS_REJECTED,
                 "Not signed off in business validation.")
        else:
            rule("signoff", STATUS_ADOPTED, "Covered by the business-validation sign-off.")
```

If `no_signoff` is referenced anywhere else in the function, remove those references too —
`grep -n "no_signoff" backend/app/agents/ledger.py` must come back empty afterwards.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_bv_signoff.py
```
Expected: PASS, ending with `all bv-signoff tests passed`.

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_ledger.py
```
Expected: PASS — the six-layer order and the inheritance property are unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/ledger.py backend/tests/test_bv_signoff.py
git commit -m "feat: ledger signoff layer rejects per indicator, with legacy L3 fallback"
```

---

## Task 5: Emit the (L4, indicator) pairs each Business Validation chart covers

**Files:**
- Modify: `backend/app/agents/data.py:450-480` (`_bv_groups`)
- Modify: `frontend/src/lib/types.ts` (`ValidationGroup`)
- Test: `backend/tests/test_bv_signoff.py` (extend)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: each dict in the `groups` list of the `a-business-validation` body gains
  `"pairs": [{"l4": str, "indicator": str}, ...]` — the indicators that L3 chart covers, in the
  same key space as `BvSignoff`. TypeScript `ValidationGroup.pairs: { l4: string; indicator: string }[]`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_bv_signoff.py` (and register it in `__main__`):

```python
def test_bv_groups_carry_their_indicator_pairs() -> None:
    """The 2.3 UI needs to know which indicators sit under each chart so it can
    offer a per-indicator Accept / Deny."""
    from app.agents.data import _bv_groups
    from app.agents.dataset_cache import model_df

    st = _state()
    groups = _bv_groups(st, model_df(st))
    assert groups, "the reference dataset must yield validation groups"
    assert all("pairs" in g for g in groups), "every group must carry its pairs"
    assert any(g["pairs"] for g in groups), "at least one group must have indicators"
    for g in groups:
        for pr in g["pairs"]:
            assert set(pr) == {"l4", "indicator"}
            assert pr["indicator"].strip(), "a pair with no indicator is not a key"
    print("✓ bv groups carry their indicator pairs")
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_bv_signoff.py
```
Expected: FAIL — `AssertionError: every group must carry its pairs`.

- [ ] **Step 3: Emit the pairs**

In `backend/app/agents/data.py`, inside the `for _, row in combo.iterrows():` loop of
`_bv_groups`, before the `groups.append({...})` call, add:

```python
        # The indicators this chart actually covers, in the ledger's (l4, metric)
        # key space — this is what the per-indicator sign-off is recorded against.
        sub_overlay = overlay[vq._casefold_eq(overlay["l3"], l3)]
        pairs = sorted({
            (str(a or "").strip(), str(b or "").strip())
            for a, b in zip(sub_overlay["l4"], sub_overlay["metric"])
            if str(b or "").strip()
        })
```

and add one key to the appended dict:

```python
            "pairs": [{"l4": a, "indicator": b} for a, b in pairs],
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_bv_signoff.py
```
Expected: PASS.

- [ ] **Step 5: Add the TypeScript field**

In `frontend/src/lib/types.ts`, add to `ValidationGroup` (line ~122):

```ts
  /** The (l4, indicator) pairs this chart covers — the sign-off key space. */
  pairs: { l4: string; indicator: string }[]
```

Because saved projects have bodies without `pairs`, every read site must tolerate its absence.
Task 10 does that with `group.pairs ?? []`.

- [ ] **Step 6: Type-check**

```bash
cd "frontend" && npm run build
```
Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add backend/app/agents/data.py backend/tests/test_bv_signoff.py frontend/src/lib/types.ts
git commit -m "feat: business-validation groups carry their (l4, indicator) pairs"
```

---

## Task 6: Turn the 2.1 mapping gate into a real decision

**Files:**
- Modify: `backend/app/domain/blueprint.py:271-284` (insert `2.1d`, repoint `2.2`)
- Modify: `backend/app/agents/data.py` (`data_processing` — mapping gap finding)
- Modify: `frontend/src/lib/scenario.ts:214-236`
- Test: `backend/tests/test_s2_roundtrip.py`, `backend/tests/test_api_smoke.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: blueprint task `2.1d` with decision `d-2.1`, options `proceed` and
  `continue-data-engine` (the latter is the rework option, pointing back at `2.1`). Task `2.2`
  now depends on `["2.1d"]`. `data_processing` adds one more `TaskFinding` summarising the
  mapping gaps per L1/L2, which `runner.ensure_recommendation` folds into the AI summary.

> **Why a separate task rather than converting 2.1's assignment:** `2.1`'s assignment carries the
> hard readiness guard (`requiresMapping` / `requiresManifest` → `engine.data_intake_ready`), and
> `Engine.resolve_decision` has no way to refuse an answer. Keeping the assignment as the guard
> and adding `2.1d` as the decision gives both behaviours using only existing mechanisms: the
> decision cannot be reached until the mapping is resolved, so "Proceed" is always legitimately
> available, and "Continue in the Data Engine" re-arms `2.1` through the existing rework path.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_s2_roundtrip.py` (register it in the `__main__` block):

```python
def test_mapping_decision_gate_exists() -> None:
    """2.1 resolves the mapping; 2.1d is where the human decides whether to keep
    building data or move on. 2.2 must sit behind that decision, not behind 2.1."""
    from app.domain import blueprint as bp

    task = bp.TASK_MAP["2.1d"]
    dec = task["decision"]
    assert dec["id"] == "d-2.1"
    assert [o["id"] for o in dec["options"]] == ["proceed", "continue-data-engine"]
    assert dec["rework_option_id"] == "continue-data-engine"
    assert dec["rework_task_id"] == "2.1"
    assert task["depends_on"] == ["2.1"]
    assert bp.TASK_MAP["2.2"]["depends_on"] == ["2.1d"]
    print("✓ mapping decision gate exists")
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_s2_roundtrip.py
```
Expected: FAIL with `KeyError: '2.1d'`.

- [ ] **Step 3: Add the task to the blueprint**

In `backend/app/domain/blueprint.py`, insert immediately after the `2.1` task dict (line 279):

```python
    {"id": "2.1d", "name": "Review the data mapping", "agent": "data", "stage": "s2", "klass": "H",
     "summary": "Review how much of the factor tree the Data Engine actually covers, then decide "
                "whether to keep building data or start scoring what you have.",
     "how": "The AI summarises the mapping — how many indicators are mapped, which parts of the "
            "factor tree have no data at all, and what that costs the model. You either go back "
            "to the Data Engine to close the gaps, or proceed to data quality scoring.",
     "basis_note": "The resolved FactorTree↔DataAssets mapping and the factor tree it covers.",
     "work_note": "Awaiting the mapping decision.",
     "depends_on": ["2.1"], "duration": 1, "produces": [],
     "decision": {"id": "d-2.1", "kind": "choice", "title": "Review the data mapping",
                  "question": "The FactorTree↔DataAssets mapping is resolved. Keep building data "
                              "in the Data Engine, or proceed to data quality scoring?",
                  "evidence": [{"artifactId": "a-data-processing", "note": "Mapping matrix & coverage"},
                               {"artifactId": "a-factor-tree", "note": "The factor tree being mapped"}],
                  "options": [
                      {"id": "proceed", "label": "Proceed to data quality",
                       "detail": "Score the indicators that are mapped today",
                       "consequence": "Ignored factors stay out of the model for this run",
                       "recommended": True},
                      {"id": "continue-data-engine", "label": "Continue in the Data Engine",
                       "detail": "Go back and build data for the factors still uncovered",
                       "consequence": "Intake reopens; the mapping gate re-arms and the timeline slips"}],
                  "rework_task_id": "2.1", "rework_option_id": "continue-data-engine"}},
```

Change the `2.2` task's dependency (line 284) from `"depends_on": ["2.1"]` to
`"depends_on": ["2.1d"]`.

- [ ] **Step 4: Run to verify it passes**

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_s2_roundtrip.py
```
Expected: PASS.

```bash
cd "backend" && PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py
```
Expected: PASS — `heal_state` back-fills `2.1d` onto saved projects via `st.tasks.setdefault`
and `st.decisions.setdefault`, so no migration is needed.

- [ ] **Step 5: Add the mapping-gap finding**

In `backend/app/agents/data.py`, inside `data_processing`, after the existing `findings = [...]`
list is built and before `eng.add_findings(...)`, add:

```python
    # Where the tree is uncovered, not just how much of it. "18 pending" tells the
    # reviewer nothing; "nothing under 渠道/终端营销 has data" is a decision.
    gaps: dict[str, int] = {}
    for r in fmap.rows:
        if r.status == "pending":
            gaps[f"{r.l1} › {r.l2}".strip(" ›")] = gaps.get(f"{r.l1} › {r.l2}".strip(" ›"), 0) + 1
    if gaps:
        top = sorted(gaps.items(), key=lambda kv: -kv[1])[:4]
        findings.append(TaskFinding(
            text="Uncovered areas of the factor tree: "
                 + "; ".join(f"{name} ({n} indicator{'s' if n > 1 else ''})" for name, n in top),
            evidence=[EvidenceRef(artifactId="a-data-processing")]))
```

`runner.ensure_recommendation` already grounds the `d-2.1` recommendation on this task's
findings plus the `a-data-processing` and `a-factor-tree` bodies, so no runner change is needed.

- [ ] **Step 6: Mirror the blueprint in `scenario.ts`**

In `frontend/src/lib/scenario.ts`, insert after the `2.1` entry (line 228):

```ts
  {
    id: '2.1d', name: 'Review the data mapping', agent: 'data', stage: 's2', class: 'H',
    summary: 'Review how much of the factor tree the Data Engine actually covers, then decide whether to keep building data or start scoring what you have.',
    how: 'The AI summarises the mapping — how many indicators are mapped, which parts of the factor tree have no data at all, and what that costs the model. You either go back to the Data Engine to close the gaps, or proceed to data quality scoring.',
    basisNote: 'The resolved FactorTree↔DataAssets mapping and the factor tree it covers.',
    workNote: 'Awaiting the mapping decision.',
    dependsOn: ['2.1'], duration: 1, produces: [],
    decision: {
      id: 'd-2.1', kind: 'choice', title: 'Review the data mapping',
      question: 'The FactorTree↔DataAssets mapping is resolved. Keep building data in the Data Engine, or proceed to data quality scoring?',
      evidence: [
        { artifactId: 'a-data-processing', note: 'Mapping matrix & coverage' },
        { artifactId: 'a-factor-tree', note: 'The factor tree being mapped' },
      ],
      options: [
        { id: 'proceed', label: 'Proceed to data quality', detail: 'Score the indicators that are mapped today', consequence: 'Ignored factors stay out of the model for this run', recommended: true },
        { id: 'continue-data-engine', label: 'Continue in the Data Engine', detail: 'Go back and build data for the factors still uncovered', consequence: 'Intake reopens; the mapping gate re-arms and the timeline slips' },
      ],
      reworkTaskId: '2.1', reworkOptionId: 'continue-data-engine',
    },
  },
```

Change the `2.2` entry's `dependsOn: ['2.1']` to `dependsOn: ['2.1d']`.

- [ ] **Step 7: Type-check**

```bash
cd "frontend" && npm run build
```
Expected: build succeeds.

- [ ] **Step 8: Commit**

```bash
git add backend/app/domain/blueprint.py backend/app/agents/data.py \
        backend/tests/test_s2_roundtrip.py frontend/src/lib/scenario.ts
git commit -m "feat: add the 2.1d mapping decision gate with an AI coverage summary"
```

---

## Task 7: The shared FactorTreeCanvas

**Files:**
- Create: `frontend/src/components/project/factor-tree/keys.ts`
- Create: `frontend/src/components/project/factor-tree/types.ts`
- Create: `frontend/src/components/project/factor-tree/useLedgerIndex.ts`
- Create: `frontend/src/components/project/factor-tree/FactorTreeCanvas.tsx`

**Interfaces:**
- Consumes: `IndicatorLedger` / `IndicatorLedgerRow` from `lib/types.ts`;
  `api.indicatorLedger(projectId)` from `api/client.ts`.
- Produces:
  - `indicatorKey(l4: string, indicator: string): string` — `"<l4>|<indicator>"`, both
    trimmed and lower-cased, matching the backend's `_norm_pair`.
  - `FactorCanvasRow` — see the type block below.
  - `useLedgerIndex(): { index: Map<string, IndicatorLedgerRow>; reload: () => void }`.
  - `blockedBefore(row: IndicatorLedgerRow | undefined, layer: string): string | undefined` —
    the label of the earlier layer that rejected this indicator, or `undefined`.
  - `<FactorTreeCanvas rows columns selectedKey onSelect actions header emptyHint />`.

- [ ] **Step 1: Create the key normaliser**

`frontend/src/components/project/factor-tree/keys.ts`:

```ts
/**
 * The indicator key space shared by every S2 layer. Must match the backend's
 * `ledger._norm_pair` exactly — (l4, metric), each trimmed and lower-cased.
 * L4 only: an indicator is identified by its leaf factor and its metric, never
 * by its L1–L3 path.
 */
export function indicatorKey(l4: string, indicator: string): string {
  return `${l4.trim().toLowerCase()}|${indicator.trim().toLowerCase()}`
}
```

- [ ] **Step 2: Create the row type**

`frontend/src/components/project/factor-tree/types.ts`:

```ts
/** Visual weight of a row's module status. */
export type FactorCanvasTone = 'ok' | 'warn' | 'bad' | 'muted'

/**
 * One indicator row on the shared FactorTree canvas. Each S2 module builds these
 * from its own slice — the canvas only groups, renders and selects. It never
 * derives status itself, so a module's overlay can never disagree with its data.
 */
export interface FactorCanvasRow {
  /** Unique within the canvas. Use `indicatorKey(l4, indicator)` unless the
   *  module has its own row id (2.1 maps factor-tree rows, which can repeat a key). */
  key: string
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
  tone: FactorCanvasTone
  /** Short status word shown on the row, e.g. "Mapped", "Denied", "Good". */
  statusLabel: string
  /** Compact extra cells, aligned to the canvas's `columns` prop. */
  cells?: string[]
  /** Set when an EARLIER S2 layer already rejected this indicator — the row
   *  renders greyed and non-interactive. Value is the layer's label. */
  blockedBy?: string
}
```

- [ ] **Step 3: Create the ledger index hook**

`frontend/src/components/project/factor-tree/useLedgerIndex.ts`:

```ts
import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../../../api/client'
import type { IndicatorLedger, IndicatorLedgerRow } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { indicatorKey } from './keys'

/**
 * Every indicator's fate across the six S2 layers, indexed by `indicatorKey`.
 *
 * Fetched rather than derived: the ledger is the backend's own resolution of the
 * layer order, and re-deriving it here is exactly how a surface comes to disagree
 * with what the model was actually fitted on. Call `reload()` after a mutation
 * that changes a verdict.
 */
export function useLedgerIndex(): {
  index: Map<string, IndicatorLedgerRow>
  reload: () => void
} {
  const projectId = useSimStore((s) => s.activeProjectId)
  const [ledger, setLedger] = useState<IndicatorLedger | null>(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    api
      .indicatorLedger(projectId)
      .then((l) => { if (!cancelled) setLedger(l) })
      .catch(() => { if (!cancelled) setLedger(null) })
    return () => { cancelled = true }
  }, [projectId, nonce])

  const index = useMemo(() => {
    const m = new Map<string, IndicatorLedgerRow>()
    for (const r of ledger?.rows ?? []) m.set(indicatorKey(r.l4, r.indicator), r)
    return m
  }, [ledger])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { index, reload }
}

/** The six S2 layers in the order they rule. Mirrors `ledger.LAYERS`. */
const LAYER_ORDER = ['mapping', 'quality', 'signoff', 'statistical', 'selection', 'range']

/**
 * The label of the layer that rejected this indicator BEFORE `layer` — or
 * undefined if no earlier layer did. A module uses this to grey out rows it must
 * not re-litigate: a rejection at any layer is inherited by every later one.
 */
export function blockedBefore(
  row: IndicatorLedgerRow | undefined,
  layer: string,
): string | undefined {
  if (!row) return undefined
  const cutoff = LAYER_ORDER.indexOf(layer)
  if (cutoff < 0) return undefined
  for (const v of row.verdicts) {
    const at = LAYER_ORDER.indexOf(v.layer)
    if (at >= 0 && at < cutoff && v.status === 'rejected') return v.label || v.layer
  }
  return undefined
}
```

> Check `LedgerVerdict` in `lib/types.ts` for the exact field names before writing
> `blockedBefore`. If it has no `label`, use `v.layer` alone and drop the `||`.

- [ ] **Step 4: Create the canvas component**

`frontend/src/components/project/factor-tree/FactorTreeCanvas.tsx`:

```tsx
import { Fragment, type ReactNode, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Lock } from 'lucide-react'

import { cn } from '../../../lib/utils'
import type { FactorCanvasRow, FactorCanvasTone } from './types'

const TONE: Record<FactorCanvasTone, string> = {
  ok: 'bg-emerald-500/15 text-emerald-600',
  warn: 'bg-amber-500/15 text-amber-600',
  bad: 'bg-rose-500/15 text-rose-600',
  muted: 'bg-muted text-muted-foreground',
}

interface Group {
  key: string
  l1: string
  l2: string
  l3: string
  rows: FactorCanvasRow[]
}

function groupRows(rows: FactorCanvasRow[]): Group[] {
  const out: Group[] = []
  const byKey = new Map<string, Group>()
  for (const r of rows) {
    const key = `${r.l1} ${r.l2} ${r.l3}`
    let g = byKey.get(key)
    if (!g) {
      g = { key, l1: r.l1, l2: r.l2, l3: r.l3, rows: [] }
      byKey.set(key, g)
      out.push(g)
    }
    g.rows.push(r)
  }
  return out
}

/**
 * The FactorTree, rendered once and reused by every S2 module.
 *
 * Every S2 step is doing the same thing to the same object — integrating and
 * filtering the factor tree — so they share this canvas and differ only in the
 * status each row carries. The component owns no data and derives no verdicts:
 * modules pass rows they built from their own slice, which is what keeps an
 * overlay from disagreeing with the thing it is displaying.
 */
export function FactorTreeCanvas({
  rows,
  columns = [],
  selectedKey,
  onSelect,
  actions,
  header,
  emptyHint = 'No factors to show yet.',
}: {
  rows: FactorCanvasRow[]
  columns?: string[]
  selectedKey?: string
  onSelect?: (key: string) => void
  actions?: (row: FactorCanvasRow) => ReactNode
  header?: ReactNode
  emptyHint?: string
}) {
  const groups = useMemo(() => groupRows(rows), [rows])
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  function toggle(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  if (!rows.length) {
    return (
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {header}
        <p className="mt-6 text-center text-xs text-muted-foreground">{emptyHint}</p>
      </div>
    )
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto p-4">
      {header}
      <table className="mt-3 w-full border-collapse text-[11.5px]">
        <thead>
          <tr className="border-b border-border text-left text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            <th className="px-2 py-1.5 font-medium">Factor · Indicator</th>
            {columns.map((c) => (
              <th key={c} className="px-2 py-1.5 text-right font-medium">{c}</th>
            ))}
            <th className="px-2 py-1.5 font-medium">Status</th>
            {actions && <th className="px-2 py-1.5 font-medium">Action</th>}
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => {
            const isCollapsed = collapsed.has(g.key)
            const span = 2 + columns.length + (actions ? 1 : 0)
            return (
              <Fragment key={g.key}>
                <tr className="bg-muted/30">
                  <td colSpan={span} className="px-2 py-1">
                    <button
                      type="button"
                      onClick={() => toggle(g.key)}
                      className="flex items-center gap-1 text-[10.5px] font-medium text-muted-foreground hover:text-foreground"
                    >
                      {isCollapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      <span>{g.l1 || '—'}</span>
                      {g.l2 && <span className="text-muted-foreground/60">› {g.l2}</span>}
                      {g.l3 && <span className="text-muted-foreground/60">› {g.l3}</span>}
                      <span className="ml-1 text-muted-foreground/50">({g.rows.length})</span>
                    </button>
                  </td>
                </tr>
                {!isCollapsed && g.rows.map((r) => {
                  const blocked = Boolean(r.blockedBy)
                  return (
                    <tr
                      key={r.key}
                      onClick={() => !blocked && onSelect?.(r.key)}
                      className={cn(
                        'border-b border-border/40',
                        blocked ? 'opacity-45' : 'cursor-pointer hover:bg-accent/50',
                        selectedKey === r.key && 'bg-accent',
                      )}
                    >
                      <td className="px-2 py-1">
                        <span className="text-muted-foreground">{r.l4 || r.l3 || '—'}</span>
                        <span className="text-muted-foreground/50"> · </span>
                        <span className="font-medium">{r.indicator}</span>
                      </td>
                      {columns.map((c, i) => (
                        <td key={c} className="px-2 py-1 text-right tabular-nums text-muted-foreground">
                          {r.cells?.[i] ?? ''}
                        </td>
                      ))}
                      <td className="px-2 py-1">
                        {blocked ? (
                          <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10.5px] bg-muted text-muted-foreground">
                            <Lock className="h-2.5 w-2.5" />
                            Denied @ {r.blockedBy}
                          </span>
                        ) : (
                          <span className={cn('rounded px-1.5 py-0.5 text-[10.5px]', TONE[r.tone])}>
                            {r.statusLabel}
                          </span>
                        )}
                      </td>
                      {actions && (
                        <td className="px-2 py-1" onClick={(e) => e.stopPropagation()}>
                          {blocked ? null : actions(r)}
                        </td>
                      )}
                    </tr>
                  )
                })}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
```

> Verify the import path of `cn` — other components in `components/project/` import it from
> `'../../lib/utils'`; from `factor-tree/` it is one level deeper. Match whatever
> `StatScoreEditor.tsx` uses, adjusted for depth.

- [ ] **Step 5: Type-check**

```bash
cd "frontend" && npm run build
```
Expected: build succeeds. The component is not mounted yet, so nothing renders — that is
correct at this point.

- [ ] **Step 6: Lint**

```bash
cd "frontend" && npm run lint
```
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/project/factor-tree
git commit -m "feat: shared FactorTreeCanvas with ledger-aware inheritance badges"
```

---

## Task 8: Data Processing (2.1) canvas

**Files:**
- Create: `frontend/src/components/project/canvas/DataProcessingCanvas.tsx`
- Modify: `frontend/src/components/project/canvas/ArtifactCanvas.tsx:346-369`

**Interfaces:**
- Consumes: `FactorTreeCanvas`, `FactorCanvasRow` (Task 7); `api.getFactorMap`,
  `api.bindFactorMap`, `api.setFactorMapIgnore`; `FactorMap` / `FactorMapRow` from `lib/types.ts`.
- Produces: `<DataProcessingCanvas inst={inst} />`, routed by artifact id in `ArtifactCanvas`.

- [ ] **Step 1: Create the canvas**

`frontend/src/components/project/canvas/DataProcessingCanvas.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'

import { api } from '../../../api/client'
import type { ArtifactInstance, FactorMap, FactorMapRow } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { Button } from '../../ui/button'
import { FactorTreeCanvas } from '../factor-tree/FactorTreeCanvas'
import type { FactorCanvasRow, FactorCanvasTone } from '../factor-tree/types'

const TONE: Record<string, FactorCanvasTone> = {
  mapped: 'ok',
  ignored: 'muted',
  pending: 'warn',
}
const STATUS_LABEL: Record<string, string> = {
  mapped: 'Mapped',
  ignored: 'Ignored',
  pending: 'Pending',
}

/**
 * 2.1 Data Processing — the factor tree with its Data-Engine mapping on every row.
 *
 * The same bind / remap / ignore actions the Data Engine's indicator catalogue
 * offers, on the surface where the factor tree is the subject. The factor map is
 * component-local state (as in the Data Engine panel) because it is derived from
 * published indicators, not from a ProjectState slice the poll replaces.
 */
export function DataProcessingCanvas({ inst }: { inst: ArtifactInstance }) {
  const projectId = useSimStore((s) => s.activeProjectId)
  const refresh = useSimStore((s) => s.refresh)
  const [map, setMap] = useState<FactorMap | null>(null)
  const [selected, setSelected] = useState<string>('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    if (!projectId) return
    api.getFactorMap(projectId).then(setMap).catch(() => setMap(null))
  }, [projectId])

  useEffect(load, [load])

  const rows: FactorCanvasRow[] = useMemo(
    () =>
      (map?.rows ?? []).map((r) => ({
        key: r.rowId,
        l1: r.l1, l2: r.l2, l3: r.l3, l4: r.l4,
        indicator: r.indicator,
        tone: TONE[r.status] ?? 'muted',
        statusLabel: STATUS_LABEL[r.status] ?? r.status,
        cells: [r.assetName || (r.status === 'ignored' ? '—' : ''), r.metric || ''],
      })),
    [map],
  )

  const selectedRow: FactorMapRow | undefined = useMemo(
    () => (map?.rows ?? []).find((r) => r.rowId === selected),
    [map, selected],
  )

  async function mutate(fn: () => Promise<FactorMap>) {
    setBusy(true)
    try {
      setMap(await fn())
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  function bind(rowId: string, indicatorId: string) {
    if (!projectId) return
    void mutate(() => api.bindFactorMap(projectId, rowId, indicatorId))
  }

  function ignore(rowId: string, ignored: boolean) {
    if (!projectId) return
    void mutate(() => api.setFactorMapIgnore(projectId, rowId, ignored, ''))
  }

  async function ignoreAllPending() {
    if (!projectId || !map) return
    setBusy(true)
    try {
      let latest = map
      for (const r of map.rows.filter((x) => x.status === 'pending')) {
        latest = await api.setFactorMapIgnore(projectId, r.rowId, true, 'No data source')
      }
      setMap(latest)
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  const header = (
    <header className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h3 className="text-sm font-medium">{inst.name}</h3>
        <p className="text-[11px] text-muted-foreground">
          {map
            ? `${map.mapped} mapped · ${map.ignored} ignored · ${map.pending} pending of ${map.total}`
            : 'Loading the mapping…'}
        </p>
      </div>
      <div className="flex items-center gap-2">
        {map && map.pending > 0 && (
          <Button size="sm" variant="outline" disabled={busy} onClick={ignoreAllPending}>
            Ignore all pending
          </Button>
        )}
        <Button size="sm" variant="outline" asChild>
          <Link to={`/p/${projectId}/data`}>
            Open Data Engine <ExternalLink className="ml-1 h-3 w-3" />
          </Link>
        </Button>
      </div>
    </header>
  )

  return (
    <>
      <FactorTreeCanvas
        rows={rows}
        columns={['Asset', 'Metric']}
        selectedKey={selected}
        onSelect={setSelected}
        header={header}
        emptyHint="No active factor-tree rows to map. Confirm the factor tree in S1 first."
        actions={(r) => {
          const row = (map?.rows ?? []).find((x) => x.rowId === r.key)
          if (!row) return null
          if (row.status === 'mapped') {
            return (
              <button type="button" disabled={busy} onClick={() => bind(row.rowId, '')}
                className="text-[10.5px] text-muted-foreground hover:text-foreground">
                Release
              </button>
            )
          }
          if (row.status === 'ignored') {
            return (
              <button type="button" disabled={busy} onClick={() => ignore(row.rowId, false)}
                className="text-[10.5px] text-muted-foreground hover:text-foreground">
                Restore
              </button>
            )
          }
          return (
            <div className="flex items-center gap-2">
              {row.suggestions[0] && (
                <button type="button" disabled={busy}
                  onClick={() => bind(row.rowId, row.suggestions[0].indicatorId)}
                  className="text-[10.5px] text-emerald-600 hover:underline">
                  Accept “{row.suggestions[0].metric}”
                </button>
              )}
              <button type="button" disabled={busy} onClick={() => ignore(row.rowId, true)}
                className="text-[10.5px] text-muted-foreground hover:text-foreground">
                Ignore
              </button>
            </div>
          )
        }}
      />
      {selectedRow && selectedRow.suggestions.length > 1 && (
        <aside className="border-t border-border p-3">
          <p className="mb-2 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Other candidates for {selectedRow.l4 || selectedRow.l3} · {selectedRow.indicator}
          </p>
          <ul className="space-y-1">
            {selectedRow.suggestions.slice(1, 6).map((s) => (
              <li key={s.indicatorId} className="flex items-center justify-between gap-2 text-[11px]">
                <span>
                  <span className="font-medium">{s.metric}</span>
                  <span className="text-muted-foreground"> · {s.assetName} · {s.unit}</span>
                  <span className="text-muted-foreground/60"> · {s.coverageStart}–{s.coverageEnd}</span>
                </span>
                <button type="button" disabled={busy}
                  onClick={() => bind(selectedRow.rowId, s.indicatorId)}
                  className="text-[10.5px] text-emerald-600 hover:underline">
                  Use this
                </button>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </>
  )
}
```

> Two things to confirm against the codebase before finishing this step: the Data Engine route
> path (grep `path=` in `frontend/src/main.tsx` for the data-engine route — the link above
> assumes `/p/:projectId/data`), and whether `Button` supports `asChild` (if not, wrap the
> `Link` in a plain styled anchor instead).

- [ ] **Step 2: Route it by artifact id**

In `frontend/src/components/project/canvas/ArtifactCanvas.tsx`, add the import and an
id-keyed check **before** the format switch:

```tsx
import { DataProcessingCanvas } from './DataProcessingCanvas'
```

```tsx
/**
 * Artifacts whose canvas is a purpose-built surface rather than a format renderer.
 * Keyed by artifact id and applied in BOTH document and edit mode: for the S2
 * modules the tree IS the document, not an editing affordance layered over one.
 */
const ID_CANVASES: Record<string, (inst: ArtifactInstance) => ReactElement> = {
  'a-data-processing': (inst) => <DataProcessingCanvas inst={inst} />,
}

export function ArtifactCanvas({ inst, editing }: { inst: ArtifactInstance; editing: boolean }) {
  const byId = ID_CANVASES[inst.id]
  if (byId) return byId(inst)
  switch (inst.format) {
    /* keep every existing case exactly as it is */
  }
}
```

Do not touch the `switch` body — the format cases stay verbatim. The only change to this
function is the two new lines above the `switch`.

Add `ReactElement` to the React type imports at the top of the file.

- [ ] **Step 3: Build and lint**

```bash
cd "frontend" && npm run build && npm run lint
```
Expected: both succeed.

- [ ] **Step 4: Verify in the running app**

Start the backend and frontend, open a project, and open the Data Processing artifact.

```bash
cd "backend" && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
```bash
cd "frontend" && npm run dev
```

Expected: the artifact canvas shows the factor tree grouped by L1 › L2 › L3, each indicator row
carrying Mapped / Ignored / Pending, an "Open Data Engine" button, and — when there are pending
rows — an "Ignore all pending" button. Accepting a suggestion flips the row to Mapped and the
header counts update.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/project/canvas/DataProcessingCanvas.tsx \
        frontend/src/components/project/canvas/ArtifactCanvas.tsx
git commit -m "feat: Data Processing canvas — factor tree with live Data-Engine mapping"
```

---

## Task 9: Data Quality (2.2) canvas

**Files:**
- Create: `frontend/src/components/project/canvas/QualityCanvas.tsx`
- Modify: `frontend/src/components/project/canvas/ArtifactCanvas.tsx` (`ID_CANVASES`)
- Modify: `frontend/src/components/project/ArtifactDetail.tsx:445-450`

**Interfaces:**
- Consumes: `FactorTreeCanvas`, `indicatorKey`, `useLedgerIndex`, `blockedBefore` (Task 7);
  the `qualityScorecard` store slice and `updateQualityScorecard` action.
- Produces: `<QualityCanvas />` (no props — store-bound, like the editor it replaces on the
  canvas), registered in `ID_CANVASES` under `a-quality-scorecard`.

- [ ] **Step 1: Create the canvas**

`frontend/src/components/project/canvas/QualityCanvas.tsx`:

```tsx
import { useMemo, useState } from 'react'

import type { QualityDisposition, QualityRow } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/utils'
import { FactorTreeCanvas } from '../factor-tree/FactorTreeCanvas'
import { indicatorKey } from '../factor-tree/keys'
import { blockedBefore, useLedgerIndex } from '../factor-tree/useLedgerIndex'
import type { FactorCanvasRow, FactorCanvasTone } from '../factor-tree/types'

const DISPOSITIONS: { id: QualityDisposition; label: string; on: string }[] = [
  { id: 'accept', label: 'Accept', on: 'bg-emerald-500/15 text-emerald-600' },
  { id: 'flag', label: 'Flag', on: 'bg-amber-500/15 text-amber-600' },
  { id: 'drop', label: 'Drop', on: 'bg-rose-500/15 text-rose-600' },
]
const DIMENSIONS = [
  { key: 'consistency', label: 'Consistency' },
  { key: 'accuracy', label: 'Accuracy' },
  { key: 'completeness', label: 'Completeness' },
  { key: 'granularity', label: 'Granularity' },
] as const
const TONE: Record<string, FactorCanvasTone> = { pass: 'ok', borderline: 'warn', unusable: 'bad' }

/**
 * 2.2 Data Quality Score on the shared factor tree.
 *
 * The four dimension scores ride on the tree row; the ten subchecks and the AI's
 * per-dimension notes open below for the selected indicator. Indicators an earlier
 * layer already rejected are greyed by the canvas — re-scoring a settled decision
 * would put it back in front of the human as if it were open.
 */
export function QualityCanvas() {
  const card = useSimStore((s) => s.qualityScorecard)
  const update = useSimStore((s) => s.updateQualityScorecard)
  const { index } = useLedgerIndex()
  const [selected, setSelected] = useState('')

  const cardRows = useMemo(() => card?.rows ?? [], [card])

  const rows: FactorCanvasRow[] = useMemo(
    () =>
      cardRows.map((r) => ({
        key: r.id,
        l1: r.l1, l2: r.l2, l3: r.l3, l4: r.l4,
        indicator: r.indicator,
        tone: TONE[r.autoVerdict] ?? 'muted',
        statusLabel: r.autoVerdict || '—',
        cells: [
          r.consistency.toString(), r.accuracy.toString(),
          r.completeness.toString(), r.granularity.toString(),
          r.total.toFixed(2),
        ],
        blockedBy: blockedBefore(index.get(indicatorKey(r.l4, r.indicator)), 'quality'),
      })),
    [cardRows, index],
  )

  const current: QualityRow | undefined = useMemo(
    () => cardRows.find((r) => r.id === selected),
    [cardRows, selected],
  )

  if (!card) return null

  function setDisposition(id: string, disposition: QualityDisposition) {
    void update({ rows: cardRows.map((r) => (r.id === id ? { ...r, disposition } : r)) })
  }

  const header = (
    <header>
      <h3 className="text-sm font-medium">Data Quality Score</h3>
      <p className="text-[11px] text-muted-foreground">
        {cardRows.length} indicators · {cardRows.filter((r) => r.disposition === 'drop').length} dropped
      </p>
    </header>
  )

  return (
    <>
      <FactorTreeCanvas
        rows={rows}
        columns={['Cons.', 'Acc.', 'Comp.', 'Gran.', 'Total']}
        selectedKey={selected}
        onSelect={setSelected}
        header={header}
        emptyHint="Run 2.2 to score the indicators."
        actions={(r) => {
          const row = cardRows.find((x) => x.id === r.key)
          if (!row) return null
          return (
            <div className="inline-flex rounded-md border border-border p-0.5">
              {DISPOSITIONS.map((d) => (
                <button key={d.id} type="button" onClick={() => setDisposition(row.id, d.id)}
                  className={cn('rounded px-1.5 py-0.5 text-[11px]',
                    row.disposition === d.id ? d.on : 'text-muted-foreground hover:bg-accent')}>
                  {d.label}
                </button>
              ))}
            </div>
          )
        }}
      />
      {current && (
        <aside className="max-h-64 overflow-auto border-t border-border p-3">
          <p className="mb-2 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {current.l4 || current.l3} · {current.indicator}
          </p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {DIMENSIONS.map((dim) => (
              <section key={dim.key}>
                <p className="text-[11px] font-medium">{dim.label}</p>
                <p className="text-[11px] text-muted-foreground">
                  {(current[`${dim.key}Note` as keyof QualityRow] as string) || '—'}
                </p>
                <ul className="mt-1 space-y-0.5">
                  {(current.subScores ?? [])
                    .filter((s) => s.dimension === dim.key)
                    .map((s) => (
                      <li key={s.key} className="text-[10.5px] text-muted-foreground">
                        <span className="tabular-nums">{s.score}</span> · {s.label}
                        {!s.computed && <span className="ml-1 text-muted-foreground/60">(advisory)</span>}
                      </li>
                    ))}
                </ul>
              </section>
            ))}
          </div>
        </aside>
      )}
    </>
  )
}
```

- [ ] **Step 2: Register it and drop the redundant editor entry**

In `ArtifactCanvas.tsx`, add to `ID_CANVASES`:

```tsx
  'a-quality-scorecard': () => <QualityCanvas />,
```
with `import { QualityCanvas } from './QualityCanvas'`.

In `frontend/src/components/project/ArtifactDetail.tsx`, remove the
`'a-quality-scorecard': () => <QualityScorecardEditor />,` line from `STRUCTURED_EDITORS` (the
canvas now serves both modes) and remove the now-unused `QualityScorecardEditor` import **only
if** nothing else in the file uses it.

**Leave `TaskStepPanel`'s `quality-review` panel on the existing `QualityScorecardEditor`.**
The spec suggested the inline panel wrap the same canvas; it should not. The panel is a narrow
column inside a build step, where a flat disposition list reads better than a grouped tree, and
swapping it would put two independently-scrolling trees on screen at once when the artifact is
open beside its Process pane. The canvas is the wide surface; the panel stays the list.

Also confirm the artifact's export path is untouched: `a-data-processing`, `a-quality-scorecard`
and `a-stat-tests` keep `format: "sheet"` in the blueprint and keep producing their sheet bodies.
`lib/export.ts` reads that body, not the canvas, so nothing about export changes — and because
the format is unchanged, `heal_state` will not null out saved bodies.

- [ ] **Step 3: Build and lint**

```bash
cd "frontend" && npm run build && npm run lint
```
Expected: both succeed.

- [ ] **Step 4: Verify in the running app**

Open the Data Quality Score artifact. Expected: the tree with four dimension scores and a total
per row, a working Accept / Flag / Drop control, subchecks opening below on row click, and rows
rejected at 2.1 mapping greyed with a "Denied @ …" badge. The `quality-review` panel inside the
Process step still shows the old editor and still works.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/project/canvas/QualityCanvas.tsx \
        frontend/src/components/project/canvas/ArtifactCanvas.tsx \
        frontend/src/components/project/ArtifactDetail.tsx
git commit -m "feat: Data Quality canvas on the shared factor tree"
```

---

## Task 10: Business Validation (2.3) — per-indicator sign-off

**Files:**
- Modify: `frontend/src/components/project/validation/BusinessValidationView.tsx:250-400`, `:579-633`
- Modify: `frontend/src/store/useSimStore.ts` (slice, action, `mapState`)

**Interfaces:**
- Consumes: `BvSignoffBook` / `BvSignoff` and `api.updateBvSignoff` (Task 3);
  `ValidationGroup.pairs` (Task 5); `indicatorKey` (Task 7).
- Produces: store slice `bvSignoff: BvSignoffBook | null` and action
  `updateBvSignoff(book: BvSignoffBook) => Promise<void>`; `FactorCard` renders per-pair
  Accept / Deny and the card header shows the aggregate.

- [ ] **Step 1: Add the store slice and action**

In `frontend/src/store/useSimStore.ts`:

Declare the slice next to `anomalyReview` (line ~208):

```ts
  /** S2 (2.3) per-indicator client sign-off. */
  bvSignoff: BvSignoffBook | null
```

Declare the action next to `updateAnomalyReview` (line ~270):

```ts
  updateBvSignoff: (book: BvSignoffBook) => Promise<void>
```

Add to `mapState` next to the other snake_case reads (line ~352):

```ts
  if (s.bv_signoff !== undefined) patch.bvSignoff = s.bv_signoff ?? null
```

Add `bvSignoff: null` to both initial-value blocks (lines ~407 and ~487).

Implement the action next to `updateAnomalyReview` (line ~893), following the same
optimistic-then-refresh template:

```ts
    updateBvSignoff: async (book) => {
      const pid = get().activeProjectId
      if (!pid) return
      // Optimistic; refresh re-syncs the ledger-derived surfaces downstream.
      set({ bvSignoff: book })
      try {
        await api.updateBvSignoff(pid, book)
        await get().refresh()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },
```

Add `BvSignoffBook` to the type imports and to the `BackendState` interface
(`bv_signoff?: BvSignoffBook | null`).

- [ ] **Step 2: Add a sign-off helper module**

Create `frontend/src/components/project/validation/signoff.ts`:

```ts
import type { BvSignoff, BvSignoffBook, ValidationGroup } from '../../../lib/types'
import { indicatorKey } from '../factor-tree/keys'

/** Index a sign-off book by the shared (l4, indicator) key. */
export function signoffIndex(book: BvSignoffBook | null): Map<string, BvSignoff> {
  const m = new Map<string, BvSignoff>()
  for (const r of book?.rows ?? []) m.set(indicatorKey(r.l4, r.indicator), r)
  return m
}

/**
 * Replace the sign-off for one indicator. Clicking the active value clears the
 * row entirely — blank means "not individually reviewed", which the d-2.3 gate
 * covers, and is not the same as accepted.
 */
export function withSignoff(
  book: BvSignoffBook | null,
  row: Omit<BvSignoff, 'status' | 'note'>,
  status: BvSignoff['status'] | null,
): BvSignoffBook {
  const key = indicatorKey(row.l4, row.indicator)
  const rows = (book?.rows ?? []).filter((r) => indicatorKey(r.l4, r.indicator) !== key)
  if (status) rows.push({ ...row, status, note: '' })
  return { rows }
}

/** How a whole chart stands: every child accepted, every child denied, or mixed. */
export function groupVerdict(
  group: ValidationGroup,
  index: Map<string, BvSignoff>,
): 'accepted' | 'denied' | 'mixed' | 'pending' {
  const pairs = group.pairs ?? []
  if (!pairs.length) return 'pending'
  let accepted = 0
  let denied = 0
  for (const p of pairs) {
    const s = index.get(indicatorKey(p.l4, p.indicator))?.status
    if (s === 'accepted') accepted += 1
    else if (s === 'denied') denied += 1
  }
  if (accepted === pairs.length) return 'accepted'
  if (denied === pairs.length) return 'denied'
  if (accepted || denied) return 'mixed'
  return 'pending'
}
```

- [ ] **Step 3: Replace the L3 sign-off with per-indicator controls**

In `BusinessValidationView.tsx`:

Change `FactorCardProps` (line 250) to:

```tsx
interface FactorCardProps {
  group: ValidationGroup
  projectId: string
  signoff: Map<string, BvSignoff>
  onSignoff: (pair: { l4: string; indicator: string }, status: 'accepted' | 'denied' | null) => void
  onSignoffAll: (status: 'accepted' | 'denied') => void
  timeWindowId: string
}
```

The `editing` prop is removed: sign-off is project state now, so it is writable in Document mode.

Replace the sign-off block in the card header (lines 364-381) with an aggregate badge plus
bulk actions:

```tsx
<div className="flex items-center gap-2">
  <span className="text-[10px] text-muted-foreground">Sign-off</span>
  <span className={cn('rounded px-1.5 py-0.5 text-[10.5px]',
    verdict === 'accepted' ? 'bg-emerald-500/15 text-emerald-600'
      : verdict === 'denied' ? 'bg-rose-500/15 text-rose-600'
      : verdict === 'mixed' ? 'bg-amber-500/15 text-amber-600'
      : 'bg-muted text-muted-foreground')}>
    {verdict}
  </span>
  <button type="button" onClick={() => onSignoffAll('accepted')}
    className="rounded border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted">
    Accept all
  </button>
  <button type="button" onClick={() => onSignoffAll('denied')}
    className="rounded border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted">
    Deny all
  </button>
</div>
```

with, inside `FactorCard`:

```tsx
const verdict = groupVerdict(group, signoff)
```

Then add a per-indicator list directly beneath the chart (after the `ValidationChart` render,
before `ComparisonBlock`):

```tsx
<section className="mt-3 border-t border-border/60 pt-2">
  <p className="mb-1 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
    Indicators in this chart
  </p>
  <ul className="grid gap-1 md:grid-cols-2">
    {(group.pairs ?? []).map((p) => {
      const status = signoff.get(indicatorKey(p.l4, p.indicator))?.status
      return (
        <li key={`${p.l4}|${p.indicator}`} className="flex items-center justify-between gap-2 text-[11px]">
          <span className="truncate">
            <span className="text-muted-foreground">{p.l4 || group.l3}</span>
            <span className="text-muted-foreground/50"> · </span>
            <span>{p.indicator}</span>
          </span>
          <span className="inline-flex rounded-md border border-border p-0.5">
            {(['accepted', 'denied'] as const).map((v) => (
              <button key={v} type="button"
                onClick={() => onSignoff(p, status === v ? null : v)}
                className={cn('rounded px-1.5 py-0.5 text-[10.5px]',
                  status === v
                    ? v === 'accepted' ? 'bg-emerald-500/15 text-emerald-600' : 'bg-rose-500/15 text-rose-600'
                    : 'text-muted-foreground hover:bg-accent')}>
                {v === 'accepted' ? 'Accept' : 'Deny'}
              </button>
            ))}
          </span>
        </li>
      )
    })}
    {!(group.pairs ?? []).length && (
      <li className="text-[11px] text-muted-foreground">
        Re-run 2.3 to record sign-off per indicator.
      </li>
    )}
  </ul>
</section>
```

- [ ] **Step 4: Wire the top-level component**

Rewrite the top of `BusinessValidationView` (lines 579-633). Keep the existing "run task 2.3"
empty-state block and the entire header/`TimeWindowBar` JSX exactly as they are — the only
changes are the store selectors, the two sign-off handlers, the `denied` count replacing
`signedOff`, and the `<FactorCard>` props:

```tsx
export function BusinessValidationView({ inst }: { inst: ArtifactInstance; editing?: boolean }) {
  const projectId = useSimStore((s) => s.activeProjectId)
  const book = useSimStore((s) => s.bvSignoff)
  const updateBvSignoff = useSimStore((s) => s.updateBvSignoff)
  const [windowId, setWindowId] = useState('')
  const data = asValidation(inst.body)
  const index = useMemo(() => signoffIndex(book), [book])

  // …empty state unchanged…

  const signPair = (
    group: ValidationGroup,
    pair: { l4: string; indicator: string },
    status: 'accepted' | 'denied' | null,
  ) => {
    void updateBvSignoff(withSignoff(book, {
      l1: group.l1, l2: group.l2, l3: group.l3, l4: pair.l4, indicator: pair.indicator,
    }, status))
  }

  const signGroup = (group: ValidationGroup, status: 'accepted' | 'denied') => {
    let next = book
    for (const p of group.pairs ?? []) {
      next = withSignoff(next, {
        l1: group.l1, l2: group.l2, l3: group.l3, l4: p.l4, indicator: p.indicator,
      }, status)
    }
    void updateBvSignoff(next ?? { rows: [] })
  }

  const denied = (book?.rows ?? []).filter((r) => r.status === 'denied').length
```

Update the header text that used `signedOff` to report `denied` instead (e.g.
`{denied} indicator{denied === 1 ? '' : 's'} denied`), and pass the new props at the
`<FactorCard …>` call site (line ~629):

```tsx
<FactorCard
  key={g.l3}
  group={g}
  projectId={projectId}
  signoff={index}
  onSignoff={(pair, status) => signPair(g, pair, status)}
  onSignoffAll={(status) => signGroup(g, status)}
  timeWindowId={windowId}
/>
```

Add the imports: `signoffIndex`, `withSignoff`, `groupVerdict` from `./signoff`;
`indicatorKey` from `../factor-tree/keys`; `BvSignoff` and `ValidationGroup` types. Remove the
now-unused `editArtifact` selector.

- [ ] **Step 5: Build and lint**

```bash
cd "frontend" && npm run build && npm run lint
```
Expected: both succeed. If `ArtifactCanvas` still passes `editing` to `BusinessValidationView`,
the optional `editing?: boolean` in the signature absorbs it.

- [ ] **Step 6: Verify end to end**

With the backend and frontend running, open Business Validation, deny one indicator under a
chart, then reload the page.

Expected: the denial survives the reload (it is project state now, not artifact body), the card
header shows `mixed`, and the Statistical Score canvas greys that indicator with
"Denied @ Business Validation" while its siblings stay live. Confirm the same via the API:

```bash
curl -s localhost:8000/api/projects/danone-mizone/indicator-ledger | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['rejected'], [r['rejectedAt'] for r in d['rows'] if not r['adopted']][:5])"
```
Expected: the denied indicator's `rejectedAt` is `signoff`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/project/validation frontend/src/store/useSimStore.ts
git commit -m "feat: business validation signs off per indicator, persisted to project state"
```

---

## Task 11: Statistical Score (2.4) canvas

**Files:**
- Create: `frontend/src/components/project/canvas/StatCanvas.tsx`
- Modify: `frontend/src/components/project/canvas/ArtifactCanvas.tsx` (`ID_CANVASES`)
- Modify: `frontend/src/components/project/ArtifactDetail.tsx:445-450`
- Modify: `frontend/src/components/project/StatScoreEditor.tsx:26-42`

**Interfaces:**
- Consumes: `FactorTreeCanvas`, `indicatorKey`, `useLedgerIndex`, `blockedBefore` (Task 7);
  the `statScorecard` slice and `updateStatScorecard`; the three-band rule from Task 1.
- Produces: `<StatCanvas />` registered under `a-stat-tests`.

- [ ] **Step 1: Update the rule legend in the existing editor**

In `frontend/src/components/project/StatScoreEditor.tsx`, replace `RULES` (lines 26-42):

```ts
const RULES: { test: string; metric: string; bands: string[] }[] = [
  { test: 'Volatility · CV', metric: 'Scale series to [0,1], then variance / mean',
    bands: ['0 · CV ≤ 0.05', '0.5 · 0.05–0.1', '1 · CV ≥ 0.1'] },
  { test: 'Correlation · Pearson r', metric: '|r| between the indicator and the KPI (univariate)',
    bands: ['0 · |r| < 0.1', '0.5 · 0.1–0.3', '1 · |r| ≥ 0.3'] },
  { test: 'Collinearity · VIF', metric: 'Variance inflation vs the other indicators',
    bands: ['0 · VIF ≥ 5', '0.5 · 1–5', '1 · VIF = 1'] },
]
```

Add a line under the legend explaining the total (place it wherever the legend body renders):

```tsx
<p className="mt-1 text-[10.5px] text-muted-foreground">
  Total = CV × Pearson × VIF. A single failing test zeroes the total and drops the indicator.
</p>
```

- [ ] **Step 2: Create the canvas**

`frontend/src/components/project/canvas/StatCanvas.tsx`:

```tsx
import { useMemo, useState } from 'react'

import type { StatDisposition, StatScoreRow } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/utils'
import { FactorTreeCanvas } from '../factor-tree/FactorTreeCanvas'
import { indicatorKey } from '../factor-tree/keys'
import { blockedBefore, useLedgerIndex } from '../factor-tree/useLedgerIndex'
import type { FactorCanvasRow, FactorCanvasTone } from '../factor-tree/types'

const DISPOSITIONS: { id: StatDisposition; label: string; on: string }[] = [
  { id: 'include', label: 'Include', on: 'bg-emerald-500/15 text-emerald-600' },
  { id: 'review', label: 'Review', on: 'bg-amber-500/15 text-amber-600' },
  { id: 'drop', label: 'Drop', on: 'bg-rose-500/15 text-rose-600' },
]
const TONE: Record<string, FactorCanvasTone> = {
  Good: 'ok',
  Acceptable: 'warn',
  unconsiderable: 'bad',
}

/**
 * 2.4 Statistical Score on the shared factor tree.
 *
 * Three tests per indicator, each 0 / 0.5 / 1, multiplied into the total — so a
 * zero anywhere is the whole story, and the selected row spells out which test
 * produced it.
 */
export function StatCanvas() {
  const card = useSimStore((s) => s.statScorecard)
  const update = useSimStore((s) => s.updateStatScorecard)
  const { index } = useLedgerIndex()
  const [selected, setSelected] = useState('')

  const cardRows = useMemo(() => card?.rows ?? [], [card])

  const rows: FactorCanvasRow[] = useMemo(
    () =>
      cardRows.map((r) => ({
        key: r.id,
        l1: r.l1, l2: r.l2, l3: r.l3, l4: r.l4,
        indicator: r.indicator,
        tone: TONE[r.autoVerdict] ?? 'muted',
        statusLabel: r.autoVerdict === 'unconsiderable' ? 'Unconsiderable' : r.autoVerdict || '—',
        cells: [
          `${r.cv.toFixed(2)} (${r.cvScore})`,
          `${r.pearson >= 0 ? '+' : ''}${r.pearson.toFixed(2)} (${r.pearsonScore})`,
          `${r.vif.toFixed(1)} (${r.vifScore})`,
          r.total.toFixed(2),
        ],
        blockedBy: blockedBefore(index.get(indicatorKey(r.l4, r.indicator)), 'statistical'),
      })),
    [cardRows, index],
  )

  const current: StatScoreRow | undefined = useMemo(
    () => cardRows.find((r) => r.id === selected),
    [cardRows, selected],
  )

  if (!card) return null

  function setDisposition(id: string, disposition: StatDisposition) {
    void update({ rows: cardRows.map((r) => (r.id === id ? { ...r, disposition } : r)) })
  }

  const zeroed = cardRows.filter((r) => r.total === 0).length
  const header = (
    <header>
      <h3 className="text-sm font-medium">Statistical Score</h3>
      <p className="text-[11px] text-muted-foreground">
        {cardRows.length} indicators scored · {zeroed} failed a test outright ·
        Total = CV × Pearson × VIF
      </p>
    </header>
  )

  return (
    <>
      <FactorTreeCanvas
        rows={rows}
        columns={['CV', 'Pearson', 'VIF', 'Total']}
        selectedKey={selected}
        onSelect={setSelected}
        header={header}
        emptyHint="Run 2.4 to score the indicators."
        actions={(r) => {
          const row = cardRows.find((x) => x.id === r.key)
          if (!row) return null
          return (
            <div className="inline-flex rounded-md border border-border p-0.5">
              {DISPOSITIONS.map((d) => (
                <button key={d.id} type="button" onClick={() => setDisposition(row.id, d.id)}
                  className={cn('rounded px-1.5 py-0.5 text-[11px]',
                    row.disposition === d.id ? d.on : 'text-muted-foreground hover:bg-accent')}>
                  {d.label}
                </button>
              ))}
            </div>
          )
        }}
      />
      {current && (
        <aside className="max-h-56 overflow-auto border-t border-border p-3">
          <p className="mb-1 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {current.l4 || current.l3} · {current.indicator}
          </p>
          <dl className="grid grid-cols-3 gap-3 text-[11px]">
            <div>
              <dt className="text-muted-foreground">Volatility · CV</dt>
              <dd className="tabular-nums">{current.cv.toFixed(3)} → band {current.cvScore}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Correlation · r</dt>
              <dd className="tabular-nums">{current.pearson.toFixed(3)} → band {current.pearsonScore}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Collinearity · VIF</dt>
              <dd className="tabular-nums">{current.vif.toFixed(2)} → band {current.vifScore}</dd>
            </div>
          </dl>
          {current.note && <p className="mt-2 text-[11px] text-muted-foreground">{current.note}</p>}
        </aside>
      )}
    </>
  )
}
```

> `StatScoreRow` has no `rationale` field on the TypeScript side (the backend renders the AI
> rationale into the sheet body); the `note` field is the human's. If a `rationale` field is
> present in `lib/types.ts`, render it above `note`.

- [ ] **Step 3: Register it and drop the redundant editor entry**

In `ArtifactCanvas.tsx` add `'a-stat-tests': () => <StatCanvas />,` to `ID_CANVASES` with the
import. In `ArtifactDetail.tsx` remove `'a-stat-tests': () => <StatScoreEditor />,` from
`STRUCTURED_EDITORS` (and the import if unused there — `TaskStepPanel` keeps its own).

- [ ] **Step 4: Build and lint**

```bash
cd "frontend" && npm run build && npm run lint
```
Expected: both succeed.

- [ ] **Step 5: Verify in the running app**

Re-run task 2.4 on a project and open the Statistical Score artifact.

Expected: each row shows CV / Pearson / VIF with their bands and the product total; every band
is one of 0, 0.5, 1; indicators denied at 2.3 are greyed with a "Denied @ Business Validation"
badge; the header counts how many failed a test outright.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/project/canvas/StatCanvas.tsx \
        frontend/src/components/project/canvas/ArtifactCanvas.tsx \
        frontend/src/components/project/ArtifactDetail.tsx \
        frontend/src/components/project/StatScoreEditor.tsx
git commit -m "feat: Statistical Score canvas on the shared factor tree"
```

---

## Task 12: Tool-call timeline

**Files:**
- Create: `frontend/src/components/tools/ToolTimeline.tsx`
- Modify: `frontend/src/components/tools/tool-language.ts`
- Modify: `frontend/src/components/project/ArtifactDetail.tsx:212-214`

**Interfaces:**
- Consumes: `ToolInvocation` from `lib/types.ts`; `invocationsForTask`, `STATUS_META`,
  `formatDuration` from `tool-language.ts`; `TaskRuntime.status` from the store.
- Produces: `<ToolTimeline taskId status className />` replacing `<ToolTrace />` at the
  `BuildStep` mount point. `ToolTrace.tsx` is left in place (nothing else imports it; delete it
  only if a grep confirms zero other references).

- [ ] **Step 1: Add the expected-tools map**

Append to `frontend/src/components/tools/tool-language.ts`:

```ts
/**
 * The registered tools each step is expected to call, in call order.
 *
 * Used only to seed queued placeholders while a task runs — the real timeline is
 * whatever `tool_invocations` reports, so a step that calls something not listed
 * here still renders it, and a step that skips a listed tool just leaves it
 * queued until the run ends.
 */
export const EXPECTED_TOOLS: Record<string, string[]> = {
  '2.2': ['quality.consistency', 'quality.accuracy', 'quality.completeness', 'quality.granularity'],
  '2.4': ['stat.cv', 'stat.pearson', 'stat.vif'],
  '2.5': ['model.ols'],
  '2.5r': ['model.ols'],
}

/** Display name for a tool id we have not seen an invocation for yet. */
export const TOOL_DISPLAY_NAME: Record<string, string> = {
  'quality.consistency': 'Consistency Check',
  'quality.accuracy': 'Accuracy Check',
  'quality.completeness': 'Completeness Check',
  'quality.granularity': 'Granularity Check',
  'stat.cv': 'CV (Volatility)',
  'stat.pearson': 'Pearson Correlation',
  'stat.vif': 'VIF (Collinearity)',
  'model.ols': 'OLS MMM Fit',
}
```

- [ ] **Step 2: Create the timeline component**

`frontend/src/components/tools/ToolTimeline.tsx`:

```tsx
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'

import { cn } from '../../lib/utils'
import type { ToolInvocation } from '../../lib/types'
import { useSimStore } from '../../store/useSimStore'
import {
  EXPECTED_TOOLS,
  STATUS_META,
  TOOL_DISPLAY_NAME,
  formatDuration,
  invocationsForTask,
} from './tool-language'

interface Line {
  key: string
  toolId: string
  toolName: string
  /** Present once the backend has recorded the call. */
  invocation?: ToolInvocation
}

/**
 * The registered tools a build step called, as an ordered timeline.
 *
 * While the step runs, tools it is expected to call are pre-rendered as queued
 * lines and light up one at a time as the 1.5s state poll brings their
 * invocations back — so the analysis reads as something being performed, not as a
 * result that appeared. Nothing here is fabricated: a queued line carries no
 * numbers, and the moment an invocation lands it replaces the placeholder.
 */
export function ToolTimeline({
  taskId,
  status,
  className,
}: {
  taskId: string
  status: string
  className?: string
}) {
  const { projectId } = useParams()
  const all = useSimStore((s) => s.toolInvocations)
  const [open, setOpen] = useState<Set<string>>(new Set())

  const lines = useMemo<Line[]>(() => {
    const done = invocationsForTask(all, taskId)
    const seen = new Set(done.map((v) => v.toolId))
    const lines: Line[] = done.map((v) => ({
      key: v.id, toolId: v.toolId, toolName: v.toolName, invocation: v,
    }))
    if (status === 'running') {
      for (const toolId of EXPECTED_TOOLS[taskId] ?? []) {
        if (seen.has(toolId)) continue
        lines.push({ key: `queued-${toolId}`, toolId, toolName: TOOL_DISPLAY_NAME[toolId] ?? toolId })
      }
    }
    return lines
  }, [all, taskId, status])

  if (!lines.length) return null

  const firstQueued = lines.find((l) => !l.invocation)?.key

  function toggle(key: string) {
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <section className={cn('space-y-1', className)} aria-label="Tool calls">
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        Tools · {lines.filter((l) => l.invocation).length}/{lines.length}
      </p>
      <ol className="space-y-0.5 border-l border-border/60 pl-2">
        {lines.map((l) => {
          const v = l.invocation
          const active = !v && l.key === firstQueued
          const expanded = open.has(l.key)
          return (
            <li key={l.key} className="text-[11px]">
              <div className="flex items-center gap-1.5">
                {v ? (
                  <button type="button" onClick={() => toggle(l.key)}
                    className="text-muted-foreground hover:text-foreground">
                    {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  </button>
                ) : active ? (
                  <Loader2 className="h-3 w-3 animate-spin text-sky-500" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/30" />
                )}
                {v ? <span className={cn('h-1.5 w-1.5 rounded-full', STATUS_META[v.status].dot)} /> : null}
                <Link to={`/p/${projectId}/tools/${encodeURIComponent(l.toolId)}`}
                  className={cn('hover:underline', !v && 'text-muted-foreground/70')}>
                  {l.toolName}
                </Link>
                {v ? (
                  <span className="ml-auto tabular-nums text-muted-foreground">
                    {formatDuration(v.durationMs)}
                  </span>
                ) : (
                  <span className="ml-auto text-muted-foreground/60">{active ? 'running' : 'queued'}</span>
                )}
              </div>
              {v && expanded && (
                <dl className="ml-6 mt-0.5 space-y-0.5 text-[10.5px] text-muted-foreground">
                  <div><dt className="inline font-medium">In · </dt><dd className="inline">{v.argsSummary || '—'}</dd></div>
                  <div><dt className="inline font-medium">Out · </dt><dd className="inline">{v.resultSummary || '—'}</dd></div>
                  {v.error && <div className="text-rose-600">{v.error}</div>}
                </dl>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
```

- [ ] **Step 3: Mount it in `BuildStep`**

In `frontend/src/components/project/ArtifactDetail.tsx`, replace lines 212-214:

```tsx
{/* Which registered tools this step called — shown collapsed too, since a
    finished step is exactly when you want to see what it actually ran, and
    shown queued while it runs, so the analysis reads as work in progress. */}
<ToolTimeline taskId={task.id} status={status} className="mt-2 pl-5" />
```

and change the import on line 17 from `ToolTrace` to `ToolTimeline`. `status` is already in
scope at line 123.

- [ ] **Step 4: Build and lint**

```bash
cd "frontend" && npm run build && npm run lint
```
Expected: both succeed.

- [ ] **Step 5: Verify the loading behaviour**

Reset a project and run it, watching the 2.2 and 2.4 build steps while they execute.

```bash
curl -XPOST localhost:8000/api/projects/danone-mizone/reset
curl -XPOST localhost:8000/api/projects/danone-mizone/run \
     -H 'content-type: application/json' -d '{"autopilot":true}'
```

Expected: while 2.4 is running, three queued lines appear (CV, Pearson, VIF) with the first
spinning; each converts to a completed line with a duration and an expandable in/out summary as
its invocation lands. A finished step shows only the real invocations, no queued lines.

- [ ] **Step 6: Remove `ToolTrace` if it is now unreferenced**

```bash
cd "frontend" && grep -rn "ToolTrace" src/
```
If the only hit is the file's own definition, delete `src/components/tools/ToolTrace.tsx`.
Otherwise leave it.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/tools frontend/src/components/project/ArtifactDetail.tsx
git commit -m "feat: tool-call timeline with live queued/running state in build steps"
```

---

## Final verification

- [ ] **Run the full backend test set**

```bash
cd "backend" && for t in tests/test_data_rules.py tests/test_stat_scoring.py \
    tests/test_bv_signoff.py tests/test_ledger.py tests/test_s2_roundtrip.py \
    tests/test_quality_scoring.py tests/test_ols_review.py tests/test_api_smoke.py \
    app/tools/_test_tools.py; do
  echo "── $t"; PYTHONPATH=. .venv/bin/python "$t" || echo "FAILED: $t"
done
```
Expected: every file prints its success summary; no `FAILED:` lines.

- [ ] **Build the frontend and walk the app**

```bash
cd "frontend" && npm run build && npm run lint
```

With both servers running:

```bash
cd "frontend" && node scripts/visual-check.mjs
```
Expected: the Playwright walk-through completes without errors.

- [ ] **Confirm the four S2 canvases all show the tree**

Open 2.1 Data Processing, 2.2 Data Quality Score, 2.3 Business Validation and 2.4 Statistical
Score in turn. Each must show the same L1 › L2 › L3 grouping over the same indicators, with its
own status overlay, and rows rejected by an earlier layer greyed with the rejecting layer named.
