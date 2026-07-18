"""Compile a TransformPipeline into a dbt project — deterministically.

Each step becomes one dbt model; enum_map steps also emit a seed. The human sees
and edits typed step configs; this module turns them into SQL, so the SQL on the
main path is never AI-authored free text (custom_sql is the explicit escape hatch).

Layers: steps whose inputs are all raw sources → staging; the pipeline's output
step → marts (named after the asset); everything else → intermediate. The mart's
schema.yml auto-attaches the MMM data-quality tests plus accepted_values for any
target column that maintains standard values.

Source provenance: when the target schema carries a ``source`` column, every raw
source read is stamped with its origin (the uploaded file's name) and that stamp
is preserved through the column-dropping steps (``field_map`` carries it forward,
``aggregate`` adds it to the group-by unless the step sets ``merge_sources``). This
lets a published asset built from several files keep per-row origin, so Business
Validation can filter a chart down to a single contributing source.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from app.dataeng.duck import sanitize_ident
from app.domain.models import TargetColumn, TransformPipeline, TransformStep

SOURCE_PREFIX = "source:"
SOURCE_COL = "source"


class CompileError(Exception):
    """Raised when a pipeline is structurally invalid (cycles, bad refs, etc.)."""


@dataclass
class CompiledModel:
    layer: str          # staging | intermediate | marts
    name: str
    sql: str


@dataclass
class CompiledProject:
    models: list[CompiledModel] = field(default_factory=list)
    seeds: list[tuple[str, str]] = field(default_factory=list)   # (name, csv)
    schema_yml: str = ""
    step_models: dict[str, str] = field(default_factory=dict)    # step id → model name


def compile_pipeline(pipe: TransformPipeline, mart_name: str,
                     target_schema: list[TargetColumn] | None = None,
                     raw_columns: dict[str, list[str]] | None = None,
                     source_labels: dict[str, str] | None = None) -> CompiledProject:
    steps = {s.id: s for s in pipe.steps}
    if not steps:
        raise CompileError("pipeline has no steps")
    output_id = pipe.output_step or pipe.steps[-1].id
    if output_id not in steps:
        raise CompileError(f"output step {output_id!r} not found")

    order = _topo_order(pipe.steps)
    out = CompiledProject()
    names_used: set[str] = set()

    for idx, step in enumerate(order, start=1):
        model_name = (sanitize_ident(mart_name) if step.id == output_id
                      else _model_name(step, idx, names_used))
        names_used.add(model_name)
        out.step_models[step.id] = model_name

    schema_cols = {c.name for c in (target_schema or [])}
    has_time = "month" in schema_cols
    prov = _Provenance(enabled=SOURCE_COL in schema_cols,
                       raw_columns=raw_columns or {}, labels=source_labels or {})
    carries: dict[str, bool] = {}  # step id → its output has a `source` column

    for step in order:
        model_name = out.step_models[step.id]
        layer = ("marts" if step.id == output_id
                 else "staging" if all(i.startswith(SOURCE_PREFIX) for i in step.inputs)
                 else "intermediate")
        expanded = [_input_ref(i, out.step_models, prov, carries) for i in step.inputs]
        refs = [e[0] for e in expanded]
        inputs_carry = [e[1] for e in expanded]
        sql, seed, produces_source = _compile_step(
            step, refs, model_name, inputs_carry, prov.enabled)
        carries[step.id] = produces_source
        if seed is not None:
            out.seeds.append(seed)
        if step.id == output_id and has_time:
            # Derive a real DATE axis from the yyyymm month so the time-based
            # data-quality tests (span / granularity / yoy) have a date to key on.
            sql = ("select *, strptime(cast(\"month\" as varchar) || '01', '%Y%m%d')::date "
                   f"as period_date\nfrom (\n{sql}\n)")
        config = "{{ config(materialized='table') }}\n" if layer == "marts" else ""
        desc = f"-- desc: {step.note}\n" if step.note else ""
        out.models.append(CompiledModel(layer=layer, name=model_name,
                                        sql=f"{desc}{config}{sql}"))

    out.schema_yml = _schema_yml(out.step_models[output_id], target_schema or [],
                                 with_time=has_time, with_value="value" in schema_cols)
    return out


# ── source provenance ────────────────────────────────────
@dataclass
class _Provenance:
    """Context for stamping/carrying the `source` origin column through the DAG."""
    enabled: bool
    raw_columns: dict[str, list[str]]   # raw table name → its columns
    labels: dict[str, str]              # raw table name → human source label (filename)


def _input_ref(inp: str, step_models: dict[str, str], prov: _Provenance,
               carries: dict[str, bool]) -> tuple[str, bool]:
    """Expand one input to (sql ref, does-it-carry-a-source-column).

    A raw source is stamped with its origin label unless the raw file already has
    its own ``source`` column; an upstream input carries whatever it produced."""
    if not inp.startswith(SOURCE_PREFIX):
        return _ref(inp, step_models), carries.get(inp, False)
    ref = _ref(inp, step_models)
    if not prov.enabled:
        return ref, False
    table = sanitize_ident(inp[len(SOURCE_PREFIX):])
    cols = prov.raw_columns.get(table, [])
    if SOURCE_COL in cols:
        return ref, True  # the file supplies its own source values
    label = (prov.labels.get(table) or table).replace("'", "''")
    return f'(select *, \'{label}\' as "{SOURCE_COL}" from {ref})', True


# ── per-step SQL ─────────────────────────────────────────
def _compile_step(step: TransformStep, refs: list[str], model_name: str,
                  inputs_carry: list[bool], prov_on: bool
                  ) -> tuple[str, tuple[str, str] | None, bool]:
    if not refs and step.kind != "custom_sql":
        raise CompileError(f"step {step.id} ({step.kind}) has no inputs")
    kind = step.kind
    carry0 = bool(inputs_carry and inputs_carry[0])
    if kind == "field_map":
        return _sql_field_map(step, refs[0], prov_on and carry0)
    if kind == "enum_map":
        sql, seed = _sql_enum_map(step, refs[0], model_name)
        return sql, seed, carry0
    if kind == "join":
        right_has_source = bool(step.join and SOURCE_COL in (step.join.right_columns or []))
        return _sql_join(step, refs), None, carry0 or right_has_source
    if kind == "union":
        sql = " union all ".join(f"select * from {r}" for r in refs)
        return sql, None, bool(inputs_carry) and all(inputs_carry)
    if kind == "aggregate":
        return _sql_aggregate(step, refs[0], prov_on and carry0)
    if kind == "filter":
        expr = step.filter_expr.strip()
        if not expr:
            raise CompileError(f"filter step {step.id} has no expression")
        return f"select * from {refs[0]} where {expr}", None, carry0
    if kind == "derive":
        if not step.derive:
            raise CompileError(f"derive step {step.id} has no expressions")
        derived = ", ".join(f"{d.expr} as \"{d.name}\"" for d in step.derive)
        return f"select *, {derived} from {refs[0]}", None, carry0
    if kind == "custom_sql":
        body = step.sql.strip()
        if not body:
            raise CompileError(f"custom_sql step {step.id} is empty")
        if not refs:
            return body, None, False
        ctes = ", ".join(f"input_{i} as (select * from {r})" for i, r in enumerate(refs, 1))
        return f"with {ctes}\n{body}", None, False
    raise CompileError(f"unknown step kind {kind!r}")


def _sql_field_map(step: TransformStep, ref: str,
                   carry_source: bool) -> tuple[str, None, bool]:
    entries = [e for e in step.field_map if e.target.strip()]
    if not entries:
        raise CompileError(f"field_map step {step.id} has no mappings")
    cols = []
    for e in entries:
        expr = e.expr.strip() or f'"{e.source}"'
        if e.cast:
            expr = f"cast({expr} as {_duck_type(e.cast)})"
        cols.append(f'{expr} as "{e.target}"')
    produces_source = any(e.target.strip() == SOURCE_COL for e in entries)
    if carry_source and not produces_source:
        cols.append(f'"{SOURCE_COL}"')   # carry the upstream origin forward
        produces_source = True
    return f"select {', '.join(cols)} from {ref}", None, produces_source


def _sql_enum_map(step: TransformStep, ref: str,
                  model_name: str) -> tuple[str, tuple[str, str]]:
    fld = step.enum_field.strip()
    if not fld:
        raise CompileError(f"enum_map step {step.id} has no field")
    rows = [e for e in step.enum_map if e.raw.strip() and e.canonical.strip()]
    if not rows:
        raise CompileError(f"enum_map step {step.id} has no accepted mappings")
    seed_name = f"map_{sanitize_ident(step.name or step.id)}"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["raw", "canonical"])
    for e in rows:
        w.writerow([e.raw, e.canonical])
    sql = (
        f'select t.* replace (coalesce(m.canonical, t."{fld}") as "{fld}")\n'
        f"from {ref} t\n"
        f'left join {{{{ ref(\'{seed_name}\') }}}} m on t."{fld}" = m.raw'
    )
    return sql, (seed_name, buf.getvalue())


def _sql_join(step: TransformStep, refs: list[str]) -> str:
    if len(refs) != 2:
        raise CompileError(f"join step {step.id} needs exactly 2 inputs, got {len(refs)}")
    cfg = step.join
    if cfg is None or not cfg.left_on or len(cfg.left_on) != len(cfg.right_on or cfg.left_on):
        raise CompileError(f"join step {step.id} has invalid keys")
    right_on = cfg.right_on or cfg.left_on
    on = " and ".join(f'l."{a}" = r."{b}"' for a, b in zip(cfg.left_on, right_on))
    right_cols = "".join(f', r."{c}"' for c in cfg.right_columns)
    return (f"select l.*{right_cols}\nfrom {refs[0]} l\n"
            f"{cfg.how} join {refs[1]} r on {on}")


def _sql_aggregate(step: TransformStep, ref: str,
                   carry_source: bool) -> tuple[str, None, bool]:
    if not step.group_by or not step.aggs:
        raise CompileError(f"aggregate step {step.id} needs group_by and aggs")
    group_cols = list(step.group_by)
    # Keep per-source granularity so charts can filter to one contributing file,
    # unless the step explicitly opts to merge sources.
    if carry_source and not step.merge_sources and SOURCE_COL not in group_cols:
        group_cols.append(SOURCE_COL)
    groups = ", ".join(f'"{g}"' for g in group_cols)
    aggs = ", ".join(
        f'{a.func}("{a.column}") as "{a.alias or a.column}"' for a in step.aggs)
    return f"select {groups}, {aggs} from {ref} group by {groups}", None, SOURCE_COL in group_cols


# ── schema.yml (quality gate) ────────────────────────────
def _schema_yml(mart: str, target_schema: list[TargetColumn], *,
                with_time: bool, with_value: bool) -> str:
    lines = ["version: 2", "models:", f"  - name: {mart}", "    columns:"]

    def col(name: str, tests: list[str]) -> None:
        lines.append(f"      - name: {name}")
        lines.append("        tests:")
        lines.extend(f"          {t}" for t in tests)

    if with_time:
        # period_date is derived by the compiler from the yyyymm month column.
        col("period_date", [
            "- time_span_min_years:",
            "      arguments: {min_years: 2}",
            "- time_granularity_allowed",
            "- yoy_comparable",
        ])
    if with_value:
        col("value", ["- not_null", "- has_variation"])
    for c in target_schema:
        if c.standard_values:
            quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in c.standard_values)
            col(c.name, [
                "- accepted_values:",
                "      arguments:",
                f"        values: [{quoted}]",
            ])
    return "\n".join(lines) + "\n"


# ── helpers ──────────────────────────────────────────────
def _topo_order(steps: list[TransformStep]) -> list[TransformStep]:
    by_id = {s.id: s for s in steps}
    seen: dict[str, int] = {}  # 0=visiting, 1=done
    order: list[TransformStep] = []

    def visit(sid: str) -> None:
        state = seen.get(sid)
        if state == 1:
            return
        if state == 0:
            raise CompileError(f"pipeline has a cycle through step {sid!r}")
        seen[sid] = 0
        step = by_id.get(sid)
        if step is None:
            raise CompileError(f"step {sid!r} referenced but not defined")
        for inp in step.inputs:
            if not inp.startswith(SOURCE_PREFIX):
                visit(inp)
        seen[sid] = 1
        order.append(step)

    for s in steps:
        visit(s.id)
    return order


def _model_name(step: TransformStep, idx: int, used: set[str]) -> str:
    base = f"s{idx}_{sanitize_ident(step.name or step.kind)}"
    name, n = base, 2
    while name in used:
        name = f"{base}_{n}"
        n += 1
    return name


def _ref(inp: str, step_models: dict[str, str]) -> str:
    if inp.startswith(SOURCE_PREFIX):
        table = sanitize_ident(inp[len(SOURCE_PREFIX):])
        return f"{{{{ source('raw', '{table}') }}}}"
    model = step_models.get(inp)
    if model is None:
        raise CompileError(f"input {inp!r} does not match any step or source")
    return f"{{{{ ref('{model}') }}}}"


def _duck_type(cast: str) -> str:
    return {"integer": "integer", "double": "double", "date": "date",
            "text": "varchar"}.get(cast, "varchar")
