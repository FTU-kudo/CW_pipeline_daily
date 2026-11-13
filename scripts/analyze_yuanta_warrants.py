#!/usr/bin/env python3
"""Lấy bảng giá chứng quyền (EW) từ Yuanta YS Radar, làm sạch và phân tích.

Cách dùng
---------
    python scripts/analyze_yuanta_warrants.py                 # gọi API, phân tích, ghi 2 file
    python scripts/analyze_yuanta_warrants.py --offline FILE  # dùng payload JSON đã lưu (không gọi mạng)
    python scripts/analyze_yuanta_warrants.py --csv out.csv --md-rows 15

Đầu ra
------
* ``yuanta_covered_warrants.csv`` — mỗi dòng một CW, đủ trường gốc của API + cột suy ra.
* ``docs/data/yuanta_board_analysis.json`` — tổng hợp, top biến động, nhóm theo cổ phiếu
  cơ sở, phân bố chênh lệch mua–bán và báo cáo kiểm tra chất lượng (schemaVersion 1).

Cả hai được ghi nguyên tử; file cũ chỉ bị thay khi lần chạy này hoàn tất thành công.
Mã thoát: 0 = thành công, 1 = lỗi mạng/schema, 3 = kiểm tra chất lượng mức "fail".
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cwintel.yuanta_board import (  # noqa: E402
    BoardIntegrityError,
    build_board_artifact,
    clean_board,
    markdown_table,
    write_csv,
    write_json,
)
from scripts.yuanta_client import API_URL, YuantaHTTPError, fetch_board  # noqa: E402

DEFAULT_CSV = ROOT / "yuanta_covered_warrants.csv"
DEFAULT_JSON = ROOT / "docs" / "data" / "yuanta_board_analysis.json"

# Bảng Markdown in ra màn hình: tên cột kỹ thuật → nhãn tiếng Việt.
DISPLAY_COLUMNS = (
    "StockCode", "Underlying", "LastPrice", "PriceChangePct", "TotalVol",
    "TradingValueVND", "TradingValueReconDiffPct", "SpreadPct", "ValueSharePct",
)
DISPLAY_TITLES = (
    "Mã CW", "Cơ sở", "Giá (VND)", "%Ngày", "KL (CW)",
    "GT (VND)", "Lệch đối chiếu (%)", "Spread (%)", "Tỷ trọng GT (%)",
)


def load_payload(path: Path) -> dict:
    """Đọc payload JSON đã lưu — dùng cho test offline và kiểm tra lại một snapshot."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def extract_rows(payload: dict) -> list[dict]:
    """Kiểm tra envelope và trả về danh sách dòng thô.

    Chấp nhận hai dạng đã được kiểm chứng:
      * payload API gốc  : ``{"success": true, "response": [...]}``
      * snapshot đã publish: ``{"schemaVersion": 1, "rows": [...]}``
        (``docs/data/yuanta_snapshot.json`` do ``fetch_yuanta_snapshot.py`` ghi)
    """
    if not isinstance(payload, dict):
        raise BoardIntegrityError(f"payload phải là object, nhận {type(payload).__name__}")
    if "response" in payload or "success" in payload:
        if payload.get("success") is not True:
            raise BoardIntegrityError(f"success != true (giá trị: {payload.get('success')!r}): "
                                      "API từ chối hoặc trả lỗi")
        rows = payload.get("response")
        if not isinstance(rows, list) or not rows:
            raise BoardIntegrityError("không có danh sách 'response' hoặc danh sách rỗng")
        return rows
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise BoardIntegrityError(
            "payload không có 'response' (API gốc) lẫn 'rows' (snapshot đã publish)"
        )
    return rows


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        Path(temp_name).replace(path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", type=Path, metavar="FILE",
                        help="đọc payload JSON đã lưu thay vì gọi API")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="đường dẫn CSV đầu ra")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="đường dẫn JSON phân tích")
    parser.add_argument("--retries", type=int, default=3, help="số lần thử khi gọi API (mặc định 3)")
    parser.add_argument("--transport", choices=("auto", "curl_cffi", "requests"),
                        default="auto",
                        help="auto: dùng curl_cffi (TLS giống Chrome) nếu đã cài")
    parser.add_argument("--no-warmup", action="store_true",
                        help="bỏ bước ghé trang chủ lấy cookie CDN trước khi gọi API")
    parser.add_argument("--md-rows", type=int, default=10, help="số dòng bảng Markdown (mặc định 10)")
    parser.add_argument("--skip-json", action="store_true",
                        help="chỉ ghi CSV (dùng khi chỉ cần dữ liệu sạch)")
    args = parser.parse_args(argv)

    if args.offline:
        try:
            payload = load_payload(args.offline)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"LỖI: không đọc được payload offline {args.offline}: {exc}", file=sys.stderr)
            return 1
        print(f"Nguồn: file offline {args.offline}")
    else:
        try:
            payload = fetch_board(retries=args.retries, transport=args.transport,
                                  warmup=not args.no_warmup)
        except (YuantaHTTPError, ValueError) as exc:
            print(f"LỖI: không gọi được API Yuanta: {exc}", file=sys.stderr)
            body = getattr(exc, "body", None)
            if body:
                print(f"--- body ({len(body)} ký tự) ---", file=sys.stderr)
                print(body, file=sys.stderr)
            return 1
        print(f"Nguồn: {API_URL}")

    fetched_at = datetime.now(timezone.utc)
    try:
        rows = extract_rows(payload)
        frame = clean_board(rows, fetched_at=fetched_at)
    except BoardIntegrityError as exc:
        print(f"LỖI: snapshot không dùng được: {exc}", file=sys.stderr)
        return 1

    artifact = build_board_artifact(
        frame,
        endpoint=API_URL,
        fetched_at=fetched_at.isoformat(timespec="seconds"),
        snapshot_count=len(rows),
    )

    # CSV: ghi qua buffer rồi thay thế để tránh file dở dang khi process bị kill.
    buffer_path = args.csv.with_suffix(args.csv.suffix + ".tmp")
    write_csv(frame, buffer_path)
    _atomic_write(args.csv, buffer_path.read_text(encoding="utf-8"))
    buffer_path.unlink(missing_ok=True)
    if not args.skip_json:
        write_json(artifact, args.json)

    summary = artifact["summary"]
    print(f"\nĐã làm sạch {len(frame)} CW | có khớp lệnh: {summary['traded']} | "
          f"không khớp: {summary['untraded']} | {summary['underlyings']} cổ phiếu cơ sở")
    print(f"Tổng giá trị giao dịch phiên: {summary['totalValueVND']:,.0f} VND · "
          f"KL: {summary['totalVolume']:,.0f} CW")
    print(f"Spread trung vị: {summary['medianSpreadPct']}% "
          f"({summary['medianSpreadTicks']} bước giá) · "
          f"tăng {summary['gainers']} / giảm {summary['losers']} / đứng {summary['unchanged']}")

    digits = {"TradingValueVND": 0, "PriceChangePct": 2, "SpreadPct": 2,
              "ValueSharePct": 2, "TradingValueReconDiffPct": 3, "TotalVol": 0,
              "LastPrice": 0}
    print(f"\n{min(args.md_rows, len(frame))} dòng đầu theo mã (đầy đủ cột trong CSV):\n")
    print(markdown_table(frame, DISPLAY_COLUMNS, DISPLAY_TITLES, limit=args.md_rows,
                         digits=digits))

    print("\nTop 5 giá trị giao dịch:\n")
    print(markdown_table(frame.nlargest(5, "TradingValueVND"), DISPLAY_COLUMNS,
                         DISPLAY_TITLES, limit=5, digits=digits))

    quality = artifact["quality"]
    print(f"\nKiểm tra chất lượng: {quality['status']} "
          f"({quality['failed']} fail, {quality['warned']} warn)")
    for check in quality["checks"]:
        if check["status"] in {"fail", "warn"}:
            print(f"  [{check['status']}] {check['title']} — {check['amount']} dòng "
                  f"{check['value']}")

    print(f"\nCSV: {args.csv}")
    if not args.skip_json:
        print(f"JSON: {args.json}")
    print("Lưu ý: đây là mặt cắt bảng giá, không có lịch sử/định giá/khuyến nghị.")
    return 3 if quality["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
