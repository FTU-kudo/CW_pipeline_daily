"""Thanh khoản chứng quyền — đo lường, chấm điểm và cảnh báo.

Vì sao cần module riêng
-----------------------
Với CW Việt Nam, "thanh khoản" không chỉ là khối lượng: dữ liệu chỉ có dòng khi có
giao dịch, nên **phiên không giao dịch = không có dòng**, và giá trị giao dịch trung
bình tính trên các phiên có giao dịch sẽ **thổi phồng** thanh khoản thật. Module này
tính mọi chỉ tiêu trên **lịch giao dịch đầy đủ** (phiên vắng mặt = volume 0) và bổ
sung các thước đo tác động giá.

Định nghĩa (đơn vị)
-------------------
* ``adv20`` / ``adv5``  : VND/phiên — trung bình giá trị giao dịch 20/5 phiên gần nhất,
  tính trên lịch đầy đủ (ngày không giao dịch = 0).
* ``coverage20/60``     : % số phiên thực sự có giao dịch trong 20/60 phiên gần nhất.
* ``zero20``            : số phiên không giao dịch trong 20 phiên.
* ``amihud20``          : Amihud (2002) — trung vị ``|r| / value × 1e9`` trên các phiên
  có giao dịch; đơn vị **% giá dịch chuyển trên 1 tỷ VND giao dịch**. Càng cao càng kém.
* ``range20``           : trung vị ``(high − low)/close × 100`` — proxy biên độ/chi phí
  khớp lệnh; CW có bước giá 10 VND nên biên độ rộng hàm ý trượt giá lớn.
* ``turnover20``        : ``volume / outstanding_volume × 100`` — % lượng CW lưu hành
  được sang tay mỗi phiên.
* ``liq_trend``         : ``adv5 / adv20`` — >1 là thanh khoản đang cải thiện.
* ``dtl_50m``           : số phiên cần để thoát 50 triệu VND ở mức tham gia 20% ADV.
* ``impact_50m_pct``    : ước lượng tác động giá theo căn bậc hai (η·σ·√(Q/ADV)), %.

Tham chiếu: Amihud (2002); quy tắc thực hành tham gia 10–25% ADV; mô hình tác động
căn bậc hai; Quyết định 72/QĐ-UBCK & 68/QĐ-SGDHCM (bước giá 10 VND, lô tối thiểu 100
CW, nghĩa vụ yết giá của tổ chức phát hành, chênh lệch mua-bán tối đa 5%).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

PARTICIPATION_RATE = 0.20          # tham gia tối đa 20% ADV mỗi phiên
IMPACT_ETA = 0.10                  # hệ số mô hình tác động căn bậc hai
DEFAULT_POSITION_VND = 50_000_000  # vị thế tham chiếu để tính days-to-liquidate
MIN_COVERAGE_WARN = 50.0           # % phiên có giao dịch
MIN_ADV_WARN = 5_000_000           # VND/phiên
MAX_DTL_WARN = 5.0                 # phiên
MAX_RANGE_WARN = 12.0              # % biên độ high-low

LIQ_COLUMNS = [
    "adv20", "adv5", "adv60", "coverage20", "coverage60", "coverage_listing",
    "sessions_listed", "zero20",
    "amihud20", "range20", "turnover20", "liq_trend", "ret_std20",
    "dtl_50m", "impact_50m_pct",
]


# ──────────────────────────────────────────────────────────────────
# TÍNH TOÁN
# ──────────────────────────────────────────────────────────────────
def days_to_liquidate(position_vnd: float, adv: float,
                      participation: float = PARTICIPATION_RATE) -> float:
    """Số phiên cần để thoát `position_vnd` ở mức tham gia `participation` × ADV."""
    if not np.isfinite(adv) or adv <= 0 or not np.isfinite(position_vnd) or position_vnd <= 0:
        return float("nan")
    return float(position_vnd / (adv * max(1e-6, participation)))


def impact_pct(sigma_daily: float, position_vnd: float, adv: float,
               eta: float = IMPACT_ETA) -> float:
    """Ước lượng tác động giá (%, căn bậc hai): η · σ · √(Q / ADV) · 100."""
    if not (np.isfinite(adv) and adv > 0 and np.isfinite(position_vnd) and position_vnd > 0):
        return float("nan")
    sigma = float(sigma_daily) if np.isfinite(sigma_daily) and sigma_daily > 0 else 0.05
    return float(eta * sigma * np.sqrt(position_vnd / adv) * 100.0)


def attach_liquidity(panel: pd.DataFrame, master: pd.DataFrame,
                     calendar: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Gắn các cột thanh khoản vào panel (1 dòng / (ticker, phiên có giao dịch)).

    Tính trên lịch giao dịch đầy đủ: phiên không có dòng được coi là volume = 0.
    """
    if panel.empty:
        out = panel.copy()
        for c in LIQ_COLUMNS:
            out[c] = np.nan
        return out

    cal = pd.DatetimeIndex(sorted(pd.to_datetime(panel["date"]).unique())) \
        if calendar is None else pd.DatetimeIndex(calendar)
    m = master.set_index("ticker") if "ticker" in master.columns else master
    frames: list[pd.DataFrame] = []

    for ticker, g in panel.groupby("ticker", sort=False):
        g = g.sort_values("date")
        full = cal[(cal >= g["date"].min()) & (cal <= g["date"].max())]
        if len(full) == 0:
            continue
        r = pd.DataFrame(index=full)
        r["close"] = g.set_index("date")["close"].reindex(full)
        val = g.set_index("date").get("value")
        if val is None:
            val = g.set_index("date")["close"] * g.set_index("date").get("volume", 0.0)
        r["value"] = val.reindex(full).fillna(0.0)
        r["volume"] = g.set_index("date")["volume"].reindex(full).fillna(0.0) \
            if "volume" in g.columns else 0.0
        r["traded"] = r["value"] > 0

        r["coverage20"] = r["traded"].rolling(20, min_periods=5).mean() * 100.0
        r["coverage60"] = r["traded"].rolling(60, min_periods=20).mean() * 100.0
        r["zero20"] = (~r["traded"]).rolling(20, min_periods=5).sum()

        # Độ phủ tính từ ngày niêm yết: CW mới có 5 phiên lịch sử không bị coi là "kém thanh khoản"
        ft = m.loc[ticker, "first_trade"] if ticker in m.index and "first_trade" in m.columns else pd.NaT
        start = full[0] if pd.isna(ft) else max(full[0], pd.Timestamp(ft))
        listed = (full >= start).astype(int)
        cum = pd.Series(np.cumsum(np.asarray(listed)), index=full)
        r["sessions_listed"] = cum
        denom = np.minimum(20, cum).replace(0, np.nan)
        r["coverage_listing"] = (r["traded"].astype(float).rolling(20, min_periods=1).sum()
                                 / denom * 100.0).clip(0, 100)
        r["adv20"] = r["value"].rolling(20, min_periods=5).sum() / 20.0
        r["adv60"] = r["value"].rolling(60, min_periods=20).sum() / 60.0
        r["adv5"] = r["value"].rolling(5, min_periods=3).sum() / 5.0

        ret = r["close"].pct_change()
        r["ret_std20"] = ret.rolling(20, min_periods=5).std()
        with np.errstate(divide="ignore", invalid="ignore"):
            amihud = (ret.abs() / r["value"].replace(0, np.nan)) * 1e9
        r["amihud20"] = amihud.rolling(20, min_periods=5).median()

        outstood = float(m.loc[ticker, "outstanding_volume"]) \
            if ticker in m.index and "outstanding_volume" in m.columns else np.nan
        if np.isfinite(outstood) and outstood > 0:
            r["turnover20"] = r["volume"].rolling(20, min_periods=5).mean() / outstood * 100.0
        else:
            r["turnover20"] = np.nan

        r["liq_trend"] = (r["adv5"] / r["adv20"].replace(0, np.nan)).clip(0, 5)

        # biên độ high-low (proxy trượt giá) cần high/low — lấy từ panel nếu có
        if {"high", "low"}.issubset(g.columns):
            hi = g.set_index("date")["high"].reindex(full)
            lo = g.set_index("date")["low"].reindex(full)
            rng = (hi - lo) / r["close"].replace(0, np.nan)
            r["range20"] = rng.rolling(20, min_periods=5).median() * 100.0
        else:
            r["range20"] = np.nan

        r["dtl_50m"] = [days_to_liquidate(DEFAULT_POSITION_VND, a) for a in r["adv20"]]
        r["impact_50m_pct"] = [impact_pct(s, DEFAULT_POSITION_VND, a)
                               for s, a in zip(r["ret_std20"], r["adv20"])]

        keep = r.loc[g["date"].values, LIQ_COLUMNS]
        keep.index = g.index
        frames.append(keep)

    out = panel.copy()
    if frames:
        liq = pd.concat(frames).sort_index()
        for c in LIQ_COLUMNS:
            out[c] = liq[c].reindex(out.index)
    else:
        for c in LIQ_COLUMNS:
            out[c] = np.nan
    return out


def rebase_to_asof(snap: pd.DataFrame, panel: pd.DataFrame,
                   asof: pd.Timestamp, window: int = 20) -> pd.DataFrame:
    """Tính lại thanh khoản **tại ngày as-of**, không phải tại lần giao dịch cuối.

    `slice_asof` lấy dòng cuối cùng của mỗi CW, nên với CW đã ngừng khớp lệnh 10 phiên,
    ADV20 bị "đóng băng" ở lần giao dịch cuối và trông tốt hơn thực tế. Hàm này tính
    lại trên `window` phiên gần nhất tính tới `asof`, coi phiên không giao dịch = 0.
    """
    if snap.empty or panel.empty:
        return snap
    cal = pd.DatetimeIndex(sorted(pd.to_datetime(panel["date"]).unique()))
    cal = cal[cal <= pd.Timestamp(asof)]
    if len(cal) == 0:
        return snap
    win = cal[-window:]
    recent = panel[panel["date"].isin(win)]
    if recent.empty:
        return snap

    val_sum = recent.groupby("ticker")["value"].sum()
    traded = recent.groupby("ticker")["date"].nunique()
    adv5_dates = cal[-5:]
    val5 = panel[panel["date"].isin(adv5_dates)].groupby("ticker")["value"].sum()

    d = snap.copy()
    tick = d["ticker"]
    d["adv20"] = tick.map(val_sum).fillna(0.0) / len(win)
    d["adv5"] = tick.map(val5).fillna(0.0) / len(adv5_dates)
    traded_n = tick.map(traded).fillna(0)
    d["zero20"] = (len(win) - traded_n).clip(lower=0)
    d["coverage20"] = traded_n / len(win) * 100.0

    if "first_trade" in d.columns:
        ft = pd.to_datetime(d["first_trade"], errors="coerce")
        listed = pd.Series([sum(1 for x in win if pd.isna(f) or x >= f) for f in ft],
                           index=d.index, dtype=float)
        d["sessions_listed"] = listed
        denom = listed.clip(upper=len(win)).replace(0, np.nan)
        d["coverage_listing"] = (traded_n / denom * 100.0).clip(0, 100)
    else:
        d["coverage_listing"] = d["coverage20"]

    d["dtl_50m"] = [days_to_liquidate(DEFAULT_POSITION_VND, a) for a in d["adv20"]]
    d["impact_50m_pct"] = [impact_pct(s, DEFAULT_POSITION_VND, a)
                           for s, a in zip(d["ret_std20"], d["adv20"])]
    d["liq_asof"] = pd.Timestamp(asof).strftime("%Y-%m-%d")
    d["liq_window"] = len(win)
    return d


# ──────────────────────────────────────────────────────────────────
# CỜ CẢNH BÁO
# ──────────────────────────────────────────────────────────────────
def liquidity_flags(row) -> list[str]:
    """Cảnh báo thanh khoản cụ thể cho một CW (dùng cho recommendation card)."""
    out: list[str] = []
    adv = row.get("adv20", np.nan)
    cov = row.get("coverage_listing",
                  row.get("coverage20", np.nan))
    zero = row.get("zero20", np.nan)
    listed = row.get("sessions_listed", np.nan)
    amihud = row.get("amihud20", np.nan)
    rng = row.get("range20", np.nan)
    dtl = row.get("dtl_50m", np.nan)
    trend = row.get("liq_trend", np.nan)

    if pd.notna(adv) and adv < MIN_ADV_WARN:
        out.append(f"Thanh khoản rất thấp: ADV20 chỉ {adv/1e6:.1f} triệu VND/phiên — "
                   f"khó vào/ra vị thế mà không làm giá chạy.")
    if pd.notna(cov) and cov < MIN_COVERAGE_WARN and (pd.isna(listed) or listed >= 20):
        out.append(f"Chỉ giao dịch {cov:.0f}% số phiên kể từ khi niêm yết"
                   + (f" ({int(zero)} phiên không khớp lệnh)" if pd.notna(zero) else "")
                   + " — rủi ro không thoát được hàng.")
    if pd.notna(dtl) and dtl > MAX_DTL_WARN:
        out.append(f"Vị thế 50 triệu VND cần ~{dtl:.1f} phiên để thoát ở mức 20% ADV.")
    if pd.notna(amihud) and amihud > 3.0:
        out.append(f"Tác động giá lớn: 1 tỷ VND giao dịch làm giá dịch chuyển ~{amihud:.1f}% "
                   f"(Amihud 20 phiên).")
    if pd.notna(rng) and rng > MAX_RANGE_WARN:
        out.append(f"Biên độ high-low 20 phiên rộng ({rng:.1f}%) — chênh lệch mua-bán và "
                   f"trượt giá thực tế cao.")
    if pd.notna(trend) and trend < 0.5:
        out.append(f"Thanh khoản đang suy giảm: ADV5 chỉ bằng {trend:.0%} ADV20.")
    return out


def liquidity_bucket(row) -> str:
    """Nhóm thanh khoản hiển thị trên UI (dựa trên ADV20 và độ phủ giao dịch)."""
    adv = row.get("adv20", np.nan)
    cov = row.get("coverage20", np.nan)
    if pd.isna(adv):
        return "không rõ"
    if adv >= 500e6 and (pd.isna(cov) or cov >= 90):
        return "rất cao"
    if adv >= 200e6:
        return "cao"
    if adv >= 50e6:
        return "trung bình"
    if adv >= 10e6:
        return "thấp"
    return "rất thấp"


# ──────────────────────────────────────────────────────────────────
# TỔNG HỢP THỊ TRƯỜNG
# ──────────────────────────────────────────────────────────────────
def liquidity_summary(snap: pd.DataFrame) -> dict:
    """Thống kê thanh khoản toàn thị trường cho artifact `liquidity.json`."""
    if snap.empty:
        return {}

    adv = pd.to_numeric(snap.get("adv20"), errors="coerce")
    cov = pd.to_numeric(snap.get("coverage_listing",
                                 snap.get("coverage20")), errors="coerce")
    val = pd.to_numeric(snap.get("value"), errors="coerce")
    amihud = pd.to_numeric(snap.get("amihud20"), errors="coerce")
    rng = pd.to_numeric(snap.get("range20"), errors="coerce")

    def _stats(s: pd.Series) -> dict:
        s = s.dropna()
        if s.empty:
            return {}
        return {
            "n": int(s.size),
            "p25": float(s.quantile(0.25)), "median": float(s.median()),
            "p75": float(s.quantile(0.75)), "p90": float(s.quantile(0.90)),
            "mean": float(s.mean()),
        }

    total_value = float(val.fillna(0).sum())
    share = (val / total_value) if total_value > 0 else pd.Series(dtype=float)
    top = share.sort_values(ascending=False) if len(share) else pd.Series(dtype=float)

    buckets = []
    for lo, hi, label in [(0, 10e6, "dưới 10 triệu"), (10e6, 50e6, "10–50 triệu"),
                          (50e6, 200e6, "50–200 triệu"), (200e6, 500e6, "200–500 triệu"),
                          (500e6, np.inf, "trên 500 triệu")]:
        m = (adv >= lo) & (adv < hi)
        buckets.append({
            "label": label, "n": int(m.sum()),
            "sharePct": round(float(m.mean()) * 100, 1),
            "valuePct": round(float(val[m].sum() / total_value * 100), 1) if total_value else None,
            "medianCoverage": round(float(cov[m].median()), 1) if cov[m].notna().any() else None,
        })

    by_issuer = []
    if "issuer_name" in snap.columns or "issuer" in snap.columns:
        key = "issuer_name" if "issuer_name" in snap.columns else "issuer"
        for name, g in snap.groupby(key):
            a = pd.to_numeric(g.get("adv20"), errors="coerce")
            by_issuer.append({
                "key": str(name), "n": int(len(g)),
                "advMedian": round(float(a.median()), 0) if a.notna().any() else None,
                "value": round(float(pd.to_numeric(g.get("value"), errors="coerce").fillna(0).sum()), 0),
                "coverageMedian": round(float(pd.to_numeric(
                    g.get("coverage_listing", g.get("coverage20")), errors="coerce").median()), 1)
                if (g.get("coverage_listing") is not None or g.get("coverage20") is not None) else None,
            })
        by_issuer.sort(key=lambda d: -(d["value"] or 0))

    by_underlying = []
    if "underlying" in snap.columns:
        for name, g in snap.groupby("underlying"):
            a = pd.to_numeric(g.get("adv20"), errors="coerce")
            by_underlying.append({
                "key": str(name), "n": int(len(g)),
                "advMedian": round(float(a.median()), 0) if a.notna().any() else None,
                "advSum": round(float(a.fillna(0).sum()), 0),
            })
        by_underlying.sort(key=lambda d: -d["advSum"])

    flags = {
        "advBelow5m": int((adv < 5e6).sum()),
        "coverageBelow50": int((cov < 50).sum()),
        "dtlAbove5": int((pd.to_numeric(snap.get("dtl_50m"), errors="coerce") > 5).sum()),
        "amihudAbove3": int((amihud > 3.0).sum()),
        "rangeAbove12": int((rng > 12.0).sum()),
    }

    # tương quan hạng trong mặt cắt hiện tại (không phải dự báo)
    corr = {}
    for col in ["adv20", "amihud20", "range20", "coverage20"]:
        s = pd.to_numeric(snap.get(col), errors="coerce")
        for other in ["premium_be", "iv_vs_hv", "days_to_maturity"]:
            o = pd.to_numeric(snap.get(other), errors="coerce")
            if s.notna().sum() > 10 and o.notna().sum() > 10:
                # Spearman = Pearson trên hạng (không cần scipy)
                corr[f"{col}~{other}"] = round(float(s.rank().corr(o.rank())), 3)
    return {
        "asof": pd.Timestamp(snap["date"].max()).strftime("%Y-%m-%d") if "date" in snap else None,
        "universe": int(len(snap)),
        "totalValue": round(total_value, 0),
        "kpi": {
            "advMedian": round(float(adv.median()), 0) if adv.notna().any() else None,
            "advMean": round(float(adv.mean()), 0) if adv.notna().any() else None,
            "coverageMedian": round(float(cov.median()), 1) if cov.notna().any() else None,
            "coverage20Median": round(float(pd.to_numeric(snap.get("coverage20"), errors="coerce").median()), 1)
            if snap.get("coverage20") is not None else None,
            "shareCoverageBelow50": round(float((cov < 50).mean()) * 100, 1),
            "amihudMedian": round(float(amihud.median()), 2) if amihud.notna().any() else None,
            "rangeMedian": round(float(rng.median()), 2) if rng.notna().any() else None,
            "top1Share": round(float(top.iloc[0]) * 100, 1) if len(top) else None,
            "top5Share": round(float(top.head(5).sum()) * 100, 1) if len(top) else None,
            "top10Share": round(float(top.head(10).sum()) * 100, 1) if len(top) else None,
            "flagged": flags,
        },
        "distribution": {
            "adv": _stats(adv),
            "coverage": _stats(cov),
            "amihud": _stats(amihud),
            "range": _stats(rng),
        },
        "buckets": buckets,
        "byIssuer": by_issuer,
        "byUnderlying": by_underlying,
        "rankCorr": corr,
        "notes": [
            "ADV tính trên lịch giao dịch đầy đủ: phiên không có giao dịch = 0 VND.",
            "Amihud = trung vị |r|/giá trị giao dịch × 1e9 — % giá dịch chuyển trên 1 tỷ VND.",
            "Days-to-liquidate dùng vị thế tham chiếu 50 triệu VND và tham gia 20% ADV.",
        ],
    }
