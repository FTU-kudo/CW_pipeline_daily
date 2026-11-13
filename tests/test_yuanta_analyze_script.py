"""Chạy end-to-end script phân tích ở chế độ offline (không gọi mạng)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts import analyze_yuanta_warrants as script
from scripts.yuanta_snapshot import normalize_payload

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "yuanta_ew_sample.json"


def test_offline_run_writes_csv_and_json(tmp_path, capsys):
    out_csv = tmp_path / "yuanta_covered_warrants.csv"
    out_json = tmp_path / "board.json"
    code = script.main(["--offline", str(FIXTURE), "--csv", str(out_csv),
                        "--json", str(out_json), "--md-rows", "5"])
    assert code == 0

    frame = pd.read_csv(out_csv)
    assert len(frame) == 12
    assert {"StockCode", "Underlying", "TradingValueVND", "SpreadPct"} <= set(frame.columns)
    # Lệnh đã chạy không để lại file tạm
    assert not list(tmp_path.glob("*.tmp"))

    artifact = json.loads(out_json.read_text(encoding="utf-8"))
    assert artifact["quality"]["status"] in {"ok", "warn"}

    printed = capsys.readouterr().out
    assert "| Mã CW |" in printed
    assert "CHPG2512" in printed
    assert "dòng đầu theo mã" in printed
    # Bảng có đúng số dòng dữ liệu theo --md-rows và số được làm tròn để đọc
    table_rows = [line for line in printed.splitlines() if line.startswith("| C")]
    assert len(table_rows) >= 5
    assert "| 19,340,250 |" in printed


def test_script_accepts_the_published_snapshot_shape(tmp_path):
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))["response"]
    snapshot = normalize_payload({"success": True, "response": rows})
    snapshot_path = tmp_path / "yuanta_snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    out_csv = tmp_path / "cw.csv"
    code = script.main(["--offline", str(snapshot_path), "--csv", str(out_csv),
                        "--json", str(tmp_path / "b.json"), "--skip-json"])
    assert code == 0
    assert len(pd.read_csv(out_csv)) == len(rows)


def test_skips_analysis_json_when_asked(tmp_path):
    out_json = tmp_path / "board.json"
    code = script.main(["--offline", str(FIXTURE), "--csv", str(tmp_path / "cw.csv"),
                        "--json", str(out_json), "--skip-json"])
    assert code == 0
    assert not out_json.exists()


def test_failed_api_call_exits_nonzero_without_writing(tmp_path, monkeypatch):
    def boom(**kwargs):
        from scripts.yuanta_client import YuantaHTTPError
        raise YuantaHTTPError("Gọi Yuanta thất bại sau 3 lần thử: HTTP 403")

    monkeypatch.setattr(script, "fetch_board", boom)
    out_csv = tmp_path / "cw.csv"
    assert script.main(["--csv", str(out_csv), "--json", str(tmp_path / "b.json")]) == 1
    assert not out_csv.exists()


def test_api_rejection_and_bad_shapes_exit_nonzero(tmp_path):
    bad_success = tmp_path / "bad.json"
    bad_success.write_text(json.dumps({"success": False, "response": []}), encoding="utf-8")
    assert script.main(["--offline", str(bad_success), "--csv", str(tmp_path / "a.csv")]) == 1

    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"success": True, "response": []}), encoding="utf-8")
    assert script.main(["--offline", str(empty), "--csv", str(tmp_path / "b.csv")]) == 1

    missing = tmp_path / "nope.json"
    assert script.main(["--offline", str(missing), "--csv", str(tmp_path / "c.csv")]) == 1


def test_quality_failure_returns_exit_code_three(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"success": True, "response": [{
        "StockCode": "CAAA2501", "Exchange": "HSX", "SymbolType": "EW",
        "RefP": 100, "FloorP": 500, "CeilingP": 900,
        "LowestP": 300, "HighestP": 200, "OpenP": 150, "AvgP": 120, "LastMP": 110,
        "TotalVol": 3000, "TotalVal": 999999, "B1P": 0, "S1P": 0,
    }]}, ensure_ascii=False), encoding="utf-8")
    out_json = tmp_path / "b.json"
    assert script.main(["--offline", str(broken), "--csv", str(tmp_path / "cw.csv"),
                        "--json", str(out_json)]) == 3
    # Dữ liệu hỏng KHÔNG được ghi đè artifact đã publish (nếu không Pages sẽ phục vụ
    # đúng cái bảng sai đó và bản tốt gần nhất bị mất).
    assert not out_json.exists()
    assert not (tmp_path / "cw.csv").exists()
