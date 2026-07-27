# Factor Tree as the Indicator source of truth — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the confirmed Business-Understanding Factor Tree the single definition of the indicators the Data module and Data Engine collect, so an indicator exists the moment a factor is confirmed rather than being manufactured from published data; and replace the silent character caps on S1 grounding material with one budget plus visible truncation.

**Architecture:** `Indicator` becomes a *derived projection* of `FactorTree` rather than a stored entity. The only thing publish persists is an `IndicatorCoverage` record — "this asset's metric supplies this factor row". Everything the UI reads (`GET /indicators`, the 2.1 factor map) is derived from `factor_tree × indicator_coverage`, so the two views cannot disagree. This follows the rule `app/agents/ledger.py` already establishes: derive, don't store.

**Tech Stack:** Python 3 / FastAPI / Pydantic v2 (`CamelModel`, `by_alias=True`), pandas, DuckDB + dbt Fusion; React 19 + TypeScript + Zustand on the front end.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-26-factor-tree-as-indicator-source-design.md`.
- Tests in this repo are **runnable scripts, not pytest**. Add to the existing
  `app/**/_test_*.py` pattern and run with
  `PYTHONPATH=. .venv/bin/python -m app.<pkg>._test_<name>`. A test returns `0`
  from `main()` on success, non-zero on failure.
- `ProjectState` is a plain `BaseModel` — **never alias its own fields**, or
  `/state` emits a key the frontend silently misses.
- Domain models that cross the API are `CamelModel` and serialize `by_alias=True`.
  Any field added to one must be mirrored in `frontend/src/lib/types.ts`.
- All in-product UI strings are **English**.
- Numbers must not move. `app/tools/_test_tools.py`, `app/agents/_test_ledger_*.py`
  and `app/agents/_test_master_data.py` must pass unchanged throughout; the ledger
  keys on `(norm_l4, norm_metric)`, not on `indicator.id`, so this refactor should
  be invisible to it. If a ledger test moves, the derivation is wrong — fix the
  derivation, not the expectation.
- Working branch: `feat/global-model-config` (current). Commit per task.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/domain/models.py` | add `IndicatorCoverage`; widen `FactorSource` / `IndicatorSource` |
| `backend/app/store/state.py` | add `indicator_coverage`; drain legacy `indicators` in `heal_state` |
| `backend/app/dataeng/indicators.py` **(new)** | the derivation — factor tree × coverage → `list[Indicator]` |
| `backend/app/dataeng/dbt/service.py` | publish *claims* a factor row instead of creating indicators |
| `backend/app/dataeng/mapping.py` | factor map reads coverage records |
| `backend/app/dataeng/mapping_suggest.py` | suggest/bind operate on orphan coverages |
| `backend/app/dataeng/mapping_auto.py` | auto-resolve candidates are orphans |
| `backend/app/dataeng/orphans.py` **(new)** | accept an orphan into the factor tree |
| `backend/app/main.py` | `/indicators` derives; new `/indicators/orphans/adopt` |
| `backend/app/agents/common.py`, `app/config.py`, `app/agents/business.py`, `app/store/files.py` | Part B — one grounding budget, visible truncation |
| `frontend/src/lib/types.ts`, `components/dataeng/IndicatorCatalogPanel.tsx` | render declared vs orphan; empty state |

---

### Task 1: `IndicatorCoverage` model + state field

Additive only — nothing reads it yet, so this cannot break a running project.

**Files:**
- Modify: `backend/app/domain/models.py` (near `Indicator`, line ~1119)
- Modify: `backend/app/store/state.py:147`
- Modify: `frontend/src/lib/types.ts`
- Test: `backend/app/dataeng/_test_indicators.py` (create)

**Interfaces:**
- Produces: `IndicatorCoverage` (all fields below); `ProjectState.indicator_coverage: list[IndicatorCoverage]`; `FactorSource` gains `"data_upload"`; `IndicatorSource` gains `"manual"`.

- [ ] **Step 1: Write the failing test**

Create `backend/app/dataeng/_test_indicators.py`:

```python
"""Derivation tests: the factor tree is the indicator catalog.

Run: ``PYTHONPATH=. .venv/bin/python -m app.dataeng._test_indicators``
"""
from __future__ import annotations

from app.domain.models import FactorRow, FactorTree, IndicatorCoverage
from app.store.state import ProjectState


def _st() -> ProjectState:
    st = ProjectState(project_id="_t")
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-1", l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视",
                  indicator="TV投放金额", source="template", status="baseline"),
        FactorRow(id="ft-2", l1="KPI", l2="", l3="", l4="",
                  indicator="本品销量", source="ai", status="accepted"),
        FactorRow(id="ft-3", l1="MARKETING FACTOR", l2="DIGITAL", l3="EC", l4="天猫",
                  indicator="电商投放金额", source="interview", status="rejected"),
    ])
    return st


def test_coverage_model_defaults() -> None:
    c = IndicatorCoverage(id="cov-1", asset_id="a1", asset_name="Sales", metric="TV投放金额")
    assert c.tree_row_id == "", "an unclaimed coverage is an orphan"
    assert c.bound_by == ""
    assert c.rows == 0


def test_state_carries_coverage() -> None:
    st = _st()
    assert st.indicator_coverage == []
    st.indicator_coverage.append(
        IndicatorCoverage(id="cov-1", tree_row_id="ft-1", asset_id="a1",
                          asset_name="Sales", metric="TV投放金额", bound_by="auto"))
    # ProjectState must round-trip without aliasing its own fields.
    dumped = st.model_dump()
    assert "indicator_coverage" in dumped, "ProjectState fields are snake_case, unaliased"
    assert dumped["indicator_coverage"][0]["tree_row_id"] == "ft-1"


def main() -> int:
    for fn in (test_coverage_model_defaults, test_state_carries_coverage):
        fn()
        print(f"ok  {fn.__name__}")
    print("all indicator derivation tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.dataeng._test_indicators`
Expected: FAIL — `ImportError: cannot import name 'IndicatorCoverage'`

- [ ] **Step 3: Add the model**

In `backend/app/domain/models.py`, widen the two source enums (line 403 and 1119):

```python
FactorSource = Literal["template", "ai", "interview", "manual", "upload", "data_upload"]
```

```python
IndicatorSource = Literal[
    "project_material", "interview", "uploaded_tree", "template", "ai",
    "manual", "data_upload"]
```

Then, immediately after `class Indicator`, add:

```python
class IndicatorCoverage(CamelModel):
    """One published (asset × metric) supplying one factor-tree row.

    This is the ONLY thing publish persists. `Indicator` itself is derived from
    the factor tree (see app/dataeng/indicators.py) — a stored catalog eventually
    disagrees with the tree it was copied from, which is exactly the drift this
    replaces.

    `tree_row_id == ""` marks an **orphan**: a metric the data supplies that no
    factor row asked for. Orphans are listed apart and can be proposed back into
    the tree; they are never silently presented as project indicators.
    """
    id: str                 # stable across re-publish — see service._indicator_id
    tree_row_id: str = Field(default="", alias="treeRowId")
    asset_id: str = Field(default="", alias="assetId")
    asset_name: str = Field(default="", alias="assetName")
    # The mart's own labels. They may differ from the factor row's wording — that
    # difference is the point of a mapping, so both sides are kept.
    metric: str = ""
    metric_type: str = Field(default="", alias="metricType")
    l1: str = ""
    l2: str = ""
    l3: str = ""
    l4: str = ""
    semantic_type: MetricType = Field(default="other", alias="semanticType")
    unit: str = ""
    currency: Optional[str] = None
    aggregation: Aggregation = "sum"
    number_format: str = Field(default="number", alias="numberFormat")
    rule_version: str = Field(default="", alias="ruleVersion")
    coverage_start: str = Field(default="", alias="coverageStart")
    coverage_end: str = Field(default="", alias="coverageEnd")
    rows: int = 0
    # "human" is a decision and survives re-publish; "auto" is re-derived each time.
    bound_by: Literal["", "auto", "human"] = Field(default="", alias="boundBy")
```

- [ ] **Step 4: Add the state field**

In `backend/app/store/state.py`, directly under `indicators` (line 147):

```python
    # LEGACY (drained by heal_state): indicators used to be stored here, built by
    # groupby over each published mart. They are now derived from the factor tree.
    # The field stays only so a saved project's human bindings can be migrated —
    # Pydantic drops unknown keys on load, so removing it outright would destroy
    # them before the migration could run. heal_state empties it.
    indicators: list[Indicator] = Field(default_factory=list, alias="indicators")
    # What publish persists: which (asset × metric) supplies which factor row.
    indicator_coverage: list[IndicatorCoverage] = Field(default_factory=list)
```

Import `IndicatorCoverage` in the models import block at the top of the file.

- [ ] **Step 5: Mirror in frontend types**

In `frontend/src/lib/types.ts`, beside `Indicator`:

```ts
export interface IndicatorCoverage {
  id: string
  treeRowId: string
  assetId: string
  assetName: string
  metric: string
  metricType: string
  l1: string
  l2: string
  l3: string
  l4: string
  semanticType: string
  unit: string
  currency: string | null
  aggregation: string
  numberFormat: string
  ruleVersion: string
  coverageStart: string
  coverageEnd: string
  rows: number
  boundBy: '' | 'auto' | 'human'
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.dataeng._test_indicators`
Expected: PASS — both tests print `ok`.

Also run `cd frontend && npm run build` — expect it to succeed (types are additive).

- [ ] **Step 7: Commit**

```bash
git add backend/app/domain/models.py backend/app/store/state.py \
        backend/app/dataeng/_test_indicators.py frontend/src/lib/types.ts
git commit -m "feat(dataeng): IndicatorCoverage model + state field

Additive. Publish will persist coverage records instead of manufacturing
indicators; Indicator becomes a projection of the factor tree. FactorSource
gains data_upload (orphan adoption) and IndicatorSource gains manual, so the
two enums can be reconciled by an explicit map."
```

---

### Task 2: The derivation — factor tree × coverage → indicators

The heart of the change. Pure function, no I/O, fully testable without dbt.

**Files:**
- Create: `backend/app/dataeng/indicators.py`
- Modify: `backend/app/dataeng/_test_indicators.py`

**Interfaces:**
- Consumes: `IndicatorCoverage`, `ProjectState.indicator_coverage` (Task 1).
- Produces:
  - `SOURCE_MAP: dict[str, str]` — `FactorSource` → `IndicatorSource`
  - `declared_indicators(st) -> list[Indicator]`
  - `orphan_indicators(st) -> list[Indicator]`
  - `derive_indicators(st) -> list[Indicator]` (declared + orphans)
  - `coverages_for(st, tree_row_id) -> list[IndicatorCoverage]`
  - `primary_coverage(st, tree_row_id) -> IndicatorCoverage | None`
  - `ACTIVE_STATUSES: tuple[str, ...]`

- [ ] **Step 1: Write the failing tests**

Append to `backend/app/dataeng/_test_indicators.py` (and add the new names to `main()`'s tuple):

```python
def test_declared_one_per_active_row() -> None:
    st = _st()
    from app.dataeng import indicators as ind

    got = ind.declared_indicators(st)
    assert [i.id for i in got] == ["ind-ft-1", "ind-ft-2"], \
        f"rejected rows are not data targets; got {[i.id for i in got]}"
    tv = got[0]
    assert tv.metric == "TV投放金额"
    assert (tv.l1, tv.l2, tv.l3, tv.l4) == ("MARKETING FACTOR", "ATL", "TV", "卫视")
    assert tv.tree_row_id == "ft-1"
    assert tv.tree_grounded is True
    assert tv.source == "template", "declared source follows the factor row"
    assert tv.asset_id == "" and tv.coverage_start == "", "no data yet"
    assert got[1].source == "ai"


def test_source_map_covers_every_factor_source() -> None:
    from app.domain.models import FactorSource
    from app.dataeng import indicators as ind
    import typing

    for v in typing.get_args(FactorSource):
        assert v in ind.SOURCE_MAP, f"FactorSource {v!r} has no IndicatorSource"


def test_coverage_fills_the_declared_row() -> None:
    st = _st()
    from app.dataeng import indicators as ind

    st.indicator_coverage.append(IndicatorCoverage(
        id="cov-1", tree_row_id="ft-1", asset_id="a1", asset_name="TV spend",
        metric="CCTV投放金额", metric_type="spending", unit="元",
        coverage_start="202201", coverage_end="202412", rows=36, bound_by="auto"))

    tv = next(i for i in ind.declared_indicators(st) if i.id == "ind-ft-1")
    assert tv.asset_id == "a1" and tv.asset_name == "TV spend"
    assert tv.coverage_start == "202201" and tv.coverage_end == "202412"
    assert tv.rows == 36
    assert tv.unit == "元"
    assert tv.metric == "TV投放金额", "the factor's own wording stays the label"
    assert tv.source == "data_upload", "a supplied factor reports as supplied"


def test_human_pin_is_the_primary_coverage() -> None:
    st = _st()
    from app.dataeng import indicators as ind

    st.indicator_coverage.extend([
        IndicatorCoverage(id="c-auto", tree_row_id="ft-1", asset_id="a1",
                          asset_name="Auto", metric="m1", rows=99, bound_by="auto"),
        IndicatorCoverage(id="c-human", tree_row_id="ft-1", asset_id="a2",
                          asset_name="Human", metric="m2", rows=1, bound_by="human"),
    ])
    prim = ind.primary_coverage(st, "ft-1")
    assert prim is not None and prim.id == "c-human", \
        "a human pin outranks a bigger auto match"
    assert len(ind.coverages_for(st, "ft-1")) == 2, "multi-source coverage is kept"


def test_orphans_are_separate_and_not_declared() -> None:
    st = _st()
    from app.dataeng import indicators as ind

    st.indicator_coverage.append(IndicatorCoverage(
        id="c-orph", tree_row_id="", asset_id="a1", asset_name="Sales",
        metric="仓库库存", l3="LOGISTICS", rows=12))

    assert [i.id for i in ind.declared_indicators(st)] == ["ind-ft-1", "ind-ft-2"]
    orph = ind.orphan_indicators(st)
    assert [i.id for i in orph] == ["c-orph"]
    assert orph[0].tree_grounded is False
    assert orph[0].source == "data_upload"
    assert len(ind.derive_indicators(st)) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.dataeng._test_indicators`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.dataeng.indicators'`

- [ ] **Step 3: Write the derivation**

Create `backend/app/dataeng/indicators.py`:

```python
"""The indicator catalog, derived from the factor tree.

The Business-Understanding factor tree defines what data this project must
collect. An `Indicator` is therefore a *projection* of an active factor row, not
an entity the data manufactures: it exists the moment the tree is confirmed, and
publishing data attaches an `IndicatorCoverage` to it rather than creating a
second, parallel list that drifts.

Nothing here is stored. Persisted state is only `factor_tree` (the definition)
and `indicator_coverage` (which asset's metric supplies which row) — the same
derive-don't-store rule `app/agents/ledger.py` follows, for the same reason.
"""
from __future__ import annotations

from app.domain.models import Indicator, IndicatorCoverage
from app.store.state import ProjectState

# A row only becomes a data target once it is confirmed. `proposed` is excluded
# here for the same reason mapping._ACTIVE_STATUSES excludes it: an unreviewed AI
# or interview suggestion is not yet something the client owes us data for.
ACTIVE_STATUSES = ("baseline", "accepted")

# The two enums were defined independently and do not share a value space.
SOURCE_MAP: dict[str, str] = {
    "template": "template",
    "ai": "ai",
    "interview": "interview",
    "manual": "manual",
    "upload": "uploaded_tree",
    "data_upload": "data_upload",
}


def active_rows(st: ProjectState) -> list:
    ft = getattr(st, "factor_tree", None)
    if ft is None:
        return []
    return [r for r in ft.rows if r.status in ACTIVE_STATUSES]


def coverages_for(st: ProjectState, tree_row_id: str) -> list[IndicatorCoverage]:
    """Every published (asset × metric) supplying this row.

    A factor may legitimately be supplied by more than one source — TV spend split
    across two files is routine — so this is a list, not an Optional.
    """
    if not tree_row_id:
        return []
    return [c for c in (getattr(st, "indicator_coverage", None) or [])
            if c.tree_row_id == tree_row_id]


def primary_coverage(st: ProjectState, tree_row_id: str) -> IndicatorCoverage | None:
    """The coverage that represents the row in flat, single-value views.

    A human pin wins outright — it is a decision, and a bigger automatic match is
    not a reason to overrule it. Otherwise the widest series wins.
    """
    covs = coverages_for(st, tree_row_id)
    if not covs:
        return None
    pinned = [c for c in covs if c.bound_by == "human"]
    return (pinned or sorted(covs, key=lambda c: -c.rows))[0]


def _declared(st: ProjectState, row, cov: IndicatorCoverage | None) -> Indicator:
    """One active factor row projected to an Indicator, filled in by its coverage."""
    return Indicator(
        id=f"ind-{row.id}",
        # The factor's own wording is the label — the mart's metric name lives on
        # the coverage record, so a rename in the data never renames the factor.
        metric=row.indicator or row.l4,
        metricType=(cov.metric_type if cov else ""),
        l1=row.l1, l2=row.l2, l3=row.l3, l4=row.l4,
        semanticType=(cov.semantic_type if cov else "other"),
        unit=(cov.unit if cov else ""),
        currency=(cov.currency if cov else None),
        aggregation=(cov.aggregation if cov else "sum"),
        numberFormat=(cov.number_format if cov else "number"),
        ruleVersion=(cov.rule_version if cov else ""),
        # Supplied rows report as data; unsupplied ones keep their provenance so
        # the catalog reads as "this is why we are asking for it".
        source=("data_upload" if cov else SOURCE_MAP.get(row.source, "template")),
        assetId=(cov.asset_id if cov else ""),
        assetName=(cov.asset_name if cov else ""),
        coverageStart=(cov.coverage_start if cov else ""),
        coverageEnd=(cov.coverage_end if cov else ""),
        rows=(cov.rows if cov else 0),
        treeGrounded=True,
        treeRowId=row.id,
        boundBy=(cov.bound_by if cov else ""),
    )


def _orphan(cov: IndicatorCoverage) -> Indicator:
    """A supplied metric no factor row asked for.

    Kept visibly apart from declared indicators: presenting it as one is how a
    data-side column ends up looking like a project deliverable.
    """
    return Indicator(
        id=cov.id, metric=cov.metric, metricType=cov.metric_type,
        l1=cov.l1, l2=cov.l2, l3=cov.l3, l4=cov.l4,
        semanticType=cov.semantic_type, unit=cov.unit, currency=cov.currency,
        aggregation=cov.aggregation, numberFormat=cov.number_format,
        ruleVersion=cov.rule_version, source="data_upload",
        assetId=cov.asset_id, assetName=cov.asset_name,
        coverageStart=cov.coverage_start, coverageEnd=cov.coverage_end,
        rows=cov.rows, treeGrounded=False, treeRowId="", boundBy="",
    )


def declared_indicators(st: ProjectState) -> list[Indicator]:
    """The data target list: one indicator per active factor row, in tree order."""
    return [_declared(st, r, primary_coverage(st, r.id)) for r in active_rows(st)]


def orphan_indicators(st: ProjectState) -> list[Indicator]:
    """Supplied metrics with no factor row — awaiting adoption or dismissal."""
    return [_orphan(c) for c in (getattr(st, "indicator_coverage", None) or [])
            if not c.tree_row_id]


def derive_indicators(st: ProjectState) -> list[Indicator]:
    return declared_indicators(st) + orphan_indicators(st)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.dataeng._test_indicators`
Expected: PASS — seven `ok` lines.

- [ ] **Step 5: Commit**

```bash
git add backend/app/dataeng/indicators.py backend/app/dataeng/_test_indicators.py
git commit -m "feat(dataeng): derive the indicator catalog from the factor tree

Every active factor row projects to an Indicator whether or not data exists
yet, so the Data Engine can show the collection target before the first
upload. Coverage records fill them in; a human pin outranks a wider automatic
match. Supplied metrics no factor row asked for are orphans, kept apart."
```

---

### Task 3: Publish claims a factor row instead of creating indicators

**Files:**
- Modify: `backend/app/dataeng/dbt/service.py:536-592` (`register_indicators`)
- Test: `backend/app/dataeng/_test_claim.py` (create)

**Interfaces:**
- Consumes: `indicators.SOURCE_MAP` etc. (Task 2), `IndicatorCoverage` (Task 1).
- Produces: `claim_published_metrics(st, asset, df) -> list[IndicatorCoverage]`, replacing `register_indicators` (keep the old name as a thin alias so `seed_reference_assets` and `_test_flow` keep importing successfully until Task 5).

- [ ] **Step 1: Write the failing test**

Create `backend/app/dataeng/_test_claim.py`:

```python
"""Publish claims factor rows; it does not manufacture indicators.

Run: ``PYTHONPATH=. .venv/bin/python -m app.dataeng._test_claim``
"""
from __future__ import annotations

import pandas as pd

from app.domain.models import DataAsset, FactorRow, FactorTree
from app.store.state import ProjectState


def _st() -> ProjectState:
    st = ProjectState(project_id="_t")
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-1", l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视",
                  indicator="TV投放金额", source="template", status="baseline"),
    ])
    return st


def _asset() -> DataAsset:
    return DataAsset(id="a1", name="TV spend")


def _df(l4: str = "卫视", metric: str = "TV投放金额") -> pd.DataFrame:
    return pd.DataFrame({
        "metric": [metric] * 3,
        "metric_type": ["spending"] * 3,
        "l1": ["MARKETING FACTOR"] * 3, "l2": ["ATL"] * 3,
        "l3": ["TV"] * 3, "l4": [l4] * 3,
        "month": [202201, 202202, 202203],
        "value": [1.0, 2.0, 3.0],
    })


def test_matching_mart_claims_the_row_and_makes_no_indicator() -> None:
    from app.dataeng.dbt import service
    st = _st()
    covs = service.claim_published_metrics(st, _asset(), _df())

    assert len(covs) == 1
    assert covs[0].tree_row_id == "ft-1", "full L1–L4 path claims the row"
    assert covs[0].bound_by == "auto"
    assert covs[0].coverage_start == "202201" and covs[0].coverage_end == "202203"
    assert covs[0].rows == 3
    assert st.indicators == [], "publish no longer writes the legacy catalog"


def test_unmatched_metric_becomes_an_orphan() -> None:
    from app.dataeng.dbt import service
    from app.dataeng import indicators as ind
    st = _st()
    service.claim_published_metrics(st, _asset(), _df(l4="不存在的层级", metric="仓库库存"))

    assert ind.declared_indicators(st)[0].asset_id == "", "the factor is still unsupplied"
    orph = ind.orphan_indicators(st)
    assert len(orph) == 1 and orph[0].metric == "仓库库存"


def test_human_pin_survives_republish() -> None:
    from app.dataeng.dbt import service
    st = _st()
    covs = service.claim_published_metrics(st, _asset(), _df(l4="不存在的层级"))
    covs[0].tree_row_id = "ft-1"
    covs[0].bound_by = "human"

    service.claim_published_metrics(st, _asset(), _df(l4="不存在的层级"))
    after = st.indicator_coverage
    assert len(after) == 1
    assert after[0].tree_row_id == "ft-1" and after[0].bound_by == "human", \
        "a human binding is a decision, not derived state"


def test_republish_replaces_only_this_asset() -> None:
    from app.dataeng.dbt import service
    from app.domain.models import IndicatorCoverage
    st = _st()
    st.indicator_coverage.append(IndicatorCoverage(
        id="other", tree_row_id="", asset_id="a2", asset_name="Other", metric="m"))
    service.claim_published_metrics(st, _asset(), _df())
    assert {c.asset_id for c in st.indicator_coverage} == {"a1", "a2"}


def main() -> int:
    for fn in (test_matching_mart_claims_the_row_and_makes_no_indicator,
               test_unmatched_metric_becomes_an_orphan,
               test_human_pin_survives_republish,
               test_republish_replaces_only_this_asset):
        fn()
        print(f"ok  {fn.__name__}")
    print("all publish-claim tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.dataeng._test_claim`
Expected: FAIL — `AttributeError: module 'app.dataeng.dbt.service' has no attribute 'claim_published_metrics'`

- [ ] **Step 3: Rewrite `register_indicators` as a claim**

In `backend/app/dataeng/dbt/service.py`, replace the whole `register_indicators`
function (lines 536-592) with:

```python
def claim_published_metrics(st, asset: DataAsset, df: pd.DataFrame) -> list[IndicatorCoverage]:
    """Attach this asset's metrics to the factor rows they supply.

    Publish no longer *creates* indicators — the factor tree already declared
    them (app/dataeng/indicators.py). Each (metric × factor path) in the mart
    claims the row it matches, recorded as an IndicatorCoverage; anything that
    matches nothing is an orphan (`tree_row_id == ""`) and is offered back to the
    tree rather than presented as a project indicator.

    A human binding is a decision, not derived state, so it is carried across by
    coverage id rather than discarded on every re-publish.
    """
    pins = {c.id: c.tree_row_id for c in st.indicator_coverage
            if c.asset_id == asset.id and c.bound_by == "human" and c.tree_row_id}
    st.indicator_coverage = [c for c in st.indicator_coverage if c.asset_id != asset.id]
    if "metric" not in df.columns:
        return []

    # Factor-tree lookup: full L1–L4 path first, then L3-only as a looser anchor.
    tree_rows = [r for r in (st.factor_tree.rows if getattr(st, "factor_tree", None) else [])
                 if r.status in indicators.ACTIVE_STATUSES]
    by_path = {_norm_path(r.l1, r.l2, r.l3, r.l4): r for r in tree_rows}
    by_l3: dict[str, object] = {}
    for r in tree_rows:
        if r.l3:
            by_l3.setdefault(_norm_path(r.l3), r)

    key_cols = [c for c in ("metric", "metric_type", "l1", "l2", "l3", "l4") if c in df.columns]
    period = df["month"] if "month" in df.columns else (df["year"] if "year" in df.columns else None)
    new: list[IndicatorCoverage] = []
    for keys, grp in df.groupby(key_cols, dropna=False):
        vals = dict(zip(key_cols, keys if isinstance(keys, tuple) else (keys,)))
        cov_start = cov_end = ""
        if period is not None:
            sub = period.loc[grp.index].dropna()
            if not sub.empty:
                cov_start, cov_end = str(sub.min()), str(sub.max())
        row = (by_path.get(_norm_path(vals.get("l1", ""), vals.get("l2", ""),
                                      vals.get("l3", ""), vals.get("l4", "")))
               or by_l3.get(_norm_path(vals.get("l3", ""))))
        meta = classify_indicator(str(vals.get("metric", "")))
        cov_id = _indicator_id(asset.id, vals)
        pinned = pins.get(cov_id, "")
        new.append(IndicatorCoverage(
            id=cov_id,
            treeRowId=pinned or (row.id if row is not None else ""),
            assetId=asset.id, assetName=asset.name,
            metric=str(vals.get("metric", "")),
            metricType=str(vals.get("metric_type", "")),
            l1=str(vals.get("l1", "")), l2=str(vals.get("l2", "")),
            l3=str(vals.get("l3", "")), l4=str(vals.get("l4", "")),
            semanticType=meta.metric_type, unit=meta.unit, currency=meta.currency,
            aggregation=meta.aggregation, numberFormat=meta.fmt,
            ruleVersion=INDICATOR_META_RULE_VERSION,
            coverageStart=cov_start, coverageEnd=cov_end, rows=int(len(grp)),
            boundBy="human" if pinned else ("auto" if row is not None else ""),
        ))
    st.indicator_coverage.extend(new)
    return new


# Transitional alias — seed_reference_assets and _test_flow still call the old
# name; both move in Task 5.
register_indicators = claim_published_metrics
```

Add to the imports at the top of `service.py`:

```python
from app.dataeng import indicators
from app.domain.models import IndicatorCoverage
```

and drop the now-unused `Indicator` import if nothing else in the file uses it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.dataeng._test_claim`
Expected: PASS — four `ok` lines.

- [ ] **Step 5: Commit**

```bash
git add backend/app/dataeng/dbt/service.py backend/app/dataeng/_test_claim.py
git commit -m "feat(dataeng): publish claims a factor row instead of creating indicators

register_indicators became claim_published_metrics: each (metric x path) in
the mart attaches to the factor row it supplies as an IndicatorCoverage.
Unmatched metrics are orphans rather than indicators with treeGrounded=false.
Human pins still survive re-publish, now carried by coverage id."
```

---

### Task 4: Factor map, suggestions and auto-resolve read coverage

**Files:**
- Modify: `backend/app/dataeng/mapping.py:73-142`
- Modify: `backend/app/dataeng/mapping_suggest.py:126-158, 211-249`
- Modify: `backend/app/dataeng/mapping_auto.py:34-78`
- Modify: `backend/app/main.py:886-889` (`get_indicators`), `:1239-1268` (`_factor_map_payload`)
- Test: `backend/app/dataeng/_test_mapping_coverage.py` (create)

**Interfaces:**
- Consumes: Tasks 2 and 3.
- Produces: `FactorMapRow.coverages: list[FactorMapCoverage]`; `mapping_suggest.bind(st, row_id, coverage_id) -> bool` (the id is now a coverage id, which for an orphan equals its `Indicator.id`).

- [ ] **Step 1: Write the failing test**

Create `backend/app/dataeng/_test_mapping_coverage.py`:

```python
"""The 2.1 factor map resolves against coverage records.

Run: ``PYTHONPATH=. .venv/bin/python -m app.dataeng._test_mapping_coverage``
"""
from __future__ import annotations

from app.domain.models import FactorRow, FactorTree, IndicatorCoverage
from app.store.state import ProjectState


def _st() -> ProjectState:
    st = ProjectState(project_id="_t")
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-1", l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视",
                  indicator="TV投放金额", status="baseline"),
        FactorRow(id="ft-2", l1="MARKETING FACTOR", l2="DIGITAL", l3="EC", l4="天猫",
                  indicator="电商投放金额", status="accepted"),
    ])
    return st


def test_row_with_coverage_is_mapped() -> None:
    from app.dataeng.mapping import resolve_factor_map
    st = _st()
    st.indicator_coverage.append(IndicatorCoverage(
        id="c1", tree_row_id="ft-1", asset_id="a1", asset_name="TV",
        metric="CCTV花费", coverage_start="202201", coverage_end="202212",
        rows=12, bound_by="auto"))

    fmap = resolve_factor_map(st)
    tv = next(r for r in fmap.rows if r.row_id == "ft-1")
    assert tv.status == "mapped"
    assert tv.asset_name == "TV" and tv.metric == "CCTV花费"
    assert fmap.mapped == 1 and fmap.pending == 1 and fmap.complete is False


def test_multi_source_coverage_maps_once() -> None:
    from app.dataeng.mapping import resolve_factor_map
    st = _st()
    st.indicator_coverage.extend([
        IndicatorCoverage(id="c1", tree_row_id="ft-1", asset_id="a1",
                          asset_name="TV central", metric="央视花费", rows=12),
        IndicatorCoverage(id="c2", tree_row_id="ft-1", asset_id="a2",
                          asset_name="TV satellite", metric="卫视花费", rows=99),
    ])
    tv = next(r for r in resolve_factor_map(st).rows if r.row_id == "ft-1")
    assert tv.status == "mapped"
    assert len(tv.coverages) == 2, "a factor may be supplied by several sources"
    assert tv.asset_name == "TV satellite", "the widest series represents the row"


def test_ignored_row_clears_without_data() -> None:
    from app.dataeng.mapping import mapping_complete
    st = _st()
    st.indicator_coverage.append(IndicatorCoverage(
        id="c1", tree_row_id="ft-1", asset_id="a1", asset_name="TV", metric="m"))
    st.factor_map_ignores["ft-2"] = "no data source"
    assert mapping_complete(st) is True


def test_bind_pins_an_orphan_and_demotes_the_incumbent() -> None:
    from app.dataeng import mapping_suggest as ms
    st = _st()
    st.indicator_coverage.extend([
        IndicatorCoverage(id="c-auto", tree_row_id="ft-1", asset_id="a1",
                          asset_name="Guess", metric="m1", bound_by="auto"),
        IndicatorCoverage(id="c-orph", tree_row_id="", asset_id="a2",
                          asset_name="Real", metric="m2"),
    ])
    assert ms.bind(st, "ft-1", "c-orph") is True
    by_id = {c.id: c for c in st.indicator_coverage}
    assert by_id["c-orph"].tree_row_id == "ft-1" and by_id["c-orph"].bound_by == "human"
    assert by_id["c-auto"].tree_row_id == "", \
        "one published metric supplies at most one factor row"


def test_unbind_releases_every_coverage_on_the_row() -> None:
    from app.dataeng import mapping_suggest as ms
    st = _st()
    st.indicator_coverage.extend([
        IndicatorCoverage(id="c1", tree_row_id="ft-1", asset_id="a1",
                          asset_name="A", metric="m1", bound_by="auto"),
        IndicatorCoverage(id="c2", tree_row_id="ft-1", asset_id="a2",
                          asset_name="B", metric="m2", bound_by="human"),
    ])
    assert ms.unbind(st, "ft-1") is True
    assert all(c.tree_row_id == "" for c in st.indicator_coverage)


def test_suggestions_only_offer_orphans() -> None:
    from app.dataeng import mapping_suggest as ms
    st = _st()
    st.indicator_coverage.extend([
        IndicatorCoverage(id="c-taken", tree_row_id="ft-1", asset_id="a1",
                          asset_name="A", metric="TV投放金额", unit="元"),
        IndicatorCoverage(id="c-free", tree_row_id="", asset_id="a2",
                          asset_name="B", metric="电商投放金额", unit="元",
                          l3="EC", l4="天猫", coverage_start="202201",
                          coverage_end="202212"),
    ])
    sugg = ms.suggest_all(st)
    assert "ft-1" not in sugg, "a mapped row needs no suggestion"
    assert [s.indicator_id for s in sugg["ft-2"]] == ["c-free"]


def main() -> int:
    for fn in (test_row_with_coverage_is_mapped,
               test_multi_source_coverage_maps_once,
               test_ignored_row_clears_without_data,
               test_bind_pins_an_orphan_and_demotes_the_incumbent,
               test_unbind_releases_every_coverage_on_the_row,
               test_suggestions_only_offer_orphans):
        fn()
        print(f"ok  {fn.__name__}")
    print("all mapping/coverage tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.dataeng._test_mapping_coverage`
Expected: FAIL — `test_row_with_coverage_is_mapped` fails with `status == "pending"` (the resolver still indexes `st.indicators`).

- [ ] **Step 3: Rewrite the resolver**

In `backend/app/dataeng/mapping.py`, add a coverage dataclass above `FactorMapRow`:

```python
@dataclass
class FactorMapCoverage:
    """One published (asset × metric) supplying this row."""
    coverage_id: str
    asset_id: str
    asset_name: str
    metric: str
    coverage_start: str = ""
    coverage_end: str = ""
    rows: int = 0
    bound_by: str = ""
```

Add to `FactorMapRow`:

```python
    # Every source supplying this row. The flat asset_id/asset_name/metric/
    # coverage_* fields above stay, reporting the primary coverage, so existing
    # readers (the 2.1 artifact, IndicatorCatalogPanel) are unaffected.
    coverages: list[FactorMapCoverage] = field(default_factory=list)
```

Delete `_cover_indicator` and `_index_indicators` entirely, and replace the body of `resolve_factor_map`'s loop:

```python
def resolve_factor_map(st: ProjectState) -> FactorMap:
    """Per active factor-tree row: mapped (≥1 coverage record supplies it),
    ignored (user-chosen), or pending (needs a decision)."""
    from app.dataeng import indicators as ind

    ft = getattr(st, "factor_tree", None)
    if ft is None:
        return FactorMap()
    ignores = getattr(st, "factor_map_ignores", None) or {}
    out: list[FactorMapRow] = []
    for r in ft.rows:
        if r.status not in _ACTIVE_STATUSES:
            continue
        fm = FactorMapRow(
            row_id=r.id, l1=r.l1, l2=r.l2, l3=r.l3, l4=r.l4,
            indicator=r.indicator, status="pending",
        )
        covs = ind.coverages_for(st, r.id)
        fm.coverages = [FactorMapCoverage(
            coverage_id=c.id, asset_id=c.asset_id, asset_name=c.asset_name,
            metric=c.metric, coverage_start=c.coverage_start,
            coverage_end=c.coverage_end, rows=c.rows, bound_by=c.bound_by)
            for c in covs]
        primary = ind.primary_coverage(st, r.id)
        if primary is not None:
            fm.status = "mapped"
            fm.asset_id = primary.asset_id
            fm.asset_name = primary.asset_name
            fm.metric = primary.metric
            fm.coverage_start = primary.coverage_start
            fm.coverage_end = primary.coverage_end
        elif r.id in ignores:
            fm.status = "ignored"
            fm.ignore_note = str(ignores[r.id] or "")
        metric_label = fm.metric or fm.indicator
        ov_role = metric_type_override(st, r.l4, metric_label)
        fm.metric_type = ov_role or default_metric_type(metric_label)
        if fm.metric_type == "spending":
            fm.metric_type = "X"
        fm.aggregation = resolve_aggregation(st, r.l4, metric_label)
        out.append(fm)
    return FactorMap(rows=out)
```

- [ ] **Step 4: Rewrite bind / unbind / suggest_all**

In `backend/app/dataeng/mapping_suggest.py`, replace `suggest_all`'s candidate
selection and `bind` / `unbind`:

```python
def suggest_all(st: ProjectState) -> dict[str, list[Suggestion]]:
    """Ranked suggestions per pending factor row id (best first).

    Only orphan coverages are candidates: a metric already supplying another
    factor cannot also supply this one, so proposing it would be a mapping error
    dressed as a suggestion.
    """
    from app.dataeng.mapping import resolve_factor_map
    from app.dataeng import indicators as ind

    fmap = resolve_factor_map(st)
    pending = [r for r in fmap.rows if r.status == "pending"]
    if not pending:
        return {}
    cands = ind.orphan_indicators(st)
    if not cands:
        return {}

    out: dict[str, list[Suggestion]] = {}
    for row in pending:
        ranked = sorted(((score(row, i), i) for i in cands), key=lambda t: -t[0])
        picks = [
            Suggestion(
                indicator_id=i.id, metric=i.metric, asset_id=i.asset_id,
                asset_name=i.asset_name, unit=i.unit,
                coverage_start=i.coverage_start, coverage_end=i.coverage_end,
                score=s, reason=_reason(row, i, s),
            )
            for s, i in ranked[:MAX_ALTERNATES + 1] if s >= MIN_SCORE
        ]
        if picks:
            out[row.row_id] = picks
    return out
```

```python
def bind(st: ProjectState, row_id: str, coverage_id: str) -> bool:
    """Pin a published (asset × metric) to a factor row.

    One published metric supplies at most one row, so any incumbent claim on this
    row is released — otherwise two coverages claim it and which one represents
    the row is resolution order. Multiple *deliberate* sources for one factor are
    still possible; they are added by publishing, not by re-pinning.
    """
    covs = getattr(st, "indicator_coverage", None) or []
    if not any(c.id == coverage_id for c in covs):
        return False
    for c in covs:
        if c.tree_row_id == row_id and c.id != coverage_id:
            c.tree_row_id = ""
            c.bound_by = ""
    for c in covs:
        if c.id == coverage_id:
            c.tree_row_id = row_id
            c.bound_by = "human"
            if getattr(st, "factor_map_ignores", None):
                st.factor_map_ignores.pop(row_id, None)
            return True
    return False


def unbind(st: ProjectState, row_id: str) -> bool:
    """Release every coverage supplying this row (remap / undo)."""
    hit = False
    for c in getattr(st, "indicator_coverage", None) or []:
        if c.tree_row_id == row_id:
            c.tree_row_id = ""
            c.bound_by = ""
            hit = True
    return hit
```

In `backend/app/dataeng/mapping_auto.py`, replace the candidate lines
(currently 44-45):

```python
    from app.dataeng import indicators as ind
    candidates = ind.orphan_indicators(st)
    used: set[str] = set()
```

(An orphan is by definition unclaimed, so the old `used` pre-seed from
`st.indicators` is gone; `used` still prevents one metric being assigned twice
inside a single pass.)

- [ ] **Step 5: Point the API at the derivation**

In `backend/app/main.py`, `get_indicators` (line 886):

```python
@app.get("/api/projects/{project_id}/indicators")
async def get_indicators(project_id: str) -> list[dict]:
    """The data target list: every confirmed factor row, plus orphan metrics."""
    from app.dataeng.indicators import derive_indicators
    st = _require_state(project_id)
    return [i.model_dump(by_alias=True) for i in derive_indicators(st)]
```

In `_factor_map_payload` (line 1245), add the coverage list to each row dict,
right after `"ignoreNote"`:

```python
            "coverages": [{
                "coverageId": c.coverage_id, "assetId": c.asset_id,
                "assetName": c.asset_name, "metric": c.metric,
                "coverageStart": c.coverage_start, "coverageEnd": c.coverage_end,
                "rows": c.rows, "boundBy": c.bound_by,
            } for c in r.coverages],
```

Mirror it in `frontend/src/lib/types.ts` on `FactorMapRow`:

```ts
  coverages: {
    coverageId: string
    assetId: string
    assetName: string
    metric: string
    coverageStart: string
    coverageEnd: string
    rows: number
    boundBy: '' | 'auto' | 'human'
  }[]
```

- [ ] **Step 6: Run the tests**

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_mapping_coverage
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_indicators
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_claim
PYTHONPATH=. .venv/bin/python -m app.agents._test_ledger_signoff
PYTHONPATH=. .venv/bin/python -m app.agents._test_master_data
```

Expected: all PASS. The last two must be unchanged — if either moves, the
derivation is wrong.

- [ ] **Step 7: Commit**

```bash
git add backend/app/dataeng/mapping.py backend/app/dataeng/mapping_suggest.py \
        backend/app/dataeng/mapping_auto.py backend/app/main.py \
        backend/app/dataeng/_test_mapping_coverage.py frontend/src/lib/types.ts
git commit -m "refactor(dataeng): 2.1 factor map resolves against coverage records

The resolver, the AI suggester and auto-resolve all read indicator_coverage
instead of a stored indicator list. A row may now be supplied by several
sources (mapped when >=1); one published metric still supplies at most one
row. GET /indicators derives from the factor tree."
```

---

### Task 5: Migration, and retire the stored catalog

**Files:**
- Modify: `backend/app/store/state.py` (`heal_state`, line 245+)
- Modify: `backend/app/dataeng/seed_reference_assets.py:60-95`
- Modify: `backend/app/dataeng/dbt/service.py` (drop the `register_indicators` alias)
- Modify: `backend/app/agents/data.py:172, 256`
- Test: `backend/app/store/_test_indicator_migration.py` (create)

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: `state._migrate_indicators_to_coverage(st) -> int` (number of pins carried), called from `heal_state`.

- [ ] **Step 1: Write the failing test**

Create `backend/app/store/_test_indicator_migration.py`:

```python
"""Saved projects keep their manual factor bindings across the refactor.

Run: ``PYTHONPATH=. .venv/bin/python -m app.store._test_indicator_migration``
"""
from __future__ import annotations

from app.domain.models import FactorRow, FactorTree, Indicator
from app.store.state import ProjectState, _migrate_indicators_to_coverage


def _st() -> ProjectState:
    st = ProjectState(project_id="_t")
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-1", l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视",
                  indicator="TV投放金额", status="baseline"),
    ])
    st.indicators = [
        Indicator(id="ind-old-1", metric="央视花费", metricType="spending",
                  l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视", unit="元",
                  assetId="a1", assetName="TV spend", coverageStart="202201",
                  coverageEnd="202212", rows=12, treeGrounded=True,
                  treeRowId="ft-1", boundBy="human"),
        Indicator(id="ind-old-2", metric="猜的", assetId="a1", assetName="TV spend",
                  treeGrounded=True, treeRowId="ft-1", boundBy="auto"),
    ]
    return st


def test_human_pin_migrates_auto_is_dropped() -> None:
    st = _st()
    carried = _migrate_indicators_to_coverage(st)

    assert carried == 1
    assert st.indicators == [], "the legacy list is drained, not left to drift"
    assert len(st.indicator_coverage) == 1
    c = st.indicator_coverage[0]
    assert c.id == "ind-old-1" and c.tree_row_id == "ft-1" and c.bound_by == "human"
    assert c.metric == "央视花费" and c.asset_id == "a1"
    assert c.coverage_start == "202201" and c.rows == 12


def test_migration_is_idempotent() -> None:
    st = _st()
    _migrate_indicators_to_coverage(st)
    assert _migrate_indicators_to_coverage(st) == 0
    assert len(st.indicator_coverage) == 1


def test_migrated_pin_still_maps_the_row() -> None:
    from app.dataeng.mapping import resolve_factor_map
    st = _st()
    _migrate_indicators_to_coverage(st)
    assert resolve_factor_map(st).rows[0].status == "mapped"


def main() -> int:
    for fn in (test_human_pin_migrates_auto_is_dropped,
               test_migration_is_idempotent,
               test_migrated_pin_still_maps_the_row):
        fn()
        print(f"ok  {fn.__name__}")
    print("all indicator migration tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.store._test_indicator_migration`
Expected: FAIL — `ImportError: cannot import name '_migrate_indicators_to_coverage'`

- [ ] **Step 3: Write the migration**

In `backend/app/store/state.py`, above `heal_state`:

```python
def _migrate_indicators_to_coverage(st: ProjectState) -> int:
    """Carry a saved project's manual factor bindings onto coverage records.

    Indicators used to be stored, built by groupby over each published mart. They
    are now derived from the factor tree, so the stored list is drained here.
    Automatic bindings are dropped — they are re-derived on the next publish, or
    re-proposed by mapping_auto. **Human bindings are decisions and would be
    destroyed if this did not run**, which is the one irreversible failure in the
    move; they are carried across by id.
    """
    if not st.indicators:
        return 0
    known = {c.id for c in st.indicator_coverage}
    carried = 0
    for ind in st.indicators:
        if ind.bound_by != "human" or not ind.tree_row_id or ind.id in known:
            continue
        st.indicator_coverage.append(IndicatorCoverage(
            id=ind.id, treeRowId=ind.tree_row_id,
            assetId=ind.asset_id, assetName=ind.asset_name,
            metric=ind.metric, metricType=ind.metric_type,
            l1=ind.l1, l2=ind.l2, l3=ind.l3, l4=ind.l4,
            semanticType=ind.semantic_type, unit=ind.unit, currency=ind.currency,
            aggregation=ind.aggregation, numberFormat=ind.number_format,
            ruleVersion=ind.rule_version,
            coverageStart=ind.coverage_start, coverageEnd=ind.coverage_end,
            rows=ind.rows, boundBy="human"))
        carried += 1
    st.indicators = []
    return carried
```

Call it as the first statement inside `heal_state` (line ~250, before
`template = initial_state(...)`):

```python
    _migrate_indicators_to_coverage(st)
```

- [ ] **Step 4: Update the remaining `st.indicators` readers**

`backend/app/dataeng/seed_reference_assets.py` — replace the wipe (line 74) and
the two counts (lines 88, 92-95):

```python
    st.indicator_coverage = []
    st.data_assets = []
```

```python
        n_ind = sum(1 for c in st.indicator_coverage if c.asset_id == asset.id)
```

```python
    from app.dataeng.indicators import derive_indicators
    all_inds = derive_indicators(st)
    grounded = sum(1 for i in all_inds if i.tree_grounded)
    return {
        "assets": len(st.data_assets),
        "indicators": len(all_inds),
        "treeGrounded": grounded,
        "perSource": summary,
    }
```

Change its `register_indicators(st, asset, df)` call (line 61) to
`claim_published_metrics(st, asset, df)` and update the import.

`backend/app/agents/data.py` — line 172 and 256:

```python
                   str(sum(1 for c in st.indicator_coverage if c.asset_id == a.id)),
```

```python
        "assets": len(published),
        "indicators": len(derive_indicators(st)),
```

with `from app.dataeng.indicators import derive_indicators` at the call site.

Finally delete the `register_indicators = claim_published_metrics` alias at the
bottom of the new function in `service.py`, and grep to confirm nothing still
references the old name:

```bash
cd backend && grep -rn "register_indicators\|st\.indicators" app/ --include='*.py'
```

Only `state.py`'s migration and the `ProjectState.indicators` field declaration
should remain.

- [ ] **Step 5: Run the tests**

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m app.store._test_indicator_migration
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_mapping_coverage
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_flow
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/store/state.py backend/app/store/_test_indicator_migration.py \
        backend/app/dataeng/seed_reference_assets.py \
        backend/app/dataeng/dbt/service.py backend/app/agents/data.py
git commit -m "feat(store): migrate stored indicators to coverage records

heal_state drains ProjectState.indicators onto indicator_coverage, carrying
every bound_by=human binding across — losing those would silently destroy the
Danone case's manual mappings. Auto bindings are re-derived. The field stays
declared only as the migration inbox; Pydantic would drop an unknown key on
load before the migration could see it."
```

---

### Task 6: Adopt an orphan into the factor tree

**Files:**
- Create: `backend/app/dataeng/orphans.py`
- Modify: `backend/app/main.py` (new endpoint beside `get_indicators`)
- Modify: `backend/app/agents/business.py` (`_factor_tree_sheet` re-render helper is already there — reuse it)
- Test: `backend/app/dataeng/_test_orphans.py` (create)

**Interfaces:**
- Consumes: Tasks 1-5.
- Produces: `orphans.adopt(st, coverage_id) -> str` returning the new `FactorRow.id`, `orphans.dismiss(st, coverage_id) -> bool`; endpoints `POST /api/projects/{id}/indicators/orphans/{coverage_id}/adopt` and `.../dismiss`.

- [ ] **Step 1: Write the failing test**

Create `backend/app/dataeng/_test_orphans.py`:

```python
"""An orphan metric can be proposed into the factor tree.

Run: ``PYTHONPATH=. .venv/bin/python -m app.dataeng._test_orphans``
"""
from __future__ import annotations

from app.domain.models import FactorRow, FactorTree, IndicatorCoverage
from app.store.state import ProjectState


def _st() -> ProjectState:
    st = ProjectState(project_id="_t")
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-1", l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视",
                  indicator="TV投放金额", status="baseline"),
    ])
    st.indicator_coverage.append(IndicatorCoverage(
        id="c-orph", tree_row_id="", asset_id="a1", asset_name="Logistics",
        metric="仓库库存", metric_type="X", l1="COMMERCIAL FACTOR", l2="SUPPLY",
        l3="WAREHOUSE", l4="库存", coverage_start="202201", coverage_end="202212",
        rows=12))
    return st


def test_adopt_creates_an_accepted_row_and_claims_it() -> None:
    from app.dataeng import orphans
    from app.dataeng.indicators import declared_indicators, orphan_indicators
    st = _st()

    row_id = orphans.adopt(st, "c-orph")

    row = next(r for r in st.factor_tree.rows if r.id == row_id)
    assert row.source == "data_upload"
    assert row.status == "accepted", \
        "the S1 gates have already closed — adoption accepts on the spot"
    assert (row.l1, row.l3, row.l4) == ("COMMERCIAL FACTOR", "WAREHOUSE", "库存")
    assert row.indicator == "仓库库存"

    assert orphan_indicators(st) == [], "the orphan is now a supplied factor"
    adopted = next(i for i in declared_indicators(st) if i.tree_row_id == row_id)
    assert adopted.asset_name == "Logistics" and adopted.rows == 12


def test_adopt_is_idempotent() -> None:
    from app.dataeng import orphans
    st = _st()
    first = orphans.adopt(st, "c-orph")
    assert orphans.adopt(st, "c-orph") == first
    assert len(st.factor_tree.rows) == 2


def test_dismiss_removes_the_orphan() -> None:
    from app.dataeng import orphans
    from app.dataeng.indicators import orphan_indicators
    st = _st()
    assert orphans.dismiss(st, "c-orph") is True
    assert orphan_indicators(st) == []
    assert len(st.factor_tree.rows) == 1
    assert orphans.dismiss(st, "c-orph") is False


def main() -> int:
    for fn in (test_adopt_creates_an_accepted_row_and_claims_it,
               test_adopt_is_idempotent,
               test_dismiss_removes_the_orphan):
        fn()
        print(f"ok  {fn.__name__}")
    print("all orphan adoption tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.dataeng._test_orphans`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.dataeng.orphans'`

- [ ] **Step 3: Write the module**

Create `backend/app/dataeng/orphans.py`:

```python
"""Orphan review — a supplied metric the factor tree never asked for.

An orphan is not an indicator. Presenting it as one is how a data-side column
ends up looking like a project deliverable, which is what the stored catalog used
to do (`treeGrounded=False` mixed into the same list). It gets two honest exits:
adopt it into the factor tree, or dismiss it.

Adoption writes `source="data_upload"`, `status="accepted"`. It does NOT go
through the S1 accept/reject gates: by the time anyone is looking at published
data, 1.21d and 1.4d are long closed, and a proposal nothing will ever accept is
just a row that silently never reaches the model.
"""
from __future__ import annotations

from app.domain.models import FactorRow, FactorTree
from app.store.state import ProjectState


def _coverage(st: ProjectState, coverage_id: str):
    return next((c for c in (getattr(st, "indicator_coverage", None) or [])
                 if c.id == coverage_id), None)


def adopt(st: ProjectState, coverage_id: str) -> str:
    """Add this orphan to the factor tree and claim it. Returns the row id.

    Idempotent: adopting an already-claimed coverage returns its existing row.
    """
    cov = _coverage(st, coverage_id)
    if cov is None:
        raise KeyError(coverage_id)
    if cov.tree_row_id:
        return cov.tree_row_id
    if st.factor_tree is None:
        st.factor_tree = FactorTree(rows=[])
    row = FactorRow(
        id=f"ft-orph-{coverage_id}",
        l1=cov.l1, l2=cov.l2, l3=cov.l3, l4=cov.l4,
        indicator=cov.metric,
        source="data_upload", status="accepted",
        rationale="Adopted from published data — supplied but not in the tree.",
        evidence=f"{cov.asset_name} · {cov.metric}",
    )
    st.factor_tree.rows.append(row)
    cov.tree_row_id = row.id
    cov.bound_by = "human"
    return row.id


def dismiss(st: ProjectState, coverage_id: str) -> bool:
    """Drop an orphan from the catalog. False when it is not an orphan."""
    covs = getattr(st, "indicator_coverage", None) or []
    cov = _coverage(st, coverage_id)
    if cov is None or cov.tree_row_id:
        return False
    st.indicator_coverage = [c for c in covs if c.id != coverage_id]
    return True
```

- [ ] **Step 4: Add the endpoints**

In `backend/app/main.py`, directly after `get_indicators`:

```python
@app.post("/api/projects/{project_id}/indicators/orphans/{coverage_id}/adopt")
async def adopt_orphan(project_id: str, coverage_id: str) -> list[dict]:
    """Add a supplied-but-undeclared metric to the factor tree, and claim it."""
    from app.dataeng import orphans
    from app.dataeng.indicators import derive_indicators
    from app.agents.business import rerender_factor_tree
    st = _require_state(project_id)
    try:
        orphans.adopt(st, coverage_id)
    except KeyError as e:
        raise HTTPException(404, f"No such indicator: {coverage_id}") from e
    rerender_factor_tree(st)
    get_store().save(project_id)
    return [i.model_dump(by_alias=True) for i in derive_indicators(st)]


@app.post("/api/projects/{project_id}/indicators/orphans/{coverage_id}/dismiss")
async def dismiss_orphan(project_id: str, coverage_id: str) -> list[dict]:
    from app.dataeng import orphans
    from app.dataeng.indicators import derive_indicators
    st = _require_state(project_id)
    if not orphans.dismiss(st, coverage_id):
        raise HTTPException(409, "That indicator is not an orphan.")
    get_store().save(project_id)
    return [i.model_dump(by_alias=True) for i in derive_indicators(st)]
```

In `backend/app/agents/business.py`, extract the existing artifact re-render
(the three lines repeated in `accept_factor_rows`) into a reusable helper next
to it:

```python
def rerender_factor_tree(st: ProjectState) -> None:
    """Re-render a-factor-tree from the current rows (after an out-of-band edit)."""
    if st.factor_tree is None:
        return
    art = st.artifact("a-factor-tree")
    if art is not None:
        art.body = _factor_tree_sheet(st.factor_tree)
```

and call it from `accept_factor_rows` in place of its inline copy.

Add the two calls to `frontend/src/api/client.ts`:

```ts
  adoptOrphanIndicator: (projectId: string, coverageId: string) =>
    post<Indicator[]>(`/api/projects/${projectId}/indicators/orphans/${coverageId}/adopt`),
  dismissOrphanIndicator: (projectId: string, coverageId: string) =>
    post<Indicator[]>(`/api/projects/${projectId}/indicators/orphans/${coverageId}/dismiss`),
```

(match the file's existing `post` helper signature — if it requires a body, pass `{}`).

- [ ] **Step 5: Run the tests**

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_orphans
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_indicators
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py
cd ../frontend && npm run build
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/dataeng/orphans.py backend/app/dataeng/_test_orphans.py \
        backend/app/main.py backend/app/agents/business.py frontend/src/api/client.ts
git commit -m "feat(dataeng): adopt or dismiss orphan indicators

A supplied metric with no factor row gets two honest exits instead of sitting
in the catalog as treeGrounded=false. Adoption writes a data_upload factor row
accepted on the spot — the S1 gates are closed by the time anyone sees
published data, so a proposal there would never be accepted."
```

---

### Task 7: Data Engine Indicators view — targets, orphans, empty state

**Files:**
- Modify: `frontend/src/components/dataeng/IndicatorCatalogPanel.tsx:363-419`

**Interfaces:**
- Consumes: `Indicator.treeGrounded` / `treeRowId` (derived, Task 4), the two orphan calls (Task 6).

- [ ] **Step 1: Split the published-indicator table in two**

Replace the "Published indicators" card (lines 363-419) with two cards driven off
`treeGrounded`:

```tsx
  const declared = visible.filter((i) => i.treeGrounded)
  const orphans = visible.filter((i) => !i.treeGrounded)
```

The first card is titled **"Data targets"** with the subtitle
`Every confirmed factor is an indicator this project must collect.` Its rows keep
the existing columns, with `Coverage` reading `Not supplied yet` (muted) when
`coverageStart` is empty, and `Source asset` reading `—` in the same case.

The second card renders only when `orphans.length > 0`, titled
**"In the data, not in the factor tree"** with the subtitle
`These metrics were published but no factor asked for them.` Each row gets two
buttons:

```tsx
<button type="button" disabled={busy === ind.id}
  onClick={() => void act(ind.id, () => api.adoptOrphanIndicator(pid!, ind.id), setIndicators)}
  className="inline-flex items-center gap-1 rounded border border-primary/40 bg-primary/5 px-2 py-0.5 text-[11px] font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-50">
  Add to factor tree
</button>
<button type="button" disabled={busy === ind.id}
  onClick={() => void act(ind.id, () => api.dismissOrphanIndicator(pid!, ind.id), setIndicators)}
  className="text-[11px] text-muted-foreground hover:text-foreground">
  Dismiss
</button>
```

`act` is the existing helper at line 188; it already sets `busy` / clears `error`.
Adoption changes the factor tree, so follow it with `refresh()` to pull the
updated factor map.

- [ ] **Step 2: Fix the empty state**

The `indicators.length === 0` card (line 364) currently reads
`No published indicators yet — publish a data asset and its metrics appear here.`
That is now wrong: an empty catalog means the factor tree is not confirmed, not
that data is missing. Replace with:

```tsx
          <Card className="p-6 text-center text-[12px] text-muted-foreground">
            No data targets yet. The factor tree defines what this project collects —
            confirm it in Business Understanding and every factor appears here.
          </Card>
```

- [ ] **Step 3: Verify in the running app**

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
cd frontend && npm run dev
```

Open `http://localhost:5173`, go to the Danone project → Data Engine → Indicators.
Expected: the confirmed factor tree is listed as data targets with coverage where
assets are published; the empty state points back to Business Understanding on a
fresh project.

- [ ] **Step 4: Build and commit**

```bash
cd frontend && npm run build && npm run lint
git add frontend/src/components/dataeng/IndicatorCatalogPanel.tsx
git commit -m "feat(dataeng): Indicators view shows data targets and orphans apart

Declared factors list whether or not data exists (Not supplied yet), so the
collection target is visible before the first upload. Orphans get their own
card with Add to factor tree / Dismiss. The empty state now points back to
Business Understanding instead of blaming a missing upload."
```

---

### Task 8: One grounding budget, visible truncation

Independent of Tasks 1-7 — can be done in any order relative to them.

**Files:**
- Modify: `backend/app/config.py:12` (`Settings`)
- Modify: `backend/app/agents/common.py:17`
- Modify: `backend/app/agents/business.py` (11 cap sites, listed below)
- Modify: `backend/app/store/files.py:163, 185`
- Test: `backend/app/agents/_test_grounding.py` (create)

**Interfaces:**
- Produces: `common.grounding_budget() -> int`, `common.clip(text, budget=None, *, label="") -> ClipResult` where `ClipResult` has `.text: str`, `.dropped: int`, `.kept_ratio: float`, `.truncated: bool`, and `common.truncation_finding(results) -> TaskFinding | None`.

- [ ] **Step 1: Write the failing test**

Create `backend/app/agents/_test_grounding.py`:

```python
"""Grounding material is budgeted once, and truncation is visible.

Run: ``PYTHONPATH=. .venv/bin/python -m app.agents._test_grounding``
"""
from __future__ import annotations

from app.agents.common import clip, grounding_budget, truncation_finding


def test_under_budget_is_untouched() -> None:
    r = clip("hello", label="SOW")
    assert r.text == "hello"
    assert r.truncated is False and r.dropped == 0 and r.kept_ratio == 1.0


def test_over_budget_reports_what_it_dropped() -> None:
    r = clip("x" * 100, budget=40, label="materials")
    assert len(r.text) == 40
    assert r.truncated is True and r.dropped == 60
    assert abs(r.kept_ratio - 0.4) < 1e-9
    assert r.label == "materials"


def test_default_budget_is_generous() -> None:
    assert grounding_budget() >= 100_000, \
        "the point of the change is that whole documents reach the model"


def test_finding_names_the_source_and_the_share() -> None:
    kept = clip("y" * 10, label="notes")
    cut = clip("x" * 1000, budget=100, label="materials")
    f = truncation_finding([kept, cut])
    assert f is not None
    assert "materials" in f.text and "10%" in f.text
    assert "notes" not in f.text, "only truncated sources are reported"
    assert f.tone == "flag"


def test_no_finding_when_nothing_was_cut() -> None:
    assert truncation_finding([clip("short", label="a")]) is None


def main() -> int:
    for fn in (test_under_budget_is_untouched,
               test_over_budget_reports_what_it_dropped,
               test_default_budget_is_generous,
               test_finding_names_the_source_and_the_share,
               test_no_finding_when_nothing_was_cut):
        fn()
        print(f"ok  {fn.__name__}")
    print("all grounding budget tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m app.agents._test_grounding`
Expected: FAIL — `ImportError: cannot import name 'clip'`

- [ ] **Step 3: Add the setting**

In `backend/app/config.py`, in `Settings` beside the other operational knobs:

```python
    # How much grounding material one agent call may see. These used to be a dozen
    # independently-chosen constants applied silently, so a 200-page deck and its
    # first six thousand characters produced indistinguishable deliverables.
    grounding_max_chars: int = 100_000
```

- [ ] **Step 4: Add clip + the finding**

In `backend/app/agents/common.py`, replacing the `MAX_CTX_CHARS = 6000` constant:

```python
from dataclasses import dataclass

from app.config import get_settings


@dataclass(frozen=True)
class ClipResult:
    """Grounding text plus what budgeting cost it."""
    text: str
    dropped: int
    label: str

    @property
    def truncated(self) -> bool:
        return self.dropped > 0

    @property
    def kept_ratio(self) -> float:
        total = len(self.text) + self.dropped
        return 1.0 if total == 0 else len(self.text) / total


def grounding_budget() -> int:
    return get_settings().grounding_max_chars


def clip(text: str, budget: int | None = None, *, label: str = "") -> ClipResult:
    """Trim grounding material to the budget, remembering what was lost."""
    text = text or ""
    cap = grounding_budget() if budget is None else budget
    if len(text) <= cap:
        return ClipResult(text=text, dropped=0, label=label)
    return ClipResult(text=text[:cap], dropped=len(text) - cap, label=label)


def truncation_finding(results: "list[ClipResult]") -> "TaskFinding | None":
    """A flag naming every source that did not fit, or None when all of them did.

    Silent truncation is the failure this replaces: a thin deliverable built from
    the first slice of a long document looks exactly like a thin document.
    """
    cut = [r for r in results if r.truncated]
    if not cut:
        return None
    parts = ", ".join(
        f"{r.label or 'material'} ({r.kept_ratio * 100:.0f}% used)" for r in cut)
    return TaskFinding(
        text=f"Grounding material exceeded the budget and was truncated: {parts}. "
             f"Raise GROUNDING_MAX_CHARS or split the source if this matters.",
        tone="flag")
```

Keep `MAX_CTX_CHARS` defined as `MAX_CTX_CHARS = 6000` **only** if something
outside grounding still uses it — grep first; if only the three sites at
`common.py:29, 31, 32, 64` use it, replace those with `clip(...).text` and delete
the constant.

- [ ] **Step 5: Route the S1 cap sites through clip**

In `backend/app/agents/business.py`, replace each bare slice on *grounding
material* with `clip`, collecting the results so the handler can emit one finding:

| Line | Was | Becomes |
|---|---|---|
| 98 | `materials[:8000]` | `clip(materials, label="SOW & brief")` |
| 189 | `max_chars=6000` | drop the arg (defaults to the budget) |
| 202 | `materials[:6000]` | `clip(materials, label="industry materials")` |
| 450 | `limit: int = 4000` | `limit: int | None = None` → `clip(joined, limit, label="factor paths")` |
| 535 | `[:3000]` | `clip(joined, label="existing paths")` |
| 557 | `materials[:6000]` | `clip(materials, label="industry materials")` |
| 772 | `materials[:5000]` | `clip(materials, label="pre-answer context")` |
| 806 | `max_chars=4000` | drop the arg |
| 1229 | `ctx[:5000]` | `clip(ctx, label="summary material")` |
| 1280 | `ctx[:8000]` | `clip(ctx, label="summary material")` |

In `derive_factor_tree` (Task A's main handler) and `run_minutes_digest`, after
`eng.produce(...)`, add:

```python
    tf = truncation_finding(clips)
    if tf is not None:
        eng.add_findings(st, task["id"], [tf])
```

where `clips` is the list of `ClipResult`s that handler produced.

Raise the `max_tokens` overrides: delete `max_tokens=3000` at line 774 and
`max_tokens=2048` at lines 1230 and 1281 and `common.py:216` so each call takes
the client default (`llm/volcano.py:226` — 16 000 for `json`).

In `backend/app/store/files.py`, change the two defaults to `None` meaning
"the budget":

```python
    def extract_category_text(self, project_id: str, category: FileCategory,
                              max_chars: int | None = None) -> str:
```
```python
    def extract_category_files(self, project_id: str, category: FileCategory,
                               per_file_cap: int | None = None) -> list[tuple[str, str]]:
```

resolving `None` to `grounding_budget()` inside each. Update
`agents/sources.py:15, 20` signatures to match (`max_chars: int | None = None`,
`per_file_cap: int | None = None`) and `business.py:825`'s
`_MINUTES_PER_FILE_CHARS = 12000` to `None`.

**Leave alone** — these are display/schema limits, not context budgets:
`evidence[:200]` (business.py:1019), `note[:120]` (1040), `title[:120]` (1037,
1047), `rationale[:120]` (328), `str(exc)[:300]` (1094), `_MAX_INSIGHTS`.

- [ ] **Step 6: Run the tests**

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m app.agents._test_grounding
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py
PYTHONPATH=. .venv/bin/python -m app.ingest._smoke
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/config.py backend/app/agents/common.py \
        backend/app/agents/business.py backend/app/agents/sources.py \
        backend/app/store/files.py backend/app/agents/_test_grounding.py
git commit -m "feat(s1): one grounding budget, and truncation is visible

A dozen independently-chosen caps (6000/9000/12000/...) silently trimmed
grounding material, so a 200-page deck and its first six thousand characters
produced indistinguishable deliverables. They collapse into
GROUNDING_MAX_CHARS (default 100k) and any handler that clips now emits a
finding naming the source and how much of it was used. Display limits
(evidence, titles) are untouched."
```

---

## Final verification

After Task 8, run everything:

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_indicators
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_claim
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_mapping_coverage
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_orphans
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_flow
PYTHONPATH=. .venv/bin/python -m app.dataeng._test_preview
PYTHONPATH=. .venv/bin/python -m app.store._test_indicator_migration
PYTHONPATH=. .venv/bin/python -m app.agents._test_grounding
PYTHONPATH=. .venv/bin/python -m app.agents._test_ledger_signoff
PYTHONPATH=. .venv/bin/python -m app.agents._test_ledger_endpoint
PYTHONPATH=. .venv/bin/python -m app.agents._test_master_data
PYTHONPATH=. .venv/bin/python -m app.agents._test_intake_gate
PYTHONPATH=. .venv/bin/python -m app.tools._test_tools
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py
cd ../frontend && npm run build && npm run lint
```

Then update `CLAUDE.md`'s Architecture section: the `app/dataeng/` line gains
`indicators.py` (the derivation) and `orphans.py`, and the S2 §2.1 paragraph's
description of `resolve_factor_map` changes from "derive per-row status from the
published indicators" to "from the coverage records publish attaches to factor
rows". Commit that separately as `docs: …`.
