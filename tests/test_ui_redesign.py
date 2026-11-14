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
    assert "el.closest('.filter').hidden = opts.length === 0" in HTML


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
    for term in ("ITM", "ATM", "OTM", "Black–Scholes", "IV", "HV", "Delta", "Theta",
                 "Vega", "Rho", "Strike", "Premium hoà vốn", "termsBasis",
                 "RefP", "Spread", "HHI", "Tích luỹ dần"):
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
def test_8_first_five_tabs_are_featured():
    tabs = re.findall(r'class="tab([^"]*)" data-view="(\w+)"', HTML)
    featured = [view for cls, view in tabs if "feature" in cls]
    assert featured == ["board", "scoring", "valuation", "liquidity", "underlyings"]
    assert ".tabs .tab.feature" in CSS


# ── 9. Emoji trước mọi mục ─────────────────────────────────────────────
def test_9_every_tab_has_an_emoji():
    icons = re.findall(r'<span class="t-ico" aria-hidden="true">([^<]+)</span>', HTML)
    views = re.findall(r'data-view="(\w+)"', HTML)
    assert len(icons) == len(views), "mỗi tab phải có đúng một emoji"
    assert all(i.strip() for i in icons)
    # Emoji là trang trí; nhãn chữ vẫn phải còn cho trình đọc màn hình.
    assert HTML.count('class="t-txt"') >= len(views)


# ── 10. Bảng thống kê toàn thị trường ở trang đầu ──────────────────────
def test_10_overview_section_exists_before_the_stats():
    assert 'id="overview"' in HTML
    assert "function renderOverview" in HTML
    # Phải đứng TRƯỚC #stats trong DOM để là thứ đầu tiên người xem thấy.
    assert HTML.index('id="overview"') < HTML.index('id="stats"')
    assert "Toàn cảnh thị trường chứng quyền" in HTML


def test_10_overview_omits_cards_whose_data_is_missing():
    """Không in số 0 giả: chỉ số nào không tính được thì bỏ hẳn ô đó."""
    block = HTML.split("function renderOverview", 1)[1].split("function renderStats", 1)[0]
    assert "if (priced)" in block
    assert "if (sum.medianIv !== undefined" in block
    assert "if (ivhv.available" in block
    assert "if (curve.available" in block


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
