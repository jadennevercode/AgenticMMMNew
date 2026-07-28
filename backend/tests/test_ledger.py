"""Unit tests for the S2 indicator lifecycle ledger.

The ledger is the contract every downstream fit depends on, so these tests pin
the two properties that matter: a rejection at any layer is **inherited** (later
layers never re-litigate it), and the resolved :class:`ModelSelection` never
lets a rejected indicator back into the model. Runs on the real reference
dataset; no LLM calls. Runnable with pytest or plain python.
"""
from __future__ import annotations

from app.agents.dataset_cache import model_objects
from app.agents.ledger import (
    STATUS_INHERITED,
    STATUS_REJECTED,
    funnel,
    indicator_ledger,
    model_selection,
    signoff_key,
)
from app.domain.models import (
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
    # A quality drop has no `object` on the row, so it lands under OBJECT_ANY —
    # every real model object inherits it.
    sel = model_selection(st)
    assert all(key in sel.exclude_for(obj) for obj in model_objects(st))


def test_statistical_drop_rejects_and_is_excluded_from_the_selection() -> None:
    st = _state()
    key = _stat_drop(st, indicator_ledger(st)[0])

    row = next(r for r in indicator_ledger(st) if r.key == key)
    assert row.rejected_at == "statistical" and not row.adopted
    # `_stat_drop` doesn't pin an object, so the drop lands under OBJECT_ANY —
    # every real model object inherits it.
    sel = model_selection(st)
    assert all(key in sel.exclude_for(obj) for obj in model_objects(st))


def test_signoff_rejects_one_indicator_without_taking_its_siblings() -> None:
    st = _state()
    rows = indicator_ledger(st)
    target = next(r for r in rows if r.l3)
    sibling = next((r for r in rows
                    if r.l3 == target.l3 and r.key != target.key), None)

    # Nothing recorded → "not individually reviewed" must not reject.
    assert next(r for r in indicator_ledger(st) if r.key == target.key).adopted

    # A "yes" is not a rejection either.
    st.signoffs = {signoff_key(target.l4, target.indicator): "yes"}
    assert next(r for r in indicator_ledger(st) if r.key == target.key).adopted

    # An explicit "no" rejects exactly that indicator.
    st.signoffs = {signoff_key(target.l4, target.indicator): "no"}
    hit = next(r for r in indicator_ledger(st) if r.key == target.key)
    assert not hit.adopted and hit.rejected_at == "signoff"
    # `signoff_key` defaults to OBJECT_ANY — every real model object inherits it.
    sel = model_selection(st)
    assert all(target.key in sel.exclude_for(obj) for obj in model_objects(st))
    if sibling is not None:
        assert next(r for r in indicator_ledger(st) if r.key == sibling.key).adopted, \
            "denying one indicator must not deny its L3 siblings"


def test_legacy_l3_signoff_still_rejects_the_whole_factor() -> None:
    """Projects saved before sign-off became indicator-granular stored a bare L3."""
    st = _state()
    target = next(r for r in indicator_ledger(st) if r.l3)
    st.signoffs = {target.l3.strip().lower(): "no"}
    hit = next(r for r in indicator_ledger(st) if r.key == target.key)
    assert not hit.adopted and hit.rejected_at == "signoff"


def test_signoff_key_shape_is_explicit_not_inferred_from_a_pipe() -> None:
    """`signoff_key` writes the `i:` shape; a metric name that itself contains
    a '|' must still round-trip as the SAME indicator pair, not be misread as
    a factor — the whole reason the key carries an explicit prefix instead of
    being told apart from a bare-L3 key by the mere presence of '|'."""
    from app.agents.ledger import signoff_denied, signoff_key

    key = signoff_key("Digital", "Search | Brand")
    assert key.startswith("i:")

    st = _state()
    st.signoffs = {key: "no"}
    pairs, l3s = signoff_denied(st)
    assert ("digital", "search | brand") in pairs
    assert l3s == set()


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
    assert sel.include_for(keep.object) is not None
    # `include` is keyed (norm_l4, norm_metric) — the same key space as `exclude`
    # and the ledger, so a tick names one indicator, not every L4 sharing a label.
    assert keep.key in (sel.include_for(keep.object) or frozenset())
    assert drop.key not in (sel.include_for(drop.object) or frozenset())
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
    assert victim.metric.strip().lower() not in (sel.include_for(victim.object) or frozenset())
    assert all(key in sel.exclude_for(obj) for obj in model_objects(st))


def test_funnel_layers_account_for_every_indicator() -> None:
    """`funnel(st)` resolves per model object and returns
    ``{"combined": [...], "byObject": {object: [...]}}`` — `combined` mirrors
    the pre-per-object shape (one funnel over every row, any object), so the
    "every layer accounted for" invariant still holds there. `byObject` is
    checked too: each channel's own funnel must independently account for
    every indicator it carries."""
    st = _state()
    _quality_drop(st, indicator_ledger(st)[0])

    funnel_dict = funnel(st)
    assert set(funnel_dict) == {"combined", "byObject"}

    objects = model_objects(st)
    f = funnel_dict["combined"]
    assert [x["layer"] for x in f] == [
        "mapping", "quality", "signoff", "statistical", "selection", "range"]
    # Each layer's survivors feed the next layer's intake — no indicator vanishes.
    for prev, nxt in zip(f, f[1:]):
        assert prev["survivors"] == nxt["intake"]
    quality = next(x for x in f if x["layer"] == "quality")
    # `_quality_drop` records the drop under OBJECT_ANY (no object pinned), so
    # every real model object inherits it — `combined` concatenates every
    # object's own ledger rows, so one globally-dropped indicator shows up as
    # one rejection PER object, not once.
    assert quality["rejected"] == len(objects) and len(quality["dropped"]) == len(objects)
    assert quality["dropped"][0]["reason"]

    # Every model object's own funnel is internally consistent too — the same
    # layer-chaining invariant, resolved independently per channel — and each
    # channel's own quality layer sees the globally-dropped indicator exactly
    # once (not multiplied by every other channel).
    by_object = funnel_dict["byObject"]
    assert set(by_object) == set(objects)
    for obj_layers in by_object.values():
        assert [x["layer"] for x in obj_layers] == [
            "mapping", "quality", "signoff", "statistical", "selection", "range"]
        for prev, nxt in zip(obj_layers, obj_layers[1:]):
            assert prev["survivors"] == nxt["intake"]
        obj_quality = next(x for x in obj_layers if x["layer"] == "quality")
        assert obj_quality["rejected"] == 1 and len(obj_quality["dropped"]) == 1


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("\nAll ledger tests passed.")
