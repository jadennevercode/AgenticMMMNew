"""DuckDB sandbox execution kernel for the data engine.

Runs AI-generated (and human-edited) cleaning SQL against registered raw tables
in a locked-down, in-process DuckDB connection. The boundary has three layers:

1. **No external access** — ``SET enable_external_access=false`` then
   ``SET lock_configuration=true`` disable file/network functions
   (``read_csv``/``read_parquet``/``httpfs``), ``ATTACH``, and ``COPY`` to disk.
2. **Statement allowlist** — the *user* SQL must be a single ``SELECT`` / ``WITH``
   query; DDL/DML and config statements are rejected before execution. The engine
   itself wraps the query in ``CREATE TEMP TABLE … AS`` to materialise results, so
   the user SQL never writes anywhere.
3. **Resource caps** — a watchdog thread interrupts the query past a timeout, and
   row counts are capped for both the preview and the materialised output.

This is the ONLY place AI-authored SQL is executed; treat it as security-critical.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Optional

import duckdb
import pandas as pd

# Resource caps.
PREVIEW_ROWS = 50          # rows returned for the UI preview grid
MAX_OUTPUT_ROWS = 500_000  # hard cap on materialised cleaning output
DEFAULT_TIMEOUT_S = 20.0   # query watchdog deadline

# Statements the user SQL may begin with (single-statement only).
_ALLOWED_PREFIXES = ("select", "with")

# Tokens that must never appear in user SQL — DDL/DML, config, and any file/network
# access function (defence-in-depth on top of enable_external_access=false).
_BANNED_TOKENS = (
    "attach", "detach", "copy", "install", "load", "pragma", "set ",
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "export", "import", "call", "vacuum", "checkpoint",
    "read_csv", "read_parquet", "read_json", "read_text", "read_blob",
    "parquet_scan", "csv_scan", "glob", "sniff_csv", "httpfs",
    "system(", "shell", "getenv", "putenv",
)


class SqlSafetyError(Exception):
    """Raised when user SQL fails the allowlist / banned-token checks."""


@dataclass
class RunResult:
    ok: bool = False
    error: str = ""
    columns: list[str] = field(default_factory=list)
    row_count: int = 0
    preview: list[list[str]] = field(default_factory=list)
    df: Optional[pd.DataFrame] = None


def sanitize_ident(name: str) -> str:
    """Turn an arbitrary sheet/table name into a safe DuckDB identifier."""
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", str(name).strip()).strip("_").lower()
    if not s:
        s = "t"
    if s[0].isdigit():
        s = f"t_{s}"
    return s[:48]


def _strip_sql(sql: str) -> str:
    """Remove SQL comments and a single trailing semicolon for validation."""
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    no_line = re.sub(r"--[^\n]*", " ", no_block)
    return no_line.strip().rstrip(";").strip()


def _blank_literals(sql: str) -> str:
    """Blank out string literals and quoted identifiers before the token scan.

    Keywords inside quotes are inert data or a column name, never a statement —
    scanning them rejects legitimate queries (a source file named ``sales copy.xlsx``
    stamped as provenance, an enum value ``Load``, a column named ``copy``).
    Semicolons inside quotes are neutralised the same way, so the single-statement
    check stays sound.
    """
    return re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "''", sql)


def validate_sql(sql: str) -> str:
    """Validate user SQL is a single read-only query. Returns the cleaned SQL.

    Raises SqlSafetyError on empty input, multiple statements, a non-SELECT/WITH
    leading keyword, or any banned token outside a string literal.
    """
    cleaned = _strip_sql(sql or "")
    if not cleaned:
        raise SqlSafetyError("SQL is empty")
    scanned = _blank_literals(cleaned)
    if ";" in scanned:
        raise SqlSafetyError("only a single statement is allowed")
    lowered = scanned.lower()
    if not lowered.startswith(_ALLOWED_PREFIXES):
        raise SqlSafetyError("only SELECT / WITH queries are allowed")
    # Token check on word boundaries so 'create' doesn't trip on 'created_at'.
    for tok in _BANNED_TOKENS:
        pattern = re.escape(tok) if not tok.isalpha() else rf"\b{re.escape(tok)}\b"
        if re.search(pattern, lowered):
            raise SqlSafetyError(f"disallowed SQL token: {tok.strip()}")
    return cleaned


def _new_connection() -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB connection with external access locked off."""
    con = duckdb.connect(database=":memory:")
    con.execute("SET enable_external_access=false")
    # Best-effort hardening; ignore on engine versions without these knobs.
    for stmt in ("SET lock_configuration=true",):
        try:
            con.execute(stmt)
        except duckdb.Error:
            pass
    return con


def _run_with_timeout(con: duckdb.DuckDBPyConnection, sql: str, timeout_s: float) -> None:
    """Execute `sql` on `con`, interrupting it if it runs past `timeout_s`."""
    done = threading.Event()

    def watchdog() -> None:
        if not done.wait(timeout_s):
            con.interrupt()

    t = threading.Thread(target=watchdog, daemon=True)
    t.start()
    try:
        con.execute(sql)
    finally:
        done.set()


def run_clean_sql(
    sql: str,
    tables: dict[str, pd.DataFrame],
    *,
    preview_rows: int = PREVIEW_ROWS,
    max_rows: int = MAX_OUTPUT_ROWS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    materialize: bool = True,
) -> RunResult:
    """Run a single read-only cleaning query against registered raw tables.

    `tables` maps a (safe) table name → its raw DataFrame; the SQL references those
    names. Returns a RunResult with a string-coerced preview always, and the full
    (row-capped) DataFrame when `materialize` is True.
    """
    try:
        cleaned = validate_sql(sql)
    except SqlSafetyError as e:
        return RunResult(ok=False, error=str(e))

    con = _new_connection()
    try:
        for name, df in tables.items():
            safe = sanitize_ident(name)
            con.register(safe, df)
        wrapped = f"CREATE TEMP TABLE __clean_out AS (\n{cleaned}\n)"
        _run_with_timeout(con, wrapped, timeout_s)

        row_count = int(con.execute("SELECT count(*) FROM __clean_out").fetchone()[0])
        preview_df = con.execute(
            f"SELECT * FROM __clean_out LIMIT {int(preview_rows)}"
        ).fetch_df()
        columns = [str(c) for c in preview_df.columns]
        preview = _to_preview(preview_df)

        out_df: Optional[pd.DataFrame] = None
        if materialize:
            out_df = con.execute(
                f"SELECT * FROM __clean_out LIMIT {int(max_rows)}"
            ).fetch_df()
        return RunResult(ok=True, columns=columns, row_count=row_count,
                         preview=preview, df=out_df)
    except duckdb.InterruptException:
        return RunResult(ok=False, error=f"query exceeded {timeout_s:.0f}s timeout")
    except duckdb.Error as e:
        return RunResult(ok=False, error=f"SQL error: {e}")
    finally:
        con.close()


# ── editor preview (pipeline prefix → grid + column profile) ──
# Header-level profiling the grid renders above each column. Caps keep the extra
# passes cheap: a column is only value-counted when it is genuinely categorical,
# and only the first few numeric columns get a histogram.
TOP_VALUES = 6          # value-counts kept per categorical column
TOP_MAX_DISTINCT = 40   # a column with more distinct values is not categorical
HIST_BUCKETS = 10
HIST_MAX_COLUMNS = 16   # numeric columns that get a histogram


@dataclass
class ColumnStat:
    """Profile of one preview column — what the grid header renders."""
    name: str
    type: str = ""
    null_pct: float = 0.0
    distinct: int = 0
    min: str = ""
    max: str = ""
    top: list[tuple[str, int]] = field(default_factory=list)
    histogram: list[int] = field(default_factory=list)


@dataclass
class PreviewResult:
    ok: bool = False
    error: str = ""
    columns: list[str] = field(default_factory=list)
    row_count: int = 0
    rows: list[list[str]] = field(default_factory=list)
    stats: list[ColumnStat] = field(default_factory=list)


_NUMERIC_TYPES = ("tinyint", "smallint", "integer", "bigint", "hugeint",
                  "float", "double", "decimal", "real")


def run_preview(sql: str, tables: dict[str, pd.DataFrame], *,
                limit: int = 200, timeout_s: float = DEFAULT_TIMEOUT_S,
                with_stats: bool = True) -> PreviewResult:
    """Run a read-only query and return grid rows plus a per-column profile.

    Unlike :func:`run_clean_sql` this never materialises the full result to the
    caller — it keeps it in the sandbox, returns `limit` rows for display, and
    profiles the whole (row-capped) output so the header stats describe the real
    data rather than the visible page.
    """
    try:
        cleaned = validate_sql(sql)
    except SqlSafetyError as e:
        return PreviewResult(ok=False, error=str(e))

    con = _new_connection()
    try:
        for name, df in tables.items():
            con.register(sanitize_ident(name), df)
        _run_with_timeout(
            con, f"CREATE TEMP TABLE __preview AS (\n{cleaned}\n)", timeout_s)

        row_count = int(con.execute("SELECT count(*) FROM __preview").fetchone()[0])
        head = con.execute(f"SELECT * FROM __preview LIMIT {int(limit)}").fetch_df()
        columns = [str(c) for c in head.columns]
        stats = (_profile(con, columns, row_count) if with_stats else [])
        return PreviewResult(ok=True, columns=columns, row_count=row_count,
                             rows=_to_preview(head), stats=stats)
    except duckdb.InterruptException:
        return PreviewResult(ok=False, error=f"query exceeded {timeout_s:.0f}s timeout")
    except duckdb.Error as e:
        return PreviewResult(ok=False, error=f"SQL error: {e}")
    finally:
        con.close()


def _profile(con: duckdb.DuckDBPyConnection, columns: list[str],
             row_count: int) -> list[ColumnStat]:
    """Column stats for the grid header, built on DuckDB's own SUMMARIZE."""
    try:
        summary = con.execute("SUMMARIZE __preview").fetch_df()
    except duckdb.Error:
        return [ColumnStat(name=c) for c in columns]

    def cell(row: pd.Series, key: str) -> str:
        v = row.get(key)
        return "" if v is None or pd.isna(v) else str(v)

    by_name: dict[str, ColumnStat] = {}
    for _, row in summary.iterrows():
        name = str(row.get("column_name"))
        try:
            null_pct = float(cell(row, "null_percentage") or 0.0)
        except ValueError:
            null_pct = 0.0
        try:
            distinct = int(float(cell(row, "approx_unique") or 0))
        except ValueError:
            distinct = 0
        by_name[name] = ColumnStat(
            name=name, type=cell(row, "column_type").lower(),
            null_pct=round(null_pct, 2), distinct=distinct,
            min=cell(row, "min"), max=cell(row, "max"))

    stats = [by_name.get(c, ColumnStat(name=c)) for c in columns]
    if row_count > 0:
        _add_top_values(con, stats)
        _add_histograms(con, stats)
    return stats


def _add_top_values(con: duckdb.DuckDBPyConnection, stats: list[ColumnStat]) -> None:
    """Value counts for categorical columns — the enum-shaped ones a cleaning
    step is most likely to target."""
    for st in stats:
        if not (0 < st.distinct <= TOP_MAX_DISTINCT):
            continue
        if any(st.type.startswith(t) for t in _NUMERIC_TYPES):
            continue
        col = st.name.replace('"', '""')
        try:
            rows = con.execute(
                f'SELECT cast("{col}" as varchar), count(*) FROM __preview '
                f'WHERE "{col}" IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT {TOP_VALUES}'
            ).fetchall()
        except duckdb.Error:
            continue
        st.top = [(str(v), int(n)) for v, n in rows]


def _add_histograms(con: duckdb.DuckDBPyConnection, stats: list[ColumnStat]) -> None:
    """Equal-width distributions for numeric columns, in one round trip."""
    parts: list[str] = []
    targets: list[ColumnStat] = []
    for st in stats:
        if len(targets) >= HIST_MAX_COLUMNS:
            break
        if not any(st.type.startswith(t) for t in _NUMERIC_TYPES):
            continue
        try:
            lo, hi = float(st.min), float(st.max)
        except ValueError:
            continue
        width = (hi - lo) / HIST_BUCKETS
        col = st.name.replace('"', '""')
        bucket = ("0" if width <= 0 else
                  f'least({HIST_BUCKETS - 1}, greatest(0, cast(floor((cast("{col}" '
                  f'as double) - {lo}) / {width}) as integer)))')
        parts.append(
            f'SELECT {_quote(st.name)} as c, {bucket} as b, count(*) as n '
            f'FROM __preview WHERE "{col}" IS NOT NULL GROUP BY 2')
        targets.append(st)
    if not parts:
        return
    try:
        rows = con.execute(" UNION ALL ".join(parts)).fetchall()
    except duckdb.Error:
        return
    buckets: dict[str, list[int]] = {st.name: [0] * HIST_BUCKETS for st in targets}
    for name, b, n in rows:
        idx = int(b)
        if 0 <= idx < HIST_BUCKETS:
            buckets[str(name)][idx] = int(n)
    for st in targets:
        st.histogram = buckets[st.name]


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _to_preview(df: pd.DataFrame) -> list[list[str]]:
    """String-coerce a small DataFrame to row-major cells for the UI grid."""
    out: list[list[str]] = []
    for _, row in df.iterrows():
        out.append(["" if pd.isna(v) else str(v) for v in row.tolist()])
    return out
