"""Kiểm thử nhập điều khoản Vietstock và định giá Black–Scholes.

Điều dễ sai nhất ở đây là **nguồn gốc của từng con số**. ``S`` không có trong file daily của
Vietstock; nó được suy từ premium và đòn bẩy. Nếu hai cách suy không khớp, bản ghi phải bị
loại — không được lấy trung bình hai giá trị rồi dùng. Test dưới đây khoá đúng điều đó.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from cwintel import config
from cwintel.yuanta_board import clean_board
from cwintel.yuanta_valuation import (
    price_warrants,
    realized_vol_from_series,
    summarize,
    years_to_maturity,
)
from scripts.import_vietstock_terms import (
    build_terms_frame,
    derive_underlying_price,
    parse_maturity,
    parse_ratio,
    terms_from_records,
)

ROOT = Path(__file__).resolve().parents[1]


# ──────────────────────────────────────────────────────────────────
# PARSER
# ──────────────────────────────────────────────────────────────────
def test_parse_ratio_handles_vietstock_format():
    assert parse_ratio("2 : 1") == 2.0
    assert parse_ratio("4:1") == 4.0
    assert parse_ratio("1 : 10") == pytest.approx(0.1)
    assert parse_ratio("2 / 1") == 2.0
    assert parse_ratio(3) == 3.0
    assert parse_ratio(None) is None
    assert parse_ratio("") is None
    assert parse_ratio("abc") is None
    assert parse_ratio("0 : 1") is None


def test_parse_maturity_accepts_source_and_iso():
    assert parse_maturity("04/03/2027") == date(2027, 3, 4)
    assert parse_maturity("2027-03-04") == date(2027, 3, 4)
    assert parse_maturity(None) is None
    assert parse_maturity("không phải ngày") is None


def test_derive_underlying_price_crosschecks_two_formulas():
    # CACB2515 thật: K=31,800 cw=150 n=2 premium=36.01 leverage=78.67 → S≈23,601
    price, diff, second = derive_underlying_price(31800, 150, 2.0, 36.01, 78.67)
    assert price == pytest.approx(23601.0, abs=1)
    assert diff is not None and diff < 1.0
    assert second == pytest.approx(23601.2, abs=2)


def test_derive_underlying_price_reports_large_disagreement():
    """Hai công thức lệch nhiều → vẫn trả số, nhưng ``diff`` phải tố cáo."""
    price, diff, _ = derive_underlying_price(31800, 150, 2.0, 5.0, 78.67)
    assert price is not None
    assert diff > 1.0


def test_derive_underlying_price_falls_back_to_premium_only():
    price, diff, second = derive_underlying_price(31800, 150, 2.0, 36.01, None)
    assert price == pytest.approx(23601.2, abs=2)
    assert diff is None and second is None


def test_terms_from_records_maps_vietstock_fields():
    rows = terms_from_records([{
        "ma_cw": "cacb2515", "ck_co_so": "acb", "to_chuc_ph_cw": "VNDIRECT",
        "gia_thuc_hien": "31,800", "ty_le_chuyen_doi": "2 : 1",
        "ngay_gd_cuoi_cung": "04/03/2027", "gia_hien_tai": 150,
        "premium": 36.01, "don_bay": 78.67,
    }], "2026-11-13")
    row = rows[0]
    assert row["ticker"] == "CACB2515"          # chuẩn hoá hoa
    assert row["underlying"] == "ACB"
    assert row["strike"] == 31800
    assert row["ratio"] == 2.0
    assert row["maturity"] == "2027-03-04"      # ISO, không phải dd/mm/yyyy
    assert row["daysToMaturity"] == (date(2027, 3, 4) - date(2026, 11, 13)).days
    assert row["underlyingPrice"] == pytest.approx(23601.0, abs=1)
    assert row["crosscheckOk"] is True


def test_build_terms_frame_dedupes_by_session_and_ticker():
    day = [{"ma_cw": "CAAA2501", "gia_thuc_hien": "100", "ty_le_chuyen_doi": "1 : 1",
            "ngay_gd_cuoi_cung": "01/12/2027", "gia_hien_tai": 10,
            "premium": 10.0, "don_bay": 10.0},
           {"ma_cw": "CAAA2501", "gia_thuc_hien": "200", "ty_le_chuyen_doi": "1 : 1",
            "ngay_gd_cuoi_cung": "01/12/2027", "gia_hien_tai": 10,
            "premium": 10.0, "don_bay": 10.0}]
    frame = build_terms_frame({"2026-11-13": day})
    assert len(frame) == 1
    assert frame.iloc[0]["strike"] == 200      # bản cuối thắng


# ──────────────────────────────────────────────────────────────────
# ĐỊNH GIÁ
# ──────────────────────────────────────────────────────────────────
def _cw(rows, at="2026-11-13T10:30:00+00:00"):
    return clean_board(rows, fetched_at=datetime.fromisoformat(at))


def _cw_row(**over):
    base = {
        "StockCode": "CACB2515", "Exchange": "HSX", "SymbolType": "EW",
        "RefP": 150, "CeilingP": 210, "FloorP": 90, "OpenP": 150,
        "HighestP": 155, "LowestP": 145, "AvgP": 150, "LastMP": 150, "LastMVol": 100,
        "TotalVol": 10_000, "TotalVal": 1_500_000, "B1P": 140, "S1P": 150,
    }
    base.update(over)
    return base


def _terms(rows):
    return pd.DataFrame(rows)


def _term_row(ticker="CACB2515", **over):
    base = {
        "session": "2026-11-13", "ticker": ticker, "underlying": "ACB", "issuer": "VNDIRECT",
        "strike": 31800.0, "ratio": 2.0, "maturity": "2027-03-04", "daysToMaturity": 111,
        "underlyingPrice": 23601.0, "cwClose": 150.0, "premiumPct": 36.01, "leverage": 78.67,
        "crosscheckPct": 0.001, "crosscheckOk": True, "termsSource": "vietstock",
        "importedAt": "2026-11-13T00:00:00+00:00",
    }
    base.update(over)
    return base


def test_years_to_maturity_uses_project_day_count():
    t = years_to_maturity("2026-11-13", "2026-11-14")
    assert t == pytest.approx(1 / config.DAYS_PER_YEAR)
    assert years_to_maturity("2026-11-13", "2026-11-13") is None       # T = 0
    assert years_to_maturity("2026-11-13", "2026-11-01") is None       # đã đáo hạn
    assert years_to_maturity("2026-11-13", None) is None


def test_price_warrants_produces_iv_and_greeks():
    frame = _cw([_cw_row()])
    priced, diag = price_warrants(frame, _terms([_term_row()]), session="2026-11-13")
    assert diag["available"] is True and diag["priced"] == 1
    row = priced.iloc[0]
    # IV phải dương và nằm trong dải hợp lý; không kiểm tra đúng số vì phụ thuộc solver
    assert 5 < row["iv"] < 300
    assert row["delta"] is not None and 0 <= row["delta"] <= 1
    assert row["bsPrice"] is not None and row["bsPrice"] > 0
    # Mô hình là quyền chọn mua: delta theo CW = delta_option / ratio
    assert row["deltaOption"] == pytest.approx(row["delta"] * 2.0, abs=1e-3)
    assert row["moneyness"] == "OTM"           # S=23,601 < K=31,800
    assert row["premiumPct"] == pytest.approx((31800 + 150 * 2 - 23601) / 23601 * 100, abs=0.01)


def test_price_warrants_excludes_when_underlying_crosscheck_fails():
    """S không nhất quán → không được dùng để định giá, dù đủ bốn biến."""
    frame = _cw([_cw_row()])
    priced, diag = price_warrants(frame, _terms([_term_row(crosscheckPct=12.0)]),
                                  session="2026-11-13")
    assert priced.empty
    assert any("không khớp chéo" in k for k in diag["excluded"])


def test_price_warrants_excludes_missing_terms_and_names_the_reason():
    frame = _cw([_cw_row(StockCode="CNOTERMS"), _cw_row()])
    terms = _terms([_term_row()])        # chỉ có CACB2515
    priced, diag = price_warrants(frame, terms, session="2026-11-13")
    assert diag["priced"] == 1
    assert diag["excluded"]["không có điều khoản trong nguồn Vietstock"] == 1


def test_price_warrants_excludes_untraded_warrants():
    frame = _cw([_cw_row(TotalVol=0, TotalVal=0, LastMP=None, AvgP=None)])
    priced, diag = price_warrants(frame, _terms([_term_row()]), session="2026-11-13")
    assert priced.empty
    assert diag["priced"] == 0


def test_price_warrants_reports_when_terms_absent():
    frame = _cw([_cw_row()])
    priced, diag = price_warrants(frame, pd.DataFrame(), session="2026-11-13")
    assert priced.empty
    assert diag["available"] is False
    assert "import_vietstock_terms.py" in diag["reason"]


def test_price_warrants_warns_risk_free_is_a_config_constant():
    frame = _cw([_cw_row()])
    _, diag = price_warrants(frame, _terms([_term_row()]), session="2026-11-13")
    assert diag["riskFree"] == config.DEFAULT_RISK_FREE
    # Có đường cong thì không rơi vào nhánh này; ở đây không truyền `yield_curve` nên vẫn
    # phải cảnh báo rằng con số là tham số phần mềm, không phải số liệu thị trường.
    assert "Tham số phần mềm" in diag["riskFreeSource"]
    assert diag["riskFreeByTenor"] is False
    assert "KHÔNG phải dự báo" in diag["ivInterpretation"]


def test_iv_residual_is_relative_to_the_same_underlying_only():
    """Hai cơ sở khác nhau có IV khác nhau không được so với nhau."""
    frame = _cw([
        _cw_row(StockCode="CACB2515", RefP=150, LastMP=150, AvgP=150),
        _cw_row(StockCode="CACB2516", RefP=300, LastMP=300, AvgP=300,
                TotalVal=3_000_000),
    ])
    terms = _terms([
        _term_row("CACB2515"),
        _term_row("CACB2516", cwClose=300.0),
    ])
    priced, _ = price_warrants(frame, terms, session="2026-11-13")
    # Chỉ 2 mã cùng cơ sở → nhóm dưới ngưỡng 5, không được gán residual
    assert priced["ivResidualPct"].isna().all()
    assert (priced["ivGroupSize"] == 2).all()


def test_summarize_is_descriptive_and_flags_no_forecast():
    frame = _cw([_cw_row()])
    priced, _ = price_warrants(frame, _terms([_term_row()]), session="2026-11-13")
    summary = summarize(priced)
    assert summary["available"] is True
    assert summary["count"] == 1
    assert "Không phải dự báo" in summary["note"] or "không phải" in summary["note"].lower()


# ──────────────────────────────────────────────────────────────────
# BIẾN ĐỘNG THỰC HIỆN TỪ CHUỖI ĐÃ TÍCH LUỸ
# ──────────────────────────────────────────────────────────────────
def test_realized_vol_needs_enough_sessions():
    thin = pd.DataFrame({"ticker": ["A"] * 5, "session": [f"2026-11-0{i}" for i in range(1, 6)],
                         "close": [100, 101, 102, 101, 103]})
    assert realized_vol_from_series(thin) == {}


def test_realized_vol_computes_from_available_closes_without_filling_gaps():
    sessions = [f"2026-10-{d:02d}" for d in range(1, 16)]
    closes = [100 * (1.01 ** i) for i in range(15)]
    series = pd.DataFrame({"ticker": ["A"] * 15, "session": sessions, "close": closes})
    vol = realized_vol_from_series(series)
    assert "A" in vol and vol["A"] > 0
    # Phiên thiếu giá không được nội suy: bỏ dòng đó thì biến động vẫn tính được
    series.loc[series.index[3], "close"] = None
    vol2 = realized_vol_from_series(series)
    assert "A" in vol2


# ──────────────────────────────────────────────────────────────────
# TÍCH HỢP: ĐIỂM SỐ CÓ TRỤC ĐỊNH GIÁ
# ──────────────────────────────────────────────────────────────────
def test_scoring_uses_valuation_when_pricing_available():
    from cwintel.yuanta_scoring import score_warrants

    frame = _cw([_cw_row()])
    priced, diag = price_warrants(frame, _terms([_term_row()]), session="2026-11-13")
    scored = score_warrants(frame, priced=priced, valuation_diagnostics=diag)
    assert scored["weights"]["valuation"] == pytest.approx(0.20)
    assert sum(scored["weights"].values()) == pytest.approx(1.0)
    # Hai khái niệm KHÁC nhau, không được gộp:
    #   valuation.available      = đã định giá được bằng BS (có đủ điều khoản)
    #   valuationMeta.available  = chấm được điểm định giá, tức cần nhóm ≥ 5 mã cùng cơ sở
    # Với một mã đơn lẻ: BS chạy được, nhưng không có gì để so sánh IV.
    assert scored["valuation"]["available"] is True
    assert scored["valuationMeta"]["available"] is False
    assert scored["ranking"][0]["parts"]["valuation"] is None


def test_scoring_stays_locked_without_terms():
    from cwintel.yuanta_scoring import score_warrants

    scored = score_warrants(_cw([_cw_row()]))
    assert scored["valuation"]["available"] is False
    assert scored["valuation"]["blockedBy"]
    assert scored["ranking"][0]["parts"]["valuation"] is None
