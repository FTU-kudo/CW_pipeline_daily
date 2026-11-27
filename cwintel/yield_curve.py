"""Ưu tiên lãi suất phi rủi ro từ đường cong lợi suất TPCP Việt Nam.

Đường cong HNX được chọn theo ngày dữ liệu mới nhất không muộn hơn phiên CW. Vì job CW
chạy trước khi repo nguồn cập nhật trong ngày, thường sẽ dùng đường cong phiên giao dịch
liền trước. ``config.DEFAULT_RISK_FREE = 0.0444`` chỉ là fallback cuối cùng khi kho không
có đường cong nào phù hợp; nguồn và ngày đường cong được ghi vào metadata.

Nguồn: repo ``FTU-kudo/VN_Bond_Yield_pipeline``, kho ``cache/hnx_yield_curve_daily.parquet``
— 11 kỳ hạn chuẩn (3M, 6M, 9M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 15Y, 20Y) từ 2013-03-19, cập nhật
hằng ngày từ HNX.

## Ba cột lợi suất của HNX, và cột nào dùng được

HNX trả ba loại cho cùng một kỳ hạn:

``par_yield``
    Lợi suất trái phiếu coupon, tính theo mệnh giá (cơ sở "bond equivalent").
``spot_annual``
    Lợi suất gộp theo năm, tức ``(1 + y)^t``.
``spot_continuous``
    Lợi suất **ghép lãi liên tục**, tức ``exp(r·t)``.

Black–Scholes chiết khấu bằng ``exp(-r·T)`` — đúng cơ sở liên tục. Vì vậy **chỉ
``spot_continuous`` được dùng làm ``r``**. Không dùng ``par_yield`` (lệch cơ sở coupon), không
dùng ``spot_annual`` (lệch cơ sở gộp năm). Quan hệ đã kiểm chứng trên dữ liệu thật:
``spot_continuous = ln(1 + spot_annual)`` — kỳ hạn 1Y ngày 2026-11-13: 3,787896% so với
ln(1 + 3,860552%) = 3,7879%.

## Kỳ hạn nào, và vì sao phải nội suy

Từng CW có kỳ hạn còn lại riêng (trung vị 119 ngày, p75 174, max 293) — không trùng khít kỳ
hạn chuẩn nào của HNX. Dùng một lãi suất duy nhất cho mọi CW là lặp lại đúng lỗi cũ ở mức
nhỏ hơn: 3M hôm 2026-11-13 là 3,688% còn 1Y là 3,788%, lệch 10 điểm cơ bản. Vì vậy ``r``
được **nội suy tuyến tính theo T** giữa hai kỳ hạn chuẩn kẹp hai bên, và **ngoại suy phẳng**
(giữ giá trị kỳ hạn gần nhất) khi T nằm ngoài dải — ngoại suy tuyến tính với đường cong lợi
suất có thể cho lãi suất âm, điều không chấp nhận được ở đây.

Nội suy là lựa chọn có chủ ý: đường cong NS đã fit sẵn trong repo nguồn mượt hơn, nhưng nó
là **mô hình** (sai số RMSE 0,03 ở ngày gần nhất). Lợi suất quan sát là **số liệu**. Khi phải
chọn giữa số liệu và mô hình cho một tham số đầu vào, chọn số liệu và ghi rõ nội suy.

## Không im lặng khi thiếu

``curve_on`` chọn đường cong mới nhất không muộn hơn phiên CW và không bao giờ chọn dữ liệu
của tương lai. Nếu không có ngày dữ liệu nào phù hợp, định giá mới dùng fallback; payload
và từng dòng CW ghi rõ nguồn cùng ngày đường cong được chọn.
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import pandas as pd

#: Cột lợi suất dùng làm ``r``. Xem docstring: chỉ cơ sở liên tục mới đúng cho BS.
RATE_TYPE = "spot_continuous"

#: Kỳ hạn chuẩn của HNX, quy ra năm để nội suy.
TENOR_YEARS: dict[str, float] = {
    "3M": 3 / 12, "6M": 6 / 12, "9M": 9 / 12,
    "1Y": 1.0, "2Y": 2.0, "3Y": 3.0, "5Y": 5.0,
    "7Y": 7.0, "10Y": 10.0, "15Y": 15.0, "20Y": 20.0,
}

#: Lợi suất ngoài dải này bị coi là dữ liệu hỏng, không dùng. Đường cong TPCP Việt Nam
#: 2013–2026 dao động khoảng 1%–15%; 0,05%–40% là biên rộng để không loại oan.
MIN_RATE_PCT = 0.05
MAX_RATE_PCT = 40.0

#: Tệp quy ước trong ``data/`` — cùng chỗ với ``cw_terms`` và ``underlying_history``.
DEFAULT_CURVE_PATH = Path(__file__).resolve().parents[1] / "data" / "bond_yield" / "yield_curve.csv"


def _rate_to_decimal(value: float | None) -> float | None:
    """Lợi suất % → thập phân, có kiểm tra dải hợp lý."""
    if value is None:
        return None
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(pct) or not (MIN_RATE_PCT <= pct <= MAX_RATE_PCT):
        return None
    return pct / 100.0


def load_curve(path: Path | None = None) -> pd.DataFrame | None:
    """Đọc kho đường cong lợi suất; ``None`` nếu không có hoặc không dùng được.

    Trả DataFrame long ``(date, tenor, years, rate)`` với ``rate`` là **thập phân, liên tục**.
    Sắp theo ``date`` tăng dần. Không nội suy gì ở bước này — chỉ đọc và kiểm tra.
    """
    path = Path(path) if path is not None else DEFAULT_CURVE_PATH
    if not path.exists():
        return None
    try:
        frame = pd.read_csv(path, dtype={"tenor": str})
    except (OSError, ValueError, pd.errors.ParserError):
        return None
    needed = {"date", "tenor", "rate"}
    if not needed.issubset(frame.columns):
        return None

    frame = frame[frame["tenor"].isin(TENOR_YEARS)].copy()
    if frame.empty:
        return None
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"])
    frame["years"] = frame["tenor"].map(TENOR_YEARS)
    frame["rate"] = frame["rate"].map(_rate_to_decimal)
    frame = frame.dropna(subset=["rate"])
    if frame.empty:
        return None
    return (frame[["date", "tenor", "years", "rate"]]
            .sort_values(["date", "years"]).reset_index(drop=True))


def curve_on(curve: pd.DataFrame, day: str | date) -> pd.DataFrame | None:
    """Đường cong mới nhất có ngày không muộn hơn phiên định giá.

    Workflow CW chạy trước khi repo nguồn cập nhật đường cong trong ngày. Vì vậy, nếu chưa
    có đường cong cùng ngày, dùng ngày dữ liệu gần nhất trước đó (thường là phiên giao dịch
    liền trước), thay vì rơi thẳng về hằng số cấu hình. Không bao giờ chọn đường cong tương
    lai. Ngày nguồn được giữ trong DataFrame để chẩn đoán và ghi vào metadata.
    """
    if curve is None or curve.empty:
        return None
    target = pd.Timestamp(day) if not isinstance(day, pd.Timestamp) else day
    target = target.normalize()
    available = curve[curve["date"] <= target]
    if available.empty:
        return None
    selected_day = available["date"].max()
    return available[available["date"] == selected_day].copy()


def rate_for_years(day_curve: pd.DataFrame, years: float) -> float | None:
    """Lãi suất liên tục (thập phân) tại kỳ hạn ``years``, nội suy tuyến tính theo T.

    Trong dải quan sát: nội suy tuyến tính giữa hai kỳ hạn kẹp hai bên.
    Ngoài dải: giữ giá trị kỳ hạn gần nhất (**ngoại suy phẳng**) — ngoại suy tuyến tính có
    thể cho lãi suất âm, không dùng được cho chiết khấu.
    """
    if day_curve is None or day_curve.empty or years is None:
        return None
    if not math.isfinite(years) or years <= 0:
        return None
    points = day_curve.sort_values("years")
    xs = points["years"].to_numpy(dtype=float)
    ys = points["rate"].to_numpy(dtype=float)
    if len(xs) == 0:
        return None
    if len(xs) == 1:
        return float(ys[0])
    if years <= xs[0]:
        return float(ys[0])
    if years >= xs[-1]:
        return float(ys[-1])
    # Tìm cặp kẹp hai bên rồi nội suy tuyến tính.
    for i in range(1, len(xs)):
        if years <= xs[i]:
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            if x1 == x0:
                return float(y1)
            weight = (years - x0) / (x1 - x0)
            return float(y0 + weight * (y1 - y0))
    return float(ys[-1])


def risk_free_for(day_curve: pd.DataFrame, years: float,
                  fallback: float) -> tuple[float, str]:
    """``(r, nguồn)`` cho một kỳ hạn cụ thể — dùng ngay tại chỗ định giá.

    Luôn trả về một số dùng được: có đường cong thì nội suy, không thì ``fallback`` kèm nhãn
    nói rõ đó là hằng số. Nhãn được ghi vào payload để người đọc biết con số đến từ đâu.
    """
    rate = rate_for_years(day_curve, years)
    if rate is None:
        return fallback, "hằng số cấu hình (không có đường cong cùng ngày hoặc trước phiên)"
    curve_day = pd.Timestamp(day_curve["date"].max()).date().isoformat()
    return rate, (f"nội suy đường cong TPCP HNX ngày {curve_day} "
                  f"tại T={years:.2f} năm")


def summarize(day_curve: pd.DataFrame | None, session: str | None = None
              ) -> dict:
    """Khối chẩn đoán gọn để nhét vào analytics JSON."""
    if day_curve is None or day_curve.empty:
        return {
            "available": False,
            "reason": ("Không có đường cong lợi suất cùng ngày hoặc trước phiên định giá. "
                       "Định giá dùng lãi suất hằng số và điều đó được ghi kèm từng dòng."),
        }
    points = day_curve.sort_values("years")
    anchor = rate_for_years(day_curve, 1.0)
    curve_session = str(pd.Timestamp(points["date"].iloc[0]).date())
    valuation_session = str(session) if session else curve_session
    age_days = (pd.Timestamp(valuation_session).normalize()
                - pd.Timestamp(curve_session).normalize()).days
    return {
        # `session` remains the source-curve date; valuationSession identifies the CW bar.
        "session": curve_session,
        "valuationSession": valuation_session,
        "ageCalendarDays": age_days,
        "available": True,
        "source": "HNX yield curve (spot_continuous) qua FTU-kudo/VN_Bond_Yield_pipeline",
        "basis": ("spot_continuous — lợi suất ghép lãi liên tục, đúng cơ sở chiết khấu "
                  "exp(-rT) của Black–Scholes"),
        "tenors": [f"{t}" for t in points["tenor"].tolist()],
        "ratesPct": {str(row.tenor): round(float(row.rate) * 100, 4)
                     for row in points.itertuples()},
        "anchored1YPct": round(anchor * 100, 4) if anchor is not None else None,
        "interpolation": ("tuyến tính theo T giữa hai kỳ hạn chuẩn kẹp hai bên; ngoại suy "
                          "phẳng ngoài dải để tránh lãi suất âm"),
    }
