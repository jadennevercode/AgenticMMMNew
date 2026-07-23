# 修复两个 S1 BREAK：门禁写回因子树 + 访谈纪要全覆盖

**Date:** 2026-07-22
**Status:** Design approved, ready for implementation planning
**来源:** `restored/model-input-2.32/qa/e2e-findings.md` 里记录的两个 BREAK，端到端跑通时实测撞到。

## 背景

端到端真实跑通一个 Case（`mizone-mmm-e2e-v2-2-32-restore`，38/38 任务）时撞到两个 BREAK：
产品会告诉你"已写回 / 已从纪要回写"，但底下的数据没真的过去。两个都不报错，流程一路绿灯，
得跑数据才看得出来。

## BREAK 1 — 审批门禁不写回因子树

### 现象

S1 跑完，因子树 255 行 = 135 `template` + 74 `interview` + 46 `ai`。`d-1.21`（"Confirm the
factor tree"）和 `d-1.4`（选项文案 **"Write back into the factor tree"**）两个门禁都批准了，
但那 120 条非 template 行的 `status` 仍然是 `proposed`。

### 根因

`app/dataeng/mapping.py`：

```python
_ACTIVE_STATUSES = ("baseline", "accepted")
```

`proposed` 不在其中 → 这 120 行根本不进 2.1 因子映射。实测：

```
tree 255 行 → active(baseline/accepted) 135 · proposed 120 (47%)
factor-map total = 135    ← 只有 template 行进来了
```

这不是孤例，是个模式：16 个决策门禁里只有 1 个注册了 effect
（`app/agents/registry.py:36 eng.register_decision("d-2.5", ledger.freeze_range_drops)`）。
`engine.resolve_decision()` 查不到 effect 时只把 decision 标 `resolved`、把 task 标 `done`，
不碰任何数据。`d-1.21` / `d-1.4` 就属于这种。真正的行级采纳是另一个 UI 动作
（`PUT /factor-tree`），autopilot 不会去点 → 必然 100% 丢。

### 修复方案

给 `d-1.21` / `d-1.4` 注册 decision effect，approve 时把该门禁认领的 `proposed` 行翻成
`accepted`。**无需改数据模型** —— `FactorStatus = Literal["baseline","proposed","accepted",
"rejected"]` 已有 `accepted`，`mapping._ACTIVE_STATUSES` 已含 `accepted`，翻转后立即进 2.1。

来源归属（清晰、不重叠）：

- `d-1.21` 认领 `{ai, template}`（1.21 产出的行）
- `d-1.4` 认领 `{interview}`（1.4 产出的行）

d-1.21 在 d-1.4 之前跑，那时还没有 interview 行，所以两个集合天然不冲突。

规则：

- 只翻 `status == "proposed"` 的行。用户此前在 `PUT /factor-tree` 里手动设成 `rejected` 的行
  **保持不动** —— approve 意味着"接受我没有手动否决的那些提议"。
- `rework` 什么都不做；现有 `_rework` 会重跑产出任务。
- 翻转后重渲染 `a-factor-tree` 的 sheet body（用现有 `_factor_tree_sheet`），保证 UI 一致。

代码（新增在 `app/agents/business.py`，纯 st 变更）：

```python
def accept_factor_rows(st, sources: set[str]) -> None:
    """Flip this gate's still-proposed rows to accepted; respect manual rejects."""
    for r in st.factor_tree.rows:
        if r.status == "proposed" and r.source in sources:
            r.status = "accepted"
    art = st.artifact("a-factor-tree")
    if art is not None:
        art.body = _factor_tree_sheet(st.factor_tree)


def confirm_tree_effect(st, option_id):        # d-1.21
    if option_id == "approve":
        accept_factor_rows(st, {"ai", "template"})


def confirm_interview_effect(st, option_id):   # d-1.4
    if option_id == "approve":
        accept_factor_rows(st, {"interview"})
```

注册（`app/agents/registry.py`，紧挨现有 `d-2.5` 那行）：

```python
eng.register_decision("d-1.21", business.confirm_tree_effect)
eng.register_decision("d-1.4",  business.confirm_interview_effect)
```

`DecisionEffect = Callable[[ProjectState, str], None]`，effect 只拿 `(st, option_id)`，
不拿 `eng` —— 上述实现只碰 `st`，符合签名。

## BREAK 2 — 访谈纪要只用了前 5/12 份

### 现象

上传 12 份真实访谈纪要，回写只报 `0/28 business questions answered`。

### 根因

```
12 份纪要抽取文本合计               24,386 字符
extract_category_text(max_chars=9000)   9,000  → 丢 63.1%
business.py 再 transcripts[:6500]        6,500  → 丢 73.3%
=> 只有前 5/12 份纪要贡献了任何文本
```

`app/store/files.py::extract_category_text` 把整个 category 的所有文件拼成一大串后才截到
9,000 字符，`business.py` 里两个 LLM 调用又各自 `[:6500]`。后 7 场访谈（Media / Activation /
EC / RTM / Sales / O2O / SIA）一个字都没进过模型，而 1.4 的产出却被呈现为"从上传纪要回写"。

### 修复方案

把"拼接后一刀切"换成**逐份调用 + 合并**。

新增函数（`app/agents/business.py`）：

```python
def _minutes_files(st) -> list[tuple[str, str]]:
    """Per-file interview text: [(filename, text), ...], per-file capped.

    Uploaded interview_minutes only (no reference fallback). Each file is
    extracted independently and capped at _MINUTES_PER_FILE_CHARS so one huge
    transcript can't crowd the others out — the whole point is that every
    transcript reaches the model, not just the first few.
    """


async def _digest_transcript(filename, text, qlist, st) -> dict:
    """One combined LLM call over ONE transcript → {answers, factor_changes, insights}.

    Combined (not two split calls) so 12 transcripts cost 12 requests, not 24 —
    the endpoint rate-limits and the pacer serialises starts at ~7s. Fault
    isolation is now per-file: one bad transcript loses only itself.
    Each call sees ALL 28 questions but ONE transcript, and answers only what
    that transcript actually covers.
    """
```

`writeback_minutes` 改为：

```python
files = _minutes_files(st)                      # e.g. 12 (filename, text)
results = await asyncio.gather(
    *(_digest_transcript(fn, tx, qlist, st) for fn, tx in files))
merged = _merge_minutes_digests(results)        # pure merge
```

合并（纯函数 `_merge_minutes_digests(results) -> dict`）：

- **answers** → 按问题号 fill-first：某问题第一个非空、带 source 的答案胜出；跨份填补。
- **factor_changes** → 拼接 + 去重，键 `(op, l1, l2, l3, l4, indicator)`。
- **insights** → 拼接，封顶（保持现有条数上限）。

**永不静默**：emit 一条 finding，报告 `files_used/total`、`answered/28`、以及任一 per-file
失败。若某份 transcript 的调用抛错，`_digest_transcript` 返回空 dict（`except` 兜底，与现有
`_minutes_answers` 一致），合并跳过它，finding 记下来。

删除被取代的旧函数 `_load_minutes_text` / `_minutes_answers` / `_minutes_factor_changes`
（仅在 `writeback_minutes` 内使用，无外部引用），逻辑并入 `_digest_transcript`。

### 常量

```python
_MINUTES_PER_FILE_CHARS = 12000   # 单份上限；真实纪要 1–9k，留足余量
_MINUTES_LLM_TIMEOUT = 300.0      # 不变
```

## 显式不在范围内

- **docx 表格内容被丢** —— `_extract_docx` 把表格放进 `.tables`，`extract_category_text`
  只拼 `.text`。本例访谈是段落型，表格仅占 9.3%；且改动落在共享的 `app/ingest/extract.py`，
  波及所有抽取消费者（知识装配、预回答等），blast radius 更大。单列为后续项。
- **artifact 状态 GAP** —— 门禁批准后 `a-scope` / `a-data-request` 等仍显示 `proposed`。
  与 BREAK 1 同源（`resolve_decision` 无通用 artifact 推进逻辑），但本次只修因子行写回
  这条实际断链，artifact 状态推进单列。
- **BLOCKER：Y 误标（已投放冰柜个数当因变量）** —— 属 Data Engine 指标分类，另案。

## 测试（runnable script，仓库风格）

仓库无 pytest harness，测试是可跑脚本（`app/tools/_test_tools.py` 风格：裸 `assert` +
`main()` 非零退出）。

### `backend/tests/test_factor_gate_effects.py`

- 构造一个 `ProjectState`，factor_tree 含：`ai/proposed`、`interview/proposed`、
  `template/proposed`、一个 `ai/rejected`（模拟手动否决）、一个 `template/baseline`。
- 造出 `a-factor-tree` artifact，body 任意。
- 跑 `confirm_tree_effect(st, "approve")`：断言 `ai/proposed` 与 `template/proposed` → `accepted`，
  `interview/proposed` **不动**，`ai/rejected` **不动**，`a-factor-tree.body` 已重渲染。
- 再跑 `confirm_interview_effect(st, "approve")`：断言 `interview/proposed` → `accepted`。
- 跑 `confirm_tree_effect(st, "rework")`：断言无任何状态变化。
- 用 `mapping.resolve_factor_map(st)`（或 `mapping_complete`）断言翻转后这些行进入 active 集
  （不再是 pending 的成因）。

### `backend/tests/test_minutes_merge.py`

- 纯函数 `_merge_minutes_digests`：喂三份合成 digest —
  - 文件 A 答了问题 1、3；文件 B 答了问题 3（应被 fill-first 忽略，因为 3 已有答案）、5；
    文件 C 答了问题 5（同样被忽略）、8。
  - 断言最终 answers 覆盖 {1,3,5,8}，每题取的是第一个非空来源。
  - factor_changes：A、B 各提一个相同 `(op,l1..l4,indicator)` + 各一个不同的 → 去重后 3 条。
  - insights：合并且不超上限。
- `_minutes_files`：构造两个上传文件，断言返回两条 `(filename, text)`、各自被 per-file 上限截断。

Live LLM 路径（真正的 `_digest_transcript` 调用）由端到端跑覆盖，不在单测里断言不确定输出。

## 验收

- 两个新测试脚本通过。
- 既有回归不破：`app/tools/_test_tools.py`、`tests/test_api_smoke.py`、
  `tests/test_ledger.py`（若存在）行为不变。
- 重跑端到端（`scripts/e2e_case.py`）后：
  - 因子树 active 行数 = 全部非 rejected 的 proposed 被翻起来（不再是仅 135/255）；
    2.1 factor-map total 覆盖 ai + interview + template 行。
  - 1.4 的 finding 报告 `files_used = 12/12`（或明确说明哪几份失败），
    `answered` 显著 > 0。
