"""Sinh toàn bộ artifact JSON cho dashboard CW Intelligence.

Artifact được tách nhỏ để trang tĩnh tải nhanh trên GitHub Pages:

    docs/data/meta.json            metadata, độ mới dữ liệu, cảnh báo
    docs/data/market.json          tổng quan thị trường, heatmap, top lists, breadth
    docs/data/screener.json        toàn bộ CW + chỉ số + điểm (cho screener)
    docs/data/recommendations.json recommendation card đầy đủ (active)
    docs/data/underlyings.json     phân tích cổ phiếu cơ sở
    docs/data/backtest.json        kết quả walk-forward + độ nhạy
    docs/data/liquidity.json       mặt cắt thanh khoản, cảnh báo, phân bố theo nhà phát hành
    docs/data/quality.json         báo cáo chất lượng dữ liệu
    docs/data/methodology.json     công thức, trọng số, định nghĩa
    docs/data/series/cw/<T>.json   chuỗi giá + chỉ báo của từng CW
    docs/data/series/und/<U>.json  chuỗi giá + chỉ báo của cổ phiếu cơ sở
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import METHODOLOGY_VERSION, __version__, config, lifecycle, liquidity as liq, sessions
from .rights import PublicationNotAuthorized, assert_public_output_allowed
from .backtest import History, build_signals, rebalance_dates, run_backtest
from .data import MarketData, load_market_data
from .panels import build_cw_panel, build_underlying_features, slice_asof
from .quality import run_quality_checks
from .recommend import build_cards
from .snapshot import build_snapshot

ICT = timezone(timedelta(hours=7))


# ──────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────
def _clean(value):
    """Chuyển NaN/Inf/numpy scalar thành JSON-safe."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else round(value, 6)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d")
    if value is pd.NaT:
        return None
    return value


def _write(path: Path, payload) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(_clean(payload), ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False)
    path.write_text(data, encoding="utf-8")
    return len(data.encode("utf-8"))


def _f(value, nd=2):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return round(v, nd)


def _on_date(value, asof: pd.Timestamp | None) -> bool | None:
    """Dòng có khớp lệnh đúng phiên `asof` không (None nếu thiếu dữ liệu)."""
    if asof is None or value is None or value is pd.NaT:
        return None
    try:
        return pd.Timestamp(value).normalize() == asof
    except (TypeError, ValueError):
        return None


def _days_since(value, asof: pd.Timestamp | None) -> int | None:
    """Số ngày kể từ `value` tới `asof` (None nếu thiếu dữ liệu)."""
    if asof is None or value is None or value is pd.NaT:
        return None
    try:
        return int((asof - pd.Timestamp(value).normalize()).days)
    except (TypeError, ValueError):
        return None


def _pct_change(series: pd.Series, n: int = 1):
    if len(series) <= n:
        return None
    prev = series.iloc[-1 - n]
    last = series.iloc[-1]
    if not prev:
        return None
    return _f((last / prev - 1) * 100, 2)


# ──────────────────────────────────────────────────────────────────
# SCREENER / SNAPSHOT
# ──────────────────────────────────────────────────────────────────
def snapshot_payload(snap: pd.DataFrame, asof: pd.Timestamp | None = None) -> list[dict]:
    asof = pd.Timestamp(asof).normalize() if asof is not None else None
    rows = []
    for _, r in snap.iterrows():
        rows.append({
            "t": r.get("ticker"),
            "u": r.get("underlying"),
            "iss": r.get("issuer"),
            "issName": r.get("issuer_name"),
            "active": bool(r.get("is_active")),
            "state": r.get("lifecycle_state") or "listed",
            "tradedOn": _on_date(r.get("date"), asof),
            "daysSince": _days_since(r.get("date"), asof),
            "date": r.get("date"),
            "price": _f(r.get("close"), 1),
            "chg1": _f(pd.to_numeric(r.get("ret1"), errors="coerce") * 100, 2)
            if pd.notna(r.get("ret1")) else None,
            "ret5": _f(pd.to_numeric(r.get("ret5"), errors="coerce") * 100, 2)
            if pd.notna(r.get("ret5")) else None,
            "ret21": _f(pd.to_numeric(r.get("ret21"), errors="coerce") * 100, 2)
            if pd.notna(r.get("ret21")) else None,
            "S": _f(r.get("u_close"), 0),
            "K": _f(r.get("K"), 0),
            "ratio": _f(r.get("ratio"), 4),
            "mat": r.get("maturity"),
            "dte": int(r["days_to_maturity"]) if pd.notna(r.get("days_to_maturity")) else None,
            "money": r.get("moneyness"),
            "moneyPct": _f(r.get("moneyness_pct"), 2),
            "intrinsic": _f(r.get("intrinsic"), 1),
            "timeValue": _f(r.get("time_value"), 1),
            "premium": _f(r.get("premium_be"), 2),
            "premiumTime": _f(r.get("premium_time"), 2),
            "be": _f(r.get("breakeven"), 0),
            "beDist": _f(r.get("be_distance_pct"), 2),
            "gearing": _f(r.get("gearing_gross"), 2),
            "effGear": _f(r.get("eff_gearing"), 2),
            "delta": _f(r.get("delta"), 4),
            "deltaOpt": _f(r.get("delta_option"), 3),
            "gamma": _f(r.get("gamma"), 6),
            "theta": _f(r.get("theta"), 3),
            "thetaPct": _f(r.get("theta_pct"), 3),
            "vega": _f(r.get("vega"), 2),
            "fvSmile": _f(r.get("fv_smile"), 1),
            "fvHv": _f(r.get("bs_fv"), 1),
            "upsideSmile": _f(r.get("fv_smile_upside"), 1),
            "upsideHv": _f(r.get("fv_hv_upside"), 1),
            "sigma": _f(r.get("sigma"), 4),
            "iv": _f(r.get("iv"), 4),
            "ivVsHv": _f(r.get("iv_vs_hv"), 1),
            "ivResid": _f(r.get("iv_resid"), 1),
            "ivRank": _f(r.get("iv_rank"), 1),
            "ivQuality": r.get("iv_quality"),
            "vol": _f(r.get("volume"), 0),
            "value": _f(r.get("value"), 0),
            "value20": _f(r.get("value_med20"), 0),
            "traded20": _f(pd.to_numeric(r.get("traded_ratio20"), errors="coerce") * 100, 1)
            if pd.notna(r.get("traded_ratio20")) else None,
            "volAccel": _f(r.get("volume_accel"), 2),
            "adv20": _f(r.get("adv20"), 0),
            "adv5": _f(r.get("adv5"), 0),
            "cov20": _f(r.get("coverage20"), 1),
            "covList": _f(r.get("coverage_listing"), 1),
            "listedSessions": _f(r.get("sessions_listed"), 0),
            "zero20": _f(r.get("zero20"), 0),
            "amihud": _f(r.get("amihud20"), 2),
            "range20": _f(r.get("range20"), 2),
            "turnover": _f(r.get("turnover20"), 2),
            "liqTrend": _f(r.get("liq_trend"), 2),
            "dtl": _f(r.get("dtl_50m"), 1),
            "impact": _f(r.get("impact_50m_pct"), 2),
            "liqBucket": liq.liquidity_bucket(r),
            "rsi": _f(r.get("rsi14"), 1),
            "macdH": _f(r.get("macd_hist"), 4),
            "ma20": _f(r.get("ma20"), 1),
            "ma50": _f(r.get("ma50"), 1),
            "above20": _f(r.get("above_ma20"), 0),
            "above50": _f(r.get("above_ma50"), 0),
            "breakout": _f(r.get("breakout20"), 0),
            "atr": _f(r.get("atr14"), 2),
            "atrPct": _f(r.get("atr_pct"), 2),
            "sessions": int(r["sessions"]) if pd.notna(r.get("sessions")) else 0,
            "uRet21": _f(pd.to_numeric(r.get("u_ret21"), errors="coerce") * 100, 2)
            if pd.notna(r.get("u_ret21")) else None,
            "uRet63": _f(pd.to_numeric(r.get("u_ret63"), errors="coerce") * 100, 2)
            if pd.notna(r.get("u_ret63")) else None,
            "uRsi": _f(r.get("u_rsi14"), 1),
            "uAbove50": _f(r.get("u_above_ma50"), 0),
            "uHv": _f(r.get("u_hv252"), 4),
            "score": _f(r.get("score"), 1),
            "dq": _f(r.get("data_quality"), 3),
            "rec": r.get("recommendation"),
            "recReason": r.get("rec_reason"),
            "sc": {k: _f(r.get(f"s_{k}"), 1) for k in config.SCORE_WEIGHTS},
            "stale": int(r["staleness_days"]) if pd.notna(r.get("staleness_days")) else None,
            "issShare": _f(r.get("issuer_value_share"), 3),
            "termsAdj": bool(r.get("terms_adjusted")) if pd.notna(r.get("terms_adjusted")) else False,
        })
    return rows


# ──────────────────────────────────────────────────────────────────
# MARKET
# ──────────────────────────────────────────────────────────────────
def _top_lists(active: pd.DataFrame) -> dict:
    def _row(r):
        return {"t": r["ticker"], "u": r.get("underlying"), "iss": r.get("issuer"),
                "chg": _f(pd.to_numeric(r.get("ret1"), errors="coerce") * 100, 2),
                "price": _f(r.get("close"), 1), "value": _f(r.get("value_med20"), 0),
                "score": _f(r.get("score"), 1), "rec": r.get("recommendation"),
                "premium": _f(r.get("premium_be"), 1)}

    liquid = active[active["value_med20"].fillna(0) >= 5_000_000]
    gain = liquid.sort_values("ret1", ascending=False).head(10)
    lose = liquid.sort_values("ret1", ascending=True).head(10)
    value = liquid.sort_values("value_med20", ascending=False).head(10)
    accel = liquid.dropna(subset=["volume_accel"]).sort_values("volume_accel", ascending=False).head(10)
    unusual = liquid.assign(absret=liquid["ret1"].abs()).sort_values("absret", ascending=False).head(10)
    return {
        "gainers": [_row(r) for _, r in gain.iterrows()],
        "losers": [_row(r) for _, r in lose.iterrows()],
        "value": [_row(r) for _, r in value.iterrows()],
        "liquidity_improving": [_row(r) for _, r in accel.iterrows()],
        "unusual": [_row(r) for _, r in unusual.iterrows()],
    }


def _breadth_history(panel: pd.DataFrame, days: int = 250) -> list[dict]:
    """Lịch sử độ rộng thị trường tính từ panel (không dùng điểm để tránh tốn thời gian)."""
    if panel.empty:
        return []
    work = panel[panel["value_med20"].fillna(0) >= 1_000_000]
    g = work.groupby("date")
    agg = g.agg(
        n=("ticker", "size"),
        up=("ret1", lambda s: int((pd.to_numeric(s, errors="coerce") > 0).sum())),
        down=("ret1", lambda s: int((pd.to_numeric(s, errors="coerce") < 0).sum())),
        value=("value", "sum"),
        premium=("premium_be", "median"),
        iv=("iv", "median"),
        dte=("days_to_maturity", "median"),
    ).sort_index().tail(days)
    out = []
    for d, r in agg.iterrows():
        out.append({
            "date": d.strftime("%Y-%m-%d"),
            "n": int(r["n"]), "up": int(r["up"]), "down": int(r["down"]),
            "value": _f(r["value"], 0), "premium": _f(r["premium"], 2),
            "iv": _f(r["iv"], 4), "dte": _f(r["dte"], 0),
        })
    return out


def market_payload(snap: pd.DataFrame, panel: pd.DataFrame, asof: pd.Timestamp,
                   life: dict | None = None) -> dict:
    active = snap[snap["is_active"]].copy() if "is_active" in snap else snap
    if active.empty:
        return {"asof": asof, "kpi": {}, "heatmap": [], "by_issuer": [], "by_underlying": [],
                "top": {}, "breadth": []}

    ret1 = pd.to_numeric(active["ret1"], errors="coerce")
    value = pd.to_numeric(active["value"], errors="coerce").fillna(0)
    volume = pd.to_numeric(active["volume"], errors="coerce").fillna(0)
    premium = pd.to_numeric(active["premium_be"], errors="coerce")
    score = pd.to_numeric(active["score"], errors="coerce")
    dte = pd.to_numeric(active["days_to_maturity"], errors="coerce")
    money = active["moneyness"].astype(str)

    def _group(col):
        out = []
        for key, g in active.groupby(col, dropna=False):
            out.append({
                "key": str(key),
                "count": int(len(g)),
                "value": _f(pd.to_numeric(g["value"], errors="coerce").fillna(0).sum(), 0),
                "volume": _f(pd.to_numeric(g["volume"], errors="coerce").fillna(0).sum(), 0),
                "avgPremium": _f(pd.to_numeric(g["premium_be"], errors="coerce").median(), 2),
                "avgScore": _f(pd.to_numeric(g["score"], errors="coerce").mean(), 1),
                "up": int((pd.to_numeric(g["ret1"], errors="coerce") > 0).sum()),
                "down": int((pd.to_numeric(g["ret1"], errors="coerce") < 0).sum()),
            })
        return sorted(out, key=lambda x: -x["count"])

    lc = (life or {}).get("counts", {}) or {}
    traded_on = int(lc.get("traded", len(active)))
    kpi = {
        "active": int(len(active)),
        "traded": traded_on,
        "listed": int(lc.get("listed", len(active))),
        "notTraded": int(lc.get("notTraded", max(int(len(active)) - traded_on, 0))),
        "matured": int(lc.get("matured", 0)),
        "maturedRecent": int(lc.get("maturedRecent", 0)),
        "newListings": int(lc.get("newListings", 0)),
        "delistedEarly": int(lc.get("delistedEarly", 0)),
        "pending": int(lc.get("pending", 0)),
        "total": int(lc.get("total", len(snap))),
        "expired": int(lc.get("expired", 0)),
        "up": int((ret1 > 0).sum()),
        "down": int((ret1 < 0).sum()),
        "flat": int((ret1 == 0).sum()),
        # Phiên giao dịch đầu tiên chưa có giá kỳ trước; không gom thiếu dữ liệu vào flat.
        "noReturnData": int(ret1.isna().sum()),
        "totalValue": _f(value.sum(), 0),
        "totalVolume": _f(volume.sum(), 0),
        "itm": int((money == "ITM").sum()),
        "atm": int((money == "ATM").sum()),
        "otm": int((money == "OTM").sum()),
        "liquid": int((pd.to_numeric(active["value_med20"], errors="coerce")
                       >= config.HIGH_LIQUIDITY_VALUE_VND).sum()),
        "positiveRec": int(active["recommendation"].isin(["BUY", "STRONG_BUY"]).sum()),
        "strongBuy": int((active["recommendation"] == "STRONG_BUY").sum()),
        "avgPremium": _f(premium.mean(), 2),
        "medianPremium": _f(premium.median(), 2),
        "avgScore": _f(score.mean(), 1),
        "medianScore": _f(score.median(), 1),
        "avgIv": _f(pd.to_numeric(active["iv"], errors="coerce").median(), 4),
        "avgHv": _f(pd.to_numeric(active["sigma"], errors="coerce").median(), 4),
        "avgDte": _f(dte.median(), 0),
        "issuers": int(active["issuer"].nunique()),
        "underlyings": int(active["underlying"].nunique()),
        "scoreAbove65": int((score >= 65).sum()),
        "noData": int((active["recommendation"] == "NO_DATA").sum()),
    }

    heat = []
    for _, r in active.iterrows():
        heat.append({
            "t": r["ticker"], "u": r.get("underlying"), "iss": r.get("issuer"),
            "chg": _f(pd.to_numeric(r.get("ret1"), errors="coerce") * 100, 2),
            "value": _f(r.get("value_med20"), 0), "volume": _f(r.get("volume"), 0),
            "score": _f(r.get("score"), 1), "rec": r.get("recommendation"),
            "money": r.get("moneyness"), "premium": _f(r.get("premium_be"), 1),
            "iv": _f(r.get("iv"), 3), "dte": int(r["days_to_maturity"])
            if pd.notna(r.get("days_to_maturity")) else None,
            "price": _f(r.get("close"), 1),
        })

    hist_score = pd.to_numeric(active["score"], errors="coerce").dropna()
    hist_prem = premium.dropna()

    return {
        "asof": asof,
        "kpi": kpi,
        "by_issuer": _group("issuer"),
        "by_underlying": _group("underlying"),
        "top": _top_lists(active),
        "heatmap": heat,
        "distributions": {
            "score": [int(((hist_score >= lo) & (hist_score < hi)).sum())
                      for lo, hi in [(0, 30), (30, 45), (45, 65), (65, 80), (80, 101)]],
            "premium": [int(((hist_prem >= lo) & (hist_prem < hi)).sum())
                        for lo, hi in [(-100, 0), (0, 10), (10, 20), (20, 30), (30, 50), (50, 1000)]],
            "rec": {k: int(v) for k, v in active["recommendation"].value_counts().items()},
        },
        "breadth": _breadth_history(panel),
    }


# ──────────────────────────────────────────────────────────────────
# SERIES
# ──────────────────────────────────────────────────────────────────
def cw_series_payload(panel: pd.DataFrame, master: pd.DataFrame, limit: int = 420) -> dict:
    out = {}
    meta = master.set_index("ticker")
    for ticker, g in panel.groupby("ticker", sort=False):
        g = g.sort_values("date").tail(limit)
        if g.empty:
            continue
        out[ticker] = {
            "ticker": ticker,
            "dates": [d.strftime("%d/%m/%Y") for d in g["date"]],
            "o": [_f(v, 3) for v in g["open"]],
            "h": [_f(v, 3) for v in g["high"]],
            "l": [_f(v, 3) for v in g["low"]],
            "c": [_f(v, 3) for v in g["close"]],
            "v": [_f(v, 0) for v in g["volume"]],
            "adv": [_f(v, 0) for v in g["adv20"]] if "adv20" in g else [],
            "cov": [_f(v, 1) for v in g["coverage20"]] if "coverage20" in g else [],
            "und": [_f(v, 0) for v in g["u_close"]],
            "ma20": [_f(v, 3) for v in g["ma20"]],
            "ma50": [_f(v, 3) for v in g["ma50"]],
            "rsi": [_f(v, 1) for v in g["rsi14"]],
            "macd": [_f(v, 4) for v in g["macd_hist"]],
            "premium": [_f(v, 2) for v in g["premium_be"]],
            "iv": [_f(v, 4) for v in g["iv"]],
            "sigma": [_f(v, 4) for v in g["sigma"]],
            "deltaOpt": [_f(v, 4) for v in g["delta_option"]] if "delta_option" in g else [],
            "fv": [_f(v, 2) for v in g["bs_fv"]],
        }
    return out


def und_series_payload(und_feat: pd.DataFrame, limit: int = 500) -> dict:
    out = {}
    for sym, g in und_feat.groupby("ticker", sort=False):
        g = g.sort_values("date").tail(limit)
        if g.empty:
            continue
        out[sym] = {
            "ticker": sym,
            "dates": [d.strftime("%d/%m/%Y") for d in g["date"]],
            "c": [_f(v, 2) for v in g["close"]],
            "ma20": [_f(v, 2) for v in g["ma20"]],
            "ma50": [_f(v, 2) for v in g["ma50"]],
            "ma200": [_f(v, 2) for v in g["ma200"]],
            "rsi": [_f(v, 1) for v in g["rsi14"]],
            "macd": [_f(v, 4) for v in g["macd_hist"]],
            "hv20": [_f(v, 4) for v in g["hv20"]],
            "hv60": [_f(v, 4) for v in g["hv60"]],
            "v": [_f(v, 0) for v in g["vol"] if "vol" in g] if "vol" in g else [],
        }
    return out


def underlying_summary(und_feat: pd.DataFrame, snap: pd.DataFrame) -> list[dict]:
    out = []
    active = snap[snap["is_active"]] if "is_active" in snap else snap
    for sym, g in und_feat.groupby("ticker", sort=False):
        g = g.sort_values("date")
        last = g.iloc[-1]
        peers = active[active["underlying"] == sym]
        best = peers.sort_values("score", ascending=False).head(1)
        out.append({
            "u": sym,
            "close": _f(last["close"], 0),
            "ret1": _f(last["ret1"] * 100, 2),
            "ret5": _f(last["ret5"] * 100, 2),
            "ret21": _f(last["ret21"] * 100, 2),
            "ret63": _f(last["ret63"] * 100, 2),
            "rsi": _f(last["rsi14"], 1),
            "ma20": _f(last["ma20"], 0),
            "ma50": _f(last["ma50"], 0),
            "ma200": _f(last["ma200"], 0),
            "above20": _f(last["close"] / last["ma20"] - 1, 4) if pd.notna(last["ma20"]) else None,
            "hv20": _f(last["hv20"], 4),
            "hv60": _f(last["hv60"], 4),
            "hv252": _f(last["hv252"], 4),
            "distHigh60": _f(last["dist_high60"] * 100, 2),
            "nCw": int(len(peers)),
            "avgScore": _f(pd.to_numeric(peers["score"], errors="coerce").mean(), 1) if len(peers) else None,
            "bestCw": best.iloc[0]["ticker"] if len(best) else None,
            "bestScore": _f(best.iloc[0]["score"], 1) if len(best) else None,
        })
    return sorted(out, key=lambda x: -(x["ret21"] or -999))


def score_history(panel: pd.DataFrame, market: MarketData, months: int = 24) -> dict:
    """Lịch sử điểm theo tháng cho từng CW (dùng cho tab lịch sử khuyến nghị)."""
    history = History(panel)
    asof = market.asof
    dates = []
    for i in range(months):
        d = (asof - pd.DateOffset(months=i)).normalize()
        pos = np.searchsorted(history.dates, np.datetime64(d), side="right") - 1
        if pos >= 0:
            dates.append(pd.Timestamp(history.dates[pos]))
    dates = sorted(set(dates))
    if not dates:
        return {}
    signals = build_signals(history, dates, market.risk_free, config.BACKTEST)
    out: dict[str, list] = {}
    for t, snap in signals.items():
        for _, row in snap.iterrows():
            if pd.isna(row.get("score")):
                continue
            out.setdefault(row["ticker"], []).append({
                "date": t.strftime("%Y-%m-%d"),
                "score": _f(row.get("score"), 1),
                "rec": row.get("recommendation"),
                "price": _f(row.get("close"), 1),
            })
    return out


# ──────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────
def build_all(out_dir: Path | None = None, run_bt: bool = True,
              asof: pd.Timestamp | None = None, verbose: bool = True) -> dict:
    t0 = time.time()
    out_dir = Path(out_dir) if out_dir else config.DATA_DIR
    # Fail before loading or writing anything when the destination is GitHub Pages.
    assert_public_output_allowed(out_dir)
    market = load_market_data(asof)
    asof = market.asof

    def log(msg):
        if verbose:
            print(f"[cwintel] {msg}", flush=True)

    log(f"asof={asof.date()} | risk_free={market.risk_free:.4%} ({market.risk_free_source})")
    und_feat = build_underlying_features(market.underlying)
    panel, iv_hist = build_cw_panel(market, und_feat)
    log(f"panel={len(panel):,} rows | {panel['ticker'].nunique()} CW | "
        f"{len(iv_hist):,} quan sát IV")

    if "delta_option" not in panel.columns:
        panel["delta_option"] = panel["delta"] * panel["ratio"]

    snap = build_snapshot(market, panel, asof, tolerance_days=14)
    life_payload = lifecycle.payload(market.master, asof, panel=panel)
    log(f"snapshot={len(snap)} CW | rec={snap['recommendation'].value_counts().to_dict()}")
    log("lifecycle: " + ", ".join(f"{k}={v}" for k, v in life_payload["counts"].items())
        + f" | identity={'OK' if life_payload['identity']['ok'] else 'LỆCH'}")

    # ── files
    sizes = {}
    sizes["market.json"] = _write(out_dir / "market.json",
                                  market_payload(snap, panel, asof, life=life_payload))
    sizes["lifecycle.json"] = _write(out_dir / "lifecycle.json", life_payload)
    screener_rows = snapshot_payload(snap, asof)

    # CW đã đáo hạn / ngừng giao dịch / chờ niêm yết: lấy dòng cuối trong panel để
    # tham chiếu (không chấm điểm, không vào snapshot)
    cls = lifecycle.classify(market.master, asof, panel=panel)
    expired = market.master[~market.master["is_active"]].copy()
    state_by_ticker = dict(zip(cls["ticker"], cls["state"])) if len(cls) else {}
    since_by_ticker = dict(zip(cls["ticker"], cls["days_since_print"])) if len(cls) else {}
    last_rows = slice_asof(panel, asof, tolerance_days=10_000)
    last_by_ticker = last_rows.set_index("ticker")

    expired_rows = []
    for _, m in expired.iterrows():
        t = m["ticker"]
        state = state_by_ticker.get(t, "matured")
        base = {
            "t": t, "u": m["underlying"], "iss": m["issuer"], "issName": m["issuer_name"],
            "active": False, "state": state,
            "daysSince": (
                int(-m["days_to_maturity"]) if state == "matured" and pd.notna(m["days_to_maturity"])
                else (int(since_by_ticker[t]) if since_by_ticker.get(t) is not None
                      and pd.notna(since_by_ticker.get(t)) else None)
            ),
            "tradedOn": False,
            "date": m["last_trade"], "mat": m["maturity"],
            "K": _f(m["K"], 0), "ratio": _f(m["ratio"], 4),
            "money": m.get("moneyness_vs"), "dte": int(m["days_to_maturity"])
            if pd.notna(m["days_to_maturity"]) else None,
        }
        if t in last_by_ticker.index:
            r = last_by_ticker.loc[t]
            if isinstance(r, pd.DataFrame):
                r = r.iloc[-1]
            base.update({
                "date": r["date"],
                "price": _f(r.get("close"), 1),
                "S": _f(r.get("u_close"), 0),
                "premium": _f(r.get("premium_be"), 2),
                "iv": _f(r.get("iv"), 4),
                "sigma": _f(r.get("sigma"), 4),
                "deltaOpt": _f(r.get("delta"), 4) * (r.get("ratio") or 1),
                "value20": _f(r.get("value_med20"), 0),
                "sessions": int(r["sessions"]) if pd.notna(r.get("sessions")) else 0,
                "lastRet": _f(r.get("ret1") * 100, 2) if pd.notna(r.get("ret1")) else None,
            })
        expired_rows.append(base)

    sizes["screener.json"] = _write(out_dir / "screener.json", {
        "asof": asof.strftime("%Y-%m-%d"),
        "active": screener_rows,
        "expired": expired_rows,
    })
    log(f"screener: {len(screener_rows)} active + {len(expired_rows)} expired")

    # ── thanh khoản (mặt cắt hiện tại; bằng chứng theo thời gian nằm trong backtest.json)
    liq_payload = liq.liquidity_summary(snap)
    liq_payload["universeFlags"] = {
        t: {"t": t, "u": r.get("underlying"), "iss": r.get("issuer"),
            "adv20": _f(r.get("adv20"), 0), "cov20": _f(r.get("coverage20"), 1),
            "zero20": _f(r.get("zero20"), 0), "amihud": _f(r.get("amihud20"), 2),
            "range20": _f(r.get("range20"), 2), "dtl": _f(r.get("dtl_50m"), 1),
            "bucket": liq.liquidity_bucket(r), "rec": r.get("recommendation"),
            "score": _f(r.get("score"), 1)}
        for t, r in snap.set_index("ticker").iterrows()
    }
    # CW đang niêm yết nhưng KHÔNG có giao dịch trong 14 phiên → không vào snapshot
    listed = market.master[market.master["is_active"]].copy()
    snap_set = set(snap["ticker"])
    last_seen = slice_asof(panel, asof, tolerance_days=10_000).set_index("ticker")
    idle = []
    for _, m in listed.iterrows():
        if m["ticker"] in snap_set:
            continue
        last_date = last_seen.loc[m["ticker"], "date"] if m["ticker"] in last_seen.index else None
        idle.append({
            "t": m["ticker"], "u": m["underlying"], "iss": m["issuer"],
            "lastDate": last_date.strftime("%Y-%m-%d") if last_date is not None else None,
            "daysSince": int((asof - last_date).days) if last_date is not None else None,
        })
    liq_payload["idle"] = sorted(idle, key=lambda d: -(d["daysSince"] or 0))
    liq_payload["kpi"]["listedActive"] = int(len(listed))
    liq_payload["kpi"]["idleCount"] = len(idle)
    liq_payload["kpi"]["idleSharePct"] = round(len(idle) / max(1, len(listed)) * 100, 1)
    liq_payload["gates"] = config.GATES
    liq_payload["thresholds"] = {
        "participation": liq.PARTICIPATION_RATE,
        "positionVnd": liq.DEFAULT_POSITION_VND,
        "impactEta": liq.IMPACT_ETA,
        "minAdvWarn": liq.MIN_ADV_WARN,
        "minCoverageWarn": liq.MIN_COVERAGE_WARN,
        "maxDtlWarn": liq.MAX_DTL_WARN,
        "maxRangeWarn": liq.MAX_RANGE_WARN,
    }
    sizes["liquidity.json"] = _write(out_dir / "liquidity.json", liq_payload)
    log(f"liquidity: ADV20 median {liq_payload['kpi']['advMedian']}, "
        f"coverage median {liq_payload['kpi']['coverageMedian']}%")

    # ── recommendations
    cards = build_cards(snap, market.risk_free)
    cards_sorted = sorted(cards, key=lambda c: -(c.get("score") or -1))
    sizes["recommendations.json"] = _write(out_dir / "recommendations.json", {
        "asof": asof.strftime("%Y-%m-%d"),
        "cards": cards_sorted,
        "thresholds": [{"min": th, "label": lb,
                        "label_vi": config.REC_LABELS_VI.get(lb, lb)}
                       for th, lb in config.REC_THRESHOLDS],
        "gates": config.GATES,
    })
    log(f"recommendations: {len(cards_sorted)} cards")

    # ── underlyings
    sizes["underlyings.json"] = _write(out_dir / "underlyings.json", {
        "asof": asof.strftime("%Y-%m-%d"),
        "items": underlying_summary(und_feat, snap),
    })
    und_series = und_series_payload(und_feat)
    for sym, payload in und_series.items():
        sizes[f"series/und/{sym}.json"] = _write(out_dir / "series" / "und" / f"{sym}.json",
                                                 payload)
    log(f"underlyings: {len(und_series)} series")

    # ── score history + CW series
    hist = score_history(panel, market, months=24)
    cw_series = cw_series_payload(panel, market.master)
    # Chỉ xuất chuỗi cho CW đang giao dịch hoặc có dữ liệu trong 12 tháng gần nhất
    last_seen = panel.groupby("ticker")["date"].max()
    keep_series = {t for t, d in last_seen.items()
                   if d >= asof - pd.Timedelta(days=365)}
    keep_series |= set(market.master.loc[market.master["is_active"], "ticker"])
    cw_series = {t: v for t, v in cw_series.items() if t in keep_series}
    meta_series = sorted(cw_series)
    for ticker, payload in cw_series.items():
        if ticker in hist:
            payload["scoreHistory"] = hist[ticker]
        sizes[f"series/cw/{ticker}.json"] = _write(
            out_dir / "series" / "cw" / f"{ticker}.json", payload)
    # Dọn các file chuỗi cũ không còn thuộc vũ trụ xuất bản (tránh phình docs/data)
    cw_dir = out_dir / "series" / "cw"
    keep_files = {f"{t}.json" for t in cw_series}
    removed = 0
    if cw_dir.exists():
        for f in cw_dir.glob("*.json"):
            if f.name not in keep_files:
                f.unlink()
                removed += 1
    keep_und = {f"{u}.json" for u in und_series}
    und_dir = out_dir / "series" / "und"
    if und_dir.exists():
        for f in und_dir.glob("*.json"):
            if f.name not in keep_und:
                f.unlink()
                removed += 1
    log(f"series: {len(cw_series)} CW files ({removed} stale removed)")

    # ── độ mới của dữ liệu: so asof với phiên đã đóng gần nhất (giờ ICT)
    session = sessions.session_status(asof)
    if session["lagSessions"]:
        log(f"session: dữ liệu dừng ở {session['asofLabel']}, thiếu "
            f"{session['lagSessions']} phiên tới {session['expectedLabel']}")
    else:
        log(f"session: dữ liệu đã tới phiên {session['asofLabel']}")

    # ── quality report
    quality = run_quality_checks(market, panel, snap, life=life_payload, session=session)
    sizes["quality.json"] = _write(out_dir / "quality.json", quality)
    log(f"quality: {quality['summary']['error']} errors, "
        f"{quality['summary']['warn']} warnings")

    # ── backtest
    backtest_path = out_dir / "backtest.json"
    if run_bt:
        log("running walk-forward backtest ...")
        bt = run_backtest(panel, market)
        bt["generated_at"] = datetime.now(ICT).strftime("%d/%m/%Y %H:%M +07:00")
        sizes["backtest.json"] = _write(backtest_path, bt)
        log(f"backtest done: {bt['n_trades_total']} trades, "
            f"{bt['summary']['score_top'].get('total_return_pct')}% total")
    elif backtest_path.exists():
        log("skip backtest (giữ file cũ)")

    # ── methodology (tĩnh, có version)
    from .methodology import methodology_payload
    sizes["methodology.json"] = _write(out_dir / "methodology.json",
                                       methodology_payload())

    # ── meta
    data_age = (datetime.now(ICT).date() - asof.date()).days
    meta = {
        "product": "CW Intelligence",
        "version": __version__,
        "methodologyVersion": METHODOLOGY_VERSION,
        "generatedAt": datetime.now(ICT).strftime("%d/%m/%Y %H:%M:%S +07:00"),
        "asof": asof.strftime("%Y-%m-%d"),
        "asofLabel": asof.strftime("%d/%m/%Y"),
        "dataAgeDays": int(data_age),
        "dataAgeSessions": int(session["lagSessions"]),
        "expectedAsOf": session["expected"],
        "expectedAsOfLabel": session["expectedLabel"],
        "session": session,
        # Lịch nghỉ cho đồng hồ topbar (2027 là dự kiến — xem config.MARKET_HOLIDAYS)
        "marketHolidays": sorted(config.MARKET_HOLIDAYS),
        "stale": bool(session["lagSessions"] >= 2
                      or data_age > config.STALE_DATA_DAYS_WARNING),
        "universe": {
            # Nguồn duy nhất: cwintel.lifecycle — tổng luôn khớp tổng các trạng thái.
            "total": int(life_payload["counts"]["total"]),
            "listed": int(life_payload["counts"]["listed"]),
            "traded": int(life_payload["counts"]["traded"]),
            "notTraded": int(life_payload["counts"]["notTraded"]),
            "expired": int(life_payload["counts"]["expired"]),
            "matured": int(life_payload["counts"]["matured"]),
            "delistedEarly": int(life_payload["counts"]["delistedEarly"]),
            "pending": int(life_payload["counts"]["pending"]),
            "unknown": int(life_payload["counts"]["unknown"]),
            "maturedRecent": int(life_payload["counts"]["maturedRecent"]),
            "newListings": int(life_payload["counts"]["newListings"]),
            "active": int(life_payload["counts"]["traded"]),
            "underlyings": int(market.master["underlying"].nunique()),
            "issuers": int(market.master["issuer"].nunique()),
        },
        "riskFree": {
            "value": round(float(market.risk_free), 5),
            "source": market.risk_free_source,
            "date": market.risk_free_date.strftime("%Y-%m-%d") if market.risk_free_date else None,
        },
        "dataSources": [
            "Nguồn do người dùng cấu hình; xem provenance/terms của dữ liệu đầu vào",
            "Kiểm tra điều khoản hiện hành trước khi sử dụng hoặc chia sẻ kết quả",
        ],
        "files": {k: v for k, v in sorted(sizes.items()) if not k.startswith("series/")},
        "seriesTickers": meta_series,
        "seriesBytes": int(sum(v for k, v in sizes.items() if k.startswith("series/"))),
        "counts": {
            "panelRows": int(len(panel)),
            "cwWithPrice": int(panel["ticker"].nunique()),
            "ivObservations": int(len(iv_hist)),
            "scored": int(snap["score"].notna().sum()),
            "cards": len(cards_sorted),
            "series": len(meta_series),
            "advBelow5m": liq_payload["kpi"]["flagged"]["advBelow5m"],
            "coverageBelow50": liq_payload["kpi"]["flagged"]["coverageBelow50"],
        },
        "warnings": quality.get("headline", []),
        "buildSeconds": round(time.time() - t0, 1),
    }
    sizes["meta.json"] = _write(out_dir / "meta.json", meta)
    log(f"meta written. total {sum(sizes.values())/1e6:.2f} MB in {time.time()-t0:.1f}s")
    return {"meta": meta, "sizes": sizes, "snapshot": snap, "panel": panel,
            "market": market, "quality": quality}


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m cwintel.build [--asof YYYY-MM-DD] [--no-backtest] [--out DIR] [-q]"""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m cwintel.build",
        description="Dựng toàn bộ artifact JSON cho dashboard CW Intelligence.",
    )
    parser.add_argument("--asof", help="phiên dữ liệu (YYYY-MM-DD), mặc định phiên mới nhất")
    parser.add_argument("--no-backtest", action="store_true", help="bỏ backtest (nhanh hơn)")
    parser.add_argument("--out", help="thư mục đích riêng tư (mặc định output/private-data/dashboard; docs/ bị khóa nếu thiếu giấy phép)")
    parser.add_argument("-q", "--quiet", action="store_true", help="giảm log")
    args = parser.parse_args(argv)

    asof = pd.Timestamp(args.asof) if args.asof else None
    try:
        result = build_all(out_dir=args.out, run_bt=not args.no_backtest, asof=asof,
                           verbose=not args.quiet)
    except PublicationNotAuthorized as exc:
        parser.error(str(exc))
    meta = result["meta"]
    u = meta["universe"]
    print(f"OK {meta['asof']} · {u['traded']} giao dịch / {u['listed']} còn hiệu lực · "
          f"{u['expired']} đã hết hạn · {sum(result['sizes'].values())/1e6:.2f} MB · "
          f"{meta['buildSeconds']:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
