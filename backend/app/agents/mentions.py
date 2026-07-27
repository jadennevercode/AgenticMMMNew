"""Chat `@`-mentions: pin a specific object as the subject of a question.

The assistant already grounds on the project's artifacts, but "the artifacts" is
sixteen documents — asking "why did this dip in March?" about one chart gets an
answer about the project. A mention names the exact object:

* ``chartTable``    — one Business-Validation chart's data, **re-resolved** from the
  filter state that produced it rather than trusted from the client, so the numbers
  in the answer are the numbers the chart is showing right now.
* ``chartAnalysis`` — the AI reading already generated for that chart.
* ``artifact``      — any produced artifact, by id.

Everything is rendered to a bounded text block: a mention is context for one
question, not a data export, and an unbounded table would push the artifacts it is
supposed to be read against out of the prompt.
"""
from __future__ import annotations

from typing import Optional

# Per-mention and total caps on injected context. A table is truncated from the
# oldest periods, because a question about a chart is nearly always about its
# recent end.
_MAX_TABLE_ROWS = 40
_MAX_MENTION_CHARS = 6000
_MAX_TOTAL_CHARS = 18000


def catalogue(st) -> list[dict]:
    """Everything mentionable in this project: artifacts, chart tables, analyses."""
    out: list[dict] = []
    for a in st.artifacts:
        if getattr(a, "internal", False):
            continue
        out.append({"kind": "artifact", "refId": a.id, "label": a.name,
                    "group": "Artifacts"})

    bv = st.artifact("a-business-validation")
    groups = ((bv.body or {}).get("groups") or []) if bv is not None else []
    for g in groups:
        l3 = str(g.get("l3") or "")
        if not l3:
            continue
        out.append({"kind": "chartTable", "refId": l3, "label": f"{l3} · data table",
                    "group": "Business Validation"})

    for key, a in (getattr(st, "validation_chart_analyses", None) or {}).items():
        label = str(a.get("l3") or "") or "chart"
        out.append({"kind": "chartAnalysis", "refId": key,
                    "label": f"{label} · AI analysis", "group": "Business Validation"})
    return out


def _table_block(res: dict, label: str) -> str:
    """One chart's periods and series as a compact markdown table."""
    x = list(res.get("x") or [])
    cols: list[tuple[str, list]] = []
    kpi = res.get("kpi") or None
    if kpi:
        cols.append((f"{kpi.get('metric')} (Y)", list(kpi.get("data") or [])))
    for s in res.get("series") or []:
        cols.append((str(s.get("metric") or ""), list(s.get("data") or [])))
    if not x or not cols:
        return f"### {label}\n(no plotted data under these filters)\n"

    keep = min(len(x), _MAX_TABLE_ROWS)
    off = len(x) - keep
    head = "| Period | " + " | ".join(n for n, _ in cols) + " |"
    rule = "|---" * (len(cols) + 1) + "|"
    lines = [f"### {label}", ""]
    if off:
        lines.append(f"(showing the last {keep} of {len(x)} periods)")
        lines.append("")
    lines += [head, rule]
    for i in range(off, len(x)):
        cells = []
        for _n, data in cols:
            v = data[i] if i < len(data) else None
            cells.append("—" if v is None else f"{float(v):g}")
        lines.append(f"| {x[i]} | " + " | ".join(cells) + " |")

    yearly = res.get("yearly") or {}
    if yearly.get("rows"):
        lines += ["", f"Year over year ({yearly.get('monthLabel', 'Full year')}):",
                  "| Indicator | " + " | ".join(str(y) for y in yearly.get("years") or []) + " |",
                  "|---" * (1 + len(yearly.get("years") or [])) + "|"]
        for r in yearly["rows"]:
            vals = []
            for v, yoy in zip(r.get("values") or [], r.get("yoy") or []):
                cell = "—" if v is None else f"{float(v):g}"
                if yoy is not None:
                    cell += f" ({float(yoy):+.1f}%)"
                vals.append(cell)
            lines.append(f"| {r.get('metric')} | " + " | ".join(vals) + " |")
    return "\n".join(lines) + "\n"


def _analysis_block(a: dict, label: str) -> str:
    lines = [f"### {label}", a.get("headline", "")]
    for name, key in (("Trends", "trends"), ("Caveats", "caveats")):
        items = a.get(key) or []
        if items:
            lines += [f"{name}:"] + [f"- {t}" for t in items]
    for name, key in (("Anomalies", "anomalies"), ("Inflections", "inflections")):
        items = a.get(key) or []
        if items:
            lines += [f"{name}:"] + [
                f"- {o.get('period', '')} {o.get('metric', '')}: {o.get('note', '')}".strip()
                for o in items]
    return "\n".join(lines) + "\n"


def resolve(st, mentions: list[dict]) -> tuple[str, list[str]]:
    """Render mentions to a grounding block. Returns ``(text, resolved_labels)``.

    A mention that cannot be resolved is reported in the text rather than dropped:
    an answer grounded on less than the user pointed at should say so.
    """
    from app.agents.common import artifact_text

    blocks: list[str] = []
    labels: list[str] = []
    used = 0
    for m in mentions or []:
        kind = str(m.get("kind") or "")
        ref = str(m.get("refId") or "")
        label = str(m.get("label") or ref)
        block = ""
        if kind == "artifact":
            body = artifact_text(st, [ref])
            block = f"### {label}\n{body}\n" if body.strip() else ""
        elif kind == "chartAnalysis":
            a = (getattr(st, "validation_chart_analyses", None) or {}).get(ref)
            block = _analysis_block(a, label) if a else ""
        elif kind == "chartTable":
            payload = m.get("payload") if isinstance(m.get("payload"), dict) else {}
            block = _chart_table(st, ref, payload, label)

        if not block:
            blocks.append(f"### {label}\n(could not be resolved — it may have been "
                          f"re-generated or the filters no longer match any rows)\n")
            continue
        if len(block) > _MAX_MENTION_CHARS:
            block = block[:_MAX_MENTION_CHARS] + "\n…(truncated)\n"
        if used + len(block) > _MAX_TOTAL_CHARS:
            blocks.append(f"### {label}\n(omitted — the mentioned context exceeded "
                          f"what fits in one question)\n")
            continue
        used += len(block)
        blocks.append(block)
        labels.append(label)
    return ("\n".join(blocks), labels)


def _chart_table(st, l3: str, payload: dict, label: str) -> str:
    """Re-run the chart's own query so the table is what the chart shows now."""
    from app.agents.time_windows import resolve_window
    from app.dataeng import validation_query

    def _lst(k: str) -> Optional[list]:
        v = payload.get(k)
        return v or None

    try:
        res = validation_query.validation_series(
            st,
            l3=str(payload.get("l3") or l3),
            l4=payload.get("l4") or None, l5=payload.get("l5") or None,
            l6=payload.get("l6") or None, l7=payload.get("l7") or None,
            l8=payload.get("l8") or None,
            indicators=_lst("indicators"), grain=str(payload.get("grain") or "month"),
            sources=_lst("sources"), brand=_lst("brand"),
            channel_type=_lst("channelType"), province_group=_lst("provinceGroup"),
            window=resolve_window(st, str(payload.get("timeWindowId") or "")),
            yoy_month=int(payload.get("yoyMonth") or 0),
        )
    except Exception:  # noqa: BLE001 — an unresolvable chart is reported, not raised
        return ""
    return _table_block(res, label)
