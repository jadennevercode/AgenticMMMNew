"""Real-data integration test: run the MMM engine on the Mizone dataset.

Run: .venv/bin/python -m app.mmm._test_real
Loads the LONG dataset, renames the 19 Chinese columns, and runs run_mmm /
make_candidates / run_all_objects on real model objects. Real MMM data is messy;
the requirement is that it RUNS and produces real computed numbers with honest
red flags.
"""
from __future__ import annotations

import os

import pandas as pd

from app.mmm import build_model_frame, make_candidates, run_all_objects, run_mmm
from app.mmm.pivot import CN_TO_EN

XLSX = os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "reference", "02.数据智能体",
    "【MMM AI】数据智能体-Data Process_2.24.xlsx",
)
SHEET = "dataset_model_data_yyyymm_20260"


def load_long() -> pd.DataFrame:
    df = pd.read_excel(XLSX, sheet_name=SHEET, engine="openpyxl")
    df = df.rename(columns=CN_TO_EN)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def _print_result(r) -> None:
    print(f"  model_object : {r.model_object}")
    print(f"  n_obs        : {r.n_obs}")
    print(f"  R2 / adjR2   : {r.r2:.4f} / {r.adj_r2:.4f}")
    print(f"  MAPE         : {r.mape:.2f}%")
    print(f"  Durbin-Watson: {r.durbin_watson:.3f}")
    print(f"  baseline %   : {r.baseline_pct:.2f}%")
    print(f"  drivers ({len(r.drivers)}): {[r.meta['drivers_meta'][d]['metric'] for d in r.drivers][:8]}")
    print("  contribution % (top 6 by |share|):")
    for d, pct in sorted(r.contribution.items(), key=lambda kv: -abs(kv[1]))[:6]:
        label = r.meta["drivers_meta"][d]["metric"]
        print(f"      {label[:48]:48s} {pct:+7.2f}%  coef={r.coefficients[d]:+.4g}")
    print(f"  ROI (paid channels, {len(r.roi)}):")
    for c, v in list(r.roi.items())[:6]:
        print(f"      {r.meta['drivers_meta'][c]['metric'][:48]:48s} ROI={v:+.4f}")
    print(f"  response_curves: {len(r.response_curves)} drivers, "
          f"{len(next(iter(r.response_curves.values()))) if r.response_curves else 0} pts each")
    print(f"  red_flags ({len(r.red_flags)}):")
    for f in r.red_flags:
        print(f"      - {f}")


def main() -> int:
    print("=== REAL-DATA TEST (Mizone dataset) ===")
    df = load_long()
    print(f"loaded LONG df: {df.shape}, columns renamed to english: {list(df.columns)[:6]}...")

    # 1. build_model_frame for MT
    mf = build_model_frame(df, "MT")
    print(f"\n[build_model_frame MT] wide shape={mf.frame.shape}, "
          f"Y='{mf.y_col}', x_cols={len(mf.x_cols)}, spend_cols={len(mf.spend_cols)}")
    print(f"  months: {mf.frame.index.min()}..{mf.frame.index.max()}")

    # 2. run_mmm on MT (primary deliverable)
    print("\n[run_mmm MT  adstock=0.5 hill_half=1.0]")
    r = run_mmm(df, "MT", adstock=0.5, hill_half=1.0)
    _print_result(r)
    assert r.n_obs >= 12 and r.coefficients, "MT produced no real fit"

    # 3. to_dict round-trips (json-serializable shape)
    d = r.to_dict()
    assert set(["model_object", "r2", "contribution", "roi", "response_curves", "red_flags"]) <= set(d)
    print("\n[to_dict] keys:", sorted(d.keys()))

    # 4. candidates (3 differing models)
    print("\n[make_candidates MT n=3]")
    cands = make_candidates(df, "MT", n=3)
    for i, c in enumerate(cands):
        print(f"  cand {i}: adstock={c.adstock} hill={c.hill_half_pct} "
              f"R2={c.r2:.4f} MAPE={c.mape:.2f}% baseline={c.baseline_pct:.1f}% flags={len(c.red_flags)}")
    distinct_r2 = len({round(c.r2, 4) for c in cands})
    assert distinct_r2 > 1, "candidates not differentiated"

    # 5. run_all_objects across the Mizone case objects
    print("\n[run_all_objects MT/TT/AFH/EC+O2O]")
    allr = run_all_objects(df, ["MT", "TT", "AFH", "EC+O2O"])
    for obj, res in allr.items():
        if res.n_obs:
            print(f"  {obj:7s}: n={res.n_obs} R2={res.r2:.4f} MAPE={res.mape:.1f}% "
                  f"baseline={res.baseline_pct:.1f}% drivers={len(res.drivers)} flags={len(res.red_flags)}")
        else:
            print(f"  {obj:7s}: FAILED -> {res.red_flags}")

    print("\nAll real-data assertions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
