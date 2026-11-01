"""Exercise plugin watcher ownership across a real preload fork."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[2]
PROBE_MODULE = "tests.framework.preload_scripts.plugin_hot_reload_under_threads"


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is required")
def test_plugin_watcher_starts_only_in_the_forked_worker() -> None:
    """Keep native watcher threads and the fork outside the pytest interpreter."""
    result = subprocess.run(
        [sys.executable, "-m", PROBE_MODULE],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "worker plugin watcher ok" in result.stdout
