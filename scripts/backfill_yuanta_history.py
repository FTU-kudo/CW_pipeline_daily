#!/usr/bin/env python3
"""Ghi snapshot Yuanta vào kho OHLCV theo ngày, rồi xuất dữ liệu cho trang phân tích.

    python scripts/backfill_yuanta_history.py --offline docs/data/yuanta_snapshot.json
    python scripts/backfill_yuanta_history.py            # gọi API rồi ghi (1 request)

Việc nó làm
-----------
1. Xác định **phiên** của snapshot (chỉ là bar hoàn chỉnh nếu chụp sau 15:10 ICT).
2. Upsert bar của phiên đó vào ``data/cw_history/YYYY-MM.csv`` (idempotent).
3. Ghi lại ``docs/data/yuanta_sessions.json`` — chuỗi theo mã, độ phủ, khoảng trống.
4. Ghi ``docs/data/yuanta_analytics.json`` — xếp hạng thanh khoản, nhóm cơ sở, mã "chết".
5. (tuỳ chọn) ``--cwintel-cache PATH``: xuất parquet đúng schema ``cwintel`` để dashboard
   CW Analytics cũ đọc được OHLCV.

Không backfill quá khứ: endpoint chỉ có bảng giá hiện tại, nên lịch sử bắt đầu từ lần chạy
đầu tiên và dày lên mỗi ngày. Ngày thiếu được ghi vào ``missingSessions`` thay vì nội suy.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cwintel import yuanta_history as hist  # noqa: E402
from cwintel.yuanta_analytics import build_analytics  # noqa: E402
from cwintel.yuanta_board import BoardIntegrityError, clean_board, write_json  # noqa: E402
from cwintel.yuanta_intraday import ref_continuity  # noqa: E402
from scripts.analyze_yuanta_warrants import extract_rows  # noqa: E402
from scripts.yuanta_client import YuantaHTTPError, fetch_board  # noqa: E402

DEFAULT_SNAPSHOT = ROOT / "docs" / "data" / "yuanta_snapshot.json"
DEFAULT_SESSIONS = ROOT / "docs" / "data" / "yuanta_sessions.json"
DEFAULT_ANALYTICS = ROOT / "docs" / "data" / "yuanta_analytics.json"


def _load_snapshot(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fetched_at(payload: dict, fallback: datetime) -> str:
    value = payload.get("fetchedAt") if isinstance(payload, dict) else None
    return str(value) if value else fallback.astimezone(timezone.utc).isoformat(timespec="seconds")


def build_sessions_payload(history, coverage: dict, *, gaps: dict[str, list[str]]) -> dict:
    return {
        "schemaVersion": 1,
        "kind": "yuanta-cw-history",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "units": {"price": "VND/CW", "volume": "CW", "value": "VND"},
        "coverage": coverage,
        "caveats": [
            "Lịch sử bắt đầu từ lần chạy đầu tiên của workflow; endpoint không có dữ liệu quá khứ.",
            "Mỗi bar chỉ hoàn chỉnh khi snapshot được chụp sau 15:10 ICT; bar giữa phiên bị đánh dấu provisional.",
            "Mã không khớp lệnh trong phiên có close = null (không lấy RefP lấp vào).",
            "Ngày thiếu nằm trong coverage.missingSessions — không nội suy, không lặp giá.",
        ],
        "tickers": hist.series_payload(history, gaps=gaps),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT,
                        help="snapshot đã lưu (mặc định docs/data/yuanta_snapshot.json)")
    parser.add_argument("--offline", action="store_true",
                        help="chỉ đọc snapshot đã lưu, không gọi API")
    parser.add_argument("--store", type=Path, default=hist.STORE_DIR,
                        help="thư mục kho CSV theo tháng (mặc định data/cw_history)")
    parser.add_argument("--sessions-out", type=Path, default=DEFAULT_SESSIONS)
    parser.add_argument("--analytics-out", type=Path, default=DEFAULT_ANALYTICS)
    parser.add_argument("--cwintel-cache", type=Path, default=None,
                        help="xuất parquet OHLCV theo schema cwintel (tuỳ chọn)")
    parser.add_argument("--limit", type=int, default=hist.SERIES_LIMIT,
                        help="số phiên giữ trong chuỗi JSON (mặc định 120)")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    if args.offline:
        if not args.snapshot.exists():
            print(f"LỖI: không có snapshot để đọc: {args.snapshot}", file=sys.stderr)
            return 1
        payload = _load_snapshot(args.snapshot)
    else:
        try:
            payload = fetch_board()
        except YuantaHTTPError as exc:
            print(f"LỖI: không gọi được API Yuanta: {exc}", file=sys.stderr)
            if exc.body:
                print(exc.body, file=sys.stderr)
            return 1
        write_json(payload, args.snapshot)

    try:
        rows = extract_rows(payload)
    except BoardIntegrityError as exc:
        print(f"LỖI: snapshot không dùng được: {exc}", file=sys.stderr)
        return 1
    fetched = _fetched_at(payload, now)
    snapshot_session = hist.resolve_session(fetched)

    try:
        bars = hist.bars_from_rows(rows, snapshot_session)
        result = hist.upsert_bars(args.store, bars)
    except hist.HistoryError as exc:
        print(f"LỖI: không ghi được lịch sử: {exc}", file=sys.stderr)
        return 1

    history = hist.load_history(args.store)
    cov = hist.coverage(history)
    gaps = hist.ticker_gaps(history)
    sessions_payload = build_sessions_payload(history, cov, gaps=gaps)

    frame = clean_board(rows, fetched_at=datetime.fromisoformat(fetched.replace("Z", "+00:00")))
    analytics = build_analytics(frame, history=history, asof=snapshot_session.iso)

    write_json(sessions_payload, args.sessions_out)
    write_json(analytics, args.analytics_out)
    if args.cwintel_cache:
        written = hist.write_cwintel_cache(history, args.cwintel_cache)
        print(f"Cache cwintel: {written} ({len(hist.to_cwintel_ohlcv(history))} bar OHLCV)")

    state = "đã đóng" if snapshot_session.closed else "DỞ DANG (chụp trước 15:10 ICT)"
    print(f"Phiên {snapshot_session.iso} — {state}; nguồn fetchedAt={fetched}")
    print(f"Upsert: +{result.added} mới, ~{result.updated} cập nhật, "
          f"={result.unchanged} không đổi, bảo vệ {result.skipped_closed_protected} bar đã đóng")
    print(f"Kho: {cov['sessions']} phiên ({cov['first']}→{cov['last']}), "
          f"{cov['tickers']} mã, {cov['rows']} dòng, "
          f"{cov['tradedSharePct']}% dòng có khớp lệnh")
    if cov["missingSessions"]:
        print(f"Phiên thiếu (không nội suy): {len(cov['missingSessions'])} — "
              f"{cov['missingSessions'][:10]}{'…' if len(cov['missingSessions']) > 10 else ''}")
    else:
        print("Không có phiên nào bị thiếu trong khoảng dữ liệu.")
    # ── Kiểm tra liên tục bằng RefP (= giá đóng cửa phiên trước) ──
    # Chỉ có thể làm được khi kho đã có phiên trước; đây là chẩn đoán dữ liệu, không phải
    # chỉ báo. Nếu RefP không khớp close phiên trước, hoặc phiên trước mất khỏi kho, ta biết
    # chính xác chỗ đứt thay vì phát hiện muộn qua một chuỗi giá trông vẫn liền.
    try:
        analytics_frame = clean_board(rows, fetched_at=snapshot_session.fetched_at)
        cont = ref_continuity(analytics_frame, hist.load_history(args.store))
    except Exception as exc:  # noqa: BLE001 - chẩn đoán không được làm hỏng lần ghi
        cont = {"available": False, "reason": f"bỏ qua kiểm tra liên tục: {exc}"}

    if cont.get("available"):
        c = cont["summary"]
        print(f"Liên tục RefP vs close {cont['prevSession']}: "
              f"{c['linked']}/{c['checked']} khớp ({c['linkedPct']}%) · "
              f"lệch>{c['tolerancePct']}%: {c['mismatch']} · "
              f"thiếu phiên: {c['missingSession']} · "
              f"không có close để so: {c['untradedRef']} → {c['verdict']}")
        if c["mismatch"] or c["missingSession"]:
            print("  Chi tiết đứt gãy: " + ", ".join(
                f"{r['t']}({r['status']})" for r in cont["rows"][:8]))
    else:
        print(f"Kiểm tra liên tục: {cont.get('reason')}")

    print(f"Chuỗi: {args.sessions_out} · Phân tích: {args.analytics_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
