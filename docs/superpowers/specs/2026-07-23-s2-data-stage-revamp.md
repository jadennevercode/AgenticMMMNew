# S2 Data Intake & Validation — Revamp Spec (v2: global total model)

**Date:** 2026-07-23
**Status:** Pending user confirmation
**Decision (user, 2026-07-23):** S2 drops the channel concept entirely — all
Processing / Scoring / Business Validation view data globally, and OLS screens
factors through a **single national total model**. S4 trains that one total model.
Channel-specific drivers enter as independent national series; per-indicator
aggregation is user-maintained in 2.1. The contribution deliverable is
**FactorTree L4-level contribution** (per-driver decomposition), not per-channel
decomposition.

All file:line references verified against the live code on 2026-07-23.

---

## Issue 1 — De-channelize S2 + single total model

### Requirement
No channel filtering anywhere in S2. One global flow: 2.1 mapping → 2.2 quality →
2.3 validation → 2.4 stat → 2.5 OLS (one total model) → 2.6 master data. S4 fits
the single national model. Channel remains a *data lineage column* (visible in raw
views / Data Station), never a model or UI dimension.

### Current state (verified)
- Screening loops `model_objects(st)` (distinct `channel_type`) and stamps `object`
  on every row; ledger resolves drops per object (`ledger.py` `*_by_object`,
  `OBJECT_ANY="*"`); OLS/S4 fit one model per object (`model.py:33-43`).
- Frontend has `s2ChannelFilter` + `ChannelTypeSelect` on Quality/Stat/OlsTree
  canvases, an `object` view dimension, and "apply to all channels" affordances.
- This multiplies noise: e.g. 201 mapping-ignores × 7 objects = 1421 "Dropped"
  rows in the 2.5r tree (see Issue 5).

### Design — keep the per-object machinery, collapse the object set to one
1. **National aggregation layer** (new, the core): `dataset_cache.national_df(st)`
   derives from `model_df(st)` a national long table — group by
   `(month, l1..l8, l4, metric)` and aggregate `value` across
   `channel_type/channel/province_group` using the indicator's **maintained
   aggregation** (Issue 3b): `sum` for spend/volume/count; `weighted_average`
   (weighted by the channel/period Y volume, fallback simple mean) for
   rate/price/index. Output keeps `LONG_COLUMNS` shape with
   `channel_type = "TOTAL"`, so every existing consumer works unchanged.
2. **Single object**: `model_objects(st)` returns `["TOTAL"]` (national frame
   present) — quality/stat/OLS/ledger/master-data loops all run once with zero
   changes to loop bodies. `OBJECT_ANY` machinery stays for compat.
3. **S4**: `train_models` naturally fits the one total model. Channel-specific
   drivers are distinct `(l4, metric)` columns of the national frame, so their
   ROI/contribution stay individually attributable (the L4-level contribution
   deliverable).
4. **Frontend removal**: delete `ChannelTypeSelect` usage + `s2ChannelFilter`
   store slice + `object` columns + "apply to all channels" checkbox from
   Quality/Stat/OlsTree canvases; `MasterDataView` drops channel dims as model
   dimensions (channel columns remain as data-lineage in the Data Station tab,
   Issue 6). `signoffKey` stays global (already is).
5. **Migration**: `heal_state` keeps legacy per-object rows (they simply stop
   being rendered); re-running S2 regenerates TOTAL rows. Saved verdicts keyed
   `OBJECT_ANY` keep their effect; per-object verdicts are unioned into TOTAL on
   heal (a drop anywhere = drop, conservative).

Non-goals: S5 report copy mentioning channels is untouched for now; raw
data-engine views keep channel columns (they are data, not model structure).

---

## Issue 2 — Canvas FactorTree: show full L1–L4 on every row

L1/L2/L3 cells are blanked when equal to the previous row, in four files:
`factor-tree/FactorTreeCanvas.tsx:153-167` (shared by DataProcessing/Stat/Quality),
`canvas/MasterDataView.tsx:349-351`, `canvas/OlsTreeView.tsx:143-145`,
`dataeng/IndicatorCatalogPanel.tsx:184-186`. L4 + Indicator already always render.

**Design:** render L1/L2/L3 unconditionally in all four; keep the `firstL1/f1`
flags (they drive group border styling).

---

## Issue 3 — Data Processing gains two maintained columns

### 3a. Metrics Type (Y / X / excluded)
- Today the model role is guessed from the metric name
  (`indicator_metadata.classify_indicator` → `model_role`, stamped at
  `data_binding.py:149`), with **two disagreeing Y classifiers**
  (`pivot._is_y_row` for 2.5 vs `validation_query._kpi_mask` for 2.3/2.6) and
  three independent "pick the Y" sites.
- **Design:** `ProjectState.metric_type_overrides: dict[indicator_key,
  "Y"|"X"|"excluded"]` keyed by `indicator_metadata.indicator_key(l4, metric)`.
  Injected at the long-table write seam (`data_binding._melt_sheet`) and the
  reference path in `dataset_cache.resolve_dataset`, so every reader is
  automatically consistent. `excluded` rows never reach the model frame.
  Unify `_kpi_mask` onto `_is_y_row` semantics; 2.3/2.6 read the resolved Y from
  `ledger.model_selection(st).y`. Choosing a new Y demotes the old one to X
  (confirmed in UI). No tag → today's name-based auto-pick (reference/legacy
  projects keep working).

### 3b. Aggregation (new, user decision 2026-07-23)
- Per-indicator aggregation method maintained in 2.1, referenced by the national
  aggregation layer (Issue 1), the 2.3 chart series (Issue 4), and master data.
- **Design:** `ProjectState.aggregation_overrides: dict[indicator_key, agg]`,
  `agg ∈ {sum, average, weighted_average, min, max}` (the existing
  `_AGG_PANDAS` vocabulary). Default from `classify_indicator` semantics
  (spend/volume/count → sum; rate/price/index → weighted_average).
- **Surface for both:** `FactorMapRow` gains `metricType` + `aggregation`
  (defaults included); `PUT /factor-map/metric-type` and
  `PUT /factor-map/aggregation` endpoints mirroring `/ignore`; two select
  columns in `DataProcessingCanvas.tsx`. Mirror `models.py`/`types.ts`.

---

## Issue 4 — Business Validation charts

### Requirement (updated)
Default composition per factor chart: **Y always as Area**; spending → **Bar**;
other → **Line** (current spend→bar/other→line assignment is correct — the missing
piece is the Y area). Plus: dual Y axes (per-metric assignment), time-span
selection, chart resize, add metrics one-by-one each with its own aggregation.

### Current state (verified)
The 2026-07-22 Graphic Walker plan **was implemented** (`ExploreTab.tsx`,
`specToChart.ts`, endpoints live). But GW 0.4.84 has **one geom per chart**
(`specToChart.ts:102`) — "Y area + bar/line overlays" is not expressible. Dual
axes are explicitly disabled (`layout.resolve.y:false`), every metric is
hard-coded SUM despite `validation_query._metric_meta` computing real per-metric
aggregation, and GW's toolbar is hidden (`showActions:false`).

### Design
Bespoke **FactorChart** on recharts `ComposedChart` (natively mixes
Area+Bar+Line + dual axes) as the default per-factor chart:
- Series roles from `metricType`: Y → `<Area>`; spend → `<Bar>`; other → `<Line>`.
- Dual Y axes with per-metric left/right assignment (default: Y-area left,
  overlays right; per-metric flip control).
- Time span via `<Brush>` on the period axis.
- Resize: height presets (S/M/L) or drag handle.
- "Add metric" picker (grouped by factor tree); each series aggregated
  server-side by its maintained aggregation (Issue 3b) via a new
  `POST /validation-series` endpoint (reuses `_pandas_agg`), returning per-metric
  period series on the national frame.
- GW fate: **recommend keeping** the GW Explore tab as a secondary free-form
  surface (already built; patch its per-metric `aggName` + `showActions:true`),
  removable later if unused. Insights/Sign-off tabs unchanged.

---

## Issue 5 — "OLS dropped everything"

### Root cause (verified against `mizone-mmm-e2e-v2-2-32-restore.json`)
1. **1421/1471 drops are inherited 2.1 mapping-ignores** (201 factor rows without
   published indicators × 7 objects), honestly inherited by the ledger but
   rendered as "Dropped" in the 2.5r tree — reads as an OLS verdict. (The ×7
   multiplication disappears with Issue 1.)
2. **Mis-specified fit on short series**: ~34 monthly obs with
   `trend + Fourier(K=2)` (5 controls) → baseline 149%, wrong-sign paid
   coefficients, contributions 122% / −242% → all 16 benchmarked in-model rows
   flagged out-of-range (`inRange 0`). One "Drop flagged" at d-2.5 would wipe the
   survivors.

### Design
1. **2.5r tree presentation**: rows rejected before the OLS layer render as
   `Not mapped` / `Excluded earlier` (distinct tone, `droppedBy` label), hidden
   by default behind a toggle; OLS-layer verdicts stand alone.
2. **Small-sample control downconfig** in the 2.5 proposal defaults: usable obs
   < 36 → propose `fourierK=1`; < 24 → seasonality off; drop trend if it pushes
   baseline share > 100%. Post-fit guard: `baselinePct > 100` or wrong-sign paid
   driver → emit a finding recommending control reduction. User-overridable in
   2.5p as today.

---

## Issue 6 — Master Data in the 2.32 reference shape

### Reference (verified from the workbook)
`reference/02.数据智能体/【MMM AI】数据智能体-model input_2.32.xlsx` has exactly two
sheets: **模型颗粒度参考表** (factor tree L1–L4 + 指标 × 渠道 scope × 区域
granularity; blank = not selected into the model) and **D.Data Station** (the
long model-input table: Task name/品牌/省份组别/渠道类型/渠道/年/月/数据源/L1–L8/
METRICS类型(unit)/METRICS/VALUE/Variable).

### Current state
Period × indicator wide pivot sliced per product×channel×region + a channel-type
verdict matrix. S4 does **not** read the artifact body (re-derives from
`model_df` + `model_selection`), so reshaping is low-risk; only the
`artifact_text` prompt for 3.1 priors must stay coherent.

### Design
Rebuild `a-master-data` as the two-sheet shape:
1. **Granularity Reference tab** — full factor tree (full L1–L4 per Issue 2);
   per indicator: **渠道** = the indicator's actual data channel coverage
   (`全渠道` when national/blank-channel data; else the channel_type list — a
   data fact, not a model dimension), blank when the indicator was not adopted;
   **区域** = province-group coverage (`National` vs group list). Adoption =
   ledger survival in the total model.
2. **Data Station tab** — the adopted-indicator long table rendered with the
   standard grid, columns mirroring D.Data Station (channel columns as lineage).
3. **Export** — one xlsx, two sheets, matching the 2.32 layout.
4. `master_table` wide pivot remains internal-only; funnel/verdict-chain detail
   collapses into a secondary panel.

---

## Sequencing & complexity

| Phase | Content | Complexity | Depends on |
|---|---|---|---|
| P0 | Issue 2 (canvas full display) + Issue 5 (OLS presentation + downconfig) | Low | — |
| P1 | Issue 3 (Metrics Type + Aggregation columns, overrides, unified Y) | Medium | — |
| P2 | Issue 1 (national aggregation layer, TOTAL object, de-channelized UI, S4 single model) | Medium-High | P1 (aggregation feeds `national_df`) |
| P3 | Issue 4 (FactorChart + `/validation-series`) | Medium | P1, P2 |
| P4 | Issue 6 (master data 2.32 shape + export) | Medium | P2 |

## Risks
- Weighted-average aggregation needs a weight series (per-channel Y volume);
  periods where the Y is missing fall back to simple mean — document in the UI.
- Single-Y override must not break the Danone reference fallback (override by
  indicator key; fallback keeps name-based classification).
- `national_df` cache invalidation must follow `invalidate_project` + override
  edits (metric type / aggregation changes recompute the frame).
- Legacy saved projects: per-object rows/verdicts heal into TOTAL by union
  (drop anywhere = drop); verify the Danone seed and recent project JSONs load.
- 3.1 priors read `artifact_text(a-master-data)` — keep a coherent text form.
- Contract sync: `models.py`/`types.ts`; blueprint unchanged (task ids stay).
