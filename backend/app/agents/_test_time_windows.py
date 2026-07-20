"""FND-002 checks: month math + yoy/pop derivation + equal-length.

Run: PYTHONPATH=. .venv/bin/python -m app.agents._test_time_windows
"""
from app.agents.time_windows import (
    derive_comparison, int_to_ym, is_equal_length, length_months,
    normalize_window, shift_months, ym_to_int,
)
from app.domain.models import TimeWindow


def test_month_math():
    assert ym_to_int("2025-01") == 202501
    assert ym_to_int("2025/1") == 202501
    assert ym_to_int("202510") == 202510
    assert ym_to_int("garbage") is None
    assert ym_to_int("2025-13") is None
    assert int_to_ym(202501) == "2025-01"
    assert shift_months(202501, -12) == 202401
    assert shift_months(202501, -1) == 202412   # cross year boundary
    assert shift_months(202412, 1) == 202501
    assert length_months(202501, 202510) == 10
    assert length_months(202501, 202412) == 0   # end < start


def test_yoy():
    w = TimeWindow(id="w", name="Jan-Oct YoY", periodType="custom",
                   currentStart="2025-01", currentEnd="2025-10", comparisonType="yoy")
    cs, ce = derive_comparison(w)
    assert (cs, ce) == ("2024-01", "2024-10")     # SPEC acceptance: base auto = prior year
    assert is_equal_length(normalize_window(w))


def test_pop():
    w = TimeWindow(id="w", name="H1 vs prev", currentStart="2026-01",
                   currentEnd="2026-06", comparisonType="pop")
    cs, ce = derive_comparison(w)
    assert (cs, ce) == ("2025-07", "2025-12")     # immediately preceding 6 months
    assert is_equal_length(normalize_window(w))


def test_unequal_flagged():
    # A hand-set custom comparison of the wrong length must fail the equal-length gate.
    w = TimeWindow(id="w", name="bad", currentStart="2025-01", currentEnd="2025-10",
                   comparisonType="custom", comparisonStart="2024-01", comparisonEnd="2024-06")
    assert not is_equal_length(w)


def test_none_trivially_equal():
    w = TimeWindow(id="w", name="single", currentStart="2025-01", currentEnd="2025-10")
    assert is_equal_length(w)
    assert derive_comparison(w) == ("", "")


if __name__ == "__main__":
    test_month_math()
    test_yoy()
    test_pop()
    test_unequal_flagged()
    test_none_trivially_equal()
    print("FND-002 time_windows: ALL PASS")
