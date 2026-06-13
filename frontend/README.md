# AgenticMMM · Mission Control（前端原型）

基于《Agentic_MMM_Platform_Design.md》的 Agentic MMM 平台**纯前端原型**：
5 个智能体 × 6 大交付阶段的 Workflow 型多智能体系统，全程人机协作可视可管理，MMM 引擎为 Mock（数据结构对齐 Robyn 真实产出，接口预留真实引擎接入）。

## 运行

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # 生产构建
node scripts/visual-check.mjs   # E2E 走查（需先启动 dev server 于 :5199）
```

## 六大界面

| 路由 | 界面 | 说明 |
|------|------|------|
| `/` | 总控台 Mission Control | 阶段进度、智能体状态、实时事件流、待决策提醒 |
| `/workflow` | 工作流画布 | React Flow DAG：泳道=智能体 × 列=阶段，与设计文档 4.2 任务矩阵一一对应；①②③④ 模拟闭环虚线穿插；点击节点看任务详情 |
| `/gates` | 决策收件箱 Gate Inbox | 5 个 HITL 质量关口；G4 模型选择呈现 3 个 Pareto 候选对比，**永不自动选定模型**；支持批准/驳回重做（驳回触发下游联动重置 + 交付物版本 +1）；全部决策留痕 |
| `/artifacts` | 交付物中心 | 22 个交付物按阶段分组，版本历史 + 血缘（Lineage）+ 在线预览 |
| `/agents` | 智能体台账 | 5 个智能体的角色档案、能力、任务清单与推理日志 |
| `/simulation` | 模拟优化 | 场景构建器（预算滑杆 + 业务硬约束）→ 贪心边际优化（真实 Hill 曲线计算）→ 分配对比 / 响应曲线 / 逐轮模拟时间线 |

## 人机协作四模式

每个任务节点显式标注协作模式徽标：

- `◔ AI Assist` — 人主导执行，AI 提供建议（访谈、场景共创、客户问答）
- `◑ AI Augment` — AI 产出初稿，人在线审改（KBQ、可行性报告、故事线）
- `● AI Delegate` — AI 全自主执行（ETL、质检、模型训练、结果聚合）
- `◆ HITL Gate` — 流程阻塞，等待人工批准/驳回（G1–G5）

## 架构

```
src/
├── lib/            # 领域类型 · 智能体/阶段档案 · 任务剧本(33节点) · 交付物蓝图(22) · Mock MMM 数据
├── store/          # useSimStore：tick 驱动的模拟编排器（任务状态机 + Gate 阻塞/恢复 + 事件溯源）
└── components/
    ├── layout/             # 应用外壳 + 运行控制（运行/单步/重置）
    ├── workflow-canvas/    # DAG 画布 + 任务节点 + 详情抽屉
    ├── gate-inbox/         # 关口卡片 + Pareto 候选对比
    ├── artifact-hub/       # 交付物库 + 血缘 + 预览
    ├── mission-control/    # 总控台
    ├── agent-console/      # 智能体台账
    └── simulation-studio/  # 模拟优化工作室
```

技术栈：Vite + React 19 + TypeScript · Tailwind CSS 4（oklch design tokens）· @xyflow/react · Zustand · Recharts。

## 接真实引擎（下一步）

模拟编排器与 Mock 数据按 Robyn 输出结构设计（NRMSE / DECOMP.RSSD / MAPE.LIFT / Hill 参数 / Pareto 聚类），
后续以 FastAPI + LangGraph 后端替换 `useSimStore` 的 tick 引擎（SSE 事件流 + `interrupt()` HITL），前端界面无需重构。
