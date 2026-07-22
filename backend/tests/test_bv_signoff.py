"""Unit tests for the 2.3 Business Validation groups' per-indicator pairs.

Each `_bv_groups` entry (one per L3 marketing factor) must declare the
(l4, indicator) pairs it covers, so the frontend can offer a per-indicator
Accept/Deny alongside the existing per-factor sign-off. The pairs live in the
same key space as `ledger.signoff_key` (raw, un-normalised l4/indicator —
the frontend normalises when it builds keys). Runs on the real reference
dataset; no LLM calls. Runnable with pytest or plain python.
"""
from __future__ import annotations

from app.store.state import danone_meta, initial_state


def _state():
    return initial_state(danone_meta())


def test_bv_groups_carry_their_indicator_pairs() -> None:
    """The 2.3 UI needs to know which indicators sit under each chart so it can
    offer a per-indicator Accept / Deny."""
    from app.agents.data import _bv_groups
    from app.agents.dataset_cache import model_df

    st = _state()
    groups = _bv_groups(st, model_df(st))
    assert groups, "the reference dataset must yield validation groups"
    assert all("pairs" in g for g in groups), "every group must carry its pairs"
    assert any(g["pairs"] for g in groups), "at least one group must have indicators"
    for g in groups:
        for pr in g["pairs"]:
            assert set(pr) == {"l4", "indicator"}
            assert pr["indicator"].strip(), "a pair with no indicator is not a key"
    print("✓ bv groups carry their indicator pairs")


def test_bv_pairs_land_in_the_ledger_key_space() -> None:
    """Every pair a chart emits must have a matching ledger row — not merely
    overlap with the ledger's key space. (C1: `indicator_ledger` used to be
    built from a driver universe that collapsed (l4, metric) to one row per
    metric with an arbitrary L4, so most emitted pairs had no ledger row at
    all — a bare intersection assertion here passed at 1/93 and did not catch
    it.) A shape mismatch on any single pair would mean sign-off silently
    rejects nothing for that indicator."""
    from app.agents.data import _bv_groups
    from app.agents.dataset_cache import model_df
    from app.agents.ledger import indicator_ledger, signoff_key

    st = _state()
    df = model_df(st)
    groups = _bv_groups(st, df)
    emitted = {signoff_key(p["l4"], p["indicator"]) for g in groups for p in g["pairs"]}
    ledger_keys = {signoff_key(r.l4, r.indicator) for r in indicator_ledger(st)}
    missing = sorted(emitted - ledger_keys)
    assert not missing, missing[:5]
    print("✓ bv pairs land in the ledger key space")


if __name__ == "__main__":
    test_bv_groups_carry_their_indicator_pairs()
    test_bv_pairs_land_in_the_ledger_key_space()
