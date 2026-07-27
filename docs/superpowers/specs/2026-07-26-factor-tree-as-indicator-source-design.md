# Factor Tree as the Indicator source of truth (+ lifting S1 grounding caps)

**Date:** 2026-07-26
**Status:** approved design, not yet implemented

Two independent changes, specced together because both were raised in the same
review of Business Understanding:

- **A.** The confirmed Business-Understanding **Factor Tree** becomes the single
  definition of what data the Data module and the Data Engine must collect and
  validate. `Indicator` stops being an entity the data manufactures and becomes a
  projection of the factor tree.
- **B.** The scattered, silent character caps on S1 grounding material collapse
  into one configurable budget, and truncation becomes visible.

---

## A · Factor Tree → Indicator

### The problem

The dependency runs backwards today.

`register_indicators` (`backend/app/dataeng/dbt/service.py:536`) runs at publish
time. It does `df.groupby(["metric", "metric_type", "l1", "l2", "l3", "l4"])` over
the published mart, manufactures one `Indicator` per group, and *then* looks each
one up in the factor tree (`_norm_path` full L1–L4, falling back to L3 alone) to
decide `treeGrounded` / `treeRowId`.

The `l1..l4` values it groups on were hand-typed by the user in the transform
pipeline's `field_map` / `enum_map` steps. Nothing in the Data Engine editor knows
the factor tree exists, so whether an indicator lands on a factor row is decided
by whether someone happened to type the same string. Everything that misses falls
through to 2.1, where a human binds it by hand
(`IndicatorCatalogPanel.tsx` · `dataeng/mapping_suggest.py`).

Two symptoms confirm this was never the intent:

- `IndicatorSource` (`domain/models.py:1119`) is
  `project_material | interview | uploaded_tree | template | ai | data_upload` —
  the first five are exactly `FactorRow.source`'s value space. Only
  `data_upload` is ever written (`service.py:584`). The factor-tree-sourced
  indicator was designed and never wired.
- Before any data is published, the Data Engine's Indicators view is empty. The
  project has a fully confirmed list of what data it needs, and the module whose
  job is to collect that data cannot see it.

### The design

**The confirmed factor tree *is* the indicator catalog.** Data does not create
indicators; it claims them.

#### 1. Identity comes from the factor row

A factor-tree row in an active status (`baseline` / `accepted` — the existing
`mapping._ACTIVE_STATUSES`) projects to exactly one `Indicator`:

```
Indicator.id        = f"ind-{factorRow.id}"
Indicator.l1..l4    read from the factor row (not copied)
Indicator.metric    = factorRow.indicator
Indicator.source    = SOURCE_MAP[factorRow.source]
Indicator.treeRowId = factorRow.id
```

The two enums do **not** currently share a value space —
`FactorSource` (`models.py:403`) is
`template | ai | interview | manual | upload`, while `IndicatorSource`
(`models.py:1119`) is
`project_material | interview | uploaded_tree | template | ai | data_upload`.
They are reconciled by one explicit map rather than by widening both:

| `FactorSource` | → `IndicatorSource` |
|---|---|
| `template` | `template` |
| `ai` | `ai` |
| `interview` | `interview` |
| `upload` | `uploaded_tree` |
| `manual` | `manual` — **added** to `IndicatorSource` |
| `data_upload` — **added** to `FactorSource` (§4) | `data_upload` |

`project_material` stays unused for now; it is the slot for a future
material-derived indicator that has no factor row.

Orphans (see §4) keep the existing content-hash id
(`service.py::_indicator_id`), so the two id spaces cannot collide.

#### 2. `st.indicators` becomes derived, not stored

This follows the rule the indicator lifecycle ledger already establishes
(`app/agents/ledger.py`): a derived view cannot disagree with the layers it reads
from, and a stored copy eventually does.

What is persisted shrinks to the decisions a human actually made:

| Persisted | Meaning |
|---|---|
| `factor_map_ignores` (exists) | rowId → note; "this factor has no data source" |
| **`indicator_coverage`** (new) | how a published metric covers a factor row (see below) |

Everything else — `l1..l4`, metric name, `source`, `dimension` — is read from
`st.factor_tree` at derive time. A factor-tree change (1.4 interview writeback
adding rows, a gate accepting/rejecting, a manual `PUT /factor-tree`) is reflected
in the indicator catalog immediately, with no second list to keep in sync.

`ProjectState.indicators` is removed as a stored field. `GET
/api/projects/{id}/indicators` returns the derived list, so the frontend contract
(`lib/types.ts::Indicator`) does not change.

#### 3. Publish claims rather than creates

`register_indicators` becomes `claim_published_metrics(st, asset, df)`. For each
`(metric × l1..l4)` group in the mart it resolves an owning factor row using the
existing precedence, unchanged:

1. an explicit human pin (`bound_by == "human"`)
2. full normalised L1–L4 path
3. L3 + indicator-name

On a hit it writes a **coverage record**, not an indicator:

```python
class IndicatorCoverage(CamelModel):
    tree_row_id: str        # "" for an orphan
    asset_id: str
    asset_name: str
    metric: str             # the mart's metric label (may differ from the factor's)
    metric_type: str        # OLS role carried from the mart
    semantic_type / unit / currency / aggregation / number_format  # classify_indicator
    coverage_start: str
    coverage_end: str
    rows: int
    bound_by: Literal["", "auto", "human"]
```

A human pin is a decision, not derived state — it survives re-publish exactly as
`service.py:544` already carries `bound_by == "human"` bindings across today.

#### 4. Orphans are listed separately, and can propose back

A mart metric that no factor row claims is **not** an indicator. Today these sit
in the catalog with `treeGrounded=false`, which is how a data-side metric ends up
looking like a project deliverable.

They get their own section — "in the data, not in the factor tree" — with two
exits:

- **Add to the factor tree** — appends a `FactorRow(status="proposed",
  source="data_upload")` reusing the existing accept/reject machinery
  (`business.accept_factor_rows`). This requires adding `data_upload` to
  `FactorSource`, and a gate that accepts this source set — the orphan review
  lives in the Data Engine, so it accepts on the spot rather than waiting for an
  S1 gate that has already closed.
- **Ignore** — recorded and never re-offered.

#### 5. One derivation, two renderings

`resolve_factor_map` (`dataeng/mapping.py:103`) and the derived indicator list
become two readings of the same derivation:

- **Data Engine › Indicators** — "here is the data target list; who has supplied
  what". Populated the moment the factor tree is confirmed, before any upload.
- **2.1 Data Processing factor map** — "can the gate clear": every active row
  mapped or ignored (`mapping_complete`).

`_index_indicators` and `_cover_indicator` are rewritten against coverage records.
`mapping_suggest` / `mapping_auto` keep scoring the *unclaimed* published metrics
against pending rows; only their input changes.

#### 6. Multi-source coverage

A factor row may be covered by several `(asset, metric)` pairs — TV spend split
across two data sources is routine. This relaxes one half of the current
constraint in `mapping_suggest.bind()`:

- **relaxed:** one row → many coverage records. `FactorMapRow.status == "mapped"`
  when ≥1 exists.
- **kept:** one published metric → at most one row. A single physical series
  cannot stand in for two different factors, and `auto_resolve_factor_map`'s
  greedy assignment depends on it.
- **kept:** at most one *human pin* per row. When a pin exists it is the row's
  primary coverage for display; auto coverages list underneath it.

`FactorMapRow` gains a `coverages: list[...]` alongside the existing flat
`assetId` / `assetName` / `metric` / `coverage*` fields, which keep reporting the
primary coverage so `IndicatorCatalogPanel` and the 2.1 artifact render unchanged.

### Migration

`heal_state()` (`store/state.py:245`) back-fills on load:

- For every stored `Indicator` with `bound_by == "human"` and a non-empty
  `tree_row_id`, write the equivalent `IndicatorCoverage` with
  `bound_by="human"`. **Losing these silently would drop the Danone case's
  existing manual mappings**, which is the one irreversible failure here.
- Stored indicators with `bound_by == "auto"` are dropped — they are re-derived
  from the marts on next publish, or re-resolved by `mapping_auto`.
- The `indicators` key is removed from the persisted JSON after back-fill.

`seed_reference_assets` (`dataeng/seed_reference_assets.py:65`) currently resets
via `st.indicators = []` and counts `treeGrounded` off the same list; it moves to
clearing/counting coverage records.

### Empty state

Before the factor tree is confirmed, the Data Engine's Indicators view is
legitimately empty — the data target is not defined yet. It must say so and point
back to Business Understanding, not read as a failure. (`IndicatorCatalogPanel`
already has this copy for the factor-map half; it needs to cover the whole view.)

### Testing

- Extend `app/dataeng/_test_flow.py`: publishing a mart whose `l1..l4` match a
  factor row produces a coverage record and no new indicator; a mart metric with
  no matching row produces an orphan and no indicator.
- New: a factor tree with N active rows derives N indicators with zero data
  assets present.
- New: `heal_state` on a fixture holding a human-bound stored indicator yields the
  equivalent coverage record.
- Existing `_test_ledger_*` / `_test_master_data.py` must pass unchanged — the
  ledger keys on `(norm_l4, norm_metric)`, not on `indicator.id`, so this change
  should be invisible to it. If a ledger test moves, the derivation is wrong.

---

## B · One grounding budget, visible truncation

### The problem

S1 grounding material is truncated at a dozen independently-chosen constants, all
silently:

| Site | Cap |
|---|---|
| `store/files.py:163` `extract_category_text` | 9 000 |
| `store/files.py:185` `extract_category_files` per file | 12 000 |
| `agents/common.py:17` `MAX_CTX_CHARS` (artifact text, knowledge pack) | 6 000 |
| `agents/business.py:98` SOW / brief | 8 000 |
| `agents/business.py:189,202,557` industry materials | 6 000 |
| `agents/business.py:535` existing factor paths | 3 000 |
| `agents/business.py:450` `_paths_block` | 4 000 |
| `agents/business.py:772` pre-answer context | 5 000 |
| `agents/business.py:806` pre-answer materials | 4 000 |
| `agents/business.py:1229,1280` summary material | 5 000 / 8 000 |
| `agents/business.py:774`, `common.py:216`, `business.py:1230,1281` `max_tokens` | 2 048 / 3 000 |

Nobody — not the model, not the user — is told when material is dropped. A factor
tree derived from the first 6 000 characters of a 200-page deck looks identical to
one derived from all of it.

### The design

- A single `grounding_max_chars` operational knob on `Settings`
  (`app/config.py:12`, so it is `.env`-overridable like `llm_timeout`), defaulting
  to 100 000. `agents/common.py` reads it; per-call overrides stay possible where a
  call genuinely needs a smaller slice.
- One helper — `clip(text, budget, *, label)` — replaces every bare `[:N]` on
  grounding material. It returns the text plus how much was dropped.
- Any handler that clips emits a `TaskFinding` naming the source and the
  proportion dropped, so a truncated run is visible in the artifact's build
  process rather than inferred from a thin result.
- `max_tokens` rises to the client default (`llm/volcano.py:226` already uses
  16 000 for `json`); the 2 048 / 3 000 overrides are removed unless a call has a
  reason to cap.

Caps that are **not** grounding material stay as they are: `evidence[:200]`,
`title[:120]`, `_MAX_INSIGHTS`, and the like are display/schema limits, not
context budgets.

### Testing

- `clip` returns input unchanged under budget, and reports the dropped fraction
  over it.
- A handler run with material over budget emits the truncation finding.

---

## Out of scope

- The Data Engine transform editor does not gain a factor-row picker. The claim
  path (§3) plus 2.1's existing AI suggestions cover the binding; a dedicated
  `factor_map` step kind is a separate proposal.
- S2–S5 handlers are untouched. `model_selection` / `model_df` read the ledger and
  the long table, neither of which changes shape.
