"""Seed the Danone reference case as **real** Data-Engine assets.

The v2 E2E shortcut splatted 135 fabricated indicators straight onto
``ProjectState.indicators`` (no backing asset, no provenance). That is exactly the
"dead seed data" the product must never carry: 2.1 mapping then resolves against
indicators that trace to nothing.

This module registers the reference case the way a real project's data arrives —
by **asset**, one per data *source* in the real 23.8k-row client table. Each source
slice is materialised to a published parquet version (so the dataset resolver reads
it via the ``published`` path, unioning back to the full table) and run through the
real :func:`register_indicators`, so every indicator has a real ``assetId``,
coverage window, and factor-tree grounding. No hand-written indicators.

The reference table itself is the genuine Danone client data (per CLAUDE.md), so
nothing here is fabricated — only the *packaging* into assets is synthesised, and it
uses the same registration path the Data Engine uses at publish time.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.dataeng import assets as asset_svc
from app.dataeng.dbt.service import register_indicators
from app.domain.models import DataAsset, DataAssetVersion


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.strip().lower()).strip("-") or "src"


def _publish_slice(project_id: str, st, asset: DataAsset, df: pd.DataFrame) -> DataAssetVersion:
    """Materialise ``df`` as this asset's next published parquet version.

    Mirrors the parquet-write + version-append half of
    ``dbt.service.publish`` (the dbt build is the reference table's slice, already
    schema-conforming, so there is nothing to compile) — then registers indicators
    through the identical real path.
    """
    version = asset.latest_version + 1
    rel_path = f"projects/{project_id}/assets/{asset.id}/v{version}.parquet"
    abs_path = asset_svc.get_settings().data_path / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(abs_path, index=False)

    ver = DataAssetVersion(
        version=version, parquetPath=rel_path, rowCount=int(len(df)),
        columns=[str(c) for c in df.columns], sql="reference source slice",
        producedAt=_now_iso(),
    )
    asset.versions.append(ver)
    asset.latest_version = version
    asset.status = "published"
    asset.updated_at = _now_iso()
    register_indicators(st, asset, df)
    return ver


def seed_reference_assets(project_id: str, st) -> dict:
    """Rebuild the reference case as per-source published assets + real indicators.

    Idempotent: clears any prior seeded assets/indicators first, so a reset re-runs
    cleanly. Returns a small summary for logging/verification.
    """
    from app import ingest

    # Wipe the fabrication + any prior seeded assets for this project.
    st.indicators = []
    st.data_assets = []

    ref = ingest.load_model_dataset()
    if "source" not in ref.columns:
        raise ValueError("Reference dataset has no `source` column to split on.")

    summary: list[dict] = []
    # One asset per real data source, busiest first for stable ordering.
    for source, grp in sorted(ref.groupby("source"), key=lambda kv: -len(kv[1])):
        name = str(source).strip() or "Unnamed source"
        asset = asset_svc.create_asset(st, name=name, description=f"Danone reference source · {name}")
        slice_df = grp.reset_index(drop=True)
        _publish_slice(project_id, st, asset, slice_df)
        n_ind = sum(1 for ind in st.indicators if ind.asset_id == asset.id)
        summary.append({"asset": name, "assetId": asset.id, "rows": int(len(slice_df)), "indicators": n_ind})

    asset_svc._invalidate(project_id)
    grounded = sum(1 for ind in st.indicators if ind.tree_grounded)
    return {
        "assets": len(st.data_assets),
        "indicators": len(st.indicators),
        "treeGrounded": grounded,
        "perSource": summary,
    }
