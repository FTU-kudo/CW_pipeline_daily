"""Walk‑forward backtest cho recommendation engine — mark-to-market theo từng phiên.

Nguyên tắc chống thiên lệch
  * Tín hiệu tại ngày t chỉ dùng dữ liệu ≤ t (rolling window trong panel).
  * **Vào lệnh ở phiên kế tiếp** sau ngày tín hiệu; không dùng giá đóng cửa của t.
  * Universe gồm cả CW sau này đáo hạn / huỷ niêm yết → không survivorship bias.
  * Chi phí giao dịch tính trên giá trị vị thế ở cả hai chiều (hoa hồng + trượt giá
    + nửa chênh lệch mua–bán); báo cáo **gross và net riêng** để thấy chi phí ăn bao
    nhiêu, không trộn lẫn với chất lượng tín hiệu.
  * Stop-loss / take-profit mô phỏng trên dữ liệu ngày, chỉ tính từ phiên SAU khi
    vào lệnh; khi giá mở cửa gap qua ngưỡng thì khớp ở giá mở cửa (thận trọng).
  * CW hết dữ liệu giữa kỳ → thoát ở phiên cuối cùng có giá, ghi rõ lý do.

Cách tính hiệu quả
  Sau mỗi kỳ, danh mục được **đánh giá lại theo từng phiên** (mark-to-market) bằng
  giá đóng cửa của từng vị thế, chia đều vốn. Nhờ vậy đường vốn, drawdown, Sharpe
  và lợi nhuận theo tháng là số liệu thật theo ngày, không phải 43 điểm rời rạc.
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
def equity_metrics(returns, periods_per_year: float, rf: float = 0.0) -> dict:
    """Chỉ số hiệu quả từ chuỗi lợi nhuận theo kỳ (hoặc theo ngày)."""
    r = pd.Series(returns, dtype="float64").dropna()
    if r.empty:
        return {}
    eq = (1 + r).cumprod()
    total = float(eq.iloc[-1] - 1)
    n = len(r)
    years = n / periods_per_year if periods_per_year else np.nan
    cagr = float(eq.iloc[-1] ** (1 / years) - 1) if years and years > 0 and eq.iloc[-1] > 0 else np.nan
    vol = float(r.std(ddof=1) * math.sqrt(periods_per_year)) if n > 1 else np.nan
    sharpe = float((r.mean() * periods_per_year - rf) / vol) if vol and vol > 0 else np.nan
    downside = r[r < 0]
    dvol = float(downside.std(ddof=1) * math.sqrt(periods_per_year)) if len(downside) > 1 else np.nan
    sortino = float((r.mean() * periods_per_year - rf) / dvol) if dvol and dvol > 0 else np.nan
    dd = eq / eq.cummax() - 1
    mdd = float(dd.min())
    calmar = float(cagr / abs(mdd)) if mdd < 0 and np.isfinite(cagr) else np.nan
    return {
        "periods": n,
        "total_return_pct": round(total * 100, 2),
        "cagr_pct": round(cagr * 100, 2) if np.isfinite(cagr) else None,
        "ann_vol_pct": round(vol * 100, 2) if np.isfinite(vol) else None,
        "sharpe": round(sharpe, 2) if np.isfinite(sharpe) else None,
        "sortino": round(sortino, 2) if np.isfinite(sortino) else None,
        "max_drawdown_pct": round(mdd * 100, 2),
        "calmar": round(calmar, 2) if np.isfinite(calmar) else None,
        "avg_period_ret_pct": round(float(r.mean()) * 100, 4),
        "median_period_ret_pct": round(float(r.median()) * 100, 4),
        "best_period_pct": round(float(r.max()) * 100, 2) if len(r) else None,
        "worst_period_pct": round(float(r.min()) * 100, 2) if len(r) else None,
        "positive_periods_pct": round(float((r > 0).mean()) * 100, 1),
        "final_equity": round(float(eq.iloc[-1]) * 100, 2),
    }


def metrics_from_equity(equity: pd.Series, spacing: int, rf: float = 0.0) -> dict:
    """Chỉ số hiệu quả từ đường vốn theo ngày.

    Lợi nhuận/Sharpe tính trên từng **kỳ tái cân bằng** (gom `spacing` phiên) để
    không bị méo bởi các phiên có bước giá 10 VND; drawdown tính trên đường vốn
    theo ngày (chính xác hơn).
    """
    eq = pd.Series(equity, dtype="float64").dropna()
    if len(eq) < 2 or eq.iloc[0] <= 0:
        return {}
    eq = eq[eq > 0]
    block = max(int(spacing), 1)
    # gom thành các kỳ: lấy giá trị cuối mỗi block
    marks = list(range(block, len(eq), block)) + [len(eq) - 1]
    marks = sorted(set([0] + marks))
    pts = eq.iloc[marks]
    per_ret = pts.pct_change().dropna()
    m = equity_metrics(per_ret, config.TRADING_DAYS_PER_YEAR / block, rf)
    dd = eq / eq.cummax() - 1
    m["max_drawdown_pct"] = round(float(dd.min()) * 100, 2)
    m["total_return_pct"] = round(float(eq.iloc[-1] / eq.iloc[0] - 1) * 100, 2)
    m["daily_vol_pct"] = round(float(eq.pct_change().std() * math.sqrt(252) * 100), 2)
    m["periods"] = int(len(per_ret))
    return m


def trade_metrics(trades: pd.DataFrame) -> dict:
    if trades is None or len(trades) == 0:
        return {}
    r = pd.to_numeric(trades["ret_pct"], errors="coerce").dropna() / 100.0
    if r.empty:
        return {}
    wins, losses = r[r > 0], r[r <= 0]
    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())
    hold = pd.to_numeric(trades.get("holding_sessions"), errors="coerce")
    return {
        "n_trades": int(len(r)),
        "win_rate_pct": round(float((r > 0).mean()) * 100, 1),
        "avg_return_pct": round(float(r.mean()) * 100, 2),
        "median_return_pct": round(float(r.median()) * 100, 2),
        "avg_win_pct": round(float(wins.mean()) * 100, 2) if len(wins) else None,
        "avg_loss_pct": round(float(losses.mean()) * 100, 2) if len(losses) else None,
        "payoff_ratio": round(abs(float(wins.mean()) / float(losses.mean())), 2)
        if len(wins) and len(losses) and float(losses.mean()) != 0 else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 1e-12 else None,
        "expectancy_pct": round(float(r.mean()) * 100, 2),
        "best_trade_pct": round(float(r.max()) * 100, 1),
        "worst_trade_pct": round(float(r.min()) * 100, 1),
        "avg_holding_sessions": round(float(hold.mean()), 1) if hold is not None and hold.notna().any() else None,
        "stop_hit_rate_pct": round(float(trades["stop_hit"].fillna(False).mean()) * 100, 1)
        if "stop_hit" in trades else None,
        "tp_hit_rate_pct": round(float(trades["tp_hit"].fillna(False).mean()) * 100, 1)
        if "tp_hit" in trades else None,
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
                "high": g["high"].to_numpy(dtype=float) if "high" in g else g["close"].to_numpy(float),
                "low": g["low"].to_numpy(dtype=float) if "low" in g else g["close"].to_numpy(float),
                "open": g["open"].to_numpy(dtype=float) if "open" in g else g["close"].to_numpy(float),
                "pos": g.index.to_numpy(),
            }
        self.dates = np.array(sorted(pd.to_datetime(self.panel["date"].dropna().unique())),
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
    """Chấm điểm một lần cho từng ngày tín hiệu."""
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
# MÔ PHỎNG MARK-TO-MARKET
# ──────────────────────────────────────────────────────────────────
def _position(history: History, ticker: str, t: pd.Timestamp, holding: int,
              use_stops: bool, atr: float | None) -> dict | None:
    """Một vị thế: vào phiên kế tiếp, đánh dấu theo ngày, stop/TP thận trọng."""
    entry_pos = history.next_session(ticker, t)
    if entry_pos is None:
        return None
    h = history.by_ticker[ticker]
    entry_pos, exit_pos = history.forward_path(ticker, entry_pos, holding)
    entry = float(h["close"][entry_pos])
    if not np.isfinite(entry) or entry <= 0:
        return None

    stop_px = tp_px = np.nan
    trigger = None  # (index, giá khớp, lý do)
    if use_stops and atr is not None and np.isfinite(atr) and atr > 0:
        stop_px = max(entry - 2.0 * float(atr), 1.0)
        tp_px = 2 * entry - stop_px
        # chỉ tính từ phiên SAU khi vào lệnh (không dùng low/high của phiên khớp lệnh)
        for i in range(entry_pos + 1, exit_pos + 1):
            lo, hi, op = float(h["low"][i]), float(h["high"][i]), float(h["open"][i])
            if np.isfinite(lo) and lo <= stop_px:
                trigger = (i, min(stop_px, op) if np.isfinite(op) else stop_px, "stop")
                break
            if np.isfinite(hi) and hi >= tp_px:
                trigger = (i, max(tp_px, op) if np.isfinite(op) else tp_px, "take_profit")
                break

    exit_reason = "horizon"
    if trigger is not None:
        trig_pos, fill, exit_reason = trigger
        exit_pos = trig_pos
        exit_price = fill
    else:
        exit_price = float(h["close"][exit_pos])
        if exit_pos - entry_pos < holding:
            exit_reason = "data_end"

    seg = slice(entry_pos, exit_pos + 1)
    hi, lo = h["high"][seg], h["low"][seg]
    return {
        "ticker": ticker,
        "signal_date": pd.Timestamp(t).strftime("%Y-%m-%d"),
        "entry_date": pd.Timestamp(h["dates"][entry_pos]).strftime("%Y-%m-%d"),
        "exit_date": pd.Timestamp(h["dates"][exit_pos]).strftime("%Y-%m-%d"),
        "entry_pos": int(entry_pos),
        "exit_pos": int(exit_pos),
        "entry": entry,
        "exit": float(exit_price),
        "gross_ret": float(exit_price) / entry - 1.0,
        "mfe": float(np.nanmax(hi) / entry - 1.0) if len(hi) else np.nan,
        "mae": float(np.nanmin(lo) / entry - 1.0) if len(lo) else np.nan,
        "holding": int(exit_pos - entry_pos),
        "exit_reason": exit_reason,
        "stop_price": float(stop_px) if np.isfinite(stop_px) else None,
        "tp_price": float(tp_px) if np.isfinite(tp_px) else None,
        "stop_hit": exit_reason == "stop",
        "tp_hit": exit_reason == "take_profit",
        "trigger_pos": int(trigger[0]) if trigger else None,
    }


def _period_curve(history: History, positions: list[dict], calendar: np.ndarray,
                  entry_date: pd.Timestamp, exit_date: pd.Timestamp) -> pd.Series:
    """Đường giá trị danh mục (chia đều vốn) trong một kỳ, đánh dấu từng phiên."""
    if not positions:
        return pd.Series(dtype="float64")
    grid = calendar[(calendar >= np.datetime64(entry_date)) & (calendar <= np.datetime64(exit_date))]
    if len(grid) == 0:
        return pd.Series(dtype="float64")
    cols = {}
    for pos in positions:
        h = history.by_ticker[pos["ticker"]]
        s = pd.Series(h["close"][pos["entry_pos"]:pos["exit_pos"] + 1],
                      index=pd.to_datetime(h["dates"][pos["entry_pos"]:pos["exit_pos"] + 1]))
        s = s.reindex(pd.DatetimeIndex(grid)).ffill()
        entry = pos["entry"]
        rel = s / entry
        if pos.get("stop_hit") or pos.get("tp_hit"):
            # Sau khi khớp stop/TP, vị thế đóng → giá trị đứng yên (tiền mặt)
            frozen = pos["exit"] / entry
            cut = pd.Timestamp(pos["exit_date"])
            rel = rel.where(rel.index < cut, frozen)
        else:
            frozen = pos["exit"] / entry
            cut = pd.Timestamp(pos["exit_date"])
            rel = rel.where(rel.index <= cut, frozen)
        cols[pos["ticker"]] = rel.ffill().bfill().fillna(1.0)
    mat = pd.DataFrame(cols)
    return mat.mean(axis=1)


def simulate(history: History, signals: dict, cfg: dict, select_fn,
             collect_trades: bool = True, gate: float | None = None,
             with_stops: bool | None = None) -> dict:
    """Mô phỏng danh mục: mỗi kỳ chọn mã, giữ `holding_days` phiên, MTM theo ngày."""
    use_stops = cfg.get("use_stops", True) if with_stops is None else with_stops
    holding = int(cfg["holding_days"])
    cost = float(cfg["cost_per_side"])
    rows, trades, equity_rows = [], [], []
    equity = 1.0
    for t in sorted(signals):
        snap = signals[t]
        elig = eligible(snap, cfg)
        if gate is not None:
            elig = elig[elig["score"] >= gate]
        if len(elig) < 3:
            continue
        picks = select_fn(elig)
        if not picks:
            continue
        positions = []
        for ticker in picks:
            row = elig[elig["ticker"] == ticker]
            atr = float(row.iloc[0].get("atr14")) if not row.empty and pd.notna(row.iloc[0].get("atr14")) else None
            pos = _position(history, ticker, t, holding, use_stops, atr)
            if pos is not None:
                positions.append(pos)
        if not positions:
            continue

        entry_dates = [pd.Timestamp(p["entry_date"]) for p in positions]
        exit_dates = [pd.Timestamp(p["exit_date"]) for p in positions]
        entry_d = min(entry_dates)
        exit_d = max(exit_dates)
        curve = _period_curve(history, positions, history.dates, entry_d, exit_d)
        if curve.empty:
            continue

        base = curve.iloc[0]
        if base <= 0:
            continue
        # Đường giá trị tương đối trong kỳ (không gồm chi phí), sau đó áp chi phí:
        #   • phí vào lệnh trừ ngay ở phiên đầu
        #   • phí ra lệnh trừ ở phiên cuối
        path = curve / base
        path.iloc[0] = 1.0 - cost
        if len(path) > 1:
            path.iloc[1:] = path.iloc[1:] * (1.0 - cost)
        path.iloc[-1] = path.iloc[-1] * (1.0 - cost)
        if len(path) == 1:
            path.iloc[0] = (1.0 - cost) ** 2
        for d, v in path.items():
            equity_rows.append({"date": pd.Timestamp(d),
                                "ret": float(v) - 1.0 if d != path.index[0] else 0.0,
                                "eq": equity * float(v),
                                "period": pd.Timestamp(t).strftime("%Y-%m-%d")})
        period_ret = float(path.iloc[-1]) - 1.0
        equity *= float(path.iloc[-1])

        gross_avg = float(np.mean([p["gross_ret"] for p in positions]))
        rows.append({"date": t, "entry_date": entry_d, "exit_date": exit_d,
                     "n_picks": len(positions), "ret": period_ret,
                     "gross_ret": gross_avg, "equity": equity})
        if collect_trades:
            for p in positions:
                row = elig[elig["ticker"] == p["ticker"]].iloc[0]
                net = (1 + p["gross_ret"]) * (1 - cost) ** 2 - 1
                trades.append({
                    "signal_date": p["signal_date"],
                    "entry_date": p["entry_date"],
                    "exit_date": p["exit_date"],
                    "ticker": p["ticker"],
                    "underlying": row.get("underlying"),
                    "issuer": row.get("issuer"),
                    "score": round(float(row.get("score", np.nan)), 1),
                    "recommendation": row.get("recommendation"),
                    "entry": round(p["entry"], 1),
                    "exit": round(p["exit"], 1),
                    "gross_ret_pct": round(p["gross_ret"] * 100, 2),
                    "ret_pct": round(net * 100, 2),
                    "cost_pct": round((p["gross_ret"] - net) * 100, 2),
                    "mfe_pct": round(p["mfe"] * 100, 1) if np.isfinite(p["mfe"]) else None,
                    "mae_pct": round(p["mae"] * 100, 1) if np.isfinite(p["mae"]) else None,
                    "holding_sessions": p["holding"],
                    "exit_reason": p["exit_reason"],
                    "stop_price": round(p["stop_price"], 1) if p["stop_price"] else None,
                    "tp_price": round(p["tp_price"], 1) if p["tp_price"] else None,
                    "stop_hit": p["stop_hit"],
                    "tp_hit": p["tp_hit"],
                })

    eq = pd.DataFrame(equity_rows).drop_duplicates(subset=["date"], keep="last")
    if not eq.empty:
        eq = eq.set_index("date").sort_index()
    return {"periods": pd.DataFrame(rows), "trades": pd.DataFrame(trades),
            "equity": eq}


def forward_stats(history: History, signals: dict, cfg: dict) -> pd.DataFrame:
    """Lợi nhuận `holding_days` phiên của TOÀN BỘ CW đủ điều kiện (gross, không stop).

    Dùng cho kiểm định tính đơn điệu của thang điểm — không phải hiệu quả chiến lược.
    """
    holding = int(cfg["holding_days"])
    out = []
    for t in sorted(signals):
        snap = signals[t]
        elig = eligible(snap, cfg)
        if elig.empty:
            continue
        for _, row in elig.iterrows():
            ticker = row["ticker"]
            h = history.by_ticker.get(ticker)
            if h is None:
                continue
            pos = history.next_session(ticker, t)
            if pos is None:
                continue
            _, exit_pos = history.forward_path(ticker, pos, holding)
            entry = float(h["close"][pos])
            exitp = float(h["close"][exit_pos])
            if not np.isfinite(entry) or entry <= 0 or not np.isfinite(exitp):
                continue
            out.append({
                "date": t, "ticker": ticker, "underlying": row.get("underlying"),
                "issuer": row.get("issuer"), "score": row.get("score"),
                "recommendation": row.get("recommendation"),
                "adv20": row.get("adv20"), "coverage20": row.get("coverage20"),
                "amihud20": row.get("amihud20"), "range20": row.get("range20"),
                "ret_pct": (exitp / entry - 1) * 100,
                "holding_sessions": int(exit_pos - pos),
            })
    return pd.DataFrame(out)


def benchmark_underlying(market, signals: dict, cfg: dict, calendar: np.ndarray,
                         cost: float = 0.0015) -> tuple[pd.Series, dict]:
    """EW rổ cổ phiếu cơ sở, đánh dấu từng phiên, cùng lịch tín hiệu."""
    und = market.underlying.copy()
    panels = und.pivot_table(index="date", columns="ticker", values="close").sort_index()
    rets: dict[pd.Timestamp, float] = {}
    period_rets: dict[pd.Timestamp, float] = {}
    for t in sorted(signals):
        pos = panels.index.searchsorted(pd.Timestamp(t), side="right")
        if pos >= len(panels):
            continue
        exit_pos = min(pos + int(cfg["holding_days"]), len(panels) - 1)
        seg = panels.iloc[pos:exit_pos + 1]
        ew = (seg / seg.iloc[0]).mean(axis=1).dropna()        # chỉ số EW trong kỳ
        if len(ew) < 2:
            continue
        daily = ew.pct_change().fillna(0.0)                    # lợi nhuận TỪNG phiên
        daily.iloc[0] = daily.iloc[0] - cost                   # phí vào
        daily.iloc[-1] = (1 + daily.iloc[-1]) * (1 - cost) - 1  # phí ra
        for d, v in daily.items():
            rets[pd.Timestamp(d)] = float(v)
        period_rets[pd.Timestamp(t)] = float(ew.iloc[-1] - 1)
    return pd.Series(rets).sort_index(), period_rets


# ──────────────────────────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────────────────────────
def run_backtest(panel: pd.DataFrame, market, cfg: dict | None = None,
                 start: str | None = None, end: pd.Timestamp | None = None) -> dict:
    cfg = {**config.BACKTEST, **(cfg or {})}
    start = start or config.BACKTEST_START
    end = pd.Timestamp(end or market.asof)
    r = market.risk_free
    history = History(panel)

    spacing = int(cfg.get("spacing", cfg["holding_days"]))
    grid = rebalance_dates(panel, start, end, spacing=spacing)
    signals = build_signals(history, grid, r, cfg)
    if not signals:
        return {"config": {}, "summary": {}, "curve": [], "trades": [],
                "n_trades_total": 0, "caveats": ["Không đủ dữ liệu để chạy backtest."]}

    top_fn = lambda d: select_top(d, cfg["top_n"], cfg["max_weight_per_issuer"])
    main = simulate(history, signals, cfg, top_fn, collect_trades=True)
    main_gross = simulate(history, signals, {**cfg, "cost_per_side": 0.0}, top_fn,
                          collect_trades=False)
    ew = simulate(history, signals, cfg, lambda d: d["ticker"].tolist(), collect_trades=False)

    random_rets = []
    for seed in range(10):
        rng = np.random.default_rng(seed)
        res = simulate(history, signals, cfg,
                       lambda d, rng=rng: list(rng.choice(
                           d["ticker"].tolist(), size=min(cfg["top_n"], len(d)), replace=False)),
                       collect_trades=False)
        if not res["equity"].empty:
            random_rets.append(res["equity"]["eq"])
    random_eq = pd.concat(random_rets, axis=1).mean(axis=1).sort_index() if random_rets else pd.Series(dtype=float)

    und, und_period = benchmark_underlying(market, signals, cfg, history.dates)
    und_eq = (1 + und.fillna(0)).cumprod() * 100

    eq_score = main["equity"]["eq"] if not main["equity"].empty else pd.Series(dtype=float)
    eq_ew = ew["equity"]["eq"] if not ew["equity"].empty else pd.Series(dtype=float)
    eq_gross = main_gross["equity"]["eq"] if not main_gross["equity"].empty else pd.Series(dtype=float)

    idx = sorted(set(eq_score.index) | set(eq_ew.index) | set(random_eq.index) | set(und_eq.index))
    idx = pd.DatetimeIndex(idx)
    curve = pd.DataFrame(index=idx)
    curve["eq_score"] = eq_score.reindex(idx).ffill()
    curve["eq_gross"] = eq_gross.reindex(idx).ffill()
    curve["eq_ew"] = eq_ew.reindex(idx).ffill()
    curve["eq_random"] = random_eq.reindex(idx).ffill()
    curve["eq_underlying"] = und_eq.reindex(idx).ffill()
    # mỗi chuỗi chuẩn hoá về 100 tại điểm đầu tiên của chính nó
    for col in ("eq_score", "eq_gross", "eq_ew", "eq_random", "eq_underlying"):
        s = curve[col].dropna()
        if len(s):
            curve[col] = curve[col] / s.iloc[0] * 100
    curve = curve.dropna(how="all")

    periods_per_year = config.TRADING_DAYS_PER_YEAR / max(spacing, 1)
    summary = {
        "score_top": metrics_from_equity(curve["eq_score"], spacing, r),
        "score_top_gross": metrics_from_equity(curve["eq_gross"], spacing, r),
        "ew_universe": metrics_from_equity(curve["eq_ew"], spacing, r),
        "random": metrics_from_equity(curve["eq_random"], spacing, r),
        "underlying_ew": metrics_from_equity(curve["eq_underlying"], spacing, r),
    }
    curve["dd_score"] = curve["eq_score"] / curve["eq_score"].cummax() - 1

    trades = main["trades"]
    fwd = forward_stats(history, signals, cfg)

    bucket_stats = []
    if not fwd.empty:
        for lo, hi, label in [(80, 101, "80–100"), (65, 80, "65–79"), (45, 65, "45–64"),
                              (30, 45, "30–44"), (0, 30, "0–29")]:
            sub = fwd[(fwd["score"] >= lo) & (fwd["score"] < hi)]
            if sub.empty:
                bucket_stats.append({"bucket": label, "n": 0})
                continue
            rr = pd.to_numeric(sub["ret_pct"], errors="coerce") / 100
            wins, losses = rr[rr > 0], rr[rr <= 0]
            bucket_stats.append({
                "bucket": label, "n": int(len(sub)),
                "avg_ret_pct": round(float(rr.mean()) * 100, 2),
                "median_ret_pct": round(float(rr.median()) * 100, 2),
                "win_rate_pct": round(float((rr > 0).mean()) * 100, 1),
                "p25_pct": round(float(rr.quantile(0.25)) * 100, 1),
                "p75_pct": round(float(rr.quantile(0.75)) * 100, 1),
                "profit_factor": round(float(wins.sum() / -losses.sum()), 2)
                if len(losses) and losses.sum() < 0 else None,
            })

    def _group_stats(df, col):
        if df is None or df.empty or col not in df:
            return []
        out = []
        for key, g in df.groupby(col):
            rr = pd.to_numeric(g["ret_pct"], errors="coerce") / 100
            out.append({"key": str(key), "n": int(len(g)),
                        "avg_ret_pct": round(float(rr.mean()) * 100, 2),
                        "median_ret_pct": round(float(rr.median()) * 100, 2),
                        "win_rate_pct": round(float((rr > 0).mean()) * 100, 1)})
        return sorted(out, key=lambda x: -x["n"])

    # ── theo chế độ thị trường (dựa trên benchmark cổ phiếu cơ sở của từng kỳ)
    per = main["periods"]
    regime = {}
    if not per.empty and und_period:
        und_map = und_period
        rows = []
        for _, p in per.iterrows():
            bench = und_map.get(p["date"])
            if bench is None:
                continue
            rows.append({"period": p["date"], "ret": p["ret"], "bench": bench})
        if rows:
            rg = pd.DataFrame(rows)
            for name, mask in (("up", rg["bench"] > 0), ("down", rg["bench"] <= 0)):
                sub = rg[mask]
                regime[name] = {
                    "n_periods": int(len(sub)),
                    "avg_ret_pct": round(float(sub["ret"].mean()) * 100, 2) if len(sub) else None,
                    "win_rate_pct": round(float((sub["ret"] > 0).mean()) * 100, 1) if len(sub) else None,
                    "avg_bench_pct": round(float(sub["bench"].mean()) * 100, 2) if len(sub) else None,
                }

    # ── lợi nhuận theo tháng (từ đường vốn theo ngày)
    monthly, monthly_cells = [], []
    if not curve.empty:
        m = (1 + curve["eq_score"].pct_change().fillna(0)).groupby(curve.index.to_period("M")).prod() - 1
        ew_m = (1 + curve["eq_ew"].pct_change().fillna(0)).groupby(curve.index.to_period("M")).prod() - 1
        und_m = (1 + curve["eq_underlying"].pct_change().fillna(0)).groupby(curve.index.to_period("M")).prod() - 1
        for k, v in m.items():
            monthly.append({
                "month": str(k), "label": k.strftime("%m/%Y"),
                "score_top_pct": round(float(v) * 100, 2),
                "ew_universe_pct": round(float(ew_m.get(k, np.nan)) * 100, 2) if pd.notna(ew_m.get(k, np.nan)) else None,
                "underlying_pct": round(float(und_m.get(k, np.nan)) * 100, 2) if pd.notna(und_m.get(k, np.nan)) else None,
            })
            monthly_cells.append({"y": int(k.year), "m": int(k.month), "v": round(float(v) * 100, 2)})

    trade_stats = trade_metrics(trades)

    # ── độ nhạy chi phí (mô phỏng lại với từng mức phí)
    cost_sensitivity = []
    for c in (0.0, 0.0025, 0.005, cfg["cost_per_side"], 0.02):
        sub_cfg = {**cfg, "cost_per_side": c}
        res = simulate(history, signals, sub_cfg, top_fn, collect_trades=False)
        eq = res["equity"]["eq"] if not res["equity"].empty else pd.Series(dtype=float)
        if eq.empty:
            continue
        cost_sensitivity.append({
            "cost_per_side_pct": round(c * 100, 2),
            "round_trip_pct": round(c * 200, 2),
            "total_return_pct": round(float(eq.iloc[-1] / eq.iloc[0] - 1) * 100, 2),
            "cagr_pct": round(float((eq.iloc[-1] / eq.iloc[0]) ** (config.TRADING_DAYS_PER_YEAR / max(len(eq), 1)) - 1) * 100, 2),
            "is_default": bool(abs(c - cfg["cost_per_side"]) < 1e-12),
        })

    # ── độ nhạy thời gian nắm giữ
    holding_sensitivity = []
    for hold in (5, 10, 20, 40):
        sub_cfg = {**cfg, "holding_days": hold}
        res = simulate(history, signals, sub_cfg, top_fn, collect_trades=True)
        m = trade_metrics(res["trades"]) if not res["trades"].empty else {}
        eq = res["equity"]["eq"] if not res["equity"].empty else pd.Series(dtype=float)
        holding_sensitivity.append({
            "holding_sessions": hold,
            "n_trades": m.get("n_trades"),
            "avg_trade_ret_pct": m.get("avg_return_pct"),
            "win_rate_pct": m.get("win_rate_pct"),
            "total_return_pct": round(float(eq.iloc[-1] / eq.iloc[0] - 1) * 100, 2) if not eq.empty else None,
        })

    # ── độ nhạy ngưỡng điểm
    gate_sensitivity = []
    for gate in (45, 65, 80):
        res = simulate(history, signals, cfg,
                       lambda d, g=gate: select_top(d[d["score"] >= g], cfg["top_n"],
                                                    cfg["max_weight_per_issuer"]),
                       collect_trades=True, gate=gate)
        m = trade_metrics(res["trades"]) if not res["trades"].empty else {}
        eq = res["equity"]["eq"] if not res["equity"].empty else pd.Series(dtype=float)
        gate_sensitivity.append({
            "score_gate": gate,
            "n_trades": m.get("n_trades"),
            "avg_trade_ret_pct": m.get("avg_return_pct"),
            "win_rate_pct": m.get("win_rate_pct"),
            "total_return_pct": round(float(eq.iloc[-1] / eq.iloc[0] - 1) * 100, 2) if not eq.empty else None,
        })

    # ── độ nhạy stop-loss / take-profit (có vs không)
    stop_sensitivity = []
    for label, ws in (("Có stop-loss / take-profit", True),
                      ("Không stop / không TP", False)):
        res = simulate(history, signals, cfg, top_fn, collect_trades=True, with_stops=ws)
        m = trade_metrics(res["trades"]) if not res["trades"].empty else {}
        eq = res["equity"]["eq"] if not res["equity"].empty else pd.Series(dtype=float)
        stop_sensitivity.append({
            "variant": label,
            "with_stops": ws,
            "n_trades": m.get("n_trades"),
            "avg_trade_ret_pct": m.get("avg_return_pct"),
            "median_trade_ret_pct": m.get("median_return_pct"),
            "win_rate_pct": m.get("win_rate_pct"),
            "profit_factor": m.get("profit_factor"),
            "avg_holding_sessions": m.get("avg_holding_sessions"),
            "total_return_pct": round(float(eq.iloc[-1] / eq.iloc[0] - 1) * 100, 2)
            if not eq.empty else None,
            "max_drawdown_pct": round(float((eq / eq.cummax() - 1).min()) * 100, 2)
            if not eq.empty else None,
        })

    # ── kiểm định bộ lọc kinh tế (công bố toàn bộ, kể cả kết quả xấu)
    filter_tests = []
    filters = {
        "Cơ sở: top-5 theo CW Score": lambda d: d,
        "Chỉ mua khi IV ≤ HV": lambda d: d[d["iv_vs_hv"] <= 0],
        "Chỉ mua khi IV thấp hơn smile cùng underlying": lambda d: d[d["iv_resid"] <= 0],
        "Chỉ mua khi cổ phiếu cơ sở trên MA50": lambda d: d[d["u_above_ma50"] == 1],
        "IV ≤ HV và trên MA50": lambda d: d[(d["iv_vs_hv"] <= 0) & (d["u_above_ma50"] == 1)],
        "Chỉ CW Score ≥ 80": lambda d: d[d["score"] >= 80],
        "ADV20 ≥ 50 triệu": lambda d: d[d["adv20"] >= 50e6],
        "ADV20 ≥ 200 triệu": lambda d: d[d["adv20"] >= 200e6],
        "ADV20 ≥ 500 triệu": lambda d: d[d["adv20"] >= 500e6],
        "Độ phủ giao dịch ≥ 80% (từ niêm yết)": lambda d: d[d["coverage_listing"].fillna(d["coverage20"]) >= 80],
        "Amihud20 ≤ trung vị vũ trụ": lambda d: d[d["amihud20"] <= d["amihud20"].median()],
        "Biên độ high-low ≤ 10%": lambda d: d[d["range20"] <= 10],
        "IV ≤ HV và ADV ≥ 200 triệu": lambda d: d[(d["iv_vs_hv"] <= 0) & (d["adv20"] >= 200e6)],
        "IV ≤ HV và Amihud ≤ trung vị": lambda d: d[(d["iv_vs_hv"] <= 0)
                                                    & (d["amihud20"] <= d["amihud20"].median())],
        "IV ≤ HV và biên độ ≤ 10%": lambda d: d[(d["iv_vs_hv"] <= 0) & (d["range20"] <= 10)],
    }
    filters_en = {
        "Cơ sở: top-5 theo CW Score": "Base: top-5 by CW Score",
        "Chỉ mua khi IV ≤ HV": "Only buy when IV ≤ HV",
        "Chỉ mua khi IV thấp hơn smile cùng underlying":
            "Only buy when IV is below the same-underlying smile",
        "Chỉ mua khi cổ phiếu cơ sở trên MA50": "Only buy when the underlying is above MA50",
        "IV ≤ HV và trên MA50": "IV ≤ HV and above MA50",
        "Chỉ CW Score ≥ 80": "Only CW Score ≥ 80",
        "ADV20 ≥ 50 triệu": "ADV20 ≥ VND 50m",
        "ADV20 ≥ 200 triệu": "ADV20 ≥ VND 200m",
        "ADV20 ≥ 500 triệu": "ADV20 ≥ VND 500m",
        "Độ phủ giao dịch ≥ 80% (từ niêm yết)": "Trading coverage ≥ 80% (since listing)",
        "Amihud20 ≤ trung vị vũ trụ": "Amihud20 ≤ universe median",
        "Biên độ high-low ≤ 10%": "High-low range ≤ 10%",
        "IV ≤ HV và ADV ≥ 200 triệu": "IV ≤ HV and ADV ≥ VND 200m",
        "IV ≤ HV và Amihud ≤ trung vị": "IV ≤ HV and Amihud ≤ median",
        "IV ≤ HV và biên độ ≤ 10%": "IV ≤ HV and range ≤ 10%",
    }
    for label, fn in filters.items():
        res = simulate(history, signals, cfg,
                       lambda d, fn=fn: select_top(fn(d), cfg["top_n"],
                                                   cfg["max_weight_per_issuer"]),
                       collect_trades=True)
        m = trade_metrics(res["trades"])
        eq = res["equity"]["eq"] if not res["equity"].empty else pd.Series(dtype=float)
        filter_tests.append({
            "filter": label,
            "filter_en": filters_en.get(label, label),
            "n_trades": m.get("n_trades", 0),
            "avg_trade_ret_pct": m.get("avg_return_pct"),
            "win_rate_pct": m.get("win_rate_pct"),
            "profit_factor": m.get("profit_factor"),
            "total_return_pct": round(float(eq.iloc[-1] / eq.iloc[0] - 1) * 100, 2) if not eq.empty else None,
        })
    filter_tests.sort(key=lambda x: (x["total_return_pct"] is None, -(x["total_return_pct"] or -1e9)))

    # ── bằng chứng thanh khoản cho trang Thanh khoản: lợi nhuận kỳ hạn theo nhóm ADV20
    liquidity_block: dict = {}
    if not fwd.empty and "adv20" in fwd.columns:
        net = pd.to_numeric(fwd["ret_pct"], errors="coerce") - cfg["cost_per_side"] * 200
        d = fwd.assign(net_pct=net).dropna(subset=["net_pct", "adv20"])
        d = d[pd.to_numeric(d["adv20"], errors="coerce") > 0]
        if len(d) >= 100:
            d = d.assign(q=pd.qcut(d["adv20"], 5, labels=False, duplicates="drop") + 1)
            quints = []
            for q, g in d.groupby("q"):
                rr = g["net_pct"]
                quints.append({
                    "quintile": int(q),
                    "advLow": round(float(g["adv20"].min()), 0),
                    "advHigh": round(float(g["adv20"].max()), 0),
                    "n": int(len(g)),
                    "avg_ret_pct": round(float(rr.mean()), 2),
                    "median_ret_pct": round(float(rr.median()), 2),
                    "win_rate_pct": round(float((rr > 0).mean()) * 100, 1),
                })
            gates = []
            for adv in (10e6, 50e6, 200e6, 500e6):
                sub = d[d["adv20"] >= adv]
                if sub.empty:
                    continue
                rr = sub["net_pct"]
                gates.append({
                    "adv": float(adv),
                    "share_pct": round(len(sub) / len(d) * 100, 1),
                    "n": int(len(sub)),
                    "avg_ret_pct": round(float(rr.mean()), 2),
                    "win_rate_pct": round(float((rr > 0).mean()) * 100, 1),
                })
            liquidity_block = {
                "quintiles": quints,
                "gates": gates,
                "note": (f"Toàn bộ CW đủ điều kiện ở mỗi ngày tín hiệu (không chỉ top-{cfg['top_n']}), "
                         f"lợi nhuận {int(cfg['holding_days'])} phiên đã trừ chi phí "
                         f"{cfg['cost_per_side'] * 200:.2f}%/vòng."),
            }

    n_signal_dates = len(signals)
    strat = summary["score_top"]
    gross = summary["score_top_gross"]
    cost_drag = None
    if strat.get("total_return_pct") is not None and gross.get("total_return_pct") is not None:
        cost_drag = round(strat["total_return_pct"] - gross["total_return_pct"], 2)

    def _row(r, keys):
        return {k: (round(float(r[k]), 4) if isinstance(r[k], (int, float, np.floating)) and pd.notna(r[k]) else r[k])
                for k in keys if k in r}

    return {
        "config": {
            "start": min(signals).strftime("%Y-%m-%d"),
            "end": pd.Timestamp(end).strftime("%Y-%m-%d"),
            "rebalance": f"mỗi {spacing} phiên",
            "rebalance_sessions": spacing,
            "holding_sessions": cfg["holding_days"],
            "top_n": cfg["top_n"],
            "min_days_to_maturity": cfg["min_days_to_maturity"],
            "min_median_value_vnd": cfg["min_median_value_vnd"],
            "max_weight_per_issuer": cfg["max_weight_per_issuer"],
            "cost_per_side_bps": round(cfg["cost_per_side"] * 10_000, 1),
            "cost_per_side_pct": round(cfg["cost_per_side"] * 100, 2),
            "round_trip_pct": round(cfg["cost_per_side"] * 200, 2),
            "cost_breakdown": {
                "commission_pct": round(cfg["commission_per_side"] * 100, 2),
                "slippage_pct": round(cfg["slippage_per_side"] * 100, 2),
                "half_spread_pct": round(cfg["half_spread"] * 100, 2),
            },
            "risk_free": round(float(r), 4),
            "n_signal_dates": n_signal_dates,
            "n_sessions": int(len(curve)),
        },
        "summary": summary,
        "cost_drag_pct": cost_drag,
        "curve": [
            {"date": d.strftime("%Y-%m-%d"),
             "eq_score": round(float(row["eq_score"]), 2) if pd.notna(row["eq_score"]) else None,
             "eq_gross": round(float(row["eq_gross"]), 2) if pd.notna(row["eq_gross"]) else None,
             "eq_ew": round(float(row["eq_ew"]), 2) if pd.notna(row["eq_ew"]) else None,
             "eq_random": round(float(row["eq_random"]), 2) if pd.notna(row["eq_random"]) else None,
             "eq_underlying": round(float(row["eq_underlying"]), 2) if pd.notna(row["eq_underlying"]) else None,
             "dd_score": round(float(row["dd_score"]) * 100, 2) if pd.notna(row["dd_score"]) else None}
            for d, row in curve.iterrows()
        ],
        "monthly": monthly,
        "monthly_matrix": {"cells": monthly_cells},
        "regime": regime,
        "trade_stats": trade_stats,
        "trades": trades.sort_values("entry_date").tail(300).to_dict("records") if not trades.empty else [],
        "n_trades_total": int(len(trades)),
        "buckets": bucket_stats,
        "by_issuer": _group_stats(trades, "issuer"),
        "by_underlying": _group_stats(trades, "underlying"),
        "cost_sensitivity": cost_sensitivity,
        "stop_sensitivity": stop_sensitivity,
        "liquidity": liquidity_block,
        "holding_sensitivity": holding_sensitivity,
        "gate_sensitivity": gate_sensitivity,
        "filter_sensitivity": filter_tests,
        "caveats": [
            "Vào lệnh tại giá đóng cửa phiên kế tiếp sau ngày tín hiệu; không mô phỏng khớp lệnh trong phiên.",
            "Không có dữ liệu bid/ask thật: giả định nửa chênh lệch 0,50% + hoa hồng 0,15% + trượt giá 0,30% mỗi chiều (1,90%/vòng).",
            "Không mô phỏng giới hạn khối lượng: CW dưới 50 triệu VND/phiên sẽ khó khớp hơn giả định.",
            "Stop-loss/TP mô phỏng trên dữ liệu ngày, chỉ tính từ phiên sau khi vào lệnh; gap qua ngưỡng thì khớp tại giá mở cửa.",
            "Vị thế đóng giữa kỳ được giữ dưới dạng tiền mặt tới hết kỳ (không tái đầu tư ngay).",
            "Điều khoản CW (strike/ratio điều chỉnh) lấy từ snapshot hiện tại — có thể lệch nếu có điều chỉnh cổ tức trong quá khứ.",
            "Lãi suất phi rủi ro dùng hằng số hiện tại cho toàn bộ giai đoạn (cache HNX chỉ có 57 phiên).",
            "Số kỳ tái cân bằng ít → sai số thống kê lớn; kết quả không phải kỳ vọng chắc chắn.",
        ],
        "caveats_en": [
            "Entry at the close of the session after the signal date; no intraday fills are simulated.",
            "No real bid/ask data: assumes a 0.50% half-spread + 0.15% commission + 0.30% slippage per side (1.90% round trip).",
            "No volume limits are simulated: warrants trading under VND 50m/session are harder to fill than assumed.",
            "Stop-loss/take-profit are simulated on daily data, starting only from the session after entry; if the open gaps through a level, the fill is assumed at the open.",
            "A position closed mid-period is held as cash until the period ends (no immediate reinvestment).",
            "Warrant terms (strike/ratio) come from the current snapshot — they can differ if dividends were adjusted in the past.",
            "The risk-free rate is a constant applied to the whole period (the HNX cache covers only 57 sessions).",
            f"Only {n_signal_dates} rebalance periods → large statistical error; the result is not a firm expectation.",
        ],
    }
