"""2.5 · the AI's judgement on each fitted factor against its Knowledge band.

The deterministic range check answers one question — is this number inside the
band? — and it answers it the same way whether the band came from a close industry
match or a distant one, whether the coefficient is significant or noise, and
whether the factor was the model's strongest driver or its weakest. A reviewer
needs the reading, not just the flag.

So this asks the model to *judge*, and only to judge:

* every number (`roi`, `contribution`, `roiStatus`, `contributionStatus`, `tValue`)
  is computed upstream and handed over as fact — the LLM may cite them and must
  not restate them differently or produce new ones;
* the output is a verdict plus a ≤30-word rationale that rides **alongside** the
  computed status, never replacing it.

With no LLM configured each row falls back to a templated rationale derived from
the same computed status, so the column is never blank and never pretends.
"""
from __future__ import annotations

import json

from app.agents.common import agent_system
from app.llm.volcano import LLMError, get_llm

SYS = agent_system("data")

# One request per chunk of rows — a 200-factor tree in one prompt is neither
# reliable nor recoverable when it fails.
_CHUNK = 30

_VERDICTS = {"consistent", "questionable", "implausible", "noBenchmark"}

_PROMPT = """You are reviewing a marketing-mix regression, factor by factor.

Each row gives a factor, the indicator the search chose for it, and the fit's
COMPUTED results. Those numbers are authoritative: cite them, never recompute,
re-round or invent them. `roiStatus` / `contributionStatus` are the deterministic
range checks ("in" = inside the Knowledge band, "out" = outside, "none" = no band
to check against).

For each row return a judgement:
- "consistent"   — the result is credible for this factor: in-band, or out of band
                   for a reason the numbers themselves support.
- "questionable" — the result is out of band, or in band but resting on a weak
                   coefficient (|tValue| < 2), or the band is a distant match.
- "implausible"  — the result contradicts how this factor can behave: a paid
                   driver with a negative coefficient, a contribution far beyond
                   its band, an ROI that cannot be real.
- "noBenchmark"  — no band exists; judge the coefficient's sign and significance
                   only, and say so.

`rationale`: <=30 words, English, naming the specific number that decided it. Do
not recommend actions. Do not assert business causes the numbers do not show.

Return ONLY JSON: {"rows": [{"key": "<key as given>", "verdict": "...", "rationale": "..."}]}

ROWS:
"""


def _fallback_rationale(row: dict) -> tuple[str, str]:
    """The computed status, said in words. Used when no LLM is available."""
    roi_s, con_s = row.get("roiStatus"), row.get("contributionStatus")
    t = row.get("tValue")
    weak = t is not None and abs(float(t)) < 2.0
    if roi_s == "none" and con_s == "none":
        base = "No Knowledge band for this factor"
        if row.get("coef") is not None:
            base += f"; coefficient {float(row['coef']):+.3g}"
        if weak:
            base += " and not statistically significant"
        return "noBenchmark", base + "."
    out = [n for n, s in (("ROI", roi_s), ("Contribution", con_s)) if s == "out"]
    if out:
        return "questionable", (
            f"{' and '.join(out)} outside the Knowledge band "
            f"({row.get('roiRange') or row.get('contributionRange') or 'n/a'}).")
    if weak:
        return "questionable", (
            f"Inside the band but the coefficient is not significant (t={float(t):+.2f}).")
    return "consistent", "Inside the Knowledge band for this factor."


async def review_rows(rows: list[dict]) -> dict[str, dict]:
    """``{key: {"verdict", "rationale"}}`` for every row. Never raises."""
    out: dict[str, dict] = {}
    for r in rows:
        v, why = _fallback_rationale(r)
        out[str(r.get("key", ""))] = {"verdict": v, "rationale": why, "ai": False}
    if not rows:
        return out

    try:
        llm = get_llm()
    except LLMError:
        return out

    for i in range(0, len(rows), _CHUNK):
        chunk = rows[i:i + _CHUNK]
        try:
            reply = await llm.json(system=SYS, user=_PROMPT + json.dumps(chunk, ensure_ascii=False))
        except Exception:  # noqa: BLE001 — a failed chunk keeps its computed rationale
            continue
        for item in (reply.get("rows") if isinstance(reply, dict) else None) or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", ""))
            if key not in out:
                continue
            verdict = str(item.get("verdict", "")).strip()
            rationale = str(item.get("rationale", "")).strip()
            if verdict in _VERDICTS and rationale:
                out[key] = {"verdict": verdict, "rationale": rationale, "ai": True}
    return out
