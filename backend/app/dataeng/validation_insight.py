"""On-demand LLM insight for a Business Validation explorer chart.

The frontend sends the chart spec plus the underlying project data rows (not
aggregated — Graphic Walker 0.4.84 exposes no view-data export, so we ground the
LLM on the raw rows and its own chart configuration instead). The LLM only
interprets those numbers into a short business reading — it never invents metrics
not present in the rows (the project-wide rule). Any LLM problem degrades to an
empty string so the caller can offer a retry without blocking the gate.
"""
from __future__ import annotations

import json

from app.agents.common import agent_system
from app.llm.volcano import LLMError, get_llm

SYS = agent_system("data")

_MAX_ROWS = 400


async def generate_insight(spec: dict, rows: list[dict]) -> str:
    try:
        llm = get_llm()
    except LLMError:
        return ""
    payload = {
        "chart": {"title": spec.get("title", ""), "encoding": spec.get("encoding", {})},
        "rows": rows[:_MAX_ROWS],
    }
    try:
        reply = await llm.json(system=SYS, user=(
            "You are reading a marketing analytics chart. The `chart` object gives "
            "the chart's configuration and filters; `rows` are the underlying project "
            "data rows. Using ONLY these rows (do not invent numbers not present in "
            "them), write one concise English business insight (<=60 words) about how "
            "the chart's plotted series relate to sell-out over time. Return JSON "
            "{\"insight\": \"...\"}.\n\n"
            + json.dumps(payload, ensure_ascii=False)))
    except LLMError:
        return ""
    if isinstance(reply, dict):
        return str(reply.get("insight", "")).strip()
    return ""
