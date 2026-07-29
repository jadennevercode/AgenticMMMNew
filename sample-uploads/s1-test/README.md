# S1 测试台（mock 数据）

用于手动/自动测试 2026-07-28 交付的三组 S1 功能：
1. 需求一 · Factor tree 模板基线与上传材料对账（keep/rename/downgrade）
2. 访谈 · 只提问 + 按真实纪要按部门重建 + 抽取新问题
3. 需求二 · 数据请求按访谈纪要提出指标 add/remove（人工 Accept/Reject）

> ⚠️ 三者都依赖真实 LLM。跑之前需在 App 的 Settings 配好可用的 LLM
> （本机 Volcano Ark `ark-code-latest` 曾因 CodingPlan 订阅过期而 HTTP 400 失败）。
> 遵循 "no mock data"：无材料/纪要则不产出，不会造假。

## 目录

- `nike/` — **Nike（运动鞋服）测试项目**的上传件（本轮主用）
  - `背景_SOW.md` → 上传到 `project_background`
  - `行业材料_运动鞋服市场brief.md` → `industry_reference`
  - `市场部访谈.txt` / `电商部访谈.txt` / `销售部访谈.txt` → `interview_minutes`
- `materials/` `minutes/` — 早期通用（功能饮料向）样例
- `mock-*.xlsx` / `mock-industry-template.json` — 功能饮料 mock 模板的可上传/可读副本

## 生成脚本（backend/scripts/）

- `mock_industry_template.py` — 造功能饮料 mock 模板，存入模板库 + 写 JSON 副本
- `mock_template_xlsx.py` — 把 mock 模板导出为可上传的 `.xlsx`（因子树 / 访谈）

Sportswear（Nike）用的模板是本轮直接写进模板库的（`tpl-sportswear-*`，
industry `apparel/sportswear`），best_match 命中 13 行因子 + 8 问。

## Nike 测试：复跑步骤

```bash
# 1) 确保 sportswear 模板在库（若清过库，重跑写库片段即可）
# 2) 项目已建为 nike-q3（apparel/sportswear/sport-shoe），5 个文件已上传
API=http://127.0.0.1:8000/api/projects/nike-q3
curl -XPOST $API/reset
curl -XPOST $API/run -H 'content-type: application/json' -d '{"autopilot":true}'
curl $API/run/status        # 轮询到 running:false
curl $API/state             # 看产物
```

## 埋好的验证点

- **对账（需求一）**：`天气温度指数` → 材料未提 → 应 **downgrade「待确认」**；
  `竞品促销强度` → 材料称"友商折扣力度" → 可能 **rename**；其余 **keep**。
- **访谈重建**：应按 **市场部 / 电商部 / 销售部** 三个真实部门重组；抽出新问题
  （市场部"会员/NRC 复购"、电商部"直播带货 ROI 单独看"）。
- **数据请求提案（需求二）**：电商部 → **add 会员复购率**（电商/平台）；
  销售部 → **remove 经销商出货**（批发/经销）。审阅面板逐条 Accept/Reject。
