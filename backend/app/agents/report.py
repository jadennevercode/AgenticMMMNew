"""S5 Report Agent handlers — decomposition / ROI tables and the final narrative.

Uses the REAL picked-model results (from the 3.4 decision → candidate index)
to build decomposition and ROI; the LLM only writes the narrative around the
real numbers.
"""
from __future__ import annotations

from app.agents.common import agent_system, artifact_text, llm_body
from app.agents.result_charts import results_review
from app.domain.models import EvidenceRef, TaskFinding
from app.orchestrator.engine import Engine
from app.store.state import ProjectState

SYS = agent_system("report")


def _picked_index(st: ProjectState) -> int:
    res = st.decisions.get("d-3.4")
    if res and res.resolution:
        opt = res.resolution.get("optionId", "cand-b")
        return {"cand-a": 0, "cand-b": 1, "cand-c": 2}.get(opt, 1)
    return 1


async def build_tables(eng: Engine, st: ProjectState, task: dict) -> None:
    candidates = st.analysis.get("candidates", {})
    idx = _picked_index(st)
    decomp_rows: list[list[str]] = []
    roi_rows: list[list[str]] = []
    picked: dict[str, dict] = {}
    for obj, cands in candidates.items():
        if not cands:
            continue
        c = cands[idx] if idx < len(cands) else cands[0]
        picked[obj] = c
        decomp_rows.append([obj, f"{c['baseline_pct']:.1f}%",
                            "; ".join(f"{k}:{v:.0f}%" for k, v in list(c["contribution"].items())[:4])])
        for ch, roi in list(c["roi"].items())[:6]:
            roi_rows.append([obj, ch[:30], f"{roi:+.2f}"])
    eng.set_analysis(st, "picked", picked)
    body = {"sheets": [
        {"name": "Decomp CHART", "columns": ["对象", "基线占比", "Top 贡献因子"], "rows": decomp_rows},
        {"name": "ROI", "columns": ["对象", "渠道/驱动", "ROI"], "rows": roi_rows},
        {"name": "技术检验", "columns": ["对象", "R²", "MAPE", "Baseline"],
         "rows": [[o, f"{c['r2']:.2f}", f"{c['mape']:.1f}%", f"{c['baseline_pct']:.1f}%"]
                  for o, c in picked.items()]},
    ]}
    eng.produce(st, "a-decomp-results", body=body, state="confirmed", agent="report")

    # Visual results dashboard: contribution, ROI, response curves and the
    # Due-to growth-attribution waterfall — all from the picked model's numbers.
    dash = results_review(picked)
    if dash["steps"]:
        eng.produce(st, "a-results-dashboard", body=dash, state="confirmed", agent="report")

    eng.add_findings(st, task["id"], [TaskFinding(
        text=f"Decomposition & ROI built for {len(picked)} model objects from the picked candidate.",
        evidence=[EvidenceRef(artifactId="a-decomp-results"), EvidenceRef(artifactId="a-results-dashboard")])])


async def write_narrative(eng: Engine, st: ProjectState, task: dict) -> None:
    picked = st.analysis.get("picked", {})
    summary = "; ".join(
        f"{o}: R²={c['r2']:.2f}, baseline={c['baseline_pct']:.0f}%, "
        f"top={'/'.join(list(c['contribution'])[:2])}"
        for o, c in picked.items()
    )
    ctx = artifact_text(st, ["a-decomp-results", "a-factor-tree"])
    body = await llm_body(
        SYS,
        "Write the final MMM report as a slide deck (slides with title + bullets) for the Mizone case, "
        "grounded ONLY in the real model results below. Every quantitative claim must use a real number "
        f"from the results. Cover: executive summary, contribution decomposition, ROI by channel, key "
        "business answers, and stated limitations (e.g. negative baselines or red flags where present). "
        f"REAL RESULTS: {summary}\n\n" + ctx,
        "slides",
    )
    eng.produce(st, "a-final-report", body=body, state="proposed", agent="report")
    flags = [o for o, c in picked.items() if c.get("red_flags")]
    eng.add_findings(st, task["id"], [TaskFinding(
        text="Final narrative drafted from real results."
        + (f" Limitations stated for: {', '.join(flags)}." if flags else ""),
        tone="flag" if flags else "info", evidence=[EvidenceRef(artifactId="a-final-report")])])
