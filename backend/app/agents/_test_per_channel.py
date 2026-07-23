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
