"""MMM engine: transform -> fit OLS -> decompose, ROI, response curves, validation.

Everything is computed from the input data; nothing is hardcoded.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.mmm.ols import OLSResult, fit_ols
from app.mmm.pivot import ModelFrame, build_model_frame
from app.mmm.transforms import adstock_geometric, hill_saturation

__all__ = ["MmmModelResult", "run_mmm", "run_all_objects", "make_candidates"]

# Validation benchmarks (from design docs).
R2_TARGET = (0.85, 0.95)
MAPE_TARGET = (5.0, 15.0)
DW_TARGET = (1.5, 2.5)
RESPONSE_GRID_POINTS = 12
RESPONSE_GRID_MAX_MULT = 2.0  # curve spans 0 .. 2x observed mean spend


@dataclass
class MmmModelResult:
    model_object: str
    n_obs: int
    drivers: list[str]
    coefficients: dict[str, float]
    r2: float
    adj_r2: float
    mape: float
    durbin_watson: float
    vif: dict[str, float]
    baseline_pct: float
    contribution: dict[str, float]
    roi: dict[str, float]
    response_curves: dict[str, list[tuple[float, float]]]
    red_flags: list[str]
    # Goodness-of-fit series for the actual-vs-predicted + residual charts.
    periods: list[str] = field(default_factory=list)
    actual: list[float] = field(default_factory=list)
    fitted: list[float] = field(default_factory=list)
    residuals: list[float] = field(default_factory=list)
    # Period-over-period contribution delta (due-to / waterfall).
    due_to: dict = field(default_factory=dict)
    # provenance / tuning so candidates are distinguishable.
    adstock: float = 0.5
    hill_half_pct: float | None = None
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "model_object": self.model_object,
            "n_obs": self.n_obs,
            "drivers": self.drivers,
            "coefficients": self.coefficients,
            "r2": self.r2,
            "adj_r2": self.adj_r2,
            "mape": self.mape,
            "durbin_watson": self.durbin_watson,
            "vif": self.vif,
            "baseline_pct": self.baseline_pct,
            "contribution": self.contribution,
            "roi": self.roi,
            "response_curves": {k: [list(p) for p in v] for k, v in self.response_curves.items()},
            "red_flags": self.red_flags,
            "periods": self.periods,
            "actual": self.actual,
            "fitted": self.fitted,
            "residuals": self.residuals,
            "due_to": self.due_to,
            "adstock": self.adstock,
            "hill_half_pct": self.hill_half_pct,
            "meta": self.meta,
        }


def _transform_drivers(
    mf: ModelFrame, adstock: float, hill_half: float | None
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Apply adstock then Hill saturation to each driver.

    Returns the transformed design matrix and the per-driver Hill ``half``
    actually used (so response curves can re-apply the same transform).
    """
    out: dict[str, np.ndarray] = {}
    halves: dict[str, float] = {}
    for c in mf.x_cols:
        raw = mf.frame[c].to_numpy(dtype=float)
        stocked = adstock_geometric(raw, adstock)
        if hill_half is not None and hill_half > 0:
            half = float(np.mean(stocked) * hill_half) if np.mean(stocked) > 0 else 0.0
            transformed = hill_saturation(stocked, half=half, slope=1.0) if half > 0 else stocked
            halves[c] = half
        else:
            transformed = stocked
            halves[c] = 0.0
        out[c] = transformed
    return pd.DataFrame(out, index=mf.frame.index), halves


def _decomposition(mf: ModelFrame, X: pd.DataFrame, res: OLSResult) -> tuple[float, dict[str, float]]:
    """Contribution share per driver + baseline, on the prediction scale.

    Driver contribution = mean(coef * transformed_x). Baseline = intercept.
    Shares are normalized by total predicted Y (sum of |components|-aware total).
    """
    components: dict[str, float] = {}
    for c in mf.x_cols:
        components[c] = float(res.coef[c] * X[c].to_numpy(dtype=float).mean())
    baseline = float(res.intercept)
    total = baseline + sum(components.values())
    if total == 0:
        total = sum(abs(v) for v in components.values()) + abs(baseline) or 1.0
    baseline_pct = 100.0 * baseline / total
    contribution = {c: 100.0 * v / total for c, v in components.items()}
    return baseline_pct, contribution


def _roi(mf: ModelFrame, X: pd.DataFrame, res: OLSResult) -> dict[str, float]:
    """ROI per paid channel = incremental sales / total spend.

    Incremental sales = coef * sum(transformed spend); spend = sum(raw spend).
    """
    roi: dict[str, float] = {}
    for c in mf.spend_cols:
        spend = float(mf.frame[c].to_numpy(dtype=float).sum())
        incremental = float(res.coef[c] * X[c].to_numpy(dtype=float).sum())
        if spend > 0:
            roi[c] = incremental / spend
    return roi


def _response_curves(
    mf: ModelFrame, res: OLSResult, adstock: float, halves: dict[str, float]
) -> dict[str, list[tuple[float, float]]]:
    """Predicted Y across a spend grid (0 .. 2x mean) per driver, others at mean."""
    curves: dict[str, list[tuple[float, float]]] = {}
    base_pred = res.intercept
    transformed_means: dict[str, float] = {}
    for c in mf.x_cols:
        raw = mf.frame[c].to_numpy(dtype=float)
        stocked = adstock_geometric(raw, adstock)
        if halves.get(c, 0.0) > 0:
            tm = float(hill_saturation(stocked, half=halves[c], slope=1.0).mean())
        else:
            tm = float(stocked.mean())
        transformed_means[c] = tm
        base_pred += res.coef[c] * tm

    for c in mf.x_cols:
        mean_spend = float(mf.frame[c].to_numpy(dtype=float).mean())
        grid = np.linspace(0.0, mean_spend * RESPONSE_GRID_MAX_MULT, RESPONSE_GRID_POINTS)
        pts: list[tuple[float, float]] = []
        for spend in grid:
            # transform a flat spend level through the same adstock steady-state.
            steady = spend / (1.0 - adstock) if adstock < 1.0 else spend
            if halves.get(c, 0.0) > 0:
                tval = float(hill_saturation(np.array([steady]), half=halves[c], slope=1.0)[0])
            else:
                tval = steady
            pred = base_pred - res.coef[c] * transformed_means[c] + res.coef[c] * tval
            pts.append((round(float(spend), 4), round(float(pred), 4)))
        curves[c] = pts
    return curves


def _red_flags(mf: ModelFrame, res: OLSResult, baseline_pct: float) -> list[str]:
    flags: list[str] = []
    if baseline_pct < 0:
        flags.append(f"Negative baseline ({baseline_pct:.1f}%): intercept below zero, model misspecified")
    for c in mf.x_cols:
        is_paid = mf.meta[c].get("is_spend", False)
        if is_paid and res.coef[c] < 0:
            flags.append(f"Wrong-sign coefficient on paid driver '{mf.meta[c]['metric']}' ({res.coef[c]:.4g} < 0)")
    if res.r2 < R2_TARGET[0]:
        flags.append(f"Low R2 ({res.r2:.3f} < {R2_TARGET[0]}): below 85% fit benchmark")
    if not (MAPE_TARGET[0] <= res.mape <= MAPE_TARGET[1]) and np.isfinite(res.mape):
        flags.append(f"MAPE {res.mape:.1f}% outside {MAPE_TARGET[0]}-{MAPE_TARGET[1]}% benchmark")
    if np.isfinite(res.durbin_watson) and not (DW_TARGET[0] <= res.durbin_watson <= DW_TARGET[1]):
        flags.append(f"Durbin-Watson {res.durbin_watson:.2f} outside {DW_TARGET[0]}-{DW_TARGET[1]} (autocorrelation)")
    high_vif = {c: v for c, v in res.vif.items() if np.isfinite(v) and v > 10}
    if high_vif:
        worst = max(high_vif, key=high_vif.get)
        flags.append(f"High multicollinearity: VIF('{mf.meta[worst]['metric']}')={high_vif[worst]:.1f} > 10")
    return flags


def _period_labels(mf: ModelFrame) -> list[str]:
    """Human-readable month labels (yyyy-mm) from the frame's yyyymm index."""
    labels: list[str] = []
    for m in mf.frame.index:
        try:
            mi = int(m)
            labels.append(f"{mi // 100}-{mi % 100:02d}")
        except (ValueError, TypeError):
            labels.append(str(m))
    return labels


def _due_to(mf: ModelFrame, X: pd.DataFrame, res: OLSResult, periods: list[str]) -> dict:
    """Period-over-period contribution delta (the 'due-to' / waterfall view).

    Splits the modeling window in half and, per driver, diffs the mean
    contribution (coef * transformed_x) of the recent half against the earlier
    half. Segment deltas sum to the predicted-Y delta (the baseline/intercept is
    constant, so it contributes no delta). Returns ``{}`` when the window is too
    short to split meaningfully.
    """
    n = len(periods)
    if n < 4:
        return {}
    mid = n // 2
    segments: list[dict] = []
    total_a = float(res.intercept)
    total_b = float(res.intercept)
    for c in mf.x_cols:
        contrib = res.coef[c] * X[c].to_numpy(dtype=float)
        a = float(contrib[:mid].mean())
        b = float(contrib[mid:].mean())
        total_a += a
        total_b += b
        delta = b - a
        segments.append({
            "source": str(mf.meta[c].get("metric", c))[:40],
            "delta": round(delta, 4),
            "direction": "up" if delta >= 0 else "down",
        })
    segments.sort(key=lambda s: -abs(s["delta"]))
    return {
        "period_a": f"{periods[0]}…{periods[mid - 1]}",
        "period_b": f"{periods[mid]}…{periods[-1]}",
        "value_a": round(total_a, 4),
        "value_b": round(total_b, 4),
        "segments": segments,
    }


def run_mmm(
    long_df: pd.DataFrame,
    model_object: str,
    *,
    adstock: float = 0.5,
    hill_half: float | None = None,
) -> MmmModelResult:
    """Full MMM pipeline for one model object.

    Args:
        long_df: tidy LONG dataframe.
        model_object: channel grouping, e.g. "MT", "TT", "AFH", "EC+O2O".
        adstock: geometric carryover decay in [0, 1).
        hill_half: saturation half-point as a fraction of mean adstocked spend
            (e.g. 1.0 = half-saturation at the mean). ``None`` disables Hill.
    """
    mf = build_model_frame(long_df, model_object)
    X, halves = _transform_drivers(mf, adstock, hill_half)
    y = mf.frame[mf.y_col].to_numpy(dtype=float)

    res = fit_ols(X, y)
    baseline_pct, contribution = _decomposition(mf, X, res)
    roi = _roi(mf, X, res)
    curves = _response_curves(mf, res, adstock, halves)
    flags = _red_flags(mf, res, baseline_pct)
    periods = _period_labels(mf)
    due_to = _due_to(mf, X, res, periods)

    return MmmModelResult(
        model_object=model_object,
        n_obs=mf.n_obs,
        drivers=mf.x_cols,
        coefficients=res.coef,
        r2=res.r2,
        adj_r2=res.adj_r2,
        mape=res.mape,
        durbin_watson=res.durbin_watson,
        vif=res.vif,
        baseline_pct=baseline_pct,
        contribution=contribution,
        roi=roi,
        response_curves=curves,
        red_flags=flags,
        periods=periods,
        actual=[round(float(v), 4) for v in y],
        fitted=[round(float(v), 4) for v in res.fitted],
        residuals=[round(float(v), 4) for v in res.residuals],
        due_to=due_to,
        adstock=adstock,
        hill_half_pct=hill_half,
        meta={
            "y_metric": mf.meta and "Y",
            "drivers_meta": mf.meta,
            "spend_cols": mf.spend_cols,
            "tvalues": res.tvalues,
        },
    )


def run_all_objects(long_df: pd.DataFrame, objects: list[str]) -> dict[str, MmmModelResult]:
    """Run the pipeline for several model objects; skip objects that fail."""
    results: dict[str, MmmModelResult] = {}
    for obj in objects:
        try:
            results[obj] = run_mmm(long_df, obj)
        except (ValueError, np.linalg.LinAlgError) as exc:
            results[obj] = _error_result(obj, str(exc))
    return results


def _error_result(model_object: str, msg: str) -> MmmModelResult:
    return MmmModelResult(
        model_object=model_object, n_obs=0, drivers=[], coefficients={},
        r2=float("nan"), adj_r2=float("nan"), mape=float("nan"),
        durbin_watson=float("nan"), vif={}, baseline_pct=float("nan"),
        contribution={}, roi={}, response_curves={},
        red_flags=[f"Model could not be built: {msg}"],
    )


def make_candidates(long_df: pd.DataFrame, model_object: str, n: int = 3) -> list[MmmModelResult]:
    """Produce ``n`` candidate models by varying adstock + saturation.

    Candidates differ in carryover/saturation assumptions, giving distinct fit
    and decomposition profiles for an analyst to compare.
    """
    presets = [
        (0.3, None),    # light carryover, linear
        (0.5, 1.0),     # medium carryover, half-saturation at mean
        (0.7, 0.5),     # heavy carryover, early saturation
        (0.2, 2.0),
        (0.6, 1.5),
    ]
    out: list[MmmModelResult] = []
    for adstock, hill in presets[:max(1, n)]:
        try:
            out.append(run_mmm(long_df, model_object, adstock=adstock, hill_half=hill))
        except (ValueError, np.linalg.LinAlgError) as exc:
            out.append(_error_result(model_object, str(exc)))
        if len(out) >= n:
            break
    return out
