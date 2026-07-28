"""Loader for the long-format MMM modeling dataset.

The dataset (~23.8k rows) is brand x province-group x channel x year x month x
factor-level (L1..L8) x metric -> value, in tidy LONG format. Source columns are
Chinese; we rename to stable English-ish names for the rest of the engine.
"""
from __future__ import annotations

import pandas as pd

from ._paths import MODEL_DATASET, MODEL_DATASET_SHEET, ref

# Chinese source column -> clean name (positional rename keeps it robust to
# stray whitespace in headers).
COLUMN_NAMES: list[str] = [
    "task_name",
    "brand",
    "province_group",
    "channel_type",
    "channel",
    "year",
    "month",
    "source",
    "l1",
    "l2",
    "l3",
    "l4",
    "l5",
    "l6",
    "l7",
    "l8",
    "metric_type",
    "metric",
    "value",
]

_STRING_COLS = [
    "task_name", "brand", "province_group", "channel_type", "channel",
    "source", "l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8",
    "metric_type", "metric",
]


def load_model_dataset() -> pd.DataFrame:
    """Load the long-format modeling dataset with clean English-ish columns.

    - Renames the 19 Chinese columns positionally.
    - Coerces ``year`` / ``month`` to nullable int (``month`` is yyyymm in source).
    - Coerces ``value`` to float (NaN where non-numeric).
    - Trims surrounding whitespace from string dimension columns and normalises
      empty strings to NA so callers get clean distinct values.
    """
    path = ref(MODEL_DATASET)
    df = pd.read_excel(path, sheet_name=MODEL_DATASET_SHEET)

    if df.shape[1] != len(COLUMN_NAMES):
        raise ValueError(
            f"Expected {len(COLUMN_NAMES)} columns in {MODEL_DATASET_SHEET}, "
            f"got {df.shape[1]}: {list(df.columns)}"
        )
    df.columns = COLUMN_NAMES

    for col in _STRING_COLS:
        df[col] = (
            df[col]
            .astype("string")
            .str.strip()
            .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
        )

    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["month"] = pd.to_numeric(df["month"], errors="coerce").astype("Int64")
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype("float64")

    return df.reset_index(drop=True)
