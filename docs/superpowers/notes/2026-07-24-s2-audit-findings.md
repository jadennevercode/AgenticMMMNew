# S2 / S1 coherence audit — running findings (Phase D)

Recorded while doing v3 Phase A. These are the "unreasonable points" the user asked
me to log. Severity: 🔴 blocks real coherence · 🟠 real gap · 🟡 smell.

## F1 🔴 Factor tree (S1) and modeling data (S2) use different taxonomies
- danone factor tree (reference 2.31, and the S1 industry template) is **Chinese**
  (`生意基本盘 › 外部因素 › 品类趋势 › 市场规模`, 94 indicator rows).
- danone modeling dataset (reference 2.32) labels the SAME factors in **English**
  (`Baseline Factor › Industry Trend`). L3 overlap = 1/17, L4 = 7/45.
- Consequence: path-grounding and fuzzy name matching bridge only ~18 of 170 factor
  rows. The analyst's real EN↔CN correspondence exists only in their head / an
  unshipped lookup — the product cannot reconstruct it deterministically.
- The v2 E2E hid this by fabricating indicators FROM the tree's own labels, so
  everything "mapped". That was the dead data the user called out.
- **Real 2.1 outcome on real data: ~18 factors map, ~150 have no data match.** That
  is honest but thin. Options to make it richer *for real*: (a) an LLM cross-language
  factor↔indicator matcher in `mapping_suggest` (real, grounded proposal — the AI
  mapping the Data Engine is supposed to do); (b) reconcile S1 so its factor tree and
  the client's modeling taxonomy are one. Needs a product decision.

## F2 🟠 Autopilot has no step that resolves the 2.1 factor↔indicator mapping
- The runner auto-submits the 2.1 assignment but never binds/ignores factor rows, so
  a real project's 2.1 gate can only clear if a human maps. Autopilot could only pass
  because the seed pre-bound everything (fabricated).
- Fix (Phase A): a real auto-mapper binds genuine matches (score ≥ threshold) and
  ignores the rest with a specific "no data source" reason. No forced weak binds.

## F3 🟠 `Indicator.metric_type` conflates OLS role with unit
- `register_indicators` fills `Indicator.metric_type` (documented as the OLS role
  `Y|spending|X`) from the dataset's `metric_type` COLUMN, whose values are **units**
  (`RMB`, `Traffic`, `箱数`, `Impression`). So the field is neither a clean role nor a
  clean unit. The model layer luckily ignores it (Y/driver come from `l1` taxonomy in
  `pivot`), but the 2.1 Metrics-Type override + any UI reading `metricType` are built
  on a muddled field.
- Fix later: separate `modelRole` (Y/X/spending/excluded) from `unit`; default role
  from `l1` taxonomy + the 2.1 override, not from the unit column.

## F4 🟡 Data Engine "data factory" for danone is bypassed
- danone's data comes from a single pre-cleaned reference table, not from raw files
  run through the dbt cleaning DAG. Phase A registers per-source assets + real
  published parquet + real indicators, but the *cleaning* step (raw→long via dbt) is
  not exercised for the seed. Whether the Data Engine can genuinely take danone's raw
  source files → the 23.8k long table is D2 (unverified). The reference table is real
  client data, so numbers are real; the transform authorship is not demonstrated.

## F5 🟠 `master_table` returns an empty slice on the mock unit test
- `app/agents/_test_master_data.py::test_master_table_acceptance` fails: `master_table`
  with `channel_type=["MT"]` returns `{columns: [], rows: [], kpi: ""}` — the slice is
  empty though the mock has MT rows. Pre-dates v3 Phase C (the test mocks
  `model_selection`, which C changed nothing about); introduced by the v2
  national-model / master-data 2.32 reshape. The real-data 2.6 must be checked in the
  E2E; if it also mis-slices, the master table is wrong for real. Fix belongs to v2
  cleanup, not the OLS search.

## F6 🟡 A parked stash from another session overlaps these files
- `git stash@{0}` = "PARKED: other session's in-flight 'restore model input 2.32' work
  (data.py caps=, ols_review.py ledger-discipline refactor, …)". Another session was
  refactoring `ols_review.py` + `master_data.py` — the same files Phase C edits. Merge
  conflict / duplicated-intent risk. Reconcile before landing either.

## F7 🟠 Master-data granularity reference (2.32 sheet 1) shows `adopted: 0`
- The E2E's 2.6 `granularityRef` iterates the **factor tree** (195 Chinese rows) and
  marks a row adopted by joining to the ledger's adopted indicators — but those are
  keyed on the **English data** `(l4, metric)` (F1), so the join finds nothing →
  `adopted: 0`, even though the ledger genuinely adopted 7 indicators and the fit has
  6 drivers. Sheet 2 (D.Data Station, the real model input) is correct: 1,696 rows ×
  19 cols. So the deliverable's *summary sheet* reads "empty model" while the *actual
  input* is real — a visible incoherence. Fix: build the granularity reference from
  the adopted indicators (which carry their own l4/metric + channel/region from data),
  not from the factor tree; or resolve the F1 tree↔data join. Overlaps the parked
  stash (F6) — reconcile first.

## E2E verification (2026-07-24, real seed, autopilot 34/34 complete)
- **A** ✅ 92 real indicators (0 fabricated, all real assetId); 2.1 auto-resolved
  honestly (10 bound + 185 ignored-for-no-data); model universe rich.
- **B** ✅ validation/series returns Y=Compass完成箱数 kind=area, Impression=bar,
  Spending=line, 34-period axis, 3-row yearly YoY table — roles + YoY correct.
- **C** ✅ OLS search ran, populated ols_config (Y + 6 drivers), fit R²=0.924,
  **baseline 46.7%** (well-specified; old bug was 149%). On danone the search does 1
  fit because the English factors have no Chinese-keyed benchmarks to optimise toward
  (F1) — mechanism verified separately at 4 fits when targets exist.
- **2.6** ⚠️ real model input correct (7 adopted, data station 1696×19); granularity
  reference sheet adopted-flag broken (F7).

(Extend during Phase D with deeper BU/S1 flow review.)
