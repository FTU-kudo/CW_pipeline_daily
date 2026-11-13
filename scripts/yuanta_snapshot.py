"""Yuanta EW price-board adapter.

Only the endpoint supplied by the project owner is used. Its payload is a current
board snapshot, not a daily historical OHLCV series. Numeric values are preserved
as returned; this adapter deliberately does not guess price/volume units.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

API_URL = (
    "https://ysradar.yuanta.com.vn/api/v3/market_data/price_board/stock/"
    "list_stock_info?stock_type=EW"
)
REQUIRED_ROW_FIELDS = ("StockCode", "Exchange", "SymbolType")


class YuantaPayloadError(ValueError):
    pass


def normalize_payload(payload: Any, *, fetched_at: datetime | None = None) -> dict:
    """Validate response envelope and wrap rows without dropping provider fields."""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise YuantaPayloadError("Yuanta response did not report success=true")
    rows = payload.get("response")
    if not isinstance(rows, list) or not rows:
        raise YuantaPayloadError("Yuanta response must contain a non-empty response list")

    clean_rows: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            raise YuantaPayloadError(f"response[{index}] is not an object")
        missing = [key for key in REQUIRED_ROW_FIELDS if key not in item]
        if missing:
            raise YuantaPayloadError(f"response[{index}] missing required fields: {missing}")
        ticker = str(item["StockCode"]).strip().upper()
        if not ticker:
            raise YuantaPayloadError(f"response[{index}] has empty StockCode")
        symbol_type = str(item["SymbolType"]).strip().upper()
        if symbol_type != "EW":
            raise YuantaPayloadError(
                f"response[{index}] has SymbolType={symbol_type!r}; expected EW"
            )
        if ticker in seen:
            raise YuantaPayloadError(f"duplicate StockCode in response: {ticker}")
        seen.add(ticker)
        # Shallow copy preserves all raw provider fields and exact units/values.
        row = dict(item)
        row["StockCode"] = ticker
        clean_rows.append(row)

    when = fetched_at or datetime.now(timezone.utc)
    if when.tzinfo is None:
        raise ValueError("fetched_at must be timezone-aware")
    return {
        "schemaVersion": 1,
        "source": "Yuanta YS Radar price board",
        "endpoint": API_URL,
        "stockType": "EW",
        "fetchedAt": when.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "historicalOhlcvAvailable": False,
        "dataGapNotice": (
            "Nguồn này cung cấp snapshot bảng giá EW hiện tại; không có chuỗi OHLCV "
            "ngày riêng từng CW. Không suy diễn lịch sử, backtest hoặc Greeks từ snapshot."
        ),
        "count": len(clean_rows),
        "fields": sorted({key for row in clean_rows for key in row}),
        "rows": clean_rows,
    }
