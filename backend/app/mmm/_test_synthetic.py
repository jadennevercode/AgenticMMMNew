"""Synthetic correctness tests for transforms + OLS.

Run: .venv/bin/python -m app.mmm._test_synthetic
We construct data with a known ground truth and assert recovery.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.mmm.ols import fit_ols
from app.mmm.transforms import adstock_geometric, hill_saturation, standardize


def _check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return cond


def test_adstock() -> bool:
    x = np.array([1.0, 0.0, 0.0, 0.0])
    out = adstock_geometric(x, 0.5)
    expected = np.array([1.0, 0.5, 0.25, 0.125])
    ok = np.allclose(out, expected)
    ok &= np.isclose(adstock_geometric(x, 0.0)[0], 1.0) and adstock_geometric(x, 0.0)[1] == 0.0
    return _check("adstock_geometric decay=0.5 impulse", ok, f"got {out.tolist()}")


def test_hill() -> bool:
    x = np.array([0.0, 5.0, 10.0, 1e9])
    out = hill_saturation(x, half=5.0, slope=1.0)
    # at x=half response=0.5; at 0 -> 0; at inf -> ~1
    ok = np.isclose(out[0], 0.0) and np.isclose(out[1], 0.5) and out[3] > 0.999
    ok &= bool(np.all(np.diff(out) >= 0))  # monotonic increasing
    return _check("hill_saturation half=5 slope=1", ok, f"got {out.round(3).tolist()}")


def test_standardize() -> bool:
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    z = standardize(x)
    ok = np.isclose(z.mean(), 0.0) and np.isclose(z.std(), 1.0)
    ok &= np.allclose(standardize(np.array([7.0, 7.0, 7.0])), 0.0)
    return _check("standardize zero-mean unit-var", ok, f"mean={z.mean():.3f} std={z.std():.3f}")


def test_ols_perfect_fit() -> bool:
    rng = np.random.default_rng(42)
    n = 60
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    x3 = rng.normal(0, 1, n)
    y = 3.0 + 2.0 * x1 - 1.5 * x2 + 0.0 * x3  # clean, no noise
    X = pd.DataFrame({"x1": x1, "x2": x2, "x3": x3})
    res = fit_ols(X, y)
    ok = res.r2 > 0.9999
    ok &= np.isclose(res.intercept, 3.0, atol=1e-6)
    ok &= np.isclose(res.coef["x1"], 2.0, atol=1e-6)
    ok &= np.isclose(res.coef["x2"], -1.5, atol=1e-6)
    return _check(
        "OLS recovers true coefficients on clean data",
        ok,
        f"R2={res.r2:.6f} b0={res.intercept:.4f} b1={res.coef['x1']:.4f} b2={res.coef['x2']:.4f}",
    )


def test_ols_noise_and_mape() -> bool:
    rng = np.random.default_rng(7)
    n = 120
    x1 = rng.normal(10, 2, n)
    y_true = 50 + 4 * x1
    y = y_true + rng.normal(0, 1, n)
    X = pd.DataFrame({"x1": x1})
    res = fit_ols(X, y)
    ok = 0.95 < res.r2 <= 1.0
    ok &= res.mape < 5.0
    ok &= 1.5 < res.durbin_watson < 2.5  # iid noise => DW ~ 2
    return _check(
        "OLS noisy data: high R2, low MAPE, DW~2",
        ok,
        f"R2={res.r2:.4f} MAPE={res.mape:.3f}% DW={res.durbin_watson:.3f}",
    )


def test_vif_collinearity() -> bool:
    rng = np.random.default_rng(1)
    n = 100
    x1 = rng.normal(0, 1, n)
    x2 = x1 + rng.normal(0, 0.01, n)  # near-duplicate => huge VIF
    x3 = rng.normal(0, 1, n)
    y = x1 + x3 + rng.normal(0, 0.1, n)
    X = pd.DataFrame({"x1": x1, "x2": x2, "x3": x3})
    res = fit_ols(X, y)
    ok = res.vif["x1"] > 50 and res.vif["x2"] > 50  # collinear pair
    ok &= res.vif["x3"] < 5  # independent
    return _check(
        "VIF flags collinear columns, spares independent",
        ok,
        f"vif x1={res.vif['x1']:.1f} x2={res.vif['x2']:.1f} x3={res.vif['x3']:.2f}",
    )


def test_dw_autocorrelated() -> bool:
    # Strongly autocorrelated residuals -> DW well below 2.
    n = 100
    rng = np.random.default_rng(3)
    e = np.zeros(n)
    for t in range(1, n):
        e[t] = 0.9 * e[t - 1] + rng.normal(0, 1)
    x1 = rng.normal(0, 1, n)
    y = 2 * x1 + e
    res = fit_ols(pd.DataFrame({"x1": x1}), y)
    ok = res.durbin_watson < 1.5
    return _check("DW detects autocorrelation (<1.5)", ok, f"DW={res.durbin_watson:.3f}")


def main() -> int:
    print("=== SYNTHETIC TESTS (transforms + OLS) ===")
    results = [
        test_adstock(),
        test_hill(),
        test_standardize(),
        test_ols_perfect_fit(),
        test_ols_noise_and_mape(),
        test_vif_collinearity(),
        test_dw_autocorrelated(),
    ]
    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
