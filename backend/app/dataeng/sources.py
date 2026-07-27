"""Read a data asset's registered raw source files into DataFrames.

Each Excel sheet / CSV becomes one raw "table" with a safe DuckDB identifier. The
same (RawTable metadata, DataFrame) pairs drive both the profiling engine and the
SQL sandbox, so the table names the AI sees in profiles match what it can query.

Table names are a **contract**: a pipeline step wires itself to ``source:<name>``,
so a name that changes when an unrelated file is added silently breaks the wiring.
Every name here is therefore derived from the identity of its own (file, sheet)
alone — never from how many other sources the asset happens to have.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.dataeng.duck import sanitize_ident
from app.domain.models import RawTable
from app.store.files import get_files

_MAX_READ_ROWS = 200_000  # guardrail on a single raw table
READABLE_SUFFIXES = (".xlsx", ".xlsm", ".csv", ".txt")

# The name a lone single-sheet source used to get. Pipelines saved under the old
# naming scheme still reference it; :func:`heal_pipeline_inputs` re-points them.
LEGACY_SINGLE_NAME = "raw"


@dataclass(frozen=True)
class SourceIssue:
    """A registered file that produced no queryable table, and why."""
    file_id: str
    filename: str
    reason: str


@dataclass
class SourceRead:
    """Everything one pass over an asset's registered files produced."""
    pairs: list[tuple[RawTable, pd.DataFrame]] = field(default_factory=list)
    issues: list[SourceIssue] = field(default_factory=list)

    @property
    def tables(self) -> dict[str, pd.DataFrame]:
        return {meta.name: df for meta, df in self.pairs}


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


def _table_name(file_id: str, filename: str, sheet: str, multi: bool) -> str:
    """A stable safe identifier for one (file, sheet).

    Depends only on this source's own identity, so adding or removing another file
    never renames it. Labels with no ASCII alphanumerics (a purely CJK filename,
    say) would all collapse to the same identifier, so those fall back to a short
    digest of the file+sheet — ugly, but stable and collision-free.
    """
    stem = Path(filename).stem
    label = f"{stem}_{sheet}" if multi else (stem or sheet)
    if not any(ch.isascii() and ch.isalnum() for ch in label):
        digest = hashlib.sha1(f"{file_id}:{sheet}".encode("utf-8")).hexdigest()[:6]
        return f"t_{digest}"
    return sanitize_ident(label)


def read_asset_sources(project_id: str, asset) -> SourceRead:
    """Resolve an asset's registered files → readable tables + per-file problems.

    A file that cannot contribute a table (missing, unsupported format, empty,
    unparseable) is reported rather than dropped, so the editor can say *why* an
    upload never showed up instead of rendering an unexplained empty source list.
    """
    files = get_files()
    out = SourceRead()
    used: set[str] = set()

    for file_id in asset.source_file_ids:
        got = files.get_path(project_id, file_id)
        if got is None:
            out.issues.append(SourceIssue(file_id, "", "file is no longer in the project folder"))
            continue
        record, path = got
        if path.suffix.lower() not in READABLE_SUFFIXES:
            out.issues.append(SourceIssue(
                record.id, record.filename,
                f"{path.suffix or 'this format'} cannot be read as a table — "
                "save it as .xlsx, .xlsm or .csv"))
            continue
        try:
            sheets = _read_file(path)
        except Exception as e:  # noqa: BLE001 — a corrupt upload must not 500 the editor
            out.issues.append(SourceIssue(record.id, record.filename, f"could not be parsed: {e}"))
            continue
        if not sheets:
            out.issues.append(SourceIssue(record.id, record.filename, "contains no non-empty sheet"))
            continue

        multi = len(sheets) > 1
        for sheet, df in sheets.items():
            base = _table_name(record.id, record.filename, sheet, multi)
            name, i = base, 2
            while name in used:
                name = f"{base}_{i}"
                i += 1
            used.add(name)
            out.pairs.append((
                RawTable(name=name, fileId=record.id, filename=record.filename,
                         sheet=str(sheet), rowCount=int(len(df)),
                         columns=[str(c) for c in df.columns]),
                df,
            ))
    return out


def source_labels(read: SourceRead) -> dict[str, str]:
    """{raw table name: the origin label stamped onto every row it produces}.

    The label is what a reader sees in the downstream `source` filter, so it names
    the file — and, only when that file contributes more than one table, the sheet
    as well. Suffixing unconditionally would relabel every single-sheet source and
    split it from its own already-published rows in that filter.
    """
    per_file: dict[str, int] = {}
    for meta, _ in read.pairs:
        per_file[meta.file_id] = per_file.get(meta.file_id, 0) + 1
    out: dict[str, str] = {}
    for meta, _ in read.pairs:
        name = meta.filename or meta.name
        out[meta.name] = (f"{name} › {meta.sheet}"
                          if per_file[meta.file_id] > 1 and meta.sheet else name)
    return out


def read_asset_frames(project_id: str, asset) -> list[tuple[RawTable, pd.DataFrame]]:
    """An asset's source files → (RawTable, DataFrame) pairs."""
    return read_asset_sources(project_id, asset).pairs


def asset_tables(project_id: str, asset) -> dict[str, pd.DataFrame]:
    """{safe_table_name: DataFrame} for SQL registration."""
    return read_asset_sources(project_id, asset).tables


def heal_pipeline_inputs(pipe, table_names) -> bool:
    """Re-point pipeline inputs left dangling by the pre-stable naming scheme.

    A lone single-sheet source used to be called ``raw``; it now carries its own
    filename-derived name, which would strand every step wired to ``source:raw``.
    Only that unambiguous case is rewritten — when the asset has exactly one table,
    there is nothing else the input could have meant. Returns whether it changed.
    """
    if pipe is None or not pipe.steps:
        return False
    names = set(table_names)
    if LEGACY_SINGLE_NAME in names or len(names) != 1:
        return False
    only = next(iter(names))
    legacy = f"source:{LEGACY_SINGLE_NAME}"
    changed = False
    for step in pipe.steps:
        if legacy in step.inputs:
            step.inputs = [f"source:{only}" if i == legacy else i for i in step.inputs]
            changed = True
    return changed
