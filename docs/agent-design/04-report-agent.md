# 报告智能体（Report Agent，任务编号 4.x）

> 源材料：`reference/04.报告智能体/5D.模型解读内容细化需求.xlsx`（模型结果解读需求 + AFH/TT/MT_Charting 三份实例 + Decomp CHART + 技术检验）。

## 1. 定位

把模型智能体输出的结果长表，转化为**客户可消费的标准报告与交互问答**。生成范式固定为：

> **模板化图表 + 图上方的解读模板 → AI 生成话术 → 结合商业逻辑补充**

5D 文档对每个标准产出都标注同一句要求："并根据我们在图上方的解读总结解读数据的话术及方式，且需要 AI 结合商业逻辑进行补充" —— 即每张图都是 `数据 + 解读模板 + LLM 商业语境化` 的三层结构。

StatusCheckList 定义（4.1）：总结结果生成报表及洞察 = **标准模板 + 交互问答**。

## 2. 前置数据准备（解读需求"总结结果"四步）

1. 建**因素 mapping 表**：模型 variable → Group1–6 分组（报告的因素层级，与因子树 L1–L4 映射但按报告口径重组，如 Group1=Baseline/Commercial/Marketing&Trade，Group3/4 为下钻层）；
2. 建**时间维度 mapping 表**：需分析的时间维度（年度 / YTD / 同期对照，如 2023、2024、2024YTD10、2025YTD10）；
3. 建**模型对象 mapping 表**：需分析的模型对象（渠道 × 区域，如 AFH/TT/MT × National）；
4. 建**长表**：各时间维度 × 各模型对象 × 各因素层级的全量指标。

## 3. 标准度量体系（10 个概念定义）

| # | 概念 | 定义 | 业务意义（"回答什么"） |
|---|---|---|---|
| 1 | Volume Contribution | 该渠道/变量直接驱动的销量绝对量（件数） | "这个渠道带来了多少销量"——预算分配基础 |
| 2 | Unit Price | 模型期内均价 = Actual Revenue / Actual Volume | 销量→金额的转换系数 |
| 3 | Value Contribution | = Volume Contribution × Unit Price | "带来了多少销售额"——与财务/销售对齐口径 |
| 4 | Spend | 渠道投入金额 | "花了多少钱"——ROI 分母、预算约束 |
| 5 | Support | 渠道投入量（源数据，如曝光/GRP） | "消费者感知到的投放有多少" |
| 6 | Effectiveness | 单位投放产生的 Volume / Support | "每一个曝光有多少效果"——与成本无关的转化能力 |
| 7 | Efficiency / ROI | = Value Contribution ÷ Spend | "每花 1 块钱回来多少钱"——需结合边际递减，不可线性外推 |
| 8 | Unit Cost | = Spend ÷ 执行指标（曝光/点击/流量） | "触达 1 个消费者花多少钱"——拆解 ROI 变化原因 |
| 9 | Spend% | 渠道花费占总花费比例 | "预算怎么分的"——与 Contribution% 对照找浪费 |
| 10 | Volume Contribution% | 占总销量比例 | "销量怎么构成的"——Base vs Incremental，品牌健康度 |

所有度量的维度统一为：**各时间维度 × 各模型对象 × 各因素层级**。

## 4. 标准报告产出清单

### 4.1 技术检查（编号 1.1–1.6，引用 Tech Review）

| 编号 | 检查 | 内容 | 图表来源 |
|---|---|---|---|
| 1.1 | Actual vs Predicted Chart | 实际 vs 拟合趋势对比；大促/特殊事件期间系统性偏差提示遗漏变量 | 技术检验 sheet |
| 1.2 | R² | 0.6–0.8 良好；过高需查过拟合 | 技术检验 |
| 1.3 | MAPE | 10–20% 可接受；MMM 核心是归因非预测 | 技术检验 |
| 1.4 | DW | 偏离 2 → 遗漏延续性变量，系数有偏 | 技术检验 |
| 1.5 | Negative Base | **核心警报**：必须修复后才能使用模型结果 | Decomp CHART |
| 1.6 | Negative Coeff | **业务红旗**：排查混淆变量/反向因果/口径 | Decomp CHART |

### 4.2 统计检查（编号 2）

Sales（数值+change%）vs Spend（数值+change%）总览 → 理解生意总体趋势（对应 Charting Part 0 生意基本面）。

### 4.3 结果检查（编号 2.1–2.5）

| 编号 | 图表 | 内容 | 业务问题 |
|---|---|---|---|
| 2.1 | Decomposition Chart | 销量 = Base + 各渠道贡献 + 其他因素 的堆叠图 | "销量从哪来"——管理层最关注 |
| 2.2 | Contribution + Contribution% | 各渠道绝对贡献与占比；结合 Spend% 找"低贡献高花费" | "谁贡献了大头" |
| 2.3 | Due-to Chart | 相比基准期的销量变化拆解（各渠道Δ + BaseΔ + 其他Δ） | "销量变化是因为谁"——归因的动态版本 |
| 2.4 | ROI Chart | 各渠道 ROI 柱状 + 行业基准线；强调上层渠道 ROI 天然偏低但有价值、需结合边际递减 | "钱花得值不值" |
| 2.5 | Effectiveness + Unit Cost 表格 | ROI 变化的归因四象限：效果↑成本↓→可加投；效果↓成本↑→优化素材/谈判价格；效果不变成本↑→外部（媒体涨价）；效果↓成本不变→内部（素材疲劳/人群耗尽） | "ROI 变化的原因是什么" |

### 4.4 对比检查（编号 3.1–3.3）

| 编号 | 对比维度 | 业务问题 |
|---|---|---|
| 3.1 | 产品间 | "不同产品应该怎么差异化投"——识别产品×渠道最佳匹配 |
| 3.2 | 销售渠道间 | "货在不同地方卖，营销打法要变吗"——渠道专属媒介策略 |
| 3.3 | 区域间 | "钱在不同地区怎么分"——一线饱和 vs 下沉红利，因地制宜 |

## 5. Charting 报告结构（AFH/TT/MT 实例的固定骨架）

每个模型对象（渠道）一份，头部声明 `Channel / Segmented Market / Version Updated Time`：

```
Part 0  生意基本面
        —— 销量与增速总览（"AFH 整体销量连续两年强劲增长，24 同比+31%，25YTD10 同比+35%"）
Part 1  全国性总结
  一. 销量的贡献拆解（Contribution & Contribution%）
      [整体] Group1 层：Baseline / Commercial / Marketing&Trade 三大因素
      [下钻] Group3/4 层：Trade、Media & Activation、EC+O2O+社团 → Cooler、Media、
             Social&Activation、Brand Visible、Consumer Promotion、Traffic Buying
  二. 销量增长的贡献拆解（Due-to）
      [整体] 三大因素对"增长部分"的贡献与趋势
      [下钻] 同上层级展开 + Commercial 执行因素细查（如 Must-distribute SKU 负向影响）
  三. 投资效率分析（ROI / SalesVal / Spend，仅投资类因素）
Part 2  分区域洞察分享（区域间对比）
```

数据矩阵的固定列组：`Sales Volume Contribution | Contribution% | Due-to（量与%） | ROI | SalesVal | Spend` × 时间维度（2023 / 2024 / 2024YTD10 / 2025YTD10 / 24 DUE-TO / 25YTD DUE-TO），含 `Unexplained`（误差项）显式呈现。

**解读话术的固定句式**（从实例归纳，可模板化）：

- 结构句：`[整体/下钻] <因素> 是 <对象> 生意"增长部分"的主要因素（但出现了下滑/呈增长趋势）`；
- 论据句：编号列举 `1）…占比 X%（时间A）vs Y%（时间B）；2）…`，数字必须同时给"量级"与"占比/增速"；
- 下钻句：`下钻至 <Group>，<子因素> 是贡献最大的增长引擎，其他因素相对稳定`。

## 6. 交互问答（4.1 后半）

标准模板之外，报告智能体支持基于结果长表 + KBQ 的交互问答：

- 输入域：因素 mapping / 时间 mapping / 模型对象 mapping 约束下的结果长表 + Tech Review + 因子树 + KBQ；
- 回答规范：复用 §3 概念定义与 §5 话术句式；涉及技术指标时使用 3.3 标准话术；ROI 类回答必须附"不可线性外推、需结合边际递减"提示；
- KBQ 回链：每条 KBQ（A1–A24 类）应能映射到至少一张标准图表作为证据。

## 7. 能力（工具）定义

| 能力 | 说明 | 类型 |
|---|---|---|
| `mapping_builder` | 因素/时间/模型对象三张 mapping 表生成与维护 | 配置 |
| `result_table_builder` | 模型输出 → 报告长表（10 度量全量计算） | 数据管道 |
| `chart_gen` | 标准图表渲染（Decomp/Contribution/Due-to/ROI/四象限表） | 图表引擎 |
| `narrative_gen` | 按解读模板 + 商业逻辑生成话术（中英） | LLM + 话术库 |
| `report_assembly` | 按 Part 0–2 骨架组装报告（by 模型对象） | 模板引擎 |
| `interactive_qa` | 结果长表上的约束问答（带 KBQ 回链与证据图表） | LLM + 检索 |

## 8. Gate 定义

| Gate | 触发点 | 判定者 | 规则 |
|---|---|---|---|
| G4.0 技术检查放行 | 报告组装前 | 自动 + DS | 1.5/1.6 红旗存在 → 禁止生成业务结论部分 |
| G4.1 解读审核 | 话术初稿完成 | BA | AI 话术 vs 数据一致性、商业逻辑合理性 |
| G4.2 客户交付 | 报告定稿 | 项目负责人 + 客户 | Review 会议；反馈回流（如版本时间戳更新） |

## 9. 与其他智能体接口

| 方向 | 内容 |
|---|---|
| ← 模型智能体 | 结果长表、Tech Review 报告（1.1–1.6 直接嵌入） |
| ← 商业智能体 | KBQ（报告必答清单）、行业判断标准（红黄绿灯阈值：渠道 ROI 2.0/1.0、蚕食率 30%/50% 等）、商业上下文 |
| ← 数据智能体 | 生意基本面数据（Part 0）、数据口径备注（脚注） |
| ← 项目管控智能体 | 交付排期、版本管理、客户反馈归档 |
