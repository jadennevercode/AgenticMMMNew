# Restore model input_2.32 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `reference/02.数据智能体/【MMM AI】数据智能体-model input_2.32.xlsx` into a reviewed folder of artifacts — a FactorTree, per-source raw data files, a publish-ready 19-column long table — plus a rebuild script and a verification script that proves the long table actually fits an OLS model.

**Architecture:** A small package `backend/scripts/restore/` holds one focused module per artifact family (source loading, taxonomy derivation, factor tree, raw export, curated export, profiling). A thin CLI `backend/scripts/restore_model_input.py` orchestrates them. Verification lives in two runnable scripts (this repo has no pytest): `backend/scripts/restore/_test_units.py` for pure functions and `backend/scripts/_test_restore.py` for the end-to-end artifact + OLS assertions.

**Tech Stack:** Python 3.14, pandas, openpyxl (already in `backend/requirements.txt`). No new dependencies. Run everything from `backend/` with the venv at `backend/.venv`.

**Spec:** `docs/superpowers/specs/2026-07-22-restore-model-input-2.32-design.md`

## Global Constraints

- **Do not modify any file under `backend/app/`.** The restore is a consumer of the product code, never a modifier of it. If a task seems to need an `app/` change, stop and report instead.
- **No pytest.** This repo's tests are runnable scripts using bare `assert` plus a `main()` that exits non-zero on failure. Follow `backend/app/tools/_test_tools.py` for style.
- **Run commands** from `backend/` as: `PYTHONPATH=. .venv/bin/python -m scripts.<module>`.
- **Reference path resolution:** never hardcode `reference/…` with the Chinese directory name — macOS stores it in a Unicode normalisation that does not match a Python string literal. Always resolve by glob (Task 1).
- **`raw/` preserves the source verbatim** — no aggregation, no pivoting, no trimming of dirty enum values (`'NAB '`, `'Snack Store'`). Those dirty values are the Data Engine's job.
- **`curated/` writes the engine taxonomy** (`Baseline Factor` / `Marketing Factor` / `Commercial Factor` / `KPI`) in `l1`, never the Chinese business taxonomy. `pivot.is_driver_row()` keys on the English values; Chinese `l1` yields zero drivers and no model.
- **`metric_type` keeps the unit family** (`箱数`/`RMB`/`Volume`/`百分比`…). The only normalisation is `花费 → Spending`.
- **Losslessness is multiset equality, not set equality.** The source has 1,140 same-key-different-value detail groups and 105 fully duplicated rows; de-duplicating before comparison would hide a ~3,000-row loss.
- **Output root:** `restored/model-input-2.32/` at the repository root (sibling of `backend/`).

### Verified source facts (do not re-derive; assert against these)

| Fact | Value |
|---|---|
| `D.Data Station` rows | 23,813 |
| `l1 = 'KPI'` rows | 4,462 |
| Granularity sheet, `header=0`, non-blank indicator | 97 rows, **66** unique indicators |
| Non-KPI indicators present in the data (`Level5`) | **56** |
| Factor tree union | **85** rows — `both` 37 · `planned` 29 · `data` 19 |
| Distinct `数据源` | 29 |
| Taxonomy evidence rows | 生意基本盘 338 · 渠道成交驱动 519 · 消费者需求驱动 662 · 促销优惠 1,076 · KPI 4,459 |

`header=1` on the granularity sheet silently eats the first data row (`品类全渠道销量`) and yields 65/86 instead of 66/85. Task 1's test exists to catch exactly that.

## File Structure

| Path | Responsibility |
|---|---|
| `backend/scripts/__init__.py` | Make `scripts` importable as a package (empty file). |
| `backend/scripts/restore/__init__.py` | Package marker (empty file). |
| `backend/scripts/restore/paths.py` | Resolve source workbooks by glob; output directory layout; `mkdirs()`. |
| `backend/scripts/restore/source.py` | Load the two sheets: `load_station()` (verbatim values, dtypes only) and `load_granularity()` (forward-filled planned tree). |
| `backend/scripts/restore/taxonomy.py` | Derive the business→engine `l1` and `metric_type` maps by joining 2.32↔2.24. Raise on conflict or uncovered value. |
| `backend/scripts/restore/factor_tree.py` | Build the 85-row union FactorTree with `origin`; emit `factor-tree.json` / `.xlsx` / `reconciliation.md`. |
| `backend/scripts/restore/raw_export.py` | 29 per-source workbooks, sheet per Task name, verbatim slices. |
| `backend/scripts/restore/curated.py` | 19-column long table + `taxonomy_map.csv` + `indicators.csv`. |
| `backend/scripts/restore/profile.py` | `qa/profile.md` — per-indicator coverage and level sparsity. |
| `backend/scripts/restore/readme.py` | Render `restored/model-input-2.32/README.md` from computed counts. |
| `backend/scripts/restore/_test_units.py` | Unit assertions for the pure functions. |
| `backend/scripts/restore_model_input.py` | CLI orchestrator; runs all stages, prints a summary. |
| `backend/scripts/_test_restore.py` | End-to-end: schema, losslessness (raw + curated), OLS smoke → `qa/ols_smoke.txt`. |
| `.gitignore` | Add `restored/model-input-2.32/raw/` and `…/curated/long_table.*`. |

---

### Task 1: Source loading

**Files:**
- Create: `backend/scripts/__init__.py`
- Create: `backend/scripts/restore/__init__.py`
- Create: `backend/scripts/restore/paths.py`
- Create: `backend/scripts/restore/source.py`
- Create: `backend/scripts/restore/_test_units.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `paths.source_workbook() -> pathlib.Path`, `paths.reference_workbook_224() -> pathlib.Path`
  - `paths.OUT`, `paths.FACTOR_TREE_DIR`, `paths.RAW_DIR`, `paths.CURATED_DIR`, `paths.QA_DIR` (all `pathlib.Path`)
  - `paths.mkdirs() -> None`
  - `source.STATION_SHEET: str`, `source.GRANULARITY_SHEET: str`
  - `source.LEVEL_COLS: list[str]` — `['数据类型Level1', …, '数据类型Level8']`
  - `source.BUSINESS_COLS: list[str]` — the 19 business columns in source order
  - `source.load_station() -> pd.DataFrame` — 23,813 rows × 22 columns; `年`/`月` `Int64`, `VALUE` `float64`, string columns `string` dtype **with values untouched**
  - `source.load_granularity() -> pd.DataFrame` — 97 rows, columns `['l1','l2','l3','l4','indicator','channel','region']`, hierarchy forward-filled, blank-indicator rows dropped, 66 unique indicators

- [ ] **Step 1: Write the failing test**

Create `backend/scripts/restore/_test_units.py`:

```python
"""Unit assertions for the restore package's pure functions.

Run: PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units
"""
from __future__ import annotations

import sys

from scripts.restore import source


def test_load_station() -> None:
    df = source.load_station()
    assert len(df) == 23813, f"expected 23813 station rows, got {len(df)}"
    assert list(df.columns)[:8] == [
        "Task name", "品牌", "省份组别", "渠道类型", "渠道", "年", "月", "数据源",
    ], list(df.columns)[:8]
    assert source.LEVEL_COLS == [f"数据类型Level{i}" for i in range(1, 9)]
    assert set(source.LEVEL_COLS).issubset(df.columns)
    assert len(source.BUSINESS_COLS) == 19, source.BUSINESS_COLS
    # Dirty enum values must survive verbatim — the Data Engine cleans them, not us.
    brands = set(df["品牌"].dropna().unique())
    assert "NAB " in brands and "NAB" in brands, sorted(brands)
    assert str(df["月"].dtype) == "Int64", df["月"].dtype
    assert str(df["VALUE"].dtype) == "float64", df["VALUE"].dtype


def test_load_granularity() -> None:
    g = source.load_granularity()
    assert list(g.columns) == [
        "l1", "l2", "l3", "l4", "indicator", "channel", "region",
    ], list(g.columns)
    assert len(g) == 97, len(g)
    # 66, not 65: header=1 would silently eat the first data row (品类全渠道销量).
    assert g["indicator"].nunique() == 66, g["indicator"].nunique()
    assert "品类全渠道销量" in set(g["indicator"]), "the first data row was eaten"
    # Forward fill must have closed every hierarchy gap.
    for col in ("l1", "l2", "l3", "l4"):
        assert g[col].isna().sum() == 0, f"{col} still has {g[col].isna().sum()} gaps"
    # Spot-check a row that only resolves via forward fill.
    rain = g[g["indicator"] == "降水量"].iloc[0]
    assert (rain["l1"], rain["l2"], rain["l3"], rain["l4"]) == (
        "生意基本盘", "外部因素", "品类趋势", "季节性趋势",
    ), rain.to_dict()


TESTS = [test_load_station, test_load_granularity]


def main() -> int:
    failed = 0
    for fn in TESTS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

From `backend/`:
```bash
PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units
```
Expected: `ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 3: Create the package markers and `paths.py`**

```bash
mkdir -p scripts/restore && touch scripts/__init__.py scripts/restore/__init__.py
```

Create `backend/scripts/restore/paths.py`:

```python
"""Filesystem layout for the model-input restore.

The reference directory name contains CJK characters whose on-disk Unicode
normalisation does not match a Python string literal on macOS, so every source
path is resolved by glob rather than by name.
"""
from __future__ import annotations

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
REFERENCE = REPO / "reference"

OUT = REPO / "restored" / "model-input-2.32"
FACTOR_TREE_DIR = OUT / "factor-tree"
RAW_DIR = OUT / "raw"
CURATED_DIR = OUT / "curated"
QA_DIR = OUT / "qa"


def _glob_one(pattern: str, needle: str) -> Path:
    matches = [p for p in REFERENCE.glob(pattern) if needle in p.name]
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected exactly one reference file matching {pattern!r} + {needle!r}, "
            f"found {[str(p) for p in matches]}"
        )
    return matches[0]


def source_workbook() -> Path:
    """The 2.32 model-input workbook being restored."""
    return _glob_one("*/*.xlsx", "model input_2.32")


def reference_workbook_224() -> Path:
    """The 2.24 dataset — the engine-taxonomy view of the same data."""
    return _glob_one("*/*.xlsx", "Data Process_2.24")


def mkdirs() -> None:
    for d in (OUT, FACTOR_TREE_DIR, RAW_DIR, CURATED_DIR, QA_DIR):
        d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Write `source.py`**

Create `backend/scripts/restore/source.py`:

```python
"""Load the two sheets of the 2.32 model-input workbook.

`load_station` deliberately does NOT clean values: dirty enum spellings
('NAB ' vs 'NAB', 'Snack Store' vs 'snack store') are what the Data Engine's
clustering step exists to resolve, so the raw export must carry them through.
Only dtypes are coerced.
"""
from __future__ import annotations

import pandas as pd

from scripts.restore import paths

STATION_SHEET = "D.Data Station"
GRANULARITY_SHEET = "模型颗粒度参考表"

LEVEL_COLS = [f"数据类型Level{i}" for i in range(1, 9)]

# The 19 business columns of the source table. The three trailing naming columns
# (Variable / Variable no. / Metric no.) are source-internal metadata and ride
# only in indicators.csv.
BUSINESS_COLS = [
    "Task name", "品牌", "省份组别", "渠道类型", "渠道", "年", "月", "数据源",
    *LEVEL_COLS,
    "METRICS类型", "METRICS", "VALUE",
]

_STRING_COLS = [
    "Task name", "品牌", "省份组别", "渠道类型", "渠道", "数据源",
    *LEVEL_COLS,
    "METRICS类型", "METRICS",
]


def load_station() -> pd.DataFrame:
    """The 23,813-row detail ledger: dtypes coerced, values verbatim."""
    df = pd.read_excel(paths.source_workbook(), sheet_name=STATION_SHEET,
                       engine="openpyxl")
    df.columns = [str(c) for c in df.columns]
    for col in _STRING_COLS:
        df[col] = df[col].astype("string")
    df["年"] = pd.to_numeric(df["年"], errors="coerce").astype("Int64")
    df["月"] = pd.to_numeric(df["月"], errors="coerce").astype("Int64")
    df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce").astype("float64")
    return df.reset_index(drop=True)


def load_granularity() -> pd.DataFrame:
    """The planned factor tree: L1-L4 + indicator + channel/region granularity.

    Read with `header=0` — the header is the sheet's first row and the first
    column is blank. Reading with `header=1` silently consumes the first data
    row (品类全渠道销量) and undercounts the planned indicators by one.

    The hierarchy columns are merged-cell sparse, so L1-L4 are forward-filled.
    Rows without an indicator carry no information and are dropped.
    """
    g = pd.read_excel(paths.source_workbook(), sheet_name=GRANULARITY_SHEET,
                      header=0, engine="openpyxl")
    g = g.iloc[:, 1:8]  # drop the leading blank column
    g.columns = ["l1", "l2", "l3", "l4", "indicator", "channel", "region"]
    for col in g.columns:
        g[col] = g[col].astype("string").str.strip().replace({"": pd.NA})
    g[["l1", "l2", "l3", "l4"]] = g[["l1", "l2", "l3", "l4"]].ffill()
    g = g[g["indicator"].notna()]
    return g.reset_index(drop=True)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units
```
Expected: `PASS test_load_station`, `PASS test_load_granularity`, `2/2 passed`, exit 0.

If the indicator count is not 66, print `g["indicator"].tolist()` and check the `header=0` read and the `iloc[:, 1:8]` slice. Do **not** relax the assertion to match whatever came out.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/__init__.py backend/scripts/restore/
git commit -m "feat(restore): load the 2.32 model-input sheets"
```

---

### Task 2: Taxonomy derivation

**Files:**
- Create: `backend/scripts/restore/taxonomy.py`
- Modify: `backend/scripts/restore/_test_units.py` (append two tests, extend `TESTS`)

**Interfaces:**
- Consumes: `source.load_station()`, `paths.reference_workbook_224()`
- Produces:
  - `taxonomy.TaxonomyError(Exception)`
  - `taxonomy.TaxonomyMap` — dataclass, fields `l1: dict[str, str]`, `metric_type: dict[str, str]`, `evidence: dict[str, int]` (key `f"l1:{business}"` / `f"metric_type:{src}"` → matched row count)
  - `taxonomy.derive(station: pd.DataFrame) -> TaxonomyMap`
  - `taxonomy.apply_l1(series: pd.Series, tmap: TaxonomyMap) -> pd.Series`
  - `taxonomy.apply_metric_type(series: pd.Series, tmap: TaxonomyMap) -> pd.Series`

- [ ] **Step 1: Write the failing test**

Append to `_test_units.py`, immediately above the `TESTS` list:

```python
from scripts.restore import taxonomy


def test_derive_taxonomy() -> None:
    tmap = taxonomy.derive(source.load_station())
    assert tmap.l1 == {
        "生意基本盘": "Baseline Factor",
        "渠道成交驱动": "Marketing Factor",
        "消费者需求驱动": "Marketing Factor",
        "促销优惠": "Commercial Factor",
        "KPI": "KPI",
    }, tmap.l1
    # Every mapping must be backed by real matched rows, and the report must say
    # how many — a thinly-supported mapping is a reviewable risk, not a secret.
    assert tmap.evidence["l1:渠道成交驱动"] == 519, tmap.evidence
    assert tmap.evidence["l1:KPI"] == 4459, tmap.evidence
    # 花费 is the only metric_type that must be renamed: pivot._is_spend() looks
    # for the 2.24 spelling.
    assert tmap.metric_type["花费"] == "Spending", tmap.metric_type
    assert tmap.metric_type["箱数"] == "箱数", tmap.metric_type


def test_taxonomy_rejects_uncovered_value() -> None:
    station = source.load_station()
    station.loc[0, "数据类型Level1"] = "全新的业务分类"
    try:
        taxonomy.derive(station)
    except taxonomy.TaxonomyError as exc:
        assert "全新的业务分类" in str(exc), str(exc)
    else:
        raise AssertionError("derive() accepted an L1 value with no derivable mapping")
```

Replace the `TESTS` list with:

```python
TESTS = [
    test_load_station,
    test_load_granularity,
    test_derive_taxonomy,
    test_taxonomy_rejects_uncovered_value,
]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units
```
Expected: `ImportError: cannot import name 'taxonomy' from 'scripts.restore'`

- [ ] **Step 3: Write `taxonomy.py`**

Create `backend/scripts/restore/taxonomy.py`:

```python
"""Derive the business→engine taxonomy map by joining 2.32 against 2.24.

2.32 and 2.24 are the same dataset in two vocabularies: 2.32 speaks the business
factor names (生意基本盘 / 渠道成交驱动 / …), 2.24 speaks the modeling names
(Baseline Factor / Marketing Factor / …). `app.mmm.pivot.is_driver_row` keys on
the modeling names, so a curated table written in the business vocabulary yields
zero drivers and no model at all.

The map is *derived from the data*, never declared: we join on the natural key
and read off the correspondence. A mapping that is ambiguous (one business value
seen against two modeling values) or absent (a business value the join never
covers) raises rather than falling back to a guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from scripts.restore import paths

REFERENCE_224_SHEET = "dataset_model_data_yyyymm_20260"

# The natural key shared by both workbooks.
_JOIN_KEY = ["Task name", "品牌", "省份组别", "渠道类型", "渠道", "年", "月",
             "METRICS", "VALUE"]


class TaxonomyError(Exception):
    """The taxonomy could not be derived unambiguously from the data."""


@dataclass
class TaxonomyMap:
    l1: dict[str, str] = field(default_factory=dict)
    metric_type: dict[str, str] = field(default_factory=dict)
    evidence: dict[str, int] = field(default_factory=dict)


def _load_224() -> pd.DataFrame:
    df = pd.read_excel(paths.reference_workbook_224(),
                       sheet_name=REFERENCE_224_SHEET, engine="openpyxl")
    df.columns = [str(c) for c in df.columns]
    for col in ("Task name", "品牌", "省份组别", "渠道类型", "渠道",
                "数据类型Level1", "METRICS", "METRICS类型"):
        df[col] = df[col].astype("string")
    df["年"] = pd.to_numeric(df["年"], errors="coerce").astype("Int64")
    df["月"] = pd.to_numeric(df["月"], errors="coerce").astype("Int64")
    df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce").astype("float64")
    return df


def _derive_column(matched: pd.DataFrame, src: str, dst: str,
                   label: str, tmap: TaxonomyMap) -> dict[str, str]:
    """Read off src→dst from the matched rows; raise if it is not a function."""
    pairs = matched.groupby([src, dst], dropna=False).size()
    out: dict[str, str] = {}
    for (business, engine), count in pairs.items():
        if pd.isna(business) or pd.isna(engine):
            continue
        business, engine = str(business), str(engine)
        if business in out and out[business] != engine:
            raise TaxonomyError(
                f"{label} mapping is ambiguous: {business!r} maps to both "
                f"{out[business]!r} and {engine!r}"
            )
        out[business] = engine
        tmap.evidence[f"{label}:{business}"] = int(count)
    return out


def derive(station: pd.DataFrame) -> TaxonomyMap:
    """Derive the l1 and metric_type maps, or raise."""
    right = _load_224()
    cols = _JOIN_KEY + ["数据类型Level1", "METRICS类型"]
    matched = station[cols].merge(
        right[cols], on=_JOIN_KEY, how="inner", suffixes=("_32", "_24"),
    ).drop_duplicates()
    if matched.empty:
        raise TaxonomyError("2.32 and 2.24 share no rows on the natural key")

    tmap = TaxonomyMap()
    tmap.l1 = _derive_column(matched, "数据类型Level1_32", "数据类型Level1_24",
                             "l1", tmap)
    tmap.metric_type = _derive_column(matched, "METRICS类型_32", "METRICS类型_24",
                                      "metric_type", tmap)

    uncovered = set(station["数据类型Level1"].dropna().astype(str)) - set(tmap.l1)
    if uncovered:
        raise TaxonomyError(
            f"no derivable l1 mapping for {sorted(uncovered)} — the join covers "
            f"{sorted(tmap.l1)}. Refusing to guess."
        )

    # metric_type values the join never covered pass through unchanged; the one
    # rename the engine actually depends on is pinned explicitly.
    tmap.metric_type.setdefault("花费", "Spending")
    return tmap


def apply_l1(series: pd.Series, tmap: TaxonomyMap) -> pd.Series:
    return (series.astype("string")
            .map(lambda v: tmap.l1.get(str(v), v))
            .astype("string"))


def apply_metric_type(series: pd.Series, tmap: TaxonomyMap) -> pd.Series:
    return (series.astype("string")
            .map(lambda v: tmap.metric_type.get(str(v), v))
            .astype("string"))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units
```
Expected: `4/4 passed`, exit 0.

If `evidence["l1:渠道成交驱动"]` is not 519, do not edit the assertion — print `matched.groupby(["数据类型Level1_32","数据类型Level1_24"]).size()` and reconcile against `_JOIN_KEY`.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/restore/taxonomy.py backend/scripts/restore/_test_units.py
git commit -m "feat(restore): derive business->engine taxonomy from the 2.32/2.24 join"
```

---

### Task 3: Factor tree

**Files:**
- Create: `backend/scripts/restore/factor_tree.py`
- Modify: `backend/scripts/restore/_test_units.py` (append one test, extend `TESTS`)

**Interfaces:**
- Consumes: `source.load_station()`, `source.load_granularity()`
- Produces:
  - `factor_tree.build(station: pd.DataFrame, granularity: pd.DataFrame) -> pd.DataFrame` — 85 rows, columns `['id','l1','l2','l3','l4','indicator','dimension','source','status','rationale','evidence','origin','hasData','rows','monthsCovered']`
  - `factor_tree.write(tree: pd.DataFrame) -> None` — emits `factor-tree.json`, `factor-tree.xlsx`, `reconciliation.md` into `paths.FACTOR_TREE_DIR`

- [ ] **Step 1: Write the failing test**

Append to `_test_units.py` above `TESTS`:

```python
from scripts.restore import factor_tree


def test_factor_tree_union() -> None:
    tree = factor_tree.build(source.load_station(), source.load_granularity())
    assert list(tree.columns) == [
        "id", "l1", "l2", "l3", "l4", "indicator", "dimension", "source",
        "status", "rationale", "evidence", "origin", "hasData", "rows",
        "monthsCovered",
    ], list(tree.columns)
    counts = tree["origin"].value_counts().to_dict()
    assert counts == {"both": 37, "planned": 29, "data": 19}, counts
    assert len(tree) == 85, len(tree)
    assert tree["id"].is_unique
    assert tree["indicator"].is_unique
    # FactorRow contract: the restore never pre-judges a row.
    assert set(tree["source"]) == {"template"}, set(tree["source"])
    assert set(tree["status"]) == {"baseline"}, set(tree["status"])
    # planned-only rows have no data by definition; data-bearing rows must have months.
    planned = tree[tree["origin"] == "planned"]
    assert (planned["rows"] == 0).all() and (~planned["hasData"]).all()
    withdata = tree[tree["origin"] != "planned"]
    assert (withdata["monthsCovered"] > 0).all(), \
        withdata[withdata["monthsCovered"] == 0]["indicator"].tolist()
    # KPI is the response, not a factor-tree leaf.
    assert "KPI" not in set(tree["indicator"]), "KPI leaked into the factor tree"
```

Extend `TESTS` with `test_factor_tree_union`.

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units
```
Expected: `ImportError: cannot import name 'factor_tree' from 'scripts.restore'`

- [ ] **Step 3: Write `factor_tree.py`**

Create `backend/scripts/restore/factor_tree.py`:

```python
"""Reconstruct the FactorTree as the union of the planned and the actual trees.

Two facts drive this module:

1. The level offset — the granularity sheet's 指标选择 column *is* the data
   table's 数据类型Level5. So FactorRow.l1..l4 <- Level1..Level4 and
   FactorRow.indicator <- Level5. L6-L8 are drill-down dimensions that live on
   the long table only; FactorRow has no fields for them.
2. The two trees disagree. 29 planned indicators have no data and 19 data-bearing
   indicators were never planned. We keep both and label the difference with
   `origin`, so the 2.1 factor-map gate sees the planned-but-empty rows as
   `pending` and a human decides to ignore them — which is the point of that gate.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from scripts.restore import paths

# KPI rows carry the literal 'KPI' at every level: the response is not a factor.
_KPI = "KPI"

_LEVELS = ["数据类型Level1", "数据类型Level2", "数据类型Level3", "数据类型Level4"]

# A control character no level name can contain, so the modal path splits back
# apart cleanly (an empty separator is a ValueError).
_SEP = "\x1f"

_COLUMNS = ["id", "l1", "l2", "l3", "l4", "indicator", "dimension", "source",
            "status", "rationale", "evidence", "origin", "hasData", "rows",
            "monthsCovered"]

_ID_UNSAFE = re.compile(r"[^0-9a-z]+")


def _row_id(indicator: str, seq: int) -> str:
    slug = _ID_UNSAFE.sub("-", str(indicator).lower()).strip("-")
    return f"fr-{seq:03d}-{slug}" if slug else f"fr-{seq:03d}"


def _actual_rows(station: pd.DataFrame) -> pd.DataFrame:
    """Per-indicator L1-L4 path + coverage, read off the data table."""
    df = station[station["数据类型Level1"] != _KPI].copy()
    df["数据类型Level5"] = df["数据类型Level5"].astype("string").str.strip()
    df = df[df["数据类型Level5"].notna() & (df["数据类型Level5"] != "")]
    out = []
    for indicator, g in df.groupby("数据类型Level5", dropna=True):
        # An indicator can appear under several paths; the modal one is its home.
        joined = (g[_LEVELS].astype("string").fillna("")
                  .agg(_SEP.join, axis=1).mode().iloc[0])
        path = joined.split(_SEP)
        channels = sorted({str(v) for v in g["渠道类型"].dropna().unique()})
        regions = sorted({str(v) for v in g["省份组别"].dropna().unique()})
        out.append({
            "indicator": str(indicator),
            "l1": path[0], "l2": path[1], "l3": path[2], "l4": path[3],
            "dimension": ", ".join(channels + regions),
            "rows": int(len(g)),
            "monthsCovered": int(g["月"].dropna().nunique()),
        })
    return pd.DataFrame(out)


def build(station: pd.DataFrame, granularity: pd.DataFrame) -> pd.DataFrame:
    """The union tree: planned ∪ actual, each row labelled with its origin."""
    actual = _actual_rows(station)
    actual_by_ind = {r["indicator"]: r for r in actual.to_dict("records")}

    rows: list[dict] = []
    planned_names: set[str] = set()
    for rec in granularity.to_dict("records"):
        indicator = str(rec["indicator"])
        if indicator in planned_names:
            continue  # the sheet repeats indicators across granularity variants
        planned_names.add(indicator)
        hit = actual_by_ind.get(indicator)
        planned_dim = ", ".join(
            str(rec[c]) for c in ("channel", "region") if pd.notna(rec[c]))
        rows.append({
            "l1": str(rec["l1"]), "l2": str(rec["l2"]),
            "l3": str(rec["l3"]), "l4": str(rec["l4"]),
            "indicator": indicator,
            "dimension": planned_dim,
            "origin": "both" if hit else "planned",
            "hasData": bool(hit),
            "rows": int(hit["rows"]) if hit else 0,
            "monthsCovered": int(hit["monthsCovered"]) if hit else 0,
        })

    for rec in actual.to_dict("records"):
        if rec["indicator"] in planned_names:
            continue
        rows.append({
            "l1": rec["l1"], "l2": rec["l2"], "l3": rec["l3"], "l4": rec["l4"],
            "indicator": rec["indicator"], "dimension": rec["dimension"],
            "origin": "data", "hasData": True,
            "rows": rec["rows"], "monthsCovered": rec["monthsCovered"],
        })

    tree = pd.DataFrame(rows)
    tree["id"] = [_row_id(r.indicator, i + 1)
                  for i, r in enumerate(tree.itertuples())]
    # The restore never pre-judges a row — source/status stay at model defaults.
    tree["source"] = "template"
    tree["status"] = "baseline"
    tree["rationale"] = ""
    tree["evidence"] = ""
    return tree[_COLUMNS].reset_index(drop=True)


def write(tree: pd.DataFrame) -> None:
    """Emit factor-tree.json, factor-tree.xlsx and reconciliation.md."""
    paths.mkdirs()

    # FactorTree{rows:[FactorRow]} — exactly the PUT /factor-tree payload.
    payload = {"rows": [
        {k: r[k] for k in ("id", "l1", "l2", "l3", "l4", "indicator",
                           "dimension", "source", "status", "rationale",
                           "evidence")}
        for r in tree.to_dict("records")
    ]}
    (paths.FACTOR_TREE_DIR / "factor-tree.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    tree.to_excel(paths.FACTOR_TREE_DIR / "factor-tree.xlsx", index=False)

    planned = tree[tree["origin"] == "planned"]
    data_only = tree[tree["origin"] == "data"]
    both = tree[tree["origin"] == "both"]
    lines = [
        "# 因子树还原：规划态 vs 实际态",
        "",
        f"因子树 = 规划 ∪ 实际 = **{len(tree)}** 行"
        f"（both {len(both)} · planned {len(planned)} · data {len(data_only)}）。",
        "",
        "## 规划了但没有数据（origin=planned）",
        "",
        "这些行在 2.1 因子映射门禁里会是 `pending`，需要人工 ignore 或补数据。",
        "",
        "| L1 | L2 | L3 | L4 | Indicator | 计划粒度 |",
        "|---|---|---|---|---|---|",
    ]
    for r in planned.to_dict("records"):
        lines.append(f"| {r['l1']} | {r['l2']} | {r['l3']} | {r['l4']} "
                     f"| {r['indicator']} | {r['dimension']} |")
    lines += [
        "",
        "## 有数据但未入规划树（origin=data）",
        "",
        "这些指标已补进因子树，L1-L4 取其在长表中出现最频繁的层级路径。",
        "",
        "| L1 | L2 | L3 | L4 | Indicator | 行数 | 覆盖月数 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in data_only.to_dict("records"):
        lines.append(f"| {r['l1']} | {r['l2']} | {r['l3']} | {r['l4']} "
                     f"| {r['indicator']} | {r['rows']} | {r['monthsCovered']} |")
    lines.append("")
    (paths.FACTOR_TREE_DIR / "reconciliation.md").write_text(
        "\n".join(lines), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units
```
Expected: `5/5 passed`, exit 0.

If the origin counts differ from `{both: 37, planned: 29, data: 19}`, the level offset or the KPI exclusion is wrong — investigate `_actual_rows`, do not edit the assertion.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/restore/factor_tree.py backend/scripts/restore/_test_units.py
git commit -m "feat(restore): build the union factor tree with origin labelling"
```

---

### Task 4: Curated 19-column long table

**Files:**
- Create: `backend/scripts/restore/curated.py`
- Modify: `backend/scripts/restore/_test_units.py` (append two tests, extend `TESTS`)

**Interfaces:**
- Consumes: `source.load_station()`, `taxonomy.derive()`, `taxonomy.apply_l1`, `taxonomy.apply_metric_type`
- Produces:
  - `curated.build(station: pd.DataFrame, tmap: taxonomy.TaxonomyMap) -> pd.DataFrame` — 23,813 rows, columns exactly `app.ingest.dataset.COLUMN_NAMES`
  - `curated.write(long: pd.DataFrame, station: pd.DataFrame, tmap: taxonomy.TaxonomyMap) -> None` — emits `long_table.csv`, `long_table.xlsx`, `taxonomy_map.csv`, `indicators.csv` into `paths.CURATED_DIR`

- [ ] **Step 1: Write the failing test**

Append to `_test_units.py` above `TESTS`:

```python
from app.ingest.dataset import COLUMN_NAMES
from scripts.restore import curated


def test_curated_long_table() -> None:
    station = source.load_station()
    tmap = taxonomy.derive(station)
    long = curated.build(station, tmap)
    assert list(long.columns) == COLUMN_NAMES, list(long.columns)
    assert len(long) == len(station), (len(long), len(station))
    # Rule 2: the engine taxonomy, or is_driver_row() finds nothing.
    assert set(long["l1"].dropna()) <= {
        "Baseline Factor", "Marketing Factor", "Commercial Factor", "KPI",
    }, set(long["l1"].dropna())
    # Rule 3: metric_type stays a unit family; only 花费 is renamed.
    assert "花费" not in set(long["metric_type"].dropna())
    assert "Spending" in set(long["metric_type"].dropna())
    assert "箱数" in set(long["metric_type"].dropna())
    # Rule 4: both Y families survive as candidates.
    kpi = long[long["l1"] == "KPI"]
    assert len(kpi) == 4462, len(kpi)
    assert {"箱数", "RMB"} <= set(kpi["metric_type"].dropna()), \
        set(kpi["metric_type"].dropna())
    # Dirty enums are cleaned here (unlike raw/).
    assert "NAB " not in set(long["brand"].dropna()), sorted(set(long["brand"].dropna()))


def test_curated_finds_drivers_and_response() -> None:
    from app.mmm.pivot import _is_y_row, is_driver_row
    station = source.load_station()
    long = curated.build(station, taxonomy.derive(station))
    assert int(is_driver_row(long).sum()) > 0, "no driver rows — l1 taxonomy is wrong"
    assert int(_is_y_row(long).sum()) > 0, "no Y rows — the KPI l1 tag was lost"
```

Extend `TESTS` with both new tests.

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units
```
Expected: `ImportError: cannot import name 'curated' from 'scripts.restore'`

- [ ] **Step 3: Write `curated.py`**

Create `backend/scripts/restore/curated.py`:

```python
"""The publish-ready 19-column long table + its provenance sidecars.

This is a 1:1 row-for-row translation of the source detail ledger — never an
aggregation. The source's 1,140 same-key-different-value detail groups are real
activity records; `build_model_frame` sums them at pivot time, and collapsing
them here would silently change every downstream number.
"""
from __future__ import annotations

import pandas as pd

from app.ingest.dataset import COLUMN_NAMES
from scripts.restore import paths, taxonomy

# Source column -> canonical long-table column.
_RENAME = {
    "Task name": "task_name", "品牌": "brand", "省份组别": "province_group",
    "渠道类型": "channel_type", "渠道": "channel", "年": "year", "月": "month",
    "数据源": "source",
    "数据类型Level1": "l1", "数据类型Level2": "l2", "数据类型Level3": "l3",
    "数据类型Level4": "l4", "数据类型Level5": "l5", "数据类型Level6": "l6",
    "数据类型Level7": "l7", "数据类型Level8": "l8",
    "METRICS类型": "metric_type", "METRICS": "metric", "VALUE": "value",
}

_STRING_COLS = [c for c in COLUMN_NAMES if c not in ("year", "month", "value")]


def build(station: pd.DataFrame, tmap: taxonomy.TaxonomyMap) -> pd.DataFrame:
    """Translate the source ledger into the canonical long table."""
    df = station[list(_RENAME)].rename(columns=_RENAME).copy()
    df["l1"] = taxonomy.apply_l1(df["l1"], tmap)
    df["metric_type"] = taxonomy.apply_metric_type(df["metric_type"], tmap)
    # curated/ is the clean side: normalise the dirty enum spellings raw/
    # deliberately preserves, matching ingest.dataset.load_model_dataset.
    for col in _STRING_COLS:
        df[col] = (df[col].astype("string").str.strip()
                   .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA}))
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["month"] = pd.to_numeric(df["month"], errors="coerce").astype("Int64")
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype("float64")
    return df[COLUMN_NAMES].reset_index(drop=True)


def _mode_or_blank(series: pd.Series) -> str:
    clean = series.dropna()
    return "" if clean.empty else str(clean.mode().iloc[0])


def _indicator_catalog(station: pd.DataFrame, long: pd.DataFrame) -> pd.DataFrame:
    """One row per (l4, metric) — the Indicator-model view, plus source metadata."""
    naming = (station[["数据类型Level5", "METRICS", "Variable", "Variable no.",
                       "Metric no."]]
              .rename(columns={"数据类型Level5": "l5", "METRICS": "metric"})
              .copy())
    # `long` was trimmed by build(); trim the join keys here too, or the merge
    # silently misses every row whose source value carried whitespace.
    for key in ("l5", "metric"):
        naming[key] = naming[key].astype("string").str.strip()
    naming = naming.drop_duplicates(subset=["l5", "metric"])

    rows = []
    for (l4, metric), g in long.groupby(["l4", "metric"], dropna=False):
        months = g["month"].dropna()
        has_value = g["value"].notna().any()
        rows.append({
            "l1": _mode_or_blank(g["l1"]),
            "l2": _mode_or_blank(g["l2"]),
            "l3": _mode_or_blank(g["l3"]),
            "l4": "" if pd.isna(l4) else str(l4),
            "l5": _mode_or_blank(g["l5"]),
            "metric": "" if pd.isna(metric) else str(metric),
            "metricType": _mode_or_blank(g["metric_type"]),
            "rows": int(len(g)),
            "coverageStart": int(months.min()) if not months.empty else 0,
            "coverageEnd": int(months.max()) if not months.empty else 0,
            "monthsCovered": int(months.nunique()),
            "nullRate": round(float(g["value"].isna().mean()), 4),
            "valueMin": float(g["value"].min()) if has_value else None,
            "valueMax": float(g["value"].max()) if has_value else None,
        })
    cat = pd.DataFrame(rows)
    return (cat.merge(naming, on=["l5", "metric"], how="left")
            .sort_values(["l1", "l2", "l3", "l4", "metric"]))


def write(long: pd.DataFrame, station: pd.DataFrame,
          tmap: taxonomy.TaxonomyMap) -> None:
    paths.mkdirs()
    long.to_csv(paths.CURATED_DIR / "long_table.csv", index=False,
                encoding="utf-8-sig")
    long.to_excel(paths.CURATED_DIR / "long_table.xlsx", index=False)

    tax_rows = [
        {"kind": kind, "source": src, "target": dst,
         "evidenceRows": tmap.evidence.get(f"{kind}:{src}", 0)}
        for kind, mapping in (("l1", tmap.l1), ("metric_type", tmap.metric_type))
        for src, dst in sorted(mapping.items())
    ]
    pd.DataFrame(tax_rows).to_csv(paths.CURATED_DIR / "taxonomy_map.csv",
                                  index=False, encoding="utf-8-sig")

    _indicator_catalog(station, long).to_csv(
        paths.CURATED_DIR / "indicators.csv", index=False, encoding="utf-8-sig")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units
```
Expected: `7/7 passed`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/restore/curated.py backend/scripts/restore/_test_units.py
git commit -m "feat(restore): emit the publish-ready 19-column long table"
```

---

### Task 5: Raw per-source export

**Files:**
- Create: `backend/scripts/restore/raw_export.py`
- Modify: `backend/scripts/restore/_test_units.py` (append one test, extend `TESTS`)

**Interfaces:**
- Consumes: `source.load_station()`, `source.BUSINESS_COLS`
- Produces:
  - `raw_export.safe_name(value: str) -> str` — filesystem/sheet-safe name, ≤31 chars
  - `raw_export.write(station: pd.DataFrame) -> list[str]` — one `.xlsx` per `数据源` into `paths.RAW_DIR`; returns the sorted filenames written

- [ ] **Step 1: Write the failing test**

Append to `_test_units.py` above `TESTS`:

```python
from scripts.restore import raw_export


def test_safe_name() -> None:
    assert raw_export.safe_name("Trade ANP 线下数据-Sandro") == "Trade ANP 线下数据-Sandro"
    assert raw_export.safe_name("a/b:c*d?e") == "a_b_c_d_e"
    assert len(raw_export.safe_name("x" * 60)) <= 31
    assert raw_export.safe_name("   ") == "unnamed"
```

Extend `TESTS` with `test_safe_name`. The round-trip losslessness of the written files is asserted end-to-end in Task 7, where the files actually exist.

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units
```
Expected: `ImportError: cannot import name 'raw_export' from 'scripts.restore'`

- [ ] **Step 3: Write `raw_export.py`**

Create `backend/scripts/restore/raw_export.py`:

```python
"""One workbook per 数据源, sheet per Task name — verbatim source slices.

Deliberately NOT a wide table. The source is a detail ledger: the same
(dimensions + full L1-L8 path + month + metric) key carries up to six distinct
activity-level values, and nothing in the data pairs a Spending record with a
签约门店数 record. Pivoting would force a choice between aggregating (which
destroys the detail the ledger exists to record) and inventing a record pairing
(which is fabrication). So each row here is one source row.

Values are copied verbatim, including the dirty enum spellings ('NAB ' vs 'NAB',
'Snack Store' vs 'snack store') — resolving those is exactly what the Data
Engine's enum clustering step is for.
"""
from __future__ import annotations

import re

import pandas as pd

from scripts.restore import paths, source

_UNSAFE = re.compile(r'[\\/:*?"<>|\[\]]+')
_SHEET_MAX = 31  # Excel's hard limit


def safe_name(value: str) -> str:
    """A filesystem- and Excel-sheet-safe name (<=31 chars)."""
    cleaned = _UNSAFE.sub("_", str(value)).strip()
    return (cleaned or "unnamed")[:_SHEET_MAX]


def write(station: pd.DataFrame) -> list[str]:
    """Write one workbook per data source; return the filenames written."""
    paths.mkdirs()
    written: list[str] = []
    for src, g in station.groupby("数据源", dropna=False):
        label = "未标注数据源" if pd.isna(src) else str(src)
        filename = f"{safe_name(label)}.xlsx"
        used: set[str] = set()
        with pd.ExcelWriter(paths.RAW_DIR / filename, engine="openpyxl") as writer:
            for task, tg in g.groupby("Task name", dropna=False):
                base = safe_name("未标注Task" if pd.isna(task) else str(task))
                name, i = base, 2
                while name in used:
                    suffix = f"_{i}"
                    name = base[: _SHEET_MAX - len(suffix)] + suffix
                    i += 1
                used.add(name)
                tg[source.BUSINESS_COLS].to_excel(writer, sheet_name=name,
                                                  index=False)
        written.append(filename)
    return sorted(written)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units
```
Expected: `8/8 passed`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/restore/raw_export.py backend/scripts/restore/_test_units.py
git commit -m "feat(restore): export per-source raw slices at detail grain"
```

---

### Task 6: Profile, README and the CLI orchestrator

**Files:**
- Create: `backend/scripts/restore/profile.py`
- Create: `backend/scripts/restore/readme.py`
- Create: `backend/scripts/restore_model_input.py`
- Modify: `.gitignore` (repo root)

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces:
  - `profile.write(long: pd.DataFrame) -> None` — emits `qa/profile.md`
  - `readme.write(stats: dict) -> None` — emits `README.md`; `stats` keys: `treeRows`, `originCounts`, `rawFiles`, `curatedRows`, `taxonomy` (a `TaxonomyMap`)
  - CLI: `PYTHONPATH=. .venv/bin/python -m scripts.restore_model_input`

- [ ] **Step 1: Write `profile.py`**

Create `backend/scripts/restore/profile.py`:

```python
"""Per-indicator coverage report for the curated long table."""
from __future__ import annotations

import pandas as pd

from scripts.restore import paths


def write(long: pd.DataFrame) -> None:
    paths.mkdirs()
    months = long["month"].dropna()
    lines = [
        "# QA · 指标画像",
        "",
        f"长表共 **{len(long)}** 行，覆盖 {int(months.min())}–{int(months.max())}，"
        f"{months.nunique()} 个月。",
        "",
        "## 层级稀疏度",
        "",
        "| 列 | 非空行数 | 非空占比 |",
        "|---|---|---|",
    ]
    for col in ("l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8"):
        nn = int(long[col].notna().sum())
        lines.append(f"| {col} | {nn} | {nn / len(long):.1%} |")

    lines += [
        "",
        "## 逐指标覆盖",
        "",
        "| L4 | Metric | 单位 | 行数 | 起 | 止 | 覆盖月数 | 缺失率 | min | max |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (l4, metric), g in long.groupby(["l4", "metric"], dropna=False):
        m = g["month"].dropna()
        unit = g["metric_type"].dropna()
        has_value = g["value"].notna().any()
        lines.append(
            f"| {'' if pd.isna(l4) else l4} | {'' if pd.isna(metric) else metric} "
            f"| {unit.iloc[0] if not unit.empty else ''} | {len(g)} "
            f"| {int(m.min()) if not m.empty else ''} "
            f"| {int(m.max()) if not m.empty else ''} "
            f"| {m.nunique()} | {g['value'].isna().mean():.1%} "
            f"| {g['value'].min() if has_value else ''} "
            f"| {g['value'].max() if has_value else ''} |"
        )
    lines.append("")
    (paths.QA_DIR / "profile.md").write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 2: Write `readme.py`**

Create `backend/scripts/restore/readme.py`:

```python
"""Render the artifact folder's README from the computed stats."""
from __future__ import annotations

from scripts.restore import paths

_TEMPLATE = """# model input_2.32 还原产物

由 `backend/scripts/restore_model_input.py` 从
`reference/02.数据智能体/【MMM AI】数据智能体-model input_2.32.xlsx` 生成，可重跑。

设计文档：`docs/superpowers/specs/2026-07-22-restore-model-input-2.32-design.md`

## 目录

| 路径 | 内容 |
|---|---|
| `factor-tree/factor-tree.json` | `FactorTree{{rows:[FactorRow]}}`，可直接 `PUT /api/projects/{{id}}/factor-tree` |
| `factor-tree/factor-tree.xlsx` | 同一棵树的人读视图（含 origin / 覆盖月数） |
| `factor-tree/reconciliation.md` | 规划态与实际态的差异逐条对照 |
| `raw/` | {raw_files} 个 workbook，按 `数据源` 切片，**明细粒度、中文原列名、脏值保留** |
| `curated/long_table.csv` | {curated_rows} 行 19 列 canonical 长表，publish-ready |
| `curated/taxonomy_map.csv` | 业务词表→引擎词表映射，附每条的证据行数 |
| `curated/indicators.csv` | 逐指标 catalog（层级、单位、覆盖区间、缺失率、极值） |
| `qa/profile.md` | 层级稀疏度 + 逐指标覆盖 |
| `qa/ols_smoke.txt` | 验证脚本输出：Y / drivers / R² / n_obs |

## 因子树

共 **{tree_rows}** 行 = 规划 ∪ 实际，每行带 `origin`：

- `both`（{both}）两边都有
- `planned`（{planned}）规划了但没有数据 —— 在 2.1 因子映射门禁里会是 `pending`，需要人工 ignore
- `data`（{data}）有数据但未入规划树 —— 已补进树，L1-L4 取其在长表中最频繁的层级路径

层级偏移：颗粒度参考表的 `指标选择` **等于** 数据表的 `数据类型Level5`。
所以 `FactorRow.l1..l4 ← Level1..Level4`，`FactorRow.indicator ← Level5`。
`Level6–L8` 是下钻维度，只在长表上，不进因子树。

## 为什么 `raw/` 不是宽表

源表是**明细流水**，不是聚合表。用全部维度 + 全部 8 层因子路径 + 月 + 指标名做键，
23,813 行只压到 20,699 组，其中 1,140 组的取值互不相同。
例如 `ANP spending 微信立减 / A / AFH / 202409` 下有 6 条不同的 `Spending`
与 6 条不同的 `签约门店数` —— 那是 6 场活动。

源表里没有任何字段能把第 N 条 Spending 和第 N 条 签约门店数 配成一行。
所以做宽表只能二选一：聚合（毁掉明细）或编造配对（凭空造数）。两条都不做，
`raw/` 因此保持明细粒度。`curated/` 不受影响 —— 19 列长表天然容纳明细行，
`build_model_frame` 在 pivot 时本就按 sum 聚合。

## 词表翻译（必须做，不是美化）

`curated/long_table.csv` 的 `l1` 写**引擎词表**，因为 `app/mmm/pivot.py::is_driver_row()`
判定驱动因子的条件是 `l1 ∈ {{Marketing Factor, Commercial Factor}}`。
若直接写中文 `l1`，OLS 找不到任何 X，模型无法拟合。

映射由 2.32 与 2.24 在自然键上 join **推导**得出（零冲突），不是声明的：

{taxonomy_table}

`METRICS类型` 保留**单位族**语义（`箱数`/`RMB`/`Volume`/`百分比`…），
因为 `pivot.is_money_metric()` 靠它决定 ROI 的单位。唯一改名：`花费 → Spending`。

## Y 的口径断层

`l1='KPI'` 的行里，指标名按渠道分裂，且**跨渠道不同质**：

| 渠道 | 销量口径 | 金额口径 |
|---|---|---|
| MT | 谈判点出货箱数 | 谈判点出货金额 |
| TT / AFH / WS | Compass完成箱数 | Compass完成金额 |
| EC | Volume | GMV |
| O2O / 社区团购 | 箱数 | GMV |

销量与金额两类**都保留为 Y 候选**，不重命名、不合并。
`pivot._pick_y_metric()` 默认按"月覆盖优先 + 销量优先"选，2.5y 门禁可人工覆盖。
跨渠道汇总的 Y 不可比 —— 默认 Y 在单个 model object（= `channel_type` 分组）内选取。

## 重新生成

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m scripts.restore_model_input
PYTHONPATH=. .venv/bin/python -m scripts._test_restore
```

`raw/` 与 `curated/long_table.*` 体积大且完全可再生成，已加入 `.gitignore`。
"""


def write(stats: dict) -> None:
    paths.mkdirs()
    tmap = stats["taxonomy"]
    rows = ["| 业务词表 (2.32) | 引擎词表 (2.24) | 证据行数 |", "|---|---|---|"]
    for src, dst in sorted(tmap.l1.items()):
        rows.append(f"| {src} | {dst} | {tmap.evidence.get(f'l1:{src}', 0)} |")
    origin = stats["originCounts"]
    (paths.OUT / "README.md").write_text(_TEMPLATE.format(
        raw_files=stats["rawFiles"],
        curated_rows=stats["curatedRows"],
        tree_rows=stats["treeRows"],
        both=origin.get("both", 0),
        planned=origin.get("planned", 0),
        data=origin.get("data", 0),
        taxonomy_table="\n".join(rows),
    ), encoding="utf-8")
```

- [ ] **Step 3: Write the CLI orchestrator**

Create `backend/scripts/restore_model_input.py`:

```python
"""Rebuild every model-input_2.32 restore artifact. Idempotent.

Run from backend/:
    PYTHONPATH=. .venv/bin/python -m scripts.restore_model_input
"""
from __future__ import annotations

import sys

from scripts.restore import (curated, factor_tree, paths, profile, raw_export,
                             readme, source, taxonomy)


def main() -> int:
    paths.mkdirs()
    print(f"source : {paths.source_workbook()}")
    print(f"output : {paths.OUT}")

    station = source.load_station()
    granularity = source.load_granularity()
    print(f"loaded : {len(station)} ledger rows, "
          f"{granularity['indicator'].nunique()} planned indicators")

    tmap = taxonomy.derive(station)
    print(f"taxonomy: {tmap.l1}")

    tree = factor_tree.build(station, granularity)
    factor_tree.write(tree)
    origin = tree["origin"].value_counts().to_dict()
    print(f"tree   : {len(tree)} rows {origin}")

    raw_files = raw_export.write(station)
    print(f"raw    : {len(raw_files)} workbooks")

    long = curated.build(station, tmap)
    curated.write(long, station, tmap)
    print(f"curated: {len(long)} rows x {len(long.columns)} cols")

    profile.write(long)
    readme.write({
        "treeRows": len(tree), "originCounts": origin,
        "rawFiles": len(raw_files), "curatedRows": len(long),
        "taxonomy": tmap,
    })
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the orchestrator**

```bash
PYTHONPATH=. .venv/bin/python -m scripts.restore_model_input
```
Expected output ends with:
```
loaded : 23813 ledger rows, 66 planned indicators
...
tree   : 85 rows {'both': 37, 'planned': 29, 'data': 19}
raw    : 29 workbooks
curated: 23813 rows x 19 cols
done
```

Then confirm the artifacts:
```bash
ls ../restored/model-input-2.32/factor-tree ../restored/model-input-2.32/curated
ls ../restored/model-input-2.32/raw | wc -l
```
Expected: `factor-tree.json factor-tree.xlsx reconciliation.md`; `indicators.csv long_table.csv long_table.xlsx taxonomy_map.csv`; and `29`.

- [ ] **Step 5: Add the gitignore entries**

Append to the repo-root `.gitignore`:

```gitignore

# Regenerable restore artifacts (docs/superpowers/plans/2026-07-22-restore-model-input-2.32.md)
restored/model-input-2.32/raw/
restored/model-input-2.32/curated/long_table.csv
restored/model-input-2.32/curated/long_table.xlsx
```

Verify only the intended artifacts are staged:
```bash
git status --short restored/
```
Expected: `factor-tree/`, `curated/taxonomy_map.csv`, `curated/indicators.csv`, `qa/profile.md`, `README.md` — and **no** `raw/` or `long_table.*`.

- [ ] **Step 6: Commit**

```bash
git add .gitignore backend/scripts/restore/profile.py backend/scripts/restore/readme.py backend/scripts/restore_model_input.py restored/
git commit -m "feat(restore): profile, README and the rebuild CLI"
```

---

### Task 7: End-to-end verification

**Files:**
- Create: `backend/scripts/_test_restore.py`

**Interfaces:**
- Consumes: the artifacts written by Task 6; `app.ingest.dataset.COLUMN_NAMES`; `app.mmm.build_model_frame`, `app.mmm.run_mmm`; `app.mmm.pivot.MAX_DRIVERS`, `app.mmm.pivot.driver_candidates`.
- Produces: `restored/model-input-2.32/qa/ols_smoke.txt`

- [ ] **Step 1: Write the verification script**

Create `backend/scripts/_test_restore.py`:

```python
"""End-to-end verification of the model-input_2.32 restore.

Run: PYTHONPATH=. .venv/bin/python -m scripts._test_restore

Three load-bearing claims:
  1. schema   — the curated long table IS the canonical 19-column schema.
  2. lossless — raw/ and curated/ each carry every source row, compared as a
                MULTISET. The source holds 1,140 same-key-different-value detail
                groups and 105 fully duplicated rows; comparing as a set would
                hide the loss of ~3,000 rows.
  3. runnable — build_model_frame finds a response and real drivers, and run_mmm
                actually fits.
"""
from __future__ import annotations

import sys

import pandas as pd

from app.ingest.dataset import COLUMN_NAMES
from app.mmm import build_model_frame, run_mmm
from app.mmm.pivot import MAX_DRIVERS, driver_candidates
from scripts.restore import curated, paths, source, taxonomy

_SMOKE: list[str] = []


def _log(line: str) -> None:
    print(line)
    _SMOKE.append(line)


def _multiset(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """Row multiset: count per normalised row, sorted by row key."""
    norm = df[cols].astype("string").fillna("__NA__")
    return norm.groupby(cols, dropna=False).size().sort_index()


def test_schema() -> None:
    long = pd.read_csv(paths.CURATED_DIR / "long_table.csv")
    assert list(long.columns) == COLUMN_NAMES, list(long.columns)


def test_raw_is_lossless() -> None:
    station = source.load_station()
    files = sorted(paths.RAW_DIR.glob("*.xlsx"))
    assert len(files) == 29, f"expected 29 raw workbooks, got {len(files)}"
    frames = []
    for path in files:
        for _sheet, df in pd.read_excel(path, sheet_name=None,
                                        engine="openpyxl").items():
            frames.append(df)
    rejoined = pd.concat(frames, ignore_index=True)
    assert len(rejoined) == len(station), (len(rejoined), len(station))
    left = _multiset(station, source.BUSINESS_COLS)
    right = _multiset(rejoined, source.BUSINESS_COLS)
    assert len(left) == len(right), (
        f"raw/ round-trip has {len(right)} distinct rows vs {len(left)} in source")
    assert left.equals(right), (
        "raw/ round-trip differs from source; first differing keys: "
        f"{left[left != right].head(3).to_dict()}")


def test_curated_is_lossless() -> None:
    """Curated maps back onto the source ledger, row for row."""
    station = source.load_station()
    tmap = taxonomy.derive(station)
    long = curated.build(station, tmap)
    assert len(long) == len(station), (len(long), len(station))
    # Every curated l1 must reverse to a business value the source actually uses.
    engine_values = set(long["l1"].dropna().astype(str))
    assert engine_values <= set(tmap.l1.values()), sorted(engine_values)
    # The factor path + value multiset must survive the translation untouched.
    cols = ["l4", "l5", "metric", "value"]
    renamed = station.rename(columns={
        "数据类型Level4": "l4", "数据类型Level5": "l5",
        "METRICS": "metric", "VALUE": "value"})
    # Compare on the trimmed form, since build() trims the string columns.
    for col in ("l4", "l5", "metric"):
        renamed[col] = renamed[col].astype("string").str.strip().replace({"": pd.NA})
    left = _multiset(renamed, cols)
    right = _multiset(long, cols)
    assert left.equals(right), (
        "curated (l4, l5, metric, value) multiset differs from source; "
        f"{len(left)} vs {len(right)} distinct rows")


def test_ols_runs() -> None:
    long = pd.read_csv(paths.CURATED_DIR / "long_table.csv")
    objects = [str(o) for o in long["channel_type"].dropna().unique()]
    fitted = 0
    for obj in objects:
        try:
            mf = build_model_frame(long, obj)
        except ValueError as exc:
            _log(f"  {obj:10s} skipped: {exc}")
            continue
        assert mf.y_metric, f"{obj}: no response metric identified"
        assert mf.x_cols, f"{obj}: zero drivers — check the l1 taxonomy"
        result = run_mmm(long, obj)
        fitted += 1
        _log(f"  {obj:10s} Y={mf.y_metric} ({mf.y_metric_type}) "
             f"n_obs={result.n_obs} drivers={len(result.drivers)} "
             f"R2={result.r2:.4f} adjR2={result.adj_r2:.4f}")
        # MAX_DRIVERS truncation must be visible, never silent.
        # Diagnostics only — this block reports, it never fails the test.
        candidates = driver_candidates(long, obj)
        if len(candidates) > len(mf.x_cols):
            kept = {str(m.get("metric", "")) for m in mf.meta.values()
                    if isinstance(m, dict)}
            dropped = [str(c.get("metric", "")) for c in candidates
                       if str(c.get("metric", "")) not in kept]
            _log(f"    NOTE {len(candidates)} candidates -> {len(mf.x_cols)} kept "
                 f"(MAX_DRIVERS={MAX_DRIVERS}); dropped {len(dropped)}: "
                 f"{dropped[:12]}")
    assert fitted > 0, "no model object could be fitted from the curated long table"
    _log(f"  fitted {fitted}/{len(objects)} model objects")


TESTS = [test_schema, test_raw_is_lossless, test_curated_is_lossless, test_ols_runs]


def main() -> int:
    failed = 0
    for fn in TESTS:
        _log(f"== {fn.__name__}")
        try:
            fn()
            _log(f"PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            _log(f"FAIL {fn.__name__}: {exc}")
    _log(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    paths.mkdirs()
    (paths.QA_DIR / "ols_smoke.txt").write_text("\n".join(_SMOKE) + "\n",
                                                encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the verification**

```bash
PYTHONPATH=. .venv/bin/python -m scripts._test_restore
```
Expected: `4/4 passed`, exit 0, and at least one `Y=… n_obs=… R2=…` line.

Failure triage — fix the code, never the assertion:
- **"zero drivers"** → the l1 taxonomy did not reach the CSV. Re-run Task 6's orchestrator and inspect `curated/long_table.csv`'s `l1` column.
- **`test_raw_is_lossless` dtype mismatch** (e.g. `月` read back as float) → `_multiset` already casts both sides through `astype("string")`; if a mismatch persists, print `left[left != right].head(20)` and fix `raw_export.write`.
- **`mf.meta` shape differs from `{col: {"metric": …}}`** → print `mf.meta` and adjust the truncation reporting to match the real structure. This block is diagnostics; it must not be the reason the test fails, so keep the `dropped` computation defensive.

- [ ] **Step 3: Confirm the smoke report landed**

```bash
cat ../restored/model-input-2.32/qa/ols_smoke.txt
```
Expected: the same lines the run printed, ending with `4/4 passed`.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/_test_restore.py restored/model-input-2.32/qa/ols_smoke.txt
git commit -m "test(restore): schema, losslessness and OLS smoke verification"
```

---

### Task 8: Document the restore in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (repo root) — the "Real reference data" section.

- [ ] **Step 1: Add the paragraph**

In `CLAUDE.md`, immediately after the `### Real reference data` paragraph, add:

```markdown
**Restored 2.32 artifacts.** `restored/model-input-2.32/` holds a reconstruction of
`reference/02.数据智能体/…-model input_2.32.xlsx` into a FactorTree + per-source raw
files + a publish-ready 19-column long table, rebuilt by
`backend/scripts/restore_model_input.py` and verified by `backend/scripts/_test_restore.py`.
Three facts to know before touching it: the granularity sheet's `指标选择` is the data
table's `数据类型Level5` (so `FactorRow.indicator ← Level5`, and reading that sheet with
`header=1` silently eats its first data row); 2.32 speaks the **business** factor
taxonomy while `pivot.is_driver_row()` keys on the **engine** taxonomy — the curated
table translates via a map derived from a 2.32↔2.24 join, and writing Chinese `l1`
yields zero drivers and no model; and `raw/` stays at detail grain because the source
is a ledger, not an aggregate. Design:
`docs/superpowers/specs/2026-07-22-restore-model-input-2.32-design.md`.
```

- [ ] **Step 2: Verify the documented commands actually work**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m scripts.restore_model_input && PYTHONPATH=. .venv/bin/python -m scripts._test_restore
```
Expected: both exit 0.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: record the model-input_2.32 restore in CLAUDE.md"
```

---

## Verification Summary

After Task 8, all of this passes from `backend/`:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.restore._test_units   # 8/8
PYTHONPATH=. .venv/bin/python -m scripts._test_restore          # 4/4
PYTHONPATH=. .venv/bin/python -m app.mmm._test_real             # unchanged
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py           # unchanged
```

The last two must be run to prove the Global Constraint held: nothing under `app/` changed, so the existing suites behave exactly as before.
