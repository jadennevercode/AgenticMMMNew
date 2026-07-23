"""Full uncapped per-channel master-data export. Run:
PYTHONPATH=. .venv/bin/python -m app.agents._test_master_export"""
from __future__ import annotations

import io
import sys

from app.agents._test_per_channel import make_two_channel_state
from app.agents.master_data import build_export


def test_export_has_a_sheet_per_channel() -> None:
    st = make_two_channel_state("t-master-export")
    data = build_export(st)
    assert isinstance(data, (bytes, bytearray)) and len(data) > 0
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert set(wb.sheetnames) >= {"MT", "TT"}, wb.sheetnames
    ws = wb["MT"]
    header = [c.value for c in next(ws.iter_rows(max_row=1))]
    assert header and header[0] == "Period", header
    # more than just Period → at least one indicator column
    assert len(header) >= 2, header
    print(f"  export ok: sheets={wb.sheetnames}, MT cols={len(header)}")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
