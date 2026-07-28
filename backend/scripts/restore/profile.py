"""Per-indicator coverage report for the curated long table."""
from __future__ import annotations

import pandas as pd

from scripts.restore import paths


def write(long: pd.DataFrame) -> None:
    paths.mkdirs()
    months = long["month"].dropna()
    lines = [
        "# QA · 指标画像",
        "",
        f"长表共 **{len(long)}** 行，覆盖 {int(months.min())}–{int(months.max())}，"
        f"{months.nunique()} 个月。",
        "",
        "## 层级稀疏度",
        "",
        "| 列 | 非空行数 | 非空占比 |",
        "|---|---|---|",
    ]
    for col in ("l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8"):
        nn = int(long[col].notna().sum())
        lines.append(f"| {col} | {nn} | {nn / len(long):.1%} |")

    lines += [
        "",
        "## 逐指标覆盖",
        "",
        "| L4 | Metric | 单位 | 行数 | 起 | 止 | 覆盖月数 | 缺失率 | min | max |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (l4, metric), g in long.groupby(["l4", "metric"], dropna=False):
        m = g["month"].dropna()
        unit = g["metric_type"].dropna()
        has_value = g["value"].notna().any()
        lines.append(
            f"| {'' if pd.isna(l4) else l4} | {'' if pd.isna(metric) else metric} "
            f"| {unit.iloc[0] if not unit.empty else ''} | {len(g)} "
            f"| {int(m.min()) if not m.empty else ''} "
            f"| {int(m.max()) if not m.empty else ''} "
            f"| {m.nunique()} | {g['value'].isna().mean():.1%} "
            f"| {g['value'].min() if has_value else ''} "
            f"| {g['value'].max() if has_value else ''} |"
        )
    lines.append("")
    (paths.QA_DIR / "profile.md").write_text("\n".join(lines), encoding="utf-8")
