"""LLM-driven DuckDB cleaning-SQL drafting + preview.

Grounds the model in the asset's field profiles, the human cleaning spec, and the
2.21 target long-table schema, then asks for a single DuckDB SELECT that maps the
raw table(s) onto that schema. The SQL is always run through the locked-down
``duck`` kernel for a preview — the generated query is never trusted blindly.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.dataeng.duck import run_clean_sql
from app.dataeng.sources import asset_tables
from app.domain.models import CleaningSpec, SqlDraft
from app.ingest.dataset import COLUMN_NAMES
from app.llm.volcano import get_llm

# Human-readable meaning of the 2.21 long-table columns the SQL must emit.
_SCHEMA_DOC = {
    "task_name": "数据来源任务名 (可用源文件名)",
    "brand": "品牌 (模型颗粒度)",
    "province_group": "省份组别/大区 (模型颗粒度)",
    "channel_type": "渠道类型 (如 MT/TT/EC)",
    "channel": "渠道 (细分)",
    "year": "年 (整数, 如 2023)",
    "month": "时间 yyyymm 整数 (如 202301);若源是 '2023-01' 需转成 202301",
    "source": "数据来源标识 (填 'upload')",
    "l1": "因子树 Level1", "l2": "Level2", "l3": "Level3", "l4": "Level4",
    "l5": "下钻 Level5 (无则空串)", "l6": "Level6", "l7": "Level7", "l8": "Level8",
    "metric_type": "指标建模角色: 'Y'(本品销量/KPI) | 'spending'(花费) | 'X'(其他驱动)",
    "metric": "指标名称",
    "value": "数值 (float)",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _target_schema(spec: CleaningSpec | None) -> list[str]:
    if spec and spec.target_schema:
        return spec.target_schema
    return list(COLUMN_NAMES)


def _spec_text(spec: CleaningSpec | None) -> str:
    if not spec or not spec.rules:
        return "(无显式清洗规则 — 请按字段名与样本值合理推断映射。)"
    lines = []
    for r in spec.rules:
        if not r.enabled:
            continue
        src = r.source_field or "(常量/合成)"
        lines.append(
            f"- 源字段「{src}」→ 目标列「{r.target_column}」"
            f" [{r.transform}] na={r.na_policy} dtype={r.dtype or '自动'}"
            + (f" 规则: {r.rule}" if r.rule else "")
            + (f" 主数据: {r.master_data_ref}" if r.master_data_ref else "")
        )
    return "\n".join(lines) or "(规则均被禁用)"


def _profiles_text(asset) -> str:
    rep = asset.review
    if rep is None or not rep.fields:
        # Fall back to raw table column lists.
        return "\n".join(
            f"表 {t.name} ({t.row_count} 行): {', '.join(t.columns)}" for t in asset.raw_tables
        ) or "(无字段画像)"
    lines = []
    for t in asset.raw_tables:
        lines.append(f"表 {t.name} ({t.row_count} 行):")
        for f in rep.fields:
            if f.table != t.name:
                continue
            samp = ", ".join(f.sample_values[:4])
            extra = ""
            if f.is_time_axis:
                extra = f" [时间轴 {f.time_granularity}]"
            elif f.cv is not None:
                extra = f" [CV={f.cv}]"
            lines.append(f"  · {f.name} ({f.dtype}){extra} 样本: {samp}")
    return "\n".join(lines)


def build_prompt(asset, spec: CleaningSpec | None) -> tuple[str, str]:
    schema = _target_schema(spec)
    schema_doc = "\n".join(f"  {c}: {_SCHEMA_DOC.get(c, '')}" for c in schema)
    table_names = ", ".join(t.name for t in asset.raw_tables) or "raw"
    system = (
        "你是数据工程智能体。根据原始表的字段画像与清洗规则,生成 **一条 DuckDB SQL** "
        "(单条 SELECT/WITH 查询),把原始数据清洗、长表化为给定的统一长表 schema。"
        "严格要求:只用 SELECT/WITH;不得使用 DDL/DML、PRAGMA、ATTACH、COPY、read_csv/"
        "read_parquet 等任何外部访问函数;输出列必须正好是目标 schema 列且同名;"
        "时间统一为 yyyymm 整数;数值转 float;缺失维度填空串 ''。"
    )
    user = (
        f"可用原始表: {table_names}\n\n"
        f"字段画像:\n{_profiles_text(asset)}\n\n"
        f"清洗规则:\n{_spec_text(spec)}\n\n"
        f"目标长表 schema (输出列, 顺序):\n{schema_doc}\n\n"
        '返回 JSON: {"sql": "<一条 DuckDB SELECT 查询>"}'
    )
    return system, user


async def generate_sql(project_id: str, asset) -> SqlDraft:
    """Ask the LLM for cleaning SQL, then preview it through the sandbox."""
    system, user = build_prompt(asset, asset.cleaning_spec)
    try:
        obj = await get_llm().json(system=system, user=user)
    except Exception as e:  # noqa: BLE001 — surface as a draft error, don't crash
        return SqlDraft(sql="", status="error", error=f"LLM unavailable: {e}",
                        generatedAt=_now_iso())
    sql = ""
    if isinstance(obj, dict):
        sql = str(obj.get("sql") or "").strip()
    elif isinstance(obj, str):
        sql = obj.strip()
    if not sql:
        return SqlDraft(sql="", status="error", error="模型未返回 SQL", generatedAt=_now_iso())
    return run_preview(project_id, asset, sql)


def run_preview(project_id: str, asset, sql: str) -> SqlDraft:
    """Execute `sql` against the asset's raw tables for a preview (no materialise)."""
    tables = asset_tables(project_id, asset)
    res = run_clean_sql(sql, tables, materialize=False)
    if not res.ok:
        return SqlDraft(sql=sql, status="error", error=res.error, generatedAt=_now_iso())
    return SqlDraft(
        sql=sql, status="ok", error="",
        previewColumns=res.columns, previewRows=res.preview, rowCount=res.row_count,
        generatedAt=_now_iso(),
    )
