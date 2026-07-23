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

---

## ✅ 修复验证 2026-07-22（真实跑通，非单测）

两个 BREAK 已修复并在真实后端 + 真实 LLM 上验证（项目 `mizone-mmm-e2e-v4-gate-minutes-v`）。
实现见 `docs/superpowers/plans/2026-07-22-s1-gate-writeback-and-minutes-coverage.md`
（commits 4266159 / b77a580 / b3ed513）。

### BREAK 1 — 已修复，实测通过
S1 跑完，`d-1.21` 批准后 **46 条 AI 因子行全部从 `proposed` 翻成 `accepted`**：

```
tree 181 行 → accepted/ai 46 · baseline/template 135
ACTIVE（进 2.1）：181/181     [修复前：仅 135 template 进 2.1，46 AI 行全被丢]
```

单测 `tests/test_factor_gate_effects.py` 另外锁定：翻转只动本门禁来源集、尊重手动
`rejected`、翻转后的行确实进入 `resolve_factor_map`。

### BREAK 2 — 已修复，实测通过
真实 `writeback_minutes` 处理器在隔离条件下（pacer 已激活、无并发 1.3b 抢占）跑 v4 的
12 份真实纪要：**12 份全部逐份送入 LLM，合并后 25/28 个业务问题被回答**
（修复前 `0/28`——只有前 5 份挤进 9000 字符上限，后 7 份一字未进）。

流水线里的"never silent"也实测生效：当 1.4 的 12 并发调用整体撞上限流惩罚时，
处理器**如实报告 `Interview digest: 0/12 transcripts used` 并标为 finding**、逐份容错
（一份失败返回 {} 不拖垮任务），而不是像修复前那样静默假装"已从纪要回写"。

### 附带发现（既有基础设施问题，不属本次两个 BREAK，未修）
LLM 端点是 20次/2分钟硬限 + **10 分钟惩罚锁死**。`973fcd9` 的 pacer 是**反应式**的
（观测到首个 429 才开始限速），存在两个洞：

1. **冷启动突发**：刚重启的后端进程 pacer 未激活，S1 前几个任务的调用齐射易触发惩罚；
   一旦进入 10 分钟锁死，3 次退避重试（约 7 分钟）盖不住，任务硬失败。
2. **未捕获的 LLMError 会卡死任务**：`assemble_knowledge`(1.1) 等处理器不 catch LLMError，
   异常冒泡杀死 `app/main.py::_run_job`，任务永久卡在 `status="running"`，整个项目楔死。
   （此条更早的 SDD 周期已记为 "FOUND, NOT FIXED"。）

对用户"自己也能从头跑到尾"的影响：同一进程内 pacer 一旦激活（首个 429 后）即持续生效，
所以在**已激活**的后端上新建项目可顺利跑通（BREAK 1 的 v4 全程 S1 15/15 即如此）。
但冷启动 + 并发齐射仍会偶发触限。建议后续单独处理：pacer 改为**主动式**（初始即带最小间隔，
或跨重启持久化"已被限流"状态），并给 S1 各处理器的 LLM 调用加 try/except 降级
（对齐 `writeback_minutes` 的容错），避免单次 429 楔死整个 run。

---

## Phase 2 per-channel verification — 2026-07-23

Verified Phase 2's per-Channel-Type screening on the **real Danone reference
dataset** (23,790 rows, `backend/app/agents/_test_real_per_channel.py`).
Deterministic, read-only: an in-memory state bound to project id `t-real-pc`
via `set_project_dataset(..., "slot")`/`invalidate_project`, never writing to
stored project JSON, no server started, no LLM called, no autopilot run.

**Result: 5/5 assertions pass, all against real computed values.**

1. **Data-derived channels.** `model_objects(st)` returns exactly the 7 real
   channel_types, ordered busiest-first by row count — re-derived independently
   from the raw frame rather than hardcoded:
   ```
   MT (5186) > AFH (4142) > TT (2522) > EC (1754) > O2O (1519) > 社区团购 (1479) > WS (942)
   ```
2. **Per-object ledger.** `indicator_ledger(st)` produces 168 rows (24 distinct
   indicator keys × 7 channels), and the set of non-`OBJECT_ANY` `object`
   values covers all 7 real channels.
3. **Per-channel statistical divergence (the core proof).** Built the real
   `build_stat_scorecard(st)`, found `POSM和陈列物料（POSM&Rack) / Bluesky KPI -
   平均POSM个数（IR拍照识别到的POSM数量加总/拍照次数）` scored in 5 real channels
   (AFH, EC, MT, TT, WS), forced its disposition to `"drop"` in AFH only and
   `"include"` in the other 4, rebuilt the ledger: AFH → `rejected_at ==
   "statistical"`, not adopted; MT/TT/EC/WS → adopted. Confirms the per-object
   statistical layer genuinely partitions by channel on real data, not just the
   synthetic two-channel fixture in `_test_per_channel.py`.
4. **`model_selection` per object.** The dropped `(l4, metric)` pair is in
   `model_selection(st).exclude_for("AFH")` and NOT in `exclude_for("MT")`.
5. **`master_table` columns differ by channel.** `master_table(st,
   channel_type=["MT"])` carries the POSM indicator as a column (4 total
   columns); `master_table(st, channel_type=["AFH"])` does not (6 total
   columns, all different) — the same real indicator is a modeling column in
   one channel and absent from another.

One adaptation from the plan as written: the plan's step 3 recipe ("force
disposition to drop for exactly one channel") was followed literally, but the
first candidate indicator tried (`产品价格调整` / `RSP`, chosen purely by
"scored in ≥2 channels") turned out to be scored by 2.4's statistical scorer
but absent from the ledger's own driver universe (`driver_candidates_by_l4` —
price-type factors are not driver candidates), so it never appears in
`indicator_ledger` at all and the forced drop silently matched nothing. Fixed
by additionally requiring the candidate indicator to be present in
`ledger._universe(st)`, which is what surfaces through the ledger/model_selection/
master_table chain. This is a real, reproducible property of the actual data
and taxonomy — documented in the script's `_pick_divergence_indicator`
docstring — not a workaround to fake a result.

**Existing suites still pass, unaffected:**
- `PYTHONPATH=. .venv/bin/python -m app.agents._test_per_channel` → 12/12 passed.
- `PYTHONPATH=. .venv/bin/python -m pytest tests/ -q` → 131 passed, 3 failed
  (all three in `tests/test_ols_config_roundtrip.py`, pre-existing and
  unrelated to this change — same 131/3 split the task's own success
  criteria call "pre-existing").

**Not run here (explicitly deferred):** criterion 5 of the Phase 2 plan — the
full live-autopilot end-to-end run on a real backend + real LLM — was **not**
attempted in this task. It needs a running `uvicorn` server, LLM credentials,
and touches shared `data/` project state, none of which this read-only,
in-memory verification is allowed to do. That run is the controller's
responsibility on a dedicated project id.

## 2026-07-23 — Live autopilot e2e on new per-channel code (BLOCKED: external LLM 502)
Ran `POST /reset` + `POST /run {autopilot:true}` on `danone-mizone` against the
feat/per-channel-screening backend (port 8020, GLM-5.2 configured).
- Deterministic S1 steps completed cleanly: 1.0, 1.0a, 1.1a done (3 tasks).
- HALTED at task 1.1 (first LLM-dependent A/C step): `LLMError: LLM chat failed
  after 3 attempts — HTTP 502`. Reproduced with a direct `get_llm().json()` probe —
  persistent, provider/gateway side, NOT a code issue and NOT transient.
- Pre-existing infra bug re-observed (out of Phase 2 scope): `app/main.py::_run_job`
  does not isolate the LLMError, so task 1.1 is stranded at status "running" while the
  run guard clears — "Task exception was never retrieved". (Documented in prior sessions.)
CONCLUSION: the per-channel pipeline itself is verified end-to-end on REAL data by
`app/agents/_test_real_per_channel.py` (7 channels, genuine per-channel divergence,
master-table columns differ by channel). A full *autopilot* case (with the LLM narrative
layer) needs the GLM-5.2 endpoint restored (check provider status / credentials / quota
in Settings → model config). No fabricated data was produced — the run stopped rather
than faking the LLM output.
