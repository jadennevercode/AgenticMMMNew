"""FND-002 · Time-window helpers (comparable-period math).

The single place month-window arithmetic lives: parsing 'YYYY-MM' bounds, counting
inclusive length, shifting by N months, and deriving a comparison window from a type
(yoy = same window one year earlier; pop = the immediately preceding equal-length
window). DATA-005 builds its period aggregation and Reporting reuse on top of this.

Bounds are inclusive 'YYYY-MM' strings; internally we use yyyymm ints (202501).
"""
from __future__ import annotations

import re
from typing import Optional

from app.domain.models import TimeWindow


def ym_to_int(s: str) -> Optional[int]:
    """'2025-01' / '2025/1' / '202501' → 202501; None if unparseable."""
    m = re.match(r"^\s*(\d{4})\D*(\d{1,2})", str(s or ""))
    if not m:
        digits = re.sub(r"\D", "", str(s or ""))
        if len(digits) == 6:
            return int(digits)
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    if not (1 <= mo <= 12):
        return None
    return y * 100 + mo


def int_to_ym(v: int) -> str:
    return f"{v // 100:04d}-{v % 100:02d}"


def shift_months(v: int, n: int) -> int:
    """Shift a yyyymm int by n months (n may be negative)."""
    total = (v // 100) * 12 + (v % 100 - 1) + n
    return (total // 12) * 100 + (total % 12) + 1


def length_months(start_i: int, end_i: int) -> int:
    """Inclusive month count between two yyyymm ints (0 if end < start)."""
    if end_i < start_i:
        return 0
    return (end_i // 100 - start_i // 100) * 12 + (end_i % 100 - start_i % 100) + 1


def derive_comparison(w: TimeWindow) -> tuple[str, str]:
    """Return (comparison_start, comparison_end) for the window's comparison_type.

    * yoy    → the same span shifted back one year (equal length, same season).
    * pop    → the immediately preceding span of equal length.
    * custom → whatever bounds the window already carries.
    * none   → empty.
    Falls back to the window's own comparison bounds when current bounds are unset.
    """
    cs, ce = ym_to_int(w.current_start), ym_to_int(w.current_end)
    if w.comparison_type == "none":
        return "", ""
    if cs is None or ce is None:
        return w.comparison_start, w.comparison_end
    if w.comparison_type == "yoy":
        return int_to_ym(shift_months(cs, -12)), int_to_ym(shift_months(ce, -12))
    if w.comparison_type == "pop":
        n = length_months(cs, ce)
        prev_end = shift_months(cs, -1)
        prev_start = shift_months(prev_end, -(n - 1))
        return int_to_ym(prev_start), int_to_ym(prev_end)
    return w.comparison_start, w.comparison_end


def normalize_window(w: TimeWindow) -> TimeWindow:
    """Fill in derived comparison bounds so a caller can save just the current
    window + comparison_type. Leaves current bounds untouched."""
    cstart, cend = derive_comparison(w)
    return w.model_copy(update={"comparison_start": cstart, "comparison_end": cend})


def resolve_window(st, time_window_id: str) -> Optional[TimeWindow]:
    """Look up a saved time window by id on a project state. Shared by Business
    Validation (DATA-005) and Reporting so both consume the same definition."""
    if not time_window_id:
        return None
    for w in getattr(st, "time_windows", []) or []:
        if w.id == time_window_id:
            return w
    return None


def is_equal_length(w: TimeWindow) -> bool:
    """True if current and comparison spans are the same inclusive length (>0).
    A window with no comparison is trivially 'equal' (nothing to mismatch)."""
    if w.comparison_type == "none":
        return True
    cs, ce = ym_to_int(w.current_start), ym_to_int(w.current_end)
    ps, pe = ym_to_int(w.comparison_start), ym_to_int(w.comparison_end)
    if None in (cs, ce, ps, pe):
        return False
    a, b = length_months(cs, ce), length_months(ps, pe)
    return a > 0 and a == b
