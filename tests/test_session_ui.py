"""UI and workflow checks for the Yuanta snapshot-only generation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
PUBLISHER = (ROOT / ".github" / "workflows" / "cw_pipeline.yml").read_text(encoding="utf-8")
TESTS = (ROOT / ".github" / "workflows" / "cw_tests.yml").read_text(encoding="utf-8")


def test_dashboard_does_not_claim_history_or_derived_signals():
    assert "không có OHLCV ngày riêng" in HTML
    assert "không hiển thị lịch sử" in HTML
    assert "backtest" in HTML.lower()
    assert "khuyến nghị" in HTML.lower()
    assert "data/yuanta_snapshot.json" in HTML


def test_github_has_separate_snapshot_publisher_and_offline_test_workflow():
    assert 'cron: "30 10 * * 1-5"' in PUBLISHER
    assert "scripts/fetch_yuanta_snapshot.py" in PUBLISHER
    assert "docs/data/yuanta_snapshot.json" in PUBLISHER
    assert "secrets." not in PUBLISHER
    assert "pytest -q" in TESTS
    assert "schedule:" not in TESTS
    assert "vnstock" not in TESTS.lower()
    assert not (ROOT / ".github" / "workflows" / "cw_intelligence.yml").exists()
