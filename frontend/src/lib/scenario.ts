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

  /* ════ S2 · Data Intake & Quality (2.1 Validation + 2.2 Process) ════ */
  {
    id: '2.0a', name: 'Collect client data', agent: 'data', stage: 's2', class: 'H',
    summary: 'Provide the filled data-request workbooks returned by the client teams — one workbook per L3 slot.',
    how: 'You upload each L3 workbook to the Project Folder (Data); the gate clears once every required L3 slot validates against the factor tree.',
    basisNote: '客户回填的数据需求工作簿（按 L3 slot，对应 37 个数据任务）。',
    workNote: 'Waiting for the data files. Per-L3 coverage is validated before intake closes.',
    dependsOn: ['1.7'], duration: 1, produces: ['a-data-files'],
    assignment: {
      id: 'in-2.0a', kind: 'upload', title: 'Collect client data (per-L3 slot)',
      prompt: '按数据需求清单逐个 L3 上传客户回填工作簿到 Project Folder (Data)。系统按因子树校验每个 L3 的 L4/指标覆盖度，全部覆盖后方可进入数据校验。',
      items: ['Media_spend_impression.xlsx', 'Nielsen_offtake.xlsx', 'Store_execution.xlsx', '+34 more'],
      submitLabel: 'Submit data files',
      category: 'data', requiresUpload: true, requiresManifest: true,
    },
  },
  // 2.1 Data Validation — standard (loaded) → AI score → human review
  {
    id: '2.11', name: 'Data validation standard', agent: 'data', stage: 's2', class: 'M',
    summary: 'Load the EXISTING general validation standard: the four-rule compliance principles and the 0 / 0.5 / 1 scoring rubric (not AI-authored).',
    how: 'The standard is loaded verbatim from the reference rule library (the two 2.11 sheets); it grounds the AI scoring that follows.',
    basisNote: '数据通用校验标准 + 打分规则（reference 2.11 sheets）。',
    workNote: '四大校验规则 + 0/0.5/1 打分细则已载入。',
    dependsOn: ['2.0a'], duration: 1, produces: ['a-validation-standard'],
  },
  {
    id: '2.12', name: 'AI scores data quality', agent: 'data', stage: 's2', class: 'A',
    summary: 'The AI scores every L1×L2×L3×L4×metric on the four dimensions (一致性/完整性/颗粒度/真实性, each 0 / 0.5 / 1) with a 情况 note, grounded in the rubric + computed evidence.',
    how: 'AI applies the loaded rubric to the computed data evidence, assigning each dimension 0 / 0.5 / 1 and writing the 情况; the verdict (weakest dimension governs) is reviewed by a human next.',
    basisNote: '校验标准 + 回填数据证据。',
    workNote: 'AI 逐指标四维评分 + 情况；Total = 最弱维度。',
    dependsOn: ['2.11'], duration: 3, produces: ['a-quality-scorecard'],
  },
  {
    id: '2.13', name: 'Review data quality verdicts', agent: 'data', stage: 's2', class: 'H',
    summary: 'Human reviews the AI scores; Final = 完整性+颗粒度+真实性+一致性 → 1 验收 · 0 不可用 · 0.5 人决策 (re-collect / drop / accept-with-caveat).',
    how: "You review the scorecard: accept the 1s, drop the 0s (alert if a factor's only metrics all fail), and decide each 0.5.",
    basisNote: 'AI 质量评分 + 验收标准。',
    workNote: 'Awaiting human review of the data-quality verdicts.',
    dependsOn: ['2.12'], duration: 1, produces: [],
    decision: {
      id: 'd-2.13', kind: 'choice', title: 'Review data-quality verdicts',
      question: 'The AI scored each metric; Final = the weakest of 完整性/颗粒度/真实性/一致性. Review and decide how to handle the 0.5-band metrics.',
      evidence: [
        { artifactId: 'a-quality-scorecard', note: 'Per-metric scores & verdicts (1 / 0.5 / 0)' },
        { artifactId: 'a-validation-standard', note: 'Acceptance standard' },
      ],
      recommendation: 'Accept the 1s and drop the clear 0s. For each 0.5, re-collect when the metric is the factor’s only signal; otherwise let it enter flagged.',
      options: [
        { id: 'accept', label: 'Accept the verdicts', detail: 'Keep the 1s, drop the 0s, 0.5 enter flagged', consequence: 'Schema & processing start on the accepted metrics', recommended: true },
        { id: 'recollect', label: 'Re-collect 0.5 data', detail: 'Ask the client to re-upload the borderline metrics', consequence: 'Intake reopens for the flagged L3s; timeline slips' },
        { id: 'drop', label: 'Drop the 0.5 metrics', detail: 'Exclude borderline metrics from this model', consequence: 'Leaner model; those factors enter via aggregate metrics only' },
      ],
      reworkTaskId: '2.0a', reworkOptionId: 'recollect',
    },
  },
  // 2.2 Data Process
  {
    id: '2.21', name: 'Define wide-table schema', agent: 'data', stage: 's2', class: 'C',
    summary: 'Define the unified long-table schema from the factor tree: model + time granularity, factor L1–L4, deep-dive L5–L8, metric type / unit.',
    how: 'AI derives the long-table column contract from the confirmed factor tree (因子树即数据 Schema); every data task outputs to this shape.',
    basisNote: '因子树 L1–L8 + 模型/时间颗粒度 + 指标类型。',
    workNote: '统一长表 Schema 成形（L1–L8 → 列）。',
    dependsOn: ['2.13'], duration: 2, produces: ['a-schema'],
  },
  {
    id: '2.22', name: 'Confirm processing logic per source', agent: 'data', stage: 's2', class: 'A',
    summary: 'AI drafts mapping/transform logic for each of the 37 data tasks (TaskLog); owners check before the pipeline runs.',
    how: 'AI drafts the column-level mapping/transform/calculation logic for each of the 37 source tasks; two owners cross-check before the pipeline runs.',
    basisNote: '宽表 Schema + 回填数据。',
    workNote: 'Task10 Sell-out: 大区分类 refreshed to 5 regions (KA/华东/华西/华南/华北). Task29 ANP: 负数反冲 kept visible. Two-person cross-check logged.',
    dependsOn: ['2.21'], duration: 3, produces: ['a-data-dictionary'],
    decision: {
      id: 'd-2.22', kind: 'approval', title: 'Confirm processing logic',
      question: 'AI drafted the column-level mapping / transform / calculation logic per source and two owners cross-checked. Confirm before the integration pipeline runs?',
      evidence: [
        { artifactId: 'a-data-dictionary', note: 'Per-source processing logic' },
        { artifactId: 'a-schema', note: 'Target schema' },
      ],
      recommendation: 'Two-person cross-check logged with no open issues — safe to confirm and run the pipeline.',
      options: [
        { id: 'approve', label: 'Confirm logic', detail: 'Owners signed off', consequence: 'Data dictionary is registered, then the pipeline integrates', recommended: true },
        { id: 'rework', label: 'Request changes', detail: "A source's mapping / transform needs fixing", consequence: 'Processing logic is redrafted' },
      ],
      reworkTaskId: '2.22', reworkOptionId: 'rework',
    },
  },
  {
    id: '2.23', name: 'Register data dictionary', agent: 'data', stage: 's2', class: 'C',
    summary: 'Register the ODS→DW metadata: per source table, column-level ETL (Hardcode / Mapping / Transform / Calculation), and the master-data mappings.',
    how: 'AI registers the confirmed processing logic into the data dictionary that the integration pipeline reads.',
    basisNote: '确认版处理逻辑 + 主数据 mapping。',
    workNote: '数据字典登记完成（列级 ETL 四类）。',
    dependsOn: ['2.22'], duration: 2, produces: ['a-data-warehouse'],
  },
  {
    id: '2.24', name: 'Integrate the master dataset', agent: 'data', stage: 's2', class: 'M',
    summary: 'Run the pipeline: one long table on the 2.21 schema, keyed by brand × region × channel × month × factor levels.',
    how: 'The pipeline cleans master data (Product / Geo / Channel / Time) and integrates everything into one long table on the unified schema.',
    basisNote: '数据字典 + 宽表 Schema。',
    workNote: '23,791 rows integrated. Master-data cleaning applied (Product / Geo / Channel / Time).',
    dependsOn: ['2.23'], duration: 3, produces: ['a-dataset'],
  },

  /* ════ S3 · Validation & Hypotheses (2.3 Data Cross-Validation) ════ */
  {
    id: '2.31', name: 'Business validation rules & drill-down', agent: 'data', stage: 's3', class: 'C',
    summary: 'Lay out the six-step business-validation rules and the L5–L8 drill-down map that anomaly localization runs on.',
    how: 'AI assembles the business-validation rules (六步法) and the per-L4 drill-down configuration grounded in the factor tree.',
    basisNote: '宽表数据集 + 行业基准 + 因子下钻维度。',
    workNote: '业务校验规则 + L5–L8 下钻框架成形；O2O 2025 增速 +80% 已定位待核对。',
    dependsOn: ['2.24'], duration: 2, produces: ['a-drill-framework'],
    aiOptions: {
      id: 'ai-2.31', prompt: 'O2O +80% 异常怎么处理？',
      options: [
        { id: 'event', label: 'Structural-event marker', rationale: '与 GM 访谈"外卖大战"一致，避免误归因到营销', tradeoff: '需客户确认事件时段', recommended: true },
        { id: 'cap', label: 'Outlier capping', rationale: '快速稳健，降低尖峰影响', tradeoff: '可能抹掉真实业务增长' },
        { id: 'raw', label: 'Leave raw + caveat', rationale: '保留真实数据', tradeoff: '模型可能高估线上营销 ROI' },
      ],
    },
  },
  {
    id: '2.32', name: 'Data review & client sign-off', agent: 'data', stage: 's3', class: 'C',
    summary: 'Charting + trend interpretation deck (per-page Y/N sign-off) plus the data & metric Q&A tracker; every chart needs sign-off before modeling.',
    how: 'AI runs the six-step review into a deck and a client Q&A tracker; you walk the client through it and record their Y/N sign-off per chart. Unsigned data does not enter the model.',
    basisNote: '业务校验规则 + 宽表数据集。',
    workNote: 'Review deck + 数据&指标沟通表 built. 3 open questions raised. Awaiting client sign-off.',
    dependsOn: ['2.31'], duration: 3, produces: ['a-trend-review', 'a-client-qa'],
    decision: {
      id: 'd-2.32', kind: 'signoff', title: 'Record client sign-off on data',
      question: 'Did the client sign off the data review? Unsigned charts cannot enter modeling. Record the outcome (charts, definitions, open questions).',
      evidence: [
        { artifactId: 'a-trend-review' },
        { artifactId: 'a-client-qa', note: '3 open questions raised during the review' },
      ],
      recommendation: 'The three open questions (WD weighting, 批发 split, RSP 折扣口径) all received answers in the session — safe to record sign-off with notes attached.',
      options: [
        { id: 'approve', label: 'Signed off', detail: 'Client confirmed, notes attached', consequence: 'Data is locked for modeling', recommended: true },
        { id: 'rework', label: 'Not signed off', detail: 'Client raised blocking issues', consequence: 'Review is revisited with the new input' },
      ],
      reworkTaskId: '2.32', reworkOptionId: 'rework',
    },
  },
  {
    id: '2.33', name: 'Statistical screening', agent: 'data', stage: 's3', class: 'M',
    summary: 'Variability, correlation and collinearity tests per metric; combined score decides model entry.',
    how: 'Variability (CV), correlation (Pearson) and collinearity (VIF) are computed per metric and combined into an entry score (≥3 good, <1.5 dropped).',
    basisNote: '统计筛选规则（Solution library）。',
    workNote: 'GDP & 消费者信心指数 strongly collinear with NAB 品类趋势 — both flagged for removal (already reflected in category trend).',
    dependsOn: ['2.32'], duration: 2, produces: ['a-stat-tests'],
    decision: {
      id: 'd-2.33', kind: 'choice', title: 'Borderline metrics into the model',
      question: 'Some metrics scored Acceptable (1.5–3) — neither clearly in nor out. How should they enter the model?',
      evidence: [
        { artifactId: 'a-stat-tests', note: 'Acceptable-band (1.5–3) rows' },
        { artifactId: 'a-quality-scorecard', note: 'Upstream quality dispositions' },
      ],
      recommendation: 'Keep the Acceptable-band metrics alongside the Good ones; the pre-fit (2.34) then checks each against its contribution / ROI range.',
      options: [
        { id: 'keep', label: 'Keep acceptable metrics', detail: 'Enter with the Good-band metrics', consequence: 'Pre-fit checks their contribution range', recommended: true },
        { id: 'drop', label: 'Drop the weakest', detail: 'Keep only Good-band metrics', consequence: 'Leaner model; some factors lose a metric' },
        { id: 'review', label: 'Review case-by-case', detail: 'Open the scorecard to decide per metric', consequence: 'Manual selection before pre-fit' },
      ],
    },
  },
  {
    id: '2.34', name: 'Quick pre-fit check', agent: 'data', stage: 's3', class: 'C',
    summary: 'Fast linear fit to verify each factor lands in a believable contribution and ROI range before full modeling.',
    how: 'A fast OLS fit checks each factor lands in a believable contribution and ROI range before the full Bayesian model is built.',
    basisNote: '行业弹性范围 + 业务校验假设。',
    workNote: 'Cooler contribution direction matches the 成都 pilot story. 社媒 elasticity within industry range. No red flags.',
    dependsOn: ['2.33'], duration: 2, produces: ['a-model-input'],
    decision: {
      id: 'd-2.34', kind: 'choice', title: 'Confirm metric selection',
      question: "Pre-fit checked each L4 factor's selected metric against its contribution / ROI range. Confirm the selection, or revisit the business hypotheses?",
      evidence: [
        { artifactId: 'a-model-input', note: '指标筛选 sheet' },
        { artifactId: 'a-trend-review', note: 'Business hypotheses' },
      ],
      recommendation: 'Selected metrics fall within their expected ranges — confirm and proceed to modeling.',
      options: [
        { id: 'confirm', label: 'Confirm selection', detail: 'Selected metrics enter the model', consequence: 'Model Input is locked for training', recommended: true },
        { id: 'rework', label: 'Revisit hypotheses', detail: 'Out-of-range factors need rethinking', consequence: 'Business sense-check is revisited' },
      ],
      reworkTaskId: '2.31', reworkOptionId: 'rework',
    },
    aiOptions: {
      id: 'ai-2.34', prompt: '预拟合里季节性怎么建模？',
      options: [
        { id: 'prophet', label: 'Prophet seasonality', rationale: '自动捕捉年节与旺季，拟合稳定', tradeoff: '可解释性略低', recommended: true },
        { id: 'dummies', label: 'Monthly dummies', rationale: '透明可控', tradeoff: '自由度消耗多' },
        { id: 'none', label: 'None', rationale: '最简', tradeoff: '旺季信号会漏入媒体项' },
      ],
    },
  },

  /* ════ S4 · Modeling ════ */
  {
    id: '3.1', name: 'Register model assumptions', agent: 'model', stage: 's4', class: 'C',
    summary: 'Turn confirmed business judgments into bounded model constraints, each traced to its source.',
    how: 'AI turns each client-confirmed business judgment into a bounded model constraint (sign, range, lag, saturation), traced back to its source.',
    basisNote: '知识包 + 业务校验假设。',
    workNote: '6 constraints registered: 外卖大战 dummy, competitor terms negative, cooler effect positive with saturation, 社媒 leads sales 1–2 months…',
    dependsOn: ['2.34'], duration: 2, produces: ['a-prior-register'],
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
