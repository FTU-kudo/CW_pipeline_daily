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


#: Số phiên dùng để tính HV dài hạn (3 tháng giao dịch).
HV_LONG_WINDOW = 63

#: Chặn tin cậy cho hệ số điều chỉnh ``f``. ``f`` là tỷ lệ nghịch đảo giữa giá cổ phiếu cơ sở
#: mà Vietstock dùng khi tính premium/đòn bẩy và giá đóng cửa thật: ``f = S_nguồn / S_thật``.
#: CW Việt Nam điều chỉnh strike và tỷ lệ chuyển đổi khi cổ phiếu cơ sở chia thưởng/cổ tức, nên
#: ``f > 1`` là bình thường. Ngoài khoảng này thì nhiều khả năng là giá nguồn đã cũ (dữ liệu
#: lệch phiên) chứ không phải một đợt điều chỉnh thật — khi đó không được dựng lại điều khoản.
MIN_CORRECTION_FACTOR = 0.5
MAX_CORRECTION_FACTOR = 4.0


def resolve_terms(*, strike: float, ratio: float, maturity: str | None,
                  strike_adj: float | None, ratio_adj: float | None,
                  maturity_adj: str | None,
                  derived_s: float | None, real_s: float | None,
                  ) -> dict:
    """Quy điều khoản CW về **hệ giá đóng cửa thật** của cổ phiếu cơ sở.

    Vì sao cần: Vietstock trả strike/tỷ lệ **chưa điều chỉnh** (``gia_thuc_hien``,
    ``ty_le_chuyen_doi``) cùng một giá cổ phiếu cơ sở **cũng chưa điều chỉnh** (ẩn trong
    premium/đòn bẩy). Ghép cặp đó với giá đóng cửa *thật* là trộn hai hệ quy chiếu: CW bị coi
    là OTM sâu, giá lý thuyết về ~0, và IV suy ngược nổ tung (TCB 101%, HDB 167%, VHM 219%).

    Ba đường, ưu tiên giảm dần:

    1. ``nguồn``      — dùng ``gia_th_dieu_chinh`` + ``tlcd_dieu_chinh`` nếu nguồn đã trả.
    2. ``dựng lại``   — nhân nghịch đảo hệ số ``f`` để đưa strike/tỷ lệ về hệ giá thật.
       Kiểm chứng: với CACB2515, cách này cho K=27.419,6 và n=1,7245, khớp chính xác trang
       Vietstock (27.420 · 1,7245). IV thì **bất biến** theo hệ quy chiếu, nên dựng lại không
       làm sai IV; nó chỉ đưa Greeks về đúng hệ (delta lệch 16% nếu để sai hệ).
    3. ``gốc``        — không có ``f`` đáng tin; giữ nguyên và ghi rõ là chưa điều chỉnh.

    Trả dict gồm ``strike``/``ratio``/``maturity`` đã quy về hệ thật, ``basis`` (nguồn gốc của
    phép quy đổi) và ``factor`` (hệ số đã dùng). Không bao giờ im lặng: ``basis`` luôn nói
    con số đến từ đâu.
    """
    factor = None
    if derived_s and real_s and derived_s > 0 and real_s > 0:
        candidate = derived_s / real_s
        if MIN_CORRECTION_FACTOR <= candidate <= MAX_CORRECTION_FACTOR:
            factor = candidate

    # (1) Nguồn đã trả điều khoản điều chỉnh → dùng thẳng, không dựng lại.
    if strike_adj and ratio_adj and strike_adj > 0 and ratio_adj > 0:
        return {
            "strike": strike_adj, "ratio": ratio_adj,
            "maturity": maturity_adj or maturity,
            "basis": "điều chỉnh từ nguồn", "factor": factor,
        }

    # (2) Không có từ nguồn → dựng lại từ chênh lệch giá, chỉ khi lệch đủ lớn để đáng làm.
    if factor and abs(factor - 1.0) * 100 > ADJUSTMENT_TRIGGER_PCT:
        return {
            "strike": strike / factor, "ratio": ratio / factor,
            "maturity": maturity, "basis": "dựng lại từ chênh lệch giá", "factor": factor,
        }

    # (3) Không lệch (hoặc lệch không đáng) → giữ nguyên.
    return {"strike": strike, "ratio": ratio, "maturity": maturity,
            "basis": BASE_TERMS_BASIS, "factor": factor}


#: Nhãn ``termsBasis`` khi điều khoản vẫn ở hệ gốc, chưa quy đổi được sang hệ giá thật.
BASE_TERMS_BASIS = "gốc, chưa điều chỉnh"

#: Ngưỡng lệch (%) để coi là có điều chỉnh và cần quy đổi. Dưới mức này sai số làm tròn của
#: nguồn (premium 2 chữ số, đòn bẩy 2 chữ số) đã đủ giải thích, dựng lại chỉ thêm nhiễu.
ADJUSTMENT_TRIGGER_PCT = 0.5

#: Biên độ tối đa một phiên của cổ phiếu Việt Nam (HOSE/HNX chặn ±7%). Nếu S suy từ nguồn
#: khác lệch S đo trực tiếp quá mức này thì một trong hai đã dùng giá cũ — không thể là biến
#: động thật trong một phiên.
UNDERLYING_DRIFT_TOLERANCE_PCT = 7.0

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


def realized_vol_fast(closes: list[float], window: int) -> float | None:
    """HV (%/năm) từ danh sách giá đóng cửa; ``None`` nếu không đủ mẫu."""
    values = [v for v in closes if v and v > 0][-window - 1:]
    if len(values) < max(MIN_VOL_SESSIONS, 6) + 1:
        return None
    returns = np.log(np.asarray(values[1:], dtype=float) / np.asarray(values[:-1], dtype=float))
    daily = float(np.std(returns, ddof=1))
    return daily * math.sqrt(config.TRADING_DAYS_PER_YEAR) * 100


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
                   crosscheck_tolerance_pct: float = DEFAULT_CROSSCHECK_TOLERANCE_PCT,
                   underlying_history: dict[str, pd.DataFrame] | None = None
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

    # Chỉ số cổ phiếu cơ sở từ lịch sử thật (nếu đã tải): giá đóng cửa mới nhất, HV 21/63
    # phiên, dòng khối ngoại. Có lịch sử thì `S` lấy trực tiếp — chính xác hơn suy từ
    # premium/đòn bẩy — và so sánh được IV với HV.
    underlyings: dict[str, dict] = {}
    for symbol, series in (underlying_history or {}).items():
        if series is None or series.empty:
            continue
        closes = pd.to_numeric(series.sort_values("TradingDate")["Close"],
                               errors="coerce").dropna().tolist()
        if not closes:
            continue
        underlyings[str(symbol).upper()] = {
            "close": closes[-1],
            "date": str(series.sort_values("TradingDate")["TradingDate"].iloc[-1]),
            "hvShort": realized_vol_fast(closes, VOL_WINDOW),
            "hvLong": realized_vol_fast(closes, HV_LONG_WINDOW),
            "sessions": len(closes),
        }

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

        # Ưu tiên S từ lịch sử cổ phiếu cơ sở (đo trực tiếp) hơn S suy từ premium/đòn bẩy.
        # Ghi lại nguồn để người đọc biết con số đến từ đâu.
        history_row = underlyings.get(str(term.get("underlying") or "").upper())
        derived_s = underlying                  # S suy từ Vietstock, giữ lại để đối chiếu
        if history_row and history_row["close"]:
            underlying = float(history_row["close"])
            underlying_source = f"lịch sử Yuanta ({history_row['date']})"
        else:
            underlying_source = "suy từ premium/đòn bẩy Vietstock"

        # Quy điều khoản về CÙNG hệ quy chiếu với `underlying` đang dùng. Đây là điểm sửa
        # gốc: strike/tỷ lệ của nguồn là hệ *chưa điều chỉnh*, còn lịch sử giá là hệ *đã điều
        # chỉnh*. Trộn hai hệ làm CW bị coi là OTM sâu và IV nổ tung. Xem `resolve_terms`.
        adjusted = resolve_terms(
            strike=strike, ratio=ratio, maturity=term.get("maturity"),
            strike_adj=_f(term.get("strikeAdjusted"), 6),
            ratio_adj=_f(term.get("ratioAdjusted"), 8),
            maturity_adj=term.get("maturityAdjusted"),
            derived_s=derived_s, real_s=underlying,
        )
        strike, ratio = adjusted["strike"], adjusted["ratio"]
        maturity = adjusted["maturity"]
        terms_basis = adjusted["basis"]

        # Chỉ báo lệch giá còn lại dùng để *chẩn đoán*, không để loại. Sau khi đã quy về cùng
        # hệ, độ lệch này đo mức nguồn dùng giá cũ — thông tin hữu ích nhưng không chặn định
        # giá, vì IV không phụ thuộc hệ quy chiếu (chỉ Greeks phụ thuộc, và đã được quy đổi).
        drift_pct = ((derived_s / underlying - 1) * 100
                     if derived_s and underlying else None)
        if drift_pct is not None and abs(drift_pct) > UNDERLYING_DRIFT_TOLERANCE_PCT:
            # Đã quy đổi được điều khoản → lệch này là chuyện bình thường (CW điều chỉnh khi
            # cổ phiếu chia thưởng) và vẫn định giá được. Chưa quy đổi được mà vẫn lệch nghĩa
            # là hệ số nằm ngoài khoảng tin cậy: nguồn dùng giá cũ quá xa, hai hệ không ghép
            # được với nhau, nên loại thay vì định giá bằng hai thước đo khác nhau.
            if terms_basis == BASE_TERMS_BASIS:
                excluded["S nguồn lệch quá biên giá (±7%) và chưa quy đổi được điều khoản"] = (
                    excluded.get(
                        "S nguồn lệch quá biên giá (±7%) và chưa quy đổi được điều khoản", 0) + 1)
                continue
            excluded["S nguồn lệch >±7% (đã quy đổi điều khoản, vẫn định giá)"] = (
                excluded.get("S nguồn lệch >±7% (đã quy đổi điều khoản, vẫn định giá)", 0) + 1)

        t_years = years_to_maturity(session, maturity)
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
            "maturity": maturity,
            "daysToMaturity": int((date.fromisoformat(str(maturity))
                                   - date.fromisoformat(str(session))).days),
            # Ghi rõ điều khoản đã được quy về hệ nào để người đọc không phải đoán.
            "termsBasis": terms_basis,
            "correctionFactor": _f(adjusted["factor"], 6),
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
            "underlyingSource": underlying_source,
            "hvShort": _f(history_row["hvShort"], 2) if history_row else None,
            "hvLong": _f(history_row["hvLong"], 2) if history_row else None,
            "ivMinusHv": (_f(iv * 100 - history_row["hvShort"], 2)
                          if history_row and history_row["hvShort"] else None),
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
