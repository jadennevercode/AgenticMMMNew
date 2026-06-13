import type { TaskBlueprint } from './types'

/**
 * Task playbook — Danone Mizone MMM POC.
 * S1 (Business Understanding) follows the MMM-Study pre-modeling flow:
 * Framing → Knowledge Assembly → Factor Tree → Indicators → Data Request,
 * with explicit import/export touchpoints.
 * UI copy is English; client/business content quoted inside notes may be Chinese.
 */
export const TASKS: TaskBlueprint[] = [
  /* ════ S1 · Business Understanding ════ */
  {
    id: '1.0a', name: 'Provide SOW & project brief', agent: 'business', stage: 's1', class: 'H',
    summary: 'Upload the signed SOW and any kickoff brief so the team can frame scope and granularity.',
    how: 'You attach the signed SOW and brief; the files are logged as the project’s source of truth and feed scope framing.',
    basisNote: '客户签署的 SOW 与立项简报。',
    workNote: 'Waiting for the SOW. Nothing downstream can start until scope is framed.',
    dependsOn: [], duration: 1, produces: ['a-sow'],
    assignment: {
      id: 'in-1.0a', kind: 'upload', title: 'Provide the SOW',
      prompt: '上传已签署的 SOW 与项目简报（渠道范围、产品线、KPI、时间窗口）。AI 将据此起草项目范围与 KBQ。',
      items: ['Danone_Mizone_MMM_SOW_signed.pdf', 'Kickoff_brief_20251118.pptx'],
      submitLabel: 'Submit SOW',
    },
  },
  {
    id: '1.0', name: 'Frame project scope & KBQ', agent: 'business', stage: 's1', class: 'C',
    summary: 'Frame scope (brand / category / market / channels / time window) and a structured list of key business questions.',
    how: 'AI reads the SOW and proposes scope + a structured KBQ list against the hard limits (≤4 channels, ≤6 region/platform groups, 1 product line); you confirm or send back.',
    basisNote: 'SOW + 行业包的标准 KBQ 框架（六类业务问题）。',
    workNote: 'Scope drafted: MT / TT / AFH / EC+O2O · 除脉动电解质外所有（为一组）· 2022-10→2025-10 月度. 6 KBQ structured.',
    dependsOn: ['1.0a'], duration: 2, produces: ['a-scope', 'a-kbq'],
    decision: {
      id: 'd-1.0', kind: 'approval', title: 'Confirm scope & KBQ',
      question: 'Does the framed scope + KBQ match the SOW and the client’s priorities? Confirming locks the analysis granularity.',
      evidence: [{ artifactId: 'a-scope' }, { artifactId: 'a-kbq', note: 'Structured key business questions' }],
      recommendation: 'Looks consistent with the SOW. All three hard limits hold. One thing to note: 脉动电解质 is excluded from the product group — flag it to the client to avoid surprises later.',
      options: [
        { id: 'approve', label: 'Confirm scope & KBQ', detail: 'Lock granularity and continue', consequence: 'Knowledge assembly starts on this scope', recommended: true },
        { id: 'rework', label: 'Send back for changes', detail: 'Adjust channels, grouping or KBQ', consequence: 'Scope is re-framed; nothing downstream starts' },
      ],
      reworkTaskId: '1.0', reworkOptionId: 'rework',
    },
  },
  {
    id: '1.1a', name: 'Upload brand reports & internal materials', agent: 'business', stage: 's1', class: 'H',
    summary: 'Provide brand financials, competitor benchmarks and internal materials for the AI to mine.',
    how: 'You upload the brand/competitor reports and any internal decks; AI mines them during knowledge assembly.',
    basisNote: '品牌财报、竞品研究、内部资料。',
    workNote: 'Waiting for materials. These feed the knowledge package alongside the interviews.',
    dependsOn: ['1.0'], duration: 1, produces: ['a-source-materials'],
    assignment: {
      id: 'in-1.1a', kind: 'upload', title: 'Upload reports & materials',
      prompt: '上传品牌财报、竞品研究（如 202408_Competitor Benchmark_CICC，密码 aurora）及内部资料。AI 将抽取为知识条目。',
      items: ['202408_Competitor_Benchmark_CICC.pdf', 'Mizone_brand_review_2025.pptx', 'Internal_channel_strategy.pdf'],
      submitLabel: 'Submit materials',
    },
  },
  {
    id: '1.1b', name: 'Upload interview minutes', agent: 'business', stage: 's1', class: 'H',
    summary: 'Upload the layered interview minutes (11 sessions) for the AI to structure.',
    how: 'You upload the minutes; AI structures them into knowledge items during knowledge assembly.',
    basisNote: '分层访谈纪要（GM / 管理层 / 执行层共 11 场）。',
    workNote: 'Waiting for the minutes. Structured into the knowledge package, not read raw downstream.',
    dependsOn: ['1.0'], duration: 1, produces: ['a-minutes-raw'],
    assignment: {
      id: 'in-1.1b', kind: 'upload', title: 'Upload interview minutes',
      prompt: '上传分层访谈纪要（11 场：GM / Mkt / Sales / Finance / Media / Activation / EC / KA / Trade / Execution / SIA / O2O）。',
      items: ['Layer1_GM.docx', 'Layer2_Mkt.docx', 'Layer3_Media.docx', '+8 more'],
      submitLabel: 'Submit minutes',
    },
  },
  {
    id: '1.1', name: 'Assemble project knowledge package', agent: 'business', stage: 's1', class: 'C',
    summary: 'Structure interviews + materials into knowledge items (source / confidence / scope) and flag conflicts & gaps.',
    how: 'AI pulls applicable items from the industry pack and structures the uploaded interviews + materials into tagged knowledge items, then flags where new input conflicts with the pack or leaves a gap.',
    basisNote: '行业知识包 + 上传的访谈与资料。',
    workNote: '知识包成形：行业通识条目 + 客户特定条目（来源/置信度/适用范围）。冲突 2 处、缺口 1 处已标注（如朗镜门店执行仅 5 个月）。',
    dependsOn: ['1.1a', '1.1b'], duration: 3, produces: ['a-knowledge-package'],
  },
  {
    id: '1.21', name: 'Derive factor-tree candidates (L3/L4)', agent: 'business', stage: 's1', class: 'C',
    summary: 'Derive L3/L4 candidates on the locked L1/L2 skeleton; each node carries its derivation basis and a reference case.',
    how: 'AI derives L3/L4 candidate nodes from the knowledge package on top of the fixed L1/L2 skeleton; every node shows why it was derived and which reference case it draws on.',
    basisNote: '知识包 + L1/L2 通用骨架（锁定）。',
    workNote: '4 个 L1 组 / 锁定 L2；L3/L4 候选已生成，每个节点附推导依据。访谈驱动的改动以建议形式待确认。',
    dependsOn: ['1.1'], duration: 2, produces: ['a-factor-tree'],
  },
  {
    id: '1.21d', name: 'Confirm factor tree', agent: 'business', stage: 's1', class: 'H',
    summary: 'Review the derived tree and interview-driven changes; L1/L2 locked, add/remove/edit L3/L4, then confirm.',
    how: 'You review the candidate tree against the knowledge package; L1/L2 are locked, you accept/adjust the L3/L4 (including the interview-driven change suggestions), then lock the tree.',
    workNote: 'Awaiting confirmation of the L3/L4 structure and the interview-driven changes.',
    dependsOn: ['1.21'], duration: 1, produces: [],
    decision: {
      id: 'd-1.21', kind: 'approval', title: 'Confirm the factor tree',
      question: 'The interviews suggest three L3/L4 changes (see the side-by-side on the Factor Tree). Confirm the tree with those changes?',
      evidence: [
        { artifactId: 'a-factor-tree' },
        { artifactId: 'a-knowledge-package', note: 'Source judgments & conflicts' },
      ],
      recommendation: 'Confirm with the three changes. Each traces to a specific interview quote: 外卖大战 (GM), 批发并入TT (Sales execution), 现调饮料外卖销量 (GM) — all within the 10–20% adjustment allowance on L3/L4.',
      options: [
        { id: 'approve', label: 'Confirm factor tree', detail: 'Lock L1–L4 (v2 with changes)', consequence: 'Indicator candidates are generated next', recommended: true },
        { id: 'rework', label: 'Re-derive', detail: 'The tree missed or misread something', consequence: 'AI re-derives from the knowledge package' },
      ],
      reworkTaskId: '1.21', reworkOptionId: 'rework',
    },
  },
  {
    id: '1.22', name: 'Generate indicator candidates', agent: 'business', stage: 's1', class: 'C',
    summary: 'For each L4, propose 3–5 candidate indicators, each scored on consumer relevance, variability and executability.',
    how: 'AI proposes 3–5 candidate indicators per L4 factor and scores each on three dimensions — consumer relevance, expected variability, and executability — with a one-line rationale.',
    basisNote: '行业包指标库 + 确认版因子树。',
    workNote: 'Candidates generated for every L4. e.g. 铺货 → 本品 ND / WD / 货架份额(SOS)，三维打分附理由。',
    dependsOn: ['1.21d'], duration: 2, produces: ['a-indicator-candidates'],
  },
  {
    id: '1.22d', name: 'Select indicators', agent: 'business', stage: 's1', class: 'H',
    summary: 'Pick a primary (and optional alternate) indicator per L4 and set granularity.',
    how: 'You pick the primary (and optional alternate) indicator per L4 and set its granularity; the selection becomes the indicator list that drives the data request.',
    workNote: 'Awaiting the per-factor indicator selection.',
    dependsOn: ['1.22'], duration: 1, produces: ['a-indicator-list'],
    decision: {
      id: 'd-1.22', kind: 'approval', title: 'Confirm indicator selection',
      question: 'Confirm the primary/alternate indicator and granularity for each L4 factor?',
      evidence: [
        { artifactId: 'a-indicator-candidates', note: '3–5 candidates × 3-dim scores' },
        { artifactId: 'a-indicator-list', note: 'Proposed selection' },
      ],
      recommendation: 'The pre-filled selection follows the highest 3-dim scores and matches the granularity the model needs. 铺货 uses WD over ND (better quality signal); 媒体 uses impression over spend where both exist.',
      options: [
        { id: 'approve', label: 'Confirm selection', detail: 'Lock the indicator list', consequence: 'Data-request package is generated next', recommended: true },
        { id: 'rework', label: 'Re-propose candidates', detail: 'Candidates miss a better option', consequence: 'AI regenerates candidates' },
      ],
      reworkTaskId: '1.22', reworkOptionId: 'rework',
    },
  },
  {
    id: '1.23', name: 'Generate data-request package', agent: 'business', stage: 's1', class: 'A',
    summary: 'Lay out a collection workbook — one sheet per L3/L4 with required granularity and fields — ready to send.',
    how: 'AI lays out a collection workbook (one sheet per L3/L4, columns per granularity, with definitions and example rows) sized to the confirmed indicator list.',
    basisNote: '指标清单 + 数据源标准（颗粒度、典型字段名）。',
    workNote: '12 个数据需求模板已生成（Media / Store Execution / BHT / Macro / 竞品RSP / Omni-channel …），含 Time Coverage 与 Brand Coverage 声明。',
    dependsOn: ['1.22d'], duration: 2, produces: ['a-data-request'],
  },
  {
    id: '1.23b', name: 'Export & send data request', agent: 'business', stage: 's1', class: 'H',
    summary: 'Download the data-request template and send it to the owning client teams, then mark it sent.',
    how: 'You download the data-request workbook, send it to the owning client teams (Media / Sales / Trade / SIA / EC / O2O), and mark it sent so the team knows data is expected.',
    workNote: 'Awaiting export & send. The collected data comes back in the next stage.',
    dependsOn: ['1.23'], duration: 1, produces: [],
    assignment: {
      id: 'in-1.23b', kind: 'export', title: 'Export & send the data request',
      prompt: '导出数据需求工作簿并分发给各客户团队（按 owner 团队打包），发送后标记完成。回填数据将在下一阶段导入。',
      items: ['Data_request_Media.xlsx', 'Data_request_Sales+Trade.xlsx', 'Data_request_SIA.xlsx', 'Data_request_EC+O2O.xlsx'],
      submitLabel: 'Mark as sent',
    },
  },

  /* ════ S2 · Data Intake & Quality ════ */
  {
    id: '2.0a', name: 'Upload collected client data', agent: 'data', stage: 's2', class: 'H',
    summary: 'Provide the filled data-request workbooks returned by the client teams.',
    how: 'You upload the filled workbooks the client teams returned; per-metric scoring begins automatically.',
    basisNote: '客户回填的数据需求工作簿（对应 37 个数据任务）。',
    workNote: 'Waiting for the data files. Scoring and integration begin once they land.',
    dependsOn: ['1.23b'], duration: 1, produces: ['a-data-files'],
    assignment: {
      id: 'in-2.0a', kind: 'upload', title: 'Upload collected client data',
      prompt: '上传客户回填的数据需求工作簿（Media / Sales / Trade / SIA / EC / O2O 等 37 个数据任务来源）。AI 将逐指标打分并集成宽表。',
      items: ['Media_spend_impression.xlsx', 'Nielsen_offtake.xlsx', 'Store_execution.xlsx', '+34 more'],
      submitLabel: 'Submit data files',
    },
  },
  {
    id: '2.11', name: 'Score incoming data', agent: 'data', stage: 's2', class: 'M',
    summary: 'Score every metric on consistency, accuracy, completeness and granularity (0 / 0.5 / 1).',
    how: 'A rule engine scores each metric on the four quality dimensions; 0.5 (borderline) and 0 (unusable) rows are surfaced — a factor with no usable metric raises an alert.',
    basisNote: '数据质量打分规则（Solution library）。',
    workNote: '86 metrics scored. 79 passed, 4 scored 0.5 (need a call), 3 scored 0 (unusable — alert raised).',
    dependsOn: ['2.0a'], duration: 3, produces: ['a-quality-scorecard'],
    decision: {
      id: 'd-2.11', kind: 'choice', title: 'Borderline data: UTC 扫码瓶数',
      question: 'UTC 扫码瓶数 only exists from 2025-07 (score 0.5 — coverage too short). The factor 消费者促销-UTC扫码营销 has no other metric. How should we handle it?',
      evidence: [
        { artifactId: 'a-quality-scorecard', note: 'Row: UTC 扫码瓶数 — coverage 4 months' },
        { artifactId: 'a-client-qa', note: 'Client confirmed no earlier data exists' },
      ],
      recommendation: 'Drop it for this model and log a client note to keep collecting — four months cannot support a monthly model. Spend for the campaign is still covered under 消费者促销 totals, so the business effect is not lost entirely.',
      options: [
        { id: 'drop', label: 'Drop the metric, keep collecting', detail: 'Exclude from this model; client keeps logging data', consequence: 'Factor enters the model via the aggregate promotion metric only', recommended: true },
        { id: 'proxy', label: 'Use spend as proxy', detail: 'Model the factor on spend only', consequence: 'Weaker signal; flagged in the report' },
        { id: 'wait', label: 'Pause and ask the client', detail: 'Request historical reconstruction', consequence: 'Stage timeline slips ~1 week' },
      ],
    },
  },
  {
    id: '2.22', name: 'Confirm processing logic per source', agent: 'data', stage: 's2', class: 'A',
    summary: 'AI drafts mapping/transform logic for each of the 37 data tasks; owners check before the pipeline runs.',
    how: 'AI drafts the column-level mapping/transform/calculation logic for each of the 37 source tasks; two owners cross-check before the pipeline runs.',
    workNote: 'Task10 Sell-out: 大区分类 refreshed to 5 regions (KA/华东/华西/华南/华北). Task29 ANP: 负数反冲 kept visible. Two-person cross-check logged.',
    dependsOn: ['2.11'], duration: 3, produces: ['a-data-dictionary'],
  },
  {
    id: '2.24', name: 'Integrate the master dataset', agent: 'data', stage: 's2', class: 'M',
    summary: 'Run the pipeline: one long table keyed by brand × region × channel × month × factor levels.',
    how: 'The pipeline cleans master data (Product / Geo / Channel / Time) and integrates everything into one long table.',
    workNote: '23,791 rows integrated. Master-data cleaning applied (Product / Geo / Channel / Time).',
    dependsOn: ['2.22'], duration: 3, produces: ['a-dataset'],
  },

  /* ════ S3 · Validation & Hypotheses ════ */
  {
    id: '2.31', name: 'Business sense-check', agent: 'data', stage: 's3', class: 'C',
    summary: 'Six-step review: overview → breakdowns → anomalies → hypotheses → constraint candidates → client questions.',
    how: 'AI runs the six-step sense-check, drilling anomalies down the factor tree and turning them into hypotheses + constraint candidates + client questions.',
    basisNote: '宽表数据集 + 行业基准。',
    workNote: 'O2O 2025 增速 +80% 异常定位 → 假设：外卖平台大战放大流量（高置信）。3 个待客户核对问题已生成。',
    dependsOn: ['2.24'], duration: 3, produces: ['a-trend-review'],
  },
  {
    id: '2.32', name: 'Client data review & sign-off', agent: 'data', stage: 's3', class: 'H',
    summary: 'Walk the client through trends; every chart needs an explicit Y/N sign-off before modeling.',
    how: 'You walk the client through the review deck and record their Y/N sign-off per chart; unsigned data does not enter the model.',
    workNote: 'Review deck sent. Awaiting the recorded outcome of the client session.',
    dependsOn: ['2.31'], duration: 1, produces: [],
    decision: {
      id: 'd-2.32', kind: 'signoff', title: 'Record client sign-off on data',
      question: 'Did the client sign off the data review? Record the outcome of the session (charts, definitions, open questions).',
      evidence: [
        { artifactId: 'a-trend-review' },
        { artifactId: 'a-client-qa', note: '3 open questions raised during the review' },
      ],
      recommendation: 'The three open questions (WD weighting, 批发 split, RSP 折扣口径) all received answers in the session — safe to record sign-off with notes attached.',
      options: [
        { id: 'approve', label: 'Signed off', detail: 'Client confirmed, notes attached', consequence: 'Data is locked for modeling', recommended: true },
        { id: 'rework', label: 'Not signed off', detail: 'Client raised blocking issues', consequence: 'Sense-check is revisited with the new input' },
      ],
      reworkTaskId: '2.31', reworkOptionId: 'rework',
    },
  },
  {
    id: '2.33', name: 'Statistical screening', agent: 'data', stage: 's3', class: 'M',
    summary: 'Variability, correlation and collinearity tests per metric; combined score decides model entry.',
    how: 'Variability (CV), correlation (Pearson) and collinearity (VIF) are computed per metric and combined into an entry score (≥3 good, <1.5 dropped).',
    basisNote: '统计筛选规则（Solution library）。',
    workNote: 'GDP & 消费者信心指数 strongly collinear with NAB 品类趋势 — both flagged for removal (already reflected in category trend).',
    dependsOn: ['2.32'], duration: 2, produces: ['a-stat-tests'],
  },
  {
    id: '2.34', name: 'Quick pre-fit check', agent: 'data', stage: 's3', class: 'C',
    summary: 'Fast linear fit to verify each factor lands in a believable contribution and ROI range before full modeling.',
    how: 'A fast OLS fit checks each factor lands in a believable contribution and ROI range before the full Bayesian model is built.',
    basisNote: '行业弹性范围 + 业务校验假设。',
    workNote: 'Cooler contribution direction matches the 成都 pilot story. 社媒 elasticity within industry range. No red flags.',
    dependsOn: ['2.33'], duration: 2, produces: ['a-model-input'],
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
    dependsOn: ['3.2'], duration: 2, produces: ['a-tech-review'],
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
    dependsOn: ['3.4'], duration: 3, produces: ['a-decomp-results'],
  },
  {
    id: '4.1b', name: 'Write the narrative', agent: 'report', stage: 's5', class: 'A',
    summary: 'AI drafts the reading for every chart following the house style; reviewers polish.',
    how: 'AI drafts the reading for each chart in the house style (magnitude + share for every claim); reviewers polish the wording.',
    basisNote: '报告解读话术模板。',
    workNote: '"Trade 对生意增量占比最大，Media & Activation 增速最快" — narrative drafted per template with magnitude + share for every claim.',
    dependsOn: ['4.1a'], duration: 2, produces: ['a-final-report'],
  },
  {
    id: '4.1c', name: 'Review & deliver', agent: 'report', stage: 's5', class: 'H',
    summary: 'Final read-through, then deliver to the client.',
    how: 'You do a final read-through and release the report (and the modeling-config export) to the client.',
    workNote: 'Awaiting release decision.',
    dependsOn: ['4.1b'], duration: 1, produces: [],
    decision: {
      id: 'd-4.1', kind: 'approval', title: 'Release the final report',
      question: 'Release the report to the client? Every key business question should map to at least one chart.',
      evidence: [
        { artifactId: 'a-final-report' },
        { artifactId: 'a-kbq', note: 'Coverage check: 20/20 questions answered' },
      ],
      recommendation: 'Release. All 20 key business questions trace to evidence charts. Two known limitations are stated up front: 朗镜 门店执行 data covers 5 months only, and 批发渠道 attribution is approximate.',
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
