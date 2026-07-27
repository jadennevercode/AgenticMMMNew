"""The indicator catalog, derived from the factor tree.

The Business-Understanding factor tree defines what data this project must
collect. An ``Indicator`` is therefore a *projection* of an active factor row,
not an entity the data manufactures: it exists the moment the tree is confirmed,
and publishing data attaches an ``IndicatorCoverage`` to it rather than creating
a second, parallel list that drifts.

Nothing here is stored. Persisted state is only ``factor_tree`` (the definition)
and ``indicator_coverage`` (which asset's metric supplies which row) — the same
derive-don't-store rule ``app/agents/ledger.py`` follows, for the same reason.
"""
from __future__ import annotations

from typing import Optional

from app.domain.models import FactorRow, Indicator, IndicatorCoverage
from app.store.state import ProjectState

# A row only becomes a data target once it is confirmed. `proposed` is excluded
# here for the same reason mapping._ACTIVE_STATUSES excludes it: an unreviewed AI
# or interview suggestion is not yet something the client owes us data for.
ACTIVE_STATUSES = ("baseline", "accepted")

# FactorSource and IndicatorSource were defined independently and do not share a
# value space; this is the one place they are reconciled.
SOURCE_MAP: dict[str, str] = {
    "template": "template",
    "ai": "ai",
    "interview": "interview",
    "manual": "manual",
    "upload": "uploaded_tree",
    "data_upload": "data_upload",
}


def active_rows(st: ProjectState) -> list[FactorRow]:
    ft = getattr(st, "factor_tree", None)
    if ft is None:
        return []
    return [r for r in ft.rows if r.status in ACTIVE_STATUSES]


def _norm(s: str) -> str:
    return "".join(str(s or "").lower().split())


def resolve_coverage(st: ProjectState) -> dict[str, list[IndicatorCoverage]]:
    """row id → the coverages supplying it, for every active row. One pass.

    Two ways a coverage reaches a row, in precedence order:

    1. **Explicitly bound** (`tree_row_id`) — set at publish when the mart's path
       matched, or pinned by a human. Authoritative.
    2. **Matched here** on full L1–L4 path, then L3 + metric name.

    Tier 2 exists because coverage can legitimately be written *before* the tree:
    resetting the Danone case seeds its 29 reference assets while `factor_tree` is
    still None (the tree is built later, by task 1.21). Matching only at write
    time left every one of them an orphan forever, and the 2.1 map permanently
    pending. The old resolver matched on read for exactly this reason.
    """
    rows = active_rows(st)
    covs = list(getattr(st, "indicator_coverage", None) or [])
    out: dict[str, list[IndicatorCoverage]] = {r.id: [] for r in rows}

    by_path: dict[tuple, str] = {}
    by_l3_metric: dict[tuple, str] = {}
    for r in rows:
        by_path.setdefault((_norm(r.l1), _norm(r.l2), _norm(r.l3), _norm(r.l4)), r.id)
        if r.l3 and r.indicator:
            by_l3_metric.setdefault((_norm(r.l3), _norm(r.indicator)), r.id)

    claimed: set[str] = set()
    for c in covs:
        if c.tree_row_id and c.tree_row_id in out:
            out[c.tree_row_id].append(c)
            claimed.add(c.id)
    for c in covs:
        if c.id in claimed or c.tree_row_id:
            continue
        hit = (by_path.get((_norm(c.l1), _norm(c.l2), _norm(c.l3), _norm(c.l4)))
               or (by_l3_metric.get((_norm(c.l3), _norm(c.metric))) if c.metric else None))
        if hit is not None:
            out[hit].append(c)
            claimed.add(c.id)
    return out


def coverages_for(st: ProjectState, tree_row_id: str) -> list[IndicatorCoverage]:
    """Every published (asset × metric) supplying this row.

    A factor may legitimately be supplied by more than one source — TV spend
    split across two files is routine — so this is a list, not an Optional.
    """
    if not tree_row_id:
        return []
    return resolve_coverage(st).get(tree_row_id, [])


def _primary(covs: list[IndicatorCoverage]) -> Optional[IndicatorCoverage]:
    """A human pin wins outright — it is a decision, and a bigger automatic match
    is not a reason to overrule it. Otherwise the widest series wins."""
    if not covs:
        return None
    pinned = [c for c in covs if c.bound_by == "human"]
    return (pinned or sorted(covs, key=lambda c: -c.rows))[0]


def primary_coverage(st: ProjectState, tree_row_id: str) -> Optional[IndicatorCoverage]:
    """The coverage that represents the row in flat, single-value views."""
    return _primary(coverages_for(st, tree_row_id))


def _declared(row: FactorRow, cov: Optional[IndicatorCoverage]) -> Indicator:
    """One active factor row projected to an Indicator, filled in by its coverage."""
    return Indicator(
        id=f"ind-{row.id}",
        # The factor's own wording is the label — the mart's metric name lives on
        # the coverage record, so a rename in the data never renames the factor.
        metric=row.indicator or row.l4,
        metricType=(cov.metric_type if cov else ""),
        l1=row.l1, l2=row.l2, l3=row.l3, l4=row.l4,
        semanticType=(cov.semantic_type if cov else "other"),
        unit=(cov.unit if cov else ""),
        currency=(cov.currency if cov else None),
        aggregation=(cov.aggregation if cov else "sum"),
        numberFormat=(cov.number_format if cov else "number"),
        ruleVersion=(cov.rule_version if cov else ""),
        # Supplied rows report as data; unsupplied ones keep their provenance so
        # the catalog reads as "this is why we are asking for it".
        source=("data_upload" if cov else SOURCE_MAP.get(row.source, "template")),
        assetId=(cov.asset_id if cov else ""),
        assetName=(cov.asset_name if cov else ""),
        coverageStart=(cov.coverage_start if cov else ""),
        coverageEnd=(cov.coverage_end if cov else ""),
        rows=(cov.rows if cov else 0),
        treeGrounded=True,
        treeRowId=row.id,
        boundBy=(cov.bound_by if cov else ""),
    )


def _orphan(cov: IndicatorCoverage) -> Indicator:
    """A supplied metric no factor row asked for.

    Kept visibly apart from declared indicators: presenting it as one is how a
    data-side column ends up looking like a project deliverable.
    """
    return Indicator(
        id=cov.id, metric=cov.metric, metricType=cov.metric_type,
        l1=cov.l1, l2=cov.l2, l3=cov.l3, l4=cov.l4,
        semanticType=cov.semantic_type, unit=cov.unit, currency=cov.currency,
        aggregation=cov.aggregation, numberFormat=cov.number_format,
        ruleVersion=cov.rule_version, source="data_upload",
        assetId=cov.asset_id, assetName=cov.asset_name,
        coverageStart=cov.coverage_start, coverageEnd=cov.coverage_end,
        rows=cov.rows, treeGrounded=False, treeRowId="", boundBy="",
    )


def declared_indicators(st: ProjectState) -> list[Indicator]:
    """The data target list: one indicator per active factor row, in tree order."""
    resolved = resolve_coverage(st)
    return [_declared(r, _primary(resolved.get(r.id, []))) for r in active_rows(st)]


def orphan_indicators(st: ProjectState) -> list[Indicator]:
    """Supplied metrics reaching no factor row — awaiting adoption or dismissal.

    A coverage matched to a row by `resolve_coverage` is NOT an orphan even
    without an explicit `tree_row_id`; otherwise the same record would appear as
    both a supplied factor and an unclaimed metric.
    """
    supplied = {c.id for covs in resolve_coverage(st).values() for c in covs}
    return [_orphan(c) for c in (getattr(st, "indicator_coverage", None) or [])
            if c.id not in supplied]


def derive_indicators(st: ProjectState) -> list[Indicator]:
    return declared_indicators(st) + orphan_indicators(st)
