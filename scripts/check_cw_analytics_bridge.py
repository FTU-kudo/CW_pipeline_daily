#!/usr/bin/env python3
"""Kiểm tra board Yuanta đã sẵn sàng nối vào dashboard CW Analytics cũ (legacy) chưa.

Vì sao cần script này
---------------------
Dashboard cũ (``docs/legacy.html`` + ``docs/assets/*``) đọc ``docs/data/meta.json``,
``market.json``, ``screener.json``, ``recommendations.json``… do ``cwintel.build`` sinh ra.
``cwintel.build`` KHÔNG chỉ cần giá: nó cần **điều khoản hợp đồng** (strike, tỷ lệ chuyển
đổi, ngày đáo hạn), **giá cổ phiếu cơ sở**, **lợi suất phi rủi ro** và **chuỗi quá khứ** để
tính IV/Greeks/điểm/khuyến nghị. Endpoint Yuanta ``stock_type=EW`` không trả bất kỳ trường
nào trong số đó.

Script này **không** tự bịa dữ liệu để lấp. Nó đọc dữ liệu thật trong repo, đối chiếu với
yêu cầu của ``cwintel`` và in ra: cái gì đã nối được (OHLCV), cái gì còn thiếu (kèm lý do),
và điều kiện để dashboard cũ chạy được.

    python scripts/check_cw_analytics_bridge.py
    python scripts/check_cw_analytics_bridge.py --json report.json

Mã thoát: 0 = đủ điều kiện build dashboard cũ, 2 = còn thiếu (mặc định hiện nay).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from cwintel import config, yuanta_history as hist  # noqa: E402

#: Những gì ``cwintel.build`` cần cho từng nhóm phân tích của dashboard cũ.
REQUIREMENTS = (
    {
        "key": "ohlcv",
        "label": "OHLCV theo ngày của từng CW",
        "available": "có (tích luỹ từ snapshot)",
        "detail": (
            "Mỗi phiên workflow chạy sau 15:10 ICT sẽ thêm một bar. Không backfill được quá "
            "khứ; mã không khớp lệnh không có bar giá."
        ),
        "unlocks": "giá, % thay đổi, RSI/MACD/MA, thanh khoản, bảng xếp hạng",
    },
    {
        "key": "terms",
        "label": "Điều khoản hợp đồng: strike, tỷ lệ chuyển đổi, ngày đáo hạn",
        "available": "KHÔNG có trong endpoint",
        "detail": (
            "Payload EW chỉ có trường bảng giá. Không có K, ratio, maturity nên không tính "
            "được intrinsic, premium, moneyness, delta/gamma/theta/vega, IV, điểm, khuyến nghị."
        ),
        "unlocks": "intrinsic, premium, moneyness, Greeks, IV, CW Score, khuyến nghị",
    },
    {
        "key": "underlying",
        "label": "Giá cổ phiếu cơ sở (chuỗi ngày)",
        "available": "chỉ có RefP của CW, không có giá cổ phiếu cơ sở",
        "detail": (
            "Cần chuỗi giá cổ phiếu cơ sở để tính HV/IV, moneyness và tương quan. Hiện chỉ suy "
            "ra được mã cơ sở từ tên CW."
        ),
        "unlocks": "HV, IV, moneyness, so sánh CW cùng cơ sở",
    },
    {
        "key": "riskfree",
        "label": "Lợi suất phi rủi ro",
        "available": "dùng giá trị cấu hình, không phải chuỗi thị trường",
        "detail": (
            "cwintel cần chuỗi lợi suất (tenor + ngày quan sát) để định giá. Giá trị cố định "
            "trong config chỉ là tham số phần mềm, không phải số liệu thị trường."
        ),
        "unlocks": "định giá Black–Scholes, Greeks",
    },
    {
        "key": "rights",
        "label": "Quyền công bố dữ liệu dẫn xuất",
        "available": "xem docs/DATA_RIGHTS.md",
        "detail": (
            "cwintel.rights chặn ghi artifact dẫn xuất vào docs/ nếu thiếu bản ghi uỷ quyền "
            "còn hiệu lực. Đây là cổng fail-closed, không phải bước có thể bỏ qua."
        ),
        "unlocks": "phát hành dashboard lên Page công khai",
    },
)


def _history_state(store: Path) -> dict:
    frame = hist.load_history(store)
    if frame.empty:
        return {"sessions": 0, "tickers": 0, "rows": 0}
    coverage = hist.coverage(frame)
    return {
        "sessions": coverage["sessions"],
        "tickers": coverage["tickers"],
        "rows": coverage["rows"],
        "first": coverage["first"],
        "last": coverage["last"],
        "tradedSharePct": coverage["tradedSharePct"],
        "missingSessions": coverage["missingSessions"],
        "bridgeRows": int(len(hist.to_cwintel_ohlcv(frame))),
    }


def build_report(*, store: Path = hist.STORE_DIR) -> dict:
    state = _history_state(store)
    master_ready = (config.VIETSTOCK_CACHE.exists() and config.OHLCV_CACHE.exists()
                    and config.UNDERLYING_CACHE.exists())
    blockers = [req["key"] for req in REQUIREMENTS if req["key"] != "ohlcv"]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "legacyDashboard": {
            "entries": ["docs/legacy.html", "docs/assets/app.js"],
            "expectedArtifacts": [
                "docs/data/meta.json", "docs/data/market.json",
                "docs/data/screener.json", "docs/data/recommendations.json",
                "docs/data/underlyings.json", "docs/data/quality.json",
                "docs/data/methodology.json", "docs/data/liquidity.json",
            ],
            "builder": "cwintel.build.build_all",
        },
        "history": state,
        "cwintelCachesPresent": {
            "vietstock": config.VIETSTOCK_CACHE.exists(),
            "ohlcv": config.OHLCV_CACHE.exists(),
            "underlying": config.UNDERLYING_CACHE.exists(),
            "allPresent": master_ready,
        },
        "requirements": list(REQUIREMENTS),
        "blockers": blockers,
        "bridged": {
            "ohlcv": {
                "status": "ready" if state["sessions"] else "empty",
                "path": str(store.relative_to(ROOT)) if store.is_relative_to(ROOT) else str(store),
                "note": (
                    "Đã có hàm chuyển đổi cwintel.yuanta_history.to_cwintel_ohlcv(); "
                    "ghi cache bằng write_cwintel_cache()."
                ),
            }
        },
        "verdict": {
            "canBuildLegacyDashboard": bool(master_ready and state["sessions"]),
            "summary": (
                "OHLCV đã nối được vào đúng schema cwintel. Dashboard cũ CHƯA build được vì "
                "thiếu điều khoản hợp đồng (strike/ratio/maturity), giá cổ phiếu cơ sở và "
                "chuỗi lợi suất — endpoint Yuanta không có các trường này, và không được bịa."
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", type=Path, default=hist.STORE_DIR)
    parser.add_argument("--json", type=Path, default=None, help="ghi báo cáo ra JSON")
    args = parser.parse_args(argv)

    report = build_report(store=args.store)
    state = report["history"]

    print("== OHLCV (đã nối) ==")
    if state["sessions"]:
        print(f"  {state['sessions']} phiên ({state['first']} → {state['last']}), "
              f"{state['tickers']} mã, {state['rows']} dòng, "
              f"{state['bridgeRows']} bar chuyển được sang schema cwintel")
        if state["missingSessions"]:
            print(f"  Thiếu {len(state['missingSessions'])} phiên (không nội suy): "
                  f"{state['missingSessions'][:8]}")
    else:
        print("  Chưa có dữ liệu: chạy scripts/backfill_yuanta_history.py trước.")

    print("\n== Còn thiếu để build dashboard CW Analytics cũ ==")
    for req in report["requirements"]:
        if req["key"] == "ohlcv":
            continue
        print(f"  - {req['label']}: {req['available']}")
        print(f"      {req['detail']}")

    verdict = report["verdict"]
    print(f"\nKết luận: build được dashboard cũ? {'CÓ' if verdict['canBuildLegacyDashboard'] else 'CHƯA'}")
    print(f"  {verdict['summary']}")
    print("\nĐiều kiện để nối hoàn chỉnh: cung cấp điều khoản hợp đồng + giá cổ phiếu cơ sở "
          "+ chuỗi lợi suất (hoặc bản cache parquet đã có), rồi xác nhận quyền công bố.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        print(f"\nBáo cáo: {args.json}")
    return 0 if verdict["canBuildLegacyDashboard"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
