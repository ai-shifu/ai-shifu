"""Run the bridge's gevent checks in a subprocess.

`monkey.patch_all()` rewrites the standard library process-wide, so it cannot run in the test
session itself. The script this launches makes the same assertions the plain-thread tests make,
under the conditions that actually break them: a request greenlet cannot run an event loop, and a
real thread cannot be joined from one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("gevent", reason="the gevent worker path needs gevent installed")

SCRIPT = Path(__file__).parent / "gevent_scripts" / "bridge_under_gevent.py"
API_ROOT = Path(__file__).resolve().parents[4]


def test_the_bridge_works_under_gevent() -> None:
    """Run the gevent checks in their own interpreter and surface whatever they print on failure."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "gevent branch ok" in result.stdout
