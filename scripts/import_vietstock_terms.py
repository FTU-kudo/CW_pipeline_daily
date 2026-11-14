#!/usr/bin/env python3
"""Chuyển kho dữ liệu Vietstock (repo Vietstock_CW_bot) thành bảng điều khoản CW.

Đây là nguồn bổ sung cho khoảng trống lớn nhất của endpoint Yuanta: **điều khoản hợp
đồng**. Yuanta chỉ trả bảng giá (34 trường), nên không thể định giá. Repo Vietstock có:

    gia_thuc_hien        → strike K
    ngay_gd_cuoi_cung    → ngày đáo hạn (maturity)
    ty_le_chuyen_doi     → tỷ lệ chuyển đổi n, dạng "2 : 1"
    ck_co_so             → mã cổ phiếu cơ sở
    premium, don_bay     → đã tính sẵn, dùng để kiểm chứng S (xem dưới)

Giá cổ phiếu cơ sở ``S`` KHÔNG có trong file daily, nhưng suy ra được **chính xác** từ hai
công thức độc lập mà nguồn đã dùng:

    don_bay  = (S / CW) / n            →  S = don_bay × CW × n
    premium  = (K + CW×n − S) / S × 100 →  S = (K + CW×n) / (1 + premium/100)

Hai công thức cho cùng một ``S`` trên **400/400 mã** kiểm tra được (sai lệch < 1%), nên đây
không phải phỏng đoán: nếu một trong hai lệch, bản ghi đó bị đánh dấu và loại. ``S`` suy ra
được kiểm chứng chéo như vậy mới được dùng làm đầu vào Black–Scholes.

Cách dùng
---------
    # Đọc trực tiếp từ bản clone repo Vietstock
    python scripts/import_vietstock_terms.py --source ../Vietstock_CW_bot

    # Chỉ một ngày
    python scripts/import_vietstock_terms.py --source ../Vietstock_CW_bot --session 2026-11-13

    # Ghi luôn vào vị trí mà cwintel.data chờ sẵn (Vietstock parquet)
    python scripts/import_vietstock_terms.py --source ../Vietstock_CW_bot \
        --vietstock-cache output/private-data/cache/vietstock.parquet

Đầu ra: ``data/cw_terms/vietstock_terms.csv`` — một dòng cho mỗi (session, ticker), có cột
``crosscheck_pct`` ghi mức lệch giữa S suy từ hai công thức. Dòng nào lệch quá ngưỡng bị loại
khỏi bảng dùng để định giá và được báo rõ, không im lặng sửa.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

#: Sai lệch tối đa (%) giữa hai cách suy `S` để bản ghi được coi là nhất quán.
#: Hai công thức dùng chung K, CW, n nhưng premium làm tròn 2 chữ số và don_bay 2 chữ số,
#: nên sai số <1% là dư sức chấp nhận; lớn hơn nghĩa là dữ liệu nguồn không khớp.
S_CROSSCHECK_TOLERANCE_PCT = 1.0

COLUMNS: tuple[str, ...] = (
    "session", "ticker", "underlying", "issuer",
    "strike", "ratio", "maturity", "daysToMaturity",
    "underlyingPrice", "cwClose", "premiumPct", "leverage",
    "crosscheckPct", "crosscheckOk", "termsSource", "importedAt",
    # Hai cột dưới đây là hệ **đã điều chỉnh** của cùng hợp đồng. CW Việt Nam điều chỉnh
    # strike và tỷ lệ chuyển đổi mỗi khi cổ phiếu cơ sở chia thưởng/cổ tức, nên cặp
    # (`strike`, `ratio`) ở trên là hệ *gốc* và KHÔNG ghép được với giá đóng cửa thật.
    # Để trống khi nguồn không trả — engine sẽ tự dựng lại từ chênh lệch giá.
    "strikeAdjusted", "ratioAdjusted",
    # Ngày đáo hạn là cột riêng, KHÔNG phải ngày giao dịch cuối cùng. Hai ngày này lệch nhau
    # vài ngày; dùng sai làm T lệch theo, kéo theta/vega lệch trên toàn bộ mã.
    "maturityAdjusted",
)


def _num(value) -> float | None:
    """Số từ chuỗi có dấu phẩy nghìn ('31,800') hoặc số thực."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        out = float(value)
    else:
        text = str(value).replace(",", "").replace("%", "").strip()
        try:
            out = float(text)
        except ValueError:
            return None
    return out if math.isfinite(out) else None


_RATIO_RE = re.compile(r"^\s*([\d.,]+)\s*[:/]\s*([\d.,]+)\s*$")


def parse_ratio(value) -> float | None:
    """Chuỗi tỷ lệ ``"2 : 1"`` → 2.0 (số CW cho 1 cổ phiếu, đúng nghĩa của engine BS).

    Nhận cả ``"2:1"``, ``"2 / 1"`` và số thuần.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value) if value and value > 0 else None
    match = _RATIO_RE.match(str(value))
    if not match:
        return None
    left, right = (_num(match.group(1)), _num(match.group(2)))
    if not left or not right or right <= 0:
        return None
    out = left / right
    return out if out > 0 else None


def parse_maturity(value) -> date | None:
    """Ngày ``dd/mm/yyyy`` (định dạng Vietstock dùng)."""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def derive_underlying_price(strike: float, cw: float, ratio: float,
                            premium_pct: float | None, leverage: float | None
                            ) -> tuple[float | None, float | None, float | None]:
    """Suy ``S`` từ hai công thức độc lập của nguồn; trả ``(S, lệch %, S thứ hai)``.

    Chọn công thức đòn bẩy làm giá trị chính vì nó **tuyến tính** theo ``don_bay`` (không có
    phép chia), nên sai số làm tròn của nguồn được giữ nguyên tỷ lệ thay vì khuếch đại gần
    điểm hoà vốn. Khi đòn bẩy thiếu, dùng công thức premium.
    """
    s_lev = leverage * cw * ratio if (leverage and cw and ratio) else None
    s_prem = ((strike + cw * ratio) / (1 + premium_pct / 100)
              if (premium_pct is not None and premium_pct > -100 and strike and cw and ratio)
              else None)

    if s_lev and s_prem:
        diff = abs(s_lev - s_prem) / s_prem * 100
        return s_lev, diff, s_prem
    if s_lev:
        return s_lev, None, None
    if s_prem:
        return s_prem, None, None
    return None, None, None


def terms_from_records(records: list[dict], session: str) -> list[dict]:
    """Một ngày dữ liệu Vietstock → các dòng điều khoản (chưa lọc)."""
    imported = datetime.now(timezone.utc).isoformat(timespec="seconds")
    session_day = date.fromisoformat(session)
    rows = []
    for rec in records:
        ticker = str(rec.get("ma_cw") or "").strip().upper()
        if not ticker:
            continue
        strike = _num(rec.get("gia_thuc_hien"))
        ratio = parse_ratio(rec.get("ty_le_chuyen_doi"))
        # Ngày đáo hạn thật. Nguồn có cả `ngay_dao_han` và `ngay_gd_cuoi_cung`; chỉ khi thiếu
        # ngày đáo hạn mới lùi về ngày giao dịch cuối cùng, và điều đó được đánh dấu.
        maturity_real = parse_maturity(rec.get("ngay_dao_han"))
        maturity = maturity_real or parse_maturity(rec.get("ngay_gd_cuoi_cung"))
        strike_adj = _num(rec.get("gia_th_dieu_chinh")) or None
        ratio_adj = parse_ratio(rec.get("tlcd_dieu_chinh"))
        cw_close = _num(rec.get("gia_hien_tai"))
        premium = _num(rec.get("premium"))
        leverage = _num(rec.get("don_bay"))

        underlying_price, crosscheck, _ = derive_underlying_price(
            strike, cw_close, ratio, premium, leverage)

        days = (maturity - session_day).days if maturity else None
        rows.append({
            "session": session,
            "ticker": ticker,
            "underlying": (str(rec.get("ck_co_so") or "").strip().upper() or None),
            "issuer": (str(rec.get("to_chuc_ph_cw") or "").strip() or None),
            "strike": round(strike, 4) if strike else None,
            "ratio": round(ratio, 6) if ratio else None,
            "maturity": maturity.isoformat() if maturity else None,
            "daysToMaturity": days,
            "underlyingPrice": round(underlying_price, 4) if underlying_price else None,
            "cwClose": cw_close,
            "premiumPct": premium,
            "leverage": leverage,
            "crosscheckPct": round(crosscheck, 4) if crosscheck is not None else None,
            "crosscheckOk": (crosscheck is not None
                             and crosscheck <= S_CROSSCHECK_TOLERANCE_PCT),
            "termsSource": "vietstock",
            "importedAt": imported,
            "strikeAdjusted": round(strike_adj, 4) if strike_adj else None,
            "ratioAdjusted": round(ratio_adj, 6) if ratio_adj else None,
            # Chỉ điền khi nguồn thật sự có `ngay_dao_han`. Để trống nếu thiếu, KHÔNG chép
            # đè bằng ngày giao dịch cuối cùng — hai ngày khác nhau và việc lẫn chúng chính
            # là lỗi mà cột này sinh ra để tránh.
            "maturityAdjusted": maturity_real.isoformat() if maturity_real else None,
        })
    return rows


def load_daily_files(source: Path) -> dict[str, list[dict]]:
    """Đọc ``docs/data/daily/*.json`` của repo Vietstock, trả ``{session: records}``."""
    daily = Path(source) / "docs" / "data" / "daily"
    if not daily.exists():
        raise SystemExit(
            f"LỖI: không thấy {daily}. Trỏ --source vào bản clone repo Vietstock_CW_bot "
            "(thư mục có docs/data/daily/).")
    out: dict[str, list[dict]] = {}
    for path in sorted(daily.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"BỎ QUA {path.name}: {exc}", file=sys.stderr)
            continue
        session = payload.get("date")
        records = payload.get("records") or []
        if session and records:
            out[str(session)] = records
    return out


def build_terms_frame(days: dict[str, list[dict]]) -> pd.DataFrame:
    rows: list[dict] = []
    for session in sorted(days):
        rows.extend(terms_from_records(days[session], session))
    frame = pd.DataFrame(rows, columns=list(COLUMNS))
    if frame.empty:
        return frame
    frame = frame.drop_duplicates(subset=["session", "ticker"], keep="last")
    return frame.sort_values(["session", "ticker"], kind="stable").reset_index(drop=True)


def report_quality(frame: pd.DataFrame) -> dict:
    """Thống kê độ phủ + các dòng không dùng được cho định giá, kèm lý do."""
    if frame.empty:
        return {"rows": 0}
    usable = frame[frame["crosscheckOk"].fillna(False)]
    missing = {
        "strike": int(frame["strike"].isna().sum()),
        "ratio": int(frame["ratio"].isna().sum()),
        "maturity": int(frame["maturity"].isna().sum()),
        "underlyingPrice": int(frame["underlyingPrice"].isna().sum()),
        "crosscheckFailed": int((~frame["crosscheckOk"].fillna(False)).sum()),
        "strikeAdjusted": int(frame["strikeAdjusted"].notna().sum()),
        "ratioAdjusted": int(frame["ratioAdjusted"].notna().sum()),
    }
    return {
        "rows": int(len(frame)),
        "sessions": int(frame["session"].nunique()),
        "tickers": int(frame["ticker"].nunique()),
        "first": frame["session"].min(),
        "last": frame["session"].max(),
        "pricingReady": int(len(usable)),
        "pricingReadyPct": round(len(usable) / len(frame) * 100, 2),
        "missing": missing,
        "crosscheckTolerancePct": S_CROSSCHECK_TOLERANCE_PCT,
    }


def to_vietstock_cache(frame: pd.DataFrame, path: Path) -> Path:
    """Ghi parquet với đúng tên cột mà ``cwintel.data.build_master`` đọc.

    Đây là định dạng riêng của pipeline cũ; chỉ tạo khi người dùng yêu cầu rõ, vì thư mục
    ``output/private-data`` không được commit.
    """
    usable = frame[frame["crosscheckOk"].fillna(False)].copy()
    out = pd.DataFrame({
        "ma_cw": usable["ticker"],
        "ck_co_so": usable["underlying"],
        "to_chuc_ph_cw": usable["issuer"],
        "ngay_phat_hanh": pd.NaT,
        "ngay_niem_yet": pd.NaT,
        "ngay_gd_dau_tien": pd.NaT,
        "ngay_gd_cuoi_cung": pd.to_datetime(usable["maturity"], errors="coerce"),
        "ngay_dao_han": pd.to_datetime(usable["maturity"], errors="coerce"),
        "gia_thuc_hien": usable["strike"],
        "gia_th_dieu_chinh": usable["strikeAdjusted"],
        "ty_le_chuyen_doi": usable["ratio"],
        "tlcd_dieu_chinh": usable["ratioAdjusted"],
        "kl_niem_yet": pd.NA,
        "kl_luu_hanh": pd.NA,
        "thoi_han": pd.NA,
        "gia_hien_tai": usable["cwClose"],
        "hoa_von": usable["strike"] + usable["cwClose"] * usable["ratio"],
        "trang_thai_cw": pd.NA,
        "gia_ck_co_so": usable["underlyingPrice"],
        "asof": pd.to_datetime(usable["session"], errors="coerce"),
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, index=False)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True,
                        help="thư mục clone repo Vietstock_CW_bot")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "cw_terms" / "vietstock_terms.csv")
    parser.add_argument("--session", default=None,
                        help="chỉ nhập một ngày YYYY-MM-DD (mặc định: mọi ngày có trong nguồn)")
    parser.add_argument("--vietstock-cache", type=Path, default=None,
                        help="ghi parquet cho cwintel.data (output/private-data/cache)")
    parser.add_argument("--json", type=Path, default=None, help="ghi báo cáo chất lượng")
    args = parser.parse_args(argv)

    days = load_daily_files(args.source)
    if args.session:
        days = {k: v for k, v in days.items() if k == args.session}
        if not days:
            print(f"LỖI: nguồn không có dữ liệu ngày {args.session}.", file=sys.stderr)
            return 1
    if not days:
        print("LỖI: không đọc được ngày dữ liệu nào.", file=sys.stderr)
        return 1

    frame = build_terms_frame(days)
    quality = report_quality(frame)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out, index=False, encoding="utf-8", lineterminator="\n")

    print(f"Vietstock → điều khoản: {quality['rows']} dòng, {quality['tickers']} mã, "
          f"{quality['sessions']} phiên ({quality['first']} → {quality['last']})")
    print(f"  Đủ đầu vào định giá (S, K, n, ngày đáo hạn khớp chéo): "
          f"{quality['pricingReady']}/{quality['rows']} ({quality['pricingReadyPct']}%)")
    missing = quality["missing"]
    if any(missing.values()):
        print(f"  Thiếu/không dùng được: {missing}")
    print(f"CSV: {args.out}")

    if args.vietstock_cache:
        path = to_vietstock_cache(frame, args.vietstock_cache)
        print(f"Parquet cho cwintel.data: {path} ({quality['pricingReady']} dòng)")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        print(f"Báo cáo chất lượng: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
