"""Responsive and accessible basics for the lightweight Yuanta snapshot page."""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / "docs" / "index.html").read_text(encoding="utf-8")


def test_page_has_viewport_semantics_and_mobile_table_scrolling():
    assert '<meta name="viewport"' in HTML
    assert "<main>" in HTML and "<header>" in HTML and "<footer>" in HTML
    assert ".table-wrap{overflow:auto" in HTML
    assert "@media(max-width:700px)" in HTML


def test_data_values_are_escaped_before_html_insertion():
    assert "const esc = (value)" in HTML
    assert "JSON.stringify(r,null,2)" in HTML
    assert "<pre>${esc(raw)}</pre>" in HTML


def test_snapshot_url_is_loaded_with_cache_busting():
    assert "const SNAPSHOT_URL = 'data/yuanta_snapshot.json'" in HTML
    assert "cache:'no-store'" in HTML
