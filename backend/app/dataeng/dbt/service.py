"""Asset-level orchestration of the dbt workspace.

Bridges a ``DataAsset`` to its dbt workspace: loads the asset's raw uploads into
the warehouse, runs / AI-drafts the models, summarises the build for the UI, and
publishes the mart to parquet through the same versioning the legacy path uses.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from app.dataeng import assets as asset_svc
from app.dataeng.dbt import compiler, executor, target_schema
from app.dataeng.dbt.workspace import Workspace
from app.dataeng.duck import sanitize_ident
from app.agents.indicator_metadata import (
    INDICATOR_META_RULE_VERSION, classify_indicator,
)
from app.dataeng import indicators
from app.domain.models import (
    DataAsset, DataAssetVersion, DbtNode, DbtSummary, EnumMapEntry, EnumViolation,
    IndicatorCoverage, SchemaConformance,
)


class DbtServiceError(Exception):
    """Raised for operations that cannot proceed (no sources, no mart, gate fail)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _mart_name(asset: DataAsset) -> str:
    return f"asset_{sanitize_ident(asset.name or asset.id)}"


def _source_labels(project_id: str, asset: DataAsset) -> dict[str, str]:
    """Raw table name → the origin label stamped onto its rows during compilation.

    Derived from the live source read, not from ``asset.raw_tables``: that field is
    only written by Run Review, so before a review the labels degraded to bare table
    names — and provenance that depends on having clicked a different button is not
    provenance.
    """
    from app.dataeng.sources import source_labels
    return source_labels(source_read(project_id, asset))


def source_read(project_id: str, asset: DataAsset):
    """The asset's parsed uploads (memoised) — the one reading of the files."""
    from app.dataeng import preview
    return preview.cached_sources(project_id, asset)


def sync_raw(project_id: str, asset: DataAsset) -> Workspace:
    """Materialise the asset's uploaded sources into the workspace ``raw`` schema.

    Also re-points any pipeline input stranded by the pre-stable table naming, so
    a pipeline saved under the old scheme compiles instead of failing on a source
    that no longer exists.
    """
    from app.dataeng.sources import heal_pipeline_inputs
    ws = Workspace(project_id, asset.id).ensure()
    read = source_read(project_id, asset)
    tables = read.tables
    if not tables:
        detail = "; ".join(f"{i.filename or i.file_id}: {i.reason}" for i in read.issues[:3])
        raise DbtServiceError(
            f"None of this asset's files could be read as a table — {detail}" if detail
            else "This asset has no usable raw sources yet — upload files first.")
    heal_pipeline_inputs(asset.pipeline, tables)
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
                raw_columns=ws.raw_tables_info(), source_labels=_source_labels(project_id, asset))
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
        source_labels=_source_labels(project_id, asset),
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
                    raw_columns=ws.raw_tables_info(), source_labels=_source_labels(project_id, asset))
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


# Above this the model's match is taken as settled; below it a human confirms.
AI_AUTO_ACCEPT = 0.85
_SUGGEST_VALUE_CAP = 200


async def suggest_enum_map(st, project_id: str, asset: DataAsset, pipe, upstream: str,
                           field: str, target_column: str,
                           existing: list[EnumMapEntry] | None = None) -> tuple[list, str]:
    """Suggest raw→canonical mappings for a field, grounded on what reaches the step.

    Reads the values from the **pipeline stream** rather than the raw workbooks: an
    enum step usually sits downstream of a field map, so the column it standardises
    no longer exists under that name in any source file — the old raw-file scan just
    returned nothing there, and the editor read that empty list as "clear the map".

    Human decisions are never overwritten; the model only fills what is undecided.
    Returns ``(entries, error)``.
    """
    from app.dataeng import preview
    from app.dataeng.dbt import pipeline_ai
    schema = target_schema.schema_for(st)
    std = next((c.standard_values for c in schema if c.name == target_column), [])
    values, error = preview.column_values(st, project_id, asset, pipe, upstream, field)
    if error:
        return [], error
    if not values:
        return [], f"No values found in {field!r} at this point in the pipeline."

    decided = {e.raw: e for e in (existing or [])}
    settled = {raw for raw, e in decided.items()
               if e.by == "human" and e.canonical.strip() and e.status == "accepted"}
    to_map = [v for v, _ in values if v not in settled][:_SUGGEST_VALUE_CAP]
    suggested = {e.raw: e for e in await pipeline_ai.suggest_enum_map(field, to_map, std)}

    out: list[EnumMapEntry] = []
    for raw, _n in values:
        if raw in settled:
            out.append(decided[raw])
            continue
        s = suggested.get(raw)
        if s is None:
            out.append(decided.get(raw) or EnumMapEntry(raw=raw, canonical="", confidence=0.0,
                                                        by="ai", status="proposed"))
            continue
        confident = bool(s.canonical.strip()) and s.confidence >= AI_AUTO_ACCEPT
        out.append(EnumMapEntry(raw=raw, canonical=s.canonical, confidence=s.confidence,
                                by="ai", status="accepted" if confident else "proposed"))
    # Rows for values that no longer flow through this step are the user's own data —
    # keep them rather than deleting decisions behind their back.
    seen = {e.raw for e in out}
    out.extend(e for raw, e in decided.items() if raw not in seen)
    return out, ""


def full_sql(st, project_id: str, asset: DataAsset,
             pipe=None) -> tuple[str, str]:
    """The whole pipeline as one self-contained ``WITH`` query. Returns ``(sql, error)``.

    This is the same compilation the sandbox preview runs, taken to the output step —
    so what is exported is what the pipeline actually does, not a re-description of
    it. A header maps each bare table name back to the file and sheet it reads, so
    the SQL still says where its inputs came from once it leaves this product.
    """
    from app.dataeng.sources import source_labels
    pipeline = pipe if pipe is not None else asset.pipeline
    if pipeline is None or not pipeline.steps:
        return "", "This asset has no transform steps yet."
    read = source_read(project_id, asset)
    tables = read.tables
    if not tables:
        return "", "This asset has no readable raw sources."
    labels = source_labels(read)
    try:
        body = compiler.compile_preview_sql(
            pipeline, pipeline.output_step or pipeline.steps[-1].id,
            target_schema=target_schema.schema_for(st),
            raw_columns={n: [str(c) for c in df.columns] for n, df in tables.items()},
            source_labels=labels)
    except compiler.CompileError as e:
        return "", str(e)

    header = [f"-- {asset.name} — compiled transform pipeline",
              f"-- generated {_now_iso()}", "-- inputs:"]
    for meta, _ in read.pairs:
        origin = f"{meta.filename}" + (f" · sheet {meta.sheet}" if meta.sheet else "")
        header.append(f"--   {meta.name}: {origin} ({meta.row_count} rows) "
                      f"→ source = '{labels.get(meta.name, '')}'")
    return "\n".join(header) + "\n\n" + body + "\n", ""


_SAMPLE_ROWS = 5


async def suggest_field_map(st, project_id: str, asset: DataAsset, pipe, upstream: str,
                            existing: list[FieldMapEntry] | None = None
                            ) -> tuple[list[FieldMapEntry], str]:
    """Match the upstream's columns onto the target schema. Returns ``(entries, error)``.

    Rows a human already wrote are kept exactly as they are and their targets are
    taken off the table, so a suggestion can add to the work but never overwrite it.
    """
    from app.dataeng import preview
    from app.dataeng.dbt import pipeline_ai
    columns, error = preview.input_columns(st, project_id, asset, pipe, upstream)
    if error:
        return [], error
    if not columns:
        return [], "This step's input has no columns yet."

    kept = [e for e in (existing or []) if e.by == "human" and (e.source or e.expr)]
    claimed = {e.target for e in kept if e.target}
    mapped_src = {e.source for e in kept if e.source}
    targets, docs = target_schema.columns_and_docs(st)

    res = preview.preview_step(st, project_id, asset, pipe, upstream, limit=_SAMPLE_ROWS)
    samples: dict[str, list[str]] = {}
    if res.ok:
        for i, name in enumerate(res.columns):
            samples[name] = [str(r[i]) for r in res.rows[:_SAMPLE_ROWS] if i < len(r)]

    fresh = await pipeline_ai.suggest_field_map(
        [c for c in columns if c not in mapped_src],
        [t for t in targets if t not in claimed], docs, samples)
    return kept + [e for e in fresh if e.target not in claimed], ""


async def suggest_sql(st, project_id: str, asset: DataAsset, pipe, step_id: str,
                      instruction: str) -> tuple[str, str]:
    """Draft a ``custom_sql`` step body from plain English. Returns ``(sql, error)``.

    The generated statement is compiled and run in the sandbox before it is handed
    back — the safety layer that rejects anything but a read-only SELECT is the same
    one every preview goes through, so free-form model output cannot reach the data
    on a path the rest of the editor does not already trust.
    """
    from app.dataeng import preview
    from app.dataeng.dbt import pipeline_ai
    step = next((s for s in (pipe.steps if pipe else []) if s.id == step_id), None)
    if step is None:
        return "", f"step {step_id!r} is not in this pipeline"

    inputs: dict[str, list[str]] = {}
    for i, inp in enumerate(step.inputs, start=1):
        cols, err = preview.input_columns(st, project_id, asset, pipe, inp)
        if err:
            return "", err
        inputs[f"input_{i}"] = cols
    if not inputs:
        return "", "Connect an input to this step first."

    targets, docs = target_schema.columns_and_docs(st)
    sql, error = await pipeline_ai.suggest_sql(instruction, inputs, targets, docs)
    if error:
        return "", error

    trial = step.model_copy(update={"sql": sql})
    trial_pipe = pipe.model_copy(update={
        "steps": [trial if s.id == step_id else s for s in pipe.steps]})
    res = preview.preview_step(st, project_id, asset, trial_pipe, step_id, limit=1)
    if not res.ok:
        return "", f"The generated SQL does not run: {res.error}"
    return sql, ""


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
    """The editor's view of the asset: available raw sources + workspace files.

    Sources are derived from the **uploaded files**, not from the dbt warehouse.
    The warehouse's ``raw`` schema is only written by a build, so reading the source
    list from it meant a freshly uploaded workbook stayed invisible in the editor
    until the user happened to run a build — with nothing saying why.
    """
    from app.dataeng.sources import source_labels
    ws = Workspace(project_id, asset.id)
    seeds = ws.list_seeds()
    read = source_read(project_id, asset)
    labels = source_labels(read)
    return {
        "models": [
            {"layer": m.layer, "name": m.name, "sql": m.sql, "description": _extract_desc(m.sql)}
            for m in ws.list_models()
        ],
        "sources": [meta.name for meta, _ in read.pairs],
        "sourceTables": [
            {"name": meta.name, "filename": meta.filename, "fileId": meta.file_id,
             "sheet": meta.sheet, "sourceLabel": labels.get(meta.name, meta.filename),
             "rowCount": meta.row_count, "columns": list(meta.columns)}
            for meta, _ in read.pairs
        ],
        "sourceIssues": [
            {"fileId": i.file_id, "filename": i.filename, "reason": i.reason}
            for i in read.issues
        ],
        "seeds": [{"name": n, "columns": cols, "csv": ws.read_seed(n) or ""}
                  for n, cols in seeds.items()],
    }


def write_model(project_id: str, asset: DataAsset, layer: str, name: str, sql: str) -> None:
    from app.dataeng.dbt.workspace import ModelFile
    Workspace(project_id, asset.id).ensure().write_model(
        ModelFile(layer=layer, name=name, sql=sql))
    _touch(asset)


def write_seed(project_id: str, asset: DataAsset, name: str, csv: str) -> None:
    Workspace(project_id, asset.id).ensure().write_seed(name, csv)
    _touch(asset)


def preview(project_id: str, asset: DataAsset, model: str, limit: int = 50) -> dict:
    ws = Workspace(project_id, asset.id)
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
    ws = Workspace(project_id, asset.id)
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
    claim_published_metrics(st, asset, df)
    asset_svc._invalidate(project_id)
    return ver


def _norm_path(*parts: str) -> str:
    return "|".join("".join(str(p).lower().split()) for p in parts)


def _indicator_id(asset_id: str, vals: dict) -> str:
    """A stable id for one (asset × metric × factor path).

    Derived from identity, not from position in the group-by. A positional id
    (``ind-<asset>-<n>``) was reshuffled by every re-publish, so a stored
    ``indicatorId`` could silently come to mean a different metric.
    """
    key = "|".join(str(vals.get(k, "")) for k in
                   ("metric", "metric_type", "l1", "l2", "l3", "l4"))
    return f"ind-{asset_id}-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:10]}"


def claim_published_metrics(st, asset: DataAsset, df: pd.DataFrame) -> list[IndicatorCoverage]:
    """Attach this asset's metrics to the factor rows they supply.

    Publish no longer *creates* indicators — the factor tree already declared
    them (``app/dataeng/indicators.py``). Each (metric × factor path) in the mart
    claims the row it matches, recorded as an ``IndicatorCoverage``; anything
    that matches nothing is an orphan (``tree_row_id == ""``) and is offered back
    to the tree rather than presented as a project indicator.

    Replaces this asset's prior coverage — but a human's row binding is a
    decision, not derived state, so it is carried across by id rather than
    discarded on every publish.
    """
    pins = {c.id: c.tree_row_id for c in st.indicator_coverage
            if c.asset_id == asset.id and c.bound_by == "human" and c.tree_row_id}
    st.indicator_coverage = [c for c in st.indicator_coverage if c.asset_id != asset.id]
    if "metric" not in df.columns:
        return []

    # Factor-tree lookup: full L1–L4 path first, then L3-only as a looser anchor.
    tree_rows = [r for r in (st.factor_tree.rows if getattr(st, "factor_tree", None) else [])
                 if r.status in indicators.ACTIVE_STATUSES]
    by_path = {_norm_path(r.l1, r.l2, r.l3, r.l4): r for r in tree_rows}
    by_l3 = {}
    for r in tree_rows:
        if r.l3:
            by_l3.setdefault(_norm_path(r.l3), r)

    key_cols = [c for c in ("metric", "metric_type", "l1", "l2", "l3", "l4") if c in df.columns]
    period = df["month"] if "month" in df.columns else (df["year"] if "year" in df.columns else None)
    new: list[IndicatorCoverage] = []
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
        # FND-001: classify the metric's semantic profile (type/unit/aggregation/
        # format) from its name once, at publish, so downstream reads metadata
        # rather than re-guessing. The OLS role (`metricType`) is left as-is.
        meta = classify_indicator(str(vals.get("metric", "")))
        cov_id = _indicator_id(asset.id, vals)
        pinned = pins.get(cov_id, "")
        new.append(IndicatorCoverage(
            id=cov_id,
            treeRowId=pinned or (row.id if row is not None else ""),
            assetId=asset.id, assetName=asset.name,
            metric=str(vals.get("metric", "")),
            metricType=str(vals.get("metric_type", "")),
            l1=str(vals.get("l1", "")), l2=str(vals.get("l2", "")),
            l3=str(vals.get("l3", "")), l4=str(vals.get("l4", "")),
            semanticType=meta.metric_type, unit=meta.unit, currency=meta.currency,
            aggregation=meta.aggregation, numberFormat=meta.fmt,
            ruleVersion=INDICATOR_META_RULE_VERSION,
            coverageStart=cov_start, coverageEnd=cov_end, rows=int(len(grp)),
            boundBy="human" if pinned else ("auto" if row is not None else ""),
        ))
    st.indicator_coverage.extend(new)
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
