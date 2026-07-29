"""FactorTree ↔ DataAssets mapping resolver for 2.1 Data Processing.

Every active factor-tree row (an L4 factor + its indicator) must be resolved
before Data Intake & Validation starts: either a published Data-Engine indicator
*maps* to it, or the user *ignores* it. This module derives that per-row status
from the published indicators (the single source of truth for "mapped") plus the
project's ``factor_map_ignores`` set, and exposes ``mapping_complete`` — the
predicate that clears the 2.1 gate on the Data-Engine path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.overrides import (
    default_metric_type,
    metric_type_override,
    resolve_aggregation,
)
from app.store.state import ProjectState

_ACTIVE_STATUSES = ("baseline", "accepted")


@dataclass
class FactorMapCoverage:
    """One published (asset × metric) supplying this row."""
    coverage_id: str
    asset_id: str
    asset_name: str
    metric: str
    coverage_start: str = ""
    coverage_end: str = ""
    rows: int = 0
    bound_by: str = ""


@dataclass
class FactorMapRow:
    """One active factor row + how (or whether) it is covered by data."""
    row_id: str
    l1: str
    l2: str
    l3: str
    l4: str
    indicator: str
    status: str            # "mapped" | "ignored" | "pending"
    asset_id: str = ""
    asset_name: str = ""
    metric: str = ""       # the covering indicator's metric label
    coverage_start: str = ""
    coverage_end: str = ""
    ignore_note: str = ""
    # 2.1 model-role + aggregation the user maintains here (resolved: override else
    # the name-based classifier default). metric_type ∈ {"Y","X","excluded"}.
    metric_type: str = "X"
    aggregation: str = "sum"
    # Every source supplying this row. The flat asset_id/asset_name/metric/
    # coverage_* fields above stay, reporting the primary coverage, so existing
    # readers (the 2.1 artifact, IndicatorCatalogPanel) are unaffected.
    coverages: list[FactorMapCoverage] = field(default_factory=list)


@dataclass
class FactorMap:
    rows: list[FactorMapRow] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def mapped(self) -> int:
        return sum(1 for r in self.rows if r.status == "mapped")

    @property
    def ignored(self) -> int:
        return sum(1 for r in self.rows if r.status == "ignored")

    @property
    def pending(self) -> int:
        return sum(1 for r in self.rows if r.status == "pending")

    @property
    def complete(self) -> bool:
        """Every active row is either mapped or ignored (and there is a tree)."""
        return self.total > 0 and self.pending == 0


def resolve_factor_map(st: ProjectState) -> FactorMap:
    """Per active factor-tree row: mapped (≥1 coverage record supplies it),
    ignored (user-chosen), or pending (needs a decision).

    Coverage is attached at publish (``service.claim_published_metrics``) or by a
    human binding; matching is not re-guessed here, so this view cannot disagree
    with what the Data Engine recorded.
    """
    from app.dataeng import indicators as ind

    ft = getattr(st, "factor_tree", None)
    if ft is None:
        return FactorMap()
    ignores = getattr(st, "factor_map_ignores", None) or {}
    out: list[FactorMapRow] = []
    for r in ft.rows:
        if r.status not in _ACTIVE_STATUSES:
            continue
        fm = FactorMapRow(
            row_id=r.id, l1=r.l1, l2=r.l2, l3=r.l3, l4=r.l4,
            indicator=r.indicator, status="pending",
        )
        fm.coverages = [FactorMapCoverage(
            coverage_id=c.id, asset_id=c.asset_id, asset_name=c.asset_name,
            metric=c.metric, coverage_start=c.coverage_start,
            coverage_end=c.coverage_end, rows=c.rows, bound_by=c.bound_by)
            for c in ind.coverages_for(st, r.id)]
        cover = ind.primary_coverage(st, r.id)
        if cover is not None:
            # Coverage is reported whatever the verdict — a reader deciding whether
            # to un-ignore a row needs to see what data is actually available for it.
            fm.asset_id = cover.asset_id
            fm.asset_name = cover.asset_name
            fm.metric = cover.metric
            fm.coverage_start = cover.coverage_start
            fm.coverage_end = cover.coverage_end
        # An explicit ignore is a human decision and outranks the automatic mapping.
        # The other way round, a factor with data could not be rejected at 2.1 at
        # all: the ignore was only reachable for rows nothing supplied, so saying
        # "leave this factor out of the model" silently evaporated the moment an
        # asset happened to cover it — and the factor went on into 2.2, 2.4 and 2.5.
        if r.id in ignores:
            fm.status = "ignored"
            fm.ignore_note = str(ignores[r.id] or "")
        elif cover is not None:
            fm.status = "mapped"
        # Resolve the model role + aggregation the user maintains at 2.1: their
        # override if set, else the name-based classifier default. Keyed by the
        # covering metric label when mapped, else the factor's own indicator name.
        metric_label = fm.metric or fm.indicator
        ov_role = metric_type_override(st, r.l4, metric_label)
        fm.metric_type = ov_role or default_metric_type(metric_label)
        # `default_metric_type` returns the engine tag ("Y"/"spending"/"X"); the UI
        # concept is Y/X/excluded, so fold "spending" into "X" for display.
        if fm.metric_type == "spending":
            fm.metric_type = "X"
        fm.aggregation = resolve_aggregation(st, r.l4, metric_label)
        out.append(fm)
    return FactorMap(rows=out)


def mapping_complete(st: ProjectState) -> bool:
    """True when the factor tree exists and every active row is mapped or ignored.
    This is the strict Data-Engine gate; callers combine it with the legacy
    manifest check so slot-upload projects keep clearing 2.1."""
    return resolve_factor_map(st).complete
