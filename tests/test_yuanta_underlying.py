"""Test cho lịch sử OHLCV cổ phiếu cơ sở và phần IV − HV.

Trọng tâm là những chỗ dễ sai một cách âm thầm: nội suy ngày thiếu, coi phiên không khớp
lệnh là giá đứng, và biến khối lượng khối ngoại thành tiền khi nguồn không cho giá trị.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from cwintel import yuanta_underlying as hist


def _payload(days: list[str], closes: list[float], *, volume: int = 1_000_000) -> dict:
    return {"success": True, "response": [
        {"TradingDate": d, "PerChange": 0.5, "Close": c, "Open": c, "Highest": c,
         "Lowest": c, "Average": c, "Volume": volume, "Value": volume * c,
         "ForeignVolumeBuy": 100, "ForeignVolumeSell": 50,
         "PutThroughVolume": 0, "PutThroughValue": 0}
        for d, c in zip(days, closes)
    ]}


# ── URL ──────────────────────────────────────────────────────────────────
def test_history_url_has_required_shape():
    url = hist.history_url("ACB", from_date="2010-01-01", to_date="2026-11-13")
    assert url == ("https://ysradarapi.yuanta.com.vn/api/v3/market_data/market_watch/"
                   "price_history/ACB?from_date=2010-01-01&to_date=2026-11-13")


def test_history_url_uppercases_and_defaults_end_to_today():
    url = hist.history_url("acb")
    assert "/price_history/ACB?" in url
    assert url.endswith(f"to_date={hist.utc_now()[:10]}")


def test_history_url_rejects_bad_symbol():
    with pytest.raises(ValueError):
        hist.history_url("ACB/../etc")


# ── parse ────────────────────────────────────────────────────────────────
def test_parse_history_maps_all_columns():
    frame = hist.parse_history(_payload(["2026-11-12"], [22100.0]), "ACB")
    assert list(frame.columns) == list(hist.COLUMNS)
    row = frame.iloc[0]
    assert row["TradingDate"] == "2026-11-12"
    assert row["Close"] == 22100.0
    assert row["ForeignVolumeBuy"] == 100


def test_parse_history_sorts_and_dedupes():
    frame = hist.parse_history(
        _payload(["2026-11-13", "2026-11-11", "2026-11-12"], [3, 1, 2]), "ACB")
    assert frame["TradingDate"].tolist() == ["2026-11-11", "2026-11-12", "2026-11-13"]


def test_parse_history_drops_rows_without_valid_date():
    payload = _payload(["2026-11-12"], [100.0])
    payload["response"].append({"TradingDate": "not-a-date", "Close": 1})
    frame = hist.parse_history(payload, "ACB")
    assert len(frame) == 1


def test_parse_history_raises_when_api_reports_failure():
    with pytest.raises(ValueError, match="success=false"):
        hist.parse_history({"success": False, "response": None}, "ACB")


def test_parse_history_raises_when_response_missing():
    """Payload rác phải nổ, không được lặng lẽ thành bảng rỗng."""
    with pytest.raises(ValueError, match="response"):
        hist.parse_history({"data": []}, "ACB")


def test_parse_history_does_not_invent_missing_values():
    payload = _payload(["2026-11-12"], [100.0])
    payload["response"][0]["ForeignVolumeBuy"] = None
    frame = hist.parse_history(payload, "ACB")
    assert pd.isna(frame.iloc[0]["ForeignVolumeBuy"])


# ── merge: resume không nhân đôi ─────────────────────────────────────────
def test_merge_prefers_fresh_row_on_same_date():
    old = hist.parse_history(_payload(["2026-11-11", "2026-11-12"], [1.0, 2.0]), "ACB")
    new = hist.parse_history(_payload(["2026-11-12", "2026-11-13"], [9.0, 3.0]), "ACB")
    merged = hist.merge_history(old, new)
    assert merged["TradingDate"].tolist() == ["2026-11-11", "2026-11-12", "2026-11-13"]
    assert merged.iloc[1]["Close"] == 9.0      # dòng mới thắng


def test_merge_is_idempotent():
    frame = hist.parse_history(_payload(["2026-11-11", "2026-11-12"], [1.0, 2.0]), "ACB")
    once = hist.merge_history(frame, frame)
    twice = hist.merge_history(once, frame)
    assert len(once) == len(twice) == 2


def test_merge_handles_empty_sides():
    frame = hist.parse_history(_payload(["2026-11-12"], [1.0]), "ACB")
    assert len(hist.merge_history(None, frame)) == 1
    assert len(hist.merge_history(frame, None)) == 1


# ── HV ───────────────────────────────────────────────────────────────────
def test_realized_volatility_matches_manual_computation():
    closes = [100.0 + i * 0.7 for i in range(40)]      # xu hướng đều → vol rất nhỏ
    value = hist.realized_volatility(closes, window=21)
    manual = np.std(np.diff(np.log(np.array(closes[-21:]))), ddof=1) * np.sqrt(252) * 100
    assert value == pytest.approx(manual, rel=1e-6)
    assert value < 5


def test_realized_volatility_returns_none_when_too_few_points():
    assert hist.realized_volatility([100.0, 101.0, 102.0]) is None


def test_realized_volatility_ignores_non_positive_prices():
    """Giá 0 là lỗi dữ liệu, không phải mức giá — nếu để lọt, log(0) làm hỏng HV."""
    closes = [100.0, 0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0,
              108.0, 109.0, 110.0, 111.0]
    assert hist.realized_volatility(closes, window=21) is not None


def test_realized_volatility_grows_with_dispersion():
    calm = hist.realized_volatility([100, 101, 100, 101, 100, 101, 100, 101, 100,
                                     101, 100, 101], window=21)
    wild = hist.realized_volatility([100, 120, 90, 115, 85, 118, 88, 121, 87, 119,
                                     86, 120], window=21)
    assert wild > calm


# ── coverage ─────────────────────────────────────────────────────────────
def test_coverage_lists_gap_between_present_days():
    frame = hist.parse_history(_payload(["2026-11-10", "2026-11-12"], [1.0, 2.0]), "ACB")
    result = hist.coverage(frame)
    assert result["available"] is True
    assert result["sessions"] == 2
    assert "2026-11-11" in result["missing"]


def test_coverage_does_not_flag_weekend_as_missing():
    # 2026-11-13 là thứ Sáu, 2026-11-16 thứ Hai → cuối tuần không phải phiên thiếu.
    frame = hist.parse_history(_payload(["2026-11-13", "2026-11-16"], [1.0, 2.0]), "ACB")
    assert hist.coverage(frame)["missing"] == []


def test_coverage_counts_zero_volume_sessions():
    payload = _payload(["2026-11-12", "2026-11-13"], [1.0, 2.0])
    payload["response"][1]["Volume"] = 0
    result = hist.coverage(hist.parse_history(payload, "ACB"))
    assert result["zeroVolumeSessions"] == 1


def test_coverage_empty_frame_is_unavailable_not_zero():
    assert hist.coverage(pd.DataFrame())["available"] is False


# ── khối ngoại: khối lượng, không phải tiền ─────────────────────────────
def test_foreign_flow_reports_volume_unit_explicitly():
    frame = hist.parse_history(_payload(["2026-11-12"], [100.0]), "ACB")
    result = hist.foreign_flow(frame)
    assert result["available"] is True
    assert result["netVolumeLast"] == 50          # 100 mua − 50 bán
    assert "cổ phiếu" in result["unit"]


def test_foreign_flow_never_returns_a_currency_field():
    frame = hist.parse_history(_payload(["2026-11-12"], [100.0]), "ACB")
    result = hist.foreign_flow(frame)
    assert not any("Value" in key for key in result)


# ── summarize ────────────────────────────────────────────────────────────
def test_summarize_last_row_is_latest_and_has_hv():
    days = [f"2026-{m:02d}-{d:02d}" for m, d in [(9, 1), (9, 2), (9, 3)]]
    closes = [100.0 + i for i in range(12)]
    payload = _payload(days + [f"2026-09-{i:02d}" for i in range(4, 14)], closes)
    frame = hist.parse_history(payload, "ACB")
    result = hist.summarize(frame)
    assert result["available"] is True
    assert result["lastDate"] == frame["TradingDate"].iloc[-1]
    assert result["sessions"] == 12
    assert result["hvShortPct"] is not None
    assert "không nội suy" in result["hvBasis"]


def test_summarize_of_empty_frame_is_unavailable():
    assert hist.summarize(None)["available"] is False


# ── store ────────────────────────────────────────────────────────────────
def test_store_round_trip(tmp_path):
    frame = hist.parse_history(_payload(["2026-11-12"], [100.0]), "ACB")
    hist.write_store({"ACB": frame}, tmp_path)
    loaded = hist.load_store(tmp_path, "ACB")
    assert loaded is not None and len(loaded) == 1
    assert hist.load_store(tmp_path, "ZZZ") is None


def test_import_from_files_uses_filename_as_symbol(tmp_path):
    path = tmp_path / "VPB.json"
    path.write_text(json.dumps(_payload(["2026-11-12"], [100.0])), encoding="utf-8")
    frames = hist.import_from_files([path])
    assert list(frames) == ["VPB"]


def test_import_from_files_skips_corrupt_json(tmp_path):
    bad = tmp_path / "BAD.json"
    bad.write_text("{not json", encoding="utf-8")
    assert hist.import_from_files([bad]) == {}


# ── tích hợp với định giá ───────────────────────────────────────────────
def test_iv_vs_hv_is_unavailable_without_history():
    from cwintel.yuanta_analytics import _iv_vs_hv

    priced = pd.DataFrame({"iv": [0.5], "ivMinusHv": [np.nan]})
    assert _iv_vs_hv(priced)["available"] is False


def test_iv_vs_hv_summarises_available_rows():
    from cwintel.yuanta_analytics import _iv_vs_hv

    priced = pd.DataFrame({"ivMinusHv": [30.0, 20.0, -5.0, np.nan]})
    result = _iv_vs_hv(priced)
    assert result["available"] is True
    assert result["count"] == 3
    assert result["medianIvMinusHv"] == pytest.approx(20.0)
    assert result["countIvAboveHv"] == 2
    assert result["countIvBelowHv"] == 1


# ── lịch thị trường suy từ dữ liệu ──────────────────────────────────────
def _day_frames(presence: dict[str, list[str]]) -> dict[str, pd.DataFrame]:
    return {sym: hist.parse_history(_payload(days, [100.0] * len(days)), sym)
            for sym, days in presence.items()}


def test_market_calendar_excludes_days_when_every_symbol_is_absent():
    """Ngày lễ 2010–2020 không có trong config, nên phải suy từ dữ liệu."""
    frames = _day_frames({
        "ACB": ["2021-09-01", "2021-09-02", "2021-09-06"],
        "FPT": ["2021-09-01", "2021-09-02", "2021-09-06"],
        "VNM": ["2021-09-01", "2021-09-02", "2021-09-06"],
    })
    frames["ACB"] = frames["ACB"][frames["ACB"]["TradingDate"] != "2021-09-02"].reset_index(drop=True)
    frames["FPT"] = frames["FPT"][frames["FPT"]["TradingDate"] != "2021-09-02"].reset_index(drop=True)
    frames["VNM"] = frames["VNM"][frames["VNM"]["TradingDate"] != "2021-09-02"].reset_index(drop=True)
    assert "2021-09-02" not in hist.market_calendar(frames)


def test_market_calendar_keeps_day_when_most_symbols_trade():
    frames = _day_frames({
        "ACB": ["2021-10-06", "2021-10-07"],
        "FPT": ["2021-10-06", "2021-10-07"],
        "VNM": ["2021-10-06", "2021-10-07"],
        "SHB": ["2021-10-07"],                      # SHB bị đình chỉ riêng 6/10
    })
    assert "2021-10-06" in hist.market_calendar(frames)


def test_coverage_with_market_flags_single_symbol_suspension():
    """SHB vắng 6/10 trong khi thị trường mở → lỗ hổng THẬT, phải bị báo."""
    frames = _day_frames({
        "ACB": ["2021-10-05", "2021-10-06", "2021-10-07"],
        "FPT": ["2021-10-05", "2021-10-06", "2021-10-07"],
        "VNM": ["2021-10-05", "2021-10-06", "2021-10-07"],
        "SHB": ["2021-10-05", "2021-10-07"],
    })
    market = hist.market_calendar(frames)
    assert hist.coverage(frames["SHB"], market=market)["missing"] == ["2021-10-06"]
    assert hist.coverage(frames["ACB"], market=market)["missing"] == []


def test_coverage_reports_calendar_basis():
    frames = _day_frames({"ACB": ["2021-10-05", "2021-10-06"]})
    market = hist.market_calendar(frames)
    assert "suy từ dữ liệu" in hist.coverage(frames["ACB"], market=market)["calendarBasis"]


def test_market_calendar_of_empty_store_is_empty():
    assert hist.market_calendar({}) == set()


# ── chặn S lệch quá biên giá Việt Nam ───────────────────────────────────
def _terms_row(**over) -> pd.DataFrame:
    base = {"session": "2026-11-13", "ticker": "CXXX2601", "underlying": "XXX",
            "strike": 26000.0, "ratio": 2.0,
            "maturity": "2026-12-17", "underlyingPrice": 23600.0, "crosscheckPct": 0.0,
            "termsSource": "test"}
    base.update(over)
    return pd.DataFrame([base])


def _board_row(price: float = 120.0) -> pd.DataFrame:
    return pd.DataFrame([{"StockCode": "CXXX2601", "Traded": True, "LastPrice": price,
                          "RefPrice": price, "UnderlyingPrice": 23600.0}])


def _history(closes: list[float]) -> pd.DataFrame:
    days = pd.bdate_range("2026-08-01", periods=len(closes)).strftime("%Y-%m-%d").tolist()
    return hist.parse_history(_payload(days, closes), "XXX")


def test_derived_price_drift_is_absorbed_by_rescaling_terms():
    """S nguồn lệch >±7% KHÔNG phải dữ liệu xấu — đó là dấu hiệu CW đã được điều chỉnh.

    Bản cũ của test này khẳng định loại mã. Điều đó sai: chính CACB2515 (RefP 31.800 gốc,
    giá thật 20.350) rơi vào tình huống này, và trang Vietstock xác nhận strike điều chỉnh
    27.420 · tỷ lệ 1,7245. Loại mã là bỏ mất 100 CW định giá được.
    """
    from cwintel.yuanta_valuation import price_warrants

    priced, diag = price_warrants(_board_row(), _terms_row(),
                                  session="2026-11-13", underlying_history={})
    assert len(priced) == 1                       # không có lịch sử → dùng S suy ra

    priced, diag = price_warrants(_board_row(), _terms_row(), session="2026-11-13",
                                  underlying_history={"XXX": _history([20350.0] * 30)})
    assert len(priced) == 1
    row = priced.iloc[0]
    # f = 23600/20350 = 1.1597 → strike 26000/f, ratio 2/f
    assert row["termsBasis"] == "dựng lại từ chênh lệch giá"
    assert abs(row["strike"] - 26000.0 / (23600.0 / 20350.0)) < 1.0
    assert abs(row["correctionFactor"] - 23600.0 / 20350.0) < 1e-4
    assert diag["excluded"].get("S nguồn lệch >±7% (đã quy đổi điều khoản, vẫn định giá)") == 1


def test_drift_beyond_confidence_range_still_excludes():
    """Ngoài khoảng tin cậy thì không dựng lại được → vẫn phải loại, không định giá liều.

    Lệch gấp nhiều lần biên ±7% không thể là điều chỉnh thật; nhiều khả năng nguồn dùng giá
    rất cũ. Khi đó hai hệ không ghép được và định giá sẽ vô nghĩa.
    """
    from cwintel.yuanta_valuation import price_warrants

    # S thật 20350, S nguồn 23600*10 → f = 11.6, vượt MAX_CORRECTION_FACTOR
    terms = _terms_row(underlyingPrice=236000.0)
    priced, diag = price_warrants(_board_row(), terms, session="2026-11-13",
                                  underlying_history={"XXX": _history([20350.0] * 30)})
    assert priced.empty
    assert diag["excluded"][
        "S nguồn lệch quá biên giá (±7%) và chưa quy đổi được điều khoản"] == 1


def test_source_adjusted_terms_take_priority_over_rescaling():
    """Khi nguồn đã trả điều khoản điều chỉnh thì dùng thẳng, không dựng lại."""
    from cwintel.yuanta_valuation import price_warrants

    terms = _terms_row(strikeAdjusted=27420.0, ratioAdjusted=1.7245,
                       maturityAdjusted="2027-03-08")
    priced, _ = price_warrants(_board_row(), terms, session="2026-11-13",
                               underlying_history={"XXX": _history([20350.0] * 30)})
    row = priced.iloc[0]
    assert row["termsBasis"] == "điều chỉnh từ nguồn"
    assert row["strike"] == 27420.0
    assert row["ratio"] == 1.7245
    assert row["maturity"] == "2027-03-08"


def test_price_history_within_limit_is_used_and_recorded():
    from cwintel.yuanta_valuation import price_warrants

    priced, _ = price_warrants(_board_row(), _terms_row(underlyingPrice=23500.0),
                               session="2026-11-13",
                               underlying_history={"XXX": _history([23000.0] * 30)})
    assert len(priced) == 1
    assert priced.iloc[0]["underlyingPrice"] == 23000.0
    assert "lịch sử Yuanta" in priced.iloc[0]["underlyingSource"]
