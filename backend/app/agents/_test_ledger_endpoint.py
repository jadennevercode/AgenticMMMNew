"""GET /indicator-ledger exposes per-object rows additively. Run:
PYTHONPATH=. .venv/bin/python -m app.agents._test_ledger_endpoint"""
from __future__ import annotations
import sys
from app.agents._test_per_channel import make_two_channel_state
from app.domain.models import StatScorecard, StatScoreRow
from app.main import get_indicator_ledger
from app.store.state import get_store
import asyncio

def test_rows_by_object_present():
    st = make_two_channel_state("t-ledger-ep")
    # Built directly (as `_test_per_channel.test_ledger_is_per_object` does)
    # rather than via `build_stat_scorecard()`: the fixture's TT 渠道库存 is a
    # constant series, which the real scorer excludes from scoring entirely
    # rather than scoring it "drop" — so a natural scorecard never carries the
    # TT disposition this test needs to force.
    st.stat_scorecard = StatScorecard(rows=[
        StatScoreRow(id="s-mt", object="MT", l4="渠道库存", indicator="渠道库存",
                     disposition="include"),
        StatScoreRow(id="s-tt", object="TT", l4="渠道库存", indicator="渠道库存",
                     disposition="drop"),
    ])
    get_store()._states["t-ledger-ep"] = st  # seed for the handler; real API confirmed: ProjectStore.get() checks _states dict first, so pre-seeding it bypasses disk load
    out = asyncio.run(get_indicator_ledger("t-ledger-ep"))
    assert "rowsByObject" in out, out.keys()
    by = out["rowsByObject"]
    assert set(by) >= {"MT", "TT"}, list(by)
    tt = [r for r in by["TT"] if r["indicator"] == "渠道库存"]
    mt = [r for r in by["MT"] if r["indicator"] == "渠道库存"]
    assert tt and not tt[0]["adopted"] and tt[0]["rejectedAt"] == "statistical", tt
    assert mt and mt[0]["adopted"], mt
    # the collapsed `rows` view is unchanged (one row per key)
    keys = [(r["l4"], r["indicator"]) for r in out["rows"]]
    assert len(keys) == len(set(keys)), "collapsed rows must stay deduped"
    print("  rowsByObject present; collapsed rows unchanged")

if __name__ == "__main__":
    fns = [v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed=0
    for fn in fns:
        try: fn()
        except Exception as e: failed+=1; print(f"  FAIL {fn.__name__}: {e}")
    print(f"{len(fns)-failed}/{len(fns)} passed"); sys.exit(1 if failed else 0)
