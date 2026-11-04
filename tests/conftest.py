"""Cấu hình pytest cho CW Intelligence."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cwintel import config  # noqa: E402


@pytest.fixture(scope="session")
def r() -> float:
    return 0.0444


@pytest.fixture()
def synthetic_panel() -> pd.DataFrame:
    """Panel tổng hợp 3 ticker × 60 phiên, đủ cột cho History/backtest."""
    dates = pd.bdate_range("2024-01-02", periods=60)
    rows = []
    for i, (ticker, und, iss) in enumerate(
        [("CAAA2401", "AAA", "ssi"), ("CAAA2402", "AAA", "vndirect"), ("CBBB2401", "BBB", "ssi")]
    ):
        base = 1000.0 + i * 100
        for j, d in enumerate(dates):
            px = base * (1 + 0.002 * j) * (1 + (0.01 if (i + j) % 3 == 0 else -0.005))
            rows.append(
                {
                    "ticker": ticker,
                    "underlying": und,
                    "issuer": iss,
                    "date": d,
                    "close": px,
                    "open": px,
                    "high": px * 1.02,
                    "low": px * 0.98,
                    "volume": 100_000.0,
                    "value": px * 100_000.0,
                    "value_med20": px * 100_000.0,
                    "days_to_maturity": 120 - j,
                    "T": (120 - j) / 365.0,
                    "K": base * 0.95,
                    "ratio": 2.0,
                    "score": 50.0 + j * 0.5,
                    "s_liquidity": 70.0,
                    "data_quality": 0.95,
                    "iv_vs_hv": 5.0,
                    "sessions": j + 1,
                    "sigma": 0.3,
                    "premium_be": 20.0,
                    "eff_gearing": 5.0,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture()
def universe_frame() -> pd.DataFrame:
    """Mặt cắt 6 CW với đủ cột cho score_universe (giá trị tổng hợp)."""
    n = 6
    und = ["AAA", "AAA", "BBB", "BBB", "CCC", "CCC"]
    return pd.DataFrame(
        {
            "ticker": [f"C{i}" for i in range(n)],
            "underlying": und,
            "issuer": ["ssi", "vndirect"] * 3,
            "close": [500, 800, 1200, 300, 950, 150],
            "K": [25000, 26000, 30000, 31000, 18000, 19000],
            "ratio": [2.0] * n,
            "T": [0.3] * n,
            "days_to_maturity": [110, 80, 200, 40, 120, 300],
            "u_close": [26000] * n,
            "u_ret21": [0.06, 0.06, -0.04, -0.04, 0.01, 0.01],
            "u_ret63": [0.12, 0.12, -0.02, -0.02, 0.03, 0.03],
            "u_rsi14": [62, 62, 38, 38, 55, 55],
            "u_above_ma20": [1, 1, 0, 0, 1, 1],
            "u_above_ma50": [1, 1, 0, 0, 1, 1],
            "u_dist_high60": [-1.0, -1.0, -12.0, -12.0, -4.0, -4.0],
            "premium_be": [12.0, 28.0, 35.0, 18.0, 22.0, 60.0],
            "iv_resid": [-8.0, 12.0, 4.0, -3.0, 0.0, 45.0],
            "iv_vs_hv": [-5.0, 20.0, 30.0, 2.0, 10.0, 80.0],
            "fv_smile_upside": [10.0, -5.0, -20.0, 8.0, 2.0, -40.0],
            "iv_rank": [30, 70, 80, 25, 50, 95],
            "delta": [0.45, 0.35, 0.28, 0.55, 0.40, 0.10],
            "gamma": [1e-5] * n,
            "theta": [-0.8, -1.2, -1.5, -0.6, -1.0, -0.4],
            "theta_pct": [-0.2, -0.35, -0.5, -0.15, -0.3, -1.8],
            "vega": [10.0] * n,
            "eff_gearing": [6.0, 4.0, 3.0, 9.0, 5.0, 25.0],
            "be_distance_pct": [12.0, 28.0, 35.0, 18.0, 22.0, 60.0],
            "value_med20": [5e7, 2e7, 1e7, 8e6, 3e7, 5e5],
            "volume_accel": [1.5, 1.0, 0.8, 2.2, 1.1, 0.4],
            "traded_ratio20": [1.0, 0.9, 0.7, 0.8, 0.95, 0.1],
            "rsi14": [55, 66, 72, 45, 60, 30],
            "macd_hist": [2.0, -1.0, -3.0, 1.5, 0.5, -8.0],
            "macd_hist_slope": [0.5, -0.2, -0.4, 0.3, 0.1, -1.0],
            "above_ma20": [1, 1, 0, 1, 1, 0],
            "above_ma50": [1, 0, 0, 1, 1, 0],
            "breakout20": [0, 0, 0, 1, 0, 0],
            "sessions": [120, 90, 150, 60, 100, 8],
            "terms_valid": [1] * n,
            "sigma_source": ["hv252"] * n,
            "staleness_days": [0] * n,
            "u_sessions": [250] * n,
            "iv": [0.30, 0.42, 0.55, 0.28, 0.35, 0.90],
            "moneyness": ["ATM"] * n,
            "moneyness_pct": [0.0] * n,
            "issuer_name": ["SSI"] * n,
            "issuer_value_share": [0.1] * n,
        }
    )
