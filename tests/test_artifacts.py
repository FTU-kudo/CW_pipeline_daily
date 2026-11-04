"""Kiểm thử đầu ra phát hành (docs/data) — bỏ qua nếu chưa build."""

from __future__ import annotations

import json
from pathlib import Path

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
