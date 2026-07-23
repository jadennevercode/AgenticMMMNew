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

_MONTHS = [202301 + m if (202301 + m) % 100 <= 12 else 202400 + ((202301 + m) % 100)
           for m in range(24)]  # 24 contiguous yyyymm from 2023-01


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
    assert model_objects(st) == ["MT", "TT"], model_objects(st)
    print("  fixture: MT + TT bound")


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
