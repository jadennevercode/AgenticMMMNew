# S2 · Data Intake & Validation — 诊断报告 / 修复规划 / SPEC

- 日期：2026-07-22
- 分支：`feat/global-model-config`
- 范围：Stage `s2`（任务 2.1 → 2.6d）的后端逻辑 + 前端交互
- 目标：把 S2 从"能跑完但结果可能是假的"变成**一条连贯的、真实项目可端到端跑通的链路**
- 状态：设计文档，**未动任何代码**

---

## 0. TL;DR

S2 今天在**演示路径**（seeded `danone-mizone` + autopilot）下是通的；在**真实路径**（新项目 + 真实上传 + 交互模式）下不通，且失败是静默的。

三句话总结：

1. **走不下去** — 交互模式下新项目卡死在 2.1 闸门，因为前端的放行条件（Project-Folder `data` 分类有已解析文件）和后端的放行条件（`mapping_complete`）是两套互不相认的规则。
2. **跑完是假的** — 只要项目数据稍有不足，`model_df` 会静默返回 23.8k 行 Danone 数据，2.2–2.6 全程无一处报错，用户拿到的是别人的模型。
3. **裁决不算数** — 六层 ledger 里，signoff 层永远无法触发（前端只写内存），d-2.2/d-2.4/d-2.6 三个人工裁决没有任何下游 effect，2.5r 又绕开了 `model_selection`，所以人在 S2 签核的模型和 S4 实际训练的模型设计矩阵不同。

修复分四阶段（P0 打通 → P1 自洽 → P2 可见 → P3 收尾）。**P0 单独交付即可让一个真实新项目走通 S2**；P1 让走通的结果可信；P2 让用户看得懂；P3 清理。

---

## 1. 验收标准：什么叫"连贯的真实可跑通 Case"

任何修复完成的判定，都以下面这条**单一验收剧本**为准。它不依赖 `reference/`，不依赖 autopilot。

### 验收剧本 R1（P0 的退出条件）

1. 从落地页新建项目 `Acme Q3`（非 `danone-mizone`），行业任选。
2. 上传 SOW / 材料 / 会议纪要，跑完 S1，得到一棵真实的 FactorTree。
3. 在 Data Engine 上传真实原始数据，建 asset、配 transform、Publish 出若干 indicator。
4. 回到 Project → S2 → 2.1：
   - 页面**必须**显示 `mapped / ignored / pending` 三个计数；
   - 每一行 pending 都能在**同一屏**或一次点击内解决（bind 或 ignore）；
   - 全部解决后闸门**必须**可提交，且 `parsedCount` 不再是前置条件。
5. 交互模式（`autopilot=false`）依次走 2.2 → 2.2d → 2.3 → 2.3a → 2.3s → 2.4 → 2.4d → 2.5 → 2.5y/x/p → 2.5r → 2.6 → 2.6d，**中途不得跳过任何 H 节点**。
6. 全程任一 artifact 里出现的数字，其来源**必须**是本项目的数据。若本项目数据不可用，链路必须**显式停下并说明原因**，而不是换成 reference。

### 验收剧本 R2（P1 的退出条件）

在 R1 的基础上，人工做出真实裁决并验证其后果可观测：

| 动作 | 必须发生的可观测后果 |
|---|---|
| 2.1 把某个 factor row 标 `ignore` | 该 factor 的指标**不出现在** 2.2 记分卡里 |
| 2.2d 把某指标 disposition 设为 `drop` | 该指标**不出现在** 2.4 记分卡、2.5 候选、2.6 主表 |
| 2.3s 把某 L3 factor 签为 `no` | 刷新页面后签核仍在；该 L3 全部指标在 2.4 起消失 |
| 2.3a 接受一张 `event` 卡 | 2.5r 的拟合**必须**包含该窗口的 dummy control（在 build process 中可验证） |
| 2.5x 取消勾选某变量 | 2.5r 与 2.6 的变量列表**一致地**少掉该变量 |
| 2.6d 锁定 | 状态被持久化；3.2 训练使用的选择与 2.5r 拟合使用的选择**完全相同** |

---

## 2. 诊断报告

严重度定义：
- **S0 断链** — 用户走不下去，或结果确定是错的。
- **S1 静默失真** — 跑得通，但结果可能与用户数据无关，且无任何提示。
- **S2 逻辑不自洽** — 各层之间互相矛盾，或人工输入被丢弃。
- **S3 可见性/体验** — 逻辑对，但用户看不懂、看不到、误操作。

### 2.1 断链（S0）

| ID | 问题 | 证据 |
|---|---|---|
| **D1** | **2.1 闸门前端永远打不开。** `canSubmit = parsedCount > 0 && …`，`parsedCount` 只数 Project-Folder `data` 分类；Data Engine 的原始上传进 `raw_data`。后端 `submit_assignment` 已允许 `bool(st.indicators) or _mapping_complete(st)` 放行，但前端从不调 `getFactorMap`，也不识别这条路径。交互模式（默认）无任何 auto-submit，因此新项目**停死**。 | `frontend/src/components/workbench/AssignmentCard.tsx:91,76-77,305,309`；`frontend/src/store/useSimStore.ts:1031`；`backend/app/orchestrator/engine.py:215,235-236`；`backend/app/orchestrator/runner.py:62-80` |
| **D2** | **2.3 per-factor 签核从不落库。** `BusinessValidationView` 调 `editArtifact`，而 `editArtifact` 是"local-only optimistic"，无 HTTP。下一次 poll 用 `/state` 整体替换 `artifacts`，签核被冲掉。而 `MODEL_BINDINGS` 只有 `a-scope`/`a-factor-tree`/`a-quality-scorecard`/`a-stat-tests` 四个，**没有 `a-business-validation` 的持久化路径**。ledger 的 signoff 层正是读 `body.groups[].signoff == "no"` → 该层**恒为空集**。 | `frontend/.../validation/BusinessValidationView.tsx:594`；`useSimStore.ts:667-678,363`；`backend/app/agents/artifact_edit.py:188-200`；`backend/app/agents/ledger.py:148-161` |

### 2.2 静默失真（S1）

| ID | 问题 | 证据 |
|---|---|---|
| **D3** | **`model_df` 静默兜底到 Danone reference。** `_resolve_project_df` 有两处裸 `except: pass / return None`；项目表为空即返回 `_reference_df()`。而"为空"的门槛很低：published 长表 `<12` 行或 `<6` 个不同月份即判 `None`。真实项目发布了一个稍短的 asset，就会拿到 23.8k 行 Mizone 数据，**全链路零报错**。 | `backend/app/agents/dataset_cache.py:29-42,44-59`；`backend/app/dataeng/binding.py:32-36`；`backend/app/agents/data_binding.py:190-197` |
| **D4** | **2.1 闸门有三个逃逸口。** `data_intake_ready` 是 OR；`manifest_satisfied` 在**抛异常时**和 `m.total == 0`（因子树无 L3/L4 行）时都返回 `True`；`data_intake_ready` 自己的 `except` 里 `ready = True`。结果：2.1 artifact 自己写着 `pending > 0`，闸门却开了。 | `backend/app/orchestrator/engine.py:53-67`；`backend/app/agents/data_request.py:151-156,172-175` |
| **D5** | **分类法不匹配 → 全链路空转但每步报成功。** `channel_type` 在 target schema 里 `required=False`；全空时 `model_objects` 返回 `[]` → ledger 空、funnel 空、`build_ols_proposal` 无 Y 无 X、2.5r 遍历空集、2.6 报 0 objects。**没有任何一步抛错**。dbt marts 由 AI 依据散文列说明生成，产出 `media` / `KPI_volume` 这类标签正是常态。 | `backend/app/agents/dataset_cache.py:62-69`；`backend/app/dataeng/dbt/target_schema.py:20`；`backend/app/mmm/pivot.py:127-135,247` |
| **D6** | **Danone 知识库被无条件套用到任何行业。** `match_factor_range` 对 `Assets/…/factor-ranges.json` 做**双向子串**匹配（`kn in norm or norm in kn`），`rangeSource="reference"` 静默生效。任何新项目的 `d-2.5` ROI/贡献度告警，都是拿饮料行业的带宽在判。 | `backend/app/agents/data_rules.py:321-333,387-389,391` |
| **D7** | **LLM 失败在 S2 里一律静默。** `_bv_narrate` / `_ai_anomaly_hypotheses` / `_ai_stat_rationales` 全部 `except LLMError: return`，不发 finding。`_repair_truncated` 会把截断的数组补齐括号，于是**部分**评分结果能正常解析。2.2 分块 30 行、`continue on LLMError`，混合 AI/确定性的记分卡仍标 `scored_by: "ai"`。且 `SYS = agent_system("data")` 是模块级、无 `st`，**S2 的所有 prompt 都没有注入 brand/industry 上下文**（S1 有）。 | `backend/app/agents/data.py:62,279-296,382,490,500,571,584,660,671`；`backend/app/llm/volcano.py:25-53`；`backend/app/agents/common.py:66-81` |

### 2.3 逻辑不自洽（S2）

| ID | 问题 | 证据 |
|---|---|---|
| **D8** | **2.5r 绕开 `model_selection`。** `build_ols_review` 取了 `sel = model_selection(st)` 但只用 `sel.exclude`；`_collect_records` 用的是 `selected_x_metrics(cfg)` 和 `cfg.params`，不是 `sel.include` / `sel.params`。anomaly effects 只在 `model_selection` 里折叠。后果：2.3a 的 event/cap 在 S2 拟合中**不生效**；只有 3.2 用了 `sel.params` → **人在 d-2.5 签核的模型 ≠ S4 训练的模型**。这正是 CLAUDE.md 明令禁止的失败模式，在上一层复现。 | `backend/app/agents/ols_review.py:264-265,428`；`backend/app/agents/ledger.py:484-485`；`backend/app/agents/model.py:39-46`；`backend/app/agents/data.py:857` |
| **D9** | **三个人工裁决是 no-op。** `register_decision` 只注册了 `d-2.5`。`d-2.2` / `d-2.6` 仅被用来改写问题文案；`d-2.4` 全代码库**无人读取**，且它没有 `rework_task_id`，三个选项全部无效。 | `backend/app/agents/registry.py:34`；`backend/app/domain/blueprint.py:298,336-343`；`backend/app/agents/data.py:394,903` |
| **D10** | **mapping 层的 key 空间与其余五层不同。** `_mapping_ignored` 用 `(r.l4, r.indicator)`（**因子树标签**）；`_universe` 用 `(c["l4"], c["metric"])`（**数据标签**）。一旦 2.1 把 `indicator "TV spend"` bind 到 `metric "TV投放花费"`（正常情况），ignore 就失效，且 ledger 追加一条幻影 orphan 行，funnel 重复计数。 | `backend/app/agents/ledger.py:314,328-330,432-441` |
| **D11** | **AI 的 top-8 截断被记成人类在 2.5x 的否决。** `DEFAULT_MAX_SELECTED = 8` 预勾选；`unticked_pairs` 把一切未勾选当作**拒绝**，在 `d-2.5x` 还没打开时就写进 ledger（理由："Not ticked as a model variable."）。 | `backend/app/agents/ols_review.py:54,195-204`；`backend/app/agents/ledger.py:228-233,407` |
| **D12** | **2.2 是唯一不继承上层否决的层。** `score_data` 直接对整张长表分组，无 `drops_before(st, "quality")`；2.4 则正确调用了。2.1 里被人工 ignore 的指标会在 2.2d 被重新当作开放问题呈现。 | `backend/app/agents/data.py:325`；`backend/app/agents/stat_scoring.py:114` |
| **D13** | **统计"Good"档结构性不可达，且两把尺子。** `_vif_band` 只在 `vif <= 1.0` 给 1.0，而 `vif_all` 仅对完全正交列返回 1.0；三档**相乘**且 `Good` 需 `total > 0.5`。实际几乎无一 Good，全落 Acceptable → `review`；任一档为 0 即总分为 0 → 默认 `drop`。在 `p ≥ n` 代理模式下 `vif = 1/(1-r²ₘₐₓ)`，`|r| ≈ 0.89` 即越过 5，紧耦合的 spend 指标在人看到之前被自动丢弃。同时 2.5 自己的门槛是 `MAX_VIF = 10.0`。 | `backend/app/agents/data_rules.py:167-179,206-244,259`；`backend/app/agents/stat_scoring.py:31-35`；`backend/app/agents/ols_review.py:53`；`backend/app/agents/data.py:725` |
| **D14** | **异常卡在不完整年份和非销量指标上被凭空制造。** `_anomalies` 若匹配不到销量类指标就**用整张表**（把花费、比率、销量一起求和），并按**年度求和**比较，任何截止到年中的数据集都会出现一个巨大的负异常。LLM 无输出时默认 `proposed="event"`，窗口是整年 → 接受它就等于插入 12 个月的 dummy control。 | `backend/app/agents/data.py:405-423,613-614,626` |
| **D15** | **artifact 之间的数字会互相打架。** 2.5r 用 `selected_x_metrics(cfg)`（原始勾选）过滤，2.6 用 `sel.include`（勾选 ∩ adopted）过滤，且 2.6 完全不带 caps/controls；若所有勾选项都被 ledger 拒绝，`sel.include` 为空集 → `adopted_mask` 只留 KPI → `build_model_frame` 抛 "No model variables selected"，2.6 每个 object 报错但文案仍称"通过了所有筛选层的指标"。 | `backend/app/agents/ols_review.py:264`；`backend/app/agents/master_data.py:83-84`；`backend/app/mmm/pivot.py:429-431` |
| **D16** | **重跑会摧毁人工裁决；rework 又留下陈旧的冻结丢弃。** `st.quality_scorecard = card` / `st.stat_scorecard = card` 无条件覆盖（2.3a 则刻意保留人工裁决）。`d-2.2 → recollect` 触发 rework，重置 2.1 及下游 → 2.2 重跑 → 上一轮所有 disposition 丢失。同时 `_rework` 把 decision 置 `idle` 却**不清 `dr.resolution`**，`range_drop_pairs` 仍返回上一轮冻结的 `droppedPairs`。 | `backend/app/agents/data.py:377,607-610,712`；`backend/app/orchestrator/engine.py:296-309,305-306`；`backend/app/agents/ledger.py:189-198` |
| **D17** | **autopilot 产出一次"零裁决"的运行。** `run_until_blocked` 一律选 blueprint 的 `recommended`（accept/approve/keep/confirm/confirm/lock），不改 disposition、不签核、不接受异常卡、不取消勾选。因此 autopilot **完全没有走过六层中的任何一层**——这正是 D2/D9/D10 长期未被发现的原因。 | `backend/app/orchestrator/runner.py:19-24,84-88` |

### 2.4 可见性 / 体验（S3）

| ID | 问题 | 证据 |
|---|---|---|
| **D18** | **`GET /indicator-ledger` 是死代码。** `api/client.ts` 定义了 `indicatorLedger`，**零调用点**。store 里的 `ledger` 字段是无关的 change ledger，也无处渲染。ledger 链条只在两个很晚的地方可见（2.6 的 rejected 行、2.5x 的 `lockedBy` chip）。用户在 2.2d/2.4d/2.3s 完全**看不到上一层已经杀掉了什么、为什么**。 | `frontend/src/api/client.ts:272-273`；`useSimStore.ts:187,366`；`canvas/MasterDataView.tsx:101-146`；`ols/OlsStepPanel.tsx:177-182` |
| **D19** | **"N waiting on you" 收件箱里没有证据。** `DecisionsView` 只渲染 `DecisionCard`；d-2.2/d-2.4 只有三个单选按钮，没有记分卡；d-2.5y/x/p 没有候选变量和参数。真正的编辑器（`TaskStepPanel`）只挂在 `ArtifactDetail → BuildStep` 里。且 **assignment 根本不进收件箱**，所以 S2 的入口 2.1 在唯一标着"Waiting on you"的屏幕上是隐形的。 | `frontend/.../AppShell.tsx:109,177-182`；`decisions/DecisionsView.tsx:36`；`ArtifactDetail.tsx:190` |
| **D20** | **2.3a 从不提示，且没有可见后果。** `2.3a` 是 class `A`（无 decision/assignment），engine 立即完成它；`ArtifactDetail.tsx:131` 的 `open = override ?? status !== 'done'` 使该 step 一 done 就折叠。用户**从未被问过**，默认 `pending` = 什么都不做。即使找到并保存，若 2.5r 已跑完，屏幕上毫无变化，也没有"重新拟合以生效"的入口。 | `frontend/src/lib/scenario.ts:270`；`ArtifactDetail.tsx:131`；`panels/AnomalyReviewPanel.tsx:17,201`；`backend/app/orchestrator/engine.py:189-190` |
| **D21** | **两个记分卡编辑器每敲一个字符就 PUT + 全量 refresh。** `setNote` 直接从 `onChange` 调 `commit`；`commit` → PUT → `refresh()` 整体替换 `qualityScorecard` 和 `artifacts`。服务端每次 PUT 重渲染 artifact、bump version、存盘。无 debounce、无 dirty/saving 指示、无错误反馈，乱序响应会在打字中途回吐字符。**对照组**：`OlsStepPanel`（`useOlsDraft`）和 `AnomalyReviewPanel`（`useAnomalyDraft`）都做了 draft+dirty+Save 保护——`TaskStepPanel.tsx:16-17` 的注释明确要求这么做，这两个漏了。 | `panels/QualityScorecardEditor.tsx:99-101`；`panels/StatScoreEditor.tsx:85-87`；`useSimStore.ts:867-878`；`backend/app/agents/artifact_edit.py:84-92` |
| **D22** | **2.1 不显示 mapping 进度，Data Engine 也不回链。** `AssignmentCard` 只有 dropzone 和 "Open Project Folder"，不渲染 mapped/ignored/pending，也没有到 Data Engine 的链接——尽管它自己的文案写着"In the Data Engine, review the AI's proposed indicator…"。反向亦然：`IndicatorCatalogPanel` 显示 "Gate ready" 却没有回到工作流的路。该面板的 `factorMap` 是 mount 时加载一次的本地 state，accept 后不 `refresh()`，也没有任何错误处理。 | `AssignmentCard.tsx:236-243`；`lib/scenario.ts:223`；`dataeng/IndicatorCatalogPanel.tsx:99-105,101-102,118-126,158-161` |
| **D23** | **三个 S2 artifact 走 `sheet` 兜底渲染。** `a-data-processing` / `a-quality-scorecard` / `a-stat-tests` 声明为 `sheet`，无专用渲染器，全落到通用可编辑网格，用户可以往**计算出来的**记分卡里 "Add Row"——而该编辑是 local-only、静默丢弃（同 D2）。`olsTree` / `masterData` body 形状不匹配时也静默落回同一网格，**无任何说明**。 | `frontend/src/lib/artifacts-data.ts:40,41,43`；`backend/app/domain/blueprint.py:110,111,113`；`canvas/ArtifactCanvas.tsx:97-102,349,362,365` |
| **D24** | **无加载/错误态。** `DecisionCard` 的 "Confirm choice" 在 `resolveDecision` + 整轮 `run()` 期间无 busy/disabled，可重复提交。所有 store 错误汇成 header 上一个 "Backend unavailable" 小药丸，不按动作清除——一次失败的记分卡 PUT 会把乐观值留在屏幕上，用户不知道没存上。`ArtifactDetail` 无 loading 态，`loadProject` 期间渲染空态文案（"The setup has not been proposed yet…"），读起来像 artifact 缺失。 | `decisions/DecisionCard.tsx:123`；`useSimStore.ts:589-599`；`AppShell.tsx:183-188` |
| **D25** | **证据 chip 会把你正在回答的问题弹走。** `DecisionCard` 的 evidence 只调 `selectAsset(ev.artifactId)`，不设 `setViewedStage`。在 2.2d 点 "Referenced data assets" 会整体换成另一个 artifact，决策卡消失且无返回入口。 | `decisions/DecisionCard.tsx:21`；`workbench/TaskTrace.tsx:32` |
| **D26** | **没有 S2 全景。** 最接近的是 `ArtifactColumn`（6 张卡 + 点状进度）和 `StageSpine`（单条 % 条），都不显示六层漏斗、各层存活指标数、下一个待办闸门。漏斗数据（`IndicatorLedger.funnel`）存在，但**只在 2.6 渲染**——那时所有决策都已经做完了。 | `ArtifactColumn.tsx:64-73`；`MasterDataView.tsx:314-319` |

### 2.5 English-only 政策违规（S3）

已确认**会被渲染**的中文串：

| 文件:行 | 内容 |
|---|---|
| `components/folder/DataRequestChecklist.tsx:8-12,44,50,57,64,91,98,107,108,111` | 整个 2.1 slot-upload 清单全中文：`待上传/待校验/已校验/缺指标/解析失败`、`指标`、`缺 N`、`重新上传`、`上传该 L3 工作簿`、`载入数据收集清单…`、`尚无 Data Request（…）`、`数据收集清单 · 按 Data Request（L3）`、`每个 L3 一个工作簿（sheet=L4、列=指标）…` |
| `components/folder/ProjectFolderPanel.tsx:159` | `其它原始数据（未绑定 L3）` |
| `canvas/ArtifactCanvas.tsx:34` | 新列名 `列${n}` |
| `canvas/ArtifactCanvas.tsx:125` | `新页` |
| `canvas/ArtifactCanvas.tsx:246` | `业务检验图表尚未生成 —— 运行 2.32（数据展示）后…`，且引用了**已废弃的任务 id 2.32** |
| `validation/BusinessValidationView.tsx:31-32`、`validation/ValidationChart.tsx:32-33` | 2.3 全部图表的 `亿` / `万` 轴与 tooltip |
| `charts/ReviewCharts.tsx:26-27,131-134` | `亿`/`万`、`份额`、`份额 →`、`增长`、`增长 ↑` |
| `ArtifactDetail.tsx:401` | 每个 S2 artifact 都显示的 chat placeholder：`加一条数据局限说明` / `把批发并入TT的理由写得更清楚` |

潜伏（当前 `basisNote` / `workNote` 无 `.tsx` 消费者，一旦做任务详情面板即泄漏）：`lib/scenario.ts:232-233,242-243,265-266,274-275,283-284,306-307,315-316,342,369,490` 及其 `blueprint.py:283,289` 孪生体。

S2 之外但紧邻（用户见到 S2 之前的头两屏）：`projects/ProjectsLanding.tsx`、`projects/NewProjectForm.tsx` 全中文。

---

## 3. 修复规划

四个阶段，每阶段可独立交付、独立验收。

```
P0 打通  ──▶  P1 自洽  ──▶  P2 可见  ──▶  P3 收尾
D1 D2         D8 D9 D10      D18 D19 D21    D13 D14 D22
D3 D4 D5      D11 D12        D20 D23 D24    D6 D7 D16
              D15 D16(部分)   D25 D26        中文串清理
退出=R1        退出=R2         退出=R3        退出=R4
```

| 阶段 | 目标 | 退出条件 |
|---|---|---|
| **P0 打通** | 真实新项目能交互式走完 S2，且数字确实来自它自己的数据 | 验收剧本 R1 全通过 |
| **P1 自洽** | 六层 ledger 真的成立；人工裁决有可观测后果；S2 拟合 == S4 训练 | 验收剧本 R2 全通过 |
| **P2 可见** | 用户在每个闸门都能看到"上层杀了什么、为什么"和"我这一步会杀掉什么" | R3：见 §4.P2 |
| **P3 收尾** | 统计带宽合理、异常卡不再凭空生成、知识库按行业取、UI 全英文 | R4：见 §4.P3 |

**建议交付节奏**：P0 单独一个 PR（它是"能不能用"的分水岭）；P1 拆 2–3 个 PR（按 ledger 层切）；P2 一个 PR；P3 可并行。

---

## 4. SPEC

每条给出：现状 → 目标 → 契约变更 → 验证方式。
**契约同步铁律**（沿用 CLAUDE.md）：改域模型必须同步 `domain/models.py` ↔ `lib/types.ts`；改工作流结构必须同步 `domain/blueprint.py` ↔ `lib/scenario.ts`。

---

### P0 · 打通

#### SPEC-1 (D1) — 统一 2.1 闸门的放行规则

**现状**：前端 `parsedCount > 0`（`data` 分类），后端 `mapping_complete(st) or manifest_satisfied(st)`。两套规则互不相认。

**目标**：**后端是唯一裁判**。前端不再自行判断，只呈现后端给出的就绪状态。

**契约变更**：
- 后端在 `/state` 的 assignment 对象上（或新增 `GET /factor-map` 的响应里已有的字段上）暴露一个显式的就绪结构：
  ```
  DataIntakeStatus {
    ready: bool
    path: "mapping" | "manifest" | "upload"   # 哪条路径判定的
    mapped: int, ignored: int, pending: int   # mapping 路径的计数
    blockers: [str]                            # 未就绪时的人类可读原因
  }
  ```
  优先做法：扩展现有 `GET /api/projects/{id}/factor-map` 的响应，避免动 `ProjectState` 序列化（注意 `ProjectState` 是 plain BaseModel，**绝不能给它自己的字段加 alias**——见 memory `projectstate-serializes-snake-case`）。
- `AssignmentCard` 改为：`canSubmit = status.ready`。文件上传仍可用，但只是 `path="upload"` 的一条路径，不再是**前置条件**。
- 未就绪时，按钮旁列出 `blockers`，而不是那句写死的 "Upload at least one readable file to continue"。

**验证**：R1 步骤 4。新增 `backend/app/orchestrator/_test_gate.py`：构造三种项目状态（仅 mapping 完成 / 仅 manifest 完成 / 两者皆无），断言 `ready` 与 `path`。

---

#### SPEC-2 (D2) — 让 2.3 签核落库

**现状**：`editArtifact` 是纯本地；`a-business-validation` 无持久化路径；ledger 的 signoff 层恒为空。

**目标**：签核成为一等状态，存在 `ProjectState` 上，而不是 artifact body 里。

**契约变更**：
- 新增 `ProjectState.signoffs: dict[str, str]`（key = L3 factor 标识，value = `"yes" | "no" | ""`）。**理由**：artifact body 会被 handler 重跑覆盖（同 D16），把人工输入放进 body 本身就是错的；`anomaly_review` / `quality_scorecard` 已经是这个模式，signoff 应对齐。
- 新增 `PUT /api/projects/{id}/signoff`，body `{factorId, verdict}`，写入后重渲染 `a-business-validation`（沿用 `artifact_edit` 的重渲染约定）。
- `ledger.signoff_reject_l3` 改为读 `st.signoffs`，不再读 artifact body。
- `data.business_validation` 渲染 artifact 时，把 `st.signoffs` 回填进 `groups[].signoff`，使显示与状态一致，且重跑不丢。
- 前端 `BusinessValidationView` 的 Y/N 改调新 API（乐观更新 + 失败回滚），不再走 `editArtifact`。
- 同时移除 "必须先切到 Edit 模式才能点" 的隐藏门槛（`disabled={!editing}`）——签核是决策不是编辑。

**验证**：R2 第 3 行。新增 `backend/app/agents/_test_ledger_signoff.py`：设 `signoffs["某L3"]="no"`，断言该 L3 的全部指标在 `drops_before(st, "statistical")` 中出现。

---

#### SPEC-3 (D3) — reference 兜底改为显式、可见、可关闭

**现状**：静默替换，两处裸 except，无任何痕迹。

**目标**：**永不静默**。数据来源永远是被声明的，且真实项目默认**不允许**兜底。

**契约变更**：
- `model_df` 返回值改为携带来源：新增 `resolve_dataset(st) -> DatasetResolution{df, source: "published"|"slot"|"reference"|"none", reason: str}`。`model_df` 保留为薄封装（保持既有调用点不变），但内部记录 `st` 上的 `dataset_source`。
- **兜底策略**：仅当 `project_id == "danone-mizone"`（seeded 演示）或显式配置开关打开时，才允许 `source="reference"`；其余项目返回 `source="none"`。
- `source="none"` 时，S2 的 producing handler **不产出空 artifact**，而是发一条 `finding`（severity=blocker）并让任务停在 blocked 状态，文案给出 `reason`（例如 "Published long table has 8 rows; at least 12 rows across 6 distinct months are required."）。
- 两处裸 `except` 改为捕获后 **记录 finding**，而非 `pass`。
- 2.1 artifact 里的数据来源行改为读 `DatasetResolution.source`/`reason`，消除今天那句会说谎的文案（`data.py:136-139`）。

**验证**：R1 步骤 6。新增 `backend/app/agents/_test_dataset_resolution.py`：短表 / 空表 / 异常表三种输入，断言 `source` 与 `reason`，并断言非 seeded 项目**不会**拿到 reference 行数。

---

#### SPEC-4 (D4) — 堵死 2.1 闸门的三个逃逸口

**契约变更**：
- `data_intake_ready` 的 `except` 改为 `return False`（失败即不放行），并发 finding。
- `manifest_satisfied` 抛异常时 `return False`；`m.total == 0` 时 `return False` 并给出 blocker 文案（"The factor tree has no L3/L4 rows to satisfy."）。
- slot `validated` 的判据从"同 L3 有任一已发布指标"收紧为"该 L3 下每个 L4 的必需指标都有对应发布指标"。
- `submit_assignment` 中 `bool(st.indicators)` 单独成立即放行的分支移除，统一走 SPEC-1 的 `DataIntakeStatus.ready`。

**验证**：`_test_gate.py` 增加三个逃逸口的回归用例。

---

#### SPEC-5 (D5) — 分类法不匹配必须响亮失败

**现状**：`channel_type` 全空 → `model_objects` 返回 `[]` → 全链路空转、每步报成功。

**目标**：把"空"从合法状态提升为**阻塞性诊断**。

**契约变更**：
- 新增 `dataset_cache.diagnose_taxonomy(df) -> TaxonomyDiagnosis{objects, y_rows, x_rows, problems: [str]}`。
- 2.1 handler 调用它并把结果写进 `a-data-processing` 的一张新 sheet（"Modeling readiness"），列出：有多少行被识别为 Y、多少为 X、`channel_type` 覆盖率、以及**具体缺什么**（"No row matched a Y role: expected `metric_type='Y'` or `l1='KPI'`"）。
- `objects == 0` 或 `y_rows == 0` 时，2.1 闸门 **不就绪**（并入 SPEC-1 的 `blockers`）。这比让 2.2–2.6 空转到底要早 5 步暴露问题。
- 在 dbt target schema 侧，把 `channel_type` 与 `metric_type` 的取值约束写成可校验的 enum 提示，供 Data Engine 的 Publish 校验引用（不强制改为 `required=True`，避免破坏既有 asset）。

**验证**：R1 步骤 4/6。新增 `backend/app/agents/_test_taxonomy_diagnosis.py`：全空 `channel_type`、无 Y、无 X 三种长表，断言 `problems` 文案与闸门不就绪。

---

### P1 · 自洽

#### SPEC-6 (D8) — `model_selection` 成为唯一选择源

**契约变更**：
- `ols_review._collect_records` 的签名改为接收 `ModelSelection`，内部一律用 `sel.include` / `sel.params` / `sel.exclude`，删除对 `selected_x_metrics(cfg)` 与 `cfg.params` 的直接引用。
- `data.assemble_master_data` 调 `build_model_frame` 时传入 `sel.params`（含 caps/controls），与 2.5r 对齐。
- 新增一条**不变量测试** `backend/app/agents/_test_selection_invariant.py`：同一 `ProjectState` 下，2.5r 使用的变量集合、2.6 主表的列集合、3.2 训练的变量集合**三者必须相等**。这条测试是 D8 类回归的护栏，应长期保留。

**验证**：R2 第 4、5、6 行。

---

#### SPEC-7 (D9) — 让 d-2.2 / d-2.4 / d-2.6 有真实 effect

**现状**：只有 `d-2.5` 注册了 decision effect。

**目标**：要么让裁决有后果，要么把它从 blueprint 里删掉。**不允许存在装饰性闸门。**

**契约变更**（逐个定性）：
- **d-2.2**：选项 `drop` 应把该轮所有 `disposition == "flag"` 的行批量转为 `drop`（一次性批准 AI 的建议），并**冻结**到 resolution 上（同 `freeze_range_drops` 模式）。选项 `keep` 冻结为"本轮不追加丢弃"。`recollect` 保持现有 rework。
- **d-2.4**：补上 `rework_task_id`（指回 `2.4`），并为 `drop` / `keep` 注册与 d-2.2 同构的 effect。若不打算实现，则从 blueprint 删除该 decision，把 2.4d 降为纯 review step。
- **d-2.6**：注册 effect，把当前 `ModelSelection` 的快照冻结到 resolution（`lockedSelection`）。`3.2` 训练时**读这份快照**而不是重新 `model_selection(st)`——这才是"锁定主数据"的实际含义，也顺带消除 S2/S4 漂移的最后一个口子。
- 三者的 effect 统一放进 `ledger.py`，与 `freeze_range_drops` 并列，registry 里集中注册。

**验证**：R2 第 2、6 行。每个 effect 一个单测。

---

#### SPEC-8 (D10) — 统一 ledger 的 key 空间

**契约变更**：
- `_mapping_ignored` 不再用因子树标签建 key。改为：先经 `resolve_factor_map` 把 factor row 解析到它 bind 的 **published indicator → 数据 metric 标签**，再用 `(norm_l4, norm_metric)` 建 key，与 `_universe` 同一空间。
- 对**未 bind 且被 ignore** 的 row（本来就没有数据），不进 `_universe`，也不产生 orphan 行——它应只体现在 2.1 的 mapping 计数里，不进 funnel。
- 删除 `ledger.py:432-441` 的幻影 orphan 追加逻辑，或将其限定为"有数据但不在任何 factor row 下"的真实孤儿。
- 断言：2.1 artifact 的 `ignored` 计数 == funnel mapping 层的拒绝数。

**验证**：R2 第 1 行。新增 `_test_ledger_keys.py`：构造 `indicator "TV spend" → metric "TV投放花费"` 的 bind，断言 ignore 生效且 funnel 不重复计数。

---

#### SPEC-9 (D11) — AI 的截断不得计为人类否决

**契约变更**：
- 在 `OlsConfig` 的候选行上区分两个字段：`ticked`（人类/最终态）与 `proposedByAi`（AI 预勾选）。`d-2.5x` **未解决之前**，`unticked_pairs` 返回空集——ledger 的 selection 层只在人类确认后才生效。
- ledger 的拒绝理由区分文案："Not ticked by the reviewer." vs AI 的建议不写入 ledger。
- `DEFAULT_MAX_SELECTED = 8` 保留为 AI 建议上限，但在 2.5x 面板上显式标注"AI proposed 8 of N candidates"，让人知道剩下的没被否决、只是没被建议。

**验证**：R2 第 5 行 + `_test_selection_layer.py`：`d-2.5x` 未解决时 funnel 的 selection 层为 0。

---

#### SPEC-10 (D12) — 2.2 继承 2.1 的否决

**契约变更**：`score_data` 分组前应用 `drops_before(st, "quality")`，与 `stat_scoring.py:114` 同构。被上层丢弃的指标不进记分卡，但在记分卡页眉显示 "N indicators excluded by earlier layers"（衔接 SPEC-13）。

**验证**：R2 第 1 行。

---

#### SPEC-11 (D15, D16) — 消除 artifact 间数字打架与重跑丢裁决

**契约变更**：
- **数字一致**：由 SPEC-6 的不变量测试覆盖。此外 `master_data` 在 `sel.include` 为空集时，不再产出"通过了所有筛选层"的文案，而是产出一条明确的 blocker artifact（"All candidate variables were rejected at layer X; go back to 2.5x."）。
- **重跑保裁决**：`score_data` / `stat_screening` 写回记分卡时，**按行 merge** 而非整体替换——保留既有行的 `disposition` 与 `note`（对齐 `data.py:607-610` 里 2.3a 的做法），只更新计算出来的分数。新增/消失的行按 key 增删。
- **rework 清冻结**：`engine._rework` 在把 decision 置 `idle` 时，同时清空 `dr.resolution`（或至少清空其中的 `droppedPairs` / `lockedSelection`），使 `range_drop_pairs` 不再返回上一轮的冻结值。

**验证**：新增 `_test_rerun_preserves_dispositions.py` 与 `_test_rework_clears_frozen.py`。

---

### P2 · 可见

**R3 退出条件**：在 2.2d、2.3s、2.4d、2.5x 四个闸门中的**任意一个**，用户不离开当前屏幕即可回答三个问题——(a) 上层已经杀掉了哪些指标、分别因为什么；(b) 我当前的选择会再杀掉多少；(c) 还剩多少会进模型。

#### SPEC-12 (D18, D26) — Ledger 成为 S2 的贯穿视图

**契约变更**：
- 前端接入已存在的 `GET /api/projects/{id}/indicator-ledger`（今天零调用）。store 增加 `indicatorLedger` 切片（注意与既有的 change `ledger` 字段**改名区分**，避免混淆）。
- 新增 `components/project/s2/LedgerFunnel.tsx`：六层漏斗条（mapping → quality → signoff → statistical → selection → range），每层显示"进入 N / 拒绝 M"，点击任一层列出被拒指标及理由。
- 该组件出现在**两处**：S2 stage 头部（全景，替代今天只有 6 张卡的 `ArtifactColumn` 顶部），以及每个 H 面板的头部（只显示"到我这一层为止"的状态）。
- 数据来源统一为 `indicator_ledger`，**不允许**任何前端重新计算漏斗数字。

#### SPEC-13 (D19, D25) — 收件箱带证据；闸门内不失焦

**契约变更**：
- `DecisionCard` 在 Decisions 视图中渲染时，内嵌与 `TaskStepPanel` 相同的编辑器（复用组件，不复制）。即：d-2.2 卡片内直接显示 `QualityScorecardEditor`，d-2.5x 内直接显示 X 候选列表。
- assignment（2.1）纳入 Decisions 收件箱，与 decision 并列为 "waiting on you" 条目。
- evidence chip 改为**侧开抽屉/弹层**，不替换主视图；或在 `selectAsset` 的同时保留一个 "Back to decision" 面包屑。

#### SPEC-14 (D20) — 2.3a 必须被问到

**契约变更**：
- 若保持 2.3a 为 class `A`：`ArtifactDetail` 的 step 折叠规则改为——含未处置项（`status == "pending"` 的 anomaly 卡）的 step **不自动折叠**，并在 step 头显示 "N anomalies awaiting your ruling"。
- 若希望它真正阻塞：把 2.3a 升为 `H`（blueprint + scenario 双改），engine 停在此处。**推荐前者**——异常处置是可选的精修，不该阻塞主链路，但必须可见。
- 保存 rulings 后，若 2.5r 已 done，显示 "Re-fit to apply" 按钮（触发 2.5r 重跑），消除"保存了但什么都没变"的困惑。

#### SPEC-15 (D21, D24) — 编辑器 draft guard 与加载/错误态

**契约变更**：
- `QualityScorecardEditor` / `StatScoreEditor` 引入与 `useOlsDraft` / `useAnomalyDraft` 同构的 draft hook（三者应抽出**一个共享 hook**，见 memory `poll-churn-clobbers-editor-state`）：本地草稿 + dirty flag + 显式 Save + poll 期间 dirty 则不 reconcile。
- `DecisionCard` 的 Confirm 加 busy/disabled。
- store 的 `error` 改为按动作维度（`errors: Record<actionKey, string>`），面板内就地显示失败并允许重试；乐观值在失败时回滚。
- `ArtifactDetail` 增加 loading 态，与"artifact 尚未产出"的空态区分开。

#### SPEC-16 (D23) — 三个 S2 artifact 用真实渲染器

**契约变更**：
- 为 `a-data-processing` / `a-quality-scorecard` / `a-stat-tests` 各自新增 format 与渲染器（`dataProcessing` / `qualityScorecard` / `statTests`），blueprint 与 `artifacts-data.ts` 同步改。
- 它们是**计算产物**，渲染器为只读表格 + 行内 disposition 控件，**移除** Add Row/Add Column。
- `olsTree` / `masterData` 形状不匹配时，渲染显式的 "This artifact was produced by an older schema" 提示，而不是静默落回网格。

---

### P3 · 收尾

#### SPEC-17 (D13) — 统计打分带宽重定
- `_vif_band` 的满分阈值从 `vif <= 1.0` 放宽到业界常规（建议 `vif < 2.5` 为 Good、`< 5` 为 Acceptable、`>= 5` 为 Poor），使 Good 档可达。
- 2.4 与 2.5 的 VIF 阈值**统一**（二者取同一常量，或明确文档化为"筛查 vs 拟合"两个不同目的并在 UI 上说明）。
- 三档**相乘**改为加权求和或取最小档，避免单项 0 直接归零导致自动 drop。这是打分语义变更，需同步 `docs/agent-design/02-data-agent.md`，且 `_test_tools.py` 的期望值需要重算（注意 CLAUDE.md 的铁律：工具层不得改数字——本次改的是 `data_rules` 的实现本身，工具 wrapper 仍是恒等封装，测试同步更新期望是合法的）。

#### SPEC-18 (D14) — 异常检测不再凭空生成
- `_anomalies` 匹配不到销量类指标时**返回空**，而不是退化为整表求和。
- 改为按**滚动 12 个月**或**同比可比区间**比较，剔除不完整年份；不完整期间显式标注为 "partial period, excluded"。
- LLM 无输出时默认 `proposed = "raw"`（仅备注），而不是 `"event"`（会插 dummy）。默认值不应是副作用最大的那个。

#### SPEC-19 (D6, D7) — 知识库按行业取；LLM 失败可见
- `match_factor_range` 的双向子串匹配改为**行业受限**匹配：先按项目 `industry.l1/l2/l3` 选包，无匹配则返回 `None` 并在 artifact 上标 `rangeSource: "none"`，UI 显示 "No industry benchmark available"，而不是套用饮料带宽。
- S2 所有 LLM 调用点注入 `project_context`（brand/industry），与 S1 对齐——把 `SYS` 从模块级常量改为按 `st` 构造。
- `_bv_narrate` / `_ai_anomaly_hypotheses` / `_ai_stat_rationales` 的 `except LLMError` 一律发 finding（severity=warning），artifact 上标注 "AI narrative unavailable"。参考 memory `llm-timeout-silent-writeback`：同类问题已经吃过一次亏。
- 2.2 分块失败时 `scored_by` 标为 `"mixed"`，并列出哪些行是确定性回退。
- `_repair_truncated` 在修复发生时记录一条 warning finding。

#### SPEC-20 (D17) — autopilot 必须走过六层
- 给 runner 增加一个 "exercise" 模式（或在现有 autopilot 中加入确定性的裁决策略）：对每一层做出**非默认**的裁决（丢一个指标、签核否掉一个 factor、接受一张异常卡、取消勾选一个变量），使一次自动运行真正穿过全部六层。
- 这是防止 D2/D9/D10 类缺陷再次长期潜伏的**唯一有效手段**——建议作为 CI 冒烟脚本纳入 `tests/`。

#### SPEC-21 — English-only 清理
- 按 §2.5 表格逐条替换为英文；数字格式 `亿`/`万` 改为 `B`/`M`（或按语言环境格式化，但产品当前政策是 English-only）。
- 删除 `ArtifactCanvas.tsx:246` 对已废弃任务 `2.32` 的引用。
- 潜伏的 `basisNote` / `workNote`（`scenario.ts` + `blueprint.py` 两处孪生）一并译为英文，避免未来任务详情面板泄漏。
- `ProjectsLanding.tsx` / `NewProjectForm.tsx` 虽在 S2 之外，但属同一条真实 case 的必经路径，建议同批处理。

---

## 5. 契约同步清单

本设计涉及的双写文件对，改动时必须成对更新：

| 后端 | 前端 |
|---|---|
| `app/domain/models.py`（`ProjectState.signoffs`、`DataIntakeStatus`、`TaxonomyDiagnosis`、`ModelSelection` 快照） | `src/lib/types.ts` |
| `app/domain/blueprint.py`（d-2.4 的 `rework_task_id`、2.3a 的 klass、三个新 format、`basisNote`/`workNote` 英文化） | `src/lib/scenario.ts` + `src/lib/artifacts-data.ts` |
| 新增路由 `PUT /signoff` | `src/api/client.ts` |

**注意**：`ProjectState` 是 plain `BaseModel`，给它自己的字段加 alias 会导致 `/state` 输出前端读不到的 key（已经在 `ols_config` 上踩过——见 memory `projectstate-serializes-snake-case`）。新增字段用 snake_case，不加 alias。

---

## 6. 风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| **SPEC-3 会让 seeded demo 之外的项目"变得跑不动"** | 这是**故意的**——今天的"跑得动"是假象。但会在观感上像是退步。 | 保留 seeded `danone-mizone` 的 reference 路径不变；新项目的 blocker 文案必须写清楚缺什么、怎么补。 |
| **SPEC-17 改变了已发布的打分语义** | 历史项目的 2.4 结果会变。 | 打分版本号写入 `stat_scorecard`；旧 artifact 保留旧分数并标注版本。 |
| **SPEC-7 若选择删除 d-2.4 而非实现** | blueprint 结构变更会影响已保存项目。 | `heal_state()` 已有回填机制，需为"删除任务"补对称的清理路径。 |
| **SPEC-12/13 组件复用** | 把 `TaskStepPanel` 的编辑器搬进 `DecisionCard` 可能引入双份 draft 状态。 | 先做 SPEC-15 的共享 draft hook，再做 SPEC-13。**顺序不可颠倒。** |
| **P0 与 P1 的耦合** | SPEC-6（统一 selection）会让 SPEC-3 暴露的数据问题更早显现。 | 保持阶段顺序；P0 交付后先跑一遍 R1 再动 P1。 |

---

## 7. 测试策略

现有测试是可执行脚本而非 pytest 套件（见 CLAUDE.md）。沿用该风格，新增：

| 脚本 | 覆盖 |
|---|---|
| `backend/app/orchestrator/_test_gate.py` | SPEC-1、SPEC-4：2.1 闸门三条路径 + 三个逃逸口 |
| `backend/app/agents/_test_dataset_resolution.py` | SPEC-3：来源解析与 blocker 文案 |
| `backend/app/agents/_test_taxonomy_diagnosis.py` | SPEC-5：空 `channel_type` / 无 Y / 无 X |
| `backend/app/agents/_test_selection_invariant.py` | **SPEC-6：2.5r == 2.6 == 3.2 的变量集合（长期护栏）** |
| `backend/app/agents/_test_ledger_signoff.py` | SPEC-2 |
| `backend/app/agents/_test_ledger_keys.py` | SPEC-8 |
| `backend/app/agents/_test_selection_layer.py` | SPEC-9 |
| `backend/app/agents/_test_rerun_preserves_dispositions.py` | SPEC-11 |
| `backend/tests/test_s2_six_layers.py` | **SPEC-20：一次跑通、穿过全部六层的端到端冒烟** |
| `frontend/scripts/visual-check.mjs`（扩展） | R1 的前端点击路径：2.1 就绪 → 逐闸门 → 2.6d |

**最高价值的两条**：`_test_selection_invariant.py`（防 D8 类漂移）和 `test_s2_six_layers.py`（防 D2/D9/D10 类静默失效）。这两条应在 P1 完成时就位。

---

## 8. 未决问题（需在进入实现前定夺）

1. **SPEC-7 的 d-2.4**：实现 effect，还是降级为纯 review step（删 decision）？后者更简单、更诚实。
2. **SPEC-14 的 2.3a**：保持 class `A`（可见但不阻塞）还是升为 `H`（阻塞）？本文推荐前者。
3. **SPEC-17 的打分公式**：加权求和 vs 取最小档？需要产品判断，涉及 `docs/agent-design/02-data-agent.md` 的语义。
4. **SPEC-3 的兜底开关**：只按 `project_id == "danone-mizone"` 判定，还是加一个显式配置项？后者更灵活但多一处配置面。
