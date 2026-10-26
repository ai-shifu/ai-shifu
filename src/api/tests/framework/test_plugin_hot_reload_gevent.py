"""Exercise plugin watcher ownership across a real gevent preload fork."""

import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).parent / "gevent_scripts" / "plugin_hot_reload_under_gevent.py"


def test_plugin_watcher_starts_only_in_the_forked_gevent_worker() -> None:
    """Keep process-wide monkey patches outside the pytest interpreter."""
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
