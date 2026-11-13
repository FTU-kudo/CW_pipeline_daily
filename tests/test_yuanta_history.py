"""Kiểm thử kho OHLCV theo ngày dựng từ snapshot — offline, có fixture thật trong repo."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from cwintel import yuanta_history as h

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "yuanta_ew_sample.json"
REAL_SNAPSHOT = ROOT / "docs" / "data" / "yuanta_snapshot.json"
UTC = timezone.utc


def rows() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["response"]


def snap(iso: str) -> h.SnapshotSession:
    return h.resolve_session(iso)


# ──────────────────────────────────────────────────────────────────
# PHIÊN
# ──────────────────────────────────────────────────────────────────
def test_closed_market_snapshot_belongs_to_the_same_session():
    """17:30 ICT (10:30 UTC) → bar hoàn chỉnh của chính ngày đó."""
    s = snap("2026-11-13T10:30:00+00:00")
    assert s.session == date(2026, 11, 13)
    assert s.closed is True and s.provisional is False


def test_intraday_snapshot_is_provisional():
    """10:00 ICT (03:00 UTC) → cùng phiên nhưng dữ liệu chưa trọn."""
    s = snap("2026-11-13T03:00:00+00:00")
    assert s.session == date(2026, 11, 13)
    assert s.closed is False and s.provisional is True


def test_just_before_close_is_still_provisional():
    assert snap("2026-11-13T08:09:00+00:00").closed is False   # 15:09 ICT
    assert snap("2026-11-13T08:10:00+00:00").closed is True    # 15:10 ICT


def test_weekend_snapshot_maps_to_friday_without_being_closed():
    s = snap("2026-11-14T10:30:00+00:00")          # thứ Bảy
    assert s.session == date(2026, 11, 13)
    assert s.closed is False


def test_holiday_snapshot_maps_to_previous_session():
    # 2026-09-02 là ngày nghỉ Quốc khánh (config.MARKET_HOLIDAYS)
    s = snap("2026-09-02T10:30:00+00:00")
    assert s.session == date(2026, 8, 28)
    assert s.closed is False


def test_naive_timestamp_is_rejected():
    with pytest.raises(h.HistoryError, match="timezone"):
        h.resolve_session("2026-11-13T10:30:00")


def test_gap_detection_lists_missing_sessions_not_weekends():
    days = [date(2026, 11, 9), date(2026, 11, 13)]      # bỏ 10, 11, 12
    assert h.session_gaps(days) == ["2026-11-10", "2026-11-11", "2026-11-12"]
    assert h.session_gaps([date(2026, 11, 13)]) == []


# ──────────────────────────────────────────────────────────────────
# BAR TỪ SNAPSHOT
# ──────────────────────────────────────────────────────────────────
def test_traded_row_becomes_a_full_bar():
    bars = h.bars_from_rows(rows(), snap("2026-11-13T10:30:00+00:00"))
    row = bars.set_index("ticker").loc["CACB2515"]
    assert row["open"] == 160 and row["high"] == 160 and row["low"] == 150
    assert row["close"] == 150            # LastMP, không phải RefP
    assert row["ref"] == 170              # RefP lưu riêng
    assert row["volume"] == 17700
    assert bool(row["traded"]) is True
    assert bool(row["provisional"]) is False


def test_untraded_row_has_no_price_at_all():
    """Mã không khớp lệnh: close/OHL phải rỗng, RefP không được thay cho close."""
    bars = h.bars_from_rows(rows(), snap("2026-11-13T10:30:00+00:00"))
    row = bars.set_index("ticker").loc["CVNM2526"]
    assert pd.isna(row["close"])
    assert pd.isna(row["open"]) and pd.isna(row["high"]) and pd.isna(row["low"])
    assert row["volume"] == 0
    assert bool(row["traded"]) is False
    assert row["ref"] == 120              # vẫn giữ, nhưng ở cột riêng


def test_bars_keep_bid_ask_and_reject_duplicates():
    bars = h.bars_from_rows(rows(), snap("2026-11-13T10:30:00+00:00"))
    assert len(bars) == 12
    assert bars.set_index("ticker").loc["CACB2515", "b1"] == 150
    with pytest.raises(h.HistoryError, match="trùng"):
        h.bars_from_rows(rows() + rows()[:1], snap("2026-11-13T10:30:00+00:00"))
    with pytest.raises(h.HistoryError, match="không có dòng"):
        h.bars_from_rows([], snap("2026-11-13T10:30:00+00:00"))


# ──────────────────────────────────────────────────────────────────
# UPSERT
# ──────────────────────────────────────────────────────────────────
def test_upsert_is_idempotent(tmp_path):
    bars = h.bars_from_rows(rows(), snap("2026-11-13T10:30:00+00:00"))
    first = h.upsert_bars(tmp_path, bars)
    assert (first.added, first.updated, first.unchanged) == (12, 0, 0)
    second = h.upsert_bars(tmp_path, bars)
    assert (second.added, second.updated, second.unchanged) == (0, 0, 12)
    assert len(h.load_history(tmp_path)) == 12


def test_closed_bar_is_not_overwritten_by_a_provisional_one(tmp_path):
    """Chạy tay giữa phiên không được phá bar đã đóng của cùng phiên."""
    closed = h.bars_from_rows(rows(), snap("2026-11-13T10:30:00+00:00"))
    h.upsert_bars(tmp_path, closed)

    partial_rows = rows()
    partial_rows[0] = {**partial_rows[0], "LastMP": 100, "TotalVol": 10, "TotalVal": 1000}
    partial = h.bars_from_rows(partial_rows, snap("2026-11-13T03:00:00+00:00"))
    result = h.upsert_bars(tmp_path, partial)
    assert result.skipped_closed_protected == 12
    assert result.updated == 0

    kept = h.load_history(tmp_path).set_index("ticker").loc["CACB2515"]
    assert kept["close"] == 150 and float(kept["volume"]) == 17700


def test_provisional_bar_can_be_corrected_by_a_closed_one(tmp_path):
    early = h.bars_from_rows(rows(), snap("2026-11-13T03:00:00+00:00"))
    h.upsert_bars(tmp_path, early)
    result = h.upsert_bars(tmp_path, h.bars_from_rows(rows(), snap("2026-11-13T10:30:00+00:00")))
    assert result.updated == 12
    hist = h.load_history(tmp_path)
    assert not hist["provisional"].any()
    assert hist.set_index("ticker").loc["CACB2515", "close"] == 150


def test_months_are_sharded_and_merged(tmp_path):
    for day in ("2026-11-12T10:30:00+00:00", "2026-11-13T10:30:00+00:00",
                "2026-12-01T10:30:00+00:00"):
        h.upsert_bars(tmp_path, h.bars_from_rows(rows(), snap(day)))
    shards = sorted(p.name for p in tmp_path.glob("*.csv"))
    assert shards == ["2026-11.csv", "2026-12.csv"]
    hist = h.load_history(tmp_path)
    assert hist["session"].nunique() == 3
    assert len(hist) == 36


def test_upsert_rejects_mixed_sessions(tmp_path):
    a = h.bars_from_rows(rows(), snap("2026-11-13T10:30:00+00:00"))
    b = h.bars_from_rows(rows(), snap("2026-11-12T10:30:00+00:00"))
    with pytest.raises(h.HistoryError, match="một phiên"):
        h.upsert_bars(tmp_path, pd.concat([a, b], ignore_index=True))


def test_empty_store_loads_with_schema(tmp_path):
    empty = h.load_history(tmp_path)
    assert empty.empty
    assert list(empty.columns) == list(h.COLUMNS)


# ──────────────────────────────────────────────────────────────────
# ĐỘ PHỦ / KHOẢNG TRỐNG
# ──────────────────────────────────────────────────────────────────
def test_coverage_names_missing_sessions(tmp_path):
    for day in ("2026-11-11T10:30:00+00:00", "2026-11-13T10:30:00+00:00"):
        h.upsert_bars(tmp_path, h.bars_from_rows(rows(), snap(day)))
    cov = h.coverage(h.load_history(tmp_path))
    assert cov["sessions"] == 2
    assert cov["missingSessions"] == ["2026-11-12"]
    assert cov["expectedSessions"] == 3
    assert cov["provisionalRows"] == 0
    assert cov["tradedSharePct"] == pytest.approx(11 / 12 * 100, abs=0.01)


def test_days_since_last_trade_counts_sessions(tmp_path):
    for day in ("2026-11-11T10:30:00+00:00", "2026-11-12T10:30:00+00:00",
                "2026-11-13T10:30:00+00:00"):
        bars = h.bars_from_rows(rows(), snap(day))
        if day.startswith("2026-11-13"):
            bars.loc[bars["ticker"] == "CACB2515", "traded"] = False
            bars.loc[bars["ticker"] == "CACB2515", "close"] = None
        h.upsert_bars(tmp_path, bars)
    hist = h.load_history(tmp_path)
    idle = h.days_since_last_trade(hist)
    assert idle["CACB2515"] == 1        # bỏ giao dịch phiên cuối
    assert idle["CHPG2512"] == 0        # vẫn giao dịch


def test_series_payload_keeps_nulls_for_untraded_sessions():
    hist = h.bars_from_rows(rows(), snap("2026-11-13T10:30:00+00:00"))
    series = h.series_payload(hist)
    cvn = series["CVNM2526"]
    assert cvn["c"] == [None]           # không bịa giá
    assert cvn["traded"] == [0]
    acb = series["CACB2515"]
    assert acb["c"] == [150.0] and acb["o"] == [160.0]


# ──────────────────────────────────────────────────────────────────
# CẦU NỐI CWINTEL
# ──────────────────────────────────────────────────────────────────
def test_cwintel_bridge_round_trips_units_to_vnd():
    """Cầu nối chia 1.000 vì cwintel.data._price_to_vnd nhân lại 1.000."""
    from cwintel.data import _canonical_ohlcv

    hist = h.bars_from_rows(rows(), snap("2026-11-13T10:30:00+00:00"))
    bridge = h.to_cwintel_ohlcv(hist)
    assert list(bridge.columns) == ["Ticker", "time", "open", "high", "low", "close", "volume"]
    assert bridge["time"].iloc[0] == "13/11/2026"
    canonical, _ = _canonical_ohlcv(bridge, "test")
    source = hist[hist["traded"]].set_index("ticker")
    first = canonical.set_index("ticker").loc["CACB2515"]
    assert first["close"] == pytest.approx(source.loc["CACB2515", "close"])
    assert first["low"] == pytest.approx(source.loc["CACB2515", "low"])


def test_cwintel_bridge_excludes_untraded_rows():
    hist = h.bars_from_rows(rows(), snap("2026-11-13T10:30:00+00:00"))
    bridge = h.to_cwintel_ohlcv(hist)
    assert len(bridge) == 11                      # 12 dòng, 1 mã không giao dịch
    assert "CVNM2526" not in set(bridge["Ticker"])
    assert bridge["close"].notna().all()


def test_cwintel_cache_file_is_readable(tmp_path):
    hist = h.bars_from_rows(rows(), snap("2026-11-13T10:30:00+00:00"))
    path = h.write_cwintel_cache(hist, tmp_path / "ohlcv.parquet")
    back = pd.read_parquet(path)
    assert len(back) == 11


# ──────────────────────────────────────────────────────────────────
# SNAPSHOT THẬT TRONG REPO (bỏ qua nếu workflow chưa từng chạy)
# ──────────────────────────────────────────────────────────────────
@pytest.mark.skipif(not REAL_SNAPSHOT.exists(), reason="chưa có snapshot thật trong repo")
def test_real_snapshot_round_trips_into_the_store(tmp_path):
    payload = json.loads(REAL_SNAPSHOT.read_text(encoding="utf-8"))
    session = h.resolve_session(payload["fetchedAt"])
    bars = h.bars_from_rows(payload["rows"], session)
    result = h.upsert_bars(tmp_path, bars)
    assert result.added == len(payload["rows"])
    hist = h.load_history(tmp_path)
    traded = hist[hist["traded"]]
    assert traded["close"].notna().all()
    assert hist.loc[~hist["traded"], "close"].isna().all()
    # Giá trị giao dịch tái lập được từ bar: volume × avg ≈ value
    check = traded[(traded["avg"] > 0)]
    ratio = (check["volume"] * check["avg"] / check["value"]).dropna()
    assert ratio.between(0.99, 1.01).mean() > 0.99
