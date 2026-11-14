"""Lãi suất phi rủi ro lấy từ đường cong lợi suất TPCP Việt Nam — không còn hằng số.

Trước module này, toàn bộ định giá Black–Scholes dùng ``config.DEFAULT_RISK_FREE = 0.0444``
và chính payload xuất bản phải tự thú: *"đây là THAM SỐ PHẦN MỀM, không phải số liệu thị
trường"*. Sai 15% ở ``r`` làm IV lệch khoảng 1 điểm phần trăm — không lớn, nhưng **toàn bộ**
mã đều dùng chung một số bịa.

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

``load_curve`` trả cả nguồn gốc. Nếu tệp không tồn tại hoặc cũ hơn ngưỡng, hàm trả ``None``
thay vì lặng lẽ lùi về hằng số — nơi gọi quyết định, và phải ghi lý do vào payload.
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
    """Các điểm lợi suất của **đúng** một phiên; ``None`` nếu phiên đó không có.

    Ngày không giao dịch thì trả ``None`` chứ không lấy phiên gần nhất: định giá phiên nào
    phải dùng lãi suất phiên đó. Nơi gọi tự quyết định lùi về phiên trước hay không, và ghi
    lý do — im lặng lấy phiên cũ là che mất lỗ hổng dữ liệu.
    """
    if curve is None or curve.empty:
        return None
    target = pd.Timestamp(day) if not isinstance(day, pd.Timestamp) else day
    day_frame = curve[curve["date"] == target.normalize()]
    return day_frame if not day_frame.empty else None


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
        return fallback, "hằng số cấu hình (không có đường cong cho phiên này)"
    return rate, f"nội suy đường cong TPCP HNX tại T={years:.2f} năm"


def summarize(day_curve: pd.DataFrame | None, session: str | None = None
              ) -> dict:
    """Khối chẩn đoán gọn để nhét vào analytics JSON."""
    if day_curve is None or day_curve.empty:
        return {
            "available": False,
            "reason": ("Không có đường cong lợi suất cho phiên này. Định giá dùng lãi suất "
                       "hằng số và điều đó được ghi kèm từng dòng."),
        }
    points = day_curve.sort_values("years")
    anchor = rate_for_years(day_curve, 1.0)
    return {
        "available": True,
        "session": session or str(points["date"].iloc[0].date()),
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
