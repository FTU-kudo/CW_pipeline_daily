#!/usr/bin/env python3
"""Fetch one Yuanta EW board snapshot and atomically write it for GitHub Pages."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.yuanta_client import API_URL, YuantaHTTPError, fetch_board  # noqa: E402
from scripts.yuanta_snapshot import YuantaPayloadError, normalize_payload  # noqa: E402


def fetch_payload(*, retries: int = 3, transport: str = "auto",
                  warmup: bool = True) -> dict:
    """Gọi endpoint EW qua lớp client dùng chung (header trình duyệt + jsKey + retry)."""
    return fetch_board(retries=retries, transport=transport, warmup=warmup)


def write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
        Path(temp_name).replace(path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "docs" / "data" / "yuanta_snapshot.json",
        help="snapshot JSON output path (default: docs/data/yuanta_snapshot.json)",
    )
    parser.add_argument(
        "--transport", choices=("auto", "curl_cffi", "requests"), default="auto",
        help="auto: dùng curl_cffi (TLS giống Chrome) nếu đã cài, không thì requests",
    )
    parser.add_argument(
        "--no-warmup", action="store_true",
        help="bỏ bước ghé trang chủ lấy cookie CDN trước khi gọi API",
    )
    args = parser.parse_args()
    try:
        payload = fetch_payload(transport=args.transport, warmup=not args.no_warmup)
        snapshot = normalize_payload(payload)
    except YuantaHTTPError as exc:
        # In ngữ cảnh đầy đủ: status, content-type, body (không cắt mất chỗ quan trọng).
        print(f"LỖI: không lấy được bảng giá: {exc}", file=sys.stderr)
        if exc.body:
            print(f"--- body ({len(exc.body)} ký tự) ---", file=sys.stderr)
            print(exc.body, file=sys.stderr)
        print(
            "Gợi ý: HTTP 200 + text/html kèm <title>Attention Required!</title> là JS "
            "interstitial của WAF (cần jsKey); HTTP 403 là chặn header; 404 là endpoint đổi.",
            file=sys.stderr,
        )
        return 1
    except YuantaPayloadError as exc:
        print(f"LỖI: payload bảng giá không đúng schema mong đợi: {exc}", file=sys.stderr)
        return 1
    write_atomic(args.out, snapshot)
    print(f"Bảng giá CW: {snapshot['count']} symbols; fetchedAt={snapshot['fetchedAt']}; output={args.out}")
    print(f"Endpoint: {API_URL}")
    print("Historical warrant OHLCV is unavailable; this output contains the current board only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
