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

import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cwintel import yuanta_history as hist  # noqa: E402
from cwintel.yuanta_analytics import build_analytics  # noqa: E402
from cwintel.yuanta_board import BoardIntegrityError, clean_board, write_json  # noqa: E402
from cwintel import yuanta_detail  # noqa: E402
from cwintel import yuanta_underlying as hist_underlying  # noqa: E402
from cwintel import yield_curve  # noqa: E402
from cwintel.yuanta_intraday import ref_continuity  # noqa: E402
from scripts.analyze_yuanta_warrants import extract_rows  # noqa: E402
from scripts.yuanta_client import YuantaHTTPError, fetch_board  # noqa: E402

DEFAULT_SNAPSHOT = ROOT / "docs" / "data" / "yuanta_snapshot.json"
DEFAULT_SESSIONS = ROOT / "docs" / "data" / "yuanta_sessions.json"
DEFAULT_DETAILS = ROOT / "docs" / "data" / "yuanta_details.json"
DEFAULT_BOARD_ANALYSIS = ROOT / "docs" / "data" / "yuanta_board_analysis.json"
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
    parser.add_argument("--details-out", type=Path, default=DEFAULT_DETAILS,
                        help="file chi tiết từng chứng quyền cho trang bấm vào mã")
    parser.add_argument("--board-analysis", type=Path, default=DEFAULT_BOARD_ANALYSIS,
                        help="phân tích bảng giá đã publish (movers theo mã)")
    parser.add_argument("--underlying-store", type=Path,
                        default=ROOT / "data" / "underlying_history",
                        help="kho lịch sử cổ phiếu cơ sở (parquet/mã); thiếu thì S lấy từ "
                             "Vietstock và không có HV")
    parser.add_argument("--terms", type=Path, default=ROOT / "data" / "cw_terms" / "vietstock_terms.csv",
                        help="bảng điều khoản (strike/ratio/đáo hạn) từ Vietstock; thiếu thì "
                             "không định giá, phần còn lại vẫn chạy")
    parser.add_argument("--yield-curve", type=Path,
                        default=ROOT / "data" / "bond_yield" / "yield_curve.csv",
                        help="đường cong lợi suất TPCP (HNX spot_continuous); thiếu thì lãi "
                             "suất phi rủi ro lùi về hằng số cấu hình và được ghi rõ")
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
            print(f"LỖI: không gọi được API bảng giá: {exc}", file=sys.stderr)
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
    # Điều khoản hợp đồng (tuỳ chọn): có thì mở khoá Black–Scholes/IV, không có thì pipeline
    # vẫn chạy đủ các phần khác. Không bao giờ bịa điều khoản để lấp chỗ trống.
    terms = None
    if args.terms and args.terms.exists():
        try:
            terms = pd.read_csv(args.terms, dtype={"session": str, "ticker": str})
        except (OSError, pd.errors.ParserError) as exc:
            print(f"CẢNH BÁO: không đọc được điều khoản {args.terms}: {exc}", file=sys.stderr)
    underlyings = {}
    if args.underlying_store and args.underlying_store.exists():
        for path in sorted(args.underlying_store.glob("*.parquet")):
            series = hist_underlying.load_store(args.underlying_store, path.stem)
            if series is not None and not series.empty:
                underlyings[path.stem.upper()] = series
    # Lãi suất phi rủi ro: đường cong TPCP của đúng phiên nếu có. Thiếu thì `yield_curve`
    # là None và engine tự lùi về hằng số, ghi rõ nguồn cho từng dòng — không im lặng.
    curve = yield_curve.load_curve(args.yield_curve) if args.yield_curve else None
    if curve is None:
        print(f"CẢNH BÁO: không có đường cong lợi suất ở {args.yield_curve}; "
              "lãi suất phi rủi ro sẽ là hằng số cấu hình.", file=sys.stderr)
    analytics = build_analytics(frame, history=history, terms=terms,
                                underlying_history=underlyings or None,
                                yield_curve=curve,
                                asof=snapshot_session.iso)

    write_json(sessions_payload, args.sessions_out)
    write_json(analytics, args.analytics_out)

    # Chi tiết một mã: ghép 5 nguồn ở Python để trang chỉ tải 1 file khi bấm vào mã, và để
    # lý do vắng mặt là lý do engine trả về chứ không phải trang tự đoán.
    published = yuanta_detail.load_published({
        "board": args.board_analysis,
        "analytics": args.analytics_out,
    })
    # Dùng chính payload vừa ghi: `sessions_payload` được dựng TRƯỚC khi upsert nên
    # `tickers` trong đó có thể rỗng ở lần chạy đầu.
    bars, history_meta = yuanta_detail.choose_history_bars(sessions_payload)
    details = yuanta_detail.build_details(
        snapshot=payload,
        board_analysis=published.get("board"),
        analytics=published.get("analytics") or analytics,
        history_bars=bars,
        history_meta=history_meta,
    )
    write_json(details, args.details_out)
    priced = sum(1 for row in details["rows"] if row.get("valuation"))
    print(f"Chi tiết: {details['count']} mã, {priced} mã có khối định giá "
          f"→ {args.details_out}")
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

    valuation = analytics.get("valuation") or {}
    if valuation.get("available"):
        summary = valuation.get("summary") or {}
        print(f"Định giá: {valuation['priced']} mã có BS/IV (IV trung vị "
              f"{summary.get('medianIv')}% · {summary.get('moneyness')})")
        excluded = valuation.get("excluded") or {}
        if excluded:
            print("  Loại khỏi định giá: " + ", ".join(f"{k}: {v}" for k, v in excluded.items()))
        curve_info = valuation.get("yieldCurve") or {}
        if curve_info.get("available"):
            print(f"  Lãi suất phi rủi ro: nội suy đường cong TPCP HNX {curve_info['session']} "
                  f"(1Y neo {curve_info.get('anchored1YPct')}%) theo kỳ hạn từng mã")
        else:
            print(f"  Lãi suất phi rủi ro {valuation.get('riskFree')} — hằng số cấu hình "
                  "(không có đường cong cho phiên này)")
        ivhv = valuation.get("ivVsHv") or {}
        if ivhv.get("available"):
            print(f"  IV − HV: trung vị {ivhv['medianIvMinusHv']:+.2f} điểm "
                  f"(p25–p75 {ivhv['p25']:+.2f} → {ivhv['p75']:+.2f}) trên "
                  f"{ivhv['count']} mã có lịch sử cổ phiếu cơ sở")
        else:
            print(f"  IV − HV: chưa có ({ivhv.get('reason')})")
    else:
        print(f"Định giá: KHÔNG chạy — {valuation.get('reason')}")
        print(f"  Để bật: python scripts/import_vietstock_terms.py --source <repo Vietstock>")

    print(f"Chuỗi: {args.sessions_out} · Phân tích: {args.analytics_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
