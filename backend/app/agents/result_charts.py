"""Build ReviewData chart books for the S4 modeling-review and S5 reporting
dashboards from real ``MmmModelResult`` dicts (``st.analysis['candidates']`` /
``st.analysis['picked']``).

Every number here comes from the MMM engine — this module only reshapes the
already-computed diagnostics into the ``review`` chart schema the frontend
``ReviewChartView`` renders. Nothing is fabricated or LLM-authored.

A chart dict mirrors ``ReviewChart`` in the frontend::

    {"id","type": line|bar|dualAxis|share|quadrant|waterfall,"title",
     "x":[labels],"series":[{"name","data":[..],"axis":"left|right"}],
     "unit","factors":[..],"interpretation","conclusion","signoff":""}
"""
from __future__ import annotations

# Keep dashboards readable and payloads bounded.
MAX_OBJECTS = 5
MAX_DRIVERS_CHART = 8
MAX_RESPONSE_CHANNELS = 2
_CAND_LABELS = ["A", "B", "C", "D", "E"]


def _chart(cid: str, ctype: str, title: str, *, x=None, series=None, unit="",
           factors=None, interpretation="", conclusion="") -> dict:
    return {
        "id": cid, "type": ctype, "title": title, "x": x or [], "series": series or [],
        "unit": unit, "factors": factors or [], "interpretation": interpretation,
        "conclusion": conclusion, "signoff": "",
    }


def _table(title: str, columns: list[str], rows: list[list], note: str = "") -> dict:
    return {"title": title, "columns": columns,
            "rows": [[("" if c is None else str(c)) for c in r] for r in rows], "note": note}


def _driver_labels(cand: dict, keys: list[str]) -> list[str]:
    """Short human labels for driver keys via the stored drivers_meta."""
    meta = (cand.get("meta") or {}).get("drivers_meta") or {}
    out: list[str] = []
    for k in keys:
        m = meta.get(k) or {}
        out.append(str(m.get("metric", k))[:18])
    return out


def _compact(n: float) -> str:
    a = abs(n)
    if a >= 1e8:
        return f"{n / 1e8:.1f}亿"
    if a >= 1e4:
        return f"{n / 1e4:.1f}万"
    if a >= 1e3:
        return f"{n / 1e3:.1f}k"
    return f"{round(n, 2)}"


def _fit_chart(obj: str, cand: dict) -> dict | None:
    periods = cand.get("periods") or []
    actual = cand.get("actual") or []
    fitted = cand.get("fitted") or []
    if not periods or not actual or not fitted:
        return None
    return _chart(
        f"fit-{obj}", "line", f"拟合优度：实际 vs 预测（{obj}）",
        x=periods,
        series=[
            {"name": "实际", "data": actual, "axis": "left"},
            {"name": "预测", "data": fitted, "axis": "left"},
        ],
        factors=["模型拟合"],
        interpretation=(f"R²={cand.get('r2', 0):.2f} · adjR²={cand.get('adj_r2', 0):.2f} · "
                        f"MAPE={cand.get('mape', 0):.1f}% · DW={cand.get('durbin_watson', 0):.2f}。"),
        conclusion="两线越贴合，模型解释力越强；系统性偏离处提示缺失变量。")


def _residual_chart(obj: str, cand: dict) -> dict | None:
    periods = cand.get("periods") or []
    resid = cand.get("residuals") or []
    if not periods or not resid:
        return None
    return _chart(
        f"resid-{obj}", "bar", f"残差诊断（{obj}）",
        x=periods, series=[{"name": "残差", "data": resid, "axis": "left"}],
        factors=["残差健康度"],
        interpretation="残差应围绕 0 随机波动；持续同号或漏斗形提示模型设定问题。",
        conclusion="配合 DW 统计量判断自相关。")


def _contribution_chart(obj: str, cand: dict) -> dict | None:
    contrib = cand.get("contribution") or {}
    if not contrib:
        return None
    keys = sorted(contrib, key=lambda k: -abs(contrib[k]))[:MAX_DRIVERS_CHART]
    labels = ["基线"] + _driver_labels(cand, keys)
    data = [round(cand.get("baseline_pct", 0.0), 1)] + [round(contrib[k], 1) for k in keys]
    top = _driver_labels(cand, keys[:1])
    return _chart(
        f"decomp-{obj}", "bar", f"贡献分解（{obj}）", unit="%",
        x=labels, series=[{"name": "贡献占比", "data": data, "axis": "left"}],
        factors=["销量分解"],
        interpretation=(f"基线占 {cand.get('baseline_pct', 0):.1f}%；"
                        f"最大驱动因子：{top[0] if top else '—'}。"),
        conclusion="各因子占比之和 + 基线 = 100%；关注可操作因子的贡献。")


def _roi_chart(obj: str, cand: dict) -> dict | None:
    roi = cand.get("roi") or {}
    if not roi:
        return None
    keys = sorted(roi, key=lambda k: -roi[k])[:MAX_DRIVERS_CHART]
    labels = _driver_labels(cand, keys)
    data = [round(roi[k], 2) for k in keys]
    return _chart(
        f"roi-{obj}", "bar", f"各渠道 ROI（{obj}）",
        x=labels, series=[{"name": "ROI", "data": data, "axis": "left"}],
        factors=["渠道效率"],
        interpretation=(f"ROI 最高：{labels[0]}（{data[0]:+.2f}）。"
                        if labels else "暂无可计算 ROI 的付费渠道。"),
        conclusion="高 ROI + 低投入 = 有加投空间；低 ROI + 高投入 = 需复盘。")


def _response_charts(obj: str, cand: dict) -> list[dict]:
    curves = cand.get("response_curves") or {}
    spend_cols = (cand.get("meta") or {}).get("spend_cols") or []
    picks = [c for c in spend_cols if c in curves][:MAX_RESPONSE_CHANNELS]
    if not picks:
        picks = list(curves)[:MAX_RESPONSE_CHANNELS]
    out: list[dict] = []
    for c in picks:
        pts = curves.get(c) or []
        if not pts:
            continue
        label = _driver_labels(cand, [c])[0]
        x = [_compact(float(p[0])) for p in pts]
        y = [round(float(p[1]), 2) for p in pts]
        out.append(_chart(
            f"resp-{obj}-{c}", "line", f"响应/饱和曲线：{label}（{obj}）",
            x=x, series=[{"name": "预测销量", "data": y, "axis": "left"}],
            factors=["饱和度 / 边际回报"],
            interpretation="曲线斜率=边际 ROI；趋平段说明该渠道趋于饱和，加投回报下降。",
            conclusion="用于判断加投空间与最优投放点。"))
    return out


def _due_to_chart(obj: str, cand: dict) -> tuple[dict | None, dict | None]:
    due = cand.get("due_to") or {}
    segs = due.get("segments") or []
    if not segs:
        return None, None
    top = segs[:MAX_DRIVERS_CHART]
    labels = [str(s["source"])[:16] for s in top]
    data = [round(float(s["delta"]), 2) for s in top]
    chart = _chart(
        f"dueto-{obj}", "waterfall", f"增长归因 Due-to（{obj}）",
        x=labels, series=[{"name": "Δ贡献", "data": data, "axis": "left"}],
        factors=["期间变化归因"],
        interpretation=(f"预测销量由 {_compact(due.get('value_a', 0))} → "
                        f"{_compact(due.get('value_b', 0))}；正向（青）拉动、负向（红）拖累。"),
        conclusion="定位近期增长/下滑的主要来源因子。")
    table = _table(
        f"Due-to 明细（{obj}）", ["区间", "预测销量均值"],
        [[due.get("period_a", "前段"), _compact(due.get("value_a", 0))],
         [due.get("period_b", "后段"), _compact(due.get("value_b", 0))]],
        note="期间对比：后段均值 − 前段均值，按因子拆解。")
    return chart, table


def _recommended(cands: list[dict]) -> dict | None:
    """The candidate the technical review defaults to (index 1 = B)."""
    if not cands:
        return None
    return cands[1] if len(cands) > 1 else cands[0]


def diagnostics_review(candidates: dict[str, list[dict]]) -> dict:
    """S4 modeling-review dashboard: candidate comparison + per-object fit,
    residuals, decomposition and response curves for the recommended candidate."""
    steps: list[dict] = []
    objects = [o for o in candidates if candidates[o]][:MAX_OBJECTS]

    # Step 1 — candidate comparison for the representative object.
    rep = objects[0] if objects else None
    if rep:
        cands = candidates[rep]
        labels = [f"候选 {_CAND_LABELS[i] if i < len(_CAND_LABELS) else i}" for i in range(len(cands))]
        r2 = [round(c.get("r2", 0.0), 3) for c in cands]
        mape = [round(c.get("mape", 0.0), 1) for c in cands]
        rows = [[labels[i], f"{c.get('r2', 0):.2f}", f"{c.get('mape', 0):.1f}%",
                 f"{c.get('baseline_pct', 0):.1f}%",
                 "✓" if not c.get("red_flags") else f"{len(c['red_flags'])} 项"]
                for i, c in enumerate(cands)]
        steps.append({
            "id": "cand-compare", "title": "步骤1：候选模型对比",
            "intro": f"以 {rep} 为代表，对比各候选的拟合与误差，辅助最终选型（推荐候选 B）。",
            "charts": [
                _chart("cand-r2", "bar", f"候选 R² 对比（{rep}）", x=labels,
                       series=[{"name": "R²", "data": r2, "axis": "left"}], factors=["拟合优度"],
                       interpretation="R² 越高拟合越好，但需兼顾 MAPE 与业务合理性，避免过拟合。",
                       conclusion="选型优先级：① 契合业务判断 ② 分解合理 ③ 统计拟合。"),
                _chart("cand-mape", "bar", f"候选 MAPE 对比（{rep}）", unit="%", x=labels,
                       series=[{"name": "MAPE", "data": mape, "axis": "left"}], factors=["误差率"],
                       interpretation="MAPE 越低预测误差越小；基准区间 5–15%。",
                       conclusion="结合 R² 综合判断。"),
            ],
            "tables": [_table("候选诊断汇总", ["候选", "R²", "MAPE", "基线", "约束"], rows)],
        })

    # One step per object — fit / residual / decomposition / response.
    for obj in objects:
        cand = _recommended(candidates[obj])
        if not cand:
            continue
        charts: list[dict] = []
        for c in (_fit_chart(obj, cand), _residual_chart(obj, cand), _contribution_chart(obj, cand)):
            if c:
                charts.append(c)
        charts.extend(_response_charts(obj, cand))
        if not charts:
            continue
        flags = cand.get("red_flags") or []
        steps.append({
            "id": f"diag-{obj}", "title": f"模型诊断：{obj}",
            "intro": f"推荐候选的拟合曲线、残差、贡献分解与饱和曲线。"
                     + (f" ⚠ 红旗：{'; '.join(flags)[:80]}" if flags else ""),
            "charts": charts, "tables": [],
        })

    return {"steps": steps}


def results_review(picked: dict[str, dict]) -> dict:
    """S5 reporting dashboard: contribution, ROI, response curves and the
    Due-to growth-attribution waterfall for the picked model per object."""
    steps: list[dict] = []
    objects = [o for o in picked if picked[o]][:MAX_OBJECTS]

    # Group by concern, one chart per object inside each concern.
    contrib_charts = [c for o in objects if (c := _contribution_chart(o, picked[o]))]
    if contrib_charts:
        steps.append({
            "id": "contribution", "title": "贡献分解 Contribution",
            "intro": "把销量拆成基线与各营销/商业因子的贡献占比，回答“生意由什么驱动”。",
            "charts": contrib_charts, "tables": [],
        })

    roi_charts = [c for o in objects if (c := _roi_chart(o, picked[o]))]
    if roi_charts:
        steps.append({
            "id": "roi", "title": "渠道 ROI",
            "intro": "每个付费渠道的真实 ROI（增量销量 / 花费），用于投放效率排序与预算建议。",
            "charts": roi_charts, "tables": [],
        })

    resp_charts: list[dict] = []
    for o in objects:
        resp_charts.extend(_response_charts(o, picked[o]))
    if resp_charts:
        steps.append({
            "id": "response", "title": "响应 / 饱和曲线",
            "intro": "各渠道花费与预测销量的响应曲线，斜率即边际 ROI，趋平即饱和。",
            "charts": resp_charts, "tables": [],
        })

    dueto_charts: list[dict] = []
    dueto_tables: list[dict] = []
    for o in objects:
        chart, table = _due_to_chart(o, picked[o])
        if chart:
            dueto_charts.append(chart)
        if table:
            dueto_tables.append(table)
    if dueto_charts:
        steps.append({
            "id": "due-to", "title": "增长归因 Due-to",
            "intro": "把预测销量的期间变化按因子拆解（后段均值 − 前段均值），定位增长/下滑来源。",
            "charts": dueto_charts, "tables": dueto_tables,
        })

    return {"steps": steps}
