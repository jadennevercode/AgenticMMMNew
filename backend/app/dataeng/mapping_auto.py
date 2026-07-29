"""Autopilot resolution of the 2.1 FactorTree↔DataAssets mapping.

A real project resolves 2.1 by hand (AI-assisted): for each factor row the analyst
either binds a published indicator or marks the factor "no data". Autopilot had no
equivalent, so the v2 demo could only clear 2.1 because the seed pre-bound every row
with fabricated indicators.

This resolver does the same job honestly and deterministically:
  · bind each pending factor row to its **best genuine** indicator match
    (``mapping_suggest.score`` ≥ ``BIND_THRESHOLD``), one indicator per row;
  · mark every remaining row **ignored** with a specific reason — the factor has no
    matching data source in the client's real published data.

It never fabricates an indicator and never force-binds a weak match, so the
resulting model is thin-but-real: only factors the client actually has data for
enter it. The rest are visibly ignored-for-no-data, not silently mapped.
"""
from __future__ import annotations

from app.dataeng import mapping_suggest as ms
from app.dataeng.mapping import resolve_factor_map
from app.store.state import ProjectState

# Below this, a factor↔indicator name/path match is too weak to auto-bind — the row
# is ignored (no data) rather than mapped to something that only looks similar.
BIND_THRESHOLD = 0.45

_NO_DATA_NOTE = (
    "Auto: no published indicator matches this factor — the client's uploaded data "
    "has no series for it (map one manually in the Data Engine if data arrives)."
)


def auto_resolve_factor_map(st: ProjectState, *, bind_threshold: float = BIND_THRESHOLD) -> dict:
    """Bind genuine matches, ignore the dataless rest. Returns a summary dict.

    Greedy by descending score with one-indicator-per-row and one-row-per-indicator
    (a single physical data series cannot stand in for two different factors)."""
    # "No published indicator matches this factor" is a judgement about the data.
    # With nothing published it is not a judgement at all — the Data Engine simply
    # has not been used yet. Resolving here writes an ignore onto *every* row, and
    # an ignore outranks coverage, so data published afterwards can never un-ignore
    # them: the factor map stays mapped=0 and the ledger drops every indicator at
    # the mapping layer. Autopilot must block on 2.1 exactly as a human would.
    if not getattr(st, "indicator_coverage", None):
        return {"bound": 0, "ignored": 0, "pending_before": 0, "no_data": True}

    fmap = resolve_factor_map(st)
    pending = [r for r in fmap.rows if r.status == "pending"]
    if not pending:
        return {"bound": 0, "ignored": 0, "pending_before": 0}

    # Only orphans can be assigned: a coverage already supplying a factor cannot
    # stand in for a second one. `used` still stops one metric being handed to two
    # rows inside a single greedy pass.
    from app.dataeng import indicators as ind
    candidates = ind.orphan_indicators(st)
    used: set[str] = set()

    scored: list[tuple[float, str, str]] = []
    for r in pending:
        for ind in candidates:
            s = ms.score(r, ind)
            if s >= bind_threshold:
                scored.append((s, r.row_id, ind.id))
    scored.sort(key=lambda t: -t[0])

    assigned: set[str] = set()
    bound = 0
    for _s, row_id, ind_id in scored:
        if row_id in assigned or ind_id in used:
            continue
        if ms.bind(st, row_id, ind_id):
            assigned.add(row_id)
            used.add(ind_id)
            bound += 1

    ignores = st.factor_map_ignores
    ignored = 0
    for r in pending:
        if r.row_id in assigned or r.row_id in ignores:
            continue
        ignores[r.row_id] = _NO_DATA_NOTE
        ignored += 1

    return {"bound": bound, "ignored": ignored, "pending_before": len(pending)}
