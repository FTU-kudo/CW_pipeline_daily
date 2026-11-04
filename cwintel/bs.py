"""Black‑Scholes cho chứng quyền Việt Nam — nguồn sự thật duy nhất.

Quy ước CW Việt Nam (châu Âu, thanh toán tiền mặt, tỷ lệ chuyển đổi n:1):
    giá trị 1 CW = C / n          (C = giá quyền trên 1 cổ phiếu)
    Delta/CW    = N(d1) / n       (số cổ phiếu quy đổi trên 1 CW)
    Gamma/CW    = φ(d1) / (S·σ·√T · n)
    Vega/CW     = S·φ(d1)·√T / 100 / n      (VND cho 1 điểm vol = 1%)
    Theta/CW    = ∂C/∂t / 365 / n           (VND/CW/ngày lịch)
    Rho/CW      = K·T·e^(−rT)·N(d2) / 100 / n

Điều khoản CW Việt Nam đã điều chỉnh strike & tỷ lệ khi có cổ tức/thưởng, nên mô
hình **không** trừ cổ tức lần nữa (dùng q = 0) — nhưng chỉ đúng khi đầu vào là
strike/ratio **đã điều chỉnh**. Nếu dùng strike gốc thì phải coi kết quả là ước
lượng thô; tầng gọi có trách nhiệm truyền đúng và ghi rõ nguồn.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np

SQRT2 = math.sqrt(2.0)
INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)

# numpy không có erf/erfc; frompyfunc là đường nhanh nhất không cần scipy
# (≈30 ms cho 200k phần tử, đủ dùng cho backfill IV ~2×10^5 dòng).
_erfc_vec = np.frompyfunc(math.erfc, 1, 1)


# ──────────────────────────────────────────────────────────────────
# HÀM PHÂN PHỐI
# ──────────────────────────────────────────────────────────────────
def norm_cdf(x):
    """CDF chuẩn, hoạt động với cả float và numpy array (dùng erfc để ổn định đuôi)."""
    if np.isscalar(x):
        return 0.5 * math.erfc(-float(x) / SQRT2)
    arr = np.asarray(x, dtype=float)
    out = 0.5 * _erfc_vec(-arr / SQRT2).astype(float)
    return out


def norm_pdf(x):
    x = np.asarray(x, dtype=float)
    out = INV_SQRT_2PI * np.exp(-0.5 * x * x)
    return float(out) if out.ndim == 0 else out


# ──────────────────────────────────────────────────────────────────
# KẾT QUẢ
# ──────────────────────────────────────────────────────────────────
@dataclass
class BSResult:
    price: float = 0.0          # VND / CW
    intrinsic: float = 0.0      # VND / CW
    time_value: float = 0.0     # VND / CW
    delta: float = 0.0          # cổ phiếu / CW
    gamma: float = 0.0
    vega: float = 0.0           # VND / CW / 1 vol point
    theta: float = 0.0          # VND / CW / ngày lịch
    rho: float = 0.0            # VND / CW / 1% lãi suất
    d1: float = float("nan")
    d2: float = float("nan")
    status: str = "ok"          # ok | expired | invalid_input

    def as_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────
# ĐỊNH GIÁ
# ──────────────────────────────────────────────────────────────────
def intrinsic_value(S, K, ratio=1.0, kind="call"):
    """Giá trị nội tại (VND/CW), không bao giờ âm."""
    if not (S > 0 and K > 0 and ratio > 0):
        return 0.0
    if kind == "put":
        return max(K - S, 0.0) / ratio
    return max(S - K, 0.0) / ratio


def price_and_greeks(S: float, K: float, T: float, r: float, sigma: float,
                     ratio: float = 1.0, kind: str = "call", q: float = 0.0) -> BSResult:
    """Định giá 1 CW bằng Black‑Scholes. Trả về đầy đủ Greeks theo đơn vị/CW.

    S, K   : VND
    T      : năm (0 → đáo hạn hôm nay)
    r, q   : lãi suất phi rủi ro / dividend yield liên tục
    sigma  : vol năm (0.3 = 30%)
    ratio  : n — số CW cho 1 cổ phiếu
    """
    kind = (kind or "call").lower()
    if kind.startswith("p"):
        kind = "put"
    else:
        kind = "call"

    if not (S and S > 0) or not (K and K > 0) or not (ratio and ratio > 0):
        return BSResult(status="invalid_input")

    intr = intrinsic_value(S, K, ratio, kind)
    if not (T and T > 0):
        return BSResult(price=intr, intrinsic=intr, status="expired",
                        d1=float("nan"), d2=float("nan"))
    if not (sigma and sigma > 0):
        return BSResult(price=intr, intrinsic=intr, status="invalid_input",
                        d1=float("nan"), d2=float("nan"))

    vol_t = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vol_t
    d2 = d1 - vol_t
    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)

    if kind == "call":
        price = S * disc_q * norm_cdf(d1) - K * disc_r * norm_cdf(d2)
        delta = disc_q * norm_cdf(d1)
        theta_opt = (-S * disc_q * norm_pdf(d1) * sigma / (2 * math.sqrt(T))
                     - r * K * disc_r * norm_cdf(d2)
                     + q * S * disc_q * norm_cdf(d1))
        rho_opt = K * T * disc_r * norm_cdf(d2)
    else:
        price = K * disc_r * norm_cdf(-d2) - S * disc_q * norm_cdf(-d1)
        delta = -disc_q * norm_cdf(-d1)
        theta_opt = (-S * disc_q * norm_pdf(d1) * sigma / (2 * math.sqrt(T))
                     + r * K * disc_r * norm_cdf(-d2)
                     - q * S * disc_q * norm_cdf(-d1))
        rho_opt = -K * T * disc_r * norm_cdf(-d2)

    price = max(price, intr)
    gamma_opt = disc_q * norm_pdf(d1) / (S * vol_t)
    vega_opt = S * disc_q * norm_pdf(d1) * math.sqrt(T) / 100.0

    return BSResult(
        price=price / ratio,
        intrinsic=intr,
        time_value=max(price / ratio - intr, 0.0),
        delta=delta / ratio,
        gamma=gamma_opt / ratio,
        vega=vega_opt / ratio,
        theta=theta_opt / 365.0 / ratio,
        rho=rho_opt / 100.0 / ratio,
        d1=d1,
        d2=d2,
        status="ok",
    )


def price_vector(S, K, T, r, sigma, ratio=1.0, kind="call"):
    """Vector hoá định giá (dùng cho backfill IV / panel). Trả về mảng VND/CW."""
    # broadcast mọi tham số về cùng shape — hàm phải chạy được cả khi sigma/ratio là scalar
    S, K, T, sigma, ratio = (
        np.array(a, dtype=float, copy=True)
        for a in np.broadcast_arrays(*[np.asarray(x, dtype=float) for x in (S, K, T, sigma, ratio)])
    )
    out = np.zeros(S.shape, dtype=float)
    valid = (S > 0) & (K > 0) & (T > 0) & (sigma > 0) & (ratio > 0)
    if not valid.any():
        return out
    vol_t = sigma[valid] * np.sqrt(T[valid])
    d1 = (np.log(S[valid] / K[valid]) + (r + 0.5 * sigma[valid] ** 2) * T[valid]) / vol_t
    d2 = d1 - vol_t
    if str(kind).lower().startswith("p"):
        px = K[valid] * np.exp(-r * T[valid]) * norm_cdf(-d2) - S[valid] * norm_cdf(-d1)
    else:
        px = S[valid] * norm_cdf(d1) - K[valid] * np.exp(-r * T[valid]) * norm_cdf(d2)
    out[valid] = px / ratio[valid]
    return out


def greeks_vector(S, K, T, r, sigma, ratio=1.0):
    """Vector hoá Greeks cho call (đơn vị/CW). Trả về dict các mảng."""
    S, K, T, sigma, ratio = (
        np.array(a, dtype=float, copy=True)
        for a in np.broadcast_arrays(*[np.asarray(x, dtype=float) for x in (S, K, T, sigma, ratio)])
    )
    shape = S.shape
    delta = np.full(shape, np.nan)
    gamma = np.full(shape, np.nan)
    vega = np.full(shape, np.nan)
    theta = np.full(shape, np.nan)
    valid = (S > 0) & (K > 0) & (T > 0) & (sigma > 0) & (ratio > 0)
    if valid.any():
        vol_t = sigma[valid] * np.sqrt(T[valid])
        d1 = (np.log(S[valid] / K[valid]) + (r + 0.5 * sigma[valid] ** 2) * T[valid]) / vol_t
        d2 = d1 - vol_t
        disc = np.exp(-r * T[valid])
        delta[valid] = norm_cdf(d1) / ratio[valid]
        gamma[valid] = norm_pdf(d1) / (S[valid] * vol_t) / ratio[valid]
        vega[valid] = S[valid] * norm_pdf(d1) * np.sqrt(T[valid]) / 100.0 / ratio[valid]
        theta[valid] = (-S[valid] * norm_pdf(d1) * sigma[valid] / (2 * np.sqrt(T[valid]))
                        - r * K[valid] * disc * norm_cdf(d2)) / 365.0 / ratio[valid]
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta}


# ──────────────────────────────────────────────────────────────────
# IMPLIED VOLATILITY
# ──────────────────────────────────────────────────────────────────
def implied_vol(market_price: float, S: float, K: float, T: float, r: float,
                ratio: float = 1.0, kind: str = "call",
                lo: float = 1e-4, hi: float = 5.0, tol: float = 1e-7,
                max_iter: int = 200) -> tuple[float | None, str]:
    """IV của 1 CW từ giá thị trường (VND/CW). Trả (iv, status).

    status: ok | no_arbitrage_range | below_intrinsic | above_upper_bound | bad_input
    """
    if not (S > 0 and K > 0 and T > 0 and ratio > 0 and market_price > 0):
        return None, "bad_input"

    intr = intrinsic_value(S, K, ratio, kind)
    upper = S / ratio if str(kind).lower().startswith("c") else K * math.exp(-r * T) / ratio
    # Dung sai 1 VND cho làm tròn giá (bước giá CW = 10 VND, dữ liệu làm tròn nghìn VND)
    if market_price < intr - 1.0:
        return None, "below_intrinsic"
    if market_price > upper + 1.0:
        return None, "above_upper_bound"
    if market_price <= intr + 1e-9:
        return None, "no_arbitrage_range"   # giá = intrinsic → vol → 0, không xác định

    def f(sig):
        return price_and_greeks(S, K, T, r, sig, ratio, kind).price - market_price

    f_lo, f_hi = f(lo), f(hi)
    if f_lo > 0:
        return lo, "ok"          # giá thị trường thấp hơn cả BS với vol tối thiểu
    if f_hi < 0:
        return None, "above_upper_bound"

    # Newton trước (nhanh), bisection bảo đảm hội tụ
    sig = 0.5 * (lo + hi)
    for _ in range(max_iter // 2):
        val = f(sig)
        if abs(val) < tol:
            return sig, "ok"
        vol_t = sig * math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / vol_t
        vega = S * norm_pdf(d1) * math.sqrt(T)     # dC/dsigma (VND/cổ phiếu)
        if vega < 1e-10:
            break
        step = val / vega
        new_sig = min(hi, max(lo, sig - step))
        if abs(new_sig - sig) < tol:
            return new_sig, "ok"
        sig = new_sig

    a, b = lo, hi
    fa = f(a)
    for _ in range(max_iter):
        mid = 0.5 * (a + b)
        fm = f(mid)
        if abs(fm) < tol or (b - a) < tol:
            return mid, "ok"
        if fa * fm <= 0:
            b = mid
        else:
            a, fa = mid, fm
    return 0.5 * (a + b), "ok"


def implied_vol_vector(market_price, S, K, T, r, ratio=1.0, kind="call",
                       lo: float = 1e-4, hi: float = 5.0, iters: int = 60):
    """IV vector hoá bằng bisection thuần (ổn định, đủ nhanh cho ~2×10^5 dòng).

    Trả về (iv, valid_mask). Dùng cho backfill lịch sử IV.
    """
    m, S, K, T, ratio = map(lambda a: np.asarray(a, dtype=float).ravel(),
                            (market_price, S, K, T, ratio))
    n = max(len(m), len(S), len(K), len(T), len(ratio))
    m, S, K, T, ratio = (np.broadcast_to(a, (n,)).astype(float) for a in (m, S, K, T, ratio))
    intr = np.where(str(kind).lower().startswith("p"),
                    np.maximum(K - S, 0) / ratio, np.maximum(S - K, 0) / ratio)
    upper = np.where(str(kind).lower().startswith("p"),
                     K * np.exp(-r * np.maximum(T, 0)) / ratio, S / ratio)
    valid = (S > 0) & (K > 0) & (T > 0) & (ratio > 0) & (m > 0)
    valid &= (m <= upper + 1.0) & (m > intr + 1.0)
    iv = np.full(n, np.nan)
    if not valid.any():
        return iv, valid

    idx = np.where(valid)[0]
    a = np.full(idx.size, lo)
    b = np.full(idx.size, hi)
    Ss, Ks, Ts, ms, ns = S[idx], K[idx], T[idx], m[idx], ratio[idx]
    for _ in range(iters):
        mid = 0.5 * (a + b)
        f = price_vector(Ss, Ks, Ts, r, mid, ns, kind) - ms
        pos = f > 0
        b = np.where(pos, mid, b)
        a = np.where(pos, a, mid)
    iv[idx] = 0.5 * (a + b)
    return iv, valid
