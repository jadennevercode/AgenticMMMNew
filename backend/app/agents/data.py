"""S2/S3 Data Agent handlers — real quality scoring, ETL docs, integration,
business sense-check, statistical screening, and pre-fit. All numbers computed
from the real dataset via pandas / app.mmm — never hardcoded.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from app import ingest
from app.agents import business_review, data_rules
from app.agents.common import agent_system, artifact_text, llm_body
from app.agents.data_rules import (
    MetricStats,
    final_verdict,
    score_statistical,
    score_validation,
)
from app.llm.volcano import LLMError, get_llm
from app.agents.dataset_cache import model_df, model_objects
from app.domain.models import (
    ClientQA,
    ClientQARow,
    DiffLine,
    EvidenceRef,
    Insight,
    InsightAction,
    Proposal,
    QualityRow,
    QualityScorecard,
    TaskFinding,
)
from app.mmm import build_model_frame, fit_ols, run_mmm
from app.mmm.transforms import standardize
from app.orchestrator.engine import Engine
from app.store.state import ProjectState

SYS = agent_system("data")


_VERDICT_CN = {"pass": "验收", "borderline": "人决策", "unusable": "弃用·预警"}
_DISPOSITION_CN = {"accept": "采纳", "flag": "待确认", "drop": "剔除"}
_DISPOSITION_DEFAULT = {"pass": "accept", "borderline": "flag", "unusable": "drop"}

_QUALITY_COLUMNS = ["L1", "L2", "L3", "L4", "指标",
                    "一致性评分", "一致性情况", "完整性评分", "完整性情况",
                    "颗粒度评分", "颗粒度情况", "真实性评分", "真实性情况",
                    "Total Score", "判定", "处置", "备注"]


def _s(v: object) -> str:
    """NA-safe cell string."""
    return "" if (v is None or pd.isna(v)) else str(v)


def quality_sheet(card: QualityScorecard) -> dict:
    """Render the quality scorecard artifact body (mirrors the Excel 2.12 layout:
    per-dimension 评分 + 情况, Total Score = weakest dimension, 判定/处置)."""
    rows = [[r.l1, r.l2, r.l3, r.l4, r.indicator,
             f"{r.consistency:g}", r.consistency_note,
             f"{r.completeness:g}", r.completeness_note,
             f"{r.granularity:g}", r.granularity_note,
             f"{r.accuracy:g}", r.accuracy_note,
             f"{r.total:g}", _VERDICT_CN.get(r.auto_verdict, r.auto_verdict),
             _DISPOSITION_CN.get(r.disposition, r.disposition), r.note]
            for r in card.rows]
    return {"sheets": [
        {"name": "2.12数据质量评分", "columns": _QUALITY_COLUMNS, "rows": rows},
    ]}


def client_qa_sheet(qa: ClientQA) -> dict:
    """Render the client Q&A tracker artifact body from the structured object."""
    rows = [[r.question, r.owner, r.response, r.status] for r in qa.rows]
    return {"sheets": [{
        "name": "数据&指标沟通表", "columns": ["问题", "负责人", "反馈", "状态"],
        "rows": rows or [["—", "—", "", "open"]],
    }]}


def build_client_qa(st: ProjectState) -> ClientQA:
    """Seed the editable Client Q&A tracker from real data issues (unusable /
    borderline metrics on the scorecard) plus the factor tree's key indicators.
    Lives in 2.32 (Data display) — the data & metric communication tracker."""
    qa_items: list[ClientQARow] = []
    seen: set[str] = set()

    def _add_q(question: str, owner: str = "") -> None:
        key = question.lower()
        if question and key not in seen and len(qa_items) < 20:
            seen.add(key)
            qa_items.append(ClientQARow(id=f"qa-{len(qa_items)}", question=question,
                                        owner=owner, status="open"))

    card = st.quality_scorecard
    if card is not None:
        unusable = [f"{r.l4 or r.l3} · {r.indicator}".strip(" ·")
                    for r in card.rows if r.auto_verdict == "unusable"]
        borderline = [f"{r.l4 or r.l3} · {r.indicator}".strip(" ·")
                      for r in card.rows if r.auto_verdict == "borderline"]
        for lbl in unusable[:5]:
            _add_q(f"数据不可用，请确认是否有更长历史或替代来源：{lbl}")
        for lbl in borderline[:5]:
            _add_q(f"数据为临界（覆盖/口径偏弱），请确认定义与可得性：{lbl}")
    ft = st.factor_tree
    if ft is not None:
        for r in ft.rows:
            if r.status not in ("baseline", "accepted"):
                continue
            label = f"{r.l3} / {r.l4} — {r.indicator}".strip(" /—")
            if label:
                _add_q(f"确认数据定义与可得性：{label}")
    return ClientQA(rows=qa_items or [ClientQARow(id="qa-0", question="—", status="open")])


def accepted_metric_labels(card: QualityScorecard) -> list[str]:
    """Metric labels the human kept (disposition != drop) — the S2 blackboard."""
    return [f"{r.l4 or r.l3} · {r.indicator}".strip(" ·")
            for r in card.rows if r.disposition != "drop"]


def _metric_stats(grp: pd.DataFrame) -> MetricStats:
    """Computable proxies for one factor×metric series (pandas, never LLM)."""
    vals = grp["value"].to_numpy(dtype=float)
    finite = np.isfinite(vals)
    nonneg = float(np.sum(vals[finite] >= 0) / finite.sum()) if finite.sum() else 0.0
    mser = grp["month"].dropna().astype("int64")
    months = int(mser.nunique())
    if months:
        lo, hi = int(mser.min()), int(mser.max())
        span = (hi // 100 - lo // 100) * 12 + (hi % 100 - lo % 100) + 1
        span = max(span, months)  # guard against malformed yyyymm
    else:
        span = 0
    monthly = bool(grp["month"].notna().mean() >= 0.5)
    return MetricStats(
        n=len(vals), months=months, span_months=span, nonneg_ratio=nonneg,
        regions=int(grp["province_group"].nunique(dropna=True)),
        channels=int(grp["channel"].nunique(dropna=True)), monthly=monthly,
    )


_SCHEMA_COLUMNS = [
    ["TASKNAME / 数据源方 / 数据源 / 数据分类", "任务与来源标识", "定位数据源"],
    ["品牌 / 产品线 / 产品", "模型颗粒度", "Product 主数据清洗，缺失填 NA"],
    ["大区 / 省份组别 / 省份", "模型颗粒度", "Geo 主数据清洗"],
    ["渠道类型 / 渠道", "模型颗粒度", "Channel 主数据清洗"],
    ["年 / 月", "时间颗粒度", "Time 主数据清洗（建模最低月度）"],
    ["数据类型 Level1–Level4", "对应因子树 L1–L4", "按因子结构树命名"],
    ["数据类型 Level5–Level8", "因子下钻颗粒度", "L4 的下钻维度，缺失填 NA"],
    ["METRICS类型 / METRICS / Unit / VALUE", "指标与值", "Unit: percentage / Unit / Volume K / RMB"],
]


def _standard_sheets() -> list[dict]:
    """Load the two real 2.11 sheets (compliance principles + 0/0.5/1 rubric) from
    the reference workbook; fall back to the KB rule JSON when it is absent."""
    try:
        rules = ingest.load_validation_rules()
    except Exception:  # noqa: BLE001 — reference dir may be absent
        rules = {}
    principles = rules.get("principles") or []
    rubric_rows: list[list[str]] = []
    for dim in (rules.get("dimensions") or {}).values():
        label = str(dim.get("label", ""))
        for crit in dim.get("criteria", []):
            rubric_rows.append([label, str(crit.get("name", "")),
                                str(crit.get("score_0", "")), str(crit.get("score_0_5", "")),
                                str(crit.get("score_1", ""))])
    if not rubric_rows:  # reference unavailable — fall back to the KB-backed rows
        rubric_rows = data_rules.validation_rule_rows()
    return [
        {"name": "2.11数据通用校验标准", "columns": ["数据 Compliance 规则"],
         "rows": [[p] for p in principles] or [["（参考标准缺失，使用知识库 fallback）"]]},
        {"name": "2.11打分规则", "columns": ["维度", "子项", "0分", "0.5分", "1分"],
         "rows": rubric_rows},
    ]


async def validation_standard(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.11 — surface the EXISTING general data-validation standard (the four-rule
    compliance principles + the 0/0.5/1 scoring rubric), loaded from the reference
    workbook (not AI-authored). It grounds the AI scoring in 2.12."""
    eng.produce(st, "a-validation-standard", body={"sheets": _standard_sheets()},
                state="confirmed", agent="data")
    eng.add_findings(st, task["id"], [TaskFinding(
        text="Validation standard loaded: four-rule compliance principles + the 0/0.5/1 "
        "scoring rubric — the standard the AI scores against in 2.12.",
        evidence=[EvidenceRef(artifactId="a-validation-standard")])])


async def wide_schema(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.21 — define the unified long-table schema (因子树即数据 Schema). The factor
    tree's L1–L8 become long-table columns; this is the binding contract the
    uploaded data is parsed into and the integration pipeline outputs to."""
    ft = st.factor_tree
    cov_rows: list[list[str]] = []
    if ft is not None:
        seen: set[tuple[str, str]] = set()
        for r in ft.rows:
            key = (r.l3, r.l4)
            if key in seen or not (r.l3 or r.l4):
                continue
            seen.add(key)
            cov_rows.append([r.l1, r.l2, r.l3, r.l4, r.indicator or ""])
    body = {"sheets": [
        {"name": "2.21宽表维度", "columns": ["列", "定义", "规则"], "rows": _SCHEMA_COLUMNS},
        {"name": "因子树→Schema 列", "columns": ["L1", "L2", "L3", "L4", "主指标"],
         "rows": cov_rows or [["—", "—", "—", "—", "(factor tree not confirmed)"]]},
    ]}
    eng.produce(st, "a-schema", body=body, state="confirmed", agent="data")
    eng.set_analysis(st, "schema_factor_rows", len(cov_rows))
    eng.add_findings(st, task["id"], [TaskFinding(
        text=f"Wide-table schema defined: L1–L8 → long-table columns; "
        f"{len(cov_rows)} L3×L4 factor rows mapped.",
        evidence=[EvidenceRef(artifactId="a-schema")])])


def _coerce_score(v: object, fallback: float) -> float:
    """Snap an LLM-returned score to the {0, 0.5, 1} band; fall back if unusable."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return fallback
    return min((0.0, 0.5, 1.0), key=lambda b: abs(b - f))


async def _ai_score_rows(evidence: list[dict]) -> dict[str, dict]:
    """Have the AI assign 0/0.5/1 per dimension + a 情况 note for each row, grounded
    in the loaded rubric and the computed evidence. Returns {} if the LLM is
    unavailable (caller then falls back to the deterministic proxy scores)."""
    if not evidence:
        return {}
    try:
        llm = get_llm()
    except LLMError:
        return {}
    rubric = data_rules.validation_rule_rows()
    rubric_txt = "\n".join(f"{r[0]} | {r[1]} | 0={r[2]} | 0.5={r[3]} | 1={r[4]}" for r in rubric[:40])
    out: dict[str, dict] = {}
    for start in range(0, len(evidence), 40):  # chunk to keep JSON parseable
        batch = evidence[start:start + 40]
        user = (
            "Score each data row on the four data-validation dimensions (consistency 一致性, "
            "completeness 完整性, granularity 颗粒度, accuracy 真实性), each strictly 0, 0.5 or 1, "
            "applying the rubric below to the computed evidence. Write a short Chinese 情况 note "
            "(≤20 chars) per dimension citing the evidence. Return a JSON array of "
            '{"id","consistency","completeness","granularity","accuracy","notes":'
            '{"consistency","completeness","granularity","accuracy"}}.\n\n'
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


async def score_data(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.12 — the AI scores every factor×metric on the four validation dimensions
    (grounded in the 2.11 rubric + computed evidence), into an editable scorecard.
    The acceptance VERDICT (weakest dimension governs) is reviewed by a human in 2.13."""
    df = model_df(st)
    # 1) deterministic evidence + baseline per row (the AI's grounding & fallback).
    base: list[tuple[str, dict, MetricStats, object]] = []
    grouped = df.groupby(["l1", "l2", "l3", "l4", "metric"], dropna=False)
    for i, ((l1, l2, l3, l4, metric), grp) in enumerate(grouped):
        if not str(metric).strip() or str(metric) == "<NA>":
            continue
        stats = _metric_stats(grp)
        sc = score_validation(stats)
        rid = f"q-{i}"
        base.append((rid, {"id": rid, "l1": _s(l1), "l2": _s(l2), "l3": _s(l3), "l4": _s(l4),
                           "indicator": _s(metric)}, stats, sc))
    # 2) AI scoring over the computed evidence (falls back to baseline if no LLM).
    evidence = [{**meta, "evidence": {"months": stats.months, "span_months": stats.span_months,
                                      "nonneg_ratio": round(stats.nonneg_ratio, 3),
                                      "regions": stats.regions, "channels": stats.channels,
                                      "monthly": stats.monthly},
                 "baseline": {"consistency": sc.consistency, "completeness": sc.completeness,
                              "granularity": sc.granularity, "accuracy": sc.accuracy}}
                for (_rid, meta, stats, sc) in base]
    ai = await _ai_score_rows(evidence)
    used_ai = bool(ai)
    # 3) merge → scorecard rows with the weakest-dimension verdict.
    qrows: list[QualityRow] = []
    borderline: list[str] = []
    unusable: list[str] = []
    for (rid, meta, _stats, sc) in base:
        a = ai.get(rid, {})
        notes = a.get("notes", {}) if isinstance(a.get("notes"), dict) else {}
        cons = _coerce_score(a.get("consistency"), sc.consistency)
        comp = _coerce_score(a.get("completeness"), sc.completeness)
        gran = _coerce_score(a.get("granularity"), sc.granularity)
        acc = _coerce_score(a.get("accuracy"), sc.accuracy)
        total, verdict = final_verdict(cons, acc, comp, gran)
        label = f"{meta['l4'] or meta['l3'] or meta['l1']} · {meta['indicator']}".strip(" ·")
        qrows.append(QualityRow(
            id=rid, l1=meta["l1"], l2=meta["l2"], l3=meta["l3"], l4=meta["l4"], indicator=meta["indicator"],
            consistency=cons, completeness=comp, granularity=gran, accuracy=acc,
            consistencyNote=str(notes.get("consistency", "")), completenessNote=str(notes.get("completeness", "")),
            granularityNote=str(notes.get("granularity", "")), accuracyNote=str(notes.get("accuracy", "")),
            total=total, autoVerdict=verdict, disposition=_DISPOSITION_DEFAULT[verdict],
        ))
        if verdict == "borderline":
            borderline.append(label)
        elif verdict == "unusable":
            unusable.append(label)
    qrows.sort(key=lambda r: r.total)
    card = QualityScorecard(rows=qrows)
    st.quality_scorecard = card
    eng.produce(st, "a-quality-scorecard", body=quality_sheet(card), state="confirmed", agent="data")
    eng.set_analysis(st, "quality", {
        "total": len(qrows), "accepted": len(accepted_metric_labels(card)),
        "borderline": borderline[:20], "unusable": unusable[:20],
        "accepted_metrics": accepted_metric_labels(card), "scored_by": "ai" if used_ai else "proxy",
    })
    findings: list[TaskFinding] = [TaskFinding(
        text=f"{'AI scored' if used_ai else 'Scored'} {len(qrows)} metrics on 4 dimensions: "
        f"{len(qrows)-len(borderline)-len(unusable)} accept (1), {len(borderline)} need a call (0.5), "
        f"{len(unusable)} unusable (0). Verdict = weakest dimension; human reviews in 2.13.",
        evidence=[EvidenceRef(artifactId="a-quality-scorecard")])]
    if unusable:
        findings.append(TaskFinding(text=f"Unusable (alert): {', '.join(unusable[:3])}",
                                    tone="flag", evidence=[EvidenceRef(artifactId="a-quality-scorecard")]))
    eng.add_findings(st, task["id"], findings)
    # Feed the 2.13 human-review gate question with the real 0.5/0-band metrics.
    if "d-2.13" in st.decisions:
        if borderline or unusable:
            eg = borderline[0] if borderline else unusable[0]
            q = (f"{len(borderline)} metric(s) scored 0.5 (e.g. {eg}) and {len(unusable)} scored 0. "
                 "Review the verdicts: accept the 1s, and decide each 0.5 "
                 "(re-collect / drop / accept-with-caveat). 0s are unusable.")
        else:
            q = "All metrics scored 1 — review and accept the data-quality verdicts."
        st.decisions["d-2.13"].question = q


async def processing_logic(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.22 — draft the per-source processing logic (TaskLog) for human confirmation."""
    dd = ingest.load_data_dictionary()
    log_rows = []
    for i, r in enumerate(dd[:60], 1):
        log_rows.append([str(i), str(r.get("table_name") or r.get("sheet") or ""),
                         str(r.get("source_system") or ""), str(r.get("etl_logic") or "")[:80]])
    eng.produce(st, "a-data-dictionary", body={"sheets": [
        {"name": "B1.TaskLog", "columns": ["NO", "TASKNAME", "数据来源", "数据处理"], "rows": log_rows},
        {"name": "数据处理流程", "columns": ["步骤", "说明"],
         "rows": [["1", "初步梳理数据逻辑"], ["2", "定义澄清 & 补充数据"], ["3", "补充后重新梳理"],
                  ["4", "by task 导出检查（逻辑/字段/趋势）"], ["5", "更新后重导出 charting"],
                  ["6", "与源数据 cross-check（两人互检）"], ["7", "寻找异常点原因"]]},
    ]}, state="confirmed", agent="data")


async def data_dictionary(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.23 — register the ODS→DW data dictionary (per-source metadata + column-level
    ETL: Hardcode / Mapping / Transform / Calculation) the pipeline reads."""
    dd = ingest.load_data_dictionary()
    dict_rows = []
    for r in dd[:80]:
        dict_rows.append([str(r.get("theme") or ""), str(r.get("sheet") or ""),
                          str(r.get("source_system") or ""), str(r.get("granularity") or ""),
                          str(r.get("serves_l4") or ""), str(r.get("y_or_x") or "")])
    eng.produce(st, "a-data-warehouse", body={"sheets": [
        {"name": "数据字典", "columns": ["Theme", "SheetName", "来源系统", "granularity", "服务 L4", "Y/X"],
         "rows": dict_rows},
        {"name": "列级 ETL 四类", "columns": ["类型", "说明"], "rows": [
            ["Hardcode", "常量"], ["Mapping", "主数据表映射（渠道/产品线/大区…）"],
            ["Transform", "格式/case when（日期、渠道）"], ["Calculation", "派生（如 PPI = 促销零售价 ÷ 原零售价）"]],
         }],
    }, state="confirmed", agent="data")
    eng.add_findings(st, task["id"], [TaskFinding(
        text=f"Data dictionary registered: {len(dict_rows)} source tables, column-level ETL in four classes.",
        evidence=[EvidenceRef(artifactId="a-data-warehouse")])])


async def integrate_dataset(eng: Engine, st: ProjectState, task: dict) -> None:
    df = model_df(st)
    n = len(df)
    sample = df.head(12)[["task_name", "brand", "province_group", "channel_type", "channel",
                          "year", "month", "metric", "value"]]
    sample_rows = [[("" if pd.isna(v) else str(v)) for v in row] for row in sample.to_numpy()]
    dims = {
        "brands": int(df["brand"].nunique()),
        "channels": int(df["channel_type"].nunique()),
        "regions": int(df["province_group"].nunique()),
        "metrics": int(df["metric"].nunique()),
        "months": int(df[["year", "month"]].dropna().drop_duplicates().shape[0]),
    }
    body = {"sheets": [
        {"name": "dataset_model_data", "columns": ["Task name", "品牌", "省份组别", "渠道类型", "渠道",
                                                   "年", "月", "METRICS", "VALUE"], "rows": sample_rows},
        {"name": "说明", "columns": ["项", "内容"],
         "rows": [["总行数", f"{n:,}"], ["品牌数", str(dims['brands'])], ["渠道类型数", str(dims['channels'])],
                  ["区域组数", str(dims['regions'])], ["指标数", str(dims['metrics'])],
                  ["覆盖月份", str(dims['months'])]]},
    ]}
    eng.produce(st, "a-dataset", body=body, state="confirmed", agent="data")
    eng.set_analysis(st, "dataset_dims", dims | {"rows": n})
    eng.add_findings(st, task["id"], [TaskFinding(
        text=f"Master dataset integrated: {n:,} rows · {dims['channels']} channels · "
        f"{dims['regions']} regions · {dims['months']} months.",
        evidence=[EvidenceRef(artifactId="a-dataset")])])


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


async def business_rules(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.31 — lay out the business-validation rules (六步法) and the L5–L8 drill-down
    map. Anomalies are localized here to seed the review deck and client questions."""
    df = model_df(st)
    anomalies = _anomalies(df)
    eng.set_analysis(st, "anomalies", anomalies)
    ctx = artifact_text(st, ["a-factor-tree"])
    drill = await llm_body(
        SYS, "Produce a business-validation & drill-down framework sheet: '业务校验六步法' "
        "[步骤, 内容] (全景概览→维度拆解→异常定位→假设生成→先验提取→客户核对) and '下钻因子树' "
        "[Level 4 因子, 下钻维度 L5–L8], grounded in the factor tree.\n\n" + ctx, "sheet")
    eng.produce(st, "a-drill-framework", body=drill, state="confirmed", agent="data")
    eng.add_findings(st, task["id"], [TaskFinding(
        text=f"Business-validation rules + L5–L8 drill map ready; {len(anomalies)} YoY anomalies "
        "localized for the review deck.",
        evidence=[EvidenceRef(artifactId="a-drill-framework")])])


async def _ai_narrate_review(review: dict) -> None:
    """Best-effort: let the AI refine each chart's 业务解读 from the computed numbers.
    Falls back silently to the deterministic interpretation when no LLM is available."""
    charts = [c for step in review.get("steps", []) for c in step.get("charts", [])]
    if not charts:
        return
    try:
        llm = get_llm()
    except LLMError:
        return
    payload = [{"id": c["id"], "title": c["title"], "x": c["x"][:36],
               "series": [{"name": s["name"], "data": s["data"][:36]} for s in c["series"]],
               "conclusion": c["conclusion"]} for c in charts]
    try:
        reply = await llm.json(system=SYS, user=(
            "For each business-review chart, write a concise Chinese 业务解读 (≤40 字) grounded ONLY "
            "in the numbers given (trend, turning points, 费用vs销量 efficiency). Return a JSON array "
            'of {"id","interpretation"}.\n\n' + json.dumps(payload, ensure_ascii=False)))
    except LLMError:
        return
    items = reply if isinstance(reply, list) else reply.get("rows", [])
    notes = {str(it["id"]): str(it.get("interpretation", "")) for it in items
             if isinstance(it, dict) and it.get("id")}
    for c in charts:
        if notes.get(c["id"]):
            c["interpretation"] = notes[c["id"]]


async def _hypothesis_step(st: ProjectState, anomalies: list[dict]) -> dict:
    """步骤4 假设生成 — anomaly → business hypotheses (AI, grounded; templated fallback)."""
    cols = ["异常", "可能原因（假设）", "置信度", "验证方法", "涉及因子"]
    if not anomalies:
        return {"id": "step4", "title": "步骤4：假设生成",
                "intro": "基于异常节点 + 行业知识库生成业务原因假设，对应因子树中的具体因子。",
                "charts": [], "tables": [business_review._table(
                    "业务假设", cols, [["无显著异常", "数据未触发阈值，暂无需生成业务假设", "—", "—", "—"]],
                    note="若步骤3 出现异常节点，此处自动生成对应假设。")]}
    fallback = [[f"{a['channel']} {a['year']} {a['growth_pct']:+}%", "内容老化 / 竞品大促 / 执行下滑（待核查）",
                 "中", "对比历史弹性、竞品花费与执行数据", "—"] for a in anomalies[:5]]
    rows = fallback
    try:
        llm = get_llm()
        ctx = artifact_text(st, ["a-factor-tree"])
        reply = await llm.json(system=SYS, user=(
            "For each anomaly, propose business-cause hypotheses grounded in the factor tree. Return a "
            'JSON array of {"anomaly","hypotheses","confidence","validation","factors"} (Chinese, concise). '
            "Anomalies: " + json.dumps(anomalies[:5], ensure_ascii=False) + "\n\nFactor tree:\n" + ctx[:3000]))
        items = reply if isinstance(reply, list) else reply.get("rows", [])
        parsed = [[str(it.get("anomaly", "")), str(it.get("hypotheses", "")), str(it.get("confidence", "")),
                   str(it.get("validation", "")), str(it.get("factors", ""))]
                  for it in items if isinstance(it, dict)]
        if parsed:
            rows = parsed
    except LLMError:
        pass
    return {"id": "step4", "title": "步骤4：假设生成",
            "intro": "基于异常节点 + 行业知识库生成业务原因假设，对应因子树中的具体因子。",
            "charts": [], "tables": [business_review._table("业务假设", cols, rows)]}


def _client_check_step(qa: ClientQA) -> dict:
    rows = [[r.question, r.owner, r.response, r.status] for r in qa.rows]
    return {"id": "step6", "title": "步骤6：客户核对",
            "intro": "带假设与约束问客户：“您觉得对吗？”每张图逐页 Y/N 签核，未签核数据不入模。",
            "charts": [], "tables": [business_review._table(
                "数据&指标沟通表", ["问题", "负责人", "反馈", "状态"],
                rows or [["—", "—", "", "open"]])]}


async def data_review(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.32 — build the VISUALIZED six-step business review (computed charts + tables +
    AI 业务解读/假设 + per-chart Y/N sign-off) and the data & metric Q&A tracker; the
    client sign-off gate."""
    df = model_df(st)
    anomalies = st.analysis.get("anomalies") or _anomalies(df)
    eng.set_analysis(st, "anomalies", anomalies)
    qa = build_client_qa(st)
    st.client_qa = qa
    steps = [
        business_review.overview_step(df),       # 1 全景概览
        business_review.breakdown_step(df),      # 2 维度拆解
        business_review.anomaly_step(df, anomalies),  # 3 异常定位
        await _hypothesis_step(st, anomalies),   # 4 假设生成 (AI)
        business_review.prior_step(),            # 5 先验提取 (先不做)
        _client_check_step(qa),                  # 6 客户核对
    ]
    review = {"steps": [s for s in steps if s]}
    await _ai_narrate_review(review)
    eng.produce(st, "a-trend-review", body=review, state="proposed", agent="data")
    eng.produce(st, "a-client-qa", body=client_qa_sheet(qa), state="confirmed", agent="data")
    findings = [TaskFinding(
        text=f"Anomaly: {a['channel']} {a['year']} growth {a['growth_pct']:+}% — needs a business explanation.",
        tone="flag", evidence=[EvidenceRef(artifactId="a-trend-review")]) for a in anomalies[:3]]
    eng.add_findings(st, task["id"], findings)
    if anomalies:
        a0 = anomalies[0]
        eng.add_insight(st, Insight(
            id="i-2.32-anomaly", kind="connection",
            title=f"{a0['channel']} {a0['year']} {a0['growth_pct']:+}% anomaly",
            finding=f"{a0['channel']} shows a {a0['growth_pct']:+}% YoY move in {a0['year']}; "
            "cross-check against interview notes before modeling to avoid mis-attribution.",
            evidence=[EvidenceRef(artifactId="a-trend-review"), EvidenceRef(artifactId="a-interview")],
            confidence=0.78,
            actions=[InsightAction(kind="client_question", label="Confirm event window with client")],
            afterTask="2.32"))


async def stat_screening(eng: Engine, st: ProjectState, task: dict) -> None:
    rows: list[list[str]] = []
    drop_candidates: list[str] = []
    acceptable: list[str] = []
    for obj in model_objects(st):
        try:
            mf = build_model_frame(model_df(st), obj)
        except Exception:  # noqa: BLE001
            continue
        frame = mf.frame
        y = frame[mf.y_col].to_numpy(dtype=float)
        for c in mf.x_cols:
            x = frame[c].to_numpy(dtype=float)
            mean = np.nanmean(x)
            cv = abs(np.nanstd(x) / mean) if mean else 0.0
            try:
                pear = float(np.corrcoef(standardize(x), standardize(y))[0, 1])
            except Exception:  # noqa: BLE001
                pear = 0.0
            # crude VIF: regress this x on the others
            others = [o for o in mf.x_cols if o != c]
            vif = 1.0
            if others:
                try:
                    Xo = frame[others]
                    r = fit_ols(Xo, x)
                    vif = 1.0 / max(1e-6, 1.0 - r.r2)
                except Exception:  # noqa: BLE001
                    vif = 1.0
            sc = score_statistical(cv, pear, vif)
            verdict_cn = {"Good": "进入模型", "Acceptable": "人确认", "unconsiderable": "剔除"}[sc.verdict]
            if sc.drop:
                drop_candidates.append(f"{obj}·{c}")
                if sc.verdict != "unconsiderable":  # dropped for severe collinearity
                    verdict_cn = "剔除·共线"
            elif sc.verdict == "Acceptable":
                acceptable.append(f"{obj}·{c}")
            rows.append([f"{obj} · {c}"[:50], f"{cv:.2f}", f"{pear:+.2f}", f"{vif:.1f}",
                         f"{sc.cv_score:g}", f"{sc.pearson_score:g}", f"{sc.vif_score:g}",
                         f"{sc.total:g}", verdict_cn])
    body = {"sheets": [
        {"name": "打分规则", "columns": ["检验", "分", "条件", "含义"],
         "rows": data_rules.statistical_rule_rows()},
        {"name": "因子统计性检验结果",
         "columns": ["指标", "CV", "Pearson", "VIF", "CV分", "相关分", "共线分", "总分", "结论"],
         "rows": rows[:160]},
    ]}
    eng.produce(st, "a-stat-tests", body=body, state="confirmed", agent="data")
    eng.set_analysis(st, "screening_drops", drop_candidates[:20])
    eng.set_analysis(st, "screening_acceptable", acceptable[:20])
    # Make the G2.33 gate question reflect the real Acceptable-band count.
    dec = task.get("decision")
    if dec and dec["id"] in st.decisions:
        n = len(acceptable)
        st.decisions[dec["id"]].question = (
            f"{n} metric(s) scored Acceptable (1.5–3) — neither clearly in nor out"
            + (f" (e.g. {acceptable[0]})" if acceptable else "")
            + ". How should they enter the model?"
        )
    if drop_candidates:
        eng.add_proposal(st, Proposal(
            id="p-2.33-collinear", targetArtifactId="a-model-input",
            title="Drop collinear / low-signal variables before modeling",
            summary="Statistical screening flagged variables with high VIF or weak correlation: "
            + ", ".join(drop_candidates[:5]),
            diff=[DiffLine(kind="remove", text=d) for d in drop_candidates[:5]],
            evidence=[EvidenceRef(artifactId="a-stat-tests")], confidence=0.72,
            sourceAgent="data", sourceMode="pipeline", afterTask="2.33"))
    eng.add_findings(st, task["id"], [TaskFinding(
        text=f"Statistical screening done across {len(model_objects(st))} model objects; "
        f"{len(drop_candidates)} variable(s) flagged to drop/downweight.",
        tone="flag" if drop_candidates else "info",
        evidence=[EvidenceRef(artifactId="a-stat-tests")])])


def _nan_mean(xs: list[float]) -> float:
    return float(np.mean(xs)) if xs else float("nan")


def _fmt(v: float, suffix: str = "") -> str:
    return "" if v != v else f"{v:.2f}{suffix}"


def _fmt_range(rng: tuple[float, float] | None, suffix: str = "") -> str:
    return "—" if rng is None else f"{rng[0]:g}~{rng[1]:g}{suffix}"


async def pre_fit(eng: Engine, st: ProjectState, task: dict) -> None:
    """2.34 — quick OLS pre-fit, then select per-L4 metrics whose modeled
    contribution / ROI fit the KB ranges; warn factors with no viable metric."""
    from collections import defaultdict

    summary_rows: list[list[str]] = []
    prefit: dict[str, dict] = {}
    # candidates[l4][metric] = {contribs, rois}
    cand: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"contribs": [], "rois": []}))
    for obj in model_objects(st):
        try:
            res = run_mmm(model_df(st), obj, adstock=0.5, hill_half=1.0)
        except Exception as e:  # noqa: BLE001
            summary_rows.append([obj, "-", "-", "-", "-", f"error: {e}"[:40]])
            continue
        summary_rows.append([obj, str(res.n_obs), str(len(res.drivers)), f"{res.r2:.2f}",
                             f"{res.mape:.1f}%", "✓" if not res.red_flags else f"{len(res.red_flags)} flags"])
        prefit[obj] = {"r2": res.r2, "mape": res.mape, "baseline_pct": res.baseline_pct,
                       "red_flags": res.red_flags}
        dmeta = res.meta.get("drivers_meta", {}) if isinstance(res.meta, dict) else {}
        for d in res.drivers:
            meta = dmeta.get(d, {})
            l4 = (meta.get("l4") or meta.get("l3") or meta.get("l1") or "").strip()
            metric = meta.get("metric") or d
            if not l4:
                continue
            entry = cand[l4][metric]
            if d in res.contribution:
                entry["contribs"].append(res.contribution[d])
            if d in res.roi:
                entry["rois"].append(res.roi[d])

    # Per-L4 selection against the KB ranges.
    sel_rows: list[list[str]] = []
    selected: dict[str, dict] = {}
    warnings: list[str] = []
    for l4, metrics in cand.items():
        rng = data_rules.match_factor_range(l4)
        scored = []
        for metric, e in metrics.items():
            contrib = _nan_mean(e["contribs"])
            roi = _nan_mean(e["rois"])
            r_ok = rng is not None and data_rules.in_range(roi, rng.roi)
            c_ok = rng is not None and data_rules.in_range(contrib, rng.contribution)
            mag = abs(contrib) if contrib == contrib else 0.0
            scored.append(((int(r_ok) + int(c_ok), mag), metric, contrib, roi, c_ok, r_ok))
        scored.sort(key=lambda t: t[0], reverse=True)
        _, sel_metric, contrib, roi, c_ok, r_ok = scored[0]
        # ROI is the comparable check (a ratio). The KB contribution range is a
        # whole-business *yearly* share, not comparable to a per-object pre-fit
        # share, so it only informs ranking — never an out-of-range warning.
        if rng is None:
            verdict = "无基准"
        elif rng.roi is not None:
            if roi != roi:
                verdict = "无ROI数据"
            elif r_ok:
                verdict = "在区间"
            else:
                verdict = "ROI超区间·复核"
                warnings.append(f"{l4}·{sel_metric}")
        else:
            verdict = "参考"  # baseline factor: contribution-only, advisory
        selected[l4] = {"metric": sel_metric,
                        "contribution": None if contrib != contrib else round(contrib, 2),
                        "roi": None if roi != roi else round(roi, 3),
                        "in_range": verdict == "在区间", "candidates": len(metrics)}
        sel_rows.append([l4, sel_metric, _fmt(contrib, "%"),
                         _fmt_range(rng.contribution if rng else None, "%"),
                         _fmt(roi), _fmt_range(rng.roi if rng else None),
                         str(len(metrics)), verdict])

    # Accepted L4 factors with no usable driver → warn.
    accepted_l4 = st.analysis.get("factor_l4") or []
    for l4 in accepted_l4:
        if l4 and l4 not in cand:
            sel_rows.append([l4, "—", "—", "—", "—", "—", "0", "无可用指标·预警"])
            warnings.append(f"{l4}: 无可用指标")

    sel_rows.sort(key=lambda r: r[7])
    body = {"sheets": [
        {"name": "指标筛选", "columns": ["L4 因子", "选定指标", "预检贡献%", "KB贡献区间",
                                      "预检ROI", "KB ROI区间", "候选数", "判定"], "rows": sel_rows},
        {"name": "模型对象", "columns": ["对象", "行", "列", "预检 R²", "MAPE", "预检"], "rows": summary_rows},
    ]}
    eng.produce(st, "a-model-input", body=body, state="confirmed", agent="data")
    eng.set_analysis(st, "prefit", prefit)
    eng.set_analysis(st, "selected_metrics", selected)
    eng.set_analysis(st, "selection_warnings", warnings[:20])

    benchmarked = sum(1 for r in sel_rows if r[7] not in ("无基准", "无可用指标·预警"))
    findings = [TaskFinding(
        text=f"指标筛选完成：{len(selected)} 个 L4 因子选定指标，{benchmarked} 个有 KB ROI/贡献区间基准"
        f"（其余为无基准——本案模型对象为渠道层，驱动多为 Trade 因子，KB 区间主要覆盖媒体/基线因子），"
        f"{len(warnings)} 项需复核/预警。",
        tone="flag" if warnings else "info", evidence=[EvidenceRef(artifactId="a-model-input")])]
    flagged = [o for o, v in prefit.items() if v.get("red_flags")]
    if flagged:
        findings.append(TaskFinding(text=f"Pre-fit red flags on: {', '.join(flagged)}.",
                                    tone="flag", evidence=[EvidenceRef(artifactId="a-model-input")]))
    eng.add_findings(st, task["id"], findings)
    # G2.34 — make the selection-confirmation question reflect real warnings.
    dec = task.get("decision")
    if dec and dec["id"] in st.decisions and warnings:
        st.decisions[dec["id"]].question = (
            f"{len(warnings)} 个因子的预检贡献/ROI 超出业务区间或无可用指标（如 {warnings[0]}）。"
            "确认指标选型，还是回到 2.31 重做业务假设？"
        )
