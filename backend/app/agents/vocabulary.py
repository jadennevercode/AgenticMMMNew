"""Per-industry model classification vocabulary — the Y / X / spend / money /
volume keyword banks and the L1 taxonomy labels that decide, for every long-table
row, whether it is the response, a driver, or spend.

The vocabulary was hardcoded in ``app.mmm.pivot``. It now lives here as
``DEFAULT_VOCAB`` (the exact former constants) and is resolved per industry by
``build_vocab`` — a Knowledge ``rules`` template's optional ``vocab`` payload
overrides the defaults, mirroring how ``build_range_index`` resolves the
ROI/contribution ranges. With no override present, ``build_vocab`` returns
``DEFAULT_VOCAB``, so every current number is unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional


@dataclass(frozen=True)
class Vocab:
    """The classification vocabulary for one industry."""
    y_metric_types: frozenset[str]
    y_keywords: frozenset[str]
    y_tags: frozenset[str]
    driver_tags: frozenset[str]
    spend_types: frozenset[str]
    spend_keywords: frozenset[str]
    volume_keywords: frozenset[str]
    money_keywords: frozenset[str]
    y_l1_labels: frozenset[str]        # L1 values that mark a response (upper-cased)
    driver_l1_labels: frozenset[str]   # L1 values that mark a driver (upper-cased)


# The exact former ``pivot.py`` constant values — the byte-parity default.
DEFAULT_VOCAB = Vocab(
    y_metric_types=frozenset({"箱数", "volume", "value", "rmb", "gmv", "unit", "百分比箱数"}),
    y_keywords=frozenset({"offtake", "sales", "gmv", "出货", "完成", "volume", "箱数"}),
    y_tags=frozenset({"y", "kpi"}),
    driver_tags=frozenset({"x", "driver", "spending", "spend"}),
    # A currency unit says "this row is money", not "this is money we spent" —
    # ``rmb`` used to sit here and classified Value / GMV / sales value / RSP /
    # Smartpath sales / Average Price as paid spend, giving a price metric an ROI
    # of incremental/Σprice and flagging a (correctly) negative price coefficient
    # as a wrong-sign paid driver. Every genuine spend row in the reference data
    # is caught by ``spend_keywords`` on the metric name, and per-project uploads
    # carry the explicit ``spending`` tag, so dropping it loses no real spend.
    spend_types=frozenset({"spending"}),
    # Aligned with ``indicator_metadata._SPEND_RE``, the semantic classifier every
    # per-project binding tags through. This bank was missing 花费 / 投入 / 预算 /
    # budget, so the two disagreed about the most common Chinese spend word of all;
    # with ``rmb`` gone from ``spend_types`` the name is now the only signal a
    # reference-taxonomy row has, and the gap would silently drop it from ROI.
    spend_keywords=frozenset({"spend", "spending", "promotion", "budget",
                              "花费", "费用", "投放", "金额", "投入", "预算"}),
    volume_keywords=frozenset({"箱", "volume", "unit"}),
    money_keywords=frozenset({"rmb", "value", "gmv", "金额", "元"}),
    y_l1_labels=frozenset({"KPI"}),
    driver_l1_labels=frozenset({"MARKETING FACTOR", "COMMERCIAL FACTOR"}),
)


def _merge(base: Vocab, vr: object) -> Vocab:
    """Return a Vocab overriding each field the template payload actually sets
    (a non-empty list); every unset field falls back to ``base``."""
    def pick(attr: str) -> Optional[frozenset[str]]:
        vals = getattr(vr, attr, None)
        if vals:
            return frozenset(str(v).strip() for v in vals if str(v).strip())
        return None
    updates: dict[str, frozenset[str]] = {}
    for field_name in (
        "y_metric_types", "y_keywords", "y_tags", "driver_tags", "spend_types",
        "spend_keywords", "volume_keywords", "money_keywords",
    ):
        v = pick(field_name)
        if v is not None:
            updates[field_name] = v
    # L1 label overrides are upper-cased to match the predicates' comparison.
    for field_name, src in (("y_l1_labels", "y_l1_labels"), ("driver_l1_labels", "driver_l1_labels")):
        vals = getattr(vr, src, None)
        if vals:
            updates[field_name] = frozenset(str(v).strip().upper() for v in vals if str(v).strip())
    return replace(base, **updates) if updates else base


def build_vocab(industry_l1: Optional[str] = None, industry_l2: Optional[str] = None) -> Vocab:
    """The classification vocabulary for an industry — a Knowledge ``rules``
    template's ``vocab`` payload overriding ``DEFAULT_VOCAB``, else the default."""
    try:
        from app.store.templates import get_templates
        tpl = get_templates().best_match("rules", industry_l1, industry_l2)
        vr = getattr(tpl, "vocab", None) if tpl else None
        if vr:
            return _merge(DEFAULT_VOCAB, vr)
    except Exception:  # noqa: BLE001 — no template store / bad payload → default
        pass
    return DEFAULT_VOCAB


def vocab_for(st: object) -> Vocab:
    """Resolve the vocabulary for a project's state (from its industry)."""
    meta = getattr(st, "meta", None)
    industry = getattr(meta, "industry", None)
    return build_vocab(getattr(industry, "l1", None), getattr(industry, "l2", None))
