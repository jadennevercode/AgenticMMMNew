"""L4-level ROI: numerator from the in-model indicator, denominator from the
L4's Spending series — whether or not that Spending column is in the model.

Run: .venv/bin/python -m app.mmm._test_l4_roi
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.mmm.pivot import build_model_frame


def _check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return bool(cond)


def make_long(n: int = 36, seed: int = 7) -> pd.DataFrame:
    """One model object 'MT', one L4 'TV' carrying both a spend and an
    exposure metric that are proportional (exposure = spend * 10), plus an
    unrelated L4 'Price' so the design matrix has a second driver."""
    rng = np.random.default_rng(seed)
    months = [202000 + 100 * (i // 12) + (i % 12) + 1 for i in range(n)]
    months = [m if m % 100 <= 12 else m for m in months]
    spend = rng.uniform(80.0, 220.0, n)
    price = rng.uniform(9.0, 11.0, n)
    y = 500.0 + 2.0 * spend - 15.0 * price + rng.normal(0, 3.0, n)

    rows: list[dict] = []
    def add(metric: str, mtype: str, l1: str, l4: str, vals: np.ndarray) -> None:
        for m, v in zip(months, vals):
            rows.append({
                "task_name": "t", "brand": "B", "province_group": "P",
                "channel_type": "MT", "channel": "MT",
                "year": m // 100, "month": m, "source": "synthetic",
                "l1": l1, "l2": "", "l3": "", "l4": l4,
                "l5": "", "l6": "", "l7": "", "l8": "",
                "metric_type": mtype, "metric": metric, "value": float(v),
            })
    add("本品销量", "箱数", "KPI", "KPI", y)
    add("TV花费", "spending", "MARKETING FACTOR", "TV", spend)
    add("TV曝光量", "X", "MARKETING FACTOR", "TV", spend * 10.0)
    add("平均售价", "X", "COMMERCIAL FACTOR", "Price", price)
    return pd.DataFrame(rows)


def test_l4_spend_collected() -> bool:
    df = make_long()
    mf = build_model_frame(df, "MT")
    got = mf.l4_spend
    ok = "tv" in got
    ok &= "price" not in got          # no spend metric under Price
    if ok:
        s = got["tv"]
        ok &= len(s) == 36
        ok &= np.isclose(float(s.sum()), float(
            df[df["metric"] == "TV花费"]["value"].sum()))
    return _check("build_model_frame collects per-L4 spend", ok,
                  f"keys={sorted(got)}")


def test_l4_spend_excluded_from_design() -> bool:
    """The spend series is a denominator, not a driver: collecting it must not
    change which columns the model fits."""
    df = make_long()
    mf = build_model_frame(df, "MT", include=frozenset({"tv曝光量"}))
    ok = mf.x_cols == ["TV曝光量"]
    ok &= "tv" in mf.l4_spend        # still collected though not in the model
    return _check("l4_spend does not enter x_cols", ok, f"x_cols={mf.x_cols}")


def main() -> int:
    results = [test_l4_spend_collected(), test_l4_spend_excluded_from_design()]
    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
