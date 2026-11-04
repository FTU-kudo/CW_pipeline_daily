"""Heatmap phải luôn có màu hợp lệ và chữ đọc được ở cả light/dark.

Bug gốc: `colorFor()` nhận `metric.domain` là **hàm** thay vì giá trị đã
resolve → `value / function = NaN` → `mix()` trả `#NaNNaNNaN` → CSS không hợp lệ
→ ô trong suốt, chữ trắng trên nền trắng ở light mode.

Bộ test này khoá lại 3 thứ:
1. `docs/assets/heatscale.js` là hàm thuần, được kiểm thử bằng Node
   (màu hợp lệ + tương phản WCAG AA cho mọi thang/giá trị).
2. `heatmap.js` resolve domain trước khi tô màu và dùng module trên.
3. CSS không còn hardcode màu chữ trắng cho ô heatmap.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEATMAP = ROOT / "docs" / "assets" / "pages" / "heatmap.js"
SCALE = ROOT / "docs" / "assets" / "heatscale.js"
CSS = ROOT / "docs" / "assets" / "app.css"
JS_TEST = ROOT / "tests" / "js" / "heatscale.test.mjs"

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="không có node trong môi trường chạy test")
def test_heatscale_module_invariants() -> None:
    """Chạy bộ kiểm thử JS: màu hợp lệ + tương phản >= 4.5:1 cho mọi ô."""
    proc = subprocess.run(  # noqa: S603 - đường dẫn cố định trong repo
        [NODE, str(JS_TEST)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "heatscale: OK" in proc.stdout


def test_heatmap_resolves_domain_before_coloring() -> None:
    src = HEATMAP.read_text(encoding="utf-8")
    assert "from '../heatscale.js'" in src, "heatmap.js phải dùng module thang màu chung"
    assert "resolveMetric(" in src, "thiếu bước resolve domain"
    assert "resolveDomain(base.domain, rows)" in src, "phải resolve domain từ hàm sang giá trị"
    # Không còn truyền metric chưa resolve vào hàm màu, và không tự chế thang màu
    assert "colorFor(val, metric)" not in src
    assert "function mix(" not in src, "thang màu phải nằm trong heatscale.js, không lặp lại ở page"


def test_heatmap_cells_set_explicit_text_color() -> None:
    src = HEATMAP.read_text(encoding="utf-8")
    assert re.search(r"background:\$\{bg\};color:\$\{fg\}", src), "ô phải đặt cả màu nền và màu chữ"
    assert "cellColors(" in src


def test_heatscale_never_returns_invalid_colors() -> None:
    src = SCALE.read_text(encoding="utf-8")
    assert "export function scaleColor" in src
    assert "export function readable" in src
    assert "NO_DATA_COLOR" in src
    # Bảo vệ: mix phải clamp và fallback, không nối chuỗi từ NaN
    assert "safeHex" in src
    assert "Number.isFinite" in src


def test_css_has_no_hardcoded_white_heatmap_text() -> None:
    css = CSS.read_text(encoding="utf-8")
    block = css[css.index(".tm-cell {"):]
    block = block[: block.index("}")]
    assert "color: #fff" not in block, "màu chữ ô heatmap phải do JS quyết định theo nền"
    assert ".tm-group-label" in css
    assert "tm-cell:focus-visible" in css


def test_heatmap_handles_empty_and_resize() -> None:
    src = HEATMAP.read_text(encoding="utf-8")
    assert "Không có CW nào khớp bộ lọc" in src, "phải có trạng thái rỗng thay vì khung trắng"
    assert "bindResize()" in src, "phải vẽ lại khi đổi kích thước"
    assert "ResizeObserver" in src
