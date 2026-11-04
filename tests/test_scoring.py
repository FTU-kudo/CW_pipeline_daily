"""Kiểm thử scoring, phân loại và các cổng chất lượng."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cwintel import config
from cwintel.scoring import classify, classify_frame, score_universe


def _frame(**overrides) -> pd.DataFrame:
    base = {
        "score": [85.0], "s_liquidity": [90.0], "data_quality": [0.95],
        "days_to_maturity": [120.0], "value_med20": [5e7], "iv_vs_hv": [0.0],
        "sessions": [120.0],
    }
    for k, v in overrides.items():
        base[k] = list(v) if isinstance(v, (list, tuple)) else [v]
    n = max(len(v) for v in base.values())
    for k, v in base.items():
        if len(v) == 1 and n > 1:
            base[k] = v * n
        elif len(v) != n:
            raise ValueError(f"cột {k} có {len(v)} giá trị, cần {n}")
    return pd.DataFrame(base)


def test_classify_thresholds_are_ascending():
    """Ngưỡng phải được áp tăng dần — lỗi cũ khiến mọi mã thành HIGH_RISK."""
    cases = [(95, "STRONG_BUY"), (85, "STRONG_BUY"), (72, "BUY"), (65, "BUY"),
             (60, "HOLD"), (45, "HOLD"), (40, "AVOID"), (30, "AVOID"), (10, "HIGH_RISK")]
    for score, expected in cases:
        rec, _ = classify(score, liq=90, dq=0.95, dte=120, med_value=5e7)
        assert rec == expected, (score, rec)


def test_classify_frame_matches_scalar():
    d = _frame(score=[95.0, 72.0, 60.0, 40.0, 10.0])
    d["s_liquidity"] = 90.0
    d["data_quality"] = 0.95
    d["days_to_maturity"] = 120.0
    d["value_med20"] = 5e7
    d["iv_vs_hv"] = 0.0
    d["sessions"] = 120.0
    rec, reason = classify_frame(d)
    assert list(rec) == ["STRONG_BUY", "BUY", "HOLD", "AVOID", "HIGH_RISK"]
    assert all(isinstance(x, str) and x for x in reason)


def test_no_data_when_quality_low():
    d = _frame(score=[99.0], data_quality=[0.10])
    rec, reason = classify_frame(d)
    assert rec.iloc[0] == "NO_DATA"
    assert "Chất lượng dữ liệu" in reason.iloc[0]


def test_strong_buy_downgraded_on_illiquidity():
    d = _frame(score=[88.0], s_liquidity=[10.0])
    rec, reason = classify_frame(d)
    # thanh khoản 10 điểm trượt cả cổng MUA → HOLD, nhưng lý do phải nêu rõ đã hạ từ MUA MẠNH
    assert rec.iloc[0] == "HOLD"
    assert "thanh khoản" in reason.iloc[0].lower()
    assert reason.iloc[0].startswith("Hạ từ MUA MẠNH")


def test_strong_buy_downgraded_on_short_history():
    d = _frame(score=[88.0], sessions=[5.0])
    rec, reason = classify_frame(d)
    assert rec.iloc[0] == "HOLD"
    assert "lịch sử" in reason.iloc[0]


def test_strong_buy_downgraded_on_high_iv():
    d = _frame(score=[88.0], iv_vs_hv=[80.0])
    rec, reason = classify_frame(d)
    assert rec.iloc[0] == "HOLD"
    assert "IV" in reason.iloc[0]


def test_strong_buy_downgraded_on_near_maturity():
    d = _frame(score=[88.0], days_to_maturity=[10.0])
    rec, reason = classify_frame(d)
    assert rec.iloc[0] == "HOLD"
    assert "đáo hạn" in reason.iloc[0]


def test_reason_not_duplicated_when_both_gates_fail():
    d = _frame(score=[88.0], sessions=[3.0], s_liquidity=[5.0])
    _, reason = classify_frame(d)
    text = reason.iloc[0]
    assert text.count("lịch sử giao dịch quá ngắn") == 1


def test_score_universe_range_and_columns(universe_frame):
    out = score_universe(universe_frame)
    assert len(out) == len(universe_frame)
    assert out["score"].between(0, 100).all()
    for k in config.SCORE_WEIGHTS:
        assert f"s_{k}" in out.columns
        assert out[f"s_{k}"].between(0, 100).all()
        assert out[f"c_{k}"].between(0, 1).all()
    assert out["recommendation"].isin(
        ["STRONG_BUY", "BUY", "HOLD", "AVOID", "HIGH_RISK", "NO_DATA"]).all()
    assert (out["rec_reason"].astype(str).str.len() > 0).all()


def test_score_prefers_cheap_liquid_cw(universe_frame):
    """CW rẻ hơn (IV thấp, premium thấp) và thanh khoản tốt phải điểm cao hơn CW đắt, khô."""
    out = score_universe(universe_frame).set_index("ticker")
    assert out.loc["C0", "score"] > out.loc["C5", "score"]


def test_weights_normalised():
    assert sum(config.SCORE_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)


def test_peer_premium_median_computed(universe_frame):
    out = score_universe(universe_frame)
    aaa = out[out["underlying"] == "AAA"]["peer_premium_median"]
    assert aaa.nunique() == 1
    assert aaa.iloc[0] == pytest.approx(np.median([12.0, 28.0]))


def test_momentum_percentile_uses_unique_underlyings(universe_frame):
    """Underlying lặp lại nhiều CW không được làm méo percentile."""
    out = score_universe(universe_frame).set_index("ticker")
    # AAA mạnh nhất (ret21 +6%) phải có percentile cao hơn CCC (+1%)
    assert out.loc["C0", "x_underlying_momentum_ret21_pct"] > out.loc["C4", "x_underlying_momentum_ret21_pct"]


def test_missing_columns_do_not_crash():
    """Universe tối thiểu vẫn phải chấm điểm được (dữ liệu thiếu → điểm thấp/NaN)."""
    d = pd.DataFrame({"ticker": ["X"], "underlying": ["X"], "close": [100.0]})
    out = score_universe(d)
    assert "score" in out.columns
    assert len(out) == 1
