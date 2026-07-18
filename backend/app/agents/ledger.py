"""Indicator lifecycle ledger — S2's single derived truth about which factor-tree
indicators reach the model, and where the rejected ones died.

Every S2 layer already records its verdict in its own place: the factor map
(2.1), the quality scorecard (2.2d), the per-factor sign-offs (2.3), the
statistical scorecard (2.4d), the OLS config's ticked variables (2.5x) and the
``d-2.5`` range gate (2.5r). Nothing here adds new state — the ledger *derives*
each indicator's lifecycle from those records so that:

* a rejection at any layer is **inherited** by every later layer (a dropped
  indicator is never re-scored, never re-offered, never silently re-enters), and
* every downstream consumer — 2.5r's fit, 2.6's master table, 3.2's training —
  filters on one resolved :class:`ModelSelection` instead of each re-deriving
  its own (which is exactly how 3.2 came to train on unfiltered data).

The ledger is also the UI's answer to "why is this indicator not in my model?":
every row carries the full chain of per-layer verdicts, not just the outcome.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.domain.models import OlsCapWindow, OlsConfig, OlsEvent, OlsParams
from app.store.state import ProjectState

# ── layers, in the order they rule ──────────────────────────────────────────
# id, the task that rules, the human label.
LAYERS: tuple[tuple[str, str, str], ...] = (
    ("mapping", "2.1", "Data Processing"),
    ("quality", "2.2d", "Data Quality"),
    ("signoff", "2.3", "Business Validation"),
    ("statistical", "2.4d", "Statistical Score"),
    ("selection", "2.5x", "Model Variables"),
    ("range", "2.5r", "OLS Range Check"),
)
LAYER_LABEL = {lid: label for lid, _task, label in LAYERS}
LAYER_TASK = {lid: task for lid, task, _label in LAYERS}

# Per-layer status vocabulary:
#   adopted    — this layer passed the indicator through
#   rejected   — this layer is where the indicator died
#   flagged    — passed, but carrying a caveat (0.5 quality / out-of-range ROI)
#   pending    — this layer has not ruled yet
#   inherited  — an earlier layer already rejected it; this layer never ruled
STATUS_REJECTED = "rejected"
STATUS_ADOPTED = "adopted"
STATUS_FLAGGED = "flagged"
STATUS_PENDING = "pending"
STATUS_INHERITED = "inherited"


def _norm(s: object) -> str:
    return str(s).strip().lower() if s is not None else ""


def _norm_pair(l4: object, metric: object) -> tuple[str, str]:
    """The canonical indicator key: ``(norm_l4, norm_metric)``.

    Deliberately ``l4``-only, with no l3/l1 fallback: this is the key space
    ``build_model_frame`` excludes on and the one both scorecards already write.
    A key built on a fallback would look right and silently fail to exclude
    anything whose L4 is blank.
    """
    return (_norm(l4), _norm(metric))


def _matches(key: tuple[str, str], pairs: set[tuple[str, str]]) -> bool:
    """Mirror ``build_model_frame``'s exclude semantics: an exact (l4, metric)
    hit, or a metric-only entry (empty l4) that drops the metric under any L4.

    Keeping this rule in one place matters — the scorecards key their rows on
    the row's own (possibly empty) l4 while the driver universe falls back to
    l3/l1, so a plain set-membership test silently misses rows.
    """
    if key in pairs:
        return True
    metric = key[1]
    return any(not l4 and m == metric for l4, m in pairs)


@dataclass(frozen=True)
class LayerVerdict:
    """One layer's ruling on one indicator."""
    layer: str
    task: str
    label: str
    status: str
    note: str = ""


@dataclass(frozen=True)
class LedgerRow:
    """One indicator's full lifecycle across the S2 filter layers."""
    key: tuple[str, str]
    l1: str
    l2: str
    l3: str
    l4: str
    indicator: str
    metric: str
    verdicts: tuple[LayerVerdict, ...]
    adopted: bool
    rejected_at: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ModelSelection:
    """The resolved model input every downstream consumer must filter on.

    ``exclude``/``include``/``y``/``params`` map 1:1 onto ``build_model_frame``
    and ``run_mmm`` arguments, so a consumer cannot accidentally honour some
    layers and skip others.
    """
    exclude: frozenset[tuple[str, str]] = frozenset()
    include: Optional[frozenset[str]] = None
    y: dict[str, str] = field(default_factory=dict)
    params: Optional[OlsParams] = None

    def y_for(self, obj: str) -> Optional[str]:
        return self.y.get(obj) or None


# ── per-layer verdict resolvers ─────────────────────────────────────────────


def _scorecard_pairs(card: object, dispositions: tuple[str, ...]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for row in getattr(card, "rows", None) or []:
        if getattr(row, "disposition", "") in dispositions:
            out.add(_norm_pair(row.l4, row.indicator))
    return out


def quality_drop_pairs(st: ProjectState) -> set[tuple[str, str]]:
    return _scorecard_pairs(getattr(st, "quality_scorecard", None), ("drop",))


def quality_flag_pairs(st: ProjectState) -> set[tuple[str, str]]:
    return _scorecard_pairs(getattr(st, "quality_scorecard", None), ("flag",))


def stat_drop_pairs(st: ProjectState) -> set[tuple[str, str]]:
    return _scorecard_pairs(getattr(st, "stat_scorecard", None), ("drop",))


def signoff_reject_l3(st: ProjectState) -> set[str]:
    """L3 factors the client explicitly did **not** sign off at 2.3.

    Only an explicit ``no`` rejects: a blank sign-off means "not individually
    reviewed", which the global ``d-2.3`` gate covers. Treating blank as a
    rejection would empty the model before the human ever opened the deck.
    """
    art = next((a for a in st.artifacts if a.id == "a-business-validation"), None)
    body = getattr(art, "body", None) or {}
    out: set[str] = set()
    for g in body.get("groups") or []:
        if isinstance(g, dict) and _norm(g.get("signoff")) == "no":
            out.add(_norm(g.get("l3")))
    return out


def ols_flagged_pairs(st: ProjectState) -> set[tuple[str, str]]:
    """Indicators 2.5r found outside their knowledge-base ROI / contribution band."""
    out: set[tuple[str, str]] = set()
    for f in st.analysis.get("ols_flagged") or []:
        if isinstance(f, dict):
            out.add(_norm_pair(f.get("l4", ""), f.get("indicator", "")))
    return out


def range_gate_drops(st: ProjectState) -> bool:
    """True when the human resolved ``d-2.5`` by dropping the flagged indicators."""
    dec = st.decisions.get("d-2.5")
    opt = (dec.resolution or {}).get("optionId") if dec and dec.resolution else None
    return opt == "drop"


def range_drop_pairs(st: ProjectState) -> set[tuple[str, str]]:
    """Indicators the human dropped at the ``d-2.5`` range gate.

    Read from the pairs frozen into the decision's own resolution when the gate
    was answered — **not** re-derived from ``analysis['ols_flagged']``. Once
    these indicators are excluded, the next re-fit has no records for them, so
    they stop being flagged; a live re-derivation would read that empty list as
    "nothing was out of range" and quietly walk them back into the model.
    """
    dec = st.decisions.get("d-2.5")
    res = (dec.resolution or {}) if dec else {}
    if res.get("optionId") != "drop":
        return set()
    frozen = res.get("droppedPairs")
    if frozen is None:
        # Resolved before the freeze existed — fall back to the live flags.
        return ols_flagged_pairs(st)
    return {(_norm(p[0]), _norm(p[1])) for p in frozen
            if isinstance(p, (list, tuple)) and len(p) == 2}


def freeze_range_drops(st: ProjectState, option_id: str) -> None:
    """``d-2.5`` effect: pin the dropped indicators onto the resolution itself.

    Registered on the engine so it runs the instant the gate is answered, while
    ``analysis['ols_flagged']`` still describes the fit the human was looking at.
    """
    if option_id != "drop":
        return
    dec = st.decisions.get("d-2.5")
    if dec is None or not dec.resolution:
        return
    dec.resolution["droppedPairs"] = [list(p) for p in sorted(ols_flagged_pairs(st))]


def signoff_drop_pairs(st: ProjectState) -> set[tuple[str, str]]:
    """Indicator pairs under an L3 factor the client refused to sign off at 2.3.

    Sign-off rules at factor (L3) granularity, so it has to be expanded against
    the indicator universe to reach the ``(l4, metric)`` key space everything
    else filters on.
    """
    rejected_l3 = signoff_reject_l3(st)
    if not rejected_l3:
        return set()
    return {key for key, c in _universe(st).items() if _norm(c.get("l3")) in rejected_l3}


def unticked_pairs(st: ProjectState) -> set[tuple[str, str]]:
    """Candidate variables the human left unticked at 2.5x."""
    cfg: OlsConfig | None = getattr(st, "ols_config", None)
    if cfg is None or not cfg.x_candidates:
        return set()
    return {_norm_pair(c.l4, c.metric) for c in cfg.x_candidates if not c.selected}


# Each layer's own rejection set, in its own key space.
_LAYER_PAIRS = {
    "mapping": lambda st: set(_mapping_ignored(st)),
    "quality": quality_drop_pairs,
    "signoff": signoff_drop_pairs,
    "statistical": stat_drop_pairs,
    "selection": unticked_pairs,
    "range": range_drop_pairs,
}


def drops_before(st: ProjectState, layer: str) -> set[tuple[str, str]]:
    """Indicators already rejected by a layer that rules *before* ``layer``.

    Always reach for this instead of hand-unioning drop sets at a call site: a
    layer must inherit every earlier verdict, and must never inherit its own —
    that would stop the human from revising the call they just made.
    """
    order = [lid for lid, _task, _label in LAYERS]
    if layer not in order:
        raise ValueError(f"unknown layer {layer!r}; expected one of {order}")
    out: set[tuple[str, str]] = set()
    for lid in order[:order.index(layer)]:
        out |= _LAYER_PAIRS[lid](st)
    return out


def upstream_drop_pairs(st: ProjectState) -> set[tuple[str, str]]:
    """Everything already rejected before the 2.5 model-variable selection:
    2.1 mapping ∪ 2.2 quality ∪ 2.3 sign-off ∪ 2.4 statistical screening.

    This is what the 2.5 X-candidate proposal must treat as already decided — it
    still *shows* these indicators, but never as selectable.
    """
    return drops_before(st, "selection")


# ── the ledger ──────────────────────────────────────────────────────────────


# The indicator universe depends only on the project's long table, never on any
# verdict — so it survives every scorecard edit and is worth caching. The ledger
# is resolved on nearly every S2 call (and once per row inside some of them);
# rebuilding it each time means a full driver scan per model object.
_UNIVERSE_CACHE: dict[str, dict[tuple[str, str], dict]] = {}


def invalidate_universe(project_id: str | None = None) -> None:
    """Drop the cached indicator universe — call when a project's data changes."""
    if project_id is None:
        _UNIVERSE_CACHE.clear()
    else:
        _UNIVERSE_CACHE.pop(project_id, None)


def _universe(st: ProjectState) -> dict[tuple[str, str], dict]:
    """Every indicator that could enter a model, from the modeling long table."""
    from app.agents.dataset_cache import model_df, model_objects
    from app.mmm import driver_candidates

    pid = getattr(st, "project_id", None) or ""
    cached = _UNIVERSE_CACHE.get(pid)
    if cached is not None:
        return cached

    try:
        df = model_df(st)
        objects = model_objects(st)
    except Exception:  # noqa: BLE001 — no bound data yet; the ledger is simply empty
        return {}

    universe: dict[tuple[str, str], dict] = {}
    for obj in objects:
        try:
            cands = driver_candidates(df, obj)
        except Exception:  # noqa: BLE001
            continue
        for c in cands:
            universe.setdefault(_norm_pair(c["l4"], c["metric"]), c)
    if pid:
        _UNIVERSE_CACHE[pid] = universe
    return universe


def _mapping_ignored(st: ProjectState) -> dict[tuple[str, str], str]:
    """Factor-tree rows the human explicitly ignored at 2.1, keyed like the universe."""
    try:
        from app.dataeng.mapping import resolve_factor_map
        fm = resolve_factor_map(st)
    except Exception:  # noqa: BLE001
        return {}
    out: dict[tuple[str, str], str] = {}
    for r in getattr(fm, "rows", None) or []:
        if getattr(r, "status", "") == "ignored":
            out[_norm_pair(r.l4, r.indicator)] = getattr(r, "note", "") or ""
    return out


def indicator_ledger(st: ProjectState) -> tuple[LedgerRow, ...]:
    """Resolve every indicator's lifecycle across the six S2 filter layers.

    Layers rule in order; the first rejection wins and every later layer records
    ``inherited`` rather than ruling again. That inheritance is the whole point:
    it is what stops a 2.2-dropped indicator from being re-scored at 2.4, from
    being re-offered at 2.5x, and from re-entering the master table at 2.6.
    """
    universe = _universe(st)
    ignored = _mapping_ignored(st)
    q_drop, q_flag = quality_drop_pairs(st), quality_flag_pairs(st)
    no_signoff = signoff_reject_l3(st)
    s_drop = stat_drop_pairs(st)
    flagged = ols_flagged_pairs(st)
    r_drop = range_drop_pairs(st)

    cfg: OlsConfig | None = getattr(st, "ols_config", None)
    # 2.5x only rules once the setup exists; a metric absent from the candidate
    # list was never offered, so the layer stays pending for it.
    ticked: dict[tuple[str, str], bool] = {}
    if cfg is not None and cfg.x_candidates:
        for c in cfg.x_candidates:
            ticked[_norm_pair(c.l4, c.metric)] = bool(c.selected)

    rows: list[LedgerRow] = []
    for key, c in sorted(universe.items()):
        verdicts: list[LayerVerdict] = []
        rejected_at, reason = "", ""

        def rule(layer: str, status: str, note: str = "") -> None:
            nonlocal rejected_at, reason
            if rejected_at:
                verdicts.append(LayerVerdict(
                    layer, LAYER_TASK[layer], LAYER_LABEL[layer], STATUS_INHERITED,
                    f"Already rejected at {LAYER_LABEL[rejected_at]}."))
                return
            verdicts.append(LayerVerdict(layer, LAYER_TASK[layer], LAYER_LABEL[layer], status, note))
            if status == STATUS_REJECTED:
                rejected_at, reason = layer, note

        # 2.1 — mapped into the long table, or explicitly ignored.
        if _matches(key, set(ignored)):
            rule("mapping", STATUS_REJECTED,
                 ignored.get(key) or "Ignored in the FactorTree↔DataAssets mapping.")
        else:
            rule("mapping", STATUS_ADOPTED, "Mapped to a published data asset.")

        # 2.2d — quality verdict.
        if _matches(key, q_drop):
            rule("quality", STATUS_REJECTED, "Dropped in the data-quality review (unusable).")
        elif _matches(key, q_flag):
            rule("quality", STATUS_FLAGGED, "Borderline quality — kept with a caveat.")
        else:
            rule("quality", STATUS_ADOPTED, "Passed the data-quality review.")

        # 2.3 — the client's per-factor sign-off (L3 granularity).
        if _norm(c.get("l3")) in no_signoff:
            rule("signoff", STATUS_REJECTED,
                 f"Factor '{c.get('l3')}' was not signed off by the client.")
        else:
            rule("signoff", STATUS_ADOPTED, "Covered by the business-validation sign-off.")

        # 2.4d — statistical screening.
        if _matches(key, s_drop):
            rule("statistical", STATUS_REJECTED, "Dropped in the statistical screening.")
        else:
            rule("statistical", STATUS_ADOPTED, "Passed the statistical screening.")

        # 2.5x — the human's model-variable selection.
        if key in ticked:
            if ticked[key]:
                rule("selection", STATUS_ADOPTED, "Ticked as a model variable.")
            else:
                rule("selection", STATUS_REJECTED, "Not ticked as a model variable.")
        else:
            rule("selection", STATUS_PENDING, "The model setup has not been proposed yet.")

        # 2.5r — the ROI / contribution range check.
        if _matches(key, r_drop):
            rule("range", STATUS_REJECTED,
                 "Outside its knowledge-base ROI / contribution band; dropped at the d-2.5 gate.")
        elif _matches(key, flagged):
            rule("range", STATUS_FLAGGED,
                 "Outside its knowledge-base ROI / contribution band; kept for review.")
        else:
            rule("range", STATUS_ADOPTED, "Within its expected range (or no benchmark).")

        rows.append(LedgerRow(
            key=key, l1=c.get("l1", ""), l2=c.get("l2", ""), l3=c.get("l3", ""),
            l4=c.get("l4", ""), indicator=c.get("metric", ""), metric=c.get("metric", ""),
            verdicts=tuple(verdicts), adopted=not rejected_at,
            rejected_at=rejected_at, reason=reason,
        ))

    # Factor-tree rows the human ignored at 2.1 never reach the long table, so
    # they are absent from the universe. Surface them anyway — "I ignored it" is
    # a lifecycle answer, and silently omitting them is what makes the funnel lie.
    known = {r.key for r in rows}
    for key, note in sorted(ignored.items()):
        if key in known:
            continue
        rows.append(LedgerRow(
            key=key, l1="", l2="", l3="", l4=key[0], indicator=key[1], metric=key[1],
            verdicts=(LayerVerdict("mapping", "2.1", LAYER_LABEL["mapping"], STATUS_REJECTED,
                                   note or "Ignored in the FactorTree↔DataAssets mapping."),),
            adopted=False, rejected_at="mapping",
            reason=note or "Ignored in the FactorTree↔DataAssets mapping.",
        ))
    return tuple(rows)


def adopted_pairs(st: ProjectState) -> frozenset[tuple[str, str]]:
    return frozenset(r.key for r in indicator_ledger(st) if r.adopted)


def rejected_pairs(st: ProjectState) -> frozenset[tuple[str, str]]:
    return frozenset(r.key for r in indicator_ledger(st) if not r.adopted)


def model_selection(st: ProjectState) -> ModelSelection:
    """The one resolved selection every downstream fit must use.

    ``include`` stays ``None`` until 2.5 has proposed a setup — that is the
    legacy auto-select path, which keeps reference/demo projects (and any
    project that has not reached 2.5) fitting exactly as before.
    """
    ledger = indicator_ledger(st)
    # The scorecards are unioned in directly as well as via the ledger: they can
    # name a pair the current long table no longer carries, and an exclude entry
    # for an absent indicator is free.
    exclude = frozenset({r.key for r in ledger if not r.adopted}
                        | quality_drop_pairs(st) | stat_drop_pairs(st))

    cfg: OlsConfig | None = getattr(st, "ols_config", None)
    include: frozenset[str] | None = None
    y: dict[str, str] = {}
    params: OlsParams | None = None
    if cfg is not None:
        if cfg.x_candidates:
            # A tick only counts if the indicator is still adopted — a stale
            # config must never resurrect what a later review rejected.
            adopted = {r.key for r in ledger if r.adopted}
            include = frozenset(
                _norm(c.metric) for c in cfg.x_candidates
                if c.selected and _norm_pair(c.l4, c.metric) in adopted
            )
        y = {c.object: c.metric for c in cfg.y if c.metric}
        # The 2.3 anomaly handlings are folded in here rather than stored on the
        # params: the review is their source of truth, so a stale params draft
        # saved from the 2.5p panel can never silently drop one.
        events, caps = anomaly_effects(st)
        params = cfg.params.model_copy(update={"events": events, "caps": caps})
    return ModelSelection(exclude=exclude, include=include, y=y, params=params)


def anomaly_effects(st: ProjectState) -> tuple[list[OlsEvent], list[OlsCapWindow]]:
    """What the 2.3 anomaly review actually does to the fit.

    Only *accepted* cards bite, and only in the way the human chose:
      ``event`` → a dummy control over the window (the spike is absorbed as
                  business, not credited to marketing);
      ``cap``   → the response is winsorized over the window;
      ``raw``   → nothing here — it rides as a caveat on the findings.

    A pending or rejected card has no effect at all: an unreviewed hypothesis
    must never quietly reshape the model.
    """
    review = getattr(st, "anomaly_review", None)
    events: list[OlsEvent] = []
    caps: list[OlsCapWindow] = []
    for r in getattr(review, "rows", None) or []:
        if r.status != "accepted" or not r.start or not r.end:
            continue
        label = f"{r.channel} {r.year} ({r.growth_pct:+.0f}%)"
        if r.handling == "event":
            events.append(OlsEvent(id=r.id, label=label, start=r.start, end=r.end))
        elif r.handling == "cap":
            caps.append(OlsCapWindow(id=r.id, label=label, start=r.start, end=r.end))
    return events, caps


def funnel(st: ProjectState) -> list[dict]:
    """Per-layer intake → survivors, with the rejected labels behind each drop.

    This is the 2.6 filter funnel: each layer reports what reached it, what it
    rejected, and exactly which indicators those were.
    """
    ledger = indicator_ledger(st)
    out: list[dict] = []
    remaining = len(ledger)
    for lid, task, label in LAYERS:
        killed = [r for r in ledger if r.rejected_at == lid]
        out.append({
            "layer": lid, "task": task, "label": label,
            "intake": remaining, "rejected": len(killed),
            "survivors": remaining - len(killed),
            "dropped": [{"l4": r.l4, "indicator": r.indicator, "reason": r.reason}
                        for r in killed],
        })
        remaining -= len(killed)
    return out
