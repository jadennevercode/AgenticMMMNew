# E2E 贯通记录 · 基于还原数据真实跑一遍 S1→S2

跑法：真实后端（`uvicorn app.main:app --port 8010`）+ 真实 LLM + 真实文件上传，
逐个门禁人工推进。每条都是当场撞到并当场取证的，不是事后回忆。

驱动脚本：`backend/scripts/e2e_case.py`
项目：`mizone-mmm-e2e-v2-2-32-restore`

## 汇总

| 级别 | 阶段 | 问题 | 状态 |
|---|---|---|---|
| BLOCKER | 全局 · LLM | 端点限流被当成普通错误，3 次无退避重试把瞬时 429 变成 10 分钟锁死，S1 每个 AI 步骤静默降级为空 | 已修 |
| BREAK | S1 · 1.21d / 1.4d | 审批门禁不写回因子树：46 条 AI 因子永远停在 `proposed`，而 `proposed` 不进 2.1 映射 → AI 的因子贡献全部丢失 | 待修 |
| BREAK | S1 · 1.4 | 12 份真实访谈纪要 → 0 条回答、0 条因子变更（BLOCKER 的下游症状，修复后复测） | 复测中 |
| GAP | S1 · 全部门禁 | 门禁批准后 artifact 仍停在 `proposed` / `draft`，只有无门禁的 artifact 是 `confirmed` | 待修 |
| GAP | 交付物 | 还原产物只含数据，不含 S1 所需文档，拿着 `restored/` 无法从头起跑 | 已补文档说明 |
| NOTE | 建模口径 | 还原树 85 个指标里 43 个（51%）落在 `Baseline Factor`，`is_driver_row` 永不将其作为 X —— 含 `本品标价`、`品牌力指数` | 设计使然，需知情 |
| NOTE | 源数据 | 源表尾部 23 行全空（23,813 = 23,790 + 23） | 已原样保留 |

---

## [BLOCKER] 全局 · LLM 限流把每个 AI 步骤静默变成空结果

**现象.** S1 全程跑完、15 个任务全部 `done`，但产出是空的：因子树 0 条 `interview` 来源行，
访谈 28 个业务问题 `0/28 answered`。

**取证.** 直接打这个 endpoint：

```
HTTP 400: {"rateLimitInfo":"短期限制: 20次/2分钟, 惩罚时长: 10分钟",
           "code":429,"error":"Too Many Requests",
           "message":"API请求频率过高，2分钟内超过15次请求，请等待10分钟后重试"}
```

三件事叠在一起：

1. 网关把 **429 包在 HTTP 400 里**，`volcano.py` 只看 status code，识别不出这是限流。
2. `chat()` 的重试循环**没有任何退避**，3 次背靠背重试；`json()` 又在外面套 3 次
   → 最多 9 次瞬时轰炸，把"等 2 分钟就好"直接变成 **10 分钟惩罚锁死**。
3. 每个 grounded agent 步骤都 `except LLMError` 降级为空结果 —— 单点看是"优雅降级"，
   连起来看就是**整个 S1 认知层全空但流程照常绿灯通过**。

**为什么是 BLOCKER.** 这不是慢，是错。流程显示全绿、任务全 `done`、门禁可批准，
而实际产出为空。用户拿到的是一个"看起来跑通了"的空壳。

**修复.**`app/llm/volcano.py` + `app/config.py`：

- `is_rate_limited()` 认 body 里的 429 / `请求频率过高`，不再只看 status code；
- `_backoff_seconds()` 分两条曲线：限流 60s→120s→240s（带抖动），普通传输错误 2s→20s；
- `_AdaptivePacer`：**默认完全不介入**（不限流的 endpoint 全速跑），一旦观测到限流，
  进程内全局最小间隔切到 `llm_paced_interval=7.0s`（≈17 次/2 分钟，压在 20 次/2 分钟线下）。
  只退避不限速是不够的 —— 退避解决"这次失败了"，限速才解决"下一步又撞上"。

**修复后实测.** 三次连续调用：第 1 次仍在 10 分钟惩罚期内失败，第 2 次退避后成功（199s），
第 3 次 6.9s 成功。重跑 S1 全程 **0 次 429**。

---

## [BREAK] S1 · 审批门禁不写回因子树，AI 因子全部丢失

**现象.** 走完 S1，因子树 181 行 = 135 `template` + 46 `ai`。
`d-1.21`（"Confirm factor tree"）和 `d-1.4`（"Accept changes → 写回因子树"）都已批准，
但 46 条 AI 行的 `status` **仍然是 `proposed`**。

**取证.** 只有一个门禁注册了 effect：

```
app/agents/registry.py:36:    eng.register_decision("d-2.5", ledger.freeze_range_drops)
```

`engine.resolve_decision()` 会查 `decision_effects`，`d-1.21` / `d-1.4` 查不到 →
只把 decision 标 `resolved`、把 task 标 `done`，**不碰任何一行因子**。

**为什么致命.** `app/dataeng/mapping.py`：

```python
_ACTIVE_STATUSES = ("baseline", "accepted")
```

`proposed` 不是 active → 这 46 行**根本不进 2.1 的因子映射**。实测：

```
tree total: 181 | active(baseline/accepted): 135 | proposed: 46
factor-map total rows: 135
```

于是：AI 从上传材料里挖出来的 46 个因子，经过一个写着"接受变更 / 写回因子树"的门禁、
用户点了"接受"，然后**静默消失**，永远不会进入 Data Intake，也永远不会进模型。

产品其实提示过一次（1.21 的 finding："46 AI-recommended factors await your accept/reject"），
但那是**另一个** UI 动作（`PUT /factor-tree`）。也就是说：**门禁批准 ≠ 采纳**。
在 autopilot 模式下没有人会去点那个 UI，46 条必然全丢。

**建议.** 给 `d-1.21` / `d-1.4` 注册 decision effect：批准即把该任务产出的 `proposed` 行
翻成 `accepted`（拒绝则翻 `rejected`）。门禁的文案已经承诺了这件事，代码补上即可。

---

## [GAP] S1 · 门禁批准后 artifact 仍是 proposed / draft

走完 S1 后的 artifact 状态：

```
a-sow                confirmed     a-scope           proposed
a-source-materials   confirmed     a-factor-tree     proposed
a-knowledge-package  confirmed     a-interview       draft
a-bu-summary         confirmed     a-data-request    proposed
```

规律很清楚：**带门禁的 artifact 全是 `proposed`/`draft`，不带门禁的反而是 `confirmed`**。
`a-scope` 的门禁 `d-1.0`（"Lock profile"）、`a-factor-tree` 的 `d-1.21`、
`a-data-request` 的 `d-1.5`（"Signed off"）都已批准，状态却没跟着走。

和上一条同源：`resolve_decision` 没有把 artifact 状态推进的通用逻辑。
影响比上一条轻（下游没有按 artifact 状态过滤的硬门槛），但 UI 上"已签署的数据需求"
显示成 `proposed` 是会误导人的。

---

## [GAP] 还原产物不含 S1 文档，拿着 `restored/` 起不了跑

`restored/model-input-2.32/` 只有数据（因子树 + raw + curated）。
但 S1 的三个上传门禁要的是**文档**：

| 门禁 | category | 需要什么 | 还原产物里有吗 |
|---|---|---|---|
| 1.0a | `project_background` | SOW / 立项简报 | ✗ |
| 1.1a | `industry_reference` | 品牌竞品报告、内部材料 | ✗ |
| 1.4a | `interview_minutes` | 访谈录音或纪要 | ✗ |

本次贯通用的是 `reference/01.商业智能体/` 下的真实文档（Scope / 行业知识 /
factor&data_request + 12 份访谈纪要）。已在 `README.md` 与
`backend/scripts/e2e_case.py::S1_DOC_SETS` 里写明来源，脚本可直接复现。

---

## [NOTE] 还原树里 51% 的因子永远进不了模型

`app/mmm/pivot.py::is_driver_row()` 只认 `Marketing Factor` / `Commercial Factor`：

```
还原树 85 行 → Baseline Factor 43 · Marketing Factor 40 · Commercial Factor 2
长表 23,813 行 → driver-eligible 15,228 (64%) · Y 4,598 · Baseline 4,100 (17%)
被排除的 distinct 指标：24 个
```

其中包括 `本品标价`、`品牌力指数`、`本品新品上市SKU个数`、`品类全渠道销量` ——
自有定价与品牌资产在不少 MMM 实践里是会当驱动因子建模的。

**这不是还原的 bug。** 逐指标核对过：26 个同时出现在 2.32 与 2.24 的指标，
业务词表→引擎词表的对应**零冲突**，`本品标价` 在源数据里就是 `生意基本盘`。
是"生意基本盘 = baseline，不进设计矩阵"这个产品口径的必然结果，
使用者需要知情：想让定价进模型，得在因子树里把它挪出 `生意基本盘`。

---

## [NOTE] 源表尾部 23 行全空

`D.Data Station` 23,813 行 = 2.24 的 23,790 行 + **23 行全空 padding**。
`raw/` 因此是 30 个 workbook（29 个真实数据源 + 1 个 `未标注数据源.xlsx` 装这 23 行）。
保留而非静默丢弃：无损断言要求逐行多重集相等，且真实客户文件本来就常带尾部空行。
