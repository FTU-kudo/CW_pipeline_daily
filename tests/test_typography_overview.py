"""Kiểm tra phông self-hosted và lưới KPI cân đối của trang Tổng quan."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CSS = (DOCS / "assets" / "app.css").read_text(encoding="utf-8")
FONT_CSS = (DOCS / "assets" / "fonts" / "be-vietnam-pro.css").read_text(encoding="utf-8")
HTML = (DOCS / "index.html").read_text(encoding="utf-8")
OVERVIEW = (DOCS / "assets" / "pages" / "overview.js").read_text(encoding="utf-8")
CORE = (DOCS / "assets" / "core.js").read_text(encoding="utf-8")


def _first_rule(selector: str) -> str:
    start = CSS.index(selector)
    return CSS[start:CSS.index("}", start) + 1]


def test_be_vietnam_pro_is_self_hosted_and_used_for_the_whole_dashboard() -> None:
    assert HTML.index("assets/fonts/be-vietnam-pro.css") < HTML.index("assets/app.css")
    assert HTML.count('as="font"') == 2
    assert "fonts.googleapis.com" not in HTML
    assert FONT_CSS.count("@font-face") == 8
    for weight in (400, 500, 600, 700):
        for subset in ("latin", "vietnamese"):
            name = f"be-vietnam-pro-{subset}-{weight}-normal.woff2"
            path = DOCS / "assets" / "fonts" / name
            assert path.read_bytes()[:4] == b"wOF2", f"font không hợp lệ: {name}"
            assert f'url("./{name}")' in FONT_CSS
    assert "SIL OPEN FONT LICENSE" in (DOCS / "assets" / "fonts" / "OFL.txt").read_text(encoding="utf-8")
    assert '--font-sans: "Be Vietnam Pro"' in CSS
    # Token mono cũ cũng dùng phông mới để KPI, bảng và canvas không bị lạc phông.
    assert '--font-mono: "Be Vietnam Pro"' in CSS
    assert "font-variant-numeric: tabular-nums" in CSS
    assert "document.fonts.ready.then(redrawAllCharts)" in CORE


def test_overview_kpis_form_balanced_grid_with_aligned_content() -> None:
    assert "grid kpi overview-kpi section" in OVERVIEW
    main = OVERVIEW.split("export default function overview", 1)[1].split("function lifeChips", 1)[0]
    assert main.count("kpiCard({") == 10

    grid = _first_rule(".grid.kpi.overview-kpi {")
    card = _first_rule(".grid.kpi.overview-kpi .kpi-card {")
    label = _first_rule(".grid.kpi.overview-kpi .kpi-label {")
    assert "repeat(5, minmax(0, 1fr))" in grid
    assert "grid-auto-rows: 1fr" in grid
    assert "grid-template-rows: auto auto 1fr" in card
    assert "height: 100%" in card and "min-height: 176px" in card
    assert "min-height: 2.7em" in label

    tablet = CSS[CSS.index("@media (max-width: 1100px)", CSS.index("OVERVIEW KPI ALIGNMENT")):]
    assert "repeat(2, minmax(0, 1fr))" in tablet
    phone = CSS[CSS.index("@media (max-width: 420px)", CSS.index("OVERVIEW KPI ALIGNMENT")):]
    assert "grid-template-columns: minmax(0, 1fr)" in phone
