"""Run the drill's Data Engine half end to end and check it against the truth table.

Applies the answer-key pipelines from ``drill_pipelines.py`` to the five seeded
assets, runs the real ``dbt build`` on each, publishes, and then compares every
published mart against ``_truth/truth_long_table.csv`` cell for cell. A guide that
tells someone to build these pipelines is only worth writing if this passes.

    PYTHONPATH=. .venv/bin/python scripts/verify_dataeng_drill.py
    PYTHONPATH=. .venv/bin/python scripts/verify_dataeng_drill.py --preview-only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

import scripts.drill_pipelines as P
from scripts.make_dataeng_drill import OUT_DIR, PROJECT_ID

KEYS = ["brand", "province_group", "channel_type", "year", "month",
        "l1", "l2", "l3", "l4", "metric_type", "metric"]

# asset display name → (pipeline builder, how many source tables it expects)
PIPELINES = {
    "01 销量": P.sales_pipeline,
    "02 品牌媒体": P.media_pipeline,
    "03 电商": P.ecom_pipeline,
    "04 线下促销周报": P.weekly_pipeline,
    "05 门店执行与外部因子": P.store_pipeline,
}


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Put both sides on the same key types before comparing.

    An all-empty dimension round-trips through CSV/parquet as NaN on one side and
    "" on the other, which would report every such row as a mismatch.
    """
    out = df.copy()
    for k in KEYS:
        if k in ("year", "month"):
            out[k] = pd.to_numeric(out[k]).astype(int)
        else:
            out[k] = out[k].astype("object").where(out[k].notna(), "").astype(str).str.strip()
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out


# asset display name → the raw-file prefixes it is built from. The prefixes are
# what the guide asks a person to group by hand in the Data Engine.
ASSET_SOURCES = {
    "01 销量": ("A1", "A2", "A3", "A4"),
    "02 品牌媒体": ("B_",),
    "03 电商": ("C_",),
    "04 线下促销周报": ("D_",),
    "05 门店执行与外部因子": ("E_",),
}


def ensure_assets(st, project_id: str) -> None:
    """Create the five assets over the uploaded raw files, if they aren't there."""
    from app.dataeng import assets as asset_svc
    from app.store.files import get_files

    raw = [f for f in get_files().list(project_id) if f.category == "raw_data"]
    if not raw:
        raise SystemExit(
            "no raw_data uploads — re-run make_dataeng_drill.py --with-raw-uploads")
    existing = {a.name for a in st.data_assets}
    for name, prefixes in ASSET_SOURCES.items():
        if name in existing:
            continue
        asset = asset_svc.create_asset(st, name=name, description="Data Engine drill")
        asset.source_file_ids = [f.id for f in raw if f.filename.startswith(prefixes)]
        print(f"    created {name:22s} ({len(asset.source_file_ids)} file(s))")


def build_pipelines(st, project_id: str) -> dict[str, str]:
    """Wire each asset's pipeline from its own source tables. Returns {asset: error}."""
    from app.dataeng.dbt import service

    errors: dict[str, str] = {}
    for asset in st.data_assets:
        builder = PIPELINES.get(asset.name)
        if builder is None:
            errors[asset.name] = "no answer-key pipeline for this asset"
            continue
        names = [meta.name for meta, _ in service.source_read(project_id, asset).pairs]
        try:
            asset.pipeline = builder(names)
        except (TypeError, StopIteration, IndexError) as exc:
            errors[asset.name] = (
                f"source tables {names} do not fit the pipeline: {type(exc).__name__}: {exc}")
    return errors


def run_preview(st, project_id: str) -> dict[str, str]:
    """Run each pipeline through the in-editor sandbox before touching dbt."""
    from app.dataeng import preview as preview_svc

    problems: dict[str, str] = {}
    for asset in st.data_assets:
        if not asset.pipeline.steps:
            continue
        try:
            res = preview_svc.preview_step(
                st, project_id, asset, asset.pipeline, asset.pipeline.output_step)
        except Exception as exc:  # noqa: BLE001 — surfacing whatever the sandbox raised
            problems[asset.name] = f"{type(exc).__name__}: {exc}"
            continue
        if not res.ok:
            problems[asset.name] = str(res.error)
        else:
            print(f"    preview {asset.name:22s} rows={res.row_count} "
                  f"cols={len(res.columns)}")
    return problems


def build_and_publish(st, project_id: str) -> dict[str, str]:
    from app.dataeng.dbt import service
    from app.store.state import get_store

    problems: dict[str, str] = {}
    for asset in st.data_assets:
        if not asset.pipeline.steps:
            continue
        summary = service.build(st, project_id, asset)
        conf = summary.conformance
        status = (f"models={summary.models} tests={summary.tests} "
                  f"passed={summary.passed} failed={summary.failed}")
        if not summary.ok:
            problems[asset.name] = f"dbt build failed — {summary.error[:400]}"
            print(f"    build   {asset.name:22s} FAILED  {status}")
            continue
        if conf and conf.checked and not conf.ok:
            problems[asset.name] = (
                f"schema conformance: missing={conf.missing_required} "
                f"violations={getattr(conf, 'violations', None)}")
        print(f"    build   {asset.name:22s} ok  {status}  "
              f"conformance={'ok' if conf and conf.ok else 'FAIL'}")
        service.publish(project_id, st, asset)
        get_store().save(project_id)
    return problems


def compare_to_truth(st, project_id: str) -> int:
    from app.dataeng import assets as asset_svc

    truth = pd.read_csv(OUT_DIR / "_truth" / "truth_long_table.csv").drop(columns=["group"])
    frames = asset_svc.published_frames(project_id, st)
    if not frames:
        print("\nNOTHING PUBLISHED — cannot compare")
        return 1
    built = pd.concat([f[[c for c in KEYS + ["value"] if c in f.columns]] for f in frames],
                      ignore_index=True)

    a = _normalise(truth).groupby(KEYS, as_index=False, dropna=False)["value"].sum().round(2)
    b = _normalise(built).groupby(KEYS, as_index=False, dropna=False)["value"].sum().round(2)
    merged = a.merge(b, on=KEYS, how="outer", suffixes=("_truth", "_built"), indicator=True)
    missing = merged[merged["_merge"] == "left_only"]
    extra = merged[merged["_merge"] == "right_only"]
    both = merged[merged["_merge"] == "both"]
    drift = both[(both["value_truth"] - both["value_built"]).abs() > 0.05]

    print(f"\n=== published vs truth ===")
    print(f"  truth rows   {len(a)}")
    print(f"  published    {len(b)}")
    print(f"  matched      {len(both)}")
    print(f"  missing      {len(missing)}")
    print(f"  invented     {len(extra)}")
    print(f"  value drift  {len(drift)}")
    for frame, label in ((missing, "MISSING"), (extra, "INVENTED"), (drift, "DRIFT")):
        if len(frame):
            print(f"\n  --- {label} (first 10) ---")
            print(frame.head(10).to_string())
    return 0 if not (len(missing) or len(extra) or len(drift)) else 1


def report_coverage(st) -> None:
    """What publish attached to the factor tree — and what it got wrong."""
    from app.dataeng import indicators

    covs = list(st.indicator_coverage)
    rows = {r.id: r for r in indicators.active_rows(st)}
    mapped = [c for c in covs if c.tree_row_id]
    # Ask the resolver rather than re-deriving from `tree_row_id`: the response
    # has no factor row and is not an orphan, and a coverage can reach a row by
    # matching without an explicit binding.
    orphans = indicators.orphan_indicators(st)
    response = indicators.response_coverages(st)
    print(f"\n=== indicator coverage ===")
    print(f"  coverage records {len(covs)}  ·  bound {len(mapped)}  ·  "
          f"orphans {len(orphans)}  ·  response {[c.metric for c in response]}")

    collisions: dict[str, list] = {}
    for c in mapped:
        collisions.setdefault(c.tree_row_id, []).append(c)
    multi = {k: v for k, v in collisions.items() if len({c.metric for c in v}) > 1}
    if multi:
        print(f"\n  rows claimed by MORE THAN ONE metric ({len(multi)}):")
        for row_id, cs in multi.items():
            row = rows.get(row_id)
            label = (f"{row.l3} > {row.l4} [declares {row.indicator!r}]"
                     if row else row_id)
            print(f"      {label}")
            for c in cs:
                print(f"          <- {c.metric!r} from {c.asset_name}")
    if orphans:
        print(f"\n  orphans ({len(orphans)}):")
        for c in orphans:
            print(f"      {c.l3} > {c.l4} > {c.metric}   ({c.asset_name})")
    # Every metric must land somewhere: bound, orphan, or the response.
    accounted = len(mapped) + len(orphans) + len(response)
    if accounted != len(covs):
        print(f"\n  UNACCOUNTED: {len(covs)} coverage records but "
              f"{accounted} classified (bound+orphan+response)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", default=PROJECT_ID)
    ap.add_argument("--preview-only", action="store_true",
                    help="wire the answer-key pipelines and sandbox them, no dbt")
    ap.add_argument("--compare-only", action="store_true",
                    help="leave the project alone; just check what it has published "
                         "against the truth table (use after building by hand)")
    args = ap.parse_args()

    from app.store.state import get_store

    store = get_store()
    st = store.get(args.project_id)
    if st is None:
        print(f"project {args.project_id} not found — run make_dataeng_drill.py first")
        return 1

    if args.compare_only:
        rc = compare_to_truth(st, args.project_id)
        report_coverage(st)
        return rc

    print("=== assets ===")
    ensure_assets(st, args.project_id)

    print(f"\n=== wiring pipelines ({len(st.data_assets)} assets) ===")
    errors = build_pipelines(st, args.project_id)
    for name, err in errors.items():
        print(f"    WIRING  {name:22s} {err}")
    store.save(args.project_id)

    print("\n=== sandbox preview ===")
    problems = run_preview(st, args.project_id)
    for name, err in problems.items():
        print(f"    PREVIEW {name:22s} {err[:300]}")
    if args.preview_only:
        return 1 if (errors or problems) else 0
    if problems:
        print("\npreview failed — not running dbt")
        return 1

    print("\n=== dbt build + publish ===")
    build_problems = build_and_publish(st, args.project_id)
    for name, err in build_problems.items():
        print(f"    BUILD   {name:22s} {err[:400]}")

    rc = compare_to_truth(st, args.project_id)
    report_coverage(st)
    store.save(args.project_id)
    return rc or (1 if build_problems else 0)


if __name__ == "__main__":
    sys.exit(main())
