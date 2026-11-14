"""Giao diện không được nêu tên nhà cung cấp dữ liệu.

Quyết định sản phẩm ("Mức 1 — chỉ đổi nhãn hiển thị"): trang là "Covered Warrants — Quant
Analysis", mọi chỗ nói về nguồn dùng từ trung tính. Việc ghi công nguồn vẫn giữ ở tầng kỹ
thuật — metadata JSON (`source`), README, URL endpoint — vì đó là nghĩa vụ khi dùng API và
là thứ duy nhất khiến pipeline chạy được.

Các test dưới đây khoá lại ranh giới đó: nhãn hiển thị trung tính, nhưng nguồn vẫn được ghi
ở nơi mà người dùng cuối không nhìn thấy.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
UI_JS = (ROOT / "docs" / "assets" / "ui.js").read_text(encoding="utf-8")
DETAIL_JS = (ROOT / "docs" / "assets" / "detail.js").read_text(encoding="utf-8")
CSS = (ROOT / "docs" / "assets" / "ui.css").read_text(encoding="utf-8")


# ── nhãn hiển thị ──────────────────────────────────────────────────────
def test_title_is_the_new_brand():
    assert "Covered Warrants — Quant Analysis" in HTML
    assert "Covered Warrants — Yuanta" not in HTML


def test_provider_name_does_not_appear_in_rendered_surfaces():
    """Không được nêu tên nhà cung cấp ở bất kỳ chuỗi nào HIỆN RA cho người đọc.

    Đường dẫn tệp (`data/yuanta_*.json`, hằng `*_URL`) là tầng kỹ thuật nên được phép —
    chúng không hiển thị. Cách kiểm tra: bỏ mọi đường dẫn tệp và URL khỏi nội dung, rồi
    khẳng định tên nhà cung cấp không còn ở đâu.
    """
    import re

    def visible_text(text: str) -> str:
        """Bỏ đường dẫn tệp JSON, URL và tên biến/hằng kỹ thuật khỏi nội dung."""
        text = re.sub(r"[\w./-]*yuanta[\w./-]*\.json", "", text, flags=re.I)
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"\b[A-Z_]*URL\b", "", text)
        return text

    for name, text in (("index.html", HTML), ("ui.js", UI_JS), ("detail.js", DETAIL_JS)):
        assert "yuanta" not in visible_text(text).lower(), (
            f"{name} còn nêu tên nhà cung cấp ở nội dung hiển thị")


def test_i18n_key_matches_the_new_title():
    """Khoá i18n phải khớp tiêu đề mới, nếu không bản tiếng Anh sẽ không dịch được."""
    assert "Covered Warrants — Quant Analysis" in UI_JS


def test_returned_data_paths_are_unchanged():
    """Đổi nhãn là thay đổi HIỂN THỊ — đường dẫn dữ liệu phải giữ nguyên.

    Nếu test này đỏ, nghĩa là ai đó đã đổi tên tệp JSON: trang sẽ trắng dữ liệu.
    """
    for artifact in ("snapshot", "board_analysis", "analytics", "sessions", "details"):
        assert f"data/yuanta_{artifact}.json" in HTML, f"thiếu đường dẫn {artifact}"


def test_notice_box_was_removed_including_its_css():
    """Bảng đen "Phạm vi dữ liệu" đã bị bỏ; CSS của nó cũng phải bị bỏ."""
    assert 'class="notice"' not in HTML
    assert ".notice{" not in CSS


def test_scope_warnings_moved_to_the_footer_and_stay_accurate():
    """Cảnh báo phạm vi vẫn phải còn — chỉ chuyển chỗ, không được mất.

    Bản cũ còn một lỗi nội dung: nó khẳng định "Vẫn không có Greeks, định giá" trong khi
    350 mã đã có. Bản mới nói đúng giới hạn thật: chỉ mã khớp lệnh và đủ điều khoản.
    """
    assert "tích luỹ dần" in HTML
    assert "không backfill quá khứ" in HTML
    assert "Mã không khớp lệnh không có giá đóng cửa" in HTML
    assert "Vẫn không có Greeks" not in HTML


# ── ghi công nguồn vẫn còn ở tầng kỹ thuật ─────────────────────────────
def test_source_attribution_remains_in_published_metadata():
    """Nhãn trung tính KHÔNG được xoá công nguồn khỏi payload.

    Đây là điểm khác biệt giữa "đổi nhãn hiển thị" và "xoá dấu nguồn": payload vẫn phải nói
    dữ liệu đến từ đâu.
    """
    for artifact in ("yuanta_board_analysis", "yuanta_snapshot"):
        path = ROOT / "docs" / "data" / f"{artifact}.json"
        if not path.exists():
            pytest.skip(f"chưa có {path.name}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "yuanta" in json.dumps(payload.get("source"), ensure_ascii=False).lower()


def test_readme_documents_the_endpoint():
    """README là nơi ghi công nguồn công khai — phải nêu endpoint, không được ẩn."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "ysradar.yuanta.com.vn" in readme
