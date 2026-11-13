"""Biến động trong phiên, dải trần–sàn và kiểm tra tính liên tục của `RefP`.

Bốn nhóm phân tích ở đây đều dựa trên hiểu biết về ngữ nghĩa payload đã được xác nhận:

``RefP``
    Giá tham chiếu = **giá đóng cửa phiên trước** của chính chứng quyền đó. Vì thế mỗi bar
    có sẵn một mốc so sánh, không cần chờ 2 phiên mới tính được % thay đổi. Đây cũng là
    chốt kiểm tra tính liên tục: nếu ``RefP`` của phiên hôm nay khác ``close`` của phiên
    liền trước trong kho, hoặc phiên liền trước không có trong kho, thì ta biết dữ liệu
    không liền mạch — và biết chính xác đứt ở đâu.

``CeilingP`` / ``FloorP``
    Giá trần/sàn của phiên. Dải này **không** phải ±7% cố định; tỷ lệ thực tế trong một
    snapshot thật trải từ ~14% đến vài nghìn phần trăm. Vì vậy không bao giờ suy ra dải
    bằng công thức — luôn đọc đúng số nguồn trả về, và chỉ dùng nó để đo xem giá còn cách
    biên bao xa.

``LastMVol``
    Khối lượng của riêng lệnh khớp cuối. Chia cho ``TotalVol`` cho biết thanh khoản tập
    trung vào bao nhiêu lệnh — hữu ích để đọc chất lượng giá đóng cửa, không phải để dự báo.

Mọi hàm ở đây chỉ mô tả dữ liệu đã có. Không định giá, không Greeks, không dự báo.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

#: Bước giá của CW niêm yết dưới 10.000 VND. Dùng để quy spread/chênh lệch ra "số bước giá".
CW_TICK_VND = 10.0

#: |RefP / close(phiên trước) − 1| vượt ngưỡng này (%) là bất thường → nghi đứt dữ liệu.
#: Một số CW thật sự tăng/giảm hơn 20% trong một phiên, nên ngưỡng được đặt rộng để tránh
#: báo động giả; mục đích là phát hiện lỗ hổng, không phải bắt biến động.
REF_CONTINUITY_TOLERANCE_PCT = 25.0

#: Chênh lệch giá thấp hơn nửa bước giá coi như khớp (làm tròn số nguồn).
_TICK_EPSILON = CW_TICK_VND / 2


def _f(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(out) else round(out, digits)


def _nz(series: pd.Series) -> pd.Series:
    """Series số dương, các giá trị ≤ 0 hoặc NaN thành NaN (tránh chia cho 0)."""
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.where(numeric > 0)


# ──────────────────────────────────────────────────────────────────
# 1. BIẾN ĐỘNG TRONG PHIÊN
# ──────────────────────────────────────────────────────────────────
def intraday_moves(frame: pd.DataFrame, *, limit: int = 15) -> dict:
    """Đo biên độ trong phiên của các mã có khớp lệnh.

    ``rangePct`` = (cao − thấp) / giá tham chiếu. Chia cho ``RefP`` chứ không cho giá mở
    cửa, vì ``RefP`` là mốc chung của cả phiên (giá đóng cửa hôm qua) nên so sánh được
    giữa các mã, kể cả mã mở cửa đã nhảy gap.

    ``closeLocation`` = vị trí giá đóng cửa trong khoảng [thấp, cao], 0 = đóng ở đáy,
    1 = đóng ở đỉnh. Đây là số **mô tả** phiên đã xảy ra, không phải tín hiệu.
    """
    traded = frame[frame["Traded"].fillna(False)].copy()
    if traded.empty:
        return {
            "available": False,
            "reason": "Không có mã nào khớp lệnh trong snapshot này.",
            "rows": [], "summary": {},
        }

    ref = _nz(traded["RefP"])
    high = pd.to_numeric(traded["HighestP"], errors="coerce")
    low = pd.to_numeric(traded["LowestP"], errors="coerce")
    close = pd.to_numeric(traded["LastPrice"], errors="coerce")

    traded = traded.assign(
        moveRangePct=((high - low) / ref * 100).where(high.notna() & low.notna()),
        moveRangeVND=(high - low).where(high.notna() & low.notna()),
    )
    # Vị trí close trong biên độ; biên độ 0 (đứng giá cả phiên) → không xác định.
    span = (high - low)
    traded["moveCloseLocation"] = ((close - low) / span.where(span > 0)).clip(0, 1)

    ranked = traded.sort_values("moveRangePct", ascending=False, kind="stable").head(limit)
    rows = []
    for row in ranked.itertuples(index=False):
        rows.append({
            "t": getattr(row, "StockCode"),
            "u": getattr(row, "Underlying") if isinstance(getattr(row, "Underlying"), str) else None,
            "ref": _f(getattr(row, "RefP")),
            "open": _f(getattr(row, "OpenP")),
            "high": _f(getattr(row, "HighestP")),
            "low": _f(getattr(row, "LowestP")),
            "close": _f(getattr(row, "LastPrice")),
            "rangeVND": _f(getattr(row, "moveRangeVND")),
            "rangePct": _f(getattr(row, "moveRangePct")),
            "rangeTicks": _f(getattr(row, "moveRangeVND") / CW_TICK_VND
                             if pd.notna(getattr(row, "moveRangeVND")) else None, 1),
            "closeLocation": _f(getattr(row, "moveCloseLocation")),
            "chgPct": _f(getattr(row, "PriceChangePct")),
            "valueVND": _f(getattr(row, "TradingValueVND"), 0),
        })

    # Chỉ tính "đóng cửa ở nửa trên/dưới" trên các mã thật sự có biên độ.
    located = traded[traded["moveCloseLocation"].notna()]
    summary = {
        "medianRangePct": _f(traded["moveRangePct"].median()),
        "medianRangeTicks": _f((traded["moveRangeVND"] / CW_TICK_VND).median(), 1),
        "countFlatSession": int((traded["moveRangeVND"].fillna(np.nan) == 0).sum()),
        "countCloseInUpperHalf": int((located["moveCloseLocation"] >= 0.5).sum()),
        "countCloseInLowerHalf": int((located["moveCloseLocation"] < 0.5).sum()),
        "closeLocationBasis": (
            "Vị trí giá đóng cửa trong khoảng [LowestP, HighestP]. 0 = đóng ở đáy, "
            "1 = đóng ở đỉnh. Mô tả phiên đã xảy ra, không phải tín hiệu."
        ),
    }
    return {"available": True, "rows": rows, "summary": summary}


# ──────────────────────────────────────────────────────────────────
# 2. DẢI TRẦN – SÀN
# ──────────────────────────────────────────────────────────────────
def price_band_profile(frame: pd.DataFrame, *, limit: int = 15) -> dict:
    """Khoảng cách từ giá hiện tại tới trần/sàn, và các mã đã chạm biên.

    Dải trần–sàn **không** được suy ra bằng công thức: ``CeilingP``/``FloorP`` đọc thẳng từ
    nguồn. Tỷ lệ (``bandPct``) được tính ngược lại chỉ để mô tả, và chính vì nó thay đổi
    theo giá nên mới không thể hard-code ±7%.
    """
    if frame is None or frame.empty:
        return {"available": False, "reason": "Bảng giá rỗng.", "rows": [], "summary": {}}

    ceil = _nz(frame["CeilingP"])
    floor = _nz(frame["FloorP"])
    ref = _nz(frame["RefP"])
    traded = frame["Traded"].fillna(False)

    # Giá dùng để đo khoảng cách: giá khớp cuối nếu có giao dịch, ngược lại là giá tham chiếu.
    # Không dùng LastMP của phiên cũ cho mã không giao dịch (sẽ tạo khoảng cách giả).
    mark = pd.to_numeric(frame["LastPrice"], errors="coerce").where(traded, ref)

    band_pct = (ceil / floor - 1) * 100
    to_ceiling = (ceil / mark - 1) * 100
    to_floor = (1 - floor / mark) * 100

    prof = frame.assign(
        bandPctCalc=band_pct,
        toCeilingCalc=to_ceiling.where(mark.notna()),
        toFloorCalc=to_floor.where(mark.notna()),
        hitCeiling=traded & (pd.to_numeric(frame["HighestP"], errors="coerce") >= ceil),
        hitFloor=traded & (pd.to_numeric(frame["LowestP"], errors="coerce") <= floor),
    )

    at_ceiling = prof[prof["hitCeiling"]]
    at_floor = prof[prof["hitFloor"]]

    # Mã còn ít dư địa tới trần: khoảng cách tuyệt đối < 1 bước giá là gần như đã chạm.
    # toCeilingPct tính theo `mark` nên quy ngược ra VND phải nhân với chính `mark`.
    distance_to_ceiling_vnd = (prof["CeilingP"] - mark).abs()
    near = prof[traded & distance_to_ceiling_vnd.le(CW_TICK_VND + _TICK_EPSILON)]
    ranked = prof[traded].sort_values("toCeilingCalc", ascending=True, kind="stable").head(limit)

    rows = []
    for row in ranked.itertuples(index=False):
        rows.append({
            "t": getattr(row, "StockCode"),
            "u": getattr(row, "Underlying") if isinstance(getattr(row, "Underlying"), str) else None,
            "ref": _f(getattr(row, "RefP")),
            "floor": _f(getattr(row, "FloorP")),
            "ceiling": _f(getattr(row, "CeilingP")),
            "close": _f(getattr(row, "LastPrice")),
            "bandPct": _f(getattr(row, "bandPctCalc"), 1),
            "toCeilingPct": _f(getattr(row, "toCeilingCalc")),
            "toCeilingTicks": _f((getattr(row, "CeilingP") - getattr(row, "LastPrice")) / CW_TICK_VND
                                 if pd.notna(getattr(row, "LastPrice")) else None, 1),
            "toFloorPct": _f(getattr(row, "toFloorCalc")),
            "atCeiling": bool(getattr(row, "hitCeiling")),
            "atFloor": bool(getattr(row, "hitFloor")),
        })

    summary = {
        "medianBandPct": _f(band_pct.median(), 1),
        "minBandPct": _f(band_pct.min(), 1),
        "maxBandPct": _f(band_pct.max(), 1),
        "countAtCeiling": int(len(at_ceiling)),
        "countAtFloor": int(len(at_floor)),
        "countNearCeiling": int(len(near)),
        "atCeiling": [str(t) for t in at_ceiling["StockCode"].tolist()[:20]],
        "atFloor": [str(t) for t in at_floor["StockCode"].tolist()[:20]],
        "bandBasis": (
            "CeilingP/FloorP đọc trực tiếp từ nguồn, không suy ra bằng công thức ±7%. Tỷ lệ "
            "dải rất rộng khi giá CW xuống gần bước giá tối thiểu (FloorP = 10 VND), nên "
            "'bandPct' chỉ để mô tả, không phải biên độ rủi ro."
        ),
    }
    return {"available": True, "rows": rows, "summary": summary}


# ──────────────────────────────────────────────────────────────────
# 3. CHẤT LƯỢNG LỆNH KHỚP CUỐI
# ──────────────────────────────────────────────────────────────────
def last_trade_profile(frame: pd.DataFrame, *, limit: int = 15) -> dict:
    """``LastMVol`` (khối lượng lệnh khớp cuối) so với ``TotalVol`` của cả phiên.

    Giá đóng cửa do đúng một lệnh quyết định (100% khối lượng) là chuyện bình thường với
    CW, nhưng khi đó giá đóng cửa kém đại diện cho cả phiên. Chỉ số này đo đúng điều đó —
    không phải để dự báo, mà để người đọc biết nên tin giá đóng cửa tới đâu.
    """
    traded = frame[frame["Traded"].fillna(False)].copy()
    if traded.empty:
        return {"available": False, "reason": "Không có mã nào khớp lệnh trong snapshot này.",
                "rows": [], "summary": {}}

    total = _nz(traded["TotalVol"])
    last_vol = pd.to_numeric(traded["LastMVol"], errors="coerce")
    traded = traded.assign(
        lastShareCalc=(last_vol / total * 100).where(last_vol.notna() & total.notna()),
    )
    share = traded["lastShareCalc"].dropna()

    concentrated = traded[traded["lastShareCalc"] >= 99.999]
    ranked = traded.sort_values("lastShareCalc", ascending=False, kind="stable").head(limit)
    rows = []
    for row in ranked.itertuples(index=False):
        rows.append({
            "t": getattr(row, "StockCode"),
            "close": _f(getattr(row, "LastPrice")),
            "lastTradeVol": _f(getattr(row, "LastMVol"), 0),
            "volume": _f(getattr(row, "TotalVol"), 0),
            "lastSharePct": _f(getattr(row, "lastShareCalc"), 1),
            "valueVND": _f(getattr(row, "TradingValueVND"), 0),
        })

    return {
        "available": True,
        "rows": rows,
        "summary": {
            "medianLastSharePct": _f(share.median(), 1),
            "countSingleTradeClose": int(len(concentrated)),
            "countTraded": int(len(traded)),
            "singleTradeSharePct": _f(len(concentrated) / len(traded) * 100, 1) if len(traded) else None,
            "basis": (
                "LastMVol/TotalVol. Tỷ lệ cao nghĩa là giá đóng cửa do một lệnh nhỏ quyết định, "
                "nên kém đại diện cho cả phiên."
            ),
        },
    }


# ──────────────────────────────────────────────────────────────────
# 4. TÍNH LIÊN TỤC: RefP CÓ KHỚP CLOSE PHIÊN TRƯỚC?
# ──────────────────────────────────────────────────────────────────
def ref_continuity(frame: pd.DataFrame, history: pd.DataFrame | None) -> dict:
    """Dùng ``RefP`` để kiểm chứng kho dữ liệu — phép kiểm tra chỉ có thể làm được nhờ

    ``RefP`` = giá đóng cửa phiên trước. Với mỗi mã, so ``RefP`` hôm nay với ``close`` của
    phiên gần nhất có trong kho. Ba kết luận có thể có, và chúng khác nhau về bản chất:

    ``linked``
        Phiên gần nhất trong kho là phiên liền trước **và** ``RefP`` khớp ``close`` → dữ
        liệu liền mạch, chuỗi giá không đứt.
    ``missingSession``
        Phiên gần nhất trong kho **không** phải phiên liền trước → có phiên bị mất ở giữa.
        Đây là chẩn đoán đáng tin nhất, vì nó không phụ thuộc việc so giá.
    ``mismatch``
        Có phiên liền trước nhưng ``RefP`` lệch ``close`` quá ngưỡng → nghi bar phiên trước
        không phải giá đóng cửa thật (hoặc nguồn đã điều chỉnh).
    ``untradedRef``
        Phiên trước mã không khớp lệnh nên không có ``close`` để so; ``RefP`` vẫn là mốc
        duy nhất và được ghi nhận nhưng không kết luận.
    """
    empty = {
        "available": False,
        "reason": "Chưa có kho lịch sử (cần ≥ 1 phiên đã ghi).",
        "rows": [], "summary": {},
    }
    if history is None or history.empty:
        return empty
    if frame is None or frame.empty:
        return {**empty, "reason": "Bảng giá rỗng."}

    session_col = history["session"].astype(str)
    sessions = sorted(session_col.unique())
    current = str(frame["FetchedAt"].iloc[0])[:10] if "FetchedAt" in frame.columns else None
    if current is None:
        return {**empty, "reason": "Bảng giá thiếu FetchedAt để xác định phiên."}

    from .yuanta_history import resolve_session  # tránh vòng import khi module nạp

    try:
        snapshot = resolve_session(frame["FetchedAt"].iloc[0])
    except Exception as exc:  # noqa: BLE001 - chẩn đoán thay vì crash
        return {**empty, "reason": f"Không xác định được phiên: {exc}"}
    session = snapshot.iso

    earlier = [s for s in sessions if s < session]
    if not earlier:
        return {
            "available": False,
            "reason": (f"Phiên {session} là phiên đầu tiên trong kho — chưa có phiên trước "
                       "để đối chiếu RefP."),
            "rows": [], "summary": {},
        }

    previous = earlier[-1]

    # Phiên gần nhất trong kho có thật sự là phiên LIỀN TRƯỚC không? Nếu không, đó là bằng
    # chứng trực tiếp của một phiên bị mất — độc lập với việc so giá, nên phải kiểm tra
    # riêng. (Chỉ so RefP với close có thể vẫn "khớp" khi RefP tình cờ bằng close của phiên
    # cách đó vài ngày, và như vậy sẽ báo liền mạch sai.)
    from datetime import date as _date, timedelta as _timedelta

    from . import sessions as session_calendar

    # Phiên liền trước thật của `session`: phiên gần nhất *trước* ngày hôm nay. Lùi 10 ngày
    # lịch là đủ để vượt qua cuối tuần và các kỳ nghỉ lễ thường gặp.
    session_day = _date.fromisoformat(session)
    candidates = [d for d in session_calendar.sessions_between(
        session_day - _timedelta(days=10), session_day) if d < session_day]
    expected_previous = candidates[-1] if candidates else None
    # Kho có đúng phiên liền trước không? Nếu không → chắc chắn có phiên bị mất ở giữa,
    # bất kể giá có tình cờ khớp hay không.
    session_break = bool(
        expected_previous is not None
        and previous != expected_previous.isoformat()
    )
    missing_in_between = [d.isoformat() for d in
                          session_calendar.sessions_between(previous, session)
                          if d.isoformat() != session]

    prev_rows = history[history["session"].astype(str) == previous].set_index("ticker")
    rows = []
    counts = {"linked": 0, "missingSession": 0, "mismatch": 0, "untradedRef": 0, "noRef": 0}

    for row in frame.itertuples(index=False):
        ticker = str(getattr(row, "StockCode"))
        ref = _f(getattr(row, "RefP"))
        if ref is None or ref <= 0:
            counts["noRef"] += 1
            continue
        if ticker not in prev_rows.index:
            counts["missingSession"] += 1
            rows.append({"t": ticker, "prevSession": previous, "ref": ref,
                         "prevClose": None, "diffPct": None,
                         "status": "missingSession",
                         "note": "Mã không có trong kho ở phiên trước."})
            continue

        prev = prev_rows.loc[ticker]
        prev_close = None if pd.isna(prev.get("close")) else _f(prev.get("close"))
        if prev_close is None or prev_close <= 0:
            counts["untradedRef"] += 1
            rows.append({"t": ticker, "prevSession": previous, "ref": ref,
                         "prevClose": None, "diffPct": None,
                         "status": "untradedRef",
                         "note": "Phiên trước không khớp lệnh → không có close để so."})
            continue

        diff_pct = (ref / prev_close - 1) * 100
        if session_break:
            # Phiên liền trước không có trong kho: giá có khớp cũng KHÔNG phải liền mạch,
            # vì còn một phiên ở giữa chưa được ghi.
            counts["missingSession"] += 1
            rows.append({"t": ticker, "prevSession": previous, "ref": ref,
                         "prevClose": prev_close, "diffPct": _f(diff_pct),
                         "status": "missingSession",
                         "note": (f"Phiên liền trước ({expected_previous}) không có trong "
                                  f"kho; đang so với {previous}.")})
        elif abs(diff_pct) > REF_CONTINUITY_TOLERANCE_PCT:
            counts["mismatch"] += 1
            rows.append({"t": ticker, "prevSession": previous, "ref": ref,
                         "prevClose": prev_close, "diffPct": _f(diff_pct),
                         "status": "mismatch",
                         "note": "RefP lệch close phiên trước quá ngưỡng."})
        else:
            counts["linked"] += 1

    checked = len(frame)
    linked_pct = _f(counts["linked"] / checked * 100, 1) if checked else None
    return {
        "available": True,
        "prevSession": previous,
        "expectedPrevSession": expected_previous.isoformat() if expected_previous else None,
        "missingSessionsBeforeCurrent": missing_in_between,
        "rows": rows[:60],
        "summary": {
            "checked": checked,
            **counts,
            "sessionBreak": bool(session_break),
            "missingSessionsBeforeCurrent": missing_in_between,
            "linkedPct": linked_pct,
            "tolerancePct": REF_CONTINUITY_TOLERANCE_PCT,
            "verdict": (
                "Liền mạch" if counts["missingSession"] == 0 and counts["mismatch"] == 0
                else "Có đứt gãy — xem chi tiết từng mã"
            ),
            "basis": (
                "RefP là giá đóng cửa phiên trước, nên so RefP với close của phiên liền trước "
                "trong kho là phép kiểm tra trực tiếp xem dữ liệu có liền mạch. Đây là kiểm "
                "tra dữ liệu, không phải chỉ báo giao dịch."
            ),
        },
    }
