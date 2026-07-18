"""2.4 Statistical Score — score every FactorTree indicator on the 2.33 tests.

For each indicator (an L1–L4 factor + its metric, grouped straight from the
Data-Processing long table) we compute three statistics against the modeling
time axis and the KPI (Y):

* **CV** (volatility)   — reference formula: min-max scale to [0,1], variance/mean.
* **Pearson** (vs KPI)  — signed correlation of the indicator with Y.
* **VIF** (collinearity)— per-indicator variance inflation across ALL indicators.

Each maps to a 0/0.5/1/2 band (``data_rules``); Total = CV+Pearson+VIF drives the
Good / Acceptable / Unconsiderable verdict. The result is a ``StatScorecard`` the
human reviews on the Canvas (per-indicator include / review / drop). Numbers are
computed from the real long table via pandas/numpy — never from the LLM.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents import data_rules
from app.agents.data_rules import reference_cv, score_statistical, vif_all
from app.domain.models import StatScoreRow, StatScorecard
from app.mmm.pivot import _is_y_row, _pick_y_metric
from app.store.state import ProjectState

# A disposition default per verdict: keep the good ones, send the middle band to
# the human, drop the unusable — the human can override any of these on the Canvas.
_DISPOSITION_DEFAULT: dict[str, str] = {
    "Good": "include",
    "Acceptable": "review",
    "unconsiderable": "drop",
}


def _monthly_y(df: pd.DataFrame) -> pd.Series | None:
    """Global monthly KPI (Y) series — the response the indicators are scored against."""
    y_rows = df[_is_y_row(df)]
    if y_rows.empty:
        return None
    y_metric = _pick_y_metric(y_rows)
    s = (
        y_rows[y_rows["metric"] == y_metric]
        .dropna(subset=["month"])
        .groupby("month")["value"].sum()
        .sort_index()
    )
    return s if not s.empty else None


def _indicator_series(df: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    """Build one monthly series per (l1,l2,l3,l4,metric) indicator.

    Returns (metas, wide) where ``wide`` is a month-indexed frame with one column
    per indicator (aligned, gaps zero-filled) and ``metas`` carries its L1–L4 path.
    Constant / all-NaN indicators are dropped (no volatility, undefined VIF).
    """
    metas: list[dict] = []
    series: dict[str, pd.Series] = {}
    grouped = df.groupby(["l1", "l2", "l3", "l4", "metric"], dropna=False)
    for i, ((l1, l2, l3, l4, metric), grp) in enumerate(grouped):
        name = str(metric)
        if not name.strip() or name == "<NA>":
            continue
        if _is_y_row(grp).all():  # the KPI itself is not a candidate driver
            continue
        s = (
            grp.dropna(subset=["month"])
            .groupby("month")["value"].sum()
            .sort_index()
        )
        if s.empty or float(np.nanstd(s.to_numpy(dtype=float))) == 0.0:
            continue
        col = f"i{i}"
        series[col] = s
        metas.append({"col": col, "l1": _s(l1), "l2": _s(l2), "l3": _s(l3),
                      "l4": _s(l4), "indicator": name})
    if not series:
        return [], pd.DataFrame()
    wide = pd.concat(series, axis=1).sort_index()
    wide = wide.fillna(0.0)
    return metas, wide


def _s(v: object) -> str:
    return "" if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v)


def build_stat_scorecard(st: ProjectState) -> StatScorecard:
    """Score the indicators still in play on CV / Pearson / VIF.

    Indicators an earlier layer already rejected (2.1 mapping, 2.2 quality, 2.3
    sign-off) are not scored at all. That is not just bookkeeping: re-scoring
    them would put a settled decision back in front of the human as if it were
    open, and — because VIF is computed across the whole set at once — the dead
    indicators' collinearity would inflate the VIF of the ones still in play.
    """
    from app.agents.dataset_cache import model_df
    from app.agents.ledger import _matches, _norm_pair, drops_before

    df = model_df(st)
    y = _monthly_y(df)
    metas, wide = _indicator_series(df)
    if not metas or y is None:
        return StatScorecard(rows=[])

    inherited = drops_before(st, "statistical")
    if inherited:
        metas = [m for m in metas
                 if not _matches(_norm_pair(m["l4"], m["indicator"]), inherited)]
        if not metas:
            return StatScorecard(rows=[])

    cols = [m["col"] for m in metas]
    # VIF is computed once across ALL indicators, at indicator granularity.
    vifs = vif_all(wide[cols].to_numpy(dtype=float))
    vif_by_col = dict(zip(cols, vifs))
    # Align each indicator to Y on the shared month index for Pearson.
    y_aligned = y.reindex(wide.index)

    rows: list[StatScoreRow] = []
    for m in metas:
        col = m["col"]
        x = wide[col].to_numpy(dtype=float)
        cv = reference_cv(x)
        pearson = _pearson(wide[col], y_aligned)
        vif = float(vif_by_col.get(col, 1.0))
        sc = score_statistical(cv, pearson, vif)
        rows.append(StatScoreRow(
            id=f"s-{col}", l1=m["l1"], l2=m["l2"], l3=m["l3"], l4=m["l4"],
            indicator=m["indicator"], cv=round(cv, 4), pearson=round(pearson, 4),
            vif=round(vif, 3), cvScore=sc.cv_score, pearsonScore=sc.pearson_score,
            vifScore=sc.vif_score, total=sc.total, autoVerdict=sc.verdict,
            disposition=_DISPOSITION_DEFAULT.get(sc.verdict, "review"),
        ))
    # Worst first so the reviewer sees the risky indicators at the top.
    rows.sort(key=lambda r: (r.total, r.indicator))
    return StatScorecard(rows=rows)


def _pearson(x: pd.Series, y: pd.Series) -> float:
    """Signed Pearson r between two aligned month-indexed series (0.0 if undefined)."""
    xv = x.to_numpy(dtype=float)
    yv = y.to_numpy(dtype=float)
    mask = ~(np.isnan(xv) | np.isnan(yv))
    if mask.sum() < 3:
        return 0.0
    xv, yv = xv[mask], yv[mask]
    if np.std(xv) == 0.0 or np.std(yv) == 0.0:
        return 0.0
    r = float(np.corrcoef(xv, yv)[0, 1])
    return 0.0 if np.isnan(r) else r


def accepted_stat_labels(card: StatScorecard) -> list[str]:
    """Indicators the human kept (disposition != drop) — the 2.4 → 2.5 hand-off."""
    return [f"{r.l4 or r.l3} · {r.indicator}".strip(" ·")
            for r in card.rows if r.disposition != "drop"]


# Column layout for the Sheet2-style artifact body (mirrors the reference workbook).
STAT_COLUMNS = ["L1", "L2", "L3", "L4", "Indicator", "CV", "Pearson", "VIF",
                "CV score", "Corr score", "VIF score", "Total", "Verdict", "Disposition",
                "AI rationale"]

_VERDICT_EN = {"Good": "Good", "Acceptable": "Acceptable", "unconsiderable": "Unconsiderable"}
_DISPOSITION_EN = {"include": "Include", "review": "Review", "drop": "Drop"}


def stat_sheet(card: StatScorecard) -> dict:
    """Render the 2.4 artifact: the rule page (Sheet1) + the per-indicator results
    page (Sheet2), matching the reference ``Data statistical test`` workbook."""
    result_rows = [[
        r.l1, r.l2, r.l3, r.l4, r.indicator,
        f"{r.cv:.2f}", f"{r.pearson:+.2f}", f"{r.vif:.1f}",
        f"{r.cv_score:g}", f"{r.pearson_score:g}", f"{r.vif_score:g}",
        f"{r.total:g}", _VERDICT_EN.get(r.auto_verdict, r.auto_verdict),
        _DISPOSITION_EN.get(r.disposition, r.disposition), r.rationale,
    ] for r in card.rows]
    return {"sheets": [
        {"name": "Scoring rules", "columns": ["Test", "Score", "Condition", "Meaning"],
         "rows": data_rules.statistical_rule_rows()},
        {"name": "Statistical score", "columns": STAT_COLUMNS,
         "rows": result_rows or [["—"] + [""] * (len(STAT_COLUMNS) - 1)]},
    ]}
