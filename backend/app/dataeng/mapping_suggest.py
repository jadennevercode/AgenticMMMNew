"""2.1 mapping suggestions — propose a published indicator for each pending row.

``resolve_factor_map`` only ever reports *exact* coverage (tree_row_id → full
L1–L4 path → L3 + indicator name). Anything else lands as ``pending``, which left
the human hand-hunting through the whole indicator catalog for every unmatched
factor — the one place in S2 where the AI contributed nothing.

This module scores the remaining candidates fuzzily and proposes the best one.
The score is deterministic (name overlap · path proximity · unit agreement ·
coverage); an LLM, when configured, only writes the sentence explaining it — the
match itself is never invented.

Accepting a suggestion binds ``indicator.tree_row_id`` to the row, which the
existing resolver then reports as ``mapped`` through its own exact-match path.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.agents.data_request import _norm
from app.store.state import ProjectState

# Below this the match is too weak to put in front of a human as a proposal.
MIN_SCORE = 0.30
# How many alternates to offer alongside the best match.
MAX_ALTERNATES = 4

_TOKEN_SPLIT = re.compile(r"[\s_\-/·|,，、()（）\[\]]+")
_CJK = re.compile(r"[^一-鿿]")


@dataclass(frozen=True)
class Suggestion:
    """One proposed indicator for a pending factor row."""
    indicator_id: str
    metric: str
    asset_id: str
    asset_name: str
    unit: str
    coverage_start: str
    coverage_end: str
    score: float
    reason: str


def _tokens(s: str) -> set[str]:
    """Word tokens plus CJK bigrams.

    Deliberately not built on ``data_request._norm``: that strips whitespace
    outright, which collapses "brand social spend" to one token and scores every
    multi-word English pair at zero. Here separators are preserved as boundaries
    (for English) and CJK is additionally bigrammed (Chinese names have no
    spaces to split on).
    """
    if not s:
        return set()
    low = str(s).strip().lower()
    out = {t for t in _TOKEN_SPLIT.split(low) if t}
    cjk = _CJK.sub("", low)
    out |= {cjk[i:i + 2] for i in range(len(cjk) - 1)}
    return out


def _overlap(a: str, b: str) -> float:
    """Jaccard overlap of two labels in [0, 1]."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _path_score(row, ind) -> float:
    """How much of the L1–L4 path the candidate shares with the row."""
    levels = [(row.l1, ind.l1), (row.l2, ind.l2), (row.l3, ind.l3), (row.l4, ind.l4)]
    hits = sum(1 for a, b in levels if _norm(a) and _norm(a) == _norm(b))
    # L3/L4 agreement is worth more than L1/L2 — the deep levels identify the factor.
    weighted = sum(w for (a, b), w in zip(levels, (0.5, 0.75, 1.5, 2.0))
                   if _norm(a) and _norm(a) == _norm(b))
    return (weighted / 4.75) if hits else 0.0


def _unit_score(row_indicator: str, ind) -> float:
    """Agreement between the indicator name's implied unit and the candidate's."""
    unit = _norm(ind.unit)
    name = _norm(row_indicator)
    if not unit or not name:
        return 0.0
    # Both sides are matched against the same vocabulary, so each group needs the
    # words that appear in a *unit* ("元") and the words that appear in a *name*
    # ("花费") — a list with only one of the two silently never fires.
    money = ("元", "rmb", "cny", "value", "金额", "spend", "gmv",
             "花费", "费用", "投放", "成本", "cost", "budget")
    volume = ("箱", "ton", "volume", "销量", "units", "件", "出货", "销售量")
    rate = ("%", "率", "rate", "pct", "share", "占比")
    for group in (money, volume, rate):
        if any(k in unit for k in group) and any(k in name for k in group):
            return 1.0
    return 0.0


def score(row, ind) -> float:
    """Deterministic match score in [0, 1] for a factor row × published indicator."""
    name = _overlap(row.indicator or row.l4, ind.metric)
    path = _path_score(row, ind)
    unit = _unit_score(row.indicator or row.l4, ind)
    covered = 1.0 if (ind.coverage_start and ind.coverage_end) else 0.0
    return round(0.45 * name + 0.35 * path + 0.12 * unit + 0.08 * covered, 4)


def _reason(row, ind, s: float) -> str:
    bits = []
    if _norm(row.l3) and _norm(row.l3) == _norm(ind.l3):
        bits.append(f"same L3 ({ind.l3})")
    if _overlap(row.indicator or row.l4, ind.metric) > 0:
        bits.append("overlapping indicator name")
    if _unit_score(row.indicator or row.l4, ind) > 0:
        bits.append(f"unit matches ({ind.unit})")
    if ind.coverage_start and ind.coverage_end:
        bits.append(f"covers {ind.coverage_start}–{ind.coverage_end}")
    head = "Likely match" if s >= 0.6 else "Possible match" if s >= 0.45 else "Weak match"
    return f"{head} — {', '.join(bits)}." if bits else f"{head} on name similarity alone."


def suggest_all(st: ProjectState) -> dict[str, list[Suggestion]]:
    """Ranked suggestions per pending factor row id (best first).

    A published indicator already bound to another row is not re-proposed: one
    indicator covering two factors is a mapping error, not a suggestion.
    """
    from app.dataeng.mapping import resolve_factor_map

    fmap = resolve_factor_map(st)
    pending = [r for r in fmap.rows if r.status == "pending"]
    if not pending:
        return {}
    taken = {r.row_id for r in fmap.rows if r.status == "mapped"}
    cands = [i for i in (getattr(st, "indicators", None) or [])
             if not i.tree_row_id or i.tree_row_id not in taken]
    if not cands:
        return {}

    out: dict[str, list[Suggestion]] = {}
    for row in pending:
        ranked = sorted(((score(row, i), i) for i in cands), key=lambda t: -t[0])
        picks = [
            Suggestion(
                indicator_id=i.id, metric=i.metric, asset_id=i.asset_id,
                asset_name=i.asset_name, unit=i.unit,
                coverage_start=i.coverage_start, coverage_end=i.coverage_end,
                score=s, reason=_reason(row, i, s),
            )
            for s, i in ranked[:MAX_ALTERNATES + 1] if s >= MIN_SCORE
        ]
        if picks:
            out[row.row_id] = picks
    return out


async def narrate(st: ProjectState, suggestions: dict[str, list[Suggestion]]) -> dict[str, list[Suggestion]]:
    """Best-effort: let the LLM rewrite the top pick's reason in business terms.

    Only the prose changes — the match and its score stay deterministic, so a
    missing or failing LLM costs nothing but phrasing.
    """
    from app.llm.volcano import LLMError, get_llm
    from app.agents.common import agent_system

    if not suggestions:
        return suggestions
    try:
        llm = get_llm()
    except LLMError:
        return suggestions

    from app.dataeng.mapping import resolve_factor_map
    rows = {r.row_id: r for r in resolve_factor_map(st).rows}
    payload = [{
        "id": rid,
        "factor": " › ".join(x for x in (rows[rid].l3, rows[rid].l4) if x),
        "wanted": rows[rid].indicator,
        "candidate": picks[0].metric,
        "unit": picks[0].unit,
        "score": picks[0].score,
    } for rid, picks in suggestions.items() if rid in rows]
    if not payload:
        return suggestions
    try:
        reply = await llm.json(system=agent_system("data"), user=(
            "Each row is a marketing factor that needs a data indicator, and the best "
            "candidate found in the client's published data. For each, write `reason`: "
            "one English sentence (≤20 words) on whether the candidate is the right "
            "measure for that factor. Ground it ONLY in the given names/unit/score. "
            "Say plainly when it looks wrong. Return a JSON array of {\"id\",\"reason\"}.\n\n"
            + json.dumps(payload, ensure_ascii=False)))
    except LLMError:
        return suggestions

    items = reply if isinstance(reply, list) else reply.get("rows", [])
    notes = {str(it["id"]): str(it.get("reason", "")) for it in items
             if isinstance(it, dict) and it.get("id")}
    out: dict[str, list[Suggestion]] = {}
    for rid, picks in suggestions.items():
        if notes.get(rid) and picks:
            picks = [Suggestion(**{**picks[0].__dict__, "reason": notes[rid]})] + picks[1:]
        out[rid] = picks
    return out


def bind(st: ProjectState, row_id: str, indicator_id: str) -> bool:
    """Accept a suggestion: bind the published indicator to the factor row.

    The resolver then reports the row as ``mapped`` through its ordinary
    exact-match path — no second notion of "mapped" is introduced here.
    """
    for ind in getattr(st, "indicators", None) or []:
        if ind.id == indicator_id:
            ind.tree_row_id = row_id
            ind.tree_grounded = True
            # A row that was ignored is no longer unresolved-by-choice.
            if getattr(st, "factor_map_ignores", None):
                st.factor_map_ignores.pop(row_id, None)
            return True
    return False


def unbind(st: ProjectState, row_id: str) -> bool:
    """Release whatever indicator was bound to this row (remap / undo)."""
    hit = False
    for ind in getattr(st, "indicators", None) or []:
        if ind.tree_row_id == row_id:
            ind.tree_row_id = ""
            ind.tree_grounded = False
            hit = True
    return hit
