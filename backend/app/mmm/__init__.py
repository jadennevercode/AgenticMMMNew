"""Dependency-light OLS-based Marketing Mix Modeling (MMM) engine.

Public API
----------
Transforms:   adstock_geometric, hill_saturation, standardize
OLS:          fit_ols, OLSResult
Pivot:        build_model_frame, ModelFrame
Engine:       run_mmm, run_all_objects, make_candidates, MmmModelResult

All results are computed from input data via numpy ``lstsq`` — no statsmodels,
no hardcoded/mock numbers.

Example
-------
    >>> from app.mmm import run_mmm, build_model_frame
    >>> result = run_mmm(long_df, "MT", adstock=0.5, hill_half=1.0)
    >>> result.r2, result.contribution, result.roi, result.red_flags
"""
from __future__ import annotations

from app.mmm.engine import (
    MmmModelResult,
    make_candidates,
    run_all_objects,
    run_mmm,
)
from app.mmm.ols import OLSResult, fit_ols
from app.mmm.pivot import (
    CN_TO_EN,
    LONG_COLUMNS,
    ModelFrame,
    build_model_frame,
    driver_candidates,
    is_money_metric,
    is_volume_metric_type,
    y_candidates,
)
from app.mmm.transforms import adstock_geometric, hill_saturation, standardize

__all__ = [
    # transforms
    "adstock_geometric", "hill_saturation", "standardize",
    # ols
    "fit_ols", "OLSResult",
    # pivot
    "build_model_frame", "ModelFrame", "LONG_COLUMNS", "CN_TO_EN",
    "y_candidates", "driver_candidates", "is_money_metric", "is_volume_metric_type",
    # engine
    "run_mmm", "run_all_objects", "make_candidates", "MmmModelResult",
]
