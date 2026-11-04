"""Walk‑forward backtest cho recommendation engine.

Nguyên tắc chống thiên lệch:
  * Tín hiệu tại ngày t chỉ dùng dữ liệu ≤ t (rolling window trong panel).
  * **Vào lệnh ở phiên kế tiếp** sau ngày tín hiệu; không dùng giá đóng cửa của t.
  * Universe gồm cả CW sau này đáo hạn/huỷ niêm yết → không có survivorship bias.
  * Có chi phí giao dịch, trượt giá và giả định chênh lệch mua–bán (không có bid/ask thật).
  * Stop-loss / take-profit được mô phỏng theo đúng quy tắc trong recommendation card
    (stop = −2 ATR, TP = 2R); khớp lệnh thận trọng khi gap (giá mở cửa xấu hơn).
  * CW hết dữ liệu giữa kỳ → thoát ở phiên cuối cùng có giá, ghi rõ lý do.
  * Báo cáo cả kết quả kém: theo nhóm điểm, theo giai đoạn, độ nhạy chi phí/thời gian nắm giữ.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config
from .scoring import score_universe
from .snapshot import SNAPSHOT_COLS, add_peer_metrics, _pick


# ──────────────────────────────────────────────────────────────────
# CHỈ SỐ HIỆU QUẢ
# ──────────────────────────────────────────────────────────────────
def equity_metrics(returns: pd.Series, periods_per_year: float, rf: float = 0.0) -> dict:
    r = pd.Series(returns, dtype="float64").dropna()
    if r.empty:
        return {}
    eq = (1 + r).cumprod()
    total = float(eq.iloc[-1] - 1)
    n = len(r)
    years = n / periods_per_year if periods_per_year else np.nan
    cagr = float(eq.iloc[-1] ** (1 / years) - 1) if years and years > 0 else np.nan
    vol = float(r.std(ddof=1) * math.sqrt(periods_per_year)) if n > 1 else np.nan
    sharpe = float((r.mean() * periods_per_year - rf) / vol) if vol and vol > 0 else np.nan
    dd = eq / eq.cummax() - 1
    return {
        "periods": n,
        "total_return_pct": round(total * 100, 2),
        "cagr_pct": round(cagr * 100, 2) if np.isfinite(cagr) else None,
        "ann_vol_pct": round(vol * 100, 2) if np.isfinite(vol) else None,
        "sharpe": round(sharpe, 2) if np.isfinite(sharpe) else None,
        "max_drawdown_pct": round(float(dd.min()) * 100, 2),
        "avg_period_ret_pct": round(float(r.mean()) * 100, 2),
        "median_period_ret_pct": round(float(r.median()) * 100, 2),
        "best_period_pct": round(float(r.max()) * 100, 2),
        "worst_period_pct": round(float(r.min()) * 100, 2),
        "positive_periods_pct": round(float((r > 0).mean()) * 100, 1),
    }


def trade_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {}
    r = pd.to_numeric(trades["ret_pct"], errors="coerce").dropna() / 100.0
    if r.empty:
        return {}
    wins, losses = r[r > 0], r[r <= 0]
    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())
    return {
        "n_trades": int(len(r)),
        "win_rate_pct": round(float((r > 0).mean()) * 100, 1),
        "avg_return_pct": round(float(r.mean()) * 100, 2),
        "median_return_pct": round(float(r.median()) * 100, 2),
        "avg_win_pct": round(float(wins.mean()) * 100, 2) if len(wins) else None,
        "avg_loss_pct": round(float(losses.mean()) * 100, 2) if len(losses) else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 1e-12 else None,
        "best_trade_pct": round(float(r.max()) * 100, 1),
        "worst_trade_pct": round(float(r.min()) * 100, 1),
        "avg_holding_sessions": round(float(pd.to_numeric(trades["holding_sessions"],
                                                          errors="coerce").mean()), 1),
        "stop_hit_rate_pct": round(float(trades["stop_hit"].fillna(False).mean()) * 100, 1),
        "tp_hit_rate_pct": round(float(trades["tp_hit"].fillna(False).mean()) * 100, 1),
    }


# ──────────────────────────────────────────────────────────────────
# TRUY CẬP LỊCH SỬ
# ──────────────────────────────────────────────────────────────────
class History:
    """Truy cập nhanh panel theo ticker và theo ngày (searchsorted)."""

    def __init__(self, panel: pd.DataFrame):
        self.panel = panel.reset_index(drop=True)
        self.by_ticker: dict[str, dict] = {}
        for ticker, g in self.panel.groupby("ticker", sort=False):
            g = g.sort_values("date")
            self.by_ticker[ticker] = {
                "dates": g["date"].to_numpy(dtype="datetime64[ns]"),
                "close": g["close"].to_numpy(dtype=float),
                "high": g["high"].to_numpy(dtype=float),
                "low": g["low"].to_numpy(dtype=float),
                "open": g["open"].to_numpy(dtype=float) if "open" in g else g["close"].to_numpy(float),
                "pos": g.index.to_numpy(),
            }
        self.dates = np.array(sorted(self.panel["date"].dropna().unique()),
                              dtype="datetime64[ns]")

    def rows_asof(self, asof: pd.Timestamp, tolerance_days: int = 7) -> pd.DataFrame:
        idx = []
        asof64 = np.datetime64(pd.Timestamp(asof).normalize())
        tol = np.timedelta64(tolerance_days, "D")
        for ticker, h in self.by_ticker.items():
            pos = int(np.searchsorted(h["dates"], asof64, side="right") - 1)
            if pos < 0 or (asof64 - h["dates"][pos]) > tol:
                continue
            idx.append(int(h["pos"][pos]))
        if not idx:
            return self.panel.iloc[0:0]
        return self.panel.iloc[sorted(idx)].reset_index(drop=True)

    def next_session(self, ticker: str, asof: pd.Timestamp) -> int | None:
        h = self.by_ticker.get(ticker)
        if not h:
            return None
        pos = int(np.searchsorted(h["dates"], np.datetime64(pd.Timestamp(asof).normalize()),
                                  side="right"))
        return pos if pos < len(h["dates"]) else None

    def forward_path(self, ticker: str, entry_pos: int, sessions: int) -> tuple[int, int]:
        h = self.by_ticker[ticker]
        return entry_pos, min(entry_pos + sessions, len(h["dates"]) - 1)

    def ticker_series(self, ticker: str) -> dict | None:
        return self.by_ticker.get(ticker)


def rebalance_dates(panel: pd.DataFrame, start: str, end: pd.Timestamp,
                    spacing: int = 20) -> list[pd.Timestamp]:
    """Các phiên tái cân bằng cách nhau `spacing` phiên (không chồng lấn)."""
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(panel["date"].dropna().unique())))
    dates = dates[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))]
    if dates.empty:
        return []
    return [pd.Timestamp(d) for d in dates[::max(1, int(spacing))]]


# ──────────────────────────────────────────────────────────────────
# TÍN HIỆU (chấm điểm 1 lần, dùng cho mọi biến thể)
# ──────────────────────────────────────────────────────────────────
def prefilter(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    if df.empty:
        return df
    dte = pd.to_numeric(df.get("days_to_maturity"), errors="coerce")
    close = pd.to_numeric(df.get("close"), errors="coerce")
    val = pd.to_numeric(df.get("value_med20"), errors="coerce")
    sess = pd.to_numeric(df.get("sessions"), errors="coerce")
    return df[dte.ge(cfg["min_days_to_maturity"]) & close.gt(0)
              & val.ge(cfg["min_median_value_vnd"]) & sess.ge(20)].copy()


def eligible(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    if df.empty:
        return df
    dte = pd.to_numeric(df.get("days_to_maturity"), errors="coerce")
    val = pd.to_numeric(df.get("value_med20"), errors="coerce")
    sess = pd.to_numeric(df.get("sessions"), errors="coerce")
    dq = pd.to_numeric(df.get("data_quality"), errors="coerce")
    mask = (
        df["score"].notna()
        & dte.ge(cfg["min_days_to_maturity"])
        & val.ge(cfg["min_median_value_vnd"])
        & sess.ge(20)
        & dq.ge(0.60)
        & pd.to_numeric(df.get("close"), errors="coerce").gt(0)
    )
    return df[mask].copy()


def build_signals(history: History, dates: list[pd.Timestamp], r: float,
                  cfg: dict) -> dict[pd.Timestamp, pd.DataFrame]:
    """Chấm điểm một lần cho từng ngày tín hiệu (tốn ~0,1 s/ngày)."""
    signals: dict[pd.Timestamp, pd.DataFrame] = {}
    for t in dates:
        rows = history.rows_asof(t)
        if rows.empty:
            continue
        snap = add_peer_metrics(_pick(rows, SNAPSHOT_COLS), r)
        snap["staleness_days"] = (pd.Timestamp(t) - snap["date"]).dt.days
        snap = score_universe(snap)
        snap["signal_date"] = pd.Timestamp(t)
        signals[pd.Timestamp(t)] = snap
    return signals


def select_top(df: pd.DataFrame, n: int, max_issuer_weight: float = 0.40) -> list[str]:
    if df.empty:
        return []
    cap = max(1, int(math.floor(max_issuer_weight * n)))
    counts: dict[str, int] = {}
    picks: list[str] = []
    for _, row in df.sort_values("score", ascending=False).iterrows():
        iss = row.get("issuer", "")
        if counts.get(iss, 0) >= cap:
            continue
        picks.append(row["ticker"])
        counts[iss] = counts.get(iss, 0) + 1
        if len(picks) >= n:
            break
    return picks


# ──────────────────────────────────────────────────────────────────
# MÔ PHỎNG
# ──────────────────────────────────────────────────────────────────
def execute_trade(history: History, ticker: str, t: pd.Timestamp, holding: int,
                  cost_per_side: float, use_stops: bool) -> dict | None:
    pos = history.next_session(ticker, t)
    if pos is None:
        return None
    h = history.by_ticker[ticker]
    entry_pos, exit_pos = history.forward_path(ticker, pos, holding)
    entry = float(h["close"][entry_pos])
    if not np.isfinite(entry) or entry <= 0:
        return None
    exitp = float(h["close"][exit_pos])
    exit_reason = "horizon" if exit_pos - entry_pos >= holding else "data_end"
    fill = exitp
    hit_stop = hit_tp = False
    stop_px = tp_px = np.nan

    if use_stops:
        atr = None
        series = h
        # ATR lấy từ panel tại ngày tín hiệu (không dùng dữ liệu tương lai)
        row = history.rows_asof(t)
        match = row[row["ticker"] == ticker]
        if not match.empty:
            atr = match.iloc[0].get("atr14")
        if atr is not None and pd.notna(atr) and np.isfinite(atr) and atr > 0:
            stop_px = max(entry - 2.0 * float(atr), 10.0)
            tp_px = 2 * entry - stop_px
            seg_lo = series["low"][entry_pos:exit_pos + 1]
            seg_hi = series["high"][entry_pos:exit_pos + 1]
            stop_hits = np.where(seg_lo <= stop_px)[0]
            tp_hits = np.where(seg_hi >= tp_px)[0]
            first_stop = int(stop_hits[0]) if len(stop_hits) else None
            first_tp = int(tp_hits[0]) if len(tp_hits) else None
            if first_stop is not None and (first_tp is None or first_stop <= first_tp):
                idx_fill = entry_pos + first_stop
                fill = min(stop_px, float(series["open"][idx_fill]))
                exit_pos, hit_stop, exit_reason = idx_fill, True, "stop"
            elif first_tp is not None:
                idx_fill = entry_pos + first_tp
                fill = max(tp_px, float(series["open"][idx_fill]))
                exit_pos, hit_tp, exit_reason = idx_fill, True, "take_profit"

    if not np.isfinite(fill) or fill <= 0:
        fill = exitp
    gross = fill / entry - 1.0
    seg_high = h["high"][entry_pos:exit_pos + 1]
    seg_low = h["low"][entry_pos:exit_pos + 1]
    return {
        "entry_date": pd.Timestamp(h["dates"][entry_pos]).strftime("%Y-%m-%d"),
        "exit_date": pd.Timestamp(h["dates"][exit_pos]).strftime("%Y-%m-%d"),
        "entry": entry,
        "exit": float(fill),
        "gross_ret": gross,
        "net_ret": gross - 2 * cost_per_side,
        "mfe": float(seg_high.max() / entry - 1.0) if len(seg_high) else np.nan,
        "mae": float(seg_low.min() / entry - 1.0) if len(seg_low) else np.nan,
        "holding": int(exit_pos - entry_pos),
        "exit_reason": exit_reason,
        "stop_price": float(stop_px) if np.isfinite(stop_px) else None,
        "tp_price": float(tp_px) if np.isfinite(tp_px) else None,
        "stop_hit": hit_stop,
        "tp_hit": hit_tp,
    }


def simulate(history: History, signals: dict, cfg: dict, select_fn,
             collect_trades: bool = True, gate: float | None = None) -> dict:
    periods, trades, bucket_rows = [], [], []
    for t in sorted(signals):
        snap = signals[t]
        elig = eligible(snap, cfg)
        if gate is not None:
            elig = elig[elig["score"] >= gate]
        if len(elig) < 3:
            continue

        # Forward return của toàn bộ universe đủ điều kiện (cho phân tích nhóm điểm)
        fwd = []
        for _, row in elig.iterrows():
            res = execute_trade(history, row["ticker"], t, cfg["holding_days"],
                                cfg["cost_per_side"], use_stops=False)
            if res is None:
                continue
            fwd.append({"ticker": row["ticker"], "underlying": row.get("underlying"),
                        "issuer": row.get("issuer"), "score": row.get("score"),
                        "recommendation": row.get("recommendation"),
                        "ret_pct": (res["entry"] and res["exit"] / res["entry"] - 1) * 100})
        if fwd:
            f = pd.DataFrame(fwd)
            f["date"] = t
            bucket_rows.append(f)

        picks = select_fn(elig)
        rets = []
        for ticker in picks:
            res = execute_trade(history, ticker, t, cfg["holding_days"],
                                cfg["cost_per_side"], use_stops=cfg.get("use_stops", True))
            if res is None:
                continue
            rets.append(res["net_ret"])
            if collect_trades:
                row = elig[elig["ticker"] == ticker].iloc[0]
                trades.append({
                    "signal_date": t.strftime("%Y-%m-%d"),
                    "ticker": ticker,
                    "underlying": row.get("underlying"),
                    "issuer": row.get("issuer"),
                    "score": round(float(row.get("score", np.nan)), 1),
                    "recommendation": row.get("recommendation"),
                    "entry": round(res["entry"], 1),
                    "exit": round(res["exit"], 1),
                    "gross_ret_pct": round(res["gross_ret"] * 100, 1),
                    "ret_pct": round(res["net_ret"] * 100, 1),
                    "mfe_pct": round(res["mfe"] * 100, 1) if np.isfinite(res["mfe"]) else None,
                    "mae_pct": round(res["mae"] * 100, 1) if np.isfinite(res["mae"]) else None,
                    "holding_sessions": res["holding"],
                    "exit_reason": res["exit_reason"],
                    "stop_price": round(res["stop_price"], 1) if res["stop_price"] else None,
                    "tp_price": round(res["tp_price"], 1) if res["tp_price"] else None,
                    "stop_hit": res["stop_hit"],
                    "tp_hit": res["tp_hit"],
                    "entry_date": res["entry_date"],
                    "exit_date": res["exit_date"],
                })
        periods.append({"date": t, "n_picks": len(rets),
                        "ret": float(np.mean(rets)) if rets else 0.0})

    dfp = pd.DataFrame(periods)
    if not dfp.empty:
        dfp["equity"] = (1 + dfp["ret"]).cumprod()
    return {"periods": dfp, "trades": pd.DataFrame(trades),
            "buckets": pd.concat(bucket_rows, ignore_index=True) if bucket_rows else pd.DataFrame()}


def benchmark_underlying(market, signals: dict, cfg: dict) -> pd.Series:
    """Equal-weight rổ 22 cổ phiếu cơ sở, cùng lịch tín hiệu, trừ phí giao dịch cổ phiếu."""
    und = market.underlying.copy()
    panels = und.pivot_table(index="date", columns="ticker", values="close").sort_index()
    rets = {}
    dates = panels.index
    for t in sorted(signals):
        pos = dates.searchsorted(pd.Timestamp(t), side="right")
        if pos >= len(dates):
            continue
        exit_pos = min(pos + cfg["holding_days"], len(dates) - 1)
        r = (panels.iloc[exit_pos] / panels.iloc[pos] - 1).dropna()
        if r.empty:
            continue
        rets[pd.Timestamp(t)] = float(r.mean()) - 2 * 0.0015
    return pd.Series(rets).sort_index()


# ──────────────────────────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────────────────────────
def run_backtest(panel: pd.DataFrame, market, cfg: dict | None = None,
                 start: str | None = None, end: pd.Timestamp | None = None) -> dict:
    cfg = {**config.BACKTEST, **(cfg or {})}
    start = start or config.BACKTEST_START
    end = end or market.asof
    r = market.risk_free
    history = History(panel)

    base_grid = rebalance_dates(panel, start, end, spacing=5)
    signals_all = build_signals(history, base_grid, r, cfg)
    # dùng mốc 20 phiên làm lưới tín hiệu chính
    spacing = int(cfg.get("spacing", cfg["holding_days"]))
    grid = {t: s for i, (t, s) in enumerate(sorted(signals_all.items())) if i % max(1, spacing // 5) == 0}
    signals = dict(sorted(grid.items()))

    top_fn = lambda d: select_top(d, cfg["top_n"], cfg["max_weight_per_issuer"])
    main = simulate(history, signals, cfg, top_fn, collect_trades=True)
    ew = simulate(history, signals, cfg, lambda d: d["ticker"].tolist(), collect_trades=False)

    random_rets = []
    for seed in range(10):
        rng = np.random.default_rng(seed)
        res = simulate(history, signals, cfg,
                       lambda d, rng=rng: list(rng.choice(
                           d["ticker"].tolist(), size=min(cfg["top_n"], len(d)), replace=False)),
                       collect_trades=False)
        if not res["periods"].empty:
            random_rets.append(res["periods"].set_index("date")["ret"])
    random_series = pd.concat(random_rets, axis=1).mean(axis=1) if random_rets else pd.Series()

    und_bench = benchmark_underlying(market, signals, cfg)

    p = main["periods"].set_index("date")
    curve = pd.DataFrame({
        "score_top": p["ret"],
        "ew_universe": ew["periods"].set_index("date")["ret"].reindex(p.index),
        "random": random_series.reindex(p.index),
        "underlying_ew": und_bench.reindex(p.index),
    })
    for col in curve.columns:
        curve[col + "_eq"] = (1 + curve[col].fillna(0)).cumprod() * 100

    periods_per_year = config.TRADING_DAYS_PER_YEAR / spacing
    summary = {k: equity_metrics(curve[v], periods_per_year, r)
               for k, v in [("score_top", "score_top"), ("ew_universe", "ew_universe"),
                            ("random", "random"), ("underlying_ew", "underlying_ew")]}

    trades = main["trades"]
    buckets = main["buckets"]

    bucket_stats = []
    if not buckets.empty:
        for lo, hi, label in [(80, 101, "80–100"), (65, 80, "65–79"), (45, 65, "45–64"),
                              (30, 45, "30–44"), (0, 30, "0–29")]:
            sub = buckets[(buckets["score"] >= lo) & (buckets["score"] < hi)]
            if sub.empty:
                bucket_stats.append({"bucket": label, "n": 0})
                continue
            rr = pd.to_numeric(sub["ret_pct"], errors="coerce") / 100
            bucket_stats.append({
                "bucket": label, "n": int(len(sub)),
                "avg_ret_pct": round(float(rr.mean()) * 100, 2),
                "median_ret_pct": round(float(rr.median()) * 100, 2),
                "win_rate_pct": round(float((rr > 0).mean()) * 100, 1),
                "p25_pct": round(float(rr.quantile(0.25)) * 100, 1),
                "p75_pct": round(float(rr.quantile(0.75)) * 100, 1),
            })

    def _group_stats(df, col):
        if df.empty or col not in df:
            return []
        out = []
        for key, g in df.groupby(col):
            rr = pd.to_numeric(g["ret_pct"], errors="coerce") / 100
            out.append({"key": str(key), "n": int(len(g)),
                        "avg_ret_pct": round(float(rr.mean()) * 100, 2),
                        "win_rate_pct": round(float((rr > 0).mean()) * 100, 1)})
        return sorted(out, key=lambda x: -x["n"])

    monthly = []
    if not curve.empty:
        m = (1 + curve["score_top"].fillna(0)).groupby(curve.index.to_period("M")).prod() - 1
        monthly = [{"month": str(k), "ret_pct": round(float(v) * 100, 2)} for k, v in m.items()]

    cost_sensitivity = []
    if not trades.empty:
        gross = pd.to_numeric(trades["gross_ret_pct"], errors="coerce") / 100
        for c in cfg["cost_sensitivity"]:
            net = gross - 2 * c
            cost_sensitivity.append({
                "cost_per_side_pct": round(c * 100, 2),
                "avg_trade_ret_pct": round(float(net.mean()) * 100, 2),
                "win_rate_pct": round(float((net > 0).mean()) * 100, 1),
            })

    # ── Kiểm tra bộ lọc kinh tế (exploratory, công bố toàn bộ kết quả)
    filter_tests = []
    filters = {
        "Cơ sở: top-5 theo CW Score": lambda d: d,
        "Chỉ mua khi IV ≤ HV": lambda d: d[d["iv_vs_hv"] <= 0],
        "Chỉ mua khi IV thấp hơn smile cùng underlying": lambda d: d[d["iv_resid"] <= 0],
        "Chỉ mua khi cổ phiếu cơ sở trên MA50": lambda d: d[d["u_above_ma50"] == 1],
        "IV ≤ HV và trên MA50": lambda d: d[(d["iv_vs_hv"] <= 0) & (d["u_above_ma50"] == 1)],
        "Chỉ CW Score ≥ 80": lambda d: d[d["score"] >= 80],
    }
    for label, fn in filters.items():
        res = simulate(history, signals, cfg,
                       lambda d, fn=fn: select_top(fn(d), cfg["top_n"],
                                                   cfg["max_weight_per_issuer"]),
                       collect_trades=True)
        m = trade_metrics(res["trades"])
        per = res["periods"].set_index("date")["ret"] if not res["periods"].empty else pd.Series(dtype=float)
        filter_tests.append({
            "filter": label,
            "n_trades": m.get("n_trades", 0),
            "avg_trade_ret_pct": m.get("avg_return_pct"),
            "win_rate_pct": m.get("win_rate_pct"),
            "profit_factor": m.get("profit_factor"),
            "total_return_pct": round(float((1 + per).prod() - 1) * 100, 2) if len(per) else None,
        })

    # ── Độ nhạy: thời gian nắm giữ & ngưỡng điểm (dùng lại signals, không chấm lại)
    holding_sensitivity = []
    for hold in (5, 10, 20):
        if hold > spacing:
            continue
        sub_cfg = {**cfg, "holding_days": hold}
        res = simulate(history, signals, sub_cfg, top_fn, collect_trades=True)
        m = trade_metrics(res["trades"]) if not res["trades"].empty else {}
        per = res["periods"].set_index("date")["ret"]
        holding_sensitivity.append({
            "holding_sessions": hold,
            "n_trades": m.get("n_trades"),
            "avg_trade_ret_pct": m.get("avg_return_pct"),
            "win_rate_pct": m.get("win_rate_pct"),
            "total_return_pct": round(float((1 + per).prod() - 1) * 100, 2),
        })

    gate_sensitivity = []
    for gate in (45, 65, 80):
        res = simulate(history, signals, cfg,
                       lambda d, g=gate: select_top(d[d["score"] >= g], cfg["top_n"],
                                                    cfg["max_weight_per_issuer"]),
                       collect_trades=True, gate=gate)
        m = trade_metrics(res["trades"]) if not res["trades"].empty else {}
        per = res["periods"].set_index("date")["ret"]
        gate_sensitivity.append({
            "score_gate": gate,
            "n_trades": m.get("n_trades"),
            "avg_trade_ret_pct": m.get("avg_return_pct"),
            "win_rate_pct": m.get("win_rate_pct"),
            "total_return_pct": round(float((1 + per).prod() - 1) * 100, 2) if len(per) else None,
        })

    return {
        "config": {
            "start": signals and min(signals).strftime("%Y-%m-%d"),
            "end": pd.Timestamp(end).strftime("%Y-%m-%d"),
            "rebalance": f"mỗi {spacing} phiên",
            "holding_sessions": cfg["holding_days"],
            "top_n": cfg["top_n"],
            "min_days_to_maturity": cfg["min_days_to_maturity"],
            "min_median_value_vnd": cfg["min_median_value_vnd"],
            "max_weight_per_issuer": cfg["max_weight_per_issuer"],
            "cost_per_side_bps": round(cfg["cost_per_side"] * 10_000, 1),
            "cost_breakdown": {
                "commission_pct": round(cfg["commission_per_side"] * 100, 2),
                "slippage_pct": round(cfg["slippage_per_side"] * 100, 2),
                "half_spread_pct": round(cfg["half_spread"] * 100, 2),
            },
            "risk_free": round(float(r), 4),
            "n_signal_dates": len(signals),
        },
        "summary": summary,
        "curve": [
            {"date": d.strftime("%Y-%m-%d"),
             "score_top": round(float(row["score_top"]), 4) if pd.notna(row["score_top"]) else None,
             "ew_universe": round(float(row["ew_universe"]), 4) if pd.notna(row["ew_universe"]) else None,
             "random": round(float(row["random"]), 4) if pd.notna(row["random"]) else None,
             "underlying_ew": round(float(row["underlying_ew"]), 4) if pd.notna(row["underlying_ew"]) else None,
             "eq_score": round(float(row["score_top_eq"]), 2),
             "eq_ew": round(float(row["ew_universe_eq"]), 2),
             "eq_random": round(float(row["random_eq"]), 2)}
            for d, row in curve.iterrows()
        ],
        "trade_stats": trade_metrics(trades),
        "trades": trades.tail(300).to_dict("records") if not trades.empty else [],
        "n_trades_total": int(len(trades)),
        "buckets": bucket_stats,
        "by_issuer": _group_stats(trades, "issuer"),
        "by_underlying": _group_stats(trades, "underlying"),
        "monthly": monthly,
        "cost_sensitivity": cost_sensitivity,
        "holding_sensitivity": holding_sensitivity,
        "gate_sensitivity": gate_sensitivity,
        "filter_sensitivity": filter_tests,
        "caveats": [
            "Vào lệnh tại giá đóng cửa phiên kế tiếp sau ngày tín hiệu; không mô phỏng khớp lệnh trong phiên.",
            "Không có dữ liệu bid/ask thật: giả định nửa chênh lệch 0,50% + hoa hồng 0,15% + trượt giá 0,30% mỗi chiều.",
            "Không mô phỏng giới hạn khối lượng: với CW giao dịch dưới 50 triệu VND/phiên, kết quả thực tế sẽ kém hơn.",
            "Stop-loss/TP mô phỏng trên dữ liệu ngày; khi giá mở cửa gap qua ngưỡng, giả định khớp tại giá mở cửa.",
            "Điều khoản CW (strike/ratio điều chỉnh) lấy từ snapshot hiện tại — có thể lệch nếu có điều chỉnh cổ tức trong quá khứ.",
            "Lãi suất phi rủi ro dùng hằng số hiện tại cho toàn bộ giai đoạn (cache HNX chỉ có 57 phiên).",
            "Số kỳ tái cân bằng ít (~40) → sai số thống kê lớn; kết quả không nên được hiểu là kỳ vọng chắc chắn.",
        ],
    }
