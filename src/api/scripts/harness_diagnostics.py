#!/usr/bin/env python3
"""Inspect request-scoped backend log evidence for the browser harness."""

from __future__ import annotations

from argparse import ArgumentParser
import json
from pathlib import Path
import os
import re
import sys
from urllib.parse import urlencode

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = ROOT / "logs"
DEFAULT_LOKI_URL = os.getenv("AI_SHIFU_LOKI_URL", "http://127.0.0.1:3100").rstrip("/")
DEFAULT_TEMPO_URL = os.getenv("AI_SHIFU_TEMPO_URL", "http://127.0.0.1:3200").rstrip("/")
DEFAULT_PROMETHEUS_URL = os.getenv(
    "AI_SHIFU_PROMETHEUS_URL", "http://127.0.0.1:9090"
).rstrip("/")
DEFAULT_GRAFANA_URL = os.getenv("AI_SHIFU_GRAFANA_URL", "http://127.0.0.1:3001").rstrip(
    "/"
)
TRACE_ID_PATTERNS = (
    re.compile(r"trace_id=([A-Za-z0-9_-]+)"),
    re.compile(r'"trace_id":\s*"([A-Za-z0-9_-]+)"'),
)
REQUEST_METADATA_PATTERN = re.compile(
    r"\s(?P<url>/\S*)\s(?P<request_id>[A-Za-z0-9_-]+)\s"
    r"trace_id=(?P<trace_id>[A-Za-z0-9_-]+)\s"
    r"span_id=(?P<span_id>[A-Za-z0-9_-]+)\s"
    r"status=(?P<status>[0-9-]+)\s"
    r"duration_ms=(?P<duration_ms>[0-9.\-]+)"
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
    parser.add_argument("--loki-url", default=DEFAULT_LOKI_URL)
    parser.add_argument("--tempo-url", default=DEFAULT_TEMPO_URL)
    parser.add_argument("--prometheus-url", default=DEFAULT_PROMETHEUS_URL)
    parser.add_argument("--grafana-url", default=DEFAULT_GRAFANA_URL)
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


def extract_request_metadata(lines: list[str]) -> dict[str, str]:
    for line in reversed(lines):
        match = REQUEST_METADATA_PATTERN.search(line)
        if match:
            return match.groupdict()
    return {}


def _safe_get_json(url: str, params: dict | None = None) -> tuple[bool, dict | str]:
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        return True, response.json()
    except Exception as exc:  # pragma: no cover - network best effort
        return False, str(exc)


def query_loki(loki_url: str, request_id: str) -> dict[str, object]:
    query = f'{{job="ai-shifu-api"}} |= "{request_id}"'
    ok, payload = _safe_get_json(f"{loki_url}/loki/api/v1/query", {"query": query})
    result: dict[str, object] = {"reachable": ok, "query": query}
    if not ok:
        result["error"] = payload
        return result

    streams = payload.get("data", {}).get("result", [])
    result["match_count"] = sum(len(stream.get("values", [])) for stream in streams)
    result["stream_count"] = len(streams)
    return result


def query_tempo(tempo_url: str, trace_ids: list[str]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for trace_id in trace_ids:
        ok, payload = _safe_get_json(f"{tempo_url}/api/traces/{trace_id}")
        summary: dict[str, object] = {"trace_id": trace_id, "reachable": ok}
        if not ok:
            summary["error"] = payload
            summaries.append(summary)
            continue

        batches = payload.get("batches", []) if isinstance(payload, dict) else []
        resource_spans = (
            payload.get("resourceSpans", []) if isinstance(payload, dict) else []
        )
        span_count = 0
        if batches:
            for batch in batches:
                for scope in batch.get("scopeSpans", []):
                    span_count += len(scope.get("spans", []))
        elif resource_spans:
            for resource in resource_spans:
                for scope in resource.get("scopeSpans", []):
                    span_count += len(scope.get("spans", []))
        summary["span_count"] = span_count
        summaries.append(summary)
    return summaries


def query_prometheus(
    prometheus_url: str, request_metadata: dict[str, str]
) -> dict[str, object]:
    path = request_metadata.get("url")
    status = request_metadata.get("status")
    if not path or not status or status == "-":
        return {"reachable": False, "error": "No path/status found in matched logs."}

    query = (
        "sum by (method, path, status) (increase(ai_shifu_http_requests_total"
        f'{{path="{path}",status="{status}"}}[15m]))'
    )
    ok, payload = _safe_get_json(
        f"{prometheus_url}/api/v1/query",
        {"query": query},
    )
    result: dict[str, object] = {"reachable": ok, "query": query}
    if not ok:
        result["error"] = payload
        return result
    result["samples"] = payload.get("data", {}).get("result", [])
    return result


def build_grafana_links(
    grafana_url: str,
    loki_query: str | None,
    trace_ids: list[str],
    prometheus_query: str | None,
) -> dict[str, str]:
    links: dict[str, str] = {}
    if loki_query:
        links["loki_explore"] = (
            f"{grafana_url}/explore?{urlencode({'left': json.dumps(['now-15m', 'now', 'Loki', {'expr': loki_query}])})}"
        )
    if trace_ids:
        links["tempo_trace"] = f"{grafana_url}/explore?traceId={trace_ids[0]}"
    if prometheus_query:
        links["prometheus_explore"] = (
            f"{grafana_url}/explore?{urlencode({'left': json.dumps(['now-15m', 'now', 'Prometheus', {'expr': prometheus_query}])})}"
        )
    return links


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
    request_metadata = extract_request_metadata(lines)
    loki_result = query_loki(args.loki_url.rstrip("/"), request_id)
    tempo_result = query_tempo(args.tempo_url.rstrip("/"), trace_ids)
    prometheus_result = query_prometheus(
        args.prometheus_url.rstrip("/"), request_metadata
    )
    grafana_links = build_grafana_links(
        args.grafana_url.rstrip("/"),
        str(loki_result.get("query", "")) or None,
        trace_ids,
        str(prometheus_result.get("query", ""))
        if prometheus_result.get("query")
        else None,
    )

    print(f"request_id: {request_id}")
    print(f"mode: {detect_langfuse_mode()}")
    print(f"log_dir: {log_dir}")
    print(f"files_scanned: {len(log_files)}")
    print(f"matching_lines: {len(matches)}")
    if request_metadata:
        print("request_metadata:")
        for key in ("url", "status", "duration_ms", "trace_id", "span_id"):
            if request_metadata.get(key):
                print(f"  - {key}: {request_metadata[key]}")

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
    else:
        print("log_excerpt:")
        for path, line in matches[: args.max_lines]:
            relative = path.relative_to(ROOT)
            print(f"  - [{relative}] {line}")

    print("observability:")
    print(f"  - loki: {json.dumps(loki_result, ensure_ascii=False)}")
    print(f"  - tempo: {json.dumps(tempo_result, ensure_ascii=False)}")
    print(f"  - prometheus: {json.dumps(prometheus_result, ensure_ascii=False)}")
    print(f"  - grafana_links: {json.dumps(grafana_links, ensure_ascii=False)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
