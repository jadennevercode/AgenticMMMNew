"""Profiling-engine smoke test on synthetic raw tables.

Run: .venv/bin/python -m app.dataeng._test_profile
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.dataeng.profile import report_from_frames
from app.domain.models import RawTable


def _frames():
    months = pd.date_range("2023-01-01", periods=24, freq="MS")
    rng = np.random.default_rng(7)
    df = pd.DataFrame({
        "Month": [d.strftime("%Y-%m") for d in months],
        "Region": (["华东", "华南", "华北"] * 8),
        "Spend": rng.normal(1000, 300, 24).round(1),       # high CV
        "Flat": [42.0] * 24,                                # ~zero CV
        "Sales": (np.arange(24) * 50 + 500).astype(float),  # trending
    })
    # introduce time gaps (drop 3 interior months) so continuity falls below 0.9
    df = df.drop(index=[5, 9, 13]).reset_index(drop=True)
    meta = RawTable(name="raw", fileId="f1", filename="sales.xlsx",
                    rowCount=len(df), columns=list(df.columns))
    return [(meta, df)]


def main() -> None:
    rep = report_from_frames(_frames())
    by = {f.name: f for f in rep.fields}

    # time axis detected as monthly with a gap
    assert rep.time_field == "Month", rep.time_field
    assert by["Month"].time_granularity == "month", by["Month"].time_granularity
    assert by["Month"].is_time_axis
    assert (by["Month"].gap_count or 0) >= 1, by["Month"].gap_count
    assert by["Month"].continuity is not None and by["Month"].continuity < 1.0
    print(f"✓ time axis: month, continuity={by['Month'].continuity}, gaps={by['Month'].gap_count}")

    # volatility: Spend high CV, Flat ~0
    assert by["Spend"].cv and by["Spend"].cv > 0.15, by["Spend"].cv
    assert by["Flat"].cv == 0 or (by["Flat"].cv or 0) < 0.01, by["Flat"].cv
    print(f"✓ volatility: Spend CV={by['Spend'].cv}, Flat CV={by['Flat'].cv}")

    # dtype inference
    assert by["Region"].dtype == "text", by["Region"].dtype
    assert by["Sales"].dtype in ("number", "integer"), by["Sales"].dtype
    print("✓ dtype inference ok")

    # charts present
    ids = {c["id"] for c in rep.charts}
    assert "volatility" in ids and "continuity" in ids, ids
    print(f"✓ charts: {sorted(ids)}")

    # warnings flag the low continuity
    assert any("连续性" in w for w in rep.warnings), rep.warnings
    print(f"✓ warnings: {rep.warnings}")

    print("\nALL PROFILE TESTS PASSED")


if __name__ == "__main__":
    main()
