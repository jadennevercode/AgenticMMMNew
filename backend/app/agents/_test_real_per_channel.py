"""Phase 2 — per-Channel-Type screening, verified end-to-end on the REAL
Danone reference dataset (23,790 rows, 7 channel_types).

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
EXPECTED_CHANNELS = {"AFH", "EC", "MT", "O2O", "TT", "WS", "社区团购"}


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

    st = make_real_state()
    objs = model_objects(st)
    assert set(objs) == EXPECTED_CHANNELS, set(objs)

    raw = load_model_dataset()
    ct = raw["channel_type"].astype("string").str.strip()
    expected_order = [str(k) for k in ct[ct.ne("") & ct.ne("nan")].value_counts().index]
    assert objs == expected_order, (objs, expected_order)
    print(f"  7 channels, busiest-first: {objs}")


def test_ledger_covers_all_channels() -> None:
    """Criterion 2: the indicator ledger scores rows tagged with each of the 7
    real channels, over a non-trivial universe of distinct indicators."""
    from app.agents import ledger

    st = make_real_state()
    rows = ledger.indicator_ledger(st)
    per_channel_objs = {r.object for r in rows if r.object != ledger.OBJECT_ANY}
    assert per_channel_objs == EXPECTED_CHANNELS, per_channel_objs

    distinct_keys = {r.key for r in rows}
    assert len(distinct_keys) > 20, len(distinct_keys)
    print(f"  ledger: {len(rows)} rows, {len(distinct_keys)} distinct indicator keys, "
          f"all 7 channels represented")


def _pick_divergence_indicator(st, card):
    """An indicator scored (present) in >= 2 channels on the real scorecard AND
    present in the ledger's own driver universe, deterministically chosen (most
    channels first, then key order) so a rerun always picks the same one.

    The statistical scorecard (2.4) scores every indicator that survived
    upstream layers, but the ledger's universe (`driver_candidates_by_l4`, 2.1's
    key space) is narrower — e.g. price-type factors such as RSP are scored by
    2.4 but never enter the driver universe, so they can never appear in
    `indicator_ledger`. Restricting to keys the ledger actually carries is what
    makes the downstream ledger/model_selection/master_table assertions land on
    a real, non-empty row instead of silently matching nothing.
    """
    from collections import defaultdict

    from app.agents import ledger

    universe = ledger._universe(st)
    by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in card.rows:
        if ledger._norm_pair(r.l4, r.indicator) in universe:
            by_key[(r.l4, r.indicator)].add(r.object)
    candidates = [(k, sorted(v)) for k, v in by_key.items() if len(v) >= 2]
    assert candidates, ("no ledger-universe indicator is scored in >=2 real channels "
                        "— cannot demonstrate divergence")
    candidates.sort(key=lambda kv: (-len(kv[1]), kv[0]))
    return candidates[0]


def test_per_channel_statistical_divergence() -> None:
    """Criterion 3 (the core proof): pick a real indicator scored in >= 2 real
    channels, force its disposition to "drop" in exactly one channel and
    "include" in the rest, rebuild the ledger, and assert the drop applies
    ONLY to the forced channel — the same indicator is rejected in one channel
    and adopted in another, on the real 7-channel universe."""
    from app.agents import ledger
    from app.agents.stat_scoring import build_stat_scorecard

    st = make_real_state()
    card = build_stat_scorecard(st)
    (l4, indicator), channels = _pick_divergence_indicator(st, card)
    dropped, kept = channels[0], channels[1:]

    forced_rows = []
    for r in card.rows:
        if r.l4 == l4 and r.indicator == indicator and r.object in channels:
            disposition = "drop" if r.object == dropped else "include"
            forced_rows.append(r.model_copy(update={"disposition": disposition}))
        else:
            forced_rows.append(r)
    st.stat_scorecard = card.model_copy(update={"rows": forced_rows})

    rows = ledger.indicator_ledger(st)
    dropped_row = next(r for r in rows if r.object == dropped and r.l4 == l4 and r.indicator == indicator)
    assert not dropped_row.adopted, dropped_row
    assert dropped_row.rejected_at == "statistical", dropped_row.rejected_at

    kept_adopted = [r for r in rows
                    if r.object in kept and r.l4 == l4 and r.indicator == indicator and r.adopted]
    assert kept_adopted, f"expected at least one of {kept} to keep {(l4, indicator)} adopted"

    print(f"  divergence indicator: {l4} / {indicator}")
    print(f"  scored in channels: {channels}")
    print(f"  dropped (forced) in: {dropped} -> rejected_at=statistical, adopted=False")
    print(f"  adopted in: {[r.object for r in kept_adopted]}")

    # Stash for the downstream tests (model_selection, master_table) so they
    # exercise the exact same forced state rather than re-deriving it.
    global _DIVERGENCE
    _DIVERGENCE = dict(st=st, l4=l4, indicator=indicator, dropped=dropped,
                       kept=kept_adopted[0].object)


_DIVERGENCE: dict = {}


def test_model_selection_per_object() -> None:
    """Criterion 4: `model_selection(st).exclude_for(channel)` reflects the
    forced per-channel drop from the previous test — excluded in the dropped
    channel, not in a kept one."""
    from app.agents.ledger import _norm_pair, model_selection

    assert _DIVERGENCE, "test_per_channel_statistical_divergence must run first"
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
    """Criterion 6: the same forced divergence surfaces in the master data
    wide table — the dropped indicator's metric is a column when sliced to a
    kept channel, absent when sliced to the dropped channel."""
    from app.agents.master_data import master_table

    assert _DIVERGENCE, "test_per_channel_statistical_divergence must run first"
    st, indicator = _DIVERGENCE["st"], _DIVERGENCE["indicator"]
    dropped, kept = _DIVERGENCE["dropped"], _DIVERGENCE["kept"]

    dropped_tbl = master_table(st, channel_type=[dropped])
    kept_tbl = master_table(st, channel_type=[kept])

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
        test_per_channel_statistical_divergence,
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
