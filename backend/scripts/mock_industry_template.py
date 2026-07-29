"""Mock a compact industry template (factor tree + interview) for functional beverage.

Saves two KnowledgeTemplates into the template store (data/templates/_index.json)
and writes a readable JSON copy to sample-uploads/. Designed to pair with
sample-uploads/s1-test/materials/ so the factor-tree × materials reconcile has
clear keep / rename / downgrade cases.

Run from backend/:  PYTHONPATH=. .venv/bin/python scripts/mock_industry_template.py
"""
from __future__ import annotations

import json
from pathlib import Path

from app.domain.models import FactorTreeRow, InterviewQuestion, KnowledgeTemplate
from app.store.templates import get_templates

ROOT = Path(__file__).resolve().parents[2]   # repo root (backend/scripts → ../../)
L1, L2 = "food-bev", "beverage"   # functional-beverage projects resolve here


def _r(l1, l2, l3, l4, ind, roi="", contrib=""):
    return FactorTreeRow(l1=l1, l2=l2, l3=l3, l4=l4, indicator=ind,
                         roiRange=roi, contributionRange=contrib)


FACTOR_ROWS = [
    # L1 生意基本盘 · 外部
    _r("生意基本盘", "外部因素", "品类趋势", "市场规模", "市场规模"),
    _r("生意基本盘", "外部因素", "品类趋势", "品类增速", "品类同比增速"),
    _r("生意基本盘", "外部因素", "宏观", "经济", "GDP增速"),          # 材料→rename 宏观经济景气度
    _r("生意基本盘", "外部因素", "季节", "气候", "天气温度指数"),      # 材料未提及→downgrade
    # L1 生意基本盘 · 竞争
    _r("生意基本盘", "竞争因素", "竞品", "竞品促销", "竞品促销强度"),
    _r("生意基本盘", "竞争因素", "竞品", "竞品新品", "竞品新品上市数"),
    # L1 营销因素 · 媒介
    _r("营销因素", "媒介", "TV", "电视", "TV投放金额", roi="0.1~0.5"),
    _r("营销因素", "媒介", "OTV", "网络视频", "OTV投放金额", roi="0.1~0.5"),
    _r("营销因素", "媒介", "社交", "KOL", "社交媒体互动量"),
    # L1 营销因素 · 促销
    _r("营销因素", "促销", "折扣", "力度", "促销折扣率", roi="0.5~1.2"),
    # L1 渠道因素
    _r("渠道因素", "分销", "铺货", "现代渠道", "加权铺货率"),
    _r("渠道因素", "电商", "平台", "GMV", "电商GMV"),
    _r("渠道因素", "电商", "平台", "转化", "电商转化率"),
]

INTERVIEW_QS = [
    InterviewQuestion(category="Leadership", role="总经理", question="今年的生意目标和增长逻辑是什么？"),
    InterviewQuestion(category="Leadership", role="总经理", question="最担心的外部风险是什么（品类/竞争）？"),
    InterviewQuestion(category="Management", role="市场部", question="各渠道占比与各自的角色定位？"),
    InterviewQuestion(category="Management", role="市场部-媒介", question="媒介投放的主力与旺季节奏？"),
    InterviewQuestion(category="Operation", role="促销", question="促销的力度、节奏与前置逻辑？"),
    InterviewQuestion(category="Operation", role="电商", question="电商的核心指标与大促波动？"),
    InterviewQuestion(category="Data", role="数据团队", question="各指标的可获得性、最小颗粒度与历史区间？"),
    InterviewQuestion(category="Data", role="数据团队", question="能否按品牌/区域/渠道/平台拆分，口径是否对齐？"),
]

FACTOR_TPL = KnowledgeTemplate(
    id="tpl-mock-fbev-factor-tree", kind="factor_tree",
    name="Functional Beverage Factor Tree (mock)", industryL1=L1, industryL2=L2,
    builtin=False, factorRows=FACTOR_ROWS)

INTERVIEW_TPL = KnowledgeTemplate(
    id="tpl-mock-fbev-interview", kind="interview",
    name="Functional Beverage Interview Outline (mock)", industryL1=L1, industryL2=L2,
    builtin=False, interviewQuestions=INTERVIEW_QS)


def main() -> None:
    ts = get_templates()
    ts.save(FACTOR_TPL)
    ts.save(INTERVIEW_TPL)

    # Readable JSON copy for inspection / import via PUT /api/templates.
    out = ROOT / "sample-uploads" / "s1-test" / "mock-industry-template.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        [FACTOR_TPL.model_dump(by_alias=True), INTERVIEW_TPL.model_dump(by_alias=True)],
        ensure_ascii=False, indent=2), "utf-8")

    print(f"Saved 2 templates to the store; JSON copy → {out}")
    print(f"  factor_tree: {len(FACTOR_ROWS)} rows · interview: {len(INTERVIEW_QS)} questions "
          f"· industry {L1}/{L2}")
    fbt = ts.best_match("factor_tree", L1, L2)
    fiv = ts.best_match("interview", L1, L2)
    print(f"  best_match(factor_tree, {L1}/{L2}) -> {fbt.id if fbt else None} "
          f"({len(fbt.factor_rows) if fbt else 0} rows)")
    print(f"  best_match(interview,   {L1}/{L2}) -> {fiv.id if fiv else None}")
    print("\n  NOTE: the builtin 'tpl-bev-*' default is first in the list, so best_match")
    print("  still returns it. To make this mock authoritative, delete the builtin:")
    print("    get_templates().delete('tpl-bev-factor-tree'); .delete('tpl-bev-interview')")


if __name__ == "__main__":
    main()
