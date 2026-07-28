# AgenticMMM 智能体体系总览

> 依据 `reference/00.MMM Agent - StatusCheckList.xlsx` 及 reference 全量文档（2026-06 版）整理。
> 任务编号即产品功能编号，全文与 StatusCheckList 保持一一对应。

## 1. 平台定位

AgenticMMM 是一个 **Workflow 性质的 Multi-Agent MMM（Marketing Mix Modeling）平台**：

- 以**因子树（L1–L8）为主数据脊柱**，从项目范围框定、业务理解、数据治理、建模到报告解读全程挂载在这棵树上；
- 以**任务编号体系（1.0–4.1）**组织全部工作项，每个任务有明确的 Input/Output/Function 属性与 Owner；
- 以**"AI 召回/生成 → 人确认 → 修改留痕 → 知识回流"**为统一人机协作范式，所有流程和 Artifact 可视、可管理；
- 由**项目管控智能体**编排五阶段流水线，在质量关口（Gate）触发人工介入。

## 2. 智能体总览

| 编号 | 智能体 | 英文名 | 核心定位 | 详细文档 |
|---|---|---|---|---|
| 1.x | 商业智能体 | Business Agent | 把 SOW、行业知识、品牌资料、分层访谈转化为可建模的业务因子结构（L1–L4）与数据需求 | [01-business-agent.md](01-business-agent.md) |
| 2.x | 数据智能体 | Data Agent | 数据校验打分、宽表集成、业务/技术双重交叉校验，产出 Model Input | [02-data-agent.md](02-data-agent.md) |
| 3.x | 模型智能体 | Model Agent | 先验设置、模型调优、技术检验、业务检验 | [03-model-agent.md](03-model-agent.md) |
| 4.x | 报告智能体 | Report Agent | 标准报表生成 + 交互问答，模型结果的业务化解读 | [04-report-agent.md](04-report-agent.md) |
| 0.x | 项目管控智能体 | Project Control Agent | 推进项目进程、控制项目节点；协调多 Agent 任务拆解与上下文同步；质量管控触发人工介入；记录项目发展 | [05-project-control-agent.md](05-project-control-agent.md) |

> 项目管控智能体在 StatusCheckList 中占位但未编号，本设计赋予其 0.x 编号段（平台级横切能力）。

## 3. 任务编号体系（StatusCheckList 全量映射）

### 商业智能体（1.x）

| 编号 | 类别 | 任务 | 说明 | 源文件 |
|---|---|---|---|---|
| 1.0 | Input | Scope | 框定项目范围及分析颗粒度 | 【MMM AI】商业智能体-Scope |
| 1.1 | Input | 行业知识 | 行业特性理解，L3/L4 生成依据 | 【MMM AI】商业智能体-行业知识 |
| 1.2 | I/O | factor&data_request | 因子结构与数据需求总载体 | 【MMM AI】商业智能体-factor&data_request |
| 1.21 | I/O | 生意因子结构 L1–L4 | 根据行业特性梳理 factor | 同上 |
| 1.22 | Input | 因子对应指标 | L4 指标库 + 补充 | 同上 |
| 1.23 | I/O | 数据准入标准及数据模板 | 生成数据需求模板 | 同上（模板 sheets） |
| 1.24 | Input | 模型分类及应用场景 | 概率模型 vs OLS 选型 | 同上（模型 sheet） |
| 1.3 | I/O | Interview | 品牌特性理解（KBQ 闭环） | 访谈框架及纪要/ |
| 1.31 | Input | 品牌报告 | 财报/行业研究（如 CICC Project Aurora） | 202408_Competitor Benchmark_CICC |
| 1.32 | Input | 访谈框架及纪要 | 分层访谈提纲 + 11 份纪要 | Interview Plan & 纪要/ |
| 1.33 | Output | 访谈纪要总结框架 | 按框架梳理品牌情况 | — |
| 1.34 | Output | 关键业务问题（KBQ） | 项目需解答的客户关键业务问题 | KBQs.xlsx |
| 1.4 | Function | 项目知识积累 | 设计方案 + 接口 + 维护培训 | 平台级能力 |
| 1.5 | Function | 项目因子主数据管理 | 知识交互，增删改 | 平台级能力 |

### 数据智能体（2.x）

| 编号 | 类别 | 任务 | 说明 | 源文件 |
|---|---|---|---|---|
| 2.1 | I/O | Data Validation | 数据通用校验 | Data Validation_2.1 |
| 2.11 | Input | 数据通用校验标准 | 通用标准 + 打分规则 | 同上 |
| 2.12 | Output | 数据质量评分 | 按 L1–L4×指标逐项打分 | 同上 |
| 2.2 | I/O | Data Process | 数据处理与集成 | Data Process 2.21–2.24 |
| 2.21 | Input | 宽表数据集维度 | 统一长表 Schema（L1–L8） | 2.21&2.23.xlsm |
| 2.22 | Input | 数据处理 | 37 个数据 Task + 人机确认处理逻辑 | 2.22.xlsx（TaskLog） |
| 2.23 | I/O | 数据字典 | ODS→DW ETL 逻辑 | 2.21&2.23.xlsm |
| 2.24 | Output | 数据集 | 统一维度集成的数据全集 | 2.24.xlsx |
| 2.3 | I/O | 数据交叉校验 | 业务 + 技术双重校验 | — |
| 2.31 | Input | 指标业务校验规则 | 六步法 + 因子树下钻 + 先验提取 | 因子树+下钻维度+交叉检验_2.31 |
| 2.32 | Output | 数据展示 | Charting + 趋势解读 + 客户 sign-off | Data Analysis_2.32 |
| 2.33 | Input | 指标技术校验规则 | CV/Pearson/VIF 统计打分 | Data statistical test_2.33 |
| 2.34 | I/O | 指标筛选 | OLS 快速验证 Contribution / ROI Range | — |
| 2.35 | Output | Model Input | 生成模型输入数据 | — |

### 模型智能体（3.x）

| 编号 | 类别 | 任务 | 说明 | 源文件 | 状态 |
|---|---|---|---|---|---|
| 3.1 | Input | 模型先验设置 | 由数据及业务总结生成先验 | 3.1.先验设置规则（**实际为空**） | ⚠️ 缺口 |
| 3.2 | Input | 模型调优规则 | 调参寻优 | **无文件** | ⚠️ 缺口 |
| 3.3 | Output | 模型技术检验 | 五指标交叉验证 + 红旗规则 | 3.3.Tech Review 模板及技术验证规则 | 完备 |
| 3.4 | Output | 模型业务检验 | 结果是否符合先验 | 依赖 3.1，无独立文件 | ⚠️ 缺口 |

缺口的补全草案见 [06-gaps-and-proposals.md](06-gaps-and-proposals.md)。

### 报告智能体（4.x）

| 编号 | 类别 | 任务 | 说明 | 源文件 |
|---|---|---|---|---|
| 4.1 | Output | 总结结果生成报表及洞察 | 标准模板 + 交互问答 | 5D.模型解读内容细化需求 |

## 4. 端到端主流程（流程大框架）

StatusCheckList「流程大框架」sheet 定义了商业 Agent 主导的前段流程，结合各文件可还原全链路：

```
①Scope ─→ ②Factor ─→ ③Indicator ─→ ④Interview ─→ ⑤Data Request
                                        │（纪要回流刷新②③，AI 标注改动、人确认）
⑤收数 ─→ 2.1 校验打分 ─[G:0.5人工决策]→ 2.2 集成宽表 ─→ 2.31 业务校验六步法
       ─→ 2.32 Charting+趋势解读 ─[G:客户sign-off]→ 2.33 统计校验 ─→ 2.34 OLS 预验证
       ─→ 2.35 Model Input
3.1 先验设置 ─→ 3.2 调优 ─→ 3.3 技术检验 ─[G:红旗即停]→ 3.4 业务检验 ─[G:先验对照]
4.1 标准报告 + 交互问答 ─[G:客户Review]
```

各步骤的关键规则：

| 步骤 | 规则要点 |
|---|---|
| ① Scope | 根据 SOW 生成；1 条产品线/组；渠道 ≤4（1 线上 + MT/TT/AFH 3 线下）；地区和平台 ≤6 组 |
| ② Factor | L1/L2 全行业一致，**100% 知识召回**；L3/L4 按行业知识召回默认全要，可补充/删除 **10%–20%**（来源：AI 推荐 / 品牌报告 / 访谈），**每个补充需人确认**；增删原因必须记录，用于维护知识库 |
| ③ Indicator | 知识库已有 L4 → 指标 100% 召回，可增删 10%–20%；知识库没有的 L4 → AI 补充指标 |
| ④ Interview | 按 KBQ 框架，Agent 先阅读已有材料作答，再按访谈层级生成待 validate 问题；访谈完成后上传纪要，回流修改 ②③；**AI 标出要改什么，人确认** |
| ⑤ Data | 以 L3 为表、L4 为 sheet、指标颗粒度+指标为列生成数据需求文档；收数后按检查规则初步诊断 |

## 5. 人机协作统一范式

全平台所有环节遵循同一协作模型，产品上对应 Gate / CollabMode 设计：

### 5.1 三态打分制（数据/指标级 Gate 判定）

| 分值 | 含义 | 系统行为 |
|---|---|---|
| 1 | 通过 | 自动验收，流程继续 |
| 0.5 | 边缘 | **人进入决策如何处理**（产品的人工介入触发点） |
| 0 | 不可用 | 直接弃用该指标并**预警**；若某因子的所有指标均为 0，升级预警 |

### 5.2 增删阈值（知识召回类 Gate）

- L1/L2：锁定，不可改；
- L3/L4 与指标：默认全召回，允许 10%–20% 增删，每项增删需人工确认 + 记录原因；
- 超出阈值的改动 → 升级到与 Solution Team 的联合 Review（产品反馈明确要求 tracking）。

### 5.3 客户 Sign-off（外部确认类 Gate）

2.32 Charting 每张图带 `Sign-off Y/N` 栏；数据问题以「数据&指标沟通表」（问题/负责人/反馈三列）的形式与客户往返，是流程的一等公民 Artifact。

### 5.4 修改留痕与知识回流

所有因子/指标的增删改记录（项目、原因、确认人）回写知识库（任务 1.4/1.5），形成跨项目积累。

## 6. 因子树：全平台主数据脊柱

| 层级 | 含义 | 治理规则 | 用途 |
|---|---|---|---|
| L1 | 生意因子大类（生意基本盘 / 消费者需求驱动 / 渠道成交驱动 / 促销优惠） | 全行业通用，100% 召回 | 模型分组、报告 Group 映射 |
| L2 | 生意因子小类（外部/内部因素、品牌广告/内容种草、渠道执行…） | 全行业通用，100% 召回 | 同上 |
| L3 | 生意因子（品类趋势、宏观环境、竞争格局、品牌传播…） | 行业知识召回 + 10–20% 增删 | 数据需求文档的"表" |
| L4 | 生意影响因子（市场规模、季节性趋势、Digital Display、冰柜…） | 行业知识召回 + 10–20% 增删 | 数据需求文档的"sheet"；模型变量挂载点 |
| 指标 | L4 对应的可量化 metric（曝光量/花费/GRP/ND/WD…） | 知识库召回 + AI 补充 | 数据校验/统计检验的打分对象 |
| L5–L8 | 下钻维度（by platform / by competitor / by campaign / by influencer tier…） | 因子级配置 | 异常定位下钻路径；Deepdive 分析 |

每个 L4 同时携带：指标选择、时间颗粒度（最低月度）、模型颗粒度（by product/category × channel × region）、下钻维度、相关业务团队、数据来源、数据准入标准（完整性/准确性/颗粒度/波动性/一致性）。

## 7. Artifact 体系总表

| Artifact | 产出任务 | 类型 | 下游消费方 |
|---|---|---|---|
| Scope 表 | 1.0 | 文档 | 全部智能体（颗粒度约束） |
| 行业知识库 | 1.1 | 知识 | 1.21/1.22 因子召回 |
| 因子树（L1–L4 + 指标 + L5–L8） | 1.21/1.22/2.31 | 主数据 | 全链路 |
| KBQ 列表 | 1.34 | 文档 | 访谈、模型设计、报告 |
| 分层访谈提纲 + 纪要 | 1.32 | 文档 | 因子树刷新、数据需求 |
| 数据需求模板（L3 为表/L4 为 sheet） | 1.23 | 模板 | 客户收数 |
| Seasonality Calendar | 1.2 | 知识 | 模型季节性变量 |
| Competitors List | 1.3 | 主数据 | 竞品因子、数据采集 |
| 数据质量评分表 | 2.12 | 评分 | Gate 判定、客户沟通 |
| 数据&指标沟通表（Q&A） | 2.x | 工作流 | 客户确认闭环 |
| TaskLog（37 数据任务） | 2.22 | 工作流 | 项目管控、进度跟踪 |
| 数据字典（ODS→DW） | 2.23 | 元数据 | 数据血缘、复现 |
| 统一长表数据集 | 2.24 | 数据 | 2.3x 校验、建模 |
| Charting + 趋势解读 Deck | 2.32 | 报告 | 客户 sign-off |
| 统计检验结果表 | 2.33 | 评分 | 指标筛选 |
| Model Input | 2.35 | 数据 | 模型智能体 |
| 先验设置表 | 3.1 | 配置 | 建模、3.4 业务检验 |
| Tech Review 报告 | 3.3 | 报告 | Gate、报告智能体 |
| 模型结果长表（Group1–6 mapping） | 4.1 | 数据 | 报告生成 |
| 标准报告（Charting by 渠道 + Decomp + 技术检验） | 4.1 | 报告 | 客户交付 |
| 项目日志 / 决策审计 | 0.x | 日志 | 复盘、知识回流 |

## 8. 知识库分区（产品反馈要求）

| 分区 | 内容 | 写权限 |
|---|---|---|
| Solution 团队沉淀区 | 跨项目通用：L1/L2 结构、行业知识包、校验/检验规则库、解读话术模板 | Solution Team |
| 项目组定制区 | 本项目因子增删、客户特定指标定义、数据口径备忘 | 项目组（带 tracking） |

其他产品反馈要点：indicator 页要带出 factor 上下文（"一张宽表串起所有信息"）；KBQ 列表需声明仅供参考（typical list, 可不 follow）；LLM 可切换；Govern 范围由平台方定义。

## 9. 双行业案例说明

reference 混合了两个真实案例，建模知识库时必须明确行业归属：

| 案例 | 行业 | 涉及文件 | 特征体系 |
|---|---|---|---|
| Danone 脉动（主案例） | 饮料/快消 | Scope、KBQs、行业知识、访谈全套、Data Validation/Process、5D | MT/TT/AFH/EC+O2O 渠道；Nielsen/Kantar/Smartpath 三方数据 |
| 医学营养品案例 | 医药营养（HCP 体系） | factor&data_request 的 PFME sheet、Data Analysis_2.32（Charting + 趋势解读 PPT） | PFME/ATL/BTL/HCP-facing；CBEC/LOCAL；贝叶斯层级模型设计实例 |

→ 行业知识包必须可插拔（饮料包 / 医药营养包 / …），L1/L2 跨包共享，L3/L4+指标按包加载。

## 10. 文档索引

- [01-business-agent.md](01-business-agent.md) — 商业智能体
- [02-data-agent.md](02-data-agent.md) — 数据智能体
- [03-model-agent.md](03-model-agent.md) — 模型智能体
- [04-report-agent.md](04-report-agent.md) — 报告智能体
- [05-project-control-agent.md](05-project-control-agent.md) — 项目管控智能体
- [06-gaps-and-proposals.md](06-gaps-and-proposals.md) — 业务规则缺口与补全草案（待业务回填）
- [07-assumptions-log.md](07-assumptions-log.md) — 平台方补充假设登记表（含已裁决事项）
- [08-product-architecture-v2.md](08-product-architecture-v2.md) — 产品架构 v2（双平面 Human-AI Collaboration 架构）

> 阅读顺序建议：00（体系）→ 08（架构怎么承载）→ 01–05（各智能体细则）→ 06/07（缺口与假设）。
> 文档分工：00–05 定义智能体"做什么"；08 定义产品"怎么承载"；06 是业务方要回填的规则缺口；07 是平台方先行假设的登记与裁决记录。
