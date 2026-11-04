"""Kiểm thử lịch phiên & phát hiện dữ liệu chậm phiên (cwintel/sessions.py).

Bối cảnh: build từng phát hành "thành công" trên cache cũ, dashboard hiển thị
phiên 03/11 trong khi phiên 04/11 đã đóng. Các test dưới đây khoá lại quy tắc
"phiên đã đóng gần nhất" theo giờ Việt Nam và cách quy ra mức cảnh báo.
"""

from datetime import date, datetime, timezone, timedelta

import pytest

from cwintel import sessions

ICT = timezone(timedelta(hours=7))

# Bộ ngày nghỉ cố định dùng riêng trong test (không phụ thuộc config thật).
HOL = ("2026-09-02", "2026-04-30", "2026-05-01")


def ict(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=ICT)


# ── phiên đã đóng gần nhất ────────────────────────────────────────────────
def test_truoc_gio_dong_cua_thi_lay_phien_hom_truoc():
    assert sessions.last_closed_session(ict(2026, 11, 4, 9, 30)) == date(2026, 11, 3)


def test_sau_1510_thi_phien_hom_nay_da_dong():
    assert sessions.last_closed_session(ict(2026, 11, 4, 15, 9)) == date(2026, 11, 3)
    assert sessions.last_closed_session(ict(2026, 11, 4, 15, 10)) == date(2026, 11, 4)
    assert sessions.last_closed_session(ict(2026, 11, 4, 23, 59)) == date(2026, 11, 4)


def test_cuoi_tuan_lui_ve_thu_sau():
    # 07/11/2026 là Thứ Bảy, 08/11 là Chủ Nhật
    assert sessions.last_closed_session(ict(2026, 11, 7, 10, 0)) == date(2026, 11, 6)
    assert sessions.last_closed_session(ict(2026, 11, 8, 20, 0)) == date(2026, 11, 6)
    # Thứ Hai trước giờ đóng cửa → vẫn là Thứ Sáu
    assert sessions.last_closed_session(ict(2026, 11, 9, 8, 0)) == date(2026, 11, 6)


def test_ngay_le_bi_bo_qua():
    # 02/09/2026 (Quốc khánh) là Thứ Tư → lùi về 01/09
    assert sessions.last_closed_session(ict(2026, 9, 2, 18, 0), holidays=HOL) == date(2026, 9, 1)
    # 30/04 + 01/05 liền nhau → lùi về 29/04
    assert sessions.last_closed_session(ict(2026, 5, 1, 18, 0), holidays=HOL) == date(2026, 4, 29)


def test_holiday_set_doc_duoc_nhieu_dinh_dang():
    s = sessions.holiday_set(["2026-09-02", date(2026, 4, 30), datetime(2026, 5, 1, 0, 0)])
    assert date(2026, 9, 2) in s and date(2026, 4, 30) in s and date(2026, 5, 1) in s


def test_is_session_day():
    assert sessions.is_session_day(date(2026, 11, 4))          # Thứ Tư
    assert not sessions.is_session_day(date(2026, 11, 7))      # Thứ Bảy
    assert not sessions.is_session_day(date(2026, 9, 2), holidays=HOL)


# ── số phiên bị thiếu ─────────────────────────────────────────────────────
def test_sessions_between_khong_gom_moc_dau():
    got = sessions.sessions_between("2026-11-03", "2026-11-06")
    assert [d.isoformat() for d in got] == ["2026-11-04", "2026-11-05", "2026-11-06"]


def test_sessions_between_nhay_qua_cuoi_tuan():
    # 06/11 (Thứ Sáu) → 09/11 (Thứ Hai) chỉ có 1 phiên
    assert sessions.sessions_between("2026-11-06", "2026-11-09") == [date(2026, 11, 9)]


# ── session_status ───────────────────────────────────────────────────────
def test_status_ok_khi_du_lieu_toi_phien_moi_nhat():
    st = sessions.session_status("2026-11-04", now=ict(2026, 11, 4, 16, 30))
    assert st["lagSessions"] == 0 and st["status"] == "ok"
    assert st["expected"] == "2026-11-04" and st["expectedLabel"] == "04/11/2026"
    assert st["todayClosed"] is True and st["missing"] == []


def test_status_warn_khi_lech_mot_phien():
    st = sessions.session_status("2026-11-03", now=ict(2026, 11, 4, 16, 30))
    assert st["lagSessions"] == 1 and st["status"] == "warn"
    assert st["missing"] == ["2026-11-04"] and st["missingLabels"] == ["04/11/2026"]
    assert st["lagDays"] == 1


def test_status_stale_khi_lech_tu_hai_phien():
    st = sessions.session_status("2026-10-30", now=ict(2026, 11, 4, 16, 30))
    assert st["lagSessions"] == 3 and st["status"] == "stale"
    assert st["missing"] == ["2026-11-02", "2026-11-03", "2026-11-04"]
    assert st["lagDays"] == 5          # 3 phiên nhưng 5 ngày lịch: vì sao phải đếm phiên


def test_status_khong_am_khi_asof_tuong_lai():
    st = sessions.session_status("2026-11-05", now=ict(2026, 11, 4, 16, 30))
    assert st["lagSessions"] == 0 and st["status"] == "ok" and st["missing"] == []


def test_status_dung_gio_ict_du_may_chay_utc():
    # 09:00 UTC ngày 04/11 = 16:00 ICT → phiên 04/11 đã đóng
    now_utc = datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc)
    st = sessions.session_status("2026-11-03", now=now_utc)
    assert st["expected"] == "2026-11-04" and st["lagSessions"] == 1


# ── cấu hình thật & artifact phát hành ───────────────────────────────────
def test_config_co_market_holidays():
    from cwintel import config
    assert config.MARKET_HOLIDAYS, "config.MARKET_HOLIDAYS phải có ít nhất một ngày"
    assert all(isinstance(h, str) and len(h) == 10 for h in config.MARKET_HOLIDAYS)


def test_artifact_asof_bang_phien_da_dong_gan_nhat():
    """Artifact phát hành phải tới phiên đã đóng gần nhất (hoặc mới hơn)."""
    import json
    from pathlib import Path

    meta_path = Path("docs/data/meta.json")
    if not meta_path.exists():
        pytest.skip("chưa có artifact (chạy python -m cwintel.build)")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    expected = sessions.last_closed_session().isoformat()
    assert meta["asof"] >= expected, (
        f"artifact dừng ở {meta['asof']} nhưng phiên đã đóng gần nhất là {expected}")
    ses = meta.get("session") or {}
    assert ses.get("lagSessions") == 0, f"meta.session báo lệch phiên: {ses}"


def test_artifact_co_cong_chat_luong_session_lag():
    import json
    from pathlib import Path

    q_path = Path("docs/data/quality.json")
    if not q_path.exists():
        pytest.skip("chưa có artifact (chạy python -m cwintel.build)")
    checks = {c["id"]: c for c in json.loads(q_path.read_text(encoding="utf-8"))["checks"]}
    assert "session_lag" in checks, "artifact phải có cổng session_lag"
    gate = checks["session_lag"]
    assert gate["status"] in {"ok", "warn"}
    if gate["value"]["lagSessions"] == 0:
        assert gate["status"] == "ok"
