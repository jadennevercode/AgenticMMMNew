"""On-demand LLM insight for a Business Validation explorer chart.

The frontend sends the chart spec plus the ROWS IT ALREADY AGGREGATED for display.
The LLM only interprets those numbers into a short business reading — it never
computes or invents metrics (the project-wide rule). Any LLM problem degrades to
an empty string so the caller can offer a retry without blocking the gate.
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
        "aggregatedRows": rows[:_MAX_ROWS],
    }
    try:
        reply = await llm.json(system=SYS, user=(
            "You are reading a marketing analytics chart. Using ONLY the aggregated "
            "rows given (do not invent or recompute any number), write one concise "
            "English business insight (<=60 words) about how the plotted series relate "
            "to sell-out over time. Return JSON {\"insight\": \"...\"}.\n\n"
            + json.dumps(payload, ensure_ascii=False)))
    except LLMError:
        return ""
    if isinstance(reply, dict):
        return str(reply.get("insight", "")).strip()
    return ""
