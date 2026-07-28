"""2.5 OLS Regression Test — build the candidate model-input wide table, fast-OLS
fit it per model object, and compare each indicator's ROI / Contribution against
the industry Knowledge ranges, projected onto the complete factor tree.

The wide table is derived from prior-stage data (``model_df`` + ``build_model_frame``),
excluding indicators dropped by 2.2 (quality) / 2.4 (statistical). Every active
factor-tree row is surfaced — in-model rows carry coef / t / p / ROI / Contribution
and a range verdict; out-of-range rows (ROI **or** Contribution) are flagged for
human review. The ``d-2.5`` gate then decides whether flagged indicators are
physically excluded when 2.6 assembles the final Master Data.

The result body uses the ``olsTree`` artifact format (see ``OlsTreeData`` in
``frontend/src/lib/types.ts``); all keys are camelCase, numbers are ``None`` on NaN.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from app.agents import data_rules
from app.agents.dataset_cache import model_df, model_objects, uses_project_data
from app.agents.data_rules import build_range_index, RangeBenchmark
from app.agents.ledger import (
    _LAYER_PAIRS_BY_OBJECT,
    LAYER_LABEL,
    LAYER_TASK,
    OBJECT_ANY,
    ModelSelection,
    _matches,
    _obj,
    _object_drops,
    indicator_ledger,
    model_selection,
    ols_flagged_pairs,
    quality_drop_pairs,
    stat_drop_pairs,
    upstream_drop_pairs,
)
from app.dataeng.mapping import resolve_factor_map
from app.domain.models import (
    OlsConfig,
    OlsParams,
    OlsXCandidate,
    OlsYCandidate,
    OlsYChoice,
)
from app.mmm import driver_candidates_by_l4, run_mmm, y_candidates
from app.store.state import ProjectState
from app.tools import get as get_tool
from app.tools.tracing import traced

# |t| threshold for statistical significance (≈ 5% two-sided at moderate dof).
SIGNIFICANT_T = 2.0

# Proposal thresholds — what the AI ticks by default in the 2.5x step.
MIN_ABS_PEARSON = 0.1   # below this the variable carries no signal vs Y
MAX_VIF = 10.0          # above this it is collinear with the rest
DEFAULT_MAX_SELECTED = 8  # keep df healthy on a ~34-month series

# Short monthly series cannot support a linear trend plus a full Fourier season
# without the controls over-absorbing actual sales into the baseline (baseline
# share > 100%, wrong-sign paid drivers). Scale the proposed controls to the
# usable observation count so the first fit is identified and interpretable.
MIN_OBS_FOR_SEASONALITY = 24   # below this: drop the seasonal controls entirely
MIN_OBS_FOR_FULL_FOURIER = 36  # below this: cap Fourier at K=1


def _norm(s: object) -> str:
    return str(s).strip().lower() if s is not None else ""


def _norm_pair(l4: object, metric: object) -> tuple[str, str]:
    return (_norm(l4), _norm(metric))


def _num(v: float | None, digits: int = 3) -> float | None:
    """Round, mapping NaN / None → None so the JSON body carries real nulls."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, digits)


def _nan_mean(xs: list[float]) -> float:
    vals = [float(x) for x in xs if x is not None and not math.isnan(float(x))]
    return sum(vals) / len(vals) if vals else float("nan")


# ── drop-pair resolution — one source of truth, in the ledger ───────────────
# These are re-exported so the existing call sites keep working; the semantics
# (and the inheritance rules behind them) live in `app.agents.ledger`.
ols_drop_pairs = ols_flagged_pairs


# ── 2.5 setup proposal (AI proposes → human reviews in 2.5y / 2.5x / 2.5p) ──


def _stat_index(st: ProjectState) -> dict[tuple[str, str, str], object]:
    """2.4's scored rows keyed by (object, l4, indicator) — the evidence behind
    the advice, one row per channel's own screening (``OBJECT_ANY`` for legacy
    scorecards recorded before rows carried an object).

    2.5 runs after 2.4, so the human-reviewed scorecard is normally on state. If
    it is missing (2.4 not run / legacy state) we recompute it with 2.4's own
    builder rather than propose without evidence.
    """
    card = getattr(st, "stat_scorecard", None)
    if card is None or not getattr(card, "rows", None):
        try:
            from app.agents.stat_scoring import build_stat_scorecard
            card = build_stat_scorecard(st)
        except Exception:  # noqa: BLE001 — a proposal without stats still beats failing
            return {}
    out: dict[tuple[str, str, str], object] = {}
    for r in getattr(card, "rows", None) or []:
        obj = _obj(getattr(r, "object", "")) or OBJECT_ANY
        out[(obj, *_norm_pair(r.l4, r.indicator))] = r
    return out


def _y_rationale(c: dict, recommended: bool) -> str:
    unit = "money" if c["is_money"] else ("volume" if c["is_volume"] else "other")
    base = f"{c['months']} months of coverage · {unit} unit ({c['metric_type']})."
    if recommended:
        return base + " Recommended: the KPI volume response keeps coefficients in sales units."
    if c["is_money"]:
        return base + " Choosing this makes ROI a true incremental-revenue / spend ratio."
    return base


def _x_rationale(row: object | None, cand: dict, recommended: bool) -> str:
    if row is None:
        return "No 2.4 statistics for this variable — review before including."
    bits = [f"r={row.pearson:+.2f} vs KPI", f"VIF={row.vif:.1f}", f"CV={row.cv:.3f}",
            f"2.4: {row.auto_verdict or '—'}"]
    head = "Recommended. " if recommended else ""
    if not recommended:
        if abs(row.pearson) < MIN_ABS_PEARSON:
            head = "Weak correlation with the KPI. "
        elif row.vif >= MAX_VIF:
            head = "Collinear with other variables. "
    return head + " · ".join(bits)


def _usable_months(df) -> int:
    """Distinct monthly observations available to the model frame — the ceiling
    on how many trend/seasonality controls a fit can afford."""
    try:
        if "month" in getattr(df, "columns", []):
            return int(df["month"].nunique())
    except Exception:  # noqa: BLE001 — a bad month column just means "unknown"
        pass
    return 0


def _propose_params(df) -> OlsParams:
    """Default transform/control settings scaled to series length.

    Seasonality is proposed **off** at every length (2026-07-26). The length-scaled
    ladder below still decides how much seasonality a series *could* afford, but on
    the real cases even one Fourier harmonic over-absorbed: with ~34 months and ~12
    drivers, the controls took the baseline past 100% and pushed contributions
    outside every Knowledge band, which made the whole range check meaningless. The
    trend stays on — one column, and a growing market needs it. The human turns
    Fourier back on in the OLS settings when the series is long enough to pay for
    it, and the artifact's misspecification finding says when it is not.
    """
    n = _usable_months(df)
    if n and n < MIN_OBS_FOR_FULL_FOURIER:
        return OlsParams(trend="linear", seasonality="none", fourier_k=1)
    return OlsParams()


def build_ols_proposal(st: ProjectState) -> OlsConfig:
    """Propose the OLS setup: response candidates, model variables, parameters.

    Everything numeric is computed (Y coverage/unit from the long table; X stats
    reused from 2.4's ``stat_scorecard``) — nothing is invented. The human
    confirms or overrides each part in the 2.5y / 2.5x / 2.5p Process steps.
    """
    df = model_df(st)
    objects = model_objects(st)
    stats = _stat_index(st)

    from app.agents.vocabulary import vocab_for
    vocab = vocab_for(st)

    # ── Y: one candidate list per model object; recommend the KPI volume ──
    y_cands: list[OlsYCandidate] = []
    y_choice: list[OlsYChoice] = []
    for obj in objects:
        cands = y_candidates(df, obj, vocab)
        for i, c in enumerate(cands):
            rec = i == 0  # y_candidates() puts the volume-preferring default first
            y_cands.append(OlsYCandidate(
                object=obj, metric=c["metric"], metricType=c["metric_type"],
                months=c["months"], isMoney=c["is_money"], recommended=rec,
                rationale=_y_rationale(c, rec),
            ))
        if cands:
            top = cands[0]
            y_choice.append(OlsYChoice(object=obj, metric=top["metric"],
                                       metricType=top["metric_type"],
                                       isMoney=top["is_money"]))

    # ── X: each object screens its own driver universe, scored by 2.4 ──
    # Indicators an earlier layer rejected are listed too, but locked. Hiding
    # them (the old behaviour) left the human with no way to see where a
    # variable went — and no trace of who decided it. Candidates are never
    # deduped across objects: the same indicator can be a strong driver in one
    # channel and collinear/insignificant in another, so each channel needs its
    # own row, its own stats, and its own lock/select verdict.
    x_cands: list[OlsXCandidate] = []
    for obj in objects:
        seen: dict[tuple[str, str], OlsXCandidate] = {}
        for c in driver_candidates_by_l4(df, obj, vocab):
            key = _norm_pair(c["l4"], c["metric"])
            if key in seen:
                continue
            locked_by = next(
                (lid for lid in ("mapping", "quality", "signoff", "statistical")
                 if _matches(key, _object_drops(_LAYER_PAIRS_BY_OBJECT[lid](st), obj))),
                "")
            row = stats.get((obj, *key)) or stats.get((OBJECT_ANY, *key))
            ok = (not locked_by
                  and row is not None
                  and abs(row.pearson) >= MIN_ABS_PEARSON
                  and row.vif < MAX_VIF)
            seen[key] = OlsXCandidate(
                key=f"{key[0]}|{key[1]}", object=obj,
                l1=c["l1"], l2=c["l2"], l3=c["l3"], l4=c["l4"],
                indicator=c["metric"], metric=c["metric"], isSpend=c["is_spend"],
                pearson=round(float(getattr(row, "pearson", 0.0)), 4),
                vif=round(float(getattr(row, "vif", 1.0)), 3),
                cv=round(float(getattr(row, "cv", 0.0)), 4),
                statVerdict=str(getattr(row, "auto_verdict", "")),
                recommended=bool(ok), selected=bool(ok),
                locked=bool(locked_by), lockedBy=locked_by,
                rationale=(f"Rejected at {LAYER_LABEL[locked_by]} ({LAYER_TASK[locked_by]}) — "
                           "not available as a model variable." if locked_by
                           else _x_rationale(row, c, bool(ok))),
            )
        obj_cands = sorted(seen.values(),
                           key=lambda r: (r.locked, not r.recommended, -abs(r.pearson), r.indicator))

        # Cap the pre-ticked set, per object, so the first fit is identified on a
        # short series; everything stays visible and the human can tick more
        # (the df guard warns). Reset at each object boundary — one channel's
        # cap must never crowd out another channel's own candidates.
        picked = 0
        for c in obj_cands:
            if c.selected:
                picked += 1
                if picked > DEFAULT_MAX_SELECTED:
                    c.selected = False
                    c.rationale += (f" Not pre-ticked — beyond the top {DEFAULT_MAX_SELECTED} "
                                    "by correlation; tick to include.")

        # Never hand this object back an empty selection: with heavily collinear
        # data nothing clears the gate, and a fit with no variables cannot run at
        # all. Pre-tick the best available as a starting point and say plainly
        # that they failed the gate. Locked candidates are never revived — an
        # earlier layer already ruled.
        openable = [c for c in obj_cands if not c.locked]
        if openable and not any(c.selected for c in openable):
            for c in sorted(openable, key=lambda r: (-abs(r.pearson), r.vif))[:DEFAULT_MAX_SELECTED]:
                c.selected = True
                c.rationale += (" Pre-ticked only as a starting point — no variable cleared the "
                                "correlation/collinearity gate. Review before trusting the fit.")

        x_cands.extend(obj_cands)

    return OlsConfig(
        dataSource="project" if uses_project_data(st) else "reference",
        yCandidates=y_cands, y=y_choice, xCandidates=x_cands,
        params=_propose_params(df), proposedAt="",
    )


# ── 2.5 indicator search (寻优) ──────────────────────────────────────────────
# The design (02-data-agent §2.34) is a per-L4 search, not a manual variable
# tick: "pick which indicator per L4 makes each factor's Contribution / ROI land
# in its business-expected range". We do exactly that — a coordinate-descent over
# each L4's candidate indicators, keeping the choice that lands the L4 in its
# Knowledge range, maximising the in-range L4 count (tie-break R²) under a fit
# budget. The single Y comes from the 2.1 Metrics-Type; params scale to length.
SEARCH_MAX_DRIVERS = 12   # p<n on a ~34-month national series
SEARCH_MAX_FITS = 96      # hard budget on trial regressions (see the wall clock below)
SEARCH_MAX_SECONDS = 90.0  # the real guard — the fit count is only a backstop


@dataclass
class SearchScore:
    """What one trial fit tells us about a candidate assignment."""
    in_range: int          # L4s landing inside their Knowledge band
    signed_ok: int         # paid drivers carrying the expected (positive) sign
    r2: float
    per_l4: dict[str, str]  # l4norm -> 'in' | 'out' | 'none'
    trials: list[dict]      # one record per (l4, indicator) in this fit

    @property
    def objective(self) -> tuple[int, int, float]:
        """Lexicographic: land factors in range, then get the signs right, then fit.

        The sign term is what makes the search useful on a project with few or no
        Knowledge benchmarks. Without it every unbenchmarked factor scored the same
        no matter which indicator it used, so the search had nothing to prefer and
        never tried an alternate — which is why it used to run four fits in total.
        """
        return (self.in_range, self.signed_ok, self.r2)


def _search_score(st: ProjectState, cfg: OlsConfig) -> SearchScore:
    """Fit ``cfg`` and score it, **without persisting it**.

    ``per_l4``: ``in`` = the L4's driver lands inside its Knowledge ROI/Contribution
    band; ``out`` = a benchmark exists and it is outside; ``none`` = no benchmark.

    The trial config is passed to ``model_selection`` explicitly rather than being
    written to ``st.ols_config`` first. Writing it meant every trial mutated the
    project — a crash mid-search left a trial configuration persisted as if a human
    had chosen it.
    """
    sel = model_selection(st, cfg=cfg)
    objects, _prefit, records = _collect_records(st, sel, cfg)
    industry = getattr(getattr(st, "meta", None), "industry", None)
    idx = build_range_index(getattr(industry, "l1", None), getattr(industry, "l2", None))
    r2 = 0.0
    for o in objects:
        if o.get("r2") is not None:
            r2 = max(r2, float(o["r2"]))
    in_range = 0
    signed_ok = 0
    per_l4: dict[str, str] = {}
    trials: list[dict] = []
    for (_obj_key, l4n, _metricn), rec in records.items():
        bench = idx.match(rec["l4"], rec["metric"])
        row = _row_from_record(rec, bench)
        coef = row.get("coef")
        # A paid driver is expected to move sales up; an exposure / count / rate
        # driver has no universal expected sign, so only spend is judged on it.
        # ROI exists only for spend columns, which is how spend is recognised here.
        sign_expected = bool(rec.get("rois"))
        sign_correct = bool(sign_expected and coef is not None and float(coef) > 0)
        if sign_correct:
            signed_ok += 1
        trials.append({
            "l4": rec.get("l4", ""), "indicator": rec.get("metric", ""),
            "r2": round(r2, 4), "coef": coef,
            "tValue": row.get("tValue"), "pValue": row.get("pValue"),
            "significant": row.get("significant"),
            "signExpected": sign_expected, "signCorrect": sign_correct,
            "roi": row.get("roi"), "contribution": row.get("contribution"),
            "roiStatus": row.get("roiStatus"), "contributionStatus": row.get("contributionStatus"),
            "roiRange": row.get("roiRange", ""), "contributionRange": row.get("contributionRange", ""),
        })
        if not _has_benchmark(bench):
            per_l4.setdefault(l4n, "none")
            continue
        ok = row["roiStatus"] != "out" and row["contributionStatus"] != "out"
        # An L4 counts in-range if any of its (rare, when duplicated) records is in.
        if ok:
            per_l4[l4n] = "in"
            in_range += 1
        else:
            per_l4.setdefault(l4n, "out")
    return SearchScore(in_range, signed_ok, round(r2, 4), per_l4, trials)


def build_ols_search(st: ProjectState, *, max_fits: int = SEARCH_MAX_FITS,
                     max_seconds: float = SEARCH_MAX_SECONDS,
                     on_pass=None) -> tuple[OlsConfig, dict]:
    """Search each L4's candidate indicators for the model that reads best.

    Returns ``(config, trace)``. ``config`` is a ready-to-fit :class:`OlsConfig`
    with one chosen indicator ticked per active L4 (the rest present-but-unticked),
    the single 2.1 Y, and length-scaled params.

    **Every L4 with more than one candidate is searched**, not only the ones already
    out of range. The old rule skipped any factor whose status was ``none`` — and
    with the reference range library most factors have no benchmark at all, so the
    "search" tried four fits for the whole model and the Build Process had nothing
    to show. The objective is lexicographic (in-range count → correct paid-driver
    signs → R²), so an unbenchmarked factor is still decided on something real.

    ``trace`` carries the per-trial record the artifact renders: what was tried for
    each factor, what it scored, and why the winner won. ``on_pass(info)`` is called
    after each coordinate-descent pass so the caller can emit progress.
    """
    import time

    started = time.monotonic()
    proposal = build_ols_proposal(st)

    # Candidates that survived every earlier layer, grouped by L4, best |r| first.
    by_l4: dict[str, list[OlsXCandidate]] = defaultdict(list)
    for c in proposal.x_candidates:
        if c.locked:
            continue
        by_l4[c.l4].append(c)
    for l4 in by_l4:
        by_l4[l4].sort(key=lambda c: -abs(c.pearson))
    if not by_l4:
        # Nothing to search — hand back the proposal's own pre-tick.
        return proposal, {"fits": 0, "l4Searched": 0, "candidates": 0, "swaps": 0,
                          "inRange": 0, "r2": 0.0, "trials": [], "perFactor": [],
                          "note": "no searchable candidates"}

    # Seed: the strongest L4s (by their best candidate) fill the driver budget,
    # each starting on its top-correlated indicator.
    l4_order = sorted(by_l4, key=lambda l4: -abs(by_l4[l4][0].pearson))
    active = l4_order[:SEARCH_MAX_DRIVERS]
    chosen: dict[str, int] = {l4: 0 for l4 in active}
    n_candidates = sum(len(by_l4[l4]) for l4 in active)

    def cfg_for(sel_idx: dict[str, int]) -> OlsConfig:
        picked = {by_l4[l4][idx].key for l4, idx in sel_idx.items()}
        new_x = [c.model_copy(update={"selected": (c.key in picked and not c.locked)})
                 for c in proposal.x_candidates]
        # `model_copy(update=...)` keys on FIELD names, not aliases. Passing
        # "xCandidates" here silently set an unrelated attribute and left
        # `x_candidates` untouched — so every trial scored the proposal's own
        # pre-tick and the search could never change anything it measured.
        return proposal.model_copy(update={"x_candidates": new_x})

    # Every trial is recorded, winner or not — "why this indicator and not that
    # one" is the question the d-2.5 reviewer actually has, and the old search
    # computed the answer on every fit and then discarded it.
    log: list[dict] = []

    def run(sel_idx: dict[str, int], *, l4: str, alternate: str, seed: bool) -> SearchScore:
        score = _search_score(st, cfg_for(sel_idx))
        for t in score.trials:
            if seed or _norm(t.get("l4")) == _norm(l4):
                log.append({**t, "trial": len(log) + 1, "seed": seed,
                            "triedFor": l4, "alternate": alternate,
                            "objectiveInRange": score.in_range,
                            "objectiveSigned": score.signed_ok})
        return score

    best_idx = dict(chosen)
    best = run(best_idx, l4="", alternate="", seed=True)
    fits = 1
    swaps = 0

    def out_of_budget() -> bool:
        return fits >= max_fits or (time.monotonic() - started) > max_seconds

    # Coordinate descent over every searchable factor: try each alternate and keep
    # any swap that improves the objective. Converges in two passes in practice; the
    # wall clock, not the fit count, is the guard that actually binds.
    for _pass in range(2):
        improved = False
        for l4 in active:
            if out_of_budget():
                break
            for alt in range(len(by_l4[l4])):
                if alt == best_idx[l4] or out_of_budget():
                    continue
                trial = dict(best_idx)
                trial[l4] = alt
                score = run(trial, l4=l4, alternate=by_l4[l4][alt].metric, seed=False)
                fits += 1
                if score.objective > best.objective:
                    best, best_idx, improved = score, trial, True
                    swaps += 1
        if on_pass is not None:
            on_pass({"pass": _pass + 1, "fits": fits, "swaps": swaps,
                     "inRange": best.in_range, "signed": best.signed_ok, "r2": best.r2})
        if not improved or out_of_budget():
            break

    per_factor = [{
        "l4": l4,
        "chosen": by_l4[l4][best_idx[l4]].metric,
        "candidates": [c.metric for c in by_l4[l4]],
        "status": best.per_l4.get(_norm(l4), "none"),
    } for l4 in active]

    truncated = len(l4_order) > len(active)
    note = (f"Searched {len(active)} factor(s) over {n_candidates} candidate indicator(s) "
            f"in {fits} trial fit(s); {swaps} swap(s) improved the model; "
            f"{best.in_range} factor(s) landed in their Knowledge ROI/Contribution range.")
    if truncated:
        note += (f" {len(l4_order) - len(active)} weaker factor(s) were left out of the "
                 f"search to keep the model identified (max {SEARCH_MAX_DRIVERS} drivers).")
    if out_of_budget():
        note += " The search stopped on its budget rather than on convergence."

    final = cfg_for(best_idx)
    trace = {"fits": fits, "l4Searched": len(active), "candidates": n_candidates,
             "swaps": swaps, "inRange": best.in_range, "signedOk": best.signed_ok,
             "r2": best.r2, "trials": log, "perFactor": per_factor,
             "factorsSkipped": len(l4_order) - len(active), "note": note}
    return final, trace


def selected_x_metrics(cfg: OlsConfig | None) -> dict[str, frozenset[tuple[str, str]]] | None:
    """Per-object indicators the human kept — ``None`` = auto-select (legacy).

    Keyed by model object (``OBJECT_ANY`` for candidates predating the object
    field); each entry is a set of ``(norm_l4, norm_metric)`` pairs, the key space
    every S2 layer shares. Ticking a bare metric name used to keep it under every
    L4 that happened to use the same label.
    """
    if cfg is None or not cfg.x_candidates:
        return None
    out: dict[str, set[tuple[str, str]]] = {}
    for c in cfg.x_candidates:
        if c.selected:
            out.setdefault(_obj(c.object) or OBJECT_ANY, set()).add(
                (_norm(getattr(c, "l4", "")), _norm(c.metric)))
    return {k: frozenset(v) for k, v in out.items()} or None


def y_metric_for(cfg: OlsConfig | None, obj: str) -> str | None:
    if cfg is None:
        return None
    for c in cfg.y:
        if c.object == obj:
            return c.metric or None
    return None


# ── OLS review builder ──────────────────────────────────────────────────────


def _collect_records(
    st: ProjectState,
    sel: ModelSelection,
    cfg: OlsConfig | None = None,
    *,
    eng=None,
    task_id: str | None = None,
) -> tuple[list[dict], dict, dict]:
    """Fit each model object; return (object summaries, prefit, per-indicator records).

    When ``cfg`` is present the fit honours the human's confirmed setup — the Y
    they chose, the X they ticked, and their transform/control parameters.
    Without it we fall back to the legacy auto-fit so old projects still run.

    ``sel`` is the resolved :class:`ModelSelection` — its exclude set is read
    per object (``sel.exclude_for(obj)``) so one channel's drop never excludes
    an indicator from another channel's fit.

    ``eng``/``task_id`` record each object's regression as an explicit
    ``model.ols`` tool invocation; without them the fit runs untraced.
    """
    objects: list[dict] = []
    prefit: dict[str, dict] = {}
    # records[(obj, l4n, metricn)] = one object's own per-indicator stats —
    # never accumulated across objects, so ROI/contribution are never averaged
    # between channels.
    records: dict[tuple[str, str, str], dict] = {}
    df = model_df(st)
    include = selected_x_metrics(cfg)
    params = cfg.params if cfg is not None else None
    for obj in model_objects(st):
        y_metric = y_metric_for(cfg, obj)
        inc = include.get(obj) if isinstance(include, dict) else include
        try:
            res = traced(
                eng, st, task_id, "model.ols",
                f"{obj} · Y={y_metric or 'auto'} · {len(inc) if inc else 'auto'} X",
                get_tool("model.ols").run, df, obj,
                adstock=0.5, hill_half=1.0, exclude=sel.exclude_for(obj),
                y_metric=y_metric, include=inc, params=params, st=st,
                summarize=lambda r: f"R²={r.r2:.3f} · {int(r.n_obs)} obs · {len(r.drivers)} drivers",
            )
        except Exception as e:  # noqa: BLE001
            objects.append({
                "object": obj, "nObs": 0, "drivers": 0, "r2": None, "adjR2": None,
                "mape": None, "durbinWatson": None, "baselinePct": None,
                "redFlags": [], "error": f"{e}"[:200],
                "yMetric": y_metric_for(cfg, obj) or "", "roiUnit": "",
                "dfRemaining": None, "controls": [],
            })
            continue
        objects.append({
            "object": obj, "nObs": int(res.n_obs), "drivers": len(res.drivers),
            "r2": _num(res.r2), "adjR2": _num(res.adj_r2), "mape": _num(res.mape, 2),
            "durbinWatson": _num(res.durbin_watson), "baselinePct": _num(res.baseline_pct, 2),
            "redFlags": list(res.red_flags or []), "error": "",
            "yMetric": str(res.meta.get("y_metric", "")),
            "roiUnit": str(res.meta.get("roi_unit", "")),
            "dfRemaining": res.meta.get("df_remaining"),
            "controls": list(res.meta.get("control_cols") or []),
        })
        prefit[obj] = {"r2": res.r2, "mape": res.mape,
                       "baseline_pct": res.baseline_pct, "red_flags": res.red_flags}
        dmeta = res.meta.get("drivers_meta", {}) if isinstance(res.meta, dict) else {}
        tvals = res.meta.get("tvalues", {}) if isinstance(res.meta, dict) else {}
        pvals = res.meta.get("pvalues", {}) if isinstance(res.meta, dict) else {}
        for d in res.drivers:
            meta = dmeta.get(d, {})
            l4 = (meta.get("l4") or meta.get("l3") or meta.get("l1") or "").strip()
            metric = meta.get("metric") or d
            key = (obj, *_norm_pair(l4, metric))
            rec = records.get(key)
            if rec is None:
                rec = {"l4": l4, "l1": meta.get("l1", ""), "l2": meta.get("l2", ""),
                       "l3": meta.get("l3", ""), "metric": metric,
                       "contribs": [], "rois": [], "coefs": [],
                       "best_t": None, "objects": [], "results": [],
                       # Which spend this indicator's ROI was divided by — an
                       # exposure metric borrows its L4's, and a reader who is
                       # not told that will misread it as a cost-per-unit.
                       "roi_basis": None,
                       # ROI is only comparable to the Knowledge money bands when
                       # this object's own fit produced a revenue ROI.
                       "roi_money": True}
                records[key] = rec
            if str(res.meta.get("roi_unit", "")) != "revenue/spend":
                rec["roi_money"] = False
            coef = res.coefficients.get(d)
            contrib = res.contribution.get(d)
            # Every driver whose L4 carries Spending has an ROI (spend columns
            # divide by their own spend, the rest by their L4's) — absent only
            # when nothing under that L4 was bought.
            roi = res.roi.get(d)
            tval = tvals.get(d)
            pval = pvals.get(d)
            if contrib is not None:
                rec["contribs"].append(contrib)
            if roi is not None:
                rec["rois"].append(roi)
                if rec["roi_basis"] is None:
                    rec["roi_basis"] = (res.meta.get("roi_basis") or {}).get(d)
            if coef is not None:
                rec["coefs"].append(coef)
            if tval is not None and not math.isnan(float(tval)):
                if rec["best_t"] is None or abs(float(tval)) > abs(rec["best_t"][0]):
                    rec["best_t"] = (float(tval), pval)
            rec["objects"].append(obj)
            rec["results"].append({
                "object": obj, "coef": _num(coef), "tValue": _num(tval),
                "pValue": _num(pval, 4), "roi": _num(roi), "contribution": _num(contrib, 2),
            })
    return objects, prefit, records


def _range_status(value: float, rng: tuple[float, float] | None) -> str:
    if rng is None or value is None or math.isnan(float(value)):
        return "none"
    return "in" if data_rules.in_range(float(value), rng) else "out"


def _row_from_record(rec: dict, bench: RangeBenchmark | None) -> dict:
    """Aggregate one object's per-indicator record + apply the range verdict.

    ``rec`` is now scoped to a single model object (the record key carries the
    object), so this mean is over that one channel's own driver columns — never
    averaged across channels."""
    contrib = _nan_mean(rec["contribs"])
    roi = _nan_mean(rec["rois"])
    coef = _nan_mean(rec["coefs"])
    tval = rec["best_t"][0] if rec["best_t"] else float("nan")
    pval = rec["best_t"][1] if rec["best_t"] else None
    significant = (abs(tval) >= SIGNIFICANT_T) if tval == tval else None

    # The Knowledge ROI bands are money ratios. Only range-check ROI when the fit
    # actually produced revenue/spend (money Y, or volume Y with a unit price) —
    # a 箱/元 ratio is not comparable and must never be flagged against them.
    roi_money = bool(rec.get("roi_money", False))
    roi_status = _range_status(roi, bench.roi if bench else None) if roi_money else "none"
    con_status = _range_status(contrib, bench.contribution if bench else None)

    # Only the borrowed denominator needs saying: an indicator that is itself a
    # spend metric divides by its own spend, which the ROI already implies.
    basis = rec.get("roi_basis") or {}
    roi_basis = ""
    if basis.get("source") == "l4":
        spent = ", ".join(str(m) for m in (basis.get("metrics") or []))
        roi_basis = f"÷ {basis.get('l4') or 'L4'} spend" + (f" ({spent})" if spent else "")
    return {
        "coef": _num(coef), "tValue": _num(tval), "pValue": _num(pval, 4),
        "significant": significant,
        "roi": _num(roi), "contribution": _num(contrib, 2),
        "roiBasis": roi_basis,
        "roiRange": (bench.roi_text if bench else "") if roi_money else "",
        "contributionRange": bench.contribution_text if bench else "",
        "rangeSource": bench.source if bench else "",
        "roiStatus": roi_status, "contributionStatus": con_status,
        "objects": sorted(set(rec["objects"])),
        "results": rec["results"],
    }


def _flag_reason(row: dict) -> str:
    parts = []
    if row["roiStatus"] == "out" and row["roi"] is not None:
        parts.append(f"ROI {row['roi']:g} outside {row['roiRange']}")
    if row["contributionStatus"] == "out" and row["contribution"] is not None:
        parts.append(f"Contribution {row['contribution']:g}% outside {row['contributionRange']}")
    return "; ".join(parts)


def _has_benchmark(bench: RangeBenchmark | None) -> bool:
    return bench is not None and (bench.roi is not None or bench.contribution is not None)


def _classify(row: dict, dropped_by: str, in_model: bool, bench: RangeBenchmark | None) -> tuple[str, str]:
    """Return (status, flagReason). Precedence: notMapped → dropped → notInModel →
    noBenchmark → review (ROI or Contribution out) → inRange.

    ``notMapped`` (rejected at the 2.1 mapping layer — no published indicator ever
    covered this factor) is split out from ``dropped`` (a real screening decision
    at quality/sign-off/statistical/range). The two read very differently: the
    first is upstream data coverage, the second is a verdict on data that exists.
    The tree hides ``notMapped`` by default so a sparse dataset doesn't look like
    the model threw everything away."""
    if dropped_by == "mapping":
        return "notMapped", ""
    if dropped_by:
        return "dropped", ""
    if not in_model:
        return "notInModel", ""
    if not _has_benchmark(bench):
        return "noBenchmark", ""
    if row["roiStatus"] == "out" or row["contributionStatus"] == "out":
        return "review", _flag_reason(row)
    return "inRange", ""


def _empty_row_fields() -> dict:
    return {
        "coef": None, "tValue": None, "pValue": None, "significant": None,
        "roi": None, "contribution": None, "roiBasis": "",
        "roiRange": "", "contributionRange": "",
        "rangeSource": "", "roiStatus": "none", "contributionStatus": "none",
        "objects": [], "results": [],
    }


def build_ols_review(st: ProjectState, *, fit: bool = True, eng=None,
                     task_id: str | None = None) -> tuple[dict, dict, list[dict]]:
    """Build the 2.5 artifact body, the prefit analysis map, and the flagged list.

    Args:
        fit: when False, skip the regression and return the **setup state** — the
            proposal is rendered but nothing is fitted yet (2.5 proposes; 2.5r
            fits once the human has confirmed Y / X / parameters).
        eng, task_id: supplied by the 2.5r handler so each object's regression is
            recorded as an explicit ``model.ols`` tool invocation.

    Returns ``(body, prefit, flagged)`` where ``body`` is the ``olsTree`` artifact,
    ``prefit[obj] = {r2, mape, baseline_pct, red_flags}``, and ``flagged`` is a list
    of ``{l4, indicator, reason}`` for every row needing human review.
    """
    cfg = getattr(st, "ols_config", None)
    # One resolved selection — the same one 2.6 and 3.2 fit on, so what the tree
    # shows as in-model is exactly what the master table and training will carry.
    sel = model_selection(st)
    # Where each rejected indicator died, for the tree's `droppedBy` column.
    # Keyed by (object, key): a rejection at a per-object layer (quality,
    # statistical, selection) only applies to that channel, so the same
    # indicator can be dropped in one channel and adopted in another.
    # OBJECT_ANY holds the still-global layers (mapping, sign-off) and the
    # ledger rows for indicators excluded before they ever reach a channel's
    # own driver universe.
    rejected_by = {(r.object, r.key): r.rejected_at for r in indicator_ledger(st) if not r.adopted}
    if not fit:
        # Setup state — the proposal is on the config; nothing is fitted yet.
        body = {
            "objects": [], "tree": [],
            "summary": {"total": 0, "inModel": 0, "inRange": 0, "flagged": 0,
                        "noBenchmark": 0, "notInModel": 0, "dropped": 0, "notMapped": 0},
            "setup": _setup_section(cfg, []),
            "note": ("Setup proposed. Confirm the response (Y), review the model variables (X) "
                     "and the model settings in the steps above — the regression runs once "
                     "they are confirmed."),
        }
        return body, {}, []
    objects, prefit, records = _collect_records(st, sel, cfg, eng=eng, task_id=task_id)

    industry = getattr(getattr(st, "meta", None), "industry", None)
    idx = build_range_index(getattr(industry, "l1", None), getattr(industry, "l2", None))

    consumed: set[tuple[str, str, str]] = set()
    tree: list[dict] = []
    fmap = resolve_factor_map(st)
    objects_list = model_objects(st) or [OBJECT_ANY]

    # One tree row per (object, factor-row): each channel screens its own
    # driver universe (Task 5), so a factor can be in-model in one channel and
    # dropped in another — the tree must show both, not one averaged verdict.
    for fm in fmap.rows:
        l4n = _norm(fm.l4)
        cand_names = {_norm(fm.metric), _norm(fm.indicator)}
        for obj in objects_list:
            # Match this object's own model record by the covering metric
            # label, then the indicator label.
            rec = None
            for name in (fm.metric, fm.indicator):
                if not name:
                    continue
                k = (obj, l4n, _norm(name))
                if k in records:
                    rec = records[k]
                    consumed.add(k)
                    break
            # droppedBy — the layer that rejected this indicator for this
            # object, tested against every name it might be keyed under; falls
            # back to OBJECT_ANY for the still-global layers.
            names = set(cand_names)
            if rec:
                names.add(_norm(rec["metric"]))
            dropped_by = next(
                (rejected_by[(obj, (l4n, n))] for n in names
                 if n and (obj, (l4n, n)) in rejected_by), "") or next(
                (rejected_by[(OBJECT_ANY, (l4n, n))] for n in names
                 if n and (OBJECT_ANY, (l4n, n)) in rejected_by), "")

            bench = idx.match(fm.l4, fm.metric or fm.indicator)
            base = _row_from_record(rec, bench) if rec else {**_empty_row_fields(),
                                                              "roiRange": bench.roi_text if bench else "",
                                                              "contributionRange": bench.contribution_text if bench else "",
                                                              "rangeSource": bench.source if bench else ""}
            in_model = rec is not None
            status, reason = _classify(base, dropped_by, in_model, bench)
            tree.append({
                "key": f"{obj}|{l4n}|{_norm(fm.metric or fm.indicator)}",
                "object": obj,
                "treeRowId": fm.row_id,
                "l1": fm.l1, "l2": fm.l2, "l3": fm.l3, "l4": fm.l4,
                "indicator": fm.indicator or fm.metric,
                "mapped": fm.status == "mapped", "inModel": in_model,
                "droppedBy": dropped_by,
                **base, "status": status, "flagReason": reason,
            })

    # Model records not tied to any active factor row → surface so nothing is hidden.
    for key, rec in records.items():
        if key in consumed:
            continue
        obj, l4n, metricn = key
        bench = idx.match(rec["l4"], rec["metric"])
        base = _row_from_record(rec, bench)
        status, reason = _classify(base, "", True, bench)
        tree.append({
            "key": f"{obj}|{l4n}|{metricn}", "object": obj, "treeRowId": "",
            "l1": rec["l1"], "l2": rec["l2"], "l3": rec["l3"], "l4": rec["l4"],
            "indicator": rec["metric"], "mapped": False, "inModel": True,
            "droppedBy": "",
            **base, "status": status, "flagReason": reason,
        })

    tree.sort(key=lambda r: (r["l1"], r["l2"], r["l3"], r["l4"], r["indicator"], r["object"]))

    # Counts are over tree rows, and every row is now (object, factor) — with
    # more than one model object the totals scale by the object count; that is
    # honest, not a bug, since each channel's own verdict is now a separate row.
    summary = {
        "total": len(tree),
        "inModel": sum(1 for r in tree if r["inModel"]),
        "inRange": sum(1 for r in tree if r["status"] == "inRange"),
        "flagged": sum(1 for r in tree if r["status"] == "review"),
        "noBenchmark": sum(1 for r in tree if r["status"] == "noBenchmark"),
        "notInModel": sum(1 for r in tree if r["status"] == "notInModel"),
        "dropped": sum(1 for r in tree if r["status"] == "dropped"),
        "notMapped": sum(1 for r in tree if r["status"] == "notMapped"),
    }
    note = ("OLS fit per model object on the confirmed setup — the response, the model "
            "variables and the transform/control settings you approved in the steps above. "
            "Each row is one factor's verdict in one model object (channel), so counts "
            "scale with the number of objects. Contribution is each variable's share of "
            "actual sales; trend and seasonality "
            "controls fold into the baseline. Benchmarks come from the industry Knowledge "
            "pack (reference rule library as fallback); ROI is only range-checked when it "
            "is a revenue/spend ratio.")
    body = {"objects": objects, "tree": tree, "summary": summary,
            "setup": _setup_section(cfg, objects), "note": note,
            # Populated by the 2.5 handler after the search runs — the per-factor
            # trial record and the AI's benchmark reading both live on the artifact
            # rather than only in `st.analysis`, so what the reviewer sees at the
            # d-2.5 gate is the same object that was produced.
            "search": None}
    # `object` rides along so the d-2.5 gate can freeze the drop per channel
    # (`ledger.freeze_range_drops`) — the same indicator can be out of range in
    # one channel and fine in another (Task 5's per-object screening).
    flagged = [{"l4": r["l4"], "indicator": r["indicator"], "reason": r["flagReason"],
               "object": r["object"]}
               for r in tree if r["status"] == "review"]
    return body, prefit, flagged


def _setup_section(cfg: OlsConfig | None, objects: list[dict]) -> dict:
    """The confirmed setup as rendered on the artifact (Y / X counts / params / unit)."""
    roi_unit = next((str(o.get("roiUnit") or "") for o in objects if o.get("roiUnit")), "")
    if not roi_unit:
        roi_unit = "revenue/spend" if _all_money(cfg) else "volume/spend"
    return {
        "dataSource": getattr(cfg, "data_source", "") if cfg else "",
        "roiUnit": roi_unit,
        "configured": cfg is not None,
        # Ticked candidates (what the human sees). `selected_x_metrics` dedupes to
        # metric names for the fit, since build_model_frame groups by metric.
        "selectedX": sum(1 for c in cfg.x_candidates if c.selected) if cfg else 0,
        "totalX": len(cfg.x_candidates) if cfg else 0,
        "params": cfg.params.model_dump(by_alias=True) if cfg else None,
        "y": [c.model_dump(by_alias=True) for c in cfg.y] if cfg else [],
    }


def _all_money(cfg: OlsConfig | None) -> bool:
    """True when every confirmed response is monetary (or a unit price is set)."""
    if cfg is None or not cfg.y:
        return False
    if (cfg.params.price_per_unit or 0) > 0:
        return True
    return all(c.is_money for c in cfg.y)
