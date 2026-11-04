"""Kiểm thử khung backtest: chống look-ahead, chọn lọc, thống kê."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cwintel import config
from cwintel.backtest import (
    History, benchmark_underlying, eligible, equity_metrics, metrics_from_equity, prefilter,
    rebalance_dates, select_top, simulate, trade_metrics,
)


def test_rows_asof_never_uses_future(synthetic_panel):
    h = History(synthetic_panel)
    asof = pd.Timestamp("2024-01-31")
    rows = h.rows_asof(asof, tolerance_days=7)
    assert not rows.empty
    assert (rows["date"] <= asof).all()


def test_rows_asof_respects_tolerance(synthetic_panel):
    h = History(synthetic_panel)
    last = synthetic_panel["date"].max()
    rows = h.rows_asof(last + pd.Timedelta(days=30), tolerance_days=7)
    assert rows.empty


def test_rows_asof_one_row_per_ticker(synthetic_panel):
    h = History(synthetic_panel)
    rows = h.rows_asof(pd.Timestamp("2024-02-15"), tolerance_days=7)
    assert rows["ticker"].is_unique


def test_next_session_is_strictly_after(synthetic_panel):
    h = History(synthetic_panel)
    t = pd.Timestamp("2024-01-31")
    pos = h.next_session("CAAA2401", t)
    assert pos is not None
    h1 = h.ticker_series("CAAA2401")
    assert pd.Timestamp(h1["dates"][pos]) > t


def test_forward_path_within_bounds(synthetic_panel):
    h = History(synthetic_panel)
    entry = 10
    start, end = h.forward_path("CAAA2401", entry, sessions=500)
    assert start == entry
    assert end <= len(h.ticker_series("CAAA2401")["dates"]) - 1


def test_rebalance_dates_spacing(synthetic_panel):
    dates = rebalance_dates(synthetic_panel, start="2024-01-02",
                            end=synthetic_panel["date"].max(), spacing=20)
    assert len(dates) >= 2
    assert dates == sorted(dates)
    assert dates[1] > dates[0]


def test_prefilter_and_eligible_filters(synthetic_panel):
    cfg = dict(config.BACKTEST)
    df = synthetic_panel.copy()
    df.loc[df.index[:5], "days_to_maturity"] = 5
    df.loc[df.index[5:10], "value_med20"] = 0.0
    pre = prefilter(df, cfg)
    assert pre["days_to_maturity"].min() >= cfg["min_days_to_maturity"]
    assert pre["value_med20"].min() >= cfg["min_median_value_vnd"]

    df2 = df.copy()
    df2["data_quality"] = 0.9
    df2.loc[df2.index[0], "data_quality"] = 0.1
    el = eligible(df2, cfg)
    assert el["data_quality"].min() >= 0.6


def test_select_top_respects_issuer_cap():
    df = pd.DataFrame({
        "ticker": [f"T{i}" for i in range(10)],
        "issuer": ["A"] * 6 + ["B"] * 4,
        "score": list(range(100, 90, -1)),
    })
    picks = select_top(df, n=5, max_issuer_weight=0.40)
    # trần 40% của 5 = 2 mã / TCPH → không thể lấp đầy 5 khi chỉ có 2 TCPH
    assert 1 <= len(picks) <= 5
    per_issuer = df.set_index("ticker").loc[picks, "issuer"].value_counts()
    assert per_issuer.max() <= 2


def test_equity_metrics_known_series():
    r = pd.Series([0.10, -0.05, 0.02, 0.03])
    m = equity_metrics(r, periods_per_year=12)
    assert m["total_return_pct"] == pytest.approx((1.10 * 0.95 * 1.02 * 1.03 - 1) * 100, abs=0.01)
    assert m["max_drawdown_pct"] <= 0
    assert m["positive_periods_pct"] == pytest.approx(75.0)


def test_equity_metrics_flat_series():
    m = equity_metrics(pd.Series([0.0] * 10), periods_per_year=12)
    assert m["total_return_pct"] == 0.0
    assert m["max_drawdown_pct"] == 0.0


def test_trade_metrics_units():
    trades = pd.DataFrame({
        "ret_pct": [10.0, -5.0, 20.0, -10.0],
        "holding_sessions": [5, 10, 5, 20],
        "stop_hit": [False, True, False, True],
        "tp_hit": [True, False, True, False],
    })
    m = trade_metrics(trades)
    assert m["n_trades"] == 4
    assert m["win_rate_pct"] == pytest.approx(50.0)
    assert m["avg_return_pct"] == pytest.approx(3.75, abs=0.01)
    assert m["profit_factor"] == pytest.approx(30.0 / 15.0, abs=1e-6)
    assert m["stop_hit_rate_pct"] == pytest.approx(50.0)


def test_backtest_no_lookahead_price_choice(synthetic_panel):
    """Giá vào lệnh phải là phiên sau tín hiệu, không phải phiên tín hiệu."""
    h = History(synthetic_panel)
    t = pd.Timestamp("2024-01-31")
    pos = h.next_session("CAAA2401", t)
    entry_date = pd.Timestamp(h.ticker_series("CAAA2401")["dates"][pos])
    assert entry_date > t


# ──────────────────────────────────────────────────────────────────
# MARK-TO-MARKET, CHI PHÍ, STOP-LOSS
# ──────────────────────────────────────────────────────────────────
def _manual_signals(panel: pd.DataFrame, dates, score: float = 80.0) -> dict:
    """Signals tối thiểu cho `simulate` — bỏ qua bước scoring để test cơ chế."""
    out = {}
    for t in dates:
        rows = panel[panel["date"] == t]
        out[pd.Timestamp(t)] = pd.DataFrame({
            "ticker": rows["ticker"].values,
            "issuer": rows["issuer"].values,
            "underlying": rows["underlying"].values,
            "score": score,
            "close": rows["close"].values,
            "days_to_maturity": rows["days_to_maturity"].values,
            "value_med20": rows["value_med20"].values,
            "sessions": rows["sessions"].values,
            "data_quality": rows["data_quality"].values,
            "atr14": 10.0,
        })
    return out


def test_metrics_from_equity_uses_daily_drawdown():
    """MDD phải lấy từ đường vốn từng phiên, không phải từ điểm cuối mỗi kỳ."""
    eq = pd.Series([100.0, 90.0, 110.0, 120.0, 80.0, 130.0])
    m = metrics_from_equity(eq, spacing=2)
    assert m["total_return_pct"] == pytest.approx(30.0, abs=0.01)
    # đáy 80 sau đỉnh 120 → −33,33% (nếu chỉ lấy điểm cuối kỳ sẽ ra −27,27%)
    assert m["max_drawdown_pct"] == pytest.approx(-33.33, abs=0.02)
    assert m["final_equity"] == pytest.approx(130.0, abs=0.01)


def test_simulate_charges_cost_on_both_sides(synthetic_panel):
    h = History(synthetic_panel)
    dates = rebalance_dates(synthetic_panel, start="2024-01-10",
                            end=synthetic_panel["date"].max(), spacing=20)[:2]
    sig = _manual_signals(synthetic_panel, dates)
    cfg = {**config.BACKTEST, "holding_days": 10, "spacing": 20,
           "cost_per_side": 0.0, "use_stops": False}

    free = simulate(h, sig, cfg, lambda d: d["ticker"].tolist())
    paid = simulate(h, sig, {**cfg, "cost_per_side": 0.01}, lambda d: d["ticker"].tolist())

    eq_free = free["equity"]["eq"]
    eq_paid = paid["equity"]["eq"]
    assert eq_paid.iloc[-1] < eq_free.iloc[-1]

    n_periods = len(free["periods"])
    assert n_periods >= 1
    # mỗi kỳ trả (1 − c) khi vào và (1 − c) khi ra → đúng (1 − c)^(2k)
    ratio = eq_paid.iloc[-1] / eq_free.iloc[-1]
    assert ratio == pytest.approx((1 - 0.01) ** (2 * n_periods), rel=0.02)


def test_trade_ret_is_gross_minus_round_trip_cost(synthetic_panel):
    h = History(synthetic_panel)
    dates = rebalance_dates(synthetic_panel, start="2024-01-10",
                            end=synthetic_panel["date"].max(), spacing=20)[:2]
    sig = _manual_signals(synthetic_panel, dates)
    cfg = {**config.BACKTEST, "holding_days": 10, "spacing": 20, "cost_per_side": 0.01}
    res = simulate(h, sig, cfg, lambda d: d["ticker"].tolist())
    trades = res["trades"]
    assert not trades.empty
    for _, t in trades.iterrows():
        expected = ((1 + t["gross_ret_pct"] / 100) * (1 - 0.01) ** 2 - 1) * 100
        assert t["ret_pct"] == pytest.approx(expected, abs=0.02)


def _small_panel(n: int = 40, entry_breaches_stop: bool = False,
                 gap_after_entry: bool = False) -> pd.DataFrame:
    """Panel 3 mã giá phẳng 1000, ATR giả định 10 → stop = 980 (cần ≥3 mã để `simulate` chạy)."""
    dates = pd.bdate_range("2024-01-02", periods=n)
    rows = []
    for i, (ticker, iss) in enumerate([("CXXX2401", "ssi"), ("CXXX2402", "vndirect"),
                                       ("CZZZ2401", "hsc")]):
        for j, d in enumerate(dates):
            px, low, op = 1000.0, 995.0, 1000.0
            if j == 6:                      # phiên khớp lệnh (entry)
                low = 990.0
                if entry_breaches_stop:
                    low, op = 900.0, 900.0
            if gap_after_entry and j == 7:   # gap qua stop ở phiên sau entry
                low, op = 940.0, 950.0
            rows.append({"ticker": ticker, "underlying": ticker[:4], "issuer": iss,
                         "date": d, "close": px, "open": op, "high": px * 1.01, "low": low,
                         "volume": 100_000.0, "value": px * 100_000.0,
                         "value_med20": px * 100_000.0, "days_to_maturity": 120 - j,
                         "sessions": 30 + j, "data_quality": 0.95, "score": 80.0})
    return pd.DataFrame(rows)


def test_stop_never_triggers_on_entry_session():
    """Low của chính phiên vào lệnh không được kích hoạt stop."""
    panel = _small_panel(entry_breaches_stop=True)
    h = History(panel)
    sig = _manual_signals(panel, [panel["date"].iloc[5]])
    cfg = {**config.BACKTEST, "holding_days": 10, "spacing": 10, "cost_per_side": 0.0}
    res = simulate(h, sig, cfg, lambda d: d["ticker"].tolist())
    trades = res["trades"]
    assert len(trades) == 3
    tr = trades[trades["ticker"] == "CXXX2401"].iloc[0]
    assert tr["exit_reason"] != "stop"
    assert tr["exit_date"] > tr["entry_date"]


def test_stop_gap_fills_at_open():
    """Gap qua stop → khớp ở giá mở cửa (thận trọng), không phải giá stop."""
    panel = _small_panel(gap_after_entry=True)
    h = History(panel)
    sig = _manual_signals(panel, [panel["date"].iloc[5]])
    cfg = {**config.BACKTEST, "holding_days": 10, "spacing": 10, "cost_per_side": 0.0}
    res = simulate(h, sig, cfg, lambda d: d["ticker"].tolist())
    tr = res["trades"][res["trades"]["ticker"] == "CXXX2401"].iloc[0]
    assert tr["exit_reason"] == "stop"
    assert tr["exit"] == pytest.approx(950.0)          # giá mở cửa, thấp hơn stop 980
    assert pd.Timestamp(tr["exit_date"]) == panel["date"].iloc[7]


def test_no_stops_holds_full_horizon():
    panel = _small_panel(gap_after_entry=True)
    h = History(panel)
    sig = _manual_signals(panel, [panel["date"].iloc[5]])
    cfg = {**config.BACKTEST, "holding_days": 10, "spacing": 10, "cost_per_side": 0.0}
    res = simulate(h, sig, cfg, lambda d: d["ticker"].tolist(), with_stops=False)
    tr = res["trades"][res["trades"]["ticker"] == "CXXX2401"].iloc[0]
    assert tr["exit_reason"] == "horizon"
    assert tr["holding_sessions"] == 10


def test_equity_path_is_daily_not_per_period(synthetic_panel):
    """Đường vốn phải có một điểm mỗi phiên, nhiều hơn hẳn số kỳ tái cân bằng."""
    h = History(synthetic_panel)
    dates = rebalance_dates(synthetic_panel, start="2024-01-10",
                            end=synthetic_panel["date"].max(), spacing=20)[:2]
    sig = _manual_signals(synthetic_panel, dates)
    cfg = {**config.BACKTEST, "holding_days": 20, "spacing": 20, "cost_per_side": 0.01,
           "use_stops": False}
    res = simulate(h, sig, cfg, lambda d: d["ticker"].tolist())
    eq = res["equity"]["eq"]
    # mỗi kỳ ~21 phiên → nhiều điểm hơn hẳn số kỳ
    assert len(eq) >= len(res["periods"]) * 15
    assert (eq > 0).all()
    assert eq.index.is_monotonic_increasing


def test_benchmark_underlying_returns_daily_not_cumulative(synthetic_panel):
    """Benchmark phải trả lợi nhuận TỪNG phiên (không phải cumulative của cả kỳ)."""
    from types import SimpleNamespace

    und = (synthetic_panel[["date", "underlying", "close"]]
           .rename(columns={"underlying": "ticker"})
           .groupby(["ticker", "date"], as_index=False)["close"].last())
    market = SimpleNamespace(underlying=und, asof=synthetic_panel["date"].max(), risk_free=0.03)

    dates = [pd.Timestamp(d) for d in synthetic_panel["date"].unique()[10::20]][:2]
    sig = {d: pd.DataFrame({"ticker": ["CAAA2401"]}) for d in dates}
    cfg = {**config.BACKTEST, "holding_days": 10}
    daily, period = benchmark_underlying(market, sig, cfg, None)

    assert not daily.empty
    # lợi nhuận từng phiên phải nhỏ; nếu trả cumulative sẽ có giá trị ~ hàng chục %
    assert daily.abs().max() < 0.15
    assert set(period).issubset(set(dates))

    # ghép các phiên trong kỳ đầu phải xấp xỉ lợi nhuận cả kỳ (đã trừ chi phí 2 chiều)
    t0 = dates[0]
    pos = und[und["ticker"] == "AAA"]["date"].searchsorted(t0, side="right")
    p = und[und["ticker"] == "AAA"].sort_values("date")
    seg_start, seg_end = p["date"].iloc[pos], p["date"].iloc[min(pos + 10, len(p) - 1)]
    seg = daily[(daily.index >= seg_start) & (daily.index <= seg_end)]
    compounded = float((1 + seg).prod() - 1)
    assert compounded == pytest.approx(period[t0], abs=0.01)
