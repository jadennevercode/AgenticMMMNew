"""Derive the business→engine taxonomy map by joining 2.32 against 2.24.

2.32 and 2.24 are the same dataset in two vocabularies: 2.32 speaks the business
factor names (生意基本盘 / 渠道成交驱动 / …), 2.24 speaks the modeling names
(Baseline Factor / Marketing Factor / …). `app.mmm.pivot.is_driver_row` keys on
the modeling names, so a curated table written in the business vocabulary yields
zero drivers and no model at all.

The map is *derived from the data*, never declared: we join on the natural key
and read off the correspondence. A mapping that is ambiguous (one business value
seen against two modeling values) or absent (a business value the join never
covers) raises rather than falling back to a guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from scripts.restore import paths

REFERENCE_224_SHEET = "dataset_model_data_yyyymm_20260"

# The natural key shared by both workbooks.
_JOIN_KEY = ["Task name", "品牌", "省份组别", "渠道类型", "渠道", "年", "月",
             "METRICS", "VALUE"]


class TaxonomyError(Exception):
    """The taxonomy could not be derived unambiguously from the data."""


@dataclass
class TaxonomyMap:
    l1: dict[str, str] = field(default_factory=dict)
    metric_type: dict[str, str] = field(default_factory=dict)
    evidence: dict[str, int] = field(default_factory=dict)


def _load_224() -> pd.DataFrame:
    df = pd.read_excel(paths.reference_workbook_224(),
                       sheet_name=REFERENCE_224_SHEET, engine="openpyxl")
    df.columns = [str(c) for c in df.columns]
    for col in ("Task name", "品牌", "省份组别", "渠道类型", "渠道",
                "数据类型Level1", "METRICS", "METRICS类型"):
        df[col] = df[col].astype("string")
    df["年"] = pd.to_numeric(df["年"], errors="coerce").astype("Int64")
    df["月"] = pd.to_numeric(df["月"], errors="coerce").astype("Int64")
    df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce").astype("float64")
    return df


def _derive_column(matched: pd.DataFrame, src: str, dst: str,
                   label: str, tmap: TaxonomyMap) -> dict[str, str]:
    """Read off src→dst from the matched rows; raise if it is not a function."""
    pairs = matched.groupby([src, dst], dropna=False).size()
    out: dict[str, str] = {}
    for (business, engine), count in pairs.items():
        if pd.isna(business) or pd.isna(engine):
            continue
        business, engine = str(business), str(engine)
        if business in out and out[business] != engine:
            raise TaxonomyError(
                f"{label} mapping is ambiguous: {business!r} maps to both "
                f"{out[business]!r} and {engine!r}"
            )
        out[business] = engine
        tmap.evidence[f"{label}:{business}"] = int(count)
    return out


def derive(station: pd.DataFrame) -> TaxonomyMap:
    """Derive the l1 and metric_type maps, or raise."""
    right = _load_224()
    cols = _JOIN_KEY + ["数据类型Level1", "METRICS类型"]
    matched = station[cols].merge(
        right[cols], on=_JOIN_KEY, how="inner", suffixes=("_32", "_24"),
    ).drop_duplicates()
    if matched.empty:
        raise TaxonomyError("2.32 and 2.24 share no rows on the natural key")

    tmap = TaxonomyMap()
    tmap.l1 = _derive_column(matched, "数据类型Level1_32", "数据类型Level1_24",
                             "l1", tmap)
    tmap.metric_type = _derive_column(matched, "METRICS类型_32", "METRICS类型_24",
                                      "metric_type", tmap)

    uncovered = set(station["数据类型Level1"].dropna().astype(str)) - set(tmap.l1)
    if uncovered:
        raise TaxonomyError(
            f"no derivable l1 mapping for {sorted(uncovered)} — the join covers "
            f"{sorted(tmap.l1)}. Refusing to guess."
        )

    # metric_type values the join never covered pass through unchanged; the one
    # rename the engine actually depends on is pinned explicitly.
    tmap.metric_type.setdefault("花费", "Spending")
    return tmap


def apply_l1(series: pd.Series, tmap: TaxonomyMap) -> pd.Series:
    return (series.astype("string")
            .map(lambda v: tmap.l1.get(str(v), v))
            .astype("string"))


def apply_metric_type(series: pd.Series, tmap: TaxonomyMap) -> pd.Series:
    return (series.astype("string")
            .map(lambda v: tmap.metric_type.get(str(v), v))
            .astype("string"))
