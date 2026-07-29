"""Orphan review — a supplied metric the factor tree never asked for.

An orphan is not an indicator. Presenting it as one is how a data-side column
ends up looking like a project deliverable, which is what the stored catalog used
to do (``treeGrounded=False`` mixed into the same list). It gets two honest
exits: adopt it into the factor tree, or dismiss it.

Adoption writes ``source="data_upload"``, ``status="accepted"``. It does NOT go
through the S1 accept/reject gates: by the time anyone is looking at published
data, 1.21d and 1.4d are long closed, and a proposal nothing will ever accept is
just a row that silently never reaches the model.
"""
from __future__ import annotations

from typing import Optional

from app.domain.models import FactorRow, FactorTree, IndicatorCoverage
from app.store.state import ProjectState


def _coverage(st: ProjectState, coverage_id: str) -> Optional[IndicatorCoverage]:
    return next((c for c in (getattr(st, "indicator_coverage", None) or [])
                 if c.id == coverage_id), None)


def adopt(st: ProjectState, coverage_id: str) -> str:
    """Add this orphan to the factor tree and claim it. Returns the row id.

    Idempotent: adopting an already-claimed coverage returns its existing row.
    """
    cov = _coverage(st, coverage_id)
    if cov is None:
        raise KeyError(coverage_id)
    if cov.tree_row_id:
        return cov.tree_row_id
    if str(cov.metric_type).strip().upper() == "Y":
        # Sales is what the factors explain; adopting it would make the model's
        # dependent variable one of its own drivers.
        raise ValueError(
            f"{cov.metric!r} is the response (Y), not a factor — it cannot be "
            "adopted into the factor tree.")
    if st.factor_tree is None:
        st.factor_tree = FactorTree(rows=[])
    row = FactorRow(
        id=f"ft-orph-{coverage_id}",
        l1=cov.l1, l2=cov.l2, l3=cov.l3, l4=cov.l4,
        indicator=cov.metric,
        source="data_upload", status="accepted",
        rationale="Adopted from published data — supplied but not in the tree.",
        evidence=f"{cov.asset_name} · {cov.metric}",
    )
    st.factor_tree.rows.append(row)
    cov.tree_row_id = row.id
    cov.bound_by = "human"
    return row.id


def dismiss(st: ProjectState, coverage_id: str) -> bool:
    """Drop an orphan from the catalog. False when it is not an orphan.

    A coverage that supplies a factor is deliberately not dismissable here —
    removing it would unmap its row without saying so. Release it from the 2.1
    map first.
    """
    covs = getattr(st, "indicator_coverage", None) or []
    cov = _coverage(st, coverage_id)
    if cov is None or cov.tree_row_id:
        return False
    st.indicator_coverage = [c for c in covs if c.id != coverage_id]
    return True
