"""Exercise plugin watcher ownership across a real threaded preload fork."""

import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    Path(__file__).parent / "preload_scripts" / "plugin_hot_reload_under_threads.py"
)


def test_plugin_watcher_starts_only_in_the_forked_threaded_worker() -> None:
    """Keep the fork and file-watcher threads outside the pytest interpreter."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "worker plugin watcher ok" in result.stdout
