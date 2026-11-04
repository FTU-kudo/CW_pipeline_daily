"""Lịch phiên giao dịch (HOSE/HNX) và phát hiện dữ liệu chậm phiên.

Vì sao cần module này
  Bản build chỉ biết `asof = phiên cuối cùng có trong cache`. Nếu pipeline nguồn
  chưa kịp cập nhật, build vẫn chạy "thành công" trên dữ liệu cũ và phát hành
  nguyên trạng — dashboard hiển thị "Phiên dữ liệu 03/11" trong khi hôm nay đã
  là 04/11 và phiên đã đóng cửa. Không có gì báo động.

  Module này tính **phiên đã đóng gần nhất** theo giờ Việt Nam rồi so với `asof`
  để biết đang thiếu bao nhiêu phiên. Kết quả được đưa vào `meta.session` và
  một kiểm tra chất lượng (`session_lag`) để build không thể "im lặng" nữa.

Quy ước
  * Giờ ICT (UTC+7), không dùng giờ máy chủ (GitHub Actions chạy UTC).
  * Phiên được coi là "đã đóng" sau 15:10 ICT (ATC kết thúc 14:45, đóng cửa
    15:00, chờ thêm 10 phút cho dữ liệu về).
  * Chỉ tính Thứ Hai–Thứ Sáu và trừ `config.MARKET_HOLIDAYS` (lịch HOSE/HNX,
    gồm cả Tết âm lịch; phần 2027 là dự kiến và được đánh dấu rõ trong config).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from . import config

ICT = timezone(timedelta(hours=7))

#: Sau mốc này thì phiên hôm nay được coi là đã đóng và dữ liệu phải có.
CLOSE_READY = time(15, 10)


def now_ict() -> datetime:
    return datetime.now(ICT)


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.astimezone(ICT).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)[:10]).date()


def holiday_set(holidays=None) -> set[date]:
    raw = config.MARKET_HOLIDAYS if holidays is None else holidays
    return {_as_date(h) for h in raw}


def is_session_day(day: date, holidays=None) -> bool:
    """Thứ Hai–Thứ Sáu, trừ ngày nghỉ đã biết."""
    return day.weekday() < 5 and day not in holiday_set(holidays)


def last_closed_session(now: datetime | None = None, holidays=None) -> date:
    """Phiên đã đóng gần nhất tính tới `now` (mặc định: bây giờ, giờ ICT)."""
    current = (now or now_ict()).astimezone(ICT)
    day = current.date()
    if day.weekday() < 5 and day not in holiday_set(holidays) and current.time() >= CLOSE_READY:
        return day
    day -= timedelta(days=1)
    for _ in range(30):                      # tối đa 30 ngày lùi (đủ cho dịp lễ dài)
        if is_session_day(day, holidays):
            return day
        day -= timedelta(days=1)
    return day


def sessions_between(start, end, holidays=None) -> list[date]:
    """Các phiên trong khoảng (start, end] — không gồm `start`."""
    first, last = _as_date(start), _as_date(end)
    out: list[date] = []
    day = first + timedelta(days=1)
    while day <= last:
        if is_session_day(day, holidays):
            out.append(day)
        day += timedelta(days=1)
    return out


def session_status(asof, now: datetime | None = None, holidays=None) -> dict:
    """So `asof` với phiên đã đóng gần nhất.

    Trả về dict sẵn sàng ghi vào `meta.json` và dùng cho kiểm tra chất lượng:

        asof / expected        : ngày (ISO) và nhãn dd/mm/yyyy
        lagSessions            : số phiên bị thiếu (0 = dữ liệu đã tới phiên mới nhất)
        lagDays                : số ngày lịch bị thiếu
        missing                : danh sách ngày còn thiếu (ISO)
        todayClosed            : phiên hôm nay đã đóng chưa
        status                 : 'ok' | 'warn' (thiếu 1 phiên) | 'stale' (thiếu ≥ 2 phiên)
    """
    current = (now or now_ict()).astimezone(ICT)
    asof_date = _as_date(asof)
    expected = last_closed_session(current, holidays)
    missing_dates = sessions_between(asof_date, expected, holidays) if asof_date < expected else []
    lag = len(missing_dates)
    today_closed = expected == current.date()
    status = "ok" if lag == 0 else ("warn" if lag == 1 else "stale")

    return {
        "asof": asof_date.isoformat(),
        "asofLabel": asof_date.strftime("%d/%m/%Y"),
        "expected": expected.isoformat(),
        "expectedLabel": expected.strftime("%d/%m/%Y"),
        "lagSessions": int(lag),
        "lagDays": int((expected - asof_date).days),
        "missing": [d.isoformat() for d in missing_dates],
        "missingLabels": [d.strftime("%d/%m/%Y") for d in missing_dates],
        "todayClosed": bool(today_closed),
        "checkedAt": current.strftime("%d/%m/%Y %H:%M +07:00"),
        "status": status,
    }
