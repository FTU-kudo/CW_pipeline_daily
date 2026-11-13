"""UI and workflow checks for the Yuanta snapshot-only generation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
PUBLISHER = (ROOT / ".github" / "workflows" / "cw_pipeline.yml").read_text(encoding="utf-8")
TESTS = (ROOT / ".github" / "workflows" / "cw_tests.yml").read_text(encoding="utf-8")


def test_dashboard_scopes_what_the_source_can_support():
    """Không được claim thứ nguồn không có: backtest, định giá, Greeks, khuyến nghị.

    Lịch sử OHLCV thì nay có, nhưng phải kèm giới hạn "tích luỹ từ workflow, không backfill".
    """
    assert "tích luỹ dần" in HTML and "không backfill quá khứ" in HTML
    assert "backtest" in HTML.lower()
    assert "khuyến nghị" in HTML.lower()
    assert "data/yuanta_snapshot.json" in HTML
    # Các artifact mới phải được tải tĩnh, không gọi API provider từ trình duyệt
    assert "data/yuanta_analytics.json" in HTML
    assert "data/yuanta_sessions.json" in HTML
    assert "ysradar.yuanta.com.vn" not in HTML


def test_workflow_commits_the_history_store():
    assert "scripts/backfill_yuanta_history.py" in PUBLISHER
    assert "data/cw_history/*.csv" in PUBLISHER
    assert "docs/data/yuanta_sessions.json" in PUBLISHER


def test_github_has_separate_snapshot_publisher_and_offline_test_workflow():
    assert 'cron: "30 10 * * 1-5"' in PUBLISHER
    assert "scripts/fetch_yuanta_snapshot.py" in PUBLISHER
    assert "docs/data/yuanta_snapshot.json" in PUBLISHER
    assert "secrets." not in PUBLISHER
    assert "pytest -q" in TESTS
    assert "schedule:" not in TESTS
    assert "vnstock" not in TESTS.lower()
    assert not (ROOT / ".github" / "workflows" / "cw_intelligence.yml").exists()
