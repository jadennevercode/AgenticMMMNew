"""Data-asset lifecycle service.

Assets live on ``ProjectState.data_assets`` (persisted with the project JSON), but
their **cleaned output** is too large for state JSON, so each published version is
materialised to parquet under ``data/projects/{id}/assets/{asset_id}/v{n}.parquet``.
Publishing re-runs the asset's validated SQL through the sandbox kernel, writes the
parquet, appends a version, and invalidates the model-dataset cache so the project
workflow picks up the new data on the next compute.
"""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from app.config import get_settings
from app.dataeng.duck import run_clean_sql
from app.dataeng.sources import asset_tables
from app.domain.models import DataAsset, DataAssetVersion


class PublishError(Exception):
    """Raised when an asset cannot be published (no SQL, bad SQL, empty output)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _assets_root(project_id: str) -> Path:
    return get_settings().data_path / "projects" / project_id / "assets"


def _asset_dir(project_id: str, asset_id: str) -> Path:
    return _assets_root(project_id) / asset_id


def create_asset(st, name: str, description: str = "",
                 source_file_ids: Optional[list[str]] = None) -> DataAsset:
    asset = DataAsset(
        id=f"da-{uuid.uuid4().hex[:8]}", name=name.strip() or "Untitled asset",
        status="raw", description=description,
        sourceFileIds=list(source_file_ids or []),
        createdAt=_now_iso(), updatedAt=_now_iso(),
    )
    st.data_assets.append(asset)
    return asset


def touch(asset: DataAsset) -> None:
    asset.updated_at = _now_iso()


def delete_asset(project_id: str, st, asset_id: str) -> bool:
    before = len(st.data_assets)
    st.data_assets = [a for a in st.data_assets if a.id != asset_id]
    if len(st.data_assets) == before:
        return False
    shutil.rmtree(_asset_dir(project_id, asset_id), ignore_errors=True)
    _invalidate(project_id)
    return True


def publish_asset(project_id: str, st, asset: DataAsset) -> DataAssetVersion:
    """Materialise the asset's cleaning SQL to parquet and register a new version."""
    draft = asset.sql_draft
    if draft is None or not draft.sql.strip():
        raise PublishError("没有可发布的清洗 SQL — 先生成并预览。")
    tables = asset_tables(project_id, asset)
    res = run_clean_sql(draft.sql, tables, materialize=True)
    if not res.ok:
        raise PublishError(f"清洗 SQL 执行失败: {res.error}")
    if res.df is None or res.df.empty:
        raise PublishError("清洗结果为空,无法发布。")

    version = asset.latest_version + 1
    out_dir = _asset_dir(project_id, asset.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    rel_path = f"projects/{project_id}/assets/{asset.id}/v{version}.parquet"
    abs_path = get_settings().data_path / rel_path
    res.df.to_parquet(abs_path, index=False)

    ver = DataAssetVersion(
        version=version, parquetPath=rel_path, rowCount=int(len(res.df)),
        columns=[str(c) for c in res.df.columns], sql=draft.sql, producedAt=_now_iso(),
    )
    asset.versions.append(ver)
    asset.latest_version = version
    asset.status = "published"
    touch(asset)
    _invalidate(project_id)
    return ver


def read_version(project_id: str, version: DataAssetVersion) -> Optional[pd.DataFrame]:
    abs_path = get_settings().data_path / version.parquet_path
    if not abs_path.exists():
        return None
    try:
        return pd.read_parquet(abs_path)
    except Exception:  # noqa: BLE001
        return None


def published_frames(project_id: str, st) -> list[pd.DataFrame]:
    """Latest published parquet of every published asset (for long-table binding)."""
    frames: list[pd.DataFrame] = []
    for asset in st.data_assets:
        if asset.status != "published" or not asset.versions:
            continue
        latest = max(asset.versions, key=lambda v: v.version)
        df = read_version(project_id, latest)
        if df is not None and not df.empty:
            frames.append(df)
    return frames


def _invalidate(project_id: str) -> None:
    from app.agents.dataset_cache import invalidate_project
    invalidate_project(project_id)
