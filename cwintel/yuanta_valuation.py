"""Định giá Black–Scholes cho CW: nối bảng giá Yuanta với điều khoản Vietstock.

Trước đây module này không thể tồn tại: endpoint Yuanta chỉ trả bảng giá, thiếu cả bốn biến
đầu vào. Repo ``Vietstock_CW_bot`` cung cấp đúng bốn biến đó, nên định giá trở nên khả thi:

    S  giá cổ phiếu cơ sở    ← suy từ chính dữ liệu Vietstock, kiểm chứng chéo 2 công thức
    K  strike                ← gia_thuc_hien
    n  tỷ lệ chuyển đổi      ← ty_le_chuyen_doi ("2 : 1")
    T  thời gian tới đáo hạn ← ngay_gd_cuoi_cung

Nguyên tắc: **không nội suy, không đoán**. Một CW chỉ được định giá khi hội đủ bốn biến và
S vượt qua phép kiểm chứng chéo; nếu thiếu, nó bị loại khỏi kết quả và được đếm vào
``excluded`` kèm lý do. Đây là lý do phải trả về cả ``excluded_breakdown``: người đọc cần
biết vì sao 407 mã chỉ còn vài trăm mã được định giá.

## Điều cần hiểu trước khi đọc số

**IV ở đây không phải là dự báo.** Nó là biến động ẩn suy ngược từ giá thị trường, tức là
"thị trường đang định giá rủi ro bao nhiêu". Với CW Việt Nam, IV thường cao hơn HV rõ rệt vì
người phát hành bán rủi ro — chênh lệch đó là **chi phí**, không phải cơ hội.

**Giá lý thuyết không phải giá mục tiêu.** BS định giá một quyền chọn châu Âu kiểu chuẩn;
CW Việt Nam có điều khoản đặc thù (chốt giá, điều chỉnh khi chia cổ tức) mà mô hình này
không mô tả. Vì vậy ``bsPrice`` được dùng để **xếp hạng tương đối** (mã nào đắt/rẻ so với
nhóm cùng cơ sở), không phải để nói "mã này sẽ về giá X".

**Lãi suất phi rủi ro** dùng hằng số cấu hình ``config.DEFAULT_RISK_FREE`` và được ghi kèm
nguồn, vì repo không có chuỗi lợi suất trái phiếu. Đây là tham số phần mềm, không phải số
liệu thị trường — ``riskFreeSource`` nói rõ điều đó.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from . import bs as bs_engine
from . import config

#: Repo Vietstock làm tròn premium 2 chữ số và đòn bẩy 2 chữ số, nên sai số tương đối nhỏ.
#: 1% là ngưỡng đủ rộng để không loại oan, đủ hẹp để bắt lỗi thật.
DEFAULT_CROSSCHECK_TOLERANCE_PCT = 1.0

#: Chặn dưới của IV hợp lý. Dưới mức này (0,5%/năm) coi như không xác định được.
MIN_IV = 0.005
#: Chặn trên: 300%/năm. Vượt mức này gần như chắc chắn là dữ liệu giá sai.
MAX_IV = 3.0

#: Chặn thời gian tới đáo hạn để tránh T→0 chia cho 0 trong Greeks.
MIN_DAYS_TO_MATURITY = 1


def _f(value: Any, digits: int = 4) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(out) else round(out, digits)


def years_to_maturity(session: str | date, maturity: str | date | None) -> float | None:
    """Tính ``T`` theo năm lịch, dùng đúng ``config.DAYS_PER_YEAR`` của dự án."""
    if not maturity:
        return None
    day = date.fromisoformat(session) if isinstance(session, str) else session
    mat = date.fromisoformat(maturity) if isinstance(maturity, str) else maturity
    days = (mat - day).days
    if days < MIN_DAYS_TO_MATURITY:
        return None
    return days / config.DAYS_PER_YEAR


#: Số phiên tối thiểu để ước lượng biến động từ chuỗi giá CW.
MIN_VOL_SESSIONS = 10
#: Số phiên dùng để ước lượng biến động gần nhất.
VOL_WINDOW = 21


def realized_vol_from_series(series: pd.DataFrame, *, window: int = VOL_WINDOW) -> dict[str, float]:
    """Biến động thực hiện của **CW** từ chuỗi giá đã tích luỹ (%, theo năm).

    Vì sao dùng chuỗi CW chứ không dùng chuỗi cổ phiếu cơ sở: repo Vietstock không lưu giá
    cổ phiếu cơ sở (chỉ lưu premium/đòn bẩy đã tính sẵn), nên không dựng lại được HV của cổ
    phiếu. Chuỗi CW thì dự án tự tích luỹ được từ mỗi phiên.

    Hàm này **không** thay thế HV của cổ phiếu: biến động CW = biến động cổ phiếu × đòn bẩy
    hiệu dụng, nên độ lớn khác hẳn. Nó chỉ dùng để so sánh **IV của chính mã đó** với chính
    nó trong quá khứ — tức là trả lời "IV hôm nay cao hay thấp so với mức thường thấy".

    Chỉ dùng log-return giữa các phiên **liền nhau có giá**; phiên thiếu giá bị bỏ, không nội
    suy, nên khoảng trống làm giảm số quan sát thay vì tạo ra biến động giả.
    """
    if series is None or series.empty:
        return {}
    out: dict[str, float] = {}
    for ticker, group in series.groupby("ticker"):
        closes = pd.to_numeric(group.sort_values("session")["close"], errors="coerce").dropna()
        closes = closes[closes > 0].tail(window + 1)
        if len(closes) < MIN_VOL_SESSIONS:
            continue
        log_ret = np.log(closes.to_numpy()[1:] / closes.to_numpy()[:-1])
        if len(log_ret) < MIN_VOL_SESSIONS - 1:
            continue
        # Độ lệch chuẩn mẫu (ddof=1) — ước lượng không chệch cho mẫu nhỏ.
        daily = float(np.std(log_ret, ddof=1))
        out[str(ticker)] = daily * math.sqrt(config.TRADING_DAYS_PER_YEAR) * 100
    return out


def iv_residual(priced: pd.DataFrame, *, min_group: int = 5) -> pd.DataFrame:
    """Chênh lệch IV của từng mã so với **trung vị IV của nhóm cùng cổ phiếu cơ sở**.

    Đây là thước đo "rẻ/đắt" thực sự dùng được, thay cho ``cwPrice/bsPrice``: khi IV được
    suy ngược từ chính giá thị trường, hai đại lượng đó luôn bằng nhau (sai số làm tròn), nên
    tỷ lệ của chúng không bao giờ khác 0. So sánh IV giữa các CW cùng cơ sở mới có nghĩa:
    cùng một cổ phiếu, cùng kỳ hạn gần nhau, mức IV khác nhau là mức bù rủi ro khác nhau.

    Nhóm dưới ``min_group`` mã thì không tính (trung vị của 2 quan sát không đáng tin) và
    ``ivResidualPct`` để trống — không gán 0.
    """
    if priced is None or priced.empty or "iv" not in priced:
        return priced
    frame = priced.copy()
    iv = pd.to_numeric(frame["iv"], errors="coerce")
    counts = frame.groupby("underlying")["ticker"].transform("count")
    median = iv.groupby(frame["underlying"]).transform("median")
    residual = (iv / median - 1) * 100
    frame["ivGroupMedian"] = median.round(2)
    frame["ivGroupSize"] = counts
    frame["ivResidualPct"] = residual.where(counts >= min_group).round(2)
    return frame


def price_warrants(frame: pd.DataFrame, terms: pd.DataFrame, *,
                   session: str | None = None,
                   risk_free: float | None = None,
                   crosscheck_tolerance_pct: float = DEFAULT_CROSSCHECK_TOLERANCE_PCT
                   ) -> tuple[pd.DataFrame, dict]:
    """Định giá từng CW. Trả ``(bảng kết quả, chẩn đoán)``.

    ``frame`` là bảng đã làm sạch của ``cwintel.yuanta_board.clean_board`` (cần ``StockCode``,
    ``LastPrice``, ``Traded``). ``terms`` là bảng điều khoản của
    ``scripts/import_vietstock_terms.py``.

    Chỉ mã **có khớp lệnh** được định giá: không có giá thị trường thì không có IV để suy
    ngược, và không có gì để so sánh với giá lý thuyết.
    """
    risk_free = config.DEFAULT_RISK_FREE if risk_free is None else risk_free
    excluded: dict[str, int] = {}

    def exclude(reason: str, n: int = 1) -> None:
        excluded[reason] = excluded.get(reason, 0) + n

    if frame is None or frame.empty:
        raise ValueError("cần DataFrame bảng giá không rỗng")
    if terms is None or terms.empty:
        return pd.DataFrame(columns=["ticker"]), {
            "available": False,
            "reason": "Chưa có bảng điều khoản (chạy scripts/import_vietstock_terms.py).",
            "excluded": {},
        }

    session = session or (str(terms["session"].max()) if "session" in terms else None)
    if not session:
        raise ValueError("cần `session` để chọn đúng bản ghi điều khoản")

    same_day = terms[terms["session"].astype(str) == str(session)]
    if same_day.empty:
        return pd.DataFrame(columns=["ticker"]), {
            "available": False,
            "reason": f"Bảng điều khoản không có phiên {session}.",
            "excluded": {},
        }
    term_by_ticker = same_day.set_index(same_day["ticker"].astype(str).str.upper())

    traded = frame[frame["Traded"].fillna(False)]
    rows: list[dict] = []

    for row in traded.itertuples(index=False):
        ticker = str(getattr(row, "StockCode")).upper()
        if ticker not in term_by_ticker.index:
            exclude("không có điều khoản trong nguồn Vietstock")
            continue
        term = term_by_ticker.loc[ticker]
        if isinstance(term, pd.DataFrame):     # trùng mã trong nguồn → lấy bản cuối
            term = term.iloc[-1]

        strike = _f(term.get("strike"), 4)
        ratio = _f(term.get("ratio"), 6)
        underlying = _f(term.get("underlyingPrice"), 4)
        crosscheck = _f(term.get("crosscheckPct"), 4)
        cw_close = _f(getattr(row, "LastPrice"), 4)

        if not strike or strike <= 0:
            exclude("thiếu strike")
            continue
        if not ratio or ratio <= 0:
            exclude("thiếu tỷ lệ chuyển đổi")
            continue
        if not underlying or underlying <= 0:
            exclude("thiếu giá cổ phiếu cơ sở")
            continue
        if not cw_close or cw_close <= 0:
            exclude("thiếu giá CW khớp lệnh")
            continue
        # S suy ra từ nguồn phải tự nhất quán, nếu không thì không được dùng để định giá.
        if crosscheck is not None and crosscheck > crosscheck_tolerance_pct:
            exclude(f"S không khớp chéo (>{crosscheck_tolerance_pct}%)")
            continue

        t_years = years_to_maturity(session, term.get("maturity"))
        if t_years is None:
            exclude("đáo hạn trong quá khứ hoặc thiếu ngày")
            continue

        result = bs_engine.price_and_greeks(
            S=underlying, K=strike, T=t_years, r=risk_free,
            sigma=None, ratio=ratio, kind="call")
        # sigma=None → engine trả invalid_input; tự tính IV từ giá thị trường thay vì
        # giả định một sigma. Đây là điểm mấu chốt: sigma phải suy từ giá, không bịa.
        iv, iv_status = bs_engine.implied_vol(
            market_price=cw_close, S=underlying, K=strike, T=t_years,
            r=risk_free, ratio=ratio, kind="call")

        if iv is None or not (MIN_IV <= iv <= MAX_IV):
            exclude(f"không suy được IV ({iv_status})")
            continue

        greeks = bs_engine.price_and_greeks(
            S=underlying, K=strike, T=t_years, r=risk_free,
            sigma=iv, ratio=ratio, kind="call")
        if greeks.status != "ok":
            exclude(f"Greeks không tính được ({greeks.status})")
            continue

        # Premium hoà vốn: giá phải vượt bao nhiêu % để hoà vốn khi giữ tới đáo hạn.
        breakeven = strike + cw_close * ratio
        premium_pct = (breakeven - underlying) / underlying * 100
        intrinsic = max(underlying - strike, 0.0) / ratio

        rows.append({
            "ticker": ticker,
            "underlying": term.get("underlying"),
            "session": str(session),
            "strike": strike,
            "ratio": ratio,
            "maturity": term.get("maturity"),
            "daysToMaturity": int((date.fromisoformat(str(term.get("maturity")))
                                   - date.fromisoformat(str(session))).days),
            "underlyingPrice": underlying,
            "cwPrice": cw_close,
            "bsPrice": _f(greeks.price, 2),
            "intrinsic": _f(intrinsic, 2),
            "timeValue": _f(greeks.time_value, 2),
            "iv": _f(iv * 100, 2),                 # hiển thị theo %/năm
            "ivStatus": iv_status,
            "delta": _f(greeks.delta, 6),
            "gamma": _f(greeks.gamma, 8),
            "theta": _f(greeks.theta, 6),
            "vega": _f(greeks.vega, 4),
            "rho": _f(greeks.rho, 6),
            "deltaOption": _f(greeks.delta * ratio, 4),
            "moneyness": ("ITM" if underlying > strike else
                          ("ATM" if abs(underlying - strike) <= strike * 0.01 else "OTM")),
            "moneynessPct": _f((underlying / strike - 1) * 100, 2),
            "premiumPct": _f(premium_pct, 2),
            "leverage": _f((underlying / cw_close) / ratio, 3),
            # Giá thị trường đắt/rẻ hơn giá lý thuyết bao nhiêu %. Dương = thị trường trả
            # nhiều hơn mô hình; âm = rẻ hơn mô hình. KHÔNG phải tín hiệu mua/bán.
            "vsBsPct": _f((cw_close / greeks.price - 1) * 100, 2),
            "crosscheckPct": crosscheck,
            "termsSource": term.get("termsSource"),
        })

    result = iv_residual(pd.DataFrame(rows))
    # Số phiên còn lại để so sánh với Vietstock — chỉ để chẩn đoán, không dùng để định giá.
    diagnostics = {
        "available": bool(len(result)),
        "session": str(session),
        "priced": int(len(result)),
        "traded": int(len(traded)),
        "excluded": dict(sorted(excluded.items(), key=lambda kv: -kv[1])),
        "riskFree": risk_free,
        "riskFreeSource": (
            "Hằng số cấu hình config.DEFAULT_RISK_FREE — repo không có chuỗi lợi suất trái "
            "phiếu, nên đây là THAM SỐ PHẦN MỀM, không phải số liệu thị trường."
        ),
        "model": (
            "Black–Scholes–Merton cho quyền chọn mua kiểu châu Âu, không cổ tức (q=0). "
            "CW Việt Nam có điều khoản đặc thù (chốt giá, điều chỉnh khi chia cổ tức) mà mô "
            "hình không mô tả, nên bsPrice dùng để xếp hạng tương đối, không phải giá mục tiêu."
        ),
        "ivInterpretation": (
            "IV là biến động ẩn suy ngược từ giá thị trường, KHÔNG phải dự báo. IV cao hơn HV "
            "là chi phí của người mua, không phải cơ hội."
        ),
        "crosscheckTolerancePct": crosscheck_tolerance_pct,
        "ivRange": [MIN_IV * 100, MAX_IV * 100],
    }
    return result, diagnostics


def summarize(priced: pd.DataFrame) -> dict:
    """Tổng hợp phân bố IV, moneyness, chênh lệch so với BS — thuần mô tả."""
    if priced is None or priced.empty:
        return {"available": False}
    iv = pd.to_numeric(priced["iv"], errors="coerce").dropna()
    vs = pd.to_numeric(priced["vsBsPct"], errors="coerce").dropna()
    return {
        "available": True,
        "count": int(len(priced)),
        "medianIv": _f(iv.median(), 2) if len(iv) else None,
        "p25Iv": _f(iv.quantile(0.25), 2) if len(iv) else None,
        "p75Iv": _f(iv.quantile(0.75), 2) if len(iv) else None,
        "medianVsBsPct": _f(vs.median(), 2) if len(vs) else None,
        "countAboveBs": int((vs > 0).sum()),
        "countBelowBs": int((vs < 0).sum()),
        "moneyness": {
            label: int((priced["moneyness"] == label).sum())
            for label in ("ITM", "ATM", "OTM")
        },
        "medianDelta": _f(pd.to_numeric(priced["delta"], errors="coerce").median(), 4),
        "note": (
            "IV/BS là mô tả mặt bằng định giá của thị trường tại một phiên. Không phải dự báo "
            "và không phải khuyến nghị."
        ),
    }
