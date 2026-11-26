"""Regression coverage for the standalone snapshot page's English UI."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "docs" / "assets" / "ui.js"
CSS = ROOT / "docs" / "assets" / "ui.css"
HTML = ROOT / "docs" / "index.html"


def test_snapshot_dictionary_has_unique_keys_and_bilingual_shell() -> None:
    source = UI.read_text(encoding="utf-8")
    start = source.index("export const STRINGS = {")
    end = source.index("\n};", start)
    block = source[start:end]
    keys = re.findall(r"^\s*'((?:[^'\\]|\\.)*)'\s*:", block, re.MULTILINE)
    assert len(keys) >= 200
    assert len(keys) == len(set(keys)), "duplicate snapshot translation key"
    for text in (
        "Toàn cảnh thị trường chứng quyền",
        "Xem",
        "Tuỳ chọn",
        "Mã không giao dịch",
        "Giải thích thuật ngữ",
        "Chứng khoán cơ sở",
        "Giá khớp cuối",
    ):
        assert text in keys, f"missing snapshot UI translation: {text}"


def test_snapshot_currency_units_follow_selected_language() -> None:
    html = HTML.read_text(encoding="utf-8")
    assert "bi('tỷ', 'bn')" in html
    assert "bi('tr', 'm')" in html


def test_overview_cards_use_five_columns_without_a_singleton_desktop_row() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert ".ov-grid {" in css
    assert "grid-template-columns: repeat(5, minmax(0, 1fr));" in css
    assert "@media (max-width: 1180px) {\n  .ov-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }" in css


@pytest.mark.skipif(shutil.which("node") is None, reason="requires Node.js")
def test_snapshot_translates_dynamic_labels_and_preserves_unknown_text() -> None:
    script = f"""
      import {{ translate }} from {json.dumps(UI.as_uri())};
      const cases = {{
        nav: translate('Xem'),
        options: translate('Tuỳ chọn'),
        board: translate('Mã CW'),
        overview: translate('Toàn cảnh thị trường chứng quyền'),
        priced: translate('trên 439 mã định giá được'),
        scored: translate('100 mã có khớp lệnh được chấm'),
        wrapped: translate('mã không giao dịch không chấm\\n ·'),
        summary: translate('439 / 442 mã'),
        overviewNote: translate('VND trong phiên · không phải ADV'),
        spreadNote: translate('1,0 bước giá (10 VND)'),
        unknown: translate('một câu kiểm thử không có trong từ điển'),
      }};
      console.log(JSON.stringify(cases));
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    values = json.loads(result.stdout)
    assert values == {
        "nav": "Views",
        "options": "Options",
        "board": "Warrant",
        "overview": "Covered-warrant market overview",
        "priced": "of 439 valued warrants",
        "scored": "100 traded tickers scored",
        "wrapped": "untraded tickers not scored ·",
        "summary": "439 / 442 tickers",
        "overviewNote": "VND this session · not ADV",
        "spreadNote": "1,0 ticks (10 VND)",
        "unknown": None,
    }
