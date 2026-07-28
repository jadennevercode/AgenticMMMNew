# OLS Regression Test (2.5) 重构 — By-L4 渐进式指标甄选 + L4 级 ROI/Contribution

日期：2026-07-22 · 状态：待实现 · 分支：feat/global-model-config

## 1. 目标

把 2.5 的核心产出从「拟合一次给结果」升级为「多轮 RunOLS，为每个 L4 甄选唯一最优
Indicator」，并解耦 ROI 的分子分母，使任何 indicator 代表 L4 入模时该 L4 都有可算的 ROI。

三条顶层需求：

1. **甄选**：一个 L4 有 k 个候选 indicator → 跑 k 次完整模型（每次只换该 L4 的代表），
   按 R² + Knowledge 区间裁决出唯一胜者，再进入下一个 L4。
2. **交互**：用户按 L4 渐进式看到每次 Run 的真实数字与裁决过程；人保留覆盖权。
3. **工具化**：甄选的每次 Run 都是标准 `ToolInvocation`，可在 Tools 模块追溯。

非目标（明确不做）：

- 不做多轮坐标下降（单遍扫描 + 可选复核遍）；
- 不做 adstock 尾部补偿（在工具文档 `method` 中如实写明该局限）;
- 不引入业务角色优先级（花费>曝光>互动 已被否决）；
- 不新增每-L4 人工门（覆盖权集中在既有 d-2.5x 一处）。

## 2. 方法论

### 2.1 为什么不是「每个 indicator 单独回归」

单变量回归中 β 吸走所有共线因子的效应，每个候选的 ROI/Contribution 都虚高，
比较无效。**ROI 与 Contribution 只在完整模型语境下有意义**，因此每次 Run 都是
所有 L4 在场的完整拟合，仅替换目标 L4 的代表指标（受控变量是"其他 L4"）。

### 2.2 扫描算法（单遍、数据驱动，无角色先验）

```
输入: 长表, model objects, 候选分组 {L4 → [indicators]}, Y(2.5y 已确认), Knowledge 区间
预筛: 剔除 ledger 前五层已否决 / 覆盖 < MIN_MONTHS / 常量列的候选
起点: 每个 L4 的初始代表 = 2.4 stat_scorecard 中 |pearson| 最高的候选
顺序: L4 按其最强候选的 |pearson| 降序（强因子先定，弱因子在稳定语境中比较）

for L4 in 顺序:
    for cand in L4.candidates:            # 单候选 L4 也跑一次（确认性 Run）
        fit = run_mmm(include = 其他L4当前代表 ∪ {cand})   # 每个 model object 一次, 聚合
        run 记录: adjR², 系数/t/符号, VIF, L4-ROI, L4-Contribution, 区间比对
    硬淘汰: 付费候选系数为负 · VIF > 10
    评分:   有 Knowledge 区间 → W_KNOWLEDGE(0.6)×区间对齐度 + W_STAT(0.4)×归一化 adjR²
            无区间           → 纯 adjR²（UI 标 "no benchmark"）
            (adjR² 在该 L4 的 k 次 Run 内做 min-max 归一化；k=1 时取 1)
    胜者 = argmax(评分); 锁定为该 L4 当前代表
收尾: 以全部胜者做一次全量拟合（最终确认 Run）
```

- 总拟合次数 = Σkᵢ + 1（次数 × model objects），闭式 OLS 亚毫秒级，秒级完成。
- 全部候选被硬淘汰的 L4 → 状态 `noViable`，不进模，UI 明示（不静默消失）。
- 区间对齐度 = ROI、Contribution 各自到区间的归一化距离（区间内=1，线性衰减），取均值；
  仅当 ROI 单位为 money（复用现有 `roi_money` 纪律）才与 Knowledge 金额区间比对。
- 多 model object：逐 object 拟合后按现有 `_collect_records` 的方式取均值聚合。
- `verify_pass` 开关（默认关）：胜者集确定后复扫一遍，报告是否有胜者变动（不自动改选）。
- 权重 `W_KNOWLEDGE=0.6 / W_STAT=0.4` 为 selector 显式常量，后续可迁入 Knowledge 配置。

已知局限（如实呈现）：单遍扫描有路径依赖，按因子强度排序缓解；`OlsSelection`
记录扫描顺序供审计。

### 2.3 ROI 解耦（分子来自入模指标，分母来自 L4 Spending）

```
现在:  ROI_c  = (β_c · Σ X_c^transformed) / Σ raw_spend_c        仅 c ∈ spend_cols
之后:  ROI_L4 = Σ_{c∈该L4入模列} (β_c · Σ X_c^transformed) × 单位换算 / Σ L4_Spending_raw
```

- `build_model_frame` 新增采集 `ModelFrame.l4_spend: dict[norm_l4, pd.Series]`：
  从长表按 `(l4, _is_spend)` 抽取每 L4 的 Spending 月度序列，与模型窗口对齐。
  **不进设计矩阵**，只作 ROI 分母。同 L4 多条 Spending → 求和为 L4 总花费，明细保留。
- 入模列本身是花费 → 分母即其自身 raw 序列（与现行为完全一致，向后兼容）。
- 该 L4 无 Spending → ROI 为空，`roi_denominator_source: "none"`，不猜。
- 每列 meta 新增 `roi_denominator_source: "self" | "l4_spend:<metric>" | "none"`。
- 单位纪律不变：money Y → revenue/spend；volume Y + price_per_unit → revenue/spend；
  否则 volume/spend 且不与 Knowledge 金额区间比对。
- **边界钉死**：「无论入不入模」指 Spending 列不必入模；L4 必须有代表入模才有
  拟合 ROI。整个 L4 不在模型里 → 无系数无增量，UI 标 "not in model — no fitted ROI"。

### 2.4 Contribution 升到 L4 口径

- 计算不动（share-of-actual-Y，分母 = mean(actual Y)，controls 折入 baseline）。
- 汇报单位从列升到 L4：`contribution_L4 = Σ 该L4入模列 contribution`。甄选后每 L4
  恰一列；legacy 自动路径多列同 L4 则求和，消除报告中同一因子出现两次的问题。
- `MmmModelResult` 新增 `l4_rollup: {l4: {contribution, roi, roi_denominator_source,
  indicators: [...]}}`；2.5r 树与 S4/S5 报表从 rollup 取数，与 Knowledge
  （本就是 L4/indicator 粒度）对齐。

## 3. 流程与架构变化

### 3.1 Blueprint（`blueprint.py` + `scenario.ts` 同步）

```
现在:  2.5 propose → 2.5y 确认Y → 2.5x 勾变量 → 2.5p 参数 → 2.5r 拟合
之后:  2.5 propose → 2.5y 确认Y → 2.5s 甄选扫描(M,新) → 2.5x 按L4复核胜者 → 2.5p → 2.5r
```

- **2.5s** "Select indicators per factor"，klass M（确定性计算，理由模板生成，无 LLM），
  `depends_on: ["2.5y"]`，produces `[]`（结果写入 `st.ols_config.selection`，
  re-render `a-ols-test` 同 2.5 的模式）；2.5x 的 `depends_on` 改为 `["2.5s"]`。
- **2.5x 语义升级**：panel `ols-x` 从扁平勾选列表 → 按 L4 分组、胜者预勾选、
  落选者带对比数字可改勾。人的覆盖权仍落在 d-2.5x，不新增门。
- 下游零改动：胜者最终落地形式就是既有 `x_candidates[].selected`，
  `ledger.model_selection()` / 2.6 / 3.2 原样工作。

### 3.2 新模块 `app/mmm/selector.py`（纯函数，~250 行）

```python
def select_indicators(long_df, objects, groups, *, y, params, exclude,
                      knowledge_ranges, verify_pass=False) -> SelectionResult
# SelectionResult: 扫描顺序 · 每 Run 完整记录 · 每 L4 胜者+理由 · noViable 列表
```

无状态、无 IO，输入输出可独立测试；内部经 `run_mmm` 调用（untraced）。

### 3.3 工具注册（`tools/registry.py`）

- 新工具 `model.select_indicator`（category `model`）：wraps
  `mmm.selector.select_indicators`，**每次 Run 记一条 ToolInvocation**
  （taskId=2.5s；args=L4/候选；result=评分摘要）— 前端渐进展示的数据源。
  内部 run_mmm 走 untraced 路径（符合「tracing 默认 untraced」约定）。
- `model.ols` 不动（2.5r 仍每 object 一条）；其 `method` 文档补 L4-ROI 语义
  与 adstock 尾部截断局限。
- 铁律不破：wrapper 是 identity wrapper，工具层零算术，`_test_tools.py` 加断言。

### 3.4 领域模型（`domain/models.py` ↔ `types.ts` 同步）

```
OlsSelectionRun   { l4, indicator, adjR2, coef, tValue, vif, roi, roiUnit,
                    roiDenominatorSource, contribution, roiStatus, contributionStatus,
                    score, scoreKnowledge, scoreStat, eliminated, eliminatedReason }
OlsSelectionGroup { l4, order, candidates: [OlsSelectionRun], winner, rationale,
                    status: "decided" | "noViable" | "single" }
OlsSelection      { order: [l4...], groups: [OlsSelectionGroup], finalRun,
                    verifyPass?, sweptAt }
OlsConfig         + selection: OlsSelection | None
OlsXCandidate     + l4Group / selectionScore / selectionRationale（分组渲染用）
MmmModelResult    + l4_rollup（见 2.4）
```

注意 `ProjectState` 本体 snake_case 序列化的既有约定 — 新字段全部挂在
`OlsConfig`（CamelModel）之下，不触碰 ProjectState 顶层。

### 3.5 前端交互（`OlsStepPanel.tsx` + 新子组件）

拟合瞬间完成，**不做假延时**：后端一次算完落库，前端做**回放动画**。

- Selection 步骤视图：左侧 L4 进度轨（pending / sweeping / decided / noViable），
  右侧当前 L4 的 Run 卡片流（候选名 → 数字滚入 → 区间比对着色 → 裁决卡）。
- 「跳到结果」常驻；已裁决 L4 折叠为一行摘要；刷新页面不丢进度（数据在 state 里）。
- 2.5x 视图按 L4 分组；ROI 分母来源徽标（self / L4 spending / none）。
- 产品文案全英文（product-english-only 约定）。

### 3.6 自证循环的处理（HIGH 风险的正面回应)

Knowledge 区间在 2.5s 当了**选择判据**，2.5r 就不能再把同一区间当**独立校验**。
2.5r 对参与过甄选的指标改口径：展示同 L4 全体候选对比、标注「相对最优」，
不再宣称「验证通过」。`_classify` 增加来源标记以区分两种口径。

## 4. 实施阶段

| # | 内容 | 关键文件 | 验证 |
|---|---|---|---|
| 1 | `l4_spend` 采集 + `_roi` 解耦 + `l4_rollup` + meta 溯源 | `mmm/pivot.py` `mmm/engine.py` | 合成单测：曝光入模×花费不入模 → ROI 与花费入模情形数量级一致；花费入模 → 数值与现版本完全一致 |
| 2 | `selector.py` + 已知答案合成单测 | `app/mmm/selector.py`（新） | 构造已知最优解，断言胜者/顺序/淘汰 |
| 3 | 工具注册 + per-Run tracing + identity 断言 | `tools/registry.py` `tools/_test_tools.py` | wrapper == direct call |
| 4 | `OlsSelection` 域模型 + blueprint 2.5s + engine/registry 接线 + `build_ols_proposal` 按 L4 分组预勾选 | `domain/models.py` `blueprint.py` `agents/ols_review.py` `agents/registry.py` | `heal_state` 对旧项目回填 2.5s |
| 5 | 契约同步 + `_collect_records` 改读 `l4_rollup` | `types.ts` `scenario.ts` `agents/ols_review.py` | tsc 通过 |
| 6 | Selection 回放视图 + 2.5x L4 分组 + 分母徽标 | `OlsStepPanel.tsx` + 新子组件 | visual-check 走查 |
| 7 | 冒烟 + 真实数据全流程 | `tests/test_api_smoke.py` | 2.5s 节点入冒烟路径 |

复杂度 MEDIUM-HIGH：后端 ~2 天 · 前端 ~1 天 · 测试联调 ~0.5 天。

## 5. 风险

| 级别 | 风险 | 缓解 |
|---|---|---|
| HIGH | 自证循环（Knowledge 既当判据又当校验） | §3.6 |
| MEDIUM | 分子分母口径错位：曝光含自然流量时 ROI 高估 | 分母来源徽标 + UI 提示口径 |
| MEDIUM | 单遍扫描路径依赖 | 强度排序 + 顺序可审计 + `verify_pass` |
| MEDIUM | 同 L4 多条 Spending 分母取谁 | 求和为总花费，明细可展开 |
| LOW | 某些 L4 无 Spending（reference 数据） | `"none"` 优雅降级，冒烟覆盖 |
| LOW | Run 卡片过多回放冗长 | 跳到结果 + 已裁决折叠 |

## 6. 既定决策记录

1. 评分权重 0.6/0.4，显式常量（用户确认）。
2. 覆盖权只在 2.5x 一处（用户确认）。
3. 业务角色优先级（花费>曝光>互动）**不采用**（用户否决）；起点/顺序纯数据驱动。
4. 渐进体验 = 前端回放真实数据，无后端假延时。
5. 「无论入不入模」的准确语义 = Spending 列不必入模；L4 需有代表入模才有拟合 ROI。
