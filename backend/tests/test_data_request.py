"""Unit tests for the BU-derived data-request manifest + coverage matching."""
from __future__ import annotations

from app.agents.data_request import _best_sheet, _match_score, _norm, _score_slot
from app.domain.models import DataRequestSlot


def test_norm_strips_punctuation_keeps_cjk() -> None:
    assert _norm("POSM和陈列物料（POSM&Rack)") == "posm和陈列物料posmrack"
    assert _norm("OTV/OTT") == "otvott"
    assert _norm("Digital Display") == "digitaldisplay"


def test_match_score_exact_beats_substring() -> None:
    # "tv" is a substring of "otvott" but must not outrank the exact OTV_OTT sheet.
    assert _match_score("otvott", "otvott") == 4
    assert _match_score("tv", "otvott") == 1
    assert _match_score("digitaldisplay", "otvott") == 0


def test_best_sheet_picks_exact_not_substring() -> None:
    sheets = {"tv": ["GRP", "花费"], "otvott": ["曝光量", "花费"], "ooh": ["曝光量"]}
    # OTV/OTT must resolve to the otvott sheet, not the tv sheet.
    assert _best_sheet("otvott", sheets) == ["曝光量", "花费"]
    assert _best_sheet("tv", sheets) == ["GRP", "花费"]


def test_best_sheet_handles_truncated_title() -> None:
    # Excel truncates titles to 31 chars → sheet is a prefix of the L4 name.
    sheets = {"消费者促销旺点促销afhafh路演afh赛事sa": ["执行门店数"]}
    cols = _best_sheet(_norm("消费者促销-旺点促销(AFH)，AFH路演，AFH赛事,Sample试饮"), sheets)
    assert cols == ["执行门店数"]


def test_score_slot_full_coverage() -> None:
    slot = DataRequestSlot(l3="品牌传播")
    l4s = {"Digital Display": ["曝光量", "花费"], "OTV/OTT": ["曝光量", "花费"]}
    headers = {
        "Digital Display": ["Time (Month)", "Channel", "曝光量", "花费"],
        "OTV_OTT": ["Time (Month)", "Channel", "曝光量", "花费"],
    }
    _score_slot(slot, l4s, headers)
    assert slot.status == "validated"
    assert slot.covered_indicators == 4 and not slot.missing_indicators


def test_score_slot_detects_missing_indicator() -> None:
    slot = DataRequestSlot(l3="冰柜")
    l4s = {"冰柜": ["已投放冰柜个数", "花费"]}
    headers = {"冰柜": ["Time (Month)", "Channel", "已投放冰柜个数"]}  # 花费 missing
    _score_slot(slot, l4s, headers)
    assert slot.status == "incomplete"
    assert slot.covered_indicators == 1
    assert slot.missing_indicators == ["冰柜·花费"]


def test_score_slot_detects_missing_l4_sheet() -> None:
    slot = DataRequestSlot(l3="店内促销")
    l4s = {"试饮": ["执行门店数"], "礼赠": ["发放个数"]}
    headers = {"试饮": ["Time (Month)", "执行门店数"]}  # 礼赠 sheet absent
    _score_slot(slot, l4s, headers)
    assert slot.status == "incomplete"
    assert slot.missing_l4s == ["礼赠"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all data_request tests passed")
