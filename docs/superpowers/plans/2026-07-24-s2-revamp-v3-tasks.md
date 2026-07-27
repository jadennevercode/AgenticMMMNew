# S2 Revamp v3 — Execution Tracker

Spec: `../specs/2026-07-24-s2-revamp-v3.md`. Execute A→B→C→E2E.

## Phase A — Real Data Engine registration ✅
- [x] A1 Removed fabricated `ind-ft-tpl-*`; reset now re-seeds real data
- [x] A2 `seed_reference_assets.py`: reference table → 29 per-source published assets → real `register_indicators` (92 real indicators, real assetId/coverage). Wired into `reset()` for reference-backed projects.
- [x] A3 `mapping_auto.py` auto-resolves 2.1 in autopilot: 11 genuine binds, rest ignored-for-no-data (real reasons). Model universe stays rich (46 real driver candidates). Wired into runner autopilot.
  - Findings recorded in `docs/superpowers/notes/2026-07-24-s2-audit-findings.md` (F1 taxonomy gap, F2 no autopilot mapper [fixed], F3 metric_type=unit, F4 dbt cleaning bypassed).

## Phase B — Business Validation ✅
- [x] B1 Restored FactorCard + ValidationChart (subagent); roles Y=Area / spend=Line / other=Bar (backend `kind` flip); custom YoY range (comparison span inputs, comparisonType='custom'); no S/M/L
- [x] B3 Removed v2 FactorChart/ChartsTab + /validation-series (BvChartSeries) route + build_validation_series + _series_role + getBvChartSeries client + BvChart* types
- [x] B4 Backend validation_series → raw_long_df (per-channel lineage for Brand/Channel/Region filters)
- [~] B2 Explore GW config polish (Y=area geom / per-metric agg / showActions) — DEFERRED; the rich Charts tab is the primary surface. Revisit if needed.

## Phase C — OLS L4 search ✅ (minimal-blueprint-risk design)
- [x] C1 Blueprint: collapsed 2.5/2.5y/2.5x/2.5p/2.5r → single **2.5 (M) search** carrying d-2.5; 2.6 depends_on 2.5; scenario.ts synced; heal_state prunes dead tasks+decisions; smoke test updated (`test_ols_search_single_task`); model.ols tool `usedBy` → 2.5
- [x] C2 `build_ols_search`: per-L4 coordinate-descent over candidate indicators, in-range objective (tie-break R²), fit budget (24), search trace. Populates `ols_config` so `model_selection` (unchanged) reads it. Tested: 4 fits, R²=0.926.
- [x] C3 Handler `ols_search_and_fit` (replaces propose_ols_setup + ols_regression_test); registry wired; per-L4 switch = existing OLS panel re-fit + d-2.5 gate (no new task). Advanced Y/params override retained via panel.

## Final ✅
- [x] E2E danone-mizone autopilot **34/34 complete** on real seed (task count 38→34
  confirms OLS collapse). Verified: A (92 real indicators, honest 10-bound/185-ignored
  mapping), B (validation/series roles Y=area/spend=line/other=bar + YoY table), C (OLS
  search → R²=0.924, baseline 46.7%, 6 real drivers). Real model input: 7 adopted, data
  station 1696×19. Open: F7 (granularity-ref adopted-flag join, F1-induced).
- Static gates green: backend smoke + tools/ledger tests, frontend tsc + prod build.

## Phase D — Audit (user request 2026-07-24, AFTER A/B/C)
- [ ] D1 Audit Business Understanding + Data Intake&Validation flow: process reasonableness + coherence vs real MMM business logic; record every unreasonable point
- [ ] D2 Investigate whether Data Engine can genuinely shoulder the data-factory + mapping role (not just claim to)
- [ ] D3 Hard constraint applied throughout: NO run may contain any fabricated/seed "dead" data — every number must trace to real data through the real path

**Constraint (all phases):** no fabricated seed data. danone's real data = the
real 23.8k reference client table; indicators must come from real asset
registration, never a hand-written `st.indicators` splat.
