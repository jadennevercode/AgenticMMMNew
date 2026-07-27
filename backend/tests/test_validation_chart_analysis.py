"""2.3 per-chart AI analysis — cache key, digest invalidation, no-LLM fallback.

Run: PYTHONPATH=. .venv/bin/python tests/test_validation_chart_analysis.py
"""
from __future__ import annotations

from app.agents import validation_analysis as va


def test_batch_and_endpoint_agree_on_the_cache_key() -> None:
    """The pre-generated analyses must land under the key the card asks for.

    2.3 generates every chart's reading up front; the card then requests the same
    chart through `POST /validation/chart-analysis`. If the two hash a different
    dict the pre-generation is invisible and every card shows "Generate analysis"
    despite the work already being done — which is exactly what an unset level
    being `None` on one side and `""` on the other produced.
    """
    from app.main import ValidationSeriesQuery

    for kwargs in (
        {"l3": "Competition", "grain": "month", "indicators": ["Spending", "WD"]},
        {"l3": "Competition", "grain": "month"},
        {"l3": "Promo", "l4": "TV", "grain": "quarter", "indicators": [], "yoyMonth": 3},
    ):
        endpoint = ValidationSeriesQuery(**kwargs).model_dump(by_alias=True)
        batch = va.normalize_query(kwargs)
        assert va.analysis_key(endpoint) == va.analysis_key(batch), kwargs
    print("✓ batch and endpoint agree on the cache key")


def test_key_ignores_fields_that_do_not_change_the_chart() -> None:
    """`force` and other request-only fields must not fork the cache."""
    base = {"l3": "A", "grain": "month"}
    assert va.analysis_key(base) == va.analysis_key({**base, "force": True})
    assert va.analysis_key(base) == va.analysis_key({**base, "timeWindowId": "tw-1"})
    # A field that DOES change the chart must fork it.
    assert va.analysis_key(base) != va.analysis_key({**base, "yoyMonth": 3})
    assert va.analysis_key(base) != va.analysis_key({**base, "l4": "TV"})
    print("✓ the key forks on what changes the chart, and only on that")


def test_digest_tracks_the_plotted_numbers() -> None:
    """A cached reading of numbers that have since moved must be detectable."""
    res = {"x": ["2024-01", "2024-02"], "kpi": {"metric": "Y", "data": [1.0, 2.0]},
           "series": [{"metric": "spend", "data": [10.0, 20.0]}]}
    same = {**res, "grain": "month"}                      # a non-numeric field
    moved = {**res, "kpi": {"metric": "Y", "data": [1.0, 9.9]}}
    assert va.series_digest(res) == va.series_digest(same)
    assert va.series_digest(res) != va.series_digest(moved)
    print("✓ the series digest tracks the plotted numbers")


def test_facts_are_computed_not_asked_of_the_model() -> None:
    """Every number the prose may quote is derived here first."""
    res = {"grain": "month",
           "x": [f"2024-{m:02d}" for m in range(1, 13)],
           "kpi": {"metric": "Y", "data": [10, 12, 14, 13, 15, 18, 22, 20, 19, 17, 16, 30]},
           "series": [{"metric": "spend", "data": [1, 2, 3, None, 5, 6, 7, 8, 9, 10, 11, 12]}]}
    f = va.compute_facts(res)
    resp = f["response"]
    assert resp["peak"] == {"period": "2024-12", "value": 30.0}
    assert resp["trough"] == {"period": "2024-01", "value": 10.0}
    assert resp["largestMove"]["to"] == "2024-12" and resp["largestMove"]["delta"] == 14.0
    # Jul→Nov (22, 20, 19, 17, 16) is the longest monotone stretch, longer than the
    # opening rise — the fact is the series', not the reader's expectation of it.
    assert resp["longestRun"] == {"direction": "falling", "from": "2024-07",
                                  "to": "2024-11", "periods": 5}
    d = f["drivers"][0]
    # The gap is reported, never interpolated over or read as a zero.
    assert d["missingPeriods"] == 1 and d["observedPeriods"] == 11
    assert d["trough"]["value"] == 1.0
    assert d["correlationWithResponse"] is not None
    print("✓ facts are computed before the model is asked anything")


def test_fallback_reads_out_the_facts_when_no_llm() -> None:
    """With no model configured a chart still carries an honest, labelled readout."""
    import asyncio

    res = {"grain": "month", "x": ["2024-01", "2024-02", "2024-03"],
           "kpi": {"metric": "Y", "data": [10.0, 20.0, 15.0]},
           "series": [{"metric": "spend", "data": [1.0, 2.0, 3.0]}]}
    real = va.get_llm

    def _no_llm():
        raise va.LLMError("not configured")

    va.get_llm = _no_llm
    try:
        a = asyncio.run(va.analyze_chart(res, {"l3": "A", "grain": "month"}, now="t"))
    finally:
        va.get_llm = real
    assert a.fallback is True
    assert a.headline and "no language model" in a.headline.lower()
    assert a.trends, "the readout must still say something concrete"
    assert a.series_digest == va.series_digest(res)
    print("✓ no-LLM fallback is an honest computed readout")


if __name__ == "__main__":
    test_batch_and_endpoint_agree_on_the_cache_key()
    test_key_ignores_fields_that_do_not_change_the_chart()
    test_digest_tracks_the_plotted_numbers()
    test_facts_are_computed_not_asked_of_the_model()
    test_fallback_reads_out_the_facts_when_no_llm()
    print("\nall validation chart-analysis tests passed")
