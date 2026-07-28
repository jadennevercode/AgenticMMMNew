"""Byte-parity guard for the pivot classification predicates + the vocab resolver.
Run: PYTHONPATH=. .venv/bin/python -m app.mmm._test_vocab_parity

The predicates were refactored to read a ``Vocab`` (default ``DEFAULT_VOCAB``).
These frozen expectations were captured from the pre-refactor code — if any
diverges, the refactor changed a number and must be reverted, not updated.
"""
from __future__ import annotations

import sys

import pandas as pd

from app.mmm.pivot import (
    _is_spend,
    _is_y_row,
    is_driver_row,
    is_money_metric,
    is_volume_metric_type,
)


def _df() -> pd.DataFrame:
    return pd.DataFrame([
        {"l1": "KPI", "metric_type": "Y", "metric": "销量箱数"},
        {"l1": "MARKETING FACTOR", "metric_type": "spending", "metric": "广告花费"},
        {"l1": "COMMERCIAL FACTOR", "metric_type": "x", "metric": "渠道库存"},
        {"l1": "", "metric_type": "kpi", "metric": "offtake volume"},
        {"l1": "", "metric_type": "value", "metric": "GMV total"},
        {"l1": "", "metric_type": "箱数", "metric": "sales gmv"},
        {"l1": "other", "metric_type": "other", "metric": "温度"},
    ])


def test_is_y_row_parity() -> None:
    assert [bool(x) for x in _is_y_row(_df())] == [True, False, False, True, True, True, False]
    print("  _is_y_row parity")


def test_is_driver_row_parity() -> None:
    assert [bool(x) for x in is_driver_row(_df())] == [False, True, True, False, False, False, False]
    print("  is_driver_row parity")


def test_volume_parity() -> None:
    got = [is_volume_metric_type(t) for t in ["箱数", "volume", "unit", "value", "rmb", "other"]]
    assert got == [True, True, True, False, False, False], got
    print("  is_volume_metric_type parity")


def test_money_parity() -> None:
    got = [is_money_metric(t) for t in ["rmb", "value", "gmv", "金额", "元", "箱数", "volume", "other"]]
    assert got == [True, True, True, True, True, False, False, False], got
    print("  is_money_metric parity")


def test_spend_parity() -> None:
    # ("rmb", "y") was frozen as True by the vocab refactor and is now False — a
    # deliberate correction, not refactor drift: a currency unit is not evidence of
    # outlay, and on the reference data the rows it uniquely caught were Value,
    # GMV, sales value, RSP, Smartpath sales and Average Price. Every real spend
    # row still matches on its name ("Spending" / 花费 / 投放 / 费用).
    got = [_is_spend(mt, m) for mt, m in
           [("spending", "x"), ("rmb", "y"), ("rmb", "广告花费"),
            ("x", "广告投放"), ("x", "费用z"), ("x", "other"), ("other", "other")]]
    assert got == [True, False, True, True, True, False, False], got
    print("  _is_spend parity")


def test_default_vocab_matches_former_constants() -> None:
    from app.agents.vocabulary import DEFAULT_VOCAB
    from app.mmm import pivot
    assert DEFAULT_VOCAB.y_metric_types == frozenset(pivot._Y_METRIC_TYPES)
    assert DEFAULT_VOCAB.y_keywords == frozenset(pivot._Y_KEYWORDS)
    assert DEFAULT_VOCAB.driver_tags == frozenset(pivot._DRIVER_TAGS)
    assert DEFAULT_VOCAB.spend_keywords == frozenset(pivot._SPEND_KEYWORDS)
    assert DEFAULT_VOCAB.driver_l1_labels == frozenset({"MARKETING FACTOR", "COMMERCIAL FACTOR"})
    assert DEFAULT_VOCAB.y_l1_labels == frozenset({"KPI"})
    print("  DEFAULT_VOCAB == former pivot constants")


def test_vocab_override_reclassifies() -> None:
    # A vocab whose driver_l1_labels adds "MY FACTOR" turns an l1="MY FACTOR" row
    # into a driver — proving the override path actually changes classification.
    from dataclasses import replace
    from app.agents.vocabulary import DEFAULT_VOCAB
    from app.mmm.pivot import is_driver_row
    df = pd.DataFrame([{"l1": "MY FACTOR", "metric_type": "z", "metric": "x"}])
    assert not bool(is_driver_row(df).iloc[0]), "default must NOT treat MY FACTOR as a driver"
    ov = replace(DEFAULT_VOCAB, driver_l1_labels=DEFAULT_VOCAB.driver_l1_labels | {"MY FACTOR"})
    assert bool(is_driver_row(df, vocab=ov).iloc[0]), "override must treat MY FACTOR as a driver"
    print("  vocab override reclassifies")


def test_vocab_rules_model_merges() -> None:
    # A VocabRules payload (as stored on a Knowledge `rules` template) merges into
    # a Vocab, overriding only the banks it names.
    from app.agents.vocabulary import DEFAULT_VOCAB, _merge
    from app.domain.models import VocabRules
    vr = VocabRules(driverL1Labels=["marketing factor", "my factor"], yKeywords=["salesx"])
    merged = _merge(DEFAULT_VOCAB, vr)
    assert merged.driver_l1_labels == frozenset({"MARKETING FACTOR", "MY FACTOR"}), merged.driver_l1_labels
    assert merged.y_keywords == frozenset({"salesx"}), merged.y_keywords
    # unset banks fall back to the default
    assert merged.spend_keywords == DEFAULT_VOCAB.spend_keywords
    print("  VocabRules model merges into Vocab")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
