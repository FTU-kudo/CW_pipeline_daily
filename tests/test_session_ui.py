"""Kiểm tra tĩnh cho phần hiển thị "độ mới dữ liệu" (phiên, không phải ngày).

Sự cố 04/11/2026: dashboard ghi "Phiên dữ liệu 03/11" trong khi phiên 04/11 đã
đóng, vì (a) pill đếm **ngày lịch** với ngưỡng 4 ngày, (b) nhãn "Phiên dữ liệu"
không phân biệt phiên cuối với phiên mong đợi, (c) hai workflow không nối nhau.
Các test dưới đây giữ nguyên ba điểm sửa đó ở phía UI/workflow.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
HTML = DOCS / "index.html"
APP = DOCS / "assets" / "app.js"
CSS = DOCS / "assets" / "app.css"
I18N = DOCS / "assets" / "i18n.js"
OVERVIEW = DOCS / "assets" / "pages" / "overview.js"
PIPELINE = ROOT / ".github" / "workflows" / "cw_pipeline.yml"
INTEL = ROOT / ".github" / "workflows" / "cw_intelligence.yml"


def test_sidebar_labels_latest_session_and_gap_row() -> None:
    html = HTML.read_text(encoding="utf-8")
    assert "Phiên dữ liệu cuối" in html
    assert 'id="sb-gap-row"' in html and 'id="sb-gap"' in html
    # dòng "Trễ" phải ẩn mặc định, chỉ hiện khi thiếu phiên
    assert re.search(r'class="mini-stat hidden"\s+id="sb-gap-row"', html)
    # disclaimer không còn nói "chậm 1 phiên" như thể là chuyện bình thường
    assert "có thể chậm 1 phiên" not in html


def test_app_counts_sessions_not_calendar_days() -> None:
    app = APP.read_text(encoding="utf-8")
    assert "meta.session" in app and "lagSessions" in app
    # pill cũ dùng ngày lịch — không được quay lại
    assert "Dữ liệu cách ${days} phiên" not in app
    assert "Thiếu ${lag} phiên" in app
    # banner phân hai mức: vàng (1 phiên) và đỏ (>= 2 phiên)
    assert "banner-warn" in app and "banner-danger" in app
    assert "expectedAsOfLabel" in app


def test_sessions_text_survives_i18n_both_mode() -> None:
    app = APP.read_text(encoding="utf-8")
    # chuỗi do JS sinh phải ghép VI · EN và được loại khỏi bộ dịch DOM
    assert "function tx(" in app and "getLang() === 'both'" in app
    assert "data-no-i18n" in app
    i18n = I18N.read_text(encoding="utf-8")
    assert '"Phiên dữ liệu cuối": "Latest data session"' in i18n
    # quy tắc cụm dài phải đứng trước cụm ngắn để không dịch sót chữ "cuối"
    long_idx = i18n.index("W('Phiên dữ liệu cuối'")
    short_idx = i18n.index("W('Phiên dữ liệu',")
    assert long_idx < short_idx


def test_banner_styles_exist_in_both_themes() -> None:
    css = CSS.read_text(encoding="utf-8")
    for cls in (".banner-warn", ".banner-danger", ".warn-text", ".mini-stat b.down"):
        assert cls in css, f"thiếu style {cls}"
    # dùng token màu, không hard-code mã màu để light/dark đều đọc được
    block = css[css.index(".banner-danger {"):css.index(".banner-danger {") + 400]
    assert "var(--down)" in block and "var(--surface)" in block


def test_overview_head_says_latest_session() -> None:
    src = OVERVIEW.read_text(encoding="utf-8")
    assert "Phiên dữ liệu cuối" in src


def test_github_workflow_is_offline_and_does_not_publish() -> None:
    pipe = PIPELINE.read_text(encoding="utf-8")
    assert "pytest -q" in pipe
    assert "workflow_dispatch:" in pipe
    assert "schedule:" not in pipe
    assert "secrets." not in pipe
    assert "VNSTOCK_SOURCE" not in pipe
    assert "upload-artifact" not in pipe
    assert "git push" not in pipe
    assert not INTEL.exists(), "old scheduled data-publishing workflow must stay removed"


def test_artifact_session_block_is_consistent() -> None:
    meta_path = DOCS / "data" / "meta.json"
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    ses = meta.get("session") or {}
    assert ses.get("asof") == meta["asof"]
    assert isinstance(ses.get("lagSessions"), int)
    assert meta.get("dataAgeSessions") == ses.get("lagSessions")
    assert meta.get("expectedAsOf") == ses.get("expected")
