"""2.3 · the AI's reading of one Business-Validation chart.

The analysis is grounded on **exactly the arrays the chart plotted** — the same
`validation_series` response the user is looking at — so it can name real periods
and real magnitudes instead of describing marketing in general.

Two rules make that trustworthy:

* **The facts are computed, the prose is written.** Every number the model is
  allowed to quote (first/last/peak/trough, the largest period-over-period move,
  the longest monotone run, the gap count, the correlation with the response) is
  derived here in pandas-free Python and handed over as an authoritative `FACTS`
  block. The model narrates it. This is the same contract the assistant's
  `MODEL RESULTS` line has, and it is why a "specific" analysis is safe to ask for.
* **Gaps are gaps.** A missing period is passed through as such and the model is
  told to say so rather than interpolate over it.

With no LLM configured the deterministic facts are rendered as prose instead, so
a chart always carries an analysis — just one that says where it came from.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from app.agents.common import agent_system
from app.domain.models import ChartObservation, ValidationChartAnalysis
from app.llm.volcano import LLMError, get_llm

SYS = agent_system("data")

# The filter fields that define "which chart is this" — the analysis key. Ordered,
# so the same filter state always hashes the same way.
_KEY_FIELDS = ("l3", "l4", "l5", "l6", "l7", "l8", "grain", "indicators",
               "sources", "brand", "channelType", "provinceGroup", "yoyMonth")

# A long axis is summarised, not transcribed: the FACTS block already carries the
# shape, and pasting 200 periods per series buys nothing but tokens.
_MAX_POINTS = 120


#: The value each key field takes when the caller did not set it. This has to match
#: what `ValidationSeriesQuery` produces, field for field: the batch generator and
#: the on-demand endpoint must hash an *identical* dict or the pre-generated
#: analyses are cached under keys the UI never asks for. (They were: a missing
#: level read as `None` from the batch and `""` from the endpoint, and 15 of 16
#: pre-generated readings were invisible.)
_KEY_DEFAULTS: dict = {
    "l3": "", "l4": "", "l5": "", "l6": "", "l7": "", "l8": "",
    "grain": "month", "indicators": [], "sources": [], "brand": [],
    "channelType": [], "provinceGroup": [], "yoyMonth": 0,
}


def normalize_query(query: dict) -> dict:
    """The canonical, hashable filter state — every key field present and typed."""
    out: dict = {}
    for k, default in _KEY_DEFAULTS.items():
        v = query.get(k, default)
        if v is None:
            v = default
        out[k] = list(v) if isinstance(default, list) else (
            int(v) if isinstance(default, int) else str(v))
    return out


def analysis_key(query: dict) -> str:
    """A stable id for the chart a filter state produces."""
    raw = json.dumps(normalize_query(query), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def series_digest(res: dict) -> str:
    """A fingerprint of the plotted numbers.

    Two analyses with the same key but different digests mean the data moved under
    a cached reading — the difference between "this is still true" and "this was
    true of numbers we no longer have".
    """
    payload = {
        "x": res.get("x") or [],
        "kpi": (res.get("kpi") or {}).get("data") or [],
        "series": [[s.get("metric"), s.get("data")] for s in (res.get("series") or [])],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def filter_label(res: dict, query: dict) -> str:
    """A human breadcrumb of what was plotted, for the analysis header."""
    parts = [f"{b.get('level')}: {b.get('value')}" for b in (res.get("breadcrumb") or [])]
    grain = str(query.get("grain") or res.get("grain") or "month").replace("_", "-")
    dims = [f"{k}: {', '.join(v)}"
            for k, v in (("Brand", query.get("brand")), ("Channel", query.get("channelType")),
                         ("Region", query.get("provinceGroup")))
            if v]
    return " · ".join([*parts, f"by {grain}", *dims])


# ── deterministic facts ─────────────────────────────────────────────────────


def _clean(pairs: list[tuple[str, Optional[float]]]) -> list[tuple[str, float]]:
    return [(p, float(v)) for p, v in pairs if v is not None]


def _series_facts(name: str, x: list[str], data: list, unit: str = "",
                  number_format: str = "") -> dict:
    """Everything the model is allowed to quote about one series."""
    pairs = _clean(list(zip(x, data)))
    facts: dict = {"metric": name, "unit": unit, "numberFormat": number_format,
                   "observedPeriods": len(pairs), "missingPeriods": len(x) - len(pairs)}
    if not pairs:
        facts["note"] = "no observed values in this view"
        return facts

    first_p, first_v = pairs[0]
    last_p, last_v = pairs[-1]
    peak_p, peak_v = max(pairs, key=lambda pv: pv[1])
    trough_p, trough_v = min(pairs, key=lambda pv: pv[1])
    facts.update({
        "first": {"period": first_p, "value": round(first_v, 4)},
        "last": {"period": last_p, "value": round(last_v, 4)},
        "peak": {"period": peak_p, "value": round(peak_v, 4)},
        "trough": {"period": trough_p, "value": round(trough_v, 4)},
    })
    if first_v:
        facts["changeFirstToLastPct"] = round((last_v - first_v) / abs(first_v) * 100, 1)

    # Largest single period-over-period move — the candidate anomaly.
    if len(pairs) > 1:
        i = max(range(1, len(pairs)), key=lambda j: abs(pairs[j][1] - pairs[j - 1][1]))
        d = pairs[i][1] - pairs[i - 1][1]
        base = abs(pairs[i - 1][1])
        facts["largestMove"] = {
            "from": pairs[i - 1][0], "to": pairs[i][0], "delta": round(d, 4),
            "deltaPct": round(d / base * 100, 1) if base else None,
        }

    # Longest run in one direction — the candidate trend / inflection boundary.
    best = cur = 1
    best_end = cur_dir = 0
    for i in range(1, len(pairs)):
        d = pairs[i][1] - pairs[i - 1][1]
        step = 1 if d > 0 else (-1 if d < 0 else 0)
        if step and step == cur_dir:
            cur += 1
        else:
            cur, cur_dir = 2 if step else 1, step
        if cur > best:
            best, best_end = cur, i
    if best >= 3:
        start_i = best_end - best + 1
        facts["longestRun"] = {
            "direction": "rising" if pairs[best_end][1] > pairs[start_i][1] else "falling",
            "from": pairs[start_i][0], "to": pairs[best_end][0], "periods": best,
        }
    return facts


def _pearson(a: list, b: list) -> Optional[float]:
    """Correlation over the periods both series actually cover."""
    pairs = [(float(u), float(v)) for u, v in zip(a, b) if u is not None and v is not None]
    if len(pairs) < 3:
        return None
    n = len(pairs)
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    if sxx <= 0 or syy <= 0:
        return None
    return round(sxy / (sxx ** 0.5 * syy ** 0.5), 3)


def compute_facts(res: dict) -> dict:
    """The authoritative numbers for one chart — computed, never asked of the LLM."""
    x = list(res.get("x") or [])[-_MAX_POINTS:]
    n = len(res.get("x") or [])
    off = max(0, n - _MAX_POINTS)
    kpi = res.get("kpi") or None

    facts: dict = {"grain": res.get("grain", ""), "periods": x,
                   "periodCount": n, "truncated": off > 0}
    if kpi:
        kdata = list(kpi.get("data") or [])[off:]
        facts["response"] = _series_facts(
            str(kpi.get("metric") or "KPI"), x, kdata,
            str(kpi.get("unit") or ""), str(kpi.get("numberFormat") or ""))
    drivers = []
    for s in res.get("series") or []:
        sdata = list(s.get("data") or [])[off:]
        f = _series_facts(str(s.get("metric") or ""), x, sdata,
                          str(s.get("unit") or ""), str(s.get("numberFormat") or ""))
        if kpi:
            f["correlationWithResponse"] = _pearson(sdata, list(kpi.get("data") or [])[off:])
        drivers.append(f)
    facts["drivers"] = drivers
    return facts


# ── prose ───────────────────────────────────────────────────────────────────

_PROMPT = """You are reading ONE chart from a marketing-mix data validation review.

FACTS below are computed from the exact series the chart plots. They are
authoritative. Do not compute, estimate, round differently, or invent any number
that is not in FACTS — quote them.

Write a specific reading of THIS chart:
- `headline`: one sentence a client would recognise as being about their data,
  naming at least one real period and one real magnitude from FACTS.
- `trends`: 2-4 statements about direction and pace over named period ranges.
  Say how a driver moves relative to the response where FACTS support it
  (`correlationWithResponse` is the only correlation you may cite).
- `anomalies`: periods where a series breaks its own pattern — use
  `largestMove`, `peak`, `trough`. Give the period and what happened. Do not
  assert a cause; say "cause not established from this data" when tempted.
- `inflections`: where a direction changes — cite the periods either side.
- `caveats`: gaps (`missingPeriods` > 0), short coverage, truncation. If a series
  has missing periods, say so instead of describing the gap as a value.

Return ONLY JSON:
{"headline": "...", "trends": ["..."],
 "anomalies": [{"period": "...", "metric": "...", "note": "..."}],
 "inflections": [{"period": "...", "metric": "...", "note": "..."}],
 "caveats": ["..."]}

English only. Be concrete. An empty list is better than a vague entry.

FACTS:
"""


def _obs(items: object, limit: int = 6) -> list[ChartObservation]:
    out: list[ChartObservation] = []
    for it in (items if isinstance(items, list) else [])[:limit]:
        if isinstance(it, dict):
            out.append(ChartObservation(period=str(it.get("period", "")),
                                        metric=str(it.get("metric", "")),
                                        note=str(it.get("note", ""))))
        elif isinstance(it, str) and it.strip():
            out.append(ChartObservation(note=it.strip()))
    return out


def _strs(items: object, limit: int = 6) -> list[str]:
    return [str(s).strip() for s in (items if isinstance(items, list) else [])[:limit]
            if str(s).strip()]


def _fallback(facts: dict) -> dict:
    """The computed facts as prose — used when no LLM is configured.

    Deliberately plain: it must be obvious this is a readout, not an analysis, so
    nobody mistakes it for a judgement the AI made.
    """
    resp = facts.get("response") or {}
    trends: list[str] = []
    anomalies: list[dict] = []
    caveats: list[str] = []

    if resp.get("first"):
        chg = resp.get("changeFirstToLastPct")
        trends.append(
            f"{resp['metric']} moved from {resp['first']['value']:g} ({resp['first']['period']}) "
            f"to {resp['last']['value']:g} ({resp['last']['period']})"
            + (f", {chg:+.1f}%." if chg is not None else "."))
    for d in facts.get("drivers") or []:
        if not d.get("first"):
            caveats.append(f"{d['metric']} has no observed values in this view.")
            continue
        r = d.get("correlationWithResponse")
        trends.append(
            f"{d['metric']} peaks at {d['peak']['value']:g} ({d['peak']['period']}) and "
            f"bottoms at {d['trough']['value']:g} ({d['trough']['period']})"
            + (f"; correlation with the response is {r:+.2f}." if r is not None else "."))
        mv = d.get("largestMove")
        if mv:
            pct = f" ({mv['deltaPct']:+.1f}%)" if mv.get("deltaPct") is not None else ""
            anomalies.append({"period": mv["to"], "metric": d["metric"],
                              "note": f"largest single move: {mv['delta']:+g}{pct} from {mv['from']}"})
        if d.get("missingPeriods"):
            caveats.append(f"{d['metric']} is missing {d['missingPeriods']} period(s) in this view.")
    if facts.get("truncated"):
        caveats.append(f"Only the most recent {_MAX_POINTS} periods were analysed.")

    return {
        "headline": (f"{resp.get('metric', 'The response')} over "
                     f"{facts.get('periodCount', 0)} {facts.get('grain', 'period')}(s), "
                     f"with {len(facts.get('drivers') or [])} driver(s) — computed readout "
                     f"(no language model configured)."),
        "trends": trends[:4],
        "anomalies": anomalies[:6],
        "inflections": [],
        "caveats": caveats[:6],
    }


async def analyze_chart(res: dict, query: dict, *, now: str = "") -> ValidationChartAnalysis:
    """Read one chart. Never raises: an LLM problem degrades to the computed readout."""
    facts = compute_facts(res)
    fallback = False
    try:
        llm = get_llm()
        reply = await llm.json(system=SYS, user=_PROMPT + json.dumps(facts, ensure_ascii=False))
        if not isinstance(reply, dict) or not str(reply.get("headline", "")).strip():
            raise LLMError("empty analysis")
    except Exception:  # noqa: BLE001 — an unread chart is worse than a computed readout
        reply = _fallback(facts)
        fallback = True

    return ValidationChartAnalysis(
        key=analysis_key(query),
        l3=str(query.get("l3") or res.get("l3") or ""),
        filterLabel=filter_label(res, query),
        headline=str(reply.get("headline", "")).strip(),
        trends=_strs(reply.get("trends")),
        anomalies=_obs(reply.get("anomalies")),
        inflections=_obs(reply.get("inflections")),
        caveats=_strs(reply.get("caveats")),
        seriesDigest=series_digest(res),
        generatedAt=now,
        fallback=fallback,
    )
