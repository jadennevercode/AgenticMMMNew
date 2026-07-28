"""Dependency-light OLS regression via numpy ``lstsq``.

Computes the diagnostics an MMM needs: R2, adjusted R2, MAPE, Durbin-Watson,
and per-regressor VIF. No statsmodels.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

__all__ = [
    "OLSResult",
    "fit_ols",
    "durbin_watson",
    "variance_inflation_factors",
    "t_pvalue",
]


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-12:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b) via the Numerical-Recipes ``betai``."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_beta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(ln_beta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_pvalue(t: float, dof: int) -> float:
    """Two-sided p-value for a t-statistic with ``dof`` degrees of freedom.

    p = I_{dof/(dof+t^2)}(dof/2, 1/2). Returns ``nan`` for non-positive dof or a
    nan statistic. No scipy dependency.
    """
    if dof <= 0 or t != t:  # dof guard + NaN check
        return float("nan")
    x = dof / (dof + float(t) * float(t))
    return float(_betainc(dof / 2.0, 0.5, x))


@dataclass
class OLSResult:
    coef: dict[str, float]
    intercept: float
    r2: float
    adj_r2: float
    mape: float
    durbin_watson: float
    vif: dict[str, float]
    fitted: list[float]
    residuals: list[float]
    n: int
    p: int
    se: dict[str, float] = field(default_factory=dict)
    tvalues: dict[str, float] = field(default_factory=dict)
    pvalues: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "coef": self.coef,
            "intercept": self.intercept,
            "r2": self.r2,
            "adj_r2": self.adj_r2,
            "mape": self.mape,
            "durbin_watson": self.durbin_watson,
            "vif": self.vif,
            "se": self.se,
            "tvalues": self.tvalues,
            "pvalues": self.pvalues,
            "n": self.n,
            "p": self.p,
        }


def durbin_watson(residuals: np.ndarray) -> float:
    """DW statistic for residual autocorrelation. ~2 = no autocorrelation."""
    r = np.asarray(residuals, dtype=float)
    if r.size < 2:
        return float("nan")
    diff = np.diff(r)
    denom = np.sum(r ** 2)
    if denom == 0:
        return float("nan")
    return float(np.sum(diff ** 2) / denom)


def variance_inflation_factors(X: pd.DataFrame) -> dict[str, float]:
    """VIF per regressor: regress each column on the others, VIF = 1/(1-R2).

    High VIF (>5-10) signals multicollinearity.
    """
    cols = list(X.columns)
    out: dict[str, float] = {}
    if len(cols) < 2:
        return {c: 1.0 for c in cols}
    Xv = X.to_numpy(dtype=float)
    for i, c in enumerate(cols):
        y = Xv[:, i]
        others = np.delete(Xv, i, axis=1)
        A = np.column_stack([np.ones(others.shape[0]), others])
        try:
            beta, *_ = np.linalg.lstsq(A, y, rcond=None)
            pred = A @ beta
            ss_res = np.sum((y - pred) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
            out[c] = float(1.0 / (1.0 - r2)) if r2 < 1.0 else float("inf")
        except np.linalg.LinAlgError:
            out[c] = float("nan")
    return out


def _mape(y: np.ndarray, fitted: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    mask = y != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y[mask] - fitted[mask]) / y[mask])) * 100.0)


def fit_ols(X: pd.DataFrame, y: np.ndarray) -> OLSResult:
    """Fit OLS with an intercept via ``np.linalg.lstsq``.

    Args:
        X: design matrix (rows = observations, named columns = regressors).
        y: response vector.

    Returns an :class:`OLSResult` with coefficients and diagnostics.
    """
    cols = list(X.columns)
    Xv = X.to_numpy(dtype=float)
    yv = np.asarray(y, dtype=float)
    n = Xv.shape[0]
    p = Xv.shape[1]
    if n <= p + 1:
        raise ValueError(f"Need more observations ({n}) than parameters ({p + 1})")

    A = np.column_stack([np.ones(n), Xv])
    beta, *_ = np.linalg.lstsq(A, yv, rcond=None)
    fitted = A @ beta
    residuals = yv - fitted

    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((yv - yv.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    dof = n - p - 1
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / dof if dof > 0 else float("nan")

    # Standard errors, t-values and two-sided p-values.
    se_map: dict[str, float] = {}
    t_map: dict[str, float] = {}
    p_map: dict[str, float] = {}
    sigma2 = ss_res / dof if dof > 0 else float("nan")
    try:
        cov = sigma2 * np.linalg.inv(A.T @ A)
        se_all = np.sqrt(np.clip(np.diag(cov), 0, None))
        for i, c in enumerate(cols):
            se_map[c] = float(se_all[i + 1])
            t_map[c] = float(beta[i + 1] / se_all[i + 1]) if se_all[i + 1] > 0 else float("nan")
            p_map[c] = t_pvalue(t_map[c], dof)
    except np.linalg.LinAlgError:
        se_map = {c: float("nan") for c in cols}
        t_map = {c: float("nan") for c in cols}
        p_map = {c: float("nan") for c in cols}

    coef = {c: float(beta[i + 1]) for i, c in enumerate(cols)}
    vif = variance_inflation_factors(X)

    return OLSResult(
        coef=coef,
        intercept=float(beta[0]),
        r2=float(r2),
        adj_r2=float(adj_r2),
        mape=_mape(yv, fitted),
        durbin_watson=durbin_watson(residuals),
        vif=vif,
        fitted=[float(v) for v in fitted],
        residuals=[float(v) for v in residuals],
        n=int(n),
        p=int(p),
        se=se_map,
        tvalues=t_map,
        pvalues=p_map,
    )
