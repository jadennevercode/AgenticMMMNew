import type { TaskBlueprint } from './types'

/**
 * Task playbook — Danone Mizone MMM POC.
 * S1 (Business Understanding) follows the MMM-Study pre-modeling flow:
 * Framing → Knowledge Assembly → Factor Tree → Indicators → Data Request,
 * with explicit import/export touchpoints.
 * UI copy is English; client/business content quoted inside notes may be Chinese.
 */
export const TASKS: TaskBlueprint[] = [
  /* ════ S1 · Business Understanding — 6 deliverables (MMM-Study flow) ════ */
  // ── 1 · Project Profile ──
  {
    id: '1.0a', name: 'Provide SOW & brief', agent: 'business', stage: 's1', class: 'H',
    summary: 'Upload the signed SOW and kickoff brief so the AI can frame the project profile.',
    how: 'You attach the SOW & brief; the AI reads them to extract the project profile fields.',
    basisNote: '客户签署的 SOW 与立项简报。',
    workNote: 'Waiting for the SOW. The project profile is framed from it.',
    dependsOn: [], duration: 1, produces: ['a-sow'],
    assignment: {
      id: 'in-1.0a', kind: 'upload', title: 'Provide the SOW & brief',
      prompt: '上传已签署 SOW 与立项简报（品牌 / 品类 / 市场 / 时间窗 / 目的）。AI 将据此抽取项目档案字段。',
      items: ['Mizone_MMM_SOW_signed.pdf', 'Kickoff_brief.pptx'],
      submitLabel: 'Submit SOW',
    },
  },
  {
    id: '1.0', name: 'Frame project profile', agent: 'business', stage: 's1', class: 'C',
    summary: 'Extract brand / category / market / time window / objective from the SOW into a locked project profile.',
    how: 'AI reads the SOW and fills the profile against the hard limits (≤4 channels · ≤6 region/platform · 1 product group); you confirm to lock.',
    basisNote: 'SOW + 立项简报。',
    workNote: 'Profile drafted: Mizone · 功能饮料 · 2023–2025 月度 · MT/TT/AFH/EC+O2O · 目的=A&P/TTS ROI.',
    dependsOn: ['1.0a'], duration: 2, produces: ['a-scope'],
    decision: {
      id: 'd-1.0', kind: 'approval', title: 'Confirm & lock the project profile',
      question: 'Does the profile match the SOW? Locking it sets the analysis granularity and unlocks the rest of the stage.',
      evidence: [{ artifactId: 'a-scope' }, { artifactId: 'a-sow', note: 'Source SOW' }],
      recommendation: 'Consistent with the SOW. All three hard limits hold. Note 脉动电解质 is excluded from the product group — flag it to the client.',
      options: [
        { id: 'approve', label: 'Lock profile', detail: 'Lock granularity and continue', consequence: 'Factor-tree work starts', recommended: true },
        { id: 'rework', label: 'Send back for changes', detail: 'Adjust channels, grouping or window', consequence: 'Profile is re-framed' },
      ],
      reworkTaskId: '1.0', reworkOptionId: 'rework',
    },
  },
  // ── 2 · Factor Tree (inputs: reports + industry knowledge) ──
  {
    id: '1.1a', name: 'Upload reports & materials', agent: 'business', stage: 's1', class: 'H',
    summary: 'Provide brand/competitor reports and internal materials for the AI to mine into the factor tree.',
    how: 'You upload reports; AI extracts factor candidates from them (e.g. Project Aurora 报告补充 L3/L4).',
    basisNote: '品牌财报、竞品研究（如 Project Aurora）、内部资料。',
    workNote: 'Waiting for materials. These feed factor-tree derivation.',
    dependsOn: ['1.0'], duration: 1, produces: ['a-source-materials'],
    assignment: {
      id: 'in-1.1a', kind: 'upload', title: 'Upload reports & materials',
      prompt: '上传品牌财报、竞品 benchmark（Project Aurora 等）及内部资料。AI 将抽取为因子候选。',
      items: ['202408_Competitor_Benchmark.pdf', 'Mizone_brand_review.pptx', 'Internal_channel_strategy.pdf'],
      submitLabel: 'Submit materials',
      choicePrompt: 'How should the factor-tree baseline be built?',
      choiceOptions: [
        { id: 'template', label: 'Start from industry template', detail: 'AI derives L3/L4 on the standard industry factor-tree skeleton.', recommended: true },
        { id: 'upload', label: 'Upload my own factor tree', detail: 'AI supplements your uploaded tree from the industry template + your materials.' },
      ],
      choiceUploadCategory: 'factor_tree',
    },
  },
  {
    id: '1.1', name: 'Assemble industry knowledge', agent: 'business', stage: 's1', class: 'C',
    summary: 'Recall the applicable industry knowledge (L1/L2 skeleton + brand analysis framework) for the beverage category.',
    how: 'AI assembles the industry-knowledge package the factor tree is derived on — the locked L1/L2 skeleton and the brand business-analysis framework.',
    basisNote: '行业知识库（饮料 / 功能饮料包）。',
    workNote: '知识包成形：L1/L2 行业骨架 + 品牌生意分析框架（媒体 vs 终端、Control/Uncontrol）。',
    dependsOn: ['1.1a'], duration: 2, produces: ['a-knowledge-package'],
  },
  {
    id: '1.21', name: 'Derive factor tree & indicators', agent: 'business', stage: 's1', class: 'C',
    summary: 'Derive L3/L4 on the locked L1/L2 skeleton and map each L4 to candidate indicators with 3-axis scores.',
    how: 'AI derives L3/L4 from the knowledge package + reports, then proposes indicators per L4 scored on consumer view / granularity fit / actionability.',
    basisNote: '知识包 + 上传报告 + L1/L2 骨架（锁定）。',
    workNote: '17 L3 / 52 L4（含报告补充 6 个 L4、AI 推荐 3 个）。每个 L4 附候选指标与三轴打分。',
    dependsOn: ['1.1'], duration: 3, produces: ['a-factor-tree'],
    aiOptions: {
      id: 'ai-1.21', prompt: '指标选型的整体取向（AI 据此为所有 L4 自动选主指标）',
      options: [
        { id: 'conservative', label: 'Conservative 谨慎', rationale: '只用高质量、已验证、口径稳定的指标，宁缺毋滥', tradeoff: '覆盖收窄，部分弱信号因子可能暂无指标' },
        { id: 'balanced', label: 'Balanced 平衡', rationale: '质量与覆盖兼顾：成熟因子用优选指标，新因子给可得代理', tradeoff: '少量指标可解释性中等', recommended: true },
        { id: 'aggressive', label: 'Aggressive 激进', rationale: '尽量广覆盖，纳入探索性 / 细颗粒 / 新数据源指标', tradeoff: '噪声与共线性风险上升，n/p 趋紧' },
      ],
    },
  },
  {
    id: '1.21d', name: 'Confirm factor tree', agent: 'business', stage: 's1', class: 'H',
    summary: 'Accept/adjust the derived L3/L4 and pick the primary indicator per L4; L1/L2 locked. Confirm to baseline.',
    how: 'You accept/adjust L3/L4 and the primary indicator per L4, then lock the baseline (interviews can still refine it later).',
    workNote: 'Awaiting confirmation of the L3/L4 + indicator selection.',
    dependsOn: ['1.21'], duration: 1, produces: [],
    decision: {
      id: 'd-1.21', kind: 'approval', title: 'Confirm the factor tree',
      question: 'Confirm the derived L3/L4 and the primary indicator per L4? L1/L2 stay locked.',
      evidence: [
        { artifactId: 'a-factor-tree' },
        { artifactId: 'a-knowledge-package', note: 'Derivation basis' },
      ],
      recommendation: 'Confirm. Report-supplemented L4 (Project Aurora) all trace to a source; indicators follow the highest 3-axis score (本品 WD over ND, impression over spend).',
      options: [
        { id: 'approve', label: 'Confirm factor tree', detail: 'Baseline L1–L4 + indicators', consequence: 'Interview outline is drafted next', recommended: true },
        { id: 'rework', label: 'Re-derive', detail: 'The tree missed something', consequence: 'AI re-derives from the knowledge package' },
      ],
      reworkTaskId: '1.21', reworkOptionId: 'rework',
    },
  },
  // ── 3 · Interview (outline → AI pre-answers → minutes → writeback) ──
  {
    id: '1.3', name: 'Draft interview outline', agent: 'business', stage: 's1', class: 'A',
    summary: 'Generate a structured interview outline by interviewee layer (GM / Mgmt / Operation) from the confirmed factor tree.',
    how: 'AI drafts one question set per role (Layer1 GM, Layer2 Mgmt, Layer3 Operation); each question is tagged to the factor it probes.',
    basisNote: '确认版因子树 + 访谈框架（seed）。',
    workNote: 'GM / Media / SIA 等分层提纲已生成，问题挂因子关联。',
    dependsOn: ['1.21d'], duration: 2, produces: ['a-interview'],
  },
  {
    id: '1.3b', name: 'AI pre-answers the outline', agent: 'business', stage: 's1', class: 'C',
    summary: 'Before the interviews, AI drafts a preliminary answer to each question from what it already knows.',
    how: 'AI answers each outline question up front using the project profile, competitor / brand reports, industry knowledge and the factor tree — with a confidence and the source it leaned on — so interviews focus on gaps and disagreements.',
    basisNote: '项目档案 + 竞品/品牌报告 + 行业知识 + 因子树。',
    workNote: 'AI 预答已生成：每题给初步回答 + 置信度 + 依据；低置信题标记为访谈重点。',
    dependsOn: ['1.3'], duration: 2, produces: [],
  },
  {
    id: '1.4a', name: 'Upload interview minutes', agent: 'business', stage: 's1', class: 'H',
    summary: 'Upload the conducted interview minutes (11 sessions) for the AI to digest against its pre-answers.',
    how: 'You upload the minutes; AI compares them to its pre-answers, digests insights and proposes factor-tree changes.',
    basisNote: '分层访谈纪要（GM / 管理层 / 执行层共 11 场）。',
    workNote: 'Waiting for the minutes. AI will reconcile them with its pre-answers and propose factor-tree adjustments.',
    dependsOn: ['1.3b'], duration: 1, produces: [],
    assignment: {
      id: 'in-1.4a', kind: 'upload', title: 'Upload interview minutes',
      prompt: '上传 11 场分层访谈纪要（GM / Mkt / Sales / Finance / Media / Activation / EC / KA / Trade / Execution / SIA）。',
      items: ['Layer1_GM.docx', 'Layer3_Media.docx', 'Layer3_SIA.docx', '+8 more'],
      submitLabel: 'Submit minutes',
    },
  },
  {
    id: '1.4', name: 'AI writeback from minutes', agent: 'business', stage: 's1', class: 'C',
    summary: 'Digest the minutes into business insights and a set of proposed Factor-Tree changes, each traced to an interview quote.',
    how: 'AI structures the minutes into insight items and derives factor-tree change suggestions (new L3/L4, regroupings) with their source quote.',
    basisNote: '访谈纪要 + AI 预答 + 确认版因子树。',
    workNote: '19 业务洞察；Factor 回写建议：新增 L3 渠道结构变化 / L4 临期折扣店、外卖大战、批发并入 TT。',
    dependsOn: ['1.4a'], duration: 2, produces: [],
  },
  {
    id: '1.4d', name: 'Confirm interview-driven factor changes', agent: 'business', stage: 's1', class: 'H',
    summary: 'Review the AI’s proposed Factor-Tree changes from the interviews; accepted ones write back into the Factor Tree.',
    how: 'You confirm each interview-driven change; accepting writes it back into the Factor Tree and logs it in the changelog.',
    workNote: 'Awaiting confirmation of the interview-driven factor-tree changes.',
    dependsOn: ['1.4'], duration: 1, produces: [],
    decision: {
      id: 'd-1.4', kind: 'approval', title: 'Confirm interview-driven factor-tree changes',
      question: 'The interviews suggest factor-tree changes (see the writeback on the Interview). Accept them into the tree?',
      evidence: [
        { artifactId: 'a-interview', note: 'AI 回写建议' },
        { artifactId: 'a-factor-tree', note: 'Target tree' },
      ],
      recommendation: 'Accept. Each change traces to a quote: 外卖大战 (GM), 批发并入TT (Sales execution), 渠道结构变化/临期折扣店 (GM) — all within the L3/L4 adjustment allowance.',
      options: [
        { id: 'approve', label: 'Accept changes', detail: 'Write back into the factor tree', consequence: 'Data request is generated next', recommended: true },
        { id: 'rework', label: 'Re-digest', detail: 'Missed or misread the minutes', consequence: 'AI re-digests the minutes' },
      ],
      reworkTaskId: '1.4', reworkOptionId: 'rework',
    },
  },
  // ── 5 · Data Request ──
  {
    id: '1.5', name: 'Data request', agent: 'business', stage: 's1', class: 'A',
    summary: 'Lay out the data-request collection templates: one Excel workbook per L3, one sheet per L4.',
    how: 'AI lays out the data-request workbook (granularity columns, definitions, example rows) per L3/L4 from the confirmed factor tree.',
    basisNote: '入选指标 + 数据源标准。',
    workNote: 'L3 模板生成（每个 L3 一个工作簿，每个 L4 一个 sheet）。',
    dependsOn: ['1.4d'], duration: 2, produces: ['a-data-request'],
  },
  {
    id: '1.5d', name: 'Confirm data request', agent: 'business', stage: 's1', class: 'H',
    summary: 'Review the data request and confirm fields, granularity and owners — this closes Business Understanding.',
    how: 'You review the request workbook, then sign off so data intake can begin.',
    workNote: 'Awaiting data-request sign-off.',
    dependsOn: ['1.5'], duration: 1, produces: [],
    decision: {
      id: 'd-1.5', kind: 'signoff', title: 'Confirm the data request',
      question: 'Did the client sign off the data request (fields, granularity, owners)?',
      evidence: [
        { artifactId: 'a-data-request' },
        { artifactId: 'a-factor-tree', note: 'Coverage' },
      ],
      recommendation: 'Sign off — all L3 templates have an owning team and granularity matches the model.',
      options: [
        { id: 'approve', label: 'Signed off', detail: 'Client confirmed the request', consequence: 'Close Business Understanding; data intake begins', recommended: true },
        { id: 'rework', label: 'Needs changes', detail: 'Client flagged gaps', consequence: 'Data request is revised' },
      ],
      reworkTaskId: '1.5', reworkOptionId: 'rework',
    },
  },
  // ── 6 · BU summary ──
  {
    id: '1.7', name: 'Business Understanding summary', agent: 'business', stage: 's1', class: 'C',
    summary: 'Synthesize the profile, factor tree, interview outcomes and the data request into one recap that closes Business Understanding.',
    how: 'AI assembles the BU summary from the confirmed S1 deliverables.',
    basisNote: 'All confirmed S1 deliverables.',
    workNote: 'BU summary assembled.',
    dependsOn: ['1.5d'], duration: 1, produces: ['a-bu-summary'],
  },

  /* ════ S2 · Data Intake & Validation (2.1 Processing → 2.2 Quality → 2.3 Business
         → 2.4 Statistical → 2.5 OLS test → 2.6 Master data) ════ */
  {
    id: '2.1', name: 'Data Processing', agent: 'data', stage: 's2', class: 'H',
    summary: 'Resolve the FactorTree↔DataAssets mapping: the AI proposes a published indicator for every unmatched factor, and you accept, remap or ignore each one.',
    how: 'In the Data Engine, each unresolved factor carries a ranked AI proposal — scored on name, factor path, unit and coverage — for you to accept, swap for another candidate, or ignore when no data exists. The gate clears once nothing is left unresolved; the mapped assets are then unioned into the modeling long table and the intake preview shows what each source actually contributed.',
    basisNote: 'Data Engine 已发布数据资产 + 确认版因子树映射。',
    workNote: 'Waiting for the FactorTree↔DataAssets mapping to be resolved (every indicator mapped or ignored).',
    dependsOn: ['1.7'], duration: 2, produces: ['a-data-processing'],
    assignment: {
      id: 'in-2.1', kind: 'upload', title: 'Resolve the FactorTree↔DataAssets mapping',
      prompt: 'In the Data Engine, map every factor-tree indicator to a published data asset, or mark it ignored. Data Intake & Validation starts once no indicator is left unresolved. (Projects using slot uploads instead clear the gate by per-L3 coverage.)',
      items: ['Mapped indicators', 'Ignored indicators'],
      submitLabel: 'Reference mapping',
      category: 'data', requiresUpload: true, requiresManifest: true, requiresMapping: true,
    },
  },
  {
    id: '2.2', name: 'Data Quality Score', agent: 'data', stage: 's2', class: 'A',
    summary: 'The AI scores every L1×L2×L3×L4×metric on the four dimensions (consistency / completeness / granularity / accuracy, each 0 / 0.5 / 1) with a note, grounded in the rubric + computed evidence.',
    how: 'AI applies the standing rubric to the computed data evidence, assigning each dimension 0 / 0.5 / 1; the verdict (weakest dimension governs) is reviewed by a human next.',
    basisNote: '校验标准 + 数据资产证据。',
    workNote: 'AI 逐指标四维评分；Total = 最弱维度。',
    dependsOn: ['2.1'], duration: 3, produces: ['a-quality-scorecard'],
  },
  {
    id: '2.2d', name: 'Review data quality verdicts', agent: 'data', stage: 's2', class: 'H',
    panel: 'quality-review',
    summary: 'Human reviews the AI scores; 1 = accept · 0 = unusable · 0.5 = human call (re-collect / drop / accept-with-caveat).',
    how: "You review the scorecard right here: accept the 1s, drop the 0s (alert if a factor's only metrics all fail), and decide each 0.5. A drop is inherited by every later layer — the indicator is not re-scored at 2.4, not offered as a model variable at 2.5, and never reaches the master table.",
    basisNote: 'AI 质量评分 + 验收标准。',
    workNote: 'Awaiting human review of the data-quality verdicts.',
    dependsOn: ['2.2'], duration: 1, produces: [],
    decision: {
      id: 'd-2.2', kind: 'choice', title: 'Review data-quality verdicts',
      question: 'Some metrics scored 0.5 (borderline). Review the verdicts and decide how to handle them.',
      evidence: [
        { artifactId: 'a-quality-scorecard', note: 'Per-metric scores & verdicts (1 / 0.5 / 0)' },
        { artifactId: 'a-data-processing', note: 'Referenced data assets' },
      ],
      recommendation: 'Accept the 1s and drop the clear 0s. For each 0.5, re-collect when the metric is the factor’s only signal; otherwise let it enter flagged.',
      options: [
        { id: 'accept', label: 'Accept the verdicts', detail: 'Keep the 1s, drop the 0s, 0.5 enter flagged', consequence: 'Business validation starts on the accepted metrics', recommended: true },
        { id: 'recollect', label: 'Re-collect 0.5 data', detail: 'Re-prepare the borderline assets in the Data Engine', consequence: 'Intake reopens for the flagged assets; timeline slips' },
        { id: 'drop', label: 'Drop the 0.5 metrics', detail: 'Exclude borderline metrics from this model', consequence: 'Leaner model; those factors enter via aggregate metrics only' },
      ],
      reworkTaskId: '2.1', reworkOptionId: 'recollect',
    },
  },
  {
    id: '2.3', name: 'Business Validation', agent: 'data', stage: 's2', class: 'C',
    summary: 'Visualized business review of the accepted data — each factor charted against sell-out, with its own reading.',
    how: 'AI charts every factor (L3) against the sell-out backdrop and writes its reading; you filter by source, sub-factor, indicator, time grain and model dimension to interrogate it.',
    basisNote: '质量验收后的数据 + 因子树 + 行业基准。',
    workNote: 'Business-validation deck built.',
    dependsOn: ['2.2d'], duration: 3, produces: ['a-business-validation'],
  },
  {
    id: '2.3a', name: 'Explain the anomalies', agent: 'data', stage: 's2', class: 'A',
    panel: 'anomaly-review',
    summary: "One card per detected anomaly: the AI's causal hypothesis and a proposed handling; you accept, edit or reject each.",
    how: 'For every year-on-year move past ±40% the AI states the most likely business cause and proposes how to handle it. Your ruling reaches the model directly: a structural event becomes a dummy control over its window, capping winsorizes the response, raw leaves the data alone and carries a caveat into the report.',
    basisNote: '计算出的 YoY 异常 + 访谈证据。',
    workNote: 'Anomaly hypothesis cards drafted for review.',
    dependsOn: ['2.3'], duration: 2, produces: [],
  },
  {
    id: '2.3s', name: 'Record client sign-off', agent: 'data', stage: 's2', class: 'H',
    summary: 'Per-factor client sign-off on the validated data — an unsigned factor cannot enter modeling.',
    how: 'You sign off each factor with the client on the chart page. Marking a factor not-signed-off excludes it and every one of its indicators from the model, inherited all the way to the master table.',
    basisNote: '业务校验图表 + 异常处理裁决。',
    workNote: 'Awaiting client sign-off.',
    dependsOn: ['2.3a'], duration: 1, produces: [],
    decision: {
      id: 'd-2.3', kind: 'signoff', title: 'Record client sign-off on data',
      question: 'Did the client sign off the business validation? Any factor you mark not-signed-off is excluded from modeling, along with all of its indicators.',
      evidence: [
        { artifactId: 'a-business-validation' },
      ],
      recommendation: 'Record the sign-off once every chart has a Y and the open questions have owners.',
      options: [
        { id: 'approve', label: 'Signed off', detail: 'Client confirmed', consequence: 'Data is locked for statistical scoring', recommended: true },
        { id: 'rework', label: 'Not signed off', detail: 'Client raised blocking issues', consequence: 'Review is revisited' },
      ],
      reworkTaskId: '2.3', reworkOptionId: 'rework',
    },
    // The old `ai-2.3` set asked "how should anomalies be handled?" once, stored
    // the answer and never read it. 2.3a replaces it with a card per anomaly
    // whose handling actually reaches the fit.
  },
  {
    id: '2.4', name: 'Statistical Score', agent: 'data', stage: 's2', class: 'A',
    summary: 'Variability, correlation and collinearity tests per indicator (CV / Pearson / VIF); the combined score decides model entry. Indicators already rejected at 2.2 or 2.3 are not scored — that call is settled.',
    how: 'CV, Pearson and VIF are computed per indicator still in play and combined into an entry score (≥3 good, <1.5 dropped); the AI then writes the case for or against each borderline indicator. Excluding the already-rejected ones is not bookkeeping — VIF is computed across the whole set, so dead indicators would inflate the collinearity of the live ones.',
    basisNote: '统计筛选规则 + 上游裁决（2.2 质量 / 2.3 签核）。',
    workNote: 'CV / Pearson / VIF computed on the indicators still in play.',
    dependsOn: ['2.3s'], duration: 2, produces: ['a-stat-tests'],
  },
  {
    id: '2.4d', name: 'Review statistical verdicts', agent: 'data', stage: 's2', class: 'H',
    panel: 'stat-review',
    summary: 'Human reviews the statistical scores and decides which borderline indicators enter the model.',
    how: 'You review the scorecard here: keep the Good band, decide each Acceptable, drop the Unconsiderable. What you drop is inherited — 2.5 will not offer it back as a model variable.',
    basisNote: '统计得分 + AI 逐行入模建议。',
    workNote: 'Awaiting human review of the statistical verdicts.',
    dependsOn: ['2.4'], duration: 1, produces: [],
    decision: {
      id: 'd-2.4', kind: 'choice', title: 'Borderline metrics into the model',
      question: 'Some metrics scored Acceptable (1.5–3) — neither clearly in nor out. How should they enter the model?',
      evidence: [
        { artifactId: 'a-stat-tests', note: 'Acceptable-band (1.5–3) rows' },
        { artifactId: 'a-quality-scorecard', note: 'Upstream quality dispositions' },
      ],
      recommendation: 'Keep the Acceptable-band metrics alongside the Good ones; the OLS regression test (2.5) then checks each against its ROI / contribution range.',
      options: [
        { id: 'keep', label: 'Keep acceptable metrics', detail: 'Enter with the Good-band metrics', consequence: 'The OLS test checks their contribution range', recommended: true },
        { id: 'drop', label: 'Drop the weakest', detail: 'Keep only Good-band metrics', consequence: 'Leaner model; some factors lose a metric' },
        { id: 'review', label: 'Review case-by-case', detail: 'Open the scorecard to decide per metric', consequence: 'Manual selection before the OLS test' },
      ],
    },
  },
  /* ── 2.5 OLS Regression Test — a five-step Process on one deliverable:
        propose → confirm Y → review X → confirm settings → fit & review.
        2.5y/2.5x/2.5p are human gates whose `panel` renders the structured
        input inside the Process step (see components/project/ols/). ── */
  {
    id: '2.5', name: 'Propose model setup', agent: 'data', stage: 's2', class: 'A',
    summary: 'Propose the OLS setup from real data: a response candidate per model object, model variables scored on their 2.4 statistics, and default transform / control settings.',
    how: 'AI proposes the response (Y) for each model object, ranks the candidate model variables (X) on their 2.4 CV / Pearson / VIF, and pre-fills the transform and trend/seasonality settings — all for you to confirm in the next steps.',
    basisNote: '2.4 统计得分 + 数据可用性（覆盖月数、单位）。',
    workNote: 'Model setup proposed for review.',
    dependsOn: ['2.4d'], duration: 1, produces: ['a-ols-test'],
  },
  {
    id: '2.5y', name: 'Confirm response variable', agent: 'data', stage: 's2', class: 'H',
    panel: 'ols-y',
    summary: 'Pick the response (Y) each model object is fitted against — the KPI volume metric is recommended.',
    how: 'You pick the response for each model object. The KPI volume metric is recommended; choosing a money metric (or setting a unit price later) makes ROI a true incremental-revenue / spend ratio.',
    basisNote: '各模型对象的 KPI 候选（单位 + 覆盖月数）。',
    workNote: 'Awaiting the response-variable confirmation.',
    dependsOn: ['2.5'], duration: 1, produces: [],
    decision: {
      id: 'd-2.5y', kind: 'approval', title: 'Confirm the response variable',
      question: 'The KPI volume metric is proposed as the response for each model object. Confirm it, or pick a different response above.',
      evidence: [{ artifactId: 'a-ols-test', note: 'Response candidates per model object' }],
      recommendation: 'The KPI volume response keeps coefficients in sales units — confirm to continue.',
      options: [
        { id: 'confirm', label: 'Confirm response', detail: 'Fit against the selected response', consequence: 'Model variables are reviewed next', recommended: true },
      ],
    },
  },
  {
    id: '2.5x', name: 'Review model variables', agent: 'data', stage: 's2', class: 'H',
    panel: 'ols-x',
    summary: 'Review the AI-proposed model variables (X) — each with its correlation, collinearity and 2.4 verdict — and tick the ones that enter the regression.',
    how: 'You tick the variables that enter the regression. Each carries its Pearson r vs the KPI, its VIF, its CV and its 2.4 verdict, plus the remaining degrees of freedom — this is where you drive the screening.',
    basisNote: '2.4 统计得分 + 共线性/自由度约束。',
    workNote: 'Awaiting the model-variable selection.',
    dependsOn: ['2.5y'], duration: 1, produces: [],
    decision: {
      id: 'd-2.5x', kind: 'approval', title: 'Confirm the model variables',
      question: 'These variables will enter the regression. Confirm the selection, or tick / untick above.',
      evidence: [
        { artifactId: 'a-ols-test', note: 'Candidate variables with their 2.4 statistics' },
        { artifactId: 'a-stat-tests', note: 'Statistical score' },
      ],
      recommendation: 'The pre-ticked variables clear the correlation and collinearity gates — confirm to continue.',
      options: [
        { id: 'confirm', label: 'Confirm variables', detail: 'These variables enter the regression', consequence: 'Model settings are confirmed next', recommended: true },
      ],
    },
  },
  {
    id: '2.5p', name: 'Confirm model settings', agent: 'data', stage: 's2', class: 'H',
    panel: 'ols-params',
    summary: 'Confirm the carryover / saturation transforms and the trend + seasonality controls that keep the paid coefficients honest.',
    how: 'You set the adstock carryover, the saturation curve, and the trend / seasonality controls. The controls absorb the trend and seasonal swing so the paid variables do not — this is what keeps the baseline positive and the coefficients correctly signed.',
    basisNote: '变换与控制项设置（默认：adstock 0.5 · Hill · 线性趋势 · Fourier 季节性）。',
    workNote: 'Awaiting the model settings.',
    dependsOn: ['2.5x'], duration: 1, produces: [],
    decision: {
      id: 'd-2.5p', kind: 'approval', title: 'Confirm the model settings',
      question: 'These transforms and controls will be used for the fit. Confirm them, or adjust above.',
      evidence: [{ artifactId: 'a-ols-test', note: 'Transform + control settings' }],
      recommendation: 'A linear trend plus Fourier seasonality is the cheapest control that keeps the paid coefficients honest — confirm to fit.',
      options: [
        { id: 'confirm', label: 'Confirm settings', detail: 'Fit with these transforms and controls', consequence: 'The regression runs', recommended: true },
      ],
    },
  },
  {
    id: '2.5r', name: 'Run OLS & review fit', agent: 'data', stage: 's2', class: 'M',
    summary: "Fit the OLS on the confirmed setup and check each variable's ROI and contribution against the knowledge-base industry ranges — far-out variables are flagged for review.",
    how: "The regression runs on the setup you confirmed. Each variable's coefficient, t / p, ROI and contribution land on the factor tree; results outside the knowledge-base industry ranges are flagged for you to drop.",
    basisNote: '行业经验 ROI / 贡献区间（知识库维护）+ 业务校验假设。',
    workNote: 'OLS fitted; ranges checked.',
    dependsOn: ['2.5p'], duration: 2, produces: ['a-ols-test'],
    decision: {
      id: 'd-2.5', kind: 'choice', title: 'Confirm indicator selection',
      question: "The OLS test checked each factor's ROI / contribution against its knowledge-base range. Confirm the selection, drop the flagged indicators, or revisit the business hypotheses?",
      evidence: [
        { artifactId: 'a-ols-test', note: 'Per-factor ROI / contribution vs knowledge ranges' },
        { artifactId: 'a-business-validation', note: 'Business hypotheses' },
      ],
      recommendation: 'Selected indicators fall within their expected ranges — confirm and assemble the master table.',
      options: [
        { id: 'confirm', label: 'Confirm selection', detail: 'Selected indicators enter the master table', consequence: 'Master data is assembled for modeling', recommended: true },
        { id: 'drop', label: 'Drop flagged indicators', detail: 'Remove the out-of-range indicators', consequence: 'Master data is assembled without them' },
        { id: 'rework', label: 'Revisit hypotheses', detail: 'Out-of-range factors need rethinking', consequence: 'Business validation is revisited' },
      ],
      reworkTaskId: '2.3', reworkOptionId: 'rework',
    },
  },
  {
    id: '2.6', name: 'Assemble master data', agent: 'data', stage: 's2', class: 'M',
    summary: 'Assemble the indicators that survived every filter layer into the master feature wide table modeling consumes — sliceable by product × channel × region.',
    how: 'The pipeline pivots the adopted indicators — the response you confirmed at 2.5y, the variables you ticked at 2.5x — into one feature wide table per model object. Every rejected indicator keeps the chain of verdicts that removed it, so the funnel is auditable end to end.',
    basisNote: '指标生命周期账本：映射/质量/业务签核/统计/选择/区间六层裁决。',
    workNote: 'Master feature table assembled from the adopted indicators.',
    dependsOn: ['2.5r'], duration: 2, produces: ['a-master-data'],
  },
  {
    id: '2.6d', name: 'Lock master data', agent: 'data', stage: 's2', class: 'H',
    summary: 'Review the assembled feature table and the filter funnel behind it, then lock it as the modeling input.',
    how: 'You slice the table by product × channel × region, check the funnel accounts for every dropped indicator, and lock it. Locking is a human act — modeling should never start on a table nobody looked at.',
    basisNote: 'Master feature 宽表 + 六层过滤漏斗。',
    workNote: 'Awaiting the master-data lock.',
    dependsOn: ['2.6'], duration: 1, produces: [],
    decision: {
      id: 'd-2.6', kind: 'approval', title: 'Lock the master data',
      question: 'Review the assembled feature table and lock it as the modeling input?',
      evidence: [
        { artifactId: 'a-master-data', note: 'Feature table + filter funnel' },
        { artifactId: 'a-ols-test', note: 'The fit it was assembled from' },
      ],
      recommendation: 'The table carries only indicators that survived every filter layer — lock it to start modeling.',
      options: [
        { id: 'lock', label: 'Lock master data', detail: 'Modeling trains on this table', consequence: 'Model assumptions are registered next', recommended: true },
        { id: 'rework', label: 'Revisit the variables', detail: 'The selection needs another pass', consequence: 'The OLS setup is revisited' },
      ],
      reworkTaskId: '2.5', reworkOptionId: 'rework',
    },
  },

  /* ════ S4 · Modeling ════ */
  {
    id: '3.1', name: 'Register model assumptions', agent: 'model', stage: 's4', class: 'C',
    summary: 'Turn confirmed business judgments into bounded model constraints, each traced to its source.',
    how: 'AI turns each client-confirmed business judgment into a bounded model constraint (sign, range, lag, saturation), traced back to its source.',
    basisNote: '知识包 + 业务校验假设。',
    workNote: '6 constraints registered: 外卖大战 dummy, competitor terms negative, cooler effect positive with saturation, 社媒 leads sales 1–2 months…',
    dependsOn: ['2.6d'], duration: 2, produces: ['a-prior-register'],
    decision: {
      id: 'd-3.1', kind: 'approval', title: 'Confirm model assumptions',
      question: 'Each constraint below traces to a client-confirmed judgment. Confirm the set before training starts?',
      evidence: [
        { artifactId: 'a-prior-register' },
        { artifactId: 'a-knowledge-package', note: 'Source judgments' },
      ],
      recommendation: 'Confirm. All six constraints carry a client confirmation reference. The cooler saturation bound is the only one based on a pilot (成都) rather than an experiment — it is marked as softer.',
      options: [
        { id: 'approve', label: 'Confirm assumptions', detail: 'Training uses these bounds', consequence: 'Model results will be checked against this register', recommended: true },
        { id: 'rework', label: 'Revise first', detail: 'A constraint needs rewording', consequence: 'Register is redrafted' },
      ],
      reworkTaskId: '3.1', reworkOptionId: 'rework',
    },
  },
  {
    id: '3.2', name: 'Train & tune models', agent: 'model', stage: 's4', class: 'M',
    summary: 'Bayesian hierarchical training per model object (channel × region group); convergence checked every round.',
    how: 'Bayesian hierarchical models train per model object; convergence is checked each round and 3 candidates are kept per object.',
    workNote: '4 model objects trained (MT / TT / AFH / EC+O2O). All chains converged. 3 candidates kept per object.',
    dependsOn: ['3.1'], duration: 5, produces: ['a-model-candidates'],
  },
  {
    id: '3.3', name: 'Technical review', agent: 'model', stage: 's4', class: 'C',
    summary: 'Cross-check R² / error rate / residual health per candidate; any negative baseline stops the line.',
    how: 'Each candidate is cross-checked on R² / error / residual health; a negative baseline or wrong-sign channel is a hard stop.',
    basisNote: '技术检验基准（R² 85–95% · MAPE 5–15% · DW 1.5–2.5）。',
    workNote: 'AFH candidate B: R² 0.95, error 8%, residual autocorrelation low. No negative baseline, no wrong-sign channels.',
    dependsOn: ['3.2'], duration: 2, produces: ['a-tech-review', 'a-model-diagnostics'],
  },
  {
    id: '3.4', name: 'Business review & model pick', agent: 'business', stage: 's4', class: 'H',
    summary: 'Check results against the assumption register; a person picks the final model.',
    how: 'You compare the technically-passing candidates against the confirmed assumptions and pick the model to deliver.',
    workNote: 'Candidates compared against the register. Awaiting the final pick.',
    dependsOn: ['3.3'], duration: 1, produces: [],
    decision: {
      id: 'd-3.4', kind: 'choice', title: 'Pick the final model',
      question: 'Three candidates passed the technical review. Pick the one to deliver — priority: ① fits confirmed business judgments ② plausible decomposition ③ statistical fit.',
      evidence: [
        { artifactId: 'a-tech-review' },
        { artifactId: 'a-model-candidates' },
        { artifactId: 'a-prior-register', note: 'Confirmed bounds for comparison' },
      ],
      recommendation: 'Candidate B. Every elasticity lands inside the confirmed bounds and the cooler story matches the 成都 pilot. Candidate A fits the data slightly better but its baseline dips below what the business would accept; Candidate C inflates Media at the expense of Trade.',
      options: [
        { id: 'cand-a', label: 'Candidate A', detail: 'Best raw fit (R² 0.96) · baseline 41% — below the agreed floor', consequence: 'Needs a written exception on baseline' },
        { id: 'cand-b', label: 'Candidate B', detail: 'R² 0.95 · all bounds respected · cooler ≈ pilot evidence', consequence: 'Proceeds straight to reporting', recommended: true },
        { id: 'cand-c', label: 'Candidate C', detail: 'R² 0.93 · Media share looks inflated vs spend', consequence: 'Media ROI claims would need extra caveats' },
      ],
    },
  },

  /* ════ S5 · Reporting ════ */
  {
    id: '4.1a', name: 'Build report tables & charts', agent: 'report', stage: 's5', class: 'M',
    summary: 'Decomposition, contribution, growth attribution and ROI views per channel from the picked model.',
    how: 'AI builds the decomposition, contribution, growth-attribution and ROI views per channel from the picked model.',
    workNote: 'AFH / TT / MT chart books built. Part 0 business overview → Part 1 national summary → Part 2 regional.',
    dependsOn: ['3.4'], duration: 3, produces: ['a-decomp-results', 'a-results-dashboard'],
  },
  {
    id: '4.1b', name: 'Write the narrative', agent: 'report', stage: 's5', class: 'A',
    summary: 'AI drafts the reading for every chart following the house style; reviewers polish.',
    how: 'AI drafts the reading for each chart in the house style (magnitude + share for every claim); reviewers polish the wording.',
    basisNote: '报告解读话术模板。',
    workNote: '"Trade 对生意增量占比最大，Media & Activation 增速最快" — narrative drafted per template with magnitude + share for every claim.',
    dependsOn: ['4.1a'], duration: 2, produces: ['a-final-report'],
    aiOptions: {
      id: 'ai-4.1b', prompt: '报告叙述风格？',
      options: [
        { id: 'exec', label: 'Executive concise', rationale: '决策者友好，结论先行', tradeoff: '细节需放附录', recommended: true },
        { id: 'detailed', label: 'Detailed', rationale: '完整论证链', tradeoff: '篇幅长' },
        { id: 'data', label: 'Data-heavy', rationale: '图表与数字驱动', tradeoff: '可读性下降' },
      ],
    },
  },
  {
    id: '4.1c', name: 'Review & deliver', agent: 'report', stage: 's5', class: 'H',
    summary: 'Final read-through, then deliver to the client.',
    how: 'You do a final read-through and release the report (and the modeling-config export) to the client.',
    workNote: 'Awaiting release decision.',
    dependsOn: ['4.1b'], duration: 1, produces: [],
    decision: {
      id: 'd-4.1', kind: 'approval', title: 'Release the final report',
      question: 'Release the report to the client? Every factor-tree question should map to at least one chart.',
      evidence: [
        { artifactId: 'a-final-report' },
        { artifactId: 'a-factor-tree', note: 'Coverage check across the confirmed factors' },
      ],
      recommendation: 'Release. Every confirmed factor traces to evidence charts. Two known limitations are stated up front: 朗镜 门店执行 data covers 5 months only, and 批发渠道 attribution is approximate.',
      options: [
        { id: 'approve', label: 'Release', detail: 'Deliver to the client', consequence: 'Project moves to wrap-up & knowledge capture', recommended: true },
        { id: 'rework', label: 'Hold for edits', detail: 'Narrative needs changes', consequence: 'Report goes back for rewriting' },
      ],
      reworkTaskId: '4.1b', reworkOptionId: 'rework',
    },
  },
]

export const TASK_MAP = new Map(TASKS.map((t) => [t.id, t]))

/** Transitive downstream set — used to reset work after a send-back */
export function downstreamOf(taskId: string): Set<string> {
  const result = new Set<string>()
  const visit = (id: string) => {
    for (const t of TASKS) {
      if (t.dependsOn.includes(id) && !result.has(t.id)) {
        result.add(t.id)
        visit(t.id)
      }
    }
  }
  visit(taskId)
  return result
}
