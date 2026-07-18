"""Read a data asset's registered raw source files into DataFrames.

Each Excel sheet / CSV becomes one raw "table" with a safe DuckDB identifier. The
same (RawTable metadata, DataFrame) pairs drive both the profiling engine and the
SQL sandbox, so the table names the AI sees in profiles match what it can query.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.dataeng.duck import sanitize_ident
from app.domain.models import RawTable
from app.store.files import get_files

_MAX_READ_ROWS = 200_000  # guardrail on a single raw table


def _read_file(path: Path) -> dict[str, pd.DataFrame]:
    """Read one source file into {sheet_or_table_name: DataFrame}."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        book = pd.read_excel(path, sheet_name=None, nrows=_MAX_READ_ROWS)
        return {str(name): df for name, df in book.items()
                if df is not None and not df.empty}
    if suffix in (".csv", ".txt"):
        df = pd.read_csv(path, nrows=_MAX_READ_ROWS)
        return {path.stem: df} if not df.empty else {}
    return {}


def read_asset_frames(project_id: str, asset) -> list[tuple[RawTable, pd.DataFrame]]:
    """Resolve an asset's source files → (RawTable, DataFrame) pairs.

    Table names are unique safe identifiers derived from the *clean* filename (a
    single-sheet file → the filename stem; a multi-sheet workbook → one table per
    sheet name). A lone single-sheet source is named ``raw`` so SQL reads naturally.
    """
    files = get_files()
    pairs: list[tuple[RawTable, pd.DataFrame]] = []
    used: set[str] = set()
    # (file_id, clean_filename, sheet, is_multi_sheet, df)
    raw_frames: list[tuple[str, str, str, bool, pd.DataFrame]] = []
    for file_id in asset.source_file_ids:
        got = files.get_path(project_id, file_id)
        if got is None:
            continue
        record, path = got
        sheets = _read_file(path)
        multi = len(sheets) > 1
        for sheet, df in sheets.items():
            raw_frames.append((record.id, record.filename, sheet, multi, df))

    single = len(raw_frames) == 1
    for file_id, filename, sheet, multi, df in raw_frames:
        # Multi-sheet workbook → sheet name; otherwise the clean filename stem.
        stem = Path(filename).stem
        base = "raw" if single else sanitize_ident(sheet if multi else (stem or sheet))
        name = base
        i = 2
        while name in used:
            name = f"{base}_{i}"
            i += 1
        used.add(name)
        meta = RawTable(
            name=name, fileId=file_id, filename=filename,
            rowCount=int(len(df)), columns=[str(c) for c in df.columns],
        )
        pairs.append((meta, df))
    return pairs


def asset_tables(project_id: str, asset) -> dict[str, pd.DataFrame]:
    """{safe_table_name: DataFrame} for SQL registration."""
    return {meta.name: df for meta, df in read_asset_frames(project_id, asset)}
