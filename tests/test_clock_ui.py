"""Static checks for the snapshot-only Pages interface."""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / "docs" / "index.html").read_text(encoding="utf-8")


def test_board_explains_how_history_is_obtained():
    """Lịch sử nay được TÍCH LUỸ từ snapshot, không phải lấy từ nguồn có sẵn.

    Trang phải nói rõ hai điều: (1) endpoint không có dữ liệu quá khứ, (2) bar chỉ hoàn
    chỉnh khi chụp sau giờ đóng cửa, và mã không khớp lệnh không có giá.

    Tên nhà cung cấp KHÔNG được xuất hiện trên giao diện: nhãn hiển thị là "Quant Analysis"
    và mọi chỗ nói về nguồn đều dùng từ trung tính ("nguồn bảng giá"). Việc ghi công nguồn
    dữ liệu nằm ở tầng kỹ thuật (metadata JSON, README, biến môi trường), không ở trang.
    """
    assert "Yuanta" not in HTML
    assert "tích luỹ dần" in HTML
    assert "không backfill quá khứ" in HTML
    assert "Mã không khớp lệnh không có giá đóng cửa" in HTML
    # Không được hứa hẹn định giá/Greeks/khuyến nghị từ nguồn không có dữ liệu đó
    assert "Greeks" in HTML and "khuyến nghị" in HTML
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
