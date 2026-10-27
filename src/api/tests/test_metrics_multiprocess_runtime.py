"""Exercise real Prometheus import ordering and fork storage in fresh processes."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]


def run_fresh(script: str, **overrides: str) -> None:
    env = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "LANG", "TMPDIR")
        if key in os.environ
    }
    env.update(SKIP_LOAD_DOTENV="1", PYTHON_DOTENV_DISABLED="1")
    env.pop("PROMETHEUS_MULTIPROC_DIR", None)
    env.pop("AI_SHIFU_METRICS_MANAGED_DIR", None)
    env.update(overrides)
    env["PYTHONPATH"] = str(API_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    if result.returncode:
        pytest.fail(result.stdout + result.stderr, pytrace=False)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="Gunicorn uses Unix forks")
def test_preload_workers_aggregate_and_dead_worker_gauges_are_reaped() -> None:
    run_fresh("""
import os, runpy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
config = runpy.run_path("gunicorn.conf.py")
from flask import Flask
from flaskr.common import observability
from flaskr.common.capacity_metrics import SSE_ACTIVE
from prometheus_client import values
from prometheus_client.parser import text_string_to_metric_families
assert values.ValueClass._multiprocess
app = Flask("isolated-metrics")
observability.init_observability(app)
# Construct labeled values before fork, as preload-time code may do.
counter = observability.HTTP_REQUEST_COUNT.labels("GET", "/items", "200")
histogram = observability.HTTP_REQUEST_DURATION.labels("GET", "/items", "200")
active = SSE_ACTIVE.labels("GET", "/items")
children = []
for count in (2, 3):
    pid = os.fork()
    if pid == 0:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: counter.inc(), range(count)))
        histogram.observe(count)
        active.inc(count)
        os._exit(0)
    children.append(pid)
for pid in children:
    _, status = os.waitpid(pid, 0)
    assert status == 0

def scrape():
    response = app.test_client().get("/internal/metrics")
    assert response.status_code == 200
    return [s for f in text_string_to_metric_families(response.data.decode()) for s in f.samples]
def value(name):
    return next((s.value for s in scrape() if s.name == name and s.labels.get("path") == "/items"), 0)
assert value("ai_shifu_http_requests_total") == 5
assert value("ai_shifu_http_request_duration_seconds_count") == 2
assert value("ai_shifu_http_request_duration_seconds_sum") == 5
assert value("ai_shifu_sse_active") == 5
server = SimpleNamespace(log=Mock())
config["child_exit"](server, SimpleNamespace(pid=children[0]))
assert value("ai_shifu_sse_active") == 3
config["child_exit"](server, SimpleNamespace(pid=children[1]))
assert value("ai_shifu_sse_active") == 0
assert value("ai_shifu_http_requests_total") == 5
path = Path(os.environ["PROMETHEUS_MULTIPROC_DIR"])
assert path.stat().st_mode & 0o777 == 0o700
config["on_exit"](server)
assert not path.exists()
server.log.exception.assert_not_called()
""")


def test_late_import_is_rejected_without_changing_storage() -> None:
    run_fresh("""
import os
import prometheus_client
from flaskr.metrics_runtime import prepare_metrics_directory
try:
    prepare_metrics_directory()
except RuntimeError as error:
    assert "before importing" in str(error)
else:
    raise AssertionError("late import must fail")
assert "PROMETHEUS_MULTIPROC_DIR" not in os.environ
""")


def test_explicit_stale_directory_is_preserved_and_rejected(tmp_path: Path) -> None:
    (tmp_path / "counter_123.db").write_text("operator data")
    run_fresh(
        """
from flaskr.metrics_runtime import prepare_metrics_directory
try:
    prepare_metrics_directory()
except RuntimeError as error:
    assert "fresh dedicated" in str(error)
else:
    raise AssertionError("stale counters must not be silently reused")
""",
        PROMETHEUS_MULTIPROC_DIR=str(tmp_path),
    )
    assert (tmp_path / "counter_123.db").read_text() == "operator data"


def test_explicit_directory_is_not_deleted_by_master_exit(tmp_path: Path) -> None:
    run_fresh(
        """
from pathlib import Path
from flaskr.metrics_runtime import prepare_metrics_directory, cleanup_metrics_directory
path = Path(prepare_metrics_directory())
from prometheus_client import Counter
Counter("test_requests", "test").inc()
cleanup_metrics_directory()
assert path.is_dir()
assert list(path.glob("*.db"))
""",
        PROMETHEUS_MULTIPROC_DIR=str(tmp_path),
    )


def test_usr2_master_uses_fresh_directory_and_preserves_parent() -> None:
    run_fresh('''
import os, subprocess, sys
from pathlib import Path
from flaskr.metrics_runtime import prepare_metrics_directory, cleanup_metrics_directory
parent = Path(prepare_metrics_directory())
from prometheus_client import Counter
Counter("parent_requests", "test").inc(7)
child = subprocess.run([sys.executable, "-c", """
from pathlib import Path
from flaskr.metrics_runtime import prepare_metrics_directory, cleanup_metrics_directory
import os
old = os.environ['PROMETHEUS_MULTIPROC_DIR']
new = Path(prepare_metrics_directory())
assert str(new) != old
assert not list(new.glob('*.db'))
cleanup_metrics_directory()
assert Path(old).exists()
"""], check=True, timeout=15)
assert list(parent.glob("*.db"))
cleanup_metrics_directory()
assert not parent.exists()
''')


def test_generated_example_keeps_single_process_metrics_unset() -> None:
    run_fresh("""
from dotenv import dotenv_values
from flaskr.common.config import EnhancedConfig, ENV_VARS
from io import StringIO
example = EnhancedConfig(ENV_VARS).export_env_example_filtered()
assert '# PROMETHEUS_MULTIPROC_DIR=""' in example
assert "PROMETHEUS_MULTIPROC_DIR" not in dotenv_values(stream=StringIO(example))
""")
