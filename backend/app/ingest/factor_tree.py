"""Loader for the business factor tree (因子树) + drill dimensions.

Source sheet ``下钻因子树`` layout (after a one-row banner):
    col0 生意因子-level 1
    col1 生意因子-level 2
    col2 生意因子-level 3
    col3 生意影响因子-Level 4
    col4 指标选择        (the concrete indicator / metric)
    col5 时间颗粒度      (time granularity)
    col6 模型颗粒度      (model granularity)
    col7 下钻维度        (drill-down dimension)

L1..L4 cells are merged in Excel, so blank cells inherit the value above them
(classic forward-fill). We rebuild the L1->L2->L3->L4->indicator hierarchy.
"""
from __future__ import annotations

import openpyxl

from ._paths import FACTOR_TREE, FACTOR_TREE_SHEET, ref

_HEADER_ROW = 2  # 1-based; the row containing "生意因子-level 1"
_NCOLS = 8


def _clean(v: object) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _read_rows() -> list[list[str]]:
    """Read data rows with merged L1..L4 cells forward-filled."""
    wb = openpyxl.load_workbook(ref(FACTOR_TREE), read_only=True, data_only=True)
    ws = wb[FACTOR_TREE_SHEET]
    rows: list[list[str]] = []
    carry = ["", "", "", ""]  # forward-fill state for L1..L4
    for r in ws.iter_rows(min_row=_HEADER_ROW + 1, values_only=True):
        cells = [_clean(c) for c in (list(r) + [""] * _NCOLS)[:_NCOLS]]
        indicator = cells[4]
        if not any(cells):
            continue
        for i in range(4):
            if cells[i]:
                carry[i] = cells[i]
                # a new value at level i invalidates deeper carried levels
                for j in range(i + 1, 4):
                    carry[j] = ""
        l1, l2, l3, l4 = carry
        if not indicator and not l4:
            continue
        rows.append([l1, l2, l3, l4, indicator, cells[5], cells[6], cells[7]])
    wb.close()
    return rows


def load_factor_tree() -> dict:
    """Return the factor tree as a nested L1->L2->L3->L4 hierarchy with indicators.

    Shape::

        {
          "levels": ["生意因子-level 1", ...],
          "factors": [  # flat rows, one per indicator
            {"l1","l2","l3","l4","indicator","time_granularity",
             "model_granularity","drill_dimension"}, ...
          ],
          "tree": {l1: {l2: {l3: {l4: [ {indicator,...}, ... ]}}}},
          "counts": {"l1":n,"l2":n,"l3":n,"l4":n,"indicators":n},
        }
    """
    rows = _read_rows()
    factors: list[dict] = []
    tree: dict = {}

    for l1, l2, l3, l4, indicator, time_g, model_g, drill in rows:
        rec = {
            "l1": l1, "l2": l2, "l3": l3, "l4": l4,
            "indicator": indicator,
            "time_granularity": time_g,
            "model_granularity": model_g,
            "drill_dimension": drill,
        }
        factors.append(rec)
        node = tree.setdefault(l1, {}).setdefault(l2, {}).setdefault(l3, {})
        node.setdefault(l4, []).append(
            {
                "indicator": indicator,
                "time_granularity": time_g,
                "model_granularity": model_g,
                "drill_dimension": drill,
            }
        )

    def _distinct(key: str) -> list[str]:
        seen: list[str] = []
        for f in factors:
            v = f[key]
            if v and v not in seen:
                seen.append(v)
        return seen

    return {
        "levels": ["L1", "L2", "L3", "L4", "indicator"],
        "factors": factors,
        "tree": tree,
        "counts": {
            "l1": len(_distinct("l1")),
            "l2": len(_distinct("l2")),
            "l3": len(_distinct("l3")),
            "l4": len(_distinct("l4")),
            "indicators": len(factors),
        },
        "l1_values": _distinct("l1"),
        "l2_values": _distinct("l2"),
    }
