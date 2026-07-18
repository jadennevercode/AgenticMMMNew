"""AI drafting and adjustment of TransformPipelines (structured JSON, never SQL).

The AI's output is a typed step list the human reviews in per-step inspectors —
field mappings, enum mappings, joins, aggregations — so every decision has a
visible, editable control point. A bounded repair loop feeds dbt build errors
back. Heuristic fallbacks (name matching for field maps, exact/case-insensitive
matching for enum maps) keep the suggesters useful without a configured LLM.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from pydantic import ValidationError

from app.dataeng.dbt import compiler, executor
from app.domain.models import EnumMapEntry, FieldMapEntry, TransformPipeline
from app.llm.volcano import get_llm


@dataclass
class DraftContext:
    raw_tables: dict[str, list[str]]     # source table → columns
    profiles_text: str                   # per-field profiles incl. enum values
    target_columns: list[str]
    target_doc: dict[str, str]
    standard_values: dict[str, list[str]]  # target column → maintained enum values
    mart_name: str
    instruction: str = ""
    current: Optional[TransformPipeline] = None   # present ⇒ adjust, not draft
    source_labels: Optional[dict[str, str]] = None  # raw table → source label (filename)


@dataclass
class DraftResult:
    ok: bool
    rounds: int
    pipeline: Optional[TransformPipeline]
    build: Optional[executor.DbtResult]
    error: str = ""


Drafter = Callable[[DraftContext, Optional[str], Optional[TransformPipeline]],
                   Awaitable[TransformPipeline]]

_STEP_SPEC = """\
Each step: {"id": "<unique>", "kind": "...", "name": "<short display name>",
"note": "<one plain-English sentence describing what it does>",
"inputs": ["source:<raw_table>" or "<step id>"], ...kind-specific fields}
Kinds and their fields:
- field_map: fieldMap: [{"source": "<raw col>", "target": "<out col>", "cast": ""|"integer"|"double"|"date"|"text", "expr": "<SQL, only for constants/derived>"}]
- enum_map: enumField: "<column>", enumMap: [{"raw": "<raw value>", "canonical": "<standard value>", "confidence": 0-1, "by": "ai"}]
- join: exactly 2 inputs; join: {"how": "left"|"inner", "leftOn": [..], "rightOn": [..], "rightColumns": [cols to carry from the right side]}
- union: 2+ inputs with identical columns
- aggregate: groupBy: [cols], aggs: [{"column": "...", "func": "sum"|"avg"|"min"|"max"|"count", "alias": ""}]
- filter: filterExpr: "<SQL boolean>"
- derive: derive: [{"name": "<new col>", "expr": "<SQL expr>"}]
- custom_sql: sql: "<SELECT ...>" (inputs available as CTEs input_1, input_2, …) — LAST RESORT only.
"""


def _system() -> str:
    return (
        "You are a senior data engineer designing a TRANSFORM PIPELINE as structured "
        "JSON — typed steps a human will review and edit, NOT free-form SQL. Given "
        "messy multi-source raw tables and a target long-table schema, plan the steps "
        "that clean, standardise and reshape the data.\n"
        + _STEP_SPEC +
        "Rules:\n"
        "1) One field_map per raw source first (rename/cast to a common shape). UNION is "
        "ONLY for sources that represent the SAME entity and, after mapping, have IDENTICAL "
        "columns (e.g. two channel-sales files) — never union tables with different columns. "
        "A LOOKUP / REFERENCE table (few rows, e.g. a price list, a product master, an "
        "exchange rate) must be attached with a JOIN, never unioned. Use enum_map (NOT SQL) "
        "wherever raw values need standardising to the maintained standard values. Finish "
        "with a step that emits EXACTLY the target schema columns (the output step).\n"
        "2) STRICT MAPPING (required): the output step must emit every REQUIRED target "
        "column and no stray columns. For EVERY dimension/factor column that has "
        "maintained standard values, insert an enum_map so its values fall within that "
        "standard set — a value outside the standard set fails validation and blocks "
        "publish.\n"
        "3) The month column must be a yyyymm integer (e.g. 202301). Do NOT emit "
        "period_date — it is derived automatically.\n"
        "4) For enum_map, map EVERY raw value you can see in the profiles into a standard "
        "value; give each mapping a confidence and set by='ai'.\n"
        "5) All names/notes in ENGLISH.\n"
        'Return JSON: {"steps": [...], "outputStep": "<id of the final step>", '
        '"note": "<one-sentence pipeline summary>"}'
    )


def _user(ctx: DraftContext, error: Optional[str],
          previous: Optional[TransformPipeline]) -> str:
    raw = "\n".join(f"  · {t}: {', '.join(cols)}" for t, cols in ctx.raw_tables.items())
    schema = "\n".join(f"  {c}: {ctx.target_doc.get(c, '')}" for c in ctx.target_columns)
    stds = "\n".join(f"  {col}: {', '.join(vals)}"
                     for col, vals in ctx.standard_values.items() if vals) or "  (none maintained)"
    parts = [
        f"Raw source tables:\n{raw}\n",
        f"Field profiles (with distinct values for categorical fields):\n{ctx.profiles_text}\n",
        f"Target schema (output step must emit exactly these columns):\n{schema}\n",
        f"Maintained standard values (enum_map canonical targets):\n{stds}\n",
        f"Output/mart name: {ctx.mart_name}\n",
    ]
    if ctx.current is not None and ctx.current.steps:
        parts.append(
            "CURRENT pipeline (ADJUST it per the instruction — keep unrelated steps "
            f"unchanged, keep ids stable):\n{ctx.current.model_dump_json(by_alias=True)}\n")
    if ctx.instruction.strip():
        parts.append(f"Human instruction:\n{ctx.instruction.strip()}\n")
    if error and previous is not None:
        parts.append(
            f"\nThe previous pipeline FAILED to build with this error — fix and return "
            f"the full corrected pipeline:\n{error}\n\nPrevious pipeline:\n"
            f"{previous.model_dump_json(by_alias=True)}\n")
    return "\n".join(parts)


def parse_pipeline(obj: object) -> TransformPipeline:
    if isinstance(obj, str):
        obj = json.loads(obj)
    if not isinstance(obj, dict):
        raise ValueError("drafter did not return a JSON object")
    try:
        pipe = TransformPipeline.model_validate(obj)
    except ValidationError as e:
        raise ValueError(f"pipeline JSON invalid: {e}") from e
    if not pipe.steps:
        raise ValueError("pipeline has no steps")
    return pipe


async def _llm_drafter(ctx: DraftContext, error: Optional[str],
                       previous: Optional[TransformPipeline]) -> TransformPipeline:
    obj = await get_llm().json(system=_system(), user=_user(ctx, error, previous))
    return parse_pipeline(obj)


async def draft(ws, ctx: DraftContext, target_schema_cols, *, max_rounds: int = 3,
                drafter: Drafter = _llm_drafter) -> DraftResult:
    """Draft (or adjust) → compile → build → repair loop. Returns on green build
    or after ``max_rounds`` attempts with the last error."""
    from app.dataeng.dbt import service
    error: Optional[str] = None
    previous: Optional[TransformPipeline] = ctx.current
    last_build: Optional[executor.DbtResult] = None
    for round_no in range(1, max_rounds + 1):
        try:
            pipe = await drafter(ctx, error, previous)
        except Exception as e:  # noqa: BLE001 — surface as a failed round
            return DraftResult(ok=False, rounds=round_no, pipeline=previous,
                               build=last_build, error=f"drafting failed: {e}")
        try:
            proj = compiler.compile_pipeline(
                pipe, ctx.mart_name, target_schema_cols,
                raw_columns=ctx.raw_tables, source_labels=ctx.source_labels or {})
        except compiler.CompileError as e:
            error, previous = f"pipeline did not compile: {e}", pipe
            continue
        service.apply_compiled(ws, proj)
        last_build = executor.build(ws)
        if last_build.ok:
            return DraftResult(ok=True, rounds=round_no, pipeline=pipe, build=last_build)
        error, previous = last_build.error, pipe
    return DraftResult(ok=False, rounds=max_rounds, pipeline=previous, build=last_build,
                       error=error or "drafting failed")


# ── mapping suggesters (LLM with heuristic fallback) ─────
def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z一-鿿]+", "", s.lower())


def suggest_enum_map_heuristic(raw_values: list[str],
                               standard_values: list[str]) -> list[EnumMapEntry]:
    """Exact / case-insensitive / containment matching; unmatched → canonical ''."""
    out: list[EnumMapEntry] = []
    norm_std = {_norm(v): v for v in standard_values}
    for rv in raw_values:
        n = _norm(rv)
        hit = norm_std.get(n)
        conf = 0.95
        if hit is None:
            hit = next((std for k, std in norm_std.items() if k and (k in n or n in k)), None)
            conf = 0.6
        out.append(EnumMapEntry(raw=rv, canonical=hit or "", confidence=conf if hit else 0.0,
                                by="ai"))
    return out


async def suggest_enum_map(field: str, raw_values: list[str],
                           standard_values: list[str]) -> list[EnumMapEntry]:
    """LLM value matching, falling back to the heuristic when the LLM is unavailable."""
    if not standard_values or not raw_values:
        return suggest_enum_map_heuristic(raw_values, standard_values)
    try:
        obj = await get_llm().json(
            system=("Map each raw data value to one of the maintained standard values. "
                    'Return JSON: {"mappings": [{"raw": "...", "canonical": "<a standard '
                    'value or empty string if none fits>", "confidence": 0-1}]}. '
                    "Map every raw value; use '' when nothing fits."),
            user=(f"Field: {field}\nStandard values: {json.dumps(standard_values, ensure_ascii=False)}\n"
                  f"Raw values: {json.dumps(raw_values, ensure_ascii=False)}"),
        )
        rows = obj.get("mappings", []) if isinstance(obj, dict) else []
        std = set(standard_values)
        out = [EnumMapEntry(raw=str(r.get("raw", "")),
                            canonical=(str(r.get("canonical", "")) if str(r.get("canonical", "")) in std else ""),
                            confidence=float(r.get("confidence", 0.5)), by="ai")
               for r in rows if isinstance(r, dict) and str(r.get("raw", ""))]
        mapped = {e.raw for e in out}
        out.extend(e for e in suggest_enum_map_heuristic(
            [v for v in raw_values if v not in mapped], standard_values))
        return out
    except Exception:  # noqa: BLE001 — LLM unavailable → heuristic
        return suggest_enum_map_heuristic(raw_values, standard_values)


def suggest_field_map_heuristic(source_columns: list[str],
                                target_columns: list[str]) -> list[FieldMapEntry]:
    """Name-similarity mapping: exact/normalised matches only (no guessing)."""
    norm_tgt = {_norm(t): t for t in target_columns}
    out: list[FieldMapEntry] = []
    for src in source_columns:
        tgt = norm_tgt.get(_norm(src))
        if tgt:
            out.append(FieldMapEntry(source=src, target=tgt))
    return out
