"""DATA-005 checks: period grains + window-scoped comparison.

Run: PYTHONPATH=. .venv/bin/python -m app.dataeng._test_validation_period
"""
import types

import pandas as pd

from app.agents.time_windows import normalize_window, resolve_window
from app.dataeng import validation_query as vq
from app.domain.models import TimeWindow


def _fixture():
    rows = []
    for y in (2024, 2025):
        for mo in range(1, 13):
            ym = y * 100 + mo
            rows.append(dict(l1="KPI", l2="x", l3="投放", l4="", l5="", l6="", l7="", l8="",
                             metric="本品销量", metric_type="Y", value=100 + mo,
                             year=y, month=ym, source="up", brand="脉动",
                             channel_type="MT", province_group="East"))
            rows.append(dict(l1="MARKETING", l2="x", l3="投放", l4="线上", l5="", l6="", l7="", l8="",
                             metric="投放花费", metric_type="spending", value=10 * mo,
                             year=y, month=ym, source="up", brand="脉动",
                             channel_type="MT", province_group="East"))
    df = pd.DataFrame(rows)
    vq.model_df = lambda st: df           # monkeypatch the data source
    return types.SimpleNamespace(time_windows=[])


def test_grains():
    st = _fixture()
    assert vq.validation_series(st, l3="投放", grain="month")["options"]["grains"] == \
        ["year", "half_year", "quarter", "month"]
    assert vq.validation_series(st, l3="投放", grain="quarter")["x"][:2] == ["2024 Q1", "2024 Q2"]
    assert vq.validation_series(st, l3="投放", grain="half_year")["x"] == \
        ["2024 H1", "2024 H2", "2025 H1", "2025 H2"]


def test_window_comparison_yoy():
    st = _fixture()
    w = normalize_window(TimeWindow(id="w1", name="2025 Jan-Oct YoY", periodType="custom",
                                    currentStart="2025-01", currentEnd="2025-10", comparisonType="yoy"))
    r = vq.validation_series(st, l3="投放", grain="month", window=w)
    c = r["comparison"]
    assert c["current"]["label"] == "2025-01 → 2025-10"
    assert c["comparison"]["label"] == "2024-01 → 2024-10"     # base auto-derived
    assert c["equalLength"] is True
    # view scoped to the current window's 10 months
    assert len(r["x"]) == 10 and r["x"][0] == "2025-01" and r["x"][-1] == "2025-10"
    kpi = next(row for row in c["rows"] if row["metric"] == "本品销量")
    assert kpi["current"] == 1055.0 and kpi["comparison"] == 1055.0 and kpi["deltaPct"] == 0.0


def test_no_window_no_comparison():
    st = _fixture()
    r = vq.validation_series(st, l3="投放", grain="year")
    assert r["comparison"] is None


def _fixture_with_rate():
    """KPI + a rate metric (NDWD, 60% in two geos every month)."""
    from app.domain.models import Indicator
    rows = []
    for y in (2024, 2025):
        for mo in range(1, 13):
            ym = y * 100 + mo
            rows.append(dict(l1="KPI", l2="x", l3="投放", l4="", l5="", l6="", l7="", l8="",
                             metric="本品销量", metric_type="Y", value=1000.0, year=y, month=ym,
                             source="up", brand="b", channel_type="MT", province_group="East"))
            for geo in ("East", "West"):
                rows.append(dict(l1="COMMERCIAL FACTOR", l2="x", l3="投放", l4="商超", l5="", l6="",
                                 l7="", l8="", metric="NDWD覆盖率", metric_type="X", value=60.0,
                                 year=y, month=ym, source="up", brand="b", channel_type="MT",
                                 province_group=geo))
    vq.model_df = lambda st: pd.DataFrame(rows)
    inds = [Indicator(id="i1", metric="NDWD覆盖率", metricType="X", semanticType="rate",
                      aggregation="average", unit="%", numberFormat="percent"),
            Indicator(id="i2", metric="本品销量", metricType="Y", semanticType="kpi_volume",
                      aggregation="sum", unit="", numberFormat="integer")]
    return types.SimpleNamespace(time_windows=[], indicators=inds)


def test_aggregation_and_metadata():
    """DATA-007: a rate averages across dims/periods (not sums). DATA-008: series and
    comparison rows carry unit/format/aggregation."""
    st = _fixture_with_rate()
    r = vq.validation_series(st, l3="投放", grain="year", indicators=["NDWD覆盖率"])
    ndwd = next(s for s in r["series"] if s["metric"] == "NDWD覆盖率")
    assert ndwd["data"] == [60.0, 60.0]           # averaged, NOT 2×12×60=1440 summed
    assert ndwd["aggregation"] == "average" and ndwd["unit"] == "%" and ndwd["numberFormat"] == "percent"
    yr = next(row for row in r["yearly"]["rows"] if row["metric"] == "NDWD覆盖率")
    assert yr["values"] == [60.0, 60.0] and yr["numberFormat"] == "percent"

    from app.agents.time_windows import normalize_window
    from app.domain.models import TimeWindow
    w = normalize_window(TimeWindow(id="w", name="2025 YoY", currentStart="2025-01",
                                    currentEnd="2025-12", comparisonType="yoy"))
    r2 = vq.validation_series(st, l3="投放", grain="month", indicators=["NDWD覆盖率"], window=w)
    crow = next(x for x in r2["comparison"]["rows"] if x["metric"] == "NDWD覆盖率")
    assert crow["current"] == 60.0 and crow["aggregation"] == "average" and crow["numberFormat"] == "percent"


def test_resolve_window():
    w = TimeWindow(id="tw-x", name="w", currentStart="2025-01", currentEnd="2025-06")
    st = types.SimpleNamespace(time_windows=[w])
    assert resolve_window(st, "tw-x") is w
    assert resolve_window(st, "missing") is None
    assert resolve_window(st, "") is None


if __name__ == "__main__":
    test_grains()
    test_window_comparison_yoy()
    test_no_window_no_comparison()
    test_aggregation_and_metadata()
    test_resolve_window()
    print("DATA-005/007/008 validation period + window + aggregation: ALL PASS")
