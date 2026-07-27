"""S2 · Data Intake & Validation handlers — six artifacts, each a filter layer:
Data Processing (assets + factor-tree mapping) → Data Quality Score → Business
Validation → Statistical Score → OLS Regression Test → Master Data. All numbers
computed from the real dataset via pandas / app.mmm — never hardcoded.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from app.agents import data_rules
from app.agents.common import agent_system
from app.agents.ledger import (
    LAYER_LABEL,
    OBJECT_ANY,
    funnel,
    indicator_ledger,
    model_selection,
    upstream_drop_pairs,
)
from app.agents.master_data import dimensions
from app.agents.ols_review import build_ols_review, build_ols_search
from app.agents.stat_scoring import (
    DETREND_PERIOD,
    MIN_DETRENDED_POINTS,
    accepted_stat_labels,
    build_stat_scorecard,
    stat_sheet,
)
from app.agents.quality_scoring import (
    DIMENSIONS,
    PASS_MIN,
    UNUSABLE_MAX,
    FieldContext,
    QualityResult,
    SeriesEvidence as QualityEvidence,
    SubScore,
    compute_series_evidence,
    roll_up_quality,
)
from app.llm.volcano import LLMError, get_llm
from app.agents.dataset_cache import model_df, model_objects
from app.domain.models import (
    AnomalyHypothesis,
    AnomalyReview,
    DiffLine,
    EvidenceRef,
    Insight,
    InsightAction,
    Proposal,
    QualityRow,
    QualityScorecard,
    QualitySubScore,
    StatScoreRow,
    TaskFinding,
)
from app.mmm import build_model_frame, run_mmm
from app.orchestrator.engine import Engine
from app.store.state import ProjectState
from app.tools import get as get_tool
from app.tools.tracing import traced

SYS = agent_system("data")


_VERDICT_EN = {"pass": "Accept", "borderline": "Human decision", "unusable": "Reject · alert"}
_DISPOSITION_EN = {"accept": "Accept", "flag": "Flag", "drop": "Drop"}
_DISPOSITION_DEFAULT = {"pass": "accept", "borderline": "flag", "unusable": "drop"}


def _ledger_row_dict(r, *, rejected: bool) -> dict:
    body = {"l1": r.l1, "l2": r.l2, "l3": r.l3, "l4": r.l4, "indicator": r.indicator,
            "verdicts": [{"layer": v.layer, "task": v.task, "label": v.label,
                          "status": v.status, "note": v.note} for v in r.verdicts]}
    if rejected:
        body["rejectedAt"] = r.rejected_at
        body["reason"] = r.reason
    return body


def _ledger_by_object(led: tuple) -> dict[str, dict]:
    """Group the indicator ledger per model object, for the Master Data (2.6)
    artifact's Tab 2 — one channel's adopted/rejected indicators at a time.

    Mirrors ``funnel``'s own per-object resolution: this object's own ledger
    rows plus whatever a still-global layer (mapping, sign-off) ruled for
    every object (``OBJECT_ANY``). Both adopted *and* rejected rows carry
    their full verdict chain (spec §3.5) — a rejected row explains why it was
    dropped, an adopted row explains why it survived every layer.
    """
    objects = sorted({r.object for r in led if r.object != OBJECT_ANY}) or [OBJECT_ANY]
    out: dict[str, dict] = {}
    for obj in objects:
        rows = [r for r in led if r.object in (obj, OBJECT_ANY)]
        seen: dict[bool, set] = {True: set(), False: set()}
        adopted: list[dict] = []
        rejected: list[dict] = []
        for r in rows:
            bucket = seen[r.adopted]
            if r.key in bucket:
                continue
            bucket.add(r.key)
            (adopted if r.adopted else rejected).append(
                _ledger_row_dict(r, rejected=not r.adopted))
        out[obj] = {"adopted": adopted, "rejected": rejected}
    return out


_QUALITY_COLUMNS = ["L1", "L2", "L3", "L4", "Indicator",
                    "Consistency", "Consistency notes", "Completeness", "Completeness notes",
                    "Granularity", "Granularity notes", "Accuracy", "Accuracy notes",
                    "Total score", "Verdict", "Disposition", "Notes"]


def _s(v: object) -> str:
    """NA-safe cell string."""
    return "" if (v is None or pd.isna(v)) else str(v)


def quality_sheet(card: QualityScorecard) -> dict:
    """Render the quality scorecard artifact body (mirrors the Excel 2.12 layout:
    per-dimension score + notes, Total = product of the four dimensions, verdict)."""
    rows = [[r.l1, r.l2, r.l3, r.l4, r.indicator,
             f"{r.consistency:g}", r.consistency_note,
             f"{r.completeness:g}", r.completeness_note,
             f"{r.granularity:g}", r.granularity_note,
             f"{r.accuracy:g}", r.accuracy_note,
             f"{r.total:g}", _VERDICT_EN.get(r.auto_verdict, r.auto_verdict),
             _DISPOSITION_EN.get(r.disposition, r.disposition), r.note]
            for r in card.rows]
    return {"sheets": [
        {"name": "Data Quality Score", "columns": _QUALITY_COLUMNS, "rows": rows},
    ]}


def accepted_metric_labels(card: QualityScorecard) -> list[str]:
    """Metric labels the human kept (disposition != drop) — the S2 blackboard.

    Rows are now per (object, indicator) — dedup by label (first occurrence
    wins) so the count reflects distinct indicators, not channel-multiplied
    rows.
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


_MAP_STATUS_EN = {"mapped": "Mapped", "ignored": "Ignored", "pending": "Pending"}


async def data_processing(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.1 — reference the FactorTree↔DataAssets mapping resolved in the Data Engine:
    every active factor row is either mapped to a published data asset or ignored.
    The artifact IS that mapping matrix; it also summarizes the referenced assets and
    the resulting modeling long table the rest of the stage filters down from."""
    from app.agents.dataset_cache import diagnose_taxonomy, resolve_dataset
    from app.dataeng.mapping import resolve_factor_map

    from app.dataeng.indicators import derive_indicators

    fmap = resolve_factor_map(st)
    published = [a for a in st.data_assets if a.status == "published"]
    asset_rows = [[a.name, f"v{max((v.version for v in a.versions), default=0)}",
                   str(sum(1 for c in st.indicator_coverage if c.asset_id == a.id)),
                   a.description or ""] for a in published]

    # The mapping matrix — one row per active factor-tree indicator.
    matrix_rows = [[
        r.l1, r.l2, r.l3, r.l4, r.indicator,
        _MAP_STATUS_EN.get(r.status, r.status),
        r.asset_name or ("—" if r.status != "ignored" else ""),
        r.metric,
        f"{r.coverage_start}–{r.coverage_end}".strip("–"),
        r.ignore_note,
    ] for r in fmap.rows]
    pending_rows = [r for r in fmap.rows if r.status == "pending"]

    # The data source is *declared*, never guessed: `resolve_dataset` is the one
    # place that decides where the modeling table came from, and it reports "none"
    # rather than silently substituting the reference table.
    res = resolve_dataset(st)
    source = {
        "published": "Data Engine published assets",
        "slot": "Uploaded data-request workbooks",
        "reference": "Danone reference dataset",
        "none": "No usable project data",
    }.get(res.source, res.source)
    df = res.df if res.usable else model_df(st)
    months = pd.to_numeric(df["month"], errors="coerce").dropna()
    axis = (f"{int(months.min())} – {int(months.max())}" if not months.empty else "—")
    dims_rows = [
        ["Source", source],
        ["Rows", f"{len(df):,}"],
        ["Metrics", str(int(df["metric"].nunique()))],
        ["Channels", str(int(df["channel_type"].nunique()))],
        ["Regions", str(int(df["province_group"].nunique()))],
        ["Months", str(int(df[["year", "month"]].dropna().drop_duplicates().shape[0]))],
        ["Time axis", axis],
    ]
    # Per-source intake: what each origin actually contributed to the long table.
    # A source that lands 12 rows when you expected 12k is the kind of thing the
    # aggregate row count hides completely.
    src_rows: list[list[str]] = []
    if "source" in df.columns:
        grp = df.groupby(df["source"].astype("string").str.strip(), dropna=True)
        for name, sub in sorted(grp, key=lambda kv: -len(kv[1])):
            if not str(name).strip():
                continue
            sm = pd.to_numeric(sub["month"], errors="coerce").dropna()
            src_rows.append([
                str(name), f"{len(sub):,}", str(int(sub["metric"].nunique())),
                f"{int(sm.min())} – {int(sm.max())}" if not sm.empty else "—",
            ])
    coverage_rows = [
        ["Factor indicators (active)", str(fmap.total)],
        ["Mapped to a data asset", str(fmap.mapped)],
        ["Ignored (no data source)", str(fmap.ignored)],
        ["Pending (unresolved)", str(fmap.pending)],
    ]
    # Modeling readiness: does this table carry the roles the OLS engine needs?
    # Checked here, at the gate, because a table with no Y (or no channel_type)
    # lets every downstream S2 task report success over an empty universe.
    diag = diagnose_taxonomy(st)
    ready_rows = [
        ["Model objects (channel_type)", ", ".join(diag.objects) or "— none —"],
        ["channel_type coverage", f"{diag.channel_type_coverage:.0%}"],
        ["Rows recognised as the response (Y)", f"{diag.y_rows:,}"],
        ["Rows recognised as drivers (X)", f"{diag.x_rows:,}"],
        ["Verdict", "Ready to model" if diag.modelable else "Not modelable"],
    ] + [["Problem", p] for p in diag.problems]
    if not res.usable:
        ready_rows.insert(0, ["Blocked", res.reason])

    body = {"sheets": [
        {"name": "FactorTree↔DataAssets", "columns":
            ["L1", "L2", "L3", "L4", "Indicator", "Status", "Asset", "Metric", "Coverage", "Note"],
         "rows": matrix_rows or [["—", "", "", "", "", "(factor tree not confirmed)", "", "", "", ""]]},
        {"name": "Mapping coverage", "columns": ["Item", "Count"], "rows": coverage_rows},
        {"name": "Referenced data assets", "columns": ["Asset", "Version", "Indicators", "Description"],
         "rows": asset_rows or [["—", "—", "0", "(no published assets)"]]},
        {"name": "Modeling long table", "columns": ["Item", "Value"], "rows": dims_rows},
        {"name": "Modeling readiness", "columns": ["Check", "Result"], "rows": ready_rows},
        {"name": "Intake by source", "columns": ["Source", "Rows", "Metrics", "Months"],
         "rows": src_rows or [["—", "0", "0", "—"]]},
    ]}
    eng.produce(st, "a-data-processing", body=body, state="confirmed", agent="data")
    eng.set_analysis(st, "data_processing", {
        "assets": len(published), "indicators": len(derive_indicators(st)),
        "total": fmap.total, "mapped": fmap.mapped, "ignored": fmap.ignored,
        "pending": fmap.pending, "source": source, "rows": len(df),
    })
    findings = [TaskFinding(
        text=f"FactorTree↔DataAssets mapping referenced: {fmap.mapped}/{fmap.total} indicators mapped, "
        f"{fmap.ignored} ignored, {fmap.pending} pending — {len(published)} published asset(s), "
        f"modeling long table {len(df):,} rows from {source}.",
        evidence=[EvidenceRef(artifactId="a-data-processing")])]
    if pending_rows:
        labels = [f"{r.l4 or r.l3} · {r.indicator}".strip(" ·") for r in pending_rows]
        findings.append(TaskFinding(
            text="Unresolved indicators (map or ignore in the Data Engine): "
            + ", ".join(labels[:5]) + (f" +{len(labels) - 5} more" if len(labels) > 5 else ""),
            tone="flag", evidence=[EvidenceRef(artifactId="a-data-processing")]))
    elif fmap.mapped == 0 and fmap.total > 0:
        findings.append(TaskFinding(
            text="All factor indicators were ignored — there is no mapped data source, "
            "so the stage has nothing of this project's own to model.",
            tone="flag", evidence=[EvidenceRef(artifactId="a-data-processing")]))
    if not res.usable:
        findings.append(TaskFinding(
            text=f"No usable project data: {res.reason}",
            tone="flag", evidence=[EvidenceRef(artifactId="a-data-processing")]))
    for problem in diag.problems:
        findings.append(TaskFinding(
            text=f"Modeling readiness: {problem}", tone="flag",
            evidence=[EvidenceRef(artifactId="a-data-processing")]))
    # Where the tree was given up on, not just how much of it. The 2.1 gate
    # cannot even open until pending is zero, so by the time this finding is
    # read the only areas still uncovered are the ones the human explicitly
    # ignored — "18 ignored" tells the reviewer nothing; "nothing under
    # 渠道/终端营销 has data" is a decision. This mirrors the d-2.1 "Ignored
    # factors stay out of the model for this run" consequence.
    gaps: dict[str, int] = {}
    for r in fmap.rows:
        if r.status == "ignored":
            key = f"{r.l1} › {r.l2}".strip(" ›")
            gaps[key] = gaps.get(key, 0) + 1
    if gaps:
        top = sorted(gaps.items(), key=lambda kv: -kv[1])[:4]
        findings.append(TaskFinding(
            text="Ignored areas of the factor tree (no data source; stays out of the model this run): "
                 + "; ".join(f"{name} ({n} indicator{'s' if n > 1 else ''})" for name, n in top),
            evidence=[EvidenceRef(artifactId="a-data-processing")]))
    eng.add_findings(st, task["id"], findings)


def _coerce_score(v: object, fallback: float) -> float:
    """Snap an LLM-returned score to the {0, 0.5, 1} band; fall back if unusable."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return fallback
    return min((0.0, 0.5, 1.0), key=lambda b: abs(b - f))


def _field_context(df: pd.DataFrame) -> dict[tuple, FieldContext]:
    """Per-parent-L4 spend/performance presence — grounds field completeness.

    A factor is field-complete when a spend metric is paired with at least one
    non-spend performance metric (the 2.11 字段完整性 rule)."""
    out: dict[tuple, FieldContext] = {}
    for key, grp in df.groupby(["l1", "l2", "l3", "l4"], dropna=False):
        types = set(grp["metric_type"].dropna().astype(str)) if "metric_type" in grp else set()
        out[key] = FieldContext(
            has_spend="spending" in types,
            has_performance=bool(types - {"spending"}),
        )
    return out


_QUALITY_TOOLS = ("quality.consistency", "quality.accuracy",
                  "quality.completeness", "quality.granularity")


def _run_quality_tools(eng: Engine, st: ProjectState, task_id: str,
                       evidences: list[QualityEvidence],
                       contexts: list[FieldContext],
                       obj: str = "") -> list[list[list[SubScore]]]:
    """Call the four quality tools, one explicit traced invocation each.

    Returns the subcheck lists per dimension in `_QUALITY_TOOLS` order — the same
    order `score_quality` concatenates them in, so the rollup is unchanged.
    ``obj`` (a model object / channel_type) only labels the trace when given —
    it never changes what is computed.
    """
    label = f"{obj}: " if obj else ""
    out: list[list[list[SubScore]]] = []
    for tool_id in _QUALITY_TOOLS:
        # Completeness is the one dimension that also reads the parent factor's
        # spend/performance context.
        args = (evidences, contexts) if tool_id == "quality.completeness" else (evidences,)
        out.append(traced(
            eng, st, task_id, tool_id, f"{label}{len(evidences)} metric series",
            get_tool(tool_id).run, *args,
            summarize=lambda subs: _quality_tool_summary(subs),
        ))
    return out


def _quality_tool_summary(per_series: list[list[SubScore]]) -> str:
    """'avg 0.83 · 4 series scored 0' — what the dimension found across the batch."""
    scores = [s.score for subs in per_series for s in subs if s.blocking]
    if not scores:
        return "no blocking subchecks"
    zeros = sum(1 for subs in per_series
                if any(s.score == 0.0 for s in subs if s.blocking))
    return f"avg {sum(scores) / len(scores):.2f} across {len(scores)} subchecks · {zeros} series scored 0"


async def _ai_review_dimensions(rows: list[dict]) -> dict[str, dict]:
    """Have the AI review the four dimension scores + write an English note per
    dimension, grounded in the deterministic subcheck breakdown and the rubric.
    Returns {} if the LLM is unavailable (caller keeps the deterministic scores)."""
    if not rows:
        return {}
    try:
        llm = get_llm()
    except LLMError:
        return {}
    rubric = data_rules.validation_rule_rows()
    rubric_txt = "\n".join(f"{r[0]} | {r[1]} | 0={r[2]} | 0.5={r[3]} | 1={r[4]}" for r in rubric[:40])
    out: dict[str, dict] = {}
    for start in range(0, len(rows), 30):  # chunk to keep JSON parseable
        batch = rows[start:start + 30]
        user = (
            "You are reviewing data-quality scores. Each row already has a deterministic score "
            "per dimension (consistency, accuracy, completeness, granularity) plus the subcheck "
            "breakdown that produced it. Keeping the rubric in mind, CONFIRM or ADJUST each of the "
            "four dimension scores (strictly 0, 0.5 or 1) — only override the deterministic score "
            "when the subcheck evidence clearly warrants it — and write a concise English note "
            "(≤90 chars) per dimension explaining the score from the evidence. Return a JSON array "
            'of {"id","consistency","accuracy","completeness","granularity","notes":'
            '{"consistency","accuracy","completeness","granularity"}}.\n\n'
            f"RUBRIC (0/0.5/1 bands):\n{rubric_txt}\n\nROWS:\n"
            + json.dumps(batch, ensure_ascii=False)
        )
        try:
            reply = await llm.json(system=SYS, user=user)
        except LLMError:
            continue
        items = reply if isinstance(reply, list) else (reply.get("rows") or reply.get("scores") or [])
        for it in items if isinstance(items, list) else []:
            if isinstance(it, dict) and it.get("id"):
                out[str(it["id"])] = it
    return out


def _verdict(total: float) -> str:
    """Excel 2.12 acceptance rule on the product Total."""
    if total <= UNUSABLE_MAX:
        return "unusable"
    return "borderline" if total < PASS_MIN else "pass"


async def score_data(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.2 — score every factor×metric on the four 2.11 validation dimensions,
    per model object.

    A deterministic subcheck scorer (`quality_scoring`) computes the 10 subchecks
    and a baseline dimension score straight from the real long table; the AI then
    reviews the four dimension scores on that grounding. Total = product of the
    four dimensions (Excel 2.12). The human reviews the verdicts in 2.2d.

    Each model object (channel_type) is scored on its own data slice — an
    indicator's quality can differ by channel (e.g. sparser reporting in one
    channel than another), so it is screened once per channel, not once globally.
    """
    from app.agents.ledger import _matches, _norm_pair, drops_before

    full = model_df(st)
    # 1) deterministic subcheck evidence, then the four registered quality tools —
    #    one explicit call each, batched over every series (see app/tools) —
    #    computed per object on that channel's own slice.
    base: list[tuple[str, str, dict, QualityResult]] = []  # (rid, obj, meta, res)
    for obj in model_objects(st):
        df = full[full["channel_type"].astype("string").str.strip() == obj]
        fields = _field_context(df)
        evidences: list[QualityEvidence] = []
        contexts: list[FieldContext] = []
        metas: list[dict] = []
        grouped = df.groupby(["l1", "l2", "l3", "l4", "metric"], dropna=False)
        for i, ((l1, l2, l3, l4, metric), grp) in enumerate(grouped):
            if not str(metric).strip() or str(metric) == "<NA>":
                continue
            evidences.append(compute_series_evidence(grp))
            contexts.append(fields.get((l1, l2, l3, l4), FieldContext(False, True)))
            metas.append({"id": f"{obj}|q-{i}", "l1": _s(l1), "l2": _s(l2), "l3": _s(l3),
                          "l4": _s(l4), "indicator": _s(metric)})
        if not metas:
            continue

        inherited = drops_before(st, "quality", obj)
        if inherited:
            keep = [not _matches(_norm_pair(m["l4"], m["indicator"]), inherited) for m in metas]
            metas = [m for m, k in zip(metas, keep) if k]
            evidences = [e for e, k in zip(evidences, keep) if k]
            contexts = [c for c, k in zip(contexts, keep) if k]
            if not metas:
                continue

        subs_by_dim = _run_quality_tools(eng, st, task["id"], evidences, contexts, obj)
        base.extend(
            (meta["id"], obj, meta, roll_up_quality([s for dim in subs_by_dim for s in dim[idx]]))
            for idx, meta in enumerate(metas)
        )
    # 2) AI reviews the dimension scores over the subcheck breakdown (falls back to baseline).
    review_rows = [{**meta,
                    "baseline": {d: getattr(res, d) for d in DIMENSIONS},
                    "subchecks": [{"dimension": s.dimension, "label": s.label,
                                   "score": s.score, "evidence": s.note} for s in res.subs]}
                   for (_rid, _obj, meta, res) in base]
    ai = await _ai_review_dimensions(review_rows)
    used_ai = bool(ai)
    # 3) merge → scorecard rows with the product-Total verdict.
    qrows: list[QualityRow] = []
    borderline: list[str] = []
    unusable: list[str] = []
    for (rid, obj, meta, res) in base:
        a = ai.get(rid, {})
        notes = a.get("notes", {}) if isinstance(a.get("notes"), dict) else {}
        dims = {d: _coerce_score(a.get(d), getattr(res, d)) for d in DIMENSIONS}
        total = round(dims["consistency"] * dims["accuracy"]
                      * dims["completeness"] * dims["granularity"], 4)
        verdict = _verdict(total)
        label = f"{obj} · {meta['l4'] or meta['l3'] or meta['l1']} · {meta['indicator']}".strip(" ·")
        subs = [QualitySubScore(key=s.key, dimension=s.dimension, label=s.label,
                                score=s.score, note=s.note, computed=s.computed, blocking=s.blocking)
                for s in res.subs]
        qrows.append(QualityRow(
            id=rid, object=obj, l1=meta["l1"], l2=meta["l2"], l3=meta["l3"], l4=meta["l4"],
            indicator=meta["indicator"],
            consistency=dims["consistency"], accuracy=dims["accuracy"],
            completeness=dims["completeness"], granularity=dims["granularity"],
            consistencyNote=str(notes.get("consistency") or res.dimension_note("consistency")),
            accuracyNote=str(notes.get("accuracy") or res.dimension_note("accuracy")),
            completenessNote=str(notes.get("completeness") or res.dimension_note("completeness")),
            granularityNote=str(notes.get("granularity") or res.dimension_note("granularity")),
            subScores=subs, total=total, autoVerdict=verdict, disposition=_DISPOSITION_DEFAULT[verdict],
        ))
        if verdict == "borderline":
            borderline.append(label)
        elif verdict == "unusable":
            unusable.append(label)
    qrows.sort(key=lambda r: (r.object, r.total))
    card = QualityScorecard(rows=qrows)
    st.quality_scorecard = card
    eng.produce(st, "a-quality-scorecard", body=quality_sheet(card), state="confirmed", agent="data")
    eng.set_analysis(st, "quality", {
        "total": len(qrows), "accepted": len(accepted_metric_labels(card)),
        "borderline": borderline[:20], "unusable": unusable[:20],
        "accepted_metrics": accepted_metric_labels(card), "scored_by": "ai" if used_ai else "proxy",
    })
    findings: list[TaskFinding] = [TaskFinding(
        text=f"{'AI-reviewed' if used_ai else 'Scored'} {len(qrows)} metrics on 4 dimensions "
        f"(Total = product): {len(qrows)-len(borderline)-len(unusable)} accept (≥0.5), "
        f"{len(borderline)} borderline (<0.5), {len(unusable)} unusable (0). Human reviews in 2.2d.",
        evidence=[EvidenceRef(artifactId="a-quality-scorecard")])]
    if unusable:
        findings.append(TaskFinding(text=f"Unusable (alert): {', '.join(unusable[:3])}",
                                    tone="flag", evidence=[EvidenceRef(artifactId="a-quality-scorecard")]))
    eng.add_findings(st, task["id"], findings)
    # Feed the 2.2d human-review gate question with the real borderline / unusable metrics.
    if "d-2.2" in st.decisions:
        if borderline or unusable:
            eg = borderline[0] if borderline else unusable[0]
            q = (f"{len(borderline)} metric(s) scored borderline (Total<0.5, e.g. {eg}) and "
                 f"{len(unusable)} scored 0 (unusable). Review the verdicts: accept the passes, and "
                 "decide each borderline (re-collect / drop / accept-with-caveat).")
        else:
            q = "All metrics passed (Total ≥ 0.5) — review and accept the data-quality verdicts."
        st.decisions["d-2.2"].question = q


def _anomalies(df: pd.DataFrame) -> list[dict]:
    """Find YoY growth anomalies per channel_type for a sales-like metric."""
    out = []
    sales = df[df["metric"].astype(str).str.contains("sales|offtake|GMV|箱|volume|Volume|销",
                                                     case=False, na=False, regex=True)]
    if sales.empty:
        sales = df
    g = sales.groupby(["channel_type", "year"])["value"].sum().reset_index()
    for ctype in g["channel_type"].dropna().unique():
        sub = g[g["channel_type"] == ctype].sort_values("year")
        vals = sub["value"].to_numpy(dtype=float)
        yrs = sub["year"].to_numpy()
        for i in range(1, len(vals)):
            if vals[i - 1] > 0:
                growth = (vals[i] - vals[i - 1]) / vals[i - 1]
                if abs(growth) >= 0.4:
                    out.append({"channel": str(ctype), "year": str(yrs[i]),
                                "growth_pct": round(growth * 100, 1)})
    return sorted(out, key=lambda x: -abs(x["growth_pct"]))[:8]


def _bv_yoy_latest(by_year: dict[int, float]) -> float | None:
    ys = sorted(by_year)
    if len(ys) < 2 or not by_year.get(ys[-2]):
        return None
    return round((by_year[ys[-1]] - by_year[ys[-2]]) / by_year[ys[-2]] * 100, 1)


def _bv_interpretation(df: pd.DataFrame, l3: str, indicators: list[str]) -> str:
    """A deterministic one-line read for an L3 factor: sell-out YoY vs the factor's
    lead indicator YoY (the AI narrator may refine this afterwards)."""
    from app.dataeng import validation_query as vq
    parts: list[str] = []
    kpi_delta = _bv_yoy_latest(vq._sum_by_period(df[vq._kpi_mask(df)], "year"))
    if kpi_delta is not None:
        parts.append(f"Sell-out {kpi_delta:+}% YoY")
    if indicators:
        sub = df[vq._casefold_eq(df["l3"], l3)]
        top = indicators[0]
        top_delta = _bv_yoy_latest(vq._sum_by_period(sub[vq._casefold_eq(sub["metric"], top)], "year"))
        parts.append(f"{top} {top_delta:+}% YoY" if top_delta is not None else f"{top} tracked")
        parts.append(f"{len(indicators)} indicator(s) overlaid")
    return "; ".join(parts) or "No overlay indicators mapped for this factor yet."


def _bv_groups(st: ProjectState, df: pd.DataFrame) -> list[dict]:
    """One group per factor (L1 › L2 › L3), driven by the modeling table's own factor
    columns so every chart has overlay data. The long table's l1/l2/l3 IS the factor
    hierarchy as realized in the data; the FactorTree object only contributes each
    L3's row ids (for sign-off linkage) where its labels line up with the data."""
    from app.dataeng import validation_query as vq
    rows_by_l3: dict[str, list[str]] = {}
    ft = getattr(st, "factor_tree", None)
    if ft is not None and ft.rows:
        for r in ft.rows:
            if r.status in ("baseline", "accepted") and (r.l3 or "").strip():
                rows_by_l3.setdefault(r.l3.strip().casefold(), []).append(r.id)

    overlay = df[~vq._kpi_mask(df)]
    combo = (overlay[["l1", "l2", "l3"]].astype("string").apply(lambda s: s.str.strip())
             .dropna(subset=["l3"]).drop_duplicates())
    combo = combo[combo["l3"].str.len() > 0].sort_values(["l1", "l2", "l3"])

    groups: list[dict] = []
    for _, row in combo.iterrows():
        l3 = row["l3"] or ""
        sub = df[vq._casefold_eq(df["l3"], l3)]
        indicators = vq._default_indicators(sub)
        # The indicators this chart actually covers, in the ledger's (l4, metric)
        # key space — this is what the per-indicator sign-off is recorded against.
        sub_overlay = overlay[vq._casefold_eq(overlay["l3"], l3)]
        pairs = sorted({
            (str(a or "").strip(), str(b or "").strip())
            for a, b in zip(sub_overlay["l4"], sub_overlay["metric"])
            if str(b or "").strip()
        })
        groups.append({
            "l1": row["l1"] or "", "l2": row["l2"] or "", "l3": l3,
            "rowIds": rows_by_l3.get(l3.casefold(), []),
            "defaultIndicators": indicators,
            "interpretation": _bv_interpretation(df, l3, indicators),
            # Reflect the durable verdict, so re-running 2.3 cannot erase a
            # sign-off the client already gave (`st.signoffs` is the truth —
            # this field is a rendering of it). Derived from THIS group's own
            # indicator pairs, not a raw L3-name lookup — sign-off is recorded
            # per indicator (`ledger.signoff_key`), not per factor name.
            "signoff": _signoff_for(st, pairs),
            "pairs": [{"l4": a, "indicator": b} for a, b in pairs],
        })
    return groups


def _signoff_for(st: ProjectState, pairs: list[tuple[str, str]]) -> str:
    """The client's recorded verdict for a factor's indicator pairs.

    "yes" when every pair is signed yes, "no" when every pair is signed no,
    "" when none are recorded — or when the pairs disagree ("mixed"). The
    frontend today only understands ""/"yes"/"no"
    (`BusinessValidationView.tsx::setSignoff` toggles between those three), so
    a genuine split is reported as "" rather than a fourth value it cannot
    render; a later task that gives the UI a per-indicator affordance can
    surface "mixed" directly instead of collapsing it here.
    """
    from app.agents.ledger import signoff_key

    signoffs = getattr(st, "signoffs", None) or {}
    verdicts = {
        str(signoffs[key]).strip().lower()
        for l4, indicator in pairs
        for key in [signoff_key(l4, indicator)]
        if key in signoffs and str(signoffs[key]).strip()
    }
    if verdicts == {"yes"}:
        return "yes"
    if verdicts == {"no"}:
        return "no"
    return ""


def refresh_signoff_in_artifact(st: ProjectState) -> None:
    """Patch just the per-group ``signoff`` field on ``a-business-validation``
    in place, after a sign-off write.

    Re-running the whole 2.3 handler on every Accept/Deny click would redo
    `_bv_narrate`'s LLM call over every group, bump the artifact `version`, and
    reset `state` back to "proposed" — un-confirming the very deliverable the
    sign-off is meant to confirm. This derives each group's `signoff` exactly
    the way `_signoff_for` does (so the two can never drift) and touches
    nothing else on the artifact: not `state`, not `version`, not the charts
    or interpretation text.
    """
    art = st.artifact("a-business-validation")
    if art is None or not isinstance(art.body, dict):
        return
    groups = art.body.get("groups")
    if not isinstance(groups, list):
        return
    for g in groups:
        if not isinstance(g, dict):
            continue
        pairs = [(p.get("l4", ""), p.get("indicator", ""))
                 for p in (g.get("pairs") or []) if isinstance(p, dict)]
        g["signoff"] = _signoff_for(st, pairs)


#: How many charts are read concurrently, and how long one read may take. A
#: reasoning model runs ~60-80s on a 36-month chart with six series, so 16 factors
#: serialised is twenty minutes; they go in parallel, but bounded — each one is a
#: full LLM call. The timeout is set well above the observed per-chart time: at 90s
#: two of sixteen charts timed out on the real case and fell through to on-demand
#: generation for no good reason.
_BV_ANALYSIS_CONCURRENCY = 4
_BV_ANALYSIS_TIMEOUT_S = 180.0


async def _bv_analyse_charts(eng: Engine, st: ProjectState, task_id: str,
                             groups: list[dict]) -> None:
    """Read every factor chart up front, so 2.3 opens with its analyses already there.

    Each chart is analysed on its *default* filter state — the one the card shows
    when it first renders — and cached under the same key the on-demand endpoint
    uses, so opening the tab is a cache hit and changing a filter still offers a
    refresh. Nothing here blocks the gate: a chart whose read fails keeps no entry
    and the UI's "Generate analysis" button covers it.
    """
    import asyncio
    from datetime import datetime, timezone

    from app.agents import validation_analysis as va
    from app.dataeng import validation_query as vq

    if not groups:
        return
    sem = asyncio.Semaphore(_BV_ANALYSIS_CONCURRENCY)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store = getattr(st, "validation_chart_analyses", None)
    if store is None:
        store = {}

    async def one(g: dict) -> tuple[str, dict] | None:
        l3 = str(g.get("l3") or "")
        if not l3:
            return None
        # Normalised through the same helper the endpoint uses, so a pre-generated
        # analysis lands under exactly the key the card will ask for.
        query = va.normalize_query({
            "l3": l3, "grain": "month",
            "indicators": list(g.get("defaultIndicators") or []),
        })
        async with sem:
            try:
                res = await asyncio.to_thread(
                    vq.validation_series, st, l3=l3, grain="month",
                    indicators=query["indicators"] or None)
                analysis = await asyncio.wait_for(
                    va.analyze_chart(res, query, now=now), timeout=_BV_ANALYSIS_TIMEOUT_S)
            except Exception:  # noqa: BLE001 — one unreadable chart must not sink the rest
                return None
        return va.analysis_key(query), analysis.model_dump(by_alias=True)

    done = await asyncio.gather(*(one(g) for g in groups))
    ok = [d for d in done if d]
    for key, payload in ok:
        store[key] = payload
    st.validation_chart_analyses = store

    fallback = sum(1 for _k, p in ok if p.get("fallback"))
    failed = len(groups) - len(ok)
    msg = (f"AI read {len(ok)} of {len(groups)} factor chart(s) — naming trends, "
           f"anomalies and inflections from the plotted series.")
    if fallback:
        msg += f" {fallback} fell back to a computed readout (no language model)."
    if failed:
        msg += f" {failed} could not be read and are left for on-demand generation."
    eng.emit(st, "data", "info", msg, task_id)
    if failed:
        eng.add_findings(st, task_id, [TaskFinding(
            text=(f"{failed} factor chart(s) could not be analysed automatically — open "
                  "the chart and use Generate analysis."),
            tone="flag", evidence=[EvidenceRef(artifactId="a-business-validation")])])


async def _bv_narrate(groups: list[dict]) -> None:
    """Best-effort: refine each factor's interpretation in one grounded LLM call.
    Silently keeps the deterministic text when no LLM is configured."""
    if not groups:
        return
    try:
        llm = get_llm()
    except LLMError:
        return
    payload = [{"l3": g["l3"], "indicators": g["defaultIndicators"],
                "reading": g["interpretation"]} for g in groups]
    try:
        reply = await llm.json(system=SYS, user=(
            "For each marketing factor (L3), rewrite `reading` as a concise English business "
            "interpretation (≤20 words) grounded ONLY in the numbers/indicators given — how the "
            "factor tracks against sell-out. Return a JSON array of {\"l3\",\"interpretation\"}.\n\n"
            + json.dumps(payload, ensure_ascii=False)))
    except LLMError:
        return
    items = reply if isinstance(reply, list) else reply.get("rows", [])
    notes = {str(it["l3"]): str(it.get("interpretation", "")) for it in items
             if isinstance(it, dict) and it.get("l3")}
    for g in groups:
        if notes.get(g["l3"]):
            g["interpretation"] = notes[g["l3"]]


async def business_validation(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.3 — Business Validation: one interactive chart per FactorTree L3 (a constant
    sell-out area background overlaid with the factor's indicators; filterable by data
    source / sub-factor / indicator / time grain / model dimension) plus a yearly+YoY
    table. The artifact carries per-factor metadata + interpretation + the `specs` that
    drive the self-serve Graphic Walker explorer (`ExploreTab`); sign-off is a separate
    tab. Anomalies are localized here; ends at the client sign-off gate."""
    from app.dataeng import validation_query as vq
    from app.dataeng import validation_specs as vspecs
    df = model_df(st)
    anomalies = _anomalies(df)
    eng.set_analysis(st, "anomalies", anomalies)

    tid = task["id"]
    kpi_df = df[vq._kpi_mask(df)]
    kpi_metric = str(kpi_df["metric"].mode().iloc[0]) if not kpi_df.empty else ""
    groups = _bv_groups(st, df)
    eng.emit(st, "data", "info",
             f"Charted {len(groups)} factor(s) against {kpi_metric or 'the response'} "
             f"({df['month'].nunique() if 'month' in df.columns else 0} months).", tid)
    await _bv_narrate(groups)
    await _bv_analyse_charts(eng, st, tid, groups)
    body = {
        "kpiMetric": kpi_metric,
        "groups": groups,
        "specs": vspecs.default_specs(st),
        "anomalies": [{"channel": a["channel"], "year": a["year"],
                       "growthPct": a["growth_pct"]} for a in anomalies],
        "note": ("Explore each factor against sell-out — adjust axes, chart type, and "
                 "dimensions freely, then sign off indicators in the Sign-off tab."),
    }
    eng.produce(st, "a-business-validation", body=body, state="proposed", agent="data")
    findings = [TaskFinding(
        text=f"Anomaly: {a['channel']} {a['year']} growth {a['growth_pct']:+}% — needs a business explanation.",
        tone="flag", evidence=[EvidenceRef(artifactId="a-business-validation")]) for a in anomalies[:3]]
    eng.add_findings(st, task["id"], findings)
    if anomalies:
        a0 = anomalies[0]
        eng.add_insight(st, Insight(
            id="i-2.3-anomaly", kind="connection",
            title=f"{a0['channel']} {a0['year']} {a0['growth_pct']:+}% anomaly",
            finding=f"{a0['channel']} shows a {a0['growth_pct']:+}% YoY move in {a0['year']}; "
            "cross-check against interview notes before modeling to avoid mis-attribution.",
            evidence=[EvidenceRef(artifactId="a-business-validation"), EvidenceRef(artifactId="a-interview")],
            confidence=0.78,
            actions=[InsightAction(kind="client_question", label="Confirm event window with client")],
            afterTask="2.3"))


_HANDLING_DEFAULTS = {
    "event": ("Matches a structural business event rather than marketing — a dummy "
              "over the window keeps the spike out of the media coefficients.",
              "Needs the client to confirm the event window."),
    "cap": ("Winsorizing the window is quick and robust when the cause is unclear.",
            "May flatten genuine business growth."),
    "raw": ("Keeps the real data; the model explains the move as best it can.",
            "Marketing ROI may be overstated for the period."),
}


async def _ai_anomaly_hypotheses(rows: list[dict]) -> dict[str, dict]:
    """Have the AI hypothesize a cause per anomaly and propose a handling,
    grounded only in the computed move. Returns {} when no LLM is configured."""
    if not rows:
        return {}
    try:
        llm = get_llm()
    except LLMError:
        return {}
    try:
        reply = await llm.json(system=SYS, user=(
            "Each row is a year-on-year sales anomaly detected in a marketing-mix "
            "dataset. For each, return:\n"
            "  `hypothesis`  — one English sentence (≤25 words) on the most likely "
            "business cause, grounded ONLY in the given channel / year / move. Say it "
            "is unexplained if you cannot ground it. Do not invent events.\n"
            "  `proposed`    — one of \"event\" (a structural business event: absorb it "
            "with a dummy), \"cap\" (unclear cause: winsorize it), \"raw\" (keep it as is).\n"
            "Return a JSON array of {\"id\",\"hypothesis\",\"proposed\"}.\n\n"
            + json.dumps(rows, ensure_ascii=False)))
    except LLMError:
        return {}
    items = reply if isinstance(reply, list) else reply.get("rows", [])
    return {str(it["id"]): it for it in items if isinstance(it, dict) and it.get("id")}


async def review_anomalies(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.3a — one hypothesis card per detected anomaly, for the human to rule on.

    This replaces the old `ai-2.3` option set, which asked "how should anomalies
    be handled?" once, recorded the answer, and then never read it. Here the
    handling is per anomaly and it actually reaches the fit: an accepted `event`
    becomes a dummy control, `cap` winsorizes the response over the window, and
    `raw` rides as a caveat (see `ledger.anomaly_effects`).
    """
    anomalies = st.analysis.get("anomalies") or _anomalies(model_df(st))
    existing = {r.id: r for r in getattr(getattr(st, "anomaly_review", None), "rows", None) or []}
    payload = [{"id": f"an-{i}", "channel": a["channel"], "year": a["year"],
                "growthPct": a["growth_pct"]} for i, a in enumerate(anomalies)]
    ai = await _ai_anomaly_hypotheses(payload)

    rows: list[AnomalyHypothesis] = []
    for p in payload:
        # A card the human already ruled on is never re-proposed over.
        if p["id"] in existing and existing[p["id"]].status != "pending":
            rows.append(existing[p["id"]])
            continue
        got = ai.get(p["id"], {})
        proposed = str(got.get("proposed", "")).lower()
        if proposed not in _HANDLING_DEFAULTS:
            proposed = "event"
        rationale, tradeoff = _HANDLING_DEFAULTS[proposed]
        year = int(p["year"]) if str(p["year"]).isdigit() else 0
        rows.append(AnomalyHypothesis(
            id=p["id"], channel=p["channel"], year=str(p["year"]), growthPct=p["growthPct"],
            hypothesis=str(got.get("hypothesis") or
                           f"{p['channel']} moved {p['growthPct']:+}% year on year in "
                           f"{p['year']}; the cause is not established from the data alone."),
            proposed=proposed, rationale=rationale, tradeoff=tradeoff,
            status="pending", handling=proposed,
            # Default the window to the anomaly's own year; the human narrows it
            # once the client confirms the dates.
            start=year * 100 + 1 if year else 0, end=year * 100 + 12 if year else 0,
        ))
    st.anomaly_review = AnomalyReview(rows=rows)

    findings = [TaskFinding(
        text=f"{len(rows)} anomaly hypothesis card(s) drafted for review. Each accepted "
        "handling reaches the model: an event becomes a dummy control, capping winsorizes "
        "the response, raw carries a caveat.",
        tone="flag" if rows else "info",
        evidence=[EvidenceRef(artifactId="a-business-validation")])]
    if not rows:
        findings = [TaskFinding(
            text="No year-on-year anomalies crossed the ±40% threshold — nothing to explain.",
            evidence=[EvidenceRef(artifactId="a-business-validation")])]
    eng.add_findings(st, task["id"], findings)


def _stat_n_obs(st: ProjectState) -> int:
    """Monthly observation count on the modeling axis (VIF identifiability check)."""
    try:
        df = model_df(st)
        return int(df[["year", "month"]].dropna().drop_duplicates().shape[0])
    except Exception:  # noqa: BLE001
        return 0


async def _ai_stat_rationales(rows: list[dict]) -> dict[str, str]:
    """Have the AI argue each borderline indicator in or out, grounded only in
    its computed stats. Returns {} when no LLM is configured — the deterministic
    verdict already stands on its own, the rationale only explains it."""
    if not rows:
        return {}
    try:
        llm = get_llm()
    except LLMError:
        return {}
    try:
        reply = await llm.json(system=SYS, user=(
            "You are screening indicators for a marketing-mix model. For each row below, "
            "write `rationale`: one English sentence (≤22 words) making the case for or "
            "against letting it into the model. Ground it ONLY in the given numbers — "
            "cv (variability; near-zero = no signal), pearson (correlation with the sales "
            "KPI), vif (collinearity; >10 is severe), verdict. Do not invent numbers. "
            "Return a JSON array of {\"id\",\"rationale\"}.\n\n"
            + json.dumps(rows, ensure_ascii=False)))
    except LLMError:
        return {}
    items = reply if isinstance(reply, list) else reply.get("rows", [])
    return {str(it["id"]): str(it.get("rationale", "")) for it in items
            if isinstance(it, dict) and it.get("id")}


def _stat_fallback_rationale(r: StatScoreRow) -> str:
    """The deterministic case, used when the AI is unavailable."""
    bits = []
    if abs(r.pearson) < 0.1:
        bits.append("almost no correlation with the KPI")
    elif abs(r.pearson) >= 0.5:
        bits.append("strong correlation with the KPI")
    if r.vif >= 10:
        bits.append("severely collinear with the other indicators")
    if r.cv < 0.05:
        bits.append("barely varies over the period")
    head = {"Good": "Clears every test", "Acceptable": "Borderline",
            "unconsiderable": "Fails the screening"}.get(r.auto_verdict, "Scored")
    return f"{head} — {', '.join(bits)}." if bits else f"{head} on CV / Pearson / VIF."


async def stat_screening(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.4 — score the indicators still in play on CV / Pearson / VIF (2.33 rule).

    The score is per indicator (not per model-object column): each gets one CV,
    one Pearson vs the KPI, and one VIF computed across the set. Indicators an
    earlier layer already rejected are not scored at all (see
    ``build_stat_scorecard``). The AI then writes the case for or against each
    row, and the human rules at 2.4d — Good → include, Acceptable → review,
    Unconsiderable → drop.
    """
    card = build_stat_scorecard(st, eng=eng, task_id=task["id"])
    # The AI argues each row from its own numbers; the score itself stays computed.
    ai = await _ai_stat_rationales([
        {"id": r.id, "indicator": f"{r.l4 or r.l3} · {r.indicator}".strip(" ·"),
         "cv": r.cv, "pearson": r.pearson, "vif": r.vif, "verdict": r.auto_verdict}
        for r in card.rows])
    for r in card.rows:
        r.rationale = ai.get(r.id) or _stat_fallback_rationale(r)
    st.stat_scorecard = card
    eng.produce(st, "a-stat-tests", body=stat_sheet(card), state="confirmed", agent="data")

    def _label(r: StatScoreRow) -> str:
        return f"{r.l4 or r.l3} · {r.indicator}".strip(" ·")

    # Auto-drop proposal fires on a genuinely weak Total (Unconsiderable) — and
    # because Total is the PRODUCT of the three 0/0.5/1 bands, a single severe
    # VIF (band 0) zeroes it on its own. So a high VIF among otherwise-strong
    # indicators is not merely surfaced on the card for the human to weigh — it
    # already put the row in the drop set. Collinearity is still expected when
    # scoring the whole indicator set at once (p ≥ n), but nothing overrides
    # the product rule to protect it from that.
    drop_candidates = [_label(r) for r in card.rows if r.auto_verdict == "unconsiderable"]
    acceptable = [_label(r) for r in card.rows if r.auto_verdict == "Acceptable"]
    # VIF runs on the year-over-year DIFFERENCED frame (see stat_scoring._yoy), not
    # the raw monthly one, so the identified-vs-proxy regime (data_rules.vif_all)
    # has to be decided from that same row count — comparing the raw monthly count
    # against p understated how often the whole-set proxy actually fires.
    p = len(card.rows)
    raw_n_obs = _stat_n_obs(st)
    detrended_n = raw_n_obs - DETREND_PERIOD
    if detrended_n < MIN_DETRENDED_POINTS:  # too short to detrend — vif_all saw the raw levels
        detrended_n = raw_n_obs
    proxy_vif = 0 < detrended_n <= p + 1
    eng.set_analysis(st, "screening_drops", drop_candidates[:20])
    eng.set_analysis(st, "screening_acceptable", acceptable[:20])
    eng.set_analysis(st, "screening", {
        "total": len(card.rows),
        "good": sum(1 for r in card.rows if r.auto_verdict == "Good"),
        "acceptable": len(acceptable),
        "drop": len(drop_candidates),
        "kept": accepted_stat_labels(card),
    })
    if drop_candidates:
        eng.add_proposal(st, Proposal(
            id="p-2.4-collinear", targetArtifactId="a-ols-test",
            title="Drop collinear / low-signal indicators before modeling",
            summary="Statistical screening flagged indicators that failed a test outright "
            "(near-zero variability, no correlation, or severe collinearity — Total is "
            "their product, so any single failure zeroes it): "
            + ", ".join(drop_candidates[:5]),
            diff=[DiffLine(kind="remove", text=d) for d in drop_candidates[:5]],
            evidence=[EvidenceRef(artifactId="a-stat-tests")], confidence=0.72,
            sourceAgent="data", sourceMode="pipeline", afterTask="2.4"))
    vif_note = (" VIF uses the pairwise-collinearity proxy (more indicators than the "
                "year-over-year periods it was computed on, so a full multivariate VIF "
                "is unidentified)."
                if proxy_vif else "")

    # A zero total means one test failed outright. Say WHICH one — "unconsiderable"
    # on its own gives the reviewer nothing to act on.
    def _zero_reason(r: StatScoreRow) -> str:
        failed = [name for name, score in
                  (("volatility", r.cv_score), ("correlation", r.pearson_score),
                   ("collinearity", r.vif_score)) if score == 0.0]
        return " and ".join(failed) or "screening"

    findings: list[TaskFinding] = []
    zeroed = [r for r in card.rows if r.total == 0.0]
    if zeroed:
        labels = [f"{_label(r)} (failed {_zero_reason(r)})" for r in zeroed]
        findings.append(TaskFinding(
            text="Zero statistical score — these indicators cannot enter the model: "
                 + "; ".join(labels[:5])
                 + (f" +{len(labels) - 5} more" if len(labels) > 5 else ""),
            tone="flag", evidence=[EvidenceRef(artifactId="a-stat-tests")]))
    findings.append(TaskFinding(
        text=f"Statistical screening scored {len(card.rows)} indicator(s) on CV/Pearson/VIF; "
        f"{len(drop_candidates)} flagged to drop, {len(acceptable)} need review." + vif_note,
        tone="flag" if drop_candidates else "info",
        evidence=[EvidenceRef(artifactId="a-stat-tests")]))
    eng.add_findings(st, task["id"], findings)


async def ols_search_and_fit(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.5 — search each L4 factor's candidate indicators and fit the winner.

    The design (02-data-agent §2.34) is a per-L4 indicator search, not a manual
    variable pick: for each factor the AI tries its candidate indicators across
    repeated OLS fits and keeps the choice that lands the factor in its Knowledge
    ROI / Contribution range (maximising the in-range factor count, tie-broken on
    R²), under a fit budget. The single response (Y) comes from the 2.1 Metrics
    Type; transforms/controls scale to the series length. The chosen selection is
    written to ``st.ols_config`` (so the ledger, 2.6 and 3.2 all read the same
    resolved selection), then fitted and rendered as the ``olsTree`` for the d-2.5
    review. Nothing is invented — every number is computed or reused from 2.4.

    The step emits its own stages as activity events so the Build Process shows the
    work — aggregate, enumerate, search, refit, AI benchmark review, summary —
    rather than a single opaque "2.5 ran" line."""
    from app.agents import ols_benchmark
    from app.agents.dataset_cache import model_df, model_objects

    tid = task["id"]

    # 1 · the data the model is fitted on.
    df = model_df(st)
    months = int(df["month"].nunique()) if not df.empty and "month" in df.columns else 0
    metrics = int(df["metric"].nunique()) if not df.empty and "metric" in df.columns else 0
    objs = model_objects(st)
    eng.emit(st, "data", "info",
             f"Aggregated the long table to {len(objs) or 0} national total model "
             f"({len(df)} rows · {months} months · {metrics} indicators).", tid)

    # 2 · what survived the earlier layers and is therefore searchable.
    def on_pass(info: dict) -> None:
        eng.emit(st, "data", "info",
                 f"Search pass {info['pass']}: {info['fits']} trial regression(s), "
                 f"{info['swaps']} indicator swap(s) improved the model "
                 f"(in-range {info['inRange']} · correct paid-driver signs {info['signed']} "
                 f"· R²={info['r2']:.3f}).", tid)

    cfg, trace = build_ols_search(st, on_pass=on_pass)
    eng.emit(st, "data", "info",
             f"Enumerated {trace.get('candidates', 0)} candidate indicator(s) across "
             f"{trace.get('l4Searched', 0)} factor(s) that survived mapping, quality, "
             f"sign-off and statistical screening.", tid)

    # 3 · the winning setup, refitted and rendered.
    st.ols_config = cfg
    body, prefit, flagged = build_ols_review(st, eng=eng, task_id=tid)
    fit = next((o for o in body.get("objects", []) if not o.get("error")), {})
    eng.emit(st, "data", "info",
             "Best model refit: "
             + (f"R²={fit.get('r2'):.3f} · adj R²={fit.get('adjR2'):.3f} · "
                f"{fit.get('nObs')} obs · {fit.get('drivers')} drivers · "
                f"baseline {fit.get('baselinePct')}%."
                if fit.get("r2") is not None else "the fit produced no usable model object."),
             tid)

    # 4 · the AI reads each fitted factor against its Knowledge band.
    in_model = [r for r in body.get("tree", []) if r.get("inModel")]
    verdicts = await ols_benchmark.review_rows([{
        "key": r["key"], "l1": r.get("l1", ""), "l3": r.get("l3", ""), "l4": r.get("l4", ""),
        "indicator": r.get("indicator", ""), "coef": r.get("coef"), "tValue": r.get("tValue"),
        "pValue": r.get("pValue"), "roi": r.get("roi"), "contribution": r.get("contribution"),
        "roiRange": r.get("roiRange", ""), "contributionRange": r.get("contributionRange", ""),
        "rangeSource": r.get("rangeSource", ""), "roiStatus": r.get("roiStatus"),
        "contributionStatus": r.get("contributionStatus"),
    } for r in in_model])
    for r in body.get("tree", []):
        v = verdicts.get(r.get("key", ""))
        r["aiVerdict"] = v["verdict"] if v else ""
        r["aiRationale"] = v["rationale"] if v else ""
    ai_written = sum(1 for v in verdicts.values() if v.get("ai"))
    consistent = sum(1 for v in verdicts.values() if v["verdict"] == "consistent")
    doubted = sum(1 for v in verdicts.values() if v["verdict"] in ("questionable", "implausible"))
    eng.emit(st, "data", "info",
             f"Benchmark review of {len(in_model)} fitted factor(s) against the Knowledge "
             f"ROI / Contribution ranges: {consistent} judged consistent, {doubted} flagged"
             + ("" if ai_written else " (computed readout — no language model configured)")
             + ".", tid)

    body["search"] = trace
    eng.produce(st, "a-ols-test", body=body, state="confirmed", agent="data")
    eng.set_analysis(st, "prefit", prefit)
    eng.set_analysis(st, "ols_flagged", flagged)
    eng.set_analysis(st, "ols_search", trace)
    # Human-readable warning strings reused by the 2.6 funnel.
    warnings = [f"{f['l4']} · {f['indicator']}" for f in flagged]
    eng.set_analysis(st, "selection_warnings", warnings[:20])

    summary = body.get("summary", {})
    no_metric = summary.get("notInModel", 0)
    n_sel = sum(1 for c in cfg.x_candidates if c.selected)
    eng.emit(st, "data", "info",
             f"Summary: {n_sel} indicator(s) adopted into the national model, "
             f"{summary.get('inRange', 0)} inside their Knowledge band, "
             f"{len(flagged)} flagged for the sign-off gate.", tid)
    findings = [TaskFinding(
        text=f"OLS indicator search: {trace.get('note', '')} "
        f"{n_sel} indicator(s) chosen; {summary.get('inModel', 0)} entered the fit, "
        f"{summary.get('inRange', 0)} within their industry ROI / Contribution band, "
        f"{len(flagged)} flagged for review, {summary.get('noBenchmark', 0)} without a benchmark.",
        tone="flag" if flagged else "info", evidence=[EvidenceRef(artifactId="a-ols-test")])]
    if cfg.data_source == "reference":
        findings.append(TaskFinding(
            text="No published project data — the search ran against the reference dataset. "
            "Publish the project's own assets in the Data Engine for a real fit.",
            tone="flag", evidence=[EvidenceRef(artifactId="a-ols-test")]))
    red_flagged = [o for o, v in prefit.items() if v.get("red_flags")]
    if red_flagged:
        findings.append(TaskFinding(text=f"OLS red flags on: {', '.join(red_flagged)}.",
                                    tone="flag", evidence=[EvidenceRef(artifactId="a-ols-test")]))
    # Misspecification guard — a baseline over 100% (trend/seasonality controls
    # absorbing more than all of actual sales) or a wrong-sign paid driver means
    # the fit, not the data, is producing the wild contributions that then fall
    # outside every Knowledge band. Recommend reducing the controls (fewer Fourier
    # terms / drop the trend in 2.5p) instead of dropping the flagged indicators.
    misspecified = [
        o.get("object", "") for o in body.get("objects", [])
        if (o.get("baselinePct") is not None and o["baselinePct"] > 100)
        or any("Wrong-sign" in f or "wrong-sign" in f for f in (o.get("redFlags") or []))
    ]
    if misspecified:
        findings.append(TaskFinding(
            text=(f"Fit likely mis-specified on {', '.join(misspecified)}: baseline exceeds 100% "
                  "or a paid driver has the wrong sign — the trend/seasonality controls are "
                  "over-absorbing sales, which pushes contributions outside every band. Reduce "
                  "the controls (fewer Fourier terms or drop the trend) in the OLS settings "
                  "before dropping flagged indicators."),
            tone="flag", evidence=[EvidenceRef(artifactId="a-ols-test")]))
    eng.add_findings(st, task["id"], findings)
    # 2.5 gate — make the selection-confirmation question reflect real flags.
    dec = task.get("decision")
    if dec and dec["id"] in st.decisions and (flagged or no_metric):
        example = flagged[0]["indicator"] if flagged else ""
        st.decisions[dec["id"]].question = (
            f"{len(flagged)} indicator(s) fell outside their industry ROI / Contribution "
            f"range" + (f" (e.g. {example})" if example else "")
            + f" and {no_metric} mapped factor(s) have no usable model metric. "
            "Confirm the selection, drop the flagged indicators, or revisit the business hypotheses?"
        )


async def assemble_master_data(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.6 — assemble the Master Data feature wide table: pivot the indicators that
    survived the four filter layers (quality → business → statistical → OLS test)
    into one wide monthly frame per model object — the locked modeling input.

    The filter is *physical* and it is the ledger's: the master table carries the
    indicators the ledger reports as adopted, fitted against the response the
    human confirmed at 2.5y and restricted to the variables they ticked at 2.5x.
    Re-deriving any of that here is how the table came to disagree with the fit
    the human actually signed off."""
    df = model_df(st)
    sel = model_selection(st)

    obj_rows: list[dict] = []
    total_features = 0
    from app.agents.vocabulary import vocab_for
    _vocab = vocab_for(st)
    for obj in model_objects(st):
        try:
            mf = build_model_frame(df, obj, vocab=_vocab, exclude=sel.exclude_for(obj),
                                   y_metric=sel.y_for(obj), include=sel.include_for(obj),
                                   st=st)
        except Exception as e:  # noqa: BLE001 — one unfittable object must not
            # sink the others; the object reports its own error on the card.
            obj_rows.append({"object": obj, "months": 0, "features": 0,
                             "y": "", "error": str(e)[:160]})
            continue
        total_features += len(mf.x_cols)
        obj_rows.append({"object": obj, "months": len(mf.frame),
                         "features": len(mf.x_cols), "y": mf.y_col})

    led = indicator_ledger(st)
    # interim: dedup by indicator key; Task 7 replaces with per-object grouping
    # `indicator_ledger` now yields one LedgerRow per (object, l4, metric), so a
    # multi-object project (danone-mizone has 4) repeats every indicator once
    # per object. Dedup by the indicator identity key here — first occurrence
    # wins — so the 2.6 lock-gate lists/counts aren't channel-inflated.
    adopted_rows: list = []
    seen_adopted: set = set()
    for r in led:
        if r.adopted and r.key not in seen_adopted:
            seen_adopted.add(r.key)
            adopted_rows.append(r)
    rejected_rows: list = []
    seen_rejected: set = set()
    for r in led:
        if not r.adopted and r.key not in seen_rejected:
            seen_rejected.add(r.key)
            rejected_rows.append(r)
    rejected = rejected_rows
    from app.agents.master_data import granularity_reference
    body = {
        "objects": obj_rows,
        # 2.32 reference deliverable · sheet 1: per-indicator model granularity
        # (渠道 scope × 区域 granularity; blank = not selected into the model). The
        # Data Station (sheet 2) is queried live via POST /master-data/data-station.
        "granularityRef": granularity_reference(st),
        # {"combined": [...], "byObject": {object: [...]}} — combined stays the
        # pre-per-object rollup any un-migrated reader still expects; byObject
        # is each channel's own funnel (the same indicator can die at a
        # different layer, or survive, in a different channel).
        "funnel": funnel(st),
        "dimensions": dimensions(st),
        # per-object adopted/rejected, each row carrying its full verdict
        # chain — Tab 2's per-channel breakdown (spec §3.5).
        "byObject": _ledger_by_object(led),
        # flat rollups kept for one release so an un-migrated reader still
        # works; deduped by indicator key (first occurrence wins) so a
        # multi-object project's per-object ledger rows don't channel-inflate
        # these counts/lists.
        "adopted": [{"l1": r.l1, "l2": r.l2, "l3": r.l3, "l4": r.l4,
                     "indicator": r.indicator} for r in adopted_rows],
        "rejected": [{"l1": r.l1, "l2": r.l2, "l3": r.l3, "l4": r.l4,
                      "indicator": r.indicator, "rejectedAt": r.rejected_at,
                      "reason": r.reason,
                      "verdicts": [{"layer": v.layer, "task": v.task, "label": v.label,
                                    "status": v.status, "note": v.note} for v in r.verdicts]}
                     for r in rejected_rows],
        "note": ("The master table carries only the indicators that survived every filter "
                 "layer, over the response confirmed at 2.5y and the variables ticked at "
                 "2.5x. Slice it by product × channel × region below; every rejected "
                 "indicator keeps the full chain of verdicts that removed it."),
    }
    eng.produce(st, "a-master-data", body=body, state="proposed", agent="data")
    eng.set_analysis(st, "master_data", {
        "objects": len(obj_rows), "features": total_features,
        "adopted": len(adopted_rows), "rejected": len(rejected),
        "excluded": sorted(f"{r.l4} · {r.indicator}" for r in rejected)[:20],
    })
    by_layer: dict[str, int] = {}
    for r in rejected:
        by_layer[r.rejected_at] = by_layer.get(r.rejected_at, 0) + 1
    trail = ", ".join(f"{LAYER_LABEL.get(k, k)} {v}" for k, v in by_layer.items()) or "none"
    eng.add_findings(st, task["id"], [TaskFinding(
        text=f"Master data assembled: {len(obj_rows)} model object(s), {total_features} feature "
        f"column(s) from {len(adopted_rows)} adopted indicator(s). "
        f"Rejected along the way — {trail}. Review and lock it as the modeling input.",
        evidence=[EvidenceRef(artifactId="a-master-data")])])
    # Make the lock gate state what is actually being locked.
    if "d-2.6" in st.decisions:
        st.decisions["d-2.6"].question = (
            f"The master table carries {total_features} feature column(s) across "
            f"{len(obj_rows)} model object(s), assembled from {len(adopted_rows)} "
            f"adopted indicator(s) ({len(rejected)} rejected upstream). Lock it as the "
            "modeling input?")
