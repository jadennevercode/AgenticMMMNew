"""2.31/2.32 business-validation analytics — compute the six-step review series
from the master dataset (``model_df``). Step 1 (全景概览) is implemented here as
real, charted series; later steps build on the same chart schema.

A chart dict is::

    {"id","type": line|bar|dualAxis|share|quadrant, "title","x":[labels],
     "series":[{"name","data":[..],"axis":"left|right"}], "unit",
     "interpretation","conclusion","factors":[..],"signoff":""}

All numbers come from pandas, never the LLM (the LLM only narrates).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Metric-name classifiers (the master table mixes Chinese/English metric names).
_SALES = r"销量|销售|销额|offtake|sales|volume|gmv|箱|出货"
_SPEND = r"花费|费用|spend|投放|金额|cost|budget"
_SEARCH = r"搜索|search|声量|互动|index|指数|social|曝光|阅读"
_SHARE = r"份额|share|占有"


def _mask(df: pd.DataFrame, pattern: str) -> pd.Series:
    return df["metric"].astype("string").str.contains(pattern, case=False, regex=True, na=False)


def _label(m: int) -> str:
    return f"{int(m) // 100}-{int(m) % 100:02d}"


def _monthly(df: pd.DataFrame, mask: pd.Series) -> tuple[list[str], list[float]]:
    sub = df[mask & df["month"].notna()]
    if sub.empty:
        return [], []
    g = sub.groupby("month")["value"].sum().sort_index()
    return [_label(m) for m in g.index], [round(float(v), 1) for v in g.to_numpy()]


def _yearly(df: pd.DataFrame, mask: pd.Series) -> tuple[list[int], list[float]]:
    sub = df[mask & df["year"].notna()]
    if sub.empty:
        return [], []
    g = sub.groupby("year")["value"].sum().sort_index()
    return [int(y) for y in g.index], [float(v) for v in g.to_numpy()]


def _pct(curr: float, prev: float) -> float | None:
    return round((curr - prev) / prev * 100, 1) if prev else None


def _chart(cid: str, ctype: str, title: str, *, x=None, series=None, unit="",
           factors=None, interpretation="", conclusion="") -> dict:
    return {
        "id": cid, "type": ctype, "title": title, "x": x or [], "series": series or [],
        "unit": unit, "factors": factors or [], "interpretation": interpretation,
        "conclusion": conclusion, "signoff": "",
    }


def build_overview(df: pd.DataFrame) -> list[dict]:
    """步骤1 全景概览 — up to 5 computed charts; each skipped when its data is absent."""
    charts: list[dict] = []
    sales_m_x, sales_m_y = _monthly(df, _mask(df, _SALES))
    spend_m_x, spend_m_y = _monthly(df, _mask(df, _SPEND))

    # 1. 整体销量趋势（月度折线）
    if sales_m_x:
        delta = _pct(sales_m_y[-1], sales_m_y[0])
        peak_i = int(np.argmax(sales_m_y))
        charts.append(_chart(
            "sales-trend", "line", "整体销量趋势（月度）",
            x=sales_m_x, series=[{"name": "销量", "data": sales_m_y, "axis": "left"}],
            factors=["市场规模"],
            interpretation=(f"区间销量{'增长' if (delta or 0) >= 0 else '下滑'} "
                            f"{delta:+}%（首末月对比）；峰值在 {sales_m_x[peak_i]}。"
                            if delta is not None else "销量趋势已绘制。"),
            conclusion="增长还是下降？是否有突变点 / 季节规律？"))

    # 2. 同比增速（年度柱状）
    years, yv = _yearly(df, _mask(df, _SALES))
    if len(years) >= 2:
        bars_x, bars_y = [], []
        for i in range(1, len(years)):
            p = _pct(yv[i], yv[i - 1])
            if p is not None:
                bars_x.append(f"{years[i]} YoY")
                bars_y.append(p)
        if bars_x:
            charts.append(_chart(
                "yoy-growth", "bar", "同比增速（年度）", unit="%",
                x=bars_x, series=[{"name": "YoY 增速", "data": bars_y, "axis": "left"}],
                factors=["市场规模"],
                interpretation=f"最近一年同比 {bars_y[-1]:+}%。是否跑赢品类大盘？",
                conclusion="销量增速 vs 品类大盘——跑赢还是跑输。"))

    # 3. 市场份额（月度曲线） — real share metric if present, else sales index proxy.
    share_x, share_y = _monthly(df, _mask(df, _SHARE))
    if share_x:
        charts.append(_chart(
            "share-curve", "line", "市场份额（月度）", unit="%",
            x=share_x, series=[{"name": "份额", "data": share_y, "axis": "left"}],
            factors=["本品ND", "竞品ND"],
            interpretation=f"份额从 {share_y[0]} 变化到 {share_y[-1]}。",
            conclusion="份额上升还是下降？"))
    elif sales_m_x:
        base = sales_m_y[0] or 1.0
        idx = [round(v / base * 100, 1) for v in sales_m_y]
        charts.append(_chart(
            "sales-index", "line", "销量指数（首月=100，份额代理）",
            x=sales_m_x, series=[{"name": "销量指数", "data": idx, "axis": "left"}],
            factors=["市场规模"],
            interpretation="无直接份额指标，用销量指数代理观察相对走势。",
            conclusion="（建议补充品类/竞品数据以计算真实份额）"))

    # 4. 费用 × 销量（双轴）
    if sales_m_x and spend_m_x:
        # align spend onto the sales month axis
        spend_map = dict(zip(spend_m_x, spend_m_y))
        spend_aligned = [round(spend_map.get(m, 0.0), 1) for m in sales_m_x]
        s_delta = _pct(sales_m_y[-1], sales_m_y[0])
        p_delta = _pct(spend_aligned[-1] or np.nan, spend_aligned[0] or np.nan)
        charts.append(_chart(
            "spend-vs-sales", "dualAxis", "营销费用与销量叠图",
            x=sales_m_x, series=[
                {"name": "销量", "data": sales_m_y, "axis": "left"},
                {"name": "费用", "data": spend_aligned, "axis": "right"}],
            factors=["各类花费"],
            interpretation=(f"费用 {p_delta:+}% vs 销量 {s_delta:+}%——"
                            "费用增加是否带来等比销量增长？"
                            if (p_delta is not None and s_delta is not None) else
                            "费用与销量叠图已绘制。"),
            conclusion="费用效率是否下降（费用涨了销量没涨）？"))

    # 5. 品牌搜索量趋势（折线，领先指标）
    search_x, search_y = _monthly(df, _mask(df, _SEARCH))
    if search_x:
        delta = _pct(search_y[-1], search_y[0])
        charts.append(_chart(
            "search-trend", "line", "品牌搜索 / 声量趋势（领先指标）",
            x=search_x, series=[{"name": "搜索/声量", "data": search_y, "axis": "left"}],
            factors=["品类社媒声量"],
            interpretation=(f"搜索/声量 {delta:+}%（首末月）；领先指标是否健康？"
                            if delta is not None else "搜索/声量趋势已绘制。"),
            conclusion="领先指标预示未来销量压力 / 动能。"))
    return charts


def _table(title: str, columns: list[str], rows: list[list], note: str = "") -> dict:
    return {"title": title, "columns": columns,
            "rows": [[("" if c is None else str(c)) for c in r] for r in rows], "note": note}


def _group_sum(df: pd.DataFrame, mask: pd.Series, by: str) -> dict:
    sub = df[mask & df[by].astype("string").str.len().gt(0)]
    if sub.empty:
        return {}
    return {str(k): float(v) for k, v in sub.groupby(by)["value"].sum().items() if str(k).strip()}


def overview_step(df: pd.DataFrame) -> dict | None:
    charts = build_overview(df)
    return {"id": "step1", "title": "步骤1：全景概览",
            "intro": "快速建立对生意全局的认知，识别最突出的矛盾（如“费用涨了销量没涨”）。",
            "charts": charts, "tables": []} if charts else None


def breakdown_step(df: pd.DataFrame) -> dict | None:
    """步骤2 维度拆解 — 渠道占比 / 渠道效率(方向性ROI) / 区域四象限。"""
    sales_by_ct = _group_sum(df, _mask(df, _SALES), "channel_type")
    spend_by_ct = _group_sum(df, _mask(df, _SPEND), "channel_type")
    charts: list[dict] = []
    tables: list[dict] = []

    # 2.1 各渠道销售额占比（柱状）
    if sales_by_ct:
        total = sum(sales_by_ct.values()) or 1.0
        cts = sorted(sales_by_ct, key=lambda k: -sales_by_ct[k])[:8]
        charts.append(_chart(
            "channel-share", "bar", "各渠道销售额占比", unit="%",
            x=cts, series=[{"name": "占比", "data": [round(sales_by_ct[c] / total * 100, 1) for c in cts], "axis": "left"}],
            factors=["按 channel 下钻"],
            interpretation=f"销售额最高渠道：{cts[0]}（{round(sales_by_ct[cts[0]]/total*100,1)}%）。",
            conclusion="渠道结构是否健康？线上/线下增速差异？"))

    # 2.1b 各渠道效率（方向性 ROI = 销量/费用，建模前近似）
    roi_cts = [c for c in sales_by_ct if spend_by_ct.get(c, 0) > 0]
    if roi_cts:
        roi_cts = sorted(roi_cts, key=lambda c: -(sales_by_ct[c] / spend_by_ct[c]))[:8]
        roi = [round(sales_by_ct[c] / spend_by_ct[c], 2) for c in roi_cts]
        charts.append(_chart(
            "channel-roi", "bar", "各渠道效率（方向性 ROI · 建模前近似）",
            x=roi_cts, series=[{"name": "销量/费用", "data": roi, "axis": "left"}],
            factors=["各渠道花费"],
            interpretation=f"{roi_cts[0]} 效率最高（{roi[0]}）；建模前为方向性参考，非真实 ROI。",
            conclusion="哪个渠道效率最高？真实 ROI 待建模确认。"))

    # 2.3 区域四象限（份额 × 增长）
    sub = df[_mask(df, _SALES) & df["year"].notna()]
    points: list[dict] = []
    if not sub.empty and sub["province_group"].nunique() >= 2:
        g = sub.groupby(["province_group", "year"])["value"].sum().reset_index()
        grand = g["value"].sum() or 1.0
        for region, rg in g.groupby("province_group"):
            rg = rg.sort_values("year")
            vals = rg["value"].to_numpy(dtype=float)
            share = round(float(vals.sum()) / grand * 100, 1)
            growth = _pct(vals[-1], vals[-2]) if len(vals) >= 2 else 0.0
            label = str(region)[:14]
            points.append({"label": label, "x": share, "y": growth or 0.0})
        points = sorted(points, key=lambda p: -p["x"])[:12]
        charts.append({
            "id": "region-quadrant", "type": "quadrant", "title": "区域四象限（份额 × 增长）",
            "x": [], "series": [{"name": "增长", "data": []}], "points": points, "unit": "",
            "factors": ["按 region 下钻"],
            "interpretation": "右上=牛眼市场(高份额高增长)，左上=潜力，右下=成熟，左下=问题市场。",
            "conclusion": "牛眼维持投资 / 成熟降本 / 潜力加大铺货 / 问题诊断原因。", "signoff": ""})

    return {"id": "step2", "title": "步骤2：维度拆解",
            "intro": "将整体指标按渠道、产品、区域、营销活动拆开，定位“问题出在哪个角落”。营销活动拆解是核心。",
            "charts": charts, "tables": tables} if charts else None


def anomaly_step(df: pd.DataFrame, anomalies: list[dict]) -> dict | None:
    """步骤3 异常定位 — 偏离阈值(YoY)的渠道节点 → 柱状 + 异常节点清单。"""
    if not anomalies:
        return {"id": "step3", "title": "步骤3：异常定位",
                "intro": "规则：ROI 降幅>30% 或销量波动>20% 自动沿 L5–L8 下钻。",
                "charts": [], "tables": [_table("异常节点清单", ["维度", "年份", "YoY 变化", "下钻路径"],
                                                [["—", "—", "无显著异常", "—"]])]}
    top = anomalies[:8]
    charts = [_chart(
        "anomaly-bars", "bar", "异常节点 YoY 变化（绝对值排序）", unit="%",
        x=[f"{a['channel']} {a['year']}" for a in top],
        series=[{"name": "YoY", "data": [a["growth_pct"] for a in top], "axis": "left"}],
        factors=["按 channel/region 下钻"],
        interpretation=f"最大异常：{top[0]['channel']} {top[0]['year']} {top[0]['growth_pct']:+}%。",
        conclusion="定位到具体维度交叉点，作为假设生成的靶点。")]
    rows = [[a["channel"], a["year"], f"{a['growth_pct']:+}%",
             "by channel → by region / competitor → by time"] for a in top]
    tables = [_table("异常节点清单", ["维度", "年份", "YoY 变化", "下钻路径（L5–L8）"], rows,
                     note="阈值触发后沿因子树下钻维度定位具体角落。")]
    return {"id": "step3", "title": "步骤3：异常定位",
            "intro": "规则：ROI 降幅>30% 或销量波动>20% 自动沿 L5–L8 下钻，输出异常节点清单。",
            "charts": charts, "tables": tables}


def prior_step() -> dict:
    """步骤5 先验提取 — 先不做（规则已定义，输出给 3.1 先验设置）。"""
    rows = [
        ["抖音弹性不应过高", "截断正态分布", "Normal(0.45,0.1) 截断至 [0.3,0.7]", "抖音相关花费"],
        ["促销存在边际递减", "弹性 = a - b×频次, b>0", "b ~ Gamma(2,2)", "花费（促销优惠）"],
        ["品牌搜索领先销售 1–2 周", "滞后阶数先验", "最大滞后 4 周，峰值在 2 周", "品类社媒声量"],
        ["竞品大促期间我方受损", "交互项系数为负", "β ~ Normal(-0.15,0.05) 截断至负", "竞品品牌媒体花费"],
    ]
    return {"id": "step5", "title": "步骤5：先验提取（先不做）",
            "intro": "本阶段先不做：先验规则已定义，作为 3.1 先验设置的直接上游。",
            "charts": [], "tables": [_table("先验规则（示例）", ["假设内容", "先验形式", "示例", "相关因子"], rows,
                                            note="经客户确认的假设 → 模型数学约束（参见规则库）。")]}
