"""Drive the drill project through S2 and report what actually survived each layer.

Run after ``verify_dataeng_drill.py`` has published the five assets. This is the
half the guide walks through by hand (2.1 → 2.6); running it in autopilot first is
how we find out whether the guide is asking for something achievable.

What it checks is not "did it finish" but "is the chain coherent":

* every model object carries both a response and drivers, and the national media
  that belongs to no channel reached all of them;
* the indicator ledger's layers inherit — a rejection at 2.2 is still a rejection
  at 2.5, and nothing rejected reappears downstream;
* the factor tree closes out at 2.6 with every active row accounted for.

    PYTHONPATH=. .venv/bin/python scripts/verify_s2_drill.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from scripts.make_dataeng_drill import PROJECT_ID


def report_mapping(st) -> None:
    from app.dataeng.mapping import resolve_factor_map

    fmap = resolve_factor_map(st)
    print("\n=== 2.1 factor map ===")
    print(f"  {fmap.total} active rows  ·  mapped={fmap.mapped} "
          f"ignored={fmap.ignored} pending={fmap.pending}  ·  complete={fmap.complete}")


def report_objects(st) -> None:
    from app.agents.dataset_cache import model_df
    from app.agents.model_objects import (
        enumerate_objects, object_label, object_mask, skipped_objects)

    df = model_df(st)
    print("\n=== model objects (channel × brand) ===")
    for obj in enumerate_objects(df, st):
        sub = df[object_mask(df, obj, st)]
        drivers = sub[sub["metric_type"] != "Y"][["l4", "metric"]].drop_duplicates()
        # National rows carry no channel at all; if they did not reach this object
        # the fit is missing most of its media.
        national = sub[sub["channel_type"].astype(str).str.strip() == ""]
        nat_metrics = national[["l4", "metric"]].drop_duplicates()
        print(f"  {obj:22s} {object_label(obj):18s} rows={len(sub):5d} "
              f"drivers={len(drivers):3d}  of which national={len(nat_metrics)}")
    skipped = skipped_objects(df, st)
    if skipped:
        print(f"  skipped ({len(skipped)}): {skipped}")


def report_ledger(st) -> None:
    from app.agents.ledger import indicator_ledger, model_selection

    ledger = indicator_ledger(st)
    print("\n=== indicator ledger ===")
    print(f"  {len(ledger)} rows (indicator × model object)")
    adopted = sum(1 for r in ledger if r.adopted)
    by_layer: dict[str, int] = {}
    for r in ledger:
        if not r.adopted:
            by_layer[r.rejected_at or "?"] = by_layer.get(r.rejected_at or "?", 0) + 1
    print(f"  adopted={adopted}  rejected={len(ledger) - adopted}")
    if by_layer:
        print("  rejected at: " + "  ".join(f"{k}={v}" for k, v in sorted(by_layer.items())))

    sel = model_selection(st)
    print("\n  resolved selection, per object:")
    for obj in sorted(set(sel.exclude) | set(sel.include) | set(sel.y)):
        inc = sel.include_for(obj)
        print(f"    {obj:22s} y={sel.y_for(obj)!r} "
              f"include={'auto' if inc is None else len(inc)} "
              f"exclude={len(sel.exclude_for(obj))}")


def report_ols(st) -> None:
    art = next((a for a in st.artifacts if a.id == "a-ols-test"), None)
    if art is None:
        print("\n=== 2.5 OLS ===\n  a-ols-test not produced")
        return
    body = art.body if isinstance(art.body, dict) else {}
    objects = body.get("objects") or []
    tree = body.get("tree") or []
    print(f"\n=== 2.5 OLS ===\n  {len(objects)} model object(s), "
          f"{len(tree)} variable rows")
    for o in objects:
        if not isinstance(o, dict):
            continue
        err = o.get("error") or ""
        print(f"  {str(o.get('label')):18s} n={o.get('nObs'):<4} "
              f"drivers={o.get('drivers'):<3} r2={o.get('r2')} "
              f"df={o.get('dfRemaining')}" + (f"  ERROR: {err}" if err else ""))
        for flag in (o.get("redFlags") or [])[:4]:
            print(f"        ! {flag}")

    # A variable can only be in a model if some layer let it through; count the
    # ones that were dropped and by whom, so a mass drop is impossible to miss.
    dropped: dict[str, int] = {}
    in_model = 0
    for node in tree:
        if not isinstance(node, dict):
            continue
        if node.get("inModel"):
            in_model += 1
        else:
            dropped[str(node.get("droppedBy") or "?")] = (
                dropped.get(str(node.get("droppedBy") or "?"), 0) + 1)
    print(f"  in model: {in_model}  ·  dropped: "
          + ("  ".join(f"{k}={v}" for k, v in sorted(dropped.items())) or "none"))


def report_tree_closeout(st) -> None:
    from app.agents.factor_link import factor_tree_verdicts

    rows = factor_tree_verdicts(st)
    tally: dict[str, int] = {}
    for r in rows:
        v = str(r.get("verdict", "?"))
        tally[v] = tally.get(v, 0) + 1
    print("\n=== 2.6 factor-tree closeout ===")
    print(f"  {len(rows)} active factor rows  ·  "
          + "  ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    # The rows worth reading are the ones some layer actually kept or scored.
    # A dataless row that 2.1 ignored also lands in `rejected` (someone judged it),
    # so listing every rejection would just reprint the interview-derived tree.
    kept = [r for r in rows if r.get("verdict") in ("adopted", "partial")]
    print(f"  adopted / partial ({len(kept)}):")
    for r in kept:
        print(f"      {str(r.get('verdict')):8s} {r.get('l3')} > {r.get('l4')} "
              f"[{r.get('indicator')}]")
    late = [r for r in rows
            if r.get("verdict") == "rejected" and r.get("rejectedAt") != "mapping"]
    if late:
        print(f"  rejected after mapping ({len(late)}):")
        for r in late:
            print(f"      {r.get('l3')} > {r.get('l4')} [{r.get('indicator')}]  "
                  f"at {r.get('rejectedAt')}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", default=PROJECT_ID)
    ap.add_argument("--report-only", action="store_true",
                    help="skip the runner, just report the current state")
    args = ap.parse_args()

    from app.agents.registry import build_engine
    from app.orchestrator.runner import run_until_blocked
    from app.store.state import get_store

    store = get_store()
    st = store.get(args.project_id)
    if st is None:
        print(f"project {args.project_id} not found")
        return 1

    if not args.report_only:
        eng = build_engine()
        result = await run_until_blocked(
            eng, st, autopilot=True, save=lambda: store.save(args.project_id))
        store.save(args.project_id)
        print(f"=== runner: {result} ===")

    report_mapping(st)
    report_objects(st)
    report_ledger(st)
    report_ols(st)
    report_tree_closeout(st)

    done = sorted(t.id for t in st.tasks.values() if t.status == "done")
    stuck = sorted((t.id, t.status) for t in st.tasks.values() if t.status != "done")
    print(f"\n=== tasks ===\n  done ({len(done)}): {done}")
    print(f"  open: {stuck}")
    # findings are keyed by task id, not a flat list.
    flat = [(task_id, f) for task_id, items in st.findings.items() for f in items]
    if flat:
        print(f"\n=== findings ({len(flat)}) ===")
        for task_id, f in flat:
            print(f"  {task_id:6s} [{f.tone}] {f.text[:130]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
