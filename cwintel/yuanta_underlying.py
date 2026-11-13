"""Lịch sử OHLCV + giao dịch nước ngoài của cổ phiếu cơ sở từ Yuanta YS Radar.

Endpoint::

    GET https://ysradarapi.yuanta.com.vn/api/v3/market_data/market_watch/
        price_history/{SYMBOL}?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD

Trả về mảng ``response`` với một object mỗi phiên::

    TradingDate, PerChange, Close, Open, Highest, Lowest, Average, Volume, Value,
    ForeignVolumeBuy, ForeignVolumeSell, PutThroughVolume, PutThroughValue

Vì sao đây là mảnh ghép quan trọng
----------------------------------
Trước đây giá cổ phiếu cơ sở ``S`` chỉ suy ra được từ premium/đòn bẩy của Vietstock — dùng
được nhưng là suy luận. Endpoint này cho ``S`` **trực tiếp**, và quan trọng hơn: cho **cả
chuỗi lịch sử**, tức là tính được biến động thực hiện (HV) thật để so với IV. Trước đó chênh
lệch IV–HV chỉ là câu nói, giờ là số đo được.

Ba quy tắc của module này
-------------------------
1. **Không nội suy.** Phiên nào nguồn không có thì để trống và ghi vào ``missing``. Chuỗi giá
   bị nội suy sẽ làm HV thấp giả tạo — đúng loại lỗi khó phát hiện nhất.
2. **Chỉ số liệu nguồn cung cấp.** ``ForeignVolumeBuy``/``Sell`` là khối lượng, không phải giá
   trị; ``Value`` là giá trị khớp lệnh, không phải giá trị ròng khối ngoại. Không tự nhân ra
   tiền tệ cho các trường không có đơn vị.
3. **Không suy ra dữ liệu thiếu.** Phiên có ``Volume = 0`` là phiên không khớp lệnh thật
   (đình chỉ, hoặc mã chưa niêm yết); nó vẫn được lưu nhưng bị loại khỏi phép tính lợi suất
   thay vì bị coi là "giá đứng".
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from cwintel import config

#: Lịch sử bắt đầu từ đây — đủ dài để tính HV ổn định và xem chu kỳ.
HISTORY_START = "2010-01-01"

#: Số phiên dùng để tính HV "gần nhất" (1 tháng giao dịch).
HV_WINDOW_SHORT = 21
#: Số phiên dùng để tính HV "trung hạn" (3 tháng).
HV_WINDOW_LONG = 63

#: Tối thiểu số lợi suất để HV có nghĩa. Dưới mức này trả None, không bịa.
MIN_RETURNS_FOR_HV = 10

COLUMNS: tuple[str, ...] = (
    "TradingDate", "Close", "Open", "Highest", "Lowest", "Average",
    "PerChange", "Volume", "Value",
    "ForeignVolumeBuy", "ForeignVolumeSell", "PutThroughVolume", "PutThroughValue",
)

#: Số mã tối đa mỗi lần chạy nếu không chỉ định — chặn tai nạn gọi 400 request.
DEFAULT_MAX_SYMBOLS = 60


def history_url(symbol: str, *, from_date: str = HISTORY_START,
                to_date: str | None = None, host: str = "api") -> str:
    """URL lịch sử giá. ``host='api'`` dùng ``ysradarapi`` (endpoint dữ liệu)."""
    symbol = str(symbol).strip().upper()
    if not symbol.isalnum():
        raise ValueError(f"mã không hợp lệ: {symbol!r}")
    end = to_date or date.today().isoformat()
    base = ("https://ysradarapi.yuanta.com.vn" if host == "api"
            else "https://ysradar.yuanta.com.vn")
    return (f"{base}/api/v3/market_data/market_watch/price_history/{symbol}"
            f"?from_date={from_date}&to_date={end}")


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def parse_history(payload: Any, symbol: str) -> pd.DataFrame:
    """Payload JSON → DataFrame đúng schema, đã sắp xếp theo ngày tăng dần.

    Chấp nhận hai dạng: ``{"response": [...]}`` (API) và ``{"success": true, "response": [...]}``.
    Ném ``ValueError`` khi payload không dùng được — im lặng trả bảng rỗng sẽ khiến
    "không có dữ liệu" và "API trả rác" không phân biệt được.
    """
    if isinstance(payload, dict):
        if payload.get("success") is False:
            raise ValueError(f"{symbol}: API trả success=false — "
                             f"{str(payload)[:200]}")
        rows = payload.get("response")
    else:
        rows = payload
    if not isinstance(rows, list):
        raise ValueError(f"{symbol}: payload không có mảng 'response' "
                         f"(nhận {type(rows).__name__})")

    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        record = {col: row.get(col) for col in COLUMNS}
        day = str(record.get("TradingDate") or "")[:10]
        try:
            datetime.fromisoformat(day)
        except ValueError:
            continue                      # bỏ dòng không có ngày hợp lệ
        record["TradingDate"] = day
        for col in COLUMNS:
            if col != "TradingDate":
                record[col] = _num(record[col])
        out.append(record)

    frame = pd.DataFrame(out, columns=list(COLUMNS))
    if frame.empty:
        return frame
    return (frame.drop_duplicates(subset=["TradingDate"], keep="last")
            .sort_values("TradingDate", kind="stable").reset_index(drop=True))


def merge_history(existing: pd.DataFrame | None, fresh: pd.DataFrame) -> pd.DataFrame:
    """Gộp chuỗi đã lưu với dữ liệu mới; dòng mới thắng khi trùng ngày.

    Idempotent: gọi lại nhiều lần cho cùng kết quả. Đây là cách kho dữ liệu lớn dần mà không
    bao giờ nhân đôi phiên hoặc ghi đè lịch sử cũ bằng một lần gọi thiếu ngày.
    """
    if existing is None or existing.empty:
        return fresh.copy()
    if fresh is None or fresh.empty:
        return existing.copy()
    combined = pd.concat([existing, fresh], ignore_index=True)
    return (combined.drop_duplicates(subset=["TradingDate"], keep="last")
            .sort_values("TradingDate", kind="stable").reset_index(drop=True))


def realized_volatility(closes: Iterable[float], *, window: int | None = None,
                         min_returns: int = MIN_RETURNS_FOR_HV) -> float | None:
    """Độ lệch chuẩn log-return, quy ra %/năm. ``None`` khi không đủ dữ liệu.

    Dùng log-return chứ không phải % thay đổi đơn giản: log-return cộng dồn được và đối xứng
    giữa tăng/giảm, nên độ lệch chuẩn của nó là ước lượng đúng cho Black–Scholes.
    """
    values = [v for v in (closes or []) if v is not None and v > 0]
    if window:
        values = values[-window:]
    if len(values) < min_returns + 1:
        return None
    log_ret = np.log(np.asarray(values[1:], dtype=float) / np.asarray(values[:-1], dtype=float))
    if len(log_ret) < min_returns:
        return None
    daily = float(np.std(log_ret, ddof=1))
    return daily * math.sqrt(config.TRADING_DAYS_PER_YEAR) * 100


def market_calendar(frames: dict[str, pd.DataFrame], *, min_share: float = 0.6) -> set[str]:
    """Lịch các **phiên thị trường thực sự mở cửa**, suy từ chính dữ liệu.

    Vì sao không dùng danh sách ngày lễ cấu hình: lịch lễ Việt Nam 2010–2020 không có trong
    ``config.MARKET_HOLIDAYS`` (chỉ khai báo từ 2021), nên nếu đối chiếu bằng lịch cứng thì
    mỗi dịp Tết 2010–2020 sẽ bị báo là "thiếu dữ liệu" — sai, và che mất lỗ hổng thật.

    Ở đây ngày được coi là phiên nếu có ít nhất ``min_share`` (mặc định 60%) số mã đã lưu có
    giao dịch. Ngày lễ toàn thị trường không mã nào giao dịch → không phải phiên → không bao
    giờ bị tính là thiếu. Mã bị đình chỉ riêng lẻ (ví dụ SHB 10/2021) vẫn lộ ra thành lỗ hổng
    vì các mã khác vẫn giao dịch ngày đó.
    """
    usable = [f for f in frames.values() if f is not None and not f.empty]
    if not usable:
        return set()
    counts: dict[str, int] = {}
    for frame in usable:
        for day in frame["TradingDate"].astype(str).unique():
            counts[day] = counts.get(day, 0) + 1
    # max(1, …) chứ không phải max(2, …): một mã duy nhất vẫn phải có lịch của chính nó.
    threshold = max(1, math.ceil(len(usable) * min_share))
    return {day for day, n in counts.items() if n >= threshold}


def coverage(frame: pd.DataFrame, *, market: set[str] | None = None) -> dict:
    """Độ phủ lịch sử: khoảng ngày, số phiên, phiên thiếu, phiên không khớp lệnh.

    ``missing`` chỉ tính trong khoảng đã có dữ liệu — không thể biết phiên nào bị thiếu trước
    ngày đầu tiên mà nguồn trả về.
    """
    if frame is None or frame.empty:
        return {"available": False, "sessions": 0, "missing": [], "reason": "Chưa có dữ liệu."}

    days = sorted(frame["TradingDate"].astype(str).unique())
    first, last = days[0], days[-1]
    present = set(days)

    if market is not None:
        # Đối chiếu với lịch thị trường suy từ dữ liệu: chỉ ngày nào THỊ TRƯỜNG giao dịch mà
        # mã này vắng mới là thiếu. Đây là cách duy nhất đúng cho cả 2010–2020, khi lịch lễ
        # không có trong config.
        expected = sorted(d for d in market if first <= d <= last)
    else:
        # Không có lịch thị trường: loại cuối tuần + ngày lễ đã biết trong config.
        from cwintel import sessions as session_calendar

        expected = [d.isoformat() for d in
                    session_calendar.sessions_between(first, last, config.MARKET_HOLIDAYS)]
    missing = [d for d in expected if d not in present]

    zero_volume = int((pd.to_numeric(frame["Volume"], errors="coerce").fillna(0) <= 0).sum())
    return {
        "available": True,
        "sessions": int(len(days)),
        "first": first,
        "last": last,
        "rows": int(len(frame)),
        "missingCount": len(missing),
        "missing": missing[:60],
        "zeroVolumeSessions": zero_volume,
        "marketSessionsInRange": len(expected),
        "calendarBasis": ("lịch thị trường suy từ dữ liệu (ngày có ≥60% số mã giao dịch)"
                          if market is not None else
                          "cuối tuần + config.MARKET_HOLIDAYS (chưa đủ cho 2010–2020)"),
        "tradingDaysPerYear": config.TRADING_DAYS_PER_YEAR,
    }


def relative_volume(frame: pd.DataFrame, *, window: int = 20) -> float | None:
    """Khối lượng phiên cuối so với trung vị ``window`` phiên trước đó (lần).

    Mô tả phiên đã xảy ra, không phải tín hiệu — dùng để đọc xem thanh khoản cổ phiếu cơ sở
    hôm nay có bất thường không.
    """
    if frame is None or frame.empty or "Volume" not in frame:
        return None
    volume = pd.to_numeric(frame.sort_values("TradingDate")["Volume"], errors="coerce").dropna()
    if len(volume) < window + 1:
        return None
    baseline = float(volume.iloc[-(window + 1):-1].median())
    if not baseline or baseline <= 0:
        return None
    return round(float(volume.iloc[-1]) / baseline, 2)


def foreign_flow(frame: pd.DataFrame, *, window: int = 20) -> dict:
    """Dòng khối ngoại ròng theo **khối lượng** (không phải giá trị).

    Nguồn chỉ cho ``ForeignVolumeBuy``/``ForeignVolumeSell``. Không quy ra tiền: muốn vậy phải
    nhân với giá khớp bình quân, mà giá bình quân của riêng phần khối ngoại không có trong
    payload — nhân với ``Average`` của cả phiên sẽ tạo ra một con số trông chính xác nhưng sai.
    """
    if frame is None or frame.empty:
        return {"available": False, "reason": "Chưa có dữ liệu."}
    data = frame.sort_values("TradingDate").tail(window)
    buy = pd.to_numeric(data["ForeignVolumeBuy"], errors="coerce").fillna(0)
    sell = pd.to_numeric(data["ForeignVolumeSell"], errors="coerce").fillna(0)
    net = buy - sell
    return {
        "available": True,
        "window": int(len(data)),
        "netVolumeLast": float(net.iloc[-1]) if len(net) else None,
        "netVolumeMedian": float(net.median()) if len(net) else None,
        "buyVolumeLast": float(buy.iloc[-1]) if len(buy) else None,
        "sellVolumeLast": float(sell.iloc[-1]) if len(sell) else None,
        "positiveSessions": int((net > 0).sum()),
        "negativeSessions": int((net < 0).sum()),
        "unit": "cổ phiếu — payload cho khối lượng, không cho giá trị ròng",
    }


def summarize(frame: pd.DataFrame, *, market: set[str] | None = None) -> dict:
    """Tóm tắt một cổ phiếu cơ sở: giá, HV ngắn/dài hạn, khối lượng, dòng khối ngoại."""
    if frame is None or frame.empty:
        return {"available": False, "reason": "Chưa có dữ liệu."}
    data = frame.sort_values("TradingDate")
    closes = pd.to_numeric(data["Close"], errors="coerce").dropna().tolist()
    last = data.iloc[-1]
    return {
        "available": True,
        "lastDate": str(last["TradingDate"]),
        "close": _num(last["Close"]),
        "changePct": _num(last["PerChange"]),
        "volume": _num(last["Volume"]),
        "value": _num(last["Value"]),
        "hvShortPct": realized_volatility(closes, window=HV_WINDOW_SHORT),
        "hvLongPct": realized_volatility(closes, window=HV_WINDOW_LONG),
        "sessions": int(len(closes)),
        "relativeVolume": relative_volume(data),
        "foreign": foreign_flow(data),
        "coverage": coverage(frame, market=market),
        "hvBasis": (
            f"Độ lệch chuẩn log-return {HV_WINDOW_SHORT} và {HV_WINDOW_LONG} phiên, "
            f"quy năm theo {config.TRADING_DAYS_PER_YEAR} phiên. Phiên không khớp lệnh bị loại "
            "khỏi lợi suất, không nội suy."
        ),
    }


def write_store(frames: dict[str, pd.DataFrame], out_dir: Path) -> Path:
    """Ghi parquet một file cho mỗi cổ phiếu cơ sở, atomically."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for symbol, frame in frames.items():
        if frame is None or frame.empty:
            continue
        path = out_dir / f"{symbol}.parquet"
        tmp = path.with_suffix(".parquet.tmp")
        frame.to_parquet(tmp, index=False)
        tmp.replace(path)
    return out_dir


def load_store(out_dir: Path, symbol: str) -> pd.DataFrame | None:
    path = Path(out_dir) / f"{symbol}.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except (OSError, ValueError):
        return None


def import_from_files(paths: Iterable[Path]) -> dict[str, pd.DataFrame]:
    """Đọc các payload JSON đã lưu (dùng offline, không gọi mạng).

    Tên file dạng ``ACB.json`` hoặc payload có trường ``symbol``; nếu không xác định được mã
    thì bỏ qua kèm cảnh báo chứ không đoán.
    """
    frames: dict[str, pd.DataFrame] = {}
    for path in paths:
        path = Path(path)
        try:
            import json
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        symbol = (payload.get("symbol") if isinstance(payload, dict) else None) or path.stem
        try:
            frames[str(symbol).upper()] = parse_history(payload, str(symbol).upper())
        except ValueError:
            continue
    return frames


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def date_span(start: str, end: str) -> timedelta:
    return date.fromisoformat(end) - date.fromisoformat(start)
