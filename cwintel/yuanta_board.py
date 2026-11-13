"""Phân tích bảng giá chứng quyền (EW) từ snapshot Yuanta — thuần offline.

Phạm vi (đọc kỹ trước khi dùng)
------------------------------
Endpoint ``stock_type=EW`` chỉ trả **bảng giá hiện tại** của các CW còn niêm yết. Nó
không có chuỗi OHLCV ngày riêng từng CW. Vì vậy module này **không** tính giá lý
thuyết, Greeks, IV, khuyến nghị hay backtest: làm vậy cần dữ liệu lịch sử không có
trong nguồn. Những gì tính được một cách trung thực từ một mặt cắt bảng giá:

* làm sạch + kiểm tra tính toàn vẹn của từng dòng (giá trần/sàn, thứ tự high/low);
* quy mô giao dịch phiên (giá trị, khối lượng) và tỷ trọng theo cổ phiếu cơ sở;
* biến động trong ngày so với giá tham chiếu;
* chênh lệch mua–bán (bid–ask) hàm ý từ B1P/S1P — thước đo chi phí khớp lệnh;
* nhóm mã không giao dịch, mã thiếu độ sâu hai chiều.

Đơn vị — bằng chứng, không phải phỏng đoán
------------------------------------------
Payload có đồng nhất thức nội tại ``AvgP ≈ TotalVal / TotalVol``. Kiểm tra trên dữ
liệu mẫu cho kết quả khớp tới sai số làm tròn 2 chữ số của ``AvgP`` (ví dụ
``2.775.000 / 17.700 = 156,78``), nghĩa là ``TotalVal`` là **VND** và giá là
**VND/CW**. Module tính lại ``TradingValueVND = TotalVol × AvgP`` và **so khớp**
với ``TotalVal``; dòng nào lệch quá ``VALUE_RECON_TOLERANCE`` bị gắn cảnh báo thay
vì bị âm thầm sửa. Các trường không kiểm chứng được (``FRoom``, ``DeemP``,
``SymbolAdminStatusCode``) được giữ nguyên, không diễn giải.

Không có trong payload: ngày đáo hạn, giá thực hiện, tỷ lệ chuyển đổi, tổ chức
phát hành, giá cổ phiếu cơ sở. ``Underlying`` dưới đây chỉ là **suy ra từ quy ước
mã** (``C`` + mã cơ sở + 4 chữ số), không phải trường do Yuanta công bố.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

# ──────────────────────────────────────────────────────────────────
# HẰNG SỐ & QUY ƯỚC
# ──────────────────────────────────────────────────────────────────
CW_TICK_VND = 10.0              # bước giá CW trên HOSE (QĐ 72/QĐ-UBCK)
VALUE_RECON_TOLERANCE = 0.005   # 0,5% — dung sai làm tròn AvgP khi đối chiếu TotalVal
MAX_SPREAD_PCT_WARN = 5.0       # chênh lệch mua–bán tối đa theo quy chế yết giá
MIN_VALUE_TO_RANK = 0.0         # xếp hạng thanh khoản không áp sàn riêng

RAW_FIELDS: tuple[str, ...] = (
    "StockCode", "Exchange", "SymbolType",
    "RefP", "CeilingP", "FloorP", "OpenP", "HighestP", "LowestP", "AvgP",
    "LastMP", "LastMVol", "DeemP", "DeemVol", "TotalVol", "TotalVal",
    "FTBuyVol", "FTSellVol", "FTBuyVal", "FTSellVal", "FRoom",
    "SymbolAdminStatusCode", "ExClassType",
    "B1P", "B1V", "B2P", "B2V", "B3P", "B3V",
    "S1P", "S1V", "S2P", "S2V", "S3P", "S3V",
)

# Cột số do API trả; chuỗi rỗng / "null" / None → NaN (không thành 0).
NUMERIC_FIELDS: tuple[str, ...] = tuple(
    f for f in RAW_FIELDS if f not in {"StockCode", "Exchange", "SymbolType",
                                       "SymbolAdminStatusCode", "ExClassType"}
)

DERIVED_FIELDS: tuple[str, ...] = (
    "Underlying", "Traded", "LastPrice", "PriceChangePct", "OpenChangePct",
    "TradingValueVND", "TradingValueReconDiffPct",
    "SpreadAbs", "SpreadPct", "SpreadTicks", "MidQuote",
    "ValueSharePct", "ValueRank",
)

_UNDERLYING_RE = re.compile(r"^C([A-Z]{3,4})\d{4}$")
_UNDERLYING_FALLBACK_RE = re.compile(r"^C([A-Z]{2,5}?)\d{2,}$")


class BoardIntegrityError(ValueError):
    """Snapshot không dùng được cho phân tích (rỗng, trùng mã, sai loại chứng khoán)."""


# ──────────────────────────────────────────────────────────────────
# LÀM SẠCH
# ──────────────────────────────────────────────────────────────────
def underlying_from_code(code: str) -> str | None:
    """Suy ra mã cổ phiếu cơ sở từ quy ước mã CW (``CACB2515`` → ``ACB``).

    Chỉ là heuristic theo tên mã; ``None`` khi không khớp để tránh bịa mã.
    """
    text = str(code or "").strip().upper()
    match = _UNDERLYING_RE.match(text) or _UNDERLYING_FALLBACK_RE.match(text)
    return match.group(1) if match else None


def _to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.replace({"": None, "null": None, "NULL": None, "-": None}),
        errors="coerce",
    ).astype("float64")


def _require_columns(df: pd.DataFrame) -> None:
    missing = [c for c in ("StockCode", "Exchange", "SymbolType") if c not in df.columns]
    if missing:
        raise BoardIntegrityError(f"thiếu cột bắt buộc: {missing}")


def clean_board(rows: Iterable[dict] | pd.DataFrame, *,
                fetched_at: datetime | None = None) -> pd.DataFrame:
    """Chuẩn hoá payload EW thành DataFrame sạch, giữ nguyên mọi trường gốc.

    * ``StockCode`` → chữ hoa, bỏ khoảng trắng; trùng mã hoặc ``SymbolType != EW``
      là lỗi (raise) chứ không tự loại bỏ, vì đó là dấu hiệu schema đã đổi.
    * Trường số ``None``/``""`` → ``NaN``; ``0`` giữ nguyên là ``0``.
    * Bổ sung cột suy ra có tiền tố rõ ràng (xem ``DERIVED_FIELDS``).
    """
    if isinstance(rows, pd.DataFrame):
        frame = rows.copy()
    else:
        frame = pd.DataFrame(list(rows))
    if frame.empty:
        raise BoardIntegrityError("snapshot rỗng: không có dòng EW nào để phân tích")
    _require_columns(frame)

    frame["StockCode"] = frame["StockCode"].astype("string").str.strip().str.upper()
    frame["Exchange"] = frame["Exchange"].astype("string").str.strip().str.upper()
    frame["SymbolType"] = frame["SymbolType"].astype("string").str.strip().str.upper()

    if frame["StockCode"].isna().any() or (frame["StockCode"].str.len() == 0).any():
        bad = frame.index[frame["StockCode"].isna() | (frame["StockCode"].str.len() == 0)]
        raise BoardIntegrityError(f"StockCode rỗng tại dòng {list(bad)[:5]}")
    dupes = frame["StockCode"][frame["StockCode"].duplicated()].unique().tolist()
    if dupes:
        raise BoardIntegrityError(f"StockCode trùng trong snapshot: {sorted(dupes)[:5]}")
    not_ew = frame.loc[frame["SymbolType"] != "EW", "StockCode"].head(5).tolist()
    if not_ew:
        raise BoardIntegrityError(f"SymbolType khác EW: {not_ew}")

    # Bổ sung cột vắng mặt bằng NaN để schema CSV ổn định giữa các lần chạy.
    for field in RAW_FIELDS:
        if field not in frame.columns:
            frame[field] = np.nan
    for field in NUMERIC_FIELDS:
        frame[field] = _to_number(frame[field]) if field in frame.columns else np.nan

    frame = frame.sort_values("StockCode", kind="stable").reset_index(drop=True)

    volume = frame["TotalVol"]
    avg_price = frame["AvgP"]
    total_value = frame["TotalVal"]

    # Đồng nhất thức của nguồn: TotalVal ≈ TotalVol × AvgP.
    recomputed = volume * avg_price
    diff_pct = (recomputed - total_value).abs() / total_value.replace(0, np.nan) * 100
    frame["TradingValueVND"] = recomputed.where((volume > 0) & (avg_price > 0), np.nan)
    frame["TradingValueReconDiffPct"] = diff_pct.where(total_value > 0, np.nan)

    traded = (volume.fillna(0) > 0) & avg_price.notna() & (avg_price > 0)
    frame["Traded"] = traded
    # Chỉ coi LastMP là giá hiện tại khi thực sự có khớp lệnh trong phiên; CW không
    # giao dịch mà vẫn hiển thị LastMP của phiên cũ sẽ tạo biến động ảo.
    frame["LastPrice"] = frame["LastMP"].where(traded, np.nan)
    frame["PriceChangePct"] = np.where(
        traded & frame["RefP"].notna() & (frame["RefP"] > 0),
        (frame["LastPrice"] - frame["RefP"]) / frame["RefP"] * 100,
        np.nan,
    )
    frame["OpenChangePct"] = np.where(
        traded & frame["RefP"].notna() & (frame["RefP"] > 0) & frame["OpenP"].notna(),
        (frame["OpenP"] - frame["RefP"]) / frame["RefP"] * 100,
        np.nan,
    )

    valid_depth = (frame["B1P"] > 0) & (frame["S1P"] > 0) & (frame["S1P"] >= frame["B1P"])
    frame["SpreadAbs"] = (frame["S1P"] - frame["B1P"]).where(valid_depth, np.nan)
    frame["MidQuote"] = ((frame["B1P"] + frame["S1P"]) / 2).where(valid_depth, np.nan)
    frame["SpreadPct"] = (
        frame["SpreadAbs"] / frame["MidQuote"].replace(0, np.nan) * 100
    ).where(valid_depth, np.nan)
    # Bước giá 10 VND: chênh lệch 1 tick là mức tối thiểu về mặt cơ học.
    frame["SpreadTicks"] = (frame["SpreadAbs"] / CW_TICK_VND).where(valid_depth, np.nan)

    frame["Underlying"] = frame["StockCode"].map(underlying_from_code)

    value_total = frame["TradingValueVND"].sum(min_count=1)
    if value_total and math.isfinite(float(value_total)) and value_total > 0:
        frame["ValueSharePct"] = frame["TradingValueVND"] / value_total * 100
        frame["ValueRank"] = (
            frame["TradingValueVND"].rank(ascending=False, method="min").astype("Int64")
        )
    else:
        frame["ValueSharePct"] = np.nan
        frame["ValueRank"] = pd.Series([pd.NA] * len(frame), dtype="Int64")

    if fetched_at is not None:
        if fetched_at.tzinfo is None:
            raise ValueError("fetched_at phải có timezone")
        frame["FetchedAt"] = fetched_at.astimezone(timezone.utc).isoformat(timespec="seconds")

    ordered = list(RAW_FIELDS) + [c for c in DERIVED_FIELDS if c in frame.columns]
    ordered += [c for c in frame.columns if c not in ordered]
    return frame[ordered]


# ──────────────────────────────────────────────────────────────────
# KIỂM TRA CHẤT LƯỢNG
# ──────────────────────────────────────────────────────────────────
def _check(cid: str, title: str, ok: bool, *, severity: str = "error",
           amount: int | None = None, value: Any = None, detail: str = "") -> dict:
    status = "ok" if ok else ("fail" if severity == "error" else "warn")
    return {"id": cid, "title": title, "status": status, "severity": severity,
            "amount": amount, "value": value, "detail": detail}


def _count_rows(frame: pd.DataFrame, mask: pd.Series, limit: int = 6) -> list[str]:
    return frame.loc[mask.fillna(False), "StockCode"].head(limit).tolist()


def quality_checks(frame: pd.DataFrame) -> dict:
    """Bộ kiểm tra toàn vẹn cho một mặt cắt bảng giá. Không sửa dữ liệu."""
    checks: list[dict] = []

    ref, floor, ceil = frame["RefP"], frame["FloorP"], frame["CeilingP"]
    mask = ref.notna() & floor.notna() & ceil.notna() & (floor > 0) & (ceil > 0)
    outside = mask & ((ref < floor) | (ref > ceil))
    checks.append(_check(
        "ref_within_price_limits",
        "Giá tham chiếu nằm trong [giá sàn, giá trần]",
        not outside.any(),
        amount=int(outside.sum()),
        value=_count_rows(frame, outside),
        detail="RefP ngoài dải FloorP–CeilingP là bất khả thi về mặt quy chế giá.",
    ))

    low, high = frame["LowestP"], frame["HighestP"]
    bad_range = low.notna() & high.notna() & (low > high)
    checks.append(_check(
        "low_below_high",
        "LowestP ≤ HighestP",
        not bad_range.any(),
        amount=int(bad_range.sum()),
        value=_count_rows(frame, bad_range),
        detail="Đảo thứ tự high/low nghĩa là đã đổi nghĩa trường khi provider cập nhật schema.",
    ))

    inside = pd.Series(True, index=frame.index)
    for col in ("OpenP", "LastMP", "AvgP"):
        val = frame[col]
        applicable = val.notna() & low.notna() & high.notna() & (low > 0) & (high > 0)
        inside &= ~(applicable & ((val < low) | (val > high)))
    checks.append(_check(
        "prices_inside_day_range",
        "Giá mở cửa / khớp cuối / bình quân nằm trong [LowestP, HighestP]",
        bool(inside.all()),
        amount=int((~inside).sum()),
        value=_count_rows(frame, ~inside),
        detail="Lệch ra ngoài khoảng ngày thường do lẫn đơn vị hoặc trộn phiên khác nhau.",
    ))

    recon = frame["TradingValueReconDiffPct"]
    bad_recon = recon.notna() & (recon > VALUE_RECON_TOLERANCE * 100)
    checks.append(_check(
        "value_identity",
        "TotalVal khớp TotalVol × AvgP (xác nhận đơn vị VND)",
        not bad_recon.any(),
        amount=int(bad_recon.sum()),
        value=_count_rows(frame, bad_recon),
        detail=(
            f"Dung sai cho phép {VALUE_RECON_TOLERANCE * 100:.1f}% do AvgP làm tròn 2 chữ số. "
            "Lệch nhiều hơn nghĩa là đơn vị hoặc ý nghĩa trường đã thay đổi."
        ),
    ))

    zero_ref = frame["RefP"].notna() & (frame["RefP"] <= 0)
    checks.append(_check(
        "ref_price_positive",
        "RefP > 0",
        not zero_ref.any(),
        amount=int(zero_ref.sum()),
        value=_count_rows(frame, zero_ref),
        detail="Giá tham chiếu ≤ 0 không dùng được cho mẫu số của % biến động.",
    ))

    untraded = ~frame["Traded"].fillna(False)
    checks.append(_check(
        "untraded_rows",
        "Số mã không khớp lệnh trong phiên",
        True,
        severity="info",
        amount=int(untraded.sum()),
        value=_count_rows(frame, untraded),
        detail=(
            "Mã không giao dịch không có giá hiện tại đáng tin: LastMP có thể là giá của "
            "phiên trước, nên LastPrice/PriceChangePct được để trống thay vì dùng lại."
        ),
    ))

    no_depth = ~((frame["B1P"] > 0) & (frame["S1P"] > 0))
    checks.append(_check(
        "two_sided_depth",
        "Có độ sâu hai chiều (B1P và S1P)",
        not no_depth.any(),
        severity="warn",
        amount=int(no_depth.sum()),
        value=_count_rows(frame, no_depth),
        detail="Thiếu một bên sổ lệnh thì không tính được chênh lệch mua–bán.",
    ))

    wide = frame["SpreadPct"].notna() & (frame["SpreadPct"] > MAX_SPREAD_PCT_WARN)
    checks.append(_check(
        "spread_within_regime",
        f"Chênh lệch mua–bán ≤ {MAX_SPREAD_PCT_WARN:.0f}%",
        not wide.any(),
        severity="warn",
        amount=int(wide.sum()),
        value=_count_rows(frame, wide),
        detail=(
            "Tính trên giá giữa (B1P+S1P)/2. Vượt ngưỡng quy chế yết giá là dấu hiệu "
            "thanh khoản rất mỏng, không phải lỗi dữ liệu."
        ),
    ))

    zero_foreign = (
        (frame[["FTBuyVal", "FTSellVal"]].fillna(0).abs().sum(axis=1) == 0).all()
    )
    if zero_foreign:
        checks.append(_check(
            "foreign_flow_absent",
            "Trường giao dịch nước ngoài không có dữ liệu",
            True,
            severity="info",
            amount=0,
            value=[],
            detail="FTBuy/SellVal đều bằng 0 trên toàn bộ snapshot; không suy diễn thành 'không có giao dịch nước ngoài'.",
        ))

    statuses = sorted({str(s) for s in frame["SymbolAdminStatusCode"].dropna().unique()})
    if statuses:
        checks.append(_check(
            "admin_status_values",
            "Giá trị SymbolAdminStatusCode gặp trong snapshot",
            True,
            severity="info",
            amount=len(statuses),
            value=statuses,
            detail="Chỉ liệt kê; nghĩa của từng mã trạng thái chưa được Yuanta công bố trong payload.",
        ))

    failures = [c for c in checks if c["status"] == "fail"]
    warnings = [c for c in checks if c["status"] == "warn"]
    return {
        "status": "fail" if failures else ("warn" if warnings else "ok"),
        "failed": len(failures),
        "warned": len(warnings),
        "checks": checks,
    }


# ──────────────────────────────────────────────────────────────────
# TỔNG HỢP
# ──────────────────────────────────────────────────────────────────
def _num(value: Any, digits: int = 2) -> float | None:
    """Chuyển scalar pandas/numpy thành float JSON-safe (None thay cho NaN)."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(out) else round(out, digits)


def _records(frame: pd.DataFrame, columns: Sequence[str]) -> list[dict]:
    out: list[dict] = []
    for row in frame[list(columns)].to_dict("records"):
        clean: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, (np.integer,)):
                clean[key] = int(value)
            elif isinstance(value, (np.floating, float)):
                clean[key] = _num(value)
            elif value is pd.NA or (isinstance(value, float) and math.isnan(value)):
                clean[key] = None
            else:
                clean[key] = value
        out.append(clean)
    return out


def summarize(frame: pd.DataFrame) -> dict:
    traded = frame["Traded"].fillna(False)
    values = frame.loc[traded, "TradingValueVND"].dropna()
    change = frame.loc[traded, "PriceChangePct"].dropna()
    spread = frame["SpreadPct"].dropna()
    return {
        "rows": int(len(frame)),
        "traded": int(traded.sum()),
        "untraded": int((~traded).sum()),
        "tradedSharePct": _num(traded.mean() * 100 if len(frame) else None),
        "underlyings": int(frame["Underlying"].nunique(dropna=True)),
        "totalVolume": _num(frame.loc[traded, "TotalVol"].sum(min_count=1), 0),
        "totalValueVND": _num(values.sum(min_count=1) if len(values) else None, 0),
        "medianValueVND": _num(values.median() if len(values) else None, 0),
        "p90ValueVND": _num(values.quantile(0.9) if len(values) else None, 0),
        "top10ValueSharePct": _num(
            values.nlargest(10).sum() / values.sum() * 100 if len(values) else None
        ),
        "gainers": int((change > 0).sum()),
        "losers": int((change < 0).sum()),
        "unchanged": int((change == 0).sum()),
        "medianChangePct": _num(change.median() if len(change) else None),
        "medianLastPriceVND": _num(frame.loc[traded, "LastPrice"].median() if traded.any() else None),
        "medianSpreadAbsVND": _num(frame["SpreadAbs"].median()),
        "medianSpreadPct": _num(spread.median() if len(spread) else None),
        "medianSpreadTicks": _num(frame["SpreadTicks"].median()),
        "rowsWithDepth": int(((frame["B1P"] > 0) & (frame["S1P"] > 0)).sum()),
    }


def display_rows(frame: pd.DataFrame) -> list[dict]:
    """Rút gọn một dòng cho UI (khoá camelCase); không chứa trường gốc để file nhẹ."""
    out: list[dict] = []
    for _, row in frame.iterrows():
        out.append({
            "t": row["StockCode"],
            "u": row["Underlying"] if isinstance(row["Underlying"], str) else None,
            "traded": bool(row["Traded"]) if pd.notna(row["Traded"]) else False,
            "lastPrice": _num(row["LastPrice"]),
            "refPrice": _num(row["RefP"]),
            "priceChangePct": _num(row["PriceChangePct"]),
            "volume": _num(row["TotalVol"], 0),
            "valueVND": _num(row["TradingValueVND"], 0),
            "spreadTicks": _num(row["SpreadTicks"]),
            "spreadPct": _num(row["SpreadPct"]),
            "valueSharePct": _num(row["ValueSharePct"]),
        })
    return out


def top_movers(frame: pd.DataFrame, limit: int = 10) -> dict:
    """Tăng/giảm mạnh nhất trong phiên, chỉ trên các mã thực sự có khớp lệnh."""
    cols = ["StockCode", "Underlying", "LastPrice", "RefP", "PriceChangePct",
            "TradingValueVND", "TotalVol", "SpreadPct"]
    traded = frame[frame["Traded"].fillna(False) & frame["PriceChangePct"].notna()]

    def slice_(data: pd.DataFrame) -> list[dict]:
        return _records(data[cols], cols)

    gainers = traded.sort_values(["PriceChangePct", "TradingValueVND"],
                                ascending=[False, False], na_position="last").head(limit)
    losers = traded.sort_values(["PriceChangePct", "TradingValueVND"],
                                ascending=[True, False], na_position="last").head(limit)
    return {
        "gainers": slice_(gainers),
        "losers": slice_(losers),
        # Dòng hiển thị cho bảng: đủ mọi mã, kể cả mã không khớp lệnh.
        "all": display_rows(frame),
    }


def by_underlying(frame: pd.DataFrame, limit: int | None = None) -> list[dict]:
    """Nhóm theo cổ phiếu cơ sở suy ra từ mã CW, xếp theo giá trị giao dịch."""
    work = frame[frame["Underlying"].notna()].copy()
    if work.empty:
        return []
    work["_value"] = work["TradingValueVND"].fillna(0.0)
    total = work["_value"].sum()
    grouped = work.groupby("Underlying", dropna=True)
    rows = []
    for underlying, sub in grouped:
        traded = sub["Traded"].fillna(False)
        value = float(sub["_value"].sum())
        rows.append({
            "underlying": underlying,
            "warrants": int(len(sub)),
            "traded": int(traded.sum()),
            "valueVND": _num(value, 0),
            "valueSharePct": _num(value / total * 100 if total else None),
            "volume": _num(sub.loc[traded, "TotalVol"].sum(min_count=1), 0),
            "medianValueVND": _num(sub.loc[traded, "TradingValueVND"].median(), 0),
            "medianSpreadPct": _num(sub["SpreadPct"].median()),
            "bestChangePct": _num(sub["PriceChangePct"].max()),
            "worstChangePct": _num(sub["PriceChangePct"].min()),
        })
    rows.sort(key=lambda r: (r["valueVND"] or 0, r["warrants"]), reverse=True)
    return rows[:limit] if limit else rows


def _spread_bucket(pct: float) -> str | None:
    if pct is None or not math.isfinite(pct):
        return None
    if pct <= 1:
        return "≤1%"
    if pct <= 2:
        return "1–2%"
    if pct <= 5:
        return "2–5%"
    return ">5%"


def spread_profile(frame: pd.DataFrame) -> dict:
    """Phân bố chênh lệch mua–bán — proxy chi phí vào/ra vị thế CW."""
    depth = frame["SpreadPct"].dropna()
    if depth.empty:
        return {"available": False, "buckets": [], "median": None, "p90": None}
    labels = ["≤1%", "1–2%", "2–5%", ">5%"]
    buckets = frame["SpreadPct"].map(_spread_bucket)
    counts = [int((buckets == label).sum()) for label in labels]
    cheapest = frame.nlargest(5, "TradingValueVND")[["StockCode", "Underlying", "SpreadPct"]]
    cheapest = cheapest[cheapest["SpreadPct"].notna()].sort_values("SpreadPct")
    return {
        "available": True,
        "median": _num(depth.median()),
        "p25": _num(depth.quantile(0.25)),
        "p75": _num(depth.quantile(0.75)),
        "p90": _num(depth.quantile(0.9)),
        "buckets": [{"label": label, "count": count} for label, count in zip(labels, counts)],
        "cheapestAmongTopValue": _records(cheapest, ["StockCode", "Underlying", "SpreadPct"]),
    }


def build_board_artifact(frame: pd.DataFrame, *, endpoint: str, fetched_at: str | None = None,
                         snapshot_count: int | None = None) -> dict:
    """Gói toàn bộ kết quả phân tích thành dict JSON-safe (không NaN/Inf)."""
    quality = quality_checks(frame)
    return {
        "schemaVersion": 1,
        "kind": "yuanta-cw-board-analysis",
        "source": {
            "name": "Yuanta YS Radar — price board",
            "endpoint": endpoint,
            "stockType": "EW",
            "fetchedAt": fetched_at,
            "rowsInSnapshot": int(snapshot_count if snapshot_count is not None else len(frame)),
        },
        "units": {
            "price": "VND/CW (giá trần, sàn, tham chiếu, khớp lệnh cùng thang)",
            "volume": "CW",
            "tradingValue": "VND",
            "pct": "phần trăm (7,8 = 7,8%)",
            "evidence": "TotalVal ≈ TotalVol × AvgP trên toàn snapshot (xem quality.value_identity)",
        },
        "caveats": [
            "Chỉ là mặt cắt bảng giá tại thời điểm gọi; không có chuỗi ngày, không phải dữ liệu realtime.",
            "Không có ngày đáo hạn, strike, tỷ lệ chuyển đổi, tổ chức phát hành trong payload: không định giá, không Greeks, không khuyến nghị.",
            "Underlying suy ra từ quy ước mã CW, không phải trường do Yuanta công bố.",
            "FRoom, DeemP/DeemVol, SymbolAdminStatusCode được giữ nguyên, không diễn giải.",
            "Giá trị giao dịch suy ra từ đồng nhất thức của nguồn và được đối chiếu, không phải trường do API trả trực tiếp.",
        ],
        "summary": summarize(frame),
        "movers": top_movers(frame),
        "byUnderlying": by_underlying(frame)[:15],
        "spread": spread_profile(frame),
        "quality": quality,
        "counts": {
            "warrants": int(len(frame)),
            "underlyingGroups": int(frame["Underlying"].nunique(dropna=True)),
            "checks": len(quality["checks"]),
        },
    }


# ──────────────────────────────────────────────────────────────────
# XUẤT BẢN
# ──────────────────────────────────────────────────────────────────
# Cột làm tròn khi xuất CSV để file đọc được bằng mắt; giá trị trong bộ nhớ giữ đầy đủ.
_PRICE_COLUMNS = {
    "RefP", "CeilingP", "FloorP", "OpenP", "HighestP", "LowestP", "AvgP", "LastMP",
    "DeemP", "LastPrice", "SpreadAbs", "MidQuote", "TradingValueVND", "TotalVal",
    "FTBuyVal", "FTSellVal", "FRoom", "B1P", "B2P", "B3P", "S1P", "S2P", "S3P",
}
_PCT_COLUMNS = {
    "PriceChangePct", "OpenChangePct", "SpreadPct", "ValueSharePct",
    "TradingValueReconDiffPct",
}


def csv_ready(frame: pd.DataFrame) -> pd.DataFrame:
    """Bản sao đã làm tròn để ghi CSV (4 chữ số cho %, 2 cho VND, 2 cho bước giá)."""
    out = frame.copy()
    for column in out.columns:
        if not pd.api.types.is_float_dtype(out[column]):
            continue
        if column in _PCT_COLUMNS:
            out[column] = out[column].round(4)
        elif column in _PRICE_COLUMNS:
            out[column] = out[column].round(2)
        elif column == "SpreadTicks":
            out[column] = out[column].round(2)
    if "Traded" in out.columns:
        out["Traded"] = out["Traded"].map({True: 1, False: 0}).astype("Int64")
    return out


def write_csv(frame: pd.DataFrame, path: Path) -> Path:
    """Ghi CSV sạch (UTF-8, không index, cột ổn định) và trả về đường dẫn."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    csv_ready(frame).to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    return path


def write_json(payload: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False,
                   default=str) + "\n",
        encoding="utf-8",
    )
    return path


def _fmt_cell(value: Any) -> str:
    if value is None or value is pd.NA:
        return ""
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            return ""
        text = f"{float(value):,.2f}".rstrip("0").rstrip(".")
        return text or "0"
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return f"{int(value):,}"
    return str(value).replace("|", "\\|")


def _fmt_number(value: Any, digits: int) -> str:
    text = f"{float(value):,.{digits}f}"
    return text


def markdown_table(frame: pd.DataFrame, columns: Sequence[str],
                   titles: Sequence[str] | None = None, limit: int = 10,
                   digits: dict[str, int] | None = None) -> str:
    """Bảng Markdown thủ công (không cần ``tabulate``) để in ra terminal/log."""
    titles = list(titles or columns)
    if len(titles) != len(columns):
        raise ValueError("số tiêu đề phải bằng số cột")
    lines = ["| " + " | ".join(titles) + " |",
             "|" + "|".join("---" for _ in titles) + "|"]
    digits = digits or {}
    for _, row in frame.head(limit).iterrows():
        cells = []
        for col in columns:
            value = row.get(col)
            if col in digits and isinstance(value, (int, float, np.floating)) and pd.notna(value):
                cells.append(_fmt_number(value, digits[col]))
            else:
                cells.append(_fmt_cell(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
