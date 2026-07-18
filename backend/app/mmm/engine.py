"""MMM engine: transform -> fit OLS -> decompose, ROI, response curves, validation.

Everything is computed from the input data; nothing is hardcoded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # avoid a runtime import cycle (domain.models is not an mmm dep)
    from app.domain.models import OlsParams

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


def _build_controls(mf: ModelFrame, params: "OlsParams | None") -> pd.DataFrame:
    """Trend / seasonality control columns for one model frame.

    Controls enter the design matrix **raw** — never adstocked or saturated — and
    fold into the baseline in :func:`_decomposition`. Their job is to absorb the
    trend and seasonal signal so the paid drivers do not, which is what keeps
    driver coefficients correctly signed and contributions interpretable.
    """
    idx = mf.frame.index
    n = len(idx)
    out: dict[str, np.ndarray] = {}
    if params is None:
        return pd.DataFrame(index=idx)

    t = np.arange(n, dtype=float)
    if getattr(params, "trend", "none") == "linear" and n > 1:
        out["_trend"] = t / max(1.0, n - 1.0)

    season = getattr(params, "seasonality", "none")
    if season == "fourier":
        k_max = max(1, int(getattr(params, "fourier_k", 2) or 1))
        for k in range(1, k_max + 1):
            out[f"_sin{k}"] = np.sin(2.0 * np.pi * k * t / 12.0)
            out[f"_cos{k}"] = np.cos(2.0 * np.pi * k * t / 12.0)
    elif season == "dummies":
        # Month-of-year dummies, first level dropped to avoid collinearity with
        # the intercept. Expensive in df on a short series — the panel warns.
        # The index is yyyymm; guard against a non-conforming key rather than
        # silently emitting one "month" level per period.
        months = [int(m) % 100 for m in idx]
        if all(1 <= m <= 12 for m in months):
            for m in sorted(set(months))[1:]:
                out[f"_m{m:02d}"] = np.array([1.0 if mm == m else 0.0 for mm in months])

    # Structural-event dummies from the 2.3 anomaly review. A window the human
    # explained as a business event gets its own column, so the paid variables
    # are not left explaining a spike marketing did not cause.
    for i, ev in enumerate(getattr(params, "events", None) or []):
        start, end = int(getattr(ev, "start", 0)), int(getattr(ev, "end", 0))
        if not start or not end:
            continue
        col = np.array([1.0 if start <= int(m) <= end else 0.0 for m in idx])
        out[f"_ev{i}"] = col

    ctrl = pd.DataFrame(out, index=idx)
    # Drop constant controls (no variance → breaks the normal equations). An
    # event window covering every period (or none) lands here.
    keep = [c for c in ctrl.columns if float(np.std(ctrl[c].to_numpy(dtype=float))) > 0]
    return ctrl[keep]


def _decomposition(
    mf: ModelFrame, X: pd.DataFrame, res: OLSResult, control_cols: list[str] | None = None
) -> tuple[float, dict[str, float]]:
    """Contribution share per driver + baseline, as a share of ACTUAL Y.

    contribution_c = Σ_t(coef_c · transformed_x_c[t]) / Σ_t(actual Y[t])
                   — the standard "share of sales" decomposition. Normalising by
    actual Y (rather than by ``intercept + Σcomponents``) keeps the shares on a
    stable, positive denominator.

    Trend/seasonality controls are NOT drivers: their components fold into the
    baseline, so only real marketing/commercial factors carry a contribution.
    """
    controls = set(control_cols or [])
    components: dict[str, float] = {}
    for c in mf.x_cols:
        components[c] = float(res.coef[c] * X[c].to_numpy(dtype=float).mean())

    baseline = float(res.intercept)
    for c in controls:
        if c in res.coef and c in X.columns:
            baseline += float(res.coef[c] * X[c].to_numpy(dtype=float).mean())

    y_mean = float(np.mean(mf.frame[mf.y_col].to_numpy(dtype=float)))
    total = y_mean if y_mean != 0 else (baseline + sum(components.values()))
    if not total:
        total = sum(abs(v) for v in components.values()) + abs(baseline) or 1.0
    baseline_pct = 100.0 * baseline / total
    contribution = {c: 100.0 * v / total for c, v in components.items()}
    return baseline_pct, contribution


def _roi(
    mf: ModelFrame, X: pd.DataFrame, res: OLSResult, price_per_unit: float | None = None
) -> tuple[dict[str, float], str]:
    """ROI per paid channel = incremental **revenue** / total spend.

    ``incremental = coef · Σ(transformed spend)`` is the counterfactual lift in Y
    from zeroing that channel. Converting it to revenue depends on what Y is:

    * Y is money (RMB / value / GMV)  → incremental is already revenue → true ROI.
    * Y is volume + ``price_per_unit`` → incremental × price → true ROI.
    * Y is volume, no price            → ROI stays volume-per-spend; the caller
      must label the unit and must NOT compare it to money ROI benchmarks.

    Returns ``(roi, unit)`` where unit is "revenue/spend" or "volume/spend".
    """
    money = mf.y_is_money
    price = None if money else (price_per_unit if (price_per_unit or 0) > 0 else None)
    unit = "revenue/spend" if (money or price) else "volume/spend"

    roi: dict[str, float] = {}
    for c in mf.spend_cols:
        spend = float(mf.frame[c].to_numpy(dtype=float).sum())
        incremental = float(res.coef[c] * X[c].to_numpy(dtype=float).sum())
        if price:
            incremental *= float(price)
        if spend > 0:
            roi[c] = incremental / spend
    return roi, unit


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
    # Only driver columns carry a metric label — trend/seasonality controls are
    # expected to correlate with each other and are not a modelling defect.
    high_vif = {c: v for c, v in res.vif.items()
                if c in mf.meta and np.isfinite(v) and v > 10}
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
    exclude: frozenset[tuple[str, str]] | None = None,
    y_metric: str | None = None,
    include: frozenset[str] | None = None,
    params: "OlsParams | None" = None,
) -> MmmModelResult:
    """Full MMM pipeline for one model object.

    Args:
        long_df: tidy LONG dataframe.
        model_object: channel grouping, e.g. "MT", "TT", "AFH", "EC+O2O".
        adstock: geometric carryover decay in [0, 1).
        hill_half: saturation half-point as a fraction of mean adstocked spend
            (e.g. 1.0 = half-saturation at the mean). ``None`` disables Hill.
        exclude: driver ``(norm_l4, norm_metric)`` pairs to drop before fitting.
        y_metric: explicit response metric (2.5y). ``None`` → auto-pick.
        include: explicit driver metric names (2.5x). ``None`` → auto-select.
        params: :class:`OlsParams` — transforms + trend/seasonality controls.
            When given, its ``adstock``/``saturation``/``hill_half`` override the
            positional args, and its controls enter the design matrix.
    """
    if params is not None:
        adstock = float(getattr(params, "adstock", adstock))
        hill_half = (float(getattr(params, "hill_half", 1.0))
                     if getattr(params, "saturation", "hill") == "hill" else None)

    mf = build_model_frame(long_df, model_object, exclude=exclude,
                           y_metric=y_metric, include=include,
                           caps=list(getattr(params, "caps", None) or []))
    X, halves = _transform_drivers(mf, adstock, hill_half)
    y = mf.frame[mf.y_col].to_numpy(dtype=float)

    # Trend / seasonality controls ride alongside the drivers in the design
    # matrix but are not drivers: no transform, no ROI, folded into baseline.
    controls = _build_controls(mf, params)
    control_cols = list(controls.columns)
    if control_cols:
        X = pd.concat([X, controls], axis=1)

    # Degrees-of-freedom guard — a wide design on a short series is exactly how
    # the old auto-fit produced offsetting coefficients and a negative baseline.
    n_params = 1 + len(mf.x_cols) + len(control_cols)
    if mf.n_obs <= n_params + 1:
        raise ValueError(
            f"'{model_object}': {mf.n_obs} months cannot identify {n_params} parameters "
            f"({len(mf.x_cols)} variables + {len(control_cols)} controls + intercept). "
            "Select fewer model variables or simpler controls."
        )

    res = fit_ols(X, y)
    baseline_pct, contribution = _decomposition(mf, X, res, control_cols)
    price = getattr(params, "price_per_unit", None) if params is not None else None
    roi, roi_unit = _roi(mf, X, res, price)
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
            "y_metric": mf.y_metric,
            "y_metric_type": mf.y_metric_type,
            "y_is_money": mf.y_is_money,
            "roi_unit": roi_unit,
            "drivers_meta": mf.meta,
            "spend_cols": mf.spend_cols,
            "control_cols": control_cols,
            "df_remaining": int(mf.n_obs - n_params),
            "tvalues": res.tvalues,
            "pvalues": res.pvalues,
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


def make_candidates(
    long_df: pd.DataFrame,
    model_object: str,
    n: int = 3,
    *,
    exclude: frozenset[tuple[str, str]] | None = None,
    y_metric: str | None = None,
    include: frozenset[str] | None = None,
    params: "OlsParams | None" = None,
) -> list[MmmModelResult]:
    """Produce ``n`` candidate models by varying adstock + saturation.

    Candidates differ in carryover/saturation assumptions, giving distinct fit
    and decomposition profiles for an analyst to compare. Everything *else* is
    held fixed at what S2 resolved — the same response, the same variables, the
    same controls the human confirmed — so the candidates differ only in the
    assumption they are meant to probe. Training on a different variable set to
    the one signed off at 2.5 would make the whole S2 review decorative.
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
        # The preset owns carryover/saturation; the confirmed params own the
        # trend/seasonality controls and the ROI unit price.
        p = None if params is None else params.model_copy(update={
            "adstock": adstock,
            "saturation": "hill" if hill is not None else "none",
            "hill_half": hill if hill is not None else 1.0,
        })
        try:
            out.append(run_mmm(long_df, model_object, adstock=adstock, hill_half=hill,
                               exclude=exclude, y_metric=y_metric, include=include, params=p))
        except (ValueError, np.linalg.LinAlgError) as exc:
            out.append(_error_result(model_object, str(exc)))
        if len(out) >= n:
            break
    return out
