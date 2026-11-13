"""Kiểm thử tầng làm sạch/phân tích bảng giá Yuanta — hoàn toàn offline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from cwintel.yuanta_board import (
    BoardIntegrityError,
    build_board_artifact,
    clean_board,
    csv_ready,
    markdown_table,
    quality_checks,
    summarize,
    underlying_from_code,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "yuanta_ew_sample.json"
FETCHED = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)


def rows() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["response"]


@pytest.fixture()
def board() -> pd.DataFrame:
    return clean_board(rows(), fetched_at=FETCHED)


# ──────────────────────────────────────────────────────────────────
# LÀM SẠCH
# ──────────────────────────────────────────────────────────────────
def test_underlying_is_derived_from_ticker_convention():
    assert underlying_from_code("CACB2515") == "ACB"
    assert underlying_from_code("cstb2523") == "STB"
    assert underlying_from_code("CHPG2512") == "HPG"
    assert underlying_from_code("") is None
    assert underlying_from_code("FPT") is None          # cổ phiếu, không phải CW
    assert underlying_from_code("CACB") is None         # thiếu phần số


def test_clean_board_keeps_raw_fields_and_adds_derived(board: pd.DataFrame):
    assert len(board) == 12
    assert board["StockCode"].is_monotonic_increasing
    assert (board["SymbolType"] == "EW").all()
    # Trường gốc còn nguyên
    acb = board.loc[board["StockCode"] == "CACB2515"].iloc[0]
    assert acb["RefP"] == 170
    assert acb["AvgP"] == 156.78
    assert acb["B1V"] == 13000
    assert acb["FRoom"] == 9969900
    # Trường suy ra
    assert acb["Underlying"] == "ACB"
    assert acb["Traded"] is True or acb["Traded"] == True  # noqa: E712
    assert acb["LastPrice"] == 150
    assert acb["PriceChangePct"] == pytest.approx((150 - 170) / 170 * 100)
    assert acb["SpreadAbs"] == 10
    assert acb["SpreadTicks"] == 1
    assert acb["FetchedAt"].startswith("2026-11-13T10:00")


def test_null_numbers_become_nan_but_zero_stays_zero(board: pd.DataFrame):
    assert board["DeemP"].isna().all()
    assert board["DeemVol"].isna().all()
    assert (board["FTBuyVol"] == 0).all()          # 0 là số liệu, không phải thiếu
    assert board["FTBuyVol"].notna().all()


def test_untraded_row_gets_no_phantom_price(board: pd.DataFrame):
    row = board.loc[board["StockCode"] == "CVNM2526"].iloc[0]
    assert row["TotalVol"] == 0
    assert bool(row["Traded"]) is False
    # LastMP của phiên trước tồn tại nhưng KHÔNG được dùng làm giá hiện tại
    assert row["LastMP"] == 120
    assert pd.isna(row["LastPrice"])
    assert pd.isna(row["PriceChangePct"])
    assert pd.isna(row["TradingValueVND"])


def test_value_identity_is_reconciled_not_assumed(board: pd.DataFrame):
    """TotalVal ≈ TotalVol × AvgP trên toàn bộ snapshot → xác nhận đơn vị VND."""
    diff = board["TradingValueReconDiffPct"]
    assert diff.notna().all() or diff.dropna().gt(0).any()
    assert diff.max() < 0.5   # dung sai làm tròn AvgP
    traded = board["TradingValueVND"].dropna()
    assert traded.sum() == pytest.approx(board["TotalVal"].sum(), rel=0.005)


def test_quality_checks_flag_broken_rows_instead_of_fixing_silently():
    bad = clean_board(
        [
            {"StockCode": "CAAA2501", "Exchange": "HSX", "SymbolType": "EW",
             "RefP": 100, "FloorP": 500, "CeilingP": 900,      # RefP < FloorP
             "LowestP": 300, "HighestP": 200,                  # đảo high/low
             "OpenP": 150, "AvgP": 120, "LastMP": 110,
             "TotalVol": 3000, "TotalVal": 999999,             # không khớp identity
             "B1P": 0, "S1P": 0},
        ],
        fetched_at=FETCHED,
    )
    report = quality_checks(bad)
    by_id = {c["id"]: c for c in report["checks"]}
    assert report["status"] == "fail"
    assert by_id["ref_within_price_limits"]["status"] == "fail"
    assert by_id["low_below_high"]["status"] == "fail"
    assert by_id["value_identity"]["status"] == "fail"
    assert by_id["ref_price_positive"]["status"] == "ok"
    # Không sửa dữ liệu: giá trị gốc vẫn còn đó để người đọc tự thấy
    assert bad.iloc[0]["RefP"] == 100
    assert bad.iloc[0]["LowestP"] == 300


def test_quality_report_is_clean_on_the_sample_snapshot(board: pd.DataFrame):
    report = quality_checks(board)
    by_id = {c["id"]: c for c in report["checks"]}
    assert report["status"] in {"ok", "warn"}
    assert by_id["ref_within_price_limits"]["status"] == "ok"
    assert by_id["low_below_high"]["status"] == "ok"
    assert by_id["prices_inside_day_range"]["status"] == "ok"
    assert by_id["value_identity"]["status"] == "ok"
    assert by_id["untraded_rows"]["status"] == "ok"
    assert by_id["untraded_rows"]["amount"] == 1
    # Giá 50–150 VND với bước giá 10 VND khiến spread/hai giá lớn; đây là hiện tượng
    # thị trường thật nên chỉ cảnh báo, không fail.
    assert by_id["spread_within_regime"]["status"] == "warn"
    # Trường nước ngoài bằng 0 trên toàn bộ → nêu rõ là không có dữ liệu
    assert by_id["foreign_flow_absent"]["status"] == "ok"


def test_clean_board_rejects_duplicates_non_ew_and_empty():
    base = {"Exchange": "HSX", "SymbolType": "EW"}
    with pytest.raises(BoardIntegrityError, match="rỗng"):
        clean_board([])
    with pytest.raises(BoardIntegrityError, match="trùng"):
        clean_board([{**base, "StockCode": "CAAA2501"},
                     {**base, "StockCode": "caaa2501"}])
    with pytest.raises(BoardIntegrityError, match="khác EW"):
        clean_board([{**base, "StockCode": "FPT", "SymbolType": "STOCK"}])
    with pytest.raises(BoardIntegrityError, match="StockCode rỗng"):
        clean_board([{**base, "StockCode": "   "}])


def test_missing_optional_fields_do_not_crash():
    frame = clean_board([{"StockCode": "CAAA2501", "Exchange": "HSX", "SymbolType": "EW"}],
                        fetched_at=FETCHED)
    assert len(frame) == 1
    assert pd.isna(frame.iloc[0]["RefP"])
    assert bool(frame.iloc[0]["Traded"]) is False
    # Không có trường tuỳ chọn thì không có gì để fail; thiếu sổ lệnh chỉ là cảnh báo.
    report = quality_checks(frame)
    assert report["status"] == "warn"
    assert report["failed"] == 0
    assert {c["id"]: c for c in report["checks"]}["two_sided_depth"]["status"] == "warn"


# ──────────────────────────────────────────────────────────────────
# TỔNG HỢP
# ──────────────────────────────────────────────────────────────────
def test_summary_counts_only_traded_rows(board: pd.DataFrame):
    summary = summarize(board)
    assert summary["rows"] == 12
    assert summary["traded"] == 11
    assert summary["untraded"] == 1
    assert summary["underlyings"] == 6
    assert summary["totalValueVND"] == pytest.approx(board["TotalVal"].sum(), rel=0.005)
    assert summary["gainers"] + summary["losers"] + summary["unchanged"] == 11
    assert summary["medianSpreadTicks"] == 1


def test_artifact_is_json_safe_and_states_its_limits(board: pd.DataFrame):
    artifact = build_board_artifact(board, endpoint="https://example.invalid",
                                    fetched_at=FETCHED.isoformat(), snapshot_count=12)
    text = json.dumps(artifact, allow_nan=False, ensure_ascii=False)  # không NaN/Inf
    assert "NaN" not in text and "Infinity" not in text
    assert artifact["schemaVersion"] == 1
    assert artifact["summary"]["traded"] == 11
    assert artifact["source"]["rowsInSnapshot"] == 12
    assert artifact["quality"]["status"] in {"ok", "warn"}
    caveats = " ".join(artifact["caveats"])
    for phrase in ("không có", "Underlying suy ra", "Greeks"):
        assert phrase in caveats
    # Không có khuyến nghị/điểm số nào bị bịa ra từ một mặt cắt
    assert not {"recommendations", "scores", "greeks", "valuation"} & set(artifact)
    gainers = artifact["movers"]["gainers"]
    assert gainers and gainers[0]["StockCode"] == "CHPG2512"
    assert gainers[0]["PriceChangePct"] == pytest.approx(10.53, abs=0.01)
    assert "CVNM2526" not in {g["StockCode"] for g in gainers}   # không giao dịch
    by_und = {row["underlying"]: row for row in artifact["byUnderlying"]}
    assert by_und["HPG"]["warrants"] == 2
    assert sum(row["valueSharePct"] for row in by_und.values()) == pytest.approx(100, abs=0.1)


def test_markdown_table_escapes_pipes_and_formats_numbers(board: pd.DataFrame):
    table = markdown_table(board, ["StockCode", "TradingValueVND", "PriceChangePct"],
                           ["Mã", "GT", "%"], limit=3)
    lines = table.splitlines()
    assert len(lines) == 5
    assert lines[0] == "| Mã | GT | % |"
    assert lines[1] == "|---|---|---|"
    piped = pd.DataFrame({"StockCode": ["A|B"], "TradingValueVND": [1234.5],
                          "PriceChangePct": [1.23456]})
    out = markdown_table(piped, ["StockCode", "TradingValueVND", "PriceChangePct"])
    assert "A\\|B" in out
    assert "1,234.5" in out


def test_csv_ready_rounds_and_encodes_booleans(board: pd.DataFrame):
    ready = csv_ready(board)
    assert set(ready["Traded"].dropna().unique()) <= {0, 1}
    assert ready["PriceChangePct"].dropna().map(lambda v: round(v, 4) == v).all()
    assert ready["TradingValueVND"].dropna().map(lambda v: round(v, 2) == v).all()
    # Bản gốc không bị sửa
    assert board["PriceChangePct"].max() != round(board["PriceChangePct"].max(), 4)
