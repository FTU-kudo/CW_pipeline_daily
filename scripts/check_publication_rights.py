#!/usr/bin/env python3
"""Validate the private written-authorization record before a public data build.

This is a fail-closed checklist, not legal advice and not proof that an approval is
valid. A human must compare the record with the provider's and exchange's current
signed terms. The record should stay outside Git unless approved for publication.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cwintel.rights import PublicationNotAuthorized, validate_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="expected Vnstock source name")
    parser.add_argument("--manifest", type=Path, help="private authorization JSON path")
    args = parser.parse_args()
    try:
        record = validate_manifest(args.manifest, source=args.source)
    except PublicationNotAuthorized as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(
        "Authorization record passes required-field and expiry checks "
        f"(source={record['source']}, valid_until={record['valid_until']})."
    )
    print("Human review against current signed provider/exchange terms is still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
