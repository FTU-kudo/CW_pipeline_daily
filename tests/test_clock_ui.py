"""Static checks for the snapshot-only Pages interface."""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / "docs" / "index.html").read_text(encoding="utf-8")


def test_board_explains_snapshot_and_missing_history():
    assert "Yuanta" in HTML
    assert "không có OHLCV ngày riêng" in HTML
    assert "không hiển thị lịch sử" in HTML
    assert "historicalOhlcvAvailable" not in HTML  # Only metadata is read, not assumed.


def test_board_exposes_raw_market_fields_and_download():
    for field in ("StockCode", "RefP", "LastMP", "TotalVol", "TotalVal", "B1P", "S1P"):
        assert field in HTML
    assert "Tải JSON snapshot" in HTML
    assert "JSON gốc" in HTML


def test_board_uses_static_snapshot_not_browser_api_calls():
    assert "data/yuanta_snapshot.json" in HTML
    assert "ysradar.yuanta.com.vn" not in HTML
    assert "historical" not in HTML.lower() or "historicalOhlcvAvailable" not in HTML
    assert "textContent" in HTML
