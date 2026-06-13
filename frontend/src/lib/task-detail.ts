import type { TaskFinding, TaskStep } from './types'

/**
 * Per-task transparency data: the concrete run trace (process) and the
 * grounded findings (results tied to evidence). Kept separate from
 * scenario.ts so the flow definition stays clean. UI labels English;
 * business content Chinese.
 */

export const TASK_TRACE: Record<string, TaskStep[]> = {
  // ── S1 ──
  '1.0a': [
    { label: 'You attach the SOW & kickoff brief' },
    { label: 'Files logged as the project’s source of truth' },
  ],
  '1.0': [
    { label: 'Parse the SOW', detail: '渠道 / 产品线 / KPI / 时间窗口' },
    { label: 'Check against the hard limits', detail: '≤4 渠道 · ≤6 区域平台组 · 1 产品线' },
    { label: 'Draft 6 structured KBQ from the standard framework' },
    { label: 'Hand to you to confirm' },
  ],
  '1.1a': [{ label: 'You upload brand & competitor reports' }, { label: 'Queued for knowledge mining' }],
  '1.1b': [{ label: 'You upload the 11 interview minutes' }, { label: 'Queued for structuring' }],
  '1.1': [
    { label: 'Pull applicable items from the beverage pack' },
    { label: 'Structure 11 interviews + materials into knowledge items' },
    { label: 'Tag each item', detail: '来源 · 置信度 · 适用范围' },
    { label: 'Cross-check against the pack → flag conflicts & gaps' },
  ],
  '1.21': [
    { label: 'Load the locked L1/L2 skeleton' },
    { label: 'Derive L3/L4 candidates from the knowledge package' },
    { label: 'Attach a derivation basis + reference case to each node' },
    { label: 'Surface interview-driven change suggestions' },
  ],
  '1.21d': [
    { label: 'Review the derived tree vs the knowledge package' },
    { label: 'Accept / adjust L3/L4 (L1/L2 locked)' },
    { label: 'Lock the tree' },
  ],
  '1.22': [
    { label: 'For each L4, propose 3–5 candidate indicators' },
    { label: 'Score each', detail: '消费者相关性 / 变异性 / 可执行性' },
    { label: 'Note overlaps & granularity mismatches' },
  ],
  '1.22d': [
    { label: 'Pick a primary (+ optional alternate) per L4' },
    { label: 'Set granularity' },
    { label: 'Lock the indicator list' },
  ],
  '1.23': [
    { label: 'Lay out one sheet per L3/L4' },
    { label: 'Add granularity columns, definitions, example rows' },
    { label: 'Size to the confirmed indicator list' },
  ],
  '1.23b': [
    { label: 'Download the workbook (packed by owner team)' },
    { label: 'Send to the client teams' },
    { label: 'Mark as sent' },
  ],
  // ── S2 ──
  '2.0a': [{ label: 'You upload the filled workbooks' }, { label: 'Parse & route to scoring' }],
  '2.11': [
    { label: 'Score each metric on the 4 quality dimensions' },
    { label: 'Auto-compute completeness & variability from samples' },
    { label: 'Flag 0.5 (needs a call) and 0 (unusable) rows' },
    { label: 'Raise an alert where a factor has no usable metric' },
  ],
  '2.22': [
    { label: 'Draft column logic per source (37 tasks)', detail: 'Hardcode / Mapping / Transform / Calculation' },
    { label: 'Two owners cross-check' },
    { label: 'Lock the data dictionary' },
  ],
  '2.24': [
    { label: 'Clean master data', detail: 'Product / Geo / Channel / Time' },
    { label: 'Join into one long table' },
    { label: 'Validate row counts (23,791)' },
  ],
  // ── S3 ──
  '2.31': [
    { label: 'Overview & dimension breakdowns' },
    { label: 'Drill anomalies down the factor tree (L5–L8)' },
    { label: 'Form hypotheses with confidence' },
    { label: 'Draft client questions to validate' },
  ],
  '2.32': [
    { label: 'Walk the client through the review deck' },
    { label: 'Capture a Y/N sign-off per chart' },
    { label: 'Record the outcome' },
  ],
  '2.33': [
    { label: 'Compute CV / Pearson / VIF per metric' },
    { label: 'Combine into an entry score (≥3 good, <1.5 drop)' },
    { label: 'Flag collinear pairs' },
  ],
  '2.34': [
    { label: 'Run a fast OLS fit' },
    { label: 'Check contribution & ROI ranges vs industry' },
    { label: 'Confirm there are no red flags' },
  ],
  // ── S4 ──
  '3.1': [
    { label: 'Turn each confirmed judgment into a bounded constraint', detail: '符号 / 区间 / 滞后 / 饱和' },
    { label: 'Trace each constraint to its source' },
    { label: 'Hand to you to confirm' },
  ],
  '3.2': [
    { label: 'Smoke run per model object' },
    { label: 'Full Bayesian hierarchical training' },
    { label: 'Check convergence each round' },
    { label: 'Keep 3 candidates per object' },
  ],
  '3.3': [
    { label: 'Cross-check R² / error / residual per candidate' },
    { label: 'Run red-flag checks', detail: '负基线 · 反向系数' },
    { label: 'Summarize fit quality + caveats' },
  ],
  '3.4': [
    { label: 'Compare candidates vs the assumption register' },
    { label: 'Weigh statistical fit vs business plausibility' },
    { label: 'Pick the delivery model' },
  ],
  // ── S5 ──
  '4.1a': [
    { label: 'Compute decomposition / contribution / due-to / ROI' },
    { label: 'Build chart books per channel' },
    { label: 'Cross-check totals against the onepager' },
  ],
  '4.1b': [
    { label: 'Draft a reading per chart (magnitude + share)' },
    { label: 'Apply the house style' },
    { label: 'Reviewers polish the wording' },
  ],
  '4.1c': [
    { label: 'Final read-through' },
    { label: 'Coverage check vs the KBQ list' },
    { label: 'Release + export the modeling config' },
  ],
}

export const TASK_FINDINGS: Record<string, TaskFinding[]> = {
  '1.0': [
    { text: '⚠ 脉动电解质 已排除出产品组，建议向客户确认以免后续返工', tone: 'flag', evidence: [{ artifactId: 'a-scope' }] },
    { text: '6 类关键业务问题已结构化（媒体vs终端贡献、门店执行三维度、辐射效应…）', evidence: [{ artifactId: 'a-kbq' }] },
  ],
  '1.1': [
    { text: 'GM：外卖与现调饮品挤占 Share of Throat（高置信 · 全品类）', evidence: [{ artifactId: 'a-minutes-raw' }] },
    { text: 'Sales 执行：批发实际约 50%、系统显示 20–30%，建议并入 TT（中置信）', evidence: [{ artifactId: 'a-minutes-raw' }] },
    { text: '⚠ 冲突：内部"品牌投放过多应转线下" vs C/D/rural 无可控抓手、依赖品牌拉力', tone: 'flag', evidence: [{ artifactId: 'a-knowledge-package' }] },
    { text: '◌ 缺口：朗镜门店执行仅 5 个月，无法支撑月度建模', tone: 'flag', evidence: [{ artifactId: 'a-knowledge-package' }] },
  ],
  '1.21': [
    { text: '+ L4 新增 外卖大战时间点（来源：GM 访谈）', evidence: [{ artifactId: 'a-minutes-raw' }] },
    { text: '+ L4 新增 现调饮料外卖销量（GM · Share of Throat 挤压）', evidence: [{ artifactId: 'a-minutes-raw' }] },
    { text: '~ 渠道分组：批发并入 TT（Sales 执行 · 26 年前不可拆）', evidence: [{ artifactId: 'a-minutes-raw' }] },
  ],
  '1.22': [
    { text: '铺货：本品 WD ★ 优于 ND（更反映质量，r>0.7）', evidence: [{ artifactId: 'a-indicator-candidates' }] },
    { text: '品牌传播：有曝光时优先 impression 而非 spend', evidence: [{ artifactId: 'a-indicator-candidates' }] },
    { text: '⚠ 冰柜 × 陈列架共线性偏高，已在候选上标注', tone: 'flag', evidence: [{ artifactId: 'a-indicator-candidates' }] },
  ],
  '2.11': [
    { text: '86 指标：79 通过 · 4 项 0.5 分 · 3 项 0 分', evidence: [{ artifactId: 'a-quality-scorecard' }] },
    { text: '⚠ UTC 扫码瓶数仅 2025-07 起（覆盖 4 个月，0.5 分）', tone: 'flag', evidence: [{ artifactId: 'a-quality-scorecard' }] },
    { text: '⚠ 朗镜门店执行仅 5 个月（0 分，已预警）', tone: 'flag', evidence: [{ artifactId: 'a-quality-scorecard' }] },
  ],
  '2.31': [
    { text: '⚠ O2O 2025 增速 +80%（上年 +36%）— 异常已定位', tone: 'flag', evidence: [{ artifactId: 'a-trend-review' }] },
    { text: '假设：外卖平台大战放大整体流量（高置信，与 GM 访谈一致）', evidence: [{ artifactId: 'a-trend-review' }] },
    { text: '3 个待客户核对问题已生成（补贴占比 / RSP 折扣口径 / 批发误差）', evidence: [{ artifactId: 'a-client-qa' }] },
  ],
  '2.33': [
    { text: '⚠ GDP、消费者信心指数与 NAB 品类趋势强共线 → 建议剔除', tone: 'flag', evidence: [{ artifactId: 'a-stat-tests' }] },
    { text: '温度 / 品类销量 / ND·WD / 社媒声量 均 Good（总分 ≥3）', evidence: [{ artifactId: 'a-stat-tests' }] },
  ],
  '3.3': [
    { text: 'AFH Candidate B：R² 0.95 · 平均误差 8% · DW 正常 ✓', evidence: [{ artifactId: 'a-tech-review' }] },
    { text: '无负基线、无反向系数 — 红旗检查通过', evidence: [{ artifactId: 'a-tech-review' }] },
    { text: '误差 >20% 节点：2024-01 春节备货（已由季节项缓解）', tone: 'flag', evidence: [{ artifactId: 'a-tech-review' }] },
  ],
  '3.4': [
    { text: 'Candidate B：全部弹性落入确认区间，冰柜效应≈成都试点', evidence: [{ artifactId: 'a-model-candidates' }] },
    { text: '⚠ Candidate A 基线 41% 低于业务底线 45%；C 媒体占比虚高', tone: 'flag', evidence: [{ artifactId: 'a-tech-review' }] },
  ],
  '4.1c': [
    { text: 'KBQ 覆盖 20/20，每条均映射到证据图表', evidence: [{ artifactId: 'a-kbq' }] },
    { text: '⚠ 明示局限：朗镜门店执行仅 5 个月 · 批发渠道归因为近似', tone: 'flag', evidence: [{ artifactId: 'a-final-report' }] },
  ],
}
