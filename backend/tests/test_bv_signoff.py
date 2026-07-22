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


if __name__ == "__main__":
    test_bv_groups_carry_their_indicator_pairs()
