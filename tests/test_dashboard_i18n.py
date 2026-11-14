"""Kiểm tra tĩnh cho lớp song ngữ (VI/EN) và giao diện sáng/tối của dashboard.

Không cần trình duyệt: chỉ đọc asset đã commit để chặn các lỗi hay gặp
(khoá trùng, bản dịch rỗng, thiếu công tắc ngôn ngữ, quên hook i18n).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
I18N = DOCS / "assets" / "i18n.js"
APP = DOCS / "assets" / "app.js"
CORE = DOCS / "assets" / "core.js"
CSS = DOCS / "assets" / "app.css"
HTML = DOCS / "index.html"


def _strings_block() -> str:
    src = I18N.read_text(encoding="utf-8")
    start = src.index("export const STRINGS = {")
    end = src.index("/* ---------------------------------------------------------------\n   2.")
    return src[start:end]


def _entries() -> list[tuple[str, str]]:
    block = _strings_block()
    pairs = re.findall(r'"((?:[^"\\]|\\.)*)":\s*("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')', block)
    return [(k, v) for k, v in pairs]


def test_dictionary_parses_and_is_large() -> None:
    entries = _entries()
    assert len(entries) > 300, f"từ điển quá nhỏ: {len(entries)}"
    assert all(k.strip() for k, _ in entries), "có khoá rỗng trong từ điển"
    assert all(v.strip() for _, v in entries), "có bản dịch rỗng trong từ điển"


def test_dictionary_has_no_duplicate_keys() -> None:
    keys = [k for k, _ in _entries()]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, f"khoá trùng trong từ điển: {dupes[:5]}"


def test_translation_values_contain_latin_letters() -> None:
    entries = _entries()
    # Bản dịch phải là tiếng Anh, không được sót nguyên chuỗi tiếng Việt.
    vn = re.compile(r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]", re.I)
    bad = [(k, v) for k, v in entries if vn.search(v) and len(v) > 12]
    # Một vài tên riêng / mã giữ nguyên tiếng Việt là chấp nhận được.
    assert not bad, f"bản dịch còn tiếng Việt: {bad[:3]}"


def test_yuanta_snapshot_shell_has_board_controls() -> None:
    """Trang Yuanta là một ứng dụng độc lập, không dùng dashboard `assets/app.js`.

    Trước đây test này cấm công tắc ngôn ngữ vì trang chỉ có bảng giá. Nay yêu cầu đã đổi:
    trang có song ngữ VI/EN, sáng/tối, đồng hồ và chi tiết từng mã — nhưng vẫn phải là
    trang TĨNH chỉ đọc file JSON đã publish, không gọi API nhà cung cấp.
    """
    html = HTML.read_text(encoding="utf-8")
    assert 'id="search"' in html
    assert 'id="download"' in html
    assert 'id="rows"' in html
    assert "tích luỹ dần" in html          # lịch sử có, nhưng phải nói rõ nguồn gốc
    assert 'id="tabs"' in html
    for view in ("liquidity", "underlyings", "stale", "history"):
        assert f'id="view-{view}"' in html
    # Song ngữ + sáng/tối phải có công tắc thật trong HTML, không chỉ trong file JS.
    assert 'data-lang-set="vi"' in html and 'data-lang-set="en"' in html
    assert 'data-theme-set="light"' in html and 'data-theme-set="dark"' in html
    # Không gọi API nhà cung cấp từ trình duyệt.
    assert "ysradar.yuanta.com.vn" not in html


def test_i18n_wired_into_runtime() -> None:
    app = APP.read_text(encoding="utf-8")
    core = CORE.read_text(encoding="utf-8")
    assert "initI18n" in app, "app.js không khởi tạo i18n"
    assert "applyI18n(view)" in core, "router không áp dụng i18n sau khi render"
    assert "cwintel:lang" in app, "không re-render khi đổi ngôn ngữ"


def test_theme_has_both_palettes_and_tokens() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert 'html[data-theme="dark"]' in css
    assert 'html[data-theme="light"]' in css
    for token in ("--bg:", "--surface:", "--text:", "--up:", "--down:", "--grid:"):
        # mỗi token phải được định nghĩa cho cả hai theme
        assert css.count(token) >= 2, f"token {token} thiếu ở một theme"
    assert ".chart-legend" in css and ".i18n-en" in css


def test_theme_cycle_is_three_state() -> None:
    core = CORE.read_text(encoding="utf-8")
    assert "THEME_ORDER" in core and "'auto'" in core, "thiếu chế độ theo hệ thống"
    assert "prefers-color-scheme" in core


def test_i18n_templates_cover_engine_narrative() -> None:
    """Các câu do engine sinh ra phải có mẫu dịch, nếu không EN mode sẽ lẫn tiếng Việt."""
    src = I18N.read_text(encoding="utf-8")
    assert "TEMPLATES" in src
    assert src.count("new RegExp(") > 20, "quá ít mẫu câu động"
    for needle in ("xếp thứ", "Premium hoà vốn", "ADV20", "đáo hạn", "Hạ từ MUA"):
        assert needle in src, f"thiếu mẫu dịch cho: {needle}"


def test_recommendation_artifacts_expose_bilingual_labels() -> None:
    """Khuyến nghị phải có cả mã và nhãn tiếng Việt để client không phải đoán."""
    path = DOCS.parent / "output" / "private-data" / "dashboard" / "recommendations.json"
    if not path.exists():
        import pytest
        pytest.skip("local private dashboard artifact not built")
    data = json.loads(path.read_text(encoding="utf-8"))
    cards = data.get("cards") or []
    assert cards, "không có card khuyến nghị"
    sample = cards[0]
    assert "recommendation" in sample
    assert "recommendation_vi" in sample


def _palette(theme: str) -> dict[str, str]:
    css = CSS.read_text(encoding="utf-8")
    start = css.index(f'html[data-theme="{theme}"]')
    end = css.index("}", start)
    block = css[start:end]
    return {k: v.strip() for k, v in re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", block)}


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    adjusted = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * adjusted[0] + 0.7152 * adjusted[1] + 0.0722 * adjusted[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def test_both_themes_meet_wcag_aa_for_text() -> None:
    """Mọi màu chữ trên nền surface/surface-3 phải đạt WCAG AA (>= 4.5:1)."""
    for theme in ("dark", "light"):
        palette = _palette(theme)
        for surface in ("--surface", "--surface-3"):
            for token in ("--text", "--text-2", "--text-3", "--accent", "--up", "--down", "--warn"):
                ratio = contrast_ratio(palette[token], palette[surface])
                assert ratio >= 4.5, f"{theme}: {token} trên {surface} chỉ đạt {ratio:.2f}:1"
