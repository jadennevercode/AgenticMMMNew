"""Quick-review profiling engine.

Given a registered data asset's raw tables, produce a ReviewReport: per-field type
inference, completeness, distinct counts, numeric stats + volatility (CV), and —
for the detected time axis — granularity (day/week/month/quarter/year) and
continuity (fraction of expected periods present + gap count). It also emits charts
in the frontend ``ReviewChart`` shape so the existing recharts renderer draws them.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.dataeng.sources import read_asset_frames
from app.domain.models import FieldProfile, ReviewReport, RawTable, TableReview

_SAMPLE = 5
_ENUM_MAX = 50  # a text field with ≤ this many distinct values is an enum candidate
_TIME_PARSE_MIN = 0.6  # ≥60% of cells must parse as dates to call a column a time axis

# Granularity by median spacing (days) between consecutive distinct periods.
_GRAN_BANDS = [
    (2.0, "day"),
    (10.0, "week"),
    (45.0, "month"),
    (135.0, "quarter"),
    (500.0, "year"),
]

_CHART_COLORS = ["#6366f1", "#f59e0b", "#14b8a6", "#f43f5e"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_datetime(series: pd.Series) -> pd.Series:
    """Best-effort parse a column to datetimes (handles yyyymm ints and 'YYYY-MM')."""
    s = series.dropna()
    if s.empty:
        return pd.Series([], dtype="datetime64[ns]")
    # yyyymm integers like 202301 → parse via string.
    as_str = s.astype(str).str.strip()
    looks_yyyymm = as_str.str.fullmatch(r"\d{6}")
    if looks_yyyymm.mean() > _TIME_PARSE_MIN:
        return pd.to_datetime(as_str + "01", format="%Y%m%d", errors="coerce")
    # Try common explicit formats first (faster, no dateutil fallback warning).
    for fmt in ("%Y-%m", "%Y/%m", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m"):
        parsed = pd.to_datetime(as_str, format=fmt, errors="coerce")
        if parsed.notna().mean() > _TIME_PARSE_MIN:
            return parsed
    return pd.to_datetime(as_str, errors="coerce", format="mixed")


def _granularity(dts: pd.Series) -> str:
    uniq = pd.Series(dts.dropna().unique()).sort_values()
    if len(uniq) < 2:
        return "month"
    diffs = uniq.diff().dropna().dt.days
    med = float(np.median(diffs)) if len(diffs) else 30.0
    for threshold, label in _GRAN_BANDS:
        if med <= threshold:
            return label
    return "year"


def _continuity(dts: pd.Series, granularity: str) -> tuple[float, int]:
    """Fraction of expected periods present + count of missing periods."""
    uniq = pd.Series(dts.dropna().dt.to_period(_period_freq(granularity)).unique())
    if len(uniq) < 2:
        return 1.0, 0
    span = pd.period_range(uniq.min(), uniq.max(), freq=_period_freq(granularity))
    present = set(uniq.tolist())
    expected = len(span)
    have = sum(1 for p in span if p in present)
    gaps = expected - have
    return (have / expected if expected else 1.0), int(gaps)


def _period_freq(granularity: str) -> str:
    return {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}.get(
        granularity, "M")


def _infer_dtype(series: pd.Series) -> str:
    s = series.dropna()
    if s.empty:
        return "empty"
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    numeric = pd.to_numeric(s, errors="coerce")
    if numeric.notna().mean() > 0.9:
        return "integer" if (numeric.dropna() % 1 == 0).all() else "number"
    dts = _to_datetime(s)
    if dts.notna().mean() > _TIME_PARSE_MIN:
        return "datetime"
    return "text"


def _profile_field(table: str, name: str, series: pd.Series) -> FieldProfile:
    total = len(series)
    non_null = int(series.notna().sum())
    null_ratio = round(1 - (non_null / total), 4) if total else 1.0
    dtype = _infer_dtype(series)
    samples = [str(v) for v in series.dropna().unique()[:_SAMPLE]]
    distinct = int(series.nunique(dropna=True))
    # Low-cardinality text ⇒ enum candidate: keep the FULL value list so mappings
    # can be reviewed against every raw spelling, not a 3-value sample.
    enum_values: list[str] = []
    if dtype == "text" and 0 < distinct <= _ENUM_MAX:
        enum_values = sorted(str(v) for v in series.dropna().unique())
    fp = FieldProfile(
        name=name, table=table, dtype=dtype, nonNull=non_null, nullRatio=null_ratio,
        distinct=distinct, sampleValues=samples, enumValues=enum_values,
    )
    if dtype in ("number", "integer"):
        numeric = pd.to_numeric(series, errors="coerce").dropna()
        if not numeric.empty:
            mean = float(numeric.mean())
            std = float(numeric.std(ddof=0))
            fp.minimum = float(numeric.min())
            fp.maximum = float(numeric.max())
            fp.mean = round(mean, 4)
            fp.std = round(std, 4)
            fp.cv = round(std / abs(mean), 4) if mean else None
            fp.negatives = int((numeric < 0).sum())
            cv_txt = f", CV={fp.cv}" if fp.cv is not None else ""
            neg_txt = f", {fp.negatives} negative" if fp.negatives else ""
            fp.note = f"numeric range [{fp.minimum:g}, {fp.maximum:g}]{cv_txt}{neg_txt}"
    elif dtype == "datetime":
        dts = _to_datetime(series)
        if dts.notna().any():
            gran = _granularity(dts)
            cont, gaps = _continuity(dts, gran)
            fp.is_time_axis = True
            fp.time_granularity = gran
            fp.continuity = round(cont, 4)
            fp.gap_count = gaps
            span = f"{dts.min():%Y-%m} → {dts.max():%Y-%m}"
            fp.note = f"{gran} axis, {span}, continuity {cont:.0%}" + (
                f", {gaps} gap(s)" if gaps else "")
    if not fp.note and null_ratio > 0.1:
        fp.note = f"{null_ratio:.0%} missing"
    return fp


def _pick_time_field(fields: list[FieldProfile]) -> FieldProfile | None:
    times = [f for f in fields if f.is_time_axis]
    if not times:
        return None
    # Prefer the most-continuous, most-granular axis.
    return sorted(times, key=lambda f: (f.continuity or 0, f.distinct), reverse=True)[0]


def _build_charts(df: pd.DataFrame, fields: list[FieldProfile],
                  time_field: FieldProfile | None) -> list[dict]:
    """Charts for ONE table, built only from that table's frame + fields."""
    charts: list[dict] = []
    # ── volatility bar (CV per numeric field) ────────────
    numerics = [f for f in fields if f.cv is not None]
    if numerics:
        numerics = sorted(numerics, key=lambda f: f.cv or 0, reverse=True)[:12]
        charts.append({
            "id": "volatility", "type": "bar", "title": "Field volatility (CV)",
            "x": [f"{f.name}" for f in numerics],
            "series": [{"name": "CV", "data": [round(f.cv or 0, 3) for f in numerics],
                        "color": _CHART_COLORS[1]}],
            "interpretation": "CV<0.05 is near-constant (consider dropping); ≥0.2 varies enough to model.",
        })
    # ── continuity line (records per period on the time axis) ─
    if time_field is not None and time_field.name in df.columns:
        dts = _to_datetime(df[time_field.name])
        gran = time_field.time_granularity or "month"
        grp = (dts.dropna().dt.to_period(_period_freq(gran))
               .value_counts().sort_index())
        if not grp.empty:
            charts.append({
                "id": "continuity", "type": "line", "title": "Time continuity (records per period)",
                "x": [str(p) for p in grp.index.tolist()],
                "series": [{"name": "records", "data": [int(v) for v in grp.tolist()],
                            "color": _CHART_COLORS[0]}],
                "unit": gran,
                "interpretation": f"{gran} grain, {(time_field.continuity or 0):.0%} continuity"
                                  + (f", {time_field.gap_count} gap(s)." if time_field.gap_count else "."),
            })
    return charts


def _review_table(meta: RawTable, df: pd.DataFrame) -> TableReview:
    """Profile a single table into a self-contained TableReview."""
    fields = [_profile_field(meta.name, str(col), df[col]) for col in df.columns]
    time_field = _pick_time_field(fields)
    warnings: list[str] = []
    if time_field is None:
        warnings.append("No time axis detected — modeling needs monthly-or-finer granularity.")
    elif (time_field.continuity or 1) < 0.9:
        warnings.append(f"Time axis “{time_field.name}” has low continuity "
                        f"({(time_field.continuity or 0):.0%}) — there are gaps.")
    return TableReview(
        name=meta.name, rowCount=int(len(df)), columnCount=len(fields), fields=fields,
        charts=_build_charts(df, fields, time_field),
        timeField=(time_field.name if time_field else None),
        timeGranularity=(time_field.time_granularity if time_field else None),
        warnings=warnings,
    )


def build_review_report(project_id: str, asset) -> ReviewReport:
    """Profile every raw table of an asset and assemble the ReviewReport."""
    return report_from_frames(read_asset_frames(project_id, asset))


def report_from_frames(frames: list[tuple[RawTable, pd.DataFrame]]) -> ReviewReport:
    """Assemble a ReviewReport from already-read (RawTable, DataFrame) pairs. Each
    table is reviewed independently (per-dataset qualities + charts); ``fields`` is the
    flattened union kept for long-table grounding. Split out so it is unit-testable."""
    tables = [meta for meta, _ in frames]
    table_reviews = [_review_table(meta, df) for meta, df in frames]
    fields = [f for tr in table_reviews for f in tr.fields]
    warnings: list[str] = []
    if not frames:
        warnings.append("No parseable raw tables (only .xlsx/.xlsm/.csv are supported).")
    # Report-level time axis = the first table's, for the legacy badge only.
    first = table_reviews[0] if table_reviews else None
    return ReviewReport(
        rowCount=sum(tr.row_count for tr in table_reviews),
        columnCount=len(fields), tables=tables, fields=fields,
        tableReviews=table_reviews, charts=[],
        timeField=(first.time_field if first else None),
        timeGranularity=(first.time_granularity if first else None),
        warnings=warnings, generatedAt=_now_iso(),
    )
