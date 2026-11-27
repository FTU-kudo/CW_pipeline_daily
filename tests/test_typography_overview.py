"""Responsive and accessible basics for the lightweight Yuanta snapshot page."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "docs" / "assets" / "ui.css").read_text(encoding="utf-8")
DETAIL_JS = (ROOT / "docs" / "assets" / "detail.js").read_text(encoding="utf-8")


def test_page_has_viewport_semantics_and_mobile_table_scrolling():
    assert '<meta name="viewport"' in HTML
    assert "<main>" in HTML and '<header class="app-header">' in HTML and '<footer id="app-footer"' in HTML
    # Responsive styling is maintained in the shared stylesheet, not duplicated inline.
    assert ".table-wrap" in CSS and "overflow: auto" in CSS
    assert "@media (max-width: 700px)" in CSS


def test_data_values_are_escaped_before_html_insertion():
    # Dynamic raw source fields in the detail drawer must be escaped as both keys and values.
    assert "function rawSection(row)" in DETAIL_JS
    assert "${esc(k)}" in DETAIL_JS
    assert "${esc(v)}" in DETAIL_JS
    # Snapshot download serializes structured data rather than interpolating it as markup.
    assert "JSON.stringify(snapshot,null,2)" in HTML


def test_snapshot_url_is_loaded_with_cache_busting():
    assert "const SNAPSHOT_URL = 'data/yuanta_snapshot.json'" in HTML
    assert "cache:'no-store'" in HTML
