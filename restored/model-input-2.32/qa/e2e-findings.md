# E2E 贯通记录 · 基于还原数据真实跑通一个完整 Case

**结果：38/38 任务全部 done，S1 → S2 → 建模 → 报告全程无断点。**

跑法：真实后端（`uvicorn app.main:app --port 8010`）+ 真实 LLM（GLM-5.2）+ 真实文件上传
+ 真实 dbt build，逐个门禁推进。无 mock、无 seed、无 reference 兜底。

- 项目：`mizone-mmm-e2e-v2-2-32-restore`
- 驱动脚本：`backend/scripts/e2e_case.py`
- 数据：本文件夹 `curated/long_table.xlsx`（23,813 行）
- S1 文档：`reference/01.商业智能体/`（Scope + 行业知识 + factor&data_request + 12 份访谈纪要）

跑通的实际结果：

```
S1  15/15  因子树 255 行（135 template + 74 interview + 46 ai）
2.1        published indicators 84 · factor map mapped 80 / ignored 55 / pending 0
2.2        quality scorecard 82 行（真实四维打分）
2.4        stat scorecard 69 行（真实 CV / Pearson / VIF，如 VIF=23.7）
2.5r       OLS 7 个 model object 全部拟合，R² 0.909–0.963，MAPE 7.9–12.3
2.6        master data 锁定
S4/S5      建模 + 报告完成
```

---

## 汇总

| 级别 | 阶段 | 问题 | 状态 |
|---|---|---|---|
| **BLOCKER** | 全局 · LLM | 限流被当成普通错误 + 无退避重试 → 瞬时 429 变 10 分钟锁死，S1 每个 AI 步骤静默降级为空 | **已修并验证** |
| **BLOCKER** | 2.5y · Y 选取 | 5/10 个指标被误标为 `Y`，MT 模型实际拿"已投放冰柜个数"当因变量拟合出 R²=0.953 | **待修** |
| BREAK | S1 · 1.21d/1.4d | 审批门禁不写回因子树：120/255 行（47%）永远停在 `proposed`，进不了 2.1 映射 | 待修 |
| BREAK | S1 · 1.4 | 12 份访谈只有前 5 份进过 LLM，73% 文本被截断丢弃；答案回写仍 0/28 | 待修 |
| GAP | 全部门禁 | 16 个门禁只有 1 个注册了 effect，文案承诺的状态变更多数不发生 | 待修 |
| GAP | 2.5 | 不显式 `PUT /ols-config` 就确认 2.5y/x/p，`ols_config` 全空，模型跑在自动默认值上 | 待改 |
| GAP | 交付物 | 还原产物只有数据，S1 所需文档需另外提供 | 已写进 README |
| NOTE | 建模口径 | 还原树 85 个指标里 43 个（51%）属 `Baseline Factor`，永不作为 X | 设计使然 |
| NOTE | 源数据 | 源表尾部 23 行全空 | 已原样保留 |

---

## [BLOCKER · 已修] LLM 限流把每个 AI 步骤静默变成空结果

**现象.** 第一次跑，S1 15 个任务全部 `done`、门禁全绿，但产出是空的：
因子树 0 条 interview 行，访谈 `0/28 answered`，profile `{}`。

**取证.**

```
HTTP 400: {"rateLimitInfo":"短期限制: 20次/2分钟, 惩罚时长: 10分钟",
           "code":429,"error":"Too Many Requests",
           "message":"API请求频率过高，2分钟内超过15次请求，请等待10分钟后重试"}
```

三件事叠加：

1. 网关把 **429 包在 HTTP 400 里**，`volcano.py` 只看 status code，识别不出限流；
2. `chat()` 重试**没有任何退避**，3 次背靠背；`json()` 外面又套 3 次 → 最多 9 次瞬时轰炸，
   把"等 2 分钟"变成**10 分钟惩罚锁死**；
3. 每个 grounded 步骤 `except LLMError` 降级为空 —— 单点是"优雅降级"，
   连起来是**整个 S1 认知层全空但流程照常绿灯**。

**修复**（`app/llm/volcano.py` + `app/config.py`，commit `973fcd9`）：

- `is_rate_limited()` 认 body 里的 429 / `请求频率过高`；
- `_backoff_seconds()` 分两条曲线：限流 60→120→240s，普通错误 2→20s；
- `_AdaptivePacer` **默认不介入**，一旦观测到限流就把进程内最小间隔切到
  `llm_paced_interval=7.0s`（≈17 次/2min，压在 20 次/2min 线下）。
  只退避不限速不够 —— 退避管"这次失败"，限速才管"下一步别再撞"。

**验证.** 修复后重跑 S1：服务端 **0 次 429**，因子树从 181 行（0 条 interview）
变成 **255 行（74 条 interview）**。同一份材料、同一个流程，产出从空变成有。

> 注意：pacer 是**按进程**的。后端服务和任何并行的 CLI 脚本各有一个，
> 两边同时打就还会触限。本次贯通中我自己的探针就抢过配额、拖慢过 1.3b。

---

## [BLOCKER · 待修] 模型拿"已投放冰柜个数"当因变量，还拟合出 R²=0.953

**这是本次最严重的问题。** 2.5r 跑完，MT 这个 model object 的结果是：

```
yMetric = 已投放冰柜个数     nObs=34  R²=0.953  adjR²=0.935  MAPE=9.42
```

**"已投放冰柜个数"是冰柜投放量，是渠道执行的驱动因子，不是销量 KPI。**
拿它当因变量，整个回归没有业务含义 —— 但七个 object 全部拟合成功、
红旗只报了 Durbin-Watson，2.5y 门禁正常打开、正常确认、正常通过。

**取证.** 84 个已发布指标里有 10 个被打上 `metricType=Y`，其中 **5 个根本不是 KPI**：

| l1 | l4 | metric | metricType | semanticType |
|---|---|---|---|---|
| Marketing Factor | 自有冰柜 | 已投放冰柜个数 | **Y** | **spending** |
| Marketing Factor | POSM和陈列物料 | 销售业代稽查平均门店POSM个数 | **Y** | count |
| Marketing Factor | POSM和陈列物料 | 销售业代稽查平均门店陈列架个数 | **Y** | count |
| Baseline Factor | 市场规模 | 品类全渠道销量 | **Y** | other |
| Baseline Factor | 特定属性趋势 | sales volume | **Y** | other |

注意第一行自相矛盾：**同一条记录 `metricType=Y` 而 `semanticType=spending`** ——
两个分类器在同一份数据上给出互斥结论，没有任何地方校验一致性。

**为什么会选中它.** `pivot._is_y_row()` 只要 `metric_type ∈ {y, kpi}` 就认作 Y 候选；
`_pick_y_metric()` 在候选里按"月覆盖优先 + 销量优先"挑 —— `已投放冰柜个数`
1380 行、覆盖完整，就赢了真正的 `谈判点出货箱数`。

**对照.** 直接用 curated 长表离线跑（`scripts/_test_restore.py`，不经过 Data Engine
的指标分类），MT 选中的是 **`谈判点出货箱数`**，正确。
**所以问题出在 Data Engine 发布时的 `metricType` 自动分类，不在还原数据。**

**建议.**

1. `l1 != 'KPI'` 的指标不允许被标 `Y`（因子树已经说明了它是驱动因子）；
2. `metricType` 与 `semanticType` 互斥时必须报错或要人工裁决，不能静默取其一；
3. 2.5y 门禁在**没有显式选择**时不应放行 —— 见下一条。

---

## [BREAK] 审批门禁不写回因子树，47% 的因子进不了 S2

走完 S1，因子树 255 行 = 135 `template` + 74 `interview` + 46 `ai`。
`d-1.21`（"Confirm the factor tree"）和 `d-1.4`（"Accept changes → **写回因子树**"）
都已批准，但 120 条非 template 行的 `status` **仍然是 `proposed`**。

`app/dataeng/mapping.py`：

```python
_ACTIVE_STATUSES = ("baseline", "accepted")
```

`proposed` 不是 active → 这 120 行**根本不进 2.1 因子映射**。实测：

```
tree 255 行 → active(baseline/accepted) 135 · proposed 120 (47%)
factor-map total = 135
```

AI 从材料里挖的 46 个因子 + 访谈挖的 74 个因子，经过一个写着"接受变更/写回因子树"的
门禁、用户点了"接受"，然后**静默消失**。

### 这不是孤例，是一个模式

16 个门禁里**只有 1 个注册了 effect**：

```
$ grep -rn "register_decision" backend/app/ | grep -v engine.py
app/agents/registry.py:36:    eng.register_decision("d-2.5", ledger.freeze_range_drops)
```

而选项文案明确承诺会改状态的至少有：

| 门禁 | 文案 | 实际 |
|---|---|---|
| `d-1.0` | "Lock granularity and continue" | 无 |
| `d-1.21` | "Baseline L1–L4 + indicators" | 无 |
| `d-1.4` | "Write back into the factor tree" | 无 |
| `d-2.2` | "Keep the 1s, drop the 0s" | 无（靠行级 Drop） |
| `d-2.4` | "Enter with the Good-band metrics" | 无（靠 2.5x 勾选） |
| `d-2.5` | "Selected indicators enter the master table" | **有** |

S2 那两个是既有设计（真正过滤在行级处置上）。但 S1 的 `d-1.21`/`d-1.4`
没有摆在流程里的补偿机制 —— 行级采纳是另一个 UI 动作（`PUT /factor-tree`），
autopilot 不会去点，于是必然 100% 丢失。

**结论：门禁文案在描述一个它并不执行的动作。** 要么补 effect，要么改文案并把
行级动作做成流程里的显式一步，但不能让人读着"已写回"而实际没写回。

---

## [BREAK] 12 份访谈只有前 5 份进过模型，73% 文本被丢弃

**取证.**

```
12 份纪要抽取文本合计            24,386 字符
_load_minutes_text(max_chars=9000)   9,000  → 丢弃 63.1%
再 transcripts[:6500]                6,500  → 丢弃 73.3%
=> 只有前 5/12 份纪要贡献了任何文本
```

`app/store/files.py::extract_category_text` 把**整个 category 的所有文件拼起来后**
截断到 9,000 字符，`business.py` 两处再各自 `[:6500]`。
后 7 份访谈（Media / Activation / EC / RTM / Sales / O2O / SIA）**一个字都没进过模型**，
而 1.4 的产出被呈现为"从上传纪要回写"。

同时 `_extract_docx` 把 `doc.tables` 解析出来放进 `tables`，但 `text` 只含段落，
`extract_category_text` 只拼 `.text` —— 表格内容解析了却从不使用（本例占 9.3%，
影响小于截断，但同样是白做的解析）。

**答案回写仍然是 0/28.** 因子抽取修好后能出 74 行，但
`Interview answers written back from minutes: 0/28 business questions answered` 依旧。
两个调用拿的是同一批 6,500 字符，因子抽取能出东西而答案匹配出不来 ——
在只有前 1~2 份纪要的情况下，模型确实答不上另外 10 场访谈的问题。

**建议.** 按文件分别调用并汇总，而不是拼接后一刀切；至少把上限提到能覆盖全部纪要，
并在截断发生时 emit 一条 finding 说明"只用了 N/M 份"。

---

## [GAP] 2.5y/x/p 确认了，但 `ols_config` 是空的

```
OLS CONFIG: y=None  object=None  include=0  exclude=0
setup: {"configured": true, "selectedX": 6, "totalX": 22, ...}
```

`d-2.5y`/`d-2.5x`/`d-2.5p` 三个门禁都 `confirm` 了，`ols_config` 仍然全空 ——
真正的选择要靠单独的 `PUT /ols-config`，门禁的 `confirm` 不携带任何选择。

严格说这不算 bug（不选就用自动默认值），但它和上一个 BLOCKER 叠在一起就很危险：
**不做显式选择 → 用自动挑的 Y → 自动挑中"已投放冰柜个数" → 门禁确认 → 训练完成。**
整条路径上没有任何一步会拦住它。

建议：`d-2.5y` 在 `ols_config.yMetric` 为空时不放行，强制人做一次选择。

---

## [GAP] 还原产物不含 S1 文档

`restored/model-input-2.32/` 只有数据。S1 三个上传门禁要文档：

| 门禁 | category | 本次用的 |
|---|---|---|
| 1.0a | `project_background` | `reference/01.商业智能体/…-Scope_1.0.xlsx` |
| 1.1a | `industry_reference` | 同目录 `行业知识_1.1.xlsx` + `factor&data_request_1.2.xlsx` |
| 1.4a | `interview_minutes` | 同目录 `访谈框架及纪要_1.32/纪要/*.docx`（12 份） |
| 2.1 | `data` | **本文件夹** `curated/long_table.xlsx` |

已写进 `README.md` 与 `e2e_case.py::S1_DOC_SETS`，可直接复现。

---

## [NOTE] 还原树里 51% 的因子永远进不了模型

`pivot.is_driver_row()` 只认 `Marketing Factor` / `Commercial Factor`：

```
还原树 85 行 → Baseline 43 · Marketing 40 · Commercial 2
长表 23,813 行 → driver-eligible 15,228 (64%) · Y 4,598 · Baseline 4,100 (17%)
被排除的 distinct 指标 24 个，含 本品标价 / 品牌力指数 / 本品新品上市SKU个数
```

**不是还原的 bug**：26 个同时出现在 2.32 与 2.24 的指标，词表对应**零冲突**，
`本品标价` 在源数据里就是 `生意基本盘`。这是"生意基本盘 = baseline，不进设计矩阵"
的必然结果。想让定价进模型，得在因子树里把它移出 `生意基本盘`。

---

## [NOTE] 源表尾部 23 行全空

`D.Data Station` 23,813 = 2.24 的 23,790 + **23 行全空 padding**。
`raw/` 因此是 30 个 workbook（29 个真实数据源 + `未标注数据源.xlsx` 装这 23 行）。
保留而非静默丢弃：无损断言要求逐行多重集相等，真实客户文件也常带尾部空行。
