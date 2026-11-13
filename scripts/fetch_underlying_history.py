#!/usr/bin/env python3
"""Tải lịch sử OHLCV + giao dịch nước ngoài của mọi cổ phiếu cơ sở (2010 → hôm nay).

Nguồn: ``ysradarapi.yuanta.com.vn/api/v3/market_data/market_watch/price_history/{MÃ}``.

Mỗi mã CW có một cổ phiếu cơ sở; bảng giá Yuanta cho biết đó là mã nào (suy ra từ quy ước
tên CW). Script này gom danh sách cơ sở từ snapshot, tải lịch sử từng mã, và ghi vào
``data/underlying_history/{MÃ}.parquet``.

Vì sao cần
----------
Giá cổ phiếu cơ sở ``S`` trước đây chỉ suy ra được từ premium/đòn bẩy của Vietstock. Endpoint
này cho ``S`` trực tiếp **và cả chuỗi lịch sử**, nên lần đầu tiên tính được biến động thực
hiện (HV) để so với IV — chênh lệch IV−HV trước đó chỉ là câu nói, giờ là số đo.

Cách dùng
---------
    # Tải toàn bộ cơ sở có trong snapshot (mặc định giới hạn 60 mã/lần để tránh gọi quá nhiều)
    python scripts/fetch_underlying_history.py

    # Chỉ một mã, để thử
    python scripts/fetch_underlying_history.py --symbol ACB

    # Từ dữ liệu đã lưu (không gọi mạng)
    python scripts/fetch_underlying_history.py --offline fixtures/underlying/

    # Giới hạn số mã và số ngày
    python scripts/fetch_underlying_history.py --limit 20 --from-date 2024-01-01

Ghi chú vận hành
----------------
* Mỗi mã là **một request**; mặc định có 0,4 giây nghỉ giữa các request để không đập vào WAF.
* Script **resume được**: nếu mất mạng giữa đường, chạy lại sẽ gộp dữ liệu mới vào kho cũ
  (``merge_history``), không ghi đè lịch sử đã có.
* Mã nào lỗi được liệt kê rõ ở cuối và **không** làm hỏng phần còn lại (mã thoát 0 nếu ít nhất
  một mã thành công, 1 nếu tất cả thất bại).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from cwintel import yuanta_underlying as hist  # noqa: E402
from cwintel.yuanta_board import underlying_from_code  # noqa: E402
from scripts.yuanta_client import YuantaHTTPError, build_session, fetch_board  # noqa: E402

#: Nghỉ giữa các request. WAF của Yuanta nhạy với chuỗi request dồn dập từ một IP.
SLEEP_BETWEEN = 0.4


def load_symbols_from_snapshot(path: Path) -> list[str]:
    """Danh sách cổ phiếu cơ sở suy ra từ snapshot bảng giá (đã sắp xếp, không trùng)."""
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    symbols = set()
    for row in rows:
        code = str((row or {}).get("StockCode") or "").strip().upper()
        if not code:
            continue
        underlying = underlying_from_code(code)
        if underlying:
            symbols.add(str(underlying).upper())
    return sorted(symbols)


def fetch_one(symbol: str, *, session, from_date: str, to_date: str | None,
              host: str, retries: int) -> pd.DataFrame:
    """Tải và parse lịch sử một mã. Ném ``YuantaHTTPError``/``ValueError`` khi thất bại."""
    url = hist.history_url(symbol, from_date=from_date, to_date=to_date, host=host)
    payload = fetch_board(session=session, retries=retries, url=url, transport="auto",
                          warmup=False)
    return hist.parse_history(payload, symbol)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", type=Path,
                        default=ROOT / "docs" / "data" / "yuanta_snapshot.json")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "underlying_history")
    parser.add_argument("--symbol", action="append", default=None,
                        help="chỉ tải mã này (lặp lại được: --symbol ACB --symbol VPB)")
    parser.add_argument("--from-date", default=hist.HISTORY_START)
    parser.add_argument("--to-date", default=None, help="mặc định là hôm nay")
    parser.add_argument("--limit", type=int, default=hist.DEFAULT_MAX_SYMBOLS,
                        help=f"số mã tối đa (mặc định {hist.DEFAULT_MAX_SYMBOLS}); 0 = không giới hạn")
    parser.add_argument("--host", choices=("api", "web"), default="api")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=SLEEP_BETWEEN)
    parser.add_argument("--offline", type=Path, default=None,
                        help="thư mục chứa payload JSON đã lưu; không gọi mạng")
    parser.add_argument("--json", type=Path, default=None, help="ghi báo cáo tổng hợp")
    args = parser.parse_args(argv)

    to_date = args.to_date or hist.utc_now()[:10]

    if args.offline:
        paths = sorted(Path(args.offline).glob("*.json"))
        if not paths:
            print(f"LỖI: không có file JSON nào trong {args.offline}", file=sys.stderr)
            return 1
        frames = hist.import_from_files(paths)
        print(f"Offline: đọc {len(frames)} mã từ {len(paths)} file")
        errors: dict[str, str] = {}
    else:
        symbols = [s.upper() for s in (args.symbol or [])] or load_symbols_from_snapshot(
            args.snapshot)
        if not symbols:
            print("LỖI: không lấy được danh sách cổ phiếu cơ sở. Cần snapshot bảng giá "
                  f"({args.snapshot}) hoặc truyền --symbol.", file=sys.stderr)
            return 1
        if args.limit and len(symbols) > args.limit:
            print(f"Giới hạn {args.limit}/{len(symbols)} mã (dùng --limit 0 để tải hết)")
            symbols = symbols[:args.limit]

        session = build_session("auto")
        frames = {}
        errors = {}
        print(f"Tải {len(symbols)} cổ phiếu cơ sở, {args.from_date} → {to_date}")
        for index, symbol in enumerate(symbols, start=1):
            try:
                frame = fetch_one(symbol, session=session, from_date=args.from_date,
                                  to_date=to_date, host=args.host, retries=args.retries)
                if frame.empty:
                    errors[symbol] = "nguồn trả về 0 phiên"
                    continue
                frames[symbol] = frame
                print(f"  [{index}/{len(symbols)}] {symbol}: {len(frame)} phiên "
                      f"({frame['TradingDate'].iloc[0]} → {frame['TradingDate'].iloc[-1]})")
            except (YuantaHTTPError, ValueError) as exc:
                errors[symbol] = str(exc)[:200]
                print(f"  [{index}/{len(symbols)}] {symbol}: LỖI — {str(exc)[:160]}",
                      file=sys.stderr)
            if args.sleep and index < len(symbols):
                time.sleep(args.sleep)

    if not frames:
        print("LỖI: không tải được mã nào.", file=sys.stderr)
        return 1

    # Gộp vào kho cũ thay vì ghi đè: chạy lại không mất lịch sử, không nhân đôi phiên.
    merged: dict[str, pd.DataFrame] = {}
    for symbol, fresh in frames.items():
        existing = hist.load_store(args.out, symbol)
        merged[symbol] = hist.merge_history(existing, fresh)
    hist.write_store(merged, args.out)

    # Lịch thị trường suy từ chính dữ liệu: ngày lễ 2010–2020 không có trong config, nên nếu
    # đối chiếu bằng lịch cứng thì mỗi dịp Tết sẽ bị báo "thiếu" — sai và che mất lỗ hổng thật.
    market = hist.market_calendar(merged)
    report = {
        "generatedAt": hist.utc_now(),
        "fromDate": args.from_date,
        "toDate": to_date,
        "store": str(args.out),
        "symbols": len(merged),
        "errors": errors,
        "marketSessions": len(market),
        "coverage": {s: hist.coverage(f, market=market) for s, f in sorted(merged.items())},
        "summary": {s: hist.summarize(f, market=market) for s, f in sorted(merged.items())},
    }

    total_rows = sum(len(f) for f in merged.values())
    print(f"\nKho: {len(merged)} mã, {total_rows} dòng → {args.out}")
    if errors:
        print(f"Mã lỗi ({len(errors)}): " + ", ".join(sorted(errors))[:300])
    complete = [s for s, c in report["coverage"].items()
                if c.get("available") and not c.get("missingCount")]
    print(f"Liền mạch (không thiếu phiên): {len(complete)}/{len(merged)} mã")
    print(f"Lịch thị trường suy từ dữ liệu: {len(market)} phiên "
          f"(ngày mà ≥60% số mã giao dịch)")
    holes = {s: c["missing"] for s, c in report["coverage"].items() if c.get("missingCount")}
    if holes:
        print("Lỗ hổng thật (thị trường mở nhưng mã này không giao dịch):")
        for symbol, days in sorted(holes.items()):
            print(f"  {symbol}: {len(days)} phiên — {days[:6]}"
                  f"{' …' if len(days) > 6 else ''}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        print(f"Báo cáo: {args.json}")

    # Chỉ thất bại khi KHÔNG mã nào lấy được; lỗi lẻ tẻ đã được báo rõ ở trên.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
