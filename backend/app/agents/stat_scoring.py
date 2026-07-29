"""2.4 Statistical Score — score every FactorTree indicator on the 2.33 tests.

For each indicator (an L1–L4 factor + its metric, grouped straight from the
Data-Processing long table) we compute three statistics against the modeling
time axis and the KPI (Y):

* **CV** (volatility)   — reference formula: min-max scale to [0,1], variance/mean.
* **Pearson** (vs KPI)  — signed correlation of the indicator with Y.
* **VIF** (collinearity)— per-indicator variance inflation across ALL indicators.

Each maps to a 0/0.5/1 band (``data_rules``); Total = CV×Pearson×VIF (a single
failing test zeroes it) drives the Good / Acceptable / Unconsiderable verdict.
The result is a ``StatScorecard`` the human reviews on the Canvas (per-indicator
include / review / drop). Numbers are computed from the real long table via
pandas/numpy — never from the LLM.

**The tests run on a panel, not on an aggregate (2026-07-27).** They used to score
one national series per indicator — 34 points, produced by collapsing every
channel and product into a single total *before* any statistic was computed. The
panel is instead stacked over the model objects themselves: one row per
``(model object, month)``, so an indicator is measured across every channel ×
product the model will actually be fitted on. Two things follow, and both matter:

* there are now ``n_objects × n_months`` observations instead of ``n_months``, which
  moves VIF out of the under-determined regime (``vif_all``'s pairwise-max proxy)
  and into the exact ``inv(R)`` one for the first time;
* an indicator that is flat inside one channel but differs sharply between
  channels is no longer indistinguishable from a genuinely constant one.

Region and the L5–L8 residual still roll up inside each cell, with that
indicator's own 2.1 aggregation — they are *inside* a model object, and indicators
disagree about how deep they report, so a panel keyed on them would leave two
indicators sharing no rows at all and silently correlate them on nothing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents import data_rules
from app.agents.data_rules import reference_cv, score_statistical, vif_all
from app.domain.models import StatScoreRow, StatScorecard
from app.mmm.pivot import _is_y_row, _pick_y_metric
from app.store.state import ProjectState
from app.tools import get as get_tool
from app.tools.tracing import traced

# A disposition default per verdict: keep the good ones, send the middle band to
# the human, drop the unusable — the human can override any of these on the Canvas.
_DISPOSITION_DEFAULT: dict[str, str] = {
    "Good": "include",
    "Acceptable": "review",
    "unconsiderable": "drop",
}

# Monthly data: a year-over-year difference removes the level, the trend and the
# seasonality in one step. Both correlation-based tests need this — on raw levels
# every indicator correlates with the KPI and with every other indicator, because
# they all ride the same seasonal trend, and the tests measure that instead of the
# indicator. CV is deliberately NOT differenced: it asks whether the series moves
# at all, which is a property of the level series.
DETREND_PERIOD = 12

# Guard on the RESULT of differencing, not the input length: a 13-14 month
# project differences down to 1-2 rows, and Pearson's `mask.sum() < 3` guard
# then silently returns 0.0 for every indicator, dropping everything with no
# explanation. Below this many resulting rows, skip differencing altogether.
MIN_DETRENDED_POINTS = 6

# Minimum observed months for an indicator's statistics to mean anything —
# aligned with `pivot.MIN_MONTHS`, which is the bar for entering the model at all.
# A shorter indicator is still emitted (with a zero total and an explicit note)
# rather than dropped, so the funnel count stays honest about what was screened.
MIN_SCORED_MONTHS = 12
_SHORT_COVERAGE_VERDICT = "unconsiderable"

# The panel's row key: one observation per model object per month.
PANEL_LEVELS = ("object", "month")

# How many indicators a VIF is measured against — the width of a *realistic* model,
# mirroring `pivot.MAX_DRIVERS`. See `_design_vifs` for why this is not "all of them".
from app.mmm.pivot import MAX_DRIVERS as SCREEN_DESIGN_COLS  # noqa: E402


def can_detrend(n_months: int, period: int = DETREND_PERIOD) -> bool:
    """Whether year-over-year differencing leaves enough points to be worth doing.

    A short project should still be screened, just without the seasonal
    correction, rather than being handed a handful of points too few for Pearson
    (or anything else) to say anything meaningful.
    """
    return n_months - period >= MIN_DETRENDED_POINTS


def _panel_yoy(frame, period: int = DETREND_PERIOD):
    """Year-over-year difference **within each model object**.

    A plain positional diff down the stacked panel would subtract one channel's
    first months from the next channel's last ones at every object boundary. The
    difference is taken inside each object's own contiguous month range, which
    ``_indicator_panel`` guarantees by reindexing every object onto the same
    complete calendar.
    """
    return frame.groupby(level="object").diff(period)


def _panel_within(frame):
    """Standardize each column **inside each model object** before pooling.

    The correlation tests ask a within-object question — "when this indicator moves
    in a channel × product cell, does that cell's response move with it" — but a
    pooled panel answers a mixed one, and the between-object part of it is noise for
    this purpose. It is also actively misleading: a national driver (TV, search) is
    the *same series* in every object while the response differs several-fold between
    them, so pooling raw year-over-year changes buries a real relationship under
    cross-sectional scale. On the synthetic case that attenuated every |r| to below
    0.25 — including drivers generated with a known 6–8% contribution — and 2.4 then
    scored 15 of 18 indicators unconsiderable, keeping the three that do least.

    Removing each object's own mean and scale (the standard within/fixed-effects
    transform) makes every object contribute its own co-movement on equal terms.
    Constant-within-object columns come back as zeros, which the tests already read
    as "no relationship" rather than dividing by zero.
    """
    def _z(g):
        sd = g.std()
        return (g - g.mean()) / sd.replace(0.0, np.nan) if hasattr(sd, "replace") else (
            (g - g.mean()) / (sd if sd else np.nan))

    return frame.groupby(level="object", group_keys=False).apply(_z)


def _complete_month_index(idx: "pd.Index") -> "pd.Index":
    """The full contiguous yyyymm month range spanning ``idx``'s min..max.

    Successive months are NOT successive integers (...202412, 202501...), so
    the range has to be built by calendar arithmetic, not ``range()``. Used to
    reindex the panel before year-over-year differencing: a month missing
    anywhere in the panel would otherwise silently turn ``a[12:] - a[:-12]``
    into a "12 rows ago" difference across the gap instead of a true YoY one.
    """
    if idx.empty:
        return idx
    lo, hi = int(idx.min()), int(idx.max())
    y, m = divmod(lo, 100)
    months: list[int] = []
    cur = lo
    while cur <= hi:
        months.append(cur)
        m += 1
        if m > 12:
            m = 1
            y += 1
        cur = y * 100 + m
    return pd.Index(months, name=idx.name)


def _roll_monthly(grp: pd.DataFrame, st, l4: object, metric: object) -> pd.Series:
    """One value per month, rolled up the way 2.1 says this indicator rolls up.

    A national row is still split across the L5–L8 residual, so within a single
    month there can be several rows for one indicator. Summing them is only right
    for an additive metric: a coverage rate or a price index summed across its
    sub-paths produces a number with no meaning, and it was that number the CV,
    Pearson and VIF tests were scoring.
    """
    from app.agents.overrides import pandas_agg, resolve_aggregation

    return (grp.dropna(subset=["month"])
            .groupby("month")["value"]
            .agg(pandas_agg(resolve_aggregation(st, l4, metric)))
            .sort_index())


def _monthly_y(df: pd.DataFrame, st=None) -> pd.Series | None:
    """Monthly KPI (Y) series — the response the indicators are scored against.

    The response is whichever indicator the user tagged ``Y`` at 2.1, resolved
    through ``overrides.resolved_y_metric``. 2.4 used to auto-pick its own Y by
    month coverage, so it could correlate every indicator against a different
    response than 2.5 would go on to fit.
    """
    from app.agents.overrides import resolved_y_metric

    y_rows = df[_is_y_row(df)]
    if y_rows.empty:
        return None
    y_metric = resolved_y_metric(st, df) or _pick_y_metric(y_rows)
    sel = y_rows[y_rows["metric"] == y_metric]
    if sel.empty:
        return None
    y_l4 = str(sel["l4"].iloc[0]) if "l4" in sel.columns else ""
    s = _roll_monthly(sel, st, y_l4, y_metric)
    return s if not s.empty else None


def _indicator_series(df: pd.DataFrame, st=None, *,
                      drop_constant: bool = True) -> tuple[list[dict], pd.DataFrame]:
    """Build one monthly series per (l1,l2,l3,l4,metric) indicator, for one slice.

    ``drop_constant=False`` keeps a series that never moves *inside this slice*.
    The panel builder needs that: an indicator can be flat in one channel and
    still carry all its information in how it differs between channels, and
    dropping it per slice would delete that before the panel is stacked.

    Returns (metas, wide) where ``wide`` is a month-indexed frame with one column
    per indicator and ``metas`` carries its L1–L4 path plus the number of months
    the indicator was actually observed. Constant / all-NaN indicators are dropped
    (no volatility, undefined VIF).

    **Gaps stay NaN.** They used to be zero-filled, which silently turned "this
    indicator did not exist before 2023" into "this indicator was zero for two
    years": CV then measured a step function instead of the series' own movement,
    Pearson correlated the zero block against the KPI's trend, and every short
    indicator shared that same zero block so VIF read them as collinear with each
    other. All three tests were scoring the padding.
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
        s = _roll_monthly(grp, st, l4, metric)
        if s.empty:
            continue
        if drop_constant and float(np.nanstd(s.to_numpy(dtype=float))) == 0.0:
            continue
        col = f"i{i}"
        series[col] = s
        metas.append({"col": col, "l1": _s(l1), "l2": _s(l2), "l3": _s(l3),
                      "l4": _s(l4), "indicator": name,
                      "months": int(s.notna().sum())})
    if not series:
        return [], pd.DataFrame()
    wide = pd.concat(series, axis=1).sort_index()
    return metas, wide


def _s(v: object) -> str:
    return "" if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v)


def _design_vifs(detr: np.ndarray, r_by_col: list[float]) -> tuple[np.ndarray, list[int]]:
    """Per-indicator VIF measured against a **realistic model**, not the whole
    candidate universe.

    VIF is a property of a design matrix: "how much is this column's variance
    inflated by the *other columns in the model*". Screening asked it of all ~93
    candidates at once, which fails in both of `vif_all`'s regimes and for the same
    underlying reason — there is no real design in which 93 co-seasonal marketing
    series sit together. On a short panel it lands in the under-determined
    pairwise-max proxy, where almost every series has some peer correlated above
    0.89; on a longer one it reaches the identified branch and inverts a
    pairwise-complete correlation matrix that is nowhere near positive-definite, so
    every VIF pins to ``VIF_MAX``. Either way nearly everything scored VIF >= 5, the
    2.33 band zeroed its total, and 2.4 dropped ~90% of the indicators it was asked
    to screen.

    So each indicator is measured against the model it could actually be in: the
    ``SCREEN_DESIGN_COLS`` most Y-correlated indicators. Members of that set get
    their VIF from that matrix; an indicator outside it is measured against the
    strongest ``SCREEN_DESIGN_COLS - 1`` peers plus itself — the same question,
    asked of a design it could plausibly join. Since 2.5 now fits every surviving
    candidate of a model object at once, and an object's universe is a dozen-odd
    indicators rather than the whole tree, that design is also close to the fit the
    indicator will really sit in.

    The 2.33 band is untouched (``VIF <= 1`` → 1, ``< 5`` → 0.5, ``>= 5`` → 0) and
    `vif_all` itself is untouched; only the matrix it is handed changes.

    Returns ``(vifs, base_idx)``.
    """
    n_cols = detr.shape[1]
    k = min(SCREEN_DESIGN_COLS, n_cols)
    base = sorted(range(n_cols), key=lambda i: -abs(r_by_col[i]))[:k]
    base_set = set(base)

    vifs = np.ones(n_cols, dtype=float)
    base_vifs = get_tool("stat.vif").run(detr[:, base])
    for pos, i in enumerate(base):
        vifs[i] = float(base_vifs[pos])

    # Secondary path — deliberately untraced, so screening still records exactly
    # one `stat.vif` invocation per task run (see CLAUDE.md's tracing granularity).
    peers = base[: max(k - 1, 1)]
    for i in range(n_cols):
        if i in base_set:
            continue
        cols = [j for j in peers if j != i] + [i]
        out = get_tool("stat.vif").run(detr[:, cols])
        vifs[i] = float(out[-1])
    return vifs, base


def _indicator_panel(st, df: pd.DataFrame,
                     objects: list[str]) -> tuple[list[dict], pd.DataFrame, pd.Series]:
    """Stack every model object's monthly series into one ``(object, month)`` panel.

    Returns ``(metas, wide, y)``. ``wide``'s columns are indicator ids that are
    **stable across objects** — the same ``(l1..l4, metric)`` indicator is one
    column no matter how many channels report it, which is what makes a single
    scorecard row per indicator meaningful. ``y`` is the response on the same
    index: each cell's own KPI, so an indicator is correlated against the sales it
    could actually have driven rather than against a national total.

    Each object's rows are reindexed onto the panel's complete calendar range
    before anything is differenced positionally. A month missing in one channel
    would otherwise turn that channel's ``a[12:] - a[:-12]`` into a "12 rows ago"
    difference across the gap instead of a true year-over-year one.
    """
    cols: dict[tuple, str] = {}
    metas_by_col: dict[str, dict] = {}
    frames: dict[str, pd.DataFrame] = {}
    y_parts: dict[str, pd.Series] = {}

    from app.agents.model_objects import object_mask

    for obj in objects:
        sub = df[object_mask(df, obj)]
        if sub.empty:
            continue
        y = _monthly_y(sub, st)
        if y is None or y.empty:
            continue
        # Constant-inside-this-channel series are kept: the panel is where that
        # question is answered, once, over every channel at the same time.
        metas, wide = _indicator_series(sub, st, drop_constant=False)
        if not metas:
            continue
        rename: dict[str, str] = {}
        for m in metas:
            key = (m["l1"], m["l2"], m["l3"], m["l4"], m["indicator"])
            col = cols.get(key)
            if col is None:
                col = cols[key] = f"i{len(cols)}"
                metas_by_col[col] = {"col": col, **dict(zip(
                    ("l1", "l2", "l3", "l4", "indicator"), key)), "months": 0}
            rename[m["col"]] = col
        frames[obj] = wide.rename(columns=rename)
        y_parts[obj] = y

    if not frames:
        return [], pd.DataFrame(), pd.Series(dtype=float)

    all_months = pd.Index(sorted({int(m) for f in frames.values() for m in f.index}))
    full_months = _complete_month_index(all_months)
    aligned: dict[str, pd.DataFrame] = {}
    for obj, f in frames.items():
        g = f.reindex(full_months)
        g["__Y__"] = y_parts[obj].reindex(full_months)
        aligned[obj] = g
    panel = pd.concat(aligned, names=list(PANEL_LEVELS))

    y_panel = panel["__Y__"]
    wide = panel.drop(columns="__Y__")
    # Months an indicator was actually observed anywhere in the panel — the same
    # coverage question `MIN_SCORED_MONTHS` has always asked, now over every cell.
    months_level = wide.index.get_level_values("month")
    metas: list[dict] = []
    for col, meta in metas_by_col.items():
        seen = wide[col].notna()
        if not bool(seen.any()):
            continue
        if float(np.nanstd(wide[col].to_numpy(dtype=float))) == 0.0:
            continue  # constant across the whole panel → no volatility, no VIF
        metas.append({**meta, "months": int(months_level[seen].nunique())})
    return metas, wide, y_panel


def build_stat_scorecard(st: ProjectState, *, eng=None,
                         task_id: str | None = None) -> StatScorecard:
    """Score the indicators still in play on CV / Pearson / VIF, over the panel.

    Pass ``eng``/``task_id`` (the 2.4 handler does) to record the three checks as
    explicit tool invocations. Secondary callers that merely re-derive the card
    for lookup leave them off, so they don't manufacture phantom invocations.

    Indicators an earlier layer already rejected (2.1 mapping, 2.2 quality, 2.3
    sign-off) are not scored at all. That is not just bookkeeping: re-scoring
    them would put a settled decision back in front of the human as if it were
    open, and — because VIF is computed across the whole set at once — the dead
    indicators' collinearity would inflate the VIF of the ones still in play.

    One row per indicator (2026-07-27). An indicator is now measured **once,
    across every channel × product at the same time**, instead of being re-screened
    inside each channel's own aggregate: three statistics over ``n_objects ×
    n_months`` observations answer the question the human is actually being asked
    at 2.4d — is this indicator usable — and answer it on more evidence than any
    single channel could provide. The verdict is therefore recorded globally and
    every model object inherits it.
    """
    from app.agents.dataset_cache import model_df, model_objects
    from app.agents.ledger import _matches, _norm_pair, drops_before

    from app.agents import factor_link
    link = factor_link.build(st)

    df = model_df(st)
    objects = model_objects(st)
    metas, wide, y = _indicator_panel(st, df, objects)
    if not metas or wide.empty or y.empty:
        return StatScorecard(rows=[])

    inherited = drops_before(st, "statistical")
    if inherited:
        metas = [m for m in metas
                 if not _matches(_norm_pair(m["l4"], m["indicator"]), inherited)]
    if not metas:
        return StatScorecard(rows=[])

    cols = [m["col"] for m in metas]
    n = len(cols)
    n_cells = int(wide.index.get_level_values("object").nunique())
    scope = f"{n} indicators × {n_cells} model object(s)"

    # The three 2.33 tests, each a registered tool — one explicit call per test,
    # batched over every indicator (see app/tools/registry.py).
    cvs = traced(
        eng, st, task_id, "stat.cv", f"{scope}: pooled series",
        get_tool("stat.cv").run, [wide[c].to_numpy(dtype=float) for c in cols],
        summarize=lambda vals: f"CV {min(vals):.2f}–{max(vals):.2f}" if vals else "no indicators",
    )
    cv_by_col = dict(zip(cols, cvs))

    # CV stays on raw levels — see DETREND_PERIOD. The two correlation tests run on
    # year-over-year differences (or, on a too-short project — see
    # MIN_DETRENDED_POINTS — on the raw levels; the trace below says which).
    # Differencing is **within each object**: a diff that ran down the stacked
    # panel would subtract one channel's first months from another channel's last.
    n_months = int(wide.index.get_level_values("month").nunique())
    if can_detrend(n_months):
        detr_df, y_detr_s = _panel_yoy(wide[cols]), _panel_yoy(y)
        period_label = f"{n_months - DETREND_PERIOD} year-over-year periods × {n_cells} object(s)"
    else:
        detr_df, y_detr_s = wide[cols], y
        period_label = f"{n_months} monthly points × {n_cells} object(s) (too short to detrend)"
    # Pool on within-object co-movement, not on cross-sectional scale — see
    # `_panel_within`. Skipped for a single object, where there is nothing between.
    if n_cells > 1:
        detr_df, y_detr_s = _panel_within(detr_df), _panel_within(y_detr_s)
    detr = detr_df.to_numpy(dtype=float)
    y_detr = y_detr_s.to_numpy(dtype=float)

    rs = traced(
        eng, st, task_id, "stat.pearson",
        f"{scope} vs KPI ({period_label})",
        get_tool("stat.pearson").run,
        [pd.Series(detr[:, i]) for i in range(len(cols))], pd.Series(y_detr),
        summarize=lambda vals: f"|r| up to {max(abs(v) for v in vals):.2f} · "
                               f"{sum(1 for v in vals if abs(v) >= 0.3)} at or above 0.3"
                               if vals else "no indicators",
    )
    r_by_col = dict(zip(cols, rs))

    # VIF is measured against a realistic model width, not the whole candidate
    # universe — see `_design_vifs`. Needs `rs`, hence the order.
    k_design = min(SCREEN_DESIGN_COLS, n)
    vifs, _base = traced(
        eng, st, task_id, "stat.vif",
        f"{scope}, each against a {k_design}-driver design × {period_label}",
        _design_vifs, detr, list(rs),
        summarize=lambda out: (
            f"max VIF {float(np.nanmax(out[0])):.1f} · "
            f"{int(np.nansum(np.asarray(out[0]) >= 5))} at or above 5"
            if len(out[0]) else "no indicators"),
    )
    vif_by_col = dict(zip(cols, vifs))

    all_rows: list[StatScoreRow] = []
    for m in metas:
        col = m["col"]
        cv = cv_by_col[col]
        corr = r_by_col[col]
        vif = float(vif_by_col.get(col, 1.0))
        months = int(m.get("months", 0))
        sc = score_statistical(cv, corr, vif)
        if months < MIN_SCORED_MONTHS:
            # Too little history for CV / Pearson / VIF to say anything. It is
            # scored and shown — with the reason — rather than quietly omitted,
            # so the funnel count still matches the indicator count.
            all_rows.append(StatScoreRow(
                id=f"s-{col}", object="", l1=m["l1"], l2=m["l2"], l3=m["l3"],
                l4=m["l4"], indicator=m["indicator"],
                treeRowId=link.row_for(m["l4"], m["indicator"]), cv=round(cv, 4),
                pearson=round(corr, 4), vif=round(vif, 3), cvScore=sc.cv_score,
                pearsonScore=sc.pearson_score, vifScore=sc.vif_score, total=0.0,
                autoVerdict=_SHORT_COVERAGE_VERDICT,
                disposition=_DISPOSITION_DEFAULT[_SHORT_COVERAGE_VERDICT],
                rationale=(f"Only {months} observed month(s) — below the "
                           f"{MIN_SCORED_MONTHS}-month minimum for statistical screening."),
            ))
            continue
        all_rows.append(StatScoreRow(
            id=f"s-{col}", object="", l1=m["l1"], l2=m["l2"], l3=m["l3"], l4=m["l4"],
            indicator=m["indicator"], treeRowId=link.row_for(m["l4"], m["indicator"]),
            cv=round(cv, 4), pearson=round(corr, 4),
            vif=round(vif, 3), cvScore=sc.cv_score, pearsonScore=sc.pearson_score,
            vifScore=sc.vif_score, total=sc.total, autoVerdict=sc.verdict,
            disposition=_DISPOSITION_DEFAULT.get(sc.verdict, "review"),
        ))
    # Worst first so the reviewer sees the risky indicators at the top.
    all_rows.sort(key=lambda r: (r.total, r.indicator))
    return StatScorecard(rows=all_rows)


def pearson(x: pd.Series, y: pd.Series) -> float:
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


_pearson = pearson  # legacy internal alias


def accepted_stat_labels(card: StatScorecard) -> list[str]:
    """Indicators the human kept (disposition != drop) — the 2.4 → 2.5 hand-off.

    The dedup by label is belt-and-braces: rows are one per indicator again since
    scoring moved to the panel, but a legacy scorecard on saved state can still
    carry the per-channel rows this used to produce.
    """
    seen: set[str] = set()
    out: list[str] = []
    for r in card.rows:
        if r.disposition == "drop":
            continue
        label = f"{r.l4 or r.l3} · {r.indicator}".strip(" ·")
        if label in seen:
            continue
        seen.add(label)
        out.append(label)
    return out


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
