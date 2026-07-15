"""
bs_calculator.py
────────────────
Tự tính Black-Scholes cho Chứng quyền (CW) Việt Nam.

Inputs (đều đã có trong pipeline):
  - OHLCV underlying  → sigma (historical volatility, annualized, 252 phiên)
  - OHLCV underlying  → S (giá đóng cửa mới nhất, VND)
  - data_fetcher.py   → r (lợi suất TPCP 10Y HNX, %/năm)  ← lãi suất phi rủi ro chuẩn BS
  - df_vietstock      → K (giá thực hiện), T (ngày đến hạn), n (tỷ lệ chuyển đổi)

Công thức:
  d1  = [ln(S/K) + (r + σ²/2)·T] / (σ·√T)
  d2  = d1 - σ·√T
  C   = S·N(d1) - K·e^(-rT)·N(d2)          # Giá Call trên 1 CP cơ sở
  CW  = C / n                                # Quy về 1 CW (chia tỷ lệ chuyển đổi)
  Δ   = N(d1)                                # Delta
  EG  = (S / (CW_price × n)) × Δ            # Effective Gearing (leverage thực tế)

Lưu ý về r:
  Dùng lợi suất TPCP **kỳ hạn 10 năm** (10Y HNX) theo đúng chuẩn định giá
  quyền chọn quốc tế (cùng cách Vietstock áp dụng). KHÔNG dùng 1Y.
"""

import math
import numpy as np
import pandas as pd
from datetime import date, datetime
from typing import Optional

# ── Fallback khi không fetch được HNX ────────────────────────────
_FALLBACK_RATE_10Y = 4.53   # % — lợi suất 10Y HNX thực tế gần nhất


# ══════════════════════════════════════════════════════════════════
# 1. LÃI SUẤT PHI RỦI RO — HNX 10Y
# ══════════════════════════════════════════════════════════════════

def get_risk_free_rate(as_of_date: Optional[str] = None) -> float:
    """
    Lấy lợi suất TPCP kỳ hạn 10 năm (10Y HNX) làm lãi suất phi rủi ro cho BS.
    Ưu tiên: HNX yield curve cache (data_fetcher) → Trading Economics scrape → fallback cứng.

    Returns:
        float: lãi suất dạng thập phân (vd: 0.0453 cho 4.53%)
    """
    target = as_of_date or date.today().strftime("%Y-%m-%d")

    # Lớp 1: Dùng cache HNX đã có (data_fetcher.fetch_hnx_official_yields)
    try:
        from data_fetcher import fetch_hnx_official_yields
        # Chỉ lấy 5 ngày gần nhất để nhanh, dùng ffill nếu HNX đóng cửa
        start = (pd.to_datetime(target) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        df_hnx = fetch_hnx_official_yields(start, target)
        if not df_hnx.empty and "10Y" in df_hnx.columns:
            val = float(df_hnx["10Y"].iloc[-1])
            if 1.0 <= val <= 15.0:
                print(f"   r (10Y HNX, {df_hnx.index[-1].date()}): {val:.3f}%")
                return val / 100
    except Exception as e:
        print(f"   WARN HNX rate: {e}")

    # Lớp 2: Trading Economics scrape (curl_cffi)
    try:
        from data_fetcher import scrape_trading_economics_10y
        val = scrape_trading_economics_10y()
        if 1.0 <= val <= 15.0:
            print(f"   r (10Y Trading Economics): {val:.3f}%")
            return val / 100
    except Exception as e:
        print(f"   WARN TE scrape: {e}")

    # Lớp 3: Fallback cứng
    print(f"   r (fallback hardcoded): {_FALLBACK_RATE_10Y:.3f}%")
    return _FALLBACK_RATE_10Y / 100


# ══════════════════════════════════════════════════════════════════
# 2. SIGMA — HISTORICAL VOLATILITY TỪ OHLCV UNDERLYING
# ══════════════════════════════════════════════════════════════════

def calc_sigma(ohlcv_underlying: pd.DataFrame,
               window: int = 252,
               as_of_date: Optional[str] = None) -> float:
    """
    Tính Annualized Sigma (σ) từ log-return giá đóng cửa của CK cơ sở.
    Dùng đúng 252 phiên giao dịch gần nhất (chuẩn Vietstock/Bloomberg).

    Args:
        ohlcv_underlying: DataFrame có cột 'close' và index là datetime (hoặc cột 'time')
        window: số phiên để tính volatility (mặc định 252 = 1 năm GD)
        as_of_date: tính sigma tại ngày này (None = ngày cuối cùng trong data)

    Returns:
        float: sigma annualized (vd: 0.3954)
    """
    df = ohlcv_underlying.copy()

    # Chuẩn hóa index về datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        time_col = next((c for c in ["time", "date", "Date"] if c in df.columns), None)
        if time_col:
            df[time_col] = pd.to_datetime(df[time_col], dayfirst=True, errors="coerce")
            df = df.set_index(time_col)
        else:
            raise ValueError("ohlcv_underlying cần có index datetime hoặc cột 'time'/'date'")

    df = df.sort_index()

    # Chuẩn hóa cột close về VND (vnstock trả về nghìn đồng nếu < 1000)
    close = df["close"].dropna().copy()
    if close.median() < 1000:
        close = close * 1000

    if as_of_date:
        close = close[close.index <= pd.to_datetime(as_of_date)]

    if len(close) < 20:
        raise ValueError(f"Không đủ dữ liệu để tính sigma (chỉ có {len(close)} phiên)")

    # Dùng tối đa `window` phiên gần nhất
    close = close.iloc[-window:]
    log_returns = np.log(close / close.shift(1)).dropna()
    sigma = float(log_returns.std() * math.sqrt(252))

    print(f"   σ ({len(log_returns)} phiên): {sigma:.4f} ({sigma*100:.2f}%/năm)")
    return round(sigma, 4)


def calc_sigma_series(ohlcv_underlying: pd.DataFrame,
                      window: int = 252) -> pd.Series:
    """
    Tính chuỗi sigma rolling theo ngày — dùng cho backtesting / chart lịch sử.
    Returns: pd.Series với index=date, value=sigma annualized mỗi ngày.
    """
    df = ohlcv_underlying.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        time_col = next((c for c in ["time", "date"] if c in df.columns), None)
        if time_col:
            df = df.set_index(pd.to_datetime(df[time_col], dayfirst=True, errors="coerce"))
    df = df.sort_index()

    close = df["close"].dropna()
    if close.median() < 1000:
        close = close * 1000

    log_ret = np.log(close / close.shift(1))
    sigma_series = log_ret.rolling(window=window, min_periods=20).std() * math.sqrt(252)
    return sigma_series.round(4)


# ══════════════════════════════════════════════════════════════════
# 3. BLACK-SCHOLES CORE
# ══════════════════════════════════════════════════════════════════

def _norm_cdf(x: float) -> float:
    """CDF phân phối chuẩn N(0,1) — dùng math.erf để tránh phụ thuộc scipy."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S: float, K: float, T: float, r: float, sigma: float) -> dict:
    """
    Tính giá Call theo Black-Scholes và các Greeks cơ bản.

    Args:
        S     : Giá hiện tại CK cơ sở (VND)
        K     : Giá thực hiện (VND)
        T     : Thời gian đến hạn (năm, vd: 103/365)
        r     : Lãi suất phi rủi ro thập phân (10Y HNX, vd: 0.045)
        sigma : Volatility annualized (vd: 0.3954)

    Returns:
        dict với keys: price, delta, gamma, theta, vega, d1, d2
    """
    if T <= 0:
        # Đã hết hạn: giá trị nội tại thuần túy
        intrinsic = max(S - K, 0.0)
        return {
            "price": round(intrinsic, 2),
            "delta": 1.0 if S > K else 0.0,
            "gamma": 0.0, "theta": 0.0, "vega": 0.0,
            "d1": float("inf"), "d2": float("inf"),
        }

    if sigma <= 0 or S <= 0 or K <= 0:
        return {"price": 0.0, "delta": 0.0, "gamma": 0.0,
                "theta": 0.0, "vega": 0.0, "d1": 0.0, "d2": 0.0}

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    Nd1  = _norm_cdf(d1)
    Nd2  = _norm_cdf(d2)
    nd1  = math.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)   # PDF tại d1
    disc = math.exp(-r * T)

    price = S * Nd1 - K * disc * Nd2

    # Greeks
    delta = Nd1
    gamma = nd1 / (S * sigma * sqrt_T)
    theta = (-(S * nd1 * sigma) / (2 * sqrt_T) - r * K * disc * Nd2) / 365  # per day
    vega  = S * nd1 * sqrt_T / 100   # per 1% change in sigma

    return {
        "price": round(price, 2),
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta, 2),   # VND/ngày
        "vega" : round(vega, 2),    # VND per 1% vol
        "d1"   : round(d1, 4),
        "d2"   : round(d2, 4),
    }


# ══════════════════════════════════════════════════════════════════
# 4. HÀM TỔNG HỢP — TÍNH BS CHO 1 CW
# ══════════════════════════════════════════════════════════════════

def calc_bs_for_cw(
    cw_info:            dict,
    ohlcv_underlying:   pd.DataFrame,
    risk_free_rate:     Optional[float] = None,
    as_of_date:         Optional[str]   = None,
) -> dict:
    """
    Tính đầy đủ Black-Scholes cho 1 CW.

    Args:
        cw_info: dict từ df_vietstock với keys:
                   'gia_thuc_hien' (K, VND)
                   'ngay_dao_han'  (DD/MM/YYYY)
                   'ty_le_chuyen_doi' (vd: '5:1' hoặc 5.0)
                   'ck_co_so'      (mã CK cơ sở)
        ohlcv_underlying: OHLCV của CK cơ sở (có cột 'close')
        risk_free_rate: float thập phân (None → tự fetch HNX 10Y)
        as_of_date: tính tại ngày này (None → hôm nay)

    Returns:
        dict hoàn chỉnh để đưa vào data.json và dashboard
    """
    today_str = as_of_date or date.today().strftime("%Y-%m-%d")
    today_dt  = pd.to_datetime(today_str)

    # ── Parse K (giá thực hiện) ───────────────────────────────
    import re
    K_raw = str(cw_info.get("gia_thuc_hien", "0"))
    K = float(re.sub(r"[^\d.]", "", K_raw) or 0)
    if K <= 0:
        return {"error": "Giá thực hiện không hợp lệ"}

    # ── Parse tỷ lệ chuyển đổi n ─────────────────────────────
    ratio_raw = str(cw_info.get("ty_le_chuyen_doi", "1"))
    try:
        n = float(ratio_raw.split(":")[0].replace(",", "."))
    except Exception:
        n = 1.0
    if n <= 0:
        n = 1.0

    # ── Parse ngày đáo hạn → T ───────────────────────────────
    maturity_raw = str(cw_info.get("ngay_dao_han", ""))
    try:
        maturity_dt = pd.to_datetime(maturity_raw, dayfirst=True, errors="raise")
    except Exception:
        return {"error": f"Ngày đáo hạn không hợp lệ: {maturity_raw}"}

    T_days = (maturity_dt - today_dt).days
    T = max(T_days, 0) / 365.0

    # ── S: giá đóng cửa mới nhất của CK cơ sở ───────────────
    df_u = ohlcv_underlying.copy()
    if not isinstance(df_u.index, pd.DatetimeIndex):
        tcol = next((c for c in ["time", "date"] if c in df_u.columns), None)
        if tcol:
            df_u = df_u.set_index(pd.to_datetime(df_u[tcol], dayfirst=True, errors="coerce"))
    df_u = df_u.sort_index()
    df_u_filtered = df_u[df_u.index <= today_dt]
    if df_u_filtered.empty:
        return {"error": "Không có dữ liệu giá CK cơ sở"}
    S = float(df_u_filtered["close"].iloc[-1])
    if S < 1000:
        S *= 1000   # vnstock trả về nghìn đồng

    # ── r: lãi suất phi rủi ro 10Y HNX ──────────────────────
    if risk_free_rate is None:
        r = get_risk_free_rate(today_str)
    else:
        r = risk_free_rate

    # ── σ: historical volatility 252 phiên ──────────────────
    try:
        sigma = calc_sigma(ohlcv_underlying, window=252, as_of_date=today_str)
    except ValueError as e:
        sigma = 0.35   # fallback hợp lý nếu thiếu data
        print(f"   WARN sigma fallback 0.35: {e}")

    # ── Black-Scholes ─────────────────────────────────────────
    bs = bs_call(S=S, K=K, T=T, r=r, sigma=sigma)

    # Giá CW lý thuyết (quy về 1 CW từ giá Call trên 1 CP)
    cw_bs_price = bs["price"] / n

    # Moneyness
    if   S > K * 1.02: moneyness = "ITM"
    elif S < K * 0.98: moneyness = "OTM"
    else:              moneyness = "ATM"

    # Effective Gearing
    cw_market = float(df_u_filtered.get("close", pd.Series([0])).iloc[-1])  # placeholder
    # EG dùng giá thị trường CW nếu có, còn không dùng giá BS
    eff_gearing = round((S / (cw_bs_price * n)) * bs["delta"], 2) if cw_bs_price > 0 else 0

    return {
        # Inputs
        "S":           round(S, 0),
        "K":           round(K, 0),
        "T_days":      T_days,
        "T_years":     round(T, 4),
        "r_pct":       round(r * 100, 3),       # % (10Y HNX)
        "sigma":       sigma,
        "sigma_pct":   round(sigma * 100, 2),   # % annualized
        "n":           n,
        "moneyness":   moneyness,
        # Outputs BS
        "bs_price_call":  round(cw_bs_price, 2),   # Giá CW lý thuyết (VND)
        "delta":          bs["delta"],
        "gamma":          bs["gamma"],
        "theta":          bs["theta"],              # VND/ngày
        "vega":           bs["vega"],               # VND per 1% vol
        "eff_gearing":    eff_gearing,
    }


# ══════════════════════════════════════════════════════════════════
# 5. BATCH: TÍNH BS CHO TOÀN BỘ CW ACTIVE TRONG PIPELINE
# ══════════════════════════════════════════════════════════════════

def step_bs_selfcalc(
    df_vietstock:       pd.DataFrame,
    valid_tickers:      list,
    underlying_ohlcv:   dict,            # {sym: DataFrame} — đã có trong step5
    as_of_date:         Optional[str] = None,
) -> dict:
    """
    Tính Black-Scholes cho tất cả CW active.
    Tích hợp vào pipeline sau step2/step3, trước step5_export_json.

    Args:
        df_vietstock:     DataFrame từ step1 (thông tin CW)
        valid_tickers:    list mã CW cần tính (từ step3)
        underlying_ohlcv: {sym: DataFrame OHLCV} — reuse từ step5
        as_of_date:       None → hôm nay

    Returns:
        dict {ticker: bs_result} để merge vào data.json
    """
    print("\n" + "=" * 60)
    print("BUOC BS (tự tính) — Black-Scholes từ OHLCV + HNX 10Y")
    print("=" * 60)

    today_str = as_of_date or date.today().strftime("%Y-%m-%d")

    # Fetch r 1 lần duy nhất cho cả batch (10Y HNX)
    r = get_risk_free_rate(today_str)
    print(f"   r (10Y HNX) = {r*100:.3f}% (dùng cho toàn bộ batch)")

    # Lọc CW active
    df_active = df_vietstock[df_vietstock["ma_cw"].isin(valid_tickers)].copy()
    today_ts  = pd.Timestamp(today_str)
    if "ngay_gd_cuoi_cung" in df_active.columns:
        ldt = pd.to_datetime(df_active["ngay_gd_cuoi_cung"], dayfirst=True, errors="coerce")
        df_active = df_active[ldt >= today_ts]

    results = {}
    ok = fail = skip = 0
    total = len(df_active)

    for _, row in df_active.iterrows():
        ticker    = str(row.get("ma_cw", ""))
        und_sym   = str(row.get("ck_co_so", "")).strip()
        ohlcv_und = underlying_ohlcv.get(und_sym)

        if ohlcv_und is None or (hasattr(ohlcv_und, "empty") and ohlcv_und.empty):
            skip += 1
            continue

        try:
            res = calc_bs_for_cw(
                cw_info           = row.to_dict(),
                ohlcv_underlying  = ohlcv_und,
                risk_free_rate    = r,      # dùng chung, không fetch lại
                as_of_date        = today_str,
            )
            if "error" in res:
                fail += 1
                if fail <= 5:
                    print(f"   FAIL {ticker}: {res['error']}")
            else:
                results[ticker] = res
                ok += 1
                if ok <= 5 or ok % 50 == 0:
                    print(f"   [{ok:>4}/{total}] {ticker:12} "
                          f"S={res['S']:>8,.0f}  K={res['K']:>8,.0f}  "
                          f"T={res['T_days']}d  σ={res['sigma_pct']:.1f}%  "
                          f"BS={res['bs_price_call']:>7.2f}  Δ={res['delta']:.3f}  "
                          f"{res['moneyness']}")
        except Exception as e:
            fail += 1
            if fail <= 5:
                print(f"   FAIL {ticker}: {e}")

    print(f"\n   OK={ok}  FAIL={fail}  SKIP(no underlying)={skip}")
    return results


# ══════════════════════════════════════════════════════════════════
# 6. BACKTESTING: CHUỖI BS THEO NGÀY (cho drill-down chart)
# ══════════════════════════════════════════════════════════════════

def calc_bs_history(
    cw_info:            dict,
    ohlcv_underlying:   pd.DataFrame,
    ohlcv_cw:           pd.DataFrame,
    risk_free_rate_series: Optional[pd.Series] = None,
) -> list:
    """
    Tính chuỗi giá BS theo từng ngày giao dịch — dùng cho biểu đồ Backtesting
    (tương tự bảng Vietstock bên phải).

    Returns:
        list of dict: [{date, S, sigma, T_days, r_pct, bs_call, delta}, ...]
        Sắp xếp tăng dần theo ngày.
    """
    import re

    # Parse metadata CW
    K_raw = str(cw_info.get("gia_thuc_hien", "0"))
    K     = float(re.sub(r"[^\d.]", "", K_raw) or 0)
    n_raw = str(cw_info.get("ty_le_chuyen_doi", "1"))
    n     = float(n_raw.split(":")[0].replace(",", ".")) if n_raw else 1.0
    mat_raw = str(cw_info.get("ngay_dao_han", ""))
    try:
        maturity_dt = pd.to_datetime(mat_raw, dayfirst=True)
    except Exception:
        return []

    # Chuẩn hóa OHLCV underlying
    df_u = ohlcv_underlying.copy()
    if not isinstance(df_u.index, pd.DatetimeIndex):
        tcol = next((c for c in ["time", "date"] if c in df_u.columns), None)
        if tcol:
            df_u = df_u.set_index(pd.to_datetime(df_u[tcol], dayfirst=True, errors="coerce"))
    df_u = df_u.sort_index()
    close_u = df_u["close"].dropna()
    if close_u.median() < 1000:
        close_u = close_u * 1000

    # Sigma rolling 252 phiên
    log_ret      = np.log(close_u / close_u.shift(1))
    sigma_series = log_ret.rolling(252, min_periods=20).std() * math.sqrt(252)

    # Fallback r nếu không có series
    r_default = 0.0453

    history = []
    for dt, S in close_u.items():
        if pd.isna(S) or S <= 0:
            continue

        T_days = (maturity_dt - dt).days
        if T_days < 0:
            continue
        T = T_days / 365.0

        sigma = float(sigma_series.get(dt, np.nan))
        if np.isnan(sigma) or sigma <= 0:
            continue

        # r: dùng series theo ngày nếu có, không thì dùng default
        if risk_free_rate_series is not None and dt in risk_free_rate_series.index:
            r = float(risk_free_rate_series[dt]) / 100
        else:
            r = r_default

        bs = bs_call(S=S, K=K, T=T, r=r, sigma=sigma)
        cw_bs = bs["price"] / n

        history.append({
            "date":     dt.strftime("%d/%m/%Y"),
            "S":        round(S, 0),           # Giá CK cơ sở
            "sigma":    round(sigma, 4),
            "T_days":   T_days,
            "r_pct":    round(r * 100, 3),
            "bs_call":  round(cw_bs, 2),       # Giá CW lý thuyết
            "delta":    bs["delta"],
        })

    return sorted(history, key=lambda x: x["date"])


# ══════════════════════════════════════════════════════════════════
# 7. QUICK TEST
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== Test BS với CSTB2604 (15/07/2026) ===\n")

    # Tái tạo số liệu từ ảnh Vietstock
    bs = bs_call(S=69800, K=60000, T=103/365, r=0.045, sigma=0.3954)
    cw_price = bs["price"] / 5   # n=5

    print(f"Giá CK cơ sở (S)  : 69,800 VND")
    print(f"Giá thực hiện (K)  : 60,000 VND")
    print(f"Thời gian (T)      : 103 ngày = {103/365:.4f} năm")
    print(f"Lãi suất (r)       : 4.50% (10Y HNX)")
    print(f"Volatility (σ)     : 39.54%")
    print(f"Tỷ lệ chuyển đổi  : 5:1")
    print()
    print(f"─── Kết quả BS ───")
    print(f"Giá CW lý thuyết   : {cw_price:,.2f} VND  (Vietstock: 2,434.52 VND)")
    print(f"Sai số             : {abs(cw_price - 2434.52)/2434.52*100:.2f}%")
    print(f"Delta (Δ)          : {bs['delta']:.4f}")
    print(f"Gamma (Γ)          : {bs['gamma']:.6f}")
    print(f"Theta (Θ)          : {bs['theta']:.2f} VND/ngày")
    print(f"Vega               : {bs['vega']:.2f} VND per 1% vol")
    print(f"d1                 : {bs['d1']:.4f}")
    print(f"d2                 : {bs['d2']:.4f}")
