"""Data-agent scoring rules, sourced from the knowledge base.

The authoritative rubric lives in ``Assets/数据智能体知识库/机器可读/*.json``
(validation-scoring · statistical-scoring · factor-ranges). This module:

* loads the JSON so the *displayed* rule sheets come straight from the KB, and
* encodes the numeric bands as typed Python so scoring is deterministic and
  testable. The constants mirror the JSON exactly (cited per band); if you
  change a threshold, change it in both places.

2.11 data validation — four dimensions, each 0 / 0.5 / 1:
    consistency (continuity) · accuracy · completeness · granularity
2.33 statistical screening — three tests, each 0 / 0.5 / 1 / 2:
    CV (volatility) · Pearson (vs KPI) · VIF (collinearity); Total = sum.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import BACKEND_ROOT

KB_DIR = (BACKEND_ROOT.parent / "Assets" / "数据智能体知识库" / "机器可读").resolve()

# Verdict thresholds (validation) — normalised total in [0, 4].
VALIDATION_PASS = 3.0       # accept
VALIDATION_BORDERLINE = 2.0  # human decision (0.5-band); below → unusable

# Statistical verdict thresholds — Total = CV + Pearson + VIF in [0, 6].
STAT_GOOD = 3.0
STAT_ACCEPTABLE = 1.5
STAT_SEVERE_VIF = 10.0      # severe collinearity → drop regardless of total


@lru_cache(maxsize=8)
def load_rule(name: str) -> dict[str, Any]:
    """Load a knowledge-base rule JSON (cached). Returns {} if unavailable."""
    path = KB_DIR / f"{name}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# ── 2.11 validation ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MetricStats:
    """Computable proxies for one metric series (from real pandas, never LLM)."""

    n: int
    months: int        # distinct yyyymm periods present
    span_months: int   # last - first + 1 in month index (continuity denominator)
    nonneg_ratio: float
    regions: int       # distinct province_group
    channels: int      # distinct channel
    monthly: bool      # has month granularity


@dataclass(frozen=True)
class ValidationScore:
    consistency: float
    accuracy: float
    completeness: float
    granularity: float
    total: float
    verdict: str       # "pass" | "borderline" | "unusable"


def score_validation(s: MetricStats) -> ValidationScore:
    """Score a metric on the four KB dimensions (each 0 / 0.5 / 1)."""
    # Completeness — data coverage (KB 2.12 Data coverage: >2yr=1, 1-2yr=0.5, <1yr=0).
    completeness = 1.0 if s.months >= 24 else (0.5 if s.months >= 12 else 0.0)

    # Consistency — continuity ("一致性（含连续性）"): present / spanned months.
    cont = (s.months / s.span_months) if s.span_months else 0.0
    consistency = 1.0 if cont >= 0.95 else (0.5 if cont >= 0.8 else 0.0)

    # Accuracy — numeric validity (KB 数值准确性: err<5%=1, 5-10%=0.5, >10%=0).
    accuracy = 1.0 if s.nonneg_ratio >= 0.99 else (0.5 if s.nonneg_ratio >= 0.9 else 0.0)

    # Granularity — KB time颗粒度 monthly=1, plus model颗粒度 (region/channel detail).
    if not s.monthly:
        granularity = 0.0
    elif s.regions > 1 or s.channels > 1:
        granularity = 1.0
    else:
        granularity = 0.5

    total = round(consistency + accuracy + completeness + granularity, 2)
    if total >= VALIDATION_PASS:
        verdict = "pass"
    elif total >= VALIDATION_BORDERLINE:
        verdict = "borderline"
    else:
        verdict = "unusable"
    return ValidationScore(consistency, accuracy, completeness, granularity, total, verdict)


def final_verdict(consistency: float, accuracy: float, completeness: float,
                  granularity: float) -> tuple[float, str]:
    """Roll the four 0/0.5/1 dimension scores up to the acceptance verdict.

    Per the 2.12 sheet (Final = 完整性+颗粒度+真实性+一致性; 1→验收, 0→不可用, 0.5→人决策),
    the weakest dimension governs: any 0 → unusable; any 0.5 (no 0) → human decision;
    all 1 → accept. This keeps the verdict on the {0, 0.5, 1} band the sheet uses."""
    final = min(consistency, accuracy, completeness, granularity)
    if final >= 1.0:
        return 1.0, "pass"
    if final <= 0.0:
        return 0.0, "unusable"
    return 0.5, "borderline"


def validation_rule_rows() -> list[list[str]]:
    """Flatten validation-scoring.json into ['维度', '子项', '0', '0.5', '1'] rows."""
    data = load_rule("validation-scoring")
    rows: list[list[str]] = []
    for dim in (data.get("dimensions") or {}).values():
        label = str(dim.get("label", ""))
        for sub, bands in (dim.get("subchecks") or {}).items():
            rows.append([
                label, str(sub),
                str(bands.get("0", ""))[:60],
                str(bands.get("0.5", ""))[:60],
                str(bands.get("1", ""))[:60],
            ])
    return rows


# ── 2.33 statistical screening ──────────────────────────────────────────────


@dataclass(frozen=True)
class StatScore:
    cv_score: float
    pearson_score: float
    vif_score: float
    total: float
    verdict: str       # "Good" | "Acceptable" | "unconsiderable"
    drop: bool


def _cv_band(cv: float) -> float:
    if cv <= 0.05:
        return 0.0
    if cv < 0.1:
        return 0.5
    if cv < 0.2:
        return 1.0
    return 2.0


def _pearson_band(r: float) -> float:
    a = abs(r)
    if a < 0.1:
        return 0.0
    if a < 0.3:
        return 0.5
    if a < 0.5:
        return 1.0
    return 2.0


def _vif_band(vif: float) -> float:
    if vif <= 1.0:
        return 0.0
    if vif < 5.0:
        return 0.5
    if vif < 10.0:
        return 1.0
    return 2.0


def reference_cv(x: "np.ndarray") -> float:
    """CV per the 2.33 rule: min-max scale the series to [0, 1], then variance/mean.

    This is the workbook's explicit definition ("波动系数CV = 方差/均值，数据先缩放到0-1"),
    not the textbook CV=std/mean. Returns 0.0 for empty/constant/degenerate series.
    """
    import numpy as np

    v = x[~np.isnan(x)].astype(float) if x.size else x
    if v.size == 0:
        return 0.0
    lo, hi = float(np.min(v)), float(np.max(v))
    if hi <= lo:  # constant series → no volatility
        return 0.0
    scaled = (v - lo) / (hi - lo)
    mean = float(np.mean(scaled))
    if mean <= 0:
        return 0.0
    return float(np.var(scaled) / mean)


VIF_MAX = 1000.0  # display/scoring cap — a VIF this high is already "severe"


def vif_all(matrix: "np.ndarray") -> "np.ndarray":
    """Per-column VIF for a (n_obs × n_cols) matrix, at column (indicator) granularity.

    Two regimes, both returning one VIF per column (never a grouped/shared score):

    * **Identified (n > p + 1):** the exact VIF_i = [inv(R)]_ii, where R is the
      column correlation matrix — equivalent to 1/(1-R²) from regressing column i
      on all the others. This is the case for real per-object modeling frames.
    * **Under-determined (p ≥ n):** a full multivariate VIF is unidentifiable
      (more indicators than observations), so we fall back to the pairwise-max
      collinearity proxy VIF_i = 1/(1 - max_{j≠i} r_ij²) — still one value per
      indicator, defined for any p, and interpretable as "how well the single most
      collinear peer explains this indicator". This is the normal regime when
      screening every FactorTree indicator before modeling.

    Values are floored at 1.0 and capped at ``VIF_MAX``.
    """
    import numpy as np

    n, p = matrix.shape
    if p < 2:
        return np.ones(p)
    corr = np.corrcoef(matrix, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0)  # constant columns → treat as uncorrelated
    np.fill_diagonal(corr, 1.0)

    if n > p + 1:
        try:
            inv = np.linalg.inv(corr + 1e-8 * np.eye(p))
            diag = np.diag(inv)
        except np.linalg.LinAlgError:
            diag = np.diag(np.linalg.pinv(corr))
    else:
        # pairwise-max proxy: strongest |correlation| to any other column.
        c2 = np.clip(corr ** 2, 0.0, 0.999999)
        np.fill_diagonal(c2, 0.0)
        r2_max = c2.max(axis=1)
        diag = 1.0 / (1.0 - r2_max)
    return np.clip(diag, 1.0, VIF_MAX).astype(float)


def score_statistical(cv: float, pearson: float, vif: float) -> StatScore:
    """Score one variable on CV / Pearson / VIF per the KB bands.

    Total follows the KB formula (CV + Pearson + VIF). The keep/drop verdict
    additionally guards against severe collinearity, since a high VIF inflates
    the KB total but means the variable should be dropped, not kept.
    """
    cv_s = _cv_band(cv)
    pear_s = _pearson_band(pearson)
    vif_s = _vif_band(vif)
    total = round(cv_s + pear_s + vif_s, 2)
    if total >= STAT_GOOD:
        verdict = "Good"
    elif total >= STAT_ACCEPTABLE:
        verdict = "Acceptable"
    else:
        verdict = "unconsiderable"
    drop = total < STAT_ACCEPTABLE or vif >= STAT_SEVERE_VIF
    return StatScore(cv_s, pear_s, vif_s, total, verdict, drop)


def statistical_rule_rows() -> list[list[str]]:
    """Flatten statistical-scoring.json into ['检验', '分', '条件', '含义'] rows."""
    data = load_rule("statistical-scoring")
    rows: list[list[str]] = []
    for test in (data.get("tests") or {}).values():
        label = str(test.get("label", ""))
        for band in test.get("bands") or []:
            rows.append([
                label, str(band.get("score", "")),
                str(band.get("cond", "")), str(band.get("meaning", ""))[:50],
            ])
    return rows


# ── 2.34 metric selection — factor ROI / Contribution ranges ────────────────


@dataclass(frozen=True)
class FactorRange:
    """Expected ranges for one L4 factor (from factor-ranges.json)."""
    l4: str
    contribution: tuple[float, float] | None  # yearly contribution %, (lo, hi)
    roi: tuple[float, float] | None           # ROI range, (lo, hi)


def _parse_range(raw: object) -> tuple[float, float] | None:
    """Parse '0%~1.5%' / '-5%~5%' / '0.8~1.3' → (lo, hi); '/' or None → None."""
    if raw is None:
        return None
    txt = str(raw).replace("%", "").replace("％", "").strip()
    if "~" not in txt:
        return None
    lo, _, hi = txt.partition("~")
    try:
        return (float(lo), float(hi))
    except ValueError:
        return None


@lru_cache(maxsize=1)
def factor_ranges() -> dict[str, FactorRange]:
    """Map L4 factor name → its expected contribution / ROI ranges."""
    out: dict[str, FactorRange] = {}
    for f in load_rule("factor-ranges").get("factors") or []:
        l4 = str(f.get("L4", "")).strip()
        if not l4:
            continue
        out[l4] = FactorRange(l4, _parse_range(f.get("contributionYearly")),
                              _parse_range(f.get("roiRange")))
    return out


def match_factor_range(l4_name: str) -> FactorRange | None:
    """Find the expected ranges for an L4 factor (exact, else normalised match)."""
    if not l4_name:
        return None
    ranges = factor_ranges()
    if l4_name in ranges:
        return ranges[l4_name]
    norm = l4_name.strip().lower()
    for key, val in ranges.items():
        kn = key.strip().lower()
        if kn and (kn in norm or norm in kn):
            return val
    return None


def in_range(value: float, rng: tuple[float, float] | None) -> bool:
    return rng is not None and rng[0] <= value <= rng[1]


# ── Knowledge-first ROI / Contribution range resolver ───────────────────────
#
# The authoritative ranges are meant to be maintained in the Knowledge module as
# the industry ``factor_tree`` template (per-indicator L1–L4 + roiRange +
# contributionRange). This resolver prefers those, keyed at (L4, indicator)
# granularity, and falls back to the reference ``factor-ranges.json`` library.


def _norm(s: object) -> str:
    return str(s).strip().lower() if s is not None else ""


@dataclass(frozen=True)
class RangeBenchmark:
    """Expected ROI / Contribution bands for one indicator, with provenance."""
    roi: tuple[float, float] | None
    contribution: tuple[float, float] | None
    roi_text: str            # original display string, e.g. "0.8~1.3" or "/"
    contribution_text: str   # e.g. "0%~1.5%"
    source: str              # "knowledge" | "reference"


class RangeIndex:
    """(L4, indicator)-keyed benchmark lookup.

    Precedence: exact (L4, indicator) knowledge pair → L4-only knowledge (exact
    then normalised substring) → reference ``factor-ranges.json`` via
    :func:`match_factor_range`. Returns ``None`` when nothing matches.
    """

    def __init__(
        self,
        pair_index: dict[tuple[str, str], RangeBenchmark],
        l4_index: dict[str, RangeBenchmark],
    ) -> None:
        self._pairs = pair_index
        self._l4 = l4_index

    def match(self, l4: str, indicator: str) -> RangeBenchmark | None:
        l4n, indn = _norm(l4), _norm(indicator)
        # 1) exact (L4, indicator) knowledge pair.
        hit = self._pairs.get((l4n, indn))
        if hit is not None:
            return hit
        # 2) L4-only knowledge — exact then normalised substring.
        if l4n and l4n in self._l4:
            return self._l4[l4n]
        for key, val in self._l4.items():
            if key and (key in l4n or l4n in key):
                return val
        # 3) reference fallback.
        ref = match_factor_range(l4)
        if ref is not None:
            return RangeBenchmark(
                roi=ref.roi,
                contribution=ref.contribution,
                roi_text=_fmt_range(ref.roi, is_pct=False),
                contribution_text=_fmt_range(ref.contribution, is_pct=True),
                source="reference",
            )
        return None


def _fmt_range(rng: tuple[float, float] | None, *, is_pct: bool) -> str:
    """Reconstruct a display string for a parsed reference range (best effort)."""
    if rng is None:
        return "/"
    if is_pct:
        return f"{rng[0]:g}%~{rng[1]:g}%"
    return f"{rng[0]:g}~{rng[1]:g}"


def build_range_index(industry_l1: str | None, industry_l2: str | None) -> RangeIndex:
    """Build a :class:`RangeIndex` from the industry Knowledge factor-tree template.

    Reads the ``factor_tree`` template for the project industry (l2 beats l1),
    indexing every row that carries a parseable ROI or Contribution band. The
    reference library is used per-lookup as the final fallback in
    :meth:`RangeIndex.match`, so an empty template still yields reference ranges.
    """
    pair_index: dict[tuple[str, str], RangeBenchmark] = {}
    l4_index: dict[str, RangeBenchmark] = {}
    # Lazy import to avoid an import cycle (templates → domain.models → agents).
    try:
        from app.store.templates import get_templates
    except Exception:
        return RangeIndex(pair_index, l4_index)

    tpl = None
    if industry_l1:
        try:
            tpl = get_templates().best_match("factor_tree", industry_l1, industry_l2)
        except Exception:
            tpl = None
    if tpl is None:
        return RangeIndex(pair_index, l4_index)

    for row in tpl.factor_rows:
        roi_txt = str(getattr(row, "roi_range", "") or "")
        con_txt = str(getattr(row, "contribution_range", "") or "")
        roi = _parse_range(roi_txt)
        con = _parse_range(con_txt)
        if roi is None and con is None:
            continue
        bench = RangeBenchmark(
            roi=roi, contribution=con,
            roi_text=roi_txt or "/", contribution_text=con_txt or "/",
            source="knowledge",
        )
        l4n, indn = _norm(row.l4), _norm(row.indicator)
        if l4n and indn:
            pair_index.setdefault((l4n, indn), bench)
        if l4n:
            l4_index.setdefault(l4n, bench)  # first-wins
    return RangeIndex(pair_index, l4_index)
