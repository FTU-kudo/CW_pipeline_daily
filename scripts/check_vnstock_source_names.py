#!/usr/bin/env python3
"""Check whether Vnstock G6 recognizes legacy source names (no market-data calls).

Run this with the Python interpreter in the Vnstock G6 environment. The check only
selects source names and asks the documented local CLI for its source tool list; it
does not request quotes, authenticate to a broker, or read/print API keys.

Recognition is not proof that an endpoint works, that an account is entitled, or
that data may be redistributed. See the printed caveat and verify the warrant OHLCV
route separately before using any provider.
"""
from __future__ import annotations

import importlib.metadata
import shutil
import subprocess
import sys

LEGACY_NAMES = ("vci", "kbs")


def check_name(source: str) -> None:
    print(f"\n=== source name: {source} ===")
    try:
        import vnstock

        version = importlib.metadata.version("vnstock")
        print(f"vnstock version: {version}")
        # Use a child process so a rejected/accepted candidate cannot change the
        # configured source for another candidate in this diagnostic process.
        code = (
            "import vnstock; "
            f"vnstock.sources.use({source!r}); "
            "print('SOURCE_SELECTOR_ACCEPTED')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], text=True, capture_output=True, timeout=20
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0 and "SOURCE_SELECTOR_ACCEPTED" in result.stdout:
            print("Source selector: ACCEPTED (name is recognized/configurable)")
        else:
            print("Source selector: REJECTED or errored")
        if output:
            print(output)
    except importlib.metadata.PackageNotFoundError:
        print("vnstock package metadata not found in this Python environment.")
        return
    except ImportError as exc:
        print(f"Could not import vnstock: {exc}")
        return
    except subprocess.TimeoutExpired:
        print("Source selector check timed out.")
        return

    cli = shutil.which("vnstock")
    if cli is None:
        print("CLI tool catalog: unavailable (vnstock executable not on PATH)")
        return
    # This documented command prints tool/route information; it does not fetch data.
    try:
        catalog = subprocess.run(
            [cli, "tools", "--source", source],
            text=True,
            capture_output=True,
            timeout=30,
        )
        print(f"CLI tool catalog: exit={catalog.returncode}")
        text = (catalog.stdout + catalog.stderr).strip()
        if text:
            print(text)
    except subprocess.TimeoutExpired:
        print("CLI tool catalog timed out.")


def main() -> int:
    try:
        import vnstock  # noqa: F401
    except ImportError:
        print(
            "vnstock is not installed in this Python environment. Activate the "
            "project's Vnstock G6 environment, then run this script again.\n"
            "Install from Vnstock's package feed (not PyPI-only):\n"
            "  python -m pip install --extra-index-url "
            "https://vnstocks.com/api/packages 'vnstock>=6,<7' 'vnstock-oapi>=0.1,<1'"
        )
        return 2

    for name in LEGACY_NAMES:
        check_name(name)

    print(
        "\nInterpretation: a rejected name means this installed package cannot select "
        "that legacy adapter. An accepted name only proves selector recognition; "
        "check the catalog for warrant OHLCV support. This diagnostic does not test "
        "credentials, make a provider request, or grant rights to publish data. "
        "It cannot establish that KBS/VCI have permanently stopped offering data "
        "through their own products or separately licensed APIs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
