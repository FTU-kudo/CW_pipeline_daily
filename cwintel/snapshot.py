"""Snapshot (mặt cắt thời gian) + định giá tương đối theo nhóm cổ phiếu cơ sở."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, liquidity as liqmod
from .bs import price_vector
from .data import MarketData
from .panels import slice_asof
from .scoring import score_universe


SNAPSHOT_COLS = [
    "ticker", "underlying", "issuer", "date", "close", "high", "low", "volume",
    "K", "ratio", "maturity", "first_trade", "last_trade", "T", "days_to_maturity",
    "is_active", "terms_valid",
    "ret1", "ret5", "ret21", "value", "value_med20", "traded_ratio20", "volume_accel",
    "rsi14", "macd_hist", "macd_hist_slope", "ma20", "ma50", "above_ma20", "above_ma50",
    "breakout20", "atr14", "atr_pct", "ret_std20", "sessions",
    "intrinsic", "time_value", "premium_be", "premium_time", "breakeven",
    "be_distance_pct", "moneyness", "moneyness_pct", "gearing_gross", "eff_gearing",
    "delta", "gamma", "vega", "theta", "theta_pct", "bs_fv", "fv_upside_pct",
    "sigma", "sigma_source", "iv", "iv_raw", "iv_quality", "iv_vs_hv", "iv_rank", "d1", "d2",
    "u_close", "u_ret1", "u_ret5", "u_ret21", "u_ret63", "u_rsi14", "u_macd_hist",
    "u_ma20", "u_ma50", "u_ma200", "u_above_ma20", "u_above_ma50", "u_above_ma200",
    "u_hv20", "u_hv60", "u_hv252", "u_dist_high60", "u_sessions", "u_vol_ratio",
    # Thanh khoản (xem cwintel/liquidity.py)
    "listed_volume", "outstanding_volume", "adv5", "adv20", "adv60",
    "coverage20", "coverage60", "coverage_listing", "sessions_listed", "zero20",
    "amihud20", "range20", "turnover20",
    "liq_trend", "dtl_50m", "impact_50m_pct",
]


def _pick(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    return df[[c for c in cols if c in df.columns]].copy()


def _fit_smile(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float, str]:
    """Hồi quy tuyến tính IV ~ a + b·z (z = ln(K/S)/√T) cho một nhóm CW.

    Trả về (b, a, r2, source). Dùng mô hình smile đơn giản thay vì lấy trung vị IV
    thô — vì CW deep OTM luôn có IV cao hơn CW ATM, so sánh trực tiếp sẽ sai.
    """
    mask = np.isfinite(x) & np.isfinite(y)
    n = int(mask.sum())
    if n < 5:
        return 0.0, float(np.median(y[mask])) if n else np.nan, np.nan, "median"
    xs, ys = x[mask], y[mask]
    if np.std(xs) < 1e-8:
        return 0.0, float(np.median(ys)), np.nan, "median"
    try:
        b, a = np.polyfit(xs, ys, 1)
    except (np.linalg.LinAlgError, ValueError):
        return 0.0, float(np.median(ys)), np.nan, "median"
    pred = a + b * xs
    ss_res = float(np.sum((ys - pred) ** 2))
    ss_tot = float(np.sum((ys - ys.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return float(b), float(a), r2, "smile"


def _kernel_smile(z: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Ước lượng IV theo moneyness bằng kernel Gaussian (băng thông theo IQR của z)."""
    out = np.full(len(z), np.nan)
    mask = np.isfinite(z) & np.isfinite(y)
    if mask.sum() == 0:
        return out
    zs, ys = z[mask], y[mask]
    if zs.size == 1:
        out[mask] = ys[0]
        return out
    iqr = np.subtract(*np.percentile(zs, [75, 25]))
    bw = max(iqr / 1.34, 0.05)
    z_query = np.where(np.isfinite(z), z, np.nanmedian(zs))
    W = np.exp(-0.5 * ((z_query[:, None] - zs[None, :]) / bw) ** 2)
    denom = W.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        pred = np.where(denom > 1e-12, (W * ys[None, :]).sum(axis=1) / denom, np.median(ys))
    out[mask] = pred[mask]
    out[~np.isfinite(z)] = float(np.median(ys))
    return out


def add_peer_metrics(d: pd.DataFrame, r: float) -> pd.DataFrame:
    """Định giá tương đối trong nhóm cùng cổ phiếu cơ sở.

    Gồm 3 lớp:
      1. `iv_smile` — IV "công bằng" theo đường cong biến động (smile) của nhóm CW
         cùng underlying, cùng mức moneyness/tenor. `iv_resid` = IV thực tế so với
         đường cong → CW đang đắt/rẻ tương đối.
      2. `fv_smile` — giá trị BS nếu CW được định giá bằng IV trên đường cong.
      3. `premium_be` so với trung vị nhóm.
    """
    out = d.copy()
    if out.empty:
        return out

    out["delta_option"] = pd.to_numeric(out["delta"], errors="coerce") * pd.to_numeric(
        out["ratio"], errors="coerce")

    out["peer_n"] = out.groupby("underlying", dropna=False)["close"].transform("size")

    iv = pd.to_numeric(out.get("iv"), errors="coerce")
    out["_iv"] = iv
    s_sum = out.groupby("underlying")["_iv"].transform("sum")
    s_cnt = out.groupby("underlying")["_iv"].transform("count")
    loo = (s_sum - iv.fillna(0)) / (s_cnt - iv.notna().astype(int)).replace(0, np.nan)
    out["peer_iv_median"] = loo.fillna(iv)

    T = pd.to_numeric(out.get("T"), errors="coerce").clip(lower=1e-6)
    S = pd.to_numeric(out.get("u_close"), errors="coerce")
    K = pd.to_numeric(out.get("K"), errors="coerce")
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.log(K / S) / np.sqrt(T)

    out["iv_smile"] = np.nan
    out["smile_r2"] = np.nan
    out["smile_source"] = "na"
    for _, idx in out.groupby("underlying", dropna=False).groups.items():
        zz = z.loc[idx].to_numpy(dtype=float)
        yy = iv.loc[idx].to_numpy(dtype=float)
        b, a, r2, source = _fit_smile(zz, yy)
        if source == "smile" and np.isfinite(r2) and r2 >= 0.15:
            fitted = np.clip(a + b * zz, 0.03, 4.0)
            out.loc[idx, "iv_smile"] = fitted
            out.loc[idx, "smile_r2"] = r2
            out.loc[idx, "smile_source"] = "smile"
        else:
            # Smile tuyến tính không giải thích được dữ liệu → dùng kernel làm mịn
            # theo moneyness (gần moneyness nào thì chịu ảnh hưởng của CW đó).
            out.loc[idx, "iv_smile"] = _kernel_smile(zz, yy)
            out.loc[idx, "smile_r2"] = r2
            out.loc[idx, "smile_source"] = "kernel" if np.isfinite(yy).sum() >= 3 else "median"

    out["peer_iv_median_iv"] = out["iv_smile"]
    out["iv_resid"] = np.where(
        out["iv_smile"].gt(0) & iv.notna(),
        (iv / out["iv_smile"] - 1.0) * 100.0, np.nan)

    out["peer_premium_median"] = out.groupby("underlying")["premium_be"].transform("median")
    out["peer_ivhv_median"] = out.groupby("underlying")["iv_vs_hv"].transform("median")

    sigma_peer = pd.to_numeric(out["iv_smile"], errors="coerce")
    valid = (sigma_peer > 0) & out["close"].gt(0) & out["K"].gt(0) & out["T"].gt(0)
    out["fv_smile"] = np.nan
    if valid.any():
        out.loc[valid, "fv_smile"] = price_vector(
            out.loc[valid, "u_close"], out.loc[valid, "K"], out.loc[valid, "T"], r,
            sigma_peer[valid], out.loc[valid, "ratio"], "call")
    out["fv_smile_upside"] = np.where(
        out["close"].gt(0) & out["fv_smile"].notna(),
        (out["fv_smile"] / out["close"] - 1.0) * 100.0, np.nan)
    out["fv_peer"] = out["fv_smile"]
    out["fv_peer_upside"] = out["fv_smile_upside"]
    out["fv_hv_upside"] = np.where(
        out["close"].gt(0) & out["bs_fv"].notna(),
        (out["bs_fv"] / out["close"] - 1.0) * 100.0, np.nan)
    out = out.drop(columns=["_iv"])
    return out


def build_snapshot(market: MarketData, panel: pd.DataFrame, asof: pd.Timestamp,
                   tolerance_days: int = 7) -> pd.DataFrame:
    """Mặt cắt tại `asof`: mỗi CW tối đa 1 dòng, kèm điểm và khuyến nghị."""
    sub = slice_asof(panel, asof, tolerance_days=tolerance_days)
    if sub.empty:
        return sub
    d = _pick(sub, SNAPSHOT_COLS)
    d["staleness_days"] = (pd.Timestamp(asof) - d["date"]).dt.days
    # Thanh khoản phải phản ánh phiên as-of, kể cả các phiên trắng sau lần khớp cuối
    d = liqmod.rebase_to_asof(d, panel, asof)

    # Metadata bổ sung từ master
    m = market.master.set_index("ticker")
    for col in ("issuer_name", "issue_date", "listing_date", "terms_adjusted",
                "listed_volume", "outstanding_volume", "price_vs", "be_vs",
                "moneyness_vs", "K_raw", "ratio_raw"):
        if col in m.columns:
            d[col] = d["ticker"].map(m[col])

    d = add_peer_metrics(d, market.risk_free)

    # Tỷ trọng giá trị giao dịch của issuer trong universe (rủi ro tập trung)
    tot = d["value_med20"].sum()
    if tot and np.isfinite(tot) and tot > 0:
        d["issuer_value_share"] = d.groupby("issuer")["value_med20"].transform("sum") / tot
    else:
        d["issuer_value_share"] = np.nan

    d = score_universe(d)
    return d.reset_index(drop=True)


def build_pit_snapshot(panel: pd.DataFrame, master: pd.DataFrame, asof: pd.Timestamp,
                       r: float) -> pd.DataFrame:
    """Mặt cắt point-in-time dùng cho backtest (không phụ thuộc MarketData).

    Chỉ giữ CW thực sự còn giao dịch tại `asof` theo điều khoản hợp đồng, và có
    dữ liệu giá không cũ hơn 7 ngày.
    """
    if panel.empty:
        return panel.iloc[0:0]
    sub = slice_asof(panel, asof, tolerance_days=7)
    if sub.empty:
        return sub
    m = master.set_index("ticker")
    keep = []
    for t in sub["ticker"]:
        if t not in m.index:
            continue
        row = m.loc[t]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        first, last, mat = row.get("first_trade"), row.get("last_trade"), row.get("maturity")
        if pd.notna(first) and asof < first - pd.Timedelta(days=3):
            continue
        if pd.notna(last) and asof > last + pd.Timedelta(days=1):
            continue
        if pd.notna(mat) and asof >= mat:
            continue
        keep.append(t)
    sub = sub[sub["ticker"].isin(set(keep))].copy()
    if sub.empty:
        return sub
    sub["tier_id"] = np.arange(len(sub))
    sub = add_peer_metrics(_pick(sub, SNAPSHOT_COLS + ["tier_id"]), r)
    sub["staleness_days"] = (pd.Timestamp(asof) - sub["date"]).dt.days
    sub = liqmod.rebase_to_asof(sub, panel, asof)
    return score_universe(sub).reset_index(drop=True)
