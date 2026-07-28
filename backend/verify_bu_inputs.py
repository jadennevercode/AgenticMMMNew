"""Manual verification: upload the fabricated run-materials inputs to the
danone-mizone project, run the S1 (Business Understanding) chain live, and dump
the key outputs so we can confirm they are derived from the INPUTS (not the
reference case).

Run:  .venv/bin/python verify_bu_inputs.py
Needs: VOLCANO_API_KEY in .env (S1 handlers call the LLM).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.agents.registry import build_engine
from app.domain import blueprint as bp
from app.orchestrator.runner import _recommended_option, ensure_recommendation
from app.store.files import get_files
from app.store.state import get_store

KIT = Path(__file__).resolve().parent.parent / "run-materials"
CATEGORY_DIRS = {
    "project_background": "1_project_background",
    "industry_reference": "2_industry_reference",
    "interview_minutes": "3_interview_minutes",
}
PID = "danone-mizone"


def upload_kit() -> None:
    files = get_files()
    files.purge(PID)  # clear any prior uploads (does not touch the state json)
    for category, sub in CATEGORY_DIRS.items():
        d = KIT / sub
        for f in sorted(d.glob("*")):
            if f.is_file() and not f.name.startswith("_"):
                rec = files.add(PID, category, f.name, f.read_bytes())
                print(f"  + [{category}] {f.name}  parsed={rec.parsed} chars={rec.parse_chars}")


async def run_s1(eng, st) -> None:
    """Replicate the autopilot loop but stop at the S1/S2 boundary."""
    steps = 0
    while steps < 200:
        steps += 1
        for d in [d for d in st.decisions.values() if d.status == "open"]:
            await ensure_recommendation(eng, st, d.id)
        acted = False
        for t in bp.TASKS:
            if t["stage"] != "s1":
                continue
            if "assignment" in t and st.assignments[t["assignment"]["id"]].status == "open":
                eng.submit_assignment(st, t["assignment"]["id"], note="auto: uploaded kit")
                acted = True
            if "decision" in t and st.decisions[t["decision"]["id"]].status == "open":
                eng.resolve_decision(st, t["decision"]["id"], _recommended_option(t), note="auto")
                acted = True
        if acted:
            continue
        task = eng.next_actionable(st)
        if task is None or task["stage"] != "s1":
            break
        print(f"  · running {task['id']} {task['name']}")
        await eng.run_task(st, task)


def dump(st) -> None:
    print("\n================ OUTPUTS ================\n")
    p = st.profile
    print("### a-scope / Project Profile")
    if p:
        print("  sourceOrigin :", p.source_origin)
        print("  timeGranularity:", p.time_granularity)
        print("  intro        :", p.project_intro[:200])
        print("  dimensions   :", [(d.name, d.values) for d in p.model_scope.dimensions])
        print("  scope rows   :", len(p.model_scope.rows))
        for r in p.model_scope.rows[:12]:
            print("     ", r)
    ft = st.factor_tree
    print("\n### a-factor-tree")
    if ft:
        base = [r for r in ft.rows if r.source == "template"]
        ai = [r for r in ft.rows if r.source == "ai"]
        iv = [r for r in ft.rows if r.source == "interview"]
        print(f"  rows: {len(ft.rows)}  (template={len(base)}, ai={len(ai)}, interview={len(iv)})")
        for r in (ai + iv)[:12]:
            print(f"     [{r.source}/{r.status}] {r.l3}/{r.l4} — {r.indicator}  :: {r.rationale[:60]}")
    print("\n### a-interview (writeback proposals on factor tree)")
    props = [p for p in st.proposals if p.after_task == "1.4"]
    for pr in props[:10]:
        print(f"     {pr.title}  :: {pr.summary[:70]}")
    print("\n### a-data-request sheets")
    req = st.artifact("a-data-request")
    if req and req.body:
        print("   ", [s["name"] for s in req.body.get("sheets", [])])
    print("\n### artifacts produced in S1:",
          [a.id for a in st.artifacts if a.stage == "s1"])


async def main() -> None:
    store = get_store()
    print("== reset danone-mizone ==")
    st = store.reset(PID)
    print("== upload kit ==")
    upload_kit()
    print("== run S1 ==")
    eng = build_engine()
    await run_s1(eng, st)
    store.save(PID)
    dump(st)


if __name__ == "__main__":
    asyncio.run(main())
