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
from app.dataeng.sources import (
    SourceRead, heal_pipeline_inputs, read_asset_sources, source_labels,
)
from app.domain.models import DataAsset, TransformPipeline

SOURCE_PREFIX = "source:"
DEFAULT_LIMIT = 200
MAX_LIMIT = 1_000
_CACHE_SIZE = 4

_frames: "OrderedDict[tuple[str, str, tuple[str, ...]], SourceRead]" = OrderedDict()


def cached_sources(project_id: str, asset: DataAsset) -> SourceRead:
    """The asset's parsed sources, memoised per (project, asset, source set).

    Reading the workbooks dominates every editor round trip, so the same parse
    serves the preview, the source list and the enum value lookups.
    """
    key = (project_id, asset.id, tuple(sorted(asset.source_file_ids)))
    hit = _frames.get(key)
    if hit is not None:
        _frames.move_to_end(key)
        return hit
    read = read_asset_sources(project_id, asset)
    _frames[key] = read
    _frames.move_to_end(key)
    while len(_frames) > _CACHE_SIZE:
        _frames.popitem(last=False)
    return read


def _cached_tables(project_id: str, asset: DataAsset) -> dict[str, pd.DataFrame]:
    return cached_sources(project_id, asset).tables


def invalidate(project_id: str, asset_id: str = "") -> None:
    """Drop memoised frames after an upload or asset change."""
    for key in [k for k in _frames if k[0] == project_id and (not asset_id or k[1] == asset_id)]:
        _frames.pop(key, None)


def _no_sources_error(read: SourceRead) -> str:
    """Say why there is nothing to read — an upload that parsed to nothing looks
    identical to no upload at all unless the reason is carried through."""
    if not read.issues:
        return "This asset has no readable raw sources yet — upload files first."
    detail = "; ".join(f"{i.filename or i.file_id}: {i.reason}" for i in read.issues[:3])
    return f"None of the uploaded files could be read as a table — {detail}"


def preview_step(st, project_id: str, asset: DataAsset, pipe: TransformPipeline | None,
                 step_id: str, *, limit: int = DEFAULT_LIMIT) -> duck.PreviewResult:
    """Preview the output of one pipeline step — or of a raw source table.

    ``step_id`` is either a pipeline step id or ``source:<table>``. An empty id
    previews the pipeline's output step.
    """
    limit = max(1, min(int(limit), MAX_LIMIT))
    read = cached_sources(project_id, asset)
    tables = read.tables
    if not tables:
        return duck.PreviewResult(ok=False, error=_no_sources_error(read))
    heal_pipeline_inputs(pipe, tables)

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
            source_labels=source_labels(read),
        )
    except compiler.CompileError as e:
        return duck.PreviewResult(ok=False, error=str(e))
    res = duck.run_preview(sql, tables, limit=limit)
    return res if res.ok else duck.PreviewResult(
        ok=False, error=_explain(res.error), columns=res.columns)


# The compiler derives `period_date` from `month` on the output step, so a bad month
# value fails inside SQL the user never wrote — with a message naming neither the
# column nor the offending row.
_MONTH_FORMAT = "%Y%m%d"


def _explain(error: str) -> str:
    """Attach the missing context to engine errors that name none of the user's work."""
    if _MONTH_FORMAT in error:
        return (f"{error}\n\nThe `month` column must be a yyyymm integer (e.g. 202301). "
                "Fix the value above at its source, or map/derive `month` so every row "
                "is a real year and month.")
    return error


def input_columns(st, project_id: str, asset: DataAsset, pipe: TransformPipeline | None,
                  step_id: str) -> tuple[list[str], str]:
    """The columns available at ``step_id`` — a raw table's, or a step's output.

    Feeds the field-map editor, which cannot ask a person to name source columns it
    has never shown them. Raw tables answer from the parsed frame directly; a step
    is compiled and probed for one row, which is enough for the column list.
    Returns ``(columns, error)``.
    """
    read = cached_sources(project_id, asset)
    tables = read.tables
    if not tables:
        return [], _no_sources_error(read)
    heal_pipeline_inputs(pipe, tables)
    if step_id.startswith(SOURCE_PREFIX):
        table = duck.sanitize_ident(step_id[len(SOURCE_PREFIX):])
        if table not in tables:
            return [], f"unknown source table {table!r}"
        return [str(c) for c in tables[table].columns], ""
    res = preview_step(st, project_id, asset, pipe, step_id, limit=1)
    return (list(res.columns), "") if res.ok else ([], res.error)


def column_values(st, project_id: str, asset: DataAsset, pipe: TransformPipeline | None,
                  step_id: str, column: str, *, limit: int = 500
                  ) -> tuple[list[tuple[str, int]], str]:
    """Distinct values of one column with their row counts, most frequent first.

    Feeds the enum-map editor: the values to standardise are whatever actually
    reaches the step, not whatever is already listed in its mapping table.
    Returns ``(values, error)`` — an empty list with a message on failure.
    """
    read = cached_sources(project_id, asset)
    tables = read.tables
    if not tables:
        return [], _no_sources_error(read)
    heal_pipeline_inputs(pipe, tables)

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
                source_labels=source_labels(read),
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
