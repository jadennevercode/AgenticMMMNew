"""Unit tests for the S2 indicator lifecycle ledger.

The ledger is the contract every downstream fit depends on, so these tests pin
the two properties that matter: a rejection at any layer is **inherited** (later
layers never re-litigate it), and the resolved :class:`ModelSelection` never
lets a rejected indicator back into the model. Runs on the real reference
dataset; no LLM calls. Runnable with pytest or plain python.
"""
from __future__ import annotations

from app.agents.ledger import (
    STATUS_INHERITED,
    STATUS_REJECTED,
    funnel,
    indicator_ledger,
    model_selection,
)
from app.domain.models import (
    ArtifactInstance,
    OlsConfig,
    OlsXCandidate,
    OlsYChoice,
    QualityRow,
    QualityScorecard,
    StatScoreRow,
    StatScorecard,
)
from app.store.state import danone_meta, initial_state


def _state():
    return initial_state(danone_meta())


def _quality_drop(st, row) -> tuple[str, str]:
    """Mark one real indicator as dropped by the 2.2d quality review."""
    st.quality_scorecard = QualityScorecard(rows=[QualityRow(
        id="q-0", l1=row.l1, l2=row.l2, l3=row.l3, l4=row.l4,
        indicator=row.indicator, disposition="drop")])
    return row.key


def _stat_drop(st, row) -> tuple[str, str]:
    """Mark one real indicator as dropped by the 2.4d statistical screening."""
    st.stat_scorecard = StatScorecard(rows=[StatScoreRow(
        id="s-0", l1=row.l1, l2=row.l2, l3=row.l3, l4=row.l4,
        indicator=row.indicator, disposition="drop")])
    return row.key


def test_ledger_enumerates_the_driver_universe() -> None:
    rows = indicator_ledger(_state())
    assert len(rows) > 0, "the reference dataset must yield indicators"
    # Every row carries a verdict from each of the six layers, in order.
    for r in rows:
        assert [v.layer for v in r.verdicts] == [
            "mapping", "quality", "signoff", "statistical", "selection", "range"]
    # With nothing reviewed yet, nothing is rejected.
    assert all(r.adopted for r in rows)


def test_quality_drop_is_inherited_by_every_later_layer() -> None:
    st = _state()
    key = _quality_drop(st, indicator_ledger(st)[0])

    row = next(r for r in indicator_ledger(st) if r.key == key)
    assert not row.adopted
    assert row.rejected_at == "quality"
    # The layers after quality must not rule again — they inherit.
    after = [v for v in row.verdicts if v.layer in ("signoff", "statistical", "selection", "range")]
    assert all(v.status == STATUS_INHERITED for v in after), \
        "a later layer re-ruling on a dropped indicator is exactly the leak this prevents"
    assert key in model_selection(st).exclude


def test_statistical_drop_rejects_and_is_excluded_from_the_selection() -> None:
    st = _state()
    key = _stat_drop(st, indicator_ledger(st)[0])

    row = next(r for r in indicator_ledger(st) if r.key == key)
    assert row.rejected_at == "statistical" and not row.adopted
    assert key in model_selection(st).exclude


def test_unsigned_factor_rejects_its_indicators_but_blank_signoff_does_not() -> None:
    st = _state()
    rows = indicator_ledger(st)
    target = next(r for r in rows if r.l3)

    # A blank sign-off means "not individually reviewed" — it must not reject.
    st.artifacts.append(_validation_artifact(target.l3, ""))
    assert next(r for r in indicator_ledger(st) if r.key == target.key).adopted

    # An explicit "no" is a rejection, and it takes the whole L3 factor with it.
    st.artifacts[-1].body = {"groups": [{"l3": target.l3, "signoff": "no"}]}
    hit = next(r for r in indicator_ledger(st) if r.key == target.key)
    assert not hit.adopted and hit.rejected_at == "signoff"
    assert target.key in model_selection(st).exclude


def _validation_artifact(l3: str, signoff: str):
    return ArtifactInstance(
        id="a-business-validation", name="Business Validation", taskRef="2.3",
        type="report", stage="s2", format="validation",
        body={"groups": [{"l3": l3, "signoff": signoff}]},
    )


def test_selection_layer_rejects_unticked_variables() -> None:
    st = _state()
    rows = indicator_ledger(st)
    keep, drop = rows[0], rows[1]

    st.ols_config = OlsConfig(
        yCandidates=[], y=[OlsYChoice(object="MT", metric="Y")],
        xCandidates=[
            OlsXCandidate(key=f"{keep.key[0]}|{keep.key[1]}", l4=keep.l4,
                          indicator=keep.indicator, metric=keep.metric, selected=True),
            OlsXCandidate(key=f"{drop.key[0]}|{drop.key[1]}", l4=drop.l4,
                          indicator=drop.indicator, metric=drop.metric, selected=False),
        ],
    )
    led = {r.key: r for r in indicator_ledger(st)}
    assert led[keep.key].adopted
    assert not led[drop.key].adopted and led[drop.key].rejected_at == "selection"

    sel = model_selection(st)
    assert sel.include is not None
    assert keep.metric.strip().lower() in sel.include
    assert drop.metric.strip().lower() not in sel.include
    assert sel.y_for("MT") == "Y"


def test_selection_include_never_carries_a_rejected_indicator() -> None:
    """A tick cannot resurrect an indicator an earlier layer already rejected."""
    st = _state()
    victim = indicator_ledger(st)[0]
    key = _quality_drop(st, victim)

    # Tick the dropped indicator anyway — a stale config, or a UI that let it through.
    st.ols_config = OlsConfig(xCandidates=[OlsXCandidate(
        key=f"{key[0]}|{key[1]}", l4=victim.l4, indicator=victim.indicator,
        metric=victim.metric, selected=True)])

    sel = model_selection(st)
    assert victim.metric.strip().lower() not in (sel.include or frozenset())
    assert key in sel.exclude


def test_funnel_layers_account_for_every_indicator() -> None:
    st = _state()
    _quality_drop(st, indicator_ledger(st)[0])

    f = funnel(st)
    assert [x["layer"] for x in f] == [
        "mapping", "quality", "signoff", "statistical", "selection", "range"]
    # Each layer's survivors feed the next layer's intake — no indicator vanishes.
    for prev, nxt in zip(f, f[1:]):
        assert prev["survivors"] == nxt["intake"]
    quality = next(x for x in f if x["layer"] == "quality")
    assert quality["rejected"] == 1 and len(quality["dropped"]) == 1
    assert quality["dropped"][0]["reason"]


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("\nAll ledger tests passed.")
