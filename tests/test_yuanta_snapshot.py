from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.yuanta_snapshot import YuantaPayloadError, normalize_payload


def test_yuanta_payload_preserves_provider_fields_without_unit_conversion():
    payload = {
        "success": True,
        "response": [{
            "StockCode": "CACB2515",
            "Exchange": "HSX",
            "SymbolType": "EW",
            "RefP": 170,
            "CeilingP": 980,
            "FloorP": 10,
            "OpenP": 160,
            "HighestP": 160,
            "LowestP": 150,
            "AvgP": 156.78,
            "LastMP": 150,
            "LastMVol": 5000,
            "TotalVol": 17700,
            "TotalVal": 2775000,
            "FTBuyVol": 0,
            "FTSellVol": 0,
            "FTBuyVal": 0,
            "FTSellVal": 0,
            "FRoom": 9969900,
            "B1P": 150,
            "B1V": 13000,
            "S1P": 160,
            "S1V": 4800,
        }],
    }
    normalized = normalize_payload(
        payload, fetched_at=datetime(2026, 11, 4, 10, 30, tzinfo=timezone.utc)
    )
    row = normalized["rows"][0]
    assert normalized["count"] == 1
    assert normalized["historicalOhlcvAvailable"] is False
    assert row["StockCode"] == "CACB2515"
    assert row["LastMP"] == 150
    assert row["AvgP"] == 156.78
    assert row["TotalVal"] == 2775000
    assert row["B1V"] == 13000
    assert "OHLCV" in normalized["dataGapNotice"]


def test_yuanta_payload_rejects_failure_empty_rows_and_non_ew():
    with pytest.raises(YuantaPayloadError, match="success=true"):
        normalize_payload({"success": False, "response": []})
    with pytest.raises(YuantaPayloadError, match="non-empty"):
        normalize_payload({"success": True, "response": []})
    with pytest.raises(YuantaPayloadError, match="expected EW"):
        normalize_payload({"success": True, "response": [{
            "StockCode": "FPT", "Exchange": "HSX", "SymbolType": "STOCK",
        }]})


def test_yuanta_payload_requires_a_fetch_timestamp_timezone():
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_payload({"success": True, "response": [{
            "StockCode": "CW1", "Exchange": "HSX", "SymbolType": "EW",
        }]}, fetched_at=datetime(2026, 11, 4))


def test_fetch_payload_uses_browser_headers(monkeypatch):
    """Job publish từng fail vì gửi UA lạ và thiếu Referer → WAF trả HTML."""
    from scripts import fetch_yuanta_snapshot as script

    captured: dict = {}

    def fake_fetch_board(*, retries=3):
        captured["retries"] = retries
        return {"success": True, "response": [{
            "StockCode": "CACB2515", "Exchange": "HSX", "SymbolType": "EW",
            "RefP": 170, "AvgP": 156.78, "TotalVol": 17700, "TotalVal": 2775000,
        }]}

    monkeypatch.setattr(script, "fetch_board", fake_fetch_board)
    payload = script.fetch_payload()
    snapshot = normalize_payload(payload)
    assert captured == {"retries": 3}
    assert snapshot["count"] == 1


def test_snapshot_shape_is_accepted_by_the_analysis_layer():
    """Snapshot đã publish phải đọc lại được mà không gọi API lần hai."""
    from cwintel.yuanta_board import clean_board
    from scripts.analyze_yuanta_warrants import extract_rows

    snapshot = normalize_payload({"success": True, "response": [{
        "StockCode": "CACB2515", "Exchange": "HSX", "SymbolType": "EW",
        "RefP": 170, "AvgP": 156.78, "TotalVol": 17700, "TotalVal": 2775000,
        "B1P": 150, "S1P": 160,
    }]})
    frame = clean_board(extract_rows(snapshot))
    assert list(frame["StockCode"]) == ["CACB2515"]
    assert frame.iloc[0]["Underlying"] == "ACB"
