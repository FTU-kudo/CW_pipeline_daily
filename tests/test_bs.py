"""Kiểm thử Black–Scholes, Greeks và IV (đơn vị: VND/CW)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from cwintel.bs import (
    greeks_vector,
    implied_vol,
    implied_vol_vector,
    intrinsic_value,
    norm_cdf,
    norm_pdf,
    price_and_greeks,
    price_vector,
)

S, K, T, R, SIG, RATIO = 26_000.0, 25_000.0, 0.35, 0.0444, 0.28, 2.0


def test_norm_cdf_known_values():
    assert norm_cdf(0.0) == pytest.approx(0.5, abs=1e-12)
    assert norm_cdf(1.959964) == pytest.approx(0.975, abs=1e-6)
    assert norm_cdf(-1.959964) == pytest.approx(0.025, abs=1e-6)
    # đối xứng
    for x in (0.3, 1.0, 2.5, 4.0):
        assert norm_cdf(x) + norm_cdf(-x) == pytest.approx(1.0, abs=1e-10)


def test_norm_pdf_peak():
    assert norm_pdf(0.0) == pytest.approx(1 / math.sqrt(2 * math.pi), rel=1e-12)
    assert norm_pdf(1.0) == pytest.approx(norm_pdf(-1.0), rel=1e-12)


def test_put_call_parity_ratio_one():
    """C − P = S − K·e^(−rT) khi tỷ lệ = 1 (không cổ tức)."""
    c = price_and_greeks(S, K, T, R, SIG, ratio=1.0, kind="call")
    p = price_and_greeks(S, K, T, R, SIG, ratio=1.0, kind="put")
    lhs = c.price - p.price
    rhs = S - K * math.exp(-R * T)
    assert lhs == pytest.approx(rhs, abs=1e-8)


def test_price_scales_inverse_with_ratio():
    """Giá 1 CW = giá quyền / n."""
    c1 = price_and_greeks(S, K, T, R, SIG, ratio=1.0).price
    c4 = price_and_greeks(S, K, T, R, SIG, ratio=4.0).price
    assert c4 == pytest.approx(c1 / 4.0, rel=1e-12)


def test_intrinsic_and_expiry():
    """T = 0 → giá = giá trị nội tại, không có giá trị thời gian."""
    res = price_and_greeks(S, K, 0.0, R, SIG, ratio=RATIO)
    assert res.status == "expired"
    assert res.price == pytest.approx(max(S - K, 0) / RATIO)
    assert res.time_value == 0.0
    # OTM khi đáo hạn → 0
    res_otm = price_and_greeks(20_000, K, 0.0, R, SIG, ratio=RATIO)
    assert res_otm.price == 0.0
    assert intrinsic_value(20_000, K, RATIO) == 0.0


def test_invalid_inputs_return_zero():
    assert price_and_greeks(0, K, T, R, SIG).price == 0.0
    assert price_and_greeks(S, 0, T, R, SIG).price == 0.0
    assert price_and_greeks(S, K, T, R, 0.0).price == intrinsic_value(S, K, 1.0)
    assert price_and_greeks(S, K, T, R, SIG, ratio=0).status == "invalid_input"


def test_greeks_units_and_signs():
    res = price_and_greeks(S, K, T, R, SIG, ratio=RATIO)
    # delta/CW = N(d1)/n → trong (0, 1/n)
    assert 0 < res.delta < 1 / RATIO
    assert res.delta == pytest.approx(norm_cdf(res.d1) / RATIO, rel=1e-12)
    assert res.gamma > 0
    assert res.vega > 0
    assert res.theta < 0          # mua quyền mất giá theo thời gian
    assert res.rho > 0            # call hưởng lợi khi lãi suất tăng
    assert res.time_value >= 0
    assert res.price == pytest.approx(res.intrinsic + res.time_value, abs=1e-9)


def test_delta_finite_difference():
    """Δ ≈ (C(S+h) − C(S−h)) / 2h, sai số nhỏ."""
    h = 1.0
    up = price_and_greeks(S + h, K, T, R, SIG, ratio=RATIO).price
    dn = price_and_greeks(S - h, K, T, R, SIG, ratio=RATIO).price
    fd = (up - dn) / (2 * h) / (1 / RATIO)   # chuyển về delta tuỳ chọn
    base = price_and_greeks(S, K, T, R, SIG, ratio=RATIO).delta * RATIO
    assert fd == pytest.approx(base, abs=5e-3)


def test_vega_theta_finite_difference():
    eps = 1e-4
    p_up = price_and_greeks(S, K, T, R, SIG + eps, ratio=RATIO).price
    p_dn = price_and_greeks(S, K, T, R, SIG - eps, ratio=RATIO).price
    vega_fd = (p_up - p_dn) / (2 * eps * 100)      # mỗi 1 điểm vol
    assert vega_fd == pytest.approx(price_and_greeks(S, K, T, R, SIG, ratio=RATIO).vega, rel=0.02)

    dt = 1 / 365
    p_t = price_and_greeks(S, K, T - dt, R, SIG, ratio=RATIO).price
    theta_fd = (p_t - price_and_greeks(S, K, T, R, SIG, ratio=RATIO).price) / 1.0
    assert theta_fd == pytest.approx(price_and_greeks(S, K, T, R, SIG, ratio=RATIO).theta, rel=0.05)


def test_implied_vol_roundtrip():
    for ratio in (1.0, 2.0, 4.0):
        for moneyness in (0.7, 0.9, 1.0, 1.1, 1.4):
            s = 25_000 * moneyness
            price = price_and_greeks(s, K, 0.5, R, 0.33, ratio=ratio).price
            iv, status = implied_vol(price, s, K, 0.5, R, ratio=ratio)
            assert status == "ok", (ratio, moneyness, status)
            assert iv == pytest.approx(0.33, abs=1e-5), (ratio, moneyness, iv)


def test_implied_vol_rejects_arbitrage_price():
    """Giá thấp hơn giá trị nội tại → không có IV hợp lệ (trả NaN/None)."""
    iv, status = implied_vol(1.0, 30_000, 20_000, 0.5, R, ratio=2.0)
    assert iv is None
    assert status in {"below_intrinsic", "no_arbitrage_range", "bad_input"}


def test_vector_matches_scalar():
    S_v = np.array([24_000.0, 26_000.0, 28_000.0])
    px = price_vector(S_v, K, T, R, SIG, RATIO)
    for s, p in zip(S_v, px):
        assert p == pytest.approx(price_and_greeks(s, K, T, R, SIG, RATIO).price, rel=1e-12)
    g = greeks_vector(S_v, K, T, R, SIG, RATIO)
    assert np.allclose(g["delta"], [price_and_greeks(s, K, T, R, SIG, RATIO).delta for s in S_v], rtol=1e-10)


def test_implied_vol_vector_roundtrip():
    S_v = np.array([24_000.0, 26_000.0, 28_000.0])
    px = price_vector(S_v, K, T, R, 0.30, RATIO)
    iv, valid = implied_vol_vector(px, S_v, K, T, R, RATIO)
    assert valid.all()
    assert np.allclose(iv, 0.30, atol=1e-3)


def test_no_arbitrage_bounds():
    """Giá call nằm giữa max(S−K,0)/n và S/n."""
    for s in (15_000, 25_000, 40_000):
        res = price_and_greeks(s, K, T, R, SIG, ratio=RATIO)
        assert max(s - K, 0) / RATIO - 1e-9 <= res.price <= s / RATIO + 1e-9
