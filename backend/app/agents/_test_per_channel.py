"""Phase 2 — per-Channel-Type screening. Shared fixture + unit tests.

Run: PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from app.agents.dataset_cache import invalidate_project, model_objects, set_project_dataset
from app.domain.models import IndustryRef, ProjectMeta
from app.store.state import initial_state


def _month_seq(start_ym: int, n: int) -> list[int]:
    """``n`` contiguous yyyymm values starting at ``start_ym`` (calendar rollover,
    not integer increment — yyyymm skips 88 values a year, so ``start_ym + m``
    walks off the end of the year instead of rolling to the next one)."""
    y, m = divmod(start_ym, 100)
    out = []
    for i in range(n):
        total = m - 1 + i
        out.append((y + total // 12) * 100 + total % 12 + 1)
    return out


_MONTHS = _month_seq(202301, 24)  # 24 contiguous yyyymm from 2023-01


def _rows_for(channel_type: str, degenerate_stock: bool) -> list[dict]:
    """One channel's rows: KPI 销量, driver 广告投放, driver 渠道库存.

    `degenerate_stock=True` makes 渠道库存 a constant series in this channel, so it
    is a legitimate drop for statistical screening here but not in the other
    channel — the exact per-channel divergence these tests assert.
    """
    rng = np.random.default_rng(1 if channel_type == "MT" else 2)
    signal = np.linspace(100, 200, len(_MONTHS)) + rng.normal(0, 5, len(_MONTHS))
    ads = signal * 0.5 + rng.normal(0, 3, len(_MONTHS))
    stock = (np.full(len(_MONTHS), 50.0) if degenerate_stock
             else signal * 0.3 + rng.normal(0, 4, len(_MONTHS)))
    out: list[dict] = []
    for i, ym in enumerate(_MONTHS):
        common = dict(task_name="mmm", brand="B", province_group="全国",
                      channel_type=channel_type, channel=channel_type, year=ym // 100,
                      month=ym, source="erp", l2="", l5="", l6="", l7="", l8="")
        out.append({**common, "l1": "KPI", "l3": "销量", "l4": "本品销量",
                    "metric_type": "Y", "metric": "销量", "value": float(signal[i])})
        out.append({**common, "l1": "MARKETING FACTOR", "l3": "广告", "l4": "广告投放",
                    "metric_type": "spending", "metric": "广告投放", "value": float(ads[i])})
        out.append({**common, "l1": "COMMERCIAL FACTOR", "l3": "渠道", "l4": "渠道库存",
                    "metric_type": "X", "metric": "渠道库存", "value": float(stock[i])})
    return out


def make_two_channel_state(pid: str = "t-per-channel"):
    meta = ProjectMeta(id=pid, name="PerChannel", brand="B",
                       industry=IndustryRef(l1="food-bev", l2="beverage", l3="functional"),
                       createdAt="2026-01-01T00:00:00+00:00")
    st = initial_state(meta)
    rows = _rows_for("MT", degenerate_stock=False) + _rows_for("TT", degenerate_stock=True)
    df = pd.DataFrame(rows)
    invalidate_project(pid)
    set_project_dataset(pid, df, "slot")
    return st


def test_fixture() -> None:
    st = make_two_channel_state()
    # MT and TT carry equal row counts in this fixture, so `model_objects`'
    # busiest-first ordering does not guarantee a specific tie order — assert
    # membership, not position (see test_model_objects_ordered_by_data below).
    assert sorted(model_objects(st)) == ["MT", "TT"], model_objects(st)
    print("  fixture: MT + TT bound")


def test_signoff_key_carries_object() -> None:
    from app.agents import ledger
    k_all = ledger.signoff_key("广告投放", "广告投放")
    k_tt = ledger.signoff_key("广告投放", "广告投放", "TT")
    assert k_all == "i:*:广告投放|广告投放", k_all
    kind, obj, l4, metric = ledger._parse_signoff_key(k_tt)
    assert (kind, obj, l4, metric) == ("indicator", "TT", "广告投放", "广告投放")
    st = make_two_channel_state()
    st.signoffs = {k_tt: "no"}
    by_obj = ledger.signoff_drop_pairs_by_object(st)
    assert ("广告投放", "广告投放") in by_obj.get("TT", set())
    assert ("广告投放", "广告投放") not in by_obj.get("MT", set())
    # A legacy unprefixed key still parses and applies to all objects.
    st.signoffs = {"广告投放|广告投放": "no"}
    by_obj = ledger.signoff_drop_pairs_by_object(st)
    assert ("广告投放", "广告投放") in by_obj.get(ledger.OBJECT_ANY, set())
    # A legacy pre-Task-4 "i:" key (no object segment) also still parses.
    old_key = "i:广告投放|广告投放"
    kind, obj, l4, metric = ledger._parse_signoff_key(old_key)
    assert (kind, obj, l4, metric) == ("indicator", ledger.OBJECT_ANY, "广告投放", "广告投放")
    st.signoffs = {old_key: "no"}
    by_obj = ledger.signoff_drop_pairs_by_object(st)
    assert ("广告投放", "广告投放") in by_obj.get(ledger.OBJECT_ANY, set())
    print("  sign-off keys are object-aware, legacy keys still parse")


def test_stat_drops_are_per_object() -> None:
    from app.agents import ledger
    # For this test we craft stat dispositions directly rather than fitting.
    from app.domain.models import StatScorecard, StatScoreRow
    st = make_two_channel_state()
    st.stat_scorecard = StatScorecard(rows=[
        StatScoreRow(id="s-mt", object="MT", l4="渠道库存", indicator="渠道库存",
                     disposition="include"),
        StatScoreRow(id="s-tt", object="TT", l4="渠道库存", indicator="渠道库存",
                     disposition="drop"),
    ])
    by_obj = ledger.stat_drop_pairs_by_object(st)
    assert ("渠道库存", "渠道库存") in by_obj.get("TT", set()), by_obj
    assert ("渠道库存", "渠道库存") not in by_obj.get("MT", set()), by_obj
    # drops_before for the statistical layer must reflect the channel asked for.
    assert ("渠道库存", "渠道库存") in ledger.drops_before(st, "range", "TT")
    assert ("渠道库存", "渠道库存") not in ledger.drops_before(st, "range", "MT")
    print("  stat drops per object")


def test_stat_scorecard_is_per_object() -> None:
    from app.agents.stat_scoring import build_stat_scorecard
    st = make_two_channel_state()
    card = build_stat_scorecard(st)
    objs = {r.object for r in card.rows}
    assert objs == {"MT", "TT"}, objs
    # 渠道库存 is constant in TT → dropped there by the degenerate-series guard,
    # but present as a scored row in MT.
    mt_stock = [r for r in card.rows if r.object == "MT" and r.indicator == "渠道库存"]
    assert mt_stock, "渠道库存 should be scored in MT"
    print("  stat scorecard per object")


def test_ledger_is_per_object() -> None:
    # Built directly (as in test_stat_drops_are_per_object above) rather than via
    # build_stat_scorecard(): the fixture's TT 渠道库存 is a constant series, which
    # the real scorer excludes from scoring entirely (see
    # test_stat_scorecard_is_per_object) rather than scoring it "drop" — so a
    # natural scorecard never carries the TT disposition this test needs to force.
    from app.agents import ledger
    from app.domain.models import StatScorecard, StatScoreRow
    st = make_two_channel_state()
    # Force TT to drop 渠道库存, MT to keep it.
    st.stat_scorecard = StatScorecard(rows=[
        StatScoreRow(id="s-mt", object="MT", l4="渠道库存", indicator="渠道库存",
                     disposition="include"),
        StatScoreRow(id="s-tt", object="TT", l4="渠道库存", indicator="渠道库存",
                     disposition="drop"),
    ])
    rows = ledger.indicator_ledger(st)
    tt = next(r for r in rows if r.object == "TT" and r.indicator == "渠道库存")
    mt = next(r for r in rows if r.object == "MT" and r.indicator == "渠道库存")
    assert not tt.adopted and tt.rejected_at == "statistical", (tt.rejected_at, tt.adopted)
    assert mt.adopted, mt.rejected_at
    print("  ledger per object: 渠道库存 dropped in TT, kept in MT")


def test_ols_candidates_are_per_object() -> None:
    from app.agents.stat_scoring import build_stat_scorecard
    from app.agents.ols_review import build_ols_proposal, selected_x_metrics
    st = make_two_channel_state()
    st.stat_scorecard = build_stat_scorecard(st)
    cfg = build_ols_proposal(st)
    objs = {c.object for c in cfg.x_candidates}
    assert objs == {"MT", "TT"}, objs
    # 广告投放 offered separately in each channel.
    ads = [c for c in cfg.x_candidates if c.metric == "广告投放"]
    assert {c.object for c in ads} == {"MT", "TT"}, [c.object for c in ads]
    sel = selected_x_metrics(cfg)
    assert isinstance(sel, dict) and set(sel) <= {"MT", "TT"}
    print("  OLS candidates + selection are per object")


def test_ols_tree_droppedby_is_per_object() -> None:
    """Task 5 regression guard: `build_ols_review`'s ``tree``/``rejected_by`` must
    key per (object, factor), not collapse "last-object-wins" across channels —
    the same bug shape `test_ledger_is_per_object` guards at the ledger layer,
    now exercised through the real ``olsTree`` artifact body.

    `resolve_factor_map(make_two_channel_state())` is empty (no factor tree on
    the synthetic fixture), and the record-only leftover-sweep can never carry a
    dropped-in-one-channel row (a locked/dropped candidate is never fit, so it
    never becomes a ``records`` entry) — so a minimal one-row factor tree is
    added here to drive the tree through its primary (fmap) path, matching how
    a real project always has a factor tree by the time 2.5 runs.
    """
    from app.agents.ledger import indicator_ledger
    from app.agents.ols_review import build_ols_proposal, build_ols_review
    from app.agents.stat_scoring import build_stat_scorecard
    from app.domain.models import FactorRow, FactorTree, StatScorecard, StatScoreRow

    st = make_two_channel_state()
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="f-stock", l1="COMMERCIAL FACTOR", l2="", l3="渠道",
                   l4="渠道库存", indicator="渠道库存"),
    ])
    # Force the divergence: TT drops 渠道库存 at the statistical layer, MT keeps
    # it — same pattern as test_ledger_is_per_object, built off the naturally
    # scored MT row (so it still carries real pearson/vif/cv for 2.5's proposal)
    # plus a synthetic TT row (TT's stock series is constant/degenerate in this
    # fixture, so the real scorer never emits a row for it at all — see
    # test_stat_scorecard_is_per_object).
    card = build_stat_scorecard(st)
    rows = [r if r.indicator != "渠道库存" else r.model_copy(update={"disposition": "include"})
            for r in card.rows]
    rows.append(StatScoreRow(id="s-tt", object="TT", l4="渠道库存", indicator="渠道库存",
                              disposition="drop"))
    st.stat_scorecard = StatScorecard(rows=rows)
    # Sanity check the fixture actually forces the divergence at the ledger
    # layer before trusting the tree assertion below.
    ledger_rows = {r.object: r for r in indicator_ledger(st) if r.indicator == "渠道库存"}
    assert not ledger_rows["TT"].adopted and ledger_rows["TT"].rejected_at == "statistical"
    assert ledger_rows["MT"].adopted

    st.ols_config = build_ols_proposal(st)
    body, _prefit, _flagged = build_ols_review(st, fit=True)
    tree_rows = {r["object"]: r for r in body["tree"] if r["indicator"] == "渠道库存"}
    assert set(tree_rows) == {"MT", "TT"}, tree_rows

    tt = tree_rows["TT"]
    assert tt["droppedBy"] == "statistical", tt
    assert tt["status"] == "dropped", tt
    assert tt["inModel"] is False, tt

    mt = tree_rows["MT"]
    assert mt["droppedBy"] == "", mt
    assert mt["status"] != "dropped", mt
    print("  ols tree droppedBy per object: 渠道库存 dropped-by-statistical in TT only")


def test_model_selection_is_per_object() -> None:
    """Task 6: `ModelSelection.exclude`/`include` are resolved per model object,
    so one channel's drop must not exclude an indicator from another channel's
    fit.

    Built directly (as `test_stat_drops_are_per_object` / `test_ledger_is_per_object`
    above do) rather than via `build_stat_scorecard()`: the fixture's TT 渠道库存
    is a constant series, which the real scorer excludes from scoring entirely
    (see `test_stat_scorecard_is_per_object`) rather than scoring it "drop" — so
    a natural scorecard never carries the TT disposition this test needs to force.
    """
    from app.agents.ledger import model_selection
    from app.domain.models import StatScorecard, StatScoreRow
    st = make_two_channel_state()
    st.stat_scorecard = StatScorecard(rows=[
        StatScoreRow(id="s-mt", object="MT", l4="渠道库存", indicator="渠道库存",
                     disposition="include"),
        StatScoreRow(id="s-tt", object="TT", l4="渠道库存", indicator="渠道库存",
                     disposition="drop"),
    ])
    sel = model_selection(st)
    assert ("渠道库存", "渠道库存") in sel.exclude_for("TT")
    assert ("渠道库存", "渠道库存") not in sel.exclude_for("MT")
    print("  model_selection excludes per object")


def test_master_table_columns_differ_by_channel() -> None:
    """Task 7: ``adopted_mask`` resolves per channel_type, so the same indicator
    can be a column in one channel's master table and absent from another's.

    Built directly (as `test_stat_drops_are_per_object` / `test_ledger_is_per_object`
    above do) rather than via `build_stat_scorecard()`: the fixture's TT 渠道库存
    is a constant series, which the real scorer excludes from scoring entirely
    (see `test_stat_scorecard_is_per_object`) rather than scoring it "drop" — so
    a natural scorecard never carries the TT disposition this test needs to force.
    """
    from app.domain.models import StatScorecard, StatScoreRow
    from app.agents.master_data import master_table
    st = make_two_channel_state()
    st.stat_scorecard = StatScorecard(rows=[
        StatScoreRow(id="s-mt", object="MT", l4="渠道库存", indicator="渠道库存",
                     disposition="include"),
        StatScoreRow(id="s-tt", object="TT", l4="渠道库存", indicator="渠道库存",
                     disposition="drop"),
    ])
    mt = master_table(st, channel_type=["MT"])
    tt = master_table(st, channel_type=["TT"])
    assert "渠道库存" in [c for c in mt["columns"]], mt["columns"]
    assert "渠道库存" not in [c for c in tt["columns"]], tt["columns"]
    print("  master table columns differ by channel")


def test_adopted_mask_screens_unmapped_channel_rows() -> None:
    """Task 7 fix: a MISSING/NaN ``channel_type`` must not escape per-object
    screening. ``channel_type.astype("string")`` turns NaN into the literal
    string ``"<NA>"``, which the old per-object loop treated as a real model
    object — ``sel.exclude_for("<NA>")`` only resolves OBJECT_ANY-level drops,
    never a per-object (TT-only) drop — so a TT-rejected indicator could leak
    into the master table via any row whose channel could not be mapped. The
    fix screens unmapped rows against the union of every model object's
    excludes instead (the strict, pre-Task-7 behaviour), so a rejected-
    anywhere indicator can never surface through an unmapped row while a
    genuinely-adopted indicator (and the KPI) still passes through.
    """
    from app.agents.master_data import adopted_mask
    from app.domain.models import StatScorecard, StatScoreRow

    st = make_two_channel_state()
    # 渠道库存 is dropped in TT only (a per-object drop, not OBJECT_ANY) —
    # exactly the shape exclude_for("<NA>") cannot see.
    st.stat_scorecard = StatScorecard(rows=[
        StatScoreRow(id="s-mt", object="MT", l4="渠道库存", indicator="渠道库存",
                     disposition="include"),
        StatScoreRow(id="s-tt", object="TT", l4="渠道库存", indicator="渠道库存",
                     disposition="drop"),
    ])

    df = pd.DataFrame([
        # rejected-in-TT indicator, channel unmapped — must NOT leak through.
        dict(l4="渠道库存", metric="渠道库存", metric_type="X", channel_type=np.nan),
        # same indicator, mapped to the channel that actually rejected it.
        dict(l4="渠道库存", metric="渠道库存", metric_type="X", channel_type="TT"),
        # same indicator, mapped to the channel that kept it.
        dict(l4="渠道库存", metric="渠道库存", metric_type="X", channel_type="MT"),
        # genuinely-adopted indicator, channel unmapped — must stay in.
        dict(l4="广告投放", metric="广告投放", metric_type="spending", channel_type=np.nan),
        # KPI row, channel unmapped — must stay in unconditionally.
        dict(l4="本品销量", metric="销量", metric_type="Y", channel_type=np.nan),
    ])

    mask = adopted_mask(st, df)
    assert list(mask) == [False, False, True, True, True], list(mask)
    print("  adopted_mask screens unmapped-channel rows against all-object excludes")


def test_legacy_global_rows_apply_to_all_objects() -> None:
    from app.agents.stat_scoring import build_stat_scorecard
    from app.agents import ledger
    st = make_two_channel_state()
    # Simulate a legacy scorecard: object="" on a drop → must hit BOTH channels.
    st.stat_scorecard = build_stat_scorecard(st)
    for r in st.stat_scorecard.rows:
        r.object = ""      # legacy state
    for r in st.stat_scorecard.rows:
        if r.indicator == "渠道库存":
            r.disposition = "drop"
    by_obj = ledger.stat_drop_pairs_by_object(st)
    assert ("渠道库存", "渠道库存") in by_obj.get(ledger.OBJECT_ANY, set())
    assert ("渠道库存", "渠道库存") in ledger.drops_before(st, "range", "MT")
    assert ("渠道库存", "渠道库存") in ledger.drops_before(st, "range", "TT")
    print("  legacy global rows apply to every channel")


def test_model_objects_ordered_by_data() -> None:
    from app.agents.dataset_cache import model_objects
    st = make_two_channel_state()  # MT and TT have equal row counts → name order
    assert set(model_objects(st)) == {"MT", "TT"}
    print("  model_objects derived from data, no hardcoded list")


def test_drops_before_no_object_equals_global_union() -> None:
    """The no-object form of `drops_before` (``object=None``) is documented as
    the legacy global-union behaviour for every un-migrated caller — pin that
    invariant: it must always equal the union of every model object's own
    `drops_before`, even once a layer's verdict genuinely diverges per channel.
    """
    from app.agents import ledger
    from app.agents.dataset_cache import model_objects
    from app.domain.models import StatScorecard, StatScoreRow

    st = make_two_channel_state()
    # Force the same per-channel divergence as test_model_selection_is_per_object:
    # TT drops 渠道库存 at the statistical layer, MT keeps it.
    st.stat_scorecard = StatScorecard(rows=[
        StatScoreRow(id="s-mt", object="MT", l4="渠道库存", indicator="渠道库存",
                     disposition="include"),
        StatScoreRow(id="s-tt", object="TT", l4="渠道库存", indicator="渠道库存",
                     disposition="drop"),
    ])

    global_drops = ledger.drops_before(st, "range")
    per_object_union: set[tuple[str, str]] = set()
    for obj in model_objects(st):
        per_object_union |= ledger.drops_before(st, "range", obj)

    assert global_drops == per_object_union, (global_drops, per_object_union)
    # Concrete sanity check the divergence is actually exercised: the TT-only
    # drop must be present in both the global union and the manual union.
    assert ("渠道库存", "渠道库存") in global_drops
    assert ("渠道库存", "渠道库存") in per_object_union
    print("  drops_before(no object) == union of drops_before(each object)")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
