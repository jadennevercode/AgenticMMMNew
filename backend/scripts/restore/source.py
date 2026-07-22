"""Load the two sheets of the 2.32 model-input workbook.

`load_station` deliberately does NOT clean values: dirty enum spellings
('NAB ' vs 'NAB', 'Snack Store' vs 'snack store') are what the Data Engine's
clustering step exists to resolve, so the raw export must carry them through.
Only dtypes are coerced.
"""
from __future__ import annotations

import pandas as pd

from scripts.restore import paths

STATION_SHEET = "D.Data Station"
GRANULARITY_SHEET = "模型颗粒度参考表"

LEVEL_COLS = [f"数据类型Level{i}" for i in range(1, 9)]

# The 19 business columns of the source table. The three trailing naming columns
# (Variable / Variable no. / Metric no.) are source-internal metadata and ride
# only in indicators.csv.
BUSINESS_COLS = [
    "Task name", "品牌", "省份组别", "渠道类型", "渠道", "年", "月", "数据源",
    *LEVEL_COLS,
    "METRICS类型", "METRICS", "VALUE",
]

_STRING_COLS = [
    "Task name", "品牌", "省份组别", "渠道类型", "渠道", "数据源",
    *LEVEL_COLS,
    "METRICS类型", "METRICS",
]


def load_station() -> pd.DataFrame:
    """The 23,813-row detail ledger: dtypes coerced, values verbatim."""
    df = pd.read_excel(paths.source_workbook(), sheet_name=STATION_SHEET,
                       engine="openpyxl")
    df.columns = [str(c) for c in df.columns]
    for col in _STRING_COLS:
        df[col] = df[col].astype("string")
    df["年"] = pd.to_numeric(df["年"], errors="coerce").astype("Int64")
    df["月"] = pd.to_numeric(df["月"], errors="coerce").astype("Int64")
    df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce").astype("float64")
    return df.reset_index(drop=True)


def load_granularity() -> pd.DataFrame:
    """The planned factor tree: L1-L4 + indicator + channel/region granularity.

    Read with `header=0` — the header is the sheet's first row and the first
    column is blank. Reading with `header=1` silently consumes the first data
    row (品类全渠道销量) and undercounts the planned indicators by one.

    The hierarchy columns are merged-cell sparse, so L1-L4 are forward-filled.
    Rows without an indicator carry no information and are dropped.
    """
    g = pd.read_excel(paths.source_workbook(), sheet_name=GRANULARITY_SHEET,
                      header=0, engine="openpyxl")
    g = g.iloc[:, 1:8]  # drop the leading blank column
    g.columns = ["l1", "l2", "l3", "l4", "indicator", "channel", "region"]
    for col in g.columns:
        g[col] = g[col].astype("string").str.strip().replace({"": pd.NA})
    g[["l1", "l2", "l3", "l4"]] = g[["l1", "l2", "l3", "l4"]].ffill()
    g = g[g["indicator"].notna()]
    return g.reset_index(drop=True)
