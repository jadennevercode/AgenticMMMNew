"""Shared helpers for agent handlers: upstream context + LLM body generation.

LLM-produced artifacts are grounded in REAL data: each handler feeds real
reference data (via app.ingest) and upstream artifact bodies into the prompt,
and the model structures them into the artifact body. No fabricated numbers —
quantitative artifacts are produced by app.mmm computation, not the LLM.
"""
from __future__ import annotations

import json
from typing import Optional

from app.domain.models import EvidenceRef, TaskFinding
from app.llm.volcano import get_llm
from app.store.state import ProjectState

MAX_CTX_CHARS = 6000


def artifact_text(st: ProjectState, ids: list[str]) -> str:
    """Serialize upstream artifact bodies into compact readable text for grounding."""
    parts: list[str] = []
    for aid in ids:
        a = st.artifact(aid)
        if a is None:
            continue
        parts.append(f"### {a.name} ({a.id}, {a.format})")
        if a.body:
            parts.append(json.dumps(a.body, ensure_ascii=False)[:MAX_CTX_CHARS])
        elif a.content:
            parts.append(a.content[:MAX_CTX_CHARS])
    return "\n".join(parts)[: MAX_CTX_CHARS * 2]


def pack_knowledge_text(st: ProjectState, include_rules: bool = False) -> str:
    """Grounding block from the project's industry knowledge pack + general knowledge.

    Pulls the editable per-industry `industry_knowledge` notes and the cross-industry
    `general_knowledge` notes (and, optionally, the `rules` section) so agents can
    reference the team's accumulated know-how. Returns "" when nothing applies —
    callers append it to a prompt only when non-empty, so no existing prompt changes."""
    from app.store.templates import get_templates

    ts = get_templates()
    ind = st.meta.industry if st.meta else None
    parts: list[str] = []

    if ind is not None:
        kn = ts.best_match("industry_knowledge", ind.l1, ind.l2)
        if kn and kn.knowledge_notes:
            parts.append("INDUSTRY KNOWLEDGE:\n" + "\n".join(
                f"- {n.title}: {n.body}" for n in kn.knowledge_notes if n.title or n.body))
        if include_rules:
            rl = ts.best_match("rules", ind.l1, ind.l2)
            if rl and rl.rule_rows:
                parts.append("APPLICABLE RULES:\n" + "\n".join(
                    f"- [{r.category}/{r.severity}] {r.name}: {r.detail}" for r in rl.rule_rows))

    gen = ts.general()
    if gen and gen.knowledge_notes:
        parts.append("GENERAL KNOWLEDGE:\n" + "\n".join(
            f"- {n.title}: {n.body}" for n in gen.knowledge_notes if n.title or n.body))

    return ("\n\n".join(parts))[: MAX_CTX_CHARS] if parts else ""


def project_context(st: Optional[ProjectState]) -> str:
    """One-line 'this engagement is brand X in the L1 › L2 › L3 industry' clause.

    Injected into the system prompt so per-project LLM calls anchor on the ACTUAL
    project, not a hardcoded case. Empty when no project metadata is available."""
    meta = getattr(st, "meta", None) if st is not None else None
    if meta is None:
        return ""
    ind = meta.industry
    path = " › ".join(p for p in (getattr(ind, "l1", ""), getattr(ind, "l2", ""),
                                  getattr(ind, "l3", "")) if p) if ind else ""
    brand = (meta.brand or meta.name or "").strip()
    if not brand and not path:
        return ""
    who = f"brand «{brand}»" if brand else "this brand"
    where = f" in the {path} industry" if path else ""
    return f" This engagement is for {who}{where}."


def agent_system(agent: str, st: Optional[ProjectState] = None) -> str:
    roles = {
        "business": "You are the Business Agent of an AI-native MMM platform. You frame projects, build the factor tree, synthesize interviews and lay out the data request for a Marketing Mix Modeling engagement.",
        "data": "You are the Data Agent of an AI-native MMM platform. You assure data quality, define ETL/processing logic, and run business + statistical sense-checks on real marketing data.",
        "model": "You are the Model Agent of an AI-native MMM platform. You register modeling assumptions/priors and reason about real OLS MMM results.",
        "report": "You are the Report Agent of an AI-native MMM platform. You turn real model results into decomposition, ROI and a client-facing narrative.",
        "control": "You are the Project Control Agent of an AI-native MMM platform.",
    }
    base = roles.get(agent, roles["control"])
    return (
        base
        + project_context(st)
        + " Product UI language is English; business content may be Chinese (keep domain terms as-is)."
        " Be precise and grounded ONLY in the data provided. Never invent numbers."
        " Do not import facts, brands or product names from any other case; ground only in THIS project's materials."
    )


def _coerce_rows(rows) -> list[list[str]]:
    out: list[list[str]] = []
    for r in rows or []:
        if isinstance(r, list):
            out.append([("" if c is None else str(c)) for c in r])
        elif isinstance(r, dict):
            out.append([("" if v is None else str(v)) for v in r.values()])
    return out


def normalize_sheet(obj) -> dict:
    """Coerce an LLM JSON reply into a valid SheetData dict."""
    sheets = obj.get("sheets") if isinstance(obj, dict) else None
    if not sheets and isinstance(obj, list):
        sheets = obj
    norm = []
    for s in sheets or []:
        if not isinstance(s, dict):
            continue
        norm.append({
            "name": str(s.get("name", "Sheet")),
            "columns": [str(c) for c in s.get("columns", [])],
            "rows": _coerce_rows(s.get("rows", [])),
        })
    if not norm:
        raise ValueError("no sheets in LLM reply")
    return {"sheets": norm}


def normalize_slides(obj) -> dict:
    slides = obj.get("slides") if isinstance(obj, dict) else obj
    norm = []
    for s in slides or []:
        if not isinstance(s, dict):
            continue
        norm.append({
            "title": str(s.get("title", "")),
            "bullets": [str(b) for b in s.get("bullets", [])],
        })
    if not norm:
        raise ValueError("no slides in LLM reply")
    return {"slides": norm}


def normalize_doc(obj) -> dict:
    blocks = obj.get("blocks") if isinstance(obj, dict) else obj
    norm = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        t = b.get("type", "p")
        if t not in ("h1", "h2", "p", "li"):
            t = "p"
        norm.append({"type": t, "text": str(b.get("text", ""))})
    if not norm:
        raise ValueError("no blocks in LLM reply")
    return {"blocks": norm}


def normalize_findings(obj) -> list[TaskFinding]:
    items = obj.get("findings") if isinstance(obj, dict) else obj
    out: list[TaskFinding] = []
    for f in items or []:
        if not isinstance(f, dict):
            continue
        ev = [EvidenceRef(artifactId=e["artifactId"], note=e.get("note"))
              for e in f.get("evidence", []) if isinstance(e, dict) and e.get("artifactId")]
        out.append(TaskFinding(
            text=str(f.get("text", "")),
            tone="flag" if f.get("tone") == "flag" else "info",
            evidence=ev,
        ))
    return out


async def llm_body(system: str, instruction: str, kind: str) -> dict:
    """Ask the LLM for a structured artifact body of the given kind."""
    schema_hint = {
        "sheet": 'Return JSON: {"sheets":[{"name":str,"columns":[str],"rows":[[str,...]]}]}',
        "slides": 'Return JSON: {"slides":[{"title":str,"bullets":[str]}]}',
        "doc": 'Return JSON: {"blocks":[{"type":"h1|h2|p|li","text":str}]}',
    }[kind]
    bound = (
        " Keep it COMPACT so the JSON is complete: each cell/bullet <= 30 characters "
        "(short phrases, not paragraphs); <= 3 sheets; <= 20 rows per sheet; <= 8 slides; "
        "<= 6 bullets per slide. Do not exceed these limits."
    )
    obj = await get_llm().json(system=system, user=instruction + "\n\n" + schema_hint + bound)
    return {"sheet": normalize_sheet, "slides": normalize_slides, "doc": normalize_doc}[kind](obj)


async def llm_findings(system: str, instruction: str, allowed_ids: list[str]) -> list[TaskFinding]:
    ids = ", ".join(allowed_ids)
    prompt = (
        instruction
        + f"\n\nReturn JSON: {{\"findings\":[{{\"text\":str,\"tone\":\"info|flag\","
        + f"\"evidence\":[{{\"artifactId\":one of [{ids}],\"note\":str}}]}}]}}. "
        + "Use tone 'flag' for anomalies/conflicts/gaps needing attention. 2-5 findings."
    )
    try:
        obj = await get_llm().json(system=system, user=prompt)
        return normalize_findings(obj)
    except Exception:  # noqa: BLE001
        return []


async def llm_recommendation(system: str, instruction: str) -> str:
    """Generate a grounded decision recommendation (plain text, <= 3 sentences)."""
    try:
        txt = await get_llm().chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": instruction + "\n\nReply with 1-3 sentences, no markdown."}],
            temperature=0.2, max_tokens=2048,
        )
        return txt.strip()
    except Exception:  # noqa: BLE001
        return ""
