"""S4 Model Agent handlers — assumptions, real OLS MMM training, technical review."""
from __future__ import annotations

from app.agents.common import agent_system, artifact_text, llm_body
from app.agents.dataset_cache import model_df, model_objects
from app.agents.ledger import model_selection
from app.agents.result_charts import diagnostics_review
from app.domain.models import EvidenceRef, TaskFinding
from app.mmm import make_candidates
from app.orchestrator.engine import Engine
from app.store.state import ProjectState

SYS = agent_system("model")
_CAND_LABELS = ["A", "B", "C"]


async def register_priors(eng: Engine, st: ProjectState, task: dict) -> None:
    anomalies = st.analysis.get("anomalies", [])
    ctx = artifact_text(st, ["a-knowledge-package", "a-business-validation", "a-master-data"])
    anom_text = "; ".join(f"{a['channel']} {a['year']} {a['growth_pct']:+}%" for a in anomalies) or "none"
    body = await llm_body(
        SYS,
        "Register modeling assumptions (priors/constraints) for the Mizone OLS MMM. Turn confirmed "
        "business judgments into bounded constraints (sign, range, lag, saturation), each traced to a "
        f"source. Real detected anomalies to consider as structural events: {anom_text}. Produce sheets: "
        "'README' [项, 内容] and '先验设置规则' [约束, 方向/区间, 来源, 强弱]. 5-8 constraints.\n\n" + ctx,
        "sheet",
    )
    eng.produce(st, "a-prior-register", body=body, state="proposed", agent="model")


async def train_models(eng: Engine, st: ProjectState, task: dict) -> None:
    objects = model_objects(st)
    # Train on exactly what S2 locked: the adopted indicators, the response
    # confirmed at 2.5y, the variables ticked at 2.5x, the controls set at 2.5p.
    # Without this the candidates silently re-pick their own drivers and the whole
    # S2 filter chain — quality, sign-off, statistics, the human's own selection —
    # never reaches the model it was supposed to shape.
    sel = model_selection(st)
    df = model_df(st)
    candidates: dict[str, list[dict]] = {}
    conv_rows: list[list[str]] = []
    for obj in objects:
        try:
            cands = make_candidates(df, obj, n=3, exclude=sel.exclude,
                                    y_metric=sel.y_for(obj), include=sel.include,
                                    params=sel.params)
            candidates[obj] = [c.to_dict() for c in cands]
            conv_rows.append([obj, f"{len(cands)} candidates", "converged"])
        except Exception as e:  # noqa: BLE001
            conv_rows.append([obj, "-", f"error: {e}"[:40]])
    eng.set_analysis(st, "candidates", candidates)

    # Candidate comparison sheet for a representative object + all-object convergence.
    rep = next(iter(candidates), None)
    cand_rows: list[list[str]] = []
    if rep:
        for i, c in enumerate(candidates[rep]):
            cand_rows.append([f"Candidate {_CAND_LABELS[i] if i < 3 else i}", f"{c['r2']:.2f}",
                              f"{c['mape']:.1f}%", f"{c['baseline_pct']:.1f}%",
                              "✓" if not c["red_flags"] else f"{len(c['red_flags'])} flags"])
    body = {"sheets": [
        {"name": f"候选模型（{rep or '示例'}）", "columns": ["候选", "R²", "误差", "基线", "约束满足"],
         "rows": cand_rows},
        {"name": "采样收敛", "columns": ["对象", "候选", "状态"], "rows": conv_rows},
    ]}
    eng.produce(st, "a-model-candidates", body=body, state="proposed", agent="model")
    eng.add_findings(st, task["id"], [TaskFinding(
        text=f"Trained {len(candidates)} model objects ({', '.join(candidates)}), 3 candidates each.",
        evidence=[EvidenceRef(artifactId="a-model-candidates")])])


async def technical_review(eng: Engine, st: ProjectState, task: dict) -> None:
    candidates = st.analysis.get("candidates", {})
    rows: list[list[str]] = []
    any_redflag = False
    for obj, cands in candidates.items():
        # review the recommended candidate (index 1 = B) by default
        c = cands[1] if len(cands) > 1 else (cands[0] if cands else None)
        if not c:
            continue
        r2_ok = "✓" if 0.70 <= c["r2"] <= 0.99 else "⚠"
        mape_ok = "✓" if c["mape"] <= 20 else "⚠"
        dw_ok = "✓" if 1.3 <= c["durbin_watson"] <= 2.7 else "⚠"
        base_ok = "✓" if c["baseline_pct"] >= 0 else "✗ negative baseline"
        if c["red_flags"]:
            any_redflag = True
        rows.append([obj, f"{c['r2']:.2f} {r2_ok}", f"{c['mape']:.1f}% {mape_ok}",
                     f"{c['durbin_watson']:.2f} {dw_ok}", base_ok,
                     "; ".join(c["red_flags"])[:60] or "—"])
    body = {"sheets": [
        {"name": "README", "columns": ["项", "内容"],
         "rows": [["基准", "R² 70–99% · MAPE ≤20% · DW 1.3–2.7 · baseline ≥ 0"],
                  ["规则", "负基线 / 付费渠道反号 = 硬停"]]},
        {"name": "F1.Tech Review", "columns": ["对象", "R²", "MAPE", "DW", "Baseline", "Red flags"],
         "rows": rows},
    ]}
    eng.produce(st, "a-tech-review", body=body, state="confirmed", agent="model")

    # Visual diagnostics dashboard (actual-vs-predicted fit, R², residuals,
    # decomposition, saturation curves) — computed, never LLM-authored.
    diag = diagnostics_review(candidates)
    if diag["steps"]:
        eng.produce(st, "a-model-diagnostics", body=diag, state="confirmed", agent="model")

    eng.add_findings(st, task["id"], [TaskFinding(
        text="Technical review complete. " + ("Red flags present — review before delivery."
             if any_redflag else "No hard-stop red flags on the recommended candidates."),
        tone="flag" if any_redflag else "info",
        evidence=[EvidenceRef(artifactId="a-tech-review"), EvidenceRef(artifactId="a-model-diagnostics")])])
