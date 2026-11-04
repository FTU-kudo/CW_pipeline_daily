"""Investment Recommendation Card: giải thích, cảnh báo và kế hoạch giao dịch.

Mọi con số trong card đều lấy từ dữ liệu thật của snapshot; chỗ nào thiếu dữ liệu
thì trả về `None` + lý do, tuyệt đối không tạo giá mục tiêu tuỳ ý.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config, liquidity as liqmod
from .bs import price_and_greeks


# ──────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────
def _f(v, nd=2):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


def _adv(row: pd.Series) -> float:
    """ADV20 nếu có, nếu không lùi về trung vị giá trị giao dịch 20 phiên."""
    v = row.get("adv20", np.nan)
    if v is None or not pd.notna(v):
        v = row.get("value_med20", np.nan)
    return float(v) if pd.notna(v) else float("nan")


def _tick_round(price: float, tick: float = 10.0) -> float:
    return max(tick, round(price / tick) * tick)


def risk_level(row: pd.Series) -> str:
    dte = row.get("days_to_maturity", np.nan)
    liq = _adv(row)
    theta = abs(row.get("theta_pct", np.nan)) if pd.notna(row.get("theta_pct", np.nan)) else np.nan
    premium = row.get("premium_be", np.nan)
    iv_hv = row.get("iv_vs_hv", np.nan)

    points = 0
    if pd.notna(dte):
        points += 2 if dte < 21 else 1 if dte < 45 else 0
    if pd.notna(liq):
        points += 2 if liq < 10_000_000 else 1 if liq < 50_000_000 else 0
    if pd.notna(theta):
        points += 2 if theta > 1.5 else 1 if theta > 0.8 else 0
    if pd.notna(premium):
        points += 1 if premium > 25 else 0
    if pd.notna(iv_hv):
        points += 1 if iv_hv > 50 else 0
    if points >= 5:
        return "Cao"
    if points >= 3:
        return "Trung bình - cao"
    if points >= 1:
        return "Trung bình"
    return "Thấp"


# ──────────────────────────────────────────────────────────────────
# FACTORS
# ──────────────────────────────────────────────────────────────────
def positive_factors(row: pd.Series) -> list[str]:
    out: list[str] = []
    u = str(row.get("underlying", ""))
    score = row.get("score", np.nan)

    s_mom = row.get("s_underlying_momentum", np.nan)
    if pd.notna(s_mom) and s_mom >= 65:
        ret21 = _f(row.get("u_ret21"), 1)
        ret63 = _f(row.get("u_ret63"), 1)
        trend = "trên" if row.get("u_above_ma50") == 1 else "dưới"
        if ret21 is not None and ret63 is not None:
            out.append(
                f"{u} xếp thứ {s_mom:.0f}/100 về động lượng so với các cổ phiếu cơ sở khác: "
                f"return 21 phiên {ret21:+.1f}%, 63 phiên {ret63:+.1f}%, giá {trend} MA50.")
        else:
            out.append(f"{u} đang trong xu hướng tăng so với mặt bằng chung.")

    resid = _f(row.get("iv_resid"), 1)
    prem_pct = row.get("x_valuation_premium_pct", np.nan)
    if resid is not None and resid <= -10:
        out.append(f"IV thấp hơn đường cong biến động của các CW cùng {u} {abs(resid):.0f}% "
                   f"→ CW đang rẻ tương đối so với nhóm cùng cơ sở.")
    if pd.notna(prem_pct) and prem_pct >= 70:
        prem = _f(row.get("premium_be"), 1)
        peer = _f(row.get("peer_premium_median"), 1)
        if prem is not None and peer is not None:
            out.append(f"Premium hoà vốn {prem:.1f}% thấp hơn trung vị nhóm {u} ({peer:.1f}%).")

    liq = _adv(row)
    cov = _f(row.get("coverage20"), 0)
    if pd.notna(liq) and liq >= config.HIGH_LIQUIDITY_VALUE_VND:
        out.append(f"Thanh khoản cao: ADV20 {liq/1e6:.0f} triệu VND/phiên"
                   + (f", giao dịch {cov:.0f}% số phiên." if cov is not None else "."))
    elif pd.notna(liq) and liq >= config.MEDIUM_LIQUIDITY_VALUE_VND:
        accel = _f(row.get("liq_trend"), 2)
        if accel is not None and accel > 1.2:
            out.append(f"Thanh khoản cải thiện: ADV5 gấp {accel:.1f}× ADV20 "
                       f"({liq/1e6:.0f} triệu VND/phiên).")
    dtl = _f(row.get("dtl_50m"), 1)
    if dtl is not None and dtl <= 1.0:
        out.append(f"Đủ thanh khoản để thoát vị thế 50 triệu VND trong ~{dtl:.1f} phiên "
                   f"(giả định tham gia 20% ADV).")

    theta = _f(row.get("theta_pct"), 2)
    if theta is not None and abs(theta) <= 0.4:
        out.append(f"Tốc độ mất giá theo thời gian thấp ({abs(theta):.2f}%/ngày).")

    sessions = _f(row.get("sessions"), 0) or 0
    s_tech = row.get("s_technical", np.nan)
    if pd.notna(s_tech) and s_tech >= 65 and sessions >= 30:
        rsi = _f(row.get("rsi14"), 0)
        above = row.get("above_ma20") == 1
        out.append(f"Kỹ thuật CW tích cực: RSI(14) {rsi:.0f}, giá "
                   f"{'trên' if above else 'dưới'} MA20.")
    if bool(row.get("breakout20")) and pd.notna(row.get("breakout20")):
        out.append("Giá CW vượt đỉnh 20 phiên (breakout) với dữ liệu khối lượng xác nhận.")

    dte = row.get("days_to_maturity", np.nan)
    if pd.notna(dte) and 45 <= dte <= 180:
        out.append(f"Thời gian đáo hạn hợp lý ({int(dte)} ngày) — đủ để luận điểm đầu tư "
                   f"phát huy mà không bị theta bào mòn quá nhanh.")

    if score is not None and pd.notna(score) and pd.notna(s_mom) and s_mom >= 80 and row.get("recommendation") in ("BUY", "STRONG_BUY"):
        out.append("Điểm tổng hợp thuộc nhóm dẫn đầu vũ trụ CW hiện tại.")
    return out[:6]


def negative_factors(row: pd.Series) -> list[str]:
    out: list[str] = []
    u = str(row.get("underlying", ""))

    s_mom = row.get("s_underlying_momentum", np.nan)
    if pd.notna(s_mom) and s_mom <= 40:
        ret21 = _f(row.get("u_ret21"), 1)
        if ret21 is not None:
            out.append(f"{u} đang yếu: return 21 phiên {ret21:+.1f}%, giá dưới MA20/MA50.")
        else:
            out.append(f"Xu hướng {u} chưa ủng hộ vị thế mua CW.")

    theta = _f(row.get("theta_pct"), 2)
    if theta is not None and abs(theta) >= 0.8:
        out.append(f"Theta decay cao: mất {abs(theta):.2f}% giá trị CW mỗi ngày nếu mọi yếu tố khác không đổi.")

    dte = row.get("days_to_maturity", np.nan)
    if pd.notna(dte) and dte < 45:
        out.append(f"Chỉ còn {int(dte)} ngày tới đáo hạn — rủi ro thời gian rất lớn.")

    prem = _f(row.get("premium_be"), 1)
    if prem is not None and prem > 20:
        out.append(f"Premium hoà vốn cao ({prem:.1f}%): cổ phiếu cơ sở phải tăng thêm "
                   f"{prem:.1f}% mới hoà vốn tại ngày đáo hạn.")

    resid = _f(row.get("iv_resid"), 1)
    if resid is not None and resid >= 15:
        out.append(f"IV cao hơn đường cong cùng {u} {resid:.0f}% → đang trả giá cao cho biến động.")

    liq = _adv(row)
    if pd.notna(liq) and liq < config.MEDIUM_LIQUIDITY_VALUE_VND:
        out.append(f"Thanh khoản thấp: ADV20 chỉ {liq/1e6:.1f} triệu VND/phiên.")
    for msg in liqmod.liquidity_flags(row)[:3]:
        if msg not in out:
            out.append(msg)

    sessions = _f(row.get("sessions"), 0) or 0
    rsi = _f(row.get("rsi14"), 0)
    if rsi is not None and rsi >= 75 and sessions >= 30:
        out.append(f"RSI(14) của CW ở mức {rsi:.0f} — vùng quá mua, rủi ro điều chỉnh ngắn hạn.")
    if sessions < 15:
        out.append(f"CW mới niêm yết ({int(sessions)} phiên giao dịch) — chưa đủ lịch sử để "
                   f"đánh giá chỉ báo kỹ thuật và thanh khoản ổn định.")
    return out[:6]


def risk_warnings(row: pd.Series) -> list[str]:
    out: list[str] = []
    dte = row.get("days_to_maturity", np.nan)
    if pd.notna(dte) and dte < 30:
        out.append(f"RỦI RO ĐÁO HẠN: còn {int(dte)} ngày. Nếu CW hết hạn OTM, toàn bộ vốn có thể mất.")
    iv_hv = row.get("iv_vs_hv", np.nan)
    if pd.notna(iv_hv) and iv_hv > 50:
        out.append(f"IV cao hơn biến động lịch sử {iv_hv:.0f}% — giá CW đã phản ánh kỳ vọng biến động lớn, "
                   f"dễ giảm nếu IV hạ nhiệt.")
    for msg in liqmod.liquidity_flags(row):
        if msg not in out:
            out.append(msg)
    if pd.notna(row.get("delta_option")) and row.get("delta_option") > 0.9:
        out.append("Delta gần 1 (ITM sâu): CW gần như cổ phiếu, đòn bẩy thấp và thường kém thanh khoản.")
    if pd.notna(row.get("delta_option")) and row.get("delta_option") < 0.10:
        out.append("Delta rất thấp (< 0,10): phần lớn giá trị là thời gian, xác suất ITM thấp.")
    if pd.notna(row.get("close")) and row.get("close") <= 50:
        out.append("Giá CW sát bước giá tối thiểu — biến động % lớn do làm tròn tick, IV suy ra kém tin cậy.")
    share = row.get("issuer_value_share", np.nan)
    if pd.notna(share) and share > 0.35:
        out.append(f"Tập trung nhà phát hành: {row.get('issuer_name') or row.get('issuer')} chiếm "
                   f"{share:.0%} giá trị giao dịch vũ trụ CW — rủi ro tổ chức phát hành khi nắm nhiều mã.")
    if pd.notna(row.get("u_hv20")) and pd.notna(row.get("u_hv252")) and row.get("u_hv20") > 1.4 * row.get("u_hv252"):
        out.append("Biến động 20 phiên của cổ phiếu cơ sở đang cao hơn nhiều mức 1 năm — định giá CW nhạy cảm.")
    if (_f(row.get("sessions"), 0) or 0) < 15:
        out.append("Lịch sử giao dịch ngắn (< 15 phiên): ATR, RSI và thanh khoản chưa đại diện.")
    if row.get("data_quality") is not None and pd.notna(row.get("data_quality")) and row.get("data_quality") < 0.7:
        out.append(f"Chất lượng dữ liệu chỉ đạt {row.get('data_quality'):.0%} (thiếu lịch sử/điều khoản) — "
                   f"các chỉ số có thể kém chính xác.")
    if row.get("moneyness") == "OTM" and pd.notna(row.get("moneyness_pct")) and row.get("moneyness_pct") < -20:
        out.append(f"CW đang OTM {abs(row.get('moneyness_pct')):.0f}% — cần cổ phiếu tăng mạnh mới có giá trị nội tại.")
    return out


def invalidation_conditions(row: pd.Series) -> list[str]:
    out: list[str] = []
    ma50 = _f(row.get("u_ma50"), 0)
    if ma50:
        out.append(f"{row.get('underlying')} đóng cửa dưới MA50 ({ma50:,.0f} VND) trong 2 phiên liên tiếp.")
    out.append("Điểm CW Score giảm xuống dưới 45 hoặc bị hạ khuyến nghị.")
    out.append("Thời gian còn lại tới đáo hạn dưới 21 ngày.")
    iv = _f(row.get("iv"), 2)
    if iv:
        out.append(f"IV tăng vượt {iv*1.4:.2f} ({iv*1.4*100:.0f}%) — CW trở nên quá đắt so với chính nó.")
    if pd.notna(_adv(row)):
        out.append("ADV20 giảm dưới 5 triệu VND/phiên hoặc độ phủ giao dịch xuống dưới 50% "
                   "số phiên (mất khả năng thoát hàng).")
    return out[:5]


# ──────────────────────────────────────────────────────────────────
# TRADING PLAN
# ──────────────────────────────────────────────────────────────────
def trading_plan(row: pd.Series, r: float) -> dict:
    """Kế hoạch giao dịch suy ra từ ATR và mô phỏng BS — không phải dự báo.

    * Vùng vào lệnh: quanh giá hiện tại ± 0,5 ATR(14).
    * Stop-loss tham chiếu: giá − 2 ATR(14).
    * Take-profit: giá CW mô phỏng khi cổ phiếu cơ sở +5% / +10% sau 10 / 20 phiên,
      dùng sigma = HV hiện tại và thời gian còn lại đã trừ đi thời gian nắm giữ.
    """
    price = row.get("close", np.nan)
    atr = row.get("atr14", np.nan)
    atr_source = "atr14"
    if not (pd.notna(atr) and float(atr) > 0) and pd.notna(price) and float(price) > 0:
        ret_std = row.get("ret_std20", np.nan)
        if pd.notna(ret_std) and float(ret_std) > 0:
            atr = float(price) * float(ret_std)
            atr_source = "ret_std20"
    dte = row.get("days_to_maturity", np.nan)
    S = row.get("u_close", np.nan)
    K = row.get("K", np.nan)
    ratio = row.get("ratio", np.nan)
    T = row.get("T", np.nan)
    sigma = row.get("sigma", np.nan)

    if not all(pd.notna(v) and float(v) > 0 for v in [price, atr, dte, S, K, ratio, T, sigma]):
        return {"available": False, "reason": "Chưa đủ dữ liệu (giá/ATR/điều khoản) để lập kế hoạch."}
    if dte < 21:
        return {"available": False,
                "reason": f"Chỉ còn {int(dte)} ngày tới đáo hạn — không đủ thời gian cho một vị thế có quản trị rủi ro."}

    holding = int(min(60, max(5, dte - 15)))
    entry_low = _tick_round(max(price - 0.5 * atr, price * 0.90))
    entry_high = _tick_round(price + 0.25 * atr)
    stop = _tick_round(max(price - 2.0 * atr, 10.0))

    scenarios = []
    for move, hold in ((0.05, min(10, holding)), (0.10, min(20, holding))):
        t_left = max(T - hold / config.DAYS_PER_YEAR, 1e-6)
        est = price_and_greeks(S * (1 + move), K, t_left, r, sigma, ratio, "call").price
        est = float(est) if est and est > 0 else None
        scenarios.append({
            "underlying_move_pct": move * 100,
            "holding_sessions": hold,
            "estimated_price": _f(est, 1),
            "estimated_pl_pct": _f((est / price - 1) * 100, 1) if est else None,
        })

    return {
        "available": True,
        "atr_source": atr_source,
        "atr_value": _f(atr, 2),
        "entry_zone": [entry_low, entry_high],
        "stop_loss": stop,
        "stop_loss_pct": _f((stop / price - 1) * 100, 1),
        "take_profit": scenarios,
        "expected_holding_days": holding,
        "rationale": ("Vùng vào lệnh ±0,5 ATR(14); stop −2 ATR(14); take-profit là giá CW "
                      "mô phỏng theo Black‑Scholes khi cổ phiếu cơ sở tăng 5%/10% và thời gian "
                      "trôi tương ứng. Đây là kịch bản giả định, không phải giá mục tiêu cam kết."),
        "risk_reward": _f((scenarios[0]["estimated_price"] - price) / max(price - stop, 1e-9), 2)
        if scenarios[0]["estimated_price"] else None,
    }


# ──────────────────────────────────────────────────────────────────
# CARD
# ──────────────────────────────────────────────────────────────────
def build_card(row: pd.Series, r: float) -> dict:
    rec = row.get("recommendation", "NO_DATA")
    positives = positive_factors(row)
    negatives = negative_factors(row)
    warnings = risk_warnings(row)

    thesis = []
    if positives:
        thesis.append(positives[0])
    if negatives:
        thesis.append(negatives[0])
    if not thesis:
        thesis.append("Không có yếu tố nổi bật; CW ở trạng thái trung tính.")

    return {
        "ticker": row.get("ticker"),
        "underlying": row.get("underlying"),
        "issuer": row.get("issuer"),
        "issuer_name": row.get("issuer_name"),
        "recommendation": rec,
        "recommendation_vi": config.REC_LABELS_VI.get(rec, rec),
        "score": _f(row.get("score"), 1),
        "data_quality": _f(row.get("data_quality"), 3),
        "risk_level": risk_level(row),
        "rec_reason": row.get("rec_reason") or "",
        "components": {
            k: _f(row.get(f"s_{k}"), 1) for k in config.SCORE_WEIGHTS
        },
        "component_confidence": {k: _f(row.get(f"c_{k}"), 2) for k in config.SCORE_WEIGHTS},
        "metrics": {
            "price": _f(row.get("close"), 1),
            "fair_value_smile": _f(row.get("fv_smile"), 1),
            "fair_value_hv": _f(row.get("bs_fv"), 1),
            "upside_smile_pct": _f(row.get("fv_smile_upside"), 1),
            "premium_be_pct": _f(row.get("premium_be"), 1),
            "breakeven": _f(row.get("breakeven"), 0),
            "days_to_maturity": int(row["days_to_maturity"]) if pd.notna(row.get("days_to_maturity")) else None,
            "delta": _f(row.get("delta"), 4),
            "delta_option": _f(row.get("delta_option"), 3),
            "theta": _f(row.get("theta"), 3),
            "theta_pct": _f(row.get("theta_pct"), 2),
            "vega": _f(row.get("vega"), 2),
            "eff_gearing": _f(row.get("eff_gearing"), 2),
            "iv": _f(row.get("iv"), 3),
            "hv252": _f(row.get("sigma"), 3),
            "iv_vs_hv_pct": _f(row.get("iv_vs_hv"), 1),
            "iv_resid_pct": _f(row.get("iv_resid"), 1),
            "value_med20": _f(row.get("value_med20"), 0),
            "adv20": _f(row.get("adv20"), 0),
            "adv5": _f(row.get("adv5"), 0),
            "coverage20": _f(row.get("coverage20"), 1),
            "zero20": _f(row.get("zero20"), 0),
            "amihud20": _f(row.get("amihud20"), 2),
            "range20": _f(row.get("range20"), 2),
            "turnover20": _f(row.get("turnover20"), 2),
            "dtl_50m": _f(row.get("dtl_50m"), 1),
            "impact_50m_pct": _f(row.get("impact_50m_pct"), 2),
            "liquidity_bucket": liqmod.liquidity_bucket(row),
            "moneyness": row.get("moneyness"),
            "liquidity_score": _f(row.get("s_liquidity"), 1),
        },
        "thesis": thesis,
        "positive_factors": positives,
        "negative_factors": negatives,
        "risk_warnings": warnings,
        "invalidation": invalidation_conditions(row),
        "trading_plan": trading_plan(row, r),
        "disclaimer": ("Khuyến nghị do mô hình định lượng tạo ra từ dữ liệu công khai, "
                       "không phải lời khuyên đầu tư. Giá trị lý thuyết không phải giá có thể "
                       "giao dịch chắc chắn."),
    }


def build_cards(snapshot: pd.DataFrame, r: float, only_actionable: bool = False) -> list[dict]:
    if snapshot.empty:
        return []
    df = snapshot
    if only_actionable:
        df = df[df["recommendation"].isin(["STRONG_BUY", "BUY", "HOLD", "AVOID"])]
    return [build_card(row, r) for _, row in df.iterrows()]
