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

from app.agents.data_request import _norm
from app.store.state import ProjectState

_ACTIVE_STATUSES = ("baseline", "accepted")


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


def _cover_indicator(row, index: dict) -> object | None:
    """The published indicator covering `row`, or None. Precedence: exact
    tree_row_id → full L1–L4 path → L3 + indicator-name match."""
    by_row_id, by_path, by_l3_metric = index["row_id"], index["path"], index["l3_metric"]
    if row.id in by_row_id:
        return by_row_id[row.id]
    path = (_norm(row.l1), _norm(row.l2), _norm(row.l3), _norm(row.l4))
    if path in by_path:
        return by_path[path]
    if row.indicator:
        key = (_norm(row.l3), _norm(row.indicator))
        if key in by_l3_metric:
            return by_l3_metric[key]
    return None


def _index_indicators(st: ProjectState) -> dict:
    """Build lookup indexes over the published indicators for row matching."""
    by_row_id: dict[str, object] = {}
    by_path: dict[tuple, object] = {}
    by_l3_metric: dict[tuple, object] = {}
    for ind in getattr(st, "indicators", None) or []:
        if ind.tree_row_id:
            by_row_id.setdefault(ind.tree_row_id, ind)
        by_path.setdefault((_norm(ind.l1), _norm(ind.l2), _norm(ind.l3), _norm(ind.l4)), ind)
        if ind.l3 and ind.metric:
            by_l3_metric.setdefault((_norm(ind.l3), _norm(ind.metric)), ind)
    return {"row_id": by_row_id, "path": by_path, "l3_metric": by_l3_metric}


def resolve_factor_map(st: ProjectState) -> FactorMap:
    """Per active factor-tree row: mapped (a published indicator covers it),
    ignored (user-chosen), or pending (needs a decision)."""
    ft = getattr(st, "factor_tree", None)
    if ft is None:
        return FactorMap()
    ignores = getattr(st, "factor_map_ignores", None) or {}
    index = _index_indicators(st)
    out: list[FactorMapRow] = []
    for r in ft.rows:
        if r.status not in _ACTIVE_STATUSES:
            continue
        fm = FactorMapRow(
            row_id=r.id, l1=r.l1, l2=r.l2, l3=r.l3, l4=r.l4,
            indicator=r.indicator, status="pending",
        )
        cover = _cover_indicator(r, index)
        if cover is not None:
            fm.status = "mapped"
            fm.asset_id = cover.asset_id
            fm.asset_name = cover.asset_name
            fm.metric = cover.metric
            fm.coverage_start = cover.coverage_start
            fm.coverage_end = cover.coverage_end
        elif r.id in ignores:
            fm.status = "ignored"
            fm.ignore_note = str(ignores[r.id] or "")
        out.append(fm)
    return FactorMap(rows=out)


def mapping_complete(st: ProjectState) -> bool:
    """True when the factor tree exists and every active row is mapped or ignored.
    This is the strict Data-Engine gate; callers combine it with the legacy
    manifest check so slot-upload projects keep clearing 2.1."""
    return resolve_factor_map(st).complete
