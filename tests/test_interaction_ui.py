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
SHELL = CSS[CSS.rindex("REFERENCE-INSPIRED ANALYTICS SHELL"):]
SHELL_BASE = SHELL.split("@media", 1)[0]


def _block(selector: str) -> str:
    """Lấy phần sau selector tới dấu } gần nhất (đủ cho các rule không lồng nhau)."""
    start = CSS.index(selector)
    return CSS[start:CSS.index("}", start) + 1]


def _last_block(selector: str, source: str = CSS) -> str:
    """Lấy rule ghi đè cuối cùng của selector trong stylesheet hoặc một section."""
    start = source.rindex(selector)
    return source[start:source.index("}", start) + 1]


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


def test_sidebar_is_a_floating_bold_navigation_card() -> None:
    sidebar = _last_block(".sidebar {", SHELL_BASE)
    assert "height: calc(100vh - 32px)" in sidebar
    assert "margin: 16px 0 16px 16px" in sidebar
    assert "border: 1px solid var(--sidebar-border)" in sidebar
    assert "border-radius: var(--shell-radius)" in sidebar
    assert "box-shadow: var(--sidebar-shadow)" in sidebar
    for theme in ('html[data-theme="dark"]', 'html[data-theme="light"]'):
        start = CSS.rindex(theme)
        assert "--sidebar-shadow:" in CSS[start:CSS.index("}", start)]

    nav = _last_block(".nav-item {", SHELL_BASE)
    active = _last_block(".nav-item.active {", SHELL_BASE)
    group = _last_block(".nav-group {", SHELL_BASE)
    assert "color: var(--text)" in nav and "font-weight: 600" in nav
    assert "color: var(--accent-2)" in active
    assert "background: var(--sidebar-active-bg)" in active
    assert "border-color: var(--sidebar-active-ring)" in active
    assert "font-weight: 700" in active and "font-weight: 700" in group


def test_analytics_shell_has_clear_hierarchy_and_mobile_fallbacks() -> None:
    topbar = _last_block(".topbar {", SHELL_BASE)
    view = _last_block(".view {", SHELL_BASE)
    title = _last_block(".page-head h1 {", SHELL_BASE)
    card = _last_block(".card {", SHELL_BASE)
    assert "margin: 16px 16px 0" in topbar and "border-radius: 16px" in topbar
    assert "padding: 26px 28px 32px" in view
    assert "font-size: 26px" in title and "font-weight: 700" in title
    assert "padding: 18px 20px" in card

    # Drawer mobile vẫn đóng/mở được; topbar hẹp chuyển search xuống hàng riêng.
    assert "#sidebar.open" in SHELL and "transform: translateX(-100%)" in SHELL
    assert "width: min(300px, 86vw)" in SHELL
    assert ".topbar-left { order: 3; flex: 1 0 100%; }" in SHELL
    assert "#data-age-pill { display: none; }" in SHELL
    coarse = SHELL[SHELL.rindex("@media (pointer: coarse)"):]
    assert ".icon-btn { width: 38px; height: 38px; }" in coarse
    assert ".nav-item { min-height: 42px; }" in coarse


def test_lifecycle_chips_are_native_buttons_only_when_actionable() -> None:
    assert "const interactive = clickable && key === 't'" in OVERVIEW
    assert "el(interactive ? 'button' : 'span'" in OVERVIEW
    assert "type: interactive ? 'button' : null" in OVERVIEW
    assert "bi('Mở phân tích chi tiết', 'Open detailed analysis for')" in OVERVIEW
    # Chip chỉ hiển thị (đáo hạn/ngừng sớm) không được biến thành nút giả.
    assert "onclick: interactive ?" in OVERVIEW
