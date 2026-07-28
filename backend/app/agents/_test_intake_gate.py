"""The 2.1 Data Intake gate + dataset resolution (SPEC-1 / 3 / 4 / 5).

These lock down the P0 rule: a project must run S2 on **its own** data, or block
with a reason. Every assertion here corresponds to a way the gate used to open
on a project that had nothing to model.

Run: PYTHONPATH=. .venv/bin/python -m app.agents._test_intake_gate
"""
from __future__ import annotations

import pandas as pd

from app.agents import dataset_cache as dc
from app.agents.intake_status import intake_status
from app.domain import blueprint as bp
from app.domain.models import FactorRow, FactorTree, Indicator, IndustryRef, ProjectMeta
from app.store.state import initial_state

ASG = bp.TASK_MAP["2.1"]["assignment"]


def _meta(pid: str) -> ProjectMeta:
    return ProjectMeta(id=pid, name="T", brand="B",
                       industry=IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional"),
                       kpi="Vol", createdAt="2026-01-01T00:00:00+00:00")


def _state(pid: str):
    dc.invalidate_project(pid)
    return initial_state(_meta(pid))


def _modelable_df() -> pd.DataFrame:
    """A minimal long table the OLS engine can actually model: one Y, one X,
    one channel, 24 months."""
    rows = []
    for mo in range(24):
        ym = 2024 * 100 + mo + 1 if mo < 12 else 2025 * 100 + mo - 11
        base = dict(task_name="t", brand="B", province_group="East", channel_type="MT",
                    channel="MT", year=ym // 100, month=ym, source="up",
                    l2="Media", l5="", l6="", l7="", l8="")
        rows += [
            {**base, "l1": "KPI", "l3": "Volume", "l4": "", "metric": "本品销量",
             "metric_type": "Y", "value": 1000.0 + mo},
            {**base, "l1": "MARKETING FACTOR", "l3": "TV", "l4": "TV", "metric": "TV spend",
             "metric_type": "spending", "value": 100.0 * (mo + 1)},
        ]
    return pd.DataFrame(rows)


def _mapped_tree(st) -> None:
    """One active factor row, covered by one published indicator."""
    st.factor_tree = FactorTree(rows=[FactorRow(
        id="fr-1", l1="MARKETING FACTOR", l2="Media", l3="TV", l4="TV",
        indicator="TV spend", status="baseline")])
    st.indicators = [Indicator(
        id="ind-1", metric="TV spend", metricType="spending",
        l1="MARKETING FACTOR", l2="Media", l3="TV", l4="TV",
        assetId="a-1", assetName="Media", treeGrounded=True, treeRowId="fr-1")]


def test_empty_project_blocks_with_a_reason() -> None:
    """No factor tree, no data → shut, and it says why. This used to OPEN: the
    manifest path returned True for `total == 0`."""
    st = _state("gate-empty")
    s = intake_status(st, ASG)
    assert not s.ready, "an empty project must not clear the data gate"
    assert s.path == "none"
    assert s.blockers, "a shut gate must give a reason"


def test_pending_rows_block() -> None:
    """A factor row with no covering indicator keeps the gate shut."""
    st = _state("gate-pending")
    st.factor_tree = FactorTree(rows=[FactorRow(
        id="fr-1", l1="MARKETING FACTOR", l2="Media", l3="TV", l4="TV",
        indicator="TV spend", status="baseline")])
    s = intake_status(st, ASG)
    assert not s.ready and s.pending == 1 and s.total == 1
    assert any("unresolved" in b for b in s.blockers), s.blockers


def test_indicators_alone_do_not_open_the_gate() -> None:
    """Publishing an indicator that covers NOTHING in the tree must not clear the
    gate. `bool(st.indicators)` used to be a shortcut through it."""
    st = _state("gate-orphan-indicator")
    st.factor_tree = FactorTree(rows=[FactorRow(
        id="fr-1", l1="MARKETING FACTOR", l2="Media", l3="TV", l4="TV",
        indicator="TV spend", status="baseline")])
    st.indicators = [Indicator(id="ind-x", metric="Unrelated", l3="Other", l4="Other",
                               assetId="a-9", assetName="Other")]
    assert not intake_status(st, ASG).ready


def test_mapped_and_modelable_opens_the_gate() -> None:
    """Every row resolved AND the data carries Y/X/objects → ready via 'mapping'."""
    pid = "gate-ready"
    st = _state(pid)
    _mapped_tree(st)
    dc.set_project_dataset(pid, _modelable_df())
    try:
        s = intake_status(st, ASG)
        assert s.ready, s.blockers
        assert s.path == "mapping"
        assert (s.mapped, s.ignored, s.pending) == (1, 0, 0)
    finally:
        dc.invalidate_project(pid)


def test_ignored_rows_count_as_resolved() -> None:
    pid = "gate-ignored"
    st = _state(pid)
    st.factor_tree = FactorTree(rows=[FactorRow(
        id="fr-1", l1="MARKETING FACTOR", l2="Media", l3="TV", l4="TV",
        indicator="TV spend", status="baseline")])
    st.factor_map_ignores = {"fr-1": "no data source"}
    dc.set_project_dataset(pid, _modelable_df())
    try:
        s = intake_status(st, ASG)
        assert s.ready and s.ignored == 1, (s.ready, s.blockers)
    finally:
        dc.invalidate_project(pid)


def test_unmodelable_taxonomy_blocks_even_when_mapped() -> None:
    """A resolved map over data with no Y (and no channel_type) must block at the
    gate — not sail through and report '0 objects' five steps later at 2.6."""
    pid = "gate-no-taxonomy"
    st = _state(pid)
    _mapped_tree(st)
    df = _modelable_df()
    df["channel_type"] = ""          # no model objects
    df["metric_type"] = "other"      # no Y, no drivers
    df["l1"] = "SOMETHING"
    dc.set_project_dataset(pid, df)
    try:
        s = intake_status(st, ASG)
        assert not s.ready, "unmodelable data must not clear the gate"
        joined = " ".join(s.blockers)
        assert "channel_type" in joined and "response (Y)" in joined, s.blockers
    finally:
        dc.invalidate_project(pid)


def test_no_reference_fallback_for_a_real_project() -> None:
    """A project with no data of its own resolves to 'none' — NOT to the 23.8k-row
    Danone table. The seeded demo keeps the reference path."""
    from app.config import get_settings

    allowed = get_settings().allow_reference_fallback
    get_settings().allow_reference_fallback = False
    pid = "gate-no-fallback"
    dc.invalidate_project(pid)
    st = _state(pid)
    try:
        res = dc.resolve_dataset(st)
        assert res.source == "none", f"a real project must not borrow reference data ({res.source})"
        assert not res.usable and res.reason
        assert dc.model_df(st).empty
        assert dc.dataset_blocker(st)

        # The seeded demo is the one project allowed to *fall back* to the
        # reference table. (Asserted on the rule, not on a full resolution: the
        # seeded project may legitimately have its own uploads on disk, which
        # would resolve earlier as "slot".)
        assert dc._allow_reference("danone-mizone")
        assert not dc._allow_reference(pid)

        # …and the switch re-opens it for everyone, for local debugging.
        get_settings().allow_reference_fallback = True
        dc.invalidate_project(pid)
        assert dc.resolve_dataset(st).source == "reference"
    finally:
        get_settings().allow_reference_fallback = allowed
        dc.invalidate_project(pid)


def test_taxonomy_diagnosis_counts_roles() -> None:
    pid = "gate-diagnose"
    st = _state(pid)
    dc.set_project_dataset(pid, _modelable_df())
    try:
        d = dc.diagnose_taxonomy(st)
        assert d.modelable and d.objects == ["MT"], (d.problems, d.objects)
        assert d.y_rows == 24 and d.x_rows == 24, (d.y_rows, d.x_rows)
        assert d.channel_type_coverage == 1.0
    finally:
        dc.invalidate_project(pid)


if __name__ == "__main__":
    test_empty_project_blocks_with_a_reason()
    test_pending_rows_block()
    test_indicators_alone_do_not_open_the_gate()
    test_mapped_and_modelable_opens_the_gate()
    test_ignored_rows_count_as_resolved()
    test_unmodelable_taxonomy_blocks_even_when_mapped()
    test_no_reference_fallback_for_a_real_project()
    test_taxonomy_diagnosis_counts_roles()
    print("intake gate tests passed")
