"""Kiểm tra tĩnh cho đồng hồ thời gian thực ở topbar.

Không cần trình duyệt: chặn các lỗi hay gặp khi thêm đồng hồ vào shell —
quên gắn vào DOM, quên khởi động, tính giờ theo timezone của máy, hoặc
thiếu phương án giảm chuyển động.
"""

from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
HTML = DOCS / "index.html"
APP = DOCS / "assets" / "app.js"
CLOCK = DOCS / "assets" / "clock.js"
CORE = DOCS / "assets" / "core.js"
CSS = DOCS / "assets" / "app.css"


def test_clock_markup_present_in_shell() -> None:
    html = HTML.read_text(encoding="utf-8")
    assert 'id="market-clock"' in html
    assert 'role="timer"' in html
    for el_id in ("clock-time", "clock-date", "clock-session", "clock-ring"):
        assert f'id="{el_id}"' in html, f"thiếu phần tử #{el_id}"
    # thẻ <time> để máy đọc được, kèm svg cho vòng giây
    assert re.search(r'<time[^>]*id="clock-time"', html), "clock-time phải là <time>"
    assert "<svg" in html and 'class="clock-face"' in html


def test_clock_is_started_by_app() -> None:
    app = APP.read_text(encoding="utf-8")
    assert "startClock" in app and "./clock.js" in app
    # phải khởi động sau khi app hiện ra (không chạy khi còn màn hình boot)
    shown = app.index("classList.remove('hidden')")
    started = app.index("startClock(document")
    assert started > shown
    # đổi ngôn ngữ phải cập nhật nhãn đồng hồ
    assert "getLang" in app
    assert "holidays: () => data.meta?.marketHolidays" in app


def test_clock_module_is_timezone_fixed() -> None:
    src = CLOCK.read_text(encoding="utf-8")
    assert "Asia/Ho_Chi_Minh" in src
    assert "Intl.DateTimeFormat" in src and "timeZone" in src
    # mỗi giây đọc lại Date.now() thay vì cộng dồn biến đếm
    assert "Date.now()" in src
    assert "setInterval" in src
    assert "visibilitychange" in src, "phải đồng bộ lại khi quay lại tab"
    for fn in ("clockParts", "sessionKey", "sessionLabel", "startClock", "secondsProgress"):
        assert f"export function {fn}" in src, f"thiếu export {fn}"
    for key in ("ato", "open", "break", "atc", "post", "closed", "weekend", "holiday"):
        assert f"'{key}'" in src, f"thiếu trạng thái phiên {key}"


def test_clock_styles_respect_reduced_motion() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert ".clock" in css and ".clock-time" in css and ".clock-session" in css
    assert "prefers-reduced-motion" in css
    # số phải dùng chữ số đều để không nhảy layout mỗi giây
    assert "tabular-nums" in css
    for tone in ("live", "amber", "muted"):
        assert f'data-tone="{tone}"' in css or f'data-tone=\\"{tone}\\"' in css


def test_kpi_cards_support_tone() -> None:
    core = CORE.read_text(encoding="utf-8")
    assert "tone" in core
    assert re.search(r"kpiCard\(\{[^}]*tone", core), "kpiCard phải nhận tham số tone"
    css = CSS.read_text(encoding="utf-8")
    for tone in ("tone-up", "tone-down", "tone-warn", "tone-accent"):
        assert tone in css
