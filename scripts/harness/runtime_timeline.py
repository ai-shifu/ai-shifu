#!/usr/bin/env python3
"""Record Runtime Harness phase timing and endpoint-readiness evidence."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_INTERVAL_SECONDS = 2.0
MAX_REQUEST_TIMEOUT_SECONDS = 10.0


def positive_float(raw: str) -> float:
    """Parse a strictly positive duration for a wait argument."""
    value = float(raw)
    if value <= 0:
        message = "duration must be greater than zero"
        raise argparse.ArgumentTypeError(message)
    return value


def utc_now() -> str:
    """Return the current UTC time in ISO-8601 format with a trailing Z."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def parse_key_value(raw: str) -> tuple[str, str]:
    """Parse a KEY=VALUE detail argument."""
    key, separator, value = raw.partition("=")
    if not separator or not key.strip():
        message = "details must use KEY=VALUE format"
        raise argparse.ArgumentTypeError(message)
    return key.strip(), value


def details_from_args(raw_details: list[tuple[str, str]]) -> dict[str, str]:
    """Convert repeated parser detail values into a JSON-safe mapping."""
    return dict(raw_details)


def empty_timeline() -> dict[str, Any]:
    """Return an empty runtime-harness timeline document."""
    return {"schema_version": SCHEMA_VERSION, "events": []}


def load_timeline(path: Path) -> dict[str, Any]:
    """Load a timeline document or return the initial document when absent."""
    if not path.exists():
        return empty_timeline()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        message = f"timeline is not valid JSON: {path}"
        raise ValueError(message) from exc
    if payload.get("schema_version") != SCHEMA_VERSION:
        message = f"unsupported timeline schema in {path}"
        raise ValueError(message)
    events = payload.get("events")
    if not isinstance(events, list):
        message = f"timeline events must be a list: {path}"
        raise TypeError(message)
    return payload


def write_timeline(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write a timeline document to its destination path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary:
        json.dump(payload, temporary, ensure_ascii=False, indent=2, sort_keys=True)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def append_event(
    path: Path,
    *,
    name: str,
    status: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a timestamped event and return its JSON-ready representation."""
    timeline = load_timeline(path)
    event: dict[str, Any] = {
        "name": name,
        "status": status,
        "timestamp": utc_now(),
    }
    if details:
        event["details"] = details
    timeline["events"].append(event)
    write_timeline(path, timeline)
    return event


def request_endpoint(url: str, *, timeout_seconds: float) -> tuple[int, str]:
    """Request an endpoint and return its status code with a short detail string."""
    try:
        with urlopen(  # noqa: S310 - CI URLs are explicit
            url, timeout=min(timeout_seconds, MAX_REQUEST_TIMEOUT_SECONDS)
        ) as response:
            return response.status, ""
    except HTTPError as exc:
        return exc.code, f"HTTP {exc.code}"
    except URLError as exc:
        return 0, str(exc.reason)
    except TimeoutError:
        return 0, "request timed out"
    except OSError as exc:
        return 0, str(exc)


def wait_for_endpoint(
    path: Path,
    *,
    name: str,
    url: str,
    timeout_seconds: float,
    interval_seconds: float,
) -> bool:
    """Wait until an HTTP endpoint succeeds, recording ready or timeout evidence."""
    if timeout_seconds <= 0:
        message = "timeout_seconds must be greater than zero"
        raise ValueError(message)
    if interval_seconds <= 0:
        message = "interval_seconds must be greater than zero"
        raise ValueError(message)

    started = time.monotonic()
    deadline = started + timeout_seconds
    attempts = 0
    last_status = 0
    last_error = "not requested"
    while True:
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            elapsed_seconds = round(time.monotonic() - started, 3)
            append_event(
                path,
                name=name,
                status="timeout",
                details={
                    "attempts": attempts,
                    "elapsed_seconds": elapsed_seconds,
                    "last_error": last_error,
                    "last_status_code": last_status,
                    "timeout_seconds": timeout_seconds,
                    "url": url,
                },
            )
            return False

        attempts += 1
        last_status, last_error = request_endpoint(
            url, timeout_seconds=remaining_seconds
        )
        elapsed_seconds = round(time.monotonic() - started, 3)
        if 200 <= last_status < 400:
            append_event(
                path,
                name=name,
                status="ready",
                details={
                    "attempts": attempts,
                    "elapsed_seconds": elapsed_seconds,
                    "status_code": last_status,
                    "url": url,
                },
            )
            return True
        if elapsed_seconds >= timeout_seconds:
            append_event(
                path,
                name=name,
                status="timeout",
                details={
                    "attempts": attempts,
                    "elapsed_seconds": elapsed_seconds,
                    "last_error": last_error,
                    "last_status_code": last_status,
                    "timeout_seconds": timeout_seconds,
                    "url": url,
                },
            )
            return False
        remaining_seconds = max(deadline - time.monotonic(), 0)
        time.sleep(min(interval_seconds, remaining_seconds))


def write_summary(path: Path, destination: Path) -> None:
    """Write a concise GitHub Actions-friendly summary from a timeline document."""
    timeline = load_timeline(path)
    lines = [
        "## Runtime Harness timeline",
        "",
        "| Time (UTC) | Event | Status | Details |",
        "| --- | --- | --- | --- |",
    ]
    for event in timeline["events"]:
        details = event.get("details", {})
        rendered_details = ", ".join(
            f"{key}={value}" for key, value in sorted(details.items())
        )
        lines.append(
            "| {timestamp} | {name} | {status} | {details} |".format(
                timestamp=event["timestamp"],
                name=event["name"],
                status=event["status"],
                details=rendered_details or "-",
            )
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as summary:
        summary.write("\n".join(lines))
        summary.write("\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for timeline operations."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    mark = subparsers.add_parser("mark", help="Record a timestamped phase event")
    mark.add_argument("--output", required=True, type=Path)
    mark.add_argument("--name", required=True)
    mark.add_argument("--status", required=True)
    mark.add_argument("--detail", action="append", default=[], type=parse_key_value)

    wait = subparsers.add_parser("wait", help="Wait for one HTTP endpoint")
    wait.add_argument("--output", required=True, type=Path)
    wait.add_argument("--name", required=True)
    wait.add_argument("--url", required=True)
    wait.add_argument(
        "--timeout-seconds", type=positive_float, default=DEFAULT_TIMEOUT_SECONDS
    )
    wait.add_argument(
        "--interval-seconds", type=positive_float, default=DEFAULT_INTERVAL_SECONDS
    )

    summary = subparsers.add_parser(
        "summary", help="Append a Markdown timeline summary"
    )
    summary.add_argument("--input", required=True, type=Path)
    summary.add_argument(
        "--output",
        type=Path,
        default=Path(
            os.environ.get("GITHUB_STEP_SUMMARY", "runtime-harness-summary.md")
        ),
    )
    return parser


def main() -> int:
    """Run the requested timeline operation."""
    args = build_parser().parse_args()
    if args.command == "mark":
        append_event(
            args.output,
            name=args.name,
            status=args.status,
            details=details_from_args(args.detail),
        )
        return 0
    if args.command == "wait":
        return int(
            not wait_for_endpoint(
                args.output,
                name=args.name,
                url=args.url,
                timeout_seconds=args.timeout_seconds,
                interval_seconds=args.interval_seconds,
            )
        )
    if args.command == "summary":
        write_summary(args.input, args.output)
        return 0
    message = f"unsupported command: {args.command}"
    raise ValueError(message)


if __name__ == "__main__":
    raise SystemExit(main())
