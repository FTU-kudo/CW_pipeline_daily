"""Bảo đảm lớp tương tác/hover của dashboard không gây hồi quy UX.

Các test này chạy không cần trình duyệt: chúng khoá những bất biến quan trọng
(nâng bằng transform, focus bàn phím, vùng chạm và reduced motion). Smoke test
jsdom ở môi trường phát triển kiểm tra thêm hành vi thật của app.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "docs" / "assets" / "app.css").read_text(encoding="utf-8")
OVERVIEW = (ROOT / "docs" / "assets" / "pages" / "overview.js").read_text(encoding="utf-8")


def _block(selector: str) -> str:
    """Lấy phần sau selector tới dấu } gần nhất (đủ cho các rule không lồng nhau)."""
    start = CSS.index(selector)
    return CSS[start:CSS.index("}", start) + 1]


def test_card_shadows_and_lift_tokens_cover_both_themes() -> None:
    for token in ("--card-rest-shadow", "--card-lift-shadow", "--control-lift-shadow"):
        assert CSS.count(token) >= 3, f"{token} phải có ở cả dark/light và được sử dụng"
    for theme in ('html[data-theme="dark"]', 'html[data-theme="light"]'):
        start = CSS.rindex(theme)
        block = CSS[start:CSS.index("}", start)]
        assert "--card-lift-shadow" in block
    assert "--lift-duration: 180ms" in CSS
    assert "--lift-ease:" in CSS


def test_cards_lift_with_transform_only_on_precise_pointers() -> None:
    media = re.search(r"@media \(hover: hover\) and \(pointer: fine\) \{(.*?)\n\}", CSS, re.S)
    assert media, "hover nâng khối chỉ được bật với chuột/con trỏ chính xác"
    body = media.group(1)
    for selector in (".card:hover", ".kpi-card:hover", ".rec-card:hover"):
        assert selector in body
    assert "translateY(-4px)" in body
    assert "var(--card-lift-shadow)" in body
    # Không thay đổi top/margin/height nên layout không bị đẩy khi hover.
    assert not re.search(r"\b(top|margin|height)\s*:", body)


def test_focus_and_reduced_motion_are_preserved() -> None:
    assert ".life-card:focus-within" in CSS and ".rec-card:focus-within" in CSS
    assert ":focus-visible" in CSS
    reduce = CSS[CSS.rindex("@media (prefers-reduced-motion: reduce)"):]
    assert "transition: none !important" in reduce
    assert "transform: none !important" in reduce


def test_pressed_state_and_touch_targets_exist() -> None:
    assert ".life-chip.clickable:active" in CSS
    assert "scale(.98)" in CSS
    coarse = CSS[CSS.index("@media (pointer: coarse)"):]
    assert ".life-chip.clickable" in coarse and "min-height: 30px" in coarse
    assert ".nav-item" in coarse and "min-height: 40px" in coarse


def test_lifecycle_chips_are_native_buttons_only_when_actionable() -> None:
    assert "const interactive = clickable && key === 't'" in OVERVIEW
    assert "el(interactive ? 'button' : 'span'" in OVERVIEW
    assert "type: interactive ? 'button' : null" in OVERVIEW
    assert "bi('Mở phân tích chi tiết', 'Open detailed analysis for')" in OVERVIEW
    # Chip chỉ hiển thị (đáo hạn/ngừng sớm) không được biến thành nút giả.
    assert "onclick: interactive ?" in OVERVIEW
