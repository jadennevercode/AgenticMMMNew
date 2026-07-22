# 还原 model input_2.32 → FactorTree + Data Engine 可注册资产

**Date:** 2026-07-22
**Source:** `reference/02.数据智能体/【MMM AI】数据智能体-model input_2.32.xlsx`
**Status:** Design approved, ready for implementation planning

## 目标

把 `model input_2.32.xlsx`（入模数据）拆解还原成两组产物：

1. **FactorTree** — L1→L4 + Indicator，带渠道/区域粒度与来源标注，可直接 `PUT /api/projects/{id}/factor-tree`。
2. **每个 Indicator 的数据** — 两种形态：客户原始态（按数据源切片、保留明细粒度与脏值，用于在 Data Engine 里注册数据资产、走完整 transform 流程），与入模态 19 列长表（publish-ready，作为标准答案与回归基线）。

产物集中在一个文件夹下，配一个可重跑的生成脚本和一个验证脚本，验证到 OLS 真的能拟合。**不改产品代码。**

## 源文件事实

`model input_2.32.xlsx`（2.14 MB）两个 sheet：

| Sheet | 形状 | 内容 |
|---|---|---|
| `模型颗粒度参考表` | 97 行 × 8 列（表头在第 1 行，首列为空列） | 规划态因子树：`生意因子-Level 1/2/3` · `生意影响因子-Level 4` · `指标选择` · `渠道` · `区域`。层级列为合并单元格式的稀疏填充，需前向填充。97 个有效行、66 个唯一指标（31 行是同一指标的多条粒度记录）。 |
| `D.Data Station` | 23,813 行 × 22 列 | 实际长表：`Task name`·`品牌`·`省份组别`·`渠道类型`·`渠道`·`年`·`月`·`数据源`·`数据类型Level1..Level8`·`METRICS类型`·`METRICS`·`VALUE`，外加 `Variable`·`Variable no.`·`Metric no.` 三列命名元数据。57 个唯一 `Level5`（含 `KPI` 自身，非 KPI 的实际指标 56 个），77 个 `Variable`，119 个 `Metric no.`，时间跨度 202301–202512。 |

其他实测量：29 个 `数据源`、25 个 `Task name`、7 个 `渠道类型`（EC/O2O/MT/TT/AFH/社区团购/WS）、6 个 `省份组别`（National/A/B/C/D/E）、25 个 `METRICS类型`。

### `D.Data Station` 是明细流水表，不是聚合表

用 `(Task name, 品牌, 省份组别, 渠道类型, 渠道, 年, 月, 数据源, Level1..Level8, METRICS类型, METRICS)` 这个**全键**分组，23,813 行只压缩到 20,699 组，其中 1,160 组重复、**1,140 组的取值互不相同**（另有 105 行是整行完全重复）。

例：`ANP spending 微信立减 / MIZONE / A / AFH / 景区、交通、商圈等 / 202409` 这一个格子下有 6 条不同的 `Spending`（970 / 1048.125 / 3955 / 7343.75 / 515.625 / 1243.125）与 6 条不同的 `签约门店数`。这是 6 场活动的明细，不是脏数据。

**结论：这份数据无法在不聚合、不编造记录配对的前提下变成宽表。** 6 条 Spending 与 6 条 签约门店数 之间的一一对应关系源表里没有任何字段支持，任何"明细序号"配对都是凭空造的。

因此 `raw/` **保持明细粒度**（见产物结构）。`curated/` 不受影响 —— 19 列长表天然容纳明细行，`build_model_frame` 在 pivot 时本就按 sum 聚合。

## 四条还原规则

### 规则 1 — 层级偏移（The L5 offset）

`模型颗粒度参考表` 的 `指标选择` 列 **等于** `D.Data Station` 的 `数据类型Level5`。

因此 `FactorRow` 的映射是：

```
FactorRow.l1        ← 数据类型Level1
FactorRow.l2        ← 数据类型Level2
FactorRow.l3        ← 数据类型Level3
FactorRow.l4        ← 数据类型Level4
FactorRow.indicator ← 数据类型Level5
```

`Level6–Level8` 是下钻维度，只存在于长表上，**不进因子树**（与 `FactorRow` 模型一致——它没有 l5–l8 字段；`Indicator` 模型才有）。

### 规则 2 — 两套 L1 词表，同一份数据

`model input_2.32` 与 `Data Process_2.24`（现有 reference 数据集）是同一份数据的两个视图：2.32 用**业务**词表，2.24 用**引擎**词表。

在 `(Task name, 品牌, 省份组别, 渠道类型, 渠道, 年, 月, METRICS, VALUE)` 上 join 两表，得到 7,054 行匹配，映射**零冲突**：

| 2.32（业务） | 2.24（引擎） | 证据行数 |
|---|---|---|
| 生意基本盘 | Baseline Factor | 338 |
| 渠道成交驱动 | Marketing Factor | 519 |
| 消费者需求驱动 | Marketing Factor | 662 |
| 促销优惠 | Commercial Factor | 1,076 |
| KPI | KPI | 4,459 |

**这条规则是产物能否跑通的关键。** `app/mmm/pivot.py::is_driver_row()` 判定驱动因子的条件是 `l1 ∈ {MARKETING FACTOR, COMMERCIAL FACTOR}`（或显式 driver tag）。若 curated 长表直接写中文 `l1`，`is_driver_row` 全 False，OLS 找不到任何 X，模型无法拟合。

所以：**curated 长表的 `l1` 写引擎词表**；中文业务词表保留在 `raw/` 那套原始态文件里，映射关系单独落 `taxonomy_map.csv` 存档。

### 规则 3 — `METRICS类型` 是单位，不是角色

19 列 schema 里的 `metric_type` 在本项目承担双重语义：reference 数据集用它表示**单位族**（`箱数`/`RMB`/`Volume`/`百分比`…），per-project binding 用它表示**建模角色**（`Y`/`spending`/`X`）。

本次还原**保留单位族语义**，因为：

- `pivot.is_money_metric()` / `is_volume_metric_type()` 靠它决定 ROI 的单位（金额 Y 的 ROI 是 Revenue/Spend，销量 Y 需要单价换算）。写成角色标签会丢掉这个信息。
- 角色信息已经由 `l1` 承载（规则 2 之后 `l1` 是引擎词表，`_is_y_row` 与 `is_driver_row` 都能正常判定）。

唯一的归一化：`花费 → Spending`（2.24 用 `Spending`，2.32 用 `花费`），使花费识别生效。其余 `METRICS类型` 原样透传。

### 规则 4 — Y 的口径

`l1='KPI'` 的 4,462 行中，`Level2..Level5` 全部字面量为 `KPI`（KPI 不是因子树的一个叶子——与"数据需求模板不含 KPI"的既有约定一致）。指标名按渠道分裂：

| 渠道 | 销量口径 | 金额口径 |
|---|---|---|
| MT | 谈判点出货箱数 | 谈判点出货金额 |
| TT / AFH / WS | Compass完成箱数 | Compass完成金额 |
| EC | Volume | GMV |
| O2O / 社区团购 | 箱数 | GMV |

**销量与金额两类都保留为 Y 候选，不做重命名、不做合并。** 依据：`pivot._pick_y_metric()` 已经能在多个 Y 候选中按"月覆盖优先 + 销量优先"选默认，而 2.5y 门禁允许人工显式指定 Y（`build_model_frame(y_metric=...)`）。这既保住产品的人机流程，默认路径也仍然落在销量上。

README 需明确写出这个口径断层：各渠道的 Y 并非同质（MT 出货 vs EC GMV vs O2O 箱数），跨渠道汇总的 Y 只在同一 `channel_type` 内可比。

## 产物结构

```
restored/model-input-2.32/
  README.md                    重建规则、口径说明、使用方式
  factor-tree/
    factor-tree.json           FactorTree{rows:[FactorRow]}，可直接 PUT /factor-tree
    factor-tree.xlsx           人看的视图：L1-L4 + Indicator + 渠道 + 区域
                               + origin(planned/data/both) + hasData + rows + monthsCovered
    reconciliation.md          29 条规划无数据 + 19 条有数据未入树，逐条列明
  raw/                         29 个 workbook，按 数据源 拆，中文列名，明细粒度
    SIA.xlsx  MI.xlsx  Media.xlsx  Trade ANP 线下数据-Sandro.xlsx  ...
                               每个 workbook: sheet = Task name
                               每行 = 一条源记录（保留明细，不聚合、不配对）
                               列 = 年·月·品牌·省份组别·渠道类型·渠道
                                    + 数据类型Level1..Level8
                                    + METRICS类型·METRICS·VALUE（中文原名）
  curated/
    long_table.csv             19 列 canonical 长表，引擎词表，publish-ready
    long_table.xlsx            同上的 Excel 版本
    taxonomy_map.csv           L1 与 METRICS类型 的映射表 + 每条的证据行数
    indicators.csv             每个 Indicator 的 catalog（对齐 Indicator 模型字段）
  qa/
    profile.md                 逐指标：覆盖月数、维度组合数、缺失率、min/max
    ols_smoke.txt              验证脚本输出（model objects / Y / drivers / R² / n_obs）
```

### 因子树口径：并集，保留差异

因子树 = 规划态（66 指标）∪ 实际态（56 个非 KPI 指标）= 85 行，每行标注 `origin`：

- `planned` — 只在颗粒度参考表里，无数据（29 条）。在 2.1 因子映射门禁里自然进入 `pending`，需要人工 `ignore`，完整跑通 Data Intake 的人机环节。
- `data` — 只在 D.Data Station 里，未入规划树（19 条）。补回树里，`l1–l4` 取该指标在长表中的实际层级路径。
- `both` — 两边都有（37 条）。

`FactorRow.dimension` 从颗粒度参考表的 `渠道` + `区域` 两列合成（如 `全渠道, National`）；`origin=data` 的行从长表里该指标实际出现的 `渠道类型` / `省份组别` distinct 值推导。`FactorRow.source` 一律 `"template"`，`status` 一律 `"baseline"`（还原产物不预设人工判定）。

### git 策略

`factor-tree/`、`curated/taxonomy_map.csv`、`curated/indicators.csv`、`README.md`、`qa/` 入 git（都是小文本，是评审对象）。
`raw/`、`curated/long_table.*` 加进 `.gitignore` —— 体积大且由脚本完全可再生成。

## 脚本

两个脚本，都放 `backend/scripts/`，都不改产品代码。

### `restore_model_input.py`

幂等重建全部产物。执行顺序：

1. 读 `模型颗粒度参考表`（`header=0`，丢掉首列空列），前向填充 L1–L4 层级列，丢掉 `指标选择` 为空的行。

   注意 `header=1` 会静默吃掉第一条数据行（`品类全渠道销量`），把规划指标数从 66 误算成 65，进而把并集从 85 误算成 86。
2. 读 `D.Data Station`，清洗字符串列（trim、空串归 NA，与 `ingest.dataset.load_model_dataset` 同口径）。
3. **推导分类映射**：join 2.32 ↔ 2.24 得到 L1 与 `METRICS类型` 的映射。若出现映射冲突（同一业务 L1 对应多个引擎 L1），或出现 join 未覆盖的 L1 取值，**直接报错退出**，不静默套用默认值。
4. 按规则 1 建因子树（并集，标 origin），输出 `factor-tree.json` / `.xlsx` / `reconciliation.md`。
5. 按 `数据源` 分组、组内按 `Task name` 分 sheet，**原样切片**（不聚合、不 pivot、不清洗脏值），输出 29 个 raw workbook。
6. 应用规则 2/3/4，输出 19 列 curated 长表 + `taxonomy_map.csv` + `indicators.csv`。
7. 输出 `qa/profile.md`。

### `_test_restore.py`

三条断言，失败即非零退出：

1. **Schema** — `curated/long_table.csv` 的列名与顺序严格等于 `app.ingest.dataset.COLUMN_NAMES`。
2. **无损** — 两条：
   - `raw/` 的 29 个 sheet 纵向拼回来，与源 `D.Data Station` 的全部 19 个业务列做**多重集相等**（行序无关，保留重复行）。
   - `curated/long_table.csv` 把引擎词表反向映射回业务词表后，同样与源做多重集相等。

   用多重集而非集合，是因为源表本身含 1,140 组同键异值的明细行与 105 行完全重复行 —— 用去重比较会把这 3,000 多行的丢失掩盖掉。
3. **可跑通** — `build_model_frame(curated_long_table)` 至少产出一个 model object；该 object 的 Y 被识别（`y_metric` 非空）、drivers 数 > 0；`run_mmm` 能拟合并输出 R² 与 n_obs。输出落 `qa/ols_smoke.txt`。

## 已知风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| join 覆盖率 30% | 7,054 / 23,813 行匹配上 2.24。映射本身零冲突，但 `渠道成交驱动 → Marketing Factor` 仅 519 行支撑。 | 脚本输出每条映射的证据行数；未匹配的 L1 取值直接报错，不猜。 |
| `MAX_DRIVERS=12` 截断 | 77 个 Variable 远超 `pivot.MAX_DRIVERS`，OLS 会按与 Y 的相关性截断驱动因子。 | 验证脚本打印被截掉的 driver 清单，避免"跑通了但悄悄丢了一半因子"。 |
| Y 跨渠道不同质 | MT 出货 / EC GMV / O2O 箱数 口径不同，跨渠道汇总不可比。 | README 显式写明；默认 Y 由 `_pick_y_metric` 在同一 model object（= channel_type 分组）内选。 |
| L6–L8 稀疏 | L6 仅 1,633 行非空、L7 4,744、L8 6,695。 | 原样透传到长表，不填补；`profile.md` 报告稀疏度。 |
| 品牌列有脏值 | `品牌` 含 `'NAB'` 与 `'NAB '`（尾空格）两个值；`渠道` 含 `'snack store'` 与 `'Snack Store'`。 | `raw/` **保留脏值原样**（这正是 Data Engine 枚举聚类要处理的对象）；`curated/` 统一 trim，与 `load_model_dataset` 同口径。 |
| raw/ 不是宽表 | 源表是明细流水，做宽表必须聚合或编造记录配对（见上文）。`raw/` 因此是按源切片的明细表。 | Data Engine 的活儿仍然真实：29 份异构文件合并、枚举清洗、词表翻译、类型转换。README 写明为何不是宽表。 |

## 不在范围内

- 不修改任何产品代码（`app/` 下一行不动）。
- 不自动建 project、不写 `data/` 真实状态、不注册 data asset —— 产物是文件，注册动作由使用者在 UI 里做。
- 不重建 `Variable` / `Variable no.` / `Metric no.` 三列的命名规则（它们是源表的内部编号，19 列 schema 不消费）；仅在 `indicators.csv` 里原样带出以便追溯。
