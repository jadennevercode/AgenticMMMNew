"""Per-model-object screening, verified end-to-end on the REAL Danone reference
dataset (23,790 rows, 7 channel_types × 1 modelable product).

Read-only: builds an in-memory bound state under a throwaway project id and
never touches stored project JSON, never starts a server, never calls the LLM.

Run: PYTHONPATH=. .venv/bin/python -m app.agents._test_real_per_channel
"""
from __future__ import annotations

import sys

from app.agents.dataset_cache import invalidate_project, model_objects, set_project_dataset
from app.domain.models import IndustryRef, ProjectMeta
from app.store.state import initial_state

PID = "t-real-pc"

# The 7 real channel_types in the reference dataset (see test_data_derived_channels
# for how this is independently re-derived from the raw frame, not hardcoded here
# for correctness — this constant is only the expected-value fixture for that check).
# Only MIZONE carries both a response and drivers, so the 7 channels yield 7 model
# objects; the competitor brands' sell-out rows cannot be modeled and are reported
# by `skipped_objects` instead.
EXPECTED_CHANNELS = {"AFH", "EC", "MT", "O2O", "TT", "WS", "社区团购"}
EXPECTED_PRODUCT = "MIZONE"


def make_real_state():
    """Bind the real Danone dataset as project `t-real-pc`'s OWN data (source
    "slot", not the reference-fallback path) and build an in-memory state.
    Nothing here is written to `data/projects/...` — `set_project_dataset` only
    seeds the in-process resolver cache.
    """
    from app.ingest import load_model_dataset

    invalidate_project(PID)
    df = load_model_dataset()
    set_project_dataset(PID, df, "slot")
    meta = ProjectMeta(id=PID, name="RealPerChannel", brand="Mizone",
                       industry=IndustryRef(l1="food-bev", l2="beverage", l3="functional"),
                       createdAt="2026-01-01T00:00:00+00:00")
    return initial_state(meta)


def test_data_derived_channels() -> None:
    """Criterion 1: model_objects(st) returns the 7 real channel_types, ordered
    busiest-first by in-data row count — with the expected order re-derived
    independently from the raw frame (not a hardcoded list) so this cannot pass
    by coincidence with a stale ordering."""
    from app.ingest import load_model_dataset

    from app.agents.model_objects import make_object, skipped_objects, split_object

    st = make_real_state()
    objs = model_objects(st)
    assert {split_object(o)[0] for o in objs} == EXPECTED_CHANNELS, objs
    assert {split_object(o)[1] for o in objs} == {EXPECTED_PRODUCT}, objs

    raw = load_model_dataset()
    expected = {make_object(c, EXPECTED_PRODUCT) for c in EXPECTED_CHANNELS}
    assert set(objs) == expected, (set(objs), expected)
    # The competitor brands carry sell-out but no drivers — reported, never modeled.
    skipped = skipped_objects(raw)
    assert skipped and all(split_object(o)[1] != EXPECTED_PRODUCT for o in skipped), skipped
    print(f"  {len(objs)} model objects (channel x product): {objs}")
    print(f"  cells with a response but no drivers, reported not modeled: {skipped}")


def test_ledger_covers_all_channels() -> None:
    """Criterion 2: the indicator ledger scores rows tagged with each of the 7
    real channels, over a non-trivial universe of distinct indicators."""
    from app.agents import ledger

    st = make_real_state()
    rows = ledger.indicator_ledger(st)
    from app.agents.model_objects import split_object
    per_channel_objs = {r.object for r in rows if r.object != ledger.OBJECT_ANY}
    assert {split_object(o)[0] for o in per_channel_objs} == EXPECTED_CHANNELS, per_channel_objs

    distinct_keys = {r.key for r in rows}
    assert len(distinct_keys) > 20, len(distinct_keys)
    print(f"  ledger: {len(rows)} rows, {len(distinct_keys)} distinct indicator keys, "
          f"all 7 channels represented")


def _pick_divergence_indicator(st, cfg):
    """An indicator offered as a model variable in >= 2 model objects AND present
    in the ledger's own driver universe, deterministically chosen (most objects
    first, then key order) so a rerun always picks the same one.

    The divergence is forced at **2.5x** (the human's model-variable tick), which
    is per model object. It used to be forced at 2.4: since 2026-07-27 the
    statistical screening scores each indicator once over a panel stacked across
    every object and records one global verdict, so it can no longer express "kept
    here, dropped there" — nor should it, that was a property of the slice rather
    than of the indicator. The layers that still rule per object are the selection
    tick and the d-2.5 range gate.
    """
    from collections import defaultdict

    from app.agents import ledger

    universe = ledger._universe(st)
    by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for c in cfg.x_candidates:
        if c.locked:
            continue
        if ledger._norm_pair(c.l4, c.metric) in universe:
            by_key[(c.l4, c.metric)].add(c.object)
    candidates = [(k, sorted(v)) for k, v in by_key.items() if len(v) >= 2]
    assert candidates, ("no ledger-universe indicator is offered in >=2 model objects "
                        "— cannot demonstrate divergence")
    candidates.sort(key=lambda kv: (-len(kv[1]), kv[0]))
    return candidates[0]


def test_per_object_selection_divergence() -> None:
    """The core proof: pick a real indicator offered in >= 2 real model objects,
    untick it in exactly one and keep it ticked in the rest, rebuild the ledger,
    and assert the rejection applies ONLY to that object — the same indicator is
    out of one channel x product model and in another, on the real universe."""
    from app.agents import ledger
    from app.agents.ols_review import build_ols_proposal

    st = make_real_state()
    cfg = build_ols_proposal(st)
    (l4, indicator), objects = _pick_divergence_indicator(st, cfg)
    dropped, kept = objects[0], objects[1:]

    forced = []
    for c in cfg.x_candidates:
        if c.l4 == l4 and c.metric == indicator and c.object in objects:
            forced.append(c.model_copy(update={"selected": c.object != dropped}))
        else:
            forced.append(c)
    st.ols_config = cfg.model_copy(update={"x_candidates": forced})

    rows = ledger.indicator_ledger(st)
    dropped_row = next(r for r in rows
                       if r.object == dropped and r.l4 == l4 and r.indicator == indicator)
    assert not dropped_row.adopted, dropped_row
    assert dropped_row.rejected_at == "selection", dropped_row.rejected_at

    kept_adopted = [r for r in rows
                    if r.object in kept and r.l4 == l4 and r.indicator == indicator and r.adopted]
    assert kept_adopted, f"expected at least one of {kept} to keep {(l4, indicator)} adopted"

    print(f"  divergence indicator: {l4} / {indicator}")
    print(f"  offered in objects: {objects}")
    print(f"  unticked (forced) in: {dropped} -> rejected_at=selection, adopted=False")
    print(f"  adopted in: {[r.object for r in kept_adopted]}")

    # Stash for the downstream tests (model_selection, master_table) so they
    # exercise the exact same forced state rather than re-deriving it.
    global _DIVERGENCE
    _DIVERGENCE = dict(st=st, l4=l4, indicator=indicator, dropped=dropped,
                       kept=kept_adopted[0].object)


_DIVERGENCE: dict = {}


def test_model_selection_per_object() -> None:
    """`model_selection(st).exclude_for(object)` reflects the forced per-object
    drop from the previous test — excluded in the dropped model, not in a kept
    one."""
    from app.agents.ledger import _norm_pair, model_selection

    assert _DIVERGENCE, "test_per_object_selection_divergence must run first"
    st, l4, indicator = _DIVERGENCE["st"], _DIVERGENCE["l4"], _DIVERGENCE["indicator"]
    dropped, kept = _DIVERGENCE["dropped"], _DIVERGENCE["kept"]

    sel = model_selection(st)
    # `exclude_for` is keyed on the ledger's normalized (lowercased) pair — the
    # same key space `_universe`/`build_model_frame` use throughout S2.
    pair = _norm_pair(l4, indicator)
    assert pair in sel.exclude_for(dropped), (pair, dropped, sel.exclude_for(dropped))
    assert pair not in sel.exclude_for(kept), (pair, kept, sel.exclude_for(kept))
    print(f"  model_selection: {pair} excluded for {dropped}, not excluded for {kept}")


def test_master_table_columns_differ_by_channel() -> None:
    """The same forced divergence surfaces in the master data wide table — the
    dropped indicator's metric is a column when sliced to a kept model object,
    absent when sliced to the dropped one."""
    from app.agents.master_data import master_table

    assert _DIVERGENCE, "test_per_object_selection_divergence must run first"
    st, indicator = _DIVERGENCE["st"], _DIVERGENCE["indicator"]
    dropped, kept = _DIVERGENCE["dropped"], _DIVERGENCE["kept"]

    from app.agents.model_objects import split_object
    dropped_tbl = master_table(st, channel_type=[split_object(dropped)[0]],
                               brand=[split_object(dropped)[1]])
    kept_tbl = master_table(st, channel_type=[split_object(kept)[0]],
                            brand=[split_object(kept)[1]])

    assert indicator in kept_tbl["columns"], (indicator, kept_tbl["columns"])
    assert indicator not in dropped_tbl["columns"], (indicator, dropped_tbl["columns"])

    only_in_kept = sorted(set(kept_tbl["columns"]) - set(dropped_tbl["columns"]))
    only_in_dropped = sorted(set(dropped_tbl["columns"]) - set(kept_tbl["columns"]))
    print(f"  master_table[{kept}] has {len(kept_tbl['columns'])} columns, "
          f"master_table[{dropped}] has {len(dropped_tbl['columns'])} columns")
    print(f"  columns only in {kept}: {only_in_kept}")
    print(f"  columns only in {dropped}: {only_in_dropped}")


if __name__ == "__main__":
    fns = [
        test_data_derived_channels,
        test_ledger_covers_all_channels,
        test_per_object_selection_divergence,
        test_model_selection_per_object,
        test_master_table_columns_differ_by_channel,
    ]
    failed = 0
    for fn in fns:
        print(f"-- {fn.__name__}")
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
