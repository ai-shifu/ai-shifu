"""Regression tests for Runtime Harness timeline reporting."""

# ruff: noqa: S101 -- pytest assertions are the expected test contract.

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from scripts.harness import runtime_timeline


class _HealthyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence HTTP server diagnostics during tests."""


def test_append_event_writes_schema_and_details() -> None:
    """Events are persisted with the expected schema and metadata."""
    with TemporaryDirectory() as directory:
        timeline_path = Path(directory) / "timeline.json"
        runtime_timeline.append_event(
            timeline_path,
            name="images",
            status="started",
            details={"target": "api"},
        )

        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))

    assert timeline["schema_version"] == runtime_timeline.SCHEMA_VERSION
    assert timeline["events"][0] == {
        "details": {"target": "api"},
        "name": "images",
        "status": "started",
        "timestamp": timeline["events"][0]["timestamp"],
    }
    assert timeline["events"][0]["timestamp"].endswith("Z")


def test_wait_for_healthy_endpoint_records_ready_event() -> None:
    """A healthy endpoint records attempts, elapsed time, and HTTP status."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with TemporaryDirectory() as directory:
            timeline_path = Path(directory) / "timeline.json"
            is_ready = runtime_timeline.wait_for_endpoint(
                timeline_path,
                name="api",
                url=f"http://127.0.0.1:{server.server_port}/health",
                timeout_seconds=1,
                interval_seconds=0.01,
            )
            timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()

    assert is_ready
    assert timeline["events"][0]["status"] == "ready"
    assert timeline["events"][0]["details"]["status_code"] == 200


def test_request_endpoint_handles_connection_reset() -> None:
    """Transient connection resets become retryable endpoint diagnostics."""
    with patch(
        "scripts.harness.runtime_timeline.urlopen",
        side_effect=ConnectionResetError("connection reset"),
    ):
        status_code, detail = runtime_timeline.request_endpoint(
            "http://127.0.0.1:5800/health", timeout_seconds=1
        )

    assert status_code == 0
    assert "connection reset" in detail


def test_wait_caps_request_timeout_to_the_remaining_budget() -> None:
    """A short overall timeout is forwarded to the endpoint request unchanged."""
    with TemporaryDirectory() as directory:
        timeline_path = Path(directory) / "timeline.json"
        with patch(
            "scripts.harness.runtime_timeline.urlopen", side_effect=TimeoutError
        ) as urlopen:
            is_ready = runtime_timeline.wait_for_endpoint(
                timeline_path,
                name="api",
                url="http://127.0.0.1:5800/health",
                timeout_seconds=0.02,
                interval_seconds=0.01,
            )

    assert not is_ready
    assert urlopen.call_args.kwargs["timeout"] <= 0.02


@pytest.mark.parametrize("interval_seconds", [0, -1])
def test_wait_rejects_non_positive_intervals(interval_seconds: float) -> None:
    """The API boundary rejects values that would busy-loop or break sleep."""
    with (
        TemporaryDirectory() as directory,
        pytest.raises(ValueError, match="interval_seconds"),
    ):
        runtime_timeline.wait_for_endpoint(
            Path(directory) / "timeline.json",
            name="api",
            url="http://127.0.0.1:5800/health",
            timeout_seconds=1,
            interval_seconds=interval_seconds,
        )


@pytest.mark.parametrize("interval_seconds", ["0", "-1"])
def test_cli_rejects_non_positive_intervals(interval_seconds: str) -> None:
    """The CLI boundary rejects invalid polling intervals before execution."""
    parser = runtime_timeline.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "wait",
                "--output",
                "timeline.json",
                "--name",
                "api",
                "--url",
                "http://127.0.0.1:5800/health",
                "--interval-seconds",
                interval_seconds,
            ]
        )


def test_wait_for_unavailable_endpoint_records_timeout() -> None:
    """An unavailable endpoint records the timeout evidence before failing."""
    with TemporaryDirectory() as directory:
        timeline_path = Path(directory) / "timeline.json"
        is_ready = runtime_timeline.wait_for_endpoint(
            timeline_path,
            name="api",
            url="http://127.0.0.1:1/health",
            timeout_seconds=0.02,
            interval_seconds=0.01,
        )
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))

    assert not is_ready
    assert timeline["events"][0]["status"] == "timeout"
    assert timeline["events"][0]["name"] == "api"
    assert timeline["events"][0]["details"]["attempts"] >= 1


def test_write_summary_renders_events() -> None:
    """Summary output includes a readable table for the GitHub job page."""
    with TemporaryDirectory() as directory:
        timeline_path = Path(directory) / "timeline.json"
        summary_path = Path(directory) / "summary.md"
        runtime_timeline.append_event(
            timeline_path,
            name="smoke",
            status="finished",
            details={"exit_code": 0},
        )
        runtime_timeline.write_summary(timeline_path, summary_path)
        summary = summary_path.read_text(encoding="utf-8")

    assert "## Runtime Harness timeline" in summary
    assert "smoke" in summary
    assert "exit_code=0" in summary
