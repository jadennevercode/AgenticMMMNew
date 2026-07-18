"""Pivot a LONG-format tidy MMM dataset into a wide monthly model frame.

A "model object" is a channel grouping (MT / TT / AFH / EC / O2O / EC+O2O ...).
For one object we build a monthly time series with one Y (sales/volume/offtake)
and several X driver columns (media spend / promotion / trade / distribution).

The frame is defensive: it aggregates duplicate (month) rows by sum, drops
all-NaN and constant columns, and requires >= MIN_MONTHS monthly observations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

__all__ = [
    "ModelFrame",
    "build_model_frame",
    "LONG_COLUMNS",
    "CN_TO_EN",
    "y_candidates",
    "driver_candidates",
    "is_money_metric",
    "is_volume_metric_type",
]

MIN_MONTHS = 12
# Keep the model identified (p < n) and interpretable: when a model object carries
# more candidate drivers than this, keep the ones most correlated with Y. Reference
# objects already sit at/under this, so this only bites wide per-project uploads.
MAX_DRIVERS = 12

# Canonical english long-format column names.
LONG_COLUMNS = [
    "task_name", "brand", "province_group", "channel_type", "channel",
    "year", "month", "source",
    "l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8",
    "metric_type", "metric", "value",
]

# Map the 19 Chinese source columns to canonical english names (order-aligned).
CN_TO_EN = {
    "Task name": "task_name", "品牌": "brand", "省份组别": "province_group",
    "渠道类型": "channel_type", "渠道": "channel", "年": "year", "月": "month",
    "数据源": "source",
    "数据类型Level1": "l1", "数据类型Level2": "l2", "数据类型Level3": "l3",
    "数据类型Level4": "l4", "数据类型Level5": "l5", "数据类型Level6": "l6",
    "数据类型Level7": "l7", "数据类型Level8": "l8",
    "METRICS类型": "metric_type", "METRICS": "metric", "VALUE": "value",
}

# metric_type tokens that indicate a Y (sales / volume / offtake / GMV) variable.
_Y_METRIC_TYPES = {"箱数", "volume", "value", "rmb", "gmv", "unit", "百分比箱数"}
_Y_KEYWORDS = ("offtake", "sales", "gmv", "出货", "完成", "volume", "箱数")
# Explicit Y / X role tags written by the per-project binding (data_binding).
_Y_TAGS = {"y", "kpi"}
_DRIVER_TAGS = {"x", "driver", "spending", "spend"}

# metric_type tokens that indicate paid spend (used for ROI).
_SPEND_TYPES = {"spending", "rmb"}
_SPEND_KEYWORDS = ("spend", "spending", "投放", "费用", "金额", "promotion")

# Response-unit classification (drives the ROI unit — see `is_money_metric`).
_VOLUME_TYPE_KEYWORDS = ("箱", "volume", "unit")
_MONEY_TYPE_KEYWORDS = ("rmb", "value", "gmv", "金额", "元")


def _clean_name(s: str) -> str:
    """Make a safe, short column name from a metric label."""
    s = str(s).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:60]


@dataclass
class ModelFrame:
    """Wide monthly frame for one model object.

    Attributes:
        model_object: channel grouping label.
        frame: wide df indexed by month (int yyyymm), Y + X columns.
        y_col: name of the response column.
        x_cols: names of driver columns.
        spend_cols: subset of x_cols that represent paid spend (ROI eligible).
        meta: per-column provenance (original metric label, metric_type, l1).
        y_metric: the source metric label chosen as the response.
        y_metric_type: its metric_type — decides whether Y is money (ROI unit).
    """
    model_object: str
    frame: pd.DataFrame
    y_col: str
    x_cols: list[str]
    spend_cols: list[str]
    meta: dict[str, dict] = field(default_factory=dict)
    y_metric: str = ""
    y_metric_type: str = ""

    @property
    def n_obs(self) -> int:
        return int(self.frame.shape[0])

    @property
    def y_is_money(self) -> bool:
        """True when Y is a monetary metric — then ROI is already Revenue/Spend."""
        return is_money_metric(self.y_metric_type)


def _resolve_object_filter(df: pd.DataFrame, model_object: str) -> pd.Series:
    """Boolean mask selecting rows for a model object (supports '+' unions)."""
    parts = [p.strip().upper() for p in str(model_object).split("+") if p.strip()]
    ct = df["channel_type"].astype("string").str.upper()
    return ct.isin(parts)


def _is_y_row(g: pd.DataFrame) -> pd.Series:
    l1 = g["l1"].astype("string").str.upper()
    mtype = g["metric_type"].astype("string").str.strip().str.lower()
    metric = g["metric"].astype("string").str.lower().fillna("")
    by_kpi = l1.eq("KPI")
    by_kw = metric.apply(lambda m: any(k in m for k in _Y_KEYWORDS))
    by_type = mtype.isin(_Y_METRIC_TYPES)
    by_tag = mtype.isin(_Y_TAGS)  # explicit Y tag from per-project binding
    return by_kpi | by_tag | (by_kw & by_type)


def is_volume_metric_type(metric_type: object) -> bool:
    """True for a volume/unit response (箱数 / volume / unit)."""
    t = str(metric_type).strip().lower()
    return any(k in t for k in _VOLUME_TYPE_KEYWORDS)


def is_money_metric(metric_type: object) -> bool:
    """True for a monetary response (RMB / value / GMV / 金额).

    Decides the ROI unit: a money Y makes ``coef·Σtransformed / Σspend`` a real
    增量Revenue/Spend; a volume Y needs a unit price to become one.
    """
    t = str(metric_type).strip().lower()
    if is_volume_metric_type(t):
        return False
    return any(k in t for k in _MONEY_TYPE_KEYWORDS)


def _pick_y_metric(ydf: pd.DataFrame) -> str:
    """Among Y candidates pick the metric with the best month coverage,
    preferring volume (箱数/volume) over value to keep units interpretable.

    This is only the *default* — 2.5 lets the human choose Y explicitly
    (``build_model_frame(y_metric=...)``); this fallback keeps legacy callers
    and un-configured projects working.
    """
    cov = ydf.groupby("metric")["month"].nunique()
    mtypes = ydf.groupby("metric")["metric_type"].first().str.lower()
    vol_pref = mtypes.apply(lambda t: 0 if any(k in t for k in ("箱", "volume", "unit")) else 1)
    ranked = pd.DataFrame({"cov": cov, "vol_pref": vol_pref})
    ranked = ranked.sort_values(["cov", "vol_pref"], ascending=[False, True])
    return str(ranked.index[0])


def y_candidates(long_df: pd.DataFrame, model_object: str) -> list[dict]:
    """Selectable response variables for a model object (2.5's Y step).

    Returns ``[{metric, metric_type, months, is_money, is_volume}]`` ordered the
    way ``_pick_y_metric`` ranks them, so the first entry is the AI default.
    """
    df = long_df
    if "value" not in df.columns and "VALUE" in df.columns:
        df = df.rename(columns=CN_TO_EN)
    df = df.copy()
    df["month"] = pd.to_numeric(df["month"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["month"])
    obj = df[_resolve_object_filter(df, model_object)]
    if obj.empty:
        return []
    ydf = obj[_is_y_row(obj)]
    if ydf.empty:
        return []
    out: list[dict] = []
    for metric, g in ydf.groupby("metric"):
        mtype = str(g["metric_type"].iloc[0])
        out.append({
            "metric": str(metric),
            "metric_type": mtype,
            "months": int(g["month"].nunique()),
            "is_money": is_money_metric(mtype),
            "is_volume": is_volume_metric_type(mtype),
        })
    default = _pick_y_metric(ydf)
    out.sort(key=lambda c: (c["metric"] != default, -c["months"], c["metric"]))
    return out


def _is_spend(metric_type: str, metric: str) -> bool:
    t = str(metric_type).strip().lower()
    m = str(metric).lower()
    return t in _SPEND_TYPES or any(k in m for k in _SPEND_KEYWORDS) or any(k in t for k in _SPEND_KEYWORDS)


def driver_candidates(long_df: pd.DataFrame, model_object: str) -> list[dict]:
    """Every driver metric usable for a model object (2.5's X step).

    Mirrors :func:`build_model_frame`'s driver predicate and ``MIN_MONTHS`` rule
    but applies **no** ``MAX_DRIVERS`` cap and no exclusions — this is the full
    candidate universe the human picks from.
    """
    df = long_df
    if "value" not in df.columns and "VALUE" in df.columns:
        df = df.rename(columns=CN_TO_EN)
    df = df.copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["month"] = pd.to_numeric(df["month"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["month", "value"])
    obj = df[_resolve_object_filter(df, model_object)]
    if obj.empty:
        return []

    y_rows = obj[_is_y_row(obj)]
    y_metric = _pick_y_metric(y_rows) if not y_rows.empty else ""

    l1u = obj["l1"].astype("string").str.upper()
    mtype = obj["metric_type"].astype("string").str.strip().str.lower()
    drv = obj[l1u.isin(["MARKETING FACTOR", "COMMERCIAL FACTOR"]) | mtype.isin(_DRIVER_TAGS)]
    drv = drv[~_is_y_row(drv) & (drv["metric"] != y_metric)]

    out: list[dict] = []
    for metric, g in drv.groupby("metric"):
        months = int(g["month"].nunique())
        if months < MIN_MONTHS:
            continue
        s = g.groupby("month")["value"].sum()
        if float(np.nanstd(s.to_numpy(dtype=float))) == 0.0:
            continue  # constant → uninformative, breaks VIF
        mt = str(g["metric_type"].iloc[0])
        out.append({
            "metric": str(metric),
            "metric_type": mt,
            "l1": str(g["l1"].iloc[0]),
            "l2": str(g["l2"].iloc[0]) if "l2" in g else "",
            "l3": str(g["l3"].iloc[0]) if "l3" in g else "",
            "l4": str(g["l4"].iloc[0]) if "l4" in g else "",
            "is_spend": _is_spend(mt, metric),
            "months": months,
        })
    return out


def _norm(s: object) -> str:
    return str(s).strip().lower() if s is not None else ""


def _winsorize_windows(y: pd.Series, caps: list) -> pd.Series:
    """Clip the response inside each 2.3 cap window to the series' own p95/p5.

    "Outlier capping" is a real intervention on the data, so it is deliberately
    narrow: only the windows the human accepted at 2.3a are touched, and only to
    the bounds the rest of the series already reaches. The alternative the human
    weighed against this is on the card — capping can flatten genuine growth.
    """
    if not caps or y.empty:
        return y
    hi, lo = float(y.quantile(0.95)), float(y.quantile(0.05))
    out = y.copy()
    for c in caps:
        start, end = int(getattr(c, "start", 0)), int(getattr(c, "end", 0))
        if not start or not end:
            continue
        mask = pd.Series([start <= int(m) <= end for m in out.index], index=out.index)
        out[mask] = out[mask].clip(lower=lo, upper=hi)
    return out


def build_model_frame(
    long_df: pd.DataFrame,
    model_object: str,
    *,
    exclude: frozenset[tuple[str, str]] | None = None,
    y_metric: str | None = None,
    include: frozenset[str] | None = None,
    caps: list | None = None,
) -> ModelFrame:
    """Pivot LONG -> wide monthly frame for one model object.

    Args:
        exclude: driver rows to drop before pivoting, keyed by ``(norm_l4,
            norm_metric)`` where ``norm = str(x).strip().lower()``. An entry with
            an empty ``l4`` (``("", metric)``) drops that metric under any L4.
        y_metric: the response metric to use. ``None`` falls back to
            :func:`_pick_y_metric` (volume-preferring auto-pick).
        include: normalized metric names the human selected as model variables.
            When given, ONLY these drivers are kept and the ``MAX_DRIVERS``
            correlation cap is skipped — the human's selection wins.
        caps: 2.3 cap windows (``OlsCapWindow``) whose response values are
            winsorized to the series' own p5/p95 before fitting.

    Raises ValueError when there is no Y variable or fewer than MIN_MONTHS rows.
    """
    df = long_df.copy()
    # Accept either english or chinese headers.
    if "value" not in df.columns and "VALUE" in df.columns:
        df = df.rename(columns=CN_TO_EN)
    missing = {"channel_type", "l1", "month", "metric", "metric_type", "value"} - set(df.columns)
    if missing:
        raise ValueError(f"long_df missing required columns: {sorted(missing)}")

    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["month"] = pd.to_numeric(df["month"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["month", "value"])

    mask = _resolve_object_filter(df, model_object)
    obj = df[mask]
    if obj.empty:
        raise ValueError(f"No rows for model object '{model_object}'")

    # --- Y selection: the human's choice wins; else volume-preferring auto-pick ---
    y_rows = obj[_is_y_row(obj)]
    if y_rows.empty:
        raise ValueError(f"No Y (sales/volume) metric found for '{model_object}'")
    if y_metric:
        chosen = y_rows[y_rows["metric"].astype("string").map(_norm) == _norm(y_metric)]
        if chosen.empty:
            raise ValueError(
                f"Selected Y metric '{y_metric}' has no rows for '{model_object}'")
        y_metric = str(chosen["metric"].iloc[0])
        y_rows = chosen
    else:
        y_metric = _pick_y_metric(y_rows)
    y_metric_type = str(y_rows[y_rows["metric"] == y_metric]["metric_type"].iloc[0])
    y_series = (
        y_rows[y_rows["metric"] == y_metric]
        .groupby("month")["value"].sum()
        .rename("Y")
    )
    # 2.3 'outlier capping' applies to the response, before anything is fitted.
    y_series = _winsorize_windows(y_series, caps or [])

    # --- X drivers: Marketing + Commercial factors (reference taxonomy) OR rows
    # carrying an explicit driver/spend metric_type tag (per-project binding). ---
    l1u = obj["l1"].astype("string").str.upper()
    mtype = obj["metric_type"].astype("string").str.strip().str.lower()
    drv = obj[l1u.isin(["MARKETING FACTOR", "COMMERCIAL FACTOR"]) | mtype.isin(_DRIVER_TAGS)]
    drv = drv[~_is_y_row(drv) & (drv["metric"] != y_metric)]

    # Physically exclude indicators flagged/dropped upstream (2.2/2.4/2.5), keyed
    # by (l4, metric) so a same-named metric under a different L4 is not over-dropped.
    if exclude:
        metric_only = {m for l4, m in exclude if not l4}
        l4n = drv["l4"].astype("string").map(_norm) if "l4" in drv.columns else pd.Series("", index=drv.index)
        mn = drv["metric"].astype("string").map(_norm)
        drop_mask = pd.Series(
            [((l4v, mv) in exclude) or (mv in metric_only) for l4v, mv in zip(l4n, mn)],
            index=drv.index,
        )
        drv = drv[~drop_mask]

    # The human's explicit X selection (2.5x) — keep only these metrics.
    if include is not None:
        keep_mask = drv["metric"].astype("string").map(_norm).isin(include)
        drv = drv[keep_mask]

    # Aggregate each metric by month (sum duplicates), build wide columns.
    x_meta: dict[str, dict] = {}
    x_series: dict[str, pd.Series] = {}
    used_names: set[str] = set()
    for metric, g in drv.groupby("metric"):
        if g["month"].nunique() < MIN_MONTHS:
            continue
        name = _clean_name(metric)
        base = name
        k = 1
        while name in used_names:
            k += 1
            name = f"{base}_{k}"
        used_names.add(name)
        s = g.groupby("month")["value"].sum()
        x_series[name] = s
        x_meta[name] = {
            "metric": str(metric),
            "metric_type": str(g["metric_type"].iloc[0]),
            "l1": str(g["l1"].iloc[0]),
            "l2": str(g["l2"].iloc[0]) if "l2" in g else "",
            "l3": str(g["l3"].iloc[0]) if "l3" in g else "",
            "l4": str(g["l4"].iloc[0]) if "l4" in g else "",
            "is_spend": _is_spend(g["metric_type"].iloc[0], metric),
        }

    if not x_series:
        if include is not None and not include:
            raise ValueError(
                f"No model variables selected for '{model_object}' — tick at least one.")
        if include is not None:
            raise ValueError(
                f"None of the selected model variables have usable data for '{model_object}' "
                f"(each needs >= {MIN_MONTHS} months).")
        raise ValueError(f"No usable X drivers for '{model_object}' (need >= {MIN_MONTHS} months each)")

    wide = pd.concat({"Y": y_series, **x_series}, axis=1).sort_index()
    # Keep only months where Y is present; forward/zero fill driver gaps.
    wide = wide[wide["Y"].notna()]
    x_cols_all = [c for c in wide.columns if c != "Y"]
    wide[x_cols_all] = wide[x_cols_all].fillna(0.0)

    # Drop all-NaN / constant columns (no variance => uninformative & breaks VIF).
    keep: list[str] = []
    for c in x_cols_all:
        col = wide[c]
        if col.notna().sum() == 0:
            continue
        if np.nanstd(col.to_numpy(dtype=float)) == 0:
            continue
        keep.append(c)
    # Cap drivers to keep the OLS identified — select the most Y-correlated ones.
    # Skipped when the human explicitly selected X (2.5x): their choice wins, and
    # the df guard in the engine reports the cost instead of silently truncating.
    if include is None and len(keep) > MAX_DRIVERS:
        yv = wide["Y"]
        corr = {c: abs(float(wide[c].corr(yv))) for c in keep}
        keep = sorted(keep, key=lambda c: corr[c] if corr[c] == corr[c] else 0.0, reverse=True)[:MAX_DRIVERS]
    wide = wide[["Y"] + keep]

    if wide.shape[0] < MIN_MONTHS:
        raise ValueError(
            f"Only {wide.shape[0]} monthly rows for '{model_object}', need >= {MIN_MONTHS}"
        )
    if not keep:
        raise ValueError(f"No varying X drivers survived cleaning for '{model_object}'")

    spend_cols = [c for c in keep if x_meta[c]["is_spend"]]
    return ModelFrame(
        model_object=model_object,
        frame=wide,
        y_col="Y",
        x_cols=keep,
        spend_cols=spend_cols,
        meta={c: x_meta[c] for c in keep},
        y_metric=y_metric,
        y_metric_type=y_metric_type,
    )
