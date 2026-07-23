"""Gate approval writes accepted status back onto the factor tree.

The two S1 factor-tree gates (d-1.21 / d-1.4) promise "write back into the
factor tree", but until now approving them changed no row: the AI/interview
rows stayed `proposed`, and mapping._ACTIVE_STATUSES excludes `proposed`, so
they never reached the 2.1 factor map. These tests pin that approving each gate
flips exactly its own source-set's still-proposed rows to `accepted`, leaves
manually-rejected rows alone, and thereby lets those rows into the map.

Run: PYTHONPATH=. .venv/bin/python tests/test_factor_gate_effects.py
"""
from __future__ import annotations

from app.agents.business import (
    accept_factor_rows,
    confirm_interview_effect,
    confirm_tree_effect,
)
from app.dataeng.mapping import resolve_factor_map
from app.domain.models import ArtifactInstance, FactorRow, FactorTree
from app.store.state import danone_meta, initial_state


def _state_with_tree() -> "object":
    st = initial_state(danone_meta())
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="r-base", l1="A", l2="B", l3="C", l4="D", indicator="base",
                  source="template", status="baseline"),
        FactorRow(id="r-ai", l1="A", l2="B", l3="C", l4="D", indicator="ai-ind",
                  source="ai", status="proposed"),
        FactorRow(id="r-tpl", l1="A", l2="B", l3="C", l4="D", indicator="tpl-ind",
                  source="template", status="proposed"),
        FactorRow(id="r-iv", l1="A", l2="B", l3="C", l4="D", indicator="iv-ind",
                  source="interview", status="proposed"),
        FactorRow(id="r-rej", l1="A", l2="B", l3="C", l4="D", indicator="rej-ind",
                  source="ai", status="rejected"),
    ])
    st.artifacts.append(ArtifactInstance(
        id="a-factor-tree", name="Factor Tree", taskRef="1.21",
        type="master-data", stage="s1", format="sheet", body={"stale": True}))
    return st


def _status(st, row_id: str) -> str:
    return next(r.status for r in st.factor_tree.rows if r.id == row_id)


def test_confirm_tree_flips_ai_and_template_only() -> None:
    st = _state_with_tree()
    confirm_tree_effect(st, "approve")
    assert _status(st, "r-ai") == "accepted", "ai proposed should be accepted"
    assert _status(st, "r-tpl") == "accepted", "template proposed should be accepted"
    assert _status(st, "r-iv") == "proposed", "interview belongs to d-1.4, not d-1.21"
    assert _status(st, "r-rej") == "rejected", "manual reject must be respected"
    assert _status(st, "r-base") == "baseline", "baseline is untouched"
    # The a-factor-tree sheet was re-rendered (no longer the stale placeholder).
    assert st.artifact("a-factor-tree").body != {"stale": True}


def test_confirm_interview_flips_interview_only() -> None:
    st = _state_with_tree()
    confirm_interview_effect(st, "approve")
    assert _status(st, "r-iv") == "accepted", "interview proposed should be accepted"
    assert _status(st, "r-ai") == "proposed", "ai belongs to d-1.21, not d-1.4"
    assert _status(st, "r-rej") == "rejected"


def test_rework_changes_nothing() -> None:
    st = _state_with_tree()
    before = {r.id: r.status for r in st.factor_tree.rows}
    confirm_tree_effect(st, "rework")
    confirm_interview_effect(st, "rework")
    after = {r.id: r.status for r in st.factor_tree.rows}
    assert before == after, "rework must not flip any status"


def test_flipped_rows_enter_the_2_1_map() -> None:
    st = _state_with_tree()
    before = resolve_factor_map(st).total
    confirm_tree_effect(st, "approve")
    confirm_interview_effect(st, "approve")
    after = resolve_factor_map(st).total
    # Before: only the baseline row is active/in the map. After: baseline + the
    # three flipped rows (ai, template, interview). The rejected row stays out.
    assert after == before + 3, f"expected 3 rows to enter the map, got {after - before}"


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("\nAll factor-gate-effect tests passed.")
