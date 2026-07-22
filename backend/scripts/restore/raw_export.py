"""One workbook per 数据源, sheet per Task name — verbatim source slices.

Deliberately NOT a wide table. The source is a detail ledger: the same
(dimensions + full L1-L8 path + month + metric) key carries up to six distinct
activity-level values, and nothing in the data pairs a Spending record with a
签约门店数 record. Pivoting would force a choice between aggregating (which
destroys the detail the ledger exists to record) and inventing a record pairing
(which is fabrication). So each row here is one source row.

Values are copied verbatim, including the dirty enum spellings ('NAB ' vs 'NAB',
'Snack Store' vs 'snack store') — resolving those is exactly what the Data
Engine's enum clustering step is for.
"""
from __future__ import annotations

import re

import pandas as pd

from scripts.restore import paths, source

_UNSAFE = re.compile(r'[\\/:*?"<>|\[\]]+')
_SHEET_MAX = 31  # Excel's hard limit


def safe_name(value: str) -> str:
    """A filesystem- and Excel-sheet-safe name (<=31 chars)."""
    cleaned = _UNSAFE.sub("_", str(value)).strip()
    return (cleaned or "unnamed")[:_SHEET_MAX]


def write(station: pd.DataFrame) -> list[str]:
    """Write one workbook per data source; return the filenames written."""
    paths.mkdirs()
    written: list[str] = []
    for src, g in station.groupby("数据源", dropna=False):
        label = "未标注数据源" if pd.isna(src) else str(src)
        filename = f"{safe_name(label)}.xlsx"
        used: set[str] = set()
        with pd.ExcelWriter(paths.RAW_DIR / filename, engine="openpyxl") as writer:
            for task, tg in g.groupby("Task name", dropna=False):
                base = safe_name("未标注Task" if pd.isna(task) else str(task))
                name, i = base, 2
                while name in used:
                    suffix = f"_{i}"
                    name = base[: _SHEET_MAX - len(suffix)] + suffix
                    i += 1
                used.add(name)
                tg[source.BUSINESS_COLS].to_excel(writer, sheet_name=name,
                                                  index=False)
        written.append(filename)
    return sorted(written)
