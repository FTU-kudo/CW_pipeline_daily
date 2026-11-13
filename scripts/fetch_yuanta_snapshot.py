#!/usr/bin/env python3
"""Fetch one Yuanta EW board snapshot and atomically write it for GitHub Pages."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.yuanta_snapshot import API_URL, normalize_payload  # noqa: E402


def fetch_payload(session: requests.Session | None = None, *, retries: int = 3) -> dict:
    session = session or requests.Session()
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(
                API_URL,
                headers={"Accept": "application/json", "User-Agent": "CW-Intelligence/1.0"},
                timeout=(5, 25),
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Yuanta request failed after {retries} attempts: {last_error}")


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
    args = parser.parse_args()
    payload = fetch_payload()
    snapshot = normalize_payload(payload)
    write_atomic(args.out, snapshot)
    print(f"Yuanta EW snapshot: {snapshot['count']} symbols; fetchedAt={snapshot['fetchedAt']}; output={args.out}")
    print("Historical warrant OHLCV is unavailable; this output contains the current board only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
