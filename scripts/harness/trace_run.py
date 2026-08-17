#!/usr/bin/env python3
"""Collect browser and backend diagnostics into a durable harness run artifact."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = ROOT / "artifacts" / "runs"
DEFAULT_PLAYWRIGHT_OUTPUT_ROOT = ROOT / "src" / "cook-web" / "test-results"
REQUEST_ID_KEYS = {
    "requestid",
    "xrequestid",
    "lastrequestid",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Write artifacts/runs/<run-id>/trace-run.json from browser "
            "diagnostics, request ids, and backend harness diagnostics."
        )
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Harness run id. Defaults to a UTC timestamp.",
    )
    parser.add_argument(
        "--request-id",
        action="append",
        default=[],
        help="Request id to include and inspect. Repeatable.",
    )
    parser.add_argument(
        "--browser-diagnostics",
        action="append",
        default=[],
        help="Path to a Playwright harness-diagnostics.json file. Repeatable.",
    )
    parser.add_argument(
        "--playwright-output-root",
        default=str(DEFAULT_PLAYWRIGHT_OUTPUT_ROOT),
        help="Directory scanned for harness-diagnostics.json files.",
    )
    parser.add_argument(
        "--artifacts-root",
        default=str(DEFAULT_ARTIFACT_ROOT),
        help="Root directory for harness run artifacts.",
    )
    parser.add_argument(
        "--skip-scan",
        action="store_true",
        help="Do not scan the Playwright output root for diagnostics files.",
    )
    parser.add_argument(
        "--skip-backend-diagnostics",
        action="store_true",
        help="Do not invoke src/api/scripts/harness_diagnostics.py.",
    )
    parser.add_argument(
        "--backend-timeout-seconds",
        type=int,
        default=20,
        help="Timeout per backend diagnostics request id.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return nonzero when backend diagnostics fail.",
    )
    return parser


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_run_id() -> str:
    return "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def normalize_run_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return cleaned.strip("-") or default_run_id()


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "diagnostics file must contain a JSON object"
    return payload, None


def collect_request_ids(value: Any) -> list[str]:
    found: list[str] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                normalized_key = str(key).replace("_", "").replace("-", "").lower()
                if normalized_key in REQUEST_ID_KEYS and isinstance(child, str):
                    add_request_id(child)
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    def add_request_id(raw: str) -> None:
        request_id = raw.strip()
        if request_id and request_id not in found:
            found.append(request_id)

    visit(value)
    return found


def discover_browser_diagnostics(
    explicit_paths: list[str],
    playwright_output_root: Path,
    *,
    skip_scan: bool,
) -> list[Path]:
    paths: list[Path] = []
    for raw_path in explicit_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT / path
        if path not in paths:
            paths.append(path)

    if not skip_scan and playwright_output_root.exists():
        for path in sorted(playwright_output_root.rglob("harness-diagnostics.json")):
            if path not in paths:
                paths.append(path)

    return paths


def load_browser_diagnostics(
    paths: list[Path],
) -> tuple[list[dict[str, Any]], list[str]]:
    diagnostics: list[dict[str, Any]] = []
    request_ids: list[str] = []
    for path in paths:
        entry: dict[str, Any] = {
            "path": safe_relative(path),
            "exists": path.exists(),
        }
        if not path.exists():
            entry["error"] = "file not found"
            diagnostics.append(entry)
            continue

        payload, error = read_json(path)
        if error:
            entry["error"] = error
            diagnostics.append(entry)
            continue

        entry["payload"] = payload
        for request_id in collect_request_ids(payload):
            if request_id not in request_ids:
                request_ids.append(request_id)
        diagnostics.append(entry)

    return diagnostics, request_ids


def run_backend_diagnostics(
    request_id: str,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    script = ROOT / "src" / "api" / "scripts" / "harness_diagnostics.py"
    command = [
        sys.executable,
        "scripts/harness_diagnostics.py",
        "--request-id",
        request_id,
    ]
    entry: dict[str, Any] = {
        "request_id": request_id,
        "cwd": safe_relative(script.parent.parent),
        "command": " ".join(command),
    }
    if not script.exists():
        entry.update({"returncode": 127, "stderr": "harness_diagnostics.py not found"})
        return entry

    try:
        result = subprocess.run(
            command,
            cwd=script.parent.parent,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        entry.update(
            {
                "returncode": 124,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or f"timed out after {timeout_seconds}s",
            }
        )
        return entry

    entry.update(
        {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
    return entry


def build_artifact(args: argparse.Namespace) -> tuple[dict[str, Any], Path, bool]:
    run_id = normalize_run_id(args.run_id or default_run_id())
    run_dir = Path(args.artifacts_root)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    run_dir = run_dir / run_id

    playwright_output_root = Path(args.playwright_output_root)
    if not playwright_output_root.is_absolute():
        playwright_output_root = ROOT / playwright_output_root

    browser_paths = discover_browser_diagnostics(
        args.browser_diagnostics,
        playwright_output_root,
        skip_scan=args.skip_scan,
    )
    browser_diagnostics, browser_request_ids = load_browser_diagnostics(browser_paths)

    request_ids: list[str] = []
    for request_id in list(args.request_id) + browser_request_ids:
        normalized = str(request_id).strip()
        if normalized and normalized not in request_ids:
            request_ids.append(normalized)

    backend_diagnostics: list[dict[str, Any]] = []
    backend_failed = False
    if not args.skip_backend_diagnostics:
        for request_id in request_ids:
            diagnostic = run_backend_diagnostics(
                request_id,
                timeout_seconds=args.backend_timeout_seconds,
            )
            backend_failed = backend_failed or diagnostic.get("returncode") not in (
                0,
                None,
            )
            backend_diagnostics.append(diagnostic)

    artifact: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": utc_now_iso(),
        "root": str(ROOT),
        "request_ids": request_ids,
        "summary": {
            "browser_diagnostics_count": len(browser_diagnostics),
            "request_id_count": len(request_ids),
            "backend_diagnostics_count": len(backend_diagnostics),
            "backend_failed": backend_failed,
        },
        "browser_diagnostics": browser_diagnostics,
        "backend_diagnostics": backend_diagnostics,
        "hints": {
            "rerun": (
                "python scripts/harness/trace_run.py "
                f"--run-id {run_id} "
                + " ".join(f"--request-id {request_id}" for request_id in request_ids)
            ).strip(),
            "artifact": safe_relative(run_dir / "trace-run.json"),
        },
    }
    return artifact, run_dir / "trace-run.json", backend_failed


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.backend_timeout_seconds <= 0:
        parser.error("--backend-timeout-seconds must be greater than 0")

    artifact, artifact_path, backend_failed = build_artifact(args)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {safe_relative(artifact_path)}")
    print(
        "request_ids: "
        + (", ".join(artifact["request_ids"]) if artifact["request_ids"] else "none")
    )
    if args.strict and backend_failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
