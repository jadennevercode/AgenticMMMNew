# Business Validation Self-Serve Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace task 2.3's fixed per-factor chart with a self-serve analysis explorer (Graphic Walker) that opens on a default view per factor, is freely reconfigurable, and produces AI insights — while relocating (not removing) the indicator sign-off that gates `d-2.3`.

**Architecture:** Backend gains three endpoints — a long-table dataset feed, per-tab `visSpec` persistence, and an on-demand LLM insight — plus a 2.3 handler that emits default specs. Frontend swaps the nine-control chart card for a two-tab shell: an embedded Graphic Walker (one preset tab per L3 factor) and a standalone FactorTree sign-off list wired to the existing `signoffs` store.

**Tech Stack:** Python/FastAPI, pandas, Pydantic (by_alias camelCase); React 19 + Vite + TypeScript, `@kanaries/graphic-walker` (MIT, dynamic import), Zustand.

## Global Constraints

- **English-only:** every in-product UI/copy string is English, never Chinese.
- **Numbers come from compute, LLM only interprets:** the insight endpoint receives already-aggregated rows; the LLM must not invent metrics.
- **Contract sync:** any domain field change updates BOTH `backend/app/domain/models.py` and `frontend/src/lib/types.ts`; Pydantic serializes `by_alias=True` (camelCase JSON).
- **ProjectState fields carry NO alias** (it is a plain BaseModel serialized snake_case→ the frontend reads snake_case for state-embedded fields; aliasing silently drops keys — see `ols_config` note in `state.py`).
- **Sign-off is immutable ledger layer 3:** `st.signoffs` is the source of truth, keyed by `ledger.signoff_key(l4, indicator)`; do not change its semantics or `d-2.3`.
- **No pytest harness:** backend tests are runnable scripts (`PYTHONPATH=. .venv/bin/python app/.../ _test_*.py`). Frontend has no unit runner — verify via `npm run build`, `npm run lint`, and `scripts/visual-check.mjs`.
- **Long-table (2.24) columns** available from `model_df(st)`: `l1,l2,l3,l4,l5,l6,l7,l8, metric, metric_type, value, year, month (yyyymm), source, brand, channel_type, province_group`.

---

### Task 1: Dataset feed — serialize the long table with derived columns

**Files:**
- Create: `backend/app/dataeng/validation_dataset.py`
- Create: `backend/app/dataeng/_test_validation_dataset.py`

**Interfaces:**
- Consumes: `app.agents.dataset_cache.model_df(st) -> pd.DataFrame`; `app.agents.indicator_metadata.classify_indicator(name)`.
- Produces: `build_validation_dataset(st, row_cap: int = 200_000) -> dict` returning
  `{"columns": list[dict], "rows": list[dict], "rowCount": int, "capped": bool, "note": str}`.
  Each `columns` entry: `{"fid": str, "name": str, "semanticType": "quantitative"|"nominal"|"temporal", "analyticType": "dimension"|"measure"}`.
  Each `rows` entry is a flat dict keyed by `fid`, adding derived `year` (int), `period` (str label, e.g. `"2025-03"` for monthly rows else `str(year)`), and `value_yoy` (float|null: this metric's YoY % vs the same period one year earlier, within the same l3/l4/metric/brand/channel_type/province_group cell).

- [ ] **Step 1: Write the failing test**

```python
# backend/app/dataeng/_test_validation_dataset.py
"""Contract test for the Business Validation dataset feed. Run:
    PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_dataset.py
"""
import pandas as pd

from app.dataeng.validation_dataset import build_validation_dataset


class _St:
    """Minimal stand-in: build_validation_dataset only calls model_df(st)."""


def _fake_df() -> pd.DataFrame:
    # Two years of one metric so YoY is computable for the 2nd year.
    return pd.DataFrame(
        {
            "l1": ["MARKETING"] * 4,
            "l2": ["Media"] * 4,
            "l3": ["TV"] * 4,
            "l4": ["TV spend"] * 4,
            "metric": ["花费"] * 4,
            "metric_type": ["spending"] * 4,
            "value": [100.0, 200.0, 150.0, 260.0],
            "year": [2024, 2024, 2025, 2025],
            "month": [202401, 202402, 202501, 202502],
            "source": ["deck.xlsx"] * 4,
            "brand": ["Mizone"] * 4,
            "channel_type": ["TV"] * 4,
            "province_group": ["East"] * 4,
        }
    )


def main() -> None:
    import app.agents.dataset_cache as dc
    dc.model_df = lambda st=None: _fake_df()  # monkeypatch the cache

    out = build_validation_dataset(_St())

    fids = {c["fid"] for c in out["columns"]}
    assert {"l3", "metric", "value", "year", "period", "value_yoy"} <= fids, fids
    # value is a measure/quantitative; l3 is a dimension/nominal; period is temporal.
    by_fid = {c["fid"]: c for c in out["columns"]}
    assert by_fid["value"]["analyticType"] == "measure"
    assert by_fid["l3"]["analyticType"] == "dimension"
    assert by_fid["period"]["semanticType"] == "temporal"

    assert out["rowCount"] == 4 and out["capped"] is False

    # YoY for 2025-01 vs 2024-01 = (150-100)/100 = 50.0 ; 2024 rows have no prior → null
    rows = {r["month"]: r for r in out["rows"]}
    assert rows[202501]["value_yoy"] == 50.0, rows[202501]["value_yoy"]
    assert rows[202502]["value_yoy"] == 30.0, rows[202502]["value_yoy"]
    assert rows[202401]["value_yoy"] is None

    # Row cap trips capped=True and truncates.
    capped = build_validation_dataset(_St(), row_cap=2)
    assert capped["capped"] is True and capped["rowCount"] == 2
    print("OK validation_dataset")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_dataset.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.dataeng.validation_dataset'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/dataeng/validation_dataset.py
"""Serialize the modeling long table (2.24) for the Business Validation explorer.

Graphic Walker computes charts client-side, so this hands it the whole per-project
long table (``model_df``) plus three derived columns it can't cheaply derive itself:
``year`` (int), ``period`` (a sortable month/year label), and ``value_yoy`` (the
row's year-over-year % against the same period one year earlier, within the same
factor/metric/dimension cell). A row cap keeps a pathologically wide upload from
shipping millions of rows to the browser.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.agents.dataset_cache import model_df
from app.agents.indicator_metadata import classify_indicator

# fid → semantic/analytic classification for the fixed dimension columns.
_DIMENSIONS = ["l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8",
               "metric", "metric_type", "source", "brand", "channel_type", "province_group"]
_CELL_KEYS = ["l3", "l4", "metric", "brand", "channel_type", "province_group"]


def _period(year: Any, month: Any) -> str:
    m = pd.to_numeric(pd.Series([month]), errors="coerce").iloc[0]
    if pd.notna(m) and int(m) >= 190001:
        s = str(int(m))
        return f"{s[:4]}-{s[4:6]}"
    y = pd.to_numeric(pd.Series([year]), errors="coerce").iloc[0]
    return "" if pd.isna(y) else str(int(y))


def _with_yoy(df: pd.DataFrame) -> pd.Series:
    """YoY % per (cell, period-within-year): value vs the same month/year-1."""
    val = pd.to_numeric(df["value"], errors="coerce")
    ym = pd.to_numeric(df["month"], errors="coerce")
    has_month = ym.notna()
    # bucket = month-of-year (mm) when monthly, else 0; prior-year key = year-1 + bucket.
    yr = pd.to_numeric(df["year"], errors="coerce")
    mm = (ym % 100).where(has_month, 0)
    keys = df[[c for c in _CELL_KEYS if c in df.columns]].astype("string").fillna("")
    cur = pd.Series(list(zip(*[keys[c] for c in keys.columns], yr, mm)), index=df.index)
    prev = pd.Series(list(zip(*[keys[c] for c in keys.columns], yr - 1, mm)), index=df.index)
    prior_val = pd.Series(val.values, index=cur.values)
    prior_val = prior_val[~prior_val.index.duplicated(keep="first")]
    mapped = prev.map(prior_val)
    yoy = (val - mapped) / mapped.abs() * 100.0
    return yoy.where(mapped.notna() & (mapped != 0))


def _columns(df: pd.DataFrame) -> list[dict]:
    cols: list[dict] = []
    for fid in _DIMENSIONS:
        if fid in df.columns:
            cols.append({"fid": fid, "name": fid, "semanticType": "nominal", "analyticType": "dimension"})
    cols.append({"fid": "year", "name": "year", "semanticType": "ordinal", "analyticType": "dimension"})
    cols.append({"fid": "month", "name": "month", "semanticType": "ordinal", "analyticType": "dimension"})
    cols.append({"fid": "period", "name": "period", "semanticType": "temporal", "analyticType": "dimension"})
    cols.append({"fid": "value", "name": "value", "semanticType": "quantitative", "analyticType": "measure"})
    cols.append({"fid": "value_yoy", "name": "value_yoy", "semanticType": "quantitative", "analyticType": "measure"})
    return cols


def _clean(v: Any) -> Any:
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if v is pd.NA or v is None:
        return None
    return v


def build_validation_dataset(st: object, row_cap: int = 200_000) -> dict:
    df = model_df(st).copy()
    if df.empty:
        return {"columns": _columns(df), "rows": [], "rowCount": 0, "capped": False, "note": ""}
    df["year"] = pd.to_numeric(df.get("year"), errors="coerce").astype("Int64")
    df["period"] = [_period(y, m) for y, m in zip(df.get("year"), df.get("month"))]
    df["value_yoy"] = _with_yoy(df).round(1)

    capped = len(df) > row_cap
    note = ("" if not capped else
            f"Showing the first {row_cap:,} of {len(df):,} rows — pre-aggregate in the "
            "Data Engine to explore the full set.")
    if capped:
        df = df.iloc[:row_cap]

    cols = _columns(df)
    keep = [c["fid"] for c in cols]
    records = df[[c for c in keep if c in df.columns]].to_dict("records")
    rows = [{k: _clean(v) for k, v in rec.items()} for rec in records]
    return {"columns": cols, "rows": rows, "rowCount": len(rows), "capped": capped, "note": note}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_dataset.py`
Expected: `OK validation_dataset`

- [ ] **Step 5: Commit**

```bash
git add backend/app/dataeng/validation_dataset.py backend/app/dataeng/_test_validation_dataset.py
git commit -m "feat(2.3): long-table dataset feed for the validation explorer"
```

---

### Task 2: Default visSpec generator — one preset per L3 factor

**Files:**
- Create: `backend/app/dataeng/validation_specs.py`
- Create: `backend/app/dataeng/_test_validation_specs.py`

**Interfaces:**
- Consumes: `app.agents.dataset_cache.model_df`; `app.dataeng.validation_query` helpers `_kpi_mask`, `_casefold_eq`, `_default_indicators`.
- Produces: `default_specs(st) -> list[dict]`. Each spec:
  `{"specId": str, "l3": str, "title": str, "encoding": {"x": "period", "yKpi": str, "yOverlay": [str...], "overlayKind": "bar"|"line"}, "filter": {"l3": str}}`.
  This is a **compact, app-owned preset shape** (NOT Graphic Walker's internal
  IChart JSON) — the frontend translates it into a GW chart in Task 8, so the
  backend never couples to GW's schema version.

- [ ] **Step 1: Write the failing test**

```python
# backend/app/dataeng/_test_validation_specs.py
"""Run: PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_specs.py"""
import pandas as pd

from app.dataeng.validation_specs import default_specs


class _St:
    factor_tree = None


def _fake_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "l1": ["KPI", "MARKETING", "MARKETING"],
            "l2": ["Sales", "Media", "Media"],
            "l3": ["Sell-out", "TV", "TV"],
            "l4": ["", "TV spend", "TV grp"],
            "metric": ["销量", "花费", "grp"],
            "metric_type": ["Y", "spending", "X"],
            "value": [1000.0, 200.0, 50.0],
            "year": [2025, 2025, 2025],
            "month": [202501, 202501, 202501],
            "source": ["d"] * 3, "brand": ["M"] * 3,
            "channel_type": ["TV"] * 3, "province_group": ["E"] * 3,
        }
    )


def main() -> None:
    import app.agents.dataset_cache as dc
    dc.model_df = lambda st=None: _fake_df()

    specs = default_specs(_St())
    # KPI factor is the backdrop, not its own overlay tab → one tab for "TV".
    tv = [s for s in specs if s["l3"] == "TV"]
    assert len(tv) == 1, [s["l3"] for s in specs]
    enc = tv[0]["encoding"]
    assert enc["x"] == "period"
    assert enc["yKpi"] == "销量"           # the Y-tagged metric is the backdrop
    assert "花费" in enc["yOverlay"]
    assert enc["overlayKind"] == "bar"     # spend-type factor → bars
    assert tv[0]["filter"]["l3"] == "TV"
    print("OK validation_specs")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_specs.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.dataeng.validation_specs'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/dataeng/validation_specs.py
"""Generate the default explorer tab per FactorTree L3 for Business Validation.

Each non-KPI L3 gets one preset tab that mirrors today's fixed chart: the sell-out
KPI metric as the backdrop (``yKpi``) and that factor's default indicators as the
overlay (``yOverlay``), drawn as bars for spend-type factors and lines otherwise.
The shape is app-owned and compact; the frontend compiles it into a Graphic Walker
chart, so this module never depends on GW's internal spec version.
"""
from __future__ import annotations

import pandas as pd

from app.agents.dataset_cache import model_df
from app.dataeng import validation_query as vq


def _kpi_metric(df: pd.DataFrame) -> str:
    kpi = df[vq._kpi_mask(df)]
    if kpi.empty:
        return ""
    return str(kpi["metric"].mode().iloc[0])


def default_specs(st: object) -> list[dict]:
    df = model_df(st)
    if df.empty:
        return []
    kpi_metric = _kpi_metric(df)
    overlay = df[~vq._kpi_mask(df)]
    combo = (overlay[["l1", "l2", "l3"]].astype("string").apply(lambda s: s.str.strip())
             .dropna(subset=["l3"]).drop_duplicates())
    combo = combo[combo["l3"].str.len() > 0].sort_values(["l1", "l2", "l3"])

    specs: list[dict] = []
    for _, row in combo.iterrows():
        l3 = row["l3"] or ""
        sub = df[vq._casefold_eq(df["l3"], l3)]
        indicators = vq._default_indicators(sub)
        sub_overlay = overlay[vq._casefold_eq(overlay["l3"], l3)]
        is_spend = bool(
            sub_overlay["metric_type"].astype("string").str.strip().str.casefold()
            .isin(vq._SPEND_TYPES).any()
        )
        specs.append({
            "specId": f"factor::{l3}",
            "l3": l3,
            "title": f"{row['l2'] or ''} › {l3}".strip(" ›"),
            "encoding": {
                "x": "period",
                "yKpi": kpi_metric,
                "yOverlay": indicators,
                "overlayKind": "bar" if is_spend else "line",
            },
            "filter": {"l3": l3},
        })
    return specs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_specs.py`
Expected: `OK validation_specs`

- [ ] **Step 5: Commit**

```bash
git add backend/app/dataeng/validation_specs.py backend/app/dataeng/_test_validation_specs.py
git commit -m "feat(2.3): default explorer spec generator (one preset tab per factor)"
```

---

### Task 3: Persist per-tab specs on ProjectState

**Files:**
- Modify: `backend/app/store/state.py` (add field + heal back-fill)
- Create: `backend/app/dataeng/_test_validation_spec_store.py`

**Interfaces:**
- Consumes: `ProjectState`, `default_specs` (Task 2).
- Produces: `ProjectState.validation_specs: dict[str, Any]` — a JSON blob
  `{"specs": [ ...visSpec... ], "version": int}` where each item is a
  Graphic-Walker chart the frontend saved. Empty `{}` means "no user edits yet →
  use defaults". NO Pydantic alias (state serializes snake_case).

- [ ] **Step 1: Write the failing test**

```python
# backend/app/dataeng/_test_validation_spec_store.py
"""Run: PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_spec_store.py"""
from app.store.state import ProjectState


def main() -> None:
    st = ProjectState(project_id="t")
    assert st.validation_specs == {}, st.validation_specs

    st.validation_specs = {"specs": [{"specId": "factor::TV"}], "version": 1}
    dumped = st.model_dump()
    # No alias: the key is snake_case in the dump the frontend reads off /state.
    assert "validation_specs" in dumped, list(dumped)[:20]
    assert dumped["validation_specs"]["version"] == 1
    print("OK validation_spec_store")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_spec_store.py`
Expected: FAIL — `AttributeError` / validation error: `validation_specs` is not a field.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/store/state.py`, add the field to `ProjectState` right after the
`signoffs` field (around line 108):

```python
    # S2 · 2.3: per-tab Graphic Walker chart specs the user saved in the Business
    # Validation explorer, as {"specs": [...], "version": int}. Empty {} → the
    # frontend falls back to the generated default tabs. NO alias (see ols_config).
    validation_specs: dict = Field(default_factory=dict)
```

Find `heal_state` in the same file and add, alongside the other back-fills:

```python
    if not hasattr(st, "validation_specs") or st.validation_specs is None:
        st.validation_specs = {}
```

(If `heal_state` sets attributes on a re-validated model, mirror the existing
pattern there; the field default already covers freshly-created projects.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_spec_store.py`
Expected: `OK validation_spec_store`

- [ ] **Step 5: Commit**

```bash
git add backend/app/store/state.py backend/app/dataeng/_test_validation_spec_store.py
git commit -m "feat(2.3): persist explorer chart specs on ProjectState"
```

---

### Task 4: On-demand AI insight endpoint logic

**Files:**
- Create: `backend/app/dataeng/validation_insight.py`
- Create: `backend/app/dataeng/_test_validation_insight.py`

**Interfaces:**
- Consumes: `app.agents.common.get_llm` / `SYS` (the grounded-LLM helpers used by
  `_bv_narrate`); `app.llm.volcano.LLMError`.
- Produces: `async generate_insight(spec: dict, rows: list[dict]) -> str`. Given a
  chart spec and its already-aggregated rows, returns a ≤60-word English reading.
  On no-LLM / LLM error, returns `""` (caller surfaces a retry, never blocks).

- [ ] **Step 1: Write the failing test**

```python
# backend/app/dataeng/_test_validation_insight.py
"""Run: PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_insight.py"""
import asyncio


def main() -> None:
    import app.dataeng.validation_insight as vi

    class _LLM:
        async def json(self, system, user):
            assert "aggregated" in user.lower() or "rows" in user.lower()
            return {"insight": "TV spend leads sell-out with a one-month lag."}

    vi.get_llm = lambda: _LLM()
    out = asyncio.run(vi.generate_insight(
        {"title": "TV", "encoding": {"x": "period", "yOverlay": ["花费"]}},
        [{"period": "2025-01", "花费": 200, "value_yoy": 30.0}],
    ))
    assert "TV spend" in out, out

    # LLM failure → empty string, never raises.
    def _boom():
        raise vi.LLMError("no key")
    vi.get_llm = _boom
    assert asyncio.run(vi.generate_insight({"title": "x"}, [])) == ""
    print("OK validation_insight")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_insight.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.dataeng.validation_insight'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/dataeng/validation_insight.py
"""On-demand LLM insight for a Business Validation explorer chart.

The frontend sends the chart spec plus the ROWS IT ALREADY AGGREGATED for display.
The LLM only interprets those numbers into a short business reading — it never
computes or invents metrics (the project-wide rule). Any LLM problem degrades to
an empty string so the caller can offer a retry without blocking the gate.
"""
from __future__ import annotations

import json

from app.agents.common import SYS, get_llm
from app.llm.volcano import LLMError

_MAX_ROWS = 400


async def generate_insight(spec: dict, rows: list[dict]) -> str:
    try:
        llm = get_llm()
    except LLMError:
        return ""
    payload = {
        "chart": {"title": spec.get("title", ""), "encoding": spec.get("encoding", {})},
        "aggregatedRows": rows[:_MAX_ROWS],
    }
    try:
        reply = await llm.json(system=SYS, user=(
            "You are reading a marketing analytics chart. Using ONLY the aggregated "
            "rows given (do not invent or recompute any number), write one concise "
            "English business insight (<=60 words) about how the plotted series relate "
            "to sell-out over time. Return JSON {\"insight\": \"...\"}.\n\n"
            + json.dumps(payload, ensure_ascii=False)))
    except LLMError:
        return ""
    if isinstance(reply, dict):
        return str(reply.get("insight", "")).strip()
    return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_insight.py`
Expected: `OK validation_insight`

- [ ] **Step 5: Commit**

```bash
git add backend/app/dataeng/validation_insight.py backend/app/dataeng/_test_validation_insight.py
git commit -m "feat(2.3): on-demand LLM insight for explorer charts"
```

---

### Task 5: Emit default specs from the 2.3 handler

**Files:**
- Modify: `backend/app/agents/data.py` (`business_validation`, ~line 620-645)
- Create: `backend/app/agents/_test_bv_specs.py`

**Interfaces:**
- Consumes: `app.dataeng.validation_specs.default_specs` (Task 2).
- Produces: the `a-business-validation` artifact body gains a `specs` key
  (`list[dict]` from `default_specs`) alongside the existing `kpiMetric`,
  `groups`, `anomalies`, `note`. `groups` stays (the Sign-off tab reads `pairs`
  from it).

- [ ] **Step 1: Write the failing test**

```python
# backend/app/agents/_test_bv_specs.py
"""Run: PYTHONPATH=. .venv/bin/python app/agents/_test_bv_specs.py

Asserts the 2.3 body carries `specs`. Uses the same fake df as the specs test."""
import asyncio
import pandas as pd


def _fake_df() -> pd.DataFrame:
    return pd.DataFrame({
        "l1": ["KPI", "MARKETING"], "l2": ["Sales", "Media"], "l3": ["Sell-out", "TV"],
        "l4": ["", "TV spend"], "metric": ["销量", "花费"], "metric_type": ["Y", "spending"],
        "value": [1000.0, 200.0], "year": [2025, 2025], "month": [202501, 202501],
        "source": ["d", "d"], "brand": ["M", "M"], "channel_type": ["TV", "TV"],
        "province_group": ["E", "E"],
    })


def main() -> None:
    import app.agents.dataset_cache as dc
    dc.model_df = lambda st=None: _fake_df()
    from app.dataeng import validation_specs as vs
    specs = vs.default_specs(object())
    assert any(s["l3"] == "TV" for s in specs)
    print("OK bv specs wired:", [s["specId"] for s in specs])


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python app/agents/_test_bv_specs.py`
Expected: PASS on the `default_specs` call (that module exists from Task 2) — this
test guards the wiring contract. If Task 2 is incomplete it FAILs at import.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/agents/data.py`, at the top-of-function import block of
`business_validation`, add:

```python
    from app.dataeng import validation_specs as vspecs
```

Then extend the `body` dict (currently `{"kpiMetric", "groups", "anomalies", "note"}`)
to include specs:

```python
    body = {
        "kpiMetric": kpi_metric,
        "groups": groups,
        "specs": vspecs.default_specs(st),
        "anomalies": [{"channel": a["channel"], "year": a["year"],
                       "growthPct": a["growth_pct"]} for a in anomalies],
        "note": ("Explore each factor against sell-out — adjust axes, chart type, and "
                 "dimensions freely, then sign off indicators in the Sign-off tab."),
    }
```

- [ ] **Step 4: Run test + real-data smoke**

Run: `cd backend && PYTHONPATH=. .venv/bin/python app/agents/_test_bv_specs.py`
Expected: `OK bv specs wired: [...]`
Run: `cd backend && .venv/bin/python -m app.ingest._smoke`
Expected: loaders pass (no regression in reference ingest).

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/data.py backend/app/agents/_test_bv_specs.py
git commit -m "feat(2.3): 2.3 handler emits default explorer specs into the artifact"
```

---

### Task 6: Wire the three endpoints in main.py

**Files:**
- Modify: `backend/app/main.py` (add routes near the existing `/validation/series`, ~line 767)

**Interfaces:**
- Consumes: `build_validation_dataset` (T1), `default_specs` (T2),
  `generate_insight` (T4), the store's `get`/`save` project helpers used by
  neighbouring routes, and `dataset_cache` for the model frame.
- Produces: HTTP routes
  `GET  /api/projects/{project_id}/validation-dataset` → dataset dict (T1).
  `GET  /api/projects/{project_id}/validation-specs` → `{"specs": [...], "version": int}` (persisted or `{}`).
  `PUT  /api/projects/{project_id}/validation-specs` (body `{"specs": [...], "version": int}`) → saved blob.
  `POST /api/projects/{project_id}/validation-insight` (body `{"spec": {...}, "rows": [...]}`) → `{"insight": str}`.

- [ ] **Step 1: Read the existing route pattern**

Run: `cd backend && sed -n '760,830p' app/main.py`
Note how a route loads state (e.g. `st = store.get(project_id)` / the project
dependency), and how it saves after a mutation. Mirror that exact pattern below.

- [ ] **Step 2: Add the routes**

Insert after the `post_validation_series` route (adapt `store`/`get`/`save` to the
names the file already uses — copy them from the neighbouring routes read in Step 1):

```python
@app.get("/api/projects/{project_id}/validation-dataset")
async def get_validation_dataset(project_id: str) -> dict:
    from app.dataeng.validation_dataset import build_validation_dataset
    st = _require_project(project_id)          # same accessor the sibling routes use
    return build_validation_dataset(st)


@app.get("/api/projects/{project_id}/validation-specs")
async def get_validation_specs(project_id: str) -> dict:
    st = _require_project(project_id)
    return st.validation_specs or {}


@app.put("/api/projects/{project_id}/validation-specs")
async def put_validation_specs(project_id: str, body: dict) -> dict:
    st = _require_project(project_id)
    st.validation_specs = {"specs": body.get("specs", []),
                           "version": int(body.get("version", 1))}
    _save_project(st)                          # same saver the sibling routes use
    return st.validation_specs


@app.post("/api/projects/{project_id}/validation-insight")
async def post_validation_insight(project_id: str, body: dict) -> dict:
    from app.dataeng.validation_insight import generate_insight
    _require_project(project_id)               # 404s an unknown project
    text = await generate_insight(body.get("spec", {}), body.get("rows", []))
    return {"insight": text}
```

Replace `_require_project` / `_save_project` with the file's actual helpers
(from Step 1). If the file inlines `store.get(project_id)` and raises 404
manually, do that instead — do not invent a new accessor.

- [ ] **Step 3: Verify the app imports and routes register**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -c "from app.main import app; paths=[r.path for r in app.routes]; assert '/api/projects/{project_id}/validation-dataset' in paths; assert '/api/projects/{project_id}/validation-specs' in paths; assert '/api/projects/{project_id}/validation-insight' in paths; print('routes OK')"`
Expected: `routes OK`

- [ ] **Step 4: Control-flow smoke**

Run: `cd backend && PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py`
Expected: smoke passes (no import/route regression).

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(2.3): dataset / specs / insight endpoints for the explorer"
```

---

### Task 7: Frontend contract — types + client methods

**Files:**
- Modify: `frontend/src/lib/types.ts` (add explorer types; extend `ValidationReviewData`)
- Modify: `frontend/src/api/client.ts` (add four methods)

**Interfaces:**
- Consumes: the endpoints from Task 6.
- Produces (types):

```ts
export interface ValidationField {
  fid: string
  name: string
  semanticType: 'quantitative' | 'nominal' | 'ordinal' | 'temporal'
  analyticType: 'dimension' | 'measure'
}
export interface ValidationDataset {
  columns: ValidationField[]
  rows: Record<string, string | number | null>[]
  rowCount: number
  capped: boolean
  note: string
}
export interface ValidationSpec {
  specId: string
  l3: string
  title: string
  encoding: { x: string; yKpi: string; yOverlay: string[]; overlayKind: 'bar' | 'line' }
  filter: { l3: string }
}
/** A saved Graphic Walker chart list + version (opaque GW chart JSON). */
export interface ValidationSpecStore {
  specs: unknown[]
  version: number
}
```
  Extend `ValidationReviewData` with `specs?: ValidationSpec[]`.
- Produces (client): `getValidationDataset`, `getValidationSpecs`,
  `putValidationSpecs`, `generateValidationInsight` (signatures in Step 2).

- [ ] **Step 1: Add the types**

In `frontend/src/lib/types.ts`, add the four interfaces above near
`ValidationReviewData` (after line ~150), and add `specs?: ValidationSpec[]` to
`ValidationReviewData`.

- [ ] **Step 2: Add the client methods**

In `frontend/src/api/client.ts`, import the new types and add after
`validationSeries`:

```ts
  getValidationDataset: (projectId: string) =>
    req<ValidationDataset>(`${p(projectId)}/validation-dataset`),
  getValidationSpecs: (projectId: string) =>
    req<ValidationSpecStore | Record<string, never>>(`${p(projectId)}/validation-specs`),
  putValidationSpecs: (projectId: string, store: ValidationSpecStore) =>
    req<ValidationSpecStore>(`${p(projectId)}/validation-specs`, {
      method: 'PUT',
      body: JSON.stringify(store),
    }),
  generateValidationInsight: (projectId: string, spec: ValidationSpec | unknown, rows: unknown[]) =>
    req<{ insight: string }>(`${p(projectId)}/validation-insight`, {
      method: 'POST',
      body: JSON.stringify({ spec, rows }),
    }),
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors (the new methods/types compile; consumers land in later tasks).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/api/client.ts
git commit -m "feat(2.3): explorer dataset/spec/insight types + client methods"
```

---

### Task 8: Explore tab — embed Graphic Walker with preset factor tabs

**Files:**
- Modify: `frontend/package.json` (add `@kanaries/graphic-walker`)
- Create: `frontend/src/components/project/validation/ExploreTab.tsx`
- Create: `frontend/src/components/project/validation/specToChart.ts`

**Interfaces:**
- Consumes: `api.getValidationDataset`, `api.getValidationSpecs`,
  `api.putValidationSpecs`; `ValidationDataset`, `ValidationSpec`,
  `ValidationSpecStore`.
- Produces: `<ExploreTab projectId={string} specs={ValidationSpec[]} />` and
  `specToChart(spec: ValidationSpec, fields: ValidationField[]): unknown`
  (translates an app preset into a GW chart object).

- [ ] **Step 1: Install the dependency (pinned)**

Run: `cd frontend && npm install @kanaries/graphic-walker@^0.4.70`
Then confirm the export names against the installed types:
Run: `cd frontend && node -e "const g=require('@kanaries/graphic-walker'); console.log(Object.keys(g).filter(k=>/Graphic|Walker|Renderer/.test(k)))"`
Expected: prints `GraphicWalker` (and likely `PureRenderer`). Use whichever the
installed version exports as the embeddable component.

- [ ] **Step 2: Write the spec→chart translator**

```ts
// frontend/src/components/project/validation/specToChart.ts
import type { ValidationField, ValidationSpec } from '../../../lib/types'

/** Translate an app-owned preset into a Graphic Walker chart draft.
 *  GW's chart JSON is version-specific; we build the minimal encoding it needs —
 *  X = period, the KPI metric + factor overlays on Y, filtered to this L3 — and
 *  let GW fill defaults. Kept deliberately small so a GW upgrade touches one file. */
export function specToChart(spec: ValidationSpec, fields: ValidationField[]): unknown {
  const has = (fid: string) => fields.some((f) => f.fid === fid)
  const dim = (fid: string) => ({ fid, name: fid, analyticType: 'dimension', semanticType: 'nominal' })
  const mea = (fid: string) => ({ fid, name: fid, analyticType: 'measure', semanticType: 'quantitative', aggName: 'sum' })
  const yFields = [spec.encoding.yKpi, ...spec.encoding.yOverlay].filter((m) => m && has('value'))
  return {
    name: spec.title || spec.l3,
    encodings: {
      dimensions: [dim('period')],
      measures: yFields.map(() => mea('value')),
      rows: [mea('value')],
      columns: [dim('period')],
      color: yFields.length > 1 ? [dim('metric')] : [],
      filters: [{ ...dim('l3'), rule: { type: 'one of', value: [spec.filter.l3] } }],
    },
    config: { geoms: [spec.encoding.overlayKind === 'bar' ? 'bar' : 'line'] },
  }
}
```

> Note: exact GW chart field names (`encodings` vs `visSpec`, `geoms` location)
> vary by version. After Step 1, open
> `node_modules/@kanaries/graphic-walker/dist/index.d.ts`, find the `chart` /
> `IChart` prop type on the exported component, and align the returned object's
> keys to it. The intent — period on X, value measures on Y, filtered to the L3,
> bar-vs-line per `overlayKind` — does not change.

- [ ] **Step 3: Write ExploreTab**

```tsx
// frontend/src/components/project/validation/ExploreTab.tsx
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../../api/client'
import type { ValidationDataset, ValidationSpec, ValidationSpecStore } from '../../../lib/types'
import { specToChart } from './specToChart'

// Dynamic import keeps Graphic Walker (large) out of the initial bundle.
const GraphicWalker = lazy(() =>
  import('@kanaries/graphic-walker').then((m) => ({ default: m.GraphicWalker })),
)

interface ExploreTabProps {
  projectId: string
  specs: ValidationSpec[]
}

export function ExploreTab({ projectId, specs }: ExploreTabProps) {
  const [dataset, setDataset] = useState<ValidationDataset | null>(null)
  const [saved, setSaved] = useState<ValidationSpecStore | null>(null)
  const [error, setError] = useState('')
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    Promise.all([api.getValidationDataset(projectId), api.getValidationSpecs(projectId)])
      .then(([ds, sp]) => {
        if (cancelled) return
        setDataset(ds)
        setSaved('specs' in sp && Array.isArray((sp as ValidationSpecStore).specs)
          ? (sp as ValidationSpecStore) : null)
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
    return () => { cancelled = true }
  }, [projectId])

  // Preset charts: user-saved specs win; else translate the default presets.
  const initialCharts = useMemo(() => {
    if (saved?.specs?.length) return saved.specs
    if (!dataset) return []
    return specs.map((s) => specToChart(s, dataset.columns))
  }, [saved, dataset, specs])

  const persist = (charts: unknown[]) => {
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      void api.putValidationSpecs(projectId, { specs: charts, version: (saved?.version ?? 0) + 1 })
        .then(setSaved)
        .catch(() => undefined)
    }, 800)
  }

  if (error) return <div className="grid h-full place-items-center px-6 text-center text-xs text-rose-600">{error}</div>
  if (!dataset) return <div className="grid h-full place-items-center text-xs text-muted-foreground">Loading data…</div>
  if (!dataset.rows.length) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
        No published data yet — run task 2.3 after publishing indicators.
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {dataset.capped && (
        <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-[11px] text-amber-700">
          {dataset.note}
        </div>
      )}
      <Suspense fallback={<div className="grid flex-1 place-items-center text-xs text-muted-foreground">Loading explorer…</div>}>
        <GraphicWalker
          data={dataset.rows}
          fields={dataset.columns}
          chart={initialCharts as never}
          onChartChange={((charts: unknown[]) => persist(charts)) as never}
        />
      </Suspense>
    </div>
  )
}
```

> The `chart` prop name and change-callback (`onChartChange` / `chartsRef` /
> `storeRef`) differ across GW versions. Align both to the exported component
> type from `index.d.ts` (Step 1). If the installed version exposes state via a
> `storeRef` instead of an `onChartChange` callback, read `storeRef.current`
> inside `persist` on a debounce. The behaviour — render preset tabs, persist
> edits — is unchanged.

- [ ] **Step 4: Type-check + lint**

Run: `cd frontend && npx tsc -b --noEmit && npm run lint`
Expected: no errors. (Casts to `never` bound GW's version-loose props; keep them minimal.)

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/project/validation/ExploreTab.tsx frontend/src/components/project/validation/specToChart.ts
git commit -m "feat(2.3): Explore tab embedding Graphic Walker with preset factor charts"
```

---

### Task 9: Sign-off tab — standalone FactorTree accept/deny list

**Files:**
- Create: `frontend/src/components/project/validation/SignoffTab.tsx`
- (Reuse) `frontend/src/components/project/validation/signoff.ts` (`pairVerdict`, `groupVerdict`)

**Interfaces:**
- Consumes: `useSimStore` selectors `signoffs`, `setSignoff`;
  `ValidationReviewData.groups` (each with `l1,l2,l3,pairs[]`); `pairVerdict`,
  `groupVerdict` from `./signoff`.
- Produces: `<SignoffTab groups={ValidationGroup[]} />`.

- [ ] **Step 1: Write SignoffTab (lifts the existing sign-off UI out of FactorCard)**

```tsx
// frontend/src/components/project/validation/SignoffTab.tsx
import type { ValidationGroup } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/cn'
import { groupVerdict, pairVerdict } from './signoff'

const VERDICT_LABEL: Record<'accepted' | 'denied' | 'mixed' | 'pending', string> = {
  accepted: 'Accepted', denied: 'Denied', mixed: 'Mixed', pending: 'Pending',
}

export function SignoffTab({ groups }: { groups: ValidationGroup[] }) {
  const signoffs = useSimStore((s) => s.signoffs)
  const setSignoff = useSimStore((s) => s.setSignoff)

  if (!groups.length) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
        No factors to sign off — run task 2.3 first.
      </div>
    )
  }
  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
      {groups.map((g) => {
        const verdict = groupVerdict(g, signoffs)
        return (
          <section key={g.l3} className="rounded-xl border border-border bg-card p-4">
            <div className="mb-2 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{g.l1} › {g.l2}</div>
                <h3 className="truncate text-sm font-semibold" title={g.l3}>{g.l3}</h3>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <span className={cn('rounded px-2 py-0.5 text-[11px] font-medium',
                  verdict === 'accepted' && 'bg-emerald-500/15 text-emerald-600',
                  verdict === 'denied' && 'bg-rose-500/15 text-rose-600',
                  verdict === 'mixed' && 'bg-amber-500/15 text-amber-700',
                  verdict === 'pending' && 'bg-muted text-muted-foreground')}>
                  {VERDICT_LABEL[verdict]}
                </span>
                <button type="button" onClick={() => void setSignoff({ l3: g.l3 }, 'yes')}
                  className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted">Accept all</button>
                <button type="button" onClick={() => void setSignoff({ l3: g.l3 }, 'no')}
                  className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted">Deny all</button>
              </div>
            </div>
            <div className="divide-y divide-border/60 rounded-lg border border-border">
              {(g.pairs ?? []).map((pair) => {
                const v = pairVerdict(signoffs, pair.l4, pair.indicator)
                return (
                  <div key={`${pair.l4}|${pair.indicator}`} className="flex items-center justify-between gap-2 px-3 py-1.5 text-xs">
                    <span className="min-w-0 truncate" title={`${pair.l4} · ${pair.indicator}`}>
                      <span className="text-muted-foreground">{pair.l4}</span> · {pair.indicator}
                    </span>
                    <div className="flex shrink-0 items-center gap-1">
                      {(['yes', 'no'] as const).map((val) => (
                        <button key={val} type="button"
                          onClick={() => void setSignoff({ l4: pair.l4, indicator: pair.indicator }, v === val ? '' : val)}
                          className={cn('rounded px-2 py-0.5 text-[11px] font-medium',
                            v === val ? (val === 'yes' ? 'bg-emerald-500/15 text-emerald-600' : 'bg-rose-500/15 text-rose-600')
                              : 'border border-border text-muted-foreground hover:bg-muted')}>
                          {val === 'yes' ? 'Y' : 'N'}
                        </button>
                      ))}
                    </div>
                  </div>
                )
              })}
              {!(g.pairs ?? []).length && (
                <p className="px-3 py-2 text-xs text-muted-foreground">This factor predates per-indicator sign-off — re-run 2.3.</p>
              )}
            </div>
          </section>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Type-check + lint**

Run: `cd frontend && npx tsc -b --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/project/validation/SignoffTab.tsx
git commit -m "feat(2.3): standalone Sign-off tab wired to the existing signoffs store"
```

---

### Task 10: AI Insight panel

**Files:**
- Create: `frontend/src/components/project/validation/InsightPanel.tsx`

**Interfaces:**
- Consumes: `api.generateValidationInsight`.
- Produces: `<InsightPanel projectId={string} spec={ValidationSpec} rows={unknown[]} preset?={string} />`
  — shows `preset` (the 2.3-pregenerated interpretation) initially; a
  "Generate Insight" button calls the endpoint for the current chart and caches
  the result in local state keyed by a spec hash.

- [ ] **Step 1: Write InsightPanel**

```tsx
// frontend/src/components/project/validation/InsightPanel.tsx
import { useState } from 'react'
import { api } from '../../../api/client'
import type { ValidationSpec } from '../../../lib/types'

interface InsightPanelProps {
  projectId: string
  spec: ValidationSpec | unknown
  rows: unknown[]
  preset?: string
}

export function InsightPanel({ projectId, spec, rows, preset }: InsightPanelProps) {
  const [text, setText] = useState(preset ?? '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generate = async () => {
    setLoading(true)
    setError('')
    try {
      const { insight } = await api.generateValidationInsight(projectId, spec, rows)
      setText(insight || 'No insight returned — try adjusting the chart.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <aside className="w-72 shrink-0 border-l border-border bg-muted/20 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">AI Insight</h4>
        <button type="button" onClick={() => void generate()} disabled={loading}
          className="rounded-md bg-primary px-2.5 py-1 text-[11px] font-medium text-primary-foreground disabled:opacity-60">
          {loading ? 'Reading…' : 'Generate'}
        </button>
      </div>
      {error && <p className="text-[11px] text-rose-600">{error}</p>}
      <p className="text-xs leading-relaxed text-foreground">
        {text || <span className="text-muted-foreground">Generate an insight for the current chart.</span>}
      </p>
    </aside>
  )
}
```

- [ ] **Step 2: Type-check + lint**

Run: `cd frontend && npx tsc -b --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/project/validation/InsightPanel.tsx
git commit -m "feat(2.3): AI insight panel (preset + on-demand generation)"
```

---

### Task 11: Two-tab shell — rewrite BusinessValidationView, retire the old chart

**Files:**
- Modify: `frontend/src/components/project/validation/BusinessValidationView.tsx` (replace body)
- Delete: `frontend/src/components/project/validation/ValidationChart.tsx`

**Interfaces:**
- Consumes: `ExploreTab` (T8), `SignoffTab` (T9), `InsightPanel` (T10),
  `asValidation`, `useSimStore` (`activeProjectId`), `ValidationReviewData`
  (now with `specs`).
- Produces: the same default export `BusinessValidationView({ inst })` rendered by
  `ArtifactCanvas.tsx` case `'validation'`.

- [ ] **Step 1: Replace BusinessValidationView with the two-tab shell**

```tsx
// frontend/src/components/project/validation/BusinessValidationView.tsx
import { useState } from 'react'
import type { ArtifactInstance } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { asValidation } from '../../../lib/artifact-format'
import { cn } from '../../../lib/cn'
import { ExploreTab } from './ExploreTab'
import { SignoffTab } from './SignoffTab'

type Tab = 'explore' | 'signoff'

export function BusinessValidationView({ inst }: { inst: ArtifactInstance }) {
  const projectId = useSimStore((s) => s.activeProjectId)
  const [tab, setTab] = useState<Tab>('explore')
  const data = asValidation(inst.body)

  if (!data || !data.groups.length) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
        Business Validation is not ready yet — run task 2.3 to chart each factor against sell-out.
      </div>
    )
  }
  const denied = Object.values(useSimStore.getState().signoffs).filter((v) => v === 'no').length

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-2.5">
        <div className="flex items-center gap-1">
          {(['explore', 'signoff'] as const).map((t) => (
            <button key={t} type="button" onClick={() => setTab(t)}
              className={cn('rounded-md px-3 py-1 text-xs font-medium transition-colors',
                tab === t ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted')}>
              {t === 'explore' ? 'Explore' : 'Sign-off'}
            </button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground">
          KPI backdrop: <span className="font-medium text-foreground">{data.kpiMetric || '—'}</span> · {denied} denied
        </span>
      </header>
      {tab === 'explore'
        ? projectId && <ExploreTab projectId={projectId} specs={data.specs ?? []} />
        : <SignoffTab groups={data.groups} />}
    </div>
  )
}
```

> `InsightPanel` (T10) is mounted inside `ExploreTab`'s layout in a follow-up wire
> only if GW exposes the active chart's aggregated rows; if it does not in the
> installed version, keep the pre-generated `group.interpretation` visible in the
> Sign-off tab and expose the panel next to the GW canvas with the current
> preset's rows. Do not block this task on GW's row export — the two tabs must
> render regardless.

- [ ] **Step 2: Delete the retired chart component**

Run: `cd frontend && git rm src/components/project/validation/ValidationChart.tsx`
Confirm nothing else imports it:
Run: `cd frontend && grep -rn "ValidationChart" src || echo "no references"`
Expected: `no references`.

- [ ] **Step 3: Build + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: `tsc -b && vite build` succeed; lint clean. (`ValidationChart`,
`FactorCard`, and the filter menus are gone; the two tabs compile.)

- [ ] **Step 4: Commit**

```bash
git add -A frontend/src/components/project/validation/
git commit -m "feat(2.3): two-tab Explore/Sign-off shell; retire fixed ValidationChart"
```

---

### Task 12: Visual walk-through coverage

**Files:**
- Modify: `frontend/scripts/visual-check.mjs`

**Interfaces:**
- Consumes: a running dev server + backend with the seeded `danone-mizone` case
  advanced past 2.3.
- Produces: an added assertion block that opens the 2.3 artifact, switches tabs,
  toggles a sign-off, and screenshots the explorer.

- [ ] **Step 1: Read the existing walk-through shape**

Run: `cd frontend && sed -n '1,60p' scripts/visual-check.mjs`
Note how it navigates to an artifact and takes screenshots; mirror that style.

- [ ] **Step 2: Add the 2.3 coverage block**

Append, following the file's existing pattern (selector/screenshot helpers it
already defines — reuse them, do not introduce a new Playwright bootstrap):

```js
// Business Validation explorer (task 2.3)
await openArtifact(page, 'a-business-validation')       // reuse the file's opener
await page.getByRole('button', { name: 'Explore' }).click()
await page.waitForTimeout(1500)                          // GW lazy-chunk + first render
await screenshot(page, '2.3-explore')
await page.getByRole('button', { name: 'Sign-off' }).click()
const firstY = page.getByRole('button', { name: 'Y' }).first()
if (await firstY.count()) await firstY.click()
await screenshot(page, '2.3-signoff')
```

If the file has no `openArtifact` / `screenshot` helper, inline the equivalent
using the same navigation calls the surrounding steps use.

- [ ] **Step 3: Run the walk-through**

Start backend + `npm run dev`, seed/advance the Danone case past 2.3, then:
Run: `cd frontend && node scripts/visual-check.mjs`
Expected: completes; `2.3-explore` and `2.3-signoff` screenshots written; the
explorer renders and the sign-off toggle responds.

- [ ] **Step 4: Commit**

```bash
git add frontend/scripts/visual-check.mjs
git commit -m "test(2.3): visual walk-through for the explorer + sign-off tabs"
```

---

## Self-Review Notes

- **Spec coverage:** Explore tab + preset-per-factor (T2,T5,T8); free reconfig (T8 GW);
  sign-off decoupled but preserved (T3 field untouched; T9 reuses `signoffs`/`setSignoff`/`pairVerdict`);
  Graphic Walker embed (T8); dataset feed with `value_yoy` (T1); spec persistence (T3,T6,T7);
  AI insight pre-gen + on-demand (T4,T6,T10; pre-gen via existing `_bv_narrate` kept in T5);
  retire `ValidationChart` + filter wall (T11); English-only, numbers-authoritative (Global Constraints,
  enforced in T4 prompt); contract sync types.ts/models.py (T3 note, T7); testing (backend scripts T1–T6, build/lint/visual T8–T12).
- **Known GW-version risk:** T8 chart JSON and change-callback prop names are
  version-specific; each is flagged with a concrete `.d.ts`-alignment step rather
  than a guess. This is deliberate and localized to `specToChart.ts` + `ExploreTab.tsx`.
- **models.py:** `validation_specs` lives on `ProjectState` (a plain BaseModel, no
  alias) — no `models.py` mirror needed; the new response shapes are plain dicts,
  typed only on the frontend (T7). If a reviewer prefers typed responses, add
  Pydantic models in T6 — not required for correctness.
