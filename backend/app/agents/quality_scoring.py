"""2.2 Data Quality Score — deterministic subcheck scorer.

The rubric (``Assets/数据智能体知识库/机器可读/validation-scoring.json``, sourced from
``reference/02.数据智能体/【MMM AI】数据智能体-Data Validation_2.1.xlsx`` sheets
"2.11数据通用校验标准" + "2.11打分规则") scores every indicator on four
dimensions, each broken into subchecks, on the {0, 0.5, 1} scale:

    consistency   — dimension · time · caliber
    accuracy      — numeric · business
    completeness  — field · data
    granularity   — time · model · drilldown

This module computes, per metric series, the deterministic **evidence** and a
**baseline score for each subcheck** straight from the real long table (pandas,
never the LLM). A dimension score = the weakest of its *blocking* subchecks;
advisory subchecks (things that need an external reference — cross-source unit
consistency, finance reconciliation, deepdive drilldown) are surfaced for
transparency but never force a dimension to 0 on their own. The AI layer
(`data.score_data`) then reviews the four dimension scores on this grounding.

Total follows the Excel 2.12 formula — the **product** of the four dimensions —
so any 0 dimension makes the metric unusable and one 0.5 halves the score:

    Total = consistency × accuracy × completeness × granularity
    Total == 0        → unusable  (reject & warn)
    0 < Total < 0.5   → borderline (human decision)
    Total >= 0.5      → pass      (accept)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DIMENSIONS = ("consistency", "accuracy", "completeness", "granularity")

# Verdict thresholds on the product Total (Excel 2.12 acceptance rule).
PASS_MIN = 0.5      # Total >= 0.5 → accept
UNUSABLE_MAX = 0.0  # Total == 0  → unusable; strictly between → borderline

# Band thresholds (mirror the 2.11 打分规则 sheet, cited per check below).
_YOY_CALIBER = 0.30       # source change + |YoY| > 30% → caliber 0
_TIME_MIX_TOL = 0.10      # >10% off the dominant time grid → time-consistency 0.5/0
_ERR_HIGH = 0.10          # numeric error ratio > 10% → 0
_ERR_MID = 0.05           # 5–10% → 0.5
_COVER_FULL = 24          # coverage span >= 2yr → 1 (Excel 2.12 "Data coverage")
_COVER_MIN = 12           # 1–2yr → 0.5; below → 0
_CONTINUITY_OK = 0.95     # present/spanned months ratio for advisory continuity
_CONTINUITY_LOW = 0.80

# Metric types that cannot legitimately be negative (spend / sales / KPI). For
# other drivers (temperature, growth %, indices) negatives are valid, so they
# don't count as data errors — spike judgement is left to the AI/human review.
_NONNEG_TYPES = frozenset({"spending", "Y"})


@dataclass(frozen=True)
class SeriesEvidence:
    """Computable proxies for one L1..L4 × metric series (from real pandas)."""

    n: int
    months: int              # distinct yyyymm periods present
    span_months: int         # last − first + 1 in month index (continuity denom)
    nonneg_ratio: float
    error_ratio: float       # non-finite + illegal-negative values / n (data errors)
    monthly_ratio: float     # fraction of rows carrying a month (vs year-only)
    monthly: bool            # month granularity is the dominant grid
    source_changed: bool     # >1 distinct data source across the series
    max_yoy: float           # max |year-over-year| change of the annual totals
    regions: int             # distinct province_group
    channels: int            # distinct channel
    drilldown_dims: int      # distinct-valued among l5..l8
    metric_type: str         # 'Y' | 'spending' | 'X'


@dataclass(frozen=True)
class FieldContext:
    """Cross-series context for the field-completeness check (per parent L4)."""

    has_spend: bool
    has_performance: bool


@dataclass(frozen=True)
class SubScore:
    key: str          # e.g. "consistency.time"
    dimension: str
    label: str        # English display label
    score: float      # 0 / 0.5 / 1
    note: str         # English, evidence-grounded
    computed: bool     # True = derived from data; False = advisory default
    blocking: bool     # whether it can drag the dimension score down


@dataclass(frozen=True)
class QualityResult:
    subs: tuple[SubScore, ...]
    consistency: float
    accuracy: float
    completeness: float
    granularity: float
    total: float
    verdict: str      # "pass" | "borderline" | "unusable"

    def dimension_note(self, dimension: str) -> str:
        """The weakest blocking subcheck's note — the driver of the dim score."""
        subs = [s for s in self.subs if s.dimension == dimension and s.blocking]
        if not subs:
            return ""
        return min(subs, key=lambda s: s.score).note


# ── evidence ────────────────────────────────────────────────────────────────


def compute_series_evidence(grp: pd.DataFrame) -> SeriesEvidence:
    """Derive the computable evidence for one metric series."""
    vals = grp["value"].to_numpy(dtype=float)
    finite = np.isfinite(vals)
    fvals = vals[finite]
    n_fin = int(finite.sum())
    n_all = max(len(vals), 1)
    nonneg = float(np.sum(fvals >= 0) / n_fin) if n_fin else 0.0
    mtype = ""
    if "metric_type" in grp:
        mt = grp["metric_type"].dropna()
        mtype = str(mt.iloc[0]) if not mt.empty else ""
    # Data errors = non-finite values (always wrong) + illegal negatives (only for
    # metrics that can't be negative). Natural variance is NOT an error.
    nonfinite = int((~finite).sum())
    illegal_neg = int(np.sum(fvals < 0)) if mtype in _NONNEG_TYPES else 0
    error_ratio = (nonfinite + illegal_neg) / n_all

    mser = grp["month"].dropna().astype("int64")
    months = int(mser.nunique())
    if months:
        lo, hi = int(mser.min()), int(mser.max())
        span = (hi // 100 - lo // 100) * 12 + (hi % 100 - lo % 100) + 1
        span = max(span, months)  # guard against malformed yyyymm
    else:
        span = 0
    monthly_ratio = float(grp["month"].notna().mean())

    source_changed = _source_changed(grp)
    max_yoy = _max_yoy(grp)
    drilldown = sum(1 for c in ("l5", "l6", "l7", "l8")
                    if c in grp and grp[c].replace("", np.nan).nunique(dropna=True) >= 1)
    return SeriesEvidence(
        n=len(vals), months=months, span_months=span, nonneg_ratio=nonneg,
        error_ratio=error_ratio, monthly_ratio=monthly_ratio,
        monthly=monthly_ratio >= 0.5, source_changed=source_changed, max_yoy=max_yoy,
        regions=int(grp["province_group"].nunique(dropna=True)),
        channels=int(grp["channel"].nunique(dropna=True)),
        drilldown_dims=drilldown, metric_type=mtype,
    )


def _source_changed(grp: pd.DataFrame) -> bool:
    """True when the data source SWITCHED over time (口径变化), not merely when the
    series aggregates several concurrent sources. Compares the source set in the
    early half of the timeline against the late half — a source appearing or
    dropping out signals a caliber change; a stable multi-source mix does not."""
    if "source" not in grp or "month" not in grp:
        return False
    sub = grp[["month", "source"]].dropna()
    if sub.empty:
        return False
    months = sub["month"].astype("int64")
    mid = months.median()
    early = set(sub.loc[months <= mid, "source"].astype(str))
    late = set(sub.loc[months > mid, "source"].astype(str))
    if not early or not late:
        return False
    return early != late


def _max_yoy(grp: pd.DataFrame) -> float:
    """Max |year-over-year| change of the annual *mean* level (caliber-shift proxy).

    Mean, not sum, so a partial leading/trailing year isn't mistaken for a level
    shift — a genuine source/definition change moves the average, not just the count.
    """
    if "year" not in grp:
        return 0.0
    ann = grp.dropna(subset=["year"]).groupby("year")["value"].mean().sort_index()
    if len(ann) < 2:
        return 0.0
    prev = ann.to_numpy(dtype=float)[:-1]
    cur = ann.to_numpy(dtype=float)[1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        yoy = np.where(prev != 0, np.abs(cur - prev) / np.abs(prev), 0.0)
    finite = yoy[np.isfinite(yoy)]
    return float(finite.max()) if finite.size else 0.0


# ── subcheck scoring ────────────────────────────────────────────────────────


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def score_quality(ev: SeriesEvidence, field: FieldContext) -> QualityResult:
    """Score one series on the 10 subchecks → 4 dimensions → product Total."""
    subs = [
        *_consistency_subs(ev),
        *_accuracy_subs(ev),
        *_completeness_subs(ev, field),
        *_granularity_subs(ev),
    ]
    dims = {d: _roll_up(subs, d) for d in DIMENSIONS}
    total = round(dims["consistency"] * dims["accuracy"]
                  * dims["completeness"] * dims["granularity"], 4)
    if total <= UNUSABLE_MAX:
        verdict = "unusable"
    elif total < PASS_MIN:
        verdict = "borderline"
    else:
        verdict = "pass"
    return QualityResult(
        subs=tuple(subs), consistency=dims["consistency"], accuracy=dims["accuracy"],
        completeness=dims["completeness"], granularity=dims["granularity"],
        total=total, verdict=verdict,
    )


def _roll_up(subs: list[SubScore], dimension: str) -> float:
    """Dimension score = weakest blocking subcheck (advisory ones can't zero it)."""
    blocking = [s.score for s in subs if s.dimension == dimension and s.blocking]
    return min(blocking) if blocking else 1.0


def _consistency_subs(ev: SeriesEvidence) -> list[SubScore]:
    # dimension consistency (维度一致性) — units/definitions across sources: not
    # verifiable from a single tidy series → advisory default, AI/human confirm.
    dim = SubScore("consistency.dimension", "consistency", "Dimension consistency", 1.0,
                   "Unified statistical caliber assumed (not cross-source verifiable).",
                   computed=False, blocking=False)
    # time consistency (时间一致性) — mixing of day/week/month grids.
    off = 1.0 - ev.monthly_ratio
    if not ev.monthly:
        time = SubScore("consistency.time", "consistency", "Time consistency", 0.0,
                        "Series is coarser than monthly granularity.", True, True)
    elif off > _TIME_MIX_TOL:
        time = SubScore("consistency.time", "consistency", "Time consistency", 0.5,
                        f"{_pct(off)} of rows are off the dominant monthly grid.", True, True)
    else:
        time = SubScore("consistency.time", "consistency", "Time consistency", 1.0,
                        "Uniform monthly time grid.", True, True)
    # caliber consistency (口径一致性) — source/definition change + YoY swing.
    if not ev.source_changed:
        cal = SubScore("consistency.caliber", "consistency", "Caliber consistency", 1.0,
                       "Single data source throughout the series.", True, True)
    elif ev.max_yoy > _YOY_CALIBER:
        cal = SubScore("consistency.caliber", "consistency", "Caliber consistency", 0.0,
                       f"Source changed with a {_pct(ev.max_yoy)} YoY swing (>30%).", True, True)
    else:
        cal = SubScore("consistency.caliber", "consistency", "Caliber consistency", 0.5,
                       f"Source changed; YoY swing {_pct(ev.max_yoy)} (≤30%).", True, True)
    # continuity (连续性) — present vs spanned months. Advisory: flighted media and
    # lower-frequency surveys legitimately have off-months, so gaps flag for review
    # rather than auto-reject.
    cont = (ev.months / ev.span_months) if ev.span_months else 0.0
    if cont >= _CONTINUITY_OK:
        con = SubScore("consistency.continuity", "consistency", "Continuity", 1.0,
                       f"Continuous grid ({ev.months}/{ev.span_months} months).", True, False)
    elif cont >= _CONTINUITY_LOW:
        con = SubScore("consistency.continuity", "consistency", "Continuity", 0.5,
                       f"{_pct(1 - cont)} of months absent — check for gaps vs flighting.",
                       True, False)
    else:
        con = SubScore("consistency.continuity", "consistency", "Continuity", 0.5,
                       f"{_pct(1 - cont)} of months absent (likely flighted/low-frequency; verify).",
                       True, False)
    return [dim, time, cal, con]


def _accuracy_subs(ev: SeriesEvidence) -> list[SubScore]:
    # numeric accuracy (数值准确性) — missing/non-finite + illegal negatives.
    err = ev.error_ratio
    if err > _ERR_HIGH:
        num = SubScore("accuracy.numeric", "accuracy", "Numeric accuracy", 0.0,
                       f"{_pct(err)} of values are invalid (non-finite / illegal negative, >10%).",
                       True, True)
    elif err >= _ERR_MID:
        num = SubScore("accuracy.numeric", "accuracy", "Numeric accuracy", 0.5,
                       f"{_pct(err)} invalid values (5–10%).", True, True)
    else:
        num = SubScore("accuracy.numeric", "accuracy", "Numeric accuracy", 1.0,
                       f"Values clean (error rate {_pct(err)} <5%).", True, True)
    # business accuracy (业务准确性) — reconcile vs finance: no external ref here.
    biz = SubScore("accuracy.business", "accuracy", "Business accuracy", 1.0,
                   "No external finance/system reference available to cross-check.",
                   computed=False, blocking=False)
    return [num, biz]


def _completeness_subs(ev: SeriesEvidence, field: FieldContext) -> list[SubScore]:
    # field completeness (字段完整性) — spend paired with a performance metric.
    if ev.metric_type == "Y":
        fld = SubScore("completeness.field", "completeness", "Field completeness", 1.0,
                       "Response/KPI series.", True, True)
    elif field.has_spend and not field.has_performance:
        fld = SubScore("completeness.field", "completeness", "Field completeness", 0.5,
                       "Spend present without a paired performance metric for this factor.",
                       True, True)
    else:
        fld = SubScore("completeness.field", "completeness", "Field completeness", 1.0,
                       "Metric fields present for this factor.", True, True)
    # data coverage (数据完整性 / Data coverage) — modeling needs enough history.
    # Measured by span duration (Excel 2.12 "Data coverage": 2yr+→1, 1–2yr→0.5,
    # <1yr→0), so flighted/low-frequency series aren't penalized for off-months.
    span = ev.span_months
    if span >= _COVER_FULL:
        dat = SubScore("completeness.data", "completeness", "Data coverage", 1.0,
                       f"Covers {span} months (2yr+).", True, True)
    elif span >= _COVER_MIN:
        dat = SubScore("completeness.data", "completeness", "Data coverage", 0.5,
                       f"Covers {span} months (1–2yr).", True, True)
    else:
        dat = SubScore("completeness.data", "completeness", "Data coverage", 0.0,
                       f"Only {span} months of history (<1yr).", True, True)
    return [fld, dat]


def _granularity_subs(ev: SeriesEvidence) -> list[SubScore]:
    # time granularity (时间颗粒度) — monthly or finer required for modeling.
    tim = SubScore("granularity.time", "granularity", "Time granularity",
                   1.0 if ev.monthly else 0.0,
                   "Monthly or finer." if ev.monthly else "Coarser than monthly (below modeling minimum).",
                   True, True)
    # model granularity (模型颗粒度) — region × channel detail to fit the L4 object.
    # Advisory: the true L4 scope requirement (contract-defined) isn't knowable from
    # the tidy series, so richer detail is a positive signal but a national/single-
    # channel series is still modelable at the object level — it must not zero out.
    if ev.regions > 1 and ev.channels > 1:
        mod = SubScore("granularity.model", "granularity", "Model granularity", 1.0,
                       f"Region ({ev.regions}) × channel ({ev.channels}) detail fits the model object.",
                       computed=True, blocking=False)
    elif ev.regions > 1 or ev.channels > 1:
        mod = SubScore("granularity.model", "granularity", "Model granularity", 1.0,
                       f"Dimensional detail present (regions={ev.regions}, channels={ev.channels}).",
                       computed=True, blocking=False)
    else:
        mod = SubScore("granularity.model", "granularity", "Model granularity", 0.5,
                       "National/single-channel series — no sub-dimension to split on "
                       "(check it meets the L4 model scope).", computed=True, blocking=False)
    # drilldown granularity (下钻颗粒度) — deepdive L5–L8 dims; advisory only.
    if ev.drilldown_dims > 2:
        drill = SubScore("granularity.drilldown", "granularity", "Drilldown granularity", 1.0,
                         f"{ev.drilldown_dims} deepdive dimensions (L5–L8).", True, False)
    elif ev.drilldown_dims >= 1:
        drill = SubScore("granularity.drilldown", "granularity", "Drilldown granularity", 0.5,
                         f"{ev.drilldown_dims} deepdive dimension(s) — limited deepdive.", True, False)
    else:
        drill = SubScore("granularity.drilldown", "granularity", "Drilldown granularity", 0.0,
                         "No L5–L8 deepdive dimensions.", True, False)
    return [tim, mod, drill]
