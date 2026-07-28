"""Loader for the data dictionary (数据字典) describing each source table.

Sheet ``数据字典`` (161 rows x 16 cols, leading blank column). Header row maps
Chinese labels to a fixed schema describing every source feed: theme, sheet,
source system, granularity, which L4 factor it serves, ETL logic, Y/X role, and
the physical table name.
"""
from __future__ import annotations

import openpyxl

from ._paths import DATA_DICT, DATA_DICT_SHEET, ref

# Chinese header label -> clean key.
_HEADER_MAP = {
    "Theme": "theme",
    "SheetName": "sheet",
    "Source Sheet": "source_sheet",
    "Source Sheet 位置": "source_location",
    "来源系统": "source_system",
    "granularity": "granularity",
    "服务于哪一个L4 factor": "serves_l4",
    "Source Sheet ETL逻辑": "etl_logic",
    "Y Or X": "y_or_x",
    "Description": "description",
    "TableName": "table_name",
    "表来源": "table_origin",
    "Data source DEPT.": "source_dept",
    "Data provider": "data_provider",
}


def _clean(v: object) -> str:
    return "" if v is None else str(v).strip()


def load_data_dictionary() -> list[dict]:
    """Return one dict per source-table row in the data dictionary.

    Keys: theme, sheet, source_sheet, source_location, source_system,
    granularity, serves_l4, etl_logic, y_or_x, description, table_name,
    table_origin, source_dept, data_provider (plus any unmapped headers verbatim).
    Rows that are entirely empty are skipped.
    """
    wb = openpyxl.load_workbook(ref(DATA_DICT), read_only=True, data_only=True)
    ws = wb[DATA_DICT_SHEET]
    it = ws.iter_rows(values_only=True)

    header_raw = next(it)
    headers = [_clean(h) for h in header_raw]
    keys = [_HEADER_MAP.get(h, h.lower().replace(" ", "_")) for h in headers]

    out: list[dict] = []
    for row in it:
        cells = [_clean(c) for c in (list(row) + [""] * len(keys))[: len(keys)]]
        if not any(cells):
            continue
        rec = {k: v for k, v in zip(keys, cells) if k}  # drop the leading blank header
        out.append(rec)
    wb.close()
    return out
