# S2 Data Intake & Validation — FactorTree-centred redesign

Date: 2026-07-22
Status: approved design, ready for implementation planning

## Premise

Every S2 module is doing one thing to one object: **integrating and filtering the
FactorTree**. 2.1 decides which factors have data, 2.2 decides whether that data is
usable, 2.3 decides whether it is believable to the business, 2.4 decides whether it is
statistically worth modelling. Today each module renders a different, unrelated surface
(a flat sheet, a scorecard editor, a chart page, another scorecard editor), so the user
never sees the tree being whittled down.

The redesign makes the FactorTree the shared canvas of all four modules, with a
per-module overlay, and fixes four specific gaps:

1. **2.1** has no artifact surface at all (mapping lives only in the Data Engine) and its
   gate is a silent readiness check rather than a decision.
2. **2.2 / 2.4** run registered tools but the Process pane only shows them after the fact,
   as static chips — no sense of the analysis being performed.
3. **2.3** signs off at L3 granularity, so rejecting one chart kills every indicator under
   that L3, and the sign-off is stored in the artifact body rather than as project state.
4. **2.4** scoring has drifted from the reference workbook
   (`reference/02.数据智能体/【MMM AI】数据智能体-Data statistical test_2.33.xlsx`):
   four bands instead of three, an inverted VIF direction, and an additive total.

## 1. Shared FactorTreeCanvas

New prop-driven component tree under
`frontend/src/components/project/factor-tree/`:

- `FactorTreeCanvas.tsx` — read-only collapsible L1›L2›L3›L4 hierarchy, indicator rows at
  the leaves. Props: `rows`, `overlay` (per-module cell renderer + legend), `selectedId`,
  `onSelect`, optional `actions` (per-row action slot).
- `useFactorTreeRows.ts` — selector that joins `factorTree` with the indicator ledger and
  the active module's slice (`factorMap` / `qualityScorecard` / `bvSignoff` /
  `statScorecard`) into a single row list. Client-side join; **no new aggregate endpoint**.

This is deliberately **not** an extension of `components/project/FactorTreeEditor.tsx`,
which is a zero-prop, store-bound singleton for the S1 editing flow. The prop-driven
knowledge-template editor (`components/knowledge/editors/FactorTreeEditor.tsx`) is the
shape to follow.

Per-module overlay content:

| Module | Row right-hand cells |
|---|---|
| 2.1 Data Processing | mapping status — mapped (bound indicator name) / ignored / pending |
| 2.2 Data Quality | four-dimension total + verdict + disposition |
| 2.3 Business Validation | sign-off status — accepted / denied / pending |
| 2.4 Statistical Score | CV · Pearson · VIF band scores + multiplicative total + disposition |

**Inheritance is visible.** A row already rejected by an earlier ledger layer renders
greyed with a `Denied @ <layer>` badge and no interactive controls, matching the ledger's
rule that a rejection at any layer is inherited by every later one. The canvas reads this
from `GET /indicator-ledger`; it never re-derives it.

Selecting a tree row scrolls/filters the module's detail surface to that indicator
(mapping row, subcheck breakdown, chart, statistical row).

**Mounting.** `ArtifactCanvas.tsx` currently dispatches on `inst.format`, and the bespoke
S2 editors are only reachable through the Edit-mode `STRUCTURED_EDITORS` id map. Add an
id-keyed canvas route that applies in **both** Document and Edit mode for
`a-data-processing`, `a-quality-scorecard`, `a-business-validation`, `a-stat-tests`. The
plain `sheet` rendering of 2.1/2.2/2.4 artifact bodies is replaced by the canvas; the
sheet body itself stays as the export payload.

## 2. Data Processing (2.1)

**Canvas.** FactorTreeCanvas with the mapping overlay, plus an action area for the
selected row: bind / remap / ignore. Reuses the existing endpoints
(`bindFactorMap`, `setFactorMapIgnore`) and the same `FactorMap` model that
`components/dataeng/IndicatorCatalogPanel.tsx` already drives. The Data Engine panel stays
as-is — the same actions now exist on both surfaces.

A bulk **Ignore all pending** action lives on the canvas header so a user can clear the
tail of unmappable factors without walking every row.

**AI mapping summary.** The runner, when generating the 2.1 gate recommendation, grounds an
LLM summary on `resolve_factor_map(st)` statistics: mapped / pending / ignored counts per
L1 and L2, and the notable gaps (which business areas have no data at all). The summary
renders on the decision card in the Process pane as the basis for the choice.

**The gate becomes a real decision** with two options:

- **Continue in Data Engine** — a non-terminal choice. The engine records it and re-arms
  the gate (the existing rework mechanism, pointing back at 2.1). The frontend navigates to
  the Data Engine view on selection.
- **Proceed to next stage** — selectable only when no pending rows remain. The existing
  `data_intake_ready` guard (mapping complete **or** legacy manifest) remains the hard
  condition; this option surfaces it rather than replacing it.

`backend/app/domain/blueprint.py` and `frontend/src/lib/scenario.ts` are updated together.

## 3. Data Quality Score (2.2)

**Canvas.** FactorTreeCanvas with the quality overlay. The selected row expands the
existing ten-subcheck breakdown and the AI dimension commentary — extracted from
`QualityScorecardEditor.tsx` into a reusable per-row detail component. Disposition
(`accept | flag | drop`) is edited on the row or in the detail and still writes through
`PUT /quality-scorecard`.

The `panel:quality-review` inline panel keeps working; it wraps the same canvas.

**Process pane.** Tool-call timeline (section 6).

## 4. Business Validation (2.3) — deny at L4/indicator granularity

**New state.** `ProjectState.bv_signoff: dict[str, BvSignoff]`, keyed by the ledger's
indicator key `(norm_l4, norm_metric)` serialised as a string, valued
`{status: "accepted" | "denied", note: str}`. New endpoint
`PUT /api/projects/{id}/bv-signoff` re-renders `a-business-validation`.

Per the project convention, `ProjectState` fields are never aliased — the field
serialises as `bv_signoff` and `types.ts` matches that spelling.

**Interaction.** Each per-L3 `FactorCard` in `BusinessValidationView` gains per-L4 /
per-indicator Accept / Deny controls, with card-level *accept all* / *deny all*. The L3
card header shows the aggregate of its children (all accepted / mixed / all denied) —
a derived display value, not stored state. Denying next to a chart immediately marks the
matching row Denied in the FactorTreeCanvas.

The current sign-off path (an `editArtifact` body mutation, only writable in Edit mode) is
retired; sign-off is project state and writable in Document mode.

**Ledger.** `signoff_drop_pairs` reads the denied pairs from `bv_signoff`. It keeps reading
the legacy L3-level `group.signoff == "no"` from the artifact body as a fallback so saved
projects keep their verdicts. `drops_before(st, "statistical")` is unchanged, so denied
indicators are never scored by 2.4 — which is the point of the change.

The `d-2.3` gate option set is unchanged. Consistent with the existing rule that gate
options change nothing and row dispositions do the filtering, the pair-level sign-off is
the filter.

## 5. Statistical Score (2.4) — realign with reference 2.33

The reference workbook's `打分规则` sheet defines three bands per test and a
multiplicative acceptance rule. Current code uses four bands (0/0.5/1/2), an inverted VIF
direction (low VIF scored 0), and an additive total. Realign:

| Test | 0 | 0.5 | 1 |
|---|---|---|---|
| CV (volatility) | cv ≤ 0.05 | 0.05 < cv < 0.1 | cv ≥ 0.1 |
| Pearson (vs KPI) | \|r\| < 0.1 | 0.1 ≤ \|r\| < 0.3 | \|r\| ≥ 0.3 |
| VIF (collinearity) | VIF ≥ 5 | 1 < VIF < 5 | VIF ≤ 1 |

The workbook writes the top VIF band as "VIF = 1". Since `vif_all` floors its output at
1.0, implement it as `VIF <= 1.0` — the same set of values, with no float-equality trap.

**Total = CV × Pearson × VIF** (the workbook's `Final score = 完整性*颗粒度*真实性*一致性`
form, applied to the three statistical tests).

Verdict and default disposition:

- `Total == 0` → **Unconsiderable**, default `drop`, and a warning finding is emitted
  ("this indicator failed <test> outright"). Any single failing test zeroes the product —
  that strictness is the intent.
- `0 < Total ≤ 0.5` → **Acceptable**, default `review` (human decides).
- `Total > 0.5` → **Good**, default `include`. With three bands the only product above 0.5
  is 1.0, so Good means all three tests passed outright.

This is one notch stricter than the workbook's own 数据验收标准 note ("若 score 0.5–1，验收"),
which would auto-accept a 0.5. The stricter line is deliberate: a 0.5 product means some
test only half-passed, and that is exactly the case worth a human look.

The `STAT_SEVERE_VIF` override is removed — VIF ≥ 5 now scores 0 and zeroes the product on
its own, so a separate guard would be redundant.

Files to change together: `data_rules._cv_band` / `_pearson_band` / `_vif_band` /
`score_statistical` / `STAT_GOOD` / `STAT_ACCEPTABLE`, the
`statistical-scoring.json` rule library (band text and the rule page rendered into the
artifact), `stat_scoring.stat_sheet`, `StatScoreEditor`'s score selector (drop the `2`
option), the `stat.*` entries' `logic` text in `app/tools/registry.py`, and any test
expectations that pin the old bands.

**The tool wrappers stay identity wrappers.** `reference_cv`, `vif_all` and `pearson`
compute the raw statistics and are unchanged; only the banding/verdict layer moves.
`app/tools/_test_tools.py` must keep passing unmodified.

**Canvas.** FactorTreeCanvas with the statistical overlay; the selected row shows the three
raw statistics, their bands, and the AI rationale.

**Migration.** The new bands apply when 2.4 is re-run. Existing saved scorecards are not
retroactively rescored; their stored verdicts stand until the task runs again.

## 6. Tool-call timeline (Process pane, 2.2 / 2.4 and every tool-calling step)

`components/tools/ToolTrace.tsx` becomes **ToolTimeline**: an ordered list inside the build
step rather than a chip row. One line per tool — icon, tool name, argument summary, status,
duration, result summary — expandable for detail and linking to the tool page.

**Loading feel.** The frontend keeps a small constant map of the tools each task is expected
to call (`2.2 → quality.*`, `2.4 → stat.cv / stat.pearson / stat.vif`,
`2.5r → model.ols`). While the task is running, expected-but-absent tools render as queued
grey lines with the current one spinning; the 1.5 s `/state` poll brings back
`tool_invocations` one at a time and each line lights up as it lands.

**No backend change.** The existing `tracing.traced` / `tool_run` path already records one
invocation per tool per task run and emits a `tool` event as it happens. Steps that call
tools not in the constant map still render them — the map only seeds the queued placeholders.

Every step that mounts the component benefits, not just 2.2 / 2.4.

## Contracts to keep in sync

Per the project's standing rule, these pairs move together:

- `backend/app/domain/blueprint.py` ↔ `frontend/src/lib/scenario.ts` (the 2.1 decision gate)
- `backend/app/domain/models.py` ↔ `frontend/src/lib/types.ts` (`BvSignoff`, stat band
  values, canvas row shapes)
- `backend/app/main.py` ↔ `frontend/src/api/client.ts` (`PUT /bv-signoff`)

## Risks

- **2.3 sign-off migration.** Moving sign-off out of the artifact body changes where the
  ledger's signoff layer reads from. The legacy read path must stay, and
  `heal_state()` must tolerate projects with no `bv_signoff` field.
- **2.4 verdict distribution shifts.** The multiplicative rule is materially stricter than
  today's additive one — indicators that scraped by on two good tests now drop on one bad
  one. This is intended, but it will visibly change the seeded Danone case on the next 2.4
  run.
- **Canvas mounting.** Replacing the sheet rendering for three artifacts risks breaking the
  export path, which reads the sheet body. Keep producing the sheet body; only change what
  is rendered.
- **Poll churn.** The canvas mirrors store slices that the 1.5 s poll replaces wholesale.
  Any local editing state (a disposition being typed, a pending bind) must be guarded
  behind a dirty flag, the way `AnomalyReviewPanel`'s draft hook already does.

## Out of scope

- 2.5 / 2.5r / 2.6 surfaces (covered by the separate OLS L4-indicator-selection spec).
- Any change to the Data Engine's own views beyond the shared mapping actions.
- Retroactive rescoring of saved scorecards.
