"""Vòng đời chứng quyền: niêm yết → giao dịch → đáo hạn / ngừng giao dịch.

CW được **niêm yết và đáo hạn liên tục** (mỗi tuần có mã mới, mỗi tháng có mã hết
hạn), nên mọi mặt cắt phải trả lời được 3 câu hỏi tách biệt:

1. **Không gian hợp đồng** — mã nào còn hiệu lực tại `asof`, mã nào đã đáo hạn,
   đáo hạn khi nào, mã nào chờ niêm yết. Tổng các trạng thái phải khớp tuyệt đối
   với số dòng master (`identity`).
2. **Hoạt động giao dịch** — trong số còn hiệu lực, mã nào thực sự khớp lệnh
   phiên `asof`, mã nào "phiên trắng" đã bao nhiêu phiên. Việc này phải dựa trên
   **giá quan sát được**, không dựa vào `ngay_gd_cuoi_cung` của Vietstock (trường
   đó là *phiên giao dịch cuối theo kế hoạch*, nằm ở tương lai so với `asof`).
3. **Sự kiện vòng đời** — mã vừa niêm yết / vừa đáo hạn trong N phiên gần nhất,
   mã sắp đáo hạn 30/60/90 ngày, mã ngừng giao dịch sớm trước hạn.

Mọi thống kê xuất bản lấy từ module này để overview, screener và quality không
thể "đếm" khác nhau.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

STATES = ("listed", "pending", "matured", "delisted_early", "unknown")

STATE_LABEL = {
    "listed": "Còn hiệu lực",
    "pending": "Chờ niêm yết",
    "matured": "Đã đáo hạn",
    "delisted_early": "Ngừng giao dịch sớm",
    "unknown": "Thiếu ngày đáo hạn",
}


def _date_col(df: pd.DataFrame, col: str) -> pd.Series:
    """Cột ngày đã parse, trả về NaT nếu thiếu cột (không bao giờ raise)."""
    if col in df.columns:
        return pd.to_datetime(df[col], errors="coerce")
    return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")


def session_cutoff(panel: pd.DataFrame | None, asof: pd.Timestamp,
                   n: int | None = None) -> pd.Timestamp:
    """Ngày bắt đầu của `n` phiên gần nhất tính đến `asof` (bao gồm phiên asof).

    Dùng lịch phiên thực tế từ panel thay vì "n ngày lịch", để cửa sổ 10 phiên
    không bị lệch khi có nghỉ lễ. Không có panel → xấp xỉ theo ngày lịch.
    """
    n = n or config.LIFECYCLE_RECENT_SESSIONS
    asof = pd.Timestamp(asof).normalize()
    if panel is not None and len(panel) and "date" in panel.columns:
        dates = pd.Series(pd.to_datetime(panel.loc[panel["date"] <= asof, "date"]).unique()).sort_values()
        # Chỉ dùng lịch phiên khi có ĐỦ n phiên trong panel; nếu lịch sử ngắn hơn
        # (test, dữ liệu mới) thì fallback theo ngày lịch để không biến toàn bộ vũ
        # trụ thành "vừa niêm yết".
        if len(dates) >= n:
            return pd.Timestamp(dates.iloc[len(dates) - n])
    return asof - pd.Timedelta(days=int(round(n * 7 / 5)))


def last_print_from_panel(panel: pd.DataFrame | None) -> pd.Series:
    """Phiên giao dịch thực tế gần nhất của từng CW (index = ticker)."""
    if panel is None or len(panel) == 0 or "ticker" not in panel.columns:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(panel.groupby("ticker")["date"].max())


def last_price_from_panel(panel: pd.DataFrame | None) -> pd.Series:
    """Giá đóng cửa gần nhất của từng CW (index = ticker)."""
    if panel is None or len(panel) == 0 or "ticker" not in panel.columns:
        return pd.Series(dtype="float64")
    work = panel.sort_values("date").drop_duplicates("ticker", keep="last").set_index("ticker")
    if "close" not in work.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(work["close"], errors="coerce")


def classify(master: pd.DataFrame, asof: pd.Timestamp,
             panel: pd.DataFrame | None = None,
             last_print: pd.Series | None = None,
             recent_sessions: int | None = None,
             early_stop_days: int | None = None) -> pd.DataFrame:
    """Gán trạng thái vòng đời cho từng CW tại `asof`.

    Trả về bản copy của `master` (nếu có) kèm các cột:

    - `state` ∈ {listed, pending, matured, delisted_early, unknown}
    - `dte` — số ngày còn lại tính **tại asof** (âm nếu đã đáo hạn)
    - `days_since_print` — số ngày kể từ lần khớp lệnh cuối (NaN nếu chưa có giá)
    - `traded_on_asof` — có khớp lệnh đúng phiên `asof`
    - `new_listing` / `recently_matured` — sự kiện trong `recent_sessions` phiên
    - `early_stop` — còn hạn nhưng đã ngừng giao dịch quá `early_stop_days` ngày
    """
    asof = pd.Timestamp(asof).normalize()
    if early_stop_days is None:
        early_stop_days = config.LIFECYCLE_EARLY_STOP_DAYS
    if master is None or len(master) == 0:
        return pd.DataFrame()

    d = master.copy()
    if "ticker" not in d.columns:
        d["ticker"] = pd.Series(dtype=str)
    mat = _date_col(d, "maturity")
    first = _date_col(d, "first_trade")
    lp = last_print if last_print is not None else last_print_from_panel(panel)
    lp_row = d["ticker"].map(lp) if len(lp) else pd.Series(pd.NaT, index=d.index, dtype="datetime64[ns]")

    d["dte"] = (mat - asof).dt.days.astype("Int64")
    d["days_since_print"] = (asof - pd.to_datetime(lp_row)).dt.days.astype("Int64")
    d["maturity"] = mat
    d["first_trade"] = first

    matured = mat.notna() & (mat <= asof)
    pending = (~matured) & first.notna() & (first > asof)
    unknown = (~matured) & (~pending) & mat.isna()
    price_known = lp_row.notna()
    stale_days = pd.to_numeric(d["days_since_print"], errors="coerce")
    days_left = pd.to_numeric(d["dte"], errors="coerce")
    # "Ngừng giao dịch sớm": còn hạn nhưng đã im lặng quá ngưỡng. Chỉ so với lần
    # khớp lệnh cuối — KHÔNG so với ngày đáo hạn, vì mọi CW đều có ngày đáo hạn xa
    # hơn lần khớp lệnh cuối (đó là bản chất của hợp đồng, không phải dấu hiệu huỷ).
    early = (~matured) & (~pending) & (~unknown) & price_known & (days_left > 0) & (
        stale_days > early_stop_days)

    d["state"] = np.select(
        [matured, pending, unknown, early],
        ["matured", "pending", "unknown", "delisted_early"],
        default="listed",
    )
    d["traded_on_asof"] = (d["state"] == "listed") & (stale_days == 0)
    d["early_stop"] = d["state"] == "delisted_early"

    cutoff = session_cutoff(panel, asof, recent_sessions)
    d["new_listing"] = first.notna() & (first <= asof) & (first > cutoff)
    d["recently_matured"] = mat.notna() & (mat <= asof) & (mat > cutoff)
    d.attrs["asof"] = asof
    d.attrs["cutoff"] = cutoff
    return d


def counts(cls: pd.DataFrame) -> dict:
    """Đếm theo trạng thái — tổng luôn khớp số dòng (`identity`)."""
    if cls is None or len(cls) == 0:
        return {"total": 0, "listed": 0, "traded": 0, "notTraded": 0, "pending": 0,
                "matured": 0, "maturedRecent": 0, "delistedEarly": 0, "unknown": 0,
                "newListings": 0, "expired": 0}
    state = cls["state"]
    vc = state.value_counts()
    listed = int(vc.get("listed", 0))
    traded = int((cls["traded_on_asof"].fillna(False)).sum()) if "traded_on_asof" in cls else 0
    matured = int(vc.get("matured", 0))
    early = int(vc.get("delisted_early", 0))
    return {
        "total": int(len(cls)),
        "listed": listed,
        "traded": min(traded, listed),
        "notTraded": max(listed - min(traded, listed), 0),
        "pending": int(vc.get("pending", 0)),
        "matured": matured,
        "delistedEarly": early,
        "unknown": int(vc.get("unknown", 0)),
        "newListings": int(cls["new_listing"].fillna(False).sum()) if "new_listing" in cls else 0,
        "maturedRecent": int(cls["recently_matured"].fillna(False).sum()) if "recently_matured" in cls else 0,
        # "expired" giữ cho tương thích: đã đáo hạn + ngừng giao dịch sớm
        "expired": matured + early,
    }


def identity(cnt: dict) -> dict:
    """Kiểm tra tổng vũ trụ: total phải bằng tổng các trạng thái."""
    total = int(cnt.get("total", 0))
    parts = sum(int(cnt.get(k, 0)) for k in ("listed", "pending", "matured", "delistedEarly", "unknown"))
    return {"total": total, "sumStates": parts, "ok": total == parts,
            "gap": total - parts}


def alive_tickers(master: pd.DataFrame, asof: pd.Timestamp) -> set[str]:
    """Ticker còn hiệu lực hợp đồng tại `asof` (dùng để lọc snapshot).

    Nguyên tắc: đáo hạn khi `maturity <= asof` (hết hiệu lực ngay trong ngày đáo
    hạn) và chỉ tính mã đã bắt đầu giao dịch. Mã thiếu ngày đáo hạn bị loại vì
    không tính được DTE/T.
    """
    if master is None or len(master) == 0:
        return set()
    asof = pd.Timestamp(asof).normalize()
    mat = _date_col(master, "maturity")
    first = _date_col(master, "first_trade")
    keep = mat.notna() & (mat > asof) & (first.isna() | (first <= asof))
    return set(master.loc[keep, "ticker"].astype(str))


def _row_list(sub: pd.DataFrame, cols: dict[str, str], limit: int) -> list[dict]:
    out = []
    for _, r in sub.head(limit).iterrows():
        item = {}
        for key, src in cols.items():
            v = r.get(src)
            if isinstance(v, pd.Timestamp):
                item[key] = v.strftime("%Y-%m-%d") if pd.notna(v) else None
            elif isinstance(v, (np.integer,)):
                item[key] = int(v)
            elif isinstance(v, (np.floating, float)):
                item[key] = None if not np.isfinite(v) else round(float(v), 2)
            else:
                item[key] = v if v is not None and v is not pd.NaT else None
        out.append(item)
    return out


def payload(master: pd.DataFrame, asof: pd.Timestamp,
            panel: pd.DataFrame | None = None,
            recent_sessions: int | None = None,
            forward_days: tuple[int, ...] | None = None,
            calendar_back: int | None = None,
            calendar_fwd: int | None = None,
            limit: int = 40) -> dict:
    """Toàn bộ dữ liệu vòng đời cho dashboard (`docs/data/lifecycle.json`)."""
    asof = pd.Timestamp(asof).normalize()
    recent_sessions = recent_sessions or config.LIFECYCLE_RECENT_SESSIONS
    forward_days = forward_days or config.LIFECYCLE_FORWARD_DAYS
    calendar_back = config.LIFECYCLE_CALENDAR_BACK if calendar_back is None else calendar_back
    calendar_fwd = config.LIFECYCLE_CALENDAR_FWD if calendar_fwd is None else calendar_fwd

    cls = classify(master, asof, panel=panel, recent_sessions=recent_sessions)
    if cls is None or len(cls) == 0:
        return {"asof": asof.strftime("%Y-%m-%d"), "counts": counts(None),
                "identity": identity(counts(None)), "newListings": {"count": 0, "rows": []},
                "recentMaturities": {"count": 0, "rows": []}, "upcoming": {},
                "earlyDelistings": {"count": 0, "rows": []}, "calendar": [],
                "recentSessions": recent_sessions}

    cnt = counts(cls)
    cutoff = cls.attrs.get("cutoff", asof)
    price = last_price_from_panel(panel)

    def _enrich(sub: pd.DataFrame, price_col: bool = True) -> pd.DataFrame:
        sub = sub.copy()
        if price_col and len(price):
            sub["lastPrice"] = sub["ticker"].map(price)
        return sub

    new = _enrich(cls[cls["new_listing"]]).sort_values("first_trade", ascending=False)
    recent = _enrich(cls[cls["recently_matured"]]).sort_values("maturity", ascending=False)
    early = _enrich(cls[cls["state"] == "delisted_early"]).sort_values(
        "days_since_print", ascending=False)

    base_cols = {"t": "ticker", "u": "underlying", "iss": "issuer", "issName": "issuer_name"}

    upcoming = {}
    for days in forward_days:
        sub = cls[(cls["state"] == "listed") & cls["dte"].notna()
                  & (pd.to_numeric(cls["dte"], errors="coerce") <= days)]
        sub = _enrich(sub).sort_values("dte")
        upcoming[f"d{days}"] = {
            "count": int(len(sub)),
            "rows": _row_list(sub, {**base_cols, "maturity": "maturity", "dte": "dte",
                                    "lastPrice": "lastPrice"}, limit),
        }

    calendar = []
    start = (asof.to_period("M") - calendar_back).to_timestamp()
    end = (asof.to_period("M") + calendar_fwd).to_timestamp()
    months = pd.period_range(start, end, freq="M")
    first_p = cls["first_trade"].dt.to_period("M").value_counts()
    mat_p = cls["maturity"].dt.to_period("M").value_counts()
    listed_now = cls[cls["state"] == "listed"]["maturity"].dt.to_period("M").value_counts()
    cur = asof.to_period("M")
    for m in months:
        calendar.append({
            "month": str(m),
            "label": m.strftime("%m/%Y"),
            "listings": int(first_p.get(m, 0)),
            "maturities": int(mat_p.get(m, 0)),
            "listedNow": int(listed_now.get(m, 0)),
            "isCurrent": bool(m == cur),
            "isPast": bool(m < cur),
        })

    nxt = cls[(cls["state"] == "listed") & cls["dte"].notna()]
    next_maturity = None
    if len(nxt):
        nxt = nxt.sort_values("dte").iloc[0]
        next_maturity = {"t": nxt.get("ticker"), "u": nxt.get("underlying"),
                         "maturity": nxt["maturity"].strftime("%Y-%m-%d"),
                         "dte": int(nxt["dte"])}

    return {
        "asof": asof.strftime("%Y-%m-%d"),
        "asofLabel": asof.strftime("%d/%m/%Y"),
        "recentSessions": int(recent_sessions),
        "recentSince": pd.Timestamp(cutoff).strftime("%Y-%m-%d"),
        "counts": cnt,
        "identity": identity(cnt),
        "newListings": {
            "count": int(len(new)),
            "rows": _row_list(new, {**base_cols, "firstTrade": "first_trade",
                                    "dte": "dte", "lastPrice": "lastPrice"}, limit),
        },
        "recentMaturities": {
            "count": int(len(recent)),
            "rows": _row_list(recent, {**base_cols, "maturity": "maturity",
                                       "daysSince": "days_since_print", "lastPrice": "lastPrice"}, limit),
        },
        "upcoming": upcoming,
        "earlyDelistings": {
            "count": int(len(early)),
            "rows": _row_list(early, {**base_cols, "maturity": "maturity",
                                      "daysSince": "days_since_print", "dte": "dte"}, limit),
        },
        "nextMaturity": next_maturity,
        "calendar": calendar,
    }
