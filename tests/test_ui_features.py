"""Test cho 5 tính năng giao diện: sáng/tối, VI/EN, giờ cập nhật, đồng hồ, chi tiết mã.

Ba lớp được kiểm:

* ``cwintel/yuanta_detail.py`` — dữ liệu chi tiết ghép từ 5 nguồn (pytest thuần).
* ``tests/js/test_ui_*.mjs``     — chạy thật ``docs/assets/ui.js`` bằng Node, kiểm tra hành vi
  (đổi theme, dịch, đồng hồ theo giây) thay vì chỉ grep chuỗi.
* ``docs/index.html`` + workflow — kiểm tra tĩnh những thứ phải nối đúng chỗ.

Vì sao kiểm tra hành vi bằng Node: grep chuỗi không phát hiện được lỗi "có hàm nhưng không
gọi", "đổi ngôn ngữ nhưng chỉ dịch lần đầu", hay "đồng hồ tính giờ máy thay vì giờ VN".
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
HTML = (DOCS / "index.html").read_text(encoding="utf-8")
UI_JS = (DOCS / "assets" / "ui.js").read_text(encoding="utf-8")
DETAIL_JS = (DOCS / "assets" / "detail.js").read_text(encoding="utf-8")
UI_CSS = (DOCS / "assets" / "ui.css").read_text(encoding="utf-8")
PUBLISHER = (ROOT / ".github" / "workflows" / "cw_pipeline.yml").read_text(encoding="utf-8")

from cwintel import yuanta_detail  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# 1 & 2. Sáng/tối + Việt/Anh: công tắc phải có thật và nối đúng
# ─────────────────────────────────────────────────────────────────
def test_theme_switch_present_with_both_modes():
    assert 'data-theme-set="light"' in HTML
    assert 'data-theme-set="dark"' in HTML
    for token in ("--bg:", "--panel:", "--text:", "--muted:", "--up:", "--down:"):
        assert token in UI_CSS


def test_light_theme_is_not_a_hair_darker_dark_theme():
    """Sáng phải thật sáng: nền sáng, chữ tối. Đây là lỗi dễ mắc khi copy bảng màu."""
    # Khối light là khối khai báo đứng riêng; khối dark đầu tiên gộp chung với `:root`
    # nên phải tách riêng để đọc đúng.
    # Bỏ comment đầu file: nó cũng nhắc tới `html[data-theme="light"]`.
    css = UI_CSS[UI_CSS.index("*/"):]
    light = css[css.index('html[data-theme="light"] {'):]
    light = light[: light.index("}")]
    assert "--bg: #f4f6f8" in light, "nền light phải sáng"
    assert "--text: #0f1a24" in light, "chữ light phải tối"
    root = css[css.index(":root,"):]
    root = root[: root.index("}")]
    assert "--bg: #0b1118" in root, "nền dark phải tối"
    assert "--text: #e6edf5" in root, "chữ dark phải sáng"


def test_theme_persists_and_respects_system_preference():
    assert "localStorage.setItem('cwintel:theme'" in UI_JS
    assert "prefers-color-scheme: light" in UI_JS


def test_language_switch_present_and_persisted():
    assert 'data-lang-set="vi"' in HTML and 'data-lang-set="en"' in HTML
    assert "localStorage.setItem('cwintel:lang'" in UI_JS
    assert "window.dispatchEvent(new CustomEvent('cwintel:lang'" in UI_JS


def test_default_language_is_vietnamese():
    assert "let lang = 'vi'" in UI_JS
    assert "lang = saved === 'en' ? 'en' : 'vi'" in UI_JS


def test_translation_helper_never_invents_a_translation():
    """Chuỗi chưa có trong từ điển phải trả null để giữ nguyên tiếng Việt."""
    assert "return null;" in UI_JS
    assert "STRINGS[key]" in UI_JS


def test_i18n_retranslates_after_dynamic_render():
    """Nội dung do JS sinh phải được dịch lại — nếu chỉ dịch lúc tải trang thì đổi ngôn
    ngữ xong bảng vẫn tiếng Việt."""
    assert "MutationObserver" in UI_JS
    assert "applyI18n(document.body)" in HTML
    assert "addEventListener('cwintel:lang'" in HTML


def test_language_switch_keeps_current_tab():
    assert "currentView" in HTML
    assert "setView(currentView)" in HTML


# ─────────────────────────────────────────────────────────────────
# 3. Dữ liệu cập nhật lúc mấy giờ
# ─────────────────────────────────────────────────────────────────
def test_freshness_line_shows_absolute_time_and_age():
    assert 'id="freshness"' in HTML
    assert "function renderFreshness" in HTML
    assert "fetchedAt" in HTML
    # Độ trễ phải tính từ fetchedAt và tự nhích, không đóng băng lúc tải trang.
    assert "Date.now() - when.getTime()" in HTML
    assert "setInterval(renderFreshness" in HTML
    assert "Asia/Ho_Chi_Minh" in HTML


# ─────────────────────────────────────────────────────────────────
# 4. Đồng hồ theo giây
# ─────────────────────────────────────────────────────────────────
def test_clock_reads_time_every_second_without_accumulating():
    """Cộng dồn biến đếm sẽ trôi khi tab bị treo; phải đọc lại Date.now() mỗi nhịp."""
    assert "setInterval(tick, 1000)" in UI_JS
    assert "nowOf = typeof opts.now === 'function' ? opts.now : () => Date.now()" in UI_JS
    assert "visibilitychange" in UI_JS


def test_clock_is_timezone_independent():
    """Máy người xem ở múi giờ khác vẫn phải thấy giờ Việt Nam."""
    assert "timeZone: TZ" in UI_JS
    assert "export const TZ = 'Asia/Ho_Chi_Minh'" in UI_JS


def test_clock_marks_holidays_and_weekends():
    assert "isHoliday" in UI_JS and "isWeekend" in UI_JS
    assert "holiday" in UI_JS and "weekend" in UI_JS


def test_clock_elements_exist_in_html():
    for element in ("clock-time", "clock-date", "clock-session", "market-clock"):
        assert f'id="{element}"' in HTML


# ─────────────────────────────────────────────────────────────────
# 5. Chi tiết từng chứng quyền
# ─────────────────────────────────────────────────────────────────
def test_every_ticker_in_the_board_is_clickable():
    assert 'class="ticker-btn" data-ticker=' in HTML
    assert "openDetail(target.dataset.ticker)" in HTML


def test_detail_drawer_sections_are_all_wired():
    """Mọi khối định nghĩa đều phải được gọi trong renderBody — không khối mồ côi."""
    blocks = ["priceGrid", "bookGrid", "foreignGrid", "valuationSection", "scoringSection",
              "bandSection", "intradaySection", "historySection", "underlyingSection",
              "rawSection"]
    for block in blocks:
        assert f"function {block}(" in DETAIL_JS, f"thiếu khối {block}"
    body = DETAIL_JS[DETAIL_JS.index("function renderBody"):]
    for block in blocks:
        assert f"{block}(row)" in body, f"khối {block} không được gọi"


def test_detail_escapes_every_injected_value():
    assert "esc(" in DETAIL_JS
    # Không được nội suy trực tiếp giá trị thô vào HTML mà bỏ qua esc().
    # Giá trị do nguồn cung cấp phải đi qua esc() trước khi vào HTML.
    assert "esc(val.underlyingSource)" in DETAIL_JS
    assert "${val.strike}" not in DETAIL_JS
    assert "num(val.strike)" in DETAIL_JS


def test_detail_never_shows_zero_for_missing_data():
    """Thiếu dữ liệu phải là "—" kèm lý do, không phải 0."""
    assert "function dash(" in UI_JS
    assert "Không có dữ liệu" in UI_JS
    assert "Không giao dịch trong phiên" in DETAIL_JS


def test_detail_explains_when_valuation_is_unavailable():
    assert "valuationBlockedBy" in DETAIL_JS
    assert "No valuation block for this ticker" in DETAIL_JS


def test_detail_backdrop_starts_hidden():
    """Backdrop có position:fixed + inset:0 — nếu không ẩn từ đầu thì nó phủ tối cả trang.

    Đây chính là lỗi "một lớp mờ khi truy cập web": backdrop được tạo lúc khởi tạo nhưng
    không được đặt `hidden`, nên người dùng thấy toàn trang bị xám ngay khi vừa mở.
    """
    shell = DETAIL_JS[DETAIL_JS.index("function buildShell"):]
    shell = shell[: shell.index("function section")]
    assert "backdrop.hidden = true" in shell, "backdrop phải ẩn ngay khi tạo"
    # Phải ẩn TRƯỚC khi gắn vào body — nếu không sẽ có một khung hình bị phủ.
    create = shell[shell.index("backdrop.className"):]
    assert create.index("backdrop.hidden = true") < create.index("appendChild(backdrop)"), \
        "phải ẩn backdrop TRƯỚC khi gắn vào body, không thì một khung hình bị phủ"


def test_detail_panel_also_starts_hidden():
    """Ngăn kéo cũng position:fixed — hiện sẵn lúc tải sẽ che mất một dải bên phải."""
    shell = DETAIL_JS[DETAIL_JS.index("function buildShell"):]
    shell = shell[: shell.index("function section")]
    assert "panel.hidden = true" in shell
    assert shell.index("panel.hidden = true") < shell.index("appendChild(panel)"), \
        "phải ẩn panel TRƯỚC khi gắn vào body"


def test_detail_backdrop_toggles_with_the_drawer():
    open_fn = DETAIL_JS[DETAIL_JS.index("export function openDetail"):]
    open_fn = open_fn[: open_fn.index("export function closeDetail")]
    close_fn = DETAIL_JS[DETAIL_JS.index("export function closeDetail"):]
    close_fn = close_fn[: close_fn.index("function buildShell")]
    assert "backdrop.hidden = false" in open_fn, "mở ngăn kéo phải hiện backdrop"
    assert "backdrop.hidden = true" in close_fn, "đóng phải ẩn backdrop, nếu không trang bị mờ lại"


def test_detail_is_optional_and_never_breaks_the_board():
    """Thiếu file chi tiết thì bảng vẫn chạy — tính năng phụ không được làm sập trang."""
    assert "if (response.ok) details = await response.json();" in HTML
    assert "initDetail(details)" in HTML


def test_detail_drawer_is_appended_to_body_not_main():
    """`main` có max-width và padding: nếu ngăn kéo nằm trong đó, nó sẽ bị cắt ở
    position:fixed và hiện sai chỗ. Phải gắn trực tiếp vào <body>."""
    assert "document.body.appendChild(panel)" in DETAIL_JS
    assert "main.appendChild" not in DETAIL_JS


def test_detail_supports_deep_link_and_escape_key():
    assert "URLSearchParams(window.location.search).get('t')" in DETAIL_JS
    assert "searchParams.set('t'" in DETAIL_JS, "mở mã phải ghi mã vào URL để chia sẻ được"
    assert "event.key === 'Escape'" in DETAIL_JS


def test_detail_file_is_published_by_the_workflow():
    assert "docs/data/yuanta_details.json" in PUBLISHER


# ─────────────────────────────────────────────────────────────────
# Dữ liệu chi tiết (Python)
# ─────────────────────────────────────────────────────────────────
def _snapshot(rows):
    return {"schemaVersion": 1, "source": "test", "fetchedAt": "2026-11-13T10:00:00+00:00",
            "count": len(rows), "rows": rows}


def _raw(code, **over):
    base = {"StockCode": code, "Exchange": "HSX", "RefP": 170, "CeilingP": 980, "FloorP": 10,
            "OpenP": 160, "HighestP": 160, "LowestP": 150, "AvgP": 156.78, "LastMP": 150,
            "LastMVol": 5000, "TotalVol": 17700, "TotalVal": 2775000, "FTBuyVol": 0,
            "FTSellVol": 0, "FRoom": 9969900, "S1P": 160, "B1P": 150,
            "B2P": None, "B3P": None, "S2P": None, "S3P": None,
            "B1V": 13000, "S1V": 4800, "B2V": None, "S2V": None, "B3V": None, "S3V": None}
    base.update(over)
    return base


def test_build_details_covers_every_ticker():
    payload = yuanta_detail.build_details(
        snapshot=_snapshot([_raw("CAAA0001"), _raw("CBBB0002")]),
        board_analysis=None, analytics=None)
    assert payload["count"] == 2
    assert {row["ticker"] for row in payload["rows"]} == {"CAAA0001", "CBBB0002"}


def test_build_details_keeps_missing_blocks_as_none_not_empty_dict():
    payload = yuanta_detail.build_details(
        snapshot=_snapshot([_raw("CAAA0001")]), board_analysis=None, analytics=None)
    row = payload["rows"][0]
    for key in ("market", "valuation", "scoring", "stale", "priceBand", "history"):
        assert row[key] is None or row[key] == [], f"{key} phải là None/rỗng, không phải {{}}"


def test_build_details_merges_valuation_and_scoring():
    analytics = {
        "asof": "2026-11-13",
        "valuation": {"available": True, "warrants": [
            {"ticker": "CAAA0001", "iv": 42.5, "delta": 0.31, "hvShort": 20.0}]},
        "scoring": {"ranking": [{"t": "CAAA0001", "score": 88.0, "rank": 3}]},
    }
    row = yuanta_detail.build_details(
        snapshot=_snapshot([_raw("CAAA0001")]), board_analysis=None,
        analytics=analytics)["rows"][0]
    assert row["valuation"]["iv"] == 42.5
    assert row["scoring"]["score"] == 88.0
    assert row["valuationBlockedBy"] is None


def test_build_details_reports_why_valuation_is_missing():
    analytics = {"asof": "2026-11-13", "valuation": {"available": False,
                                                     "reason": "Chưa có bảng điều khoản."}}
    row = yuanta_detail.build_details(
        snapshot=_snapshot([_raw("CAAA0001")]), board_analysis=None,
        analytics=analytics)["rows"][0]
    assert row["valuation"] is None
    assert "điều khoản" in row["valuationBlockedBy"]


def test_build_details_history_is_grouped_by_ticker():
    bars = {"CAAA0001": [{"session": "2026-11-13", "close": 150.0}],
            "CBBB0002": []}
    payload = yuanta_detail.build_details(
        snapshot=_snapshot([_raw("CAAA0001"), _raw("CBBB0002")]),
        board_analysis=None, analytics=None, history_bars=bars)
    by_code = {row["ticker"]: row for row in payload["rows"]}
    assert len(by_code["CAAA0001"]["history"]) == 1
    assert by_code["CBBB0002"]["history"] == []


def test_build_details_accepts_flat_bar_list_too():
    bars = [{"ticker": "CAAA0001", "session": "2026-11-12", "close": 140.0},
            {"ticker": "CAAA0001", "session": "2026-11-13", "close": 150.0}]
    row = yuanta_detail.build_details(
        snapshot=_snapshot([_raw("CAAA0001")]), board_analysis=None,
        analytics=None, history_bars=bars)["rows"][0]
    assert [b["session"] for b in row["history"]] == ["2026-11-12", "2026-11-13"]


def test_build_details_of_empty_snapshot_is_unavailable_not_crash():
    payload = yuanta_detail.build_details(snapshot=None, board_analysis=None, analytics=None)
    assert payload["available"] is False
    assert payload["rows"] == []


def test_build_details_converts_nan_to_null_for_json():
    """NaN không phải JSON hợp lệ: json.dump sẽ nổ nếu để lọt."""
    row = yuanta_detail.build_details(
        snapshot=_snapshot([_raw("CAAA0001", AvgP=float("nan"))]),
        board_analysis=None, analytics=None)["rows"][0]
    assert row["raw"]["AvgP"] is None
    json.dumps(row)          # không được ném


def test_choose_history_bars_parses_parallel_arrays():
    sessions = {"coverage": {"sessions": 2}, "tickers": {"CAAA0001": {
        "dates": ["2026-11-12", "2026-11-13"], "o": [140, 150], "h": [145, 160],
        "l": [138, 148], "c": [144, 155], "v": [1000, 2000], "val": [1.4e5, 3.1e5],
        "ref": [140, 144]}}}
    bars, meta = yuanta_detail.choose_history_bars(sessions)
    assert meta["available"] is True
    assert len(bars["CAAA0001"]) == 2
    assert bars["CAAA0001"][1]["close"] == 155


def test_choose_history_bars_pads_short_columns_with_none():
    """Cột thiếu dữ liệu phải thành None, không được lệch chỉ số."""
    sessions = {"coverage": {}, "tickers": {"CAAA0001": {
        "dates": ["2026-11-12", "2026-11-13"], "c": [144]}}}
    bars, _ = yuanta_detail.choose_history_bars(sessions)
    assert bars["CAAA0001"][1]["close"] is None
    assert bars["CAAA0001"][1]["volume"] is None


def test_choose_history_bars_of_missing_file_is_unavailable():
    bars, meta = yuanta_detail.choose_history_bars(None)
    assert bars == {} and meta["available"] is False


def test_load_published_tolerates_missing_and_corrupt_files(tmp_path):
    good = tmp_path / "good.json"
    good.write_text('{"a": 1}', encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    out = yuanta_detail.load_published({"good": good, "bad": bad,
                                        "gone": tmp_path / "nope.json"})
    assert out["good"] == {"a": 1}
    assert out["bad"] is None and out["gone"] is None


# ─────────────────────────────────────────────────────────────────
# Chạy thật module JS bằng Node (nếu có Node)
# ─────────────────────────────────────────────────────────────────
@pytest.mark.skipif(shutil.which("node") is None, reason="cần Node để chạy JS")
def test_ui_module_behaviour_in_node(tmp_path):
    """Kiểm tra hành vi thật: theme đổi được, dịch đúng, đồng hồ theo giây và theo giờ VN."""
    site = tmp_path / "site"
    site.mkdir()
    assets = site / "assets"
    assets.mkdir()
    for name in ("ui.js", "detail.js", "ui.css"):
        shutil.copy(DOCS / "assets" / name, assets / name)

    script = tmp_path / "run.mjs"
    script.write_text(
        "globalThis.localStorage={_m:new Map(),getItem(k){return this._m.has(k)?this._m.get(k):null},"
        "setItem(k,v){this._m.set(k,String(v))}};\n"
        "globalThis.window={addEventListener(){},dispatchEvent(){return true},"
        "matchMedia:()=>({matches:false}),clearTimeout,setTimeout,location:{search:''},"
        "history:{replaceState(){}}};\n"
        "globalThis.location=globalThis.window.location;globalThis.history=globalThis.window.history;\n"
        "globalThis.document={documentElement:{dataset:{},lang:'vi'},body:{classList:{add(){},remove(){}},"
        "appendChild(){},querySelectorAll:()=>[]},querySelectorAll:()=>[],getElementById:()=>null,"
        "createTreeWalker:()=>({nextNode:()=>null}),addEventListener(){},hidden:false};\n"
        "globalThis.CustomEvent=class{constructor(t,o){this.type=t;this.detail=o&&o.detail}};\n"
        "globalThis.MutationObserver=class{observe(){}takeRecords(){return[]}};\n"
        f"const ui=await import('{(assets / 'ui.js').as_posix()}');\n"
        "const out={};\n"
        "out.translate=ui.translate('Bảng giá');\n"
        "out.unknown=ui.translate('chuỗi lạ hoàn toàn zzz');\n"
        "ui.setTheme('light');out.theme=document.documentElement.dataset.theme;\n"
        "out.saved=globalThis.localStorage.getItem('cwintel:theme');\n"
        "const t=Date.UTC(2026,10,13,3,25,30);\n"
        "const p=ui.clockParts(t);out.time=p.hhmmss;out.session=p.session;\n"
        "out.next=ui.clockParts(t+1000).hhmmss;\n"
        "out.weekend=ui.clockParts(Date.UTC(2026,10,14,3,0,0)).session;\n"
        "out.holiday=ui.clockParts(t,new Set(['2026-11-13'])).session;\n"
        "console.log(JSON.stringify(out));\n",
        encoding="utf-8")
    proc = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)

    assert out["translate"] == "Board"
    assert out["unknown"] is None, "chuỗi lạ phải trả null, không được tự dịch bừa"
    assert out["theme"] == "light" and out["saved"] == "light"
    # 03:25:30 UTC = 10:25:30 giờ Việt Nam, thứ Sáu, trong phiên khớp lệnh liên tục.
    assert out["time"] == "10:25:30"
    assert out["session"] == "open"
    assert out["next"] == "10:25:31", "đồng hồ phải nhích từng giây"
    assert out["weekend"] == "weekend"
    assert out["holiday"] == "holiday", "ngày lễ phải được nhận ra, không phải 'đang khớp lệnh'"
