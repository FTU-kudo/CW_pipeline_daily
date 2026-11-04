"""Xây dựng panel đặc trưng theo ngày cho từng CW và từng cổ phiếu cơ sở.

Panel là dạng long `(ticker, date)` chứa mọi thứ tầng scoring/backtest cần. Mọi đặc
trưng tại ngày t chỉ dùng dữ liệu ≤ t (rolling window kết thúc tại t) nên dùng lại
được cho walk-forward backtest mà không có look-ahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, indicators as ta, liquidity as liq
from .bs import greeks_vector, implied_vol_vector, price_vector
from .data import MarketData


# ──────────────────────────────────────────────────────────────────
# CỔ PHIẾU CƠ SỞ
# ──────────────────────────────────────────────────────────────────
def build_underlying_features(und: pd.DataFrame) -> pd.DataFrame:
    """Đặc trưng kỹ thuật cho từng cổ phiếu cơ sở, một dòng / (symbol, ngày)."""
    if und.empty:
        return pd.DataFrame()

    rows = []
    for sym, g in und.groupby("ticker", sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        close = g["close"]
        f = pd.DataFrame({"ticker": sym, "date": g["date"], "close": close})
        f["ret1"] = ta.pct_change_n(close, 1)
        f["ret5"] = ta.pct_change_n(close, 5)
        f["ret21"] = ta.pct_change_n(close, 21)
        f["ret63"] = ta.pct_change_n(close, 63)
        f["ma20"] = ta.sma(close, 20)
        f["ma50"] = ta.sma(close, 50)
        f["ma200"] = ta.sma(close, 200)
        f["rsi14"] = ta.rsi(close, 14)
        m = ta.macd(close)
        f["macd_hist"] = m["hist"]
        f["hv20"] = ta.realized_vol(close, 20)
        f["hv60"] = ta.realized_vol(close, 60)
        f["hv252"] = ta.realized_vol(close, 252)
        f["vol"] = pd.Series(g["volume"], dtype="float64")
        f["vol_ma20"] = ta.sma(g["volume"], 20)
        f["vol_ratio"] = g["volume"] / f["vol_ma20"].replace(0, np.nan)
        f["high60"] = close.rolling(60, min_periods=20).max()
        f["low60"] = close.rolling(60, min_periods=20).min()
        n = np.arange(1, len(g) + 1)
        f["sessions"] = n
        rows.append(f)

    out = pd.concat(rows, ignore_index=True)
    out["above_ma20"] = (out["close"] > out["ma20"]).astype(float).where(out["ma20"].notna())
    out["above_ma50"] = (out["close"] > out["ma50"]).astype(float).where(out["ma50"].notna())
    out["above_ma200"] = (out["close"] > out["ma200"]).astype(float).where(out["ma200"].notna())
    out["dist_high60"] = out["close"] / out["high60"] - 1.0
    out["dist_low60"] = out["close"] / out["low60"] - 1.0
    return out.sort_values(["ticker", "date"]).reset_index(drop=True)


def _daily_trading_calendar(frames: list[pd.DataFrame]) -> pd.DatetimeIndex:
    dates = pd.Index([])
    for f in frames:
        if f is not None and not f.empty:
            dates = dates.union(pd.DatetimeIndex(f["date"].unique()))
    return pd.DatetimeIndex(sorted(dates))


# ──────────────────────────────────────────────────────────────────
# PANEL CW
# ──────────────────────────────────────────────────────────────────
def build_cw_panel(market: MarketData, und_feat: pd.DataFrame | None = None,
                   r: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Trả về (panel, iv_history).

    panel: 1 dòng / (ticker, ngày giao dịch) với đặc trưng giá, thanh khoản, định giá.
    iv_history: 1 dòng / (ticker, ngày) có IV tính được từ giá thị trường.
    """
    oh = market.ohlcv
    if oh.empty:
        return pd.DataFrame(), pd.DataFrame()
    if und_feat is None:
        und_feat = build_underlying_features(market.underlying)
    r = market.risk_free if r is None else r

    master = market.master.set_index("ticker")

    rows = []
    for ticker, g in oh.groupby("ticker", sort=False):
        if ticker not in master.index:
            continue
        m = master.loc[ticker]
        if isinstance(m, pd.DataFrame):
            m = m.iloc[-1]
        g = g.sort_values("date").reset_index(drop=True)
        close = g["close"]
        high = g.get("high", close).fillna(close)
        low = g.get("low", close).fillna(close)
        volume = g["volume"].fillna(0.0)

        f = pd.DataFrame({"ticker": ticker, "date": g["date"], "close": close,
                          "open": g.get("open", close).fillna(close),
                          "high": high, "low": low, "volume": volume})
        f["ret1"] = ta.pct_change_n(close, 1)
        f["ret5"] = ta.pct_change_n(close, 5)
        f["ret21"] = ta.pct_change_n(close, 21)
        f["value"] = ta.turnover_value(close, volume)
        f["value_med20"] = f["value"].rolling(config.LIQUIDITY_WINDOW, min_periods=5).median()
        f["value_med5"] = f["value"].rolling(5, min_periods=3).median()
        f["traded_ratio20"] = (volume > 0).astype(float).rolling(
            config.LIQUIDITY_WINDOW, min_periods=5).mean()
        f["volume_ma20"] = ta.sma(volume, 20)
        f["volume_accel"] = (volume.rolling(5, min_periods=3).mean()
                             / f["volume_ma20"].replace(0, np.nan))
        f["atr14"] = ta.atr(high, low, close, 14)
        # Độ biến động giá CW thực tế (dùng làm phương án dự phòng khi thiếu 14 phiên cho ATR)
        f["ret_std20"] = f["ret1"].rolling(20, min_periods=5).std()
        f["atr_pct"] = f["atr14"] / close.replace(0, np.nan) * 100.0
        f["rsi14"] = ta.rsi(close, 14)
        _macd = ta.macd(close)["hist"]
        f["macd_hist"] = _macd
        f["macd_hist_slope"] = _macd.diff()
        f["ma20"] = ta.sma(close, 20)
        f["ma50"] = ta.sma(close, 50)
        f["above_ma20"] = (close > f["ma20"]).astype(float).where(f["ma20"].notna())
        f["above_ma50"] = (close > f["ma50"]).astype(float).where(f["ma50"].notna())
        f["high20_prev"] = high.rolling(20, min_periods=10).max().shift(1)
        f["low20_prev"] = low.rolling(20, min_periods=10).min().shift(1)
        f["breakout20"] = (close > f["high20_prev"]).astype(float).where(
            f["high20_prev"].notna())
        f["sessions"] = np.arange(1, len(g) + 1)

        # Điều khoản hợp đồng
        f["underlying"] = m["underlying"]
        f["issuer"] = m["issuer"]
        f["K"] = m["K"]
        f["ratio"] = m["ratio"]
        f["maturity"] = m["maturity"]
        f["first_trade"] = m["first_trade"]
        f["last_trade"] = m["last_trade"]
        # Cờ theo TỪNG dòng: hợp đồng còn hiệu lực tại ngày đó (không phải cờ asof)
        f["is_active"] = (f["date"] <= m["maturity"]) if pd.notna(m["maturity"]) else False
        f["days_to_maturity"] = (m["maturity"] - f["date"]).dt.days
        f["T"] = f["days_to_maturity"] / config.DAYS_PER_YEAR
        # CW chỉ được giao dịch trong khoảng first_trade → last_trade
        f = f[(f["date"] >= (m["first_trade"] - pd.Timedelta(days=3))) |
              f["first_trade"].isna()]
        rows.append(f)

    panel = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if panel.empty:
        return panel, pd.DataFrame()

    # ── Ghép đặc trưng cổ phiếu cơ sở (as-of, ffill để không dùng tương lai)
    u = und_feat.sort_values(["ticker", "date"]).copy()
    und_cols = ["close", "ret1", "ret5", "ret21", "ret63", "ma20", "ma50", "ma200", "vol",
                "rsi14", "macd_hist", "hv20", "hv60", "hv252", "vol_ratio",
                "above_ma20", "above_ma50", "above_ma200", "dist_high60", "dist_low60",
                "sessions"]
    u = u.rename(columns={"ticker": "underlying", **{c: f"u_{c}" for c in und_cols}})
    panel = panel.merge(u, on=["underlying", "date"], how="left")
    # ffill trong từng underlying: chỉ mang giá trị QUÁ KHỨ sang phiên CW thiếu dữ liệu
    u_cols = [c for c in u.columns if c.startswith("u_")]
    panel = panel.sort_values(["underlying", "date"])
    panel[u_cols] = panel.groupby("underlying", sort=False)[u_cols].ffill()
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)

    # ── Sigma dùng cho định giá mô hình: HV252 → HV60 → HV20
    panel["sigma"] = panel["u_hv252"].where(panel["u_hv252"].notna() & (panel["u_hv252"] > 0))
    panel["sigma"] = panel["sigma"].fillna(panel["u_hv60"].where(panel["u_hv60"] > 0))
    panel["sigma"] = panel["sigma"].fillna(panel["u_hv20"].where(panel["u_hv20"] > 0))
    panel["sigma_source"] = np.where(panel["u_hv252"].notna() & (panel["u_hv252"] > 0), "hv252",
                            np.where(panel["u_hv60"].notna() & (panel["u_hv60"] > 0), "hv60",
                            np.where(panel["u_hv20"].notna() & (panel["u_hv20"] > 0), "hv20",
                                     "fallback")))
    panel["sigma"] = panel["sigma"].fillna(config.SIGMA_FALLBACK)

    S = panel["u_close"]
    K = panel["K"]
    T = panel["T"]
    ratio = panel["ratio"]
    sigma = panel["sigma"]
    valid_terms = S.notna() & (S > 0) & K.notna() & (K > 0) & (T > 0) & ratio.gt(0)

    # ── Định giá mô hình (theoretical value theo HV)
    panel["bs_fv"] = np.nan
    panel.loc[valid_terms, "bs_fv"] = price_vector(
        S[valid_terms], K[valid_terms], T[valid_terms], r, sigma[valid_terms],
        ratio[valid_terms], "call")
    greeks = greeks_vector(
        S.where(valid_terms), K.where(valid_terms), T.where(valid_terms), r,
        sigma.where(valid_terms), ratio.where(valid_terms))
    for k, v in greeks.items():
        panel[k] = v

    # ── Định giá tương đối
    panel["intrinsic"] = np.where(valid_terms,
                                  np.maximum(S - K, 0) / ratio, np.nan)
    panel["time_value"] = panel["close"] - panel["intrinsic"]
    panel["premium_be"] = np.where(
        S.gt(0) & panel["intrinsic"].notna(),
        ((K + panel["close"] * ratio) / S - 1.0) * 100.0, np.nan)
    panel["premium_time"] = np.where(
        S.gt(0) & panel["intrinsic"].notna(),
        panel["time_value"] / S * 100.0, np.nan)
    panel["breakeven"] = K + panel["close"] * ratio
    panel["be_distance_pct"] = (panel["breakeven"] / S - 1.0) * 100.0
    panel["moneyness_pct"] = (S / K - 1.0) * 100.0
    panel["moneyness"] = np.select(
        [panel["moneyness_pct"] > config.ATM_BAND * 100,
         panel["moneyness_pct"] < -config.ATM_BAND * 100],
        ["ITM", "OTM"], default="ATM")
    panel.loc[~valid_terms, "moneyness"] = "N/A"
    panel["gearing_gross"] = np.where(
        panel["close"].gt(0) & ratio.gt(0), S / (panel["close"] * ratio), np.nan)
    panel["eff_gearing"] = panel["gearing_gross"] * panel["delta"] * ratio
    panel["fv_upside_pct"] = np.where(
        panel["close"].gt(0) & panel["bs_fv"].notna(),
        (panel["bs_fv"] / panel["close"] - 1.0) * 100.0, np.nan)
    panel["theta_pct"] = np.where(panel["close"].gt(0),
                                  panel["theta"] / panel["close"] * 100.0, np.nan)

    # ── Implied volatility từ giá thị trường (backfill toàn bộ lịch sử)
    iv = np.full(len(panel), np.nan)
    vmask = valid_terms & panel["close"].gt(0)
    if vmask.any():
        iv_vals, _ = implied_vol_vector(
            panel.loc[vmask, "close"].to_numpy(), S[vmask].to_numpy(), K[vmask].to_numpy(),
            T[vmask].to_numpy(), r, ratio[vmask].to_numpy(), "call")
        iv[vmask.to_numpy()] = iv_vals
    # Chất lượng IV: giá CW ở mức 1–2 bước giá (10–20 VND) hoặc thời gian còn quá
    # ngắn làm IV bùng nổ do làm tròn tick, không phản ánh kỳ vọng biến động.
    # Giá CW ≤ 30 VND (3 bước giá) → IV bị chi phối bởi làm tròn tick;
    # T < 7 ngày hoặc IV > 300% → không đáng tin.
    iv_unreliable = (panel["close"].le(30.0) | panel["T"].lt(7.0 / config.DAYS_PER_YEAR)
                     | ~np.isfinite(iv) | (iv > 3.0))
    panel["iv_raw"] = iv
    panel["iv"] = np.where(iv_unreliable, np.nan, iv)
    panel["iv_quality"] = np.select(
        [panel["iv"].notna(), panel["iv_raw"].notna()], ["ok", "low"], default="na")
    panel["iv_vs_hv"] = np.where(panel["iv"].notna() & panel["sigma"].gt(0),
                                 (panel["iv"] / panel["sigma"] - 1.0) * 100.0, np.nan)

    # ── IV rank / percentile trên 252 quan sát IV của chính CW đó
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    iv_hist = panel[["ticker", "date", "iv", "sigma"]].dropna(subset=["iv"]).copy()

    def _iv_rank(s: pd.Series) -> pd.Series:
        win = config.HV_WINDOW
        roll = s.rolling(win, min_periods=20)
        hi, lo = roll.max(), roll.min()
        rng = (hi - lo)
        return ((s - lo) / rng.replace(0, np.nan) * 100.0)

    panel["iv_rank"] = panel.groupby("ticker", sort=False)["iv"].transform(_iv_rank)

    # ── Thanh khoản trên lịch giao dịch đầy đủ (phiên vắng mặt = 0 VND)
    panel = liq.attach_liquidity(panel, market.master)

    # Lịch sử IV 252 quan sát gần nhất cho từng ticker/ngày (theo quan sát, không theo lịch)
    return panel, iv_hist


# ──────────────────────────────────────────────────────────────────
# SNAPSHOT
# ──────────────────────────────────────────────────────────────────
def slice_asof(panel: pd.DataFrame, asof: pd.Timestamp,
               tolerance_days: int = 7) -> pd.DataFrame:
    """Lấy dòng mới nhất ≤ asof cho mỗi ticker trong cửa sổ `tolerance_days`.

    Không ffill vô hạn: CW không giao dịch quá 7 ngày bị loại khỏi snapshot
    (tránh hiển thị dữ liệu cũ như dữ liệu hiện tại).
    """
    if panel.empty:
        return panel
    asof = pd.Timestamp(asof).normalize()
    sub = panel[panel["date"] <= asof]
    if sub.empty:
        return panel.iloc[0:0]
    last = sub.groupby("ticker")["date"].max()
    keep = last[last >= asof - pd.Timedelta(days=tolerance_days)].index
    out = sub[(sub["ticker"].isin(keep)) & (sub["date"] == sub["ticker"].map(last))]
    return out.reset_index(drop=True)
