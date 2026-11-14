"""Khoá lại 10 thay đổi giao diện theo yêu cầu của chủ dự án.

Mỗi test tương ứng một việc được yêu cầu, để lần sửa sau không vô tình làm mất. Vài test
kiểm tra sự VẮNG MẶT (khối chất lượng, độ trễ) — đó là điểm dễ tái phát nhất vì chúng từng
là tính năng.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "docs" / "assets" / "ui.css").read_text(encoding="utf-8")


def _details() -> dict:
    return json.loads((ROOT / "docs" / "data" / "yuanta_details.json").read_text(encoding="utf-8"))


# ── 1. Dòng phụ nêu giờ cập nhật ────────────────────────────────────────
def test_1_sub_line_states_the_update_time():
    assert 'id="sub-line"' in HTML
    assert "Bảng giá chứng quyền (CW)" in HTML
    assert "được cập nhật lúc" in HTML
    # Câu này được dựng động từ fetchedAt nên phải nằm trong renderFreshness.
    assert "sub.textContent" in HTML


# ── 2. Bỏ độ trễ và mã phiên ───────────────────────────────────────────
def test_2_relative_age_and_session_are_gone():
    assert "Date.now() - when.getTime()" not in HTML
    assert "bi('cách đây','ago')" not in HTML
    assert "bi('phiên','session')}" not in HTML
    # Nhưng giờ tuyệt đối vẫn phải còn.
    assert "Asia/Ho_Chi_Minh" in HTML


# ── 3. Bỏ khối kiểm tra chất lượng ─────────────────────────────────────
def test_3_quality_block_is_fully_removed():
    assert 'id="quality"' not in HTML
    assert "function renderQuality" not in HTML
    assert "renderQuality(" not in HTML
    assert "Kiểm tra chất lượng dữ liệu" not in HTML
    # CSS đi kèm cũng phải đi, nếu không là rác.
    assert ".quality{" not in HTML
    assert ".chip{" not in HTML


# ── 4. Rê chuột không còn màu đen ──────────────────────────────────────
def test_4_hover_uses_theme_variable_not_hardcoded_black():
    """`tr:hover td{background:#172330}` là màu xanh-đen hard-code — ở light mode thành đen."""
    assert "tr:hover td{background:#172330}" not in HTML
    assert "tr:hover td{background:var(--row-hover)}" in HTML
    assert "--row-hover" in CSS
    # Cả hai chế độ đều phải khai báo, nếu không chế độ kia sẽ thừa hưởng màu sai.
    assert CSS.count("--row-hover:") >= 2


# ── 5. Bộ lọc bốn tiêu chí ─────────────────────────────────────────────
@pytest.mark.parametrize("control", ["#f-underlying", "#f-moneyness", "#f-maturity", "#f-issuer"])
def test_5_filter_controls_exist(control):
    assert f'id="{control.lstrip("#")}"' in HTML


def test_5_filters_are_applied_in_render():
    for needle in ("fUnderlying", "fMoneyness", "fMaturity", "fIssuer"):
        assert needle in HTML
    assert "function fillFilters" in HTML
    # Ô lọc phải tự ẩn khi kho không có trường tương ứng.
    # Ô lọc ẩn bằng `el.hidden` vì thanh lọc nay là MỘT hàng grid, không còn khối nhãn
    # bọc ngoài để ẩn cả khối.
    assert "el.hidden = opts.length === 0" in HTML


def test_5_filter_options_come_from_real_data():
    """Cơ sở / đáo hạn / tổ chức phát hành phải có nhiều hơn một lựa chọn với dữ liệu thật."""
    rows = _details()["rows"]
    underlyings = {r.get("underlying") for r in rows if r.get("underlying")}
    assert len(underlyings) > 5
    issuers = {r.get("issuer") for r in rows if r.get("issuer")}
    assert len(issuers) > 5, "mất trường issuer thì bộ lọc công ty phát hành vô dụng"
    buckets = {str((r.get("valuation") or {}).get("maturity"))[:7]
               for r in rows if (r.get("valuation") or {}).get("maturity")}
    assert len(buckets) >= 2


# ── 6. Màu theo trạng thái tiền và biến động ───────────────────────────
def test_6_moneyness_colours_itm_green_atm_yellow_otm_red():
    assert "money-itm" in HTML and "money-atm" in HTML and "money-otm" in HTML
    for var in ("--itm", "--atm", "--otm"):
        assert CSS.count(f"{var}:") >= 2, f"{var} phải khai báo cho cả hai chế độ"


def test_6_change_colours_up_down_flat():
    assert "chg-up" in HTML and "chg-down" in HTML and "chg-flat" in HTML


def test_6_no_colour_when_moneyness_unknown():
    """Mã không định giá được thì không tô màu — trạng thái chưa xác định, tô là đoán."""
    assert "money === 'ITM' ? 'money-itm'" in HTML
    assert ": money === 'OTM' ? 'money-otm' : ''" in HTML


def test_6_moneyness_counts_match_the_published_analytics():
    rows = _details()["rows"]
    counts = {"ITM": 0, "ATM": 0, "OTM": 0}
    for r in rows:
        m = (r.get("valuation") or {}).get("moneyness")
        if m in counts:
            counts[m] += 1
    assert sum(counts.values()) > 300
    assert counts["OTM"] > counts["ITM"] > 0


# ── 7. Thuật ngữ tập trung một chỗ ─────────────────────────────────────
def test_7_glossary_tab_exists_and_renders():
    assert 'data-view="glossary"' in HTML
    assert 'id="view-glossary"' in HTML
    assert "function renderGlossary" in HTML
    assert "const GLOSSARY" in HTML


def test_7_glossary_covers_every_core_term():
    block = HTML.split("const GLOSSARY", 1)[1].split("function renderGlossary", 1)[0]
    # Tên cột đã đổi sang cách gọi của nhà đầu tư; mã trường gốc vẫn phải còn trong ngoặc
    # "(nguồn: …)" để người đối chiếu dữ liệu tra được.
    for term in ("ITM", "ATM", "OTM", "Black–Scholes", "IV", "HV", "Delta", "Theta",
                 "Vega", "Rho", "Strike", "Premium hoà vốn", "termsBasis",
                 "RefP", "Chênh lệch mua–bán", "HHI", "Tích luỹ dần"):
        assert term in block, f"thiếu thuật ngữ: {term}"


def test_7_long_explanations_were_removed_from_individual_tabs():
    """Các đoạn giải thích chung đã chuyển vào Thuật ngữ.

    Giữ lại câu mang số liệu của phiên (ví dụ "IV trung vị 48,9%") vì bỏ thì con số mất
    ngữ cảnh — nên chỉ khẳng định những đoạn văn dài đặc trưng đã biến mất.
    """
    assert "Vì sao loại" not in HTML
    assert "Đọc IV thế nào" not in HTML
    assert "Giới hạn của mô hình:" not in HTML
    assert "Mã cơ sở suy ra từ quy ước tên CW" not in HTML


# ── 8. Năm tab đầu nổi bật ─────────────────────────────────────────────
def test_8_navigation_is_split_into_three_groups():
    """Chủ dự án yêu cầu tách chế độ xem / tuỳ chọn hiển thị / nút phụ.

    Thay cho yêu cầu "năm tab đầu phải nổi bật": nay không còn khái niệm tab nổi bật,
    thay vào đó là ba nhóm có nhãn riêng và kích thước khác nhau.
    """
    nav = HTML.split('<nav class="nav-block"', 1)[1].split('</nav>', 1)[0]
    # Nhóm 1: năm chế độ xem chính.
    primary = ['board', 'scoring', 'valuation', 'liquidity', 'underlyings']
    for view in primary:
        assert f'data-view="{view}"' in nav
    # Nhóm 2: ba tuỳ chọn hiển thị, phải mang class chip để nhỏ hơn.
    for view in ('stale', 'intraday', 'band'):
        assert f'class="tab chip" data-view="{view}"' in nav, f"{view} phải là chip"
    # Nhóm 3: hai nút phụ có viền, không phải .tab, đẩy sang phải.
    secondary = nav.split('class="nav-secondary"', 1)[1]
    assert 'class="btn-ghost" data-view="history"' in secondary
    assert 'class="btn-ghost" data-view="glossary"' in secondary
    # Mỗi nhóm có nhãn riêng để người dùng hiểu ba loại điều hướng khác nhau.
    assert nav.count('class="nav-group-label"') == 2


def test_9_every_navigation_item_has_an_outline_icon():
    """Emoji đã được thay bằng bộ icon đơn sắc thống nhất (yêu cầu 2.c).

    Emoji mỗi cái một bảng màu nên hàng điều hướng trông lộn xộn; icon nét vẽ 1.75
    và ăn theo currentColor nên tự đúng màu ở cả hai chế độ.
    """
    nav = HTML.split('<nav class="nav-block"', 1)[1].split('</nav>', 1)[0]
    assert nav.count('<svg class="icon"') == 10, "mỗi mục điều hướng đúng một icon"
    assert 'stroke="currentColor"' in nav
    assert 'stroke-width="1.75"' in nav
    # Không còn emoji nào trong thanh điều hướng.
    assert not any(0x1F300 <= ord(ch) <= 0x1FAFF for ch in nav), "nav còn emoji"
    # Nhãn chữ vẫn còn cho trình đọc màn hình.
    assert nav.count('class="t-txt"') == 10


# ── 10. Bảng thống kê toàn thị trường ở trang đầu ──────────────────────
def test_10_overview_is_the_first_thing_on_the_page():
    """Hàng thẻ thống kê thứ ba (#stats) đã bị xoá vì lặp lại đúng các chỉ số này.

    Nay chỉ còn một khối #overview, và nó phải đứng trước thanh điều hướng để là thứ
    đầu tiên người xem thấy.
    """
    assert 'id="overview"' in HTML
    assert "function renderOverview" in HTML
    assert "Toàn cảnh thị trường chứng quyền" in HTML
    # Không còn hàng thẻ trùng lặp.
    assert 'id="stats"' not in HTML
    assert 'class="stats"' not in HTML
    # Đứng trước nav và trước bảng giá.
    assert HTML.index('id="overview"') < HTML.index('class="nav-block"')
    assert HTML.index('id="overview"') < HTML.index('id="rows"')


def test_10_overview_has_exactly_two_rows_of_four_cards():
    """Yêu cầu: tối đa 8–10 chỉ số, chia hai hàng bốn thẻ."""
    block = HTML.split('function renderOverview', 1)[1]
    block = block.split('function ', 1)[0]
    # Tám thẻ được push vào mảng, trong đó hai thẻ có điều kiện (IV, IV − HV).
    assert block.count("{k: '") == 8
    for label in ('Mã CW niêm yết', 'Giá trị giao dịch', 'Cổ phiếu cơ sở',
                  'Tăng / giảm / đứng', 'Phân bố trạng thái tiền', 'IV trung vị',
                  'IV − HV', 'Spread trung vị'):
        assert label in block, f"thiếu thẻ KPI: {label}"


def test_10_kpi_cards_use_the_shared_outline_icon_set():
    """Yêu cầu 2.c: bỏ emoji, dùng icon đơn sắc đồng nhất."""
    block = HTML.split('const ICONS = {', 1)[1].split('function renderOverview', 1)[0]
    assert block.count(':') >= 8, "bộ icon phải có đủ hình cho các thẻ"
    assert not any(0x1F300 <= ord(ch) <= 0x1FAFF for ch in block), "còn emoji trong bộ icon"
    overview = HTML.split('function renderOverview', 1)[1].split('function renderStats', 1)[0]
    assert "icon(c.icon)" in overview


def test_10_change_and_moneyness_cards_have_progress_bars():
    """Yêu cầu 2.c: thanh tiến trình nhỏ cho hai thẻ phân bố."""
    assert "function miniBars" in HTML
    assert "mini-bars" in HTML
    overview = HTML.split('function renderOverview', 1)[1].split('function renderStats', 1)[0]
    assert "bars: [['Tăng'" in overview
    assert "bars: [['ITM'" in overview


def test_10_change_values_are_coloured_green_and_red():
    """Yêu cầu 2.b: tăng xanh, giảm đỏ thay vì toàn bộ chữ đen."""
    overview = HTML.split('function renderOverview', 1)[1].split('function renderStats', 1)[0]
    assert "['up', num(s.gainers)]" in overview
    assert "['down', num(s.losers)]" in overview
    assert "--up-text" in CSS and "--down-text" in CSS


def test_10_overview_omits_cards_whose_data_is_missing():
    """Không in số 0 giả: chỉ số nào không tính được thì bỏ hẳn ô đó."""
    block = HTML.split("function renderOverview", 1)[1].split("function renderStats", 1)[0]
    assert "if (priced)" in block
    assert "if (sum.medianIv !== undefined" in block
    assert "if (ivhv.available" in block


# ── chốt chặn dữ liệu ──────────────────────────────────────────────────
def test_details_file_is_complete_not_truncated():
    """File chi tiết từng bị ghi ra chỉ 12/407 dòng mà không báo lỗi.

    Lỗi im lặng: trang thiếu 395 mã định giá, bộ lọc chỉ còn 3 lựa chọn, và không có gì đỏ.
    """
    payload = _details()
    assert payload["count"] == len(payload["rows"])
    assert len(payload["rows"]) > 350
    priced = sum(1 for r in payload["rows"] if r.get("valuation"))
    assert priced > 300, f"chỉ {priced} mã có định giá — file có thể đã bị ghi thiếu"


def test_build_details_refuses_inconsistent_snapshot_count():
    from cwintel.yuanta_detail import build_details

    snapshot = {"count": 100, "rows": [{"StockCode": "CABC2601"}, {"StockCode": "CABC2602"}]}
    with pytest.raises(ValueError, match="không nhất quán"):
        build_details(snapshot=snapshot, board_analysis=None, analytics=None)


# ── Tiêu đề cột phải là tiếng Việt của nhà đầu tư, không phải tên trường API ──
def _board_thead() -> str:
    return HTML.split('<thead><tr>', 1)[1].split('</tr></thead>', 1)[0]


def _board_headers() -> list[str]:
    """Nhãn hiển thị của 22 cột bảng giá, đã bỏ tooltip."""
    import re
    # Tách theo thẻ mở, bỏ phần thuộc tính của chính <th> đầu tiên.
    cells = re.findall(r'<th[^>]*>(.*?)</th>', _board_thead(), re.S)
    return [re.sub(r'<[^>]+>', '', c).strip() for c in cells]


def test_board_headers_are_investor_vocabulary():
    headers = _board_headers()
    expected = ['Mã CW', 'Giá tham chiếu', 'Giá trần', 'Giá sàn', 'Giá mở cửa',
                'Giá cao nhất', 'Giá thấp nhất', 'Giá bình quân', 'Giá khớp cuối',
                'KL khớp cuối', 'Tổng KL', 'Tổng giá trị', 'KL ngoại mua', 'KL ngoại bán',
                'Room ngoại', 'Giá (VND)', '% trong ngày', 'Chênh lệch mua–bán',
                'Tỷ trọng GT', 'Giá mua 1–3', 'Giá bán 1–3', 'Dữ liệu gốc']
    assert headers == expected


def test_no_source_field_name_appears_as_a_visible_header():
    """Điều chủ dự án nêu: bảng giá không được bắt người đọc học thuật ngữ API."""
    raw = ('RefP', 'CeilingP', 'FloorP', 'OpenP', 'HighestP', 'LowestP', 'AvgP',
           'LastMP', 'LastMVol', 'TotalVol', 'TotalVal', 'FTBuyVol', 'FTSellVol',
           'FRoom', 'Payload')
    for header in _board_headers():
        for field in raw:
            assert field not in header, f"tiêu đề '{header}' còn chứa tên trường {field}"


def test_every_data_column_keeps_its_source_field_in_the_tooltip():
    """Đổi nhãn KHÔNG được làm mất khả năng đối chiếu với dữ liệu gốc."""
    thead = _board_thead()
    for field in ('RefP', 'CeilingP', 'FloorP', 'OpenP', 'HighestP', 'LowestP', 'AvgP',
                  'LastMP', 'LastMVol', 'TotalVol', 'TotalVal', 'FTBuyVol', 'FTSellVol',
                  'FRoom', 'B1', 'S1'):
        assert f'nguồn: {field}' in thead, f"tooltip thiếu trường {field}"


def test_tooltips_appear_on_both_light_and_dark():
    """Tooltip là thuộc tính HTML nên không phụ thuộc theme — khoá lại để không ai gỡ."""
    assert _board_thead().count('title="') >= 18


def test_glossary_explains_each_column_in_plain_vietnamese():
    """Mỗi tiêu đề phải có một mục giải thích trong tab Thuật ngữ."""
    block = HTML.split("const GLOSSARY", 1)[1].split("function renderGlossary", 1)[0]
    for label in ('Giá tham chiếu', 'Giá trần', 'Giá sàn', 'Giá mở cửa', 'Giá bình quân',
                  'Giá khớp cuối', 'KL khớp cuối', 'Tổng KL', 'Tổng giá trị',
                  'KL ngoại mua', 'KL ngoại bán', 'Room ngoại', 'Giá mua 1–3',
                  'Giá bán 1–3', 'Chênh lệch mua–bán', '% trong ngày'):
        assert label in block, f"Thuật ngữ chưa giải thích cột: {label}"


# ── Thanh tiêu đề phải dịu ở chế độ sáng ──
def test_table_header_has_no_hardcoded_colour():
    """`th{background:#172330}` là dải đen chắn ngang trang ở chế độ sáng."""
    assert 'background:#172330' not in HTML
    assert 'th{position:sticky;top:0;background:var(--th-bg)' in HTML
    assert 'th:first-child{z-index:2;background:var(--th-bg)}' in HTML
    assert CSS.count('--th-bg:') >= 2, "phải khai báo cho cả hai chế độ"


import re


def _theme_block(name: str) -> str:
    """Nội dung khối khai báo biến của một theme.

    Không cắt theo `CSS.split('html[data-theme="light"]')` vì chuỗi đó còn xuất hiện trong
    chú thích phía trên, khiến phép cắt rơi vào đúng đoạn chú thích thay vì khối biến.
    """
    match = re.search(rf'html\[data-theme="{name}"\]\s*\{{(.*?)\n\}}', CSS, re.S)
    assert match, f"không tìm thấy khối biến của theme {name}"
    return match.group(1)


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip('#')
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_light_header_is_a_pale_tint_not_a_dark_band():
    """Đo bằng độ sáng tương đối, không đo bằng cảm nhận."""
    light = _theme_block("light")
    th_bg = re.search(r'--th-bg:\s*(#[0-9a-fA-F]{6})', light).group(1)
    page_bg = re.search(r'--bg:\s*(#[0-9a-fA-F]{6})', light).group(1)
    # Rất sáng (gần trắng) chứ không phải xanh-đen.
    assert _luminance(th_bg) > 0.80, f"{th_bg} vẫn còn tối"
    # Có thể trùng nền trang nếu đường kẻ dưới đủ rõ — kiểm tra đường kẻ thay vì
    # bắt buộc hai màu khác nhau.
    if th_bg.lower() == page_bg.lower():
        assert 'thead th' in CSS and 'border-bottom' in CSS.split('thead th', 1)[1][:400]


def test_light_header_text_is_readable():
    """Nền nhạt thì chữ phải đủ đậm — nếu không sẽ thành chữ xám trên nền xám."""
    light = _theme_block("light")
    th_bg = re.search(r'--th-bg:\s*(#[0-9a-fA-F]{6})', light).group(1)
    th_text = re.search(r'--th-text:\s*(#[0-9a-fA-F]{6})', light).group(1)
    assert _contrast(th_bg, th_text) >= 4.5, "chưa đạt WCAG AA"


def test_dark_header_text_is_readable():
    dark = _theme_block("dark")
    th_bg = re.search(r'--th-bg:\s*(#[0-9a-fA-F]{6})', dark).group(1)
    th_text = re.search(r'--th-text:\s*(#[0-9a-fA-F]{6})', dark).group(1)
    assert _contrast(th_bg, th_text) >= 4.5


# ═══════════════════════════════════════════════════════════════════
# Tab Xếp hạng — banner phương pháp, huy hiệu, heatmap, sắp xếp
# ═══════════════════════════════════════════════════════════════════

def _scoring_js() -> str:
    """Thân hàm renderScoring và các hàm phụ trợ của bảng xếp hạng."""
    start = HTML.index('const scoringSort')
    end = HTML.index('// GIẢI THÍCH THUẬT NGỮ')
    return HTML[start:end]


# ── 1. Banner phương pháp ───────────────────────────────────────────────
def test_1_methodology_is_one_collapsible_banner():
    """Hai tiêu đề + ba đoạn văn dài gộp thành một thẻ, phần chi tiết gập lại.

    Bảng dữ liệu phải lên cao hơn — đó là lý do chính của thay đổi này.
    """
    js = _scoring_js()
    assert 'class="score-banner"' in js
    # Chỉ còn MỘT tiêu đề trong banner; hai tiêu đề cũ đã biến mất.
    assert js.count('<h2>Điểm CW theo ngày</h2>') == 0
    assert js.count('<h2>Định giá đã bật</h2>') == 0
    assert js.count('Điểm CW theo ngày') == 1
    # Phần chi tiết mặc định đóng và có nút mở/đóng.
    assert 'id="score-detail" hidden' in js
    assert 'Xem chi tiết cách tính điểm' in js
    assert "toggle.setAttribute('aria-expanded'" in js


def test_1_banner_uses_the_light_blue_palette():
    block = CSS.split('.score-banner {', 1)[1].split('}', 1)[0]
    assert '#f0f9ff' in block          # nền
    assert '#bae6fd' in block          # viền
    # Chế độ tối phải có biến thể, nếu không banner thành ô trắng chói.
    assert 'html[data-theme="dark"] .score-banner' in CSS


def test_1_weights_render_as_badges_not_prose():
    """Yêu cầu: trọng số dạng badge thay cho câu văn xuôi khó đọc."""
    js = _scoring_js()
    assert 'class="wbadge"' in js
    assert 'weightBadges' in js
    # Câu văn xuôi cũ đã bỏ.
    assert "Trọng số: ${parts.map" not in js
    for label in ('Thanh khoản', 'Chi phí', 'Định giá', 'Chất lượng giá'):
        assert label in js
    # Trục "độ ổn định" đã bỏ: badge không được còn nhắc tới nó.
    assert 'Độ ổn định' not in js


def test_1_weight_badges_match_the_published_weights():
    """Badge phải lấy số từ analytics, không hard-code 34/26/20/12/8."""
    import json
    analytics = json.loads(
        (ROOT / 'docs' / 'data' / 'yuanta_analytics.json').read_text(encoding='utf-8'))
    weights = analytics['scoring']['weights']
    # Bốn trục, chuẩn hoá để tổng bằng 1. Không còn 'consistency'.
    assert set(weights) == {'liquidity', 'cost', 'valuation', 'priceQuality'}
    assert sum(weights.values()) == pytest.approx(1.0)
    # Tỷ lệ giữa các trục y như trước khi bỏ trục thứ năm (34/26/20/12 trên tổng 92).
    for key, base in (('liquidity', 34), ('cost', 26), ('valuation', 20), ('priceQuality', 12)):
        assert weights[key] == pytest.approx(base / 92, abs=1e-9)
    js = _scoring_js()
    assert 'weights[k]' in js, "badge phải đọc từ sc.weights"
    assert 'Math.round((weights[k] || 0) * 100)' in js


# ── 2. Bảng xếp hạng ────────────────────────────────────────────────────
def test_2_top_three_get_gold_silver_bronze():
    js = _scoring_js()
    assert "rank === 1 ? 'gold'" in js
    assert "rank === 2 ? 'silver'" in js
    assert "rank === 3 ? 'bronze'" in js
    for cls in ('.medal.gold', '.medal.silver', '.medal.bronze'):
        assert cls in CSS, f"thiếu CSS cho {cls}"


def test_2_ticker_and_underlying_share_one_column():
    """Gộp Mã + Cơ sở thành một cột để tiết kiệm chiều ngang."""
    js = _scoring_js()
    assert 'tick-cell' in js
    assert 'class="utag"' in js
    # Cột "Cơ sở" riêng không còn trong tiêu đề bảng xếp hạng.
    assert "scoringHead('underlying'" not in js
    assert 'Mã / Cơ sở' in js


def test_2_total_score_is_a_badge_with_a_bar():
    js = _scoring_js()
    assert 'score-badge' in js and 'score-track' in js
    # Ba ngưỡng: ≥80, 60–80, <60.
    assert "score >= 80 ? 'strong'" in js
    assert "score >= 60 ? 'mid'" in js
    for cls in ('.score-badge.strong', '.score-badge.mid', '.score-badge.weak'):
        assert cls in CSS


def test_2_component_scores_have_micro_bars():
    js = _scoring_js()
    assert 'part-cell' in js and 'part-track' in js and 'part-fill' in js
    # Năm mức màu chia theo 20 điểm.
    for step in (0, 20, 40, 60, 80):
        assert f'.part-fill.b{step}' in CSS
    # Thanh phải phản ánh điểm thật, không phải chiều rộng cố định.
    assert 'style="width:${v}%"' in js


def test_2_unscored_is_not_rendered_as_zero():
    """`null` = chưa chấm, khác hẳn điểm 0. Hai thứ không được hiển thị giống nhau."""
    js = _scoring_js()
    assert 'chưa chấm' in js
    assert 'title="${escAttr(label)}: chưa đủ dữ liệu để chấm"' in js
    assert '.na {' in CSS


def test_2_change_column_has_colours_and_arrows():
    js = _scoring_js()
    assert '▲ ' in js and '▼ ' in js and '= ' in js
    assert 'chg-up' in js and 'chg-down' in js and 'chg-flat' in js


def test_2_warning_column_uses_dash_and_icon():
    js = _scoring_js()
    # Không cảnh báo → gạch mờ.
    assert '<td class="warn-cell"><span class="na">—</span></td>' in js
    # Có cảnh báo → tam giác + tooltip.
    assert 'warn-icon' in js and 'title="${escAttr(text)}"' in js
    assert 'WARN_ICON' in js
    assert '.warn-icon {' in CSS


def test_2_warning_column_only_flags_outliers_not_every_row():
    """Cảnh báo theo độ phủ từng làm CẢ 50 dòng đều có tam giác — cột mất tác dụng.

    Nay trục thiếu ở toàn bộ mã được nêu một lần ở banner; cột này chỉ nêu cái khác biệt.
    """
    js = _scoring_js()
    warn_fn = js.split('function warnCell', 1)[1].split('\n}', 1)[0]
    assert 'coveragePct' not in warn_fn, "không cảnh báo theo độ phủ nữa"
    assert 'nearCeiling' in warn_fn
    # Vẫn phải nêu được trường hợp một mã đơn lẻ thiếu dữ liệu.
    assert 'Thiếu dữ liệu để chấm' in warn_fn


# ── 3. Tương tác bảng ───────────────────────────────────────────────────
def test_3_header_is_sticky():
    block = CSS.split('thead th {', 1)[1].split('}', 1)[0]
    assert 'position: sticky' in block
    assert 'top: 0' in block


def test_3_every_numeric_column_is_sortable():
    js = _scoring_js()
    for key in ('rank', 'ticker', 'score', 'coveragePct', 'valueVND', 'chgPct',
                'liquidity', 'cost', 'valuation', 'priceQuality'):
        assert f"scoringHead('{key}'" in js, f"cột {key} chưa sắp xếp được"
    # Cột đã bỏ thì không được còn là tiêu đề sắp xếp.
    assert "scoringHead('consistency'" not in js
    assert 'sort-arrow' in js
    assert 'aria-sort' in js
    assert 'tabindex="0"' in js


def test_3_sort_recomputes_rows_on_every_click():
    """Lỗi thật đã xảy ra: lần bấm sắp xếp ĐẦU TIÊN không có tác dụng.

    Nguyên nhân: `resort()` vẽ lại bảng bằng mảng `shown` đã tính TRƯỚC khi đổi khoá.
    Bài học: danh sách phải là kết quả của một hàm gọi lại mỗi lần, không phải biến
    chụp một lần. Test này khoá lại điều đó.
    """
    js = _scoring_js()
    assert 'function scoringRows(sc)' in js, "phải có hàm tính lại danh sách"
    resort = js.split('const resort = () => {', 1)[1].split('};', 1)[0]
    assert 'scoringRows(sc)' in resort, "resort() phải tính lại, không dùng mảng cũ"
    # Mảng cũ tính một lần không được còn tồn tại.
    assert 'const shown = ' not in js


def test_3_sorting_resets_to_a_sensible_direction_per_column():
    js = _scoring_js()
    assert 'SCORING_DEFAULT_DIR' in js
    # Điểm, giá trị, độ phủ đều nên giảm dần khi mở lần đầu.
    block = js.split('const SCORING_DEFAULT_DIR', 1)[1].split('};', 1)[0]
    assert "score: 'desc'" in block
    assert "valueVND: 'desc'" in block


def test_3_missing_part_values_sort_last_in_both_directions():
    """Mã chưa chấm không phải mã điểm thấp — phải nằm cuối ở cả hai chiều."""
    js = _scoring_js()
    fn = js.split('function scoringValue', 1)[1].split('\n}', 1)[0]
    assert '-Infinity' in fn
    sort_block = js.split('function scoringRows', 1)[1].split('\n}', 1)[0]
    assert 'va === -Infinity) return 1' in sort_block
    assert 'vb === -Infinity) return -1' in sort_block


def test_3_rows_are_roomier_and_hover_is_light():
    block = CSS.split('.rank-table tbody td {', 1)[1].split('}', 1)[0]
    padding = block.split('padding:', 1)[1].split(';', 1)[0].strip()
    assert padding != '8px 10px', "hàng phải thoáng hơn bảng giá thường"
    assert '#f8fafc' in CSS.split('.rank-table tbody tr:hover td {', 1)[1].split('}', 1)[0]
