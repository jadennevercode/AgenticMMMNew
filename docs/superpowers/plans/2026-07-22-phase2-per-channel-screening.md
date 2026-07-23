# Phase 2 — Per-Channel-Type Screening (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the S2 indicator-screening chain (data quality, statistical, sign-off, X selection, ROI/contribution range) run **independently per Channel Type**, so an indicator can survive in MT and be rejected in TT, and that difference flows through to the master-data assembly.

**Architecture:** The S2 ledger — the single derived truth about each indicator's fate — is re-keyed from `(l4, metric)` to `(object, l4, metric)`, where `object` is the existing model object (channel_type). The **mapping** layer (2.1) stays global; layers 2–6 (quality → range) become per-object. `ModelSelection.include/exclude` change from one flat set to a per-object dict (mirroring the already-per-object `y`). Every consumer already loops over `model_objects(st)`, so consumers switch from `sel.exclude` to `sel.exclude_for(obj)`. This plan is **backend only**; the frontend Channel Type selector + canvas live in the Phase 1 plan.

**Tech Stack:** Python 3, FastAPI, Pydantic (CamelModel), pandas/numpy, no pytest harness (runnable `_test_*.py` modules invoked with `PYTHONPATH=. .venv/bin/python -m <module>`).

## Global Constraints

- **English-only product strings.** All new user-facing text (notes, reasons, rationales) is English; data values (Chinese factor names) render verbatim. (`product-english-only`)
- **Numbers come from `app/mmm`, never the LLM.** This plan touches only screening/keying, not the arithmetic. Tool wrappers stay identity wrappers — `app/tools/_test_tools.py` must still pass unchanged. (`tools-registry-module`)
- **Four contracts stay in sync when a domain field changes:** `domain/models.py` ↔ `frontend/src/lib/types.ts`; `blueprint.py` ↔ `scenario.ts`. This phase changes `models.py` types → `types.ts` must be updated in the same task (Task 3, Task 9).
- **`ProjectState` fields carry no alias** — adding a field to it must not use `Field(alias=...)` or `/state` silently drops it. (`projectstate-serializes-snake-case`)
- **`model_selection(st)` is the ONE resolved selection every fit uses.** 2.5r, 2.6 and 3.2 must all read it; never re-derive a selection at a call site. (`indicator-lifecycle-ledger`)
- Object identity is `channel_type` (the `dataset_cache.model_objects` string). Do **not** split to the finer `channel` column.
- Run tests with `PYTHONPATH=. .venv/bin/python -m <module>` from `backend/`.

---

## File Structure

- `backend/app/agents/ledger.py` — key space widened to `(object, l4, metric)`; per-object drop resolvers, `drops_before(st, layer, object)`, per-object `ModelSelection`, per-object `indicator_ledger`/`funnel`. (heaviest change)
- `backend/app/agents/_test_per_channel.py` — **new** shared fixture + all Phase 2 unit tests.
- `backend/app/domain/models.py` — `object` field on `QualityRow`, `StatScoreRow`, `OlsXCandidate`; `LayerVerdict`/ledger stays dataclass (not serialized directly).
- `backend/app/agents/quality_scoring.py` + `backend/app/agents/data.py::score_data` — quality scorecard built per object.
- `backend/app/agents/stat_scoring.py` — stat scorecard built per object.
- `backend/app/agents/ols_review.py` — per-object X candidates, per-object records (no cross-object averaging), per-object `selected_x_metrics`.
- `backend/app/agents/master_data.py` — `adopted_mask` per object.
- `backend/app/agents/model.py::train_models` — per-object include/exclude.
- `backend/app/agents/data.py::assemble_master_data` — per-object payload serialization.
- `backend/app/main.py::put_signoff` — object-aware sign-off keys (default-all).
- `backend/app/store/state.py::heal_state` — expand legacy global records to per-object.
- `backend/app/agents/dataset_cache.py::model_objects` — data-derived ordering (removes the hardcoded preferred list; the small dynamic-ordering slice of Phase 3 folded in here since this plan re-touches the function).
- `frontend/src/lib/types.ts` — mirror the three `object` fields + per-object masterData payload.

---

## Task 0: Shared test fixture — a two-channel project

**Files:**
- Create: `backend/app/agents/_test_per_channel.py`

**Interfaces:**
- Produces: `make_two_channel_state(pid="t-per-channel") -> ProjectState` — a state bound to a synthetic long table with two channel types (`"MT"`, `"TT"`), a shared KPI `销量`, and two drivers `广告投放` (clean in both) and `渠道库存` (clean in MT, constant/degenerate in TT). `model_objects(st) == ["MT", "TT"]`.

- [ ] **Step 1: Write the fixture module with a self-check**

```python
"""Phase 2 — per-Channel-Type screening. Shared fixture + unit tests.

Run: PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from app.agents.dataset_cache import invalidate_project, model_objects, set_project_dataset
from app.domain.models import Industry, ProjectMeta
from app.store.state import initial_state

_MONTHS = [202301 + m if (202301 + m) % 100 <= 12 else 202400 + ((202301 + m) % 100)
           for m in range(24)]  # 24 contiguous yyyymm from 2023-01


def _rows_for(channel_type: str, degenerate_stock: bool) -> list[dict]:
    """One channel's rows: KPI 销量, driver 广告投放, driver 渠道库存.

    `degenerate_stock=True` makes 渠道库存 a constant series in this channel, so it
    is a legitimate drop for statistical screening here but not in the other
    channel — the exact per-channel divergence these tests assert.
    """
    rng = np.random.default_rng(1 if channel_type == "MT" else 2)
    signal = np.linspace(100, 200, len(_MONTHS)) + rng.normal(0, 5, len(_MONTHS))
    ads = signal * 0.5 + rng.normal(0, 3, len(_MONTHS))
    stock = (np.full(len(_MONTHS), 50.0) if degenerate_stock
             else signal * 0.3 + rng.normal(0, 4, len(_MONTHS)))
    out: list[dict] = []
    for i, ym in enumerate(_MONTHS):
        common = dict(task_name="mmm", brand="B", province_group="全国",
                      channel_type=channel_type, channel=channel_type, year=ym // 100,
                      month=ym, source="erp", l2="", l5="", l6="", l7="", l8="")
        out.append({**common, "l1": "KPI", "l3": "销量", "l4": "本品销量",
                    "metric_type": "Y", "metric": "销量", "value": float(signal[i])})
        out.append({**common, "l1": "MARKETING FACTOR", "l3": "广告", "l4": "广告投放",
                    "metric_type": "spending", "metric": "广告投放", "value": float(ads[i])})
        out.append({**common, "l1": "COMMERCIAL FACTOR", "l3": "渠道", "l4": "渠道库存",
                    "metric_type": "X", "metric": "渠道库存", "value": float(stock[i])})
    return out


def make_two_channel_state(pid: str = "t-per-channel"):
    meta = ProjectMeta(id=pid, name="PerChannel", brand="B",
                       industry=Industry(l1="food-bev", l2="beverage", l3="functional"))
    st = initial_state(meta)
    rows = _rows_for("MT", degenerate_stock=False) + _rows_for("TT", degenerate_stock=True)
    df = pd.DataFrame(rows)
    invalidate_project(pid)
    set_project_dataset(pid, df, "slot")
    return st


def test_fixture() -> None:
    st = make_two_channel_state()
    assert model_objects(st) == ["MT", "TT"], model_objects(st)
    print("  fixture: MT + TT bound")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 2: Run it to verify the fixture binds**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: `fixture: MT + TT bound` then `1/1 passed`. If `model_objects` returns them in another order, adjust the assertion to `sorted(...) == ["MT", "TT"]` — order is finalized in Task 8.

- [ ] **Step 3: Commit**

```bash
git add backend/app/agents/_test_per_channel.py
git commit -m "test: two-channel fixture for per-channel-type screening"
```

---

## Task 1: Ledger triple-key helpers + per-object drop resolvers (backward compatible)

Add the object dimension to the ledger's drop-set resolvers **without** changing any existing caller yet: the old global functions keep working (they union across objects), so the suite stays green.

**Files:**
- Modify: `backend/app/agents/ledger.py` (add helpers near `_norm_pair:57`, add per-object resolvers after `unticked_pairs:310`, generalize `drops_before:323`)
- Test: `backend/app/agents/_test_per_channel.py`

**Interfaces:**
- Produces:
  - `OBJECT_ANY = "*"` — the default-all object sentinel.
  - `quality_drop_pairs_by_object(st) -> dict[str, set[tuple[str,str]]]` and likewise `stat_drop_pairs_by_object`, `signoff_drop_pairs_by_object`, `unticked_pairs_by_object`, `range_drop_pairs_by_object`, `mapping_ignored_by_object` — each maps object → that channel's drop set. Layers that are still global (mapping) return `{OBJECT_ANY: <set>}`.
  - `drops_before(st, layer, object=None) -> set[tuple[str,str]]` — `object=None` keeps the current global-union behaviour; a concrete object returns the drops that rule before `layer` **for that channel** (global layers apply to all).

- [ ] **Step 1: Write the failing test**

Add to `_test_per_channel.py`:

```python
def test_stat_drops_are_per_object() -> None:
    from app.agents import ledger
    from app.agents.data import score_data_sync  # built in Task 2; see note
    # For this test we craft stat dispositions directly rather than fitting.
    from app.domain.models import StatScorecard, StatScoreRow
    st = make_two_channel_state()
    st.stat_scorecard = StatScorecard(rows=[
        StatScoreRow(id="s-mt", object="MT", l4="渠道库存", indicator="渠道库存",
                     disposition="include"),
        StatScoreRow(id="s-tt", object="TT", l4="渠道库存", indicator="渠道库存",
                     disposition="drop"),
    ])
    by_obj = ledger.stat_drop_pairs_by_object(st)
    assert ("渠道库存", "渠道库存") in by_obj.get("TT", set()), by_obj
    assert ("渠道库存", "渠道库存") not in by_obj.get("MT", set()), by_obj
    # drops_before for the statistical layer must reflect the channel asked for.
    assert ("渠道库存", "渠道库存") in ledger.drops_before(st, "range", "TT")
    assert ("渠道库存", "渠道库存") not in ledger.drops_before(st, "range", "MT")
    print("  stat drops per object")
```

(Remove the unused `score_data_sync` import line — it was a stray; the test crafts the scorecard directly. Keep only the `StatScorecard`/`StatScoreRow` import.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: FAIL — `StatScoreRow` has no `object` field yet (added in Task 2) **and** `stat_drop_pairs_by_object` does not exist. Add the `object` field to `StatScoreRow` now as part of this step's minimal implementation (it is also formally added in Task 3 for the full contract):

- [ ] **Step 3: Write the implementation**

In `backend/app/domain/models.py`, add to `StatScoreRow` (after `id: str`, line ~475) and `QualityRow` (after `id: str`, line ~443) and `OlsXCandidate` (after `key: str`, line ~535):

```python
    object: str = ""   # model object (channel_type) this row was screened under
```

In `backend/app/agents/ledger.py`, add after `_norm_pair` (line 65):

```python
OBJECT_ANY = "*"   # sentinel: a verdict recorded for every model object


def _obj(v: object) -> str:
    return str(v).strip() if v is not None else ""
```

Replace `_scorecard_pairs` (line 128) and add object-aware variants, and add the per-object resolvers after `unticked_pairs` (line 310):

```python
def _scorecard_pairs_by_object(card, dispositions):
    out: dict[str, set[tuple[str, str]]] = {}
    for row in getattr(card, "rows", None) or []:
        if getattr(row, "disposition", "") in dispositions:
            out.setdefault(_obj(getattr(row, "object", "")) or OBJECT_ANY, set()).add(
                _norm_pair(row.l4, row.indicator))
    return out


def quality_drop_pairs_by_object(st):
    return _scorecard_pairs_by_object(getattr(st, "quality_scorecard", None), ("drop",))


def quality_flag_pairs_by_object(st):
    return _scorecard_pairs_by_object(getattr(st, "quality_scorecard", None), ("flag",))


def stat_drop_pairs_by_object(st):
    return _scorecard_pairs_by_object(getattr(st, "stat_scorecard", None), ("drop",))


def unticked_pairs_by_object(st):
    cfg = getattr(st, "ols_config", None)
    out: dict[str, set[tuple[str, str]]] = {}
    for c in (getattr(cfg, "x_candidates", None) or []):
        if not c.selected:
            out.setdefault(_obj(getattr(c, "object", "")) or OBJECT_ANY, set()).add(
                _norm_pair(c.l4, c.metric))
    return out


def mapping_ignored_by_object(st):
    # Mapping is global — one ignore applies to every object.
    return {OBJECT_ANY: set(_mapping_ignored(st))}


def signoff_drop_pairs_by_object(st):
    # Object-aware sign-off keys land in Task 4; until then every denial is global.
    return {OBJECT_ANY: signoff_drop_pairs(st)}


def range_drop_pairs_by_object(st):
    # d-2.5 freeze becomes per-object in Task 6; until then it is global.
    return {OBJECT_ANY: range_drop_pairs(st)}


_LAYER_PAIRS_BY_OBJECT = {
    "mapping": mapping_ignored_by_object,
    "quality": quality_drop_pairs_by_object,
    "signoff": signoff_drop_pairs_by_object,
    "statistical": stat_drop_pairs_by_object,
    "selection": unticked_pairs_by_object,
    "range": range_drop_pairs_by_object,
}


def _object_drops(by_object: dict[str, set[tuple[str, str]]], object: str | None) -> set[tuple[str, str]]:
    """The drop set that applies to `object` (None → union of everything)."""
    if object is None:
        return set().union(*by_object.values()) if by_object else set()
    return set(by_object.get(OBJECT_ANY, set())) | set(by_object.get(object, set()))
```

Then generalize `drops_before` (line 323) to accept `object`:

```python
def drops_before(st: ProjectState, layer: str, object: str | None = None) -> set[tuple[str, str]]:
    order = [lid for lid, _task, _label in LAYERS]
    if layer not in order:
        raise ValueError(f"unknown layer {layer!r}; expected one of {order}")
    out: set[tuple[str, str]] = set()
    for lid in order[:order.index(layer)]:
        out |= _object_drops(_LAYER_PAIRS_BY_OBJECT[lid](st), object)
    return out
```

Keep the existing `_LAYER_PAIRS` and the old global resolvers (`quality_drop_pairs`, etc.) exactly as they are — they still back the un-migrated callers.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: `stat drops per object` then all pass.

- [ ] **Step 5: Verify nothing else regressed**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.tools._test_tools && PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py`
Expected: both green (the old global path is untouched).

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/ledger.py backend/app/domain/models.py backend/app/agents/_test_per_channel.py
git commit -m "feat(ledger): per-object drop resolvers + drops_before(object) (backward compatible)"
```

---

## Task 2: Build the quality & statistical scorecards per object

Make `score_data` (quality, in `data.py`) and `build_stat_scorecard` (stat) emit one row **per (object, indicator)** by fitting/scoring each channel's own slice. Rows carry `object`; ids are object-scoped so the disposition-edit round-trip stays unique.

**Files:**
- Modify: `backend/app/agents/stat_scoring.py` (`build_stat_scorecard:144`, `_monthly_y:` uses global Y → per object, `_indicator_series` grouping)
- Modify: `backend/app/agents/data.py` (`score_data`, the quality builder around `:389-420`)
- Test: `backend/app/agents/_test_per_channel.py`

**Interfaces:**
- Consumes: `model_objects(st)`, `model_df(st)`, `drops_before(st, layer, object)` from Task 1.
- Produces: `st.stat_scorecard.rows` and `st.quality_scorecard.rows` each carry `object` set to a concrete channel type; the same indicator appears once per channel it is scored under.

- [ ] **Step 1: Write the failing test**

```python
def test_stat_scorecard_is_per_object() -> None:
    from app.agents.stat_scoring import build_stat_scorecard
    st = make_two_channel_state()
    card = build_stat_scorecard(st)
    objs = {r.object for r in card.rows}
    assert objs == {"MT", "TT"}, objs
    # 渠道库存 is constant in TT → dropped there by the degenerate-series guard,
    # but present as a scored row in MT.
    mt_stock = [r for r in card.rows if r.object == "MT" and r.indicator == "渠道库存"]
    assert mt_stock, "渠道库存 should be scored in MT"
    print("  stat scorecard per object")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: FAIL — every row's `object` is `""` (empty), so `objs == {""}`.

- [ ] **Step 3: Implement per-object stat scoring**

In `backend/app/agents/stat_scoring.py`, rewrite `build_stat_scorecard` to loop over objects, slicing `df` by `channel_type` and passing the object into `drops_before`. Replace the single-pass body (from `df = model_df(st)` through the `rows.append(...)` loop) with:

```python
    from app.agents.dataset_cache import model_df, model_objects
    from app.agents.ledger import _matches, _norm_pair, drops_before

    full = model_df(st)
    all_rows: list[StatScoreRow] = []
    for obj in model_objects(st):
        df = full[full["channel_type"].astype("string").str.strip() == obj]
        y = _monthly_y(df)
        metas, wide = _indicator_series(df)
        if not metas or y is None:
            continue
        wide = wide.reindex(_complete_month_index(wide.index), fill_value=0.0)
        inherited = drops_before(st, "statistical", obj)
        if inherited:
            metas = [m for m in metas
                     if not _matches(_norm_pair(m["l4"], m["indicator"]), inherited)]
            if not metas:
                continue
        cols = [m["col"] for m in metas]
        # ... (the existing CV / Pearson / VIF computation, unchanged, over `cols`)
        # then, where the existing code does `rows.append(StatScoreRow(id=f"s-{col}", ...))`:
        for m, sc in _scored_rows(metas, ...):   # keep the existing scoring shape
            all_rows.append(StatScoreRow(
                id=f"{obj}|s-{m['col']}", object=obj,
                l1=m["l1"], l2=m["l2"], l3=m["l3"], l4=m["l4"], indicator=m["indicator"],
                # ... all existing numeric fields unchanged ...
                disposition=_DISPOSITION_DEFAULT.get(sc.verdict, "review"),
            ))
    return StatScorecard(rows=all_rows)
```

Keep the CV/Pearson/VIF tool calls **inside** the per-object loop exactly as they are today (they now run once per channel over that channel's `cols`). The tool wrappers are unchanged — `_test_tools.py` still asserts identity. Delete the old top-level single-pass `df = model_df(st)` block and the outer `inherited = drops_before(st, "statistical")` (no object) call.

In `backend/app/agents/data.py::score_data`, apply the same shape: loop `for obj in model_objects(st)`, slice `df` by `channel_type == obj`, build `QualityRow(id=f"{obj}|q-{i}", object=obj, ...)` per that channel's series, and gate with `drops_before(st, "quality", obj)`. (Quality's `drops_before` is only mapping today, so this changes nothing numerically yet — but it establishes the per-object rows the ledger reads.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: `stat scorecard per object` passes.

- [ ] **Step 5: Verify identity + smoke**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.tools._test_tools && PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py`
Expected: green. If `_test_tools` recomputes the scorecard and asserts a global shape, update only its expectation to iterate objects — never change a tool wrapper's arithmetic.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/stat_scoring.py backend/app/agents/data.py backend/app/agents/_test_per_channel.py
git commit -m "feat(s2): build quality + statistical scorecards per model object"
```

---

## Task 3: Wire the ledger's own resolvers to the per-object scorecards

`indicator_ledger`, `funnel`, `quality_drop_pairs`, `stat_drop_pairs` still read the scorecard **globally** (any row with a matching disposition drops the pair for all objects). Re-point the ledger's internal reads at the per-object resolvers and give `LedgerRow` an `object`, so the derived lifecycle is per channel.

**Files:**
- Modify: `backend/app/agents/ledger.py` (`LedgerRow:92`, `indicator_ledger:418`, `funnel:623`, `adopted_pairs`/`rejected_pairs`)
- Test: `backend/app/agents/_test_per_channel.py`

**Interfaces:**
- Produces: `LedgerRow.object: str`; `indicator_ledger(st)` returns one row per `(object, l4, metric)`; `funnel(st)` returns `list[dict]` with a top-level `objects` breakdown (see below). `adopted_pairs`/`rejected_pairs` gain an optional `object` filter.

- [ ] **Step 1: Write the failing test**

```python
def test_ledger_is_per_object() -> None:
    from app.agents.stat_scoring import build_stat_scorecard
    from app.agents import ledger
    st = make_two_channel_state()
    st.stat_scorecard = build_stat_scorecard(st)
    # Force TT to drop 渠道库存, MT to keep it.
    for r in st.stat_scorecard.rows:
        if r.indicator == "渠道库存":
            r.disposition = "drop" if r.object == "TT" else "include"
    rows = ledger.indicator_ledger(st)
    tt = next(r for r in rows if r.object == "TT" and r.indicator == "渠道库存")
    mt = next(r for r in rows if r.object == "MT" and r.indicator == "渠道库存")
    assert not tt.adopted and tt.rejected_at == "statistical", (tt.rejected_at, tt.adopted)
    assert mt.adopted, mt.rejected_at
    print("  ledger per object: 渠道库存 dropped in TT, kept in MT")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: FAIL — `LedgerRow` has no `object`, so the `next(... r.object ...)` raises `AttributeError`.

- [ ] **Step 3: Implement the per-object ledger**

In `ledger.py`, add `object: str = ""` to `LedgerRow` (line 102 area). Rewrite `indicator_ledger` to loop objects × universe. The universe (`_universe`) is already keyed by `(l4, metric)` and is object-independent; iterate it once per object, resolving each object's own drop sets:

```python
def indicator_ledger(st: ProjectState) -> tuple[LedgerRow, ...]:
    universe = _universe(st)
    ignored = _mapping_ignored(st)
    q_drop_o = quality_drop_pairs_by_object(st)
    q_flag_o = quality_flag_pairs_by_object(st)
    sign_o = signoff_drop_pairs_by_object(st)
    s_drop_o = stat_drop_pairs_by_object(st)
    tick_o = unticked_pairs_by_object(st)
    range_o = range_drop_pairs_by_object(st)
    flagged = ols_flagged_pairs(st)   # flags stay global display-only for now

    from app.agents.dataset_cache import model_objects
    objects = model_objects(st) or [OBJECT_ANY]

    cfg: OlsConfig | None = getattr(st, "ols_config", None)

    rows: list[LedgerRow] = []
    for obj in objects:
        q_drop = _object_drops(q_drop_o, obj)
        q_flag = _object_drops(q_flag_o, obj)
        sign_drop = _object_drops(sign_o, obj)
        s_drop = _object_drops(s_drop_o, obj)
        r_drop = _object_drops(range_o, obj)
        # 2.5x rules only once a candidate exists for this object.
        ticked_here = {p: False for p in _object_drops(tick_o, obj)}
        offered = set()
        if cfg is not None and cfg.x_candidates:
            for c in cfg.x_candidates:
                if (_obj(getattr(c, "object", "")) or OBJECT_ANY) in (OBJECT_ANY, obj):
                    offered.add(_norm_pair(c.l4, c.metric))

        for key, c in sorted(universe.items()):
            verdicts: list[LayerVerdict] = []
            rejected_at, reason = "", ""

            def rule(layer, status, note=""):
                nonlocal rejected_at, reason
                if rejected_at:
                    verdicts.append(LayerVerdict(layer, LAYER_TASK[layer], LAYER_LABEL[layer],
                                                 STATUS_INHERITED,
                                                 f"Already rejected at {LAYER_LABEL[rejected_at]}."))
                    return
                verdicts.append(LayerVerdict(layer, LAYER_TASK[layer], LAYER_LABEL[layer], status, note))
                if status == STATUS_REJECTED:
                    rejected_at, reason = layer, note

            # 2.1 mapping — global
            if _matches(key, set(ignored)):
                rule("mapping", STATUS_REJECTED,
                     ignored.get(key) or "Ignored in the FactorTree↔DataAssets mapping.")
            else:
                rule("mapping", STATUS_ADOPTED, "Mapped to a published data asset.")
            # 2.2d quality
            if _matches(key, q_drop):
                rule("quality", STATUS_REJECTED, "Dropped in the data-quality review (unusable).")
            elif _matches(key, q_flag):
                rule("quality", STATUS_FLAGGED, "Borderline quality — kept with a caveat.")
            else:
                rule("quality", STATUS_ADOPTED, "Passed the data-quality review.")
            # 2.3 sign-off
            if _matches(key, sign_drop):
                rule("signoff", STATUS_REJECTED,
                     f"Not signed off by the client at Business Validation ({c.get('metric', key[1])}).")
            else:
                rule("signoff", STATUS_ADOPTED, "Covered by the business-validation sign-off.")
            # 2.4d statistical
            if _matches(key, s_drop):
                rule("statistical", STATUS_REJECTED, "Dropped in the statistical screening.")
            else:
                rule("statistical", STATUS_ADOPTED, "Passed the statistical screening.")
            # 2.5x selection
            if key in offered:
                if key in ticked_here:
                    rule("selection", STATUS_REJECTED, "Not ticked as a model variable.")
                else:
                    rule("selection", STATUS_ADOPTED, "Ticked as a model variable.")
            else:
                rule("selection", STATUS_PENDING, "The model setup has not been proposed yet.")
            # 2.5r range
            if _matches(key, r_drop):
                rule("range", STATUS_REJECTED,
                     "Outside its knowledge-base ROI / contribution band; dropped at the d-2.5 gate.")
            elif _matches(key, flagged):
                rule("range", STATUS_FLAGGED,
                     "Outside its knowledge-base ROI / contribution band; kept for review.")
            else:
                rule("range", STATUS_ADOPTED, "Within its expected range (or no benchmark).")

            rows.append(LedgerRow(
                key=key, object=obj, l1=c.get("l1", ""), l2=c.get("l2", ""),
                l3=c.get("l3", ""), l4=c.get("l4", ""), indicator=c.get("metric", ""),
                metric=c.get("metric", ""), verdicts=tuple(verdicts),
                adopted=not rejected_at, rejected_at=rejected_at, reason=reason))

    # Ignored-but-absent + C1 sign-off rows (global) — emit once, object=OBJECT_ANY,
    # unchanged from the current tail of indicator_ledger except LedgerRow(object=OBJECT_ANY, ...).
    # (keep the two existing loops; add object=OBJECT_ANY to each LedgerRow)
    return tuple(rows)
```

Update `adopted_pairs`/`rejected_pairs` to accept an optional object:

```python
def adopted_pairs(st, object: str | None = None) -> frozenset[tuple[str, str]]:
    return frozenset(r.key for r in indicator_ledger(st)
                     if r.adopted and (object is None or r.object in (object, OBJECT_ANY)))


def rejected_pairs(st, object: str | None = None) -> frozenset[tuple[str, str]]:
    return frozenset(r.key for r in indicator_ledger(st)
                     if not r.adopted and (object is None or r.object in (object, OBJECT_ANY)))
```

Rewrite `funnel` to report per object plus an "all" rollup:

```python
def funnel(st: ProjectState) -> dict:
    """Per-object per-layer intake → survivors, plus a combined rollup."""
    from app.agents.dataset_cache import model_objects
    ledger = indicator_ledger(st)
    def _for(rows) -> list[dict]:
        out, remaining = [], len(rows)
        for lid, task, label in LAYERS:
            killed = [r for r in rows if r.rejected_at == lid]
            out.append({"layer": lid, "task": task, "label": label,
                        "intake": remaining, "rejected": len(killed),
                        "survivors": remaining - len(killed),
                        "dropped": [{"l4": r.l4, "indicator": r.indicator, "reason": r.reason}
                                    for r in killed]})
            remaining -= len(killed)
        return out
    per_object = {obj: _for([r for r in ledger if r.object in (obj, OBJECT_ANY)])
                  for obj in (model_objects(st) or [OBJECT_ANY])}
    return {"combined": _for(list(ledger)), "byObject": per_object}
```

**Note the funnel return-shape change** (`list` → `dict`): update the two callers in `data.py::assemble_master_data` (Task 7) — they are the only consumers. Keep `quality_drop_pairs`/`stat_drop_pairs` (the flat global helpers) since `model_selection` still unions them defensively (Task 6 re-points that).

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: `ledger per object: 渠道库存 dropped in TT, kept in MT` passes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/ledger.py backend/app/agents/_test_per_channel.py
git commit -m "feat(ledger): indicator_ledger + funnel resolved per model object"
```

---

## Task 4: Object-aware sign-off keys (default-all)

Extend the `st.signoffs` key to carry the object, with the `*` sentinel meaning "every channel". A single "Deny" from the 2.3 deck still applies to all channels (default), and a per-channel override is possible.

**Files:**
- Modify: `backend/app/agents/ledger.py` (`signoff_key:148`, `_parse_signoff_key:161`, `signoff_denied:196`, `signoff_drop_pairs_by_object`)
- Modify: `backend/app/main.py` (`put_signoff:848` — pass object through; default `OBJECT_ANY`)
- Modify: `backend/app/domain/models.py` (`SignoffBody` — add optional `object: str = ""`)
- Test: `backend/app/agents/_test_per_channel.py`

**Interfaces:**
- Produces: `signoff_key(l4, metric, object="*") -> str` = `f"i:{object}:{l4}|{metric}"`; `_parse_signoff_key` returns `(kind, object, l4_or_l3, metric)`; `signoff_drop_pairs_by_object` reads a concrete object into that object's set and `*` into `OBJECT_ANY`.

- [ ] **Step 1: Write the failing test**

```python
def test_signoff_key_carries_object() -> None:
    from app.agents import ledger
    k_all = ledger.signoff_key("广告投放", "广告投放")
    k_tt = ledger.signoff_key("广告投放", "广告投放", "TT")
    assert k_all == "i:*:广告投放|广告投放", k_all
    kind, obj, l4, metric = ledger._parse_signoff_key(k_tt)
    assert (kind, obj, l4, metric) == ("indicator", "TT", "广告投放", "广告投放")
    st = make_two_channel_state()
    st.signoffs = {k_tt: "no"}
    by_obj = ledger.signoff_drop_pairs_by_object(st)
    assert ("广告投放", "广告投放") in by_obj.get("TT", set())
    assert ("广告投放", "广告投放") not in by_obj.get("MT", set())
    # A legacy unprefixed key still parses and applies to all objects.
    st.signoffs = {"广告投放|广告投放": "no"}
    by_obj = ledger.signoff_drop_pairs_by_object(st)
    assert ("广告投放", "广告投放") in by_obj.get(ledger.OBJECT_ANY, set())
    print("  sign-off keys are object-aware, legacy keys still parse")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: FAIL — `signoff_key` takes 2 args / builds the old `i:<l4>|<metric>` shape.

- [ ] **Step 3: Implement**

Replace `signoff_key` and `_parse_signoff_key`:

```python
def signoff_key(l4: object, metric: object, object: str = OBJECT_ANY) -> str:
    a, b = _norm_pair(l4, metric)
    return f"i:{_obj(object) or OBJECT_ANY}:{a}|{b}"


def _parse_signoff_key(key: str) -> Optional[tuple[str, str, str, str]]:
    """Returns (kind, object, l4_or_l3, metric); object is OBJECT_ANY for legacy keys."""
    if key.startswith("i:"):
        rest = key[2:]
        obj, sep, pair = rest.partition(":")
        if not sep:
            return None
        l4, psep, metric = pair.partition("|")
        if not psep or f"i:{obj}:{l4}|{metric}" != key:
            return None
        return ("indicator", obj or OBJECT_ANY, l4, metric)
    if "|" in key:
        l4, _, metric = key.partition("|")
        return ("indicator", OBJECT_ANY, l4, metric)
    return ("factor", OBJECT_ANY, key, "")
```

Update `signoff_denied` to return objects, and add the by-object resolver (replacing the stub from Task 1):

```python
def signoff_denied(st):
    """Denied entries as (object, l4, metric) triples and (object, l3) pairs."""
    triples: set[tuple[str, str, str]] = set()
    l3s: set[tuple[str, str]] = set()
    for key, verdict in (getattr(st, "signoffs", None) or {}).items():
        if _norm(verdict) != "no":
            continue
        parsed = _parse_signoff_key(key)
        if parsed is None:
            continue
        kind, obj, a, b = parsed
        if kind == "indicator":
            triples.add((obj, _norm(a), _norm(b)))
        else:
            l3s.add((obj, _norm(a)))
    return triples, l3s


def signoff_drop_pairs_by_object(st):
    triples, l3s = signoff_denied(st)
    out: dict[str, set[tuple[str, str]]] = {}
    for obj, l4, metric in triples:
        out.setdefault(obj, set()).add((l4, metric))
    if l3s:
        uni = _universe(st)
        for obj, l3 in l3s:
            out.setdefault(obj, set()).update(
                key for key, c in uni.items() if _norm(c.get("l3")) == l3)
    return out
```

Keep the old flat `signoff_drop_pairs(st)` working for `model_selection`'s defensive union — redefine it as the union across objects:

```python
def signoff_drop_pairs(st):
    return set().union(*signoff_drop_pairs_by_object(st).values()) if getattr(st, "signoffs", None) else set()
```

Update `stale_factor_keys` for the new 4-tuple parse (`parsed[0] == "factor" and _norm(parsed[2]) == target`).

In `models.py`, add `object: str = ""` to `SignoffBody`. In `main.py::put_signoff`, thread `body.object` (default `""` → `OBJECT_ANY`) into every `ledger.signoff_key(...)` call (the three branches at lines 883, 890, 904).

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel && PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py`
Expected: green (smoke exercises `put_signoff`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/ledger.py backend/app/main.py backend/app/domain/models.py backend/app/agents/_test_per_channel.py
git commit -m "feat(s2): object-aware sign-off keys with default-all sentinel"
```

---

## Task 5: Per-object X candidates + per-object OLS records

Stop the 2.5 proposal from deduping candidates across channels, and stop the review from averaging ROI/contribution across channels. Each channel gets its own candidate list and its own per-indicator verdicts.

**Files:**
- Modify: `backend/app/agents/ols_review.py` (`build_ols_proposal:131`, the `seen` dedupe `:164-192`; `selected_x_metrics:223`; `_collect_records:242` key `:305`; `_row_from_record:346`; `y_metric_for` unchanged)
- Test: `backend/app/agents/_test_per_channel.py`

**Interfaces:**
- Consumes: `OlsXCandidate.object` (Task 1/3).
- Produces: `build_ols_proposal(st)` returns a config whose `x_candidates` carry `object` and are **not** deduped across objects; `selected_x_metrics(cfg) -> dict[str, frozenset[str]] | None` (per object); `_collect_records` keyed by `(object, l4, metric)` — no `_nan_mean` across objects.

- [ ] **Step 1: Write the failing test**

```python
def test_ols_candidates_are_per_object() -> None:
    from app.agents.stat_scoring import build_stat_scorecard
    from app.agents.ols_review import build_ols_proposal, selected_x_metrics
    st = make_two_channel_state()
    st.stat_scorecard = build_stat_scorecard(st)
    cfg = build_ols_proposal(st)
    objs = {c.object for c in cfg.x_candidates}
    assert objs == {"MT", "TT"}, objs
    # 广告投放 offered separately in each channel.
    ads = [c for c in cfg.x_candidates if c.metric == "广告投放"]
    assert {c.object for c in ads} == {"MT", "TT"}, [c.object for c in ads]
    sel = selected_x_metrics(cfg)
    assert isinstance(sel, dict) and set(sel) <= {"MT", "TT"}
    print("  OLS candidates + selection are per object")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: FAIL — candidates dedupe to one object; `selected_x_metrics` returns a flat `frozenset`.

- [ ] **Step 3: Implement**

In `build_ols_proposal`, replace the `seen: dict[...]` cross-object dedupe with a per-object build: key `seen` by `(obj, l4, metric)`, set `object=obj` on each `OlsXCandidate`, use `drops_before(st, "selection", obj)` for `locked_by` per channel, and apply the `DEFAULT_MAX_SELECTED` cap **per object** (reset `picked = 0` at each object boundary). Sort within object, then concatenate.

Rewrite `selected_x_metrics`:

```python
def selected_x_metrics(cfg):
    """Per-object metric names the human kept — None = legacy auto-select."""
    if cfg is None or not cfg.x_candidates:
        return None
    out: dict[str, frozenset[str]] = {}
    for c in cfg.x_candidates:
        if c.selected:
            out.setdefault(_obj_of(c), set()).add(_norm(c.metric))
    return {k: frozenset(v) for k, v in out.items()} or None
```

where `_obj_of(c) = (c.object or OBJECT_ANY)`. In `_collect_records`, resolve `include` per object inside the loop — `inc = include.get(obj) if isinstance(include, dict) else include` when `include` is the dict — and key `records` by `(obj, l4n, metricn)` instead of `(l4n, metricn)`. Drop the `roi_money` cross-object averaging concern by keeping the record scoped to one object; `_row_from_record` now aggregates a single object's samples (its lists usually hold one value), so remove the cross-object `_nan_mean` semantics comment and keep the mean (still correct for one object). `build_ols_review`'s tree loop must now emit **one tree row per (object, factor-row)**: wrap the `for fm in fmap.rows` loop in `for obj in model_objects(st)` and look up `records[(obj, l4n, name)]`, tagging each tree row with `"object": obj`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: `OLS candidates + selection are per object` passes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/ols_review.py backend/app/agents/_test_per_channel.py
git commit -m "feat(2.5): per-object X candidates and per-object OLS review records"
```

---

## Task 6: Per-object `ModelSelection` (the resolved fit input)

Change `ModelSelection.include/exclude` to per-object dicts, derive them per object in `model_selection`, and pin the d-2.5 range freeze per object.

**Files:**
- Modify: `backend/app/agents/ledger.py` (`ModelSelection:108`, `model_selection:558`, `range_drop_pairs:256`, `freeze_range_drops:277`, `range_drop_pairs_by_object`)
- Test: `backend/app/agents/_test_per_channel.py`

**Interfaces:**
- Produces:
  - `ModelSelection.exclude: dict[str, frozenset[pair]]`, `include: dict[str, Optional[frozenset[str]]]`, `y: dict[str,str]` (unchanged), `params`.
  - `exclude_for(obj) -> frozenset[pair]` = `.get(obj, frozenset()) | .get(OBJECT_ANY, frozenset())`.
  - `include_for(obj) -> Optional[frozenset[str]]` = `.get(obj)` (falls back to `.get(OBJECT_ANY)`; `None` = legacy auto).
  - `y_for(obj)` unchanged.

- [ ] **Step 1: Write the failing test**

```python
def test_model_selection_is_per_object() -> None:
    from app.agents.stat_scoring import build_stat_scorecard
    from app.agents.ledger import model_selection
    st = make_two_channel_state()
    st.stat_scorecard = build_stat_scorecard(st)
    for r in st.stat_scorecard.rows:
        if r.indicator == "渠道库存":
            r.disposition = "drop" if r.object == "TT" else "include"
    sel = model_selection(st)
    assert ("渠道库存", "渠道库存") in sel.exclude_for("TT")
    assert ("渠道库存", "渠道库存") not in sel.exclude_for("MT")
    print("  model_selection excludes per object")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: FAIL — `exclude_for` does not exist; `sel.exclude` is a flat frozenset.

- [ ] **Step 3: Implement**

Replace `ModelSelection`:

```python
@dataclass(frozen=True)
class ModelSelection:
    exclude: dict[str, frozenset[tuple[str, str]]] = field(default_factory=dict)
    include: dict[str, Optional[frozenset[str]]] = field(default_factory=dict)
    y: dict[str, str] = field(default_factory=dict)
    params: Optional[OlsParams] = None

    def exclude_for(self, obj: str) -> frozenset[tuple[str, str]]:
        return frozenset(self.exclude.get(obj, frozenset()) | self.exclude.get(OBJECT_ANY, frozenset()))

    def include_for(self, obj: str) -> Optional[frozenset[str]]:
        v = self.include.get(obj)
        return v if v is not None else self.include.get(OBJECT_ANY)

    def y_for(self, obj: str) -> Optional[str]:
        return self.y.get(obj) or None
```

Rewrite `model_selection` to build the dicts per object from the per-object ledger:

```python
def model_selection(st: ProjectState) -> ModelSelection:
    from app.agents.dataset_cache import model_objects
    ledger = indicator_ledger(st)
    cfg: OlsConfig | None = getattr(st, "ols_config", None)
    exclude: dict[str, frozenset] = {}
    include: dict[str, Optional[frozenset[str]]] = {}
    for obj in (model_objects(st) or [OBJECT_ANY]):
        obj_rows = [r for r in ledger if r.object in (obj, OBJECT_ANY)]
        adopted = {r.key for r in obj_rows if r.adopted}
        exclude[obj] = frozenset({r.key for r in obj_rows if not r.adopted}
                                 | _object_drops(quality_drop_pairs_by_object(st), obj)
                                 | _object_drops(stat_drop_pairs_by_object(st), obj)
                                 | _object_drops(signoff_drop_pairs_by_object(st), obj))
        if cfg is not None and cfg.x_candidates:
            include[obj] = frozenset(
                _norm(c.metric) for c in cfg.x_candidates
                if c.selected and (_obj(getattr(c, "object", "")) or OBJECT_ANY) in (OBJECT_ANY, obj)
                and _norm_pair(c.l4, c.metric) in adopted)
        else:
            include[obj] = None
    y = {c.object: c.metric for c in (cfg.y if cfg else []) if c.metric}
    params = None
    if cfg is not None:
        events, caps = anomaly_effects(st)
        params = cfg.params.model_copy(update={"events": events, "caps": caps})
    return ModelSelection(exclude=exclude, include=include, y=y, params=params)
```

Make the d-2.5 range freeze per object: `freeze_range_drops` stores `dec.resolution["droppedPairsByObject"] = {obj: [[l4,metric],...]}` from `ols_flagged_pairs` grouped by object (the flagged list gains `object` in Task 5's `build_ols_review`; read `f.get("object")`). `range_drop_pairs_by_object` reads that per-object frozen map (falling back to the legacy flat `droppedPairs` under `OBJECT_ANY`).

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: `model_selection excludes per object` passes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/ledger.py backend/app/agents/_test_per_channel.py
git commit -m "feat(ledger): ModelSelection.include/exclude keyed per model object"
```

---

## Task 7: Migrate every fit consumer to `*_for(obj)`

Point the three consumers at the per-object accessors and update the master-data payload to serialize per object. This is where a channel's own surviving set actually shapes its fit.

**Files:**
- Modify: `backend/app/agents/ols_review.py` (`build_ols_review:428` `exclude = sel.exclude` → per-object in `_collect_records`)
- Modify: `backend/app/agents/master_data.py` (`adopted_mask:67` per object)
- Modify: `backend/app/agents/model.py` (`train_models:45` → `exclude_for`/`include_for`)
- Modify: `backend/app/agents/data.py` (`assemble_master_data` — `build_model_frame` per object + funnel dict + per-object adopted/rejected)
- Test: `backend/app/agents/_test_per_channel.py`

**Interfaces:**
- Consumes: `sel.exclude_for(obj)`, `sel.include_for(obj)`, `sel.y_for(obj)`; `funnel(st)` dict shape from Task 3.

- [ ] **Step 1: Write the failing test**

```python
def test_master_table_columns_differ_by_channel() -> None:
    from app.agents.stat_scoring import build_stat_scorecard
    from app.agents.master_data import master_table
    st = make_two_channel_state()
    st.stat_scorecard = build_stat_scorecard(st)
    for r in st.stat_scorecard.rows:
        if r.indicator == "渠道库存":
            r.disposition = "drop" if r.object == "TT" else "include"
    mt = master_table(st, channel_type=["MT"])
    tt = master_table(st, channel_type=["TT"])
    assert "渠道库存" in [c for c in mt["columns"]], mt["columns"]
    assert "渠道库存" not in [c for c in tt["columns"]], tt["columns"]
    print("  master table columns differ by channel")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: FAIL — `adopted_mask` uses the flat `sel.exclude` (now a dict) → either raises or keeps 渠道库存 in both.

- [ ] **Step 3: Implement**

`master_data.adopted_mask` — resolve the object from the rows being masked. Since a master-table call is already sliced to a channel via `_apply_dims`, compute the mask **per channel_type present** in `df`:

```python
def adopted_mask(st: ProjectState, df: pd.DataFrame) -> pd.Series:
    sel = model_selection(st)
    l4 = df["l4"].astype("string").map(_lower) if "l4" in df.columns else pd.Series("", index=df.index)
    metric = df["metric"].astype("string").map(_lower)
    ct = df["channel_type"].astype("string").map(lambda s: str(s).strip()) if "channel_type" in df.columns \
        else pd.Series("", index=df.index)
    keep = pd.Series(True, index=df.index)
    for obj in sorted(set(ct) - {""}):
        excl = sel.exclude_for(obj)
        metric_only = {m for excl_l4, m in excl if not excl_l4}
        inc = sel.include_for(obj)
        rowsel = ct == obj
        rej = pd.Series([(a, b) in excl or b in metric_only
                         for a, b in zip(l4[rowsel], metric[rowsel])], index=l4[rowsel].index)
        block = rej if inc is None else (rej | ~metric[rowsel].isin(inc))
        keep.loc[rowsel] = ~block
    return keep | _kpi_mask(df)
```

`model.train_models` (line 45): `make_candidates(df, obj, n=3, exclude=sel.exclude_for(obj), y_metric=sel.y_for(obj), include=sel.include_for(obj), params=sel.params)`.

`data.assemble_master_data`: replace `mf = build_model_frame(df, obj, exclude=sel.exclude, ...)` with `exclude=sel.exclude_for(obj), include=sel.include_for(obj)`. Replace `"funnel": funnel(st)` with the new dict (it already returns `{"combined","byObject"}`). Serialize `adopted`/`rejected` grouped by object:

```python
    led = indicator_ledger(st)
    body = {
        "objects": obj_rows,
        "funnel": funnel(st),                       # {combined, byObject}
        "dimensions": dimensions(st),
        "byObject": _ledger_by_object(led),         # helper below
        "note": (...),                              # keep existing English note
    }
```

where `_ledger_by_object` (add near the top of `data.py`) returns, per object, `{adopted:[...], rejected:[{..., verdicts:[...]}]}` — **and adopted rows now also carry `verdicts`** (spec §3.5), so Tab 2 can show why-accepted. Keep the flat `adopted`/`rejected` keys too for one release so any un-migrated reader still works.

Update `build_ols_review` (`ols_review.py:429`): it currently reads `exclude = sel.exclude` and passes it whole to `_collect_records`. Pass `sel` through and resolve `exclude_for(obj)` inside `_collect_records`'s per-object loop; `rejected_by` becomes `{(r.object, r.key): r.rejected_at}`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: `master table columns differ by channel` passes.

- [ ] **Step 5: Full backend regression**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.tools._test_tools && PYTHONPATH=. .venv/bin/python -m app.mmm._test_real && PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py`
Expected: all green. `_test_real` fits the Danone reference (7 channel types) — confirms the per-object path runs on real multi-channel data.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/master_data.py backend/app/agents/model.py backend/app/agents/data.py backend/app/agents/ols_review.py backend/app/agents/_test_per_channel.py
git commit -m "feat(s2): every fit consumer resolves selection per model object"
```

---

## Task 8: `heal_state` migration + data-derived channel ordering

Old archived projects hold global scorecard rows (`object=""`), global sign-off keys, and a global d-2.5 freeze. Expand them to per-object so legacy projects behave identically; and remove the hardcoded channel-ordering list.

**Files:**
- Modify: `backend/app/store/state.py` (`heal_state:206` — add the migration block)
- Modify: `backend/app/agents/dataset_cache.py` (`model_objects:144` — data-derived ordering)
- Test: `backend/app/agents/_test_per_channel.py`

**Interfaces:**
- Consumes: `OBJECT_ANY`.
- Produces: after `heal_state`, a legacy row with `object=""` is treated as `OBJECT_ANY` (applies to all channels) — the resolvers in Task 1 already map empty `object` → `OBJECT_ANY`, so **no data rewrite is needed**; assert that invariant here and document it. `model_objects` orders by in-data row count (descending), then name.

- [ ] **Step 1: Write the failing test**

```python
def test_legacy_global_rows_apply_to_all_objects() -> None:
    from app.agents.stat_scoring import build_stat_scorecard
    from app.agents import ledger
    st = make_two_channel_state()
    # Simulate a legacy scorecard: object="" on a drop → must hit BOTH channels.
    st.stat_scorecard = build_stat_scorecard(st)
    for r in st.stat_scorecard.rows:
        r.object = ""      # legacy state
    for r in st.stat_scorecard.rows:
        if r.indicator == "渠道库存":
            r.disposition = "drop"
    by_obj = ledger.stat_drop_pairs_by_object(st)
    assert ("渠道库存", "渠道库存") in by_obj.get(ledger.OBJECT_ANY, set())
    assert ("渠道库存", "渠道库存") in ledger.drops_before(st, "range", "MT")
    assert ("渠道库存", "渠道库存") in ledger.drops_before(st, "range", "TT")
    print("  legacy global rows apply to every channel")


def test_model_objects_ordered_by_data() -> None:
    from app.agents.dataset_cache import model_objects
    st = make_two_channel_state()  # MT and TT have equal row counts → name order
    assert set(model_objects(st)) == {"MT", "TT"}
    print("  model_objects derived from data, no hardcoded list")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: the first test passes already (the resolvers map `""`→`OBJECT_ANY`), confirming no rewrite is needed — but the second **fails** if `model_objects` still filters through the hardcoded `preferred` list (`社区团购` etc. bias). Keep both as regression guards.

- [ ] **Step 3: Implement**

In `dataset_cache.model_objects`, replace the hardcoded `preferred` block:

```python
def model_objects(st: object | None = None) -> list[str]:
    df = model_df(st)
    if df.empty or "channel_type" not in df.columns:
        return []
    ct = df["channel_type"].astype("string").str.strip()
    counts = ct[ct.ne("") & ct.ne("nan")].value_counts()
    return [str(k) for k in counts.index]  # busiest channel first, ties by pandas order
```

In `heal_state`, add a short documented block (no data rewrite; assert-and-forget) after the `validation_specs` back-fill:

```python
    # Per-channel-type screening migration: legacy scorecard rows / OLS candidates
    # carry object="" (pre-migration global verdicts). The ledger resolvers treat an
    # empty object as OBJECT_ANY (applies to every channel), so a saved global verdict
    # keeps its exact effect — no row rewrite required. Left as a comment so a future
    # reader does not "fix" the empty object by guessing a channel.
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel`
Expected: both new tests pass; earlier tests still pass. Revisit Task 0's ordering assertion if needed (now `set(...) == {"MT","TT"}`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/store/state.py backend/app/agents/dataset_cache.py backend/app/agents/_test_per_channel.py
git commit -m "feat(s2): legacy-global heal invariant + data-derived channel ordering"
```

---

## Task 9: Frontend contract mirror (types only)

Mirror the three `object` fields and the per-object masterData payload in `types.ts` so the Phase 1 UI (and any typed reader) compiles. No component work here — that is the Phase 1 plan.

**Files:**
- Modify: `frontend/src/lib/types.ts` (`OlsXCandidate`, `QualityRow`/`StatScoreRow`, `MasterData`, `SignoffBody`)

**Interfaces:**
- Produces: `object?: string` on the OLS X candidate and both scorecard rows; `byObject` on the masterData body; `object?: string` on the sign-off request.

- [ ] **Step 1: Add the fields**

In `frontend/src/lib/types.ts`, add `object?: string;` to the OLS X candidate, quality row, and stat row interfaces; add `byObject?: Record<string, { adopted: LedgerVerdictRow[]; rejected: LedgerVerdictRow[] }>;` and keep `funnel` as the new `{ combined: FunnelLayer[]; byObject: Record<string, FunnelLayer[]> }` shape on the masterData body; add `object?: string` to the sign-off request type. Match the exact interface names already present (grep `OlsXCandidate`, `MasterData`, `Signoff` in the file first).

- [ ] **Step 2: Type-check the frontend**

Run: `cd frontend && npm run build`
Expected: `tsc -b` passes. If a component reads `funnel` as an array, add a temporary adapter (`funnel.combined ?? funnel`) — the real UI rework is the Phase 1 plan.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/types.ts
git commit -m "feat(types): mirror per-object screening fields in the frontend contract"
```

---

## Task 10: End-to-end verification on the real case

Prove the whole chain runs per channel on real multi-channel data with no breakpoints.

**Files:**
- None (verification only)

- [ ] **Step 1: Reset + autopilot the Danone case**

Start the backend (`.venv/bin/python -m uvicorn app.main:app --port 8000`), then:

```bash
P=danone-mizone
curl -XPOST localhost:8000/api/projects/$P/reset
curl -XPOST localhost:8000/api/projects/$P/run -H 'content-type: application/json' -d '{"autopilot":true}'
# poll until status is done (~8 min)
curl localhost:8000/api/projects/$P/run/status
```

- [ ] **Step 2: Assert per-channel divergence in the master data**

```bash
curl -s localhost:8000/api/projects/$P/state | \
  python3 -c "import sys,json; b=[a for a in json.load(sys.stdin)['artifacts'] if a['id']=='a-master-data'][0]['body']; \
  print('objects:', [o['object'] for o in b['objects']]); \
  print('byObject keys:', list(b.get('byObject',{}).keys()))"
```
Expected: multiple channel-type objects (MT/TT/AFH/EC/…); `byObject` present with per-channel adopted/rejected. Spot-check that at least one indicator is adopted in one channel and rejected in another.

- [ ] **Step 3: Record findings**

Append to `restored/model-input-2.32/qa/e2e-findings.md` a short note: which indicators diverged by channel, and any breakpoint encountered. If any step fabricated data or stalled, stop and open a follow-up rather than papering over it.

- [ ] **Step 4: Commit the findings**

```bash
git add restored/model-input-2.32/qa/e2e-findings.md
git commit -m "test(e2e): per-channel screening runs end-to-end on the Danone case"
```

---

## Self-Review

**Spec coverage (spec §2, §3):** layer keying table → Tasks 1–6 (mapping global; quality/stat/signoff/selection/range per object). §3.1 ledger → Tasks 1,3,6. §3.2 OLS → Task 5. §3.3 scorecards per object → Task 2. §3.4 engine unchanged / consumers use `*_for` → Task 7. §3.5 master-data per object + adopted `verdicts` → Task 7. §3.6 heal migration → Task 8. §5 (channel ordering slice) → Task 8. Frontend selector/canvas (§4) is **out of scope here** — Phase 1 plan (only the type mirror is here, Task 9). E2E success criteria → Task 10.

**Placeholder scan:** the scorecard-builder steps (Task 2) reference "the existing CV/Pearson/VIF computation, unchanged" and Task 5 references "the existing scoring shape" — these are deliberate *preservation* instructions (do-not-touch the arithmetic), not missing code; the surrounding loop and row construction are given in full. The executor keeps the read-in numeric block verbatim inside the new per-object loop.

**Type consistency:** `OBJECT_ANY = "*"` used uniformly; `exclude_for`/`include_for`/`y_for` names consistent across Tasks 6–7; `signoff_key(l4, metric, object)` 3-arg form consistent Tasks 4→8; `funnel(st)` returns `{combined, byObject}` (Task 3) and every caller updated (Task 7, Task 9). `object` field name identical on `QualityRow`/`StatScoreRow`/`OlsXCandidate`/`LedgerRow`.

**Risk checkpoints:** after Tasks 2 and 7 run `_test_tools` (tool-identity invariant) and `_test_real` (real multi-channel fit). If either regresses, the tool layer or a consumer started re-deriving — revert, do not update expectations.
