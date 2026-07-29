"""2.5 · what each fitted model actually says.

With one regression per channel × product there are now N×M results to read, and
a reviewer opening the artifact meets a wall of coefficient tables. This asks the
model to do the reading it can honestly do: name the indicators that carry the
result and describe the shape of the fit — per model object, one short paragraph.

The division of labour is the same as everywhere else in S2. **Every number is
computed upstream** by ``app.mmm`` and handed over as fact; the LLM ranks, groups
and explains, and must not restate a number differently or produce a new one. The
key-driver list is likewise not the model's opinion: it is computed here by
contribution magnitude among the significant drivers, and the LLM is asked to
explain that list, not to choose it. With no LLM configured the list still stands
and the paragraph falls back to a deterministic reading of the same numbers.

One request per model object, run concurrently under a small semaphore — an LLM
that is slow or down degrades the artifact, it never blocks the fit.
"""
from __future__ import annotations

import asyncio
import json

from app.agents.common import agent_system
from app.agents.model_objects import object_label
from app.llm.volcano import LLMError, get_llm

SYS = agent_system("data")

# How many indicators are named as a model's key drivers.
TOP_DRIVERS = 5
# Concurrent LLM requests. The models are independent, but a project with 30
# objects must not open 30 sockets at once.
MAX_CONCURRENCY = 4
# |t| at which a driver is treated as significant (mirrors ols_review).
SIGNIFICANT_T = 2.0

_PROMPT = """You are reading ONE marketing-mix regression: a single channel × product model.

You are given the model's fit statistics and its drivers, each with COMPUTED
coefficient, t-value, p-value, ROI, and contribution (that driver's share of actual
sales). `keyDrivers` is the pre-computed ranking of the significant drivers by
contribution — the one the reader will see beside your text.

Those numbers are authoritative. Cite them; never recompute, re-round or invent one.
Never claim a driver matters if its |t| < 2 without saying it is not significant.

Write `summary`: 2-4 sentences of English, for an analyst who can see the table.
Say what carries this model (naming drivers from keyDrivers and the numbers that
make the case), then the one thing that most qualifies it — a weak fit, a baseline
that has absorbed most of the sales, a wrong-signed paid driver, too few
observations for the number of variables, a driver whose ROI looks unreal. Do not
recommend actions. Do not assert a business cause the numbers do not show. If the
model is too weak to read, say exactly that instead of narrating it.

Return ONLY JSON: {"summary": "..."}

MODEL:
"""


def key_drivers(rows: list[dict], limit: int = TOP_DRIVERS) -> list[dict]:
    """The drivers that carry a model: significant ones, by contribution size.

    Computed, not asked for. Significance comes first because a large contribution
    resting on ``|t| < 2`` is the model failing to distinguish that driver from
    noise — reporting it as the model's key finding is exactly the mistake this
    ranking exists to avoid. Only if nothing clears the bar do we fall back to the
    largest contributions, and the caller says so.
    """
    def _mag(r: dict) -> float:
        c = r.get("contribution")
        try:
            return abs(float(c))
        except (TypeError, ValueError):
            return 0.0

    def _sig(r: dict) -> bool:
        t = r.get("tValue")
        try:
            return abs(float(t)) >= SIGNIFICANT_T
        except (TypeError, ValueError):
            return False

    ranked = sorted((r for r in rows if _sig(r)), key=_mag, reverse=True)
    if not ranked:
        ranked = sorted(rows, key=_mag, reverse=True)
    return ranked[:limit]


def _fallback_summary(obj: dict, drivers: list[dict], top: list[dict]) -> str:
    """The computed picture, said in words — used when no LLM is available."""
    label = obj.get("label") or object_label(obj.get("object", ""))
    r2, n_obs = obj.get("r2"), obj.get("nObs") or 0
    if obj.get("error"):
        return f"{label} could not be fitted: {obj['error']}"
    if not drivers:
        return f"{label} fitted on {n_obs} months but carries no usable drivers."

    parts = [f"{label}: R²={float(r2):.2f} over {n_obs} months and {len(drivers)} "
             f"variable(s)." if r2 is not None else f"{label}: {n_obs} months, "
             f"{len(drivers)} variable(s)."]
    if top:
        named = ", ".join(
            f"{d.get('indicator', '?')} ({float(d['contribution']):+.1f}%)"
            if d.get("contribution") is not None else str(d.get("indicator", "?"))
            for d in top[:3])
        n_sig = sum(1 for d in drivers
                    if d.get("tValue") is not None and abs(float(d["tValue"])) >= SIGNIFICANT_T)
        parts.append(f"Largest contributions: {named}."
                     if n_sig else
                     f"No variable reached |t|≥{SIGNIFICANT_T:g}; largest contributions "
                     f"(not significant): {named}.")
    base = obj.get("baselinePct")
    if base is not None and float(base) > 100:
        parts.append(f"Baseline is {float(base):.0f}% of sales — the trend/seasonality "
                     "controls have absorbed more than all of it, so the driver "
                     "contributions below are not trustworthy.")
    elif base is not None and float(base) < 0:
        parts.append(f"Baseline is {float(base):.0f}% — negative, so the fit is "
                     "mis-specified and the contributions do not decompose sales.")
    if obj.get("redFlags"):
        parts.append("Red flags: " + "; ".join(str(f) for f in obj["redFlags"][:3]) + ".")
    return " ".join(parts)


def _payload(obj: dict, drivers: list[dict], top: list[dict]) -> dict:
    return {
        "modelObject": obj.get("label") or object_label(obj.get("object", "")),
        "response": obj.get("yMetric", ""),
        "roiUnit": obj.get("roiUnit", ""),
        "fit": {k: obj.get(k) for k in
                ("r2", "adjR2", "mape", "nObs", "drivers", "dfRemaining",
                 "baselinePct", "durbinWatson")},
        "redFlags": list(obj.get("redFlags") or []),
        "controls": list(obj.get("controls") or []),
        "keyDrivers": [d.get("indicator", "") for d in top],
        "rows": [{k: d.get(k) for k in
                  ("l4", "indicator", "coef", "tValue", "pValue", "roi", "contribution")}
                 for d in drivers],
    }


async def summarize_models(objects: list[dict],
                           rows_by_object: dict[str, list[dict]]) -> dict[str, dict]:
    """``{object: {"summary", "keyDrivers", "ai"}}`` for every model. Never raises.

    ``rows_by_object`` maps a model object to its in-model tree rows (the ones
    carrying that object's own coef / t / ROI / contribution).
    """
    out: dict[str, dict] = {}
    prepared: list[tuple[str, dict]] = []
    for obj in objects:
        oid = str(obj.get("object", ""))
        drivers = rows_by_object.get(oid, [])
        top = key_drivers(drivers)
        out[oid] = {
            "summary": _fallback_summary(obj, drivers, top),
            "keyDrivers": [str(d.get("indicator", "")) for d in top],
            "ai": False,
        }
        if drivers and not obj.get("error"):
            prepared.append((oid, _payload(obj, drivers, top)))

    if not prepared:
        return out
    try:
        llm = get_llm()
    except LLMError:
        return out

    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def one(oid: str, payload: dict) -> None:
        async with sem:
            try:
                reply = await llm.json(
                    system=SYS, user=_PROMPT + json.dumps(payload, ensure_ascii=False))
            except Exception:  # noqa: BLE001 — this model keeps its computed reading
                return
            text = str((reply or {}).get("summary", "")).strip() if isinstance(reply, dict) else ""
            if text:
                out[oid] = {**out[oid], "summary": text, "ai": True}

    await asyncio.gather(*(one(oid, p) for oid, p in prepared))
    return out
