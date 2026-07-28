# 09 · Business Understanding（业务理解，S1）完整流程文档

> 本文档描述 MMM 平台 **Stage 1 — Business Understanding** 模块的完整设计：流程、
> 输入/输出、过程、功能、数据模型、API 与前端界面。产品 UI 语言为英文；业务内容
> （因子树、访谈、KBQ 等）保留中文。本文档与代码保持一致，修改 S1 时请同步更新。
>
> 对应代码：
> - 蓝图（DAG）：`backend/app/domain/blueprint.py` ↔ `frontend/src/lib/scenario.ts`
> - 处理器：`backend/app/agents/business.py`、`uploads.py`、`validation_rules.py`、`sources.py`
> - 数据模型：`backend/app/domain/models.py` ↔ `frontend/src/lib/types.ts`
> - 状态/存储：`backend/app/store/{state,files,templates,template_seed}.py`
> - 前端界面：`folder/ProjectFolderPanel`、`project/ProfileEditor`、`project/FactorTreeEditor`、
>   `knowledge/TemplatesTab`、`lib/export.ts`

---

## 1. 模块目标

把一个 MMM 项目从「立项」推进到「冻结建模问题集」。S1 结束时（KBQ frozen）应当产出：
- 锁定的**项目档案**（品牌/品类/市场/时间颗粒度/模型颗粒度）；
- 确认的**因子树**（L1–L4 + Indicator，含 AI/访谈建议的接受结果）；
- 完成的**访谈**（四类提纲 + AI 预答 + 纪要回写）；
- 客户签收的**数据需求**与**初步数据校验**结果；
- 冻结的 **KBQ**（关键业务问题）；
- 一份 **Business Understanding 总结**。

设计原则（与 CLAUDE.md 一致）：
- **流程是固定的产品蓝图**（任务 DAG / 依赖 / 人工门 / 选项集），内容由运行时真实计算或
  受控 LLM 生成，从不硬编码。
- **数字来自计算**（`app/mmm`、pandas），叙述来自 LLM；不让叙述代理编造指标。
- **优先用用户上传，回退到参考数据**：S1 各步在「项目文件夹」对应类目有文件时用真实上传
  解析，否则回退到 Danone 参考数据集（保证种子项目无需上传也能跑通）。

---

## 2. 三大基础能力（贯穿 S1）

### 2.1 项目文件夹 Project Folder（真实上传 + 存储 + 解析）
- 入口：右下角浮动坞第三个按钮（`FloatingDock` → `ProjectFolderPanel`）。
- 五个类目：`project_background`（SOW/Brief）、`industry_reference`（行业/竞品资料）、
  `interview_minutes`（访谈纪要）、`data`（数据需求反馈/数据集）、`other`。
- 后端 `app/store/files.py` 落盘到 `data/projects/{id}/files/{category}/`，索引 `_index.json`；
  上传即调用 `app/ingest/extract.py` 抽取文本/表格（pdf/pptx/docx/xlsx/xlsm/csv/txt/md），
  记录 `parsed` / `parseChars` / `parseError`。
- 代理通过 `app/agents/sources.py` 解析「该类目优先上传，空则回退参考」。

### 2.2 知识库模板 Knowledge Templates（按行业、可编辑）
- 入口：Knowledge 页 → **Templates** 标签（`TemplatesTab`）。
- 两类模板：**Factor Tree**（L1–L4 + Indicator 行）与 **Interview Outline**
  （Leadership / Management / Operation 问题）；按行业枚举（与建项目一致的 L1–L3）归属。
- 饮料内置模板由 `template_seed.py` 从 `Assets/Default Factor Tree.xlsx`（94 行）与
  `Assets/Interview Plan & Question.xlsx`（94 题）解析种子，存 `data/templates/_index.json`。
- 支持：克隆、行级增删改、新建行业模板、导出。内置模板需克隆后才能编辑。

### 2.3 全量导出 Universal Export
- 每个产出物都可导出（`lib/export.ts`）：sheet → 真 `.xlsx`（懒加载 SheetJS），
  doc/slides/markdown → `.md`。模板编辑器导出 `.xlsx`。

---

## 3. 角色 / 产物 / 人工门总览

- **执行代理**：S1 全部由 **Business Agent** 承担（`agent: business`）。
- **任务类型 klass**：`M` 机械计算 · `A`/`C` LLM 受控生成 · `H` 人工（上传/决策/导出）。
- **10 个产物（artifacts）**：

| ID | 名称 | 产出任务 | 格式 | 说明 |
|---|---|---|---|---|
| `a-sow` | SOW & Brief (provided) | 1.0a | doc | 输入：列出上传的立项材料（内部） |
| `a-scope` | Project Profile | 1.0 | sheet | 项目档案（含时间/模型颗粒度），可编辑 |
| `a-source-materials` | Reports & Materials (provided) | 1.1a | doc | 输入：行业/竞品资料（内部） |
| `a-knowledge-package` | Industry Knowledge | 1.1 | sheet | 行业知识包（内部） |
| `a-factor-tree` | Factor Tree | 1.21 | sheet | 因子树（L1–L4+Indicator，含逐条接受状态） |
| `a-interview` | Interview | 1.3 | sheet | 四类提纲 + AI 预答 + 纪要回写 |
| `a-data-request` | Data Request & Review | 1.5 | sheet | 每 L3 一工作簿、每 L4 一 sheet |
| `a-data-validation` | Preliminary Data Validation | 1.5v | sheet | 四条初步校验规则 |
| `a-kbq` | Key Business Questions | 1.6 | sheet | 结构化 KBQ |
| `a-bu-summary` | Business Understanding Summary | 1.7 | doc | S1 成果总结 |

- **人工决策门（5）**：`d-1.0` 锁定档案 · `d-1.21` 确认因子树 · `d-1.4` 接受访谈驱动的因子变更 ·
  `d-1.5` 数据需求签收 · `d-1.6` 冻结 KBQ。
- **AI 认知选项（2）**：`ai-1.21` 指标选型取向（Conservative/Balanced/Aggressive）·
  `ai-1.6` KBQ 归类方式（6 类法 / 按利益方 / 按渠道）。

---

## 4. 完整流程（18 个任务，分 7 个逻辑步骤）

> 每步给出：**输入 → 过程 → 输出 → 人工确认**。任务 ID 与蓝图一致。

### 步骤 0 · 提供立项材料 → 框定项目档案（1.0a → 1.0）
- **1.0a Provide SOW & brief**（H/upload，产 `a-sow`）
  - 提醒用户把 SOW/Brief 上传到项目文件夹（Project Background）。
- **1.0 Frame project profile**（C，产 `a-scope`，依赖 1.0a）
  - 输入：上传的 SOW/Brief（优先）或参考 scope。
  - 过程：LLM 抽取项目简介；从真实 scope 构建**模型颗粒度矩阵**（Product × Channel ×
    Platform & Region）；默认时间颗粒度 Month。写入 `ProjectState.profile` 并渲染 `a-scope`。
  - 输出：`ProjectProfile`（projectIntro / timeGranularity / modelScope / sourceOrigin）。
  - **可编辑**：前端 `ProfileEditor`（在 a-scope 详情内）支持改时间颗粒度（Year/Month/Week）与
    **维度矩阵构建器**（维度值 → 叉乘生成 scope 行 → 逐行可改/删）；`PUT /profile` 落库并重渲染。
  - **人工门 d-1.0**：确认并锁定档案（rework → 重框）。

### 步骤 1 · 组装行业知识（1.1a → 1.1）
- **1.1a Upload reports & materials**（H/upload，产 `a-source-materials`）：提醒上传行业/竞品资料
  到 Industry Reference。
- **1.1 Assemble industry knowledge**（C，产 `a-knowledge-package`，依赖 1.1a）：LLM 基于真实行业
  知识装配 L1/L2 骨架 + 品牌生意分析框架（内部产物）。

### 步骤 2 · 推导因子树 + 逐条确认（1.21 → 1.21d）
- **1.21 Derive factor tree & indicators**（C，产 `a-factor-tree`，依赖 1.1）
  - 输入：按项目行业从知识库匹配的**标准 Factor Tree 模板**（`templates.best_match`）为 baseline；
    颗粒度与 Project Profile 一致；AI 推荐基于上传的行业资料（优先）/参考。
  - 过程：baseline 行（source=template, status=baseline）+ LLM 推荐的 L3/L4/Indicator
    （source=ai, status=proposed, 带 rationale）。写入 `ProjectState.factor_tree`，渲染 `a-factor-tree`。
  - 输出：`FactorTree.rows[]`（每行带 source/status/rationale/evidence），AI 推荐覆盖到
    Indicator 级；维度统计 sheet + AI Recommendations sheet。
  - `ai-1.21` 选项：指标选型整体取向。
  - **逐条接受**：前端 `FactorTreeEditor`（在 a-factor-tree 详情内）对每条 proposed 行 **Accept/Reject**，
    支持「Accept all」、按 source 过滤、行级编辑、新增因子；`PUT /factor-tree` 落库并重渲染，
    同步 `analysis.factor_l4`（供下游使用）。
  - **人工门 d-1.21**：确认 L3/L4 + 主指标（rework → 重推导）。

### 步骤 3 · 访谈（1.3 → 1.3b → 1.4a → 1.4 → 1.4d）
- **1.3 Draft interview outline**（A，产 `a-interview`，依赖 1.21d）
  - 输入：行业**访谈提纲模板** + 项目/行业资料；因子树（用于 Data 类）。
  - 过程：生成**四大类**提纲——Leadership / Management / Operation 取自模板（含 role）；
    **Data 直接由因子树派生**：每个 accepted/baseline 数据点一条「确认数据是否存在/来源/颗粒度/
    历史/缺口」。写入 `analysis.interview_questions`，渲染 By Category + Outline。
- **1.3b AI pre-answers the outline**（C，依赖 1.3）
  - 过程：LLM 对每题给**初步回答 + 置信度 + 来源（溯源）**；追加 Disclaimer sheet
    （"AI preliminary answers … knowledge for reference"）+ AI Pre-answers sheet。
- **1.4a Upload interview minutes**（H/upload，依赖 1.3b）：提醒访谈完成后把纪要上传到
  Interview Minutes。
- **1.4 AI writeback from minutes**（C，依赖 1.4a）
  - 输入：上传纪要（优先）或参考 12 份纪要。
  - 过程：LLM 据纪要写**每题最终答案 + 来源**（Minutes Writeback sheet）；并提出**因子变更**
    （add/modify L1–L4 / Indicator / 颗粒度，带 rationale 与纪要引用），作为 `status=proposed,
    source=interview` 行追加进因子树，同时生成 Proposal/Insight。
- **1.4d Confirm interview-driven factor changes**（H/decision d-1.4）：用户在 FactorTreeEditor
  逐条接受/拒绝访谈驱动的变更（rework → 重消化）。

### 步骤 4 · 数据需求 + 初步校验（1.5 → 1.5r → 1.5b → 1.5v）
- **1.5 Generate data request**（A，产 `a-data-request`，依赖 1.4d）
  - 过程：按因子树 accepted 指标，**每个 L3 一个工作簿、每个 L4 一个 sheet**；列 =
    时间维（按 Profile 时间颗粒度）+ 模型维（Profile 模型 scope 维度）+ 该 L4 指标；含示例行。
    生成 Template Index + 各 L4 sheet + Review & Sign-off（参考 `Assets/Data Request.xlsx`）。
- **1.5r Client review & sign-off**（H/decision d-1.5）：与客户走查、记录签收。
- **1.5b Export & send data request**（H/export）：导出工作簿分发、标记已发。
- **1.5v Preliminary data validation**（M，产 `a-data-validation`，依赖 1.5b）
  - 输入：项目文件夹 Data 类的上传反馈（优先，pandas 解析）或参考数据集。
  - 过程（`validation_rules.run_rules`，**确定性 pandas 计算**）四条规则：
    1. **完整性**：时间跨度 > 2 年；
    2. **颗粒度**：与 Profile 时间颗粒度一致；
    3. **波动性**：数值有变化（变异系数 CV > 0.05）；
    4. **统计一致性 & 同比可比**：逐年记录数可比（min/max ≥ 0.7）。
  - 输出：PASS/FLAG 明细表；FLAG 进 findings。无数据时提醒上传反馈。

### 步骤 5 · KBQ（1.6 → 1.6d）
- **1.6 Generate KBQ**（C，产 `a-kbq`，依赖 1.5v）：综合档案 + 因子树 + 访谈，输出结构化 KBQ
  （头部说明 / 分类统计 / KBQ 全表）。`ai-1.6` 选项：归类方式。
- **1.6d Confirm & freeze KBQ**（H/decision d-1.6）：冻结 KBQ，**关闭 Business Understanding**
  （rework → 重生成）。

### 步骤 6 · 业务理解总结（1.7）
- **1.7 Business Understanding summary**（C，产 `a-bu-summary`，依赖 1.6d）：综合所有已确认 S1 产物，
  LLM 写执行摘要 + 关键统计（档案颗粒度 / 因子数 / 访谈四类计数 / 校验 FLAG 数 / KBQ 数）。
  S1 完成后下游 `2.0a`（数据采集）依赖 `1.7`。

---

## 5. 关键数据模型（`models.py` ↔ `types.ts`）

```text
ProjectFile        { id, category, filename, size, contentType, uploadedAt, parsed, parseChars, parseError }
KnowledgeTemplate  { id, kind('factor_tree'|'interview'), name, industryL1, industryL2?, version,
                     builtin, factorRows[], interviewQuestions[], updatedAt }
FactorTreeRow      { l1, l2, l3, l4, indicator }
InterviewQuestion  { category('Leadership'|'Management'|'Operation'|'Data'), role, question }
ProjectProfile     { projectIntro, timeGranularity('Year'|'Month'|'Week'),
                     modelScope:{ dimensions:[{name, values[]}], rows[][] }, sourceOrigin }
FactorRow          { id, l1, l2, l3, l4, indicator,
                     source('template'|'ai'|'interview'|'manual'),
                     status('baseline'|'proposed'|'accepted'|'rejected'), rationale, evidence }
FactorTree         { rows: FactorRow[] }
```
`ProjectState` 新增字段：`profile: ProjectProfile?`、`factor_tree: FactorTree?`。
`heal_state()` 在加载旧存档时回填新增的蓝图任务（升级不丢数据、不报 KeyError）。

---

## 6. API 一览（新增）

```text
# 项目文件夹
GET    /api/projects/{id}/files
POST   /api/projects/{id}/files        (multipart: category, file)
GET    /api/projects/{id}/files/{fileId}     下载
DELETE /api/projects/{id}/files/{fileId}

# 项目档案（可编辑颗粒度 + 模型 scope）
PUT    /api/projects/{id}/profile      → 重渲染 a-scope

# 因子树（逐条接受/拒绝/编辑）
PUT    /api/projects/{id}/factor-tree  → 重渲染 a-factor-tree，同步 analysis.factor_l4

# 知识库模板（跨项目）
GET    /api/templates?kind=&industryL1=
GET    /api/templates/{id}
POST   /api/templates                  新建/保存（version 自增）
POST   /api/templates/{id}/clone
DELETE /api/templates/{id}             （内置模板禁止删除）
```
（既有：`/state` `/run` `/run/status` `/reset`、`/decisions/{id}/resolve`、
`/assignments/{id}/submit`、`/proposals/{id}/resolve`、`/ai-choices/{setId}`、`/assistant` 等。）

---

## 7. 前端界面

- **Project Folder 浮动面板**（右下角）：分类目拖拽上传、解析状态、下载、删除。
- **ProfileEditor**（a-scope 详情内）：项目简介、时间颗粒度切换、**模型 scope 维度矩阵构建器**
  （维度值 → 生成 scope 行 → 行级编辑/删除）、Save。
- **FactorTreeEditor**（a-factor-tree 详情内）：L1–L4+Indicator 表，proposed 行逐条 **Accept/Reject**、
  Accept all、AI/全部过滤、行级编辑、新增因子。
- **Knowledge → Templates**：行业模板选择/克隆/行级编辑/新建/导出。
- **导出按钮**：每个产物详情头部都有 Export（sheet→.xlsx，其它→.md）。

---

## 8. Autopilot vs 交互

- **交互模式**：上传由用户在项目文件夹完成；决策门在 Decisions 页解决；因子树/档案在对应编辑器
  中编辑保存；AI 推荐逐条接受/拒绝。
- **Autopilot**：自动补齐上传（参考数据回退）、用「推荐项」自动解决 5 个决策门，逐任务推进。
  - 注意：autopilot 解决的是**决策门**；因子树的**逐条 accept/reject** 是独立的人工动作，
    autopilot 不会自动接受，AI/访谈建议会以 `proposed` 状态保留，等人工在 FactorTreeEditor 处理。

---

## 9. 真实运行验证（Danone Mizone 种子项目）

一次完整真实跑通（真实 LLM + 真实参考数据）后 S1 全部 18 任务完成、10 个产物落地，例：
- Profile：真实简介、Month 颗粒度、模型 scope 4 行 × 3 维（Product/Channel/Platform&Region）。
- Factor Tree：102 行 = 94 baseline（饮料模板）+ 8 AI 推荐（proposed，待接受）。
- Interview：By Category / Outline / Disclaimer / AI Pre-answers / Minutes Writeback 五表。
- Data Request：15 个 sheet（按 L3·L4 命名）。
- Data Validation：在真实 23,790 行数据上四条规则全 PASS（2023–2025、Month、CV 21.69、YoY）。
- KBQ：29 条（来自归档 KBQ 工作簿）。
- BU Summary：真实执行摘要。

---

## 10. 设计约束与回退策略

- MMM 引擎与参考加载器仍为 Danone 专用（单一 `REFERENCE_DIR`）。**S1 框定已按项目上传落地**，
  仅在缺失时回退参考；定量 MMM 引擎（S2–S5）仍跑同一参考数据集——模型引擎的按项目数据绑定为后续工作。
- 参考文件名带版本号时，`ref()` 按路径段做**版本容错 glob 回退**；KBQ 仅存档时回退归档工作簿。
- 改 S1 时务必同步四处契约：`blueprint.py`/`scenario.ts`、`models.py`/`types.ts`。
