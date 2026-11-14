#!/usr/bin/env python3
"""Đồng bộ đường cong lợi suất TPCP từ repo VN_Bond_Yield_pipeline về kho cục bộ.

Vì sao cần script này: ``cwintel.yuanta_valuation`` cần lãi suất phi rủi ro cho **từng kỳ hạn
CW**. Trước đây nó dùng hằng số ``config.DEFAULT_RISK_FREE``. Repo
``FTU-kudo/VN_Bond_Yield_pipeline`` cập nhật lợi suất TPCP hằng ngày từ HNX, nên ``r`` trở
thành số liệu thị trường thật thay vì tham số phần mềm.

Nguồn đọc: ``cache/hnx_yield_curve_daily.parquet`` của repo đó (dạng long, 4 cột
``date/tenor/rate_type/value``). Chỉ lấy ``rate_type == "spot_continuous"`` vì đó là lợi suất
ghép lãi liên tục — cùng cơ sở với ``exp(-rT)`` trong Black–Scholes. Hai loại còn lại
(``par_yield`` cơ sở coupon, ``spot_annual`` cơ sở gộp năm) **không** dùng được.

Cách dùng
---------
    # Clone sẵn rồi trỏ vào
    python scripts/sync_bond_yield.py --source /tmp/vn_bond --out data/bond_yield/yield_curve.csv

    # Chế độ workflow: tự clone nông nếu chưa có
    python scripts/sync_bond_yield.py --clone

    # Chỉ kiểm tra, không ghi
    python scripts/sync_bond_yield.py --source /tmp/vn_bond --dry-run

Đầu ra: CSV ``date,tenor,rate`` — ``rate`` theo **phần trăm** như nguồn, để đọc bằng mắt
được; ``cwintel.yield_curve`` tự đổi sang thập phân khi nạp.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from cwintel import yield_curve as yc  # noqa: E402

REPO_URL = "https://github.com/FTU-kudo/VN_Bond_Yield_pipeline.git"
#: Đường dẫn kho parquet trong repo nguồn.
CACHE_RELPATH = Path("cache") / "hnx_yield_curve_daily.parquet"


def _clone(dest: Path) -> bool:
    """Clone nông, chỉ lấy phần cần. Trả ``True`` nếu thành công."""
    if not shutil.which("git"):
        print("LỖI: không có git để clone repo nguồn.", file=sys.stderr)
        return False
    tmp = Path(tempfile.mkdtemp(prefix="vnbond_"))
    cmd = ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
           REPO_URL, str(tmp / "repo")]
    if subprocess.run(cmd, capture_output=True).returncode != 0:
        print("LỖI: clone repo nguồn thất bại.", file=sys.stderr)
        return False
    if subprocess.run(["git", "sparse-checkout", "set", "cache"],
                      cwd=tmp / "repo", capture_output=True).returncode != 0:
        print("LỖI: sparse-checkout thất bại.", file=sys.stderr)
        return False
    src = tmp / "repo" / CACHE_RELPATH
    if not src.exists():
        print(f"LỖI: không thấy {CACHE_RELPATH} trong repo nguồn.", file=sys.stderr)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def build_curve_frame(parquet_path: Path) -> tuple[pd.DataFrame, dict]:
    """Parquet nguồn → (khung ``date,tenor,rate`` chỉ spot_continuous, chẩn đoán).

    Lọc và **không** sửa số: nếu lợi suất ngoài dải hợp lý thì loại dòng đó và **đếm** vào
    chẩn đoán, không im lặng kẹp về biên.
    """
    raw = pd.read_parquet(parquet_path)
    needed = {"date", "tenor", "rate_type", "value"}
    missing = needed - set(raw.columns)
    if missing:
        raise SystemExit(f"LỖI: parquet nguồn thiếu cột {sorted(missing)}")

    diag: dict = {
        "sourceRows": int(len(raw)),
        "rateTypesPresent": sorted(raw["rate_type"].dropna().unique().tolist()),
    }
    frame = raw[raw["rate_type"] == yc.RATE_TYPE].copy()
    diag["rowsAfterRateType"] = int(len(frame))
    if frame.empty:
        raise SystemExit(f"LỖI: nguồn không có dòng {yc.RATE_TYPE} nào.")

    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"])
    frame["tenor"] = frame["tenor"].astype(str).str.upper().str.strip()
    unknown = sorted(set(frame["tenor"]) - set(yc.TENOR_YEARS))
    if unknown:
        diag["tenorsIgnored"] = unknown
    frame = frame[frame["tenor"].isin(yc.TENOR_YEARS)]
    diag["rowsAfterTenorFilter"] = int(len(frame))

    frame["rate"] = pd.to_numeric(frame["value"], errors="coerce")
    out_of_range = frame["rate"].notna() & (
        (frame["rate"] < yc.MIN_RATE_PCT) | (frame["rate"] > yc.MAX_RATE_PCT))
    diag["rowsOutOfRange"] = int(out_of_range.sum())
    frame = frame[~out_of_range]
    frame = frame.dropna(subset=["rate"])

    out = (frame[["date", "tenor", "rate"]]
           .drop_duplicates(subset=["date", "tenor"], keep="last")
           .sort_values(["date", "tenor"]).reset_index(drop=True))
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")

    diag.update({
        "rows": int(len(out)),
        "sessions": int(out["date"].nunique()) if len(out) else 0,
        "first": out["date"].min() if len(out) else None,
        "last": out["date"].max() if len(out) else None,
        "tenors": sorted(out["tenor"].unique().tolist()) if len(out) else [],
    })
    return out, diag


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=None,
                        help="thư mục clone repo VN_Bond_Yield_pipeline (có cache/)")
    parser.add_argument("--clone", action="store_true",
                        help="tự clone nông repo nguồn nếu chưa có --source")
    parser.add_argument("--out", type=Path, default=yc.DEFAULT_CURVE_PATH,
                        help="CSV đích (mặc định data/bond_yield/yield_curve.csv)")
    parser.add_argument("--dry-run", action="store_true", help="chỉ báo cáo, không ghi")
    parser.add_argument("--json", type=Path, default=None, help="ghi báo cáo chẩn đoán")
    args = parser.parse_args(argv)

    parquet_path: Path | None = None
    if args.source:
        parquet_path = Path(args.source) / CACHE_RELPATH
        if not parquet_path.exists():
            print(f"LỖI: không thấy {parquet_path}.", file=sys.stderr)
            return 1
    elif args.clone:
        staged = Path(tempfile.mkdtemp(prefix="vnbond_sync_")) / "yield_curve.parquet"
        if not _clone(staged):
            return 1
        parquet_path = staged
    else:
        print("LỖI: cần --source hoặc --clone.", file=sys.stderr)
        return 1

    try:
        frame, diag = build_curve_frame(parquet_path)
    except (OSError, ValueError) as exc:
        print(f"LỖI: đọc parquet nguồn thất bại — {exc}", file=sys.stderr)
        return 1

    print(f"Đường cong lợi suất TPCP ({yc.RATE_TYPE}): {diag['rows']} dòng · "
          f"{diag['sessions']} phiên ({diag['first']} → {diag['last']})")
    print(f"  Kỳ hạn: {', '.join(diag['tenors'])}")
    if diag.get("tenorsIgnored"):
        print(f"  Bỏ qua kỳ hạn ngoài danh mục chuẩn: {diag['tenorsIgnored']}")
    if diag["rowsOutOfRange"]:
        print(f"  Loại {diag['rowsOutOfRange']} dòng lợi suất ngoài dải "
              f"{yc.MIN_RATE_PCT}–{yc.MAX_RATE_PCT}%")

    if args.dry_run:
        print("Chế độ --dry-run: không ghi tệp.")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.out, index=False, encoding="utf-8", lineterminator="\n")
        size_kb = args.out.stat().st_size / 1024
        print(f"CSV: {args.out} ({size_kb:.0f} KB)")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(diag, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        print(f"Chẩn đoán: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
