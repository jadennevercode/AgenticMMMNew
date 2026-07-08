"""S1 Business Agent handlers — framing, factor tree, interviews, data request.

S1 deliverables are parsed strictly from the user's REAL uploaded materials
(Project Folder) — the profile, knowledge package, factor-tree AI additions,
interview write-back and data request all ground on uploads, never on the
Danone reference. The industry factor-tree / interview *templates* remain the
baseline skeleton; the LLM adds grounding on top of the uploaded sources.
"""
from __future__ import annotations

import asyncio
import re
from itertools import product

from app.agents import sources
from app.agents.common import (
    agent_system,
    artifact_text,
    llm_body,
    llm_findings,
    pack_knowledge_text,
)
from app.domain.models import (
    DiffLine,
    EvidenceRef,
    FactorRow,
    FactorTree,
    Insight,
    InsightAction,
    ModelScope,
    ModelScopeDimension,
    ProjectProfile,
    Proposal,
    TaskFinding,
)
from app.llm.volcano import LLMError, get_llm
from app.orchestrator.engine import Engine
from app.store.state import ProjectState
from app.store.templates import get_templates

SYS = agent_system("business")

_SCOPE_DIMENSIONS = ["Product", "Channel", "Platform & Region"]

_TIME_GRANULARITIES = {"year": "Year", "month": "Month", "week": "Week"}


def _unreadable_upload_finding(artifact_id: str, category_label: str) -> TaskFinding:
    """Flag for the anomalous case where the upload gate passed (files were
    provided) but none of them could be parsed. The 'please upload' prompt lives
    on the upstream upload task (1.0a / 1.1a / 1.4a) — this is about a file that
    is present but unreadable, so it belongs on the producing task."""
    return TaskFinding(
        text=f"The files in the Project Folder ({category_label}) could not be parsed — "
             "re-upload a readable copy. This deliverable is built only from your real materials.",
        tone="flag", evidence=[EvidenceRef(artifactId=artifact_id)])


def _parse_failed_finding(artifact_id: str) -> TaskFinding:
    """Flag the case where the upload was readable but the LLM parse of it failed
    (timeout / transient error). We must NOT emit a hollow default deliverable in
    this case — that would silently mask the failure — so re-run is required."""
    return TaskFinding(
        text="The uploaded SOW/brief was read but the AI framing step failed (timeout or "
             "transient error) — re-run this task. No scope was inferred, so nothing was "
             "produced rather than a misleading empty scope.",
        tone="flag", evidence=[EvidenceRef(artifactId=artifact_id)])


async def _profile_from_materials(materials: str, origin: str) -> ProjectProfile:
    """Parse a structured project profile from the uploaded SOW/brief text.

    This is what makes Business Understanding genuinely input-driven: the model
    scope (dimensions + in-scope rows), time granularity and intro all come from
    the user's uploaded SOW rather than the Danone reference scope.
    """
    # No try/except here: a failed LLM call must propagate (LLMError) so the caller
    # can flag it and skip producing a hollow default scope. Only field-level gaps
    # in a SUCCESSFUL reply fall back to defaults below.
    obj = await get_llm().json(
        system=SYS,
        user=(
            "You are framing an MMM project from the SOW / kickoff brief below. Extract:\n"
            "- intro: a 2-3 sentence project introduction (objective, brand/category, what the "
            "model should answer)\n"
            "- timeGranularity: one of Year / Month / Week (the modeling time grain)\n"
            "- dimensions: the model-scope dimensions, each {name, values:[...]}. Typical "
            "dimensions for an MMM are Product, Channel, Platform & Region.\n"
            "- rows: the IN-SCOPE combinations as a list of rows; each row is a list of values "
            "aligned to the dimensions order (only the combinations the SOW lists as in scope).\n"
            'Return JSON: {"intro":str,"timeGranularity":str,'
            '"dimensions":[{"name":str,"values":[str]}],"rows":[[str]]}\n\n'
            "SOW / BRIEF:\n" + materials[:8000]
        ),
    )
    if not isinstance(obj, dict):
        obj = {}

    intro = str(obj.get("intro", "")).strip()
    tg_raw = str(obj.get("timeGranularity", "Month")).strip().lower()
    time_gran = _TIME_GRANULARITIES.get(tg_raw, "Month")

    dims: list[ModelScopeDimension] = []
    for d in obj.get("dimensions", []) if isinstance(obj.get("dimensions"), list) else []:
        if isinstance(d, dict) and str(d.get("name", "")).strip():
            vals = [str(v).strip() for v in d.get("values", []) if str(v).strip()]
            dims.append(ModelScopeDimension(name=str(d["name"]).strip(), values=vals))
    if not dims:
        dims = [ModelScopeDimension(name=n, values=[]) for n in _SCOPE_DIMENSIONS]

    rows = [[str(c).strip() for c in r]
            for r in (obj.get("rows", []) if isinstance(obj.get("rows"), list) else [])
            if isinstance(r, list) and any(str(c).strip() for c in r)]

    return ProjectProfile(
        projectIntro=intro or "MMM engagement framing the marketing-investment ROI question.",
        timeGranularity=time_gran,
        modelScope=ModelScope(dimensions=dims, rows=rows),
        sourceOrigin=origin,
    )


def _profile_sheet(profile: ProjectProfile, meta) -> dict:
    """Render the structured profile into the a-scope sheet body."""
    brand = getattr(meta, "brand", "") if meta else ""
    overview_rows = [
        ["Brand", brand],
        ["Project intro", profile.project_intro[:400]],
        ["Time granularity", profile.time_granularity],
        ["Model granularity", f"{len(profile.model_scope.rows)} scope rows across "
                              f"{len(profile.model_scope.dimensions)} dimensions"],
        ["Source", profile.source_origin or "reference case"],
    ]
    scope_cols = [d.name for d in profile.model_scope.dimensions] or _SCOPE_DIMENSIONS
    scope_rows = [[(r[i] if i < len(r) else "") for i in range(len(scope_cols))]
                  for r in profile.model_scope.rows]
    return {"sheets": [
        {"name": "Project Overview", "columns": ["Field", "Value"], "rows": overview_rows},
        {"name": "Model Scope", "columns": scope_cols, "rows": scope_rows[:60]},
    ]}


async def frame_profile(eng: Engine, st: ProjectState, task: dict) -> None:
    # Input-driven only: parse the whole profile (scope matrix, granularity, intro)
    # from the user's uploaded SOW/brief. No reference fallback — the 1.0a upload
    # gate guarantees these files exist before this handler runs.
    materials = sources.category_text(st.project_id, "project_background")
    if not materials:
        # The 1.0a gate guarantees a SOW/brief was uploaded before this runs, so an
        # empty read means the uploaded file couldn't be parsed — not a missing upload.
        eng.emit(st, "business", "info",
                 "Profile not framed — the uploaded SOW/brief could not be parsed", task["id"])
        eng.add_findings(st, task["id"], [_unreadable_upload_finding("a-scope", "Project Background")])
        return

    try:
        profile = await _profile_from_materials(materials, "uploaded files")
    except LLMError:
        # The AI framing call failed (timeout / transient). Do NOT fall back to a
        # hollow default scope — that silently masks the failure and gets persisted.
        # Flag it and leave the task un-produced so it can be re-run.
        eng.emit(st, "business", "info",
                 "Profile framing failed — the AI could not parse the SOW/brief (timeout or "
                 "transient error). Re-run this task; no scope was produced.", task["id"])
        eng.add_findings(st, task["id"], [_parse_failed_finding("a-scope")])
        return

    st.profile = profile
    eng.produce(st, "a-scope", body=_profile_sheet(profile, st.meta), state="proposed", agent="business")
    eng.emit(st, "business", "info",
             f"Project profile parsed from uploaded SOW/brief · {len(profile.model_scope.rows)} scope rows",
             task["id"])

    findings = await llm_findings(
        SYS, "Given the framed profile, list key findings (exclusions, ambiguities, granularity risks).",
        ["a-scope", "a-sow"])
    if findings:
        eng.add_findings(st, task["id"], findings)


async def assemble_knowledge(eng: Engine, st: ProjectState, task: dict) -> None:
    # Input-driven only: assemble from the user's uploaded reports/materials. The
    # 1.1a upload gate guarantees these exist before this handler runs.
    materials = sources.category_text(st.project_id, "industry_reference", max_chars=6000)
    if not materials:
        # 1.1a gate guarantees materials were uploaded — empty read = parse failure.
        eng.emit(st, "business", "info",
                 "Knowledge package not assembled — the uploaded materials could not be parsed",
                 task["id"])
        eng.add_findings(st, task["id"], [_unreadable_upload_finding("a-knowledge-package", "Industry Reference")])
        return
    body = await llm_body(
        SYS,
        "Assemble the industry-knowledge package for the beverage/functional-drinks category from the "
        "materials below. Produce sheets: '目录' (部分/内容), '行业知识' (L1 / L2（锁定）), "
        "'品牌生意分析框架' (维度/说明). Keep the locked L1/L2 skeleton faithful to the source.\n\n"
        + materials[:6000],
        "sheet",
    )
    eng.produce(st, "a-knowledge-package", body=body, state="confirmed", agent="business")
    eng.emit(st, "business", "info", "Industry knowledge assembled from uploaded materials", task["id"])


def _default_dimension(st: ProjectState) -> str:
    """Comma-joined model-scope dimension names from the project profile.

    Seeds each factor row's editable Dimension so it stays consistent with the
    dimensions the user defined in the Project Profile (names only, no enumerated
    values). Empty when there is no parsed profile yet."""
    prof = st.profile
    if prof is None:
        return ""
    return ", ".join(d.name.strip() for d in prof.model_scope.dimensions if d.name.strip())


def _baseline_rows_from_template(st: ProjectState) -> list[FactorRow]:
    """Pull the industry's standard factor-tree template as the baseline."""
    ind = st.meta.industry if st.meta else None
    tpl = None
    if ind is not None:
        tpl = get_templates().best_match("factor_tree", ind.l1, ind.l2)
    dim = _default_dimension(st)
    rows: list[FactorRow] = []
    if tpl is not None and tpl.factor_rows:
        for i, fr in enumerate(tpl.factor_rows):
            rows.append(FactorRow(
                id=f"ft-tpl-{i}", l1=fr.l1, l2=fr.l2, l3=fr.l3, l4=fr.l4, indicator=fr.indicator,
                dimension=dim, source="template", status="baseline"))
    # No reference fallback: the per-industry template is the only baseline skeleton.
    return rows


def _uploaded_factor_rows(st: ProjectState) -> list[FactorRow]:
    """Parse the user's own factor-tree workbook(s) from the `factor_tree`
    Project-Folder category into baseline FactorRows (source='upload')."""
    from app.ingest.factor_tree_upload import parse_factor_tree_upload
    from app.store.files import get_files

    files = get_files()
    paths = []
    for f in files.list(st.project_id):
        if f.category == "factor_tree":
            got = files.get_path(st.project_id, f.id)
            if got is not None:
                paths.append(got[1])
    dim = _default_dimension(st)
    return [r.model_copy(update={"dimension": dim}) for r in parse_factor_tree_upload(paths)]


def _row_key(r: FactorRow) -> tuple[str, str, str, str, str]:
    return (r.l1, r.l2, r.l3, r.l4, r.indicator)


def apply_pack_to_factor_tree(st: ProjectState, l1: str, l2: str | None) -> FactorTree:
    """Re-seed a project's factor tree from an industry knowledge pack, preserving
    the user's decisions: accepted / rejected factors and any AI / manual / interview
    additions survive; baseline factors are refreshed from the (possibly edited) pack.

    Deterministic — no LLM call. Used by the "Apply pack to project" action."""
    from app.agents.artifact_edit import apply_factor_tree

    ind = st.meta.industry if st.meta else None
    use_l1 = l1 or (ind.l1 if ind else "")
    use_l2 = l2 if l2 is not None else (ind.l2 if ind else None)

    tpl = get_templates().best_match("factor_tree", use_l1, use_l2)
    dim = _default_dimension(st)
    baseline: list[FactorRow] = []
    if tpl is not None and tpl.factor_rows:
        for i, fr in enumerate(tpl.factor_rows):
            baseline.append(FactorRow(
                id=f"ft-tpl-{i}", l1=fr.l1, l2=fr.l2, l3=fr.l3, l4=fr.l4, indicator=fr.indicator,
                dimension=dim, source="template", status="baseline"))
    baseline = atomic_factor_rows(baseline)

    existing = list(st.factor_tree.rows) if st.factor_tree else []
    by_key = {_row_key(r): r for r in existing}

    merged: list[FactorRow] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    # 1. New baseline — but keep the prior row (and its decision) when it already exists.
    for b in baseline:
        k = _row_key(b)
        if k in seen:
            continue
        seen.add(k)
        merged.append(by_key.get(k, b))
    # 2. Preserve user/AI customizations and any explicit accept/reject the pack dropped.
    for r in existing:
        k = _row_key(r)
        if k in seen:
            continue
        if r.source != "template" or r.status in ("accepted", "rejected"):
            seen.add(k)
            merged.append(r)

    tree = FactorTree(rows=merged)
    apply_factor_tree(st, tree)
    return tree


def _factor_tree_sheet(ft: FactorTree) -> dict:
    """Render the structured factor tree into the a-factor-tree sheet body."""
    active = [r for r in ft.rows if r.status in ("baseline", "accepted")]
    l1s = {r.l1 for r in active if r.l1}
    l2s = {r.l2 for r in active if r.l2}
    l3s = {r.l3 for r in active if r.l3}
    l4s = {r.l4 for r in active if r.l4}
    proposed = [r for r in ft.rows if r.status == "proposed"]
    rows = [[r.l1, r.l2, r.l3, r.l4, r.indicator, r.dimension, r.source, r.status] for r in ft.rows]
    sheets = [
        {"name": "Dimensions", "columns": ["Level", "Count"],
         "rows": [["L1", str(len(l1s))], ["L2", str(len(l2s))], ["L3", str(len(l3s))],
                  ["L4", str(len(l4s))], ["Indicators", str(len(active))],
                  ["AI proposed", str(len(proposed))]]},
        {"name": "Factor Tree",
         "columns": ["L1", "L2", "L3", "L4", "Indicator", "Dimension", "Source", "Status"],
         "rows": rows},
    ]
    if proposed:
        sheets.append({"name": "AI Recommendations",
                       "columns": ["L3", "L4", "Indicator", "Rationale"],
                       "rows": [[r.l3, r.l4, r.indicator, r.rationale[:120]] for r in proposed]})
    return {"sheets": sheets}


# Split combined cells like "TV/OTV/OOH" or "A、B、C" into atomic values. We split
# only on clear list separators (/ 、 ； ; |) — NOT on "+"/"&" which appear inside
# single names (e.g. the "EC+O2O" channel).
_FACTOR_SEPARATORS = set("/、；;|")
# Bracket pairs whose contents must stay intact — splitting inside them would
# leave a dangling '（' / '）' (e.g. "TV投放（中央台/卫视/地方台）" must NOT become
# "TV投放（中央台" / "卫视" / "地方台）").
_BRACKET_OPEN = "（(「【[{《"
_BRACKET_CLOSE = "）)」】]}》"
_MAX_ATOMIC_EXPANSION = 60


def _split_top_level(v: str) -> list[str]:
    """Split on list separators only at bracket depth 0 (so separators inside a
    '（…）' group are left for _distribute_bracket to handle)."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in v:
        if ch in _BRACKET_OPEN:
            depth += 1
        elif ch in _BRACKET_CLOSE:
            depth = max(0, depth - 1)
        if ch in _FACTOR_SEPARATORS and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _first_bracket_group(s: str) -> tuple[int, int, str, str] | None:
    """Locate the first top-level bracket group; returns (open_idx, close_idx,
    open_char, close_char) or None."""
    depth = 0
    start = -1
    open_ch = ""
    for i, ch in enumerate(s):
        if ch in _BRACKET_OPEN:
            if depth == 0:
                start = i
                open_ch = ch
            depth += 1
        elif ch in _BRACKET_CLOSE:
            depth -= 1
            if depth <= 0 and start >= 0:
                return (start, i, open_ch, ch)
            depth = max(0, depth)
    return None


def _distribute_bracket(piece: str) -> list[str]:
    """Expand a shared-prefix bracket enumeration into one COMPLETE value per item:
    'TV投放金额（中央台/卫视/地方台）' -> ['TV投放金额（中央台）','TV投放金额（卫视）','TV投放金额（地方台）'].
    Each result keeps the prefix, its own bracket pair and any suffix — so brackets
    always stay balanced. A single-item bracket ('派样面（新品）') is left as-is."""
    grp = _first_bracket_group(piece)
    if grp is None:
        return [piece]
    o, c, open_ch, close_ch = grp
    items = _split_top_level(piece[o + 1:c])
    if len(items) <= 1:
        return [piece]
    prefix, suffix = piece[:o], piece[c + 1:]
    return [f"{prefix}{open_ch}{it}{close_ch}{suffix}" for it in items]


def _split_cell(value: str) -> list[str]:
    """Atomize a combined cell. Splits on top-level list separators, then expands
    any '（a/b/c）' enumeration by distributing the shared prefix/brackets so every
    resulting value is complete and its punctuation stays balanced."""
    v = (value or "").strip()
    if not v:
        return [""]
    out: list[str] = []
    seen: set[str] = set()
    for piece in _split_top_level(v):
        for expanded in _distribute_bracket(piece):
            e = expanded.strip()
            if e and e not in seen:
                seen.add(e)
                out.append(e)
    return out or [v]


def atomic_factor_rows(rows: list[FactorRow]) -> list[FactorRow]:
    """Expand any row whose L1–L4 or indicator combines several values into one
    row per atomic combination, so every level holds a single value. Dedupes
    identical resulting rows and keeps ids stable when a row is already atomic."""
    out: list[FactorRow] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for r in rows:
        combos = list(product(
            _split_cell(r.l1), _split_cell(r.l2), _split_cell(r.l3),
            _split_cell(r.l4), _split_cell(r.indicator)))[:_MAX_ATOMIC_EXPANSION]
        single = len(combos) == 1
        for i, (l1, l2, l3, l4, ind) in enumerate(combos):
            key = (l1, l2, l3, l4, ind)
            if key in seen:
                continue
            seen.add(key)
            out.append(FactorRow(
                id=r.id if single else f"{r.id}-{i}",
                l1=l1, l2=l2, l3=l3, l4=l4, indicator=ind, dimension=r.dimension,
                source=r.source, status=r.status, rationale=r.rationale, evidence=r.evidence))
    return out


def _refresh_factor_analysis(eng: Engine, st: ProjectState) -> None:
    """Keep the analysis blackboard's L4 list in sync with accepted factors."""
    ft = st.factor_tree
    if ft is None:
        return
    active = [r for r in ft.rows if r.status in ("baseline", "accepted")]
    eng.set_analysis(st, "factor_l4", sorted({r.l4 for r in active if r.l4}))


def _paths_block(rows: list[FactorRow], limit: int = 4000) -> str:
    return "; ".join(sorted({f"{r.l1}/{r.l2}/{r.l3}/{r.l4}/{r.indicator}" for r in rows}))[:limit]


def _keydiff_supplement(uploaded: list[FactorRow], template_rows: list[FactorRow]) -> list[FactorRow]:
    """Deterministic fallback: template factors absent from the user tree (exact key)."""
    up_keys = {_row_key(r) for r in uploaded}
    return [r.model_copy(update={"id": f"ft-tplsup-{i}", "status": "proposed",
                                 "rationale": "Template factor missing from your tree",
                                 "evidence": "industry template (key-diff)"})
            for i, r in enumerate(template_rows) if _row_key(r) not in up_keys]


async def _ai_template_supplement(st: ProjectState, uploaded: list[FactorRow],
                                  template_rows: list[FactorRow]) -> list[FactorRow]:
    """LLM-select which industry-template factors the user's uploaded tree is
    genuinely missing (semantic dedup + brand relevance), as 'proposed' template
    supplements. Falls back to a deterministic key-diff when the LLM is
    unavailable / returns nothing, so the tree is still supplemented."""
    if not template_rows:
        return []
    dim = _default_dimension(st)
    up_keys = {_row_key(r) for r in uploaded}
    try:
        obj = await get_llm().json(
            system=agent_system("business", st),
            user=(
                "You are supplementing a user's MMM factor tree with factors from the standard "
                "industry template.\n\nUSER TREE — already covered (L1/L2/L3/L4/indicator):\n"
                + _paths_block(uploaded)
                + "\n\nINDUSTRY TEMPLATE — candidate factors:\n" + _paths_block(template_rows)
                + "\n\nReturn ONLY the template factors the USER TREE is genuinely MISSING and that are "
                "relevant to this brand. Do SEMANTIC dedup: if the user already covers a concept under "
                "different wording, DO NOT propose it. Judge relevance — do not blindly return every "
                "template factor. Keep each proposed factor's l1/l2/l3/l4/indicator as written in the "
                "template. IMPORTANT: each of l1/l2/l3/l4 and indicator must be a SINGLE atomic value — "
                "never combine several; every value must have BALANCED brackets/quotes （）()「」\"\". "
                "Return JSON: {\"supplements\":[{\"l1\":str,\"l2\":str,\"l3\":str,\"l4\":str,"
                "\"indicator\":str,\"rationale\":str}]}"
            ),
        )
    except Exception:  # noqa: BLE001
        obj = {}
    recs = obj.get("supplements", []) if isinstance(obj, dict) else []
    out: list[FactorRow] = []
    for rec in recs:
        if not isinstance(rec, dict):
            continue
        row = FactorRow(
            id=f"ft-tplsup-{len(out)}", l1=str(rec.get("l1", "")), l2=str(rec.get("l2", "")),
            l3=str(rec.get("l3", "")), l4=str(rec.get("l4", "")), indicator=str(rec.get("indicator", "")),
            dimension=dim, source="template", status="proposed",
            rationale=str(rec.get("rationale", "")), evidence="industry template (AI-selected)")
        if _row_key(row) in up_keys:
            continue  # guard: skip anything the user already has verbatim
        out.append(row)
    # No usable LLM output → deterministic key-diff so supplementation still happens.
    return out if out else _keydiff_supplement(uploaded, template_rows)


async def derive_factor_tree(eng: Engine, st: ProjectState, task: dict) -> None:
    template_rows = _baseline_rows_from_template(st)
    use_upload = st.factor_tree_source == "upload"
    uploaded = _uploaded_factor_rows(st) if use_upload else []

    # Branch on the 1.1a source choice:
    #  · template → template skeleton is the baseline (the default flow)
    #  · upload   → the user's uploaded tree is the baseline (source='upload'); the
    #               LLM supplements it from the industry template (semantic dedup +
    #               relevance, offered as 'proposed') + the materials recs below.
    supplement: list[FactorRow] = []
    if use_upload and uploaded:
        baseline = uploaded
        supplement = await _ai_template_supplement(st, uploaded, template_rows)
    else:
        if use_upload and not uploaded:
            # User chose upload but nothing parsed — don't fabricate; fall back to the
            # template baseline and flag it so they can re-upload a valid workbook.
            eng.add_findings(st, task["id"], [_unreadable_upload_finding("a-factor-tree", "Factor Tree")])
        baseline = template_rows

    grounded = baseline + supplement
    # Ground AI recommendations strictly on the user's uploaded industry materials.
    materials = sources.category_text(st.project_id, "industry_reference")
    origin = "uploaded materials"
    existing = "; ".join(sorted({f"{r.l1}/{r.l2}/{r.l3}" for r in grounded if r.l3}))[:3000]
    # Ground additionally on the editable industry + general knowledge pack (best-effort).
    know = pack_knowledge_text(st)
    know_block = ("\n\nKNOWLEDGE PACK (team know-how — use to inform, not to invent numbers):\n" + know) if know else ""
    try:
        obj = await get_llm().json(
            system=agent_system("business", st),
            user=(
                "You are extending an MMM factor tree. Existing L1/L2/L3 paths:\n" + existing
                + know_block
                + "\n\nFrom the materials below, recommend ADDITIONAL factors at L3/L4 + a candidate "
                "Indicator that the materials justify but the baseline may miss — recommend as many as the "
                "materials genuinely support (no fixed limit), but only ones the materials justify. Every "
                "recommendation must fit under an existing L1/L2. IMPORTANT: each of l1/l2/l3/l4 and indicator "
                "must be a SINGLE atomic value — never combine several (no 'TV/OTV/OOH', no 'A、B、C'); emit a "
                "separate recommendation per combination. FORMAT: every emitted value must have BALANCED "
                "punctuation — any bracket or quote （）()「」\"\" opened must also be closed; never leave a dangling "
                "'（' or '）'. When several sub-items share a prefix, write them as 'PREFIX（a/b/c）' — the system "
                "expands that into one COMPLETE factor per item ('PREFIX（a）','PREFIX（b）','PREFIX（c）'), e.g. "
                "'TV投放金额（中央台/卫视/地方台）' becomes three complete factors — or emit each as its own complete "
                "value; either way each value must read as a whole phrase with balanced brackets. Return JSON: "
                "{\"recommendations\":[{\"l1\":str,\"l2\":str,"
                "\"l3\":str,\"l4\":str,\"indicator\":str,\"rationale\":str}]}\n\nMATERIALS:\n" + materials[:6000]
            ),
        )
    except Exception:  # noqa: BLE001
        obj = {}
    proposed: list[FactorRow] = []
    for i, rec in enumerate(obj.get("recommendations", []) if isinstance(obj, dict) else []):
        if not isinstance(rec, dict):
            continue
        proposed.append(FactorRow(
            id=f"ft-ai-{i}", l1=str(rec.get("l1", "")), l2=str(rec.get("l2", "")),
            l3=str(rec.get("l3", "")), l4=str(rec.get("l4", "")), indicator=str(rec.get("indicator", "")),
            dimension=_default_dimension(st),
            source="ai", status="proposed", rationale=str(rec.get("rationale", "")), evidence=origin))

    # Every L1–L4 / indicator must be a single value — split any combined cells.
    st.factor_tree = FactorTree(rows=atomic_factor_rows(baseline + supplement + proposed))
    eng.produce(st, "a-factor-tree", body=_factor_tree_sheet(st.factor_tree), state="proposed", agent="business")
    _refresh_factor_analysis(eng, st)
    if use_upload and uploaded:
        eng.emit(st, "business", "info",
                 f"Factor tree built from your uploaded tree ({len(baseline)} rows) + "
                 f"{len(supplement)} template supplements + {len(proposed)} AI recommendations "
                 f"grounded in {origin}", task["id"])
    else:
        eng.emit(st, "business", "info",
                 f"Factor tree derived from template ({len(baseline)} baseline) + {len(proposed)} AI "
                 f"recommendations grounded in {origin}", task["id"])

    if proposed:
        eng.add_findings(st, task["id"], [TaskFinding(
            text=f"{len(proposed)} AI-recommended factors await your accept/reject in the Factor Tree.",
            tone="flag", evidence=[EvidenceRef(artifactId="a-factor-tree")])])


# ── Interview outline: 2-level hierarchy (Layer → Team / target) ─────────
# Leadership / Management / Operations come from the industry interview template
# (one target per team); Data is a synthesized target whose questions are
# generated from the project's accepted factor-tree leaves. The exported shape
# mirrors reference/Gatorade …MMM-Interview-Outline-…xlsx: an Overview sheet
# plus one sheet per target.

_LAYER_BY_CATEGORY = {"Leadership": "leadership", "Management": "management", "Operation": "operations"}
_LAYER_ZH = {"leadership": "高层", "management": "管理层", "operations": "执行层", "data": "数据团队"}
_LAYER_DURATION = {"leadership": 60, "management": 60, "operations": 90, "data": 90}

# Structured data-availability sub-questions asked per accepted factor-tree leaf.
_DATA_SUBQUESTIONS = [
    "该指标当前是否可获得？主要来源系统 / 供应商是什么？",
    "可提供的最小时间颗粒度与可回溯的历史区间是什么（周度 / 月度，起止时间）？",
    "可按哪些业务维度拆分（品牌 / 区域 / 渠道 / 平台），各维度的颗粒度如何？",
    "数据口径是否已与业务现实对齐？是否存在已知缺口、口径调整或可比性问题？",
]

_IV_COLUMNS = ["#", "Q Type", "Question", "Related Factor Path", "AI Pre-Answer",
               "访谈回答", "回答来源", "Confidence", "Sources"]
_OVERVIEW_COLUMNS = ["Target ID", "Layer", "Layer (中文)", "Team", "Participants",
                     "Proposed Schedule", "Duration (min)", "Status", "Question Count"]

# The interview-minutes extractions run on a reasoning model and routinely take
# ~180s for the (rich) factor-change call — well past the default 120s client
# timeout, which silently zeroed the writeback. Give these two calls more room.
_MINUTES_LLM_TIMEOUT = 300.0


def _clean_team(role: str) -> str:
    """Tidy a template sheet-title into a team label (e.g. 'Operation Team-Mkt-Media'
    -> 'Marketing-Media')."""
    team = re.sub(r"^(Operation Team-|Management Team-|Leadership Team-)", "", (role or "").strip())
    team = team.replace("Mkt", "Marketing")
    return team or (role or "").strip()


def _target_id(layer: str, team: str) -> str:
    import hashlib
    digest = hashlib.sha1(f"{layer}|{team}".encode("utf-8")).hexdigest()[:10]
    return f"tgt_{digest}"


def _make_target(layer: str, team: str, questions: list[dict]) -> dict:
    return {
        "id": _target_id(layer, team), "layer": layer, "layerZh": _LAYER_ZH.get(layer, layer),
        "team": team, "participants": "", "schedule": "",
        "durationMin": _LAYER_DURATION.get(layer, 60), "status": "pending", "questions": questions,
    }


def _data_questions(st: ProjectState) -> list[dict]:
    """One structured sub-question set per accepted factor-tree leaf, each carrying
    its factor path (the Data-Team target)."""
    ft = st.factor_tree
    if ft is None:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for r in ft.rows:
        if r.status not in ("baseline", "accepted"):
            continue
        parts = [p for p in (r.l1, r.l2, r.l3, r.l4) if p]
        if r.indicator:
            parts.append(r.indicator)
        path_slash = " / ".join(parts)
        if not path_slash or path_slash in seen:
            continue
        seen.add(path_slash)
        path_arrow = " › ".join(parts)
        for subq in _DATA_SUBQUESTIONS:
            out.append({"qType": "data", "question": f"[{path_arrow}] {subq}",
                        "relatedFactorPath": path_slash, "preAnswer": "",
                        "confidence": "low", "sources": []})
    return out


def _build_targets(st: ProjectState) -> list[dict]:
    """Build the interview targets: template-driven business teams + a Data-Team
    target derived from the factor tree."""
    ind = st.meta.industry if st.meta else None
    tpl = get_templates().best_match("interview", ind.l1, ind.l2) if ind else None
    grouped: dict[tuple[str, str], list[dict]] = {}
    order: list[tuple[str, str]] = []
    if tpl is not None:
        for q in tpl.interview_questions:
            layer = _LAYER_BY_CATEGORY.get(q.category)
            if layer is None or not q.question.strip():
                continue
            team = _clean_team(q.role) or q.category
            key = (layer, team)
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append({"qType": "business", "question": q.question.strip(),
                                 "relatedFactorPath": "", "preAnswer": "",
                                 "confidence": "low", "sources": []})
    targets = [_make_target(layer, team, grouped[(layer, team)]) for (layer, team) in order]
    data_qs = _data_questions(st)
    if data_qs:
        targets.append(_make_target("data", "Data Team", data_qs))
    return targets


def _flatten_targets(targets: list[dict]) -> list[dict]:
    """Flat question view (carries layer/team/targetId) for minutes-writeback & summary."""
    flat: list[dict] = []
    for t in targets:
        for q in t["questions"]:
            flat.append({**q, "layer": t["layer"], "team": t["team"], "targetId": t["id"]})
    return flat


def _interview_sheets(targets: list[dict]) -> dict:
    """Overview sheet + one sheet per target, with a banner (title + meta) above
    each per-target table — mirrors the Gatorade reference workbook."""
    overview_rows = [[t["id"], t["layer"], t["layerZh"], t["team"], t["participants"],
                      t["schedule"], str(t["durationMin"]), t["status"], str(len(t["questions"]))]
                     for t in targets]
    sheets: list[dict] = [{"name": "Overview", "columns": _OVERVIEW_COLUMNS, "rows": overview_rows}]
    for t in targets:
        # Sheet tab name uses a tight `·` (Excel-friendly); the banner title is spaced.
        tab = f"{t['layerZh']}·{t['team']}"
        title = f"{t['layerZh']} · {t['team']}"
        meta = (f"Layer: {t['layer']}  |  Duration: {t['durationMin']} min  |  "
                f"Status: {t['status']}  |  Participants: {t.get('participants') or '—'}")
        rows = [[str(i), q["qType"], q["question"], q.get("relatedFactorPath", ""),
                 q.get("preAnswer", ""), q.get("finalAnswer", ""), q.get("answerSource", ""),
                 q.get("confidence", ""), "; ".join(q.get("sources", []))]
                for i, q in enumerate(t["questions"], 1)]
        sheets.append({"name": tab, "preRows": [[title], [meta], []],
                       "columns": _IV_COLUMNS, "rows": rows})
    return {"sheets": sheets}


def _source_labels(st: ProjectState) -> list[str]:
    """Candidate grounding-source labels for pre-answer attribution (matches the
    reference's `ai_recommendation:<label>` form)."""
    labels = ["SOW summary"]
    labels += [aid for aid in ("a-scope", "a-factor-tree") if st.artifact(aid)]
    return labels


async def draft_interview(eng: Engine, st: ProjectState, task: dict) -> None:
    targets = _build_targets(st)
    eng.set_analysis(st, "interview_targets", targets)
    eng.set_analysis(st, "interview_questions", _flatten_targets(targets))
    eng.produce(st, "a-interview", body=_interview_sheets(targets), state="draft", agent="business")
    data_t = next((t for t in targets if t["layer"] == "data"), None)
    data_n = len(data_t["questions"]) if data_t else 0
    total = sum(len(t["questions"]) for t in targets)
    eng.emit(st, "business", "info",
             f"Interview outline drafted: {len(targets)} targets across 4 layers · {total} questions "
             f"({data_n} data-availability items from the factor tree)", task["id"])


def _norm_confidence(value: str) -> str:
    conf = str(value or "low").lower()
    return conf if conf in ("low", "medium", "high") else "low"


async def _fill_business_preanswers(target: dict, materials: str, src_labels: list[str]) -> None:
    """Inline preliminary answers for one business target's questions (one LLM call)."""
    qs = target["questions"]
    if not qs:
        return
    qlist = "\n".join(f"{i + 1}. {q['question']}" for i, q in enumerate(qs))
    cand = ", ".join(src_labels)
    try:
        obj = await get_llm().json(
            system=SYS,
            user=(
                "Before the interviews, draft a PRELIMINARY answer to each question below — explicitly a "
                "hypothesis to validate, not fact. If the provided context lacks the information needed, "
                "you MUST begin that answer with the exact prefix 【暂无足够信息】 and state what is missing. "
                "Keep each answer to 1-3 sentences. For each question return: n (1-based), answer, "
                "confidence (low|medium|high), and sources — a list chosen from these candidate labels: "
                f"[{cand}]. Return JSON: "
                "{\"answers\":[{\"n\":int,\"answer\":str,\"confidence\":str,\"sources\":[str]}]}\n\n"
                f"CONTEXT:\n{materials[:5000]}\n\nQUESTIONS:\n{qlist}"
            ),
            max_tokens=3000,
        )
    except Exception:  # noqa: BLE001
        obj = {}
    by_n = {int(a.get("n", 0)): a for a in obj.get("answers", []) if isinstance(a, dict)} if isinstance(obj, dict) else {}
    for i, q in enumerate(qs):
        a = by_n.get(i + 1, {})
        ans = str(a.get("answer", "")).strip() or "【暂无足够信息】现有材料不足以预判该问题，待访谈确认。"
        srcs = a.get("sources") if isinstance(a.get("sources"), list) else None
        srcs = srcs or src_labels[:2]
        q["preAnswer"] = ans
        q["confidence"] = _norm_confidence(a.get("confidence"))
        q["sources"] = [f"ai_recommendation:{s}" for s in srcs]


def _fill_data_preanswers(target: dict, src_labels: list[str]) -> None:
    """Templated preliminary answers for the (large) Data-Team target — avoids one
    LLM call per factor leaf. Data specs are confirmed by the data team in-interview."""
    base = src_labels[:2] or ["SOW summary"]
    for q in target["questions"]:
        q["preAnswer"] = ("【暂无足够信息】该数据点的可获得性、来源、颗粒度与口径需由数据团队在访谈中确认；"
                          "现有材料尚未覆盖该因子的完整数据规格。")
        q["confidence"] = "low"
        q["sources"] = [f"ai_recommendation:{s}" for s in base]


async def pre_answer(eng: Engine, st: ProjectState, task: dict) -> None:
    targets = st.analysis.get("interview_targets", [])
    if not targets:
        return
    # Context for preliminary answers: the uploaded materials plus the project's
    # own framed artifacts (both derived from the user's input — no reference).
    materials = (sources.category_text(st.project_id, "industry_reference", max_chars=4000)
                 + "\n\n" + artifact_text(st, ["a-scope", "a-factor-tree"]))
    src_labels = _source_labels(st)
    # Business targets each need one grounded LLM call — run them CONCURRENTLY so
    # wall-time is ~one call, not the sum of a dozen. The (large) Data-Team target
    # is templated (no LLM). Each call is internally fault-tolerant (falls back to
    # 【暂无足够信息】 on failure), so one bad target can't sink the task.
    business = [t for t in targets if t["layer"] != "data"]
    await asyncio.gather(*(_fill_business_preanswers(t, materials, src_labels) for t in business))
    for t in targets:
        if t["layer"] == "data":
            _fill_data_preanswers(t, src_labels)
    eng.set_analysis(st, "interview_targets", targets)
    eng.set_analysis(st, "interview_questions", _flatten_targets(targets))
    eng.produce(st, "a-interview", body=_interview_sheets(targets), state="draft", agent="business")
    eng.emit(st, "business", "artifact",
             "AI pre-answers added inline (knowledge for reference, to validate in interviews)", task["id"])


def _load_minutes_text(st: ProjectState) -> tuple[str, str]:
    """Interview minutes text — uploaded files only (no reference transcripts)."""
    uploaded = sources.category_text(st.project_id, "interview_minutes", max_chars=9000)
    if uploaded:
        return uploaded, "uploaded minutes"
    return "", "none"


async def _minutes_answers(qlist: str, transcripts: str) -> dict:
    """Best-effort: map the interview minutes back onto the outline questions."""
    try:
        obj = await get_llm().json(
            system=SYS,
            user=(
                "From the interview minutes below, write the FINAL answer to each outline question "
                "that the minutes actually address, with its source. Skip questions the minutes "
                "don't cover. Return JSON: {\"answers\":[{\"n\":int,\"answer\":str,\"source\":str}]}\n\n"
                f"OUTLINE:\n{qlist}\n\nMINUTES:\n{transcripts[:6500]}"
            ),
            timeout=_MINUTES_LLM_TIMEOUT,
        )
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


async def _minutes_factor_changes(transcripts: str, st: ProjectState) -> dict:
    """The important extraction — interview-driven factor-tree changes + insights.

    Kept as its own focused call so it can't be zeroed out by a failure in the
    (heavier, often-misaligned) answer-writeback above.
    """
    try:
        obj = await get_llm().json(
            system=agent_system("business", st),
            user=(
                "From the interview minutes below, propose the factor-tree changes the interviews "
                "imply (add a new factor, or modify an existing factor's indicator / granularity / "
                "channel caliber), each traced to a verbatim minute quote; plus 1-2 cross-source "
                "insights. Each of l1/l2/l3/l4 and indicator must be a SINGLE atomic value — never "
                "combine several (no 'TV/OTV/OOH', no 'A、B'); emit a separate change per combination. "
                "FORMAT: every emitted value must have BALANCED punctuation — any bracket or quote （）()「」\"\" "
                "opened must also be closed; never leave a dangling '（' or '）'. When several sub-items share a "
                "prefix, write them as 'PREFIX（a/b/c）' — the system expands that into one COMPLETE value per item "
                "('PREFIX（a）','PREFIX（b）','PREFIX（c）') — or emit each as its own complete value. "
                "Return JSON: {\"factor_changes\":[{\"op\":\"add|modify\",\"l1\":str,"
                "\"l2\":str,\"l3\":str,\"l4\":str,\"indicator\":str,\"granularity\":str,"
                "\"rationale\":str,\"quote\":str}],\"insights\":[{\"kind\":"
                "\"connection|gap|conflict|reference\",\"title\":str,\"finding\":str,"
                "\"confidence\":0-1}]}\n\nMINUTES:\n" + transcripts[:6500]
            ),
            timeout=_MINUTES_LLM_TIMEOUT,
        )
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


async def writeback_minutes(eng: Engine, st: ProjectState, task: dict) -> None:
    transcripts, origin = _load_minutes_text(st)
    targets = st.analysis.get("interview_targets", [])
    # Collect references to the REAL business-question dicts (the flattened
    # interview_questions are copies, so writing onto them would not reach the
    # rendered per-target sheets). Data-team items are confirmed by the data team,
    # not covered by stakeholder minutes — skip them. Cap at 28.
    biz: list[tuple[dict, str]] = []
    for t in targets:
        if t.get("layer") == "data":
            continue
        label = t.get("team") or t.get("layer", "")
        for q in t.get("questions", []):
            biz.append((q, label))
    biz = biz[:28]
    qlist = "\n".join(f"{i + 1}. [{label}] {q['question']}" for i, (q, label) in enumerate(biz))

    # Two isolated calls, each on a long timeout — these run on a reasoning model
    # and the factor-change call routinely needs ~180s; under the default 120s
    # client timeout it failed on every retry and silently produced nothing.
    ans_obj = await _minutes_answers(qlist, transcripts)
    obj = await _minutes_factor_changes(transcripts, st)

    # ── Issue 1: write the AI-parsed final answers back as a COLUMN on each
    # existing question row (not a separate sheet). ──
    answers = {int(a.get("n", 0)): a for a in ans_obj.get("answers", []) if isinstance(a, dict)}
    answered = 0
    for i, (q, _label) in enumerate(biz):
        a = answers.get(i + 1)
        ans_text = str(a.get("answer", "")).strip() if isinstance(a, dict) else ""
        if ans_text:
            q["finalAnswer"] = ans_text
            q["answerSource"] = str(a.get("source", "")).strip() if isinstance(a, dict) else ""
            answered += 1
    if targets:
        # Re-render from targets so the 访谈回答 column shows; keep the flat view in sync.
        eng.set_analysis(st, "interview_targets", targets)
        eng.set_analysis(st, "interview_questions", _flatten_targets(targets))
        eng.produce(st, "a-interview", body=_interview_sheets(targets), state="draft", agent="business")
    eng.emit(st, "business", "info",
             f"Interview answers written back from minutes ({origin}): "
             f"{answered}/{len(biz)} business questions answered", task["id"])

    # ── Issue 2: interview-driven factor changes → append as 'proposed' rows on
    # the factor tree (user accepts/rejects each at gate 1.4d) + proposals. ──
    changes = [c for c in (obj.get("factor_changes", []) if isinstance(obj, dict) else [])
               if isinstance(c, dict)]
    if not changes:
        # Make the empty result VISIBLE — this used to be a silent timeout that
        # zeroed the single most important S1 output.
        eng.emit(st, "business", "finding",
                 f"No interview-driven factor changes were extracted from the minutes "
                 f"({origin}) — review the minutes or re-run if the model timed out.", task["id"])
    elif st.factor_tree is None:
        eng.emit(st, "business", "finding",
                 f"{len(changes)} interview factor changes extracted but no factor tree "
                 f"exists to attach them to.", task["id"])
    else:
        new_rows = [
            FactorRow(
                id=f"ft-iv-{st.tick}-{i}", l1=str(ch.get("l1", "")), l2=str(ch.get("l2", "")),
                l3=str(ch.get("l3", "")), l4=str(ch.get("l4", "")), indicator=str(ch.get("indicator", "")),
                dimension=_default_dimension(st),
                source="interview", status="proposed",
                rationale=f"{ch.get('op', 'add')} · {ch.get('rationale', '')} · granularity: {ch.get('granularity', '—')}",
                evidence=str(ch.get("quote", ""))[:200])
            for i, ch in enumerate(changes)
        ]
        # Keep every L1–L4 / indicator a single value, then drop any that already
        # exist on the tree so re-running 1.4 doesn't duplicate rows.
        existing_keys = {(r.l1, r.l2, r.l3, r.l4, r.indicator) for r in st.factor_tree.rows}
        atomic = [r for r in atomic_factor_rows(new_rows)
                  if (r.l1, r.l2, r.l3, r.l4, r.indicator) not in existing_keys]
        st.factor_tree.rows.extend(atomic)
        _refresh_factor_analysis(eng, st)
        eng.produce(st, "a-factor-tree", body=_factor_tree_sheet(st.factor_tree),
                    state="proposed", agent="business")
        eng.emit(st, "business", "info",
                 f"{len(atomic)} interview-sourced factor rows proposed on the factor tree "
                 f"(source=interview, pending accept/reject).", task["id"])
    for i, ch in enumerate(changes):
        eng.add_proposal(st, Proposal(
            id=f"p-1.4-{i}", targetArtifactId="a-factor-tree",
            title=f"{ch.get('op', 'add')}: {ch.get('l4') or ch.get('l3') or 'factor'}"[:120],
            summary=str(ch.get("rationale", "")),
            diff=[DiffLine(kind="add", text=f"{ch.get('l3','')}/{ch.get('l4','')} — {ch.get('indicator','')}")],
            evidence=[EvidenceRef(artifactId="a-interview", note=str(ch.get("quote", ""))[:120])],
            confidence=0.7, sourceAgent="business", sourceMode="pipeline", afterTask="1.4"))
    for i, ins in enumerate(obj.get("insights", [])[:2] if isinstance(obj, dict) else []):
        if not isinstance(ins, dict):
            continue
        eng.add_insight(st, Insight(
            id=f"i-1.4-{i}", kind=ins.get("kind", "connection"),
            title=str(ins.get("title", "Insight"))[:120], finding=str(ins.get("finding", "")),
            evidence=[EvidenceRef(artifactId="a-interview")],
            confidence=float(ins.get("confidence", 0.7)),
            actions=[InsightAction(kind="open_asset", label="Open Interview", artifactId="a-interview")],
            afterTask="1.4"))


async def transcribe_audio(eng: Engine, st: ProjectState, task: dict) -> None:
    """ASR step (task 1.4b): transcribe uploaded interview audio to text.

    Each audio recording in the interview_minutes category is transcribed via the
    project's ASR model and written back as a `.transcript.txt` sidecar — so the
    downstream writeback (`writeback_minutes`) consumes it through the existing
    category-text path with zero changes. Text uploads pass straight through.
    """
    from app.asr import ASRError, get_asr
    from app.store.files import get_files

    files = get_files()
    pending = files.audio_pending(st.project_id, "interview_minutes")
    if not pending:
        eng.emit(st, "business", "info",
                 "No interview audio to transcribe (text minutes pass through).", task["id"])
        return

    asr = get_asr()
    if not asr.available:
        for f in pending:
            files.update_record(st.project_id, f.id, asr_status="error",
                                asr_error="ASR not configured")
        eng.emit(st, "business", "finding",
                 f"{len(pending)} interview recording(s) uploaded but ASR is not configured. "
                 "Enter the ASR API key, base URL, and model in Settings, or upload text minutes "
                 "instead.", task["id"])
        return

    done, failed = 0, 0
    for f in pending:
        found = files.get_path(st.project_id, f.id)
        if found is None:
            continue
        record, disk = found
        files.update_record(st.project_id, f.id, asr_status="transcribing")
        try:
            text = await asr.transcribe(data=disk.read_bytes(), filename=record.filename)
        except ASRError as exc:
            failed += 1
            files.update_record(st.project_id, f.id, asr_status="error", asr_error=str(exc)[:300])
            continue
        if not text:
            failed += 1
            files.update_record(st.project_id, f.id, asr_status="error", asr_error="empty transcript")
            continue
        stem = record.filename.rsplit(".", 1)[0]
        files.add(st.project_id, "interview_minutes", f"{stem}.transcript.txt",
                  text.encode("utf-8"), content_type="text/plain")
        files.update_record(st.project_id, f.id, asr_status="done", asr_error=None)
        done += 1

    msg = f"ASR transcription complete: {done} recording(s) transcribed"
    if failed:
        msg += f", {failed} failed (see Project Folder for details)"
    eng.emit(st, "business", "info", msg + ".", task["id"])
    if done and not failed:
        return
    if failed and not done:
        eng.emit(st, "business", "finding",
                 f"All {failed} interview recording(s) failed to transcribe — check the ASR "
                 "configuration and audio format/size (≤25 MB).", task["id"])


_MAX_REQUEST_SHEETS = 12


async def gen_data_request(eng: Engine, st: ProjectState, task: dict) -> None:
    """Lay out the data-request workbook: one template per L3, one sheet per L4.

    Each L4 sheet's columns = time dimension + model-scope dimensions + the L4 indicators.
    """
    ft = st.factor_tree
    rows = [r for r in ft.rows if r.status in ("baseline", "accepted")] if ft else []
    profile = st.profile
    time_col = f"Time ({profile.time_granularity})" if profile else "Time (Month)"
    scope_dims = [d.name for d in profile.model_scope.dimensions] if profile else ["Channel"]
    scope_rows = profile.model_scope.rows[:3] if profile else []

    # Group accepted indicators by L3 -> L4.
    by_l3: dict[str, dict[str, list[str]]] = {}
    for r in rows:
        l3 = r.l3 or r.l2 or r.l1 or "—"
        l4 = r.l4 or l3
        by_l3.setdefault(l3, {}).setdefault(l4, [])
        if r.indicator and r.indicator not in by_l3[l3][l4]:
            by_l3[l3][l4].append(r.indicator)

    index_rows = [[l3, str(len(l4s)), str(sum(len(i) for i in l4s.values()))]
                  for l3, l4s in by_l3.items()]
    sheets: list[dict] = [
        {"name": "Template Index", "columns": ["L3 (one workbook each)", "L4 sheets", "Indicators"],
         "rows": index_rows},
    ]
    # One sheet per L4 (capped) — columns: time + model dims + indicators, with example rows.
    made = 0
    for l3, l4s in by_l3.items():
        for l4, indicators in l4s.items():
            if made >= _MAX_REQUEST_SHEETS:
                break
            cols = [time_col, *scope_dims, *(indicators or ["value"])]
            example = []
            for sr in scope_rows:
                example.append(["2023-01", *[(sr[i] if i < len(sr) else "") for i in range(len(scope_dims))],
                                *["" for _ in (indicators or ["value"])]])
            sheets.append({"name": f"{l3} · {l4}"[:31], "columns": cols, "rows": example or [["2023-01"]]})
            made += 1
    if made >= _MAX_REQUEST_SHEETS:
        sheets.append({"name": "Note", "columns": ["Note"],
                       "rows": [[f"Showing first {_MAX_REQUEST_SHEETS} L4 sheets; the full workbook "
                                 "set has one workbook per L3."]]})
    sheets.append({"name": "Review & Sign-off", "columns": ["Item", "Status"],
                   "rows": [["Fields & granularity", "pending"], ["Owners assigned", "pending"],
                            ["Client sign-off", "pending"]]})

    eng.produce(st, "a-data-request", body={"sheets": sheets}, state="proposed", agent="business")
    eng.emit(st, "business", "info",
             f"Data request laid out: {len(by_l3)} L3 workbooks · {made} L4 sheets · "
             f"time={time_col} · scope dims={', '.join(scope_dims)}. "
             "Export delivers one workbook per L3 (one sheet per L4).", task["id"])


_BU_MAX_RISKS = 6


def _bu_stats(st: ProjectState) -> dict:
    """Deterministic facts for the BU summary — counts come from state, never the LLM."""
    profile = st.profile
    rows = st.factor_tree.rows if st.factor_tree else []
    active = [r for r in rows if r.status in ("baseline", "accepted")]
    accepted_ai = [r for r in rows if r.source in ("ai", "interview") and r.status == "accepted"]
    # Top-level demand-driver families (L1) among the active factors, in first-seen order.
    drivers: list[str] = []
    seen: set[str] = set()
    for r in active:
        key = (r.l1 or "").strip()
        if key and key not in seen:
            seen.add(key)
            drivers.append(key)
    # Interview coverage by stakeholder layer.
    cats: dict[str, int] = {}
    for t in st.analysis.get("interview_targets", []):
        label = t.get("layerZh") or t.get("layer", "—")
        cats[label] = cats.get(label, 0) + len(t.get("questions", []))
    from app.agents.data_request import factor_tree_by_l3
    by_l3 = factor_tree_by_l3(st)
    flags = [f for fl in st.findings.values() for f in fl if getattr(f, "tone", "info") == "flag"]
    return {
        "time_granularity": profile.time_granularity if profile else "—",
        "scope_rows": len(profile.model_scope.rows) if profile else 0,
        "dimensions": [d.name.strip() for d in profile.model_scope.dimensions
                       if d.name.strip()] if profile else [],
        "active": len(active),
        "accepted_ai": len(accepted_ai),
        "drivers": drivers,
        "cats": cats,
        "l3_count": len(by_l3),
        "l4_total": sum(len(l4s) for l4s in by_l3.values()),
        "flags": flags,
    }


async def _bu_prose(instruction: str, ctx: str) -> str:
    """One client-facing narrative section — interpretive prose grounded ONLY in ctx."""
    if not ctx.strip():
        return ""
    try:
        txt = await get_llm().chat(
            [{"role": "system", "content": SYS},
             {"role": "user", "content": (
                 instruction
                 + "\n\nWrite a tight, client-facing narrative of 2-4 sentences — an interpretive "
                   "business reading, not a list of counts (the platform reports counts separately). "
                   "Ground ONLY in the material below; never invent numbers or facts. Write in "
                   "English but keep Chinese domain terms (brand, factor, channel names) as-is. "
                   "No markdown, no headings.\n\nMATERIAL:\n" + ctx[:5000])}],
            temperature=0.3, max_tokens=2048)
        return txt.strip()
    except Exception:  # noqa: BLE001
        return ""


def _bu_section(blocks: list[dict], heading: str, prose: str, bullets: list[str]) -> None:
    """Append a heading, the prose split into paragraphs, then any fact bullets.

    Skips the section entirely when there is neither prose nor any bullet, so a thinly
    grounded project never renders a bare heading.
    """
    clean = [b.strip() for b in bullets if b and b.strip()]
    if not (prose or "").strip() and not clean:
        return
    blocks.append({"type": "h2", "text": heading})
    for para in (prose or "").split("\n\n"):
        if para.strip():
            blocks.append({"type": "p", "text": para.strip()})
    for b in clean:
        blocks.append({"type": "li", "text": b})


async def _bu_hypotheses(ctx: str) -> list[str]:
    """Bulleted modeling hypotheses — the bridge from business understanding to the model.

    Each line pairs a driver/lever with its expected effect and direction, the rationale,
    a rough priority, and how the MMM will test it (mirrors the hypothesis-building lens of
    a pre-modeling diagnostic). Grounded ONLY in ctx; never invents brand-specific numbers.
    """
    if not ctx.strip():
        return []
    try:
        txt = await get_llm().chat(
            [{"role": "system", "content": SYS},
             {"role": "user", "content": (
                 "From the Business Understanding material below, synthesize the key MODELING "
                 "HYPOTHESES the MMM should test — the bridge from business understanding to the "
                 "statistical model. Cover, where the material supports it: (1) which demand "
                 "drivers move the KPI and the expected direction of effect; (2) media/marketing "
                 "levers whose ROI and diminishing-returns (saturation / S-curve) should be "
                 "quantified; (3) attribution risks — where platform last-click may overstate a "
                 "touchpoint's true contribution (e.g. in-platform conversion absorbing out-of-"
                 "platform seeding); (4) collinearity risks — levers that move together and may "
                 "need finer (e.g. weekly) granularity to separate.\n\n"
                 "Return 5-8 hypotheses, ONE PER LINE, each in the form:\n"
                 "Driver/lever — expected effect & direction (+/−) — rationale — priority "
                 "(High/Med/Low) — how the model tests it.\n"
                 "Ground ONLY in the material; never invent numbers or brand-specific facts. "
                 "Keep Chinese domain terms (channel/factor names) as-is. No markdown, no "
                 "headings — just the lines.\n\nMATERIAL:\n" + ctx[:8000])}],
            temperature=0.3, max_tokens=2048)
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for raw in txt.splitlines():
        ln = raw.strip().lstrip("-•*0123456789.) ").strip()
        if ln:
            out.append(ln)
    return out[:8]


def _bu_risks(st: ProjectState, flags: list) -> list[str]:
    """Open questions / risks in business language, drawn from real S1 signals."""
    items: list[str] = []
    for p in st.proposals:
        if p.status == "open":
            items.append(f"{p.title} — {p.summary}".strip(" —"))
    for ins in st.insights:
        if ins.kind in ("gap", "conflict"):
            items.append(f"{ins.title} — {ins.finding}".strip(" —"))
    for f in flags:
        items.append(getattr(f, "text", ""))
    # De-dup while preserving order, then cap.
    out, seen = [], set()
    for it in items:
        it = (it or "").strip()
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out[:_BU_MAX_RISKS]


async def bu_summary(eng: Engine, st: ProjectState, task: dict) -> None:
    """Assemble a client-facing Business Understanding report from the confirmed S1 deliverables.

    Insight-led: each narrative section is a separately-grounded LLM call on its own
    deliverable (profile / industry knowledge / factor tree / interviews / data request),
    so the reading stays close to its real source; every number is computed here, not by
    the model. Section prose is generated concurrently; the executive recap is synthesized
    last from those sections.
    """
    s = _bu_stats(st)
    meta = st.meta

    # Combined grounding for the cross-cutting diagnosis / opportunity / hypotheses sections.
    diag_ctx = artifact_text(st, ["a-knowledge-package", "a-interview", "a-factor-tree"])
    hyp_ctx = artifact_text(st, ["a-scope", "a-knowledge-package", "a-factor-tree", "a-interview"])

    # Independent, separately-grounded narratives (run concurrently). The diagnosis,
    # opportunity and hypotheses sections fold in the pre-modeling hypothesis-building lens
    # (category background → brand-growth diagnosis → growth opportunity → modeling hypotheses)
    # on top of the original context / market / drivers / interview / data reading.
    (context_prose, market_prose, diagnosis_prose, opportunity_prose,
     drivers_prose, interview_prose, data_prose, hypotheses) = await asyncio.gather(
        _bu_prose("Recap how this MMM project is framed and the business question it must answer "
                  "(brand, category, market, modeling objective).", artifact_text(st, ["a-scope"])),
        _bu_prose("Give the market and category reading: category size and growth, the structural "
                  "shifts underway, and the brand's growth logic and what drives its sell-out.",
                  artifact_text(st, ["a-knowledge-package"])),
        _bu_prose("Diagnose the brand's growth versus its category: separate EXTERNAL factors "
                  "(category trend, competitive share dynamics) from INTERNAL factors (product-mix "
                  "structure, new-product ramp, marketing-investment trend). Explain why the brand "
                  "is out- or under-performing the category.", diag_ctx),
        _bu_prose("Read the growth opportunities as product opportunity × channel opportunity: "
                  "which products are the future engine, and the differentiated role each channel "
                  "should play (defend vs grow vs educate).", diag_ctx),
        _bu_prose("Interpret the demand drivers the factor tree locks in — which families matter "
                  "most and what the AI/interview-driven additions changed about the picture.",
                  artifact_text(st, ["a-factor-tree"])),
        _bu_prose("Synthesize the key stakeholder-interview takeaways — points of consensus, "
                  "tension, and what they imply for the model.", artifact_text(st, ["a-interview"])),
        _bu_prose("Assess the data request and the project's readiness for data intake — coverage "
                  "and any obvious gaps.", artifact_text(st, ["a-data-request"])),
        _bu_hypotheses(hyp_ctx),
    )

    # Executive recap is synthesized from the section narratives (incl. diagnosis, opportunity
    # and the modeling hypotheses) above.
    synth = "\n\n".join(p for p in (
        context_prose, market_prose, diagnosis_prose, opportunity_prose, drivers_prose,
        interview_prose, data_prose, "\n".join(hypotheses)) if p)
    exec_prose = await _bu_prose(
        "Write the executive recap of the Business Understanding stage: what was framed, the "
        "brand-growth diagnosis and where the opportunity sits, what the factors and interviews "
        "established, the key modeling hypotheses to test, and readiness for data intake.", synth)

    industry = (f"{meta.industry.l2} / {meta.industry.l3}" if meta else "—")
    blocks: list[dict] = [
        {"type": "h1", "text": "Business Understanding — Summary"},
    ]
    for para in (exec_prose or "Business Understanding stage complete.").split("\n\n"):
        if para.strip():
            blocks.append({"type": "p", "text": para.strip()})

    _bu_section(blocks, "Business Background & Objectives", context_prose, [
        f"Brand: {meta.brand}" if meta else "",
        f"Category: {industry}",
        f"Primary KPI: {meta.kpi}" if meta else "",
        f"Time granularity: {s['time_granularity']}",
        f"Model scope: {s['scope_rows']} combinations across {len(s['dimensions'])} dimensions"
        + (f" ({', '.join(s['dimensions'])})" if s["dimensions"] else ""),
    ])
    _bu_section(blocks, "Category & Market Dynamics", market_prose, [])
    _bu_section(blocks, "Brand Growth Diagnosis", diagnosis_prose, [])
    _bu_section(blocks, "Growth Opportunities", opportunity_prose, [])
    _bu_section(blocks, "Key Demand Drivers", drivers_prose, [
        f"{s['active']} active factors · {s['accepted_ai']} AI/interview-driven additions accepted",
        ("Driver families: " + ", ".join(s["drivers"][:8])) if s["drivers"] else "",
    ])
    _bu_section(blocks, "Modeling Hypotheses",
                ("Testable hypotheses carried into the model — each pairs a driver or lever with "
                 "its expected effect, priority and how the MMM will quantify it." if hypotheses else ""),
                hypotheses)
    _bu_section(blocks, "Stakeholder Interview Insights", interview_prose, [
        "Coverage: " + (", ".join(f"{k} ({v})" for k, v in s["cats"].items()) or "—"),
    ])
    _bu_section(blocks, "Data Request & Readiness", data_prose, [
        f"{s['l3_count']} datasets requested · {s['l4_total']} tables",
        f"{len(s['flags'])} data quality flag(s) raised" if s["flags"] else "",
    ])

    risks = _bu_risks(st, s["flags"])
    if risks:
        _bu_section(blocks, "Risks, Assumptions & Open Questions", "", risks)

    blocks.append({"type": "h2", "text": "Next Steps"})
    blocks.append({"type": "p", "text": (
        "Business Understanding is closed. The engagement moves to S2 — data collection and "
        "processing: the client returns the requested datasets per the data request, which are then "
        "validated, cleaned and assembled into the modeling master table, where the hypotheses above "
        "are quantified."
        + (" Open questions above should be resolved alongside data intake." if risks else ""))})

    eng.produce(st, "a-bu-summary", body={"blocks": blocks}, state="confirmed", agent="business")
    eng.emit(st, "business", "info",
             f"Business Understanding report assembled — {len(blocks)} blocks across context, "
             "market, brand-growth diagnosis, opportunities, drivers, modeling hypotheses, "
             "interviews, data readiness and next steps.", task["id"])
