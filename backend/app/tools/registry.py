"""The tool catalog: 8 registered analysis tools wrapping the real implementations.

Each `run` is an identity wrapper over the function named in `detail.source` — the
tool layer adds visibility, never arithmetic. Granularity is one call per tool
per task run (batched over series/columns), not one per series, so a 2.2 run
records four invocations rather than several thousand.

Every tool also carries its own documentation — scenario, method, decision bands
and thresholds — kept next to the wrapper so the Tools page can never drift from
what actually runs. The source code itself is not duplicated here: `detail()`
reads it off the live function with `inspect.getsource`.
"""
from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.domain.models import ToolApiCall, ToolDetail, ToolSource, ToolSpec

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Tool:
    detail: ToolDetail
    run: Callable[..., Any]
    module: str
    symbol: str

    @property
    def id(self) -> str:
        return self.detail.id

    @property
    def spec(self) -> ToolSpec:
        """The light catalog entry for the list view."""
        return ToolSpec(**{k: getattr(self.detail, k) for k in ToolSpec.model_fields})


# ── wrappers ────────────────────────────────────────────────────────────────


def _quality_batch(fn_name: str) -> Callable[..., list[list]]:
    """Batch one `quality_scoring._*_subs` over a list of series evidences."""

    def run(evidences: list, fields: list | None = None) -> list[list]:
        from app.agents import quality_scoring

        fn = getattr(quality_scoring, fn_name)
        if fields is None:
            return [fn(ev) for ev in evidences]
        return [fn(ev, fld) for ev, fld in zip(evidences, fields)]

    return run


def _run_cv(columns: list) -> list[float]:
    from app.agents.data_rules import reference_cv

    return [reference_cv(x) for x in columns]


def _run_pearson(xs: list, y) -> list[float]:
    from app.agents.stat_scoring import pearson

    return [pearson(x, y) for x in xs]


def _run_vif(matrix: "np.ndarray") -> "np.ndarray":
    from app.agents.data_rules import vif_all

    return vif_all(matrix)


def _run_ols(df, obj: str, **kwargs):
    from app.mmm import run_mmm

    return run_mmm(df, obj, **kwargs)


# ── shared API surface ──────────────────────────────────────────────────────


def _api(task_ids: list[str]) -> list[ToolApiCall]:
    """Tools are not individually addressable: they are called by the step that
    owns them. What IS addressable is the catalog and the resulting trace."""
    step = task_ids[0]
    return [
        ToolApiCall(method="GET", path="/api/tools",
                    note="The catalog — every registered tool.",
                    example="curl localhost:8000/api/tools"),
        ToolApiCall(method="GET", path="/api/tools/{toolId}",
                    note="This page's data, including the live source code.",
                    example="curl localhost:8000/api/tools/{id}"),
        ToolApiCall(method="POST", path="/api/projects/{projectId}/run",
                    note=f"Runs the workflow; step {step} calls this tool as it executes.",
                    example="curl -XPOST localhost:8000/api/projects/danone-mizone/run "
                            "-H 'content-type: application/json' -d '{\"autopilot\":true}'"),
        ToolApiCall(method="GET", path="/api/projects/{projectId}/tool-invocations",
                    note="The recorded calls — filter by step or by tool.",
                    example="curl 'localhost:8000/api/projects/danone-mizone/"
                            "tool-invocations?toolId={id}'"),
    ]


@dataclass(frozen=True)
class _Entry:
    detail: ToolDetail
    run: Callable[..., Any]
    module: str
    symbol: str


def _entry(detail: ToolDetail, run: Callable[..., Any], module: str, symbol: str) -> _Entry:
    detail.api = [
        ToolApiCall(method=c.method, path=c.path, note=c.note,
                    example=c.example.replace("{id}", detail.id))
        for c in _api(detail.used_by)
    ]
    return _Entry(detail=detail, run=run, module=module, symbol=symbol)


_ENTRIES: list[_Entry] = [
    _entry(ToolDetail(
        id="quality.consistency", name="Consistency Check", category="quality",
        description="Scores time-grid uniformity, caliber (source-change × YoY swing) and "
                    "continuity for every metric series on the 0 / 0.5 / 1 band.",
        inputSummary="Series evidence (time grid, source changes, YoY, coverage) per metric",
        outputSummary="4 subcheck scores per series → the consistency dimension score",
        wraps="agents.quality_scoring._consistency_subs", usedBy=["2.2"],
        scenario=(
            "Runs inside step 2.2 Data Quality Score, once per run, batched over every "
            "factor × metric series in the project's long table. Consistency is the first "
            "of the four 2.11 validation dimensions; a 0 here zeroes the product Total and "
            "makes the indicator unusable, which the human then rules on at gate 2.2d."),
        method=(
            "Four subchecks, each scored 0 / 0.5 / 1 against evidence computed from the real "
            "series (pandas, never the LLM). The dimension score is the WEAKEST blocking "
            "subcheck — advisory subchecks are surfaced but cannot drag the score down."),
        logic=[
            "Dimension consistency — advisory: a single tidy series cannot prove cross-source "
            "unit/definition agreement, so it defaults to 1 and is flagged for human confirmation.",
            "Time consistency — 1 when the series sits on a uniform monthly grid; 0.5 when more "
            "than 10% of rows are off that grid; 0 when the series is coarser than monthly.",
            "Caliber consistency — 1 when one data source runs throughout; 0.5 when the source "
            "changed with a YoY swing at or below 30%; 0 when it changed with a swing above 30%.",
            "Continuity — advisory: months present ÷ months spanned. ≥95% reads as continuous, "
            "below that flags gaps to check against flighting rather than auto-rejecting.",
            "Source change is detected by comparing the source SET in the early half of the "
            "timeline against the late half — a stable multi-source mix is not a caliber change.",
        ],
        params=[
            ["_TIME_MIX_TOL", "0.10", "Share of rows allowed off the dominant monthly grid"],
            ["_YOY_CALIBER", "0.30", "YoY swing above which a source change scores 0"],
            ["_CONTINUITY_OK", "0.95", "Present/spanned month ratio that reads as continuous"],
            ["_CONTINUITY_LOW", "0.80", "Below this, gaps are called out explicitly"],
        ],
    ), _quality_batch("_consistency_subs"), "app.agents.quality_scoring", "_consistency_subs"),

    _entry(ToolDetail(
        id="quality.accuracy", name="Accuracy Check", category="quality",
        description="Scores numeric validity (non-finite values and illegal negatives) and "
                    "flags the business reconciliation that needs an external reference.",
        inputSummary="Series evidence (error ratio, metric type) per metric",
        outputSummary="2 subcheck scores per series → the accuracy dimension score",
        wraps="agents.quality_scoring._accuracy_subs", usedBy=["2.2"],
        scenario=(
            "Runs inside step 2.2 alongside the other three dimensions. It answers one "
            "question the model cannot recover from: are the numbers themselves valid? A "
            "series with more than 10% invalid values scores 0 and is excluded from modeling "
            "unless the human overrides at 2.2d."),
        method=(
            "error_ratio = (non-finite values + illegal negatives) ÷ all values, computed per "
            "series. Negatives only count as errors for metrics that cannot legitimately be "
            "negative (spend and the KPI); for temperature, growth % or index drivers a "
            "negative is valid data, so it is not penalised."),
        logic=[
            "Numeric accuracy — 1 when the error ratio is under 5%; 0.5 between 5% and 10%; "
            "0 above 10%.",
            "Business accuracy — advisory: reconciling against finance/source systems needs an "
            "external reference the platform does not hold, so it defaults to 1 and is stated "
            "as unverified rather than silently passed.",
            "Natural variance is never an error. Spikes are left to the AI review and to step "
            "2.3a anomaly handling, not scored here.",
        ],
        params=[
            ["_ERR_HIGH", "0.10", "Error ratio above which numeric accuracy scores 0"],
            ["_ERR_MID", "0.05", "Error ratio from here to _ERR_HIGH scores 0.5"],
            ["_NONNEG_TYPES", "{spending, Y}", "Metric types where a negative counts as an error"],
        ],
    ), _quality_batch("_accuracy_subs"), "app.agents.quality_scoring", "_accuracy_subs"),

    _entry(ToolDetail(
        id="quality.completeness", name="Completeness Check", category="quality",
        description="Scores field completeness (spend paired with a performance metric) and "
                    "history coverage (2yr+ → 1, 1–2yr → 0.5, under 1yr → 0).",
        inputSummary="Series evidence + the parent factor's spend/performance context",
        outputSummary="2 subcheck scores per series → the completeness dimension score",
        wraps="agents.quality_scoring._completeness_subs", usedBy=["2.2"],
        scenario=(
            "Runs inside step 2.2. It is the one quality tool that reads CROSS-series context: "
            "whether the parent L4 factor pairs its spend with at least one performance metric. "
            "It also enforces the modeling history minimum — under a year of coverage cannot "
            "identify seasonality, so it scores 0."),
        method=(
            "Coverage is measured by SPAN (last month − first month + 1), not by the count of "
            "months present, so a flighted or low-frequency series is not punished twice for "
            "its off-months — continuity already reports those."),
        logic=[
            "Field completeness — 1 for a response/KPI series; 0.5 when the factor has spend but "
            "no paired performance metric; 1 otherwise.",
            "Data coverage — 1 at 24 months or more; 0.5 from 12 to 23 months; 0 below 12.",
            "Both subchecks are blocking: either can drag the completeness dimension down.",
        ],
        params=[
            ["_COVER_FULL", "24", "Months of span scoring 1 (2 years or more)"],
            ["_COVER_MIN", "12", "Months of span scoring 0.5 (1–2 years); below this scores 0"],
        ],
    ), _quality_batch("_completeness_subs"), "app.agents.quality_scoring", "_completeness_subs"),

    _entry(ToolDetail(
        id="quality.granularity", name="Granularity Check", category="quality",
        description="Scores time granularity (monthly or finer is the modeling minimum), "
                    "model granularity (region × channel detail) and L5–L8 drilldown depth.",
        inputSummary="Series evidence (time grid, regions, channels, deepdive dims)",
        outputSummary="3 subcheck scores per series → the granularity dimension score",
        wraps="agents.quality_scoring._granularity_subs", usedBy=["2.2"],
        scenario=(
            "Runs inside step 2.2. Only ONE of its three subchecks blocks: time granularity. "
            "The other two describe how much detail the series carries for deepdive work, "
            "which is useful signal but must not disqualify a national or single-channel "
            "series that is still perfectly modelable at the object level."),
        method=(
            "Granularity is read off the evidence the same pass computed: the dominant time "
            "grid, the count of distinct province groups and channels, and how many of the "
            "L5–L8 deepdive columns carry values."),
        logic=[
            "Time granularity (blocking) — 1 when the series is monthly or finer; 0 otherwise.",
            "Model granularity (advisory) — 1 when region and/or channel detail is present; "
            "0.5 for a national single-channel series, with a note to check it meets the L4 "
            "model scope.",
            "Drilldown granularity (advisory) — 1 above 2 deepdive dimensions; 0.5 for 1–2; "
            "0 when none are populated.",
        ],
        params=[
            ["monthly", "monthly_ratio ≥ 0.5", "The dominant time grid must be monthly or finer"],
            ["drilldown_dims", "L5–L8", "Deepdive columns counted toward drilldown depth"],
        ],
    ), _quality_batch("_granularity_subs"), "app.agents.quality_scoring", "_granularity_subs"),

    _entry(ToolDetail(
        id="stat.cv", name="CV (Volatility)", category="statistical",
        description="Coefficient of variation per the 2.33 rule: min-max scale the series to "
                    "[0,1], then variance / mean. A flat indicator cannot explain movement.",
        inputSummary="One monthly value column per candidate indicator",
        outputSummary="CV per indicator → the 0 / 0.5 / 1 volatility band",
        wraps="agents.data_rules.reference_cv", usedBy=["2.4"],
        scenario=(
            "Runs inside step 2.4 Statistical Score, once per run, over every indicator still "
            "in play (indicators already rejected at 2.1 mapping, 2.2 quality or 2.3 sign-off "
            "are not re-scored). CV is the first of the three 2.33 screening tests; its band "
            "adds into the Total that produces the Good / Acceptable / Unconsiderable verdict."),
        method=(
            "This is the workbook's explicit definition — 波动系数CV = 方差/均值 with the data "
            "first scaled to 0–1 — NOT the textbook CV = std/mean. Min-max scaling makes the "
            "measure unit-free so spend in RMB and GRPs are comparable. Empty, constant or "
            "degenerate series return 0.0. Runs on the indicator's raw monthly levels — unlike "
            "Pearson and VIF, which run on year-over-year differenced series."),
        logic=[
            "Drop NaNs, then min-max scale the series to [0,1]. A constant series (max ≤ min) "
            "returns 0 — no volatility to explain anything with.",
            "CV = variance(scaled) ÷ mean(scaled); a non-positive mean returns 0.",
            "Band: CV ≤ 0.05 → 0 · CV < 0.1 → 0.5 · CV ≥ 0.1 → 1.",
        ],
        params=[
            ["band 0", "CV ≤ 0.05", "Effectively flat — cannot explain KPI movement"],
            ["band 0.5", "0.05 < CV < 0.1", "Low volatility"],
            ["band 1", "CV ≥ 0.1", "Adequate volatility"],
        ],
    ), _run_cv, "app.agents.data_rules", "reference_cv"),

    _entry(ToolDetail(
        id="stat.pearson", name="Pearson Correlation", category="statistical",
        description="Signed Pearson r between each indicator and the KPI (Y) on the shared "
                    "month index — the direction and strength of its relationship to sales.",
        inputSummary="Each indicator's monthly series + the aligned monthly KPI series",
        outputSummary="Signed r per indicator → the 0 / 0.5 / 1 correlation band",
        wraps="agents.stat_scoring.pearson", usedBy=["2.4"],
        scenario=(
            "Runs inside step 2.4 next to CV and VIF. The KPI series is the global monthly sum "
            "of the Y metric; each indicator is reindexed onto that month axis before the "
            "correlation is taken. The SIGN is kept, not just the magnitude — a negative "
            "correlation on a media driver is exactly the kind of thing 2.4d must see. It is "
            "also reused downstream: the 2.5x proposal will not tick an X with |r| below 0.1."),
        method=(
            "Standard Pearson r over the months where BOTH series are present. Fewer than 3 "
            "overlapping points, or a zero-variance side, returns 0.0 rather than a spurious "
            "correlation. Runs on year-over-year differenced series, not raw levels — on raw "
            "levels every indicator correlates with the KPI, because they all ride the same "
            "seasonal trend."),
        logic=[
            "Align indicator and KPI on the shared month index; mask out months where either "
            "side is missing.",
            "Fewer than 3 usable months → 0.0. Zero standard deviation on either side → 0.0.",
            "r = corrcoef(x, y); NaN → 0.0.",
            "Band on |r|: < 0.1 → 0 · < 0.3 → 0.5 · ≥ 0.3 → 1.",
        ],
        params=[
            ["band 0", "|r| < 0.1", "No usable relationship with the KPI"],
            ["band 0.5", "0.1 ≤ |r| < 0.3", "Weak relationship"],
            ["band 1", "|r| ≥ 0.3", "Moderate or strong relationship"],
            ["MIN_ABS_PEARSON", "0.1", "Below this the 2.5x proposal leaves the X unticked"],
        ],
    ), _run_pearson, "app.agents.stat_scoring", "pearson"),

    _entry(ToolDetail(
        id="stat.vif", name="VIF (Collinearity)", category="statistical",
        description="Variance inflation factor per indicator, computed once across the whole "
                    "candidate set — collinear indicators destabilise the regression.",
        inputSummary="The (months × indicators) matrix of all candidates still in play, "
                    "year-over-year detrended",
        outputSummary="VIF per indicator → the 0 / 0.5 / 1 collinearity band",
        wraps="agents.data_rules.vif_all", usedBy=["2.4"],
        scenario=(
            "Runs inside step 2.4 ONCE across the whole candidate set — this is why rejected "
            "indicators must be filtered out before the call: a dead indicator's collinearity "
            "would inflate the VIF of the ones still in play. Note the band direction: VIF = 1 "
            "(no collinearity) is the GOOD end and scores 1, while VIF ≥ 5 scores 0 — and "
            "because the 2.4 Total is the product of the three bands, that zero drops the "
            "indicator no matter how well it scored on CV and Pearson."),
        method=(
            "Two regimes, both returning one VIF per column. Identified (n > p+1): the exact "
            "VIF_i = [inv(R)]_ii from the column correlation matrix R, equivalent to 1/(1−R²) "
            "of regressing column i on the rest. Under-determined (p ≥ n), the normal regime "
            "when screening every FactorTree indicator: the pairwise-max proxy "
            "VIF_i = 1/(1 − max_{j≠i} r_ij²) — defined for any p and readable as 'how well the "
            "single most collinear peer explains this indicator'. Like Pearson, runs on "
            "year-over-year differenced series, not raw levels."),
        logic=[
            "Fewer than 2 columns → all VIFs are 1.0 (nothing to be collinear with).",
            "Build the column correlation matrix; constant columns are treated as uncorrelated.",
            "n > p + 1 → exact VIF from the inverted correlation matrix (pseudo-inverse on a "
            "singular matrix).",
            "p ≥ n → pairwise-max proxy on the squared correlations.",
            "Floor at 1.0, cap at VIF_MAX. Band: VIF ≥ 5 → 0 · 1 < VIF < 5 → 0.5 · VIF ≤ 1 → 1.",
        ],
        params=[
            ["VIF_MAX", "1000.0", "Display/scoring cap"],
            ["band 0", "VIF ≥ 5", "Clear collinearity — zeroes the 2.4 Total"],
            ["band 0.5", "1 < VIF < 5", "Mild collinearity, generally acceptable"],
            ["band 1", "VIF ≤ 1", "No linear relationship with the other indicators"],
        ],
    ), _run_vif, "app.agents.data_rules", "vif_all"),

    _entry(ToolDetail(
        id="model.ols", name="OLS MMM Fit", category="model",
        description="Fits the marketing-mix regression for one model object: adstock + Hill "
                    "saturation on the drivers, then OLS against the chosen response.",
        inputSummary="Long table + model object, Y metric, selected X, transform/control params",
        outputSummary="R², adj. R², MAPE, Durbin-Watson, baseline %, per-driver contribution/ROI",
        wraps="mmm.engine.run_mmm", usedBy=["2.5r"],
        scenario=(
            "Called once PER MODEL OBJECT — so a five-object project records five invocations "
            "per run. Step 2.5 proposes the setup (Y / X / parameters) and 2.5r fits it once "
            "the human has confirmed each part at 2.5y / 2.5x / 2.5p. The same resolved "
            "selection drives 2.6 master data and S4 training, so what this tool fits is "
            "exactly what the model is trained on — never a separately re-derived set."),
        method=(
            "Each driver is transformed with geometric adstock (carry-over) then a Hill "
            "saturation curve (diminishing returns), optionally joined by trend and seasonality "
            "controls, and regressed on the response with ordinary least squares. Every number "
            "on the 2.5 tree — coefficient, t, p, contribution, ROI — comes from this fit; the "
            "narrative agents are explicitly told the computed results are authoritative."),
        logic=[
            "Build the model frame for the object: pivot the long table to a month × driver "
            "wide table, pick the response, and cap the drivers at MAX_DRIVERS (most "
            "Y-correlated) so the regression stays identified with p < n.",
            "Apply adstock, then Hill saturation, to each driver.",
            "Add the requested controls (trend, seasonality) as columns.",
            "Fit OLS; derive t and p per coefficient, decomposed contribution, and ROI where "
            "the response is revenue-like.",
            "Red-flag the result on low df, wrong-sign coefficients or an implausible baseline.",
            "|t| ≥ 2.0 marks a coefficient significant (≈5% two-sided at moderate dof).",
        ],
        params=[
            ["adstock", "0.5", "Default geometric carry-over rate"],
            ["hill_half", "1.0", "Default Hill half-saturation point"],
            ["MAX_DRIVERS", "12", "Cap on drivers per fit, keeping the OLS identified"],
            ["SIGNIFICANT_T", "2.0", "|t| at or above this is reported as significant"],
        ],
    ), _run_ols, "app.mmm.engine", "run_mmm"),
]

TOOLS: dict[str, Tool] = {
    e.detail.id: Tool(detail=e.detail, run=e.run, module=e.module, symbol=e.symbol)
    for e in _ENTRIES
}


def list_specs() -> list[ToolSpec]:
    """The light catalog, in registration order."""
    return [t.spec for t in TOOLS.values()]


def get(tool_id: str) -> Tool:
    tool = TOOLS.get(tool_id)
    if tool is None:
        raise KeyError(f"unknown tool {tool_id}")
    return tool


def detail(tool_id: str) -> ToolDetail:
    """The full page for one tool, with the implementation's real source attached."""
    tool = get(tool_id)
    out = tool.detail.model_copy(deep=True)
    out.source = _read_source(tool.module, tool.symbol)
    return out


def _read_source(module: str, symbol: str) -> ToolSource:
    """Read the live implementation off disk — documentation that cannot drift."""
    src = ToolSource(module=module, path=module.replace(".", "/") + ".py", symbol=symbol)
    try:
        fn = getattr(importlib.import_module(module), symbol)
        code, line = inspect.getsourcelines(fn)
        file = Path(inspect.getsourcefile(fn) or "").resolve()
        src.code = "".join(code)
        src.line = line
        try:
            src.path = f"backend/{file.relative_to(_BACKEND_ROOT)}"
        except ValueError:
            src.path = str(file)
    except Exception as e:  # noqa: BLE001 — a missing symbol must not 500 the page
        src.code = f"# source unavailable: {e}"
    return src
