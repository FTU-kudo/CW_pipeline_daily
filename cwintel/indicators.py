"""Chỉ số kỹ thuật — tính trên chuỗi đã sắp xếp tăng dần theo ngày.

Mọi hàm nhận Series/ndarray và **không** fillna về 0: giá trị thiếu giữ nguyên NaN để
tầng trên biết dữ liệu chưa đủ. Công thức ghi rõ trong docs/METHODOLOGY.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def sma(values, window: int) -> pd.Series:
    return pd.Series(values, dtype="float64").rolling(window, min_periods=window).mean()


def ema(values, span: int) -> pd.Series:
    return pd.Series(values, dtype="float64").ewm(span=span, adjust=False,
                                                  min_periods=span).mean()


def rsi(close, period: int = 14) -> pd.Series:
    """RSI Wilder: RSI = 100 − 100/(1+RS), RS = EMA_alpha1/p (gain)/EMA(1/p)(loss)."""
    s = pd.Series(close, dtype="float64")
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    out = out.where(avg_loss > 0, 100.0)          # chuỗi chỉ tăng → RSI = 100
    out = out.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)
    return out


def macd(close, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    s = pd.Series(close, dtype="float64")
    ema_fast = s.ewm(span=fast, adjust=False).mean()
    ema_slow = s.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False).mean()
    hist = line - sig
    return pd.DataFrame({"macd": line, "signal": sig, "hist": hist})


def atr(high, low, close, period: int = 14) -> pd.Series:
    h = pd.Series(high, dtype="float64")
    l = pd.Series(low, dtype="float64")
    c = pd.Series(close, dtype="float64")
    prev_close = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_close).abs(), (l - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def log_returns(close) -> pd.Series:
    s = pd.Series(close, dtype="float64")
    return np.log(s / s.shift(1))


def realized_vol(close, window: int = 20) -> pd.Series:
    """Độ lệch chuẩn log-return × √252 (ddof=1)."""
    lr = log_returns(close)
    return lr.rolling(window, min_periods=max(5, window // 2)).std(ddof=1) * np.sqrt(
        config.TRADING_DAYS_PER_YEAR
    )


def hv_from_prices(prices, window: int = config.HV_WINDOW) -> float:
    """Historical volatility annualised của `window` phiên cuối (dùng cho snapshot)."""
    arr = np.asarray(prices, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size < 3:
        return float("nan")
    arr = arr[-window:] if arr.size > window else arr
    lr = np.diff(np.log(arr))
    if lr.size < 2:
        return float("nan")
    return float(np.std(lr, ddof=1) * np.sqrt(config.TRADING_DAYS_PER_YEAR))


def turnover_value(close_vnd, volume) -> pd.Series:
    """Giá trị giao dịch (VND) = giá đóng cửa (VND) × khối lượng."""
    c = pd.Series(close_vnd, dtype="float64")
    v = pd.Series(volume, dtype="float64")
    return c * v


def pct_change_n(close, n: int) -> pd.Series:
    s = pd.Series(close, dtype="float64")
    return s / s.shift(n) - 1.0


def percentile_rank(values, higher_is_better: bool = True) -> pd.Series:
    """Xếp hạng percentile trong *cùng một mặt cắt* (0..100). NaN giữ NaN.

    Dùng mid-rank để CW đồng hạng không bị đẩy lên/xuống tuỳ thứ tự.
    """
    s = pd.Series(values, dtype="float64")
    valid = s.notna()
    out = pd.Series(np.nan, index=s.index, dtype="float64")
    if valid.sum() == 0:
        return out
    r = s[valid].rank(method="average", pct=True) * 100.0
    if not higher_is_better:
        r = 100.0 - r
    out.loc[valid] = r
    return out


def bucket_score(value: float, bands: list[tuple[float, float, float]], default=np.nan) -> float:
    """Áp bảng điểm dạng [(low, high, score)] với low <= x < high."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return default
    for low, high, score in bands:
        if low <= value < high:
            return float(score)
    return default


def distance_pct(a: float, b: float) -> float:
    if not b:
        return float("nan")
    return abs(a - b) / b * 100.0
