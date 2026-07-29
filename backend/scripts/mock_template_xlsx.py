"""Emit the mock functional-beverage template as uploadable .xlsx workbooks.

Two files under sample-uploads/s1-test/:
  · mock-factor-tree.xlsx  — cols L1·L2·L3·L4·Indicator·ROI Range·Contribution Range
      Upload to a project's **Factor Tree** category (S1 upload gate), OR import
      into a factor_tree template on the Knowledge screen.
  · mock-interview.xlsx    — cols Category·Role·Question
      Import into an interview template on the Knowledge screen.

Column ORDER matches both the backend factor-tree parser (header-alias based) and
the frontend Knowledge importer (positional), so either upload path accepts them.

Run from backend/:  PYTHONPATH=. .venv/bin/python scripts/mock_template_xlsx.py
"""
from __future__ import annotations

from pathlib import Path

import openpyxl

from scripts.mock_industry_template import FACTOR_ROWS, INTERVIEW_QS, ROOT

OUT = ROOT / "sample-uploads" / "s1-test"
OUT.mkdir(parents=True, exist_ok=True)


def _write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template"
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(path)
    print(f"  wrote {path}  ({len(rows)} rows)")


def main() -> None:
    ft_header = ["L1", "L2", "L3", "L4", "Indicator", "ROI Range", "Contribution Range"]
    ft_rows = [[r.l1, r.l2, r.l3, r.l4, r.indicator, r.roi_range, r.contribution_range]
               for r in FACTOR_ROWS]
    _write(OUT / "mock-factor-tree.xlsx", ft_header, ft_rows)

    iv_header = ["Category", "Role", "Question"]
    iv_rows = [[q.category, q.role, q.question] for q in INTERVIEW_QS]
    _write(OUT / "mock-interview.xlsx", iv_header, iv_rows)


if __name__ == "__main__":
    main()
