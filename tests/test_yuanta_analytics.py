"""Kiểm thử phân tích bảng (xếp hạng thanh khoản, nhóm cơ sở, giám sát mã chết) — offline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from cwintel import yuanta_history as h
from cwintel.yuanta_analytics import (
    LIQUIDITY_TIERS,
    assign_tier,
    build_analytics,
    liquidity_ranking,
    session_comparison,
    stale_monitor,
    tier_thresholds,
    underlying_breakdown,
)
from cwintel.yuanta_board import clean_board

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "yuanta_ew_sample.json"
FETCHED = datetime(2026, 11, 13, 10, 30, tzinfo=timezone.utc)


def _rows() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["response"]


@pytest.fixture()
def board() -> pd.DataFrame:
    return clean_board(_rows(), fetched_at=FETCHED)


@pytest.fixture()
def history() -> pd.DataFrame:
    return h.bars_from_rows(_rows(), h.resolve_session(FETCHED.isoformat()))


# ──────────────────────────────────────────────────────────────────
# XẾP HẠNG THANH KHOẢN
# ──────────────────────────────────────────────────────────────────
def test_thresholds_come_from_the_snapshot_itself(board):
    thresholds = tier_thresholds(board)
    assert [t["quantile"] for t in thresholds] == ["p80", "p60", "p30", "p10"]
    values = board.loc[board["Traded"], "TradingValueVND"]
    assert thresholds[0]["valueVND"] == pytest.approx(values.quantile(0.8), rel=1e-6)
    # Giảm dần → nhãn tiers đi từ cao xuống thấp
    assert [t["valueVND"] for t in thresholds] == sorted(
        [t["valueVND"] for t in thresholds], reverse=True)


def test_untraded_warrant_is_never_ranked(board):
    ranking = liquidity_ranking(board)
    ranked = {row["t"] for row in ranking["ranking"]}
    assert "CVNM2526" not in ranked            # không khớp lệnh
    assert ranking["ranking"][0]["t"] == "CHPG2512"   # GT lớn nhất
    assert ranking["ranking"][0]["rank"] == 1
    values = [row["valueVND"] for row in ranking["ranking"]]
    assert values == sorted(values, reverse=True)


def test_tier_distribution_covers_every_row(board):
    ranking = liquidity_ranking(board)
    total = sum(t["count"] for t in ranking["tiers"])
    assert total == len(board)
    labels = {t["tier"] for t in ranking["tiers"]}
    assert labels == set(LIQUIDITY_TIERS) | {"không giao dịch"}
    untraded = [t for t in ranking["tiers"] if t["tier"] == "không giao dịch"][0]
    assert untraded["count"] == 1


def test_assign_tier_handles_missing_values():
    thresholds = [{"quantile": "p80", "valueVND": 100.0}, {"quantile": "p60", "valueVND": 50.0},
                  {"quantile": "p30", "valueVND": 10.0}, {"quantile": "p10", "valueVND": 1.0}]
    # 4 ngưỡng = 4 nhóm phía trên "rất thấp"; dưới p10 rơi vào nhóm cuối.
    series = pd.Series([500.0, 70.0, 20.0, 5.0, 0.5, None])
    assert list(assign_tier(series, thresholds)) == [
        "rất cao", "cao", "trung bình", "thấp", "rất thấp", "không giao dịch"]
    assert list(assign_tier(series, [])) == ["không xác định"] * 6
    # Ngưỡng NaN (mã thiếu dữ liệu) không được làm hỏng việc phân nhóm
    partial = [{"quantile": "p80", "valueVND": None}, {"quantile": "p60", "valueVND": 50.0},
               {"quantile": "p30", "valueVND": 10.0}, {"quantile": "p10", "valueVND": 1.0}]
    assert list(assign_tier(pd.Series([80.0, 5.0]), partial)) == ["cao", "thấp"]


def test_concentration_is_bounded(board):
    conc = liquidity_ranking(board)["concentration"]
    assert 0 < conc["top10ValueSharePct"] <= 100
    assert 0 < conc["hhi"] <= 1
    assert conc["top1ValueSharePct"] <= conc["top10ValueSharePct"]


# ──────────────────────────────────────────────────────────────────
# NHÓM CỔ PHIẾU CƠ SỞ
# ──────────────────────────────────────────────────────────────────
def test_underlying_breakdown_sums_to_the_board(board):
    rows = underlying_breakdown(board)
    assert {r["underlying"] for r in rows} == set(board["Underlying"].dropna())
    assert sum(r["valueSharePct"] for r in rows) == pytest.approx(100, abs=0.1)
    assert sum(r["warrants"] for r in rows) == len(board)
    hpg = [r for r in rows if r["underlying"] == "HPG"][0]
    assert hpg["warrants"] == 2 and hpg["traded"] == 2
    # sắp xếp theo giá trị giảm dần
    values = [r["valueVND"] for r in rows]
    assert values == sorted(values, reverse=True)


def test_underlying_breakdown_skips_rows_without_underlying(board):
    frame = board.copy()
    frame.loc[frame.index[:2], "Underlying"] = None
    rows = underlying_breakdown(frame)
    assert sum(r["warrants"] for r in rows) == len(board) - 2


# ──────────────────────────────────────────────────────────────────
# MÃ KHÔNG GIAO DỊCH
# ──────────────────────────────────────────────────────────────────
def test_stale_monitor_flags_wide_spread_without_history(board):
    monitor = stale_monitor(board)
    assert monitor["count"] == 1
    assert monitor["historyAvailable"] is False
    assert monitor["rows"][0]["t"] == "CVNM2526"
    assert monitor["rows"][0]["sessionsIdle"] is None
    assert "RefP" in monitor["note"]


def test_stale_monitor_uses_history_for_idle_sessions(board, history):
    monitor = stale_monitor(board, history)
    assert monitor["historyAvailable"] is True
    row = monitor["rows"][0]
    assert row["t"] == "CVNM2526"
    # Chưa từng khớp lệnh → chưa xác định (None), KHÔNG phải 0 phiên
    assert row["sessionsIdle"] is None


def test_stale_monitor_reports_idle_sessions_for_untraded_warrant(board, history):
    """Mã không giao dịch hôm nay và có lịch sử: số phiên im lặng phải đếm được."""
    from cwintel.yuanta_analytics import STALE_SESSIONS_WARN

    days = [f"2026-11-{d:02d}" for d in (2, 3, 4, 5, 6, 9, 10, 11, 12, 13)]
    frames = []
    for day in days:
        bars = history.copy()
        bars["session"] = day
        frames.append(bars)
    combined = pd.concat(frames, ignore_index=True)
    # CVNM2526 giao dịch các phiên đầu, rồi im lặng đúng ngưỡng phiên cuối
    silent = days[-STALE_SESSIONS_WARN:]
    combined.loc[combined["ticker"] == "CVNM2526", "traded"] = True
    combined.loc[(combined["ticker"] == "CVNM2526") & (combined["session"].isin(silent)),
                 "traded"] = False
    monitor = stale_monitor(board, combined, asof="2026-11-13")
    row = {r["t"]: r for r in monitor["rows"]}["CVNM2526"]
    assert row["sessionsIdle"] == len(silent)
    assert any("phiên không khớp" in flag for flag in row["flags"])


def test_stale_monitor_surfaces_recovered_warrants(board, history):
    """Mã đã giao dịch lại nhưng từng im lặng ≥ ngưỡng được báo riêng, không bị bỏ sót."""
    from cwintel.yuanta_analytics import STALE_SESSIONS_WARN

    days = [f"2026-11-{d:02d}" for d in (2, 3, 4, 5, 6, 9, 10, 11, 12, 13)]
    assert len(days) > STALE_SESSIONS_WARN
    frames = []
    for day in days:
        bars = history.copy()
        bars["session"] = day
        frames.append(bars)
    combined = pd.concat(frames, ignore_index=True)
    # CHPG2512 im lặng đúng STALE_SESSIONS_WARN phiên rồi giao dịch lại phiên cuối
    silent = days[:STALE_SESSIONS_WARN]
    combined.loc[combined["ticker"] == "CHPG2512", ["traded", "close"]] = [False, None]
    combined.loc[(combined["ticker"] == "CHPG2512") & (combined["session"] == days[-1]),
                 ["traded", "close"]] = [True, 420.0]
    monitor = stale_monitor(board, combined, asof="2026-11-13")
    assert "CHPG2512" not in {r["t"] for r in monitor["rows"]}      # hôm nay có giao dịch
    recovered = {r["t"]: r for r in monitor["recovered"]}
    # Im lặng mọi phiên trừ phiên cuối → chuỗi gap dài nhất = len(days) - 1
    assert recovered["CHPG2512"]["longestGapSessions"] == len(days) - 1
    assert recovered["CHPG2512"]["coveragePct"] == pytest.approx(10.0)
    assert monitor["recoveredCount"] >= 1


def test_ticker_stats_and_coverage(board, history):
    from cwintel.yuanta_history import ticker_stats

    stats = ticker_stats(history)
    assert stats["CACB2515"]["tradedSessions"] == 1
    assert stats["CACB2515"]["coveragePct"] == 100.0
    assert stats["CVNM2526"]["tradedSessions"] == 0
    assert stats["CVNM2526"]["idleNow"] is None          # chưa từng khớp lệnh
    assert stats["CVNM2526"]["coveragePct"] == 0.0
    payload = build_analytics(board, history=history, asof="2026-11-13")
    cover = {r["t"]: r for r in payload["tickerCoverage"]}
    assert cover["CVNM2526"]["coveragePct"] == 0.0


# ──────────────────────────────────────────────────────────────────
# SO SÁNH PHIÊN
# ──────────────────────────────────────────────────────────────────
def test_session_comparison_unavailable_with_one_session(history):
    result = session_comparison(history)
    assert result["available"] is False
    assert "2 phiên" in result["reason"] or "≥ 2" in result["reason"]
    assert result["sessions"] == ["2026-11-13"]


def test_session_comparison_reports_delta_between_sessions(history):
    older = history.copy()
    older["session"] = "2026-11-12"
    older["value"] = older["value"] * 0.5
    combined = pd.concat([older, history], ignore_index=True)
    result = session_comparison(combined)
    assert result["available"] is True
    assert result["delta"]["valuePct"] == pytest.approx(100.0, abs=0.01)
    assert [s["session"] for s in result["sessions"]] == ["2026-11-12", "2026-11-13"]


# ──────────────────────────────────────────────────────────────────
# GÓI TỔNG HỢP
# ──────────────────────────────────────────────────────────────────
def test_build_analytics_is_json_safe_and_honest(board, history):
    payload = build_analytics(board, history=history, asof="2026-11-13")
    text = json.dumps(payload, allow_nan=False, ensure_ascii=False)
    assert "NaN" not in text
    assert payload["kind"] == "yuanta-cw-analytics"
    assert payload["historyCoverage"]["sessions"] == 1
    assert payload["stale"]["count"] == 1
    assert payload["sessions"]["available"] is False
    caveats = " ".join(payload["caveats"])
    assert "RefP" in caveats and "phân vị" in caveats
    for forbidden in ("recommendations", "scores", "iv", "greeks", "valuation"):
        assert forbidden not in payload


def test_build_analytics_rejects_empty_frame():
    with pytest.raises(ValueError):
        build_analytics(pd.DataFrame(), history=None)
