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


def test_workflow_build_artifact_truoc_khi_chay_test():
    """Freshness test phải chạy trên artifact vừa build, không phải bản cũ ở checkout."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/cw_intelligence.yml").read_text(encoding="utf-8")
    build = workflow.index("- name: Build artifacts")
    test = workflow.index("- name: Run test suite")
    assert build < test, "workflow phải build artifact mới trước khi pytest kiểm tra asof"


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


# ── lịch lễ thật của HOSE/HNX (config.MARKET_HOLIDAYS) ────────────────────
def test_lich_le_2026_khop_thong_bao_cua_so():
    """2026: HOSE công bố 13 phiên nghỉ (2294/TB-SGDHCM)."""
    from cwintel import config

    days = [d for d in config.MARKET_HOLIDAYS if d.startswith("2026-")]
    assert len(days) == 13, f"2026 phải có 13 phiên nghỉ, đang có {len(days)}"
    for d in ("2026-01-01", "2026-01-02", "2026-02-16", "2026-02-20",
              "2026-04-27", "2026-04-30", "2026-05-01",
              "2026-08-31", "2026-09-01", "2026-09-02"):
        assert d in days


def test_lich_le_2025_khop_thong_bao_cua_so():
    from cwintel import config

    days = [d for d in config.MARKET_HOLIDAYS if d.startswith("2025-")]
    assert len(days) == 12, f"2025 phải có 12 phiên nghỉ, đang có {len(days)}"


def test_lich_le_khong_co_ngay_cuoi_tuan_va_khong_trung_lap():
    from cwintel import config

    for d in config.MARKET_HOLIDAYS:
        day = date.fromisoformat(d)
        assert day.weekday() < 5, f"{d} là cuối tuần — không cần khai báo"
    assert len(set(config.MARKET_HOLIDAYS)) == len(config.MARKET_HOLIDAYS)


def test_tet_va_quoc_khanh_lui_ve_phien_truoc_ky_nghi():
    # 17/02/2026 (Tết) → phiên cuối là 13/02
    assert sessions.last_closed_session(ict(2026, 2, 17, 18)) == date(2026, 2, 13)
    # 02/09/2026 (Quốc khánh) → 28/08 (31/08–02/09 đều nghỉ)
    assert sessions.last_closed_session(ict(2026, 9, 2, 18)) == date(2026, 8, 28)
    # 27/04/2026 (Giỗ Tổ, nghỉ bù) → 24/04
    assert sessions.last_closed_session(ict(2026, 4, 27, 18)) == date(2026, 4, 24)


def test_ngay_nghi_lao_dong_chua_duoc_so_xac_nhan_khong_che_canh_bao():
    """24/11/2026 chưa có lịch nghỉ giao dịch của Sở → vẫn phải đòi dữ liệu."""
    from cwintel import config

    assert "2026-11-24" not in config.MARKET_HOLIDAYS
    st = sessions.session_status("2026-11-23", now=ict(2026, 11, 24, 16, 30))
    assert st["lagSessions"] == 1 and st["status"] == "warn"
    assert st["expected"] == "2026-11-24" and st["missing"] == ["2026-11-24"]


def test_lich_2027_du_kien_co_du_ngay_nghi_bu():
    from cwintel import config

    days = {d for d in config.MARKET_HOLIDAYS if d.startswith("2027-")}
    assert days == {
        "2027-01-01",
        "2027-02-04", "2027-02-05", "2027-02-08", "2027-02-09", "2027-02-10",
        "2027-04-16", "2027-04-30", "2027-05-03", "2027-09-02", "2027-09-03",
    }


def test_bo_lich_le_rieng_khong_anh_huong_config():
    # Truyền danh sách ngày lễ riêng vẫn hoạt động (dùng cho test/backtest lịch sử)
    st = sessions.session_status("2026-09-01", now=ict(2026, 9, 2, 18),
                                 holidays=("2026-09-02",))
    assert st["expected"] == "2026-09-01" and st["lagSessions"] == 0


def test_meta_phat_hanh_lich_le_cho_dong_ho():
    import json
    from pathlib import Path

    from cwintel import config

    meta_path = Path("docs/data/meta.json")
    if not meta_path.exists():
        pytest.skip("chưa có artifact")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta.get("marketHolidays") == sorted(config.MARKET_HOLIDAYS)
