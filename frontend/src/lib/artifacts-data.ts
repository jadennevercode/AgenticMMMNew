import type { ArtifactBlueprint } from './types'

/**
 * Artifact blueprints — names in English (product language),
 * bodies in Chinese where they carry client/business content.
 * Content condensed from the project reference pack (Danone Mizone POC).
 */
export const ARTIFACTS: ArtifactBlueprint[] = [
  /* ── S1 · Business Understanding (MMM-Study flow) ──────── */
  {
    id: 'a-sow', name: 'SOW & Brief (provided)', taskRef: '1.0a', type: 'document', stage: 's1', lineage: [],
    content: `# SOW 与项目简报（人工提供）
- 文件：Danone_Mizone_MMM_SOW_signed.pdf · Kickoff_brief_20251118.pptx
- 渠道范围：MT / TT / AFH / EC+O2O
- 产品：除脉动电解质外所有（为一组）
- KPI：Sell-out Volume · 窗口 2022-10 至 2025-10 · 月度`,
  },
  {
    id: 'a-scope', name: 'Scope & KBQ Card', taskRef: '1.0', type: 'document', stage: 's1', lineage: ['a-sow'],
    content: `# 项目作用域卡片（依据 SOW）
## 范围硬约束
- 渠道 ≤4：MT（现代商超）/ TT（传统流通）/ AFH（新兴渠道）/ EC+O2O
- 地区和平台 ≤6 组（线下按省份分组，线上按平台）
- 产品：除脉动电解质外所有（为一组）
## 颗粒度
- 时间：月度 · 2022-10 至 2025-10 · KPI：Sell-out Volume
## 适用知识范围
- 行业通识：饮料/功能饮料包 · 历史项目：暂无同品类可复用`,
  },
  {
    id: 'a-kbq', name: 'Key Business Questions', taskRef: '1.0', type: 'document', stage: 's1', lineage: ['a-scope'],
    content: `# 关键业务问题（结构化，节选自 20 条）
- A7 如何量化媒体投放与店内投入分别对生意的贡献？（Marketing）
- A8 门店执行三维度（Availability/Visibility/Impact）对销售的影响？（Marketing）
- A11 Control 门店及 A&P 投资如何影响 Uncontrol 门店——辐射效应？（Finance）
- A13 资源有限时优先聚焦哪些场景/区域/场所？（Sales）
- A19 站外投放对电商站内的实际影响？（EC）
## 声明
- 此为 typical 问题列表 for reference，访谈中可调整`,
  },
  {
    id: 'a-source-materials', name: 'Reports & Materials (provided)', taskRef: '1.1a', type: 'document', stage: 's1', lineage: ['a-scope'],
    content: `# 品牌报告与内部资料（人工提供）
- 文件：202408_Competitor_Benchmark_CICC.pdf（密码 aurora）· Mizone_brand_review_2025.pptx · Internal_channel_strategy.pdf
- 用途：知识装配阶段被 AI 抽取为知识条目
- 要点：农夫山泉终端优先模式；东鹏 value-for-money + 五码合一`,
  },
  {
    id: 'a-minutes-raw', name: 'Interview Minutes (provided)', taskRef: '1.1b', type: 'document', stage: 's1', lineage: ['a-scope'],
    content: `# 访谈纪要原件（人工提供，11 场）
- Layer 1 GM · Layer 2 Mkt/Sales/Finance · Layer 3 Media/Activation/EC/KA/Trade/Execution/SIA/O2O
- 共 11 份 docx，覆盖战略、业务细节与数据明细
- 进入知识装配阶段被结构化为知识条目`,
  },
  {
    id: 'a-knowledge-package', name: 'Project Knowledge Package', taskRef: '1.1', type: 'master-data', stage: 's1', lineage: ['a-source-materials', 'a-minutes-raw', 'a-scope'],
    content: `# 本项目知识包（结构化条目）
## 行业通识条目（继承自饮料包）
- 品类天花板约 300–400 亿，Q2-Q3 旺季；健康化无糖增速 >20%
## 客户特定条目（来源/置信度/适用范围）
- GM：外卖与现调饮品挤占 Share of Throat（高 · 全品类）
- Marketing：媒体 vs 终端执行相对贡献是核心命题（高 · 本品）
- Finance：Control 店约 55% 销售占比（中 · 本品）
- Sales 执行：批发实际约 50%，系统显示 20–30%，建议批发并入 TT（中 · 渠道）
## 冲突与缺口
- ⚠ 冲突：内部"品牌投放过多应转线下" vs C/D/rural 无可控抓手依赖品牌拉力
- ◌ 缺口：朗镜门店执行仅 5 个月，无法支撑月度建模`,
  },
  {
    id: 'a-factor-tree', name: 'Factor Tree (L1–L4)', taskRef: '1.21', type: 'master-data', stage: 's1', lineage: ['a-knowledge-package'],
    content: `# 生意因子结构树（每节点附推导依据）
## L1 生意基本盘（锁定 L2）
- 外部因素：品类趋势 · 宏观环境 · 竞争格局
- 内部因素：动销（品牌资产/价格/产品吸引力）· 复购粘性
## L1 消费者需求驱动
- 品牌广告/内容种草：品牌传播（TV/OTV/OTT/OOH/Digital）· 社媒及线下路演 · 自有媒体
- 电商平台媒体及促销：站内投流 · 电商买赠
## L1 渠道成交驱动
- 渠道执行 · 渠道/终端营销（POSM/店内促销/冰柜）· 铺货（ND/WD/SOS）
## L1 促销优惠
- 促销优惠（花费 / PPI）
## 访谈驱动的待确认改动（3 处）
- + 结构性突变因素 → 外卖大战时间点（来源：GM 访谈）
- + 特定属性趋势 → 现调饮料外卖销量（来源：GM 访谈）
- ~ 批发并入 TT 渠道组（来源：Sales 执行访谈）
## 治理
- L1/L2 锁定；L3/L4 允许 10–20% 增删，需确认并留痕`,
  },
  {
    id: 'a-indicator-candidates', name: 'Indicator Candidates', taskRef: '1.22', type: 'master-data', stage: 's1', lineage: ['a-factor-tree'],
    content: `# 指标候选矩阵（每个 L4 给 3–5 个候选 + 三维打分）
## 示例：铺货
- 本品 WD ★ 消费者相关 高 / 变异性 中 / 可执行 高 — 比 ND 更反映质量
- 本品 ND   消费者相关 中 / 变异性 中 / 可执行 高
- 货架份额(SOS) 消费者相关 高 / 变异性 中 / 可执行 中
## 示例：品牌传播
- 曝光量(impression) ★ vs 花费(spend) — 有曝光优先曝光，建模用曝光
## 示例：冰柜
- 已投放冰柜个数 ★ / 花费（与陈列架共线性偏高，标注）`,
  },
  {
    id: 'a-indicator-list', name: 'Indicator List', taskRef: '1.22d', type: 'master-data', stage: 's1', lineage: ['a-indicator-candidates'],
    content: `# 入选指标清单（因子 ↔ 主指标 ↔ 备选 ↔ 颗粒度）
- 铺货 → 主：本品 WD（备：ND）· by channel/region
- 品牌传播 → 主：impression（备：spend）· by region/format/campaign
- 冰柜 → 主：已投放冰柜个数 · by region
- 市场规模 → 主：品类全渠道销量 · by category/channel
## 选用理由
- 跟随三维最高分；与下游建模颗粒度匹配`,
  },
  {
    id: 'a-data-request', name: 'Data Request Package', taskRef: '1.23', type: 'document', stage: 's1', lineage: ['a-indicator-list', 'a-factor-tree'], exportable: true,
    content: `# 数据需求包（可导出模板，12 份）
- 结构：以 L3 为表、L4 为 sheet、指标颗粒度+指标为列
- 模板：Media / Store Execution / BHT / Macroeconomics / 竞品RSP / Omni-channel / Mkt Activation Buzz / 线条饮料 …
- 每个模板声明 Time Coverage（2022/10–2025/10）与 Brand Coverage
- 按 owner 团队打包导出（Media / Sales+Trade / SIA / EC+O2O）`,
  },

  /* ── S2 ─────────────────────────────────────────────── */
  {
    id: 'a-data-files', name: 'Collected Client Data (provided)', taskRef: '2.0a', type: 'dataset', stage: 's2', lineage: ['a-data-request'],
    content: `# 客户回填数据（人工提供）
- 来源团队：Media / Sales / Trade / SIA / EC / O2O · 共 37 个数据任务
- 文件示例：Media_spend_impression.xlsx · Nielsen_offtake.xlsx · Store_execution.xlsx
- 时间窗口：2022-10 至 2025-10（部分指标覆盖不全，待打分）`,
  },
  {
    id: 'a-quality-scorecard', name: 'Data Quality Scorecard', taskRef: '2.11', type: 'scorecard', stage: 's2', lineage: ['a-data-files'],
    content: `# 数据质量评分（86 项指标）
## 规则
- 一致性 / 准确性 / 完整性 / 颗粒度 · 每项 0 / 0.5 / 1
- 1 = 验收；0.5 = 需人决策；0 = 弃用并预警
## 结果
- 79 项通过 · 4 项 0.5 分 · 3 项 0 分
## 0.5 分项
- UTC 扫码瓶数（仅 2025-07 起）· 微信立减（各年不全）· 冰柜个数（年度拆月）· BHT（月度断档）
## 0 分项（预警）
- 朗镜门店执行（仅 5 个月）· 竞品冰柜渗透率（无监测）· 复购率（无连续数据）`,
  },
  {
    id: 'a-client-qa', name: 'Client Q&A Tracker', taskRef: '2.11', type: 'workflow', stage: 's2', lineage: ['a-data-request'],
    content: `# 数据&指标沟通表（节选）
- Q: WD 按什么逻辑加权？ → A: 以门店 NAB 销售额作为权重（已回）
- Q: Nielsen RSP 是否含促销折扣？ → A: 取决于折扣是否进 POS 小票（已回）
- Q: 批发能否拆分 AFH/TT/EC 批发？ → A: 26 年起才可分；建议批发与 TT 合并（已回）
- Q: UTC 扫码是否有 2025-07 前的历史数据？ → A: 无（已回）`,
  },
  {
    id: 'a-data-dictionary', name: 'Data Dictionary', taskRef: '2.22', type: 'document', stage: 's2', lineage: ['a-quality-scorecard'],
    content: `# 数据字典（ODS→DW，37 个数据任务）
- 每张源表登记：来源系统 / 颗粒度 / 服务的 L4 因子 / 处理逻辑 / 时间范围 / X 或 Y
- 列级逻辑四类：常量 · 主数据映射 · 转换 · 计算
- 例：PPI = Σ促销零售价 ÷ Σ原零售价（按渠道）
- 两人互检记录：Task10 / Task29 已复核`,
  },
  {
    id: 'a-dataset', name: 'Master Dataset', taskRef: '2.24', type: 'dataset', stage: 's2', lineage: ['a-data-dictionary'],
    content: `# 统一长表数据集
- 23,791 行 · 品牌 × 省份组别 × 渠道 × 年月 × 因子层级（L1–L8）× 指标 × 值
- 主数据清洗：Product / Geo / Channel / Time 四张映射表
- 覆盖：2022-10 至 2025-10 · 月度`,
  },

  /* ── S3 ─────────────────────────────────────────────── */
  {
    id: 'a-trend-review', name: 'Data Review Deck', taskRef: '2.31', type: 'report', stage: 's3', lineage: ['a-dataset'],
    content: `# 趋势解读（客户 Review 材料）
## 全景
- 整体销量 3 年趋势健康；O2O 2025 增速 +80%（上年 +36%）— 异常定位
## 假设
- 外卖平台大战显著放大 O2O 流量（高置信）— 与 GM 访谈一致 → 建议设结构性事件标记
## 待客户核对（3 条）
- O2O 增长中平台补贴占比 · MT 价格战对 RSP 的影响节点 · AFH 批发误差容忍度
## Sign-off
- 每页 Y/N 栏，未签核数据不入模`,
  },
  {
    id: 'a-stat-tests', name: 'Statistical Screening Results', taskRef: '2.33', type: 'scorecard', stage: 's3', lineage: ['a-dataset', 'a-trend-review'],
    content: `# 统计检验（波动性 / 相关性 / 共线性）
- 总分 ≥3 Good · 1.5–3 需确认 · <1.5 不入模
## 关键结论
- GDP、消费者信心指数与 NAB 品类趋势强共线 → 剔除（品类趋势已反映）
- 冰柜个数 × 陈列架数量 共线性偏高 → 入模时关注
- 温度、品类销量、ND/WD、社媒声量均 Good`,
  },
  {
    id: 'a-model-input', name: 'Model Input', taskRef: '2.34', type: 'dataset', stage: 's3', lineage: ['a-dataset', 'a-stat-tests'],
    content: `# 模型输入（按模型对象拆分）
- 4 个模型对象：MT / TT(含批发) / AFH / EC+O2O · 各一份输入矩阵
- 行=月份 · 列=KPI + 入选变量（含变量-因子映射清单）
- 预检：各因子贡献方向与 ROI 范围落在业务可信区间，无红旗`,
  },

  /* ── S4 ─────────────────────────────────────────────── */
  {
    id: 'a-prior-register', name: 'Assumption Register', taskRef: '3.1', type: 'document', stage: 's4', lineage: ['a-knowledge-package', 'a-trend-review', 'a-model-input'],
    content: `# 模型假设登记（6 条，均有确认来源）
- 外卖大战时间段设结构性事件标记 · 来源：GM 访谈 + 趋势异常（已核对）
- 竞品项方向为负 · 来源：竞争格局共识
- 冰柜效应为正且有饱和上限 · 来源：成都试点（覆盖 35%→55%，增速 16% vs 全国 7%）— 标注为较软约束
- 社媒声量领先销量 1–2 个月 · 来源：行业经验 + 数据相关性
- 促销存在边际递减 · 来源：行业通识
- 基线必须为正 · 来源：业务常识（违反即停）`,
  },
  {
    id: 'a-model-candidates', name: 'Model Candidates', taskRef: '3.2', type: 'model', stage: 's4', lineage: ['a-model-input', 'a-prior-register'],
    content: `# 候选模型（每个模型对象保留 3 个，AFH 示例）
- Candidate A：R² 0.96 · 误差 7% · 基线 41%（低于业务底线 45%）
- Candidate B：R² 0.95 · 误差 8% · 基线 47% · 全部约束满足 · 冰柜效应≈成都试点
- Candidate C：R² 0.93 · 误差 9% · Media 贡献占比明显高于其花费占比
- 采样收敛：全部通过`,
  },
  {
    id: 'a-tech-review', name: 'Technical Review', taskRef: '3.3', type: 'report', stage: 's4', lineage: ['a-model-candidates'],
    content: `# 技术检验（AFH · Candidate B）
- R² 0.95（基准 85–95%）✓ · 平均误差 8%（基准 5–15%）✓ · 残差自相关低 ✓
- 无负基线 · 无反向系数 — 红旗检查通过
## 拟合解读
- 误差 >20% 节点：2024-01（春节备货低估）— 已通过季节项缓解
- 连续偏差段：无
## 结论
- 候选 B 技术合格；A 基线偏低需例外说明；C 归因结构存疑`,
  },

  /* ── S5 ─────────────────────────────────────────────── */
  {
    id: 'a-decomp-results', name: 'Results & Chart Book', taskRef: '4.1a', type: 'report', stage: 's5', lineage: ['a-tech-review'],
    content: `# 结果图册（AFH 节选）
## Part 0 生意基本面
- AFH 销量连续两年强劲增长（2024 +31%，2025YTD +35%）
## Part 1 贡献拆解
- Baseline 占比 23 年 68% → 25YTD 43%；Marketing & Trade 25YTD 贡献过半（53%）
- 下钻：Trade 贡献最大（冰柜为主引擎）；Media & Activation 增速最快（9%→14%）
## 增长归因
- 增长部分主要由 Marketing & Trade 拉动；Commercial 执行因素影响微小且稳定`,
  },
  {
    id: 'a-final-report', name: 'Final Report', taskRef: '4.1b', type: 'report', stage: 's5', lineage: ['a-decomp-results', 'a-kbq'],
    content: `# 最终报告（草稿）
## 结构
- 技术检查 → 生意基本面 → 贡献/增长/效率三视角 → 渠道间对比 → 关键业务问题逐条回应
## 话术风格
- 每个结论同时给量级与占比；ROI 结论附"不可线性外推"提示
## 已知局限（明示）
- 朗镜门店执行数据仅 5 个月 · 批发渠道归因为近似处理`,
  },
]

export const ARTIFACT_MAP = new Map(ARTIFACTS.map((a) => [a.id, a]))
