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
    # 2.5 is one task since the v3 revamp — the former 2.5y/2.5x/2.5p/2.5r chain
    # is gone, so both late layers rule from it. Naming a deleted task here put
    # "Denied @ Model Variables (2.5x)" badges in front of the user pointing at
    # something the blueprint no longer contains.
    ("selection", "2.5", "Model Variables"),
    ("range", "2.5", "OLS Range Check"),
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


OBJECT_ANY = "*"   # sentinel: a verdict recorded for every model object


def _obj(v: object) -> str:
    return str(v).strip() if v is not None else ""


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
    """One indicator's full lifecycle across the S2 filter layers, for one
    model object (``OBJECT_ANY`` for the layers that are still global)."""
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
    object: str = ""


@dataclass(frozen=True)
class ModelSelection:
    """The resolved model input every downstream consumer must filter on.

    ``exclude``/``include`` are keyed per model object (channel type): a
    per-object layer (quality, statistical, selection) can reach a different
    verdict per channel, so one channel's drop must never exclude an indicator
    from another channel's fit. Still-global layers (mapping, sign-off, and any
    layer that has not run yet) record under ``OBJECT_ANY``, which every object
    inherits — see :meth:`exclude_for` / :meth:`include_for`. ``y``/``params``
    map 1:1 onto ``build_model_frame`` and ``run_mmm`` arguments, so a consumer
    cannot accidentally honour some layers and skip others.
    """
    exclude: dict[str, frozenset[tuple[str, str]]] = field(default_factory=dict)
    include: dict[str, Optional[frozenset[tuple[str, str]]]] = field(default_factory=dict)
    y: dict[str, str] = field(default_factory=dict)
    params: Optional[OlsParams] = None

    def exclude_for(self, obj: str) -> frozenset[tuple[str, str]]:
        """This object's own drops, plus whatever a still-global layer dropped
        for everyone (``OBJECT_ANY``)."""
        return frozenset(self.exclude.get(obj, frozenset()) | self.exclude.get(OBJECT_ANY, frozenset()))

    def include_for(self, obj: str) -> Optional[frozenset[tuple[str, str]]]:
        """This object's own ticked set, falling back to a global one;
        ``None`` means the legacy auto-select path (no setup confirmed yet)."""
        v = self.include.get(obj)
        return v if v is not None else self.include.get(OBJECT_ANY)

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


def signoff_key(l4: object, metric: object, object: str = OBJECT_ANY) -> str:
    """The ``st.signoffs`` key for one indicator:
    ``i:<object>:<norm_l4>|<norm_metric>``.

    ``object`` is the model object (channel type) the verdict applies to;
    it defaults to ``OBJECT_ANY`` — a single "Deny" from the 2.3 deck still
    denies the indicator for every channel unless a caller explicitly names
    one. The ``i:`` prefix makes the shape self-describing instead of
    inferred from the mere presence of ``|`` — an uploaded factor/metric name
    can itself contain a ``|`` (e.g. ``"Search | Brand"``), which under the
    old bare ``"<l4>|<metric>"`` vs bare-L3 scheme was ambiguous with the
    factor shape. See :func:`_parse_signoff_key`.
    """
    a, b = _norm_pair(l4, metric)
    return f"i:{_obj(object) or OBJECT_ANY}:{a}|{b}"


def _parse_signoff_key(key: str) -> Optional[tuple[str, str, str, str]]:
    """Decode one ``st.signoffs`` key.

    Returns ``(kind, object, l4_or_l3, metric)`` — ``kind`` is ``"indicator"``
    or ``"factor"``; ``metric`` is ``""`` for a factor; ``object`` is
    ``OBJECT_ANY`` unless the key names a concrete channel. Returns ``None``
    when the key cannot be trusted (the round-trip guards below): the caller
    must treat that as "no recorded verdict", never act on a guess.

    Accepts three shapes so nothing already stored is lost:
      * ``"i:<object>:<l4>|<metric>"`` — the current shape (`signoff_key`).
      * ``"i:<l4>|<metric>"``   — pre-Task-4 shape (no object segment); reads
        as ``OBJECT_ANY``.
      * unprefixed legacy      — predates the ``i:`` prefix entirely: a bare
        ``"<l4>|<metric>"`` (has a ``|``) reads as an indicator, a bare
        ``"<l3>"`` (no ``|``) reads as a whole-factor verdict, both under
        ``OBJECT_ANY``. This is the same rule the prefix exists to replace,
        kept only so state saved before this change keeps its verdicts — a
        legacy L3 name that itself contains ``|`` is a known, accepted gap in
        that old data (today's reference dataset has none), not something
        re-parsing can resolve after the fact. Likewise an object-free legacy
        L4 that itself contains ``:`` before its ``|`` is a known, accepted
        gap — indistinguishable from the object-prefixed shape.

    There is no ``"f:"`` factor-key shape: nothing ever writes one (only the
    ``l3`` fallback in ``PUT /signoff`` exists, and it fans out to per-indicator
    ``i:`` keys rather than storing a factor-level key), so a whole-factor
    verdict only ever reaches this parser via the unprefixed-legacy path above.
    """
    if key.startswith("i:"):
        rest = key[2:]
        head, psep, tail = rest.partition("|")
        if not psep:
            return None  # malformed — an "i:" key must carry a '|'
        if ":" in head:
            # Current shape: "<object>:<l4>" before the '|'.
            obj, _, l4 = head.partition(":")
            metric = tail
            if f"i:{obj}:{l4}|{metric}" != key:
                return None
            return ("indicator", obj or OBJECT_ANY, l4, metric)
        # Pre-Task-4 shape: no object segment at all.
        l4, metric = head, tail
        if f"i:{l4}|{metric}" != key:
            return None
        return ("indicator", OBJECT_ANY, l4, metric)
    if "|" in key:
        l4, _, metric = key.partition("|")
        return ("indicator", OBJECT_ANY, l4, metric)
    return ("factor", OBJECT_ANY, key, "")


def signoff_denied(st: ProjectState) -> tuple[set[tuple[str, str]], set[str]]:
    """Everything the client denied at 2.3, split by key shape, flattened
    across every model object.

    Returns (denied_pairs, denied_l3). Only an explicit "no" rejects: a missing
    entry means "not individually reviewed", which the d-2.3 gate covers —
    treating it as a rejection would empty the model before the human ever
    opened the deck.

    This is the object-agnostic view for callers that only care whether an
    indicator was denied anywhere; see :func:`_signoff_denied_by_object` for
    the per-channel breakdown that :func:`signoff_drop_pairs_by_object` uses.
    """
    pairs: set[tuple[str, str]] = set()
    l3s: set[str] = set()
    for key, verdict in (getattr(st, "signoffs", None) or {}).items():
        if _norm(verdict) != "no":
            continue
        parsed = _parse_signoff_key(key)
        if parsed is None:
            continue  # unparseable / ambiguous key — see _parse_signoff_key
        kind, _obj_, a, b = parsed
        if kind == "indicator":
            pairs.add((_norm(a), _norm(b)))
        else:
            l3s.add(_norm(a))
    return pairs, l3s


def _signoff_denied_by_object(st: ProjectState) -> tuple[set[tuple[str, str, str]], set[tuple[str, str]]]:
    """Everything the client denied at 2.3, split by key shape, per object.

    Returns (denied_triples, denied_l3s) where a triple is
    ``(object, l4, metric)`` and an l3 entry is ``(object, l3)`` — object is
    ``OBJECT_ANY`` for a key with no explicit channel (the default: a plain
    "Deny" applies to every channel).
    """
    triples: set[tuple[str, str, str]] = set()
    l3s: set[tuple[str, str]] = set()
    for key, verdict in (getattr(st, "signoffs", None) or {}).items():
        if _norm(verdict) != "no":
            continue
        parsed = _parse_signoff_key(key)
        if parsed is None:
            continue
        kind, obj, a, b = parsed
        obj = _obj(obj) or OBJECT_ANY
        if kind == "indicator":
            triples.add((obj, _norm(a), _norm(b)))
        else:
            l3s.add((obj, _norm(a)))
    return triples, l3s


def stale_factor_keys(st: ProjectState, l3: object) -> list[str]:
    """Every ``st.signoffs`` key that resolves to a whole-factor legacy verdict
    on ``l3`` (the unprefixed bare-L3 shape; see ``_parse_signoff_key``).

    A verdict recorded at a finer grain (a single indicator, or a fresh
    whole-L3 call) must not keep being overridden by a coarser one recorded
    earlier, before sign-off became indicator-granular. See
    ``app/main.py::put_signoff``.
    """
    target = _norm(l3)
    if not target:
        return []
    out: list[str] = []
    for key in getattr(st, "signoffs", None) or {}:
        parsed = _parse_signoff_key(key)
        if parsed is not None and parsed[0] == "factor" and _norm(parsed[2]) == target:
            out.append(key)
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

    Freezes both shapes: the legacy flat ``droppedPairs`` (still read by
    :func:`range_drop_pairs`, and by anything saved before this per-object
    freeze existed) and the new per-object ``droppedPairsByObject`` (read by
    :func:`range_drop_pairs_by_object`) — each channel screens its own driver
    universe (Task 5), so the same indicator can be out-of-range in one channel
    and fine in another; freezing one flat set would drop it everywhere.
    """
    if option_id != "drop":
        return
    dec = st.decisions.get("d-2.5")
    if dec is None or not dec.resolution:
        return
    dec.resolution["droppedPairs"] = [list(p) for p in sorted(ols_flagged_pairs(st))]
    by_object: dict[str, set[tuple[str, str]]] = {}
    for f in st.analysis.get("ols_flagged") or []:
        if not isinstance(f, dict):
            continue
        obj = _obj(f.get("object")) or OBJECT_ANY
        by_object.setdefault(obj, set()).add(_norm_pair(f.get("l4", ""), f.get("indicator", "")))
    dec.resolution["droppedPairsByObject"] = {
        obj: [list(p) for p in sorted(pairs)] for obj, pairs in sorted(by_object.items())
    }


def signoff_drop_pairs(st: ProjectState) -> set[tuple[str, str]]:
    """Indicators 2.3 rejected, in the (l4, metric) key space everything filters
    on, flattened across every model object.

    Kept as a flat/global view for callers that only care whether an indicator
    was denied anywhere (``model_selection`` now reads the per-object
    breakdown directly — see :func:`signoff_drop_pairs_by_object`). Defined as
    the union of :func:`signoff_drop_pairs_by_object`, which already expands
    legacy per-L3 denials against the indicator universe.
    """
    by_obj = signoff_drop_pairs_by_object(st)
    return set().union(*by_obj.values()) if by_obj else set()


def unticked_pairs(st: ProjectState) -> set[tuple[str, str]]:
    """Candidate variables the human left unticked at 2.5x."""
    cfg: OlsConfig | None = getattr(st, "ols_config", None)
    if cfg is None or not cfg.x_candidates:
        return set()
    return {_norm_pair(c.l4, c.metric) for c in cfg.x_candidates if not c.selected}


# ── per-object variants ─────────────────────────────────────────────────────
# Each maps object (channel_type) → that channel's own drop set. Layers that
# are still global report everything under ``OBJECT_ANY``, which every object
# inherits — see ``_object_drops``.


def _scorecard_pairs_by_object(card: object, dispositions: tuple[str, ...]) -> dict[str, set[tuple[str, str]]]:
    out: dict[str, set[tuple[str, str]]] = {}
    for row in getattr(card, "rows", None) or []:
        if getattr(row, "disposition", "") in dispositions:
            out.setdefault(_obj(getattr(row, "object", "")) or OBJECT_ANY, set()).add(
                _norm_pair(row.l4, row.indicator))
    return out


def quality_drop_pairs_by_object(st: ProjectState) -> dict[str, set[tuple[str, str]]]:
    return _scorecard_pairs_by_object(getattr(st, "quality_scorecard", None), ("drop",))


def quality_flag_pairs_by_object(st: ProjectState) -> dict[str, set[tuple[str, str]]]:
    return _scorecard_pairs_by_object(getattr(st, "quality_scorecard", None), ("flag",))


def stat_drop_pairs_by_object(st: ProjectState) -> dict[str, set[tuple[str, str]]]:
    return _scorecard_pairs_by_object(getattr(st, "stat_scorecard", None), ("drop",))


def unticked_pairs_by_object(st: ProjectState) -> dict[str, set[tuple[str, str]]]:
    cfg: OlsConfig | None = getattr(st, "ols_config", None)
    out: dict[str, set[tuple[str, str]]] = {}
    for c in (getattr(cfg, "x_candidates", None) or []):
        if not c.selected:
            out.setdefault(_obj(getattr(c, "object", "")) or OBJECT_ANY, set()).add(
                _norm_pair(c.l4, c.metric))
    return out


def mapping_ignored_by_object(st: ProjectState) -> dict[str, set[tuple[str, str]]]:
    # Mapping is global — one ignore applies to every object.
    return {OBJECT_ANY: set(_mapping_ignored(st))}


def signoff_drop_pairs_by_object(st: ProjectState) -> dict[str, set[tuple[str, str]]]:
    """Per-object breakdown of what 2.3 denied, keyed by model object.

    A denial recorded under ``OBJECT_ANY`` (the default — see
    :func:`signoff_key`) belongs to every channel; ``_object_drops`` is what
    merges that bucket into a concrete object's own. Legacy per-L3 denials are
    expanded against the (still object-agnostic) indicator universe, same as
    the old flat ``signoff_drop_pairs``.
    """
    triples, l3s = _signoff_denied_by_object(st)
    out: dict[str, set[tuple[str, str]]] = {}
    for obj, l4, metric in triples:
        out.setdefault(obj, set()).add((l4, metric))
    if l3s:
        uni = _universe(st)
        for obj, l3 in l3s:
            out.setdefault(obj, set()).update(
                key for key, c in uni.items() if _norm(c.get("l3")) == l3)
    return out


def range_drop_pairs_by_object(st: ProjectState) -> dict[str, set[tuple[str, str]]]:
    """Per-object breakdown of what the human dropped at the ``d-2.5`` range gate.

    Read from ``droppedPairsByObject``, frozen by :func:`freeze_range_drops` at
    the moment the gate was answered. Falls back to the legacy flat
    ``droppedPairs`` (via :func:`range_drop_pairs`), applied under
    ``OBJECT_ANY`` so every object still inherits it, for resolutions frozen
    before this per-object shape existed.
    """
    dec = st.decisions.get("d-2.5")
    res = (dec.resolution or {}) if dec else {}
    if res.get("optionId") != "drop":
        return {}
    frozen = res.get("droppedPairsByObject")
    if frozen is None:
        return {OBJECT_ANY: range_drop_pairs(st)}
    out: dict[str, set[tuple[str, str]]] = {}
    for obj, pairs in frozen.items():
        out[_obj(obj) or OBJECT_ANY] = {
            (_norm(p[0]), _norm(p[1])) for p in pairs
            if isinstance(p, (list, tuple)) and len(p) == 2
        }
    return out


# Each layer's own rejection set, in its own key space.
_LAYER_PAIRS = {
    "mapping": lambda st: set(_mapping_ignored(st)),
    "quality": quality_drop_pairs,
    "signoff": signoff_drop_pairs,
    "statistical": stat_drop_pairs,
    "selection": unticked_pairs,
    "range": range_drop_pairs,
}

# Object-aware counterpart of ``_LAYER_PAIRS`` — same keys, each resolver
# returns a per-object mapping instead of one flat set.
_LAYER_PAIRS_BY_OBJECT = {
    "mapping": mapping_ignored_by_object,
    "quality": quality_drop_pairs_by_object,
    "signoff": signoff_drop_pairs_by_object,
    "statistical": stat_drop_pairs_by_object,
    "selection": unticked_pairs_by_object,
    "range": range_drop_pairs_by_object,
}


def _object_drops(by_object: dict[str, set[tuple[str, str]]], object: str | None) -> set[tuple[str, str]]:
    """The drop set that applies to ``object`` (``None`` → union of everything)."""
    if object is None:
        return set().union(*by_object.values()) if by_object else set()
    return set(by_object.get(OBJECT_ANY, set())) | set(by_object.get(object, set()))


def drops_before(st: ProjectState, layer: str, object: str | None = None) -> set[tuple[str, str]]:
    """Indicators already rejected by a layer that rules *before* ``layer``.

    Always reach for this instead of hand-unioning drop sets at a call site: a
    layer must inherit every earlier verdict, and must never inherit its own —
    that would stop the human from revising the call they just made.

    ``object=None`` keeps the legacy global-union behaviour (every un-migrated
    caller). Passing a concrete model object narrows each layer's drop set to
    that channel's own verdicts plus whatever a still-global layer rejected
    for everyone (``OBJECT_ANY``).
    """
    order = [lid for lid, _task, _label in LAYERS]
    if layer not in order:
        raise ValueError(f"unknown layer {layer!r}; expected one of {order}")
    out: set[tuple[str, str]] = set()
    for lid in order[:order.index(layer)]:
        out |= _object_drops(_LAYER_PAIRS_BY_OBJECT[lid](st), object)
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
    """Every indicator that could enter a model, from the modeling long table.

    Keyed on the true ``(l4, metric)`` combination via
    :func:`~app.mmm.driver_candidates_by_l4` — **not** the plain
    ``driver_candidates``, which collapses to one row per metric with an
    arbitrary L4 (``g["l4"].iloc[0]``) and so silently disagrees with every
    other layer's key space (the scorecards, the per-indicator sign-off,
    `build_model_frame`'s own per-row exclude).
    """
    from app.agents.dataset_cache import model_df, model_objects
    from app.mmm import driver_candidates_by_l4

    pid = getattr(st, "project_id", None) or ""
    cached = _UNIVERSE_CACHE.get(pid)
    if cached is not None:
        return cached

    try:
        df = model_df(st)
        objects = model_objects(st)
    except Exception:  # noqa: BLE001 — no bound data yet; the ledger is simply empty
        return {}

    from app.agents.vocabulary import vocab_for
    vocab = vocab_for(st)
    universe: dict[tuple[str, str], dict] = {}
    for obj in objects:
        try:
            cands = driver_candidates_by_l4(df, obj, vocab)
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
    """Resolve every indicator's lifecycle across the six S2 filter layers,
    independently per model object (channel type).

    Layers rule in order; the first rejection wins and every later layer records
    ``inherited`` rather than ruling again. That inheritance is the whole point:
    it is what stops a 2.2-dropped indicator from being re-scored at 2.4, from
    being re-offered at 2.5x, and from re-entering the master table at 2.6. A
    layer that is still global (mapping, sign-off) rules the same for every
    object via ``OBJECT_ANY``; a layer that is per-object (quality,
    statistical, selection, range) can reach a different verdict per channel —
    the same indicator can die in one channel and survive in another.
    """
    from app.agents.dataset_cache import model_objects

    universe = _universe(st)
    ignored = _mapping_ignored(st)
    q_drop_o = quality_drop_pairs_by_object(st)
    q_flag_o = quality_flag_pairs_by_object(st)
    sign_o = signoff_drop_pairs_by_object(st)
    s_drop_o = stat_drop_pairs_by_object(st)
    tick_o = unticked_pairs_by_object(st)
    range_o = range_drop_pairs_by_object(st)
    flagged = ols_flagged_pairs(st)  # flags stay global display-only for now

    objects = model_objects(st) or [OBJECT_ANY]

    cfg: OlsConfig | None = getattr(st, "ols_config", None)

    rows: list[LedgerRow] = []
    for obj in objects:
        q_drop = _object_drops(q_drop_o, obj)
        q_flag = _object_drops(q_flag_o, obj)
        sign_drop = _object_drops(sign_o, obj)
        s_drop = _object_drops(s_drop_o, obj)
        r_drop = _object_drops(range_o, obj)
        # 2.5x rules only once a candidate exists for this object.
        unticked_here = _object_drops(tick_o, obj)
        offered: set[tuple[str, str]] = set()
        if cfg is not None and cfg.x_candidates:
            for c in cfg.x_candidates:
                if (_obj(getattr(c, "object", "")) or OBJECT_ANY) in (OBJECT_ANY, obj):
                    offered.add(_norm_pair(c.l4, c.metric))

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

            # 2.1 — mapped into the long table, or explicitly ignored (global).
            if _matches(key, set(ignored)):
                rule("mapping", STATUS_REJECTED,
                     ignored.get(key) or "Ignored in the FactorTree↔DataAssets mapping.")
            else:
                rule("mapping", STATUS_ADOPTED, "Mapped to a published data asset.")

            # 2.2d — quality verdict, this object's own scorecard rows.
            if _matches(key, q_drop):
                rule("quality", STATUS_REJECTED, "Dropped in the data-quality review (unusable).")
            elif _matches(key, q_flag):
                rule("quality", STATUS_FLAGGED, "Borderline quality — kept with a caveat.")
            else:
                rule("quality", STATUS_ADOPTED, "Passed the data-quality review.")

            # 2.3 — the client's business-validation sign-off, per indicator (or,
            # for legacy keys, per L3 factor). Still global until Task 4.
            if _matches(key, sign_drop):
                rule("signoff", STATUS_REJECTED,
                     f"Not signed off by the client at Business Validation ({c.get('indicator', key[1])}).")
            else:
                rule("signoff", STATUS_ADOPTED, "Covered by the business-validation sign-off.")

            # 2.4d — statistical screening, this object's own scorecard rows.
            if _matches(key, s_drop):
                rule("statistical", STATUS_REJECTED, "Dropped in the statistical screening.")
            else:
                rule("statistical", STATUS_ADOPTED, "Passed the statistical screening.")

            # 2.5x — the human's model-variable selection, this object's own
            # candidate list.
            if key in offered:
                if _matches(key, unticked_here):
                    rule("selection", STATUS_REJECTED, "Not ticked as a model variable.")
                else:
                    rule("selection", STATUS_ADOPTED, "Ticked as a model variable.")
            else:
                rule("selection", STATUS_PENDING, "The model setup has not been proposed yet.")

            # 2.5r — the ROI / contribution range check, this object's own frozen drops.
            if _matches(key, r_drop):
                rule("range", STATUS_REJECTED,
                     "Outside its knowledge-base ROI / contribution band; dropped at the d-2.5 gate.")
            elif _matches(key, flagged):
                rule("range", STATUS_FLAGGED,
                     "Outside its knowledge-base ROI / contribution band; kept for review.")
            else:
                rule("range", STATUS_ADOPTED, "Within its expected range (or no benchmark).")

            rows.append(LedgerRow(
                key=key, object=obj, l1=c.get("l1", ""), l2=c.get("l2", ""), l3=c.get("l3", ""),
                l4=c.get("l4", ""), indicator=c.get("metric", ""), metric=c.get("metric", ""),
                verdicts=tuple(verdicts), adopted=not rejected_at,
                rejected_at=rejected_at, reason=reason,
            ))

    # Factor-tree rows the human ignored at 2.1 never reach the long table, so
    # they are absent from the universe. Surface them anyway — "I ignored it" is
    # a lifecycle answer, and silently omitting them is what makes the funnel lie.
    # Mapping is global, so these are emitted once, under OBJECT_ANY.
    known = {r.key for r in rows}
    for key, note in sorted(ignored.items()):
        if key in known:
            continue
        rows.append(LedgerRow(
            key=key, object=OBJECT_ANY, l1="", l2="", l3="", l4=key[0], indicator=key[1], metric=key[1],
            verdicts=(LayerVerdict("mapping", "2.1", LAYER_LABEL["mapping"], STATUS_REJECTED,
                                   note or "Ignored in the FactorTree↔DataAssets mapping."),),
            adopted=False, rejected_at="mapping",
            reason=note or "Ignored in the FactorTree↔DataAssets mapping.",
        ))
        known.add(key)

    # C1 belt-and-braces: a sign-off denial the (still-imperfect) driver
    # universe never carried at all — real enough for the client to deny at
    # 2.3, but absent from `_universe`'s own predicate. `model_selection`
    # already excludes it directly (see above); surface it here too so the
    # funnel and the canvas do not silently disagree with the fit. Sign-off is
    # still global, so these too are emitted once, under OBJECT_ANY.
    sign_drop_all = _object_drops(sign_o, None)
    for key in sorted(sign_drop_all):
        if key in known:
            continue
        l4, metric = key
        rows.append(LedgerRow(
            key=key, object=OBJECT_ANY, l1="", l2="", l3="", l4=l4, indicator=metric, metric=metric,
            verdicts=(LayerVerdict("signoff", LAYER_TASK["signoff"], LAYER_LABEL["signoff"],
                                   STATUS_REJECTED,
                                   f"Not signed off by the client at Business Validation ({metric})."),),
            adopted=False, rejected_at="signoff",
            reason=f"Not signed off by the client at Business Validation ({metric}).",
        ))
        known.add(key)
    return tuple(rows)


def adopted_pairs(st: ProjectState, object: str | None = None) -> frozenset[tuple[str, str]]:
    """Adopted (l4, metric) pairs — every object, or one object's own verdicts
    (plus whatever a still-global layer rejected for everyone)."""
    return frozenset(r.key for r in indicator_ledger(st)
                     if r.adopted and (object is None or r.object in (object, OBJECT_ANY)))


def rejected_pairs(st: ProjectState, object: str | None = None) -> frozenset[tuple[str, str]]:
    """Rejected (l4, metric) pairs — every object, or one object's own verdicts
    (plus whatever a still-global layer rejected for everyone)."""
    return frozenset(r.key for r in indicator_ledger(st)
                     if not r.adopted and (object is None or r.object in (object, OBJECT_ANY)))


def model_selection(st: ProjectState, *, cfg: OlsConfig | None = None) -> ModelSelection:
    """The one resolved selection every downstream fit must use.

    ``exclude``/``include`` are resolved per model object: a per-object layer
    (quality, statistical, selection) can drop or keep an indicator in one
    channel without touching another, so the same key can be excluded from
    one object's fit and included in another's. ``include_for(obj)`` stays
    ``None`` until 2.5 has proposed a setup — that is the legacy auto-select
    path, which keeps reference/demo projects (and any project that has not
    reached 2.5) fitting exactly as before.

    ``cfg`` scores a **hypothetical** configuration without persisting it — the
    2.5 indicator search needs to price dozens of candidate assignments, and it
    used to do that by writing each one to ``st.ols_config`` and leaving it there.
    The trial config is swapped in for the duration of the derivation (the ledger's
    selection layer reads it too, so the two must agree) and always swapped back,
    including on an exception. Omit it — the only call shape every downstream
    consumer uses — and the project's own saved config is read, exactly as before.
    """
    if cfg is not None:
        saved = getattr(st, "ols_config", None)
        try:
            st.ols_config = cfg
            return model_selection(st)
        finally:
            st.ols_config = saved

    from app.agents.dataset_cache import model_objects

    ledger = indicator_ledger(st)
    cfg = getattr(st, "ols_config", None)

    exclude: dict[str, frozenset[tuple[str, str]]] = {}
    include: dict[str, Optional[frozenset[str]]] = {}
    for obj in (model_objects(st) or [OBJECT_ANY]):
        # This object's own ledger rows, plus whatever a still-global layer
        # (mapping, sign-off) rejected for everyone (OBJECT_ANY rows).
        obj_rows = [r for r in ledger if r.object in (obj, OBJECT_ANY)]
        adopted = {r.key for r in obj_rows if r.adopted}
        # The scorecards (and sign-off) are unioned in directly as well as via
        # the ledger: they can name a pair the current long table no longer
        # carries — or, for sign-off, a pair the (still-imperfect) driver
        # universe never carried at all (C1) — and an exclude entry for an
        # absent indicator is free.
        exclude[obj] = frozenset(
            {r.key for r in obj_rows if not r.adopted}
            | _object_drops(quality_drop_pairs_by_object(st), obj)
            | _object_drops(stat_drop_pairs_by_object(st), obj)
            | _object_drops(signoff_drop_pairs_by_object(st), obj)
        )
        if cfg is not None and cfg.x_candidates:
            # A tick only counts if the indicator is still adopted for THIS
            # object — a stale config must never resurrect what a later
            # review rejected, and one channel's tick must never leak into
            # another's fit.
            # Keyed by (norm_l4, norm_metric) — the same key space as `exclude`,
            # the scorecards and the ledger. Ticking a metric name alone used to
            # keep every L4 that shared the label.
            include[obj] = frozenset(
                _norm_pair(c.l4, c.metric) for c in cfg.x_candidates
                if c.selected
                and (_obj(getattr(c, "object", "")) or OBJECT_ANY) in (OBJECT_ANY, obj)
                and _norm_pair(c.l4, c.metric) in adopted
            )
        else:
            include[obj] = None

    y: dict[str, str] = {}
    params: OlsParams | None = None
    if cfg is not None:
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


def funnel(st: ProjectState) -> dict:
    """Per-layer intake → survivors, with the rejected labels behind each drop —
    resolved once per model object, plus a combined rollup over every object.

    This is the 2.6 filter funnel: each layer reports what reached it, what it
    rejected, and exactly which indicators those were. Returns
    ``{"combined": [...], "byObject": {object: [...]}}``: ``combined`` mirrors
    the pre-per-object shape (one funnel over every row, any object), while
    ``byObject`` is each channel's own funnel — the same indicator can die at a
    different layer, or survive, in a different channel.
    """
    from app.agents.dataset_cache import model_objects

    ledger = indicator_ledger(st)

    def _for(rows: list[LedgerRow]) -> list[dict]:
        out: list[dict] = []
        remaining = len(rows)
        for lid, task, label in LAYERS:
            killed = [r for r in rows if r.rejected_at == lid]
            out.append({
                "layer": lid, "task": task, "label": label,
                "intake": remaining, "rejected": len(killed),
                "survivors": remaining - len(killed),
                "dropped": [{"l4": r.l4, "indicator": r.indicator, "reason": r.reason}
                            for r in killed],
            })
            remaining -= len(killed)
        return out

    per_object = {obj: _for([r for r in ledger if r.object in (obj, OBJECT_ANY)])
                  for obj in (model_objects(st) or [OBJECT_ANY])}
    return {"combined": _for(list(ledger)), "byObject": per_object}
