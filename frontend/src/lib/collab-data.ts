import type { AssistantScriptEntry, InsightBlueprint, ProposalBlueprint } from './types'

/**
 * Collaboration-plane seed data: suggested changes, AI findings and the
 * assistant's scripted answers. UI copy English; quoted business content Chinese.
 */

export const PROPOSALS: ProposalBlueprint[] = [
  {
    id: 'p-factor-updates',
    targetArtifactId: 'a-factor-tree',
    title: 'Three factor-tree changes from the interviews',
    summary: 'Each change traces to a specific interview quote and stays within the 10–20% adjustment allowance.',
    diff: [
      { kind: 'add', text: 'L4 新增：结构性突变因素 → 外卖大战时间点（来源：GM 访谈）' },
      { kind: 'add', text: 'L4 新增：特定属性趋势 → 现调饮料外卖销量（来源：GM 访谈 · Share of Throat 挤压）' },
      { kind: 'remove', text: '渠道分组调整：批发不再单列，并入 TT 渠道组（来源：Sales 执行访谈 · 26 年前数据不可拆）' },
      { kind: 'keep', text: 'L1/L2 结构不变（锁定层）' },
    ],
    evidence: [
      { artifactId: 'a-knowledge-package', note: 'GM / Sales execution items' },
      { artifactId: 'a-factor-tree', note: 'Current confirmed version' },
    ],
    confidence: 0.88,
    sourceAgent: 'business',
    sourceMode: 'pipeline',
    afterTask: '1.21',
  },
  {
    id: 'p-drop-macro',
    targetArtifactId: 'a-model-input',
    title: 'Remove GDP and consumer confidence from the variable list',
    summary: 'Both move almost one-for-one with the category trend, so keeping them would double-count the same signal.',
    diff: [
      { kind: 'remove', text: '变量剔除：GDP（与 NAB 品类趋势强共线）' },
      { kind: 'remove', text: '变量剔除：消费者信心指数（同上）' },
      { kind: 'keep', text: '保留：NAB 品类全渠道销量（已承载宏观信号）' },
    ],
    evidence: [{ artifactId: 'a-stat-tests', note: 'Collinearity section' }],
    confidence: 0.92,
    sourceAgent: 'data',
    sourceMode: 'pipeline',
    afterTask: '2.33',
  },
  {
    id: 'p-merge-cooler',
    targetArtifactId: 'a-model-input',
    title: 'Consider merging cooler and display-rack variables',
    summary: 'The two move together strongly. Merging avoids unstable attribution between them; the split can be reported descriptively instead.',
    diff: [
      { kind: 'add', text: '合并变量：冰柜个数 + 陈列架数量 → 终端冷柜与陈列资产' },
      { kind: 'remove', text: '原独立变量：冰柜个数 · 陈列架数量' },
    ],
    evidence: [
      { artifactId: 'a-stat-tests', note: '冰柜 × 陈列架 collinearity flag' },
    ],
    confidence: 0.74,
    sourceAgent: 'model',
    sourceMode: 'assistant',
    afterTask: '2.34',
  },
]

export const INSIGHTS: InsightBlueprint[] = [
  {
    id: 'i-o2o-war',
    kind: 'connection',
    title: 'O2O spike matches what the GM said about the delivery-platform war',
    finding:
      'The +80% O2O growth anomaly lines up with the GM interview: 外卖大战显著放大整体流量. Worth marking the affected months as a structural event so the model does not credit the lift to marketing.',
    evidence: [
      { artifactId: 'a-trend-review', note: 'O2O 2025 +80% anomaly' },
      { artifactId: 'a-knowledge-package', note: 'GM: 外卖大战放大流量' },
    ],
    confidence: 0.9,
    actions: [
      { kind: 'open_asset', label: 'Open the review deck', artifactId: 'a-trend-review' },
      { kind: 'client_question', label: 'Draft a client question on subsidy share' },
    ],
    afterTask: '2.31',
  },
  {
    id: 'i-kbq-gap',
    kind: 'gap',
    title: 'One key question has no data behind it yet',
    finding:
      'KBQ A19（站外投放对电商站内的实际影响）is not covered by any collected dataset — EC 仅有花费与 ROI，无站外触点到站内的桥接数据. The report will have to answer it qualitatively unless data is added.',
    evidence: [
      { artifactId: 'a-kbq', note: 'A19' },
      { artifactId: 'a-quality-scorecard', note: 'EC coverage rows' },
    ],
    confidence: 0.85,
    actions: [
      { kind: 'create_task', label: 'Add a data request item' },
      { kind: 'open_asset', label: 'Open key questions', artifactId: 'a-kbq' },
    ],
    afterTask: '2.11',
  },
  {
    id: 'i-tts-shift',
    kind: 'conflict',
    title: 'TTS spend means different things across years',
    finding:
      'Sales 访谈：TTS 中提成占比三年间从 10% 变到 80%——同样金额的 TTS，对渠道的真实投入差异巨大。把 TTS 当作单一连续变量会误导归因，建议拆分或加结构调整。',
    evidence: [
      { artifactId: 'a-knowledge-package', note: 'Sales execution: 提成占比 10%→80%' },
      { artifactId: 'a-data-dictionary', note: 'TTS spending source logic' },
    ],
    confidence: 0.82,
    actions: [
      { kind: 'client_question', label: 'Ask for the yearly commission split' },
      { kind: 'open_asset', label: 'Open the data dictionary', artifactId: 'a-data-dictionary' },
    ],
    afterTask: '2.22',
  },
  {
    id: 'i-store-exec',
    kind: 'reference',
    title: 'Store-execution data is too short to model — seen before',
    finding:
      '朗镜门店执行数据仅覆盖 5 个月，无法支撑月度模型。过往项目同样情况的处理方式：本期仅作描述性参照，约定继续采集，下一期建模再入模。',
    evidence: [
      { artifactId: 'a-quality-scorecard', note: '朗镜 row — 5 months, score 0' },
    ],
    confidence: 0.88,
    actions: [
      { kind: 'client_question', label: 'Log a data-collection agreement' },
    ],
    afterTask: '2.11',
  },
  {
    id: 'i-cooler-pilot',
    kind: 'connection',
    title: 'Cooler results echo the 成都 pilot',
    finding:
      '模型给出的冰柜效应（AFH 增长主引擎）与成都试点经验一致：覆盖率 35%→55% 带来增速 16% vs 全国 7%。这为冰柜结论提供了模型之外的独立证据，可写入报告增强说服力。',
    evidence: [
      { artifactId: 'a-model-candidates', note: 'Candidate B cooler effect' },
      { artifactId: 'a-prior-register', note: '成都 pilot reference' },
    ],
    confidence: 0.86,
    actions: [
      { kind: 'open_asset', label: 'Open the technical review', artifactId: 'a-tech-review' },
    ],
    afterTask: '3.3',
  },
]

/** Scripted assistant answers, matched by keyword (mock retrieval) */
export const ASSISTANT_SCRIPT: AssistantScriptEntry[] = [
  {
    match: ['cooler', '冰柜', 'roi'],
    answer:
      'The cooler effect in Candidate B sits near the top of its agreed range. Two independent reasons to trust it: the 成都 pilot (覆盖 35%→55%，增速 16% vs 全国 7%) points the same way, and the screening flagged cooler × display-rack collinearity — there is an open suggestion to merge them if you would rather be conservative.',
    evidence: [
      { artifactId: 'a-prior-register', note: '成都 pilot' },
      { artifactId: 'a-stat-tests', note: 'Collinearity flag' },
    ],
  },
  {
    match: ['batch', 'wholesale', '批发'],
    answer:
      '批发 is folded into the TT channel group. Reason from the interviews: before 2026 the data cannot split AFH/TT/EC wholesale, and treating it separately would dilute AFH effectiveness. The report marks wholesale attribution as approximate.',
    evidence: [{ artifactId: 'a-knowledge-package', note: 'Sales execution interview' }],
  },
  {
    match: ['o2o', '外卖'],
    answer:
      'O2O grew +80% in 2025, but part of that is the delivery-platform war inflating traffic — the GM interview says the same. The affected months carry a structural-event marker so the model does not credit that lift to marketing spend.',
    evidence: [
      { artifactId: 'a-trend-review' },
      { artifactId: 'a-prior-register', note: '外卖大战 marker' },
    ],
  },
  {
    match: ['where', 'status', 'stuck', 'progress'],
    answer:
      'Quick status: see the Project page for the live picture. Anything blocked will be sitting in Decisions with my recommendation attached — that is always the fastest way to unblock the timeline.',
  },
  {
    match: ['baseline', '基线'],
    answer:
      'Baseline for AFH moved from 68% (2023) to 43% (2025 YTD) — the business is increasingly driven by Marketing & Trade rather than riding the base. Candidate B keeps baseline at 47% for the full window, inside the agreed 45–55% floor; Candidate A dips to 41%, which is why it was not recommended.',
    evidence: [
      { artifactId: 'a-decomp-results' },
      { artifactId: 'a-model-candidates' },
    ],
  },
]

export const ASSISTANT_FALLBACK =
  'I could not match that to project evidence. Try asking about a specific channel, metric or document — or open the asset and ask from there so I have the right context.'
