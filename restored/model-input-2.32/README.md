# model input_2.32 还原产物

由 `backend/scripts/restore_model_input.py` 从
`reference/02.数据智能体/【MMM AI】数据智能体-model input_2.32.xlsx` 生成，可重跑。

设计文档：`docs/superpowers/specs/2026-07-22-restore-model-input-2.32-design.md`

## 目录

| 路径 | 内容 |
|---|---|
| `factor-tree/factor-tree.json` | `FactorTree{rows:[FactorRow]}`，可直接 `PUT /api/projects/{id}/factor-tree` |
| `factor-tree/factor-tree.xlsx` | 同一棵树的人读视图（含 origin / 覆盖月数） |
| `factor-tree/reconciliation.md` | 规划态与实际态的差异逐条对照 |
| `raw/` | 30 个 workbook，按 `数据源` 切片，**明细粒度、中文原列名、脏值保留** |
| `curated/long_table.csv` | 23813 行 19 列 canonical 长表，publish-ready |
| `curated/taxonomy_map.csv` | 业务词表→引擎词表映射，附每条的证据行数 |
| `curated/indicators.csv` | 逐指标 catalog（层级、单位、覆盖区间、缺失率、极值） |
| `qa/profile.md` | 层级稀疏度 + 逐指标覆盖 |
| `qa/ols_smoke.txt` | 验证脚本输出：Y / drivers / R² / n_obs |

## 因子树

共 **85** 行 = 规划 ∪ 实际，每行带 `origin`：

- `both`（37）两边都有
- `planned`（29）规划了但没有数据 —— 在 2.1 因子映射门禁里会是 `pending`，需要人工 ignore
- `data`（19）有数据但未入规划树 —— 已补进树，L1-L4 取其在长表中最频繁的层级路径

层级偏移：颗粒度参考表的 `指标选择` **等于** 数据表的 `数据类型Level5`。
所以 `FactorRow.l1..l4 ← Level1..Level4`，`FactorRow.indicator ← Level5`。
`Level6–L8` 是下钻维度，只在长表上，不进因子树。

## 为什么 `raw/` 不是宽表

源表是**明细流水**，不是聚合表。用全部维度 + 全部 8 层因子路径 + 月 + 指标名做键，
23,813 行只压到 20,699 组，其中 1,140 组的取值互不相同。
例如 `ANP spending 微信立减 / A / AFH / 202409` 下有 6 条不同的 `Spending`
与 6 条不同的 `签约门店数` —— 那是 6 场活动。

源表里没有任何字段能把第 N 条 Spending 和第 N 条 签约门店数 配成一行。
所以做宽表只能二选一：聚合（毁掉明细）或编造配对（凭空造数）。两条都不做，
`raw/` 因此保持明细粒度。`curated/` 不受影响 —— 19 列长表天然容纳明细行，
`build_model_frame` 在 pivot 时本就按 sum 聚合。

## 词表翻译（必须做，不是美化）

`curated/long_table.csv` 的 `l1` 写**引擎词表**，因为 `app/mmm/pivot.py::is_driver_row()`
判定驱动因子的条件是 `l1 ∈ {Marketing Factor, Commercial Factor}`。
若直接写中文 `l1`，OLS 找不到任何 X，模型无法拟合。

映射由 2.32 与 2.24 在自然键上 join **推导**得出（零冲突），不是声明的：

| 业务词表 (2.32) | 引擎词表 (2.24) | 证据行数 |
|---|---|---|
| KPI | KPI | 4459 |
| 促销优惠 | Commercial Factor | 1076 |
| 消费者需求驱动 | Marketing Factor | 662 |
| 渠道成交驱动 | Marketing Factor | 519 |
| 生意基本盘 | Baseline Factor | 338 |

`METRICS类型` 保留**单位族**语义（`箱数`/`RMB`/`Volume`/`百分比`…），
因为 `pivot.is_money_metric()` 靠它决定 ROI 的单位。唯一改名：`花费 → Spending`。

## Y 的口径断层

`l1='KPI'` 的行里，指标名按渠道分裂，且**跨渠道不同质**：

| 渠道 | 销量口径 | 金额口径 |
|---|---|---|
| MT | 谈判点出货箱数 | 谈判点出货金额 |
| TT / AFH / WS | Compass完成箱数 | Compass完成金额 |
| EC | Volume | GMV |
| O2O / 社区团购 | 箱数 | GMV |

销量与金额两类**都保留为 Y 候选**，不重命名、不合并。
`pivot._pick_y_metric()` 默认按"月覆盖优先 + 销量优先"选，2.5y 门禁可人工覆盖。
跨渠道汇总的 Y 不可比 —— 默认 Y 在单个 model object（= `channel_type` 分组）内选取。

## 从头跑一个 Case 需要什么

**这个文件夹只有数据，不含 S1 需要的文档。** S1 的三个上传门禁要的是文本材料，
本还原产物覆盖不到，必须另外提供：

| 门禁 | category | 需要什么 | 本次贯通用的 |
|---|---|---|---|
| 1.0a | `project_background` | SOW / 立项简报 | `reference/01.商业智能体/【MMM AI】商业智能体-Scope_1.0.xlsx` |
| 1.1a | `industry_reference` | 品牌竞品报告、内部材料 | 同目录 `行业知识_1.1.xlsx` + `factor&data_request_1.2.xlsx` |
| 1.4a | `interview_minutes` | 访谈录音或纪要 | 同目录 `访谈框架及纪要_1.32/纪要/*.docx`（12 份） |
| 2.1  | `data` | 建模数据 | **本文件夹** `curated/long_table.xlsx`（或 `raw/` 30 份） |

端到端复现（真实后端 + 真实 LLM，无 mock）：

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 &
PYTHONPATH=. .venv/bin/python -m scripts.e2e_case
```

跑通过程中撞到的断点与假数问题，全部记在 `qa/e2e-findings.md`。

## 重新生成

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m scripts.restore_model_input
PYTHONPATH=. .venv/bin/python -m scripts._test_restore
```

`raw/` 与 `curated/long_table.*` 体积大且完全可再生成，已加入 `.gitignore`。
