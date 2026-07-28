/**
 * Marketing-vertical industry taxonomy (L1 大行业 → L2 品类 → L3 子类).
 *
 * Tuned for consumer-marketing / MMM projects (the Danone Mizone case lands at
 * food-bev › beverage › sports-functional). Codes are stable slugs; labels are
 * the Chinese display names. This tree is mirrored on the backend at
 * backend/app/domain/industries.py — keep the two in sync (codes especially).
 */

export interface IndustryNode {
  code: string
  label: string
  children?: IndustryNode[]
}

/** A fully-qualified industry selection: three levels of codes. */
export interface IndustryRef {
  l1: string
  l2: string
  l3: string
}

export const INDUSTRY_TREE: IndustryNode[] = [
  {
    code: 'food-bev',
    label: '食品饮料',
    children: [
      {
        code: 'beverage',
        label: '饮料',
        children: [
          { code: 'sports-functional', label: '功能/运动饮料' },
          { code: 'packaged-water', label: '包装水' },
          { code: 'carbonated', label: '碳酸饮料' },
          { code: 'tea-drink', label: '茶饮料' },
          { code: 'juice', label: '果汁' },
          { code: 'rtd-coffee', label: '即饮咖啡' },
        ],
      },
      {
        code: 'dairy',
        label: '乳制品',
        children: [
          { code: 'ambient-milk', label: '常温奶' },
          { code: 'chilled-milk', label: '低温奶' },
          { code: 'yogurt', label: '酸奶' },
          { code: 'cheese', label: '奶酪' },
          { code: 'milk-powder', label: '奶粉' },
        ],
      },
      {
        code: 'snacks',
        label: '休闲零食',
        children: [
          { code: 'biscuit-pastry', label: '饼干糕点' },
          { code: 'candy-chocolate', label: '糖果巧克力' },
          { code: 'nuts', label: '坚果炒货' },
          { code: 'puffed', label: '膨化食品' },
        ],
      },
      {
        code: 'staple-instant',
        label: '调味速食',
        children: [
          { code: 'condiment', label: '调味品' },
          { code: 'instant-noodle', label: '方便面' },
          { code: 'frozen-food', label: '速冻食品' },
        ],
      },
      {
        code: 'alcohol',
        label: '酒类',
        children: [
          { code: 'baijiu', label: '白酒' },
          { code: 'beer', label: '啤酒' },
          { code: 'wine', label: '葡萄酒' },
        ],
      },
    ],
  },
  {
    code: 'beauty',
    label: '美妆个护',
    children: [
      {
        code: 'skincare',
        label: '护肤',
        children: [
          { code: 'facial-care', label: '面部护理' },
          { code: 'sunscreen', label: '防晒' },
          { code: 'mask', label: '面膜' },
          { code: 'body-care', label: '身体护理' },
        ],
      },
      {
        code: 'makeup',
        label: '彩妆',
        children: [
          { code: 'base-makeup', label: '底妆' },
          { code: 'lip-makeup', label: '唇妆' },
          { code: 'eye-makeup', label: '眼妆' },
        ],
      },
      {
        code: 'personal-care',
        label: '个人护理',
        children: [
          { code: 'hair-care', label: '洗护发' },
          { code: 'oral-care', label: '口腔护理' },
          { code: 'body-wash', label: '身体清洁' },
        ],
      },
      { code: 'fragrance', label: '香水', children: [{ code: 'perfume', label: '香水香氛' }] },
    ],
  },
  {
    code: 'mother-baby',
    label: '母婴',
    children: [
      { code: 'baby-food', label: '婴幼儿食品', children: [{ code: 'infant-formula', label: '婴配粉' }, { code: 'baby-snack', label: '婴幼儿辅食' }] },
      { code: 'diaper', label: '纸尿裤', children: [{ code: 'tape-diaper', label: '腰贴型' }, { code: 'pant-diaper', label: '拉拉裤' }] },
      { code: 'baby-care', label: '婴童洗护', children: [{ code: 'baby-wash', label: '婴童清洁' }, { code: 'baby-skincare', label: '婴童护肤' }] },
      { code: 'toy', label: '玩具', children: [{ code: 'educational-toy', label: '益智玩具' }, { code: 'figure-toy', label: '潮玩手办' }] },
    ],
  },
  {
    code: 'home-care',
    label: '家清家居',
    children: [
      { code: 'cleaning', label: '家庭清洁', children: [{ code: 'laundry', label: '衣物清洁' }, { code: 'dish-clean', label: '餐具清洁' }, { code: 'floor-clean', label: '地面清洁' }] },
      { code: 'paper', label: '纸品', children: [{ code: 'tissue', label: '生活用纸' }, { code: 'wet-wipe', label: '湿巾' }] },
      { code: 'home-goods', label: '家居用品', children: [{ code: 'kitchenware', label: '厨房用具' }, { code: 'storage', label: '收纳整理' }] },
    ],
  },
  {
    code: 'electronics',
    label: '3C数码',
    children: [
      { code: 'mobile', label: '手机通讯', children: [{ code: 'smartphone', label: '智能手机' }, { code: 'accessory', label: '手机配件' }] },
      { code: 'computer', label: '电脑办公', children: [{ code: 'laptop', label: '笔记本' }, { code: 'desktop', label: '台式整机' }, { code: 'peripheral', label: '外设' }] },
      { code: 'wearable', label: '智能穿戴', children: [{ code: 'smartwatch', label: '智能手表' }, { code: 'earbud', label: '耳机' }] },
      { code: 'av', label: '影音', children: [{ code: 'tv-projector', label: '电视投影' }, { code: 'camera', label: '相机' }] },
    ],
  },
  {
    code: 'appliance',
    label: '家电',
    children: [
      { code: 'large-appliance', label: '大家电', children: [{ code: 'fridge', label: '冰箱' }, { code: 'washer', label: '洗衣机' }, { code: 'air-conditioner', label: '空调' }] },
      { code: 'kitchen-appliance', label: '厨房电器', children: [{ code: 'range-hood', label: '油烟机' }, { code: 'small-kitchen', label: '小厨电' }] },
      { code: 'personal-appliance', label: '个护电器', children: [{ code: 'hair-dryer', label: '美发电器' }, { code: 'shaver', label: '剃须美容' }] },
      { code: 'env-appliance', label: '环境电器', children: [{ code: 'purifier', label: '净化器' }, { code: 'vacuum', label: '清洁电器' }] },
    ],
  },
  {
    code: 'apparel',
    label: '服饰箱包',
    children: [
      { code: 'clothing', label: '服装', children: [{ code: 'womenswear', label: '女装' }, { code: 'menswear', label: '男装' }, { code: 'underwear', label: '内衣' }] },
      { code: 'footwear', label: '鞋靴', children: [{ code: 'casual-shoe', label: '休闲鞋' }, { code: 'formal-shoe', label: '正装鞋' }] },
      { code: 'bag', label: '箱包', children: [{ code: 'handbag', label: '手袋' }, { code: 'luggage', label: '行李箱' }] },
      { code: 'sportswear', label: '运动户外', children: [{ code: 'sport-shoe', label: '运动鞋' }, { code: 'outdoor-gear', label: '户外装备' }] },
    ],
  },
  {
    code: 'auto',
    label: '汽车',
    children: [
      { code: 'passenger-car', label: '乘用车', children: [{ code: 'sedan', label: '轿车' }, { code: 'suv', label: 'SUV' }, { code: 'mpv', label: 'MPV' }] },
      { code: 'nev', label: '新能源车', children: [{ code: 'bev', label: '纯电动' }, { code: 'phev', label: '插电混动' }] },
      { code: 'aftermarket', label: '汽车后市场', children: [{ code: 'maintenance', label: '维修保养' }, { code: 'car-accessory', label: '汽车用品' }] },
    ],
  },
  {
    code: 'health',
    label: '医药健康',
    children: [
      { code: 'otc', label: 'OTC药品', children: [{ code: 'cold-med', label: '感冒用药' }, { code: 'digestive-med', label: '肠胃用药' }] },
      { code: 'supplement', label: '保健品', children: [{ code: 'vitamin', label: '维生素' }, { code: 'tonic', label: '滋补营养' }] },
      { code: 'medical-device', label: '医疗器械', children: [{ code: 'home-device', label: '家用器械' }, { code: 'pro-device', label: '专业器械' }] },
      { code: 'health-service', label: '健康服务', children: [{ code: 'clinic', label: '医疗机构' }, { code: 'physical-exam', label: '体检' }] },
    ],
  },
  {
    code: 'finance',
    label: '金融',
    children: [
      { code: 'bank', label: '银行', children: [{ code: 'retail-bank', label: '零售银行' }, { code: 'credit-card', label: '信用卡' }] },
      { code: 'insurance', label: '保险', children: [{ code: 'life-insurance', label: '寿险' }, { code: 'property-insurance', label: '财产险' }] },
      { code: 'securities', label: '证券基金', children: [{ code: 'brokerage', label: '券商' }, { code: 'fund', label: '基金' }] },
      { code: 'fintech', label: '互联网金融', children: [{ code: 'payment', label: '第三方支付' }, { code: 'consumer-finance', label: '消费金融' }] },
    ],
  },
  {
    code: 'internet',
    label: '互联网科技',
    children: [
      { code: 'ecommerce', label: '电商平台', children: [{ code: 'marketplace', label: '综合电商' }, { code: 'vertical-ecom', label: '垂直电商' }] },
      { code: 'gaming', label: '游戏', children: [{ code: 'mobile-game', label: '手游' }, { code: 'pc-console-game', label: '端游主机' }] },
      { code: 'video', label: '在线视频', children: [{ code: 'long-video', label: '长视频' }, { code: 'short-video', label: '短视频' }] },
      { code: 'social', label: '社交', children: [{ code: 'social-network', label: '社交网络' }, { code: 'dating', label: '婚恋交友' }] },
      { code: 'tool-app', label: '工具应用', children: [{ code: 'productivity', label: '效率工具' }, { code: 'utility', label: '生活工具' }] },
    ],
  },
  {
    code: 'education',
    label: '教育',
    children: [
      { code: 'k12', label: 'K12', children: [{ code: 'after-school', label: '课后辅导' }, { code: 'edu-hardware', label: '教育硬件' }] },
      { code: 'higher-voc', label: '高等职业', children: [{ code: 'vocational', label: '职业培训' }, { code: 'exam-prep', label: '考研考证' }] },
      { code: 'language', label: '语言培训', children: [{ code: 'english', label: '英语' }, { code: 'other-language', label: '小语种' }] },
      { code: 'quality-edu', label: '素质教育', children: [{ code: 'arts', label: '艺术' }, { code: 'sports-edu', label: '体育' }] },
    ],
  },
  {
    code: 'travel',
    label: '旅游出行',
    children: [
      { code: 'ota', label: 'OTA', children: [{ code: 'flight-booking', label: '机票预订' }, { code: 'hotel-booking', label: '酒店预订' }] },
      { code: 'airline', label: '航空', children: [{ code: 'full-service', label: '全服务航司' }, { code: 'low-cost', label: '低成本航司' }] },
      { code: 'hotel', label: '酒店', children: [{ code: 'luxury-hotel', label: '高端酒店' }, { code: 'economy-hotel', label: '经济酒店' }] },
      { code: 'local-mobility', label: '本地出行', children: [{ code: 'ride-hailing', label: '网约车' }, { code: 'shared-mobility', label: '共享出行' }] },
    ],
  },
]

/** Top-level (L1) options. */
export function l1Options(): IndustryNode[] {
  return INDUSTRY_TREE
}

/** L2 options under an L1 code (empty if unknown). */
export function l2Options(l1: string): IndustryNode[] {
  return INDUSTRY_TREE.find((n) => n.code === l1)?.children ?? []
}

/** L3 options under an L1/L2 pair (empty if unknown). */
export function l3Options(l1: string, l2: string): IndustryNode[] {
  return l2Options(l1).find((n) => n.code === l2)?.children ?? []
}

/** Resolve a ref to its three display labels, or null if any level is invalid. */
export function industryLabels(ref: IndustryRef | null | undefined): [string, string, string] | null {
  if (!ref) return null
  const n1 = INDUSTRY_TREE.find((n) => n.code === ref.l1)
  const n2 = n1?.children?.find((n) => n.code === ref.l2)
  const n3 = n2?.children?.find((n) => n.code === ref.l3)
  if (!n1 || !n2 || !n3) return null
  return [n1.label, n2.label, n3.label]
}

/** Human-readable breadcrumb, e.g. "食品饮料 › 饮料 › 功能/运动饮料". */
export function industryPath(ref: IndustryRef | null | undefined, sep = ' › '): string {
  const labels = industryLabels(ref)
  return labels ? labels.join(sep) : '—'
}

/** True when the ref is a complete, valid L1/L2/L3 path. */
export function isValidIndustry(ref: Partial<IndustryRef> | null | undefined): ref is IndustryRef {
  if (!ref?.l1 || !ref.l2 || !ref.l3) return false
  return industryLabels(ref as IndustryRef) !== null
}
