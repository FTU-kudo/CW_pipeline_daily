"""Kiểm thử tầng thanh khoản: công thức, lịch đầy đủ, cờ cảnh báo và cổng khuyến nghị."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cwintel import liquidity as liq
from cwintel import scoring


def _panel(n_days: int = 40, skip_every: int = 0, start: str = "2026-01-05") -> tuple[pd.DataFrame, pd.DataFrame]:
    cal = pd.bdate_range(start, periods=n_days)
    rows = []
    for i, d in enumerate(cal):
        traded = True if skip_every == 0 else (i % skip_every != 0)
        volume = 1e5 if traded else 0.0
        close = 1000.0 + i
        rows.append({
            "ticker": "AAA1", "date": d, "close": close,
            "high": close * 1.05, "low": close * 0.95,
            "volume": volume, "value": close * volume,
        })
    panel = pd.DataFrame(rows)
    master = pd.DataFrame([{"ticker": "AAA1", "outstanding_volume": 1e7,
                            "first_trade": cal[0]}])
    return panel, master


def test_days_to_liquidate_and_impact_bounds():
    assert liq.days_to_liquidate(50e6, 50e6) == pytest.approx(5.0)
    assert liq.days_to_liquidate(50e6, 0) != liq.days_to_liquidate(50e6, 0)  # NaN
    assert liq.days_to_liquidate(0, 50e6) != liq.days_to_liquidate(0, 50e6)
    # tác động tăng theo căn bậc hai của quy mô
    i1 = liq.impact_pct(0.05, 50e6, 100e6)
    i2 = liq.impact_pct(0.05, 200e6, 100e6)
    assert i2 == pytest.approx(2 * i1, rel=1e-6)
    assert liq.impact_pct(0.05, 50e6, 0) != liq.impact_pct(0.05, 50e6, 0)


def test_adv_counts_untraded_sessions_as_zero():
    panel, master = _panel(40, skip_every=2)   # cứ 2 phiên nghỉ 1 phiên
    out = liq.attach_liquidity(panel, master)
    last = out.iloc[-1]
    # 20 phiên gần nhất chỉ có 10 phiên giao dịch → ADV = tổng GT / 20
    assert last["coverage20"] == pytest.approx(50.0, abs=1.0)
    traded_value = out.tail(20).query("volume > 0")["value"].sum()
    assert last["adv20"] == pytest.approx(traded_value / 20, rel=1e-6)
    assert last["zero20"] == pytest.approx(10, abs=1)
    assert last["dtl_50m"] == pytest.approx(50e6 / (0.2 * last["adv20"]), rel=1e-6)


def test_coverage_listing_does_not_penalise_new_warrant():
    cal = pd.bdate_range("2026-01-05", periods=40)
    # CW mới niêm yết 8 phiên, giao dịch đủ cả 8 phiên
    rows = [{"ticker": "NEW1", "date": d, "close": 1000.0, "high": 1050.0, "low": 950.0,
             "volume": 1e5, "value": 1e8} for d in cal[-8:]]
    panel = pd.DataFrame(rows)
    master = pd.DataFrame([{"ticker": "NEW1", "outstanding_volume": 1e7,
                            "first_trade": cal[-8]}])
    out = liq.attach_liquidity(panel, master, calendar=cal)
    last = out.iloc[-1]
    assert last["sessions_listed"] == 8
    assert last["coverage_listing"] == pytest.approx(100.0)
    assert not any("Chỉ giao dịch" in f for f in liq.liquidity_flags(last))


def test_coverage_detects_gaps_inside_trading_range():
    cal = pd.bdate_range("2026-01-05", periods=40)
    rows = []
    for i, d in enumerate(cal):
        traded = (i % 4 == 0)          # chỉ giao dịch 1/4 số phiên
        rows.append({"ticker": "SPAR1", "date": d, "close": 1000.0, "high": 1050.0,
                     "low": 950.0, "volume": 1e5 if traded else 0.0,
                     "value": 1e8 if traded else 0.0})
    panel = pd.DataFrame(rows)
    master = pd.DataFrame([{"ticker": "SPAR1", "outstanding_volume": 1e7,
                            "first_trade": cal[0]}])
    out = liq.attach_liquidity(panel, master, calendar=cal)
    last = out.iloc[-1]
    assert 20 <= last["coverage20"] <= 30
    assert last["zero20"] >= 5
    assert last["coverage_listing"] == pytest.approx(last["coverage20"], abs=1.0)
    assert any("Chỉ giao dịch" in f for f in liq.liquidity_flags(last))


def test_liquidity_flags_trigger_and_bucket():
    row = pd.Series({
        "adv20": 1e6, "coverage20": 30.0, "coverage_listing": 30.0,
        "sessions_listed": 40, "zero20": 14, "amihud20": 9.0, "range20": 20.0,
        "dtl_50m": 250.0, "liq_trend": 0.2,
    })
    flags = liq.liquidity_flags(row)
    assert any("ADV20" in f for f in flags)
    assert any("Chỉ giao dịch" in f for f in flags)
    assert any("50 triệu VND" in f for f in flags)
    assert any("Amihud" in f or "Tác động giá" in f for f in flags)
    assert liq.liquidity_bucket(row) == "rất thấp"
    assert liq.liquidity_bucket(pd.Series({"adv20": 800e6, "coverage20": 100})) == "rất cao"


def test_liquidity_score_prefers_deep_market():
    d = pd.DataFrame({
        "adv20": [1e6, 20e6, 300e6, 2e9],
        "coverage_listing": [100, 100, 100, 100],
        "amihud20": [20.0, 8.0, 1.0, 0.2],
        "liq_trend": [0.9, 1.0, 1.1, 1.0],
        "impact_50m_pct": [8.0, 3.0, 0.8, 0.2],
        "value_med20": [1e6, 20e6, 300e6, 2e9],
        "underlying": list("ABCD"),
    })
    score, conf, detail = scoring.score_liquidity(d)
    assert score.is_monotonic_increasing
    assert conf.min() > 0.9
    assert "adv_pct" in detail


def test_classify_downgrades_on_liquidity_gates():
    # đủ điểm MUA MẠNH nhưng ADV/độ phủ/biên độ vi phạm
    rec, reason = scoring.classify(88.0, 85.0, 0.95, 120.0, 200e6,
                                   adv_value=5e6, coverage=90.0, range20=8.0)
    assert rec == "HOLD"
    assert "thanh khoản" in reason.lower() or "giao dịch" in reason.lower()
    rec2, _ = scoring.classify(88.0, 85.0, 0.95, 120.0, 200e6,
                              adv_value=300e6, coverage=40.0, range20=8.0)
    assert rec2 == "HOLD"
    rec3, _ = scoring.classify(88.0, 85.0, 0.95, 120.0, 200e6,
                              adv_value=300e6, coverage=95.0, range20=30.0)
    assert rec3 == "HOLD"
    rec4, _ = scoring.classify(88.0, 85.0, 0.95, 120.0, 200e6,
                              adv_value=300e6, coverage=95.0, range20=8.0)
    assert rec4 == "STRONG_BUY"


def test_rebase_to_asof_discounts_idle_sessions():
    cal = pd.bdate_range("2026-01-05", periods=40)
    rows = [{"ticker": "OLD1", "date": d, "close": 1000.0, "high": 1050.0, "low": 950.0,
             "volume": 1e5, "value": 1e8} for d in cal]
    panel = pd.DataFrame(rows)
    snap = pd.DataFrame([{
        "ticker": "OLD1", "date": cal[-1], "adv20": 1e8, "value": 1e8,
        "ret_std20": 0.05, "first_trade": cal[0], "coverage20": 100.0,
    }])
    live = liq.rebase_to_asof(snap, panel, cal[-1])
    assert live.iloc[0]["adv20"] == pytest.approx(1e8)
    assert live.iloc[0]["coverage20"] == pytest.approx(100.0)

    # CW ngừng giao dịch 10 phiên trước as-of: 10 phiên trắng phải được tính là 0
    # (giữ một ticker khác giao dịch đủ 40 phiên để lịch thị trường vẫn kết thúc tại as-of)
    market_cal = panel.assign(ticker="MKTCAL")
    stale_panel = pd.concat([panel.iloc[:-10], market_cal], ignore_index=True)
    stale = liq.rebase_to_asof(snap, stale_panel, cal[-1])
    row = stale.iloc[0]
    assert row["adv20"] == pytest.approx(5e7)
    assert row["coverage20"] == pytest.approx(50.0)
    assert row["zero20"] == pytest.approx(10.0)
    assert row["dtl_50m"] == pytest.approx(50e6 / (0.2 * 5e7))
