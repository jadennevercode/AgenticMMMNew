/**
 * Knowledge base seed data (tasks 1.4 / 1.5, docs 08 §8 + 00 §8).
 * Two zones: a reusable Solution library and per-project customizations,
 * plus a change ledger that records every factor/metric add/remove with reason.
 * UI labels English; business content Chinese.
 */

export interface IndustryPack {
  id: string
  name: string
  version: string
  l1l2Locked: number
  l3l4Count: number
  metricCount: number
  active: boolean
}

export const INDUSTRY_PACKS: IndustryPack[] = [
  { id: 'beverage', name: '饮料 / 功能饮料 (Beverage)', version: 'v2.3', l1l2Locked: 12, l3l4Count: 38, metricCount: 93, active: true },
  { id: 'nutrition', name: '医学营养 (Medical Nutrition)', version: 'v1.4', l1l2Locked: 12, l3l4Count: 31, metricCount: 74, active: false },
]

/** The factor tree the active pack recalls — L1/L2 locked, L3/L4 with source */
export interface FactorNode {
  l1: string
  l2: string
  l3: string
  source: 'pack' | 'interview' | 'report' | 'ai'
  locked?: boolean
}

export const FACTOR_TREE: FactorNode[] = [
  { l1: '生意基本盘', l2: '外部因素', l3: '品类趋势（市场规模/季节性/场景化）', source: 'pack', locked: true },
  { l1: '生意基本盘', l2: '外部因素', l3: '宏观环境（经济周期/渠道变迁）', source: 'pack', locked: true },
  { l1: '生意基本盘', l2: '外部因素', l3: '竞争格局（价格/产品/渠道扩张）', source: 'pack', locked: true },
  { l1: '生意基本盘', l2: '外部因素', l3: '特定属性趋势 → 现调饮料外卖销量', source: 'interview' },
  { l1: '生意基本盘', l2: '外部因素', l3: '结构性突变因素 → 外卖大战时间点', source: 'interview' },
  { l1: '生意基本盘', l2: '内部因素', l3: '动销（品牌资产/价格/产品吸引力）', source: 'pack', locked: true },
  { l1: '生意基本盘', l2: '内部因素', l3: '复购粘性', source: 'pack', locked: true },
  { l1: '消费者需求驱动', l2: '品牌广告/内容种草', l3: '品牌传播（TV/OTV/OTT/OOH/Digital）', source: 'pack', locked: true },
  { l1: '消费者需求驱动', l2: '品牌广告/内容种草', l3: '社交媒体及线下路演', source: 'pack', locked: true },
  { l1: '消费者需求驱动', l2: '品牌广告/内容种草', l3: '自有媒体（会员/社群/开盖有奖）', source: 'pack' },
  { l1: '消费者需求驱动', l2: '电商平台媒体及促销', l3: '电商站内投流 · 电商买赠', source: 'pack', locked: true },
  { l1: '渠道成交驱动', l2: '渠道执行', l3: '产品全 / 数量多 / 位置好', source: 'pack', locked: true },
  { l1: '渠道成交驱动', l2: '渠道/终端营销', l3: 'POSM · 店内促销 · 冰柜', source: 'pack', locked: true },
  { l1: '渠道成交驱动', l2: '铺货', l3: 'ND / WD / 货架份额（SOS）', source: 'pack', locked: true },
  { l1: '促销优惠', l2: '促销优惠', l3: '促销优惠（花费 / PPI）', source: 'pack', locked: true },
]

/** Change ledger — the 留痕 record. Seeded; appends when a change is accepted. */
export interface LedgerEntry {
  id: string
  action: 'add' | 'remove' | 'merge'
  target: string
  reason: string
  source: 'interview' | 'report' | 'ai' | 'stats'
  confirmedBy: string
  /** Day index, or undefined for pre-seeded */
  day?: number
}

export const SEED_LEDGER: LedgerEntry[] = [
  { id: 'l-seed-1', action: 'remove', target: 'GDP / 消费者信心指数', reason: '与 NAB 品类趋势强共线，品类趋势已承载宏观信号', source: 'stats', confirmedBy: 'DS' },
]

/** Proposal id → ledger entry produced when accepted (wires workflow → knowledge) */
export const PROPOSAL_LEDGER: Record<string, Omit<LedgerEntry, 'id' | 'day'>> = {
  'p-factor-updates': {
    action: 'add',
    target: '外卖大战时间点 · 现调饮料外卖销量；批发并入 TT',
    reason: 'GM 访谈：外卖与现调饮品挤占 Share of Throat；Sales 执行：26 年前批发不可拆',
    source: 'interview',
    confirmedBy: 'BA',
  },
  'p-drop-macro': {
    action: 'remove',
    target: 'GDP · 消费者信心指数',
    reason: '统计检验显示与品类趋势强共线，避免重复计算',
    source: 'stats',
    confirmedBy: 'DS',
  },
  'p-merge-cooler': {
    action: 'merge',
    target: '冰柜个数 + 陈列架数量 → 终端冷柜与陈列资产',
    reason: '两者共线性偏高，合并避免归因不稳',
    source: 'stats',
    confirmedBy: 'DS',
  },
}

/** Reusable assets in the cross-project Solution zone */
export interface SolutionAsset {
  id: string
  kind: 'rule' | 'template'
  name: string
  detail: string
}

export const SOLUTION_LIBRARY: SolutionAsset[] = [
  { id: 's-quality', kind: 'rule', name: 'Data quality scoring rules', detail: '一致性/准确性/完整性/颗粒度 · 0/0.5/1 三态打分' },
  { id: 's-stat', kind: 'rule', name: 'Statistical screening rules', detail: 'CV · Pearson · VIF 组合打分，≥3 Good / <1.5 剔除' },
  { id: 's-tech', kind: 'rule', name: 'Technical review benchmarks', detail: 'R² 85–95% · MAPE 5–15% · DW 1.5–2.5 · 红旗规则' },
  { id: 's-narrative', kind: 'template', name: 'Report narrative style', detail: '每个结论同时给量级与占比；ROI 附"不可线性外推"' },
  { id: 's-chart', kind: 'template', name: 'Chart book skeleton', detail: 'Part 0 基本面 → Part 1 全国 → Part 2 区域' },
  { id: 's-interview', kind: 'template', name: 'Layered interview framework', detail: 'Layer 1/2/3 × 三段式问题（现状/期望/数据）' },
]

/** Project customizations that could be promoted into the Solution zone at wrap-up */
export interface ReflowCandidate {
  id: string
  name: string
  detail: string
}

export const REFLOW_CANDIDATES: ReflowCandidate[] = [
  { id: 'r-throat', name: '"Share of Throat" 跨品类挤压因子', detail: '现调饮料外卖销量作为饮料品类的外部竞争因子 — 可沉淀进饮料包' },
  { id: 'r-wholesale', name: '批发并入 TT 的渠道规则', detail: '批发数据不可拆时并入 TT，避免稀释 AFH 投资有效性 — 通用渠道规则' },
  { id: 'r-cooler', name: '冰柜 × 陈列架合并变量', detail: '终端冷柜与陈列资产高共线时合并 — 可沉淀进统计处理规则库' },
]
