# CONTRIBUTING — 开发规范与习惯

> 本文件把本项目已经形成的开发习惯固化下来，供新成员直接继承。
> 面向人和 AI 助手（Claude Code / Codex）双读者。工作流部分来自 `superpowers`
> 规格驱动方法，产物见 `docs/superpowers/`；工程约束来自 `CLAUDE.md` / `AGENTS.md`。

---

## 0. 一句话原则

**绝不造假数据。** 每一个数字都必须能沿着真实路径追溯到真实数据
（`No mock data` / `every number traces to real data through the real path`）。
宁可结果诚实但稀疏，也不要漂亮的假数据——历史上用伪造指标"让流程看起来跑通"
被明确当成 bug 返工。

---

## 1. 规格驱动工作流（specs → plans → notes）

改动**先写文档、拿确认，再动代码**。三类文档都放在 `docs/superpowers/`，
命名统一为 `YYYY-MM-DD-主题.md`：

| 目录 | 作用 | 要点 |
|---|---|---|
| `specs/` | 设计文档 | 顶部标 `**Date:**` 和 `**Status:** Approved (user, 日期)`；写清要解决的**具体缺陷**；按 Phase 拆目标与步骤 |
| `plans/` | 执行追踪器 | 用 `[x] 完成 / [~] 部分或 DEFERRED / [ ] 待办`；每条写「做了什么 **+ 落在哪个文件**」；`[~]` 必须写清延后原因 |
| `notes/` | 审计发现 | 严重度分级：`🔴 阻断真实一致性 · 🟠 真实缺口 · 🟡 味道`；每条含现状 → 后果 → 修复选项 |

小改动可只写 plan；涉及数据/模型/工作流结构的改动必须先有 spec 并获确认。

---

## 2. 假设可追溯、可推翻

拿不准的地方**不要拍脑袋写死**，登记为假设：

- **产品设计层假设** → `docs/agent-design/07-assumptions-log.md`，走状态机
  `提出 → 已按假设设计 → 已确认（转正）/ 已推翻（登记返工范围）`，每条标**置信度**和**待确认人**。
- **业务规则层缺口** → `docs/agent-design/06-gaps-and-proposals.md`，草案未经业务确认**不得当作已定规则实施**。

---

## 3. "完成"的定义 = 静态门禁全绿

说"做完了"之前，必须跑过并贴出以下结果：

### 后端（`backend/`）
```bash
PYTHONPATH=. .venv/bin/python tests/test_api_smoke.py   # 控制流冒烟
.venv/bin/python -m app.mmm._test_synthetic             # OLS 正确性（已知数据）
.venv/bin/python -m app.mmm._test_real                  # 真实数据集上的 MMM
.venv/bin/python -m app.ingest._smoke                   # 所有真实数据 loader
.venv/bin/python -m app.tools._test_tools               # 工具 wrapper == 直算
```

### 前端（`frontend/`）
```bash
npm run build    # tsc -b && vite build（类型 + 生产构建必须过）
npm run lint
```

### 端到端
真实 seed（`danone-mizone`）跑一次 autopilot，确认 `N/N complete`，并核对关键指标
（R²、baseline、driver 数、data station 维度）。

> 测试是**可运行脚本**，不是 pytest 框架——直接 `python -m` 跑。

---

## 4. 契约同步纪律（改一处必改对应处）

| 改动 | 必须同步的两处 |
|---|---|
| domain model 字段 | `backend/app/domain/models.py` ↔ `frontend/src/lib/types.ts` |
| 工作流结构（task/dep/gate） | `backend/app/domain/blueprint.py` ↔ `frontend/src/lib/scenario.ts` |
| 行业分类 | `app/domain/industries.py` ↔ `frontend/src/lib/industries.ts` |

其他约束：
- **后端数字来自 `app/mmm`，不是 LLM**；叙事类 prompt 明确被告知 `MODEL RESULTS` 行为准，不得让 LLM 编造指标。
- **工具层是 identity wrapper**：注册一个计算为 `Tool` **绝不能改变数字**，
  `app/tools/_test_tools.py` 会 assert `wrapper == direct call`。若失败，是工具层开始自己算数了——**回退，别改期望值**。
- 后端 Pydantic 用 `by_alias=True` 序列化为 camelCase，与 `types.ts` 完全对齐。

---

## 5. 启停与环境

```bash
./start.sh            # 启动前后端（PID/日志在 .run/，gitignored）
./stop.sh             # 全部停止
./start.sh backend    # 只启后端
tail -f .run/backend.log .run/frontend.log
```

- 后端：FastAPI/uvicorn → http://127.0.0.1:8000
- 前端：Vite → http://localhost:5173（**需 Node 22.12+**；Vite 8 的原生 binding 依赖它）
- 后端 venv：`python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt`
- LLM/ASR 凭据只在 App 全局 Settings 里填，存 `data/model_service.json`（gitignored，**绝不提交**）。`backend/.env` 不含任何密钥。

---

## 6. 推荐的 AI 助手 Skills

- **`superpowers`**（obra/superpowers）—— 本项目 specs/plans/notes 流程的来源。
  交互式 `claude` 里：`/plugin marketplace add obra/superpowers` → `/plugin install superpowers`。
- `/code-review`、`/security-review` —— 对应第 3 节的门禁习惯，改完自查。
- `simplify` —— 改动后做复用/简化清理（契约不重复、identity-wrapper 不膨胀）。
- `dataviz` —— 前端图表（ValidationChart、DataGrid）配色/画图前先读。
- `pptx` / `xlsx` / `docx` —— 处理 `Agentic_MMM_Product_Intro.pptx`、S1 交付物 `.xlsx` 导出等。
