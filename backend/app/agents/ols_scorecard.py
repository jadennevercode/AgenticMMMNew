"""2.5's range verdicts as reviewable, stored state — the `range` filter layer.

Every other S2 layer records its verdict in a place a human can see and revise:
2.2 and 2.4 each have a scorecard with a per-row disposition. 2.5 did not. Its
range check produced a `review` status on the artifact, and the only way to act on
it was the `d-2.5` gate's *all-or-nothing* "drop flagged indicators" option — a
verdict on the whole set, recorded nowhere per factor.

That forced a workaround, and the workaround is what this module removes. Because
nothing stored the drops, `d-2.5` had to **freeze** them onto its own resolution
at the moment it was answered (`ledger.freeze_range_drops`): once the dropped
indicators are excluded, the next fit has no records for them, so they stop being
flagged, and a live re-derivation would read that silence as "nothing was out of
range" and walk them straight back into the model. Storing the verdict makes the
freeze unnecessary — a rejection persists because it was written down, not because
a gate photographed it.

Two rules the merge must hold, and both have burned us before:

* **A human's verdict outranks a re-fit.** Re-fitting rebuilds every computed
  field and the AI's recommendation. A row carrying ``decided_by="human"`` keeps
  its disposition through all of it.
* **A rejected row does not disappear.** Rejecting excludes the indicator, so the
  next fit has no record of it and it is absent from the new tree. Dropping rows
  the tree no longer mentions would delete the very verdict that removed them, and
  the indicator would silently return.
"""
from __future__ import annotations

from app.domain.models import OlsRangeRow, OlsRangeScorecard
from app.store.state import ProjectState

# Statuses that mean "an earlier layer already ruled, or this never entered a fit".
# These carry no range verdict of their own and are not offered for review.
NOT_REVIEWABLE = frozenset({"dropped", "notMapped", "notInModel"})

# The AI's own readings, from `ols_benchmark.review_rows`.
AI_IMPLAUSIBLE = "implausible"
AI_QUESTIONABLE = "questionable"


def _norm(s: object) -> str:
    return str(s).strip().lower() if s is not None else ""


def row_id(object: str, l4: object, indicator: object) -> str:
    return f"{str(object).strip()}|{_norm(l4)}|{_norm(indicator)}"


def recommend(row: dict) -> tuple[str, str]:
    """The AI's accept/reject proposal for one fitted factor → (verdict, reason).

    Deterministic first, language second: the range check is arithmetic and the
    AI's reading is commentary on it. `implausible` rejects on its own because it
    is the model saying the coefficient cannot be believed even where a band is
    absent — `noBenchmark` is otherwise unfalsifiable and would always accept.
    `questionable` does **not** reject: the arithmetic passed, and turning a hedge
    into a rejection would drop variables nobody decided to drop.
    """
    if row.get("status") == "review":
        return "reject", row.get("flagReason") or "Outside its knowledge-base range."
    if _norm(row.get("aiVerdict")) == AI_IMPLAUSIBLE:
        return "reject", (row.get("aiRationale")
                          or "The benchmark review judged this result implausible.")
    if _norm(row.get("aiVerdict")) == AI_QUESTIONABLE:
        return "accept", (f"Within range, but flagged as questionable: "
                          f"{row.get('aiRationale') or 'see the benchmark review'}")
    if row.get("status") == "noBenchmark":
        return "accept", "No industry band to check against; nothing contradicts the fit."
    return "accept", "ROI and contribution sit inside their industry band."


_COMPUTED = ("l1", "l2", "l3", "l4", "metric", "coef", "roi", "contribution",
             "significant", "status", "aiVerdict", "aiRationale")


def _from_tree_row(r: dict) -> OlsRangeRow:
    auto, why = recommend(r)
    return OlsRangeRow(
        id=row_id(r.get("object", ""), r.get("l4"), r.get("indicator")),
        object=str(r.get("object", "")),
        treeRowId=str(r.get("treeRowId", "")),
        l1=str(r.get("l1", "")), l2=str(r.get("l2", "")),
        l3=str(r.get("l3", "")), l4=str(r.get("l4", "")),
        indicator=str(r.get("indicator", "")), metric=str(r.get("metric", "") or r.get("indicator", "")),
        coef=r.get("coef"), tValue=r.get("tValue"), pValue=r.get("pValue"),
        significant=r.get("significant"),
        roi=r.get("roi"), contribution=r.get("contribution"),
        roiRange=str(r.get("roiRange", "")), contributionRange=str(r.get("contributionRange", "")),
        roiStatus=str(r.get("roiStatus", "none")),
        contributionStatus=str(r.get("contributionStatus", "none")),
        rangeSource=str(r.get("rangeSource", "")),
        status=str(r.get("status", "")), flagReason=str(r.get("flagReason", "")),
        aiVerdict=str(r.get("aiVerdict", "")), aiRationale=str(r.get("aiRationale", "")),
        autoVerdict=auto, autoReason=why, disposition=auto, decidedBy="ai",
    )


def build_scorecard(st: ProjectState, body: dict) -> OlsRangeScorecard:
    """Refresh the 2.5 scorecard from a freshly-built `a-ols-test` body.

    Merges over whatever is already stored: computed fields and the AI's
    recommendation are always refreshed, the disposition only where the AI still
    owns it, and rows absent from the new tree are carried forward (see the module
    docstring — those are usually the rejected ones, which is exactly why the
    fit no longer mentions them).
    """
    prior = {r.id: r for r in (getattr(st, "ols_scorecard", None) or OlsRangeScorecard()).rows}
    seen: set[str] = set()
    rows: list[OlsRangeRow] = []

    for r in body.get("tree") or []:
        if r.get("status") in NOT_REVIEWABLE:
            continue
        fresh = _from_tree_row(r)
        seen.add(fresh.id)
        old = prior.get(fresh.id)
        if old is not None and old.decided_by == "human":
            # Keep the human's call and their note; everything else re-derives.
            fresh = fresh.model_copy(update={
                "disposition": old.disposition, "decided_by": "human", "note": old.note})
        rows.append(fresh)

    # Rows the new tree does not mention. A rejected indicator is excluded from the
    # re-fit, so it cannot appear — carrying it forward is what makes the rejection
    # stick instead of evaporating on the next save.
    for rid, old in prior.items():
        if rid not in seen and old.disposition == "reject":
            rows.append(old)

    rows.sort(key=lambda r: (r.l1, r.l2, r.l3, r.l4, r.indicator, r.object))
    return OlsRangeScorecard(rows=rows, generatedAt=str(getattr(st, "tick", "") or ""))


def reject_pairs_by_object(st: ProjectState) -> dict[str, set[tuple[str, str]]]:
    """What 2.5d rejected, keyed by model object — the `range` layer's drop set.

    Returns ``{}`` when no scorecard exists, which is the signal for the ledger to
    fall back to the legacy `d-2.5` frozen drops so projects resolved before this
    surface existed keep their verdicts.
    """
    card = getattr(st, "ols_scorecard", None)
    out: dict[str, set[tuple[str, str]]] = {}
    for r in (getattr(card, "rows", None) or []):
        if r.disposition != "reject":
            continue
        obj = str(r.object).strip() or "*"
        out.setdefault(obj, set()).add((_norm(r.l4), _norm(r.indicator)))
    return out


def pending_rows(st: ProjectState) -> list[tuple[str, str]]:
    """Rows with no verdict at all. Structurally impossible — the disposition is
    seeded from the AI and the type admits only accept/reject — so this exists to
    make the gate's guarantee explicit rather than assumed."""
    card = getattr(st, "ols_scorecard", None)
    return [(str(r.l4), str(r.indicator)) for r in (getattr(card, "rows", None) or [])
            if r.disposition not in ("accept", "reject")]


def summary(st: ProjectState) -> dict:
    card = getattr(st, "ols_scorecard", None)
    rows = list(getattr(card, "rows", None) or [])
    return {
        "total": len(rows),
        "accepted": sum(1 for r in rows if r.disposition == "accept"),
        "rejected": sum(1 for r in rows if r.disposition == "reject"),
        "byHuman": sum(1 for r in rows if r.decided_by == "human"),
        "overridden": sum(1 for r in rows
                          if r.decided_by == "human" and r.disposition != r.auto_verdict),
    }
