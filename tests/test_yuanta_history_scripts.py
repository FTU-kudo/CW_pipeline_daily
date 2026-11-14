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
    """Ghi snapshot giả. ``count`` phải khớp số dòng thật — trước đây nó tính trên ``rows or []``
    nên khi ``rows=None`` (dùng fixture) thì ``count=0`` cạnh 12 dòng, và chốt chặn trong
    ``build_details`` đã bắt được sự lệch này."""
    if rows is None:
        rows = json.loads(FIXTURE.read_text(encoding="utf-8"))["response"]
    payload = {
        "schemaVersion": 1,
        "fetchedAt": fetched_at,
        "count": len(rows),
        "rows": rows,
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
            "--details-out", str(tmp_path / "details.json"),
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
            "--analytics-out", str(tmp_path / "a.json"),
            "--details-out", str(tmp_path / "details.json")]

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
            "--details-out", str(tmp_path / "details.json"),
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
                   "--analytics-out", str(tmp_path / "a.json"),
            "--details-out", str(tmp_path / "details.json")])

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
                   "--analytics-out", str(tmp_path / "a.json"),
            "--details-out", str(tmp_path / "details.json")])
    target = tmp_path / "report.json"
    assert bridge.main(["--store", str(store), "--json", str(target)]) == 2
    assert target.exists()


def test_bridge_reports_ready_when_cwintel_caches_exist(tmp_path, monkeypatch):
    """Khi đã có đủ cache của pipeline cũ, báo cáo phải chuyển sang 'build được'."""
    store = tmp_path / "store"
    snapshot = _write_snapshot(tmp_path / "snap.json", "2026-11-13T10:30:00+00:00")
    backfill.main(["--offline", "--snapshot", str(snapshot), "--store", str(store),
                   "--sessions-out", str(tmp_path / "s.json"),
                   "--analytics-out", str(tmp_path / "a.json"),
            "--details-out", str(tmp_path / "details.json")])

    for name in ("VIETSTOCK_CACHE", "OHLCV_CACHE", "UNDERLYING_CACHE"):
        fake = tmp_path / f"{name}.parquet"
        fake.write_bytes(b"")
        monkeypatch.setattr(bridge.config, name, fake)
    report = bridge.build_report(store=store)
    assert report["cwintelCachesPresent"]["allPresent"] is True
    assert report["verdict"]["canBuildLegacyDashboard"] is True


# ── chốt chặn ghi đè file publish ───────────────────────────────────────
def test_guard_refuses_to_shrink_a_published_file(tmp_path):
    """Đây là lỗi thật đã xảy ra: test gọi main() với fixture 12 dòng đã ghi đè file 407 dòng.

    Trang mất 395 mã định giá, bộ lọc còn 3 lựa chọn, và không có gì đỏ ở đâu cả.
    """
    target = tmp_path / "details.json"
    target.write_text(json.dumps({"count": 407, "rows": [{"ticker": "X"}] * 407}),
                      encoding="utf-8")
    assert backfill._rows_in_file(target) == 407

    with pytest.raises(SystemExit) as excinfo:
        backfill._guard_published_overwrite({"rows": [{"ticker": "X"}] * 12}, target, 407)
    assert "từ chối ghi đè" in str(excinfo.value)
    # Nêu cả hai con số để người đọc biết quy mô mất mát.
    assert "407" in str(excinfo.value) and "12" in str(excinfo.value)


def test_guard_allows_growth_and_first_write(tmp_path):
    target = tmp_path / "details.json"
    # Chưa có file → lần ghi đầu luôn được phép.
    backfill._guard_published_overwrite({"rows": [1] * 5}, target, None)
    # Tăng số dòng là bình thường.
    backfill._guard_published_overwrite({"rows": [1] * 420}, target, 407)


def test_guard_tolerates_a_small_dip_but_not_a_collapse(tmp_path):
    """Rụng vài mã (huỷ niêm yết) là bình thường; rụng 25% trở lên thì phải dừng."""
    target = tmp_path / "details.json"
    backfill._guard_published_overwrite({"rows": [1] * 400}, target, 407)   # -1,7%: cho qua
    with pytest.raises(SystemExit):
        backfill._guard_published_overwrite({"rows": [1] * 300}, target, 407)  # -26%: chặn


def test_rows_in_file_is_none_when_unreadable(tmp_path):
    assert backfill._rows_in_file(tmp_path / "missing.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text("{khong-phai-json", encoding="utf-8")
    assert backfill._rows_in_file(broken) is None
    # File hợp lệ nhưng không có "rows" (ví dụ payload lỗi) cũng phải trả None, không nổ.
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"available": False}), encoding="utf-8")
    assert backfill._rows_in_file(other) is None


def test_backfill_writes_details_to_the_requested_path(tmp_path):
    """Test phải chỉ rõ --details-out, nếu không nó ghi vào docs/data/ thật."""
    snapshot = _write_snapshot(tmp_path / "snap.json", "2026-11-13T10:30:00+00:00")
    details_out = tmp_path / "details.json"
    assert backfill.main([
        "--offline", "--snapshot", str(snapshot), "--store", str(tmp_path / "store"),
        "--sessions-out", str(tmp_path / "s.json"),
        "--analytics-out", str(tmp_path / "a.json"),
        "--details-out", str(details_out),
    ]) == 0
    payload = json.loads(details_out.read_text(encoding="utf-8"))
    assert payload["count"] == len(payload["rows"]) == 12
