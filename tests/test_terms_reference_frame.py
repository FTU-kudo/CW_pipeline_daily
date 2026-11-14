"""Điều khoản CW phải ở CÙNG hệ quy chiếu với giá cổ phiếu cơ sở.

Bối cảnh: Vietstock trả `gia_thuc_hien`/`ty_le_chuyen_doi` ở hệ **chưa điều chỉnh**, cùng một
giá cổ phiếu cơ sở cũng chưa điều chỉnh (ẩn trong premium/đòn bẩy). Ghép cặp đó với giá đóng
cửa thật là trộn hai hệ: CW bị coi là OTM sâu, giá lý thuyết về ~0, IV nổ tung (TCB 101%,
HDB 167%, VHM 219%), và 100 mã bị loại oan.

Các test dưới đây khoá lại hành vi đúng, với CACB2515 làm chuẩn đối chiếu vì có trang chi
tiết của nguồn xác nhận: K 31.800 → 27.420, n 2 → 1,7245, f = 1,15976.
"""

# ── quy điều khoản về cùng hệ quy chiếu với giá cổ phiếu ──────────────────
def test_resolve_terms_uses_source_adjustment_when_present():
    """Nguồn đã trả `gia_th_dieu_chinh`/`tlcd_dieu_chinh` → dùng thẳng, ưu tiên cao nhất."""
    from cwintel.yuanta_valuation import resolve_terms

    out = resolve_terms(strike=31800.0, ratio=2.0, maturity="2027-03-04",
                        strike_adj=27420.0, ratio_adj=1.7245,
                        maturity_adj="2027-03-08",
                        derived_s=23601.0, real_s=20350.0)
    assert out["strike"] == 27420.0
    assert out["ratio"] == 1.7245
    assert out["maturity"] == "2027-03-08"
    assert out["basis"] == "điều chỉnh từ nguồn"


def test_resolve_terms_rescales_to_match_cacb2515_detail_page():
    """Dựng lại từ chênh lệch giá phải cho đúng số trên trang Vietstock.

    Trang chi tiết CACB2515 ghi: Giá thực hiện 31.800 · Giá TH điều chỉnh 27.420 ·
    Tỷ lệ 2:1 · TLCĐ điều chỉnh 1,7245:1. f = 23601/20350 = 1,15976.
    """
    from cwintel.yuanta_valuation import resolve_terms

    out = resolve_terms(strike=31800.0, ratio=2.0, maturity="2027-03-04",
                        strike_adj=None, ratio_adj=None, maturity_adj=None,
                        derived_s=23601.0, real_s=20350.0)
    assert out["basis"] == "dựng lại từ chênh lệch giá"
    assert abs(out["strike"] - 27420.0) < 25.0        # 27.419,6
    assert abs(out["ratio"] - 1.7245) < 0.002


def test_resolve_terms_keeps_raw_terms_when_no_drift():
    """Lệch trong phạm vi làm tròn của nguồn → giữ nguyên, không thêm nhiễu."""
    from cwintel.yuanta_valuation import resolve_terms

    out = resolve_terms(strike=26000.0, ratio=2.0, maturity="2026-12-17",
                        strike_adj=None, ratio_adj=None, maturity_adj=None,
                        derived_s=26000.5, real_s=26000.0)
    assert out["basis"] == "gốc, chưa điều chỉnh"
    assert out["strike"] == 26000.0


def test_resolve_terms_refuses_factor_outside_confidence_range():
    """Hệ số vô lý (giá nguồn cũ quá xa) → không dựng lại, giữ gốc để chốt chặn loại sau."""
    from cwintel.yuanta_valuation import resolve_terms

    out = resolve_terms(strike=26000.0, ratio=2.0, maturity="2026-12-17",
                        strike_adj=None, ratio_adj=None, maturity_adj=None,
                        derived_s=236000.0, real_s=20350.0)   # f ≈ 11.6
    assert out["basis"] == "gốc, chưa điều chỉnh"
    assert out["strike"] == 26000.0


def test_iv_is_invariant_under_reference_frame():
    """IV không phụ thuộc hệ quy chiếu; delta thì có (lệch đúng hệ số f).

    Đây là lý do dựng lại điều khoản an toàn cho IV nhưng bắt buộc cho Greeks.
    """
    from cwintel.bs import implied_vol, price_and_greeks

    T, r, cw = 115 / 365, 0.0444, 150.0
    K_a, n_a, S_a = 27420.0, 1.7245, 20350.0      # hệ điều chỉnh (thật)
    f = 31800.0 / 27420.0
    K_r, n_r, S_r = 31800.0, 2.0, S_a * f         # hệ gốc

    iv_a, _ = implied_vol(market_price=cw, S=S_a, K=K_a, T=T, r=r, ratio=n_a, kind="call")
    iv_r, _ = implied_vol(market_price=cw, S=S_r, K=K_r, T=T, r=r, ratio=n_r, kind="call")
    assert abs(iv_a - iv_r) < 1e-5

    g_a = price_and_greeks(S=S_a, K=K_a, T=T, r=r, sigma=iv_a, ratio=n_a, kind="call")
    g_r = price_and_greeks(S=S_r, K=K_r, T=T, r=r, sigma=iv_r, ratio=n_r, kind="call")
    assert abs(g_a.price - g_r.price) < 0.01      # giá CW bất biến
    assert abs(g_a.delta / g_r.delta - f) < 1e-3  # delta lệch đúng f
