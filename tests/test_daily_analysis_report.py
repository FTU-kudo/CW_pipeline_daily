"""Kiểm thử báo cáo hằng ngày và workflow phân tích (offline, không mạng)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import daily_analysis_report as dr

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "yuanta_ew_sample.json"
WORKFLOW = ROOT / ".github" / "workflows" / "daily_analysis.yml"


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _snapshot(path: Path, fetched: str, rows=None, count: int | None = None) -> Path:
    rows = rows if rows is not None else json.loads(FIXTURE.read_text(encoding="utf-8"))["response"]
    return _write(path, {"schemaVersion": 1, "fetchedAt": fetched,
                         "count": count if count is not None else len(rows), "rows": rows})


def _paths(tmp_path: Path) -> dict:
    return {
        "snapshot_path": tmp_path / "snap.json",
        "board_path": tmp_path / "board.json",
        "analytics_path": tmp_path / "an.json",
        "sessions_path": tmp_path / "se.json",
    }


# ──────────────────────────────────────────────────────────────────
# ĐẦU VÀO THIẾU / CŨ
# ──────────────────────────────────────────────────────────────────
def test_missing_snapshot_is_actionable_not_a_crash(tmp_path):
    report, code = dr.build_report(**_paths(tmp_path))
    assert code == 1 and report["ok"] is False
    assert "fetch_yuanta_snapshot.py" in report["reason"]
    text = dr.render_markdown(report)
    assert "KHÔNG CÓ DỮ LIỆU" in text
    assert "fetch_yuanta_snapshot.py" in text


def test_stale_data_sets_exit_code_three_and_warns(tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat(timespec="seconds")
    paths = _paths(tmp_path)
    _snapshot(paths["snapshot_path"], old)
    report, code = dr.build_report(**paths, max_age_hours=36)
    assert code == 3
    assert report["staleData"] is True
    assert report["ageHours"] > 48
    assert "Dữ liệu cũ" in dr.render_markdown(report)


def test_fresh_data_does_not_warn(tmp_path):
    fresh = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(timespec="seconds")
    paths = _paths(tmp_path)
    _snapshot(paths["snapshot_path"], fresh)
    report, code = dr.build_report(**paths, max_age_hours=36)
    assert code == 0 and report["staleData"] is False
    assert "Dữ liệu cũ" not in dr.render_markdown(report)


def test_max_age_zero_disables_the_check(tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec="seconds")
    paths = _paths(tmp_path)
    _snapshot(paths["snapshot_path"], old)
    _, code = dr.build_report(**paths, max_age_hours=None)
    assert code == 0


# ──────────────────────────────────────────────────────────────────
# NỘI DUNG BÁO CÁO
# ──────────────────────────────────────────────────────────────────
def test_report_reads_published_artifacts_end_to_end(tmp_path):
    paths = _paths(tmp_path)
    _snapshot(paths["snapshot_path"], "2026-11-13T10:30:00+00:00")
    _write(paths["board_path"], {
        "summary": {"rows": 12, "traded": 11, "untraded": 1, "totalValueVND": 31_660_158_461,
                    "totalVolume": 57_865_800, "underlyings": 20, "gainers": 95,
                    "losers": 206, "unchanged": 52, "medianChangePct": -1.2,
                    "medianSpreadPct": 2.9, "medianSpreadTicks": 1.0,
                    "top10ValueSharePct": 23.82},
        "quality": {"status": "ok", "failed": 0, "warned": 0, "checks": []},
        "movers": {"gainers": [], "losers": []},
        "byUnderlying": [],
    })
    _write(paths["analytics_path"], {
        "liquidity": {
            "ranking": [{"rank": 1, "t": "CVPB2622", "u": "VPB", "price": 1350,
                         "chgPct": -1.46, "valueVND": 1_294_586_496,
                         "valueSharePct": 4.09, "tier": "rất cao"}],
            "thresholds": [{"quantile": "p80", "valueVND": 116_065_361}],
            "concentration": {"top1ValueSharePct": 4.09, "top10ValueSharePct": 23.82,
                              "hhi": 0.0129},
        },
        "stale": {"count": 54, "sharePct": 13.27, "thresholdSessions": 5, "rows": [],
                  "recoveredCount": 0},
        "intraday": {"available": True, "summary": {"medianRangePct": 7.3,
                                                    "medianRangeTicks": 3.0,
                                                    "countFlatSession": 63,
                                                    "countCloseInUpperHalf": 188,
                                                    "countCloseInLowerHalf": 102}},
        "priceBand": {"available": True, "summary": {"countAtCeiling": 2,
                                                     "atCeiling": ["CVPB2532"],
                                                     "countAtFloor": 6,
                                                     "atFloor": ["CFPT2603"],
                                                     "medianBandPct": 3800.0}},
        "lastTrade": {"available": True, "summary": {"medianLastSharePct": 2.9,
                                                     "countSingleTradeClose": 36,
                                                     "countTraded": 353,
                                                     "singleTradeSharePct": 10.2}},
        "refContinuity": {"available": True, "prevSession": "2026-11-12",
                          "summary": {"linked": 353, "checked": 407, "linkedPct": 86.7,
                                      "mismatch": 0, "missingSession": 0,
                                      "tolerancePct": 25, "verdict": "Liền mạch"}},
        "historyCoverage": {"sessions": 1, "first": "2026-11-13", "last": "2026-11-13",
                            "tickers": 11, "rows": 11, "tradedSharePct": 86.73,
                            "missingSessions": []},
        "caveats": [],
    })
    _write(paths["sessions_path"], {"tickers": {"CVPB2622": {}}})

    report, code = dr.build_report(**paths, max_age_hours=None)
    assert code == 0
    text = dr.render_markdown(report)
    # Số phải đọc đúng từ artifact, không tự tính lại
    assert "31.660.158.461 VND" in text
    assert "CVPB2622" in text and "rất cao" in text
    assert "4,09%" in text
    assert "Liền mạch" in text
    assert "3.800,0%" in text
    # Và phải nói rõ cái gì KHÔNG có
    assert "khuyến nghị" in text and "backtest" in text


def test_report_does_not_mislabel_missing_artifacts_as_zero(tmp_path):
    """Thiếu file phân tích → báo 'KHÔNG', không được im lặng coi như 0."""
    paths = _paths(tmp_path)
    _snapshot(paths["snapshot_path"], "2026-11-13T10:30:00+00:00")
    report, _ = dr.build_report(**paths, max_age_hours=None)
    assert report["hasBoardAnalysis"] is False
    assert report["hasAnalytics"] is False
    text = dr.render_markdown(report)
    assert "phân tích board: KHÔNG" in text


def test_summary_mode_omits_detail_tables(tmp_path):
    paths = _paths(tmp_path)
    _snapshot(paths["snapshot_path"], "2026-11-13T10:30:00+00:00")
    _write(paths["analytics_path"], {"stale": {"count": 54, "sharePct": 13.27, "rows": [
        {"t": "CFPT2617", "u": "FPT", "refPrice": 100, "sessionsIdle": None}]}})
    report, _ = dr.build_report(**paths, max_age_hours=None)
    assert "CFPT2617" in dr.render_markdown(report, compact=False)
    assert "CFPT2617" not in dr.render_markdown(report, compact=True)


def test_continuity_gap_is_surfaced_in_the_report(tmp_path):
    paths = _paths(tmp_path)
    _snapshot(paths["snapshot_path"], "2026-11-13T10:30:00+00:00")
    _write(paths["analytics_path"], {"refContinuity": {
        "available": True, "prevSession": "2026-11-11",
        "summary": {"linked": 0, "checked": 407, "linkedPct": 0.0, "mismatch": 0,
                    "missingSession": 353, "tolerancePct": 25,
                    "verdict": "Có đứt gãy — xem chi tiết từng mã"}}})
    text = dr.render_markdown(dr.build_report(**paths, max_age_hours=None)[0])
    assert "thiếu phiên: 353" in text
    assert "đứt gãy" in text


# ──────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────
def test_cli_json_and_file_output(tmp_path, capsys):
    paths = _paths(tmp_path)
    _snapshot(paths["snapshot_path"], "2026-11-13T10:30:00+00:00")
    out = tmp_path / "report.md"
    code = dr.main(["--snapshot", str(paths["snapshot_path"]),
                    "--board", str(tmp_path / "no.json"),
                    "--analytics", str(tmp_path / "no2.json"),
                    "--sessions", str(tmp_path / "no3.json"),
                    "--max-age-hours", "0", "--out", str(out)])
    assert code == 0
    assert out.exists() and "Báo cáo chứng quyền Yuanta" in out.read_text(encoding="utf-8")
    capsys.readouterr()          # bỏ output của lần gọi trước trước khi đọc JSON

    code = dr.main(["--snapshot", str(paths["snapshot_path"]),
                    "--board", str(tmp_path / "no.json"),
                    "--analytics", str(tmp_path / "no2.json"),
                    "--sessions", str(tmp_path / "no3.json"),
                    "--max-age-hours", "0", "--format", "json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["counts"]["rows"] == 12


def test_cli_exit_code_three_when_stale(tmp_path):
    paths = _paths(tmp_path)
    _snapshot(paths["snapshot_path"], "2020-01-01T00:00:00+00:00")
    args = ["--snapshot", str(paths["snapshot_path"]),
            "--board", str(tmp_path / "no.json"), "--analytics", str(tmp_path / "no2.json"),
            "--sessions", str(tmp_path / "no3.json")]
    assert dr.main([*args, "--max-age-hours", "36"]) == 3


# ──────────────────────────────────────────────────────────────────
# WORKFLOW
# ──────────────────────────────────────────────────────────────────
def test_daily_workflow_is_dispatchable_and_offline():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text            # cronjob.org gọi được
    assert "scripts/daily_analysis_report.py" in text
    assert "GITHUB_STEP_SUMMARY" in text          # kết quả đọc được trên trang Actions
    assert "exit 3" in text                       # dữ liệu cũ → job đỏ
    # Không tự gọi API: phân tích đọc artifact đã publish
    assert "fetch_yuanta_snapshot.py" not in text
    assert "ysradar.yuanta.com.vn" not in text
    assert "permissions:\n  contents: read" in text


def test_workflow_creates_the_report_directory_before_redirecting():
    """`> report/daily.md` mở file TRƯỚC khi python chạy → phải mkdir trước.

    Đây là lỗi thật đã làm workflow đỏ ở lần chạy đầu: shell báo
    "report/daily.md: No such file or directory" và thoát 1, dù script đúng.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    run = text[text.index("Build the daily report"):text.index("Upload the report")]

    mkdir_at = run.find("mkdir -p report")
    first_redirect = min((i for i in (run.find("> report/daily.md"),
                                      run.find("> report/daily.json")) if i != -1), default=-1)
    assert mkdir_at != -1, "thiếu mkdir -p report"
    assert first_redirect != -1
    assert mkdir_at < first_redirect, "mkdir phải đứng trước lệnh redirect"
    # Mỗi chế độ đều ghi ra file có ngày để lưu trữ
    assert "-cw-report.md" in run and "-cw-report.json" in run


def test_workflow_shell_snippet_is_valid_bash(tmp_path):
    """Trích step ra file .sh và chạy `bash -n` — bắt lỗi cú pháp trước khi lên CI."""
    import shutil
    import subprocess

    text = WORKFLOW.read_text(encoding="utf-8")
    run = text[text.index("        run: |\n", text.index("Build the daily report")):]
    lines = []
    for line in run.splitlines()[1:]:
        if line.strip() and not line.startswith("          "):
            break
        lines.append(line[10:] if line.startswith(" " * 10) else "")
    script = tmp_path / "step.sh"
    script.write_text("\n".join(lines), encoding="utf-8")
    if shutil.which("bash"):
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    assert "mkdir -p report" in script.read_text(encoding="utf-8")


def test_published_docs_mention_the_new_workflow():
    deploy = (ROOT / "docs" / "CRONJOB.md").read_text(encoding="utf-8")
    assert "daily_analysis.yml" in deploy
    assert "/dispatches" in deploy
    assert "Actions: Read and write" in deploy
    assert "10 18 * * 1-5" in deploy
