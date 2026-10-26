"""Prepare Prometheus storage before Gunicorn preloads application imports.

Keep this module stdlib-only: importing prometheus_client before setting its
multiprocess directory permanently selects the wrong writer implementation.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class _Runtime:
    owned_directory: Path | None = None
    owner_pid: int | None = None
    directory: Path | None = None


_runtime = _Runtime()
_MANAGED_ENV = "AI_SHIFU_METRICS_MANAGED_DIR"


def prepare_metrics_directory() -> str:
    """Create one writer directory per master, or validate an explicit one."""
    if _runtime.owner_pid == os.getpid() and _runtime.directory is not None:
        return str(_runtime.directory)
    if "prometheus_client" in sys.modules:
        message = "Prepare multiprocess metrics before importing prometheus_client"
        raise RuntimeError(message)

    configured = os.environ.get("PROMETHEUS_MULTIPROC_DIR", "").strip()
    inherited_managed = os.environ.get(_MANAGED_ENV, "")
    if configured and configured != inherited_managed:
        directory = Path(configured).resolve()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not directory.is_dir() or any(directory.glob("*.db")):
            message = "PROMETHEUS_MULTIPROC_DIR must be a fresh dedicated directory"
            raise RuntimeError(message)
        # Validate actual writability, including read-only mounts.
        with tempfile.TemporaryFile(dir=directory):
            pass
        _runtime.owned_directory = None
        os.environ.pop(_MANAGED_ENV, None)
    else:
        directory = Path(tempfile.mkdtemp(prefix="ai-shifu-metrics-"))
        _runtime.owned_directory = directory
        os.environ[_MANAGED_ENV] = str(directory)
    _runtime.owner_pid = os.getpid()
    _runtime.directory = directory
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(directory)
    return str(directory)


def mark_worker_exit(pid: int) -> None:
    """Remove live gauges, retaining counters and histograms for this master."""
    from prometheus_client import multiprocess

    if _runtime.directory is not None:
        multiprocess.mark_process_dead(pid, path=str(_runtime.directory))


def cleanup_metrics_directory() -> None:
    """Delete only the exiting master's automatically allocated directory."""
    if _runtime.owner_pid == os.getpid() and _runtime.owned_directory is not None:
        shutil.rmtree(_runtime.owned_directory)
        _runtime.owned_directory = None
