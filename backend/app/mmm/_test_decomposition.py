"""The decomposition identity, and what each driver is measured against.

Run: ``PYTHONPATH=. .venv/bin/python -m app.mmm._test_decomposition``

Two properties have to hold together, and only holding one of them is how the
reference case ended up reporting 竞品ND at −1907% while still "summing to 100":

1. ``baseline_pct + Σ contribution_pct == 100`` — the decomposition accounts for
   all of Y, so a share is a share of something real.
2. Every factor-tree driver keeps **its own** contribution, and a level driver
   (price, distribution rate, temperature) is measured against the level it
   actually sits at rather than against zero. Merging such drivers into the
   baseline would work here and break on the next project, whose factor tree
   names different things.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.mmm.engine import _decomposition, _reference_level
from app.mmm.ols import fit_ols


class _Frame:
    """The slice of ModelFrame the decomposition actually reads."""

    def __init__(self, frame: pd.DataFrame, x_cols: list[str],
                 spend_cols: list[str], y_col: str = "y") -> None:
        self.frame = frame
        self.x_cols = x_cols
        self.spend_cols = spend_cols
        self.y_col = y_col
        self.meta = {c: {"metric": c, "metric_type": "spending" if c in spend_cols else "X"}
                     for c in x_cols}


def _case() -> tuple[_Frame, pd.DataFrame, object, list[str]]:
    """Spend that goes to zero, a price that never does, and a trend control."""
    n = 36
    rng = np.random.default_rng(11)
    spend = np.where(rng.random(n) < 0.4, 0.0, rng.uniform(50, 200, n))
    price = rng.uniform(3.4, 3.9, n)          # never near zero
    trend = np.arange(n, dtype=float)
    # A large intercept offset by a large price term — the shape the reference
    # case has, and the one that makes a zero-referenced price term worth several
    # hundred percent of Y on its own.
    y = 5200.0 + 2.5 * spend - 1200.0 * price + 1.5 * trend + rng.normal(0, 5, n)

    frame = pd.DataFrame({"y": y, "spend": spend, "price": price, "_trend": trend})
    X = frame[["spend", "price", "_trend"]]
    res = fit_ols(X, frame["y"].to_numpy(dtype=float))
    mf = _Frame(frame, x_cols=["spend", "price"], spend_cols=["spend"])
    return mf, X, res, ["_trend"]


def test_reference_is_zero_for_spend_and_the_floor_for_a_level() -> None:
    mf, X, _res, _ctrl = _case()
    ref_spend, kind_spend = _reference_level(mf, X, "spend")
    ref_price, kind_price = _reference_level(mf, X, "price")
    assert (ref_spend, kind_spend) == (0.0, "zero"), (ref_spend, kind_spend)
    assert kind_price == "min" and ref_price > 3.0, (ref_price, kind_price)


def test_identity_holds() -> None:
    mf, X, res, ctrl = _case()
    baseline, contrib, _basis = _decomposition(mf, X, res, ctrl)
    total = baseline + sum(contrib.values())
    assert abs(total - 100.0) < 0.01, f"baseline + Σcontribution = {total}, not 100"


def test_a_level_driver_no_longer_swallows_the_decomposition() -> None:
    """Measured against zero, the price term alone is worth about −250% of Y."""
    mf, X, res, ctrl = _case()
    _baseline, contrib, _basis = _decomposition(mf, X, res, ctrl)

    against_zero = 100.0 * float(res.coef["price"]) * float(X["price"].mean()) / float(
        mf.frame["y"].mean())
    assert against_zero < -100.0, f"fixture is not exercising the bug ({against_zero:.1f}%)"
    assert abs(contrib["price"]) < 50.0, (
        f"price still swallows the decomposition: {contrib['price']:.1f}%")


def test_every_driver_keeps_its_own_share() -> None:
    """No factor is folded away — the next project's tree names other things."""
    mf, X, res, ctrl = _case()
    _baseline, contrib, basis = _decomposition(mf, X, res, ctrl)
    assert set(contrib) == {"spend", "price"}, set(contrib)
    assert set(basis) == {"spend", "price"}, set(basis)
    assert "_trend" not in contrib, "engine-added controls are not factor-tree drivers"


def test_spend_contribution_is_unchanged_by_the_reference_rule() -> None:
    """Spend already had zero as its reference, so its share must not move."""
    mf, X, res, ctrl = _case()
    _baseline, contrib, _basis = _decomposition(mf, X, res, ctrl)
    expected = 100.0 * float(res.coef["spend"]) * float(X["spend"].mean()) / float(
        mf.frame["y"].mean())
    assert abs(contrib["spend"] - expected) < 1e-6, (contrib["spend"], expected)


def main() -> int:
    for fn in (test_reference_is_zero_for_spend_and_the_floor_for_a_level,
               test_identity_holds,
               test_a_level_driver_no_longer_swallows_the_decomposition,
               test_every_driver_keeps_its_own_share,
               test_spend_contribution_is_unchanged_by_the_reference_rule):
        fn()
        print(f"ok  {fn.__name__}")
    print("all decomposition tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
