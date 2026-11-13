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


def _response_preview(response: requests.Response) -> str:
    """Short, single-line body excerpt for diagnosing HTML/empty API responses."""
    try:
        text = response.text
    except Exception:
        text = ""
    text = " ".join("".join(ch for ch in text if ch.isprintable() or ch.isspace()).split())
    if not text:
        return "<empty body>"
    return repr(text[:240])


def fetch_payload(session: requests.Session | None = None, *, retries: int = 3) -> dict:
    session = session or requests.Session()
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(
                API_URL,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "CW-Intelligence/1.0 (+https://github.com/FTU-kudo/CW_pipeline_daily)",
                },
                timeout=(5, 25),
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
                continue
            break

        # Retry only transient server/rate-limit responses. A 200 HTML/empty body
        # is a contract/configuration error, so report it immediately with context.
        if response.status_code == 429 or response.status_code >= 500:
            last_error = RuntimeError(
                f"HTTP {response.status_code}; content-type={response.headers.get('Content-Type', '<missing>')}; "
                f"body={_response_preview(response)}"
            )
            if attempt + 1 < retries:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(max(int(retry_after), 1), 30) if retry_after else 2 ** attempt
                except ValueError:
                    delay = 2 ** attempt
                time.sleep(delay)
                continue
            break

        if not response.ok:
            raise RuntimeError(
                f"Yuanta returned HTTP {response.status_code}; "
                f"content-type={response.headers.get('Content-Type', '<missing>')}; "
                f"body={_response_preview(response)}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Yuanta returned a non-JSON/empty response; HTTP {response.status_code}; "
                f"content-type={response.headers.get('Content-Type', '<missing>')}; "
                f"final-url={response.url}; body={_response_preview(response)}"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Yuanta JSON top level must be an object, got {type(payload).__name__}; "
                f"HTTP {response.status_code}; content-type={response.headers.get('Content-Type', '<missing>')}"
            )
        return payload

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
