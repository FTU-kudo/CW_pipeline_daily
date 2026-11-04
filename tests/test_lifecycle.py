"""Kiểm thử cơ chế vòng đời CW (niêm yết / đáo hạn / ngừng giao dịch).

Dùng master + panel tổng hợp để kiểm tra chính xác từng trạng thái, không phụ
thuộc dữ liệu thị trường thật.
"""

from __future__ import annotations

import pandas as pd
import pytest

from cwintel import lifecycle

ASOF = pd.Timestamp("2026-11-03")


def _master(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["last_trade"] = pd.NaT          # trường "phiên cuối theo kế hoạch" của Vietstock
    for col in ("maturity", "first_trade", "last_trade"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df["issuer_name"] = df.get("issuer", "X") + " Securities"
    return df


def _panel(pairs: list[tuple[str, str]], close: float = 100.0) -> pd.DataFrame:
    """Panel tối thiểu: chỉ cần (ticker, date) để biết lần khớp lệnh cuối."""
    df = pd.DataFrame(pairs, columns=["ticker", "date"])
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = close
    return df


@pytest.fixture()
def universe():
    master = _master([
        # còn hiệu lực & có khớp lệnh đúng phiên
        {"ticker": "AAA2601", "underlying": "AAA", "issuer": "SSI",
         "maturity": "2027-01-15", "first_trade": "2026-06-01"},
        # còn hiệu lực nhưng im lặng > 45 ngày → ngừng giao dịch sớm
        {"ticker": "BBB2602", "underlying": "BBB", "issuer": "SSI",
         "maturity": "2027-03-15", "first_trade": "2026-06-01"},
        # chờ niêm yết
        {"ticker": "CCC2603", "underlying": "CCC", "issuer": "VND",
         "maturity": "2027-06-15", "first_trade": "2026-12-01"},
        # vừa đáo hạn (3 ngày trước)
        {"ticker": "DDD2604", "underlying": "DDD", "issuer": "VND",
         "maturity": "2026-10-31", "first_trade": "2026-01-05"},
        # đáo hạn từ lâu
        {"ticker": "EEE2301", "underlying": "EEE", "issuer": "VND",
         "maturity": "2023-08-03", "first_trade": "2023-02-01"},
        # không có ngày đáo hạn
        {"ticker": "FFF2605", "underlying": "FFF", "issuer": "VND",
         "maturity": None, "first_trade": "2026-06-01"},
        # niêm yết mới trong cửa sổ 10 phiên
        {"ticker": "GGG2606", "underlying": "GGG", "issuer": "SSI",
         "maturity": "2027-02-15", "first_trade": "2026-10-30"},
        # sắp đáo hạn 30 ngày
        {"ticker": "HHH2607", "underlying": "HHH", "issuer": "SSI",
         "maturity": "2026-11-20", "first_trade": "2026-03-01"},
    ])
    panel = _panel([
        ("AAA2601", "2026-11-03"),
        ("BBB2602", "2026-09-10"),
        ("CCC2603", "2026-11-02"),   # có giá cũ nhưng chưa niêm yết theo điều khoản
        ("DDD2604", "2026-10-30"),
        ("EEE2301", "2023-08-01"),
        ("FFF2605", "2026-11-03"),
        ("GGG2606", "2026-11-03"),
        ("HHH2607", "2026-11-03"),
    ])
    return master, panel


def test_states_classified(universe):
    master, panel = universe
    cls = lifecycle.classify(master, ASOF, panel=panel).set_index("ticker")
    assert cls.loc["AAA2601", "state"] == "listed"
    assert cls.loc["BBB2602", "state"] == "delisted_early"
    assert cls.loc["CCC2603", "state"] == "pending"
    assert cls.loc["DDD2604", "state"] == "matured"
    assert cls.loc["EEE2301", "state"] == "matured"
    assert cls.loc["FFF2605", "state"] == "unknown"
    assert cls.loc["GGG2606", "state"] == "listed"
    assert cls.loc["HHH2607", "state"] == "listed"


def test_dte_rebased_to_asof(universe):
    master, panel = universe
    cls = lifecycle.classify(master, ASOF, panel=panel).set_index("ticker")
    assert cls.loc["HHH2607", "dte"] == 17          # 2026-11-20 − 2026-11-03
    assert cls.loc["DDD2604", "dte"] == -3          # đã đáo hạn 3 ngày
    assert cls.loc["EEE2301", "dte"] < -1100
    assert pd.isna(cls.loc["FFF2605", "dte"])


def test_traded_flag_and_days_since(universe):
    master, panel = universe
    cls = lifecycle.classify(master, ASOF, panel=panel).set_index("ticker")
    assert bool(cls.loc["AAA2601", "traded_on_asof"]) is True
    assert int(cls.loc["AAA2601", "days_since_print"]) == 0
    # BB im lặng 54 ngày
    assert int(cls.loc["BBB2602", "days_since_print"]) == 54
    # CCC có giá nhưng chưa niêm yết → không được coi là đã giao dịch
    assert bool(cls.loc["CCC2603", "traded_on_asof"]) is False


def test_counts_are_consistent_and_complete(universe):
    master, panel = universe
    cls = lifecycle.classify(master, ASOF, panel=panel)
    cnt = lifecycle.counts(cls)
    assert cnt["total"] == len(master)
    assert cnt["listed"] == 3                       # AAA, GGG, HHH (BBB ngừng GD, CCC chờ niêm yết)
    assert cnt["pending"] == 1
    assert cnt["matured"] == 2
    assert cnt["delistedEarly"] == 1
    assert cnt["unknown"] == 1
    assert cnt["traded"] == 3                       # AAA, GGG, HHH
    assert cnt["notTraded"] == cnt["listed"] - cnt["traded"]
    ident = lifecycle.identity(cnt)
    assert ident["ok"] is True and ident["gap"] == 0
    # tổng các trạng thái = tổng vũ trụ, không mã nào bị đếm hai lần
    assert sum(cnt[k] for k in ("listed", "pending", "matured", "delistedEarly", "unknown")) == cnt["total"]


def test_alive_tickers_excludes_expired(universe):
    master, _ = universe
    alive = lifecycle.alive_tickers(master, ASOF)
    assert "AAA2601" in alive and "HHH2607" in alive
    assert "DDD2604" not in alive and "EEE2301" not in alive   # đã đáo hạn
    assert "CCC2603" not in alive                              # chưa niêm yết
    assert "FFF2605" not in alive                              # thiếu ngày đáo hạn


def test_events_new_listing_and_recent_maturity(universe):
    master, panel = universe
    payload = lifecycle.payload(master, ASOF, panel=panel)
    assert payload["counts"]["newListings"] == 1
    assert payload["newListings"]["rows"][0]["t"] == "GGG2606"
    assert payload["recentMaturities"]["count"] == 1
    assert payload["recentMaturities"]["rows"][0]["t"] == "DDD2604"
    assert payload["upcoming"]["d30"]["count"] == 1
    assert payload["upcoming"]["d30"]["rows"][0]["t"] == "HHH2607"
    assert payload["earlyDelistings"]["rows"][0]["t"] == "BBB2602"
    assert payload["identity"]["ok"] is True


def test_calendar_rolls_listings_and_maturities():
    master = _master([
        {"ticker": "A1", "underlying": "A", "issuer": "X",
         "maturity": "2026-12-15", "first_trade": "2026-11-01"},
        {"ticker": "A2", "underlying": "A", "issuer": "X",
         "maturity": "2027-01-15", "first_trade": "2026-11-02"},
        {"ticker": "A3", "underlying": "A", "issuer": "X",
         "maturity": "2026-11-30", "first_trade": "2026-06-01"},
    ])
    panel = _panel([("A1", "2026-11-03"), ("A2", "2026-11-03"), ("A3", "2026-11-03")])
    payload = lifecycle.payload(master, ASOF, panel=panel, calendar_back=2, calendar_fwd=3)
    cal = {c["month"]: c for c in payload["calendar"]}
    assert cal["2026-11"]["listings"] == 2
    assert cal["2026-11"]["maturities"] == 1
    assert cal["2026-11"]["listedNow"] == 1
    assert cal["2026-12"]["maturities"] == 1
    assert cal["2026-11"]["isCurrent"] is True
    assert cal["2026-10"]["isPast"] is True
    assert cal["2027-01"]["maturities"] == 1


def test_empty_universe_is_safe():
    empty = pd.DataFrame(columns=["ticker", "underlying", "issuer", "maturity", "first_trade"])
    assert lifecycle.classify(empty, ASOF).empty
    payload = lifecycle.payload(empty, ASOF)
    assert payload["counts"]["total"] == 0
    assert payload["identity"]["ok"] is True
    assert lifecycle.alive_tickers(empty, ASOF) == set()


def test_number_crlf_robust():
    """Maturity trùng đúng phiên asof coi như đã đáo hạn (không còn DTE/T để chấm điểm)."""
    master = _master([{"ticker": "Z1", "underlying": "Z", "issuer": "X",
                       "maturity": "2026-11-03", "first_trade": "2026-05-01"}])
    panel = _panel([("Z1", "2026-11-03")])
    cls = lifecycle.classify(master, ASOF, panel=panel).iloc[0]
    assert cls["state"] == "matured"
    assert cls["dte"] == 0
    assert "Z1" not in lifecycle.alive_tickers(master, ASOF)
