"""Kiểm thử đầu ra phát hành (docs/data) — bỏ qua nếu chưa build."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

DATA = Path(__file__).resolve().parents[1] / "docs" / "data"

pytestmark = pytest.mark.skipif(not DATA.exists(), reason="chưa build docs/data")


def _load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def test_required_files_exist():
    for name in ["meta", "market", "screener", "recommendations", "underlyings",
                 "quality", "methodology", "backtest"]:
        assert (DATA / f"{name}.json").exists(), name


def test_meta_contract():
    m = _load("meta.json")
    for key in ["asof", "asofLabel", "generatedAt", "version", "methodologyVersion",
                "universe", "riskFree", "dataSources", "seriesTickers"]:
        assert key in m, key
    assert 0 < m["riskFree"]["value"] < 0.2
    assert m["universe"]["active"] > 0
    assert m["dataAgeDays"] >= 0


def test_screener_rows_have_units_documented_fields():
    s = _load("screener.json")
    rows = s["active"]
    assert rows
    required = {"t", "u", "price", "S", "K", "ratio", "dte", "premium", "score", "rec", "dq"}
    for r in rows[:50]:
        assert required.issubset(r), required - set(r)
        assert r["price"] is None or r["price"] >= 0
        assert r["K"] is None or r["K"] > 0
        assert r["ratio"] is None or r["ratio"] > 0
        assert r["dte"] is None or r["dte"] >= -1


def test_recommendation_cards_explain_themselves():
    r = _load("recommendations.json")
    cards = r["cards"]
    assert cards
    for c in cards:
        assert c["rec_reason"], c["ticker"]
        assert c["thesis"], c["ticker"]
        assert 0 <= c["score"] <= 100
        assert set(c["components"]) >= {"underlying_momentum", "valuation", "liquidity",
                                        "risk_reward", "technical", "time_to_maturity"}
        plan = c["trading_plan"]
        assert "available" in plan
        if not plan["available"]:
            assert plan.get("reason")


def test_no_strong_buy_on_short_history_or_illiquid():
    r = _load("recommendations.json")
    s = {x["t"]: x for x in _load("screener.json")["active"]}
    for c in r["cards"]:
        if c["recommendation"] != "STRONG_BUY":
            continue
        row = s.get(c["ticker"], {})
        assert (row.get("sessions") or 0) >= 15, c["ticker"]
        assert (row.get("dq") or 0) >= 0.6, c["ticker"]
        assert (row.get("dte") or 0) >= 30, c["ticker"]


def test_market_kpi_consistency():
    m = _load("market.json")
    k = m["kpi"]
    assert k["itm"] + k["atm"] + k["otm"] <= k["total"]
    assert abs(k["up"] + k["down"] + k["flat"] - k["active"]) <= 5
    assert 0 <= k["avgScore"] <= 100
    assert len(m["breadth"]) > 20


def test_quality_summary_keys():
    q = _load("quality.json")
    summary = q["summary"]
    assert {"ok", "warn", "error", "total"} <= set(summary)
    assert summary["total"] == len(q["checks"])
    statuses = {c["status"] for c in q["checks"]}
    assert statuses <= {"ok", "warn", "error"}
    assert summary["error"] == 0


def test_methodology_weights_sum_to_one():
    m = _load("methodology.json")
    weights = m["scoring"]["weights"]
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)
    assert {"conventions", "scoring", "recommendation", "backtest", "limitations", "sources"} <= set(m)


def test_backtest_reports_losses_honestly():
    b = _load("backtest.json")
    assert b["n_trades_total"] > 0
    assert len(b["caveats"]) >= 3
    assert "score_top" in b["summary"]
    assert b["summary"]["score_top"]["total_return_pct"] is not None
    # không được che giấu kết quả âm
    assert any(v["total_return_pct"] < 0 for v in b["summary"].values())
    for t in b["trades"][:20]:
        assert t["entry_date"] > t["signal_date"]


def test_series_files_match_manifest():
    meta = _load("meta.json")
    tickers = meta["seriesTickers"]
    files = {p.stem for p in (DATA / "series" / "cw").glob("*.json")}
    assert files == set(tickers)
    # chỉ giữ CW đang giao dịch hoặc giao dịch trong 365 ngày → không vượt vũ trụ
    assert len(files) <= meta["universe"]["total"]


def test_series_payload_shape():
    meta = _load("meta.json")
    ticker = meta["seriesTickers"][0]
    with open(DATA / "series" / "cw" / f"{ticker}.json", encoding="utf-8") as f:
        s = json.load(f)
    assert {"dates", "o", "h", "l", "c", "v"} <= set(s)
    assert len(s["dates"]) == len(s["c"]) == len(s["v"])
    for i in range(1, len(s["c"])):
        assert s["h"][i] is None or s["c"][i] is None or s["h"][i] >= s["l"][i]


def test_underlyings_payload():
    u = _load("underlyings.json")
    assert u["items"]
    for it in u["items"]:
        assert it["u"]
        assert it["nCw"] >= 0
        assert it["hv252"] is None or 0 < it["hv252"] < 3


# ──────────────────────────────────────────────────────────────────
# VÒNG ĐỜI CW — chặn tái phát lỗi "đếm trùng mã đã đáo hạn"
# ──────────────────────────────────────────────────────────────────
def test_universe_identity_matches_states():
    """Tổng vũ trụ = còn hiệu lực + chờ niêm yết + đã đáo hạn + ngừng GD (+ thiếu ngày)."""
    u = _load("meta.json")["universe"]
    parts = u["listed"] + u["pending"] + u["matured"] + u["delistedEarly"] + u["unknown"]
    assert parts == u["total"]
    assert u["traded"] + u["notTraded"] == u["listed"]
    assert u["expired"] == u["matured"] + u["delistedEarly"]
    assert u["total"] == len(_load("screener.json")["active"]) + len(_load("screener.json")["expired"])


def test_screener_sets_are_disjoint():
    """Không một CW nào vừa "còn hiệu lực" vừa "đã đáo hạn" (lỗi cũ: 13 mã nằm cả hai)."""
    s = _load("screener.json")
    active = {r["t"] for r in s["active"]}
    expired = {r["t"] for r in s["expired"]}
    assert not (active & expired)


def test_snapshot_has_no_matured_warrants():
    asof = pd.Timestamp(_load("meta.json")["asof"])
    for r in _load("screener.json")["active"]:
        assert r.get("state") == "listed", r["t"]
        assert pd.Timestamp(r["mat"]) > asof, r["t"]
        assert r["dte"] is None or r["dte"] >= 0, r["t"]


def test_expired_rows_are_really_expired():
    asof = pd.Timestamp(_load("meta.json")["asof"])
    rows = _load("screener.json")["expired"]
    assert rows
    for r in rows:
        st = r.get("state")
        assert st in {"matured", "delisted_early", "pending", "unknown"}, r["t"]
        if st == "matured":
            assert pd.Timestamp(r["mat"]) <= asof, r["t"]
            assert r["dte"] is None or r["dte"] <= 0, r["t"]


def test_recommendations_only_for_live_warrants():
    live = {r["t"] for r in _load("screener.json")["active"]}
    for c in _load("recommendations.json")["cards"]:
        assert c["ticker"] in live, c["ticker"]


def test_lifecycle_payload_is_published_and_consistent():
    lc = _load("lifecycle.json")
    assert lc["asof"] == _load("meta.json")["asof"]
    assert lc["identity"]["ok"] is True
    u = _load("meta.json")["universe"]
    for key in ("total", "listed", "traded", "matured", "delistedEarly", "pending", "unknown"):
        assert lc["counts"][key] == u[key], key
    assert lc["recentSessions"] >= 1
    assert lc["recentSince"] <= lc["asof"]
    # sự kiện phải khớp với danh sách mã kèm theo
    assert lc["newListings"]["count"] == len(lc["newListings"]["rows"]) or lc["newListings"]["count"] > len(lc["newListings"]["rows"])
    assert lc["recentMaturities"]["count"] == len(lc["recentMaturities"]["rows"]) or lc["recentMaturities"]["count"] > len(lc["recentMaturities"]["rows"])
    for r in lc["newListings"]["rows"]:
        assert r["firstTrade"] >= lc["recentSince"]
    for r in lc["recentMaturities"]["rows"]:
        assert lc["recentSince"] < r["maturity"] <= lc["asof"]


def test_lifecycle_calendar_covers_current_month():
    lc = _load("lifecycle.json")
    cal = lc["calendar"]
    assert cal
    cur = [c for c in cal if c["isCurrent"]]
    assert len(cur) == 1
    assert cur[0]["month"] == lc["asof"][:7]
    # còn hiệu lực, đáo hạn trong tháng hiện tại = số mã listed có maturity tháng này
    assert cur[0]["listedNow"] >= 0
    assert all({"month", "label", "listings", "maturities", "listedNow"} <= set(c) for c in cal)
