"""Reconstruct the Danone/Mizone master dataset (2.24 workbook) as 37 Data-Engine
data assets — one per Task name — each built through a REAL dbt pipeline and
published, so the S2 "2.1 Data Processing" gate resolves via a fully-grounded
FactorTree↔DataAssets mapping (no reference-dataset fallback, no per-L3 upload).

The 2.24 workbook is already the FINAL unioned long table (19 columns matching
the project's target schema exactly). This script un-unions it back into its
source tasks, publishes each through the Data Engine, derives the FactorTree
from the same data, and drives the project to task 2.1.

Run from the backend venv:
    PYTHONPATH=. .venv/bin/python scripts/seed_dataprocess_demo.py [--limit N]

--limit N restricts to the first N task names (by row count, descending) for a
quick spike run before committing to the full 37.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents import business  # noqa: E402
from app.agents.registry import build_engine  # noqa: E402
from app.dataeng import assets as asset_svc  # noqa: E402
from app.dataeng.dbt import service as dbt_service  # noqa: E402
from app.dataeng.dbt.service import DbtServiceError  # noqa: E402
from app.dataeng.mapping import resolve_factor_map  # noqa: E402
from app.domain import blueprint as bp  # noqa: E402
from app.domain.models import (  # noqa: E402
    FactorRow,
    FactorTree,
    FieldMapEntry,
    IndustryRef,
    ModelScope,
    ModelScopeDimension,
    ProjectProfile,
    TransformPipeline,
    TransformStep,
)
from app.ingest.dataset import COLUMN_NAMES  # noqa: E402
from app.store.files import get_files  # noqa: E402
from app.store.state import get_store  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
MASTER_XLSX = (REPO_ROOT / "reference" / "02.数据智能体"
               / "【MMM AI】数据智能体-Data Process_2.24.xlsx")

PROJECT_NAME = "Mizone Data-Process Demo"

# S1 tasks bypassed straight to "done" — deterministic seeding, no LLM. 2.1 only
# depends on 1.7, but marking the whole chain done keeps the task list coherent.
S1_TASK_IDS = [
    "1.0a", "1.0", "1.1a", "1.1", "1.21", "1.21d",
    "1.3", "1.3b", "1.4a", "1.4b", "1.4", "1.4d", "1.5", "1.5d", "1.7",
]

_INT_COLS = ("year", "month")


def _safe_ident(name: str) -> str:
    name = re.sub(r"[^\w一-鿿-]+", "_", str(name)).strip("_")
    return name or "task"


def load_master() -> pd.DataFrame:
    """Parse the 2.24 workbook and normalise it into the 19-column target schema,
    replacing the raw METRICS类型 unit column with a derived Y/spending/X role
    (the target schema's `metric_type` is a modeling ROLE, not a unit)."""
    raw = pd.read_excel(MASTER_XLSX, sheet_name=0)
    if raw.shape[1] != len(COLUMN_NAMES):
        raise SystemExit(f"expected {len(COLUMN_NAMES)} columns, got {raw.shape[1]}")
    raw.columns = COLUMN_NAMES

    df = raw.copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    before = len(df)
    df = df.dropna(subset=["value"]).reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        print(f"  dropped {dropped} row(s) with non-numeric value")

    for c in _INT_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")

    for c in COLUMN_NAMES:
        if c not in ("year", "month", "value"):
            df[c] = df[c].fillna("").astype(str).str.strip()

    # metric_type = modeling ROLE (Y/spending/X), derived from the factor-tree L1
    # bucket — Baseline Factor = context driver, Marketing/Commercial Factor =
    # ROI-eligible spend, KPI = the response. Overwrites the raw unit column.
    conditions = [df["l1"] == "KPI", df["l1"].isin(["Marketing Factor", "Commercial Factor"])]
    choices = ["Y", "spending"]
    df["metric_type"] = np.select(conditions, choices, default="X")
    return df[COLUMN_NAMES]


def build_factor_tree(df: pd.DataFrame) -> FactorTree:
    """One accepted FactorRow per distinct (l1, l2, l3, l4, metric) — the exact
    coverage target the 2.1 gate's mapping_complete() checks against."""
    paths = (df[["l1", "l2", "l3", "l4", "metric"]]
             .drop_duplicates().sort_values(["l1", "l2", "l3", "l4", "metric"]))
    rows = [
        FactorRow(
            id=f"fr-{i:03d}", l1=r.l1, l2=r.l2, l3=r.l3, l4=r.l4, indicator=r.metric,
            dimension="brand, province_group, channel_type, channel",
            source="upload", status="accepted",
            rationale="Derived from the unified master dataset (2.24 workbook).",
        )
        for i, r in enumerate(paths.itertuples(index=False), start=1)
    ]
    return FactorTree(rows=rows)


def _cast_for(col: str) -> str:
    if col in _INT_COLS:
        return "integer"
    if col == "value":
        return "double"
    return ""


def identity_pipeline() -> TransformPipeline:
    """One field_map step: the raw CSV's columns already ARE the target schema's
    columns (this is the whole point — un-unioning an already-final table), so the
    pipeline documents that mapping 1:1 rather than inventing transforms."""
    step = TransformStep(
        id="step_map", kind="field_map", name="Map to target schema",
        note="Source columns already match the target schema — identity map with type casts.",
        inputs=["source:raw"],
        field_map=[FieldMapEntry(source=c, target=c, cast=_cast_for(c)) for c in COLUMN_NAMES],
    )
    return TransformPipeline(steps=[step], outputStep=step.id,
                             note="Reconstructed from the 2.24 master dataset.")


def seed_s1(st) -> None:
    """Deterministically mark S1 done (no LLM) so 2.1 (depends_on 1.7) is reachable."""
    for tid in S1_TASK_IDS:
        rt = st.tasks[tid]
        rt.status, rt.progress, rt.started_tick, rt.finished_tick, rt.runs = "done", 100.0, 0, 0, 1
        tdef = bp.TASK_MAP[tid]
        if "decision" in tdef:
            d = st.decisions[tdef["decision"]["id"]]
            d.status, d.resolution = "resolved", {"optionId": "accept", "note": "seeded"}
        if "assignment" in tdef:
            a = st.assignments[tdef["assignment"]["id"]]
            a.status, a.note = "submitted", "seeded"
    st.factor_tree_source = "upload"
    business_engine_produce_placeholder(st)


def business_engine_produce_placeholder(st) -> None:
    """Produce the one S1 artifact that materially matters downstream — the
    factor-tree sheet — using the project's real render function so the UI shows
    the actual derived tree, not a stub."""
    eng = build_engine()
    eng.produce(st, "a-factor-tree", body=business._factor_tree_sheet(st.factor_tree),
                state="confirmed", agent="business")


def publish_task_asset(pid: str, st, task_name: str, task_df: pd.DataFrame) -> tuple[bool, str]:
    """Create, build and publish one Data-Engine asset for a single Task name.
    Returns (published_ok, error_message)."""
    files = get_files()
    buf = io.StringIO()
    task_df.to_csv(buf, index=False)
    record = files.add(pid, "raw_data", f"{_safe_ident(task_name)}.csv",
                       buf.getvalue().encode("utf-8"), content_type="text/csv")

    asset = asset_svc.create_asset(
        st, name=task_name,
        description=f"Reconstructed from the 2.24 master dataset — Task '{task_name}'.",
        source_file_ids=[record.id],
    )
    asset.pipeline = identity_pipeline()

    try:
        summary = dbt_service.build(st, pid, asset)
        if not summary.ok:
            return False, summary.error or "dbt build failed"
        if summary.conformance is not None and not summary.conformance.ok:
            missing = ", ".join(summary.conformance.missing_required)
            return False, f"schema conformance failed (missing: {missing})" if missing else "schema conformance failed"
        dbt_service.publish(pid, st, asset)
        return True, ""
    except DbtServiceError as e:
        return False, str(e)


async def drive_to_data_processing(st) -> None:
    """Run the real orchestrator path for task 2.1 — same code the interactive
    and autopilot flows use — so the demo state is indistinguishable from one
    reached through the UI."""
    eng = build_engine()
    eng._promote_ready(st)
    if st.tasks["2.1"].status != "ready":
        raise SystemExit(f"task 2.1 not ready — status={st.tasks['2.1'].status} "
                         f"(check 1.7={st.tasks['1.7'].status})")
    await eng.run_task(st, bp.TASK_MAP["2.1"])
    ok = await eng.submit_assignment(st, "in-2.1")
    if not ok:
        raise SystemExit("submit_assignment(in-2.1) returned False — gate still blocked")
    if st.tasks["2.1"].status != "done":
        raise SystemExit(f"task 2.1 did not finish — status={st.tasks['2.1'].status}")


def print_verification(pid: str, st) -> None:
    from app.agents.dataset_cache import model_df
    from app.agents.data_request import build_manifest

    fmap = resolve_factor_map(st)
    manifest = build_manifest(st)
    published = [a for a in st.data_assets if a.status == "published"]
    df = model_df(st)

    print("\n=== verification ===")
    print(f"published assets   : {len(published)} / {len(st.data_assets)}")
    print(f"factor-tree rows    : total={fmap.total} mapped={fmap.mapped} "
         f"ignored={fmap.ignored} pending={fmap.pending}")
    print(f"mapping_complete()  : {fmap.complete}")
    print(f"manifest L3 slots   : {manifest.validated} / {manifest.total} validated")
    print(f"model_df row count  : {len(df):,}")
    print(f"task 2.1 status     : {st.tasks['2.1'].status}")
    print(f"task 2.2 status     : {st.tasks['2.2'].status}")
    if fmap.pending:
        print("PENDING rows (unexpected):")
        for r in fmap.rows:
            if r.status == "pending":
                print(f"  - {r.l1}/{r.l2}/{r.l3}/{r.l4} :: {r.indicator}")
    if st.factor_map_ignores:
        print("Ignored rows (data-quality gate rejected the covering asset):")
        for rid, note in st.factor_map_ignores.items():
            row = next((r for r in st.factor_tree.rows if r.id == rid), None)
            label = f"{row.l3}/{row.l4} :: {row.indicator}" if row else rid
            print(f"  - {label} — {note}")


def find_or_create_project(store) -> str:
    """Idempotent: reuse a prior run's project (matched by name) via reset(),
    else create fresh. Returns the project id (store.create() owns id slugging)."""
    existing = next((m for m in store.list_meta() if m.name == PROJECT_NAME), None)
    if existing is not None:
        store.reset(existing.id)
        return existing.id
    meta = store.create(PROJECT_NAME, "Mizone",
                        IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional"),
                        kpi="Sell-out Volume")
    return meta.id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="only process the first N task names (spike run)")
    args = ap.parse_args()

    print(f"Loading master dataset from {MASTER_XLSX} ...")
    df = load_master()
    print(f"  {len(df):,} rows, {df['task_name'].nunique()} distinct task names")

    store = get_store()
    project_id = find_or_create_project(store)
    st = store.get(project_id)
    print(f"Project: {project_id}")

    st.profile = ProjectProfile(
        projectIntro="Mizone (NAB) national MMM — reconstructed from the unified "
                     "master modeling dataset (2.24) to demo the Data-Engine → "
                     "Data-Processing path end to end.",
        timeGranularity="Month",
        modelScope=ModelScope(
            dimensions=[
                ModelScopeDimension(name="Brand", values=sorted(df["brand"].unique().tolist())),
                ModelScopeDimension(name="Channel type", values=sorted(v for v in df["channel_type"].unique() if v)),
            ],
            rows=[],
        ),
        sourceOrigin="uploaded files",
    )

    print("Building FactorTree from the master data's L1-L4 + metric paths ...")
    st.factor_tree = build_factor_tree(df)
    print(f"  {len(st.factor_tree.rows)} accepted factor rows")

    print("Seeding S1 to done (deterministic, no LLM) ...")
    seed_s1(st)
    store.save(project_id)

    task_names = (df.groupby("task_name").size().sort_values(ascending=False).index.tolist())
    if args.limit:
        task_names = task_names[: args.limit]
    print(f"\nPublishing {len(task_names)} Data-Engine asset(s) ...")

    failures: list[tuple[str, str]] = []
    for i, task_name in enumerate(task_names, start=1):
        task_df = df[df["task_name"] == task_name]
        ok, err = publish_task_asset(project_id, st, task_name, task_df)
        tag = "OK" if ok else "FAIL"
        print(f"  [{i:2d}/{len(task_names)}] {task_name:42s} {len(task_df):5d} rows  {tag}"
             + (f" — {err}" if err else ""))
        if not ok:
            failures.append((task_name, err))
        store.save(project_id)

    if failures:
        print(f"\n{len(failures)} asset(s) failed to publish — marking their unique "
             "factor rows 'ignored' (a real data-quality outcome, not a script bug):")
        fmap = resolve_factor_map(st)
        by_l3l4metric = {(r.l1, r.l2, r.l3, r.l4, r.indicator): r for r in st.factor_tree.rows}
        for task_name, err in failures:
            task_df = df[df["task_name"] == task_name]
            paths = task_df[["l1", "l2", "l3", "l4", "metric"]].drop_duplicates()
            for p in paths.itertuples(index=False):
                row = by_l3l4metric.get((p.l1, p.l2, p.l3, p.l4, p.metric))
                if row is None:
                    continue
                still_pending = next((r for r in fmap.rows if r.row_id == row.id and r.status == "pending"), None)
                if still_pending is not None:
                    st.factor_map_ignores[row.id] = f"'{task_name}' failed dbt build/tests: {err}"
                    print(f"  - {row.l3}/{row.l4} :: {row.indicator} <- ignored ({task_name})")
        store.save(project_id)

    print("\nDriving project to task 2.1 (Data Processing) ...")
    asyncio.run(drive_to_data_processing(st))
    store.save(project_id)

    print_verification(project_id, st)


if __name__ == "__main__":
    main()
