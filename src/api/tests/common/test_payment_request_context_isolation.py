"""Run the unchanged trace tests after real request-formatting state pollution."""

import os
import subprocess
import sys
from pathlib import Path


def test_trace_contract_survives_request_context_from_prior_tests(
    tmp_path: Path,
) -> None:
    plugin = tmp_path / "prior_request_context.py"
    plugin.write_text("""import logging
import pytest
from flaskr.common.log import RequestFormatter
from flaskr.common.request_context import thread_local

@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    vars(thread_local).clear()
    record = logging.LogRecord("prior-payment-test", logging.INFO, __file__, 0, "prior request", (), None)
    RequestFormatter("%(request_id)s").format(record)
    assert thread_local.request_id
""")
    env = {
        **os.environ,
        "PYTHONPATH": str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:testmon",
            "-p",
            "prior_request_context",
            "-o",
            "addopts=",
            "tests/test_langfuse.py",
            "-q",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
