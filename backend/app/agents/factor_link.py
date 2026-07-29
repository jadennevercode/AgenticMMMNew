"""The bridge between a factor-tree row and the data that supplies it.

S2 has two key spaces and they had nothing joining them:

* the **factor tree** keys on a row's declared ``(l4, indicator)`` — what Business
  Understanding said it wanted to collect;
* the **data** keys on ``(l4, metric)`` — what the published assets actually
  delivered, under whatever label the source file used.

Those labels are rarely the same string. On the reference case the tree asks for
``OTV投放 · impression`` and the data delivers ``OTV · Impression``; of 123 factor
rows the human had explicitly *ignored* at 2.1, **zero** matched a data key. So
``drops_before(st, "quality")`` — the mechanism that is supposed to stop a rejected
factor from being re-scored at 2.2, re-screened at 2.4 and re-offered at 2.5 — was a
filter that never filtered anything. A factor you told the product to drop went on
being scored all the way into the model.

The join already exists in the data model and nothing was reading it: publishing
records an :class:`IndicatorCoverage` per (asset metric → factor row), so a factor
row *knows* which metric labels supply it. This module turns that into a lookup both
directions, and every S2 layer keys through it.

Ambiguity is resolved conservatively. A metric supplies at most one row (the publish
contract), but the same label can appear under two L4s, so the primary key is the
pair; a metric-only lookup is offered **only when that label is unambiguous across
the whole tree**, because guessing here silently moves a verdict onto the wrong
factor.

**Both sides of a coverage are registered, under their own L4.** A coverage records
the mart's labels *and* the factor row it supplies, and the two disagree by design —
that disagreement is the whole reason a human pins one to the other. Registering the
coverage's metric under the *factor row's* L4 therefore produces a key nothing in the
data ever uses: on the drill case the human pinned ``(站内投流, 花费)`` to the row
``电商站内投流 · 花费`` and ``(促销优惠, 花费)`` to ``买N赠N · 花费``, and the bridge
registered only the tree-side spelling, so both pins resolved to nothing. Because 50
rows of that tree declare ``花费``, the metric-only fallback declined to guess (rightly)
and the two indicators read as **orphans** — data no factor asked for — while sitting
in the model with a human's binding on them. The key a later layer filters on is the
data's, so the data's ``(l4, metric)`` must be in the map.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


def _norm(s: object) -> str:
    return str(s).strip().lower() if s is not None else ""


def _pair(l4: object, metric: object) -> tuple[str, str]:
    return (_norm(l4), _norm(metric))


# How a data key reached (or failed to reach) a factor row. The distinction is
# load-bearing: `undeclared` is an orphan the Data Engine offers to adopt, while
# `ambiguous` is data the tree *does* declare — under a label several rows share —
# and adopting it would add a duplicate of a factor that already exists.
HOW_BOUND = "bound"            # a coverage record pins this exact data key to a row
HOW_DECLARED = "declared"      # a row declares this (l4, indicator) itself
HOW_AMBIGUOUS = "ambiguous"    # the metric is declared by >1 row and no l4 matched
HOW_UNDECLARED = "undeclared"  # no row declares it and no coverage claims it


@dataclass(frozen=True)
class Resolution:
    """The outcome of looking one data key up in the bridge."""
    row_id: str
    how: str

    @property
    def orphan(self) -> bool:
        """True only for data the factor tree genuinely never asked for."""
        return self.how == HOW_UNDECLARED


@dataclass(frozen=True)
class FactorLink:
    """Two-way lookup between factor rows and the data keys that supply them."""

    row_of_pair: dict[tuple[str, str], str] = field(default_factory=dict)
    row_of_metric: dict[str, str] = field(default_factory=dict)
    keys_of_row: dict[str, frozenset[tuple[str, str]]] = field(default_factory=dict)
    meta_of_row: dict[str, dict] = field(default_factory=dict)
    # Which registration produced each `row_of_pair` entry, and every row that
    # declares a bare metric label (>1 ⇒ the metric-only fallback declines).
    how_of_pair: dict[tuple[str, str], str] = field(default_factory=dict)
    rows_of_metric: dict[str, frozenset[str]] = field(default_factory=dict)

    def resolve(self, l4: object, metric: object) -> Resolution:
        """Look one data key up, saying **how** it resolved.

        ``row_for`` collapses every miss to ``""``, which conflates "the tree never
        asked for this" with "the tree asked for it under a label this lookup could
        not reach". Reading the second as the first is what reported two
        human-pinned indicators as orphans; a caller that acts on orphanhood —
        adoption, dismissal, the 2.6 close-out — must ask this instead.
        """
        key = _pair(l4, metric)
        hit = self.row_of_pair.get(key)
        if hit:
            return Resolution(hit, self.how_of_pair.get(key, HOW_BOUND))
        sole = self.row_of_metric.get(key[1])
        if sole:
            return Resolution(sole, HOW_DECLARED)
        if len(self.rows_of_metric.get(key[1], frozenset())) > 1:
            return Resolution("", HOW_AMBIGUOUS)
        return Resolution("", HOW_UNDECLARED)

    def row_for(self, l4: object, metric: object) -> str:
        """The factor row a data indicator supplies, or "" when it supplies none.

        An indicator that maps to no row is an **orphan**: real data the tree never
        asked for. It is not an error and must not be silently attached to a
        near-miss row — 2.2 still scores it, and the Data Engine offers to adopt it
        into the tree. Use :meth:`resolve` when "" needs to be told apart from an
        ambiguous label.
        """
        return self.resolve(l4, metric).row_id

    def keys_for(self, row_id: str) -> frozenset[tuple[str, str]]:
        return self.keys_of_row.get(row_id, frozenset())

    def data_keys_for_rows(self, row_ids) -> set[tuple[str, str]]:
        """Every data key supplied by any of ``row_ids`` — how a factor-level verdict
        becomes a set the data-keyed layers can actually filter on."""
        out: set[tuple[str, str]] = set()
        for rid in row_ids:
            out |= set(self.keys_for(rid))
        return out


def build(st) -> FactorLink:
    """Resolve the bridge for a project. Never raises — a project with no factor
    tree yields an empty link, and every consumer degrades to "no factor context"."""
    try:
        from app.dataeng.mapping import resolve_factor_map
        fmap = resolve_factor_map(st)
    except Exception:  # noqa: BLE001 — no tree yet is a normal early state
        return FactorLink()

    row_of_pair: dict[tuple[str, str], str] = {}
    how_of_pair: dict[tuple[str, str], str] = {}
    keys_of_row: dict[str, set[tuple[str, str]]] = defaultdict(set)
    meta_of_row: dict[str, dict] = {}
    by_metric: dict[str, set[str]] = defaultdict(set)

    # The data-side labels, from the coverage records themselves. `FactorMapRow`
    # projects a coverage down to its `metric` and drops the mart's l1–l4, so the
    # only place the data's own L4 survives is `st.indicator_coverage` — read it
    # directly rather than widening the lossy projection and every reader of it.
    covs_by_row: dict[str, list] = defaultdict(list)
    for c in (getattr(st, "indicator_coverage", None) or []):
        if getattr(c, "tree_row_id", ""):
            covs_by_row[c.tree_row_id].append(c)

    def register(rid: str, l4: object, label: object, how: str) -> None:
        if not _norm(label):
            return
        key = _pair(l4, label)
        # First registration wins, but a `bound` key outranks a `declared` one:
        # a human pin is a statement about this exact data key, while a declared
        # name only happens to spell the same thing.
        if key not in row_of_pair or (how == HOW_BOUND and how_of_pair.get(key) != HOW_BOUND):
            row_of_pair[key] = rid
            how_of_pair[key] = how
        keys_of_row[rid].add(key)
        by_metric[_norm(label)].add(rid)

    for r in getattr(fmap, "rows", None) or []:
        rid = r.row_id
        meta_of_row[rid] = {
            "rowId": rid, "l1": r.l1, "l2": r.l2, "l3": r.l3, "l4": r.l4,
            "indicator": r.indicator, "status": r.status,
            "ignoreNote": getattr(r, "ignore_note", "") or "",
        }
        # Tree side: the row's own declared name, plus every metric label a
        # published asset claimed against it, under the row's own L4.
        labels = {r.indicator}
        labels.update(c.metric for c in (getattr(r, "coverages", None) or []) if c.metric)
        if getattr(r, "metric", ""):
            labels.add(r.metric)
        for label in labels:
            register(rid, r.l4, label, HOW_DECLARED)
        # Data side: the coverage's OWN (l4, metric) — the key every later layer
        # filters on. Without this a pin across differing L4 wording resolves to
        # nothing and the indicator reads as an orphan.
        for c in covs_by_row.get(rid, ()):
            register(rid, getattr(c, "l4", "") or r.l4, c.metric, HOW_BOUND)

    # A metric-only fallback, but only where the label is unambiguous tree-wide.
    row_of_metric = {m: next(iter(rids)) for m, rids in by_metric.items() if len(rids) == 1}

    return FactorLink(
        row_of_pair=row_of_pair,
        row_of_metric=row_of_metric,
        keys_of_row={k: frozenset(v) for k, v in keys_of_row.items()},
        meta_of_row=meta_of_row,
        how_of_pair=how_of_pair,
        rows_of_metric={m: frozenset(rids) for m, rids in by_metric.items()},
    )


def ignored_data_keys(st) -> dict[tuple[str, str], str]:
    """Data keys belonging to factor rows the human ignored at 2.1 → the reason.

    This is what makes "a factor you rejected does not come back" true rather than
    aspirational: the returned keys are in the space 2.2, 2.4 and 2.5 actually
    filter on.
    """
    link = build(st)
    out: dict[tuple[str, str], str] = {}
    for rid, meta in link.meta_of_row.items():
        if meta.get("status") != "ignored":
            continue
        note = meta.get("ignoreNote") or "Ignored in the FactorTree↔DataAssets mapping."
        for key in link.keys_for(rid):
            out[key] = note
    return out


# ── the factor tree, with each row's fate ───────────────────────────────────

# What a factor row's verdict can be. `notSupplied` is deliberately distinct from
# `rejected`: no data ever arrived for it, which is an upstream coverage fact, not a
# judgement anyone made about the factor.
FACTOR_ADOPTED = "adopted"
FACTOR_REJECTED = "rejected"
FACTOR_PARTIAL = "partial"
FACTOR_NOT_SUPPLIED = "notSupplied"
# Supplied, but never a candidate *driver*: either it is the response itself, or it
# failed the driver universe's own bar (fewer than MIN_MONTHS of history, or no
# variance). Distinct from `rejected` because nobody judged it.
FACTOR_NOT_MODELED = "notModeled"


def factor_tree_verdicts(st) -> list[dict]:
    """The **complete** factor tree, every row carrying its fate and where it was decided.

    This is the answer to "what happened to everything Business Understanding asked
    for" — the question 2.6 has to close out. The indicator ledger already resolves
    each *data* indicator's lifecycle, but it is keyed on what the data delivered, so
    a factor nothing ever supplied simply had no row anywhere and dropped out of the
    story. Here the tree is the spine: every active row appears exactly once, whether
    or not any data arrived for it.

    Per-object nuance is preserved rather than averaged. A factor can be adopted in
    one channel × product model and rejected in another (quality, statistical,
    selection and range all rule per object), so:

    * ``adopted``     — kept in every model that considered it,
    * ``rejected``    — rejected in all of them, with the earliest layer that ruled,
    * ``partial``     — kept in some, rejected in others; ``objects`` says which,
    * ``notSupplied`` — no published data claimed this row at all.
    """
    from app.agents.ledger import LAYER_LABEL, LAYER_TASK, indicator_ledger

    link = build(st)
    if not link.meta_of_row:
        return []

    # The response is supplied and used, but it is never a *driver*, so it has no
    # ledger row. Without this it read as "no data supplies this factor" — the one
    # factor the whole model is built on, reported as missing.
    response = ""
    try:
        from app.agents.dataset_cache import model_df
        from app.agents.overrides import resolved_y_metric
        response = _norm(resolved_y_metric(st, model_df(st)) or "")
    except Exception:  # noqa: BLE001
        response = ""

    try:
        ledger = indicator_ledger(st)
    except Exception:  # noqa: BLE001 — no ledger yet: report supply only
        ledger = ()

    # Ledger rows, grouped onto the factor row they belong to.
    by_row: dict[str, list] = {}
    for r in ledger:
        rid = link.row_for(r.l4, r.metric or r.indicator)
        if rid:
            by_row.setdefault(rid, []).append(r)

    supplied_keys = _supplied_keys(st)
    out: list[dict] = []
    for rid, meta in link.meta_of_row.items():
        rows = by_row.get(rid, [])
        supplying = sorted({m for _l4, m in link.keys_for(rid)} - {_norm(meta["indicator"])})
        base = {
            **meta,
            "supplyingMetrics": supplying,
            "objects": [],
            "rejectedAt": "", "rejectedAtLabel": "", "rejectedAtTask": "", "reason": "",
        }
        if meta.get("status") == "ignored":
            out.append({**base, "verdict": FACTOR_REJECTED, "rejectedAt": "mapping",
                        "rejectedAtLabel": LAYER_LABEL["mapping"],
                        "rejectedAtTask": LAYER_TASK["mapping"],
                        "reason": meta.get("ignoreNote")
                        or "Ignored in the FactorTree↔DataAssets mapping."})
            continue
        mine = link.keys_for(rid) & supplied_keys
        is_response = response and any(m == response for _l4, m in link.keys_for(rid))
        if is_response:
            out.append({**base, "verdict": FACTOR_ADOPTED, "role": "response",
                        "reason": "The model's response (Y) — measured, not explained."})
            continue
        if not rows:
            # Two rows can be pinned to the same data key (sibling factors whose
            # sources both deliver "花费" under one L4). Only one of them owns it in
            # `row_of_pair`, so the other has supply but no ledger row — saying
            # "too little history or no variation" there sends someone hunting a
            # data problem that does not exist.
            claimed = sorted({link.row_of_pair[k] for k in mine
                              if link.row_of_pair.get(k) not in (rid, None)})
            if mine and claimed:
                other = link.meta_of_row.get(claimed[0], {})
                label = " > ".join(x for x in (other.get("l4"), other.get("indicator")) if x)
                out.append({**base, "verdict": FACTOR_NOT_MODELED,
                            "claimedBy": claimed[0],
                            "reason": "Its data is supplied under a key another factor row "
                                      f"already claims ({label or claimed[0]}), so it carries "
                                      "no verdict of its own."})
            elif mine:
                out.append({**base, "verdict": FACTOR_NOT_MODELED,
                            "reason": "Supplied, but not a candidate driver — too little "
                                      "history or no variation to model."})
            else:
                out.append({**base, "verdict": FACTOR_NOT_SUPPLIED,
                            "reason": "No published data asset supplies this factor."})
            continue

        adopted = [r for r in rows if r.adopted]
        rejected = [r for r in rows if not r.adopted]
        objects = [{"object": r.object, "adopted": r.adopted,
                    "rejectedAt": r.rejected_at, "reason": r.reason}
                   for r in sorted(rows, key=lambda r: r.object)]
        if adopted and rejected:
            verdict = FACTOR_PARTIAL
        elif adopted:
            verdict = FACTOR_ADOPTED
        else:
            verdict = FACTOR_REJECTED
        first = _earliest_rejection(rejected)
        out.append({
            **base, "verdict": verdict, "objects": objects,
            "rejectedAt": first, "rejectedAtLabel": LAYER_LABEL.get(first, ""),
            "rejectedAtTask": LAYER_TASK.get(first, ""),
            "reason": next((r.reason for r in rejected if r.rejected_at == first), ""),
        })

    # An industry factor tree describes what *explains* sales, so none of them
    # declares sales itself: on the reference case the response matched no row and
    # the `is_response` branch above could never fire, leaving the one series the
    # whole model is built on absent from the close-out entirely. Report it from
    # the published data instead — as the response, never as an adoptable factor.
    if not any(r.get("role") == "response" for r in out):
        out.extend(_response_rows(st))

    out.sort(key=lambda r: (r["l1"], r["l2"], r["l3"], r["l4"], r["indicator"]))
    return out


def _response_rows(st) -> list[dict]:
    """The published response metric(s), shaped like a factor-tree verdict row."""
    from app.dataeng.indicators import response_coverages

    seen: set[tuple[str, str]] = set()
    rows: list[dict] = []
    for cov in response_coverages(st):
        key = (str(cov.l4), str(cov.metric))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "rowId": "", "l1": cov.l1, "l2": cov.l2, "l3": cov.l3, "l4": cov.l4,
            "indicator": cov.metric, "status": "response",
            "supplyingMetrics": [], "objects": [],
            "rejectedAt": "", "rejectedAtLabel": "", "rejectedAtTask": "",
            "verdict": FACTOR_ADOPTED, "role": "response",
            "reason": "The model's response (Y) — measured, not explained. "
                      "It is not in the factor tree because factors explain it.",
        })
    return rows


def _supplied_keys(st) -> set[tuple[str, str]]:
    """Every ``(l4, metric)`` actually present in the assembled table."""
    try:
        from app.agents.dataset_cache import model_df
        df = model_df(st)
        if df.empty:
            return set()
        return {_pair(l4, m) for (_a, _b, _c, l4, m), _g
                in df.groupby(["l1", "l2", "l3", "l4", "metric"], dropna=False)}
    except Exception:  # noqa: BLE001
        return set()


def _earliest_rejection(rejected: list) -> str:
    """The first layer in ruling order that rejected this factor anywhere.

    Reporting the *earliest* matters: a factor dropped at 2.2 for unusable data is a
    different conversation from one dropped at 2.5 for an out-of-range ROI, and every
    later layer merely inherits the first one's call.
    """
    from app.agents.ledger import LAYERS
    order = [lid for lid, _t, _l in LAYERS]
    hits = [r.rejected_at for r in rejected if r.rejected_at in order]
    return min(hits, key=order.index) if hits else ""


def factor_tree_summary(rows: list[dict]) -> dict:
    """Counts for the 2.6 header — the tree's own funnel, not the data's."""
    def n(v: str) -> int:
        return sum(1 for r in rows if r["verdict"] == v)
    by_layer: dict[str, int] = {}
    for r in rows:
        if r["verdict"] in (FACTOR_REJECTED, FACTOR_PARTIAL) and r["rejectedAt"]:
            by_layer[r["rejectedAt"]] = by_layer.get(r["rejectedAt"], 0) + 1
    return {"total": len(rows), "adopted": n(FACTOR_ADOPTED), "partial": n(FACTOR_PARTIAL),
            "rejected": n(FACTOR_REJECTED), "notSupplied": n(FACTOR_NOT_SUPPLIED),
            "notModeled": n(FACTOR_NOT_MODELED), "rejectedByLayer": by_layer}
