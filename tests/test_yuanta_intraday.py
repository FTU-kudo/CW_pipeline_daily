"""Kiểm thử phân tích trong phiên, dải trần–sàn và phép kiểm tra liên tục bằng RefP.

Trọng tâm là **ngữ nghĩa** của payload, vì đó là thứ dễ làm sai nhất:

- ``RefP`` = giá đóng cửa phiên trước → mốc so sánh và chốt kiểm tra liên tục;
- ``CeilingP``/``FloorP`` đọc thẳng từ nguồn, **không** suy ra ±7%;
- ``LastMVol`` là khối lượng của riêng lệnh khớp cuối;
- ``HighestP``/``LowestP``/``OpenP``/``LastMP`` là biên độ và giá đóng cửa của phiên.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from cwintel import yuanta_history as hist
from cwintel.yuanta_board import clean_board
from cwintel.yuanta_intraday import (
    CW_TICK_VND,
    intraday_moves,
    last_trade_profile,
    price_band_profile,
    ref_continuity,
)


def _row(**over):
    """Một dòng payload tối thiểu, đúng tên trường như API Yuanta trả về."""
    base = {
        "StockCode": "CACB2515", "Exchange": "HSX", "SymbolType": "EW",
        "RefP": 170, "CeilingP": 980, "FloorP": 10,
        "HighestP": 160, "LowestP": 150, "OpenP": 160, "AvgP": 156.78,
        "LastMP": 150, "LastMVol": 5000, "DeemP": None, "DeemVol": None,
        "TotalVol": 17700, "TotalVal": 2775000, "B1P": 145, "S1P": 155,
        "FTBuyVol": 0, "FTSellVol": 0, "FRoom": 0,
    }
    base.update(over)
    return base


def _frame(rows, at="2026-11-13T10:30:00+00:00"):
    return clean_board(rows, fetched_at=datetime.fromisoformat(at))


# ──────────────────────────────────────────────────────────────────
# BIẾN ĐỘNG TRONG PHIÊN
# ──────────────────────────────────────────────────────────────────
def test_intraday_range_uses_ref_as_denominator_and_marks_close_location():
    frame = _frame([_row()])
    out = intraday_moves(frame)
    row = out["rows"][0]
    # (160 − 150) / 170 = 5.88% — mẫu số là RefP (giá đóng cửa hôm qua), không phải OpenP.
    assert row["rangePct"] == pytest.approx(5.88, abs=0.01)
    assert row["rangeVND"] == pytest.approx(10)
    assert row["rangeTicks"] == pytest.approx(10 / CW_TICK_VND, abs=0.1)
    # Close 150 nằm ở đáy khoảng [150, 160] → 0.0
    assert row["closeLocation"] == pytest.approx(0.0)


def test_intraday_skips_untraded_and_flat_sessions_are_not_division_errors():
    frame = _frame([
        _row(StockCode="CVND0001", TotalVol=0, TotalVal=0, LastMP=None, LastMVol=0,
             HighestP=None, LowestP=None, OpenP=None, AvgP=None),
        _row(StockCode="CVND0002", HighestP=170, LowestP=170, OpenP=170, LastMP=170,
             AvgP=170, TotalVol=100, TotalVal=17000, LastMVol=100),
    ])
    out = intraday_moves(frame)
    tickers = [r["t"] for r in out["rows"]]
    assert "CVND0001" not in tickers          # không giao dịch → không xếp hạng
    flat = [r for r in out["rows"] if r["t"] == "CVND0002"][0]
    assert flat["closeLocation"] is None      # biên độ 0 → vị trí không xác định
    assert out["summary"]["countFlatSession"] == 1
    assert "không phải tín hiệu" in out["summary"]["closeLocationBasis"]


def test_intraday_reports_unavailable_when_nothing_traded():
    frame = _frame([_row(TotalVol=0, TotalVal=0, LastMP=None, LastMVol=0, AvgP=None)])
    out = intraday_moves(frame)
    assert out["available"] is False and out["rows"] == []


# ──────────────────────────────────────────────────────────────────
# DẢI TRẦN – SÀN
# ──────────────────────────────────────────────────────────────────
def test_price_band_reads_source_values_and_never_assumes_7pct():
    # Dải thật của dòng mẫu: FloorP 10, CeilingP 980 — tức trần gấp 98 lần sàn.
    out = price_band_profile(_frame([_row()]))
    s = out["summary"]
    assert s["medianBandPct"] == pytest.approx(9700.0, abs=0.1)
    assert "không cố định" in s["bandBasis"] or "±7%" in s["bandBasis"]
    row = out["rows"][0]
    assert row["floor"] == 10 and row["ceiling"] == 980
    # Còn (980 − 150) / 150 = 553% tới trần
    assert row["toCeilingPct"] == pytest.approx(553.33, abs=0.01)
    assert row["atCeiling"] is False


def test_price_band_flags_ceiling_and_floor_touches():
    frame = _frame([
        _row(StockCode="CUP0001", HighestP=980, LastMP=900, OpenP=800, LowestP=800,
             AvgP=850, TotalVol=1000, TotalVal=850000, LastMVol=100),
        _row(StockCode="CDN0002", LowestP=10, LastMP=15, OpenP=20, HighestP=20,
             AvgP=18, TotalVol=1000, TotalVal=18000, LastMVol=100),
    ])
    s = price_band_profile(frame)["summary"]
    assert s["countAtCeiling"] == 1 and s["atCeiling"] == ["CUP0001"]
    assert s["countAtFloor"] == 1 and s["atFloor"] == ["CDN0002"]


def test_price_band_uses_ref_for_untraded_warrants_not_stale_lastmp():
    """Mã không giao dịch vẫn có RefP, nhưng LastMP là giá phiên cũ → không dùng."""
    frame = _frame([_row(StockCode="CSTALE01", TotalVol=0, TotalVal=0, AvgP=None,
                         LastMP=999, LastMVol=0, RefP=200, CeilingP=300, FloorP=100)])
    out = price_band_profile(frame)
    assert out["rows"] == []                                 # không xếp hạng mã không giao dịch
    assert out["summary"]["countAtCeiling"] == 0             # và không báo chạm trần


# ──────────────────────────────────────────────────────────────────
# CHẤT LƯỢNG LỆNH KHỚP CUỐI
# ──────────────────────────────────────────────────────────────────
def test_last_trade_profile_computes_share_of_session_volume():
    frame = _frame([
        _row(StockCode="CA0001", LastMVol=5000, TotalVol=17700),
        _row(StockCode="CB0002", LastMVol=1000, TotalVol=1000),   # đóng cửa bằng đúng 1 lệnh
        _row(StockCode="CC0003", LastMVol=1, TotalVol=100000),
    ])
    out = last_trade_profile(frame)
    rows = {r["t"]: r for r in out["rows"]}
    assert rows["CA0001"]["lastSharePct"] == pytest.approx(28.2, abs=0.1)
    assert rows["CB0002"]["lastSharePct"] == pytest.approx(100.0)
    assert out["summary"]["countSingleTradeClose"] == 1
    assert out["summary"]["countTraded"] == 3


def test_last_trade_profile_unavailable_without_trades():
    assert last_trade_profile(_frame([_row(TotalVol=0, LastMVol=0, AvgP=None)]))["available"] is False


# ──────────────────────────────────────────────────────────────────
# LIÊN TỤC: RefP vs close phiên trước
# ──────────────────────────────────────────────────────────────────
def _prior_snapshot(session: str, *, scale: float = 1.0):
    """Snapshot "phiên trước" có close = RefP của hôm nay (đúng quy luật của nguồn)."""
    rows = [_row(StockCode="CA0001", RefP=170, LastMP=170, TotalVol=1000, TotalVal=170000,
                 LastMVol=100, AvgP=170),
            _row(StockCode="CB0002", RefP=200, LastMP=200, TotalVol=500, TotalVal=100000,
                 LastMVol=50, AvgP=200)]
    if scale != 1.0:
        for r in rows:
            r["LastMP"] = r["LastMP"] * scale
    return hist.bars_from_rows(rows, hist.resolve_session(session))


def test_ref_continuity_confirms_a_linked_store(tmp_path):
    store = tmp_path / "store"
    hist.upsert_bars(store, _prior_snapshot("2026-11-12T10:30:00+00:00"))
    frame = _frame([_row(StockCode="CA0001", RefP=170), _row(StockCode="CB0002", RefP=200)])

    out = ref_continuity(frame, hist.load_history(store))
    s = out["summary"]
    assert out["prevSession"] == "2026-11-12"
    assert s["sessionBreak"] is False
    assert s["linked"] == 2 and s["mismatch"] == 0
    assert s["linkedPct"] == 100.0
    assert s["verdict"] == "Liền mạch"
    assert out["missingSessionsBeforeCurrent"] == []


def test_ref_continuity_detects_a_missing_session_even_if_prices_match(tmp_path):
    """Kho chỉ có 11-11 → liền trước thật là 11-12. Giá khớp vẫn phải bị coi là đứt."""
    store = tmp_path / "store"
    hist.upsert_bars(store, _prior_snapshot("2026-11-11T10:30:00+00:00"))
    frame = _frame([_row(StockCode="CA0001", RefP=170)])

    out = ref_continuity(frame, hist.load_history(store))
    s = out["summary"]
    assert out["prevSession"] == "2026-11-11"
    assert out["expectedPrevSession"] == "2026-11-12"
    assert s["sessionBreak"] is True
    assert s["linked"] == 0 and s["missingSession"] == 1
    assert "2026-11-12" in out["missingSessionsBeforeCurrent"]
    assert "đứt gãy" in s["verdict"]


def test_ref_continuity_detects_price_mismatch(tmp_path):
    store = tmp_path / "store"
    hist.upsert_bars(store, _prior_snapshot("2026-11-12T10:30:00+00:00", scale=0.6))
    frame = _frame([_row(StockCode="CA0001", RefP=170)])

    out = ref_continuity(frame, hist.load_history(store))
    s = out["summary"]
    assert s["mismatch"] == 1 and s["linked"] == 0
    row = out["rows"][0]
    assert row["status"] == "mismatch"
    assert row["diffPct"] == pytest.approx(66.67, abs=0.1)
    assert "đứt gãy" in s["verdict"]


def test_ref_continuity_does_not_conclude_when_prior_day_had_no_close(tmp_path):
    """Phiên trước không khớp lệnh → không có close để so, và phải nói đúng như vậy."""
    store = tmp_path / "store"
    bars = hist.bars_from_rows(
        [_row(StockCode="CA0001", TotalVol=0, TotalVal=0, LastMP=None, LastMVol=0, AvgP=None)],
        hist.resolve_session("2026-11-12T10:30:00+00:00"))
    hist.upsert_bars(store, bars)
    out = ref_continuity(_frame([_row(StockCode="CA0001", RefP=170)]), hist.load_history(store))
    assert out["summary"]["untradedRef"] == 1
    assert out["summary"]["linked"] == 0
    assert out["rows"][0]["status"] == "untradedRef"


def test_ref_continuity_is_unavailable_without_a_prior_session(tmp_path):
    store = tmp_path / "store"
    hist.upsert_bars(store, _prior_snapshot("2026-11-13T10:30:00+00:00"))
    out = ref_continuity(_frame([_row()]), hist.load_history(store))
    assert out["available"] is False
    assert "phiên đầu tiên" in out["reason"]


def test_ref_continuity_survives_weekend_gap(tmp_path):
    """Thứ Sáu → Thứ Hai là liền mạch: không được báo thiếu phiên."""
    friday = "2026-11-06T10:30:00+00:00"
    bars = hist.bars_from_rows([_row(StockCode="CA0001", LastMP=170, RefP=170, TotalVol=10,
                                     TotalVal=1700, AvgP=170, LastMVol=10)],
                               hist.resolve_session(friday))
    store = tmp_path / "store"
    hist.upsert_bars(store, bars)
    monday = _frame([_row(StockCode="CA0001", RefP=170)], at="2026-11-09T10:30:00+00:00")
    out = ref_continuity(monday, hist.load_history(store))
    assert out["prevSession"] == "2026-11-06"
    assert out["summary"]["sessionBreak"] is False
    assert out["summary"]["linked"] == 1


# ──────────────────────────────────────────────────────────────────
# TÍCH HỢP
# ──────────────────────────────────────────────────────────────────
def test_analytics_payload_includes_the_four_new_blocks():
    from cwintel.yuanta_analytics import build_analytics

    frame = _frame([_row()])
    out = build_analytics(frame, asof="2026-11-13")
    for key in ("intraday", "priceBand", "lastTrade", "refContinuity"):
        assert key in out, key
    assert out["intraday"]["available"] is True
    assert out["refContinuity"]["available"] is False      # chưa có kho lịch sử
    caveats = " ".join(out["caveats"])
    assert "RefP là giá đóng cửa phiên trước" in caveats
    assert "không dùng ±7%" in caveats


def test_series_payload_carries_ref_change_from_the_first_session(tmp_path):
    """% thay đổi có ngay ở phiên đầu vì RefP là close hôm qua — không cần chờ phiên 2."""
    store = tmp_path / "store"
    hist.upsert_bars(store, hist.bars_from_rows(
        [_row(StockCode="CA0001", RefP=170, LastMP=153, AvgP=153, TotalVol=100,
              TotalVal=15300, LastMVol=100)],
        hist.resolve_session("2026-11-13T10:30:00+00:00")))
    series = hist.series_payload(hist.load_history(store))["CA0001"]
    assert series["refChangePct"][0] == pytest.approx(-10.0, abs=0.01)
    assert series["c"][0] == 153.0


def test_series_payload_ref_change_is_null_for_untraded_rows(tmp_path):
    store = tmp_path / "store"
    hist.upsert_bars(store, hist.bars_from_rows(
        [_row(StockCode="CA0001", TotalVol=0, TotalVal=0, LastMP=None, LastMVol=0, AvgP=None)],
        hist.resolve_session("2026-11-13T10:30:00+00:00")))
    series = hist.series_payload(hist.load_history(store))["CA0001"]
    assert series["refChangePct"] == [None]      # không có close → không có % thay đổi
    assert series["c"] == [None]


# ──────────────────────────────────────────────────────────────────
# UI: hai tab mới phải tồn tại và không được hứa hẹn quá dữ liệu
# ──────────────────────────────────────────────────────────────────
def test_ui_exposes_intraday_and_band_tabs():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "docs" / "index.html").read_text(encoding="utf-8")
    for view in ("intraday", "band"):
        assert f'data-view="{view}"' in html
        assert f'id="view-{view}"' in html
    assert "renderIntraday();" in html and "renderBand();" in html
    # Phải nói rõ RefP là giá đóng cửa phiên trước, và dải trần–sàn không phải ±7%
    assert "giá đóng cửa phiên trước" in html
    assert "không bao giờ dùng ±7%" in html
