"""The publish-ready 19-column long table + its provenance sidecars.

This is a 1:1 row-for-row translation of the source detail ledger — never an
aggregation. The source's 1,140 same-key-different-value detail groups are real
activity records; `build_model_frame` sums them at pivot time, and collapsing
them here would silently change every downstream number.
"""
from __future__ import annotations

import pandas as pd

from app.ingest.dataset import COLUMN_NAMES
from scripts.restore import paths, taxonomy

# Source column -> canonical long-table column.
_RENAME = {
    "Task name": "task_name", "品牌": "brand", "省份组别": "province_group",
    "渠道类型": "channel_type", "渠道": "channel", "年": "year", "月": "month",
    "数据源": "source",
    "数据类型Level1": "l1", "数据类型Level2": "l2", "数据类型Level3": "l3",
    "数据类型Level4": "l4", "数据类型Level5": "l5", "数据类型Level6": "l6",
    "数据类型Level7": "l7", "数据类型Level8": "l8",
    "METRICS类型": "metric_type", "METRICS": "metric", "VALUE": "value",
}

_STRING_COLS = [c for c in COLUMN_NAMES if c not in ("year", "month", "value")]


def build(station: pd.DataFrame, tmap: taxonomy.TaxonomyMap) -> pd.DataFrame:
    """Translate the source ledger into the canonical long table."""
    df = station[list(_RENAME)].rename(columns=_RENAME).copy()
    df["l1"] = taxonomy.apply_l1(df["l1"], tmap)
    df["metric_type"] = taxonomy.apply_metric_type(df["metric_type"], tmap)
    # curated/ is the clean side: normalise the dirty enum spellings raw/
    # deliberately preserves, matching ingest.dataset.load_model_dataset.
    for col in _STRING_COLS:
        df[col] = (df[col].astype("string").str.strip()
                   .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA}))
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["month"] = pd.to_numeric(df["month"], errors="coerce").astype("Int64")
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype("float64")
    return df[COLUMN_NAMES].reset_index(drop=True)


def _mode_or_blank(series: pd.Series) -> str:
    clean = series.dropna()
    return "" if clean.empty else str(clean.mode().iloc[0])


def _indicator_catalog(station: pd.DataFrame, long: pd.DataFrame) -> pd.DataFrame:
    """One row per (l4, metric) — the Indicator-model view, plus source metadata."""
    naming = (station[["数据类型Level5", "METRICS", "Variable", "Variable no.",
                       "Metric no."]]
              .rename(columns={"数据类型Level5": "l5", "METRICS": "metric"})
              .copy())
    # `long` was trimmed by build(); trim the join keys here too, or the merge
    # silently misses every row whose source value carried whitespace.
    for key in ("l5", "metric"):
        naming[key] = naming[key].astype("string").str.strip()
    naming = naming.drop_duplicates(subset=["l5", "metric"])

    rows = []
    for (l4, metric), g in long.groupby(["l4", "metric"], dropna=False):
        months = g["month"].dropna()
        has_value = g["value"].notna().any()
        rows.append({
            "l1": _mode_or_blank(g["l1"]),
            "l2": _mode_or_blank(g["l2"]),
            "l3": _mode_or_blank(g["l3"]),
            "l4": "" if pd.isna(l4) else str(l4),
            "l5": _mode_or_blank(g["l5"]),
            "metric": "" if pd.isna(metric) else str(metric),
            "metricType": _mode_or_blank(g["metric_type"]),
            "rows": int(len(g)),
            "coverageStart": int(months.min()) if not months.empty else 0,
            "coverageEnd": int(months.max()) if not months.empty else 0,
            "monthsCovered": int(months.nunique()),
            "nullRate": round(float(g["value"].isna().mean()), 4),
            "valueMin": float(g["value"].min()) if has_value else None,
            "valueMax": float(g["value"].max()) if has_value else None,
        })
    cat = pd.DataFrame(rows)
    return (cat.merge(naming, on=["l5", "metric"], how="left")
            .sort_values(["l1", "l2", "l3", "l4", "metric"]))


def write(long: pd.DataFrame, station: pd.DataFrame,
          tmap: taxonomy.TaxonomyMap) -> None:
    paths.mkdirs()
    long.to_csv(paths.CURATED_DIR / "long_table.csv", index=False,
                encoding="utf-8-sig")
    long.to_excel(paths.CURATED_DIR / "long_table.xlsx", index=False)

    tax_rows = [
        {"kind": kind, "source": src, "target": dst,
         "evidenceRows": tmap.evidence.get(f"{kind}:{src}", 0)}
        for kind, mapping in (("l1", tmap.l1), ("metric_type", tmap.metric_type))
        for src, dst in sorted(mapping.items())
    ]
    pd.DataFrame(tax_rows).to_csv(paths.CURATED_DIR / "taxonomy_map.csv",
                                  index=False, encoding="utf-8-sig")

    _indicator_catalog(station, long).to_csv(
        paths.CURATED_DIR / "indicators.csv", index=False, encoding="utf-8-sig")
