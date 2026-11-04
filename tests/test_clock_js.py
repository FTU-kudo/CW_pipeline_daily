"""Chạy bộ kiểm thử JS của đồng hồ (tests/js/clock.test.mjs) trong pytest.

Bộ đó kiểm tra giờ Việt Nam độc lập timezone, các mốc phiên, ngày lễ, tương phản
WCAG của nhãn phiên. Không có node (ví dụ máy CI tối giản) thì bỏ qua.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests" / "js" / "clock.test.mjs"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="không có node trong môi trường chạy test")
def test_clock_js_suite_passes() -> None:
    proc = subprocess.run(  # noqa: S603 - đường dẫn cố định trong repo
        [NODE, str(SCRIPT)],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, f"clock.test.mjs lỗi:\n{proc.stdout}\n{proc.stderr}"
    assert "kiểm tra OK" in proc.stdout
