# S2 Revamp — Execution Tracker

Spec: `../specs/2026-07-23-s2-data-stage-revamp.md`. Decision: global total model.

## P0 — mechanical + OLS (low risk) ✅
- [x] T1 Canvas full L1–L4 display (4 files)
- [x] T2 2.5r tree: notMapped status split + default-hide
- [x] T3 Small-sample control downconfig + post-fit guard finding

## P1 — Data Processing two maintained columns ✅
- [x] T4 metric_type_overrides + aggregation_overrides on ProjectState; inject at model_df seam; align Y tag-sets
- [x] T5 2.1 canvas Metrics Type + Aggregation selects + 2 PUT endpoints; types mirror

## P2 — de-channelize + single total model ✅
- [x] T6 national.py build_national + raw_long_df/model_df split; model_objects → ["TOTAL"]; diagnose on raw
- [x] T7 remove ChannelTypeSelect from Quality/Stat/Ols canvases (store slice left dead)

## P3 — Business Validation charts ✅
- [x] T8 bespoke FactorChart (Y Area/spend Bar/other Line + dual axis + brush + resize + add-metric) + POST /validation-series
- [x] T9 GW kept as secondary "Free explore" tab; Charts is default

## P4 — Master data 2.32 shape ✅
- [x] T10 a-master-data two-tab (Granularity Reference 模型颗粒度参考表 + D.Data Station)
- [x] T11 two-sheet xlsx export (granularity ref + data station)

## Final ✅
- [x] E2E: danone-mizone ran to 38/38 complete. Verified: quality(94)/stat(30) scorecards
  all on TOTAL object; OLS single Y (本品月度销量), fourierK=1, baseline 94% (was 149%),
  notMapped(35) split from dropped; master data 2.32 two-sheet export (模型颗粒度参考表 171×7
  + D.Data Station 2881×19); BV 17 factor specs + series (KPI→area, spend→bar). Fixed a
  ledger-key mismatch (tuple vs indicator_key string) in granularity_reference/data_station.
