# Design: Phase 3 — Dynamic Channel/Factor Vocabulary (Knowledge-sourced, not hardcoded)

**Date:** 2026-07-23
**Status:** Approved (pending plan)
**Depends on:** Phase 2 merged.
**Scope:** externalize the last hardcoded model vocabulary (the Y/X/spend/money/volume keyword banks + L1 taxonomy literals in `pivot.py`, and the interview role tokens) so it comes from the Knowledge/templates system, with the current constants retained as a byte-identical fallback. Backend-only.

---

## 1. Problem

Requirement #3: "模型涉及到哪些 Channel，涉及到哪些 Factor 从 Knowledge 调，都要动态，不能写死。"

Recon shows most of this is **already done**:
- **Channel coverage + ordering** — done in Phase 2 (`model_objects` is `value_counts`-ordered from data; the hardcoded `preferred` list was removed).
- **ROI / Contribution ranges** — already Knowledge-first: `build_range_index()` reads the `factor_tree` template per industry and only falls back to the reference `factor-ranges.json`; the sole production consumer is `ols_review.py`, which routes through it. The bare `match_factor_range` is called only by tests.

**What remains hardcoded** (the actual Phase 3 work):
1. `pivot.py` classification keyword banks: `_Y_METRIC_TYPES`, `_Y_KEYWORDS`, `_Y_TAGS`, `_DRIVER_TAGS`, `_SPEND_TYPES`, `_SPEND_KEYWORDS`, `_VOLUME_TYPE_KEYWORDS`, `_MONEY_TYPE_KEYWORDS`, plus the inline duplicate volume tokens in `_pick_y_metric` (L186).
2. `pivot.py` L1 taxonomy literals: `"KPI"` (`_is_y_row` L132), `"MARKETING FACTOR"`/`"COMMERCIAL FACTOR"` (`is_driver_row` L146).
3. `interviews.py` `_ROLE_TOKENS` (L19) — interview role/channel codes parsed from filenames.

## 2. Goal

Move the vocabulary above behind a per-industry Knowledge resolver, so a new industry can be onboarded by editing templates rather than Python — **without changing any current number** when no template override exists (the constants become the default).

## 3. Design

### 3.1 A vocabulary resolver (mirrors `build_range_index`)

Add `app/agents/vocabulary.py::build_vocab(industry_l1, industry_l2) -> Vocab`, a frozen dataclass carrying:
- `y_metric_types`, `y_keywords`, `y_tags`, `driver_tags`, `spend_types`, `spend_keywords`, `volume_keywords`, `money_keywords` (each `frozenset[str]`),
- `y_l1_labels`, `driver_l1_labels` (frozensets — the `{"KPI"}` and `{"MARKETING FACTOR","COMMERCIAL FACTOR"}` sets).

Resolution order (same pattern as `RangeIndex.match`): a Knowledge template override → the built-in default constants (the exact current values, moved into `vocabulary.py` as `DEFAULT_VOCAB`). With no template present, `build_vocab(...)` returns `DEFAULT_VOCAB` — byte-identical to today.

### 3.2 Knowledge source

Store the override on a **`rules`-kind template** (the kind already exists) via a new optional structured payload `vocab: VocabRules` on `KnowledgeTemplate` (a Pydantic block: the eight token lists + two L1-label lists, all optional; a missing field falls back to the default). `_ensure_seeded`'s version-heal already supports adding a builtin section, so the beverage pack can seed its `vocab` explicitly (equal to the defaults) as documentation, and other industries can override. `build_vocab` reads it via `get_templates().best_match("rules", l1, l2)`.

(Alternative considered: derive L1 labels from the `factor_tree` template's distinct `l1` values — viable for the L1 literals but the keyword banks aren't representable in `FactorTreeRow`, so a `rules.vocab` payload is the single coherent home. Chosen.)

### 3.3 Threading it through `pivot.py`

The `pivot.py` predicates (`_is_y_row`, `is_driver_row`, `is_volume_metric_type`, `is_money_metric`, `_is_spend`, `_pick_y_metric`) currently read module constants directly. Thread a `vocab: Vocab` parameter (defaulting to `DEFAULT_VOCAB`) so:
- Existing call sites that don't pass one keep today's behavior exactly (default).
- The S2/S4 entry points that know the project's industry (`build_model_frame`, `driver_candidates_by_l4`, `y_candidates`, `stat_scoring._monthly_y`) resolve `build_vocab(industry)` once and pass it down. Industry comes from `st.meta.industry` (already available where these run).
- Remove the inline duplicate volume tokens at `_pick_y_metric` L186 — use `vocab.volume_keywords`.

Keep signatures backward-compatible (new param last, defaulted) so untraced/secondary paths are untouched.

### 3.4 Interview role tokens

`interviews.py::_parse_layer_role` reads `_ROLE_TOKENS` from the **`interview`-kind** template when available (the interview template already carries roles via `interview_questions[].role`), falling back to the current `_ROLE_TOKENS` default. Lowest-risk: add `role_tokens` to the interview template payload (or derive distinct roles from its questions), resolved via `get_templates().best_match("interview", l1, l2)`; default = current list.

## 4. Byte-parity guarantee (the load-bearing constraint)

No current number may change when no override exists. This is enforced by:
- `DEFAULT_VOCAB` = the exact current constant values.
- A **new** direct parity test `app/mmm/_test_vocab_parity.py`: for a fixture covering every token, assert `_is_y_row`/`is_driver_row`/`is_volume_metric_type`/`is_money_metric`/`_is_spend`/`_pick_y_metric` produce identical output with `DEFAULT_VOCAB` as they did before the refactor (capture the pre-refactor outputs as the expected fixture). And the seeded beverage `vocab` override (equal to defaults) must produce the same results as no override.
- `_test_synthetic` / `_test_real` / `_test_tools` must stay green with identical numbers (R² unchanged), and `tests/test_data_rules.py:97-102` (range values) untouched.

## 5. Risks

- **HIGH — silent number drift.** If the resolver or threading changes any predicate's result, S2 screening and the OLS fit shift. Mitigated by the parity test + the unchanged-numbers suites; if any diverges, revert rather than update the expectation.
- **MEDIUM — call-site coverage.** Every predicate consumer that runs on a project must receive the industry-resolved vocab, or it silently uses the default (correct today, but misses the override). Enumerate consumers (recon §1) and thread explicitly; a consumer left on the default is safe (falls back), just not yet industry-aware — acceptable and documented.
- **LOW — template heal** when adding the `vocab`/`role_tokens` payload; `_ensure_seeded` version bump handles it.

## 6. Success criteria

1. `pivot.py` predicates and `interviews.py` role parsing read their vocabulary from `build_vocab`/the interview template, with `DEFAULT_VOCAB`/`_ROLE_TOKENS` as fallback.
2. With no Knowledge override, every predicate and the full OLS pipeline produce **identical** numbers to before (parity test + unchanged suites green; R² identical).
3. Editing a `rules.vocab` (or interview) template for an industry changes classification for that industry's projects with no code change — demonstrated by a test where an override reclassifies a metric.
4. No hardcoded classification vocabulary remains as the *only* source in `pivot.py`/`interviews.py` (constants survive only as defaults).
