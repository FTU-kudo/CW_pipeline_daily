"""Kiểm thử CLI ghi lịch sử và báo cáo nối dashboard cũ — offline."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts import backfill_yuanta_history as backfill
from scripts import check_cw_analytics_bridge as bridge

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "yuanta_ew_sample.json"


def _write_snapshot(path: Path, fetched_at: str, rows: list[dict] | None = None) -> Path:
    payload = {
        "schemaVersion": 1,
        "fetchedAt": fetched_at,
        "count": len(rows or []),
        "rows": rows if rows is not None else
        json.loads(FIXTURE.read_text(encoding="utf-8"))["response"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_backfill_writes_store_and_payloads(tmp_path):
    snapshot = _write_snapshot(tmp_path / "snap.json", "2026-11-13T10:30:00+00:00")
    store = tmp_path / "store"
    sessions_out = tmp_path / "sessions.json"
    analytics_out = tmp_path / "analytics.json"
    code = backfill.main([
        "--offline", "--snapshot", str(snapshot), "--store", str(store),
        "--sessions-out", str(sessions_out), "--analytics-out", str(analytics_out),
    ])
    assert code == 0
    assert (store / "2026-11.csv").exists()

    sessions = json.loads(sessions_out.read_text(encoding="utf-8"))
    assert sessions["kind"] == "yuanta-cw-history"
    assert sessions["coverage"]["sessions"] == 1
    assert set(sessions["tickers"]) == {r["StockCode"]
                                        for r in json.loads(snapshot.read_text())["rows"]}
    analytics = json.loads(analytics_out.read_text(encoding="utf-8"))
    assert analytics["kind"] == "yuanta-cw-analytics"


def test_backfill_is_idempotent_and_upgrades_provisional(tmp_path):
    store = tmp_path / "store"
    snapshot = tmp_path / "snap.json"
    args = ["--offline", "--snapshot", str(snapshot), "--store", str(store),
            "--sessions-out", str(tmp_path / "s.json"),
            "--analytics-out", str(tmp_path / "a.json")]

    _write_snapshot(snapshot, "2026-11-13T03:00:00+00:00")     # giữa phiên → provisional
    assert backfill.main(args) == 0
    hist = pd.read_csv(store / "2026-11.csv")
    assert hist["provisional"].all()

    _write_snapshot(snapshot, "2026-11-13T10:30:00+00:00")     # sau đóng cửa → chốt
    assert backfill.main(args) == 0
    hist = pd.read_csv(store / "2026-11.csv")
    assert not hist["provisional"].any()
    assert len(hist) == len(hist["ticker"].unique())            # không nhân đôi dòng

    assert backfill.main(args) == 0                             # chạy lại: không đổi
    assert len(pd.read_csv(store / "2026-11.csv")) == len(hist)


def test_backfill_writes_cwintel_cache_on_request(tmp_path):
    snapshot = _write_snapshot(tmp_path / "snap.json", "2026-11-13T10:30:00+00:00")
    cache = tmp_path / "ohlcv.parquet"
    code = backfill.main([
        "--offline", "--snapshot", str(snapshot), "--store", str(tmp_path / "store"),
        "--sessions-out", str(tmp_path / "s.json"), "--analytics-out", str(tmp_path / "a.json"),
        "--cwintel-cache", str(cache),
    ])
    assert code == 0 and cache.exists()
    frame = pd.read_parquet(cache)
    assert list(frame.columns) == ["Ticker", "time", "open", "high", "low", "close", "volume"]
    assert len(frame) == 11          # chỉ các mã có khớp lệnh


def test_backfill_fails_cleanly_without_snapshot(tmp_path, capsys):
    code = backfill.main(["--offline", "--snapshot", str(tmp_path / "missing.json"),
                          "--store", str(tmp_path / "store")])
    assert code == 1
    assert "không có snapshot" in capsys.readouterr().err


def test_backfill_rejects_bad_payload(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"success": False, "response": []}), encoding="utf-8")
    code = backfill.main(["--offline", "--snapshot", str(bad), "--store", str(tmp_path / "s")])
    assert code == 1
    assert "không dùng được" in capsys.readouterr().err


# ──────────────────────────────────────────────────────────────────
# BÁO CÁO NỐI DASHBOARD CŨ
# ──────────────────────────────────────────────────────────────────
def test_bridge_report_states_what_is_missing(tmp_path):
    store = tmp_path / "store"
    snapshot = _write_snapshot(tmp_path / "snap.json", "2026-11-13T10:30:00+00:00")
    backfill.main(["--offline", "--snapshot", str(snapshot), "--store", str(store),
                   "--sessions-out", str(tmp_path / "s.json"),
                   "--analytics-out", str(tmp_path / "a.json")])

    report = bridge.build_report(store=store)
    keys = {req["key"] for req in report["requirements"]}
    assert {"ohlcv", "terms", "underlying", "riskfree", "rights"} <= keys
    # Thiếu điều khoản + giá cơ sở + lợi suất → chưa build được dashboard cũ
    assert report["verdict"]["canBuildLegacyDashboard"] is False
    assert set(report["blockers"]) == {"terms", "underlying", "riskfree", "rights"}
    assert report["history"]["sessions"] == 1
    assert report["history"]["bridgeRows"] == 11
    text = json.dumps(report, ensure_ascii=False)
    for word in ("strike", "maturity", "Greeks", "KHÔNG có trong endpoint"):
        assert word in text
    # Không được tuyên bố có số liệu mà nguồn không có
    assert "canBuildLegacyDashboard\": true" not in text


def test_bridge_cli_exit_codes(tmp_path, capsys):
    assert bridge.main(["--store", str(tmp_path / "empty")]) == 2
    out = capsys.readouterr().out
    assert "Chưa có dữ liệu" in out
    assert "KHÔNG có trong endpoint" in out

    snapshot = _write_snapshot(tmp_path / "snap.json", "2026-11-13T10:30:00+00:00")
    store = tmp_path / "store"
    backfill.main(["--offline", "--snapshot", str(snapshot), "--store", str(store),
                   "--sessions-out", str(tmp_path / "s.json"),
                   "--analytics-out", str(tmp_path / "a.json")])
    target = tmp_path / "report.json"
    assert bridge.main(["--store", str(store), "--json", str(target)]) == 2
    assert target.exists()


def test_bridge_reports_ready_when_cwintel_caches_exist(tmp_path, monkeypatch):
    """Khi đã có đủ cache của pipeline cũ, báo cáo phải chuyển sang 'build được'."""
    store = tmp_path / "store"
    snapshot = _write_snapshot(tmp_path / "snap.json", "2026-11-13T10:30:00+00:00")
    backfill.main(["--offline", "--snapshot", str(snapshot), "--store", str(store),
                   "--sessions-out", str(tmp_path / "s.json"),
                   "--analytics-out", str(tmp_path / "a.json")])

    for name in ("VIETSTOCK_CACHE", "OHLCV_CACHE", "UNDERLYING_CACHE"):
        fake = tmp_path / f"{name}.parquet"
        fake.write_bytes(b"")
        monkeypatch.setattr(bridge.config, name, fake)
    report = bridge.build_report(store=store)
    assert report["cwintelCachesPresent"]["allPresent"] is True
    assert report["verdict"]["canBuildLegacyDashboard"] is True
