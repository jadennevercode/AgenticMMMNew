# 产品架构 v2：双平面 Human-AI Collaboration 架构

> 在 00–05 文档（智能体定位/能力/流程，"做什么"）之上，本文档定义**产品如何承载这些工作**（"怎么做"）。
> v2 不推翻编号任务体系——任务体系是流程平面的内容；v2 重新设计的是承载它的架构与交互形态。
> 设计依据：产品负责人六条 Philosophy（2026-06-13）+ reference 全量材料 + [07-assumptions-log.md](07-assumptions-log.md) 登记的假设。

## 1. 设计哲学与架构转译总表

| # | Philosophy（原话） | 架构转译 | 落点章节 |
|---|---|---|---|
| P1 | 设计考虑机械化/自动化流程 和 需要感知计划协调决策的流程 | **任务自动化分类法**：M 机械 / A 可自动 / C 认知 / H 人专属，全任务打标，标签决定执行引擎、UI 形态与审计要求 | §2 |
| P2 | 考虑流程确定性和 AI 不确定性间的 Balance | **确定性骨架，概率填肉**：AI 永不直接改状态，全平台唯一写入通道 = Proposal→Apply（三道闸） | §3 |
| P3 | 充分体现 AI 价值，不一定 Task/Step 驱动，多考虑 Human-AI Collaboration | **双平面架构**：流程平面（任务/Gate）+ 协作平面（Artifact Workspace 人机共创），共享同一底座 | §4 |
| P4 | 从确定性流程中用 AI 非线性（Unliner）的方式挖掘、放大特性体现 AI 价值 | **Insight Engine**：常驻观察者，跨阶段/跨资产非线性挖掘，产出可落回流程的 Insight Card | §5 |
| P5 | 充分考虑 Human Intuitive | **三视角体验架构** + 交互三原则（diff 呈现 / 渐进披露 / 决策即选择题） | §7 |
| P6 | Copilot 和流程驱动的 AI-Human Collaboration 并存 | **双模式同底座**：Pipeline Mode 与 Copilot Mode 共享上下文总线与 Proposal→Apply 通道 | §6 |
| P7 | 多考虑流程中的通用模块（Knowledge / Artifacts / Task Assignment 等） | **五大平台服务**下沉，业务智能体变薄 | §8 |
| P8 | 文档中的功能设计描述、概念哲学，不能出现在产品前端页面中 | **内部语言与界面语言隔离**：架构词汇仅存在于文档与代码，UI 只说用户的业务语言，建禁用词表并纳入走查 | §7.3 |

一句话架构观：**确定性流程保证交付下限，协作平面与 Insight Engine 拉高价值上限，五大平台服务让两者跑在同一套底座上。**

## 2. 任务自动化分类法（P1）

### 2.1 四个 Automation Class

| Class | 名称 | 定义 | 执行引擎 | UI 形态 | 审计要求 |
|---|---|---|---|---|---|
| **M** | 机械（Mechanical） | 确定性规则可完整执行，零 AI 参与 | 规则引擎 / 数据管道 / 统计库 | 后台执行 + 结果呈现，无需人盯 | 输入版本 + 规则版本 → 结果可复现 |
| **A** | 可自动（AI-Automatable） | AI 生成，但产出有 Schema/规则可机器校验，错误可兜底 | LLM + 结构校验器 | 草案直接呈现，人抽检/微调 | 记录 LLM 模型版本 + prompt 版本 + 校验结果 |
| **C** | 认知（Cognitive） | 需感知、计划、协调、判断；无客观对错判据 | LLM（推理强模型）+ 证据组装 | **建议 + 证据 + 候选**，等待人裁决 | 全量保留推理依据与人的裁决记录 |
| **H** | 人专属（Human-only） | 决策权不可让渡（客户承诺、责任归属） | 人 | 选择题形态（候选 + AI 推荐 + 后果说明） | 决策人 + 理由 + 时间 + 凭证 |

判别规则：有唯一正确答案且可规则验证 → M；有标准格式但内容靠生成 → A；要"想"但不担责 → C；要"担责" → H。同一编号任务通常拆出多 Class 子步骤（材料中"0.5 分人进入决策"即 M+H 复合的原生案例）。

### 2.2 全任务打标表

| 任务 | 子步骤分解 | Class |
|---|---|---|
| 1.0 Scope | AI 起草（约束校验：渠道≤4、组≤6）→ 确认 | A → H |
| 1.1 行业知识加载 | 按行业包加载 | M |
| 1.21 因子召回 | L1/L2 全量召回 ｜ L3/L4 召回 ｜ 补充建议（≤20%） ｜ 增删确认 | M ｜ M ｜ C ｜ H |
| 1.22 指标召回 | 已有 L4 指标召回 ｜ 新 L4 指标补充 ｜ 确认 | M ｜ C ｜ H |
| 1.23 数据需求模板 | 因子树 → L3 表/L4 sheet 模板生成 | A |
| 1.24 模型选型 | 选型建议（概率模型 vs OLS）→ 确认 | C → H |
| 1.31 读品牌报告答 KBQ | 长文档理解与六类问题作答 | C |
| 1.32 访谈提纲 | 分层提纲生成 | A |
| 1.33 纪要总结 | 框架化总结（假设 A4）｜ 结构化抽取（因子 diff/口径/KBQ 候选） | A ｜ C |
| 1.34 KBQ 定稿 | 候选整理 → 确认 | A → H |
| 1.4/1.5 知识管理 | 留痕 CRUD ｜ 回流评审 | M ｜ H |
| 2.11/2.12 数据打分 | 10 项规则打分 ｜ 0.5 分项处置 ｜ 全 0 预警升级 | M ｜ H ｜ M(触发)+H(处置) |
| 2.21 长表实例化 | Schema 实例化 + 主数据清洗 | M |
| 2.22 数据处理 | ETL 逻辑起草 ｜ 逻辑确认（两人互检） ｜ 管道执行 ｜ 异常原因探查 | A ｜ H ｜ M ｜ C |
| 2.23 数据字典 | 登记生成 ｜ 校对 | A ｜ H |
| 2.24 数据集成 | 长表集成 | M |
| 2.31 业务校验六步 | 全景/拆解图表 ｜ 异常定位下钻 ｜ 假设生成 ｜ 先验提取 ｜ 客户核对 | M ｜ M ｜ C ｜ C ｜ H |
| 2.32 数据展示 | 图表渲染 ｜ 趋势解读初稿 ｜ 客户 sign-off | M ｜ A ｜ H |
| 2.33 统计检验 | CV/Pearson/VIF 计算 ｜ 1.5–3 分段取舍 | M ｜ H |
| 2.34 OLS 预验证 | 拟合执行 ｜ Range 判读（假设 A2） | M ｜ C |
| 2.35 Model Input | 透视转换（假设 A3） | M |
| 3.1 先验设置 | 假设→数学形式映射 ｜ 先验确认 | C ｜ H |
| 3.2 模型调优 | 训练执行 ｜ 诊断与调优方向 | M ｜ C |
| 3.3 技术检验 | 五指标计算 + 红旗检测 ｜ 三维度解读 | M ｜ C |
| 3.4 业务检验 | 红黄绿灯对照 ｜ 最终模型选择 | M ｜ H |
| 4.1 报告 | 长表/图表生成 ｜ 话术生成 ｜ 商业逻辑补充 ｜ 审核交付 ｜ 交互问答（假设 A5） | M ｜ A ｜ C ｜ H ｜ C |

统计含义：全流程约 **45% M、20% A、22% C、13% H**——平台的自动化收益主要来自 M+A（约 2/3 工作量），而产品差异化价值在 C 类步骤的质量与 H 类步骤的决策体验。

## 3. 确定性 × AI 的 Balance：Proposal→Apply 协议（P2）

### 3.1 核心原则

**AI 永远不直接改变系统状态。** AI 的一切产出都是 Proposal；状态变更只由确定性引擎执行 Apply。这是全平台唯一写入通道，Pipeline 内的智能体与 Copilot 共用（保证 §6 双模式不分叉）。

### 3.2 Proposal 数据结构

```ts
interface Proposal {
  id: string
  targetArtifact: { id: string; version: number }   // 基于哪个版本提出（过期即失效）
  diff: ArtifactDiff                                  // 结构化变更（非自由文本）
  rationale: string                                   // 理由
  evidence: EvidenceAnchor[]                          // 证据锚点：引用 artifact 精确位置
  confidence: number                                  // 0–1
  producedBy: { agent: AgentId; mode: 'pipeline' | 'copilot'; llm: string }
  automationClass: 'A' | 'C'                          // M 不产生 Proposal（直接执行）；H 不由 AI 提出
  validations: ValidationResult[]                     // 闸一、闸二结果
  status: 'draft' | 'proposed' | 'applied' | 'rejected' | 'stale'
}
```

### 3.3 三道闸

| 闸 | 执行者 | 内容 | 失败处置 |
|---|---|---|---|
| ① Schema 校验 | 机器 | 结构合法性（diff 可应用、引用存在、枚举合法） | 自动打回 AI 重试，不进入人审 |
| ② 规则校验 | 规则引擎 | 业务阈值（增删 ≤20%、打分边界、先验区间、Scope 约束） | 标红进入人审或按规则升级（如超阈值 → Solution Team 联审） |
| ③ 人工 Gate | 人（按 Class） | A 类：抽检/事后审；C 类：必审；H 类：本身就是人的决策 | 驳回 → 回炉任务（带驳回理由进入 AI 上下文） |

### 3.4 不确定性降级

`confidence < 阈值（默认 0.7，规则库可配）` 时，Proposal 自动从"草案（可一键 Apply）"降级为"建议（必须人改写后才能 Apply）"；连续 3 次同任务低置信 → 通知项目管控转人工执行。

### 3.5 可复现性分层

- M 类产出：输入版本 + 规则版本 → **严格可复现**；
- A/C 类产出：不追求复现，追求**可追溯**（prompt/模型/证据全留痕）+ **可验证**（三道闸记录）。
- 审计视角：任何 confirmed Artifact 都能回答"哪些部分是机器算的、哪些是 AI 写的、哪些是人定的"。

## 4. 双平面架构（P3）

### 4.1 两个平面

| | 流程平面（Process Plane） | 协作平面（Collaboration Plane） |
|---|---|---|
| 驱动 | 任务 DAG + 阶段状态机 + Gate（00 文档 §4） | 人随时发起 |
| 单位 | 编号任务 | **Workspace 会话**：人 + AI 在某个 Artifact 上的一次共创 |
| 价值 | 交付确定性、项目可控、客户承诺 | 深度、灵活性、人的直觉介入 |
| 产出回写 | 任务产出 → Artifact 新版本 | 会话产出 → Proposal → 同一 Apply 通道 |

两平面不是两套系统：**协作平面是流程平面的"放大镜"**——流程保证事情按序发生，Workspace 让人在任何时刻深入任何资产，产出仍然受 Gate 体系约束。

### 4.2 Artifact Workspace 规范

每类 Artifact 的 Workspace = `主视图 + AI 侧栏 + 血缘条 + 版本/diff 条`：

| 区域 | 内容 |
|---|---|
| 主视图 | 按类型定制：因子树 = 可编辑树 + 来源标记；数据集 = 透视图表；模型结果 = decomp/弹性视图；报告 = 文档视图 |
| AI 侧栏 | 针对当前 Artifact 的对话（上下文自动注入该 Artifact + 血缘上游摘要）；支持四个动词：**问**（解释/溯源）、**挑战**（"这个弹性为什么这么高"→ AI 组装证据回应或承认存疑并建议动作）、**改**（生成 Proposal diff）、**比**（版本间/对象间对比解读） |
| 血缘条 | 上游依赖（基于哪些版本）与下游影响（谁消费了我）；版本过期标记 |
| 版本/diff 条 | 历史版本、待审 Proposal 队列、应用/驳回记录 |

### 4.3 平面间的流转

- 流程 → 协作：任务卡、Gate 待办、Insight Card 都提供"在 Workspace 打开"入口（带任务上下文）；
- 协作 → 流程：Workspace 产生的 Proposal 若涉及 confirmed/frozen Artifact，自动按 Gate 路由表（05 文档 §4.1）生成待办；涉及新工作量的（如"需要补一个数据 Task"）→ 一键转任务给项目管控。

## 5. Insight Engine：非线性挖掘（P4）

### 5.1 定位

不在流水线内的**常驻观察者智能体**。确定性流程是线性的，AI 的差异化价值在跨阶段、跨资产、跨项目的非线性关联——流程保证下限，Insight Engine 拉高上限。它是"从确定性流程中挖掘、放大 AI 价值"的专职载体。

### 5.2 输入（订阅上下文总线）

事件流（任务状态、Gate 决策、Artifact 版本变更、打分结果、红旗）+ 全 Artifact 检索域 + 知识库（含跨项目沉淀区）。

### 5.3 四类洞察

| 类型 | 触发逻辑 | 实例（基于 Danone 材料可演示） |
|---|---|---|
| **关联**（Cross-link） | 新异常/新 Artifact 与既有材料的语义关联 | "2.31 发现 8 月抖音 ROI -43% ↔ EC 访谈纪要提到 8 月更换代理"——把数据异常与访谈口供自动接上 |
| **缺口**（Gap） | 覆盖率扫描：KBQ↔数据Task↔模型变量↔报告图表 的链路断点 | "KBQ A19（站外投放对站内影响）没有任何数据 Task 支撑"；"朗镜数据仅 5 个月，竞品门店执行因子将无法入模" |
| **矛盾**（Conflict) | 已确认结论间的逻辑冲突 | "客户确认的弹性上限 0.7 与近三月数据趋势冲突"；"财务口径 100M ↔ 营销收数 87M，超出 10% 容差" |
| **联想**（Recall） | 跨项目知识库相似情境检索 | "上一个饮料项目同类渠道弹性区间 0.3–0.5，本项目 OLS 预验证结果 0.9 偏高" |

### 5.4 Insight Card 数据结构与生命周期

```ts
interface InsightCard {
  id: string
  type: 'cross-link' | 'gap' | 'conflict' | 'recall'
  finding: string                          // 一句话发现
  evidence: EvidenceAnchor[]               // ≥2 个证据锚点（非线性=多源）
  confidence: number
  suggestedActions: Array<                 // 必须可落回流程平面
    | { kind: 'create_task'; template: string }
    | { kind: 'client_question'; draft: string }     // 转数据&指标沟通表
    | { kind: 'prior_candidate'; draft: PriorDraft } // 转 3.1 候选
    | { kind: 'open_workspace'; artifactId: string }
  >
  status: 'new' | 'acknowledged' | 'actioned' | 'dismissed'  // dismissed 须选理由（反馈学习）
}
```

纪律：**洞察必须能落回流程，否则就是噪音**——无 suggestedAction 的发现不出卡；同类卡片去重聚合；每日上限防打扰（项目级可配）。

## 6. Copilot 与流程驱动并存（P6）

| | Pipeline Mode | Copilot Mode |
|---|---|---|
| 驱动者 | 流程（任务就绪 → AI 干活，人被 Gate 召唤） | 人（随时发起） |
| 上下文 | 当前任务的输入 Artifact + 任务定义 | 全局：项目记忆 + 因子树 + 全 Artifact 检索 + 事件流 + 知识库 |
| 典型能力 | 任务定义内的工具（01–04 文档能力表） | 只读分析、血缘溯源问答（"这个数从哪来"）、起草任意 Proposal、调用任意领域智能体能力、解释项目状态（"现在卡在哪"） |
| 写入 | Proposal→Apply | **同一条 Proposal→Apply 通道，不绕过 Gate** |
| 界面 | 任务卡/Gate Inbox | 全局常驻面板 + Workspace AI 侧栏（同一 Copilot，不同上下文注入） |

边界声明：Copilot 没有任何特权——它能"替人起草一切"，但不能"替人确认任何 H 类决策"；它对 frozen Artifact 只读。

## 7. Human Intuitive 体验架构（P5）

### 7.1 三个一级视角（按人的心智模型，而非系统模型）

| 视角 | 回答的问题 | 核心界面 | 对应现有前端组件 |
|---|---|---|---|
| **项目视角** | "现在该做什么？卡在哪？" | Mission Control（阶段/里程碑/延迟/回流）+ Gate Inbox（待我决策） | MissionControl、GateInbox、WorkflowCanvas（降级为项目视角内的流程图） |
| **资产视角** | "我要看/改某个东西" | Artifact Hub 升级为 **Workspace 主工作台**（§4.2） | ArtifactHub（大改） |
| **对话视角** | "我想问" | Copilot 全局面板 + Insight 信息流 | AgentConsole（改造为 Copilot）；SimulationStudio 按裁决 D1 重新评估去留 |

### 7.2 交互三原则

1. **AI 改动一律以 diff 呈现**：纪要→因子树 diff、先验 diff、ETL 逻辑 diff——人审 diff 远比读全文直觉；这是 Proposal 数据结构强制 `diff` 字段的体验侧理由；
2. **渐进披露**：默认只给结论 + 推荐，证据链可逐层下钻——与业务上 L4→L5–L8 的下钻心智同构，一套交互范式覆盖数据下钻与证据下钻；
3. **决策即选择题**：H 类节点永不呈现空白表单，固定为"候选项 + AI 推荐（含理由）+ 各选项后果说明"，附证据锚点（材料原生范例：0.5 分处置、Pareto 候选选择、纪要改动确认）。

### 7.3 内部语言与界面语言隔离（P8，裁决 D4）

**原则**：本套文档中的架构概念、功能设计描述、设计哲学（双平面、Proposal→Apply、Automation Class、Insight Engine、三道闸、上下文总线、血缘三元组、M/A/C/H……）是**工程内部语言**，只允许出现在设计文档、代码标识符与注释中；**前端界面的一切可见文案只使用用户的业务语言**。用户感知机制带来的体验，而不是机制的名字。

**术语映射表**（内部 → 界面，Phase B 文案基线，可在评审中调整措辞但不得回退为内部术语）：

| 内部概念 | 前端呈现 |
|---|---|
| Proposal / Proposal→Apply | "AI 建议的更改"——diff 卡片 + 「采纳」「驳回」按钮；不出现 Proposal/Apply 字样 |
| Automation Class（M/A/C/H） | 不显示分类本身，只体现为行为差异；如需状态徽标：「已自动完成」「AI 草稿」「待确认」「需要你决策」 |
| Gate / 人工 Gate / 三态打分 | 「待确认」「需要你的决定」；打分以红/黄/绿与分值呈现，不出现"三态""Gate" |
| 双平面 / 流程平面 / 协作平面 | 不出现；导航即「项目」「资产」「助手」等业务名词 |
| Workspace 会话 | 即"打开某个资产"本身，无须命名机制 |
| Insight Engine / Insight Card | 「AI 发现」/「线索」/「提醒」（Phase B 定稿一个词并全局统一） |
| Copilot Agent | 产品化命名（如「助手」），Phase B 定稿 |
| Context Bus / 事件流 | 不出现；体现为「动态」「项目日志」 |
| 血缘三元组 / EvidenceAnchor | 「数据来源」「引用」「依据」 |
| confidence / 置信降级 | 不出现数值术语堆砌；低置信体现为措辞（"AI 不确定，建议人工复核"）或视觉弱化 |
| 确定性引擎 / 规则引擎 | 不出现 |
| 知识回流 / 沉淀区 | 「知识库」「保存为团队经验」 |

**执行机制**：

1. 前端建立**禁用词表**（上表左列 + 文档新增概念随时追加），作为常量维护在 `frontend/src/lib/` 下；
2. 文案走查纳入 Phase C 验收清单：对构建产物全文检索禁用词，命中即不通过；
3. 例外：开发者工具/调试面板（不面向用户）不受限，但默认不出现在产品构建中。

业务智能体变**薄**（= 领域 prompt + 规则绑定 + 工具绑定），通用能力全部下沉：

| 服务 | 职责 | 核心接口（示意） | 材料依据 |
|---|---|---|---|
| **Knowledge Management** | 行业包（Solution 沉淀区 / 项目定制区）、增删留痕、回流评审、跨项目检索 | `recall(industry, level)` / `suggest(context)` / `track_change(change)` / `promote_review(project)` | 1.4/1.5、留痕要求、知识库分区反馈 |
| **Artifact Management** | 类型注册、版本、血缘三元组、diff 计算、证据锚点解析、生命周期 `draft→proposed→confirmed→frozen` | `commit(artifact, lineage)` / `diff(v1,v2)` / `resolveAnchor(anchor)` / `staleness(artifactId)` | 21 类 Artifact 总表、sign-off 实践 |
| **Task & Assignment** | 任务模板库（StatusCheckList 即模板）、实例化、优先级/排期/Owner/SLA、回流边管理 | `instantiate(template, scope)` / `assign(task, owner)` / `reflow(task, reason)` | Schedule/TaskLog/Timeline |
| **Gate & Approval** | 三态打分、sign-off 录入（含凭证，假设 A6）、阈值路由、收件箱、SLA 升级、决策审计 | `open(gate, evidence, options)` / `decide(gate, choice, note)` / `escalate(gate)` | 0/0.5/1 体系、11 条路由表 |
| **Context Bus & Memory** | 版本广播、一致性检查、项目记忆、事件流（Insight Engine 与审计的共同数据源） | `publish(event)` / `subscribe(filter)` / `checkConsistency(task)` / `memory(project)` | 项目管控四职责 |

项目管控智能体与平台服务的关系：服务是"机制"，管控智能体是用这些机制执行编排策略的"大脑"（05 文档能力表即对这五个服务的调用组合）。

## 9. 总体架构图与场景走查

```
┌─ Experience 层 ───────────────────────────────────────────────┐
│   项目视角            资产视角(Workspace)         对话视角(Copilot)  │
├─ 协作平面 ─────────────────┬─ 流程平面 ──────────────────────────┤
│   Artifact 人机共创会话      │   编号任务 DAG · 阶段状态机 · Gate     │
├─ 智能层 ──────────────────────────────────────────────────────┤
│   商业/数据/模型/报告智能体（薄） + Insight Engine + Copilot Agent   │
├─ 平台服务层 ───────────────────────────────────────────────────┤
│   Knowledge │ Artifact │ Task & Assignment │ Gate │ Context Bus   │
├─ 确定性引擎层（Proposal→Apply 唯一写入口） ─────────────────────────┤
│   规则引擎 · 数据管道 · 打分器 · 图表渲染 · 模型后端(Meridian/PyMC/OLS) │
└───────────────────────────────────────────────────────────────┘
```

**场景走查 1（Pipeline 主导）**：客户数据到达 → Task 服务激活 2.11 → 打分器（M）算出某指标 0.5 分 → Gate 服务开待办（选择题：剔除/降权/补数，AI 推荐 + 证据）→ DS 选"补数" → 自动生成客户沟通表条目 → 事件入总线 → Insight Engine 关联到"该指标服务的 L4 是 KBQ A8 的关键因子"，出 conflict 卡提醒优先级。

**场景走查 2（Copilot 主导）**：BA 在模型结果 Workspace 问"冰柜 ROI 4.0 是不是太高了" → Copilot 组装证据（行业知识典型范围、上项目联想、该变量先验区间、共线性记录）→ 回答"高于先验上沿，且与陈列架共线性 VIF 6.2" → BA 点"挑战成立" → Copilot 起草 Proposal（建议冰柜与陈列架合并变量重跑）→ 规则校验通过 → 路由到 G3.4 待办 → DS 确认 → 触发 3.2 重训任务。

## 10. 对现有实现的影响

### 10.1 前端重构清单（Phase B 范围）

| 现有 | 处置 |
|---|---|
| `types.ts` 领域模型 | 增加 `AutomationClass`、`Proposal`、`InsightCard`、Artifact 生命周期与血缘三元组；任务编号对齐 1.0–4.1 |
| MissionControl / WorkflowCanvas | 合并为项目视角；流程图标注 Automation Class 与回流边 |
| GateInbox | 升级为"选择题"形态（候选+推荐+后果+证据锚点）；接入三态打分与 sign-off 凭证录入 |
| ArtifactHub | 升级为 Workspace 主工作台（最大改动，建议最先做：资产视角是双平面的最小闭环） |
| AgentConsole | 改造为 Copilot（全局面板 + Workspace 侧栏复用） |
| SimulationStudio | 按裁决 D1：预算优化出范围，组件裁撤或转为 Workspace 内轻量 what-if 视图，Phase B 定 |
| Mock 引擎 | 事件流化（供 Insight 卡演示）；按 Class 区分确定性输出与"AI 输出"（含 confidence）；模型结果结构转贝叶斯 decomp 范式 |
| 全部界面文案 | 按 §7.3 术语映射表重写；建禁用词表常量 + 构建产物全文检索走查（裁决 D4） |

### 10.1.1 已落地状态（Phase B 实现，2026-06-13）

前端已按本架构重建并通过验证。当前实现要点（与上表的差异以本节为准）：

- **设计语言**：参考 `OntologyFactory0527`，采用 shadcn 风格 —— slate 中性 + blue-600 accent、Geist Sans/Mono、Radix 原语（`radix-ui` 统一包）、`lucide-react` 图标、`--radius:0.625rem`、含 dark tokens（暂无切换开关）。原"暖色编辑部/纸张"风格已弃用。
- **信息架构（IA）= 2 目的地 + 3 抽屉**（裁决：Decisions/Assets 改抽屉，更贴近"在哪用就在哪弹出"）：
  - 顶部水平导航目的地：**Project**、**Knowledge**；
  - 抽屉（右侧 Sheet，从任意位置唤起）：**Decisions**（队列+选择题）、**Assets**（master-detail：Content/Sources/Suggested changes/Ask AI）、**Assistant**（Ask + What the AI noticed）；
  - Header 右侧触发区：Assets / Decisions(•) / Assistant(•) + Run/Step/Reset；证据芯片、血缘、活动流均就地唤起对应抽屉（含抽屉叠抽屉：Decision 证据 → Asset）。
- **Knowledge 模块（新建，补齐 08 §8 缺口 + 任务 1.4/1.5）**：四个 Tab —— Industry pack（因子树主数据，L1/L2 锁定、L3/L4 带来源标记）、Change ledger（留痕：增/删/合并 × 原因 × 来源 × 确认人，**接受建议变更时自动追加**，已验证工作流→知识回流联动）、Solution library（跨项目规则库/模板）、Promote to library（项目定制回流候选）。
- **依赖新增**：`radix-ui`、`lucide-react`、`clsx`、`tailwind-merge`、`class-variance-authority`、`@fontsource-variable/geist(-mono)`；新增 `components/ui/`（button/card/badge/tabs/sheet/misc）与 `lib/cn.ts`、`lib/knowledge-data.ts`。
- **D4 走查**：`scripts/copy-check.mjs` 仍绿；界面全英文，Artifact/账本/用户输入保留中文。

### 10.1.2 Phase B-3（工作台布局 + 人工输入任务，2026-06-13）

按用户调整重构 Project 页与人工触点模型：

- **Project = 三栏工作台**（不再是 drawer 唤起）：
  - **左侧栏**：只展示**当前运行 Stage** 的任务列表（`currentStage()` = 首个未全 done 的阶段）；顶部 5 段 stage dots 可点击「窥视」其他阶段（read-only，可"Back to current"）；任务行内联展开 summary/workNote。
  - **中间**：`HumanWorkbench` —— "What needs you"，一次呈现一个待办（决策或输入），队列尾标 "N more waiting"；无待办时 calm state（"AI is working on X" / "Project delivered"）。
  - **右侧**：`ArtifactsPanel` —— 列表 ↔ 详情（Content/Sources/Changes/Ask）内联切换；证据芯片/血缘/Insight 改为**在此面板选中**（`selectAsset`），不再开抽屉。
- **Activity 与 Assistant 改为右下角悬浮按钮（FAB）**：`FloatingDock` 两个圆钮，点击展开浮动卡片；Assistant 含 Ask + "Noticed"（findings）两个 Tab。三个抽屉组件（Decisions/Asset/Assistant Drawer）已删除。
- **人工输入任务（Human Assignment，补齐用户点 5）**：识别出流程中"决策"之外的人工输入点，建模为 `assignment?: AssignmentBlueprint`（kind=upload，mock 附件 + 提交）。新增 4 个输入任务并重连依赖：
  - `1.0a Provide SOW`（→1.0）· `1.31a Upload brand & competitor reports`（→1.31）· `1.32a Upload interview minutes`（→1.33）· `2.0a Upload collected client data`（→2.11）。
  - 产出 4 个 "(provided)" 人工来源 Artifact（a-sow / a-brand-reports / a-minutes-raw / a-data-files），作者=人，状态直接 **confirmed**，并接入下游血缘。
  - 行为徽标新增 **"Your input"**（区别于 "Your decision"）。决策 + 输入共 **11 个人工触点**，统一在中间工作台处理。
- store 改造：`drawer` slice → `panels{activity,assistant}` + `selectedAssetId` + `viewedStageId`；新增 `assignments` runtime 与 `submitAssignment`；导出 `currentStage()`。

### 10.1.3 Phase B-4（通用任务工作台 + S1 按 MMM-Study 重构，2026-06-13）

参考 `MMM-Study`（7 阶段前置工作台 SPEC）修正 Business Understanding，并把中间工作台从"只接决策"升级为通用任务详情台：

- **中间 = 通用任务工作台**（`workbench/TaskWorkbench.tsx`，替换 HumanWorkbench）：点击左侧**任意**任务即在中间展示该任务的 **What this does / How it runs / Draws on（上游 artifact 芯片 + basisNote）/ Produces（下游 artifact，exportable 标记）/ Working note**；若该任务正等待人工（决策或输入/导出），在详情内**内联**渲染 DecisionCard / AssignmentCard。焦点优先级：显式选中 → 首个待人工任务 → 运行中任务 → calm。显式选中时保留焦点，header 提供「What needs you」跳回 + "N needs you" 计数。**坑**：DecisionCard/AssignmentCard 含本地 state，TaskDetail 必须 `key={focus.id}` 否则切任务时 state 串号（曾导致附件计数 7/4 卡死）。
- **S1 Business Understanding 按 MMM-Study 重排**（Framing → Knowledge Assembly → Factor Tree → Indicators → Data Request，显式 import/export）：
  - 任务：`1.0a` 导入SOW → `1.0` 框定 Scope&KBQ(决策) → `1.1a` 导入报告资料 + `1.1b` 导入访谈纪要 → `1.1` 装配知识包(含冲突/缺口) → `1.21` 推导因子树 → `1.21d` 确认因子树(决策) → `1.22` 指标候选(3–5/L4 三维打分) → `1.22d` 选指标(决策) → `1.23` 生成数据需求包 → `1.23b` 导出并发送(export)。
  - 新 artifact：Scope&KBQ Card、Reports&Materials(provided)、Project Knowledge Package（行业通识/客户特定条目 + 来源·置信度·适用范围 + 冲突缺口）、Indicator Candidates（三维打分）、Indicator List；Data Request 标 `exportable`。删除 Metric Library / Interview Plan / Brand Reports / Interview Digest。
  - 类型新增：TaskBlueprint `how` + `basisNote`（全任务填充）；`AssignmentKind` 加 `'export'`；ArtifactBlueprint 加 `exportable`；ui-language 加 `EXPORT_BADGE`("Export & send")。AssignmentCard 支持 export 变体（Download + Mark as sent）。
  - S2–S5 结构不变，仅补 `how`/`basisNote`。后续若要把 S2 也对齐 MMM-Study 的 Data Sourcing + Quality Gate，再开一轮。

### 10.1.4 Phase B-5（左侧可伸缩导航 + 恢复 Canvas/Decisions/Assets 三模块，2026-06-13）

- **导航从顶部移到左侧可伸缩 rail**（`layout/AppShell.tsx`）：左侧 `w-52` 展开 / `w-14` 折叠（icon-only + Tooltip），状态存 `localStorage('agenticmmm.nav.expanded')`，底部 Collapse 开关；顶部改为 slim top bar 只放 Run/Step/Reset + Day/进度 + "N waiting"。五个目的地：Project / Workflow Canvas / Decisions / Assets / Knowledge（Decisions 带 open 计数徽标）。FloatingDock（Activity/Assistant FAB）保留。
- **恢复三个 V1 模块为独立目的地**（基于当前数据模型 + shadcn 重建，非旧代码）：
  - **Workflow Canvas**（`canvas/WorkflowCanvas.tsx`，@xyflow/react）：5 阶段分列的任务 DAG，节点显示 id/名称/行为徽标/状态色，边=dependsOn（done 边变绿、running 边动画），底部图例；点节点 → `selectTask` + 跳 Project 工作台。index.css 加了 react-flow 主题。
  - **Decisions inbox**（`decisions/DecisionsView.tsx`）：整页 open+resolved 决策列表，复用 DecisionCard。
  - **Assets library**（`assets/AssetsView.tsx`）：整页 list+detail 并排；从 ArtifactsPanel 抽出可复用 `AssetList` / `AssetDetail`（onBack 可选），Project 右栏仍用 ArtifactsPanel 的窄列 list↔detail 切换。
- 取舍（用户已确认）：决策同时出现在 Project 工作台与 Decisions inbox、资产同时在 Project 右栏与 Assets library——刻意冗余（聚焦工作 vs 专门模块）。详见本节。

### 10.1.5 Phase B-6（Asset 占位"亮起" + Canvas 多视图，2026-06-13）

- **Asset 预置占位 → 产出后亮起**：`AssetList`（ArtifactsPanel + AssetsView 共用）改为渲染**全部** `ARTIFACTS` 蓝图，未产出的灰显 + `disabled` + "not yet"，产出后正常可点并显示状态徽标。还原 V1"既定交付物清单先灰后亮"的体感。
- **Workflow Canvas 多视图**（左上 segmented：Stage / Agent / Human·AI·Auto）：`columnsFor(view)` 按维度分列重排——By Stage=5 阶段；By Agent=按 agent（空列如 Project Control 自动剔除）；By execution=按自动化类（M→Automation / A·C→AI / H→Human）。列头改为**流内 header 节点**（随平移缩放），切视图 `key={view}` 重挂载触发 fitView；非 Stage 视图未完成的依赖边降透明度。点 task 节点仍 selectTask+跳 Project。

### 10.1.6 Phase B-7（Task Detail 透明化：过程时间线 + Grounded findings，2026-06-13）

中间工作台的任务详情过于单薄，补充"过程可视化"与"证据落地"让顾问不再一头雾水：

- **Process 时间线**：每个任务一组具体子步骤（`lib/task-detail.ts` 的 `TASK_TRACE`，按 task id 全覆盖 26 任务），随运行进度点亮——已完成 ✓（绿）/ 进行中（primary pulse）/ 未开始（灰）；未开始的任务标题改为"What it will do"，让顾问预先看到将要发生什么。
- **What it found（grounded）**：`TASK_FINDINGS` 把关键结论挂到来源 artifact——每条 finding 带证据芯片（点击在右栏打开来源），冲突/缺口/异常以 ⚠ amber 高亮。覆盖约 11 个关键任务（知识装配冲突/缺口、因子树访谈改动、指标三维优选、数据打分 0.5/0、O2O 异常、共线性剔除、技术检验红旗、候选对比、KBQ 覆盖与局限等）。无 findings 的任务回退显示 workNote。
- 详情新顺序：标题+一句 summary →（待人工时的 action card）→ **Process** → **What it found** → Draws on → Produces。数据放 `lib/task-detail.ts`，`scenario.ts` 不动；类型加 `TaskStep`/`TaskFinding`。

### 10.2 后端（LangGraph）设计含义（暂不实施，记录约束）

- 编排图中心节点 = 项目管控（05 文档 §8 图），业务智能体不互调；
- `interrupt()` 对应 Gate 服务的人工节点；M 类节点是普通函数节点（不进 LLM）；
- Proposal→Apply 作为图外的持久化协议实现（状态写入不在 LLM 节点内发生）；
- Insight Engine 是独立于主图的事件消费者（非图内节点）。

## 11. 版本与维护

- 本文档为架构基线 v2.0（2026-06-13）；
- 引用假设以"（假设 A_n）"标注，假设状态变更时本文档同步修订；
- 与 00–05 文档冲突时：智能体"做什么"以 00–05 为准，"怎么承载"以本文档为准。
