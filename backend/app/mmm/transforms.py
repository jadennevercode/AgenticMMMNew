"""Marketing-mix transforms: adstock (carryover) and Hill saturation (diminishing returns).

All functions are pure and operate on numpy arrays. No mutation of inputs.
"""
from __future__ import annotations

import numpy as np

__all__ = ["adstock_geometric", "hill_saturation", "standardize"]


def adstock_geometric(x: np.ndarray, decay: float) -> np.ndarray:
    """Geometric adstock (carryover).

    a[t] = x[t] + decay * a[t-1]

    Models the lingering effect of marketing spend across periods. ``decay`` in
    [0, 1): 0 = no carryover, higher = longer memory.
    """
    x = np.asarray(x, dtype=float)
    if not 0.0 <= decay < 1.0:
        raise ValueError(f"decay must be in [0, 1), got {decay}")
    if x.ndim != 1:
        raise ValueError("adstock expects a 1-D array")
    out = np.empty_like(x)
    carry = 0.0
    for t in range(x.size):
        carry = x[t] + decay * carry
        out[t] = carry
    return out


def hill_saturation(x: np.ndarray, half: float, slope: float) -> np.ndarray:
    """Hill saturation curve (diminishing returns).

    f(x) = x^slope / (x^slope + half^slope)

    Maps spend to a 0..1 response. ``half`` is the spend at which response is
    50% of the maximum; ``slope`` controls steepness (S-shape). When ``half`` is
    not positive the input is returned unchanged (no saturation).
    """
    x = np.asarray(x, dtype=float)
    if slope <= 0:
        raise ValueError(f"slope must be > 0, got {slope}")
    if half is None or half <= 0:
        return x
    # Guard against negative inputs producing complex powers.
    xc = np.clip(x, 0.0, None)
    xp = np.power(xc, slope)
    hp = half ** slope
    denom = xp + hp
    out = np.divide(xp, denom, out=np.zeros_like(xp), where=denom > 0)
    return out


def standardize(x: np.ndarray) -> np.ndarray:
    """Z-score standardize a 1-D array. Constant arrays return all zeros."""
    x = np.asarray(x, dtype=float)
    mu = np.nanmean(x)
    sd = np.nanstd(x)
    if not np.isfinite(sd) or sd == 0:
        return np.zeros_like(x)
    return (x - mu) / sd
