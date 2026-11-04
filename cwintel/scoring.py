"""Scoring engine 0–100, minh bạch và tái lập được.

Mỗi thành phần trả về điểm 0–100 và **độ tin cậy** (confidence) dựa trên tỷ lệ dữ
liệu thực sự có. Total score là trung bình có trọng số của các thành phần, chuẩn hoá
lại theo trọng số khả dụng — nghĩa là CW thiếu dữ liệu sẽ có confidence thấp chứ
không bị "điểm 0" oan.

Nguyên tắc chống so sánh sai: các tiêu chí mang tính *tương đối* (premium, IV/HV) được
xếp hạng percentile **trong cùng cổ phiếu cơ sở**, không so CW của FPT với CW của HPG.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config, indicators as ta


# ──────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────
def _col(d: pd.DataFrame, name: str) -> pd.Series:
    """Lấy cột, trả NaN Series nếu thiếu (để hàm chấm điểm không vỡ)."""
    if name in d.columns:
        return d[name]
    return pd.Series(np.nan, index=d.index, dtype="float64")


def _num_col(d: pd.DataFrame, name: str) -> pd.Series:
    """Cột số an toàn: luôn trả Series cùng index, kể cả khi cột thiếu/không phải số."""
    if name not in d.columns:
        return pd.Series(np.nan, index=d.index, dtype="float64")
    out = pd.to_numeric(d[name], errors="coerce")
    if not isinstance(out, pd.Series):
        out = pd.Series(np.nan, index=d.index, dtype="float64")
    return out


def _rank(df: pd.DataFrame, col: str, higher_is_better: bool = True,
          by: str | None = None) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    s = pd.to_numeric(df[col], errors="coerce")
    if by is None or by not in df.columns:
        out = s.rank(method="average", pct=True) * 100.0
    else:
        out = s.groupby(df[by], dropna=False).rank(method="average", pct=True) * 100.0
    out = out.astype("float64")
    return out if higher_is_better else (100.0 - out)


def _rank_underlying(df: pd.DataFrame, col: str, higher_is_better: bool = True) -> pd.Series:
    """Percentile của một đặc trưng cổ phiếu cơ sở, tính trên **các underlying duy nhất**.

    Nếu xếp hạng trực tiếp trên panel CW, một underlying có nhiều CW sẽ bị đếm nhiều lần
    và percentile trở nên méo. Hàm này map percentile của underlying trở lại từng CW.
    """
    if col not in df.columns or "underlying" not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    uniq = df[["underlying", col]].copy()
    uniq[col] = pd.to_numeric(uniq[col], errors="coerce")
    uniq = uniq.dropna(subset=[col]).drop_duplicates("underlying")
    if uniq.empty:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    pct = uniq.set_index("underlying")[col].rank(method="average", pct=True) * 100.0
    out = df["underlying"].map(pct).astype("float64")
    return out if higher_is_better else (100.0 - out)


def _combine(parts: list[tuple[pd.Series, float]]) -> pd.Series:
    """Trung bình có trọng số, bỏ qua NaN (tự chuẩn hoá theo trọng số khả dụng)."""
    num = pd.Series(0.0, index=parts[0][0].index, dtype="float64")
    den = pd.Series(0.0, index=parts[0][0].index, dtype="float64")
    for values, weight in parts:
        v = pd.to_numeric(values, errors="coerce")
        mask = v.notna()
        num = num.add((v.fillna(0.0) * weight).where(mask, 0.0), fill_value=0.0)
        den = den.add(pd.Series(np.where(mask, weight, 0.0), index=num.index), fill_value=0.0)
    return (num / den.replace(0, np.nan)).clip(0, 100)


def _confidence(parts: list[tuple[pd.Series, float]], index) -> pd.Series:
    den = pd.Series(0.0, index=index, dtype="float64")
    total = 0.0
    for values, weight in parts:
        v = pd.to_numeric(values, errors="coerce")
        den = den.add(pd.Series(np.where(v.notna(), weight, 0.0), index=index), fill_value=0.0)
        total += weight
    return (den / total).clip(0, 1) if total else den


def _bucket(series: pd.Series, bands: list[tuple[float, float, float]]) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    out = pd.Series(np.nan, index=s.index, dtype="float64")
    for low, high, score in bands:
        mask = s.notna() & (s >= low) & (s < high)
        out = out.mask(mask, score)
    # band cuối mở (high = inf)
    return out


def _trend_points(above_short: pd.Series, above_long: pd.Series) -> pd.Series:
    """100 nếu trên cả MA20 & MA50, 70 nếu chỉ trên MA20, 40 nếu chỉ trên MA50, 10 nếu dưới cả hai."""
    a = pd.to_numeric(above_short, errors="coerce")
    b = pd.to_numeric(above_long, errors="coerce")
    out = pd.Series(np.nan, index=a.index, dtype="float64")
    out = out.mask((a == 1) & (b == 1), 100)
    out = out.mask((a == 1) & (b == 0), 70)
    out = out.mask((a == 0) & (b == 1), 40)
    out = out.mask((a == 0) & (b == 0), 10)
    return out


# ──────────────────────────────────────────────────────────────────
# THÀNH PHẦN
# ──────────────────────────────────────────────────────────────────
def score_underlying_momentum(d: pd.DataFrame) -> tuple[pd.Series, pd.Series, dict]:
    p_ret21 = _rank_underlying(d, "u_ret21")
    p_ret63 = _rank_underlying(d, "u_ret63")
    trend = _trend_points(_col(d, "u_above_ma20"),
                          _col(d, "u_above_ma50"))
    rsi_band = _bucket(_col(d, "u_rsi14"), [
        (0, 30, 35), (30, 45, 60), (45, 65, 100), (65, 75, 70), (75, 100, 30)])
    dist_high = _rank_underlying(d, "u_dist_high60")   # gần đỉnh 60 phiên → mạnh

    parts = [(p_ret21, 0.40), (p_ret63, 0.20), (trend, 0.20),
             (rsi_band, 0.15), (dist_high, 0.05)]
    score = _combine(parts)
    conf = _confidence(parts, d.index)
    detail = {"ret21_pct": p_ret21, "ret63_pct": p_ret63, "trend": trend, "rsi": rsi_band}
    return score, conf, detail


def score_valuation(d: pd.DataFrame) -> tuple[pd.Series, pd.Series, dict]:
    """Định giá tương đối: premium, IV so với đường cong biến động cùng underlying và so với HV.

    Không dùng "upside so với BS@HV" làm tín hiệu mua vì trên thị trường CW Việt Nam
    gần như toàn bộ CW giao dịch cao hơn giá trị BS theo HV (xem docs/METHODOLOGY.md).
    """
    p_prem = _rank(d, "premium_be", higher_is_better=False, by="underlying")
    p_ivhv = _rank(d, "iv_vs_hv", higher_is_better=False, by="underlying")
    p_ivrank = _rank(d, "iv_rank", higher_is_better=False)
    p_ivresid = _rank(d, "iv_resid", higher_is_better=False, by="underlying")
    p_fv = _rank(d, "fv_smile_upside", higher_is_better=True, by="underlying")

    delta_opt = pd.to_numeric(_col(d, "delta_option"), errors="coerce")
    delta_band = pd.Series(np.nan, index=d.index, dtype="float64")
    delta_band = delta_band.mask(delta_opt.between(0.30, 0.70), 100)
    delta_band = delta_band.mask(delta_opt.between(0.15, 0.30) | delta_opt.between(0.70, 0.85), 65)
    delta_band = delta_band.mask(delta_opt.notna() & (delta_band.isna()), 25)

    parts = [(p_prem, 0.30), (p_ivresid, 0.30), (p_ivhv, 0.15), (p_fv, 0.10),
             (p_ivrank, 0.05), (delta_band, 0.10)]
    score = _combine(parts)
    conf = _confidence(parts, d.index)
    detail = {"premium_pct": p_prem, "iv_resid_pct": p_ivresid, "iv_hv_pct": p_ivhv,
              "fv_pct": p_fv, "iv_rank_pct": p_ivrank, "delta_band": delta_band}
    return score, conf, detail


def score_liquidity(d: pd.DataFrame) -> tuple[pd.Series, pd.Series, dict]:
    """Thanh khoản 0–100: độ sâu (ADV), tác động giá (Amihud), độ phủ phiên, xu hướng.

    Cơ sở thực nghiệm (docs/RESEARCH_LIQUIDITY.md): trong 7.134 quan sát 20 phiên,
    nhóm ADV20 thấp nhất có lợi nhuận trung bình −18,3% và tỷ lệ phiên thoát bị kẹt
    14,1%; nhóm ADV20 cao nhất −3,9% và 8,0%. Amihud cũng đơn điệu (−2,8% → −17,8%).
    Vì vậy trọng số dồn cho ADV và Amihud, còn "khối lượng tăng" chỉ là tín hiệu phụ.

    Nếu panel thiếu cột thanh khoản mới (dữ liệu cũ/khung test), quay lại công thức
    theo `value_med20`/`traded_ratio20` để không phá vỡ tương thích.
    """
    adv = _num_col(d, "adv20")
    if adv.notna().sum() == 0:
        log_value = np.log10(pd.to_numeric(_col(d, "value_med20"), errors="coerce").clip(lower=1.0))
        p_value = ta.percentile_rank(log_value)
        p_accel = _rank(d, "volume_accel")
        traded = (pd.to_numeric(_col(d, "traded_ratio20"), errors="coerce") * 100).clip(0, 100)
        parts = [(p_value, 0.50), (traded, 0.25), (p_accel, 0.25)]
        score = _combine(parts)
        conf = _confidence(parts, d.index)
        return score, conf, {"value_pct": p_value, "volume_accel_pct": p_accel,
                             "traded_ratio": traded}

    p_adv = np.log10(adv.clip(lower=1.0)).rank(method="average", pct=True) * 100.0
    p_amihud = _rank(d, "amihud20", higher_is_better=False)
    coverage = _num_col(d, "coverage_listing").fillna(_num_col(d, "coverage20")).clip(0, 100)
    trend = _num_col(d, "liq_trend").clip(0, 5)
    trend_band = _bucket(trend, [(0, 0.5, 20), (0.5, 0.8, 45), (0.8, 1.2, 70),
                                 (1.2, np.inf, 100)])
    impact = _num_col(d, "impact_50m_pct")
    impact_band = _bucket(impact, [(0, 0.5, 100), (0.5, 1.0, 85), (1.0, 2.0, 65),
                                   (2.0, 4.0, 40), (4.0, np.inf, 15)])
    # Không có Amihud/impact vẫn chấm được, chỉ giảm độ tin cậy.
    parts = [(p_adv, 0.35), (p_amihud, 0.20), (coverage, 0.20),
             (trend_band, 0.10), (impact_band, 0.15)]
    score = _combine(parts)
    conf = _confidence(parts, d.index)
    return score, conf, {"adv_pct": p_adv, "amihud_pct": p_amihud, "coverage": coverage,
                         "trend": trend_band, "impact": impact_band}


def score_risk_reward(d: pd.DataFrame) -> tuple[pd.Series, pd.Series, dict]:
    theta_pct = pd.to_numeric(_col(d, "theta_pct"), errors="coerce").abs()
    theta_band = _bucket(theta_pct, [
        (0, 0.30, 100), (0.30, 0.60, 80), (0.60, 1.00, 55), (1.00, 1.50, 35),
        (1.50, np.inf, 15)])
    be_dist = pd.to_numeric(_col(d, "be_distance_pct"), errors="coerce").abs()
    be_band = _bucket(be_dist, [
        (0, 5, 100), (5, 10, 80), (10, 20, 55), (20, 35, 30), (35, np.inf, 10)])
    dte = pd.to_numeric(_col(d, "days_to_maturity"), errors="coerce")
    dte_band = _bucket(dte, [
        (0, 14, 5), (14, 30, 30), (30, 60, 75), (60, 180, 100), (180, 270, 80),
        (270, np.inf, 55)])
    sigma = pd.to_numeric(_col(d, "sigma"), errors="coerce")
    sigma_pct = ta.percentile_rank(sigma)
    vol_band = 100 - (sigma_pct - 50).abs() * 1.6      # ưu tiên vùng 40–65 percentile
    vol_band = vol_band.clip(0, 100)
    eg = pd.to_numeric(_col(d, "eff_gearing"), errors="coerce")
    eg_band = _bucket(eg, [
        (0, 2, 50), (2, 5, 80), (5, 12, 100), (12, 20, 55), (20, np.inf, 20)])

    parts = [(theta_band, 0.30), (be_band, 0.25), (dte_band, 0.25),
             (vol_band, 0.10), (eg_band, 0.10)]
    score = _combine(parts)
    conf = _confidence(parts, d.index)
    return score, conf, {"theta_pct": theta_band, "breakeven": be_band, "dte": dte_band,
                         "vol": vol_band, "gearing": eg_band}


def score_technical(d: pd.DataFrame) -> tuple[pd.Series, pd.Series, dict]:
    rsi = pd.to_numeric(_col(d, "rsi14"), errors="coerce")
    rsi_band = _bucket(rsi, [
        (0, 30, 45), (30, 45, 70), (45, 65, 100), (65, 75, 55), (75, 100, 20)])
    macd_pos = _bucket(pd.to_numeric(_col(d, "macd_hist"), errors="coerce"),
                       [(-np.inf, 0, 20), (0, np.inf, 100)])
    macd_rise = _bucket(pd.to_numeric(_col(d, "macd_hist_slope"), errors="coerce"),
                        [(-np.inf, 0, 25), (0, np.inf, 100)])
    above20 = pd.to_numeric(_col(d, "above_ma20"), errors="coerce") * 100
    above50 = pd.to_numeric(_col(d, "above_ma50"), errors="coerce") * 100
    breakout = pd.to_numeric(_col(d, "breakout20"), errors="coerce") * 100

    parts = [(rsi_band, 0.30), (macd_pos, 0.20), (macd_rise, 0.10), (above20, 0.20),
             (above50, 0.10), (breakout, 0.10)]
    score = _combine(parts)
    conf = _confidence(parts, d.index)
    # Ít phiên giao dịch → không tin indicator
    sessions = pd.to_numeric(_col(d, "sessions"), errors="coerce")
    conf = conf * np.clip(sessions / config.MIN_SESSIONS_FOR_TECH, 0, 1)
    return score, conf, {"rsi": rsi_band, "macd": macd_pos, "above_ma20": above20,
                         "breakout": breakout}


def score_time_to_maturity(d: pd.DataFrame) -> tuple[pd.Series, pd.Series, dict]:
    dte = pd.to_numeric(_col(d, "days_to_maturity"), errors="coerce")
    band = _bucket(dte, [
        (0, 14, 5), (14, 21, 20), (21, 30, 40), (30, 45, 70), (45, 180, 100),
        (180, 270, 80), (270, 365, 55), (365, np.inf, 35)])
    conf = band.notna().astype(float)
    return band, conf, {"dte": band}


def data_quality_score(d: pd.DataFrame) -> pd.Series:
    """Chỉ số chất lượng dữ liệu 0–1 cho từng CW (không phải điểm đầu tư)."""
    index = d.index
    parts: list[tuple[pd.Series, float]] = []

    terms_ok = pd.to_numeric(_col(d, "terms_valid").fillna(1), errors="coerce")
    parts.append((terms_ok.fillna(0).astype(float), 0.25))

    sigma_src = _col(d, "sigma_source").astype(str).fillna("fallback")
    parts.append((sigma_src.isin(["hv252", "hv60", "hv20"]).astype(float), 0.15))

    age = pd.to_numeric(_col(d, "staleness_days").fillna(0), errors="coerce")
    parts.append(((age <= 3).astype(float).where(age.notna(), 0), 0.15))

    sessions = pd.to_numeric(_col(d, "sessions").fillna(0), errors="coerce")
    parts.append((np.clip(sessions / 60.0, 0, 1), 0.15))

    u_sessions = pd.to_numeric(_col(d, "u_sessions").fillna(0), errors="coerce")
    parts.append((np.clip(u_sessions / 120.0, 0, 1), 0.10))

    iv = pd.to_numeric(_col(d, "iv"), errors="coerce")
    parts.append((iv.notna().astype(float), 0.10))

    liq = pd.to_numeric(_col(d, "traded_ratio20"), errors="coerce")
    parts.append((liq.clip(0, 1), 0.10))

    return _combine(parts).clip(0, 1)


# ──────────────────────────────────────────────────────────────────
# TỔNG HỢP
# ──────────────────────────────────────────────────────────────────
COMPONENT_FUNCS = {
    "underlying_momentum": score_underlying_momentum,
    "valuation": score_valuation,
    "liquidity": score_liquidity,
    "risk_reward": score_risk_reward,
    "technical": score_technical,
    "time_to_maturity": score_time_to_maturity,
}


def _fail_depth(gate: dict, med_value: float, adv_value: float | None) -> bool:
    """Cổng độ sâu: ưu tiên ADV20 (đúng bản chất), lùi về trung vị giá trị/phiên."""
    try:
        adv = float(adv_value)
    except (TypeError, ValueError):
        adv = float("nan")
    if math.isfinite(adv):
        return adv < gate.get("min_adv_vnd", gate["min_median_value_vnd"])
    try:
        med = float(med_value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(med) and med < gate["min_median_value_vnd"]


def classify(score: float, liq: float, dq: float, dte: float, med_value: float,
             adv_value: float | None = None, coverage: float | None = None,
             range20: float | None = None) -> tuple[str, str]:
    """Phân loại khuyến nghị + lý do nếu bị hạ hạng bởi cổng chất lượng."""
    if score is None or not np.isfinite(score):
        return "NO_DATA", "Không đủ dữ liệu để chấm điểm"
    if dq is None or not np.isfinite(dq) or dq < config.MIN_DATA_QUALITY_FOR_REC:
        return "NO_DATA", f"Chất lượng dữ liệu quá thấp ({dq:.0%})" if dq == dq else "Thiếu dữ liệu"

    base = next(label for th, label in config.REC_THRESHOLDS if score >= th)
    notes = []

    g = config.GATES["STRONG_BUY"]
    if base == "STRONG_BUY":
        ok = True
        if liq < g["min_liquidity"]:
            ok, _ = False, notes.append("thanh khoản chưa đạt chuẩn MUA MẠNH")
        if dq < g["min_data_quality"]:
            ok, _ = False, notes.append("chất lượng dữ liệu chưa đạt chuẩn MUA MẠNH")
        if dte < g["min_days_to_maturity"]:
            ok, _ = False, notes.append("thời gian đáo hạn quá ngắn")
        if _fail_depth(g, med_value, adv_value):
            ok, _ = False, notes.append("giá trị giao dịch bình quân thấp")
        if coverage is not None and np.isfinite(coverage) and coverage < g.get("min_coverage20", 0):
            ok, _ = False, notes.append("quá nhiều phiên không giao dịch")
        if (range20 is not None and g.get("max_range20_pct") is not None
                and np.isfinite(range20) and range20 > g["max_range20_pct"]):
            ok, _ = False, notes.append("biên độ giá quá rộng, khó khớp lệnh")
        if not ok:
            base = "BUY"

    if base == "BUY":
        g = config.GATES["BUY"]
        ok = True
        if liq < g["min_liquidity"]:
            ok, _ = False, notes.append("thanh khoản thấp")
        if dq < g["min_data_quality"]:
            ok, _ = False, notes.append("dữ liệu chưa đủ tin cậy")
        if dte < g["min_days_to_maturity"]:
            ok, _ = False, notes.append("còn quá ít ngày tới đáo hạn")
        if _fail_depth(g, med_value, adv_value):
            ok, _ = False, notes.append("giá trị giao dịch bình quân thấp")
        if coverage is not None and np.isfinite(coverage) and coverage < g.get("min_coverage20", 0):
            ok, _ = False, notes.append("quá nhiều phiên không giao dịch")
        if (range20 is not None and g.get("max_range20_pct") is not None
                and np.isfinite(range20) and range20 > g["max_range20_pct"]):
            ok, _ = False, notes.append("biên độ giá quá rộng, khó khớp lệnh")
        if not ok:
            base = "HOLD"

    return base, "; ".join(notes)


def classify_frame(d: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Vector hoá `classify` cho cả mặt cắt."""
    score = _num_col(d, "score")
    liq = _num_col(d, "s_liquidity")
    dq = _num_col(d, "data_quality")
    dte = _num_col(d, "days_to_maturity")
    med = _num_col(d, "value_med20")
    adv = _num_col(d, "adv20")
    cov = _num_col(d, "coverage_listing").fillna(_num_col(d, "coverage20"))
    rng = _num_col(d, "range20")
    ivhv = _num_col(d, "iv_vs_hv")
    sessions = _num_col(d, "sessions")

    base = pd.Series("NO_DATA", index=d.index, dtype="object")
    # Áp từ ngưỡng thấp → cao để ngưỡng cao ghi đè (mask ghi đè lên giá trị cũ)
    for th, label in sorted(config.REC_THRESHOLDS, key=lambda x: x[0]):
        base = base.mask(score >= th, label)
    base = base.mask(score.isna(), "NO_DATA")

    reason = pd.Series("", index=d.index, dtype="object")

    g_strong = config.GATES["STRONG_BUY"]
    g_buy = config.GATES["BUY"]

    def _fail(g: dict) -> tuple[pd.Series, pd.Series]:
        """Trả (mask_thất_bại, mô_tả_lý_do) cho bộ cổng g."""
        has_adv = adv.notna() & (adv > 0)
        depth_fail = ((has_adv & (adv < g.get("min_adv_vnd", g["min_median_value_vnd"])))
                      | (~has_adv & (med < g["min_median_value_vnd"])))
        fails = {
            "thanh khoản chưa đạt chuẩn": liq < g["min_liquidity"],
            "chất lượng dữ liệu thấp": dq < g["min_data_quality"],
            "thời gian đáo hạn quá ngắn": dte < g["min_days_to_maturity"],
            "giá trị giao dịch bình quân thấp": depth_fail,
            "quá nhiều phiên không giao dịch": (cov.notna() & (cov < g.get("min_coverage20", 0))),
            "biên độ giá quá rộng": (
                rng.notna() & (rng > g["max_range20_pct"])
                if g.get("max_range20_pct") is not None
                else pd.Series(False, index=d.index)),
            "IV quá cao so với biến động lịch sử": (
                ivhv > g["max_iv_vs_hv_pct"] if g.get("max_iv_vs_hv_pct") is not None
                else pd.Series(False, index=d.index)),
            "lịch sử giao dịch quá ngắn": sessions < g.get("min_sessions", 0),
        }
        mask = pd.Series(False, index=d.index)
        text = pd.Series("", index=d.index, dtype="object")
        for label, m in fails.items():
            if not isinstance(m, pd.Series):
                m = pd.Series(bool(m), index=d.index, dtype=bool)
            m = m.fillna(True)
            text = text + np.where(m & (text == ""), label, np.where(m, "; " + label, ""))
            mask = mask | m
        return mask, text

    m_strong, t_strong = _fail(g_strong)
    downgrade_strong = (base == "STRONG_BUY") & m_strong
    base = base.mask(downgrade_strong, "BUY")
    reason = reason.mask(downgrade_strong, "Hạ từ MUA MẠNH do " + t_strong)

    m_buy, t_buy = _fail(g_buy)
    downgrade_buy = (base == "BUY") & m_buy
    base = base.mask(downgrade_buy, "HOLD")
    reason = reason.mask(downgrade_buy & ~downgrade_strong,
                         np.where(reason == "", "Hạ từ MUA do " + t_buy,
                                  reason + "; hạ tiếp do " + t_buy))

    # Lý do nền cho các mã không bị hạ hạng (để card luôn giải thích được)
    base_text = {
        "STRONG_BUY": "Điểm đạt ngưỡng MUA MẠNH và vượt toàn bộ cổng thanh khoản, chất lượng dữ liệu, thời hạn",
        "BUY": "Điểm đạt ngưỡng MUA và vượt cổng thanh khoản/chất lượng",
        "HOLD": "Điểm trong vùng THEO DÕI — chưa đủ hấp dẫn để hành động",
        "AVOID": "Điểm thấp — định giá và/hoặc cấu trúc rủi ro không thuận lợi",
        "HIGH_RISK": "Điểm rất thấp — rủi ro cao, không phù hợp để nắm giữ",
    }
    reason = reason.mask(reason == "", base.map(base_text).fillna(""))

    # Chất lượng dữ liệu quá thấp → không khuyến nghị hành động
    no_data = dq < config.MIN_DATA_QUALITY_FOR_REC
    base = base.mask(no_data | dq.isna(), "NO_DATA")
    reason = reason.mask(no_data | dq.isna(),
                         "Chất lượng dữ liệu dưới ngưỡng " + f"{config.MIN_DATA_QUALITY_FOR_REC:.0%}"
                         + " — không đủ tin cậy để khuyến nghị")
    return base, reason


def score_universe(d: pd.DataFrame, weights: dict | None = None) -> pd.DataFrame:
    """Chấm điểm toàn bộ universe trong một mặt cắt thời gian.

    `d` phải là snapshot 1 dòng / CW (xem `snapshot.py`).
    """
    weights = weights or config.SCORE_WEIGHTS
    out = d.copy()

    if "delta_option" not in out.columns and {"delta", "ratio"}.issubset(out.columns):
        out["delta_option"] = pd.to_numeric(out["delta"], errors="coerce") * pd.to_numeric(
            out["ratio"], errors="coerce")

    components, details = {}, {}
    for name, func in COMPONENT_FUNCS.items():
        score, conf, detail = func(out)
        out[f"s_{name}"] = score.round(2)
        out[f"c_{name}"] = conf.round(3)
        components[name] = (out[f"s_{name}"], out[f"c_{name}"], weights.get(name, 0.0))
        details[name] = detail

    num = pd.Series(0.0, index=out.index)
    den = pd.Series(0.0, index=out.index)
    for name, (s, c, w) in components.items():
        valid = s.notna() & c.notna() & (c > 0)
        num = num.add((s.fillna(0) * c.fillna(0) * w).where(valid, 0.0), fill_value=0.0)
        den = den.add(pd.Series(np.where(valid, c * w, 0.0), index=out.index), fill_value=0.0)
    out["score"] = (num / den.replace(0, np.nan)).clip(0, 100).round(1)

    # Premium trung vị của các CW cùng underlying — dùng cho phần giải thích
    if {"underlying", "premium_be"}.issubset(out.columns):
        out["peer_premium_median"] = (
            pd.to_numeric(out["premium_be"], errors="coerce")
            .groupby(out["underlying"], dropna=False).transform("median").round(2)
        )

    out["data_quality"] = data_quality_score(out).round(3)

    out["recommendation"], out["rec_reason"] = classify_frame(out)

    # Lưu detail percentile để giải thích (dùng cho factor text)
    for name, det in details.items():
        for key, series in det.items():
            out[f"x_{name}_{key}"] = pd.to_numeric(series, errors="coerce").round(1)

    return out
