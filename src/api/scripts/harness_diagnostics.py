#!/usr/bin/env python3
"""Inspect request-scoped backend log evidence for the browser harness."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import os
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = ROOT / "logs"
TRACE_ID_PATTERNS = (
    re.compile(r"trace_id=([A-Za-z0-9_-]+)"),
    re.compile(r'"trace_id":\s*"([A-Za-z0-9_-]+)"'),
)


def parse_args() -> ArgumentParser:
    parser = ArgumentParser(
        description="Summarize backend log evidence for a given X-Request-ID."
    )
    parser.add_argument("--request-id", required=True, help="Request id to inspect.")
    parser.add_argument(
        "--log-dir",
        default=str(DEFAULT_LOG_DIR),
        help="Directory containing ai-shifu.log files.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=20,
        help="Maximum number of matching log lines to print.",
    )
    return parser


def iter_log_files(log_dir: Path) -> list[Path]:
    return sorted(
        (path for path in log_dir.glob("ai-shifu.log*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def detect_langfuse_mode() -> str:
    keys = (
        os.getenv("LANGFUSE_PUBLIC_KEY", "").strip(),
        os.getenv("LANGFUSE_SECRET_KEY", "").strip(),
        os.getenv("LANGFUSE_HOST", "").strip(),
    )
    return "langfuse-configured" if all(keys) else "local-log-only"


def collect_matches(log_files: list[Path], request_id: str) -> list[tuple[Path, str]]:
    matches: list[tuple[Path, str]] = []
    for path in log_files:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if request_id in line:
                matches.append((path, line))
    return matches


def extract_trace_ids(lines: list[str]) -> list[str]:
    trace_ids: list[str] = []
    for line in lines:
        for pattern in TRACE_ID_PATTERNS:
            trace_ids.extend(pattern.findall(line))
    deduped: list[str] = []
    for trace_id in trace_ids:
        if trace_id not in deduped:
            deduped.append(trace_id)
    return deduped


def main() -> int:
    parser = parse_args()
    args = parser.parse_args()

    request_id = str(args.request_id).strip()
    log_dir = Path(args.log_dir).resolve()
    if not request_id:
        parser.error("--request-id must not be empty")

    if not log_dir.exists():
        print(f"Log directory not found: {log_dir}", file=sys.stderr)
        return 1

    log_files = iter_log_files(log_dir)
    if not log_files:
        print(f"No ai-shifu.log files found in {log_dir}", file=sys.stderr)
        return 1

    matches = collect_matches(log_files, request_id)
    lines = [line for _, line in matches]
    trace_ids = extract_trace_ids(lines)

    print(f"request_id: {request_id}")
    print(f"mode: {detect_langfuse_mode()}")
    print(f"log_dir: {log_dir}")
    print(f"files_scanned: {len(log_files)}")
    print(f"matching_lines: {len(matches)}")

    if trace_ids:
        print("trace_hints:")
        for trace_id in trace_ids:
            print(f"  - {trace_id}")
    else:
        print("trace_hints:")
        print(
            "  - No explicit trace_id found in matched logs. The backend uses "
            "X-Request-ID as the fallback trace identifier in shared Langfuse helpers."
        )

    if not matches:
        print("log_excerpt:")
        print("  - No matching log lines found.")
        return 0

    print("log_excerpt:")
    for path, line in matches[: args.max_lines]:
        relative = path.relative_to(ROOT)
        print(f"  - [{relative}] {line}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
