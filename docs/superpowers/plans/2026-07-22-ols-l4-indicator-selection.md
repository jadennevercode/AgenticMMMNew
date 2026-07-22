# OLS 2.5 By-L4 Indicator Selection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn step 2.5 from a single fit into a By-L4 sweep that runs one OLS per candidate indicator and elects one winner per L4, and decouple ROI so any indicator representing an L4 yields that L4's ROI from its Spending series.

**Architecture:** A new pure module `app/mmm/selector.py` runs a single-pass sweep — L4s ordered by their strongest candidate's |pearson|, each L4's candidates fitted in the full-model context of the other L4s' current representatives, scored on Knowledge-range alignment + adj-R². It is registered as tool `model.select_indicator` with one `ToolInvocation` per Run. `ModelFrame` gains `l4_spend` (per-L4 Spending series, never in the design matrix) so `_roi` can use an in-model indicator as numerator and the L4's spend as denominator; `MmmModelResult` gains `l4_rollup`. A new blueprint task `2.5s` executes the sweep between `2.5y` and `2.5x`.

**Tech Stack:** Python 3 / FastAPI / pandas / numpy (no new deps) · React 19 + TypeScript + Zustand (no new deps)

**Spec:** `docs/superpowers/specs/2026-07-22-ols-l4-indicator-selection-design.md`

## Global Constraints

- **No mock data.** Every number is computed from the long table or reused from an earlier layer. Never hardcode ROI/contribution/scores.
- **Identity wrappers only.** Tool `run` functions must not do arithmetic. `app/tools/_test_tools.py` asserts wrapper == direct call; if it fails, revert the tool layer.
- **Backward compatibility is load-bearing.** When the in-model column IS the spend column, ROI must be numerically identical to today. Legacy auto-fit path (no `ols_config`) must keep working.
- **Four contracts stay in sync:** `domain/blueprint.py` ↔ `lib/scenario.ts`, `domain/models.py` ↔ `lib/types.ts`.
- **`ProjectState` serializes snake_case** — never alias `ProjectState`'s own fields. All new fields hang off `OlsConfig` (a `CamelModel`).
- **Product copy is English-only** (UI strings, findings text, tool docs). Chinese is allowed only in blueprint `basis_note` fields, matching existing rows.
- **Scoring constants:** `W_KNOWLEDGE = 0.6`, `W_STAT = 0.4`, `MAX_VIF_SELECT = 10.0`.
- **Tests are runnable scripts, not pytest.** Pattern: `_check(name, cond, detail)` printing `[PASS]`/`[FAIL]`, `main()` returning exit code. Run with `.venv/bin/python -m app.mmm._test_x` from `backend/`.
- All backend commands run from `backend/` with `.venv/bin/python`; frontend from `frontend/` with `npm`.

---

### Task 1: Per-L4 Spending series on `ModelFrame`

Collect each L4's Spending series during the pivot. It never enters the design matrix — it exists only to be an ROI denominator.

**Files:**
- Modify: `backend/app/mmm/pivot.py` (`ModelFrame` dataclass ~line 77-107; `build_model_frame` ~line 287-452)
- Test: `backend/app/mmm/_test_l4_roi.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ModelFrame.l4_spend: dict[str, pd.Series]` keyed by `_norm(l4)`, values indexed by yyyymm month; `ModelFrame.l4_spend_meta: dict[str, list[str]]` mapping norm-l4 → contributing metric labels. `_norm` is the existing module-level function in `pivot.py`.

- [ ] **Step 1: Write the failing test**

Create `backend/app/mmm/_test_l4_roi.py`:

```python
"""L4-level ROI: numerator from the in-model indicator, denominator from the
L4's Spending series — whether or not that Spending column is in the model.

Run: .venv/bin/python -m app.mmm._test_l4_roi
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.mmm.pivot import build_model_frame


def _check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return bool(cond)


def make_long(n: int = 36, seed: int = 7) -> pd.DataFrame:
    """One model object 'MT', one L4 'TV' carrying both a spend and an
    exposure metric that are proportional (exposure = spend * 10), plus an
    unrelated L4 'Price' so the design matrix has a second driver."""
    rng = np.random.default_rng(seed)
    months = [202000 + 100 * (i // 12) + (i % 12) + 1 for i in range(n)]
    months = [m if m % 100 <= 12 else m for m in months]
    spend = rng.uniform(80.0, 220.0, n)
    price = rng.uniform(9.0, 11.0, n)
    y = 500.0 + 2.0 * spend - 15.0 * price + rng.normal(0, 3.0, n)

    rows: list[dict] = []
    def add(metric: str, mtype: str, l1: str, l4: str, vals: np.ndarray) -> None:
        for m, v in zip(months, vals):
            rows.append({
                "task_name": "t", "brand": "B", "province_group": "P",
                "channel_type": "MT", "channel": "MT",
                "year": m // 100, "month": m, "source": "synthetic",
                "l1": l1, "l2": "", "l3": "", "l4": l4,
                "l5": "", "l6": "", "l7": "", "l8": "",
                "metric_type": mtype, "metric": metric, "value": float(v),
            })
    add("本品销量", "箱数", "KPI", "KPI", y)
    add("TV花费", "spending", "MARKETING FACTOR", "TV", spend)
    add("TV曝光量", "X", "MARKETING FACTOR", "TV", spend * 10.0)
    add("平均售价", "X", "COMMERCIAL FACTOR", "Price", price)
    return pd.DataFrame(rows)


def test_l4_spend_collected() -> bool:
    df = make_long()
    mf = build_model_frame(df, "MT")
    got = mf.l4_spend
    ok = "tv" in got
    ok &= "price" not in got          # no spend metric under Price
    if ok:
        s = got["tv"]
        ok &= len(s) == 36
        ok &= np.isclose(float(s.sum()), float(
            df[df["metric"] == "TV花费"]["value"].sum()))
    return _check("build_model_frame collects per-L4 spend", ok,
                  f"keys={sorted(got)}")


def test_l4_spend_excluded_from_design() -> bool:
    """The spend series is a denominator, not a driver: collecting it must not
    change which columns the model fits."""
    df = make_long()
    mf = build_model_frame(df, "MT", include=frozenset({"tv曝光量"}))
    ok = mf.x_cols == ["TV曝光量"]
    ok &= "tv" in mf.l4_spend        # still collected though not in the model
    return _check("l4_spend does not enter x_cols", ok, f"x_cols={mf.x_cols}")


def main() -> int:
    results = [test_l4_spend_collected(), test_l4_spend_excluded_from_design()]
    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && .venv/bin/python -m app.mmm._test_l4_roi
```
Expected: FAIL — `AttributeError: 'ModelFrame' object has no attribute 'l4_spend'`

- [ ] **Step 3: Add the fields to `ModelFrame`**

In `backend/app/mmm/pivot.py`, extend the `ModelFrame` dataclass. Add to the docstring's Attributes list and add the two fields after `y_metric_type`:

```python
    y_metric: str = ""
    y_metric_type: str = ""
    # Per-L4 Spending series (norm_l4 -> monthly Series), aligned to the frame's
    # index. These are ROI *denominators* only: they never enter the design
    # matrix, so an L4 represented in the model by an exposure metric still has
    # a real spend to divide by. `l4_spend_meta` records which metric labels
    # were summed into each series so the UI can explain the denominator.
    l4_spend: dict[str, pd.Series] = field(default_factory=dict)
    l4_spend_meta: dict[str, list[str]] = field(default_factory=dict)
```

- [ ] **Step 4: Collect the series in `build_model_frame`**

In `backend/app/mmm/pivot.py`, immediately BEFORE the line `# Aggregate each metric by month (sum duplicates), build wide columns.` insert:

```python
    # --- Per-L4 Spending series (ROI denominators) -------------------------
    # Collected from the object's rows BEFORE exclusions and the include filter:
    # a spend metric that is not a model variable (or was dropped upstream) is
    # still the honest denominator for its L4. Not added to the design matrix.
    l4_spend: dict[str, pd.Series] = {}
    l4_spend_meta: dict[str, list[str]] = {}
    spend_rows = obj[[_is_spend(mt, mv) for mt, mv in
                      zip(obj["metric_type"], obj["metric"])]]
    if not spend_rows.empty:
        l4_of = (spend_rows["l4"].astype("string").map(_norm)
                 if "l4" in spend_rows.columns
                 else pd.Series("", index=spend_rows.index))
        for l4v, g in spend_rows.groupby(l4_of):
            if not l4v:
                continue
            l4_spend[str(l4v)] = g.groupby("month")["value"].sum()
            l4_spend_meta[str(l4v)] = sorted({str(m) for m in g["metric"]})
```

Then in the `return ModelFrame(...)` call at the end of the function, add the two arguments after `y_metric_type=y_metric_type,`:

```python
        l4_spend={k: v.reindex(wide.index).fillna(0.0) for k, v in l4_spend.items()},
        l4_spend_meta=l4_spend_meta,
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && .venv/bin/python -m app.mmm._test_l4_roi
```
Expected: `2/2 passed`

- [ ] **Step 6: Verify no regression in the existing suites**

```bash
cd backend && .venv/bin/python -m app.mmm._test_synthetic && .venv/bin/python -m app.mmm._test_real
```
Expected: both print their existing all-pass summaries.

- [ ] **Step 7: Commit**

```bash
git add backend/app/mmm/pivot.py backend/app/mmm/_test_l4_roi.py
git commit -m "feat(mmm): collect per-L4 spending series on ModelFrame as ROI denominators"
```

---

### Task 2: ROI numerator/denominator decoupling + L4 rollup

**Files:**
- Modify: `backend/app/mmm/engine.py` (`_roi` ~line 192-219; `MmmModelResult` ~line 30-82; `run_mmm` ~line 330-427)
- Test: `backend/app/mmm/_test_l4_roi.py` (extend)

**Interfaces:**
- Consumes: `ModelFrame.l4_spend`, `ModelFrame.l4_spend_meta` from Task 1.
- Produces:
  - `engine._roi(mf, X, res, price_per_unit) -> tuple[dict[str, float], str, dict[str, str]]` — third element is `roi_denominator_source` per driver column: `"self"` | `"l4_spend:<labels>"` | `"none"`.
  - `MmmModelResult.l4_rollup: dict[str, dict]` — `{norm_l4: {"l4": str, "contribution": float, "roi": float|None, "roiDenominatorSource": str, "indicators": [col names]}}`.
  - `MmmModelResult.meta["roi_denominator_source"]: dict[str, str]`.

- [ ] **Step 1: Write the failing test**

Append to `backend/app/mmm/_test_l4_roi.py`, before `def main()`:

```python
def test_roi_when_spend_in_model() -> bool:
    """Backward compatibility: spend column in the model → denominator is
    itself, and the number matches the manual coef * sum(X) / sum(raw)."""
    from app.mmm.engine import run_mmm

    df = make_long()
    res = run_mmm(df, "MT", adstock=0.0, hill_half=None,
                  include=frozenset({"tv花费", "平均售价"}))
    roi = res.roi.get("TV花费")
    src = res.meta["roi_denominator_source"].get("TV花费")
    ok = roi is not None and src == "self"
    return _check("ROI with spend in model uses itself as denominator", ok,
                  f"roi={roi} src={src}")


def test_roi_when_only_exposure_in_model() -> bool:
    """Exposure represents the L4; spend is NOT a model variable. ROI must
    still exist, and — because exposure = spend * 10 exactly — it must equal
    the spend-in-model ROI to within numerical tolerance."""
    from app.mmm.engine import run_mmm

    df = make_long()
    a = run_mmm(df, "MT", adstock=0.0, hill_half=None,
                include=frozenset({"tv花费", "平均售价"}))
    b = run_mmm(df, "MT", adstock=0.0, hill_half=None,
                include=frozenset({"tv曝光量", "平均售价"}))
    roi_a = a.l4_rollup.get("tv", {}).get("roi")
    roi_b = b.l4_rollup.get("tv", {}).get("roi")
    src_b = b.meta["roi_denominator_source"].get("TV曝光量", "")
    ok = roi_a is not None and roi_b is not None
    ok &= np.isclose(float(roi_a), float(roi_b), rtol=1e-6)
    ok &= src_b.startswith("l4_spend:")
    return _check("ROI from exposure equals ROI from spend (proportional data)",
                  ok, f"spend={roi_a} exposure={roi_b} src={src_b}")


def test_l4_rollup_sums_contribution() -> bool:
    from app.mmm.engine import run_mmm

    df = make_long()
    res = run_mmm(df, "MT", adstock=0.0, hill_half=None,
                  include=frozenset({"tv花费", "tv曝光量", "平均售价"}))
    tv = res.l4_rollup.get("tv", {})
    manual = sum(res.contribution[c] for c in ("TV花费", "TV曝光量")
                 if c in res.contribution)
    ok = np.isclose(float(tv.get("contribution", 0.0)), manual, rtol=1e-9)
    ok &= sorted(tv.get("indicators", [])) == ["TV曝光量", "TV花费"]
    return _check("l4_rollup sums per-L4 contribution", ok,
                  f"rollup={tv.get('contribution')} manual={manual}")
```

And replace the `main()` body's `results` list with:

```python
    results = [
        test_l4_spend_collected(),
        test_l4_spend_excluded_from_design(),
        test_roi_when_spend_in_model(),
        test_roi_when_only_exposure_in_model(),
        test_l4_rollup_sums_contribution(),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && .venv/bin/python -m app.mmm._test_l4_roi
```
Expected: FAIL — `KeyError: 'roi_denominator_source'` / `AttributeError: ... 'l4_rollup'`

- [ ] **Step 3: Rewrite `_roi` in `backend/app/mmm/engine.py`**

Replace the whole `_roi` function (lines ~192-219) with:

```python
def _roi(
    mf: ModelFrame, X: pd.DataFrame, res: OLSResult, price_per_unit: float | None = None
) -> tuple[dict[str, float], str, dict[str, str]]:
    """ROI per driver = incremental **revenue** / that driver's L4 spend.

    ``incremental = coef · Σ(transformed x)`` is the counterfactual lift in Y
    from zeroing that driver. The denominator is decoupled from the numerator:

    * the driver IS a spend column       → denominator is its own raw series
      (identical to the pre-decoupling behaviour);
    * the driver is any other metric     → denominator is its L4's Spending
      series (``mf.l4_spend``), so a factor represented in the model by an
      exposure metric still yields a real ROI;
    * the L4 has no Spending series      → no ROI for that driver.

    Converting the lift to revenue depends on what Y is:

    * Y is money (RMB / value / GMV)  → incremental is already revenue → true ROI.
    * Y is volume + ``price_per_unit`` → incremental × price → true ROI.
    * Y is volume, no price            → ROI stays volume-per-spend; the caller
      must label the unit and must NOT compare it to money ROI benchmarks.

    Returns ``(roi, unit, denominator_source)`` where unit is "revenue/spend" or
    "volume/spend" and denominator_source maps column → "self" |
    "l4_spend:<labels>" | "none".
    """
    money = mf.y_is_money
    price = None if money else (price_per_unit if (price_per_unit or 0) > 0 else None)
    unit = "revenue/spend" if (money or price) else "volume/spend"

    roi: dict[str, float] = {}
    source: dict[str, str] = {}
    for c in mf.x_cols:
        incremental = float(res.coef[c] * X[c].to_numpy(dtype=float).sum())
        if price:
            incremental *= float(price)

        if c in mf.spend_cols:
            spend = float(mf.frame[c].to_numpy(dtype=float).sum())
            src = "self"
        else:
            l4n = str(mf.meta[c].get("l4", "")).strip().lower()
            series = mf.l4_spend.get(l4n)
            if series is None:
                source[c] = "none"
                continue
            spend = float(pd.Series(series).to_numpy(dtype=float).sum())
            labels = ", ".join(mf.l4_spend_meta.get(l4n, []))
            src = f"l4_spend:{labels}"

        if spend > 0:
            roi[c] = incremental / spend
            source[c] = src
        else:
            source[c] = "none"
    return roi, unit, source
```

- [ ] **Step 4: Add the rollup builder**

In `backend/app/mmm/engine.py`, insert this function immediately after `_roi`:

```python
def _l4_rollup(
    mf: ModelFrame, contribution: dict[str, float], roi: dict[str, float],
    roi_source: dict[str, str],
) -> dict[str, dict]:
    """Aggregate per-column results to the L4 (factor) level.

    Contribution sums across the L4's in-model columns; ROI sums the same
    columns' incremental effect over ONE shared denominator, so summing the
    per-column ratios is correct only because they share it — a column whose
    denominator is missing contributes nothing and is recorded as such.
    Knowledge ranges are maintained per (L4, indicator), so this is the level
    the review compares against.
    """
    out: dict[str, dict] = {}
    for c in mf.x_cols:
        l4_label = str(mf.meta[c].get("l4", "")).strip()
        l4n = l4_label.lower()
        if not l4n:
            continue
        entry = out.setdefault(l4n, {
            "l4": l4_label, "contribution": 0.0, "roi": None,
            "roiDenominatorSource": "none", "indicators": [],
        })
        entry["indicators"].append(c)
        entry["contribution"] += float(contribution.get(c, 0.0))
        if c in roi:
            entry["roi"] = float(roi[c]) if entry["roi"] is None else entry["roi"] + float(roi[c])
            entry["roiDenominatorSource"] = roi_source.get(c, "none")
    for entry in out.values():
        entry["contribution"] = round(entry["contribution"], 6)
        if entry["roi"] is not None:
            entry["roi"] = round(entry["roi"], 6)
        entry["indicators"].sort()
    return out
```

- [ ] **Step 5: Add `l4_rollup` to `MmmModelResult`**

In `backend/app/mmm/engine.py`, in the `MmmModelResult` dataclass add after `due_to: dict = field(default_factory=dict)`:

```python
    # Per-L4 (factor-level) aggregation — the level Knowledge ranges compare at.
    l4_rollup: dict = field(default_factory=dict)
```

And in `to_dict()` add after `"due_to": self.due_to,`:

```python
            "l4_rollup": self.l4_rollup,
```

- [ ] **Step 6: Wire it in `run_mmm`**

In `backend/app/mmm/engine.py`, in `run_mmm`, replace the line:

```python
    roi, roi_unit = _roi(mf, X, res, price)
```

with:

```python
    roi, roi_unit, roi_source = _roi(mf, X, res, price)
    l4_rollup = _l4_rollup(mf, contribution, roi, roi_source)
```

In the `return MmmModelResult(...)` call add after `due_to=due_to,`:

```python
        l4_rollup=l4_rollup,
```

and inside the `meta={...}` dict add after `"spend_cols": mf.spend_cols,`:

```python
            "roi_denominator_source": roi_source,
            "l4_spend_meta": mf.l4_spend_meta,
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd backend && .venv/bin/python -m app.mmm._test_l4_roi
```
Expected: `5/5 passed`

- [ ] **Step 8: Verify no regression**

```bash
cd backend && .venv/bin/python -m app.mmm._test_synthetic && .venv/bin/python -m app.mmm._test_real && PYTHONPATH=. .venv/bin/python -m app.tools._test_tools
```
Expected: all print their existing all-pass summaries. `_test_tools` must still pass unchanged — `run_mmm`'s numbers for spend-in-model columns did not move.

- [ ] **Step 9: Commit**

```bash
git add backend/app/mmm/engine.py backend/app/mmm/_test_l4_roi.py
git commit -m "feat(mmm): decouple ROI numerator/denominator and add per-L4 rollup"
```

---

### Task 3: The sweep — `app/mmm/selector.py`

**Files:**
- Create: `backend/app/mmm/selector.py`
- Create: `backend/app/mmm/_test_selector.py`
- Modify: `backend/app/mmm/__init__.py` (export)

**Interfaces:**
- Consumes: `run_mmm` (Task 2 signature), `MmmModelResult.l4_rollup`, `meta["roi_denominator_source"]`.
- Produces:
  ```python
  @dataclass(frozen=True) class CandidateRun:
      l4: str; indicator: str; metric: str
      adj_r2: float; coef: float; t_value: float; vif: float
      roi: float | None; roi_unit: str; roi_denominator_source: str
      contribution: float | None
      roi_status: str; contribution_status: str          # "in"|"out"|"none"
      score: float; score_knowledge: float; score_stat: float
      eliminated: bool; eliminated_reason: str
  @dataclass(frozen=True) class L4Group:
      l4: str; order: int; candidates: list[CandidateRun]
      winner: str; rationale: str; status: str            # "decided"|"single"|"noViable"
  @dataclass(frozen=True) class SelectionResult:
      order: list[str]; groups: list[L4Group]; run_count: int

  def select_indicators(long_df, objects, groups, *, y, params, exclude,
                        benchmark, pearson_of, on_run=None) -> SelectionResult
  ```
  - `groups: dict[str, list[dict]]` — norm_l4 → candidate dicts with keys `l4`, `metric`, `is_spend` (as produced by `pivot.driver_candidates`).
  - `y: dict[str, str]` — model object → Y metric (may be empty for auto-pick).
  - `benchmark: Callable[[str, str], RangeBenchmark | None]` — `(l4, indicator)`.
  - `pearson_of: Callable[[str, str], float]` — `(l4, metric)` → |pearson| from the 2.4 scorecard, 0.0 when unknown.
  - `on_run: Callable[[CandidateRun], None] | None` — called after every fit; the tracing hook.

- [ ] **Step 1: Write the failing test**

Create `backend/app/mmm/_test_selector.py`:

```python
"""By-L4 indicator selection on data with a known best answer.

Run: .venv/bin/python -m app.mmm._test_selector

Ground truth: under L4 'TV' the metric 'TV花费' drives Y and 'TV噪声' is pure
noise, so the sweep must elect 'TV花费'. Under L4 'Price' there is a single
candidate, which must be elected with status "single".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents.data_rules import RangeBenchmark
from app.mmm.selector import select_indicators


def _check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return bool(cond)


def make_long(n: int = 36, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = [202000 + 100 * (i // 12) + (i % 12) + 1 for i in range(n)]
    spend = rng.uniform(80.0, 220.0, n)
    noise = rng.uniform(80.0, 220.0, n)      # same scale, no relation to Y
    price = rng.uniform(9.0, 11.0, n)
    y = 500.0 + 2.0 * spend - 15.0 * price + rng.normal(0, 2.0, n)

    rows: list[dict] = []
    def add(metric: str, mtype: str, l1: str, l4: str, vals: np.ndarray) -> None:
        for m, v in zip(months, vals):
            rows.append({
                "task_name": "t", "brand": "B", "province_group": "P",
                "channel_type": "MT", "channel": "MT",
                "year": m // 100, "month": m, "source": "synthetic",
                "l1": l1, "l2": "", "l3": "", "l4": l4,
                "l5": "", "l6": "", "l7": "", "l8": "",
                "metric_type": mtype, "metric": metric, "value": float(v),
            })
    add("本品销量", "箱数", "KPI", "KPI", y)
    add("TV花费", "spending", "MARKETING FACTOR", "TV", spend)
    add("TV噪声", "X", "MARKETING FACTOR", "TV", noise)
    add("平均售价", "X", "COMMERCIAL FACTOR", "Price", price)
    return pd.DataFrame(rows)


GROUPS = {
    "tv": [
        {"l4": "TV", "metric": "TV花费", "is_spend": True},
        {"l4": "TV", "metric": "TV噪声", "is_spend": False},
    ],
    "price": [{"l4": "Price", "metric": "平均售价", "is_spend": False}],
}


def _no_benchmark(l4: str, indicator: str):
    return None


def _pearson(l4: str, metric: str) -> float:
    return {"TV花费": 0.9, "TV噪声": 0.05, "平均售价": 0.4}.get(metric, 0.0)


def test_elects_the_real_driver() -> bool:
    res = select_indicators(
        make_long(), ["MT"], GROUPS, y={}, params=None,
        exclude=frozenset(), benchmark=_no_benchmark, pearson_of=_pearson)
    tv = next(g for g in res.groups if g.l4 == "TV")
    ok = tv.winner == "TV花费" and tv.status == "decided"
    return _check("sweep elects the real driver over noise", ok,
                  f"winner={tv.winner} status={tv.status}")


def test_single_candidate_group() -> bool:
    res = select_indicators(
        make_long(), ["MT"], GROUPS, y={}, params=None,
        exclude=frozenset(), benchmark=_no_benchmark, pearson_of=_pearson)
    pr = next(g for g in res.groups if g.l4 == "Price")
    ok = pr.winner == "平均售价" and pr.status == "single"
    ok &= len(pr.candidates) == 1        # still runs a confirming fit
    return _check("single-candidate L4 still runs and is elected", ok,
                  f"status={pr.status} runs={len(pr.candidates)}")


def test_order_is_by_strongest_pearson() -> bool:
    res = select_indicators(
        make_long(), ["MT"], GROUPS, y={}, params=None,
        exclude=frozenset(), benchmark=_no_benchmark, pearson_of=_pearson)
    ok = res.order == ["TV", "Price"]     # TV max |r|=0.9 > Price 0.4
    return _check("L4 order follows strongest candidate |pearson|", ok,
                  f"order={res.order}")


def test_run_count_and_hook() -> bool:
    seen: list[str] = []
    res = select_indicators(
        make_long(), ["MT"], GROUPS, y={}, params=None,
        exclude=frozenset(), benchmark=_no_benchmark, pearson_of=_pearson,
        on_run=lambda r: seen.append(r.indicator))
    ok = res.run_count == 3               # 2 TV + 1 Price
    ok &= len(seen) == 3
    return _check("one on_run callback per candidate fit", ok,
                  f"run_count={res.run_count} hook={len(seen)}")


def test_knowledge_range_breaks_the_tie() -> bool:
    """Two candidates, both real drivers: the one whose contribution lands in
    its Knowledge band must win even if the other fits marginally better."""
    df = make_long()
    # Give TV噪声 a band it cannot hit and TV花费 a wide band it must hit.
    def bench(l4: str, indicator: str):
        if indicator == "TV花费":
            return RangeBenchmark(roi=None, contribution=(0.0, 100.0),
                                  roi_text="/", contribution_text="0%~100%",
                                  source="knowledge")
        return RangeBenchmark(roi=None, contribution=(99.0, 100.0),
                              roi_text="/", contribution_text="99%~100%",
                              source="knowledge")
    res = select_indicators(df, ["MT"], GROUPS, y={}, params=None,
                            exclude=frozenset(), benchmark=bench,
                            pearson_of=_pearson)
    tv = next(g for g in res.groups if g.l4 == "TV")
    ok = tv.winner == "TV花费"
    ok &= any(c.contribution_status == "in" for c in tv.candidates
              if c.indicator == "TV花费")
    return _check("Knowledge range participates in scoring", ok,
                  f"winner={tv.winner}")


def main() -> int:
    results = [
        test_elects_the_real_driver(),
        test_single_candidate_group(),
        test_order_is_by_strongest_pearson(),
        test_run_count_and_hook(),
        test_knowledge_range_breaks_the_tie(),
    ]
    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && .venv/bin/python -m app.mmm._test_selector
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.mmm.selector'`

- [ ] **Step 3: Write `backend/app/mmm/selector.py`**

```python
"""By-L4 indicator selection: one OLS Run per candidate, one winner per L4.

The problem this solves: a factor (L4) usually carries several indicators that
measure the same lever — spend, exposure, GRP, clicks. They are near-collinear,
so putting more than one in the regression splits the coefficient, inflates VIF
and double-counts the factor's contribution. Exactly one must represent the L4.

Why not score each indicator with its own single-variable regression: in a
single-variable fit the coefficient absorbs every collinear factor's effect, so
every candidate looks excellent and nothing discriminates. ROI and contribution
are only meaningful inside the full model. So each Run here is a COMPLETE fit —
all L4s present — with only the target L4's representative swapped. The
controlled variable is the other factors, not the candidate.

Cost: a single pass costs Σ(candidates) fits rather than Π(candidates) — an
addition, not a product. With closed-form OLS on a monthly series each fit is
sub-millisecond, so a real project sweeps in well under a second.

Path dependence is real and deliberate: L4s are swept strongest-first (by the
2.4 |pearson| of their best candidate) so that the strong factors are settled
before the weak ones are compared, and the order is reported so the choice is
auditable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import pandas as pd

from app.mmm.engine import run_mmm

__all__ = ["CandidateRun", "L4Group", "SelectionResult", "select_indicators"]

# Score weights: how much the Knowledge band matters versus how well the model
# fits. Knowledge leads because a statistically better fit on the wrong measure
# of a factor is still the wrong measure; statistics keep it honest because the
# bands are industry priors, not this client's truth.
W_KNOWLEDGE = 0.6
W_STAT = 0.4
MAX_VIF_SELECT = 10.0


def _norm(s: object) -> str:
    return str(s).strip().lower() if s is not None else ""


@dataclass(frozen=True)
class CandidateRun:
    """One complete OLS fit in which this candidate represented its L4."""
    l4: str
    indicator: str
    metric: str
    adj_r2: float
    coef: float
    t_value: float
    vif: float
    roi: Optional[float]
    roi_unit: str
    roi_denominator_source: str
    contribution: Optional[float]
    roi_status: str            # "in" | "out" | "none"
    contribution_status: str   # "in" | "out" | "none"
    score: float
    score_knowledge: float
    score_stat: float
    eliminated: bool
    eliminated_reason: str


@dataclass(frozen=True)
class L4Group:
    l4: str
    order: int
    candidates: list[CandidateRun]
    winner: str
    rationale: str
    status: str                # "decided" | "single" | "noViable"


@dataclass(frozen=True)
class SelectionResult:
    order: list[str] = field(default_factory=list)
    groups: list[L4Group] = field(default_factory=list)
    run_count: int = 0

    @property
    def winners(self) -> dict[str, str]:
        """norm_l4 -> winning metric label (winner-less groups omitted)."""
        return {_norm(g.l4): g.winner for g in self.groups if g.winner}


def _band_distance(value: Optional[float], rng: Optional[tuple]) -> Optional[float]:
    """1.0 inside the band, decaying linearly to 0 one band-width outside.

    Returns None when there is nothing to compare, so the caller can fall back
    to statistics alone rather than treating "no benchmark" as "bad".
    """
    if value is None or rng is None:
        return None
    v = float(value)
    if v != v:  # NaN
        return None
    lo, hi = float(rng[0]), float(rng[1])
    if lo <= v <= hi:
        return 1.0
    width = max(hi - lo, abs(hi), abs(lo), 1e-9)
    gap = (lo - v) if v < lo else (v - hi)
    return max(0.0, 1.0 - gap / width)


def _status(value: Optional[float], rng: Optional[tuple]) -> str:
    if value is None or rng is None:
        return "none"
    v = float(value)
    if v != v:
        return "none"
    return "in" if float(rng[0]) <= v <= float(rng[1]) else "out"


def _aggregate(values: list[float]) -> float:
    """Mean of the finite values across model objects; NaN when there are none."""
    finite = [float(v) for v in values if v is not None and float(v) == float(v)]
    return float(np.mean(finite)) if finite else float("nan")


def _fit_candidate(
    long_df: pd.DataFrame, objects: list[str], include: frozenset[str],
    *, l4n: str, metric: str, y: dict, params, exclude,
) -> dict:
    """Fit every model object with this candidate representing its L4.

    Returns the per-indicator numbers aggregated across objects. A model object
    that cannot be fitted at all is skipped rather than failing the sweep — a
    project may carry an object with too few months for this variable set.
    """
    adj_r2s, coefs, tvals, vifs, rois, contribs = [], [], [], [], [], []
    roi_unit, roi_src = "", "none"
    mn = _norm(metric)
    for obj in objects:
        try:
            res = run_mmm(long_df, obj, exclude=exclude,
                          y_metric=y.get(obj) or None, include=include,
                          params=params)
        except Exception:  # noqa: BLE001 — an unfittable object is not a verdict
            continue
        col = next((c for c in res.drivers
                    if _norm(res.meta.get("drivers_meta", {})
                             .get(c, {}).get("metric", c)) == mn), None)
        if col is None:
            continue
        adj_r2s.append(res.adj_r2)
        coefs.append(res.coefficients.get(col))
        tvals.append((res.meta.get("tvalues") or {}).get(col))
        vifs.append((res.vif or {}).get(col))
        rollup = (res.l4_rollup or {}).get(l4n, {})
        contribs.append(rollup.get("contribution"))
        if rollup.get("roi") is not None:
            rois.append(rollup["roi"])
        roi_unit = str(res.meta.get("roi_unit", "")) or roi_unit
        roi_src = str(rollup.get("roiDenominatorSource", "")) or roi_src
    return {
        "adj_r2": _aggregate(adj_r2s), "coef": _aggregate(coefs),
        "t_value": _aggregate(tvals), "vif": _aggregate(vifs),
        "roi": (_aggregate(rois) if rois else None),
        "contribution": (_aggregate(contribs) if contribs else None),
        "roi_unit": roi_unit, "roi_denominator_source": roi_src,
        "fitted": bool(adj_r2s),
    }


def _eliminate(stats: dict, is_spend: bool) -> str:
    """Hard constraints. A candidate failing one is out regardless of score."""
    if not stats["fitted"]:
        return "Did not enter any fitted model object"
    vif = stats["vif"]
    if vif == vif and float(vif) > MAX_VIF_SELECT:
        return f"VIF {float(vif):.1f} > {MAX_VIF_SELECT:g} — collinear with the rest"
    coef = stats["coef"]
    if is_spend and coef == coef and float(coef) < 0:
        return f"Wrong-sign coefficient on a paid driver ({float(coef):.4g} < 0)"
    return ""


def _normalize(values: list[float]) -> list[float]:
    """Min-max over the group's finite values; all-equal (or single) → all 1.0."""
    finite = [v for v in values if v == v]
    if not finite:
        return [0.0 for _ in values]
    lo, hi = min(finite), max(finite)
    if hi - lo < 1e-12:
        return [1.0 if v == v else 0.0 for v in values]
    return [((v - lo) / (hi - lo)) if v == v else 0.0 for v in values]


def _rationale(win: CandidateRun, others: list[CandidateRun], n_cands: int) -> str:
    if n_cands == 1:
        return (f"Only candidate for this factor — fitted once to confirm it "
                f"holds up (adj. R² {win.adj_r2:.3f}).")
    bits = [f"Best of {n_cands} candidates (score {win.score:.3f})"]
    if win.contribution_status == "in" or win.roi_status == "in":
        hit = [n for n, s in (("contribution", win.contribution_status),
                              ("ROI", win.roi_status)) if s == "in"]
        bits.append(f"{' and '.join(hit)} within the Knowledge band")
    bits.append(f"adj. R² {win.adj_r2:.3f}")
    runner = next((c for c in others if not c.eliminated), None)
    if runner is not None:
        bits.append(f"next best {runner.indicator} scored {runner.score:.3f}")
    return "; ".join(bits) + "."


def select_indicators(
    long_df: pd.DataFrame,
    objects: list[str],
    groups: dict[str, list[dict]],
    *,
    y: dict[str, str],
    params,
    exclude: frozenset,
    benchmark: Callable[[str, str], object],
    pearson_of: Callable[[str, str], float],
    on_run: Optional[Callable[[CandidateRun], None]] = None,
) -> SelectionResult:
    """Sweep every L4 once, electing one indicator each. See the module docstring.

    Args:
        groups: norm_l4 -> candidate dicts with ``l4`` / ``metric`` / ``is_spend``.
        y: model object -> confirmed Y metric ("" or missing = auto-pick).
        params: :class:`OlsParams` or None — passed through to every fit.
        exclude: driver ``(norm_l4, norm_metric)`` pairs rejected upstream.
        benchmark: ``(l4, indicator) -> RangeBenchmark | None``.
        pearson_of: ``(l4, metric) -> |pearson|`` from the 2.4 scorecard.
        on_run: called once per completed candidate fit (the tracing hook).
    """
    # Sweep order: the factor with the strongest candidate first, so the weak
    # factors are compared inside an already-settled model.
    ordered = sorted(
        groups.items(),
        key=lambda kv: -max((abs(float(pearson_of(c.get("l4", ""), c["metric"])))
                             for c in kv[1]), default=0.0),
    )

    # Starting representative per L4: the strongest candidate by |pearson|. This
    # is only the sweep's starting point, not a verdict.
    current: dict[str, str] = {
        l4n: max(cands, key=lambda c: abs(float(pearson_of(c.get("l4", ""), c["metric"]))))["metric"]
        for l4n, cands in groups.items() if cands
    }

    order: list[str] = []
    out_groups: list[L4Group] = []
    run_count = 0

    for position, (l4n, cands) in enumerate(ordered):
        if not cands:
            continue
        l4_label = str(cands[0].get("l4", "") or l4n)
        order.append(l4_label)

        runs: list[CandidateRun] = []
        raw: list[dict] = []
        for cand in cands:
            metric = cand["metric"]
            include = frozenset(
                [_norm(m) for k, m in current.items() if k != l4n] + [_norm(metric)])
            stats = _fit_candidate(long_df, objects, include, l4n=l4n, metric=metric,
                                   y=y, params=params, exclude=exclude)
            run_count += 1
            bench = benchmark(l4_label, metric)
            roi_rng = getattr(bench, "roi", None)
            con_rng = getattr(bench, "contribution", None)
            # A volume-per-spend ratio is not comparable to the Knowledge money
            # bands — the same discipline 2.5r already applies.
            if stats["roi_unit"] != "revenue/spend":
                roi_rng = None
            raw.append({
                "cand": cand, "metric": metric, "stats": stats,
                "roi_rng": roi_rng, "con_rng": con_rng,
                "eliminated": _eliminate(stats, bool(cand.get("is_spend"))),
            })

        # Statistical component is min-max normalised WITHIN the L4: the question
        # is which candidate represents this factor best, not how this factor
        # compares to others.
        stat_norm = _normalize([r["stats"]["adj_r2"] for r in raw])

        for r, s_stat in zip(raw, stat_norm):
            st_ = r["stats"]
            d_roi = _band_distance(st_["roi"], r["roi_rng"])
            d_con = _band_distance(st_["contribution"], r["con_rng"])
            hits = [d for d in (d_roi, d_con) if d is not None]
            s_know = float(np.mean(hits)) if hits else float("nan")
            score = (W_KNOWLEDGE * s_know + W_STAT * s_stat) if hits else s_stat
            run = CandidateRun(
                l4=l4_label, indicator=r["metric"], metric=r["metric"],
                adj_r2=float(st_["adj_r2"]), coef=float(st_["coef"]),
                t_value=float(st_["t_value"]), vif=float(st_["vif"]),
                roi=st_["roi"], roi_unit=st_["roi_unit"],
                roi_denominator_source=st_["roi_denominator_source"],
                contribution=st_["contribution"],
                roi_status=_status(st_["roi"], r["roi_rng"]),
                contribution_status=_status(st_["contribution"], r["con_rng"]),
                score=float(0.0 if score != score else score),
                score_knowledge=float(0.0 if s_know != s_know else s_know),
                score_stat=float(s_stat),
                eliminated=bool(r["eliminated"]), eliminated_reason=r["eliminated"],
            )
            runs.append(run)
            if on_run is not None:
                on_run(run)

        viable = [r for r in runs if not r.eliminated]
        if not viable:
            out_groups.append(L4Group(
                l4=l4_label, order=position, candidates=runs, winner="",
                rationale="No candidate cleared the sign / collinearity constraints — "
                          "this factor does not enter the model.",
                status="noViable"))
            current.pop(l4n, None)
            continue

        best = max(viable, key=lambda r: r.score)
        current[l4n] = best.metric
        others = sorted((r for r in runs if r is not best),
                        key=lambda r: -r.score)
        out_groups.append(L4Group(
            l4=l4_label, order=position, candidates=runs, winner=best.metric,
            rationale=_rationale(best, others, len(runs)),
            status="single" if len(runs) == 1 else "decided"))

    return SelectionResult(order=order, groups=out_groups, run_count=run_count)
```

- [ ] **Step 4: Export from the package**

In `backend/app/mmm/__init__.py`, add to the imports and `__all__`:

```python
from app.mmm.selector import SelectionResult, select_indicators
```

Add `"select_indicators"` and `"SelectionResult"` to the module's `__all__` list.

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && .venv/bin/python -m app.mmm._test_selector
```
Expected: `5/5 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/mmm/selector.py backend/app/mmm/_test_selector.py backend/app/mmm/__init__.py
git commit -m "feat(mmm): by-L4 indicator selection sweep"
```

---

### Task 4: Register `model.select_indicator` as a tool

**Files:**
- Modify: `backend/app/tools/registry.py` (wrappers section after `_run_ols` ~line 82; `_ENTRIES` list before the closing `]` ~line 391; `model.ols` doc ~line 355-390)
- Modify: `backend/app/tools/_test_tools.py`

**Interfaces:**
- Consumes: `mmm.selector.select_indicators` (Task 3).
- Produces: tool id `"model.select_indicator"`, callable via `app.tools.get("model.select_indicator").run(...)` with the exact signature of `select_indicators`.

- [ ] **Step 1: Write the failing test**

In `backend/app/tools/_test_tools.py`, add this function before its `main()`:

```python
def test_select_indicator_identity() -> bool:
    """The selector wrapper is an identity wrapper: routing through the
    registry returns exactly what calling the implementation returns."""
    from app.mmm._test_selector import GROUPS, _no_benchmark, _pearson, make_long
    from app.mmm.selector import select_indicators

    df = make_long()
    kwargs = dict(y={}, params=None, exclude=frozenset(),
                  benchmark=_no_benchmark, pearson_of=_pearson)
    direct = select_indicators(df, ["MT"], GROUPS, **kwargs)
    viaTool = get("model.select_indicator").run(df, ["MT"], GROUPS, **kwargs)
    ok = direct.order == viaTool.order
    ok &= direct.run_count == viaTool.run_count
    ok &= [g.winner for g in direct.groups] == [g.winner for g in viaTool.groups]
    ok &= [round(c.score, 12) for g in direct.groups for c in g.candidates] == \
          [round(c.score, 12) for g in viaTool.groups for c in g.candidates]
    return _check("model.select_indicator wrapper == direct call", ok)
```

Then add `test_select_indicator_identity()` to the results list inside `main()`.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m app.tools._test_tools
```
Expected: FAIL — `KeyError`/`ValueError` for unknown tool `model.select_indicator`

- [ ] **Step 3: Add the wrapper**

In `backend/app/tools/registry.py`, immediately after `_run_ols` add:

```python
def _run_select_indicator(df, objects, groups, **kwargs):
    from app.mmm.selector import select_indicators

    return select_indicators(df, objects, groups, **kwargs)
```

- [ ] **Step 4: Register the tool**

In `backend/app/tools/registry.py`, add this entry to `_ENTRIES` immediately after the `model.ols` entry (before the closing `]`). Entries are built with the `_entry(detail, run, module, symbol)` helper, which fills `detail.api` automatically from `usedBy` — do not pass `api` yourself:

```python
    _entry(ToolDetail(
        id="model.select_indicator", name="By-L4 Indicator Selection", category="model",
        description="Elects one indicator per factor (L4) by running a full OLS for each "
                    "candidate and scoring it on its Knowledge band and model fit.",
        inputSummary="Long table + model objects + candidate indicators grouped by L4",
        outputSummary="Per-L4 winner with every candidate's Run: adj. R², coefficient, t, "
                      "VIF, ROI, contribution, band verdict and score",
        wraps="mmm.selector.select_indicators", usedBy=["2.5s"],
        scenario=(
            "Called once at 2.5s, after the response is confirmed at 2.5y and before the "
            "human reviews variables at 2.5x. A factor usually carries several indicators "
            "measuring the same lever — spend, exposure, GRP — which are near-collinear and "
            "must not enter the regression together. This elects one per factor. Every "
            "candidate's Run is recorded as its own invocation, so the sweep is replayable "
            "step by step."),
        method=(
            "Single pass over the factors, strongest first by the 2.4 |Pearson r| of their "
            "best candidate. For each candidate the tool fits a COMPLETE model — every other "
            "factor represented by its current indicator — swapping in only the candidate. "
            "Scoring a candidate in a single-variable regression would be meaningless: the "
            "coefficient there absorbs every collinear factor, so every candidate looks "
            "excellent. Cost is the sum of the candidate counts, not their product."),
        logic=[
            "Order factors by the strongest candidate's |Pearson r| from the 2.4 scorecard.",
            "Start each factor at its strongest candidate; this is a starting point, not a verdict.",
            "For each candidate, fit every model object with that candidate representing its "
            "factor and the other factors at their current representative.",
            "Eliminate on hard constraints: VIF > 10, or a negative coefficient on a paid driver.",
            "Score = 0.6 x Knowledge-band alignment + 0.4 x adj. R² min-max normalised within "
            "the factor; with no band available the score is the fit alone.",
            "Band alignment is 1.0 inside the band and decays linearly to 0 one band-width outside.",
            "ROI is only compared to the Knowledge money bands when the fit produced a "
            "revenue/spend ratio — a volume/spend ratio is not comparable.",
            "A factor whose candidates are all eliminated is reported as not entering the model.",
        ],
        params=[
            ["W_KNOWLEDGE", "0.6", "Weight on Knowledge-band alignment"],
            ["W_STAT", "0.4", "Weight on the normalised adj. R²"],
            ["MAX_VIF_SELECT", "10.0", "VIF above this eliminates a candidate"],
        ],
    ), _run_select_indicator, "app.mmm.selector", "select_indicators"),
```

- [ ] **Step 5: Document the new ROI semantics on `model.ols`**

In `backend/app/tools/registry.py`, in the `model.ols` entry's `logic` list, replace the line:

```python
            "Fit OLS; derive t and p per coefficient, decomposed contribution, and ROI where "
            "the response is revenue-like.",
```

with:

```python
            "Fit OLS; derive t and p per coefficient, decomposed contribution, and ROI.",
            "ROI numerator and denominator are decoupled: the lift comes from the indicator "
            "in the model, the spend from that factor's own Spending series. A factor "
            "represented by an exposure metric therefore still has a real ROI.",
            "Carry-over reaching past the last modelled month is not recovered, so ROI is "
            "marginally conservative on short windows with heavy adstock.",
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m app.tools._test_tools
```
Expected: all checks pass, including `model.select_indicator wrapper == direct call`.

- [ ] **Step 7: Verify the catalog serves the new tool**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -c "
from app.tools import list_specs, get
print([s.id for s in list_specs()])
print(get('model.select_indicator').detail.name)"
```
Expected: the id list contains `model.select_indicator`; the name prints `By-L4 Indicator Selection`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/tools/registry.py backend/app/tools/_test_tools.py
git commit -m "feat(tools): register model.select_indicator and document decoupled ROI"
```

---

### Task 5: Domain models + blueprint task 2.5s

**Files:**
- Modify: `backend/app/domain/models.py` (after `OlsXCandidate` ~line 556; `OlsConfig` ~line 633)
- Modify: `backend/app/domain/blueprint.py` (2.5 block ~line 344-400)
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/scenario.ts`

**Interfaces:**
- Consumes: `selector.CandidateRun` / `L4Group` / `SelectionResult` field names (Task 3).
- Produces: `OlsSelection`, `OlsSelectionGroup`, `OlsSelectionRun` Pydantic models; `OlsConfig.selection: OlsSelection | None`; `OlsXCandidate.l4_group` / `selection_score` / `selection_rationale`; blueprint task `2.5s`.

- [ ] **Step 1: Add the Pydantic models**

In `backend/app/domain/models.py`, insert immediately after the `OlsXCandidate` class:

```python
class OlsSelectionRun(CamelModel):
    """One candidate's complete OLS Run during the 2.5s By-L4 sweep."""
    l4: str = ""
    indicator: str = ""
    adj_r2: float = Field(default=0.0, alias="adjR2")
    coef: float = 0.0
    t_value: float = Field(default=0.0, alias="tValue")
    vif: float = 1.0
    roi: Optional[float] = None
    roi_unit: str = Field(default="", alias="roiUnit")
    roi_denominator_source: str = Field(default="", alias="roiDenominatorSource")
    contribution: Optional[float] = None
    roi_status: str = Field(default="none", alias="roiStatus")
    contribution_status: str = Field(default="none", alias="contributionStatus")
    score: float = 0.0
    score_knowledge: float = Field(default=0.0, alias="scoreKnowledge")
    score_stat: float = Field(default=0.0, alias="scoreStat")
    eliminated: bool = False
    eliminated_reason: str = Field(default="", alias="eliminatedReason")


class OlsSelectionGroup(CamelModel):
    """One factor (L4): every candidate's Run, and the elected representative."""
    l4: str = ""
    order: int = 0
    candidates: list[OlsSelectionRun] = Field(default_factory=list)
    winner: str = ""
    rationale: str = ""
    status: str = "decided"     # "decided" | "single" | "noViable"


class OlsSelection(CamelModel):
    """The 2.5s sweep result — the audit trail behind the pre-ticked variables."""
    order: list[str] = Field(default_factory=list)
    groups: list[OlsSelectionGroup] = Field(default_factory=list)
    run_count: int = Field(default=0, alias="runCount")
    swept_at: str = Field(default="", alias="sweptAt")
```

- [ ] **Step 2: Extend `OlsXCandidate` and `OlsConfig`**

In `backend/app/domain/models.py`, add to `OlsXCandidate` after the `rationale: str = ""` line:

```python
    # 2.5s sweep provenance — how this candidate fared in its factor's contest.
    l4_group: str = Field(default="", alias="l4Group")
    selection_score: Optional[float] = Field(default=None, alias="selectionScore")
    selection_rationale: str = Field(default="", alias="selectionRationale")
```

And to `OlsConfig` after `proposed_at`:

```python
    selection: Optional[OlsSelection] = None
```

- [ ] **Step 3: Add task 2.5s to the blueprint**

In `backend/app/domain/blueprint.py`, insert this task between the `2.5y` task and the `2.5x` task:

```python
    {"id": "2.5s", "name": "Select indicators per factor", "agent": "data", "stage": "s2", "klass": "M",
     "summary": "Run one OLS per candidate indicator, factor by factor, and elect the one indicator that represents each factor in the model.",
     "how": "A factor usually carries several indicators measuring the same lever — spend, exposure, reach — which are near-collinear and cannot enter the regression together. Each candidate is fitted inside a complete model with the other factors held at their current indicator, then scored on its Knowledge ROI / contribution band and the model fit. You see every Run and can override the result in the next step.",
     "basis_note": "行业经验 ROI / 贡献区间（知识库维护）+ 2.4 统计得分。", "work_note": "Indicators elected per factor.",
     "depends_on": ["2.5y"], "duration": 2, "produces": ["a-ols-test"]},
```

Then change the `2.5x` task's `"depends_on": ["2.5y"]` to `"depends_on": ["2.5s"]`.

- [ ] **Step 4: Mirror in the frontend scenario**

In `frontend/src/lib/scenario.ts`, find the `2.5y` task object and add the matching `2.5s` entry after it, using the same field names the neighbouring tasks use (`id`, `name`, `agent`, `stage`, `klass`, `summary`, `how`, `dependsOn`, `duration`, `produces`), with:

```ts
  {
    id: '2.5s',
    name: 'Select indicators per factor',
    agent: 'data',
    stage: 's2',
    klass: 'M',
    summary: 'Run one OLS per candidate indicator, factor by factor, and elect the one indicator that represents each factor in the model.',
    how: 'A factor usually carries several indicators measuring the same lever — spend, exposure, reach — which are near-collinear and cannot enter the regression together. Each candidate is fitted inside a complete model with the other factors held at their current indicator, then scored on its Knowledge ROI / contribution band and the model fit. You see every Run and can override the result in the next step.',
    dependsOn: ['2.5y'],
    duration: 2,
    produces: ['a-ols-test'],
  },
```

and change the `2.5x` entry's `dependsOn` from `['2.5y']` to `['2.5s']`.

- [ ] **Step 5: Mirror the types**

In `frontend/src/lib/types.ts`, add next to `OlsXCandidate`:

```ts
export interface OlsSelectionRun {
  l4: string
  indicator: string
  adjR2: number
  coef: number
  tValue: number
  vif: number
  roi: number | null
  roiUnit: string
  roiDenominatorSource: string
  contribution: number | null
  roiStatus: 'in' | 'out' | 'none'
  contributionStatus: 'in' | 'out' | 'none'
  score: number
  scoreKnowledge: number
  scoreStat: number
  eliminated: boolean
  eliminatedReason: string
}

export interface OlsSelectionGroup {
  l4: string
  order: number
  candidates: OlsSelectionRun[]
  winner: string
  rationale: string
  status: 'decided' | 'single' | 'noViable'
}

export interface OlsSelection {
  order: string[]
  groups: OlsSelectionGroup[]
  runCount: number
  sweptAt: string
}
```

Add to the existing `OlsXCandidate` interface:

```ts
  l4Group?: string
  selectionScore?: number | null
  selectionRationale?: string
```

Add to the existing `OlsConfig` interface:

```ts
  selection?: OlsSelection | null
```

- [ ] **Step 6: Verify both sides compile**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -c "
from app.domain.models import OlsSelection, OlsConfig
s = OlsSelection(order=['TV'], runCount=3)
print(OlsConfig(selection=s).model_dump(by_alias=True)['selection'])"
```
Expected: a dict containing `'runCount': 3` (camelCase confirms the alias).

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/domain/models.py backend/app/domain/blueprint.py frontend/src/lib/types.ts frontend/src/lib/scenario.ts
git commit -m "feat(domain): OlsSelection models and blueprint task 2.5s"
```

---

### Task 6: The 2.5s handler + pre-ticking winners

**Files:**
- Modify: `backend/app/agents/data.py` (after `propose_ols_setup` ~line 763-795)
- Modify: `backend/app/agents/ols_review.py` (`build_ols_proposal` ~line 131-220; add `apply_selection`)
- Modify: `backend/app/agents/registry.py` (~line 29)

**Interfaces:**
- Consumes: `select_indicators` via `app.tools.get("model.select_indicator")`; `OlsSelection*` models (Task 5); `data_rules.build_range_index`; existing `_stat_index`, `_LAYER_PAIRS`, `_matches` in `ols_review.py`.
- Produces:
  - `ols_review.candidate_groups(st, cfg) -> dict[str, list[dict]]`
  - `ols_review.run_selection(st, cfg, *, eng=None, task_id=None) -> OlsSelection`
  - `ols_review.apply_selection(cfg, selection) -> None` (mutates `cfg.x_candidates` ticks in place)
  - `data.select_indicators_step(eng, st, task)` registered at `2.5s`

- [ ] **Step 1: Write the failing test**

Create `backend/app/agents/_test_selection_step.py`:

```python
"""2.5s wiring: the sweep ticks exactly one candidate per factor.

Run: PYTHONPATH=. .venv/bin/python -m app.agents._test_selection_step
"""
from __future__ import annotations

from app.agents.ols_review import apply_selection
from app.domain.models import (
    OlsConfig, OlsSelection, OlsSelectionGroup, OlsSelectionRun, OlsXCandidate,
)


def _check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return bool(cond)


def test_apply_selection_ticks_one_per_l4() -> bool:
    cfg = OlsConfig(xCandidates=[
        OlsXCandidate(key="tv|tv花费", l4="TV", indicator="TV花费", metric="TV花费", selected=True),
        OlsXCandidate(key="tv|tv曝光量", l4="TV", indicator="TV曝光量", metric="TV曝光量", selected=True),
        OlsXCandidate(key="price|平均售价", l4="Price", indicator="平均售价", metric="平均售价", selected=False),
    ])
    sel = OlsSelection(groups=[
        OlsSelectionGroup(l4="TV", winner="TV曝光量", status="decided", rationale="r1",
                          candidates=[
                              OlsSelectionRun(l4="TV", indicator="TV花费", score=0.4),
                              OlsSelectionRun(l4="TV", indicator="TV曝光量", score=0.9)]),
        OlsSelectionGroup(l4="Price", winner="平均售价", status="single", rationale="r2",
                          candidates=[OlsSelectionRun(l4="Price", indicator="平均售价", score=1.0)]),
    ])
    apply_selection(cfg, sel)
    got = {c.metric: c.selected for c in cfg.x_candidates}
    ok = got == {"TV花费": False, "TV曝光量": True, "平均售价": True}
    ok &= all(c.l4_group for c in cfg.x_candidates)
    ok &= cfg.x_candidates[1].selection_score == 0.9
    return _check("apply_selection ticks exactly the winners", ok, f"{got}")


def test_locked_candidate_is_never_revived() -> bool:
    cfg = OlsConfig(xCandidates=[
        OlsXCandidate(key="tv|tv花费", l4="TV", indicator="TV花费", metric="TV花费",
                      selected=False, locked=True, lockedBy="quality"),
    ])
    sel = OlsSelection(groups=[
        OlsSelectionGroup(l4="TV", winner="TV花费", status="single",
                          candidates=[OlsSelectionRun(l4="TV", indicator="TV花费", score=1.0)])])
    apply_selection(cfg, sel)
    ok = cfg.x_candidates[0].selected is False
    return _check("a locked candidate is never ticked by the sweep", ok)


def test_noviable_group_ticks_nothing() -> bool:
    cfg = OlsConfig(xCandidates=[
        OlsXCandidate(key="tv|tv花费", l4="TV", indicator="TV花费", metric="TV花费", selected=True),
    ])
    sel = OlsSelection(groups=[
        OlsSelectionGroup(l4="TV", winner="", status="noViable",
                          candidates=[OlsSelectionRun(l4="TV", indicator="TV花费",
                                                      eliminated=True,
                                                      eliminatedReason="VIF 22.0 > 10")])])
    apply_selection(cfg, sel)
    ok = cfg.x_candidates[0].selected is False
    return _check("a noViable factor leaves nothing ticked", ok)


def main() -> int:
    results = [
        test_apply_selection_ticks_one_per_l4(),
        test_locked_candidate_is_never_revived(),
        test_noviable_group_ticks_nothing(),
    ]
    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_selection_step
```
Expected: FAIL — `ImportError: cannot import name 'apply_selection'`

- [ ] **Step 3: Add `candidate_groups`, `run_selection`, `apply_selection`**

In `backend/app/agents/ols_review.py`, add these three functions immediately after `build_ols_proposal`:

```python
def candidate_groups(st: ProjectState, cfg: OlsConfig) -> dict[str, list[dict]]:
    """Group the un-locked X candidates by factor (norm L4) for the 2.5s sweep.

    Locked candidates are excluded outright: an earlier layer already rejected
    them, and a sweep that could elect one would silently overturn that verdict.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in cfg.x_candidates:
        if c.locked:
            continue
        l4n = _norm(c.l4)
        if not l4n:
            continue
        groups[l4n].append({"l4": c.l4, "metric": c.metric, "is_spend": c.is_spend})
    return dict(groups)


def run_selection(st: ProjectState, cfg: OlsConfig, *, eng=None,
                  task_id: str | None = None) -> OlsSelection:
    """2.5s — sweep every factor, recording one tool invocation per Run.

    Granularity is deliberately one invocation per candidate Run (not per run of
    the step): the per-Run trace is what lets the UI replay the contest factor by
    factor, and what makes the elected indicator auditable.
    """
    from app.mmm.selector import select_indicators as _select

    df = model_df(st)
    objects = model_objects(st)
    groups = candidate_groups(st, cfg)
    idx = build_range_index(
        getattr(getattr(st, "meta", None), "industry_l1", None) or None,
        getattr(getattr(st, "meta", None), "industry_l2", None) or None,
    )
    stats = _stat_index(st)

    def _pearson_of(l4: str, metric: str) -> float:
        row = stats.get(_norm_pair(l4, metric))
        return abs(float(getattr(row, "pearson", 0.0) or 0.0))

    def _emit(run) -> None:
        if eng is None or not task_id:
            return
        with tool_run(eng, st, task_id, "model.select_indicator",
                      f"{run.l4} · {run.indicator}") as h:
            h.result(
                f"adjR²={run.adj_r2:.3f} · score={run.score:.3f}"
                + (f" · eliminated: {run.eliminated_reason}" if run.eliminated else ""))

    result = _select(
        df, objects, groups,
        y={c.object: c.metric for c in cfg.y if c.metric},
        params=cfg.params, exclude=model_selection(st).exclude,
        benchmark=idx.match, pearson_of=_pearson_of, on_run=_emit,
    )
    return OlsSelection(
        order=list(result.order),
        runCount=int(result.run_count),
        sweptAt=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        groups=[OlsSelectionGroup(
            l4=g.l4, order=g.order, winner=g.winner, rationale=g.rationale,
            status=g.status,
            candidates=[OlsSelectionRun(
                l4=c.l4, indicator=c.indicator, adjR2=_num(c.adj_r2) or 0.0,
                coef=_num(c.coef) or 0.0, tValue=_num(c.t_value) or 0.0,
                vif=_num(c.vif) or 0.0, roi=_num(c.roi), roiUnit=c.roi_unit,
                roiDenominatorSource=c.roi_denominator_source,
                contribution=_num(c.contribution, 2),
                roiStatus=c.roi_status, contributionStatus=c.contribution_status,
                score=round(float(c.score), 4),
                scoreKnowledge=round(float(c.score_knowledge), 4),
                scoreStat=round(float(c.score_stat), 4),
                eliminated=c.eliminated, eliminatedReason=c.eliminated_reason,
            ) for c in g.candidates],
        ) for g in result.groups],
    )


def apply_selection(cfg: OlsConfig, selection: OlsSelection) -> None:
    """Tick exactly the elected indicator in each factor; untick its rivals.

    Locked candidates are never ticked — the sweep excludes them, and this is
    the second guard so a hand-edited selection cannot revive one either.
    """
    winners = {(_norm(g.l4), _norm(g.winner)) for g in selection.groups if g.winner}
    swept = {_norm(g.l4) for g in selection.groups}
    scores = {(_norm(c.l4), _norm(c.indicator)): c
              for g in selection.groups for c in g.candidates}
    rationales = {_norm(g.l4): g.rationale for g in selection.groups}
    for c in cfg.x_candidates:
        l4n = _norm(c.l4)
        c.l4_group = c.l4 or l4n
        run = scores.get((l4n, _norm(c.metric)))
        if run is not None:
            c.selection_score = run.score
        if l4n not in swept:
            continue
        c.selection_rationale = rationales.get(l4n, "")
        c.selected = (not c.locked) and ((l4n, _norm(c.metric)) in winners)
```

Add the needed imports at the top of `backend/app/agents/ols_review.py`:

```python
from datetime import datetime, timezone
```

and extend the existing `from app.domain.models import (...)` block with `OlsSelection`, `OlsSelectionGroup`, `OlsSelectionRun`; extend the existing `from app.agents.ledger import (...)` block with `model_selection`; and add:

```python
from app.tools.tracing import tool_run
```

(`traced` is already imported; `tool_run` is the context-manager form used here because the tool result is produced by the callback, not the call.)

- [ ] **Step 4: Add the 2.5s handler**

In `backend/app/agents/data.py`, add immediately after `propose_ols_setup`:

```python
async def select_indicators_step(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.5s — elect one indicator per factor by running a full OLS per candidate.

    A factor (L4) usually carries several indicators measuring the same lever;
    they are near-collinear, so exactly one must represent the factor. Each
    candidate is fitted inside a complete model — the other factors held at
    their current indicator — and scored on its Knowledge ROI / contribution
    band and the model fit. Every Run is recorded as its own tool invocation so
    the contest can be replayed. The human overrides at 2.5x.
    """
    cfg = st.ols_config
    if cfg is None:
        cfg = build_ols_proposal(st)
        st.ols_config = cfg
    selection = run_selection(st, cfg, eng=eng, task_id=task["id"])
    cfg.selection = selection
    apply_selection(cfg, selection)
    st.ols_config = cfg

    body, _, _ = build_ols_review(st, fit=False)
    eng.produce(st, "a-ols-test", body=body, state="proposed", agent="data")

    decided = [g for g in selection.groups if g.winner]
    noviable = [g for g in selection.groups if not g.winner]
    contested = [g for g in selection.groups if len(g.candidates) > 1]
    findings = [TaskFinding(
        text=f"Swept {len(selection.groups)} factor(s) with {selection.run_count} OLS run(s): "
             f"{len(decided)} factor(s) elected an indicator "
             f"({len(contested)} had more than one candidate competing). "
             f"Review the elected variables in the next step.",
        evidence=[EvidenceRef(artifactId="a-ols-test")])]
    if noviable:
        findings.append(TaskFinding(
            text=f"{len(noviable)} factor(s) had no viable candidate and do not enter the "
                 f"model: {', '.join(g.l4 for g in noviable[:5])}. Each candidate failed the "
                 f"sign or collinearity constraint — see the runs on the deliverable.",
            tone="flag", evidence=[EvidenceRef(artifactId="a-ols-test")]))
    eng.add_findings(st, task["id"], findings)
```

Add `run_selection` and `apply_selection` to the existing `from app.agents.ols_review import (...)` block in `backend/app/agents/data.py`.

- [ ] **Step 5: Register the handler**

In `backend/app/agents/registry.py`, add after the `2.5` registration line:

```python
    eng.register("2.5s", data.select_indicators_step)  # By-L4 indicator election
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_selection_step
```
Expected: `3/3 passed`

- [ ] **Step 7: Verify the blueprint heals onto the saved project**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -c "
from app.store.state import get_store
st = get_store().get('danone-mizone')
print([t.id for t in st.tasks if t.id.startswith('2.5')])"
```
Expected: the list includes `2.5s`. If it does not, `heal_state` did not back-fill — check that the task was added to `TASKS` in `blueprint.py` and re-run.

- [ ] **Step 8: Commit**

```bash
git add backend/app/agents/ols_review.py backend/app/agents/data.py backend/app/agents/registry.py backend/app/agents/_test_selection_step.py
git commit -m "feat(agents): 2.5s by-L4 selection step with per-run tool tracing"
```

---

### Task 7: 2.5r reads the L4 rollup and drops the self-validation claim

The Knowledge band is now a *selection* criterion at 2.5s. It cannot also be presented as independent *validation* at 2.5r. This task changes what 2.5r claims and where its numbers come from.

**Files:**
- Modify: `backend/app/agents/ols_review.py` (`_collect_records` ~line 242-338; `_classify` ~line 387-398)

**Interfaces:**
- Consumes: `MmmModelResult.l4_rollup`, `meta["roi_denominator_source"]` (Task 2); `OlsConfig.selection` (Task 5).
- Produces: per-indicator record key `roiDenominatorSource`; row field `sweptAt2_5s: bool`; `_classify` status `"relativeBest"`.

- [ ] **Step 1: Take ROI from the rollup**

In `backend/app/agents/ols_review.py`, inside `_collect_records`'s per-driver loop, replace:

```python
            roi = res.roi.get(d)  # only spend cols → else absent
```

with:

```python
            # ROI now comes from the factor-level rollup: the numerator is this
            # driver's lift, the denominator its factor's own spend — so a factor
            # represented by an exposure metric still carries a real ROI.
            roi = res.roi.get(d)
            rec_src = (res.meta.get("roi_denominator_source") or {}).get(d, "none")
```

and immediately after the existing `rec["objects"].append(obj)` line add:

```python
            rec["roi_denominator_source"] = rec_src
```

Also add `"roi_denominator_source": "none",` to the `rec = {...}` initialiser dict (next to `"roi_money": True`).

- [ ] **Step 2: Surface the denominator source on the row**

In `_row_from_record`, add to the returned dict (next to `"rangeSource"`):

```python
        "roiDenominatorSource": rec.get("roi_denominator_source", "none"),
```

- [ ] **Step 3: Change what 2.5r claims for swept indicators**

Replace `_classify` in `backend/app/agents/ols_review.py` with:

```python
def _classify(row: dict, dropped_by: str, in_model: bool, bench: RangeBenchmark | None,
              swept: bool = False) -> tuple[str, str]:
    """Return (status, flagReason). Precedence: dropped → notInModel → noBenchmark
    → review (ROI or Contribution out) → relativeBest / inRange.

    ``swept`` marks an indicator that 2.5s elected using these same Knowledge
    bands. For those, landing in the band is NOT independent validation — the
    band chose it. It is reported as the best of its factor's candidates
    instead, and the losing runs sit next to it on the deliverable.
    """
    if dropped_by:
        return "dropped", ""
    if not in_model:
        return "notInModel", ""
    if not _has_benchmark(bench):
        return "noBenchmark", ""
    if row["roiStatus"] == "out" or row["contributionStatus"] == "out":
        return "review", _flag_reason(row)
    return ("relativeBest" if swept else "inRange"), ""
```

- [ ] **Step 4: Pass `swept` at the call site**

In `build_ols_review`, before the loop that calls `_classify`, add:

```python
    # Indicators the 2.5s sweep elected using these same Knowledge bands.
    sel = getattr(getattr(st, "ols_config", None), "selection", None)
    swept_pairs = {
        _norm_pair(g.l4, g.winner) for g in (getattr(sel, "groups", None) or []) if g.winner
    }
```

and change each `_classify(...)` call to pass the extra argument, e.g.:

```python
        status, flag_reason = _classify(row, dropped_by, in_model, bench,
                                        _norm_pair(rec["l4"], rec["metric"]) in swept_pairs)
```

Apply the same change to the second `_classify` call site (the factor-map branch), using that branch's own `(l4, metric)` pair.

- [ ] **Step 5: Verify the review still builds on the real project**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -c "
from app.store.state import get_store
from app.agents.ols_review import build_ols_review
st = get_store().get('danone-mizone')
body, prefit, flagged = build_ols_review(st, fit=True)
print('summary:', body.get('summary'))
print('statuses:', sorted({r.get('status') for r in body.get('tree', [])}))
print('roi denominators:', sorted({r.get('roiDenominatorSource') for r in body.get('tree', [])}))"
```
Expected: a summary dict prints, statuses are drawn from the known set, and denominator sources are among `self` / `l4_spend:...` / `none`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/ols_review.py
git commit -m "feat(agents): 2.5r reads L4 rollup ROI and reports swept indicators as relative-best"
```

---

### Task 8: Frontend — sweep replay + L4-grouped variable review

The fits are sub-millisecond, so the backend computes everything at once. The progressive experience is a **replay of real, already-stored data** — never an artificial delay, and refreshing the page must not lose the result.

**Files:**
- Create: `frontend/src/components/project/ols/SelectionReplay.tsx`
- Modify: `frontend/src/components/project/ols/OlsStepPanel.tsx`

**Interfaces:**
- Consumes: `OlsSelection`, `OlsSelectionGroup`, `OlsSelectionRun`, `OlsXCandidate.l4Group` / `selectionScore` / `selectionRationale` (Task 5).
- Produces: `<SelectionReplay selection={...} />` default-exported React component.

- [ ] **Step 1: Write the replay component**

Create `frontend/src/components/project/ols/SelectionReplay.tsx`:

```tsx
import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronRight, SkipForward, X } from 'lucide-react'
import { cn } from '../../../lib/cn'
import { Button } from '../../ui/button'
import type { OlsSelection, OlsSelectionRun } from '../../../lib/types'

/**
 * Replay of the 2.5s By-L4 sweep.
 *
 * Every number here was computed server-side and is already in the store —
 * this only paces the reveal so the contest reads factor by factor. There is
 * no artificial work: "Skip to result" jumps straight to the full state, and
 * a page refresh lands on the finished view rather than restarting.
 */
const STEP_MS = 420

function statusTone(status: string): string {
  if (status === 'in') return 'text-emerald-600 dark:text-emerald-400'
  if (status === 'out') return 'text-amber-600 dark:text-amber-400'
  return 'text-muted-foreground'
}

function RunRow({ run, isWinner }: { run: OlsSelectionRun; isWinner: boolean }) {
  return (
    <li
      className={cn(
        'flex items-baseline gap-3 rounded-md border px-2.5 py-1.5 text-[11.5px]',
        isWinner
          ? 'border-emerald-500/40 bg-emerald-500/5'
          : run.eliminated
            ? 'border-border bg-muted/30 opacity-70'
            : 'border-border',
      )}
    >
      <span className="flex w-4 shrink-0 justify-center">
        {isWinner ? <Check className="size-3.5 text-emerald-600" aria-hidden />
          : run.eliminated ? <X className="size-3.5 text-muted-foreground" aria-hidden />
            : null}
      </span>
      <span className="min-w-0 flex-1 truncate font-medium">{run.indicator}</span>
      {run.eliminated ? (
        <span className="text-muted-foreground">{run.eliminatedReason}</span>
      ) : (
        <>
          <span className="tabular-nums text-muted-foreground">
            adj. R² {run.adjR2.toFixed(3)}
          </span>
          {run.contribution != null && (
            <span className={cn('tabular-nums', statusTone(run.contributionStatus))}>
              contrib {run.contribution.toFixed(1)}%
            </span>
          )}
          {run.roi != null && (
            <span className={cn('tabular-nums', statusTone(run.roiStatus))}>
              ROI {run.roi.toFixed(2)}
            </span>
          )}
          <span className="tabular-nums font-semibold">{run.score.toFixed(3)}</span>
        </>
      )}
    </li>
  )
}

export default function SelectionReplay({ selection }: { selection: OlsSelection }) {
  const groups = selection.groups
  const [revealed, setRevealed] = useState(0)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    if (revealed >= groups.length) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) {
      setRevealed(groups.length)
      return
    }
    timer.current = window.setTimeout(() => setRevealed((n) => n + 1), STEP_MS)
    return () => window.clearTimeout(timer.current)
  }, [revealed, groups.length])

  const elected = useMemo(
    () => groups.filter((g) => g.winner).length,
    [groups],
  )
  const done = revealed >= groups.length

  return (
    <section className="mt-3 rounded-lg border border-border bg-card p-3">
      <header className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="text-[12.5px] font-semibold">Indicator selection by factor</h4>
          <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
            {selection.runCount} regression run{selection.runCount === 1 ? '' : 's'} across{' '}
            {groups.length} factor{groups.length === 1 ? '' : 's'} — {elected} elected an
            indicator. Each run is a complete model with only this factor&rsquo;s indicator
            swapped.
          </p>
        </div>
        {!done && (
          <Button size="sm" variant="ghost" className="shrink-0"
                  onClick={() => setRevealed(groups.length)}>
            <SkipForward /> Skip to result
          </Button>
        )}
      </header>

      <ol className="space-y-2">
        {groups.slice(0, Math.max(revealed, 1)).map((g, i) => {
          const isLatest = i === revealed - 1 && !done
          return (
            <li key={`${g.l4}-${g.order}`}
                className={cn('rounded-md border border-border p-2',
                              isLatest && 'ring-1 ring-primary/40')}>
              <div className="flex items-baseline gap-2">
                <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                <span className="text-[12px] font-semibold">{g.l4}</span>
                <span className="text-[11px] text-muted-foreground">
                  {g.candidates.length} candidate{g.candidates.length === 1 ? '' : 's'}
                </span>
                <span className="ml-auto text-[11px]">
                  {g.winner
                    ? <span className="font-medium text-emerald-600 dark:text-emerald-400">
                        {g.winner}
                      </span>
                    : <span className="text-amber-600 dark:text-amber-400">
                        not in model
                      </span>}
                </span>
              </div>
              <ul className="mt-1.5 space-y-1">
                {g.candidates.map((c) => (
                  <RunRow key={c.indicator} run={c} isWinner={c.indicator === g.winner} />
                ))}
              </ul>
              {g.rationale && (
                <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">
                  {g.rationale}
                </p>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
```

- [ ] **Step 2: Group the 2.5x variable list by factor**

In `frontend/src/components/project/ols/OlsStepPanel.tsx`, inside the `ols-x` panel's rendering, replace the flat `.map` over `draft.xCandidates` with a grouped render. Insert this helper above the panel component:

```tsx
function byFactor(cands: OlsXCandidate[]): [string, OlsXCandidate[]][] {
  const out = new Map<string, OlsXCandidate[]>()
  for (const c of cands) {
    const key = c.l4Group || c.l4 || '—'
    const bucket = out.get(key)
    if (bucket) bucket.push(c)
    else out.set(key, [c])
  }
  return [...out.entries()]
}
```

and render each group with a header showing the factor name and its elected indicator:

```tsx
{byFactor(draft.xCandidates).map(([factor, cands]) => (
  <div key={factor} className="mt-2 rounded-md border border-border p-2">
    <div className="mb-1 flex items-baseline gap-2">
      <span className="text-[12px] font-semibold">{factor}</span>
      <span className="text-[11px] text-muted-foreground">
        {cands.filter((c) => c.selected).length} of {cands.length} selected
      </span>
    </div>
    {cands[0]?.selectionRationale && (
      <p className="mb-1 text-[11px] leading-snug text-muted-foreground">
        {cands[0].selectionRationale}
      </p>
    )}
    {cands.map((c) => renderCandidateRow(c))}
  </div>
))}
```

where `renderCandidateRow` is the existing per-candidate JSX extracted verbatim into a local function — do not change its markup or handlers.

- [ ] **Step 3: Render the replay in the ols-x panel**

In `frontend/src/components/project/ols/OlsStepPanel.tsx`, add the import:

```tsx
import SelectionReplay from './SelectionReplay'
```

and render it above the grouped list inside the `ols-x` panel body:

```tsx
{draft.selection && draft.selection.groups.length > 0 && (
  <SelectionReplay selection={draft.selection} />
)}
```

- [ ] **Step 4: Verify the build and lint pass**

```bash
cd frontend && npm run build && npm run lint
```
Expected: build succeeds; lint reports no new errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/project/ols/SelectionReplay.tsx frontend/src/components/project/ols/OlsStepPanel.tsx
git commit -m "feat(ui): by-L4 selection replay and factor-grouped variable review"
```

---

### Task 9: Smoke test and end-to-end verification

**Files:**
- Modify: `backend/tests/test_api_smoke.py`

**Interfaces:**
- Consumes: everything from Tasks 1-8.
- Produces: no new interfaces — this task proves the pipeline runs.

- [ ] **Step 1: Add 2.5s to the smoke path**

In `backend/tests/test_api_smoke.py`, find the assertion listing the expected S2 task ids and add `"2.5s"` in its position between `"2.5y"` and `"2.5x"`. If the file asserts on a task count, increment it by one. Add this check after the run completes:

```python
    cfg = st.ols_config
    assert cfg is not None, "2.5 did not produce an ols_config"
    sel = cfg.selection
    assert sel is not None, "2.5s did not produce a selection"
    assert sel.run_count >= len(sel.groups), "fewer runs than factors swept"
    for g in sel.groups:
        picked = [c for c in cfg.x_candidates
                  if (c.l4 or "").strip().lower() == g.l4.strip().lower() and c.selected]
        assert len(picked) <= 1, f"factor {g.l4} has {len(picked)} selected indicators"
    print(f"[PASS] 2.5s elected <=1 indicator per factor across {len(sel.groups)} factors")
```

- [ ] **Step 2: Run the smoke test**

```bash
cd backend && PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py
```
Expected: the existing smoke output plus the new `[PASS] 2.5s elected <=1 indicator per factor…` line.

- [ ] **Step 3: Run every backend suite**

```bash
cd backend && \
  .venv/bin/python -m app.mmm._test_synthetic && \
  .venv/bin/python -m app.mmm._test_real && \
  .venv/bin/python -m app.mmm._test_l4_roi && \
  .venv/bin/python -m app.mmm._test_selector && \
  PYTHONPATH=. .venv/bin/python -m app.agents._test_selection_step && \
  PYTHONPATH=. .venv/bin/python -m app.tools._test_tools && \
  PYTHONPATH=. .venv/bin/python -m app.dataeng._test_preview
```
Expected: every suite prints an all-pass summary.

- [ ] **Step 4: Drive the real case end to end**

Start the backend, then:

```bash
P=danone-mizone
curl -XPOST localhost:8000/api/projects/$P/reset
curl -XPOST localhost:8000/api/projects/$P/run -H 'content-type: application/json' -d '{"autopilot":true}'
# poll until complete
curl localhost:8000/api/projects/$P/run/status
curl "localhost:8000/api/projects/$P/tool-invocations?toolId=model.select_indicator" | head -c 600
```
Expected: the run completes; the invocation list contains one entry per candidate Run with an `argsSummary` of the form `"<L4> · <indicator>"` and a real `durationMs`.

- [ ] **Step 5: Walk the UI**

```bash
cd frontend && npm run dev
# in another shell:
node scripts/visual-check.mjs
```
Expected: the Playwright walk-through completes. Manually confirm on the 2.5x step that the sweep replay renders, factors are grouped, and exactly one indicator is ticked per factor.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_api_smoke.py
git commit -m "test: cover 2.5s selection in the API smoke test"
```

---

## Self-Review Notes

**Spec coverage:** §2.2 sweep → Task 3; §2.3 ROI decoupling → Tasks 1-2; §2.4 L4 rollup → Task 2; §3.1 blueprint → Task 5; §3.2 selector module → Task 3; §3.3 tool registration → Task 4; §3.4 domain models → Task 5; §3.5 frontend → Task 8; §3.6 self-validation loop → Task 7. §2.2's optional `verify_pass` is deliberately **not** implemented — it is spec'd as default-off and adds a second full sweep for no current user-visible behaviour (YAGNI); add it only if path dependence is observed in practice.

**Type consistency:** `select_indicators` returns `SelectionResult` with `order` / `groups` / `run_count`; `run_selection` maps it to the `OlsSelection` Pydantic model with `order` / `groups` / `runCount` / `sweptAt`. `CandidateRun.adj_r2` ↔ `OlsSelectionRun.adjR2` ↔ TS `adjR2`. `_roi` returns a 3-tuple everywhere it is called (single call site, in `run_mmm`).
