"""One place for Vnstock generation-6 source and compatibility configuration.

Set VNSTOCK_SOURCE after choosing and authorizing a provider. Source API keys are
managed outside this file by vnstock-oapi / OS keyring or the provider's env vars.
"""
from __future__ import annotations
import os

# Deliberately unset: choose a source whose API supports the required OHLCV routes.
VNSTOCK_SOURCE = os.getenv("VNSTOCK_SOURCE", "").strip()


def configure_vnstock():
    if not VNSTOCK_SOURCE:
        raise RuntimeError(
            "VNSTOCK_SOURCE is not configured. Choose a source and set it in the "
            "environment before fetching data; no provider is selected by default."
        )
    import vnstock
    vnstock.compat.use("v5")
    vnstock.sources.use(VNSTOCK_SOURCE)
    return vnstock
