"""Reconstruct the FactorTree as the union of the planned and the actual trees.

Two facts drive this module:

1. The level offset — the granularity sheet's 指标选择 column *is* the data
   table's 数据类型Level5. So FactorRow.l1..l4 <- Level1..Level4 and
   FactorRow.indicator <- Level5. L6-L8 are drill-down dimensions that live on
   the long table only; FactorRow has no fields for them.
2. The two trees disagree. 29 planned indicators have no data and 19 data-bearing
   indicators were never planned. We keep both and label the difference with
   `origin`, so the 2.1 factor-map gate sees the planned-but-empty rows as
   `pending` and a human decides to ignore them — which is the point of that gate.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from scripts.restore import paths

# KPI rows carry the literal 'KPI' at every level: the response is not a factor.
_KPI = "KPI"

_LEVELS = ["数据类型Level1", "数据类型Level2", "数据类型Level3", "数据类型Level4"]

# A control character no level name can contain, so the modal path splits back
# apart cleanly (an empty separator is a ValueError).
_SEP = "\x1f"

_COLUMNS = ["id", "l1", "l2", "l3", "l4", "indicator", "dimension", "source",
            "status", "rationale", "evidence", "origin", "hasData", "rows",
            "monthsCovered"]

_ID_UNSAFE = re.compile(r"[^0-9a-z]+")


def _row_id(indicator: str, seq: int) -> str:
    slug = _ID_UNSAFE.sub("-", str(indicator).lower()).strip("-")
    return f"fr-{seq:03d}-{slug}" if slug else f"fr-{seq:03d}"


def _actual_rows(station: pd.DataFrame) -> pd.DataFrame:
    """Per-indicator L1-L4 path + coverage, read off the data table."""
    df = station[station["数据类型Level1"] != _KPI].copy()
    df["数据类型Level5"] = df["数据类型Level5"].astype("string").str.strip()
    df = df[df["数据类型Level5"].notna() & (df["数据类型Level5"] != "")]
    out = []
    for indicator, g in df.groupby("数据类型Level5", dropna=True):
        # An indicator can appear under several paths; the modal one is its home.
        joined = (g[_LEVELS].astype("string").fillna("")
                  .agg(_SEP.join, axis=1).mode().iloc[0])
        path = joined.split(_SEP)
        channels = sorted({str(v) for v in g["渠道类型"].dropna().unique()})
        regions = sorted({str(v) for v in g["省份组别"].dropna().unique()})
        out.append({
            "indicator": str(indicator),
            "l1": path[0], "l2": path[1], "l3": path[2], "l4": path[3],
            "dimension": ", ".join(channels + regions),
            "rows": int(len(g)),
            "monthsCovered": int(g["月"].dropna().nunique()),
        })
    return pd.DataFrame(out)


def build(station: pd.DataFrame, granularity: pd.DataFrame) -> pd.DataFrame:
    """The union tree: planned ∪ actual, each row labelled with its origin."""
    actual = _actual_rows(station)
    actual_by_ind = {r["indicator"]: r for r in actual.to_dict("records")}

    rows: list[dict] = []
    planned_names: set[str] = set()
    for rec in granularity.to_dict("records"):
        indicator = str(rec["indicator"])
        if indicator in planned_names:
            continue  # the sheet repeats indicators across granularity variants
        planned_names.add(indicator)
        hit = actual_by_ind.get(indicator)
        planned_dim = ", ".join(
            str(rec[c]) for c in ("channel", "region") if pd.notna(rec[c]))
        rows.append({
            "l1": str(rec["l1"]), "l2": str(rec["l2"]),
            "l3": str(rec["l3"]), "l4": str(rec["l4"]),
            "indicator": indicator,
            "dimension": planned_dim,
            "origin": "both" if hit else "planned",
            "hasData": bool(hit),
            "rows": int(hit["rows"]) if hit else 0,
            "monthsCovered": int(hit["monthsCovered"]) if hit else 0,
        })

    for rec in actual.to_dict("records"):
        if rec["indicator"] in planned_names:
            continue
        rows.append({
            "l1": rec["l1"], "l2": rec["l2"], "l3": rec["l3"], "l4": rec["l4"],
            "indicator": rec["indicator"], "dimension": rec["dimension"],
            "origin": "data", "hasData": True,
            "rows": rec["rows"], "monthsCovered": rec["monthsCovered"],
        })

    tree = pd.DataFrame(rows)
    tree["id"] = [_row_id(r.indicator, i + 1)
                  for i, r in enumerate(tree.itertuples())]
    # The restore never pre-judges a row — source/status stay at model defaults.
    tree["source"] = "template"
    tree["status"] = "baseline"
    tree["rationale"] = ""
    tree["evidence"] = ""
    return tree[_COLUMNS].reset_index(drop=True)


def write(tree: pd.DataFrame) -> None:
    """Emit factor-tree.json, factor-tree.xlsx and reconciliation.md."""
    paths.mkdirs()

    # FactorTree{rows:[FactorRow]} — exactly the PUT /factor-tree payload.
    payload = {"rows": [
        {k: r[k] for k in ("id", "l1", "l2", "l3", "l4", "indicator",
                           "dimension", "source", "status", "rationale",
                           "evidence")}
        for r in tree.to_dict("records")
    ]}
    (paths.FACTOR_TREE_DIR / "factor-tree.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    tree.to_excel(paths.FACTOR_TREE_DIR / "factor-tree.xlsx", index=False)

    planned = tree[tree["origin"] == "planned"]
    data_only = tree[tree["origin"] == "data"]
    both = tree[tree["origin"] == "both"]
    lines = [
        "# 因子树还原：规划态 vs 实际态",
        "",
        f"因子树 = 规划 ∪ 实际 = **{len(tree)}** 行"
        f"（both {len(both)} · planned {len(planned)} · data {len(data_only)}）。",
        "",
        "## 规划了但没有数据（origin=planned）",
        "",
        "这些行在 2.1 因子映射门禁里会是 `pending`，需要人工 ignore 或补数据。",
        "",
        "| L1 | L2 | L3 | L4 | Indicator | 计划粒度 |",
        "|---|---|---|---|---|---|",
    ]
    for r in planned.to_dict("records"):
        lines.append(f"| {r['l1']} | {r['l2']} | {r['l3']} | {r['l4']} "
                     f"| {r['indicator']} | {r['dimension']} |")
    lines += [
        "",
        "## 有数据但未入规划树（origin=data）",
        "",
        "这些指标已补进因子树，L1-L4 取其在长表中出现最频繁的层级路径。",
        "",
        "| L1 | L2 | L3 | L4 | Indicator | 行数 | 覆盖月数 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in data_only.to_dict("records"):
        lines.append(f"| {r['l1']} | {r['l2']} | {r['l3']} | {r['l4']} "
                     f"| {r['indicator']} | {r['rows']} | {r['monthsCovered']} |")
    lines.append("")
    (paths.FACTOR_TREE_DIR / "reconciliation.md").write_text(
        "\n".join(lines), encoding="utf-8")
