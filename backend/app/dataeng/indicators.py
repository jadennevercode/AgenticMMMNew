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


def coverages_for(st: ProjectState, tree_row_id: str) -> list[IndicatorCoverage]:
    """Every published (asset × metric) supplying this row.

    A factor may legitimately be supplied by more than one source — TV spend
    split across two files is routine — so this is a list, not an Optional.
    """
    if not tree_row_id:
        return []
    return [c for c in (getattr(st, "indicator_coverage", None) or [])
            if c.tree_row_id == tree_row_id]


def primary_coverage(st: ProjectState, tree_row_id: str) -> Optional[IndicatorCoverage]:
    """The coverage that represents the row in flat, single-value views.

    A human pin wins outright — it is a decision, and a bigger automatic match is
    not a reason to overrule it. Otherwise the widest series wins.
    """
    covs = coverages_for(st, tree_row_id)
    if not covs:
        return None
    pinned = [c for c in covs if c.bound_by == "human"]
    return (pinned or sorted(covs, key=lambda c: -c.rows))[0]


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
    return [_declared(r, primary_coverage(st, r.id)) for r in active_rows(st)]


def orphan_indicators(st: ProjectState) -> list[Indicator]:
    """Supplied metrics with no factor row — awaiting adoption or dismissal."""
    return [_orphan(c) for c in (getattr(st, "indicator_coverage", None) or [])
            if not c.tree_row_id]


def derive_indicators(st: ProjectState) -> list[Indicator]:
    return declared_indicators(st) + orphan_indicators(st)
