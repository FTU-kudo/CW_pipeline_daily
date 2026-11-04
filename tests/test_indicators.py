"""Kiểm thử chỉ báo kỹ thuật và xử lý ngày."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from cwintel import indicators as ta
from cwintel.dates import parse_date, parse_dates, parse_numbers


def test_sma_matches_manual():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = ta.sma(s, 3)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[4] == pytest.approx(4.0)


def test_ema_converges_to_constant():
    s = pd.Series([10.0] * 60)
    out = ta.ema(s, 12)
    assert out.iloc[-1] == pytest.approx(10.0, abs=1e-9)


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.linspace(10, 30, 60))
    dn = pd.Series(np.linspace(30, 10, 60))
    assert ta.rsi(up, 14).iloc[-1] == pytest.approx(100.0, abs=1e-6)
    assert ta.rsi(dn, 14).iloc[-1] == pytest.approx(0.0, abs=1e-6)
    rnd = pd.Series(np.random.default_rng(0).normal(100, 2, 200).cumsum())
    r = ta.rsi(rnd, 14).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_macd_relationship():
    s = pd.Series(np.linspace(10, 20, 120) + np.sin(np.arange(120) / 5))
    m = ta.macd(s)
    assert {"macd", "signal", "hist"}.issubset(m.columns)
    # hist = macd − signal
    diff = (m["macd"] - m["signal"] - m["hist"]).abs().max()
    assert diff < 1e-9


def test_atr_positive_and_flat_series():
    n = 40
    close = pd.Series([100.0] * n)
    high = close + 1.0
    low = close - 1.0
    a = ta.atr(high, low, close, 14)
    assert a.dropna().gt(0).all()
    # chuỗi phẳng biên độ 2 → ATR tiến về 2
    assert a.iloc[-1] == pytest.approx(2.0, abs=1e-6)


def test_log_returns_and_hv():
    px = pd.Series([100.0, 110.0, 99.0, 121.0])
    lr = ta.log_returns(px)
    assert lr.iloc[1] == pytest.approx(math.log(1.1))
    # log-return xen kẽ ±1% → std mẫu ≈ 1% → HV ≈ 1%·√252
    logr = np.array([0.01 if i % 2 == 0 else -0.01 for i in range(251)])
    prices = 100 * np.exp(np.concatenate([[0.0], np.cumsum(logr)]))
    expected = logr.std(ddof=1) * math.sqrt(252)
    assert ta.hv_from_prices(prices) == pytest.approx(expected, rel=0.02)
    # chuỗi tăng đều → biến động ~0
    flat = 100 * np.exp(0.001 * np.arange(252))
    assert ta.hv_from_prices(flat) < 1e-6


def test_percentile_rank_monotone():
    s = pd.Series([5.0, 1.0, 3.0, 2.0, 4.0])
    p = ta.percentile_rank(s)
    assert p.idxmax() == 0 and p.idxmin() == 1
    assert p.max() == pytest.approx(100.0) and p.min() == pytest.approx(20.0)


def test_turnover_value_unit():
    """Giá VND × khối lượng = giá trị VND."""
    out = ta.turnover_value(pd.Series([10_000.0]), pd.Series([1_000.0]))
    assert out.iloc[0] == pytest.approx(1e7)


def test_parse_date_formats():
    assert parse_date("2024-03-14") == pd.Timestamp("2024-03-14")
    assert parse_date("14/03/2024") == pd.Timestamp("2024-03-14")
    assert parse_date("14/3/2024") == pd.Timestamp("2024-03-14")
    # ISO có timezone +07:00 phải quy về đúng ngày giao dịch
    assert parse_date("2024-03-14T07:00:00+07:00") == pd.Timestamp("2024-03-14")
    assert parse_date("bad") is None
    assert parse_date(None) is None


def test_parse_dates_dedupes_equivalent_formats():
    """Cùng một phiên ở 2 định dạng phải cho cùng Timestamp (nguồn gốc lỗi trùng lặp)."""
    s = pd.Series(["2024-03-14", "14/03/2024", "2024-03-15"])
    out = parse_dates(s)
    assert out.iloc[0] == out.iloc[1] == pd.Timestamp("2024-03-14")


def test_parse_numbers_handles_vietnamese_format():
    s = pd.Series(["1.234,5", "12,345.6", "1,000", "abc", None])
    out = parse_numbers(s)
    assert out.iloc[0] == pytest.approx(1234.5)
    assert out.iloc[1] == pytest.approx(12345.6)
    assert out.iloc[2] == pytest.approx(1000.0)
    assert np.isnan(out.iloc[3]) and np.isnan(out.iloc[4])
