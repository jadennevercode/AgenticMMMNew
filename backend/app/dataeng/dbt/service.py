"""Asset-level orchestration of the dbt workspace.

Bridges a ``DataAsset`` to its dbt workspace: loads the asset's raw uploads into
the warehouse, runs / AI-drafts the models, summarises the build for the UI, and
publishes the mart to parquet through the same versioning the legacy path uses.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from app.dataeng import assets as asset_svc
from app.dataeng.dbt import compiler, executor, target_schema
from app.dataeng.dbt.workspace import Workspace
from app.dataeng.duck import sanitize_ident
from app.dataeng.sources import asset_tables
from app.agents.indicator_metadata import (
    INDICATOR_META_RULE_VERSION, classify_indicator,
)
from app.domain.models import (
    DataAsset, DataAssetVersion, DbtNode, DbtSummary, EnumViolation, Indicator,
    SchemaConformance,
)


class DbtServiceError(Exception):
    """Raised for operations that cannot proceed (no sources, no mart, gate fail)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _mart_name(asset: DataAsset) -> str:
    return f"asset_{sanitize_ident(asset.name or asset.id)}"


def _source_labels(asset: DataAsset) -> dict[str, str]:
    """Raw table name → a human source label (the uploaded file's name) for
    stamping per-row provenance during compilation."""
    return {t.name: (t.filename or t.name) for t in asset.raw_tables}


def sync_raw(project_id: str, asset: DataAsset) -> Workspace:
    """Materialise the asset's uploaded sources into the workspace ``raw`` schema."""
    ws = Workspace(project_id).ensure()
    tables = asset_tables(project_id, asset)
    if not tables:
        raise DbtServiceError("This asset has no usable raw sources yet — upload files first.")
    ws.load_raw(tables)
    return ws


def _summary(res: executor.DbtResult, ws: Workspace, *, ai_rounds: int = 0,
             step_models: Optional[dict[str, str]] = None) -> DbtSummary:
    layer_of = {m.name: m.layer for m in ws.list_models()}
    nodes = [
        DbtNode(
            uniqueId=n.unique_id, resourceType=n.resource_type, name=n.name,
            layer=layer_of.get(n.name, ""), status=n.status,
            executionTime=round(n.execution_time, 3), message=n.message,
            failures=n.failures, relation=n.relation,
        )
        for n in res.nodes
    ]
    models = [n for n in res.nodes if n.resource_type == "model"]
    tests = res.tests
    marts = [m.name for m in ws.list_models() if m.layer == "marts"]
    return DbtSummary(
        ok=res.ok, ranAt=_now_iso(), command=res.command, error=res.error,
        mart=(marts[-1] if marts else ""),
        models=len(models), tests=len(tests),
        passed=sum(1 for t in tests if t.ok),
        failed=sum(1 for t in tests if not t.ok),
        aiRounds=ai_rounds, nodes=nodes, stepModels=step_models or {},
    )


def apply_compiled(ws: Workspace, proj: compiler.CompiledProject) -> None:
    """Write a compiled pipeline's files into the workspace. The compiled output
    owns both the model set and the seed set (stale files are removed)."""
    from app.dataeng.dbt.workspace import ModelFile
    ws.clear_models()
    ws.clear_seeds()
    for name, csv_text in proj.seeds:
        ws.write_seed(name, csv_text)
    for m in proj.models:
        ws.write_model(ModelFile(m.layer, m.name, m.sql))
    ws.write_schema_yml(proj.schema_yml)


def build(st, project_id: str, asset: DataAsset) -> DbtSummary:
    """Compile the asset's pipeline (when present), load raw, run ``dbt build``,
    and record the summary. Without a pipeline the existing workspace files run
    as-is (hand-authored dbt is still allowed)."""
    ws = sync_raw(project_id, asset)
    step_models: dict[str, str] = {}
    if asset.pipeline is not None and asset.pipeline.steps:
        try:
            proj = compiler.compile_pipeline(
                asset.pipeline, _mart_name(asset), target_schema.schema_for(st),
                raw_columns=ws.raw_tables_info(), source_labels=_source_labels(asset))
        except compiler.CompileError as e:
            asset.dbt = DbtSummary(ok=False, ranAt=_now_iso(), error=f"Pipeline invalid: {e}")
            _touch(asset)
            return asset.dbt
        apply_compiled(ws, proj)
        step_models = proj.step_models
    res = executor.build(ws)
    summary = _summary(res, ws, step_models=step_models)
    # Only judge conformance off a mart that actually built this run — never a stale
    # relation left in the warehouse by an earlier (now-failed) build.
    mart_ok = any(n.resource_type == "model" and n.name == summary.mart and n.ok
                  for n in res.nodes)
    summary.conformance = (_check_conformance(st, ws, summary.mart) if mart_ok
                           else SchemaConformance(ok=False, checked=False))
    asset.dbt = summary
    _touch(asset)
    return asset.dbt


# period_date is a compiler-derived helper axis, not a target-schema column.
_ALLOWED_EXTRA = {"period_date"}
_VIOLATION_CAP = 20


def _check_conformance(st, ws: Workspace, mart: str) -> SchemaConformance:
    """Strictly compare the materialised mart to the target schema — required field
    presence + every standard-valued column's values ⊆ its standard set."""
    schema = target_schema.schema_for(st)
    if not mart or not ws.warehouse_path.exists():
        return SchemaConformance(ok=False, checked=False)
    try:
        df = ws.read_relation(mart)
    except Exception:  # noqa: BLE001 — mart not materialised (build failed early)
        return SchemaConformance(ok=False, checked=False)

    cols = set(df.columns)
    required = [c.name for c in schema if c.required]
    schema_names = {c.name for c in schema}
    missing = [c for c in required if c not in cols]
    extra = [c for c in df.columns if c not in schema_names and c not in _ALLOWED_EXTRA]

    violations: list[EnumViolation] = []
    unenforced: list[str] = []
    for c in schema:
        if c.kind not in ("dimension", "factor"):
            continue
        if not c.standard_values:
            if c.name in cols:
                unenforced.append(c.name)
            continue
        if c.name not in cols:
            continue
        allowed = set(c.standard_values)
        seen = {str(v) for v in df[c.name].dropna().unique()}
        bad = sorted(v for v in seen if v not in allowed)
        if bad:
            violations.append(EnumViolation(column=c.name, values=bad[:_VIOLATION_CAP]))

    ok = not missing and not violations
    return SchemaConformance(
        ok=ok, checked=True, missingRequired=missing, extra=extra,
        enumViolations=violations, unenforcedDimensions=unenforced,
    )


async def ai_pipeline(st, project_id: str, asset: DataAsset,
                      instruction: str = "") -> DbtSummary:
    """AI-draft (or, when a pipeline already exists, adjust) the asset's transform
    pipeline as structured steps, compile + build it with a repair loop, and record
    both the pipeline and the build summary on the asset."""
    from app.dataeng.dbt import pipeline_ai
    ws = sync_raw(project_id, asset)
    columns, docs = target_schema.columns_and_docs(st)
    schema = target_schema.schema_for(st)
    ctx = pipeline_ai.DraftContext(
        raw_tables=ws.raw_tables_info(),
        profiles_text=_profiles_text(asset),
        target_columns=columns,
        target_doc=docs,
        standard_values={c.name: c.standard_values for c in schema if c.standard_values},
        mart_name=_mart_name(asset),
        instruction=instruction,
        current=asset.pipeline if (asset.pipeline and asset.pipeline.steps) else None,
        source_labels=_source_labels(asset),
    )
    res = await pipeline_ai.draft(ws, ctx, schema)
    if res.pipeline is not None:
        asset.pipeline = res.pipeline
    if res.build is not None:
        step_models = {}
        mart = ""
        if res.pipeline is not None:
            try:
                compiled = compiler.compile_pipeline(
                    res.pipeline, _mart_name(asset), schema,
                    raw_columns=ws.raw_tables_info(), source_labels=_source_labels(asset))
                step_models = compiled.step_models
                mart = _mart_name(asset)
            except compiler.CompileError:
                step_models = {}
        asset.dbt = _summary(res.build, ws, ai_rounds=res.rounds, step_models=step_models)
        mart_name = mart or asset.dbt.mart
        mart_ok = any(n.resource_type == "model" and n.name == mart_name and n.ok
                      for n in res.build.nodes)
        asset.dbt.conformance = (_check_conformance(st, ws, mart_name) if mart_ok
                                 else SchemaConformance(ok=False, checked=False))
        if not res.ok:
            asset.dbt.error = res.error or asset.dbt.error
    else:
        asset.dbt = DbtSummary(ok=False, ranAt=_now_iso(), error=res.error,
                               aiRounds=res.rounds)
    _touch(asset)
    return asset.dbt


async def suggest_enum_map(st, project_id: str, asset: DataAsset, field: str,
                           target_column: str) -> list:
    """Suggest raw→canonical mappings for a field: raw distinct values from the
    asset's sources vs the target column's maintained standard values."""
    from app.dataeng.dbt import pipeline_ai
    schema = target_schema.schema_for(st)
    std = next((c.standard_values for c in schema if c.name == target_column), [])
    raw_values: list[str] = []
    for _, df in asset_tables(project_id, asset).items():
        if field in df.columns:
            vals = df[field].dropna().astype(str).unique().tolist()
            raw_values.extend(v for v in vals if v not in raw_values)
    raw_values = raw_values[:200]
    return await pipeline_ai.suggest_enum_map(field, raw_values, std)


def _extract_desc(sql: str) -> str:
    """Pull the leading ``-- desc: ...`` plain-English annotation from a model."""
    for line in sql.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("-- desc:"):
            return s.split(":", 1)[1].strip()
        break
    return ""


def list_models(project_id: str, asset: DataAsset) -> dict:
    ws = Workspace(project_id)
    seeds = ws.list_seeds()
    return {
        "models": [
            {"layer": m.layer, "name": m.name, "sql": m.sql, "description": _extract_desc(m.sql)}
            for m in ws.list_models()
        ],
        "sources": list(ws.raw_tables_info().keys()),
        "seeds": [{"name": n, "columns": cols, "csv": ws.read_seed(n) or ""}
                  for n, cols in seeds.items()],
    }


def write_model(project_id: str, asset: DataAsset, layer: str, name: str, sql: str) -> None:
    from app.dataeng.dbt.workspace import ModelFile
    Workspace(project_id).ensure().write_model(ModelFile(layer=layer, name=name, sql=sql))
    _touch(asset)


def write_seed(project_id: str, asset: DataAsset, name: str, csv: str) -> None:
    Workspace(project_id).ensure().write_seed(name, csv)
    _touch(asset)


def preview(project_id: str, asset: DataAsset, model: str, limit: int = 50) -> dict:
    ws = Workspace(project_id)
    if not ws.warehouse_path.exists():
        raise DbtServiceError("No build output yet — run a build first.")
    try:
        df = ws.read_relation(model, limit=limit)
    except Exception as e:  # noqa: BLE001
        raise DbtServiceError(f"Cannot preview {model}: {e}") from e
    return _df_payload(df)


def publish(project_id: str, st, asset: DataAsset) -> DataAssetVersion:
    """Gate on a green build, then materialise the mart to parquet as a new version."""
    summary = build(st, project_id, asset)
    if not summary.ok:
        raise DbtServiceError(
            f"Build / validation failed — cannot publish: {summary.error or 'some tests failed'}")
    if not summary.mart:
        raise DbtServiceError("No marts-layer model, so there is no asset table to publish.")
    conf = summary.conformance
    if conf is not None and not conf.ok:
        parts = []
        if conf.missing_required:
            parts.append(f"missing required columns: {', '.join(conf.missing_required)}")
        if conf.enum_violations:
            parts.append("values outside the target schema's standard set in "
                         + ", ".join(v.column for v in conf.enum_violations))
        raise DbtServiceError(
            "Output does not strictly map to the target schema — " + "; ".join(parts)
            + ". Map these in the Transform step before publishing.")
    ws = Workspace(project_id)
    df = ws.read_relation(summary.mart)
    if df.empty:
        raise DbtServiceError("The mart is empty — nothing to publish.")

    version = asset.latest_version + 1
    rel_path = f"projects/{project_id}/assets/{asset.id}/v{version}.parquet"
    abs_path = asset_svc.get_settings().data_path / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(abs_path, index=False)

    ver = DataAssetVersion(
        version=version, parquetPath=rel_path, rowCount=int(len(df)),
        columns=[str(c) for c in df.columns], sql=f"dbt mart {summary.mart}",
        producedAt=_now_iso(),
    )
    asset.versions.append(ver)
    asset.latest_version = version
    asset.status = "published"
    _touch(asset)
    register_indicators(st, asset, df)
    asset_svc._invalidate(project_id)
    return ver


def _norm_path(*parts: str) -> str:
    return "|".join("".join(str(p).lower().split()) for p in parts)


def register_indicators(st, asset: DataAsset, df: pd.DataFrame) -> list[Indicator]:
    """Register one indicator per (metric × factor path) in the published mart, so
    Data Intake can reference indicators instead of raw files. Each indicator is
    grounded against the Business-Understanding factor tree when a row matches
    (unmatched ones are flagged for review). Replaces this asset's prior indicators."""
    st.indicators = [ind for ind in st.indicators if ind.asset_id != asset.id]
    if "metric" not in df.columns:
        return []

    # Factor-tree lookup: full L1–L4 path first, then L3-only as a looser anchor.
    tree_rows = (st.factor_tree.rows if getattr(st, "factor_tree", None) else [])
    by_path = {_norm_path(r.l1, r.l2, r.l3, r.l4): r for r in tree_rows}
    by_l3 = {}
    for r in tree_rows:
        if r.l3:
            by_l3.setdefault(_norm_path(r.l3), r)

    key_cols = [c for c in ("metric", "metric_type", "l1", "l2", "l3", "l4") if c in df.columns]
    period = df["month"] if "month" in df.columns else (df["year"] if "year" in df.columns else None)
    new: list[Indicator] = []
    for keys, grp in df.groupby(key_cols, dropna=False):
        vals = dict(zip(key_cols, keys if isinstance(keys, tuple) else (keys,)))
        cov_start = cov_end = ""
        if period is not None:
            sub = period.loc[grp.index].dropna()
            if not sub.empty:
                cov_start, cov_end = str(sub.min()), str(sub.max())
        row = (by_path.get(_norm_path(vals.get("l1", ""), vals.get("l2", ""),
                                      vals.get("l3", ""), vals.get("l4", "")))
               or by_l3.get(_norm_path(vals.get("l3", ""))))
        # FND-001: classify the indicator's semantic profile (type/unit/aggregation/
        # format) from its metric name once, at publish, so downstream reads metadata
        # rather than re-guessing. The OLS role (`metricType`) is left as-is.
        meta = classify_indicator(str(vals.get("metric", "")))
        ind = Indicator(
            id=f"ind-{asset.id}-{len(new)}",
            metric=str(vals.get("metric", "")),
            metricType=str(vals.get("metric_type", "")),
            l1=str(vals.get("l1", "")), l2=str(vals.get("l2", "")),
            l3=str(vals.get("l3", "")), l4=str(vals.get("l4", "")),
            semanticType=meta.metric_type, unit=meta.unit, currency=meta.currency,
            aggregation=meta.aggregation, numberFormat=meta.fmt, source="data_upload",
            ruleVersion=INDICATOR_META_RULE_VERSION,
            assetId=asset.id, assetName=asset.name,
            coverageStart=cov_start, coverageEnd=cov_end, rows=int(len(grp)),
            treeGrounded=row is not None, treeRowId=(row.id if row is not None else ""),
        )
        new.append(ind)
    st.indicators.extend(new)
    return new


# ── helpers ──────────────────────────────────────────────
def _touch(asset: DataAsset) -> None:
    asset.updated_at = _now_iso()


def _df_payload(df: pd.DataFrame, cap: int = 50) -> dict:
    head = df.head(cap)
    return {
        "columns": [str(c) for c in head.columns],
        "rows": [[_cell(v) for v in row] for row in head.itertuples(index=False, name=None)],
        "rowCount": int(len(df)),
    }


def _cell(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v)


def _profiles_text(asset: DataAsset) -> str:
    rep = asset.review
    if rep is None or not rep.fields:
        return "(no field profiles — infer the mapping from column names and sample values)"
    lines: list[str] = []
    for t in asset.raw_tables:
        lines.append(f"Table {t.name} ({t.row_count} rows):")
        for f in rep.fields:
            if f.table != t.name:
                continue
            extra = f" [time axis {f.time_granularity}]" if f.is_time_axis else (
                f" [CV={f.cv}]" if f.cv is not None else "")
            if f.enum_values:
                vals = f"ALL distinct values: {', '.join(f.enum_values)}"
            else:
                vals = f"samples: {', '.join(f.sample_values[:4])}"
            lines.append(f"  · {f.name} ({f.dtype}){extra} {vals}")
    return "\n".join(lines)
