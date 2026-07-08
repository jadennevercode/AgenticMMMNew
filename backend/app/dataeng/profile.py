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
from app.domain.models import FieldProfile, ReviewReport, RawTable

_SAMPLE = 5
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
    fp = FieldProfile(
        name=name, table=table, dtype=dtype, nonNull=non_null, nullRatio=null_ratio,
        distinct=int(series.nunique(dropna=True)), sampleValues=samples,
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


def _build_charts(frames: list[tuple[RawTable, pd.DataFrame]],
                  fields: list[FieldProfile], time_field: FieldProfile | None) -> list[dict]:
    charts: list[dict] = []
    # ── volatility bar (CV per numeric field) ────────────
    numerics = [f for f in fields if f.cv is not None]
    if numerics:
        numerics = sorted(numerics, key=lambda f: f.cv or 0, reverse=True)[:12]
        charts.append({
            "id": "volatility", "type": "bar", "title": "字段波动性 (CV)",
            "x": [f"{f.name}" for f in numerics],
            "series": [{"name": "CV", "data": [round(f.cv or 0, 3) for f in numerics],
                        "color": _CHART_COLORS[1]}],
            "interpretation": "CV<0.05 近似常数(建议剔除);≥0.2 波动充分,利于建模。",
        })
    # ── continuity line (records per period on the time axis) ─
    if time_field is not None:
        df = _frame_for(frames, time_field.table)
        if df is not None and time_field.name in df.columns:
            dts = _to_datetime(df[time_field.name])
            gran = time_field.time_granularity or "month"
            grp = (dts.dropna().dt.to_period(_period_freq(gran))
                   .value_counts().sort_index())
            if not grp.empty:
                charts.append({
                    "id": "continuity", "type": "line", "title": "时间连续性 (每期记录数)",
                    "x": [str(p) for p in grp.index.tolist()],
                    "series": [{"name": "records", "data": [int(v) for v in grp.tolist()],
                                "color": _CHART_COLORS[0]}],
                    "unit": gran,
                    "interpretation": f"{gran} 粒度,连续性 {(time_field.continuity or 0):.0%}"
                                      + (f",有 {time_field.gap_count} 处缺口。" if time_field.gap_count else "。"),
                })
    return charts


def _frame_for(frames: list[tuple[RawTable, pd.DataFrame]], table: str) -> pd.DataFrame | None:
    for meta, df in frames:
        if meta.name == table:
            return df
    return None


def build_review_report(project_id: str, asset) -> ReviewReport:
    """Profile every raw table of an asset and assemble the ReviewReport."""
    return report_from_frames(read_asset_frames(project_id, asset))


def report_from_frames(frames: list[tuple[RawTable, pd.DataFrame]]) -> ReviewReport:
    """Assemble a ReviewReport from already-read (RawTable, DataFrame) pairs.
    Split out from build_review_report so it is unit-testable without the file store."""
    tables = [meta for meta, _ in frames]
    fields: list[FieldProfile] = []
    warnings: list[str] = []
    total_rows = 0
    for meta, df in frames:
        total_rows += len(df)
        for col in df.columns:
            fields.append(_profile_field(meta.name, str(col), df[col]))
    if not frames:
        warnings.append("无可解析的原始表(仅支持 .xlsx/.xlsm/.csv)。")
    time_field = _pick_time_field(fields)
    if time_field is None and frames:
        warnings.append("未检测到时间轴 — 建模需要月度及以上的时间粒度。")
    elif time_field is not None and (time_field.continuity or 1) < 0.9:
        warnings.append(f"时间轴 “{time_field.name}” 连续性偏低({(time_field.continuity or 0):.0%}),存在缺口。")
    charts = _build_charts(frames, fields, time_field)
    return ReviewReport(
        rowCount=total_rows, columnCount=len(fields), tables=tables, fields=fields,
        charts=charts,
        timeField=(time_field.name if time_field else None),
        timeGranularity=(time_field.time_granularity if time_field else None),
        warnings=warnings, generatedAt=_now_iso(),
    )
