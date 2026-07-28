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
    "driver_candidates_by_l4",
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

from app.agents.vocabulary import DEFAULT_VOCAB, Vocab

# The former hardcoded banks now live in ``app.agents.vocabulary`` as
# ``DEFAULT_VOCAB``; these module names are kept as byte-parity references (the
# vocab-parity test asserts they equal the default) and for any legacy importer.
# metric_type tokens that indicate a Y (sales / volume / offtake / GMV) variable.
_Y_METRIC_TYPES = {"箱数", "volume", "value", "rmb", "gmv", "unit", "百分比箱数"}
_Y_KEYWORDS = ("offtake", "sales", "gmv", "出货", "完成", "volume", "箱数")
# Explicit Y / X role tags written by the per-project binding (data_binding).
_Y_TAGS = {"y", "kpi"}
_DRIVER_TAGS = {"x", "driver", "spending", "spend"}

# metric_type tokens that indicate paid spend (used for ROI). ``rmb`` was removed
# — see the note on ``DEFAULT_VOCAB.spend_types``.
_SPEND_TYPES = {"spending"}
_SPEND_KEYWORDS = ("spend", "spending", "promotion", "budget",
                   "花费", "费用", "投放", "金额", "投入", "预算")

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
        l4_spend: per-L4 Spending series (norm_l4 -> monthly Series), aligned
            to the frame's index. ROI *denominators* only.
        l4_spend_meta: norm_l4 -> the metric labels summed into that series.
    """
    model_object: str
    frame: pd.DataFrame
    y_col: str
    x_cols: list[str]
    spend_cols: list[str]
    meta: dict[str, dict] = field(default_factory=dict)
    y_metric: str = ""
    y_metric_type: str = ""
    # Per-L4 Spending series (norm_l4 -> monthly Series), aligned to the frame's
    # index. These are ROI *denominators* only: they never enter the design
    # matrix, so an L4 represented in the model by an exposure metric still has
    # a real spend to divide by. `l4_spend_meta` records which metric labels
    # were summed into each series so the UI can explain the denominator.
    l4_spend: dict[str, pd.Series] = field(default_factory=dict)
    l4_spend_meta: dict[str, list[str]] = field(default_factory=dict)

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


def _is_y_row(g: pd.DataFrame, vocab: Vocab = DEFAULT_VOCAB) -> pd.Series:
    l1 = g["l1"].astype("string").str.upper()
    mtype = g["metric_type"].astype("string").str.strip().str.lower()
    metric = g["metric"].astype("string").str.lower().fillna("")
    by_kpi = l1.isin(vocab.y_l1_labels)
    by_kw = metric.apply(lambda m: any(k in m for k in vocab.y_keywords))
    by_type = mtype.isin(vocab.y_metric_types)
    by_tag = mtype.isin(vocab.y_tags)  # explicit Y tag from per-project binding
    return by_kpi | by_tag | (by_kw & by_type)


def is_driver_row(g: pd.DataFrame, vocab: Vocab = DEFAULT_VOCAB) -> pd.Series:
    """Boolean mask selecting rows eligible to be an X driver (before the
    per-metric quality filters). The one definition of "this row is a driver",
    shared by `driver_candidates` and the taxonomy diagnosis so the two cannot
    disagree about whether a table has any drivers at all."""
    l1u = g["l1"].astype("string").str.upper()
    mtype = g["metric_type"].astype("string").str.strip().str.lower()
    return l1u.isin(vocab.driver_l1_labels) | mtype.isin(vocab.driver_tags)


def is_volume_metric_type(metric_type: object, vocab: Vocab = DEFAULT_VOCAB) -> bool:
    """True for a volume/unit response (箱数 / volume / unit)."""
    t = str(metric_type).strip().lower()
    return any(k in t for k in vocab.volume_keywords)


def is_money_metric(metric_type: object, vocab: Vocab = DEFAULT_VOCAB) -> bool:
    """True for a monetary response (RMB / value / GMV / 金额).

    Decides the ROI unit: a money Y makes ``coef·Σtransformed / Σspend`` a real
    增量Revenue/Spend; a volume Y needs a unit price to become one.
    """
    t = str(metric_type).strip().lower()
    if is_volume_metric_type(t, vocab):
        return False
    return any(k in t for k in vocab.money_keywords)


def _pick_y_metric(ydf: pd.DataFrame, vocab: Vocab = DEFAULT_VOCAB) -> str:
    """Among Y candidates pick the metric with the best month coverage,
    preferring **volume** over value so the default Y stays a unit count (the client
    requires the OLS default Y to be KPI-Volume; DATA-009/012).

    This is only the *default* — 2.5 lets the human choose Y explicitly
    (``build_model_frame(y_metric=...)``); this fallback keeps legacy callers
    and un-configured projects working.
    """
    from app.agents.indicator_metadata import classify_indicator

    cov = ydf.groupby("metric")["month"].nunique()
    mtypes = ydf.groupby("metric")["metric_type"].first().str.lower()

    def _is_volume(metric: str) -> bool:
        # Legacy taxonomy tags volume in the metric_type; a per-project upload only
        # carries the "Y" role, so fall back to the FND-001 semantic classifier which
        # distinguishes 本品销量 (kpi_volume) from 本品销售额 (kpi_value).
        mt = str(mtypes.get(metric, ""))
        if any(k in mt for k in vocab.volume_keywords):
            return True
        return classify_indicator(metric).metric_type == "kpi_volume"

    vol_pref = pd.Series({m: 0 if _is_volume(m) else 1 for m in cov.index})
    ranked = pd.DataFrame({"cov": cov, "vol_pref": vol_pref})
    ranked = ranked.sort_values(["cov", "vol_pref"], ascending=[False, True])
    return str(ranked.index[0])


def y_candidates(long_df: pd.DataFrame, model_object: str, vocab: Vocab = DEFAULT_VOCAB) -> list[dict]:
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
    ydf = obj[_is_y_row(obj, vocab)]
    if ydf.empty:
        return []
    out: list[dict] = []
    for metric, g in ydf.groupby("metric"):
        mtype = str(g["metric_type"].iloc[0])
        out.append({
            "metric": str(metric),
            "metric_type": mtype,
            "months": int(g["month"].nunique()),
            "is_money": is_money_metric(mtype, vocab),
            "is_volume": is_volume_metric_type(mtype, vocab),
        })
    default = _pick_y_metric(ydf, vocab)
    out.sort(key=lambda c: (c["metric"] != default, -c["months"], c["metric"]))
    return out


def _is_spend(metric_type: str, metric: str, vocab: Vocab = DEFAULT_VOCAB) -> bool:
    t = str(metric_type).strip().lower()
    m = str(metric).lower()
    return t in vocab.spend_types or any(k in m for k in vocab.spend_keywords) or any(k in t for k in vocab.spend_keywords)


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

    drv = obj[is_driver_row(obj)]
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


def driver_candidates_by_l4(long_df: pd.DataFrame, model_object: str, vocab: Vocab = DEFAULT_VOCAB) -> list[dict]:
    """Every ``(l4, metric)`` driver combination usable for a model object.

    Same predicate and ``MIN_MONTHS`` rule as :func:`driver_candidates`, but
    grouped on ``["l1", "l2", "l3", "l4", "metric"]`` instead of ``metric``
    alone. ``driver_candidates`` collapses to one row per metric with an
    arbitrary L4 (``g["l4"].iloc[0]``), which silently disagrees with every
    other S2 layer's key space — the scorecards (`stat_scoring._indicator_series`
    groups the same way), the per-indicator sign-off, and `build_model_frame`'s
    own per-row exclude. This is the driver universe the ledger must build from.
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

    y_rows = obj[_is_y_row(obj, vocab)]
    y_metric = _pick_y_metric(y_rows, vocab) if not y_rows.empty else ""

    drv = obj[is_driver_row(obj, vocab)]
    drv = drv[~_is_y_row(drv, vocab) & (drv["metric"] != y_metric)]

    group_cols = [c for c in ("l1", "l2", "l3", "l4") if c in drv.columns] + ["metric"]
    out: list[dict] = []
    for key, g in drv.groupby(group_cols, dropna=False):
        vals = dict(zip(group_cols, key if isinstance(key, tuple) else (key,)))
        metric = vals["metric"]
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
            "l1": str(vals.get("l1", "")),
            "l2": str(vals.get("l2", "")),
            "l3": str(vals.get("l3", "")),
            "l4": str(vals.get("l4", "")),
            "is_spend": _is_spend(mt, str(metric), vocab),
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
    include: frozenset | None = None,
    caps: list | None = None,
    vocab: Vocab = DEFAULT_VOCAB,
    st: object | None = None,
) -> ModelFrame:
    """Pivot LONG -> wide monthly frame for one model object.

    Args:
        exclude: driver rows to drop before pivoting, keyed by ``(norm_l4,
            norm_metric)`` where ``norm = str(x).strip().lower()``. An entry with
            an empty ``l4`` (``("", metric)``) drops that metric under any L4.
        y_metric: the response metric to use. ``None`` falls back to
            :func:`_pick_y_metric` (volume-preferring auto-pick).
        include: the human's model-variable selection. Accepts ``(norm_l4,
            norm_metric)`` pairs — the key space every other S2 layer uses — and,
            for backward compatibility with configs saved before the split, bare
            normalized metric names (which keep that metric under any L4). When
            given, ONLY these drivers are kept and the ``MAX_DRIVERS`` correlation
            cap is skipped — the human's selection wins.
        caps: 2.3 cap windows (``OlsCapWindow``) whose response values are
            winsorized to the series' own p5/p95 before fitting.
        st: the project state, read only for each indicator's 2.1 aggregation.
            ``None`` resolves to the name classifier's default, which is what the
            standalone MMM tests and any non-project caller get.

    Drivers are grouped on ``(l1, l2, l3, l4, metric)``, not on ``metric`` alone.
    Two different L4 factors that happen to share a metric label ("花费") are two
    different indicators everywhere else in S2 — the scorecards, the sign-off, the
    ledger and ``driver_candidates_by_l4`` all key on ``(l4, metric)`` — and
    summing them into one design column meant a verdict on one of them could not
    be expressed in the fit at all, and the per-L4 indicator search had nothing
    addressable to search over.

    Raises ValueError when there is no Y variable or fewer than MIN_MONTHS rows.
    """
    from app.agents.overrides import pandas_agg, resolve_aggregation

    def _agg_months(g: pd.DataFrame, l4: object, metric: object) -> pd.Series:
        """One monthly value per period, rolled up the way 2.1 says this
        indicator rolls up. Within a single month a national row can still be
        split across the L5–L8 residual, so this is a real choice: summing a
        rate or an index across those paths produces a number that means nothing.
        """
        return g.groupby("month")["value"].agg(
            pandas_agg(resolve_aggregation(st, l4, metric)))
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
    y_rows = obj[_is_y_row(obj, vocab)]
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
        y_metric = _pick_y_metric(y_rows, vocab)
    y_rows_sel = y_rows[y_rows["metric"] == y_metric]
    y_metric_type = str(y_rows_sel["metric_type"].iloc[0])
    y_l4 = str(y_rows_sel["l4"].iloc[0]) if "l4" in y_rows_sel.columns else ""
    y_series = _agg_months(y_rows_sel, y_l4, y_metric).rename("Y")
    # 2.3 'outlier capping' applies to the response, before anything is fitted.
    y_series = _winsorize_windows(y_series, caps or [])

    # --- X drivers: Marketing + Commercial factors (reference taxonomy) OR rows
    # carrying an explicit driver/spend metric_type tag (per-project binding). ---
    drv = obj[is_driver_row(obj, vocab)]
    drv = drv[~_is_y_row(drv, vocab) & (drv["metric"] != y_metric)]

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

    # The human's explicit X selection (2.5) — keep only these indicators.
    # Accepts (l4, metric) pairs and, for configs saved before the key space was
    # split, bare metric names (which keep that metric under every L4).
    if include is not None:
        inc_pairs = {i for i in include if isinstance(i, tuple)}
        inc_metrics = {i for i in include if isinstance(i, str)}
        l4n = drv["l4"].astype("string").map(_norm) if "l4" in drv.columns else pd.Series("", index=drv.index)
        mn = drv["metric"].astype("string").map(_norm)
        keep_mask = pd.Series(
            [(mv in inc_metrics) or ((l4v, mv) in inc_pairs) for l4v, mv in zip(l4n, mn)],
            index=drv.index,
        )
        drv = drv[keep_mask]

    # --- Per-L4 Spending series (ROI denominators) -------------------------
    # Collected from the object's rows BEFORE exclusions and the include filter:
    # a spend metric that is not a model variable (or was dropped upstream) is
    # still the honest denominator for its L4. Not added to the design matrix.
    # Y rows are excluded: a money response (本品销售额 carries metric_type RMB)
    # satisfies the spend predicate but is revenue, not outlay — left in, it would
    # inflate its L4's denominator with the very sales the ROI is measuring.
    l4_spend: dict[str, pd.Series] = {}
    l4_spend_meta: dict[str, list[str]] = {}
    spend_mask = pd.Series(
        [_is_spend(mt, mv, vocab) for mt, mv in zip(obj["metric_type"], obj["metric"])],
        index=obj.index,
    )
    spend_rows = obj[spend_mask & ~_is_y_row(obj, vocab)]
    if not spend_rows.empty:
        l4_of = (spend_rows["l4"].astype("string").map(_norm)
                 if "l4" in spend_rows.columns
                 else pd.Series("", index=spend_rows.index))
        for l4v, g in spend_rows.groupby(l4_of):
            if not l4v:
                continue
            # Spend is a denominator: it sums across the metrics and residual
            # paths that make up an L4's outlay, regardless of any per-indicator
            # averaging choice.
            l4_spend[str(l4v)] = g.groupby("month")["value"].sum()
            l4_spend_meta[str(l4v)] = sorted({str(m) for m in g["metric"]})

    # One wide column per (l1..l4, metric) indicator, rolled up monthly with its
    # own 2.1 aggregation.
    x_meta: dict[str, dict] = {}
    x_series: dict[str, pd.Series] = {}
    used_names: set[str] = set()
    group_cols = [c for c in ("l1", "l2", "l3", "l4") if c in drv.columns] + ["metric"]
    for key, g in drv.groupby(group_cols, dropna=False):
        vals = dict(zip(group_cols, key if isinstance(key, tuple) else (key,)))
        metric = str(vals["metric"])
        l4v = str(vals.get("l4", "") or "")
        if g["month"].nunique() < MIN_MONTHS:
            continue
        name = _clean_name(metric)
        base = name
        k = 1
        while name in used_names:
            k += 1
            name = f"{base}_{k}"
        used_names.add(name)
        x_series[name] = _agg_months(g, l4v, metric)
        x_meta[name] = {
            "metric": metric,
            "metric_type": str(g["metric_type"].iloc[0]),
            "l1": str(vals.get("l1", "") or ""),
            "l2": str(vals.get("l2", "") or ""),
            "l3": str(vals.get("l3", "") or ""),
            "l4": l4v,
            # Normalized here, with the same `_norm` that keys `l4_spend`, so the
            # ROI denominator lookup cannot drift from the series it looks up.
            "l4_norm": _norm(l4v),
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
        l4_spend={k: v.reindex(wide.index).fillna(0.0) for k, v in l4_spend.items()},
        l4_spend_meta=l4_spend_meta,
    )
