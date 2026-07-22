"""Instant preview of a transform pipeline — the editor's feedback loop.

``dbt build`` is the authoritative path, but it is a subprocess over the whole DAG:
too slow to answer "what does this step do to my data?" while someone is editing.
This module answers that question in the sandbox instead — it compiles the prefix
of the pipeline ending at one step (:func:`compiler.compile_preview_sql`) and runs
it through the locked-down DuckDB kernel, returning grid rows plus a per-column
profile.

Two properties keep it honest:

* the SQL comes from the **same** per-step templates the dbt build compiles, so a
  preview cannot show a shape the build would not produce; and
* the pipeline is taken from the request, not from disk, so an unsaved edit
  previews immediately — the loop is edit → see, with no save/build in between.

Reading the raw workbooks dominates the cost, so parsed frames are memoised per
(project, asset, source set); an upload changes the source set and so the key.
"""
from __future__ import annotations

from collections import OrderedDict

import pandas as pd

from app.dataeng import duck
from app.dataeng.dbt import compiler, target_schema
from app.dataeng.sources import asset_tables
from app.domain.models import DataAsset, TransformPipeline

SOURCE_PREFIX = "source:"
DEFAULT_LIMIT = 200
MAX_LIMIT = 1_000
_CACHE_SIZE = 4

_frames: "OrderedDict[tuple[str, str, tuple[str, ...]], dict[str, pd.DataFrame]]" = OrderedDict()


def _cached_tables(project_id: str, asset: DataAsset) -> dict[str, pd.DataFrame]:
    key = (project_id, asset.id, tuple(sorted(asset.source_file_ids)))
    hit = _frames.get(key)
    if hit is not None:
        _frames.move_to_end(key)
        return hit
    tables = asset_tables(project_id, asset)
    _frames[key] = tables
    _frames.move_to_end(key)
    while len(_frames) > _CACHE_SIZE:
        _frames.popitem(last=False)
    return tables


def invalidate(project_id: str, asset_id: str = "") -> None:
    """Drop memoised frames after an upload or asset change."""
    for key in [k for k in _frames if k[0] == project_id and (not asset_id or k[1] == asset_id)]:
        _frames.pop(key, None)


def preview_step(st, project_id: str, asset: DataAsset, pipe: TransformPipeline | None,
                 step_id: str, *, limit: int = DEFAULT_LIMIT) -> duck.PreviewResult:
    """Preview the output of one pipeline step — or of a raw source table.

    ``step_id`` is either a pipeline step id or ``source:<table>``. An empty id
    previews the pipeline's output step.
    """
    limit = max(1, min(int(limit), MAX_LIMIT))
    tables = _cached_tables(project_id, asset)
    if not tables:
        return duck.PreviewResult(
            ok=False, error="This asset has no readable raw sources yet — upload files first.")

    if step_id.startswith(SOURCE_PREFIX):
        table = duck.sanitize_ident(step_id[len(SOURCE_PREFIX):])
        if table not in tables:
            return duck.PreviewResult(ok=False, error=f"unknown source table {table!r}")
        return duck.run_preview(f'select * from {table}', tables, limit=limit)

    if pipe is None or not pipe.steps:
        return duck.PreviewResult(ok=False, error="This pipeline has no steps yet.")
    try:
        sql = compiler.compile_preview_sql(
            pipe, step_id,
            target_schema=target_schema.schema_for(st),
            raw_columns={name: [str(c) for c in df.columns] for name, df in tables.items()},
            source_labels={t.name: (t.filename or t.name) for t in asset.raw_tables},
        )
    except compiler.CompileError as e:
        return duck.PreviewResult(ok=False, error=str(e))
    return duck.run_preview(sql, tables, limit=limit)


def column_values(st, project_id: str, asset: DataAsset, pipe: TransformPipeline | None,
                  step_id: str, column: str, *, limit: int = 500
                  ) -> tuple[list[tuple[str, int]], str]:
    """Distinct values of one column with their row counts, most frequent first.

    Feeds the enum-map editor: the values to standardise are whatever actually
    reaches the step, not whatever is already listed in its mapping table.
    Returns ``(values, error)`` — an empty list with a message on failure.
    """
    tables = _cached_tables(project_id, asset)
    if not tables:
        return [], "This asset has no readable raw sources yet — upload files first."

    if step_id.startswith(SOURCE_PREFIX):
        table = duck.sanitize_ident(step_id[len(SOURCE_PREFIX):])
        if table not in tables:
            return [], f"unknown source table {table!r}"
        inner = f"select * from {table}"
    elif pipe is None or not pipe.steps:
        return [], "This pipeline has no steps yet."
    else:
        try:
            inner = compiler.compile_preview_sql(
                pipe, step_id,
                target_schema=target_schema.schema_for(st),
                raw_columns={n: [str(c) for c in df.columns] for n, df in tables.items()},
                source_labels={t.name: (t.filename or t.name) for t in asset.raw_tables},
            )
        except compiler.CompileError as e:
            return [], str(e)

    col = column.replace('"', '""')
    sql = (f'select cast("{col}" as varchar) as value, count(*) as n\n'
           f"from (\n{inner}\n)\nwhere \"{col}\" is not null\ngroup by 1 order by 2 desc")
    res = duck.run_preview(sql, tables, limit=limit, with_stats=False)
    if not res.ok:
        return [], res.error
    return [(row[0], int(float(row[1]))) for row in res.rows if row], ""
