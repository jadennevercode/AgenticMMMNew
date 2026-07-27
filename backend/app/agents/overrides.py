"""Per-indicator human overrides from 2.1 Data Processing.

Two maps live on ``ProjectState`` (keyed by
``indicator_metadata.indicator_key(l4, metric)``):

* ``metric_type_overrides`` — the model role the user assigned: ``"Y"`` (response)
  / ``"X"`` (driver) / ``"excluded"`` (not in model). Applied at the ``model_df``
  seam via :func:`apply_metric_type_overrides`, so every downstream reader sees
  one consistent tagging and there is exactly one Y.
* ``aggregation_overrides`` — how the indicator rolls up across time/dimensions.
  Read by every roll-up in the pipeline via :func:`resolve_aggregation` /
  :func:`aggregation_override_for_metric`.

Absent keys fall back to the name-based classifier (``classify_indicator``), so a
project that sets no overrides — the Danone reference case, every legacy project —
resolves byte-identically to before.

This module is the **single authority** for both questions. Two resolvers exist
precisely so no downstream step re-derives them:

* :func:`resolved_y_metric` — what the model is explaining. 2.3's chart backdrop,
  2.4's Pearson and 2.5's fit all read it, so they cannot disagree about the
  response the way they used to.
* :func:`resolve_aggregation` — how a series is rolled up, honoured by the
  national collapse (2.1), the quality subchecks (2.2), the validation series and
  yearly table (2.3), the statistical screen (2.4), the design matrix (2.5) and
  the master table (2.6).
"""
from __future__ import annotations

import pandas as pd

from app.agents.indicator_metadata import classify_indicator, indicator_key, model_role

# Valid user choices for the model role.
METRIC_ROLE_Y = "Y"
METRIC_ROLE_X = "X"
METRIC_ROLE_EXCLUDED = "excluded"
_VALID_ROLES = {METRIC_ROLE_Y, METRIC_ROLE_X, METRIC_ROLE_EXCLUDED}


def _overrides(st: object | None, attr: str) -> dict[str, str]:
    raw = getattr(st, attr, None) if st is not None else None
    return raw if isinstance(raw, dict) else {}


def metric_type_override(st: object | None, l4: object, metric: object) -> str | None:
    """The user's model-role choice for an indicator, or ``None`` if unset."""
    ov = _overrides(st, "metric_type_overrides").get(indicator_key(l4, metric))
    return ov if ov in _VALID_ROLES else None


def _role_to_tag(role: str, metric: str) -> str:
    """Map a user role to the long-table ``metric_type`` tag the OLS engine reads.

    ``X`` preserves the spend sub-classification (spend is ROI-eligible), so a
    driver the user keeps as X is still tagged ``spending`` when its name is a
    spend metric — the user picks Y/X/excluded, the engine keeps needing spend."""
    if role == METRIC_ROLE_Y:
        return "Y"
    # role == "X": keep the spend distinction the engine relies on.
    return "spending" if classify_indicator(metric).metric_type == "spending" else "X"


def apply_metric_type_overrides(df: pd.DataFrame, st: object | None) -> pd.DataFrame:
    """Return ``df`` with ``metric_type`` remapped per the user's 2.1 choices and
    ``excluded`` indicators dropped. A no-op (same frame) when no overrides exist —
    keeping the reference/legacy paths unchanged."""
    ov = _overrides(st, "metric_type_overrides")
    if not ov or df is None or df.empty or "metric" not in df.columns:
        return df

    l4col = df["l4"] if "l4" in df.columns else pd.Series([""] * len(df), index=df.index)
    keys = [indicator_key(a, b) for a, b in zip(l4col, df["metric"])]
    roles = pd.Series([ov.get(k) for k in keys], index=df.index)

    matched = roles.isin(list(_VALID_ROLES))
    if not matched.any():
        return df

    out = df.copy()
    # Drop excluded indicators outright — they never reach the model frame.
    keep = ~(roles == METRIC_ROLE_EXCLUDED)
    # Remap Y / X tags for the rest (leave spend-vs-driver intact for X).
    new_tags = [
        _role_to_tag(r, str(m)) if r in (METRIC_ROLE_Y, METRIC_ROLE_X) else t
        for r, m, t in zip(roles, out["metric"], out.get("metric_type", pd.Series([""] * len(out), index=out.index)))
    ]
    out["metric_type"] = new_tags
    return out[keep].reset_index(drop=True)


def resolved_y_key(st: object | None) -> str | None:
    """The ``indicator_key`` the user tagged ``Y`` at 2.1, or ``None`` when unset.

    ``metric_type_overrides`` holds at most one ``Y`` — the API demotes the
    previous response when a new one is picked — so the first hit is the answer.
    """
    for key, role in _overrides(st, "metric_type_overrides").items():
        if role == METRIC_ROLE_Y:
            return key
    return None


def resolved_y_metric(st: object | None, df: pd.DataFrame | None) -> str | None:
    """The one response metric every S2 step must score / plot / fit against.

    Resolution order:

    1. the indicator the user tagged ``Y`` at 2.1 Data Processing, mapped back to
       the metric label actually present in ``df``;
    2. otherwise the volume-preferring auto-pick over ``df``'s Y rows
       (:func:`app.mmm.pivot._pick_y_metric`).

    Step 2 is what the Danone reference case and every un-configured project get,
    so this is byte-identical to the old behaviour until someone picks a Y. Before
    this resolver existed 2.4, 2.3 and 2.5 each re-derived the response
    independently and could disagree about what the model was even explaining.
    """
    from app.mmm.pivot import _is_y_row, _pick_y_metric  # local: pivot must not import us

    if df is None or df.empty or "metric" not in df.columns:
        return None

    key = resolved_y_key(st)
    if key:
        l4col = df["l4"] if "l4" in df.columns else pd.Series([""] * len(df), index=df.index)
        hit = df[[indicator_key(a, b) == key for a, b in zip(l4col, df["metric"])]]
        if not hit.empty:
            return str(hit["metric"].iloc[0])
        # The tagged indicator is absent from this frame (a data change dropped
        # it). Fall through to the auto-pick rather than returning nothing — but
        # callers that can surface it should flag the mismatch.

    y_rows = df[_is_y_row(df)]
    if y_rows.empty:
        return None
    return _pick_y_metric(y_rows)


def resolve_aggregation(st: object | None, l4: object, metric: object) -> str:
    """The aggregation method for an indicator: user override, else the classifier
    default (spend/volume/count → sum, rate/price/index → average).

    This is the **one** aggregation authority. Every roll-up in the pipeline —
    the national collapse (2.1), the quality subchecks (2.2), the validation
    series and tables (2.3), the statistical screen (2.4), the design matrix
    (2.5) and the master table (2.6) — resolves through here, so an indicator the
    user marked ``AVG`` is never summed anywhere downstream.
    """
    ov = _overrides(st, "aggregation_overrides").get(indicator_key(l4, metric))
    if ov:
        return ov
    return classify_indicator(str(metric or "")).aggregation


def aggregation_override_for_metric(st: object | None, metric: object) -> str | None:
    """Any 2.1 aggregation override whose metric matches, regardless of L4.

    Surfaces that address an indicator by metric label alone — the 2.3 chart
    series, the 2.2 subchecks — have no L4 in scope but must still honour the
    user's SUM/AVG choice. When two L4s share a metric name and disagree the
    first wins; a same-named metric carrying different aggregations under
    different factors is a data-modelling problem, not something to paper over
    differently on each surface.
    """
    want = _norm_metric(metric)
    if not want:
        return None
    for key, method in _overrides(st, "aggregation_overrides").items():
        if key.split("::", 1)[-1] == want:
            return method
    return None


def _norm_metric(metric: object) -> str:
    """The metric half of an ``indicator_key`` (same normalisation)."""
    return indicator_key("", metric).split("::", 1)[-1]


def pandas_agg(method: str) -> str:
    """Map an aggregation method to the pandas reducer name.

    ``sum`` stays ``sum``; everything averaging (``average``, and
    ``weighted_average`` wherever no weights are available) becomes ``mean``.
    ``min``/``max`` survive for legacy saved overrides.
    """
    m = str(method or "sum").strip().lower()
    if m in ("min", "max"):
        return m
    if m in ("sum", "count", "distinct_count"):
        return "sum" if m == "sum" else "count"
    return "mean"


def default_metric_type(metric: object) -> str:
    """The name-derived model role (Y/X/spending) an indicator gets with no override."""
    return model_role(classify_indicator(str(metric or "")).metric_type)
