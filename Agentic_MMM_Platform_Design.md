# Agentic MMM 平台设计文档
**AI Agent Marketing Mix Modeling Platform — Design Specification**

> 本文档将两份规划稿整合为可落地的设计说明：
> （1）**智能体架构**——5 个专业智能体的角色、职责、能力与产出；
> （2）**端到端业务流程**——6 大交付阶段下「智能体 × 阶段」的任务矩阵，以及模拟优化跨阶段穿插的结构性设计。

---

## 1. 设计理念 Overview

平台以 **多智能体协作（Multi-Agent Collaboration）** 的方式交付一个完整的 MMM（营销组合建模）咨询项目。核心思路：

- **专业分工**：把一个 MMM 咨询团队拆解为 5 个角色明确的智能体，各自承载真实项目中的专家职能（咨询顾问 / 数据工程 / 计量科学家 / 报告专家 / 项目经理）。
- **人机协同（HITL）**：由「项目管控智能体」统一调度，在质量关口触发人工介入，保证关键决策可控、可追溯。
- **业务先验驱动**：以业务逻辑（business prior）牵引模型先验（model prior），保证模型结果既统计稳健、又符合商业常识。
- **模拟优化前置穿插**：把「模拟优化」从流程末端的孤立步骤，重构为贯穿假设、建模、洞察三阶段的连续能力（详见第 4 节）。

---

## 2. 智能体架构 Agent Roster

| # | 智能体 | 英文定位 | 一句话职能 |
|---|--------|----------|-----------|
| 1 | 项目管控智能体 | Orchestration Agent | 推进流程、调度多 Agent、质量关口与人工介入 |
| 2 | 商业智能体 | Business Agent | 业务理解、问题定义、方案设计与商业解读 |
| 3 | 数据智能体 | Data Agent | 数据接入、ETL、清洗标准化与质量检验 |
| 4 | 模型智能体 | Model Agent | 先验参数、模型训练调优、模型校验 |
| 5 | 报告智能体 | Report Agent | 故事线、可视化、报告与报表生成 |

---

## 3. 智能体详细设计 Agent Specifications

### 3.1 项目管控智能体 / Orchestration Agent

| 维度 | 内容 |
|------|------|
| **Role** | PM · Human Governance |
| **Responsibility** | • 推进项目进程，控制项目节点<br>• 协调多 Agent 任务拆解与上下文同步<br>• 质量管控触发人工介入，记录项目发展 |
| **Capability** | Task dependency reasoning · Workflow state awareness · Multi-agent collaboration · Context synchronization · Task routing · Quality gate control · Escalation handling |
| **Output** | Agent coordination logs · Escalation alerts · Project workflow status · Dependency tracking |

### 3.2 商业智能体 / Business Agent

| 维度 | 内容 |
|------|------|
| **Role** | Marketing Effectiveness Expert · Senior Strategy Consultant · Solution Lead · Industry Expert |
| **Responsibility** | • 理解行业模式与客户痛点与需求<br>• 保留历史项目经验结果<br>• 解释数据及结果的商业意义、识别机会风险，输出业务逻辑<br>• 从业务与商业逻辑层面定义项目问题与分析方向<br>• 把控 MMM 能力边界，设计分析方案（因子设计、数据设计、模型设计） |
| **Capability** | Business Strategy · Industry benchmarking · Problem structuring · Hypothesis generation · MMM Expertise · Consulting Thinking |
| **Output** | 业务理解 & 业务假设 · KPI 框架 |

### 3.3 数据智能体 / Data Agent

| 维度 | 内容 |
|------|------|
| **Role** | Data Architect · Data Engineer |
| **Responsibility** | • 理解数据源和数据表结构以及数据层级架构<br>• 数据接入并以固定频率更新<br>• 数据清洗，统一标准化<br>• 数据质量与交叉维度统计检验 |
| **Capability** | Data ETL · API Integration · Feature engineering · Data validation · Data Analysis |
| **Output** | Full Dataset · Model Dataset · ETL Code · Data Quality Check · Data mapping table |

### 3.4 模型智能体 / Model Agent

| 维度 | 内容 |
|------|------|
| **Role** | MMM Data Scientist · Econometrics Expert · Marketing Analytics Lead |
| **Responsibility** | • 通过业务先验寻找模型先验参数范围<br>• 模型训练以及参数调优<br>• 模型校验结果 |
| **Capability** | Modeling builder & trainer · Model validation |
| **Output** | Model result（coefficient, parameter）· Statistical & Business validation result |

### 3.5 报告智能体 / Report Agent

| 维度 | 内容 |
|------|------|
| **Role** | PPT Expert · Excel Expert · Dashboard Expert |
| **Responsibility** | • 生成 PPT，生成报告，生成报表<br>• 提炼洞察、组织故事线、表达润色<br>• 数据可视化 |
| **Capability** | Storylining · Insight summarization · Executive messaging · Deck Structuring · Data Visualization |
| **Output** | Business Alignment report（KBQ, Factors, Interview Question）· Data Review（QC report, Dashboard）· Result Visualization（calc sheet+）· Final Report + Simulation |

---

## 4. 端到端业务流程 End-to-End Process

### 4.1 六大交付阶段

| 阶段 | 中文 | 英文 | 阶段目标 |
|------|------|------|----------|
| 01 | 业务启动 | Business | 明确业务问题、KBQ 与业务目标 |
| 02 | 数据准备 | Data | 数据接入、清洗、质量校验与可行性确认 |
| 03 | 先验假设 | Hypothesis | 设计模型层级与渠道结构，确立业务/模型先验 |
| 04 | 模型搭建 | Modelling | 训练调优、产出 ROI/贡献度/响应曲线/优化结果 |
| 05 | 洞察报告 | Insights | 提炼洞察、形成故事线、产出最终报告 |
| 06 | 模拟优化 | Simulation | 跨阶段穿插：定义场景、调参模拟、记录优化结果 |

### 4.2 智能体 × 阶段 任务矩阵

> 注：任务节点按「访谈/收数/确认/建模/报告」的前—中—后时序展开。空格表示该智能体在该阶段无直接交付任务。

#### 01 业务启动 Business
| 智能体 | 任务节点 | 工作内容 |
|--------|----------|----------|
| 项目管控 | 访谈中 | 跟踪访谈完成情况；管理待确认问题 |
| 商业 | 访谈前 | 生成行业 KBQ；生成待确认业务问题 |
| 商业 | 访谈后 | 理解业务逻辑/营销链路；调整 KBQ 生意因子；识别业务目标 |
| 报告 | 访谈前 | 根据待确认《业务问题》生成访谈清单 |
| 报告 | 访谈后 | 输出《业务需求文档》；输出《业务访谈总结》 |

#### 02 数据准备 Data
| 智能体 | 任务节点 | 工作内容 |
|--------|----------|----------|
| 项目管控 | 收数中 | 管理异常问题；跟踪补数进度；管理解决闭环 |
| 商业 | 收数前 | 根据业务需求生成数据需求；定义指标逻辑 |
| 商业 | 收数后 | 判断数据是否满足业务需求；是否影响业务分析；处理逻辑是否需要人为决策 |
| 数据 | 收数后 | 接入数据；识别字段结构；ETL；统一粒度；检查数据（独立+交叉） |
| 报告 | 收数前 | 生成《数据需求列表》；生成《数据收集模版》 |
| 报告 | 收数后 | 输出《Data Review》Dashboard；输出《数据可行性报告》 |

#### 03 先验假设 Hypothesis
| 智能体 | 任务节点 | 工作内容 |
|--------|----------|----------|
| 项目管控 | 确认中 | 跟踪客户确认；模型颗粒度 |
| 商业 | 确认前 | 设计模型层级；定义渠道结构；**定义优化目标场景 ①** |
| 商业 | 确认后 | 输出/调整业务先验（ROI 预期 Base 占比、渠道相对关系） |
| 模型 | 确认后 | 将业务先验转化为模型先验；建立/调整先验参数搜索空间 |
| 报告 | 确认前 | 输出《模型设计文档》 |

#### 04 模型搭建 Modelling
| 智能体 | 任务节点 | 工作内容 |
|--------|----------|----------|
| 项目管控 | 建模中 | 管理异常问题；跟踪先验补充进度；管理解决闭环 |
| 商业 | 建模中 | 判断结果是否符合业务先验；是否有业务先验需调整；**判断模拟优化结果是否可执行 ②** |
| 模型 | 模型 | 调优参数；拟合模型；生成结构模板 |
| 模型 | 结果 | ROI；Contribution；Response curve；**Optimization Result ③** |

#### 05 洞察报告 Insights
| 智能体 | 任务节点 | 工作内容 |
|--------|----------|----------|
| 项目管控 | 报告 | 客户反馈交流 |
| 商业 | 报告前 | 提炼业务洞察；形成策略线；输出业务故事线 |
| 数据 | 报告前 | 聚合模型结果；输出统计数据；输出最终结果集 |
| 报告 | 报告前 | 生成结果可视化展示；生成《最终报告》 |
| 报告 | 报告 | 交互问答；**输出并记录优化场景及结果 ④** |

#### 06 模拟优化 Simulation（跨阶段穿插）
| 智能体 | 阶段 | 工作内容 |
|--------|------|----------|
| 商业 | 假设阶段 | **定义优化目标场景 ①** |
| 商业 | 模型阶段 | **判断模拟结果是否合理 ②** |
| 模型 | 模型阶段 | **每轮调参同步输出模拟结果 ③** |
| 报告 | 报告阶段 | **并记录优化场景及结果 ④** |

---

## 5. 模拟优化的结构性设计 Simulation Threading

平台的核心设计取舍是：**模拟优化（Simulation）不是流程末端的独立步骤，而是贯穿"假设—建模—洞察"三阶段的连续能力**。下表的上标①②③④对应跨阶段闭环链路：

| 链路 | 起点（嵌入阶段） | 终点（模拟优化阶段） | 含义 |
|------|------------------|----------------------|------|
| ① 优化目标场景 | 03 先验假设 · 商业智能体 | 06 假设阶段 | 在假设阶段就定义"要优化什么"，模拟有的放矢 |
| ② 结果合理性 | 04 模型搭建 · 商业智能体 | 06 模型阶段 | 建模过程中即判断模拟结果是否合理、是否可执行 |
| ③ 模拟结果产出 | 04 模型搭建 · 模型智能体 | 06 模型阶段 | 每轮调参同步输出模拟结果，而非建模完成后再跑 |
| ④ 场景记录回流 | 05 洞察报告 · 报告智能体 | 06 报告阶段 | 优化场景与结果在报告阶段沉淀、记录、回流 |

**设计收益**：
- 模拟与建模同节奏迭代，缩短"建模→模拟→反馈"循环；
- 业务先验在模拟早期即介入，避免不可执行的优化解；
- 优化场景全程留痕，最终报告可直接交付"可模拟（simulation-ready）"产物。

---

## 6. 关键协作机制 Collaboration Mechanics

1. **编排中枢**：项目管控智能体负责任务拆解、上下文同步、任务路由与状态感知，是其余 4 个智能体的调度器。
2. **质量关口（Quality Gate）**：每个阶段交付前由项目管控触发校验；不达标则升级（Escalation）并记录，必要时引入人工。
3. **业务—模型先验桥接**：商业智能体产出业务先验 → 模型智能体转化为模型先验参数搜索空间，是 03→04 的关键交接点。
4. **双重校验**：模型结果同时接受 *统计校验*（模型智能体）与 *业务校验*（商业智能体），双过方可进入洞察阶段。
5. **报告即产品**：报告智能体的产出贯穿全程（访谈清单 → Data Review → 模型设计文档 → 最终报告+模拟），保证每阶段都有客户可见交付物。

---

## 7. 阶段产出清单 Deliverables by Phase

| 阶段 | 主要交付物 |
|------|-----------|
| 01 业务启动 | 访谈清单 · 《业务需求文档》· 《业务访谈总结》· KBQ/业务因子 |
| 02 数据准备 | 《数据需求列表》· 《数据收集模版》· Full/Model Dataset · ETL Code · 《Data Review》Dashboard · 《数据可行性报告》 |
| 03 先验假设 | 模型层级与渠道结构 · 业务先验 · 模型先验参数空间 · 《模型设计文档》 |
| 04 模型搭建 | Model result（coefficient/parameter）· ROI · Contribution · Response curve · Optimization Result · 统计与业务双校验结果 |
| 05 洞察报告 | 业务洞察 · 策略故事线 · 统计数据/最终结果集 · 结果可视化 · 《最终报告》 |
| 06 模拟优化 | 优化目标场景 · 逐轮模拟结果 · 优化场景记录（simulation-ready） |
