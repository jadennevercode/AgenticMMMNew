"""FND-001 · Unified indicator metadata.

Every indicator carries a semantic profile — **what kind of number it is** — that
downstream steps read instead of re-guessing from the name each time:

* ``metric_type`` (semantic): kpi_volume · kpi_value · spending · count · rate ·
  index · other. Drives default chart form, number format and OLS eligibility
  (DATA-008 / DATA-009 / DATA-010).
* ``aggregation``: how the indicator rolls up across time/dimensions. A rate or
  coverage metric (NDWD) must average, not sum (DATA-007).
* ``unit`` / ``currency`` / ``fmt``: how the value is displayed (% vs money vs count).

The **model role** (Y / spending / X) the OLS engine uses is *derived* from the
semantic type via :func:`model_role`, so the keyword rules live in exactly one
place: ``data_binding._metric_type`` now calls through here, keeping the Y/X/spend
tagging and the semantic tagging from ever disagreeing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.models import Aggregation, MetricType

# Bump when the classification rules change; stamped onto each classified indicator
# so a re-classification is distinguishable from a stored human override.
INDICATOR_META_RULE_VERSION = "1.0"

# The KPI (response) and spending gates are the exact rules the OLS tagging has
# always used — kept verbatim so model_role() reproduces the legacy Y/spending/X.
_KPI_RE = re.compile(r"本品.*(销量|销售)|kpi|本品月度销量|offtake|本品.*volume", re.I)
_VALUE_RE = re.compile(r"销售额|销额|金额|收入|value|revenue|gmv|营业额", re.I)
_SPEND_RE = re.compile(r"花费|费用|投放|金额|spend|promotion|投入|预算|budget", re.I)
# Finer buckets for the non-KPI / non-spending remainder (semantic only — every one
# of these maps to the OLS driver role X, so this never perturbs the fit).
_RATE_RE = re.compile(r"率|占比|渗透|覆盖|ndwd|distribution|percentage|percent|ratio|%", re.I)
_INDEX_RE = re.compile(r"指数|index|价格指数|tps|情感|sentiment|score", re.I)
_COUNT_RE = re.compile(r"门店|家数|铺货|网点|store|count|数量|个数|条数|次数", re.I)


@dataclass(frozen=True)
class IndicatorMeta:
    metric_type: MetricType
    unit: str
    currency: str | None
    aggregation: Aggregation
    fmt: str  # money | percent | index | integer | number


def classify_indicator(name: str) -> IndicatorMeta:
    """Infer the semantic metadata of an indicator from its name (heuristic).

    Gate order matters and mirrors the legacy role tagging: KPI first (so a
    ``本品销售额`` KPI is never mistaken for spend), then spending, then the finer
    driver buckets. Every branch returns a complete, self-consistent profile."""
    n = str(name or "")
    if _KPI_RE.search(n):
        if _VALUE_RE.search(n):
            return IndicatorMeta("kpi_value", "¥", "CNY", "sum", "money")
        return IndicatorMeta("kpi_volume", "", None, "sum", "integer")
    if _SPEND_RE.search(n):
        return IndicatorMeta("spending", "¥", "CNY", "sum", "money")
    if _RATE_RE.search(n):
        # Rates / coverage (NDWD) must average across periods & regions, not sum.
        return IndicatorMeta("rate", "%", None, "average", "percent")
    if _INDEX_RE.search(n):
        return IndicatorMeta("index", "", None, "average", "index")
    if _COUNT_RE.search(n):
        return IndicatorMeta("count", "", None, "sum", "integer")
    return IndicatorMeta("other", "", None, "sum", "number")


def model_role(metric_type: MetricType) -> str:
    """Map a semantic type to the OLS engine's role tag: 'Y' | 'spending' | 'X'."""
    if metric_type in ("kpi_volume", "kpi_value"):
        return "Y"
    if metric_type == "spending":
        return "spending"
    return "X"


def _norm(s: object) -> str:
    return re.sub(r"\s+", "", str(s or "")).strip().lower()


def indicator_key(l4: object, metric: object) -> str:
    """Stable key for an indicator's metadata (matches the ledger's key space)."""
    return f"{_norm(l4)}::{_norm(metric)}"
