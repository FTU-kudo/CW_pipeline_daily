"""Kiểm thử khung backtest: chống look-ahead, chọn lọc, thống kê."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cwintel import config
from cwintel.backtest import (
    History, equity_metrics, eligible, prefilter, rebalance_dates, select_top, trade_metrics,
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
