"""Gộp mọi thông tin của MỘT chứng quyền vào một bản ghi, để trang chi tiết chỉ cần đọc.

Vì sao cần module này
---------------------
Trang chính hiện đọc bốn file khác nhau (snapshot thô, phân tích bảng giá, analytics, lịch
sử). Khi người dùng bấm một mã, trình duyệt sẽ phải tự ghép năm nguồn và tự đoán xem mã đó
vắng ở đâu thì vì lý do gì. Ghép ở Python thì:

* lý do vắng mặt là **lý do thật** do engine trả về (``excluded``), không phải suy đoán;
* trang chỉ phải tải một file nhỏ (~1 MB) chứ không phải toàn bộ 482 KB analytics cộng
  thêm lần đọc nữa khi bấm;
* mọi con số đều đi qua đúng một chỗ, nên không có chuyện trang hiển thị "IV = —" trong khi
  analytics có IV.

Nguyên tắc: **không suy diễn**. Mã không có trong ``valuation.warrants`` thì ``valuation`` là
``None`` kèm ``valuationBlockedBy``; mã không có trong ``stale.rows`` thì ``stale`` là ``None``.
Trường nào nguồn không có thì để ``null``, không điền 0 và không nội suy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

#: Trường thô của API Yuanta, giữ nguyên tên gốc để người đọc đối chiếu được với payload.
RAW_FIELDS: tuple[str, ...] = (
    "Exchange", "SymbolType", "RefP", "CeilingP", "FloorP", "OpenP", "HighestP",
    "LowestP", "AvgP", "LastMP", "LastMVol", "TotalVol", "TotalVal",
    "FTBuyVol", "FTSellVol", "FTBuyVal", "FTSellVal", "FRoom",
    "SymbolAdminStatusCode", "ExClassType",
    "S1P", "S1V", "S2P", "S2V", "S3P", "S3V",
    "B1P", "B1V", "B2P", "B2V", "B3P", "B3V",
)


def _num(value: Any) -> float | None:
    """Số hữu hạn, hoặc ``None``. Không đổi 0 thành None — 0 là giá trị thật."""
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def _json_safe(value: Any) -> Any:
    """Chuyển NaN/NaT của pandas thành ``None`` để ``json.dump`` không nổ."""
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (ValueError, AttributeError):
            return None
    return value


def _find(rows: Any, field: str, code: str) -> dict | None:
    """Tìm dòng có ``rows[i][field] == code``. Trả ``None`` nếu không có — không đoán."""
    if not rows:
        return None
    for row in rows:
        if isinstance(row, dict) and str(row.get(field) or "").upper() == code:
            return {key: _json_safe(val) for key, val in row.items()}
    return None


def valuation_block(valuation: dict | None, code: str) -> dict | None:
    """Khối Black–Scholes/Greeks của một mã, hoặc ``None`` nếu mã không được định giá."""
    if not valuation:
        return None
    return _find(valuation.get("warrants"), "ticker", code)


def blocked_reason(valuation: dict | None, code: str) -> str | None:
    """Vì sao mã không có khối định giá.

    Chỉ trả lời được khi nguồn cho biết lý do. Vì ``valuation.excluded`` là **đếm theo lý do**
    chứ không kèm danh sách mã, ta chỉ khẳng định được hai trường hợp chắc chắn:
    (1) phiên này không có bảng điều khoản, (2) mã có giá khớp lệnh nhưng không nằm trong danh
    sách đã định giá → bị loại vì một trong các lý do trong ``excluded``. Không gán bừa lý do
    cụ thể cho từng mã.
    """
    if not valuation:
        return "Chưa có lớp định giá trong analytics."
    if not valuation.get("available"):
        return valuation.get("reason") or "Lớp định giá không khả dụng ở phiên này."
    return None


def build_details(*, snapshot: dict | None, board_analysis: dict | None,
                  analytics: dict | None, history_bars: dict[str, list[dict]] | list[dict] | None = None,
                  history_meta: dict | None = None,
                  terms: Any = None,
                  session: str | None = None) -> dict:
    """Dựng ``{"rows": [...]}`` — mỗi phần tử là MỌI thông tin của một mã.

    Tham số đều là dữ liệu đã publish; hàm không đọc mạng và không đọc đĩa.

    ``terms`` là bảng điều khoản (tuỳ chọn). Khi có, ``issuer`` (tổ chức phát hành) được gắn
    vào từng dòng để bộ lọc trên trang có dữ liệu — bảng giá của nguồn không có trường này.
    Không có thì trường để ``None``, và bộ lọc tự ẩn thay vì hiện ô rỗng.
    """
    rows_in = (snapshot or {}).get("rows") or []
    if not rows_in:
        return {"schemaVersion": SCHEMA_VERSION, "kind": "yuanta_details",
                "available": False, "reason": "Snapshot rỗng — chưa có dữ liệu để dựng chi tiết.",
                "count": 0, "rows": []}

    # Chốt chặn: số dòng ra phải bằng số dòng vào. Một lần chạy từng ghi ra file chỉ 12/407
    # dòng mà không báo lỗi, khiến trang thiếu 395 mã định giá và bộ lọc chỉ còn 3 lựa chọn —
    # lỗi im lặng, không có gì đỏ. Thà dừng còn hơn publish file thiếu.
    snapshot_count = (snapshot or {}).get("count")
    if isinstance(snapshot_count, int) and snapshot_count != len(rows_in):
        raise ValueError(
            f"snapshot.count={snapshot_count} nhưng rows={len(rows_in)} — dữ liệu vào không "
            "nhất quán, không dựng chi tiết để tránh publish file thiếu.")


    valuation = (analytics or {}).get("valuation") or {}
    scoring = (analytics or {}).get("scoring") or {}
    stale = (analytics or {}).get("stale") or {}
    price_band = (analytics or {}).get("priceBand") or {}
    intraday = (analytics or {}).get("intraday") or {}
    last_trade = (analytics or {}).get("lastTrade") or {}
    continuity = (analytics or {}).get("refContinuity") or {}
    movers = (board_analysis or {}).get("movers") or {}

    # `analytics` có thể là None (chạy lần đầu, chưa có file) — mọi truy cập phải chịu được.
    analytics = analytics or {}
    coverage_by_ticker = {
        str(r.get("t") or "").upper(): r
        for r in analytics.get("tickerCoverage") or [] if isinstance(r, dict)
    }
    # Tổ chức phát hành: chỉ bảng điều khoản Vietstock có. Lấy đúng phiên nếu biết, ngược lại
    # lấy bản ghi mới nhất của mỗi mã. Không suy từ tên mã — mã CW không mã hoá tổ chức phát
    # hành, và đoán sai sẽ làm bộ lọc nói dối.
    #
    # Đọc qua `itertuples`/`columns` chứ không import pandas: module này cố ý không phụ thuộc
    # pandas để trang chi tiết chỉ cần dữ liệu đã publish.
    issuer_by_ticker: dict[str, str] = {}
    if terms is not None and len(terms) and "issuer" in set(getattr(terms, "columns", ())):
        frame = terms
        if session and "session" in set(frame.columns):
            same = frame[frame["session"].astype(str) == str(session)]
            if len(same):
                frame = same
        if "session" in set(frame.columns):
            frame = frame.sort_values("session")
        for row in frame.itertuples(index=False):
            code = str(getattr(row, "ticker", "") or "").strip().upper()
            name = getattr(row, "issuer", None)
            if code and name is not None and str(name).strip():
                issuer_by_ticker[code] = str(name).strip()
    # Lịch sử CW theo ngày. Nhận cả hai dạng: ``{mã: [bar, ...]}`` (đã gom sẵn, xem
    # ``choose_history_bars``) và danh sách bar phẳng có trường ``ticker``.
    bars: dict[str, list[dict]] = {}
    if isinstance(history_bars, dict):
        for code, series in history_bars.items():
            if isinstance(series, list):
                bars[str(code).upper()] = [
                    {k: _json_safe(v) for k, v in bar.items()}
                    for bar in series if isinstance(bar, dict)
                ]
    else:
        for bar in history_bars or []:
            if not isinstance(bar, dict):
                continue
            code = str(bar.get("ticker") or "").upper()
            if code:
                bars.setdefault(code, []).append({k: _json_safe(v) for k, v in bar.items()})
    for series in bars.values():
        series.sort(key=lambda b: str(b.get("session") or ""))

    out: list[dict] = []
    for raw in rows_in:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("StockCode") or "").strip().upper()
        if not code:
            continue

        moved = _find(movers.get("all"), "t", code)
        val = valuation_block(valuation, code)
        score = _find(scoring.get("ranking"), "t", code)
        under = _find(analytics.get("underlyings"), "underlying",
                      str((moved or {}).get("u") or "").upper())

        record = {
            "ticker": code,
            "underlying": (moved or {}).get("u"),
            "issuer": issuer_by_ticker.get(code),
            "raw": {field: _json_safe(raw.get(field)) for field in RAW_FIELDS},
            "market": moved,
            "valuation": val,
            "scoring": score,
            "stale": _find(stale.get("rows"), "t", code),
            "priceBand": _find(price_band.get("rows"), "t", code),
            "intraday": _find(intraday.get("rows"), "t", code),
            "lastTrade": _find(last_trade.get("rows"), "t", code),
            "refContinuity": _find(continuity.get("rows"), "t", code),
            "coverage": coverage_by_ticker.get(code),
            "underlyingStats": under,
            "history": bars.get(code) or [],
            # Chỉ ghi khi thực sự không định giá được; mã có giá thì để None.
            "valuationBlockedBy": None if val else blocked_reason(valuation, code),
        }
        out.append(record)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "yuanta_details",
        "source": (snapshot or {}).get("source"),
        "fetchedAt": (snapshot or {}).get("fetchedAt"),
        "session": (analytics or {}).get("asof"),
        "historyMeta": history_meta or {},
        "count": len(out),
        "rows": out,
    }


def choose_history_bars(sessions: dict | None) -> tuple[dict[str, list[dict]], dict]:
    """Chuyển ``yuanta_sessions.json`` thành ``{mã: [bar, ...]}`` theo từng phiên.

    Kho lịch sử lưu **mảng song song** (``dates``/``o``/``h``/``l``/``c``/``v``/``val``) cho gọn,
    không phải danh sách object. Hàm này đổi sang dạng bar để trang chi tiết chỉ việc đọc.

    ``c`` là ``null`` ở phiên không khớp lệnh — giữ nguyên ``None`` thay vì điền giá, để biểu
    đồ thể hiện khoảng trống thật.
    """
    if not sessions:
        return {}, {"available": False, "reason": "Chưa có file lịch sử."}
    coverage = sessions.get("coverage") or {}
    tickers = sessions.get("tickers") or {}
    bars: dict[str, list[dict]] = {}
    for code, series in tickers.items():
        if not isinstance(series, dict):
            continue
        dates = series.get("dates") or []
        if not dates:
            continue
        def column(key: str) -> list:
            values = series.get(key) or []
            return list(values) + [None] * (len(dates) - len(values))

        opens, highs, lows = column("o"), column("h"), column("l")
        closes, volumes, values, refs = column("c"), column("v"), column("val"), column("ref")
        bars[str(code).upper()] = [
            {
                "session": str(day),
                "open": _json_safe(opens[i]),
                "high": _json_safe(highs[i]),
                "low": _json_safe(lows[i]),
                "close": _json_safe(closes[i]),
                "volume": _json_safe(volumes[i]),
                "value": _json_safe(values[i]),
                "ref": _json_safe(refs[i]),
            }
            for i, day in enumerate(dates)
        ]
    meta = {
        "available": bool(bars),
        "coverage": coverage,
        "sessions": coverage.get("sessions"),
        "reason": None if bars else "Kho lịch sử chưa có bar nào.",
    }
    return bars, meta


def load_published(paths: dict[str, "Path"]) -> dict[str, dict | None]:
    """Đọc các file JSON đã publish. Thiếu hoặc hỏng thì trả ``None`` cho khoá đó.

    Trang chi tiết là tính năng **phụ trợ**: thiếu một file không được làm sập cả trang, nên
    lỗi được nuốt ở đây và ghi lại thành ``None`` để tầng trên tự nói rõ phần nào thiếu.
    """
    import json

    out: dict[str, dict | None] = {}
    for key, path in paths.items():
        try:
            out[key] = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out[key] = None
    return out
