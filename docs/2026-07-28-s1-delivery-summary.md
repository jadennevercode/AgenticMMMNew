# S1 需求交付说明（2026-07-28）

本次共交付 **3 组需求**，全部已合入 `main`。三组都遵循项目铁律 **"no mock data"**（无真实上传的材料/纪要就不产出）、**复用现有 HITL 门禁而非新增**，并全程走 superpowers 流程（spec → plan → 逐任务 TDD + 双阶段 review → 最终整分支 review）。

相关设计/计划文档见 `docs/superpowers/specs/` 与 `docs/superpowers/plans/`（`2026-07-28-*`）。

---

## 需求组一：Interview 只提问 + 按真实纪要重建

分支 `feature/interview-questions-only`（commits `ed8fe3a`→`6c231d1`，清理 `95c388d`）。

| 子需求 | 改之前 | 改之后 |
|---|---|---|
| 提纲只提问、砍 pre-answer | `1.3b` 任务让 AI 预答每个提纲问题，质量差 | `1.3b` 全链路移除（blueprint / scenario / registry / handler）；提纲只出问题 |
| 纪要回填答案 | 已有，混在旧逻辑 | 保留：纪要能答的提纲问题自动回填答案 |
| 提取新问题 | 无 | 从每份纪要抽出业务**自己新问的、提纲外的问题**（连答案），标 `origin=新问题` |
| 组织架构对齐真实 | 用预设分层（高层/管理/执行） | 按**纪要文件名**重建成真实部门（AI 推断 + 文件名兜底）；没对上的提纲问题丢弃 |
| 访谈 sheet 列 | 含 AI预答/置信度/来源等冗列 | 精简为 问题/答案/来源 + `Origin`（提纲 vs 新问题） |
| 清理项 | — | 文件名解析正则改为末尾锚定（`记录部`/`Interviewer` 不再被误剥）；Excel sheet 名去非法字符 + 31 字符裁剪 + 重名去重 |

**核心改动文件：** `backend/app/agents/business.py`、`backend/app/domain/blueprint.py`、`frontend/src/lib/scenario.ts`、`backend/app/store/state.py`（heal_state）。
**新增/重写测试：** `backend/app/agents/_test_interview.py`、`backend/app/domain/_test_blueprint_interview.py`、重写 `backend/tests/test_minutes_merge.py`。

**成果：** 访谈从"AI 猜答案"变成"贴近真实访谈记录"——只提问、按真实纪要回填 + 抽新问题、按真实部门组织。

---

## 需求组二：Factor tree 模板基线结合上传材料

分支 `feature/s1-materials-grounding`（Phase 1，commits `3c6649a`/`7fdd6c4`）。

- **改之前：** 模板因子**逐行照抄**成自动生效的 `baseline`，不看上传材料 → 会带上不适用本品牌的因子、或与材料命名冲突。
- **改之后：** `derive_factor_tree` 新增一步 **AI 对账**，每条模板行给判定：
  - **keep**（材料支持）→ 保持 `baseline` 自动生效
  - **rename**（命名不一致）→ 就地改名对齐材料
  - **downgrade**（材料未提及/矛盾）→ 降级为 `proposed`「待确认」，走**现有 d-1.21 门禁**由人定留/弃（**不硬删**）
  - 无材料 / LLM 失败 → **照抄模板兜底**，树永不被清空
  - 与 AI 材料因子按 key 去重

**核心改动文件：** `backend/app/agents/business.py`（`_apply_reconcile_verdicts` 纯函数 + `_reconcile_baseline_with_materials` LLM 包装 + 接入 `derive_factor_tree` 非上传路径）。
**新增测试：** `backend/app/agents/_test_factor_reconcile.py`。

**成果：** 模板部分从"照抄"变成"与材料一致"，冲突消除；不适用的因子降级待确认而非静默保留。

---

## 需求组三：访谈纪要驱动数据请求指标增减

分支 `feature/s1-materials-grounding`（Phase 2，commits `61b2047`→`d72f8eb`）。

- **改之前：** 数据请求（1.5）只把因子树投影成工作簿（指标→列），**完全不读纪要**。
- **改之后：**
  - 从纪要抽取每个 L4 的**指标 add/remove 提案**（带 rationale + 引用），列在数据请求产物的审阅区，**不自动应用**
  - 新增 `DataRequestReviewPanel`，逐条 **Accept/Reject**
  - **accept 和 reject 都粘滞**——同意的应用到请求列，拒绝的不再反复弹出
  - **只碰数据请求字段，不动因子树**；**不加新门禁**，复用现有 **1.5d** 签核

**层次说明：** 访谈对"因子"的影响本就通过因子树（1.4/d-1.4）进入数据请求；本需求补的是"数据请求**字段**层"——数据可得性/采集口径信号（哪些指标真能拿到 / 不跟踪），与因子重要性是两回事。

**核心改动文件：**
- `backend/app/store/state.py`（`data_request_field_edits` 存储）
- `backend/app/agents/business.py`（`_apply_field_edits` 应用 + `_datareq_proposals` 抽取 + `_filter_proposals` 纯过滤 + `_datareq_review_sheet` 渲染）
- `backend/app/main.py`（`PUT /data-request/review` endpoint）
- `frontend/src/api/client.ts`（`reviewDataRequest`）、`frontend/src/components/project/panels/DataRequestReviewPanel.tsx`、`frontend/src/lib/types.ts`

**新增测试：** `backend/app/agents/_test_datareq_review.py`。

**成果：** 访谈里的数据可得性信号能落到数据请求上，且由人逐条把关。

---

## 已知的非阻断项（park，需要再单独处理）

1. 需求组三：每次 accept/reject 会重跑一次 LLM 重推 pending 提案（spec 选定的"pending 不落库、每次重推"设计）。
2. 需求组三：若在 1.5d 签核**之后**再有 ruling，会把产物状态翻回 `proposed`（UI 上不可达——面板在无 pending 时隐藏）。

## 验证与使用提醒

- 单元测试（可运行脚本）：`_test_interview` / `_test_factor_reconcile` / `_test_datareq_review` / `test_minutes_merge` 均绿；前端 `npm run build` 通过。
- 依赖 `reference/` 目录的既有测试在本机因该 gitignored 数据缺失而失败，与本次改动无关。
- 端到端跑通三条链路需：在 Settings 配好 LLM + 上传真实**材料**和**访谈纪要**（文件名带部门）。不造假输入，故 E2E 标记为"待真实上传验证"。
- 想在 App 里看效果需重启后端：`./stop.sh && ./start.sh`。
