"""End-to-end verification of the model-input_2.32 restore.

Run: PYTHONPATH=. .venv/bin/python -m scripts._test_restore

Three load-bearing claims:
  1. schema   — the curated long table IS the canonical 19-column schema.
  2. lossless — raw/ and curated/ each carry every source row, compared as a
                MULTISET. The source holds 1,140 same-key-different-value detail
                groups and 105 fully duplicated rows; comparing as a set would
                hide the loss of ~3,000 rows.
  3. runnable — build_model_frame finds a response and real drivers, and run_mmm
                actually fits.
"""
from __future__ import annotations

import sys

import pandas as pd

from app.ingest.dataset import COLUMN_NAMES
from app.mmm import build_model_frame, run_mmm
from app.mmm.pivot import MAX_DRIVERS, driver_candidates
from scripts.restore import curated, paths, source, taxonomy

# 29 real data sources + one workbook holding the source's 23 fully-blank
# trailing rows (23813 = 23790 + 23), kept verbatim rather than silently dropped.
EXPECTED_RAW_WORKBOOKS = 30

_SMOKE: list[str] = []


def _log(line: str) -> None:
    print(line)
    _SMOKE.append(line)


# Excel round-trips integers back as floats ('2024' -> '2024.0'), so numeric
# columns must be coerced to a canonical dtype on BOTH sides before the rows are
# stringified — otherwise the comparison reports a difference that is purely a
# rendering artifact and hides any real one.
_INT_COLS = {"年", "月", "year", "month"}
_FLOAT_COLS = {"VALUE", "value"}


def _multiset(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """Row multiset: count per normalised row, sorted by row key."""
    norm = df[cols].copy()
    for col in cols:
        if col in _INT_COLS:
            norm[col] = pd.to_numeric(norm[col], errors="coerce").astype("Int64")
        elif col in _FLOAT_COLS:
            norm[col] = pd.to_numeric(norm[col], errors="coerce").astype("float64")
    norm = norm.astype("string").fillna("__NA__")
    return norm.groupby(cols, dropna=False).size().sort_index()


def test_schema() -> None:
    long = pd.read_csv(paths.CURATED_DIR / "long_table.csv")
    assert list(long.columns) == COLUMN_NAMES, list(long.columns)


def test_raw_is_lossless() -> None:
    station = source.load_station()
    files = sorted(paths.RAW_DIR.glob("*.xlsx"))
    assert len(files) == EXPECTED_RAW_WORKBOOKS, \
        f"expected {EXPECTED_RAW_WORKBOOKS} raw workbooks, got {len(files)}"
    frames = []
    for path in files:
        for _sheet, df in pd.read_excel(path, sheet_name=None,
                                        engine="openpyxl").items():
            frames.append(df)
    rejoined = pd.concat(frames, ignore_index=True)
    assert len(rejoined) == len(station), (len(rejoined), len(station))

    # Dimensions (everything but VALUE) must match exactly, as a multiset.
    dims = [c for c in source.BUSINESS_COLS if c != "VALUE"]
    left = _multiset(station, dims)
    right = _multiset(rejoined, dims)
    only_source = sorted(set(left.index) - set(right.index))[:3]
    only_raw = sorted(set(right.index) - set(left.index))[:3]
    assert left.equals(right), (
        f"raw/ dimensions differ from source; only in source: {only_source}; "
        f"only in raw: {only_raw}")

    # VALUE is compared numerically. Writing xlsx serialises a float64 to ~15
    # significant decimal digits, so the read-back is a *different* float64
    # (42703.547999999995 -> 42703.548). That is a real, if microscopic, loss —
    # so the tolerance is asserted explicitly and the worst observed deviation is
    # reported, never assumed to be zero.
    ls = station["VALUE"].dropna().sort_values().to_numpy()
    rs = pd.to_numeric(rejoined["VALUE"], errors="coerce").dropna().sort_values().to_numpy()
    assert len(ls) == len(rs), f"VALUE count differs: {len(ls)} vs {len(rs)}"
    denom = pd.Series(ls).abs().clip(lower=1e-12).to_numpy()
    worst = float((abs(ls - rs) / denom).max()) if len(ls) else 0.0
    _log(f"  raw/ VALUE max relative deviation from xlsx round-trip: {worst:.3e}")
    assert worst < 1e-9, f"xlsx round-trip lost real precision: {worst:.3e}"


def test_curated_is_lossless() -> None:
    """Curated maps back onto the source ledger, row for row."""
    station = source.load_station()
    tmap = taxonomy.derive(station)
    long = curated.build(station, tmap)
    assert len(long) == len(station), (len(long), len(station))
    # Every curated l1 must reverse to a business value the source actually uses.
    engine_values = set(long["l1"].dropna().astype(str))
    assert engine_values <= set(tmap.l1.values()), sorted(engine_values)
    # The factor path + value multiset must survive the translation untouched.
    cols = ["l4", "l5", "metric", "value"]
    renamed = station.rename(columns={
        "数据类型Level4": "l4", "数据类型Level5": "l5",
        "METRICS": "metric", "VALUE": "value"})
    # Compare on the trimmed form, since build() trims the string columns.
    for col in ("l4", "l5", "metric"):
        renamed[col] = renamed[col].astype("string").str.strip().replace({"": pd.NA})
    left = _multiset(renamed, cols)
    right = _multiset(long, cols)
    assert left.equals(right), (
        "curated (l4, l5, metric, value) multiset differs from source; "
        f"{len(left)} vs {len(right)} distinct rows")


def test_ols_runs() -> None:
    long = pd.read_csv(paths.CURATED_DIR / "long_table.csv")
    objects = [str(o) for o in long["channel_type"].dropna().unique()]
    fitted = 0
    for obj in objects:
        try:
            mf = build_model_frame(long, obj)
        except ValueError as exc:
            _log(f"  {obj:10s} skipped: {exc}")
            continue
        assert mf.y_metric, f"{obj}: no response metric identified"
        assert mf.x_cols, f"{obj}: zero drivers — check the l1 taxonomy"
        result = run_mmm(long, obj)
        fitted += 1
        _log(f"  {obj:10s} Y={mf.y_metric} ({mf.y_metric_type}) "
             f"n_obs={result.n_obs} drivers={len(result.drivers)} "
             f"R2={result.r2:.4f} adjR2={result.adj_r2:.4f}")
        # Diagnostics only — this block reports, it never fails the test.
        candidates = driver_candidates(long, obj)
        if len(candidates) > len(mf.x_cols):
            kept = {str(m.get("metric", "")) for m in mf.meta.values()
                    if isinstance(m, dict)}
            dropped = [str(c.get("metric", "")) for c in candidates
                       if str(c.get("metric", "")) not in kept]
            _log(f"    NOTE {len(candidates)} candidates -> {len(mf.x_cols)} kept "
                 f"(MAX_DRIVERS={MAX_DRIVERS}); dropped {len(dropped)}: "
                 f"{dropped[:12]}")
    assert fitted > 0, "no model object could be fitted from the curated long table"
    _log(f"  fitted {fitted}/{len(objects)} model objects")


TESTS = [test_schema, test_raw_is_lossless, test_curated_is_lossless, test_ols_runs]


def main() -> int:
    failed = 0
    for fn in TESTS:
        _log(f"== {fn.__name__}")
        try:
            fn()
            _log(f"PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            _log(f"FAIL {fn.__name__}: {exc}")
    _log(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    paths.mkdirs()
    (paths.QA_DIR / "ols_smoke.txt").write_text("\n".join(_SMOKE) + "\n",
                                                encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
