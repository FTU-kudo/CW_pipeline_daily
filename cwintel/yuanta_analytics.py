"""Phân tích bảng giá chứng quyền: xếp hạng thanh khoản, nhóm cơ sở, giám sát mã "chết".

Chỉ dùng những gì một mặt cắt bảng giá thật sự chứa: giá trị/khối lượng phiên, spread từ
sổ lệnh, giá tham chiếu. Không định giá, không Greeks, không khuyến nghị — xem
``cwintel.yuanta_board`` để biết vì sao.

Thang xếp hạng thanh khoản **không** dùng ngưỡng VND tuyệt đối tuỳ tiện. Ngưỡng được suy
từ chính phân bố của snapshot hiện tại (phân vị), và được ghi kèm trong payload để người đọc
thấy nó phụ thuộc dữ liệu ngày hôm đó. Nhờ vậy bảng xếp hạng vẫn có nghĩa khi thanh khoản
toàn thị trường co lại hoặc bùng lên.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .yuanta_scoring import score_warrants
from .yuanta_valuation import price_warrants, summarize as summarize_valuation
from .yuanta_intraday import (
    intraday_moves,
    last_trade_profile,
    price_band_profile,
    ref_continuity,
)

#: Nhãn nhóm thanh khoản, từ cao xuống thấp. Ranh giới = phân vị của snapshot hiện tại.
LIQUIDITY_TIERS: tuple[str, ...] = ("rất cao", "cao", "trung bình", "thấp", "rất thấp")
TIER_QUANTILES: tuple[float, ...] = (0.80, 0.60, 0.30, 0.10)

#: Cảnh báo "mã chết": không khớp lệnh liên tiếp ≥ ngưỡng này (phiên).
STALE_SESSIONS_WARN = 5
#: Spread rộng hơn ngưỡng này (%) là chi phí vào/ra đáng kể với CW.
WIDE_SPREAD_PCT = 5.0


def _f(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(out) else round(out, digits)


def tier_thresholds(frame: pd.DataFrame) -> list[dict]:
    """Ranh giới phân vị để chia nhóm thanh khoản (VND/phiên, chỉ trên mã có khớp lệnh)."""
    values = frame.loc[frame["Traded"].fillna(False), "TradingValueVND"].dropna()
    if values.empty:
        return []
    out = []
    for label, q in zip(("p80", "p60", "p30", "p10"), TIER_QUANTILES):
        out.append({"quantile": label, "valueVND": _f(values.quantile(q), 0)})
    return out


def assign_tier(values: pd.Series, thresholds: list[dict]) -> pd.Series:
    """Gán nhãn nhóm theo ngưỡng phân vị; mã không khớp lệnh → ``không giao dịch``."""
    if not thresholds:
        return pd.Series(["không xác định"] * len(values), index=values.index, dtype="object")

    usable = [(tier, float(th["valueVND"])) for tier, th in zip(LIQUIDITY_TIERS, thresholds)
              if th.get("valueVND") is not None
              and math.isfinite(float(th["valueVND"]))]

    def label(value: float) -> str:
        # NaN = mã không khớp lệnh (không có giá trị giao dịch), khác với 0 đồng.
        if value is None or (isinstance(value, float) and not math.isfinite(value)):
            return "không giao dịch"
        for tier, threshold in usable:
            if value >= threshold:
                return tier
        return LIQUIDITY_TIERS[-1]

    return values.map(label).astype("object")


def liquidity_ranking(frame: pd.DataFrame, *, limit: int = 25) -> dict:
    """Bảng xếp hạng theo giá trị giao dịch phiên + phân bố theo nhóm."""
    thresholds = tier_thresholds(frame)
    tiers = pd.Series("không giao dịch", index=frame.index, dtype="object")
    traded_mask = frame["Traded"].fillna(False)
    if traded_mask.any():
        tiers.loc[traded_mask] = assign_tier(
            frame.loc[traded_mask, "TradingValueVND"], thresholds).to_numpy()
    frame = frame.assign(LiquidityTier=tiers)
    traded = frame[traded_mask].copy()

    ranked = traded.sort_values("TradingValueVND", ascending=False).head(limit)
    rows = []
    for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
        rows.append({
            "rank": rank,
            "t": row["StockCode"],
            "u": row["Underlying"] if isinstance(row["Underlying"], str) else None,
            "price": _f(row["LastPrice"]),
            "chgPct": _f(row["PriceChangePct"]),
            "volume": _f(row["TotalVol"], 0),
            "valueVND": _f(row["TradingValueVND"], 0),
            "valueSharePct": _f(row["ValueSharePct"]),
            "spreadPct": _f(row["SpreadPct"]),
            "tier": row["LiquidityTier"],
        })

    distribution = []
    for tier in (*LIQUIDITY_TIERS, "không giao dịch"):
        group = frame[frame["LiquidityTier"] == tier]
        distribution.append({
            "tier": tier,
            "count": int(len(group)),
            "sharePct": _f(len(group) / len(frame) * 100) if len(frame) else None,
            "valueVND": _f(group["TradingValueVND"].sum(min_count=1), 0),
            "medianSpreadPct": _f(group["SpreadPct"].median() if len(group) else None),
        })

    by_tier = {tier: frame[frame["LiquidityTier"] == tier]["TradingValueVND"].dropna()
               for tier in LIQUIDITY_TIERS}
    total = frame["TradingValueVND"].sum(min_count=1)
    concentration = {
        "top10ValueSharePct": _f(traded["TradingValueVND"].nlargest(10).sum()
                                 / total * 100 if len(traded) and total else None),
        "top1ValueSharePct": _f(traded["TradingValueVND"].max() / total * 100
                                if len(traded) and total else None),
        "hhi": _f(((traded["TradingValueVND"] / total) ** 2).sum() if len(traded) and total else None, 4),
    }
    return {
        "ranking": rows,
        "tiers": distribution,
        "thresholds": thresholds,
        "thresholdBasis": (
            "Phân vị của chính snapshot này (p80/p60/p30/p10 theo giá trị giao dịch phiên), "
            "không phải ngưỡng VND cố định. Mã không khớp lệnh không được xếp hạng."
        ),
        "concentration": concentration,
        "medianValueByTier": {tier: _f(series.median() if len(series) else None, 0)
                              for tier, series in by_tier.items()},
    }


def underlying_breakdown(frame: pd.DataFrame, *, limit: int = 20) -> list[dict]:
    """Nhóm theo cổ phiếu cơ sở (suy ra từ quy ước mã), kèm độ tập trung và spread."""
    work = frame[frame["Underlying"].notna()].copy()
    if work.empty:
        return []
    total_value = work["TradingValueVND"].sum(min_count=1) or 0.0
    rows = []
    for underlying, group in work.groupby("Underlying", sort=False):
        traded = group[group["Traded"].fillna(False)]
        value = float(traded["TradingValueVND"].sum(min_count=1) or 0.0)
        spread = traded["SpreadPct"].dropna()
        rows.append({
            "underlying": underlying,
            "warrants": int(len(group)),
            "traded": int(len(traded)),
            "valueVND": _f(value, 0),
            "valueSharePct": _f(value / total_value * 100 if total_value else None),
            "volume": _f(traded["TotalVol"].sum(min_count=1), 0),
            "medianValueVND": _f(traded["TradingValueVND"].median() if len(traded) else None, 0),
            "medianSpreadPct": _f(spread.median() if len(spread) else None),
            "medianPriceVND": _f(traded["LastPrice"].median() if len(traded) else None),
            "bestChangePct": _f(traded["PriceChangePct"].max() if len(traded) else None),
            "worstChangePct": _f(traded["PriceChangePct"].min() if len(traded) else None),
            "liquidSharePct": _f((traded["TradingValueVND"] >= work["TradingValueVND"]
                                  .quantile(0.60)).mean() * 100 if len(traded) else None),
        })
    rows.sort(key=lambda r: (r["valueVND"] or 0, r["warrants"]), reverse=True)
    return rows[:limit]


def stale_monitor(frame: pd.DataFrame, history: pd.DataFrame | None = None, *,
                  asof: str | None = None, limit: int = 25) -> dict:
    """Giám sát mã mất thanh khoản — cả mã im lặng hôm nay lẫn mã vừa hồi phục.

    ``history`` (nếu có) cho biết "đã bao nhiêu phiên", thay vì chỉ "hôm nay". Không có
    lịch sử thì chỉ báo được trạng thái hôm nay — không suy ra quá khứ.

    Danh sách chính là các mã **không khớp lệnh hôm nay** (sắp xếp theo số phiên im lặng
    giảm dần). Kèm ``recovered`` — mã đã giao dịch lại nhưng trước đó im lặng ≥ ngưỡng,
    vì nhóm này vừa thoát khỏi trạng thái mất thanh khoản và cũng đáng theo dõi.
    """
    untraded = frame[~frame["Traded"].fillna(False)].copy()
    rows = []
    stats: dict = {}
    if history is not None and len(history):
        from .yuanta_history import ticker_stats

        stats = ticker_stats(history, asof=asof)

    for _, row in untraded.iterrows():
        sessions_idle = (stats.get(row["StockCode"]) or {}).get("idleNow")
        flags = []
        if sessions_idle is not None and sessions_idle >= STALE_SESSIONS_WARN:
            flags.append(f"≥{STALE_SESSIONS_WARN} phiên không khớp")
        if row["B1P"] and row["S1P"]:
            spread_abs = float(row["S1P"] - row["B1P"])
            if spread_abs > 0 and row["B1P"] > 0:
                pct = spread_abs / ((row["B1P"] + row["S1P"]) / 2) * 100
                if pct > WIDE_SPREAD_PCT:
                    flags.append(f"spread {pct:.0f}%")
        rows.append({
            "t": row["StockCode"],
            "u": row["Underlying"] if isinstance(row["Underlying"], str) else None,
            "refPrice": _f(row["RefP"]),
            "bid": _f(row["B1P"]),
            "ask": _f(row["S1P"]),
            "sessionsIdle": sessions_idle,
            "flags": flags,
        })
    rows.sort(key=lambda r: (-(r["sessionsIdle"] if r["sessionsIdle"] is not None else -1),
                             r["t"]))

    recovered = []
    if stats:
        traded = frame[frame["Traded"].fillna(False)]
        for _, row in traded.iterrows():
            stat = stats.get(row["StockCode"]) or {}
            gap = stat.get("longestGap") or 0
            if gap >= STALE_SESSIONS_WARN:
                recovered.append({
                    "t": row["StockCode"],
                    "u": row["Underlying"] if isinstance(row["Underlying"], str) else None,
                    "lastPrice": _f(row["LastPrice"]),
                    "valueVND": _f(row["TradingValueVND"], 0),
                    "longestGapSessions": int(gap),
                    "coveragePct": stat.get("coveragePct"),
                })
        recovered.sort(key=lambda r: (-r["longestGapSessions"], -(r["valueVND"] or 0)))

    return {
        "count": int(len(untraded)),
        "sharePct": _f(len(untraded) / len(frame) * 100 if len(frame) else None),
        "thresholdSessions": STALE_SESSIONS_WARN,
        "rows": rows[:limit],
        "recovered": recovered[:limit],
        "recoveredCount": len(recovered),
        "historyAvailable": bool(history is not None and len(history)),
        "note": (
            "Mã không khớp lệnh không có giá đóng cửa của phiên: RefP là giá tham chiếu, "
            "chỉ hiển thị để tham khảo, không dùng làm giá."
        ),
    }


def session_comparison(history: pd.DataFrame | None, *, current_summary: dict | None = None,
                       limit: int = 10) -> dict:
    """So sánh phiên hiện tại với các phiên trước (chỉ khi kho lịch sử đã có ≥ 2 phiên)."""
    if history is None or history.empty or history["session"].nunique() < 2:
        return {
            "available": False,
            "reason": (
                "Cần ≥ 2 phiên trong kho data/cw_history để so sánh. Endpoint không có "
                "lịch sử nên không thể dựng lại quá khứ; dữ liệu sẽ dày lên mỗi ngày "
                "workflow chạy."
            ),
            "sessions": [] if history is None or history.empty
            else sorted(history["session"].unique().tolist()),
        }
    from .yuanta_history import per_session_summary

    sessions = per_session_summary(history)
    rows = sessions[-limit:]
    latest = rows[-1] if rows else None
    previous = rows[-2] if len(rows) >= 2 else None
    delta = None
    if latest and previous:
        def change(key):
            a, b = latest.get(key), previous.get(key)
            if a is None or b is None or not b:
                return None
            return _f((a / b - 1) * 100)
        delta = {
            "valuePct": change("valueVND"),
            "volumePct": change("volume"),
            "tradedDelta": (latest["traded"] - previous["traded"]),
            "gainersDelta": change("gainers"),
        }
    return {
        "available": True,
        "sessions": rows,
        "latest": latest,
        "previous": previous,
        "delta": delta,
        "currentSummary": current_summary,
    }


def _ticker_coverage(history: pd.DataFrame | None, *, asof: str | None = None,
                     limit: int = 20) -> list[dict]:
    """Các mã có dữ liệu lịch sử ít nhất (mẫu số nhỏ thì đừng đọc quá mạnh)."""
    if history is None or history.empty:
        return []
    from .yuanta_history import ticker_stats

    stats = ticker_stats(history, asof=asof)
    rows = [{"t": ticker, **stat} for ticker, stat in stats.items()]
    rows.sort(key=lambda r: (r["coveragePct"], r["sessions"]))
    return rows[:limit]


def _attach_tiers(frame: pd.DataFrame, liquidity: dict) -> pd.DataFrame:
    """Gắn cột ``LiquidityTier`` từ kết quả ``liquidity_ranking`` (không tính lại phân vị)."""
    thresholds = liquidity.get("thresholds") or []
    traded = frame["Traded"].fillna(False)
    tiers = pd.Series("không giao dịch", index=frame.index, dtype="object")
    if traded.any() and thresholds:
        tiers.loc[traded] = assign_tier(
            frame.loc[traded, "TradingValueVND"], thresholds).to_numpy()
    return frame.assign(LiquidityTier=tiers)


def build_analytics(frame: pd.DataFrame, *, history: pd.DataFrame | None = None,
                    terms: pd.DataFrame | None = None,
                    asof: str | None = None) -> dict:
    """Gói toàn bộ phân tích mở rộng thành dict JSON-safe."""
    if frame is None or frame.empty:
        raise ValueError("cần DataFrame bảng giá không rỗng")
    current = frame["TradingValueVND"].sum(min_count=1)
    summary = {
        "valueVND": _f(current, 0),
        "traded": int(frame["Traded"].fillna(False).sum()),
        "untraded": int((~frame["Traded"].fillna(False)).sum()),
    }
    if history is not None and len(history):
        from .yuanta_history import coverage

        cov = coverage(history)
    else:
        cov = {"sessions": 0, "tickers": 0, "first": None, "last": None,
               "missingSessions": [], "rows": 0, "tradedRows": 0,
               "tradedSharePct": None, "provisionalRows": 0, "expectedSessions": 0}
    liquidity = liquidity_ranking(frame)
    # Điểm số dùng chính bảng tier của liquidity (frame đã có cột LiquidityTier) để hai
    # phần không bao giờ nói hai chuyện khác nhau.
    tiered = _attach_tiers(frame, liquidity)

    trade_value = pd.to_numeric(frame["TotalVol"], errors="coerce").where(lambda s: s > 0)
    last_share = (pd.to_numeric(frame["LastMVol"], errors="coerce") / trade_value * 100)

    # Định giá: chỉ chạy khi có bảng điều khoản. Thiếu điều khoản thì `priced` rỗng và
    # `valuation.available=False` giữ nguyên lý do — không được im lặng bỏ qua.
    priced, valuation_diag = pd.DataFrame(), {"available": False,
                                              "reason": "Chưa nạp điều khoản hợp đồng."}
    if terms is not None and not terms.empty and asof:
        priced, valuation_diag = price_warrants(frame, terms, session=asof)

    return {
        "schemaVersion": 1,
        "kind": "yuanta-cw-analytics",
        "asof": asof,
        "liquidity": liquidity,
        "valuation": {
            **valuation_diag,
            "summary": summarize_valuation(priced),
            # replace({nan: None}) chứ không phải to_dict thô: pandas để NaN cho nhóm quá
            # nhỏ, và NaN không phải JSON hợp lệ (json.dumps mặc định allow_nan=False).
            # NaN ở đây có nghĩa "không xác định", không phải "bằng 0".
            "warrants": (priced.sort_values("ivResidualPct", na_position="last")
                         .replace({np.nan: None}).to_dict(orient="records")
                         if len(priced) else []),
        },
        "scoring": score_warrants(tiered, history=history, last_share=last_share,
                                  priced=priced if len(priced) else None,
                                  valuation_diagnostics=valuation_diag),
        "underlyings": underlying_breakdown(frame),
        "stale": stale_monitor(frame, history, asof=asof),
        "tickerCoverage": _ticker_coverage(history, asof=asof),
        "sessions": session_comparison(history, current_summary=summary),
        "historyCoverage": cov,
        # Bốn khối dưới đây dùng đúng ngữ nghĩa payload: RefP = giá đóng cửa phiên trước,
        # CeilingP/FloorP = dải trần–sàn (không suy ra công thức), LastMVol = khối lượng
        # lệnh khớp cuối. Tất cả đều mô tả phiên đã xảy ra, không dự báo.
        "intraday": intraday_moves(frame),
        "priceBand": price_band_profile(frame),
        "lastTrade": last_trade_profile(frame),
        "refContinuity": ref_continuity(frame, history),
        "caveats": [
            "Nhóm thanh khoản dùng phân vị của chính snapshot, không phải ngưỡng VND cố định.",
            "Mã không khớp lệnh không có OHLC của phiên; RefP không được dùng làm giá.",
            "RefP là giá đóng cửa phiên trước, nên % thay đổi và kiểm tra liên tục dùng RefP làm mốc.",
            "CeilingP/FloorP đọc trực tiếp từ nguồn; tỷ lệ dải trần–sàn không cố định nên không dùng ±7%.",
            "Biến động trong phiên là mô tả phiên đã xảy ra, không phải tín hiệu hay dự báo.",
            "So sánh nhiều phiên chỉ có khi kho data/cw_history đã tích luỹ ≥ 2 phiên.",
            "Không có định giá, Greeks hay khuyến nghị: nguồn không có strike/hạn mức/chuỗi quá khứ.",
        ],
    }
