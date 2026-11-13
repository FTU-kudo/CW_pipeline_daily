"""Lịch sử OHLCV theo ngày cho từng chứng quyền — dựng từ snapshot bảng giá Yuanta.

Vì sao làm được (và không làm được gì)
--------------------------------------
Mỗi ngày workflow chụp bảng giá EW một lần. Nếu lần chụp xảy ra **sau khi phiên đóng**
(≥ 15:10 ICT, cron hiện tại là 17:30), payload chứa đúng bar của phiên đó cho từng mã:
``OpenP`` (giá khớp đầu), ``HighestP``/``LowestP``, ``LastMP`` (giá khớp cuối),
``TotalVol``, ``TotalVal``. Nối các lần chụp lại thành chuỗi ngày — không suy diễn gì thêm.

Ba giới hạn phải giữ, không được "làm đầy" cho đẹp:

1. **Không backfill.** Endpoint không có lịch sử. Ngày nào workflow không chạy (hoặc thất
   bại) là ngày đó **mất**, và được ghi vào danh sách ``gaps``. Không nội suy, không lặp
   giá phiên trước để lấp.
2. **Mã không giao dịch không có bar giá.** Khi ``TotalVol`` rỗng/0, nguồn trả
   ``OpenP/HighestP/LowestP/AvgP/LastMP = null`` và chỉ còn ``RefP`` — mà ``RefP`` là giá
   tham chiếu của **phiên trước**, không phải giá khớp hôm nay. Vì vậy bar được ghi với
   ``close = None``, ``traded = False``; ``RefP`` nằm ở cột riêng và không bao giờ được
   dùng làm close. Hệ quả: ``open/high/low/close`` chỉ có nghĩa ở các dòng ``traded``.
3. **Bar giữa phiên là ``provisional``.** Chạy tay lúc 10:00 sẽ có bar dở dang; nó được
   đánh dấu và **không** ghi đè bar đã đóng của cùng phiên, nhưng bar đã đóng thì ghi đè
   được bar provisional.

Kho dữ liệu
-----------
``data/cw_history/YYYY-MM.csv`` — shard theo tháng, commit vào Git để tích luỹ qua các
lần chạy CI (``output/`` bị ignore nên không dùng được cho việc này). Mỗi dòng là một
(ticker, phiên); ghi lại nhiều lần cho cùng một phiên là **idempotent** (upsert).

Đơn vị: giá VND/CW, khối lượng CW, giá trị VND — giữ nguyên như payload.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from . import config, sessions

ICT = timezone(timedelta(hours=7))
ROOT = Path(__file__).resolve().parents[1]
STORE_DIR = ROOT / "data" / "cw_history"

COLUMNS: tuple[str, ...] = (
    "session", "ticker", "exchange", "traded", "provisional",
    "ref", "open", "high", "low", "close", "avg", "last",
    "volume", "value", "b1", "s1", "fetchedAt",
)

#: Số phiên tối đa giữ trong payload công bố (file JSON của trang phân tích).
SERIES_LIMIT = 120


class HistoryError(ValueError):
    """Snapshot không dùng được để ghi lịch sử (thiếu trường, sai kiểu)."""


# ──────────────────────────────────────────────────────────────────
# PHIÊN
# ──────────────────────────────────────────────────────────────────
def _as_ict(value: datetime | str) -> datetime:
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        value = datetime.fromisoformat(text)
    if not isinstance(value, datetime):
        raise HistoryError(f"fetchedAt phải là datetime hoặc ISO string, nhận {type(value)!r}")
    if value.tzinfo is None:
        raise HistoryError("fetchedAt phải có timezone (payload ghi UTC)")
    return value.astimezone(ICT)


@dataclass(frozen=True)
class SnapshotSession:
    """Phiên mà một lần chụp đại diện."""

    session: date
    closed: bool          # True nếu chụp sau giờ đóng cửa của chính phiên đó
    fetched_at: datetime

    @property
    def iso(self) -> str:
        return self.session.isoformat()

    @property
    def provisional(self) -> bool:
        return not self.closed


def resolve_session(fetched_at: datetime | str, *, holidays=None,
                    close_ready: time | None = None) -> SnapshotSession:
    """Xác định phiên của một lần chụp bảng giá.

    * Chụp sau ``close_ready`` (mặc định 15:10 ICT) trong một phiên → bar của **ngày đó**,
      ``closed=True``.
    * Chụp trước giờ đóng (hoặc vào ngày nghỉ) → bar dở dang của ngày đó nếu là phiên,
      ngược lại thuộc phiên đã đóng gần nhất; ``closed=False`` khi dữ liệu chưa trọn phiên.
    """
    current = _as_ict(fetched_at)
    ready = close_ready or sessions.CLOSE_READY
    today = current.date()
    if sessions.is_session_day(today, holidays):
        if current.time() >= ready:
            return SnapshotSession(today, True, current)
        return SnapshotSession(today, False, current)
    # Ngày nghỉ: dữ liệu không đổi trong ngày, thuộc phiên đã đóng gần nhất.
    return SnapshotSession(sessions.last_closed_session(current, holidays), False, current)


def session_gaps(session_dates: Iterable[date], *, holidays=None) -> list[str]:
    """Các phiên bị thiếu giữa phiên đầu và phiên cuối có dữ liệu.

    ``sessions.sessions_between`` trả khoảng ``(start, end]`` — tức **gồm** phiên cuối,
    nên phải loại các ngày thực sự đã có dữ liệu; nếu không phiên mới nhất sẽ luôn bị báo
    thiếu.
    """
    days = sorted({d for d in session_dates})
    if len(days) < 2:
        return []
    present = set(days)
    return [d.isoformat() for d in sessions.sessions_between(days[0], days[-1], holidays)
            if d not in present]


# ──────────────────────────────────────────────────────────────────
# BAR TỪ SNAPSHOT
# ──────────────────────────────────────────────────────────────────
def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(out) else out


def bar_from_row(row: dict, snapshot: SnapshotSession) -> dict:
    """Một dòng snapshot → một bar ngày. Không bịa giá cho mã không giao dịch."""
    ticker = str(row.get("StockCode") or "").strip().upper()
    if not ticker:
        raise HistoryError("dòng snapshot thiếu StockCode")
    volume = _number(row.get("TotalVol"))
    last = _number(row.get("LastMP"))
    open_ = _number(row.get("OpenP"))
    high = _number(row.get("HighestP"))
    low = _number(row.get("LowestP"))
    traded = bool(volume and volume > 0 and last is not None and last > 0)
    return {
        "session": snapshot.iso,
        "ticker": ticker,
        "exchange": str(row.get("Exchange") or "").strip().upper() or None,
        "traded": traded,
        "provisional": snapshot.provisional,
        # Giá tham chiếu luôn được lưu nhưng KHÔNG phải close của phiên.
        "ref": _number(row.get("RefP")),
        "open": open_ if traded else None,
        "high": high if traded else None,
        "low": low if traded else None,
        "close": last if traded else None,
        "avg": _number(row.get("AvgP")) if traded else None,
        "last": last if traded else None,
        "volume": volume if traded else 0.0,
        "value": _number(row.get("TotalVal")) if traded else 0.0,
        "b1": _number(row.get("B1P")),
        "s1": _number(row.get("S1P")),
        "fetchedAt": snapshot.fetched_at.astimezone(timezone.utc).isoformat(timespec="seconds"),
    }


def bars_from_rows(rows: Iterable[dict], snapshot: SnapshotSession) -> pd.DataFrame:
    """Chuyển toàn bộ ``rows`` của snapshot thành DataFrame bar, kiểm tra trùng mã."""
    bars = [bar_from_row(row, snapshot) for row in rows]
    if not bars:
        raise HistoryError("snapshot không có dòng nào để ghi lịch sử")
    frame = pd.DataFrame(bars, columns=list(COLUMNS))
    dupes = frame.loc[frame["ticker"].duplicated(), "ticker"].unique().tolist()
    if dupes:
        raise HistoryError(f"StockCode trùng trong snapshot: {sorted(dupes)[:5]}")
    frame["traded"] = frame["traded"].astype(bool)
    frame["provisional"] = frame["provisional"].astype(bool)
    return frame.sort_values("ticker", kind="stable").reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────
# KHO DỮ LIỆU (CSV shard theo tháng)
# ──────────────────────────────────────────────────────────────────
def shard_path(store_dir: Path, session: str | date) -> Path:
    key = session.isoformat()[:7] if isinstance(session, date) else str(session)[:7]
    if len(key) != 7 or key[4] != "-":
        raise HistoryError(f"session phải là YYYY-MM-DD, nhận {session!r}")
    return Path(store_dir) / f"{key}.csv"


def load_history(store_dir: Path = STORE_DIR) -> pd.DataFrame:
    """Đọc toàn bộ shard; trả DataFrame rỗng đúng schema nếu chưa có dữ liệu."""
    store_dir = Path(store_dir)
    files = sorted(store_dir.glob("*.csv")) if store_dir.exists() else []
    if not files:
        empty = pd.DataFrame(columns=list(COLUMNS))
        empty["traded"] = empty["traded"].astype(bool)
        empty["provisional"] = empty["provisional"].astype(bool)
        return empty
    frames = [pd.read_csv(f, dtype={"session": str, "ticker": str}) for f in files]
    frame = pd.concat(frames, ignore_index=True)
    for col in COLUMNS:
        if col not in frame.columns:
            frame[col] = np.nan
    frame["traded"] = frame["traded"].fillna(False).astype(bool)
    frame["provisional"] = frame["provisional"].fillna(False).astype(bool)
    return frame[list(COLUMNS)].sort_values(["session", "ticker"], kind="stable") \
        .reset_index(drop=True)


def _write_shard(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = frame[list(COLUMNS)].copy()
    for col in ("open", "high", "low", "close", "avg", "last", "ref", "b1", "s1", "value"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(4)
    tmp = path.with_suffix(".csv.tmp")
    out.to_csv(tmp, index=False, encoding="utf-8", lineterminator="\n")
    tmp.replace(path)


@dataclass
class UpsertResult:
    session: str
    added: int
    updated: int
    unchanged: int
    skipped_closed_protected: int
    path: Path

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.skipped_closed_protected)


def upsert_bars(store_dir: Path, bars: pd.DataFrame) -> UpsertResult:
    """Ghi bar của **một** phiên vào shard tháng, idempotent theo (ticker, session).

    Quy tắc ưu tiên: bar đã đóng (``provisional=False``) không bị bar dở dang ghi đè.
    """
    if bars.empty:
        raise HistoryError("không có bar nào để ghi")
    sessions_in = bars["session"].unique().tolist()
    if len(sessions_in) != 1:
        raise HistoryError(f"upsert_bars chỉ nhận một phiên, nhận {sessions_in}")
    session = str(sessions_in[0])
    store_dir = Path(store_dir)
    path = shard_path(store_dir, session)
    existing = load_history(store_dir)
    same = existing[existing["session"] == session] if len(existing) else existing

    existing_by_ticker = ({r["ticker"]: r for _, r in same.iterrows()}
                          if len(same) else {})
    added = updated = unchanged = protected = 0
    new_rows: list[dict] = []
    for _, row in bars.iterrows():
        prior = existing_by_ticker.get(row["ticker"])
        if prior is None:
            added += 1
            new_rows.append(row.to_dict())
            continue
        if bool(prior["provisional"]) is False and bool(row["provisional"]) is True:
            # Không cho bar dở dang ghi đè bar đã đóng.
            protected += 1
            continue
        payload = row.to_dict()
        same_fields = all(
            (pd.isna(prior[c]) and pd.isna(payload[c]))
            or (not pd.isna(prior[c]) and not pd.isna(payload[c])
                and float(prior[c]) == float(payload[c]))
            for c in ("close", "open", "high", "low", "volume", "value", "traded",
                      "provisional")
        )
        if same_fields:
            unchanged += 1
            continue
        updated += 1
        new_rows.append(payload)

    if added or updated:
        others = existing[existing["session"] != session] if len(existing) else existing
        keep = same[same["ticker"].isin(
            set(same["ticker"]) - {r["ticker"] for r in new_rows}
        )] if len(same) else same
        merged = pd.concat([others, keep, pd.DataFrame(new_rows, columns=list(COLUMNS))],
                           ignore_index=True)
        merged = merged.sort_values(["session", "ticker"], kind="stable")
        # Chỉ ghi lại các shard bị ảnh hưởng.
        for month, chunk in merged.groupby(merged["session"].str[:7], sort=True):
            _write_shard(store_dir / f"{month}.csv", chunk)
    return UpsertResult(session=session, added=added, updated=updated,
                        unchanged=unchanged, skipped_closed_protected=protected, path=path)


# ──────────────────────────────────────────────────────────────────
# BÁO CÁO
# ──────────────────────────────────────────────────────────────────
def coverage(history: pd.DataFrame, *, holidays=None) -> dict:
    """Độ phủ dữ liệu: phiên có/thiếu, mã có/không có bar giá."""
    if history.empty:
        return {"sessions": 0, "tickers": 0, "first": None, "last": None,
                "missingSessions": [], "rows": 0, "tradedRows": 0, "tradedSharePct": None}
    dates = sorted(history["session"].unique())
    missing = session_gaps([date.fromisoformat(d) for d in dates], holidays=holidays)
    traded = history["traded"].astype(bool)
    return {
        "sessions": len(dates),
        "tickers": int(history["ticker"].nunique()),
        "first": dates[0],
        "last": dates[-1],
        "expectedSessions": len(dates) + len(missing),
        "missingSessions": missing,
        "rows": int(len(history)),
        "tradedRows": int(traded.sum()),
        "tradedSharePct": round(float(traded.mean() * 100), 2),
        "provisionalRows": int(history["provisional"].astype(bool).sum()),
    }


def per_session_summary(history: pd.DataFrame) -> list[dict]:
    """Tổng hợp theo phiên cho biểu đồ breadth (giá trị, số mã, tăng/giảm)."""
    out: list[dict] = []
    for session, group in history.groupby("session", sort=True):
        traded = group[group["traded"].astype(bool)]
        closes = traded["close"].dropna()
        refs = traded["ref"].dropna()
        change = ((closes / refs - 1) * 100).dropna() if len(closes) else pd.Series(dtype=float)
        out.append({
            "session": session,
            "tickers": int(len(group)),
            "traded": int(len(traded)),
            "valueVND": float(traded["value"].fillna(0).sum()),
            "volume": float(traded["volume"].fillna(0).sum()),
            "gainers": int((change > 0).sum()),
            "losers": int((change < 0).sum()),
            "unchanged": int((change == 0).sum()),
            "provisional": bool(group["provisional"].astype(bool).any()),
        })
    return out


def days_since_last_trade(history: pd.DataFrame, *, asof: str | date | None = None) -> dict[str, int | None]:
    """Số phiên kể từ lần cuối mã thực sự khớp lệnh (dùng cho giám sát mã "chết")."""
    if history.empty:
        return {}
    traded = history[history["traded"].astype(bool)]
    last = traded.groupby("ticker")["session"].max()
    dates = sorted(history["session"].unique())
    ref = str(asof) if asof is not None else dates[-1]
    calendar = [d for d in dates if d <= ref]
    position = {d: i for i, d in enumerate(calendar)}
    out: dict[str, int | None] = {}
    for ticker in history["ticker"].unique():
        seen = last.get(ticker)
        if seen is not None and seen in position:
            out[str(ticker)] = len(calendar) - 1 - position[seen]
        else:
            # Chưa từng khớp lệnh kể từ khi xuất hiện trong kho → chưa xác định, KHÔNG phải 0.
            out[str(ticker)] = None
    return out


def ticker_stats(history: pd.DataFrame, *, asof: str | date | None = None) -> dict[str, dict]:
    """Thống kê thanh khoản quan sát được của từng mã (chỉ trong cửa sổ có dữ liệu).

    Trả ``{ticker: {sessions, tradedSessions, coveragePct, idleNow, longestGap}}``.

    * ``coveragePct`` — % phiên mã thực sự khớp lệnh kể từ lần đầu xuất hiện. Mã mới niêm
      yết có coverage thấp một cách hợp lý, nên cần đọc cùng ``sessions``.
    * ``idleNow`` — số phiên im lặng tính tới ``asof``; ``None`` nếu chưa từng khớp lệnh.
    * ``longestGap`` — chuỗi phiên im lặng dài nhất trong cửa sổ.
    """
    if history.empty:
        return {}
    dates = sorted(history["session"].unique())
    ref = str(asof) if asof is not None else dates[-1]
    window = [d for d in dates if d <= ref]
    out: dict[str, dict] = {}
    for ticker, group in history.groupby("ticker", sort=False):
        seen = [d for d in group["session"].unique() if d in window]
        if not seen:
            continue
        traded = set(group.loc[group["traded"].astype(bool), "session"])
        traded_seen = [d for d in seen if d in traded]
        idle_now = None
        if traded_seen:
            last = max(traded_seen)
            idle_now = len([d for d in window if d > last])
        longest = run = 0
        for day in seen:
            run = 0 if day in traded else run + 1
            longest = max(longest, run)
        out[str(ticker)] = {
            "sessions": len(seen),
            "tradedSessions": len(traded_seen),
            "coveragePct": round(len(traded_seen) / len(seen) * 100, 1),
            "idleNow": idle_now,
            "longestGap": int(longest),
            "firstSeen": min(seen),
        }
    return out


def ticker_gaps(history: pd.DataFrame, *, holidays=None) -> dict[str, list[str]]:
    """Phiên bị thiếu riêng của từng mã (mã chưa niêm yết thì chỉ tính từ lần đầu xuất hiện)."""
    out: dict[str, list[str]] = {}
    if history.empty:
        return out
    for ticker, group in history.groupby("ticker", sort=False):
        days = [date.fromisoformat(d) for d in sorted(group["session"].unique())]
        gaps = session_gaps(days, holidays=holidays)
        if gaps:
            out[str(ticker)] = gaps
    return out


def series_payload(history: pd.DataFrame, *, limit: int = SERIES_LIMIT,
                   gaps: dict[str, list[str]] | None = None) -> dict[str, dict]:
    """Chuỗi gọn cho trang phân tích: một object/ticker, mảng song song theo phiên.

    ``c`` là ``null`` ở phiên không khớp lệnh — cố ý, để biểu đồ thể hiện khoảng trống
    thay vì vẽ một đường liền giả tạo.
    """
    out: dict[str, dict] = {}
    if history.empty:
        return out
    for ticker, group in history.groupby("ticker", sort=False):
        group = group.sort_values("session").tail(limit)
        out[str(ticker)] = {
            "ticker": str(ticker),
            "dates": [d for d in group["session"]],
            "o": [_clean(v) for v in group["open"]],
            "h": [_clean(v) for v in group["high"]],
            "l": [_clean(v) for v in group["low"]],
            "c": [_clean(v) for v in group["close"]],
            "v": [_clean(v) for v in group["volume"]],
            "val": [_clean(v) for v in group["value"]],
            "ref": [_clean(v) for v in group["ref"]],
            # RefP là giá đóng cửa phiên trước → % thay đổi có ngay từ phiên đầu tiên,
            # không cần chờ phiên thứ hai trong kho.
            "refChangePct": [
                None if (r is None or c is None or not r) else round((c / r - 1) * 100, 2)
                for r, c in zip((_clean(v) for v in group["ref"]),
                                (_clean(v) for v in group["close"]))
            ],
            "traded": [1 if t else 0 for t in group["traded"].astype(bool)],
            "provisional": [1 if t else 0 for t in group["provisional"].astype(bool)],
            "gaps": (gaps or {}).get(str(ticker), []),
        }
    return out


def _clean(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(out) else round(out, 2)


# ──────────────────────────────────────────────────────────────────
# CẦU NỐI SANG BỘ MÁY CWLINTEL (CW Analytics)
# ──────────────────────────────────────────────────────────────────
def to_cwintel_ohlcv(history: pd.DataFrame) -> pd.DataFrame:
    """Chuyển lịch sử sang schema cache ``cwintel`` (``Ticker/time/open/high/low/close/volume``).

    Hai điểm phải khớp với ``cwintel.data``:

    * ``time`` dạng ``dd/mm/yyyy`` (định dạng chuẩn của pipeline);
    * giá theo **nghìn VND** — ``cwintel.data._price_to_vnd`` nhân 1.000 khi median ≤ 1.000,
      nên phải chia 1.000 ở đây, nếu không giá sẽ bị nhân sai.

    Chỉ xuất các dòng ``traded`` (có OHLC thật). Dòng không giao dịch không có giá khớp nên
    không thể là một bar; ``cwintel`` tự coi phiên vắng mặt là volume 0 khi tính thanh khoản.
    """
    if history.empty:
        return pd.DataFrame(columns=["Ticker", "time", "open", "high", "low", "close", "volume"])
    traded = history[history["traded"].astype(bool) & history["close"].notna()].copy()
    if traded.empty:
        return pd.DataFrame(columns=["Ticker", "time", "open", "high", "low", "close", "volume"])
    out = pd.DataFrame({
        "Ticker": traded["ticker"].astype(str),
        "time": [date.fromisoformat(d).strftime("%d/%m/%Y") for d in traded["session"]],
        "open": traded["open"] / 1000.0,
        "high": traded["high"] / 1000.0,
        "low": traded["low"] / 1000.0,
        "close": traded["close"] / 1000.0,
        "volume": pd.to_numeric(traded["volume"], errors="coerce").fillna(0.0),
    })
    return out.sort_values(["Ticker", "time"], kind="stable").reset_index(drop=True)


def write_cwintel_cache(history: pd.DataFrame, path: Path) -> Path:
    """Ghi parquet đúng chỗ ``cwintel`` đọc (``config.OHLCV_CACHE`` mặc định)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    to_cwintel_ohlcv(history).to_parquet(path, index=False)
    return path
