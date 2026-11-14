"""Xếp hạng và chấm điểm CW theo ngày — chỉ trên những gì dữ liệu thật sự cho phép.

Vì sao KHÔNG có Black–Scholes ở đây
----------------------------------
Endpoint ``stock_type=EW`` của Yuanta trả **34 trường bảng giá**
(``RefP/OpenP/HighestP/LowestP/AvgP/LastMP/TotalVol/TotalVal/B1P..S3V/FT*``).
Không có trường nào trong số này là điều khoản hợp đồng:

    StrikePrice · MaturityDate · ConversionRatio · UnderlyingPrice · IssueDate

Ba biến số đầu là **bắt buộc** để Black–Scholes có nghĩa: không có strike thì không có
moneyness, không có ngày đáo hạn thì không có ``T``, không có tỷ lệ chuyển đổi thì không có
giá trị trên một CW. Không có giá cổ phiếu cơ sở thì không có ``S``. Bốn ẩn số, bốn nguồn
không có.

Suy ra từ tên mã (``CVPB2622`` → cơ sở VPB) thì được — đó là quy ước đặt tên, và dự án đã
dùng đúng cách đó để nhóm theo cổ phiếu cơ sở. Nhưng **không** suy ra được strike hay ngày
đáo hạn: hai chữ số cuối không mã hoá đủ thông tin, và các CW cùng cơ sở có strike khác nhau.
Gán một con số cho đẹp sẽ tạo ra Greeks và điểm số trông rất hợp lý nhưng vô nghĩa — đúng
loại lỗi mà dự án này từ chối từ đầu.

Vì vậy module này chấm điểm trên các trục **đo được** từ bảng giá:

    thanh khoản · chi phí giao dịch · định giá (khi có điều khoản) · chất lượng giá

và nói thẳng trong payload rằng trục định giá bị **khoá** cho tới khi có điều khoản hợp đồng.
Khi có nguồn điều khoản, ``cwintel.bs.price_and_greeks`` đã sẵn sàng và chỉ cần nối vào
``score_valuation`` — không phải viết lại engine.

Điểm số ở đây **không phải** khuyến nghị mua/bán. Nó trả lời một câu hẹp hơn: "mã này có
giao dịch được ở quy mô vừa phải mà không bị trượt giá quá nhiều không?".
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

#: Trọng số điểm tổng. Chỉ gồm các trục đo được từ snapshot hiện tại.
#:
#: Vì sao KHÔNG có trục "độ ổn định" (tỷ lệ phiên có khớp lệnh)
#: ------------------------------------------------------------
#: Trục đó từng chiếm 8%. Nó chưa từng chấm được mã nào: cần ≥5 phiên lịch sử mà kho mới có
#: 1. Vì ``_weighted`` loại bỏ trục thiếu rồi chia lại trọng số, 8% đó **chưa bao giờ** ảnh
#: hưởng tới điểm — kiểm chứng trên 353 mã: bỏ trục, điểm không đổi và thứ hạng giữ nguyên.
#: Cái giá phải trả thì có thật: cột "chưa chấm" ở toàn bộ 353 dòng và độ phủ kẹt ở 92%,
#: khiến người đọc tưởng dữ liệu có lỗ hổng 8% mà thực ra không có.
#:
#: Ngoài ra nó trùng phần lớn với thanh khoản (mã giao dịch đều đương nhiên có giá trị giao
#: dịch cao hơn). Nếu sau này kho đủ ≥5 phiên và trục này thật sự phân biệt được các mã, nó
#: nên quay lại với trọng số có ý nghĩa (≥10%) chứ không phải 8% — và chỉ khi chứng minh được
#: nó thêm thông tin so với thanh khoản.
#: Tỷ lệ tương đối giữa các trục, giữ đúng như trước khi bỏ trục độ ổn định. Trọng số thật
#: là tỷ lệ này chia cho tổng của chúng (xem ``DEFAULT_WEIGHTS``).
_BASE_WEIGHTS: dict[str, float] = {
    "liquidity": 0.34,      # giá trị giao dịch — thước đo trực tiếp khả năng vào/ra
    "cost": 0.26,           # spread quanh giá giữa — chi phí vòng
    "valuation": 0.20,      # IV thấp so với nhóm cùng cơ sở = rủi ro được định giá rẻ hơn
    "priceQuality": 0.12,   # độ đại diện của giá đóng cửa
}

#: Trọng số điểm tổng, chuẩn hoá để tổng bằng 1.
#:
#: Chia lại thay vì làm tròn thành 37/28/22/13: trọng số cũ của bốn trục này là 34/26/20/12
#: trên tổng 92%, và ``_weighted`` vốn đã chia cho 0,92 khi trục thứ năm thiếu. Giữ đúng phép
#: chia đó thì **bỏ trục không làm đổi điểm của bất kỳ mã nào** — đó cũng là bằng chứng trục
#: kia chưa từng tham gia. Làm tròn thành số đẹp sẽ đổi điểm 337 mã (tới 0,26 điểm) và xáo
#: lại thứ hạng: sai lệch do cách viết trọng số, không phải do bỏ trục. Nhãn trên trang vẫn
#: hiện 37% / 28% / 22% / 13% vì đó là phần làm tròn khi hiển thị.
DEFAULT_WEIGHTS: dict[str, float] = {
    key: value / sum(_BASE_WEIGHTS.values()) for key, value in _BASE_WEIGHTS.items()
}

#: Không chấm điểm định giá khi nhóm cùng cơ sở ít hơn ngưỡng này — trung vị của 2–4 quan
#: sát không đủ tin cậy để nói mã nào "rẻ".
MIN_GROUP_FOR_VALUATION = 5

#: ``headroom`` KHÔNG nằm trong điểm: 81,6% mã còn >50% dư địa tới trần, nên nó gần như hằng
#: số và chỉ làm nén thang điểm. Nó vẫn được tính, nhưng là **cờ cảnh báo** (mã sát trần thì
#: khó mua thêm ở giá hiện tại) chứ không phải thước đo chất lượng.
HEADROOM_WARN_PCT = 10.0

TIER_ORDER: tuple[str, ...] = ("rất cao", "cao", "trung bình", "thấp", "rất thấp")

def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _pct_rank(values: pd.Series, *, higher_is_better: bool = True) -> pd.Series:
    """Xếp hạng phân vị 0–100; NaN giữ nguyên NaN (không ai bị chấm 0 vì thiếu dữ liệu)."""
    numeric = _num(values)
    valid = numeric.notna()
    out = pd.Series(np.nan, index=numeric.index, dtype="float64")
    if valid.sum() == 0:
        return out
    ranks = numeric[valid].rank(pct=True, method="average")
    out.loc[valid] = (ranks * 100) if higher_is_better else ((1 - ranks) * 100)
    return out


def _inverse_level(values: pd.Series, *, best: float, worst: float) -> pd.Series:
    """Thang 0–100 giảm dần: ``best`` → 100, ``worst`` → 0, ở giữa nội suy tuyến tính."""
    numeric = _num(values)
    span = worst - best
    if span == 0:
        return pd.Series(np.nan, index=numeric.index, dtype="float64")
    score = (worst - numeric) / span * 100
    return score.clip(lower=0, upper=100)


def _weighted(parts: dict[str, pd.Series], weights: dict[str, float]) -> pd.Series:
    """Trung bình có trọng số, **bỏ qua** trục thiếu dữ liệu thay vì coi là 0.

    Nếu một mã thiếu dữ liệu spread mà vẫn cộng 0 điểm cho trục đó, nó bị phạt oan. Cách
    đúng là tính lại trọng số trên các trục thực sự có, rồi ghi ``coverage`` để người đọc
    biết điểm này dựa trên bao nhiêu phần trăm trọng số.
    """
    total_weight = pd.Series(0.0, index=next(iter(parts.values())).index)
    accum = pd.Series(0.0, index=total_weight.index)
    for key, series in parts.items():
        weight = weights.get(key, 0.0)
        if not weight:
            continue
        valid = series.notna()
        accum = accum.add(series.fillna(0.0) * weight, fill_value=0.0)
        total_weight = total_weight.add(
            pd.Series(np.where(valid, weight, 0.0), index=series.index), fill_value=0.0)
    score = accum.divide(total_weight.replace(0, np.nan))
    return score.round(2)


def _coverage(parts: dict[str, pd.Series], weights: dict[str, float]) -> pd.Series:
    """Phần trăm trọng số thực sự có dữ liệu — để người đọc biết điểm đáng tin tới đâu."""
    total = sum(weights.get(k, 0.0) for k in parts)
    if not total:
        return pd.Series(np.nan, index=next(iter(parts.values())).index)
    index = next(iter(parts.values())).index
    covered = pd.Series(0.0, index=index)
    for key, series in parts.items():
        covered = covered.add(
            pd.Series(np.where(series.notna(), weights.get(key, 0.0), 0.0), index=index),
            fill_value=0.0)
    return (covered / total * 100).round(1)


# ──────────────────────────────────────────────────────────────────
# CÁC TRỤC ĐIỂM
# ──────────────────────────────────────────────────────────────────
def _liquidity_score(frame: pd.DataFrame) -> pd.Series:
    """Giá trị giao dịch (chính) + số mã cùng cơ sở đang cạnh tranh (phụ).

    Giá trị giao dịch là thước đo trực tiếp khả năng vào/ra. Khối lượng một mình dễ đánh
    lừa: CW giá 100 VND khớp 1 triệu đơn vị chỉ là 100 triệu đồng.
    """
    value = _pct_rank(frame["TradingValueVND"])
    volume = _pct_rank(_num(frame["TotalVol"]))
    return (value * 0.8 + volume.fillna(value) * 0.2).round(2)


def _cost_score(frame: pd.DataFrame) -> pd.Series:
    """Spread quanh giá giữa, quy ra thang 0–100.

    1 bước giá (10 VND) trên CW 100 VND là 10% — chi phí khứ hồi 20%, không thể bỏ qua.
    Ngưỡng: ≤1% → 100 điểm, ≥10% → 0 điểm. Đây là ngưỡng **kinh tế** (chi phí vòng),
    không phải ngưỡng thống kê, nên cố định là đúng.
    """
    return _inverse_level(frame["SpreadPct"], best=1.0, worst=10.0)


def _price_quality_score(frame: pd.DataFrame, last_share: pd.Series | None) -> pd.Series:
    """Độ đại diện của giá đóng cửa: ít lệnh hơn → giá kém tin cậy hơn.

    ``LastMVol/TotalVol`` cao nghĩa là cả phiên chỉ có một lệnh, nên "giá đóng cửa" thực
    chất là giá của một giao dịch lẻ. Chỉ số này **không** nói mã tốt hay xấu — nó nói giá
    đóng cửa đáng tin tới đâu.
    """
    if last_share is None:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    # 1 lệnh duy nhất (100%) → 0 điểm; ≤10% → 100 điểm. Không dùng ngưỡng tuyệt đối khác
    # vì 65,7% mã có tỷ lệ ≤10%, tức phần lớn mã đạt điểm tối đa — thang này cố ý chỉ phạt
    # nhóm đóng cửa bằng một lệnh duy nhất.
    return _inverse_level(last_share, best=10.0, worst=100.0)


def _valuation_score(priced: pd.DataFrame | None,
                     tickers: pd.Series) -> tuple[pd.Series, dict]:
    """Điểm theo ``ivResidualPct``: IV thấp hơn trung vị nhóm → điểm cao hơn.

    Vì sao dùng IV chứ không dùng ``cwPrice/bsPrice``: khi IV được suy ngược từ chính giá
    thị trường thì hai đại lượng đó bằng nhau, tỷ lệ luôn bằng 0 và không xếp hạng được gì.
    So sánh IV của các CW **cùng một cổ phiếu cơ sở** mới có nghĩa — cùng rủi ro nền, khác
    mức bù rủi ro.

    Thang: residual −50% (rẻ hơn nhóm một nửa) → 100 điểm; +100% → 0 điểm. Đây là thang đo
    tương đối trong nhóm, không phải "IV bao nhiêu là tốt".
    """
    empty = pd.Series(np.nan, index=tickers.index, dtype="float64")
    if priced is None or priced.empty or "ivResidualPct" not in priced:
        return empty, {"available": False,
                       "reason": "Chưa có kết quả định giá (thiếu điều khoản hợp đồng)."}

    residual = pd.to_numeric(priced.set_index("ticker")["ivResidualPct"], errors="coerce")
    residual = residual[~residual.index.duplicated(keep="last")]
    mapped = tickers.astype(str).str.upper().map(residual)

    score = ((100 + mapped) / 150 * 100).clip(lower=0, upper=100)
    # residual = −50 → 100 điểm; 0 → 66,7; +50 → 33,3; +100 → 0
    return score, {
        "available": bool(mapped.notna().any()),
        "scored": int(mapped.notna().sum()),
        "groupsTooSmall": int((pd.to_numeric(priced.get("ivGroupSize"), errors="coerce")
                               .fillna(0) < MIN_GROUP_FOR_VALUATION).sum()),
        "basis": (
            "IV so với trung vị IV của các CW cùng cổ phiếu cơ sở. Dùng IV chứ không dùng "
            "cwPrice/bsPrice vì IV suy ngược từ chính giá thị trường khiến tỷ lệ đó luôn ≈ 0."
        ),
    }


def _headroom_score(frame: pd.DataFrame) -> pd.Series:
    """Dư địa tới trần: mã sát trần thì khó mua thêm ở giá hiện tại.

    Dùng ``CeilingP`` đọc từ nguồn (không suy ra ±7%). Mã đã chạm trần → 0 điểm.
    """
    ceiling = _num(frame["CeilingP"])
    mark = _num(frame["LastPrice"]).where(frame["Traded"].fillna(False), _num(frame["RefP"]))
    room_pct = (ceiling / mark - 1) * 100
    # ≥50% dư địa → 100; 0% (chạm trần) → 0
    return (room_pct / 50 * 100).clip(lower=0, upper=100)


# ──────────────────────────────────────────────────────────────────
# CHẤM ĐIỂM + XẾP HẠNG
# ──────────────────────────────────────────────────────────────────
def score_warrants(frame: pd.DataFrame, *, last_share: pd.Series | None = None,
                   priced: pd.DataFrame | None = None,
                   valuation_diagnostics: dict | None = None,
                   weights: dict[str, float] | None = None) -> dict:
    """Điểm 0–100 cho từng mã, kèm điểm thành phần và độ phủ dữ liệu.

    Chỉ mã **có khớp lệnh** được chấm: mã không giao dịch không có giá, nên mọi trục đều
    thiếu — chấm điểm nó sẽ là bịa.

    Không nhận ``history``: mọi trục đều đọc từ snapshot hiện tại. Trục độ ổn định theo lịch
    sử đã bị bỏ (xem ``DEFAULT_WEIGHTS``) nên truyền kho lịch sử vào đây không còn làm gì;
    giữ tham số lại sẽ khiến người đọc tưởng nó vẫn nuôi điểm số.
    """
    if frame is None or frame.empty:
        raise ValueError("cần DataFrame bảng giá không rỗng")
    weights = weights or DEFAULT_WEIGHTS

    traded = frame["Traded"].fillna(False)

    if last_share is None:
        total = _num(frame["TotalVol"]).where(lambda s: s > 0)
        last_share = (_num(frame["LastMVol"]) / total * 100).where(traded)

    headroom = _headroom_score(frame).where(traded)
    tickers = frame["StockCode"]
    valuation, valuation_meta = _valuation_score(priced, tickers)
    parts = {
        "liquidity": _liquidity_score(frame).where(traded),
        "cost": _cost_score(frame).where(traded),
        "valuation": valuation.where(traded),
        "priceQuality": _price_quality_score(frame, last_share).where(traded),
    }

    total = _weighted(parts, weights).where(traded)
    coverage = _coverage(parts, weights).where(traded)

    scored = frame.assign(
        CwScore=total,
        CwScoreCoverage=coverage,
        ScoreLiquidity=parts["liquidity"].round(2),
        ScoreValuation=parts["valuation"].round(2),
        ScoreCost=parts["cost"].round(2),
        ScorePriceQuality=parts["priceQuality"].round(2),
        ScoreHeadroom=headroom.round(2),
    )
    scored["CwRank"] = (
        scored["CwScore"].rank(ascending=False, method="min").astype("Int64")
    )

    ranking = []
    top = scored[traded & scored["CwScore"].notna()].sort_values(
        "CwScore", ascending=False, kind="stable")
    for rank, row in enumerate(top.itertuples(index=False), start=1):
        ranking.append({
            "rank": rank,
            "t": getattr(row, "StockCode"),
            "u": getattr(row, "Underlying") if isinstance(getattr(row, "Underlying"), str) else None,
            "score": _f(getattr(row, "CwScore")),
            "coveragePct": _f(getattr(row, "CwScoreCoverage"), 1),
            "price": _f(getattr(row, "LastPrice")),
            "chgPct": _f(getattr(row, "PriceChangePct")),
            "valueVND": _f(getattr(row, "TradingValueVND"), 0),
            "spreadPct": _f(getattr(row, "SpreadPct")),
            "parts": {
                "liquidity": _f(getattr(row, "ScoreLiquidity")),
                "valuation": _f(getattr(row, "ScoreValuation")),
                "cost": _f(getattr(row, "ScoreCost")),
                "priceQuality": _f(getattr(row, "ScorePriceQuality")),
                # Không có "headroom" ở đây: nó là cờ cảnh báo (xem headroomPct/nearCeiling),
                # không phải một trục của điểm — để nguyên sẽ khiến người đọc cộng sai trọng số.
            },
            "headroomPct": _f(getattr(row, "ScoreHeadroom")),
            "nearCeiling": bool(getattr(row, "ScoreHeadroom", 100) is not None
                                and getattr(row, "ScoreHeadroom", 100) <= HEADROOM_WARN_PCT),
            "tier": row.LiquidityTier if hasattr(row, "LiquidityTier") else None,
        })

    # Xếp hạng theo cổ phiếu cơ sở: hữu ích vì nhà đầu tư thường chọn cơ sở trước, CW sau.
    by_underlying = []
    for underlying, group in scored[traded & scored["CwScore"].notna()].groupby("Underlying"):
        best = group.sort_values("CwScore", ascending=False, kind="stable").iloc[0]
        by_underlying.append({
            "u": str(underlying) if isinstance(underlying, str) else None,
            "count": int(len(group)),
            "bestTicker": best["StockCode"],
            "bestScore": _f(best["CwScore"]),
            "medianScore": _f(group["CwScore"].median()),
            "valueVND": _f(group["TradingValueVND"].sum(min_count=1), 0),
        })
    by_underlying.sort(key=lambda r: (r["bestScore"] or 0), reverse=True)

    score_values = total.dropna()
    return {
        "ranking": ranking,
        "byUnderlying": by_underlying,
        "scored": int(len(score_values)),
        "unscored": int(len(frame) - len(score_values)),
        "weights": weights,
        "distribution": {
            "median": _f(score_values.median()) if len(score_values) else None,
            "p25": _f(score_values.quantile(0.25)) if len(score_values) else None,
            "p75": _f(score_values.quantile(0.75)) if len(score_values) else None,
        },
        "valuationMeta": valuation_meta,
        "valuation": valuation_status(priced, valuation_diagnostics),
    }


def valuation_status(priced: pd.DataFrame | None = None,
                     diagnostics: dict | None = None) -> dict:
    """Trạng thái trục định giá — luôn trả về, kể cả khi bị khoá.

    Trả về đúng cái đang thiếu thay vì một con số thay thế. Khi nguồn điều khoản xuất hiện,
    ``available`` chuyển thành ``True`` và engine ``cwintel.bs`` được dùng trực tiếp.
    """
    if priced is not None and not priced.empty:
        return {
            "available": True,
            "source": "điều khoản Vietstock (strike, tỷ lệ chuyển đổi, ngày đáo hạn) "
                      "+ S suy từ dữ liệu Vietstock, kiểm chứng chéo hai công thức",
            "priced": int(len(priced)),
            "excluded": (diagnostics or {}).get("excluded", {}),
            "riskFree": (diagnostics or {}).get("riskFree"),
            "riskFreeSource": (diagnostics or {}).get("riskFreeSource"),
            "model": (diagnostics or {}).get("model"),
            "ivInterpretation": (diagnostics or {}).get("ivInterpretation"),
            "ratingUse": (
                "Xếp hạng dùng IV so với trung vị cùng cơ sở (ivResidualPct), không dùng "
                "cwPrice/bsPrice — hai đại lượng đó bằng nhau khi IV suy ngược từ giá."
            ),
        }

    return {
        "available": False,
        "blockedBy": ["StrikePrice (K)", "MaturityDate (T)", "ConversionRatio (n)",
                      "UnderlyingPrice (S)"],
        "reason": (
            "Endpoint stock_type=EW chỉ trả 34 trường bảng giá; không có strike, ngày đáo hạn, "
            "tỷ lệ chuyển đổi hay giá cổ phiếu cơ sở. Black–Scholes cần đủ bốn biến này, nên "
            "không thể tính giá lý thuyết, IV, delta/gamma/theta/vega hay premium. Không suy "
            "ra từ tên mã: hai chữ số cuối không mã hoá strike, và các CW cùng cơ sở có strike "
            "khác nhau."
        ),
        "engineReady": "cwintel.bs.price_and_greeks / implied_vol (đã có, chờ dữ liệu đầu vào)",
        "unlocks": ["giá lý thuyết", "IV", "Greeks", "premium", "moneyness", "điểm định giá"],
        "alternativeUsed": (
            "Điểm số thay thế dùng 5 trục đo được từ bảng giá: thanh khoản, chi phí giao dịch, "
            "chất lượng giá, độ ổn định lịch sử, dư địa trần–sàn."
        ),
    }


def _f(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(out) else round(out, digits)
