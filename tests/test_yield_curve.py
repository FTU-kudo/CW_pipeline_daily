"""Lãi suất phi rủi ro từ đường cong TPCP HNX — không được lặng lẽ rơi về hằng số.

Bối cảnh: toàn bộ định giá Black–Scholes từng dùng `config.DEFAULT_RISK_FREE = 0.0444` và
payload phải tự thú đó là "tham số phần mềm". Repo `FTU-kudo/VN_Bond_Yield_pipeline` cung cấp
đường cong HNX hằng ngày, nên `r` trở thành số liệu thị trường.

Điểm dễ sai nhất, được khoá bằng test ở đây: HNX trả **ba** loại lợi suất cho cùng một kỳ hạn.
Chỉ `spot_continuous` đúng cơ sở chiết khấu `exp(-rT)` của Black–Scholes.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from cwintel import yield_curve as yc


#: Đường cong thật của HNX ngày 2026-11-13 (spot_continuous, %/năm), đúng phiên bảng giá dùng.
REAL_2026_11_13: dict[str, float] = {
    "3M": 3.687576, "6M": 3.721695, "9M": 3.755134, "1Y": 3.787896,
    "2Y": 3.912274, "3Y": 4.026186, "5Y": 4.223712, "7Y": 4.382650,
    "10Y": 4.553354, "15Y": 4.674466, "20Y": 4.618107,
}


def _curve(rates: dict[str, float] | None = None) -> pd.DataFrame:
    """Khung long tối thiểu để test nội suy, dựng từ dict kỳ hạn → %/năm."""
    rates = REAL_2026_11_13 if rates is None else rates
    return pd.DataFrame([
        {"date": pd.Timestamp("2026-11-13"), "tenor": tenor,
         "years": yc.TENOR_YEARS[tenor], "rate": pct / 100.0}
        for tenor, pct in rates.items()
    ])


# ── cơ sở lãi suất ──────────────────────────────────────────────────────
def test_continuous_basis_equals_log_of_annual():
    """`spot_continuous = ln(1 + spot_annual)` — xác nhận trên số liệu HNX thật.

    Đây là lý do chỉ `spot_continuous` dùng được: BS chiết khấu bằng exp(-rT), tức cơ sở
    liên tục. Dùng `par_yield` hay `spot_annual` là lệch cơ sở.
    """
    annual_pct = 3.860552          # par_yield == spot_annual cho 1Y ngày 2026-11-13
    continuous_pct = 3.787896      # spot_continuous cùng kỳ hạn
    assert math.isclose(math.log(1 + annual_pct / 100) * 100, continuous_pct, abs_tol=1e-4)


def test_rate_type_is_continuous():
    assert yc.RATE_TYPE == "spot_continuous"


# ── nội suy theo kỳ hạn ────────────────────────────────────────────────
def test_rate_at_exact_tenor_matches_source_value():
    curve = _curve(REAL_2026_11_13)
    assert math.isclose(yc.rate_for_years(curve, 1.0) * 100, 3.787896, abs_tol=1e-6)
    assert math.isclose(yc.rate_for_years(curve, 0.25) * 100, 3.687576, abs_tol=1e-6)


def test_rate_between_tenors_is_linear_interpolation():
    """Kỳ hạn CW trung vị ~119 ngày nằm giữa 3M và 6M — không trùng kỳ hạn chuẩn nào."""
    curve = _curve(REAL_2026_11_13)
    r = yc.rate_for_years(curve, 0.375) * 100          # giữa 3M (0,25) và 6M (0,5)
    expected = (3.687576 + 3.721695) / 2
    assert math.isclose(r, expected, abs_tol=1e-6)


def test_rate_outside_range_holds_nearest_flat():
    """Ngoại suy PHẲNG, không tuyến tính — ngoại suy tuyến tính có thể cho lãi suất âm."""
    curve = _curve(REAL_2026_11_13)
    assert math.isclose(yc.rate_for_years(curve, 0.05) * 100, 3.687576, abs_tol=1e-6)
    assert math.isclose(yc.rate_for_years(curve, 30.0) * 100, 4.618107, abs_tol=1e-6)
    assert yc.rate_for_years(curve, 0.05) > 0


def test_invalid_years_returns_none():
    curve = _curve(REAL_2026_11_13)
    assert yc.rate_for_years(curve, 0.0) is None
    assert yc.rate_for_years(curve, -1.0) is None
    assert yc.rate_for_years(curve, float("nan")) is None


# ── chọn phiên ─────────────────────────────────────────────────────────
def test_curve_on_missing_session_returns_none_not_previous_day():
    """Không có phiên thì trả None. Lặng lẽ lấy phiên trước là che mất lỗ hổng dữ liệu."""
    curve = _curve(REAL_2026_11_13)
    assert yc.curve_on(curve, "2026-11-13") is not None
    assert yc.curve_on(curve, "2026-11-14") is None       # thứ Bảy, không có phiên


def test_risk_free_falls_back_with_explicit_label():
    curve = _curve(REAL_2026_11_13)
    rate, source = yc.risk_free_for(curve, 0.33, fallback=0.0444)
    assert rate != 0.0444 and "nội suy" in source

    rate2, source2 = yc.risk_free_for(None, 0.33, fallback=0.0444)
    assert rate2 == 0.0444
    assert "hằng số" in source2


# ── dải hợp lý ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [0.0, -3.0, 99.0, float("nan"), None])
def test_rates_outside_plausible_range_are_rejected(bad):
    assert yc._rate_to_decimal(bad) is None


def test_valid_rate_is_converted_to_decimal():
    assert math.isclose(yc._rate_to_decimal(3.787896), 0.03787896, abs_tol=1e-12)


# ── kho thật đã commit ─────────────────────────────────────────────────
def test_committed_curve_loads_and_covers_the_session_used_by_the_board():
    """Kho đã commit phải đọc được và có đúng phiên bảng giá đang dùng."""
    curve = yc.load_curve()
    if curve is None:
        pytest.skip("chưa đồng bộ data/bond_yield/yield_curve.csv")
    assert len(curve) > 30000
    day = yc.curve_on(curve, "2026-11-13")
    assert day is not None
    assert len(day) == len(yc.TENOR_YEARS)          # đủ 11 kỳ hạn
    assert (day["rate"] > 0).all()
    # Lợi suất dài hạn phải cao hơn ngắn hạn trên đường cong VN 2026 — không phải điều kiện
    # mô hình, chỉ là kiểm tra tỉnh táo rằng dữ liệu đã vào đúng cột.
    assert yc.rate_for_years(day, 10.0) > yc.rate_for_years(day, 0.25)


# ── nối vào định giá ───────────────────────────────────────────────────
def test_price_warrants_uses_per_tenor_rate_from_curve():
    """`r` phải khác nhau theo kỳ hạn từng mã, và mỗi dòng ghi nguồn của nó."""
    from cwintel.yuanta_valuation import price_warrants

    frame = pd.DataFrame([{"StockCode": "CXXX2601", "Traded": True, "LastPrice": 120.0,
                           "RefPrice": 120.0, "UnderlyingPrice": 23600.0}])
    term = pd.DataFrame([{"session": "2026-11-13", "ticker": "CXXX2601", "underlying": "XXX",
                          "strike": 26000.0, "ratio": 2.0, "maturity": "2026-12-17",
                          "underlyingPrice": 23600.0, "crosscheckPct": 0.0,
                          "termsSource": "test"}])
    curve = _curve(REAL_2026_11_13)
    priced, diag = price_warrants(frame, term, session="2026-11-13", yield_curve=curve)
    assert len(priced) == 1
    row = priced.iloc[0]
    assert diag["riskFreeByTenor"] is True
    # 34 ngày → gần 3M, phải gần 3,6876% chứ không phải hằng số 4,44%
    assert row["riskFree"] < 0.038
    assert "nội suy" in row["riskFreeSource"]
    assert diag["yieldCurve"]["available"] is True
