"""Kiểm thử chấm điểm và xếp hạng CW — và kiểm thử rằng định giá bị KHOÁ đúng cách.

Điều quan trọng nhất ở đây không phải là con số điểm, mà là **danh sách biến còn thiếu**:
Black–Scholes cần S, K, T, n; endpoint chỉ trả bảng giá. Module phải nói ra điều đó bằng
một cấu trúc dữ liệu kiểm tra được, và không được lén tạo giá trị thay thế.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from cwintel.yuanta_board import clean_board
from cwintel.yuanta_scoring import (
    DEFAULT_WEIGHTS,
    HEADROOM_WARN_PCT,
    score_warrants,
    valuation_status,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "yuanta_ew_sample.json"


def _row(**over):
    base = {
        "StockCode": "CAAA2501", "Exchange": "HSX", "SymbolType": "EW",
        "RefP": 100, "CeilingP": 150, "FloorP": 50,
        "OpenP": 100, "HighestP": 110, "LowestP": 95, "AvgP": 102,
        "LastMP": 105, "LastMVol": 100, "TotalVol": 10_000, "TotalVal": 1_020_000,
        "B1P": 100, "S1P": 104,
    }
    base.update(over)
    return base


def _frame(rows, at="2026-11-13T10:30:00+00:00"):
    return clean_board(rows, fetched_at=datetime.fromisoformat(at))


# ──────────────────────────────────────────────────────────────────
# ĐỊNH GIÁ BỊ KHOÁ — VÀ NÓI ĐÚNG LÝ DO
# ──────────────────────────────────────────────────────────────────
def test_valuation_is_blocked_and_names_the_missing_inputs():
    status = valuation_status()
    assert status["available"] is False
    # Đủ bốn biến Black–Scholes, và đúng biến — không được thiếu biến nào trong danh sách
    assert set(status["blockedBy"]) == {
        "StrikePrice (K)", "MaturityDate (T)", "ConversionRatio (n)", "UnderlyingPrice (S)"}
    assert "strike" in status["reason"]
    assert "cwintel.bs" in status["engineReady"]
    assert "Black" in status["reason"]


def _walk_keys(node, path=""):
    """Duyệt mọi khoá trong payload (kể cả lồng trong list/dict)."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}.{key}"
            yield from _walk_keys(value, f"{path}.{key}")
    elif isinstance(node, list):
        for item in node:
            yield from _walk_keys(item, path)


def test_payload_has_no_valuation_fields_without_contract_terms():
    """Không được có TRƯỜNG SỐ nào cho IV/Greeks/giá lý thuyết.

    Chỉ kiểm tra khoá, không kiểm tra chữ: payload có nhắc "iv"/"delta" trong phần giải
    thích *vì sao chúng không tồn tại* — đó là điều phải có, không phải điều phải cấm.
    """
    result = score_warrants(_frame([_row()]))
    keys = {k.rsplit(".", 1)[-1].lower() for k in _walk_keys(result)}
    for forbidden in ("iv", "impliedvol", "ivpct", "delta", "deltaoption", "gamma", "theta",
                      "vega", "rho", "bsvalue", "fairvalue", "theoreticalprice", "premium",
                      "moneyness", "intrinsic"):
        assert forbidden not in keys, forbidden
    # Và danh sách khoá của một dòng xếp hạng chỉ gồm những gì đã cam kết
    row_keys = set(result["ranking"][0])
    assert row_keys <= {"rank", "t", "u", "score", "coveragePct", "price", "chgPct",
                        "valueVND", "spreadPct", "parts", "headroomPct", "nearCeiling", "tier"}
    assert set(result["ranking"][0]["parts"]) <= {"liquidity", "cost", "valuation",
                                                  "priceQuality", "consistency"}
    # Không có `priced` (chưa có điều khoản) → trục định giá KHÔNG được chấm
    assert result["ranking"][0]["parts"]["valuation"] is None
    assert result["valuation"]["available"] is False


def test_scoring_payload_says_valuation_is_unavailable():
    result = score_warrants(_frame([_row()]))
    assert result["valuation"]["available"] is False
    assert result["valuation"]["blockedBy"]


# ──────────────────────────────────────────────────────────────────
# CHẤM ĐIỂM
# ──────────────────────────────────────────────────────────────────
def test_only_traded_warrants_are_scored():
    frame = _frame([
        _row(StockCode="CAAA2501"),
        _row(StockCode="CBBB2502", TotalVol=0, TotalVal=0, AvgP=None, LastMP=None, LastMVol=0),
    ])
    result = score_warrants(frame)
    assert result["scored"] == 1
    assert result["unscored"] == 1
    assert [r["t"] for r in result["ranking"]] == ["CAAA2501"]


def test_liquid_tight_spread_beats_thin_wide_spread():
    frame = _frame([
        # Thanh khoản lớn, spread 1 bước trên giá 1000 → 1%
        _row(StockCode="CGOOD001", RefP=1000, LastMP=1000, CeilingP=1500, FloorP=500,
             AvgP=1000, TotalVol=100_000, TotalVal=100_000_000, LastMVol=1000,
             B1P=1000, S1P=1010),
        # Thanh khoản nhỏ, spread 20% quanh giá 100
        _row(StockCode="CBAD0002", RefP=100, LastMP=100, CeilingP=150, FloorP=50,
             AvgP=100, TotalVol=100, TotalVal=10_000, LastMVol=100, B1P=90, S1P=110),
    ])
    result = score_warrants(frame)
    best, worst = result["ranking"][0], result["ranking"][-1]
    assert best["t"] == "CGOOD001"
    assert best["score"] > worst["score"]
    assert best["parts"]["cost"] > worst["parts"]["cost"]
    assert best["parts"]["liquidity"] > worst["parts"]["liquidity"]


def test_single_trade_close_is_penalised_on_price_quality():
    """Giá đóng cửa do đúng một lệnh quyết định → chất lượng giá kém hơn."""
    frame = _frame([
        _row(StockCode="CDEEP001", TotalVol=10_000, LastMVol=100),   # 1% khối lượng
        _row(StockCode="CONE0002", TotalVol=1_000, LastMVol=1_000),  # 100% — 1 lệnh
    ])
    result = score_warrants(frame)
    by_ticker = {r["t"]: r for r in result["ranking"]}
    assert by_ticker["CDEEP001"]["parts"]["priceQuality"] > \
           by_ticker["CONE0002"]["parts"]["priceQuality"]
    assert by_ticker["CONE0002"]["parts"]["priceQuality"] == 0


def test_consistency_is_unscored_without_enough_history():
    frame = _frame([_row()])
    result = score_warrants(frame)
    assert result["consistency"]["available"] is False
    assert "Chưa có kho lịch sử" in result["consistency"]["reason"]
    # Không chấm trục đó, nhưng điểm vẫn có (coverage < 100%)
    assert result["ranking"][0]["parts"]["consistency"] is None
    # coverage = phần trọng số thực sự có dữ liệu. Không có định giá (20%) và không có lịch
    # sử (8%) → 72% trọng số được dùng. Đây là lý do coverage phải hiển thị: điểm này chỉ
    # dựa trên 72% trọng số, không phải 100%.
    assert result["ranking"][0]["coveragePct"] == pytest.approx(72.0)


def test_consistency_uses_history_when_available():
    # Cần ≥ CONSISTENCY_MIN_SESSIONS (5) phiên để tỷ lệ giao dịch có nghĩa.
    sessions = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"]
    history = pd.DataFrame({
        "session": sessions * 2,
        "ticker": ["CAAA2501"] * 5 + ["CBBB2502"] * 5,
        "traded": [True] * 5 + [True, False, False, False, False],
    })
    frame = _frame([_row(StockCode="CAAA2501"), _row(StockCode="CBBB2502")])
    result = score_warrants(frame, history=history)
    assert result["consistency"]["available"] is True
    by_ticker = {r["t"]: r for r in result["ranking"]}
    assert by_ticker["CAAA2501"]["parts"]["consistency"] == 100.0
    assert by_ticker["CBBB2502"]["parts"]["consistency"] == 20.0
    # Có lịch sử nhưng không có điều khoản → thiếu trục định giá 20%
    assert by_ticker["CAAA2501"]["coveragePct"] == pytest.approx(80.0)


def test_missing_part_does_not_penalise_the_score():
    """Mã thiếu spread không được bị cộng 0 điểm cho trục đó — phải tính lại trọng số."""
    frame = _frame([
        _row(StockCode="CNOSPREAD", B1P=0, S1P=0),   # không có độ sâu sổ lệnh
        _row(StockCode="CFULL0002"),
    ])
    result = score_warrants(frame)
    by_ticker = {r["t"]: r for r in result["ranking"]}
    assert by_ticker["CNOSPREAD"]["parts"]["cost"] is None
    assert by_ticker["CNOSPREAD"]["coveragePct"] < 100.0
    # Điểm của mã thiếu dữ liệu dựa trên 70% trọng số còn lại, không bị chia cho 100
    assert by_ticker["CNOSPREAD"]["score"] is not None


def test_weights_sum_to_one():
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)
    # headroom là cờ cảnh báo, không phải trục điểm
    assert "headroom" not in DEFAULT_WEIGHTS
    # valuation là trục thật, dùng khi có điều khoản hợp đồng
    assert DEFAULT_WEIGHTS["valuation"] == pytest.approx(0.20)


def test_near_ceiling_is_flagged_not_scored():
    frame = _frame([
        _row(StockCode="CATCEIL01", CeilingP=105, LastMP=105, HighestP=105, AvgP=105,
             TotalVol=1000, TotalVal=105_000, B1P=104, S1P=110),
        _row(StockCode="CFAR00002", CeilingP=500, LastMP=105),
    ])
    result = score_warrants(frame)
    by_ticker = {r["t"]: r for r in result["ranking"]}
    assert by_ticker["CATCEIL01"]["nearCeiling"] is True
    assert by_ticker["CFAR00002"]["nearCeiling"] is False
    assert HEADROOM_WARN_PCT == 10.0


# ──────────────────────────────────────────────────────────────────
# NHÓM THEO CƠ SỞ + TÍCH HỢP
# ──────────────────────────────────────────────────────────────────
def test_best_warrant_per_underlying():
    frame = _frame([
        _row(StockCode="CVPB2601", RefP=1000, LastMP=1000, AvgP=1000, TotalVol=50_000,
             TotalVal=50_000_000, LastMVol=500, CeilingP=1500, FloorP=500),
        _row(StockCode="CVPB2602", RefP=100, LastMP=100, AvgP=100, TotalVol=100,
             TotalVal=10_000, LastMVol=100, CeilingP=150, FloorP=50),
        _row(StockCode="CMWG2603", RefP=200, LastMP=200, AvgP=200, TotalVol=20_000,
             TotalVal=4_000_000, LastMVol=200, CeilingP=300, FloorP=100),
    ])
    result = score_warrants(frame)
    by_u = {g["u"]: g for g in result["byUnderlying"]}
    assert by_u["VPB"]["bestTicker"] == "CVPB2601"
    assert by_u["VPB"]["count"] == 2
    assert by_u["MWG"]["bestTicker"] == "CMWG2603"


def test_analytics_payload_includes_scoring():
    from cwintel.yuanta_analytics import build_analytics

    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))["response"]
    payload = build_analytics(_frame(rows), asof="2026-11-13")
    assert "scoring" in payload
    assert payload["scoring"]["valuation"]["available"] is False
    assert payload["scoring"]["weights"] == DEFAULT_WEIGHTS
    # Caveat phải nhắc cả hai: có điểm, và không có định giá
    caveats = " ".join(payload["caveats"])
    assert "Black" in caveats or "định giá" in caveats


def test_scoring_handles_empty_frame():
    with pytest.raises(ValueError):
        score_warrants(pd.DataFrame())
