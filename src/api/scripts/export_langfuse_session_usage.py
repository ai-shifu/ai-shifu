#!/usr/bin/env python3
"""Export Langfuse model usage aggregated per session into a CSV file."""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional, Tuple

from dotenv import load_dotenv
from langfuse import Langfuse
from langfuse.api.resources.commons.types.observation import Observation
from langfuse.api.resources.commons.types.trace_with_details import TraceWithDetails

# Default pagination size for Langfuse API requests.
# Langfuse rejects page sizes greater than 100.
DEFAULT_PAGE_SIZE = 100

# Determine project root (scripts directory sits inside src/api/scripts/).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


logger = logging.getLogger(__name__)


def parse_iso8601(value: str) -> datetime:
    """Parse an ISO-8601 timestamp or date string."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - defensive against bad input
        raise argparse.ArgumentTypeError(
            f"Unable to parse '{value}'. Use ISO-8601 formats like '2024-09-01' or '2024-09-01T12:00:00+08:00'."
        ) from exc
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Langfuse sessions and aggregate model usage per session, writing the results to a CSV file."
        )
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("langfuse_session_usage.csv"),
        help="Destination CSV path (default: ./langfuse_session_usage.csv).",
    )
    parser.add_argument(
        "--from-ts",
        dest="from_ts",
        type=parse_iso8601,
        default=None,
        help="Only include sessions created on or after this timestamp (ISO-8601).",
    )
    parser.add_argument(
        "--to-ts",
        dest="to_ts",
        type=parse_iso8601,
        default=None,
        help="Only include sessions created before this timestamp (ISO-8601).",
    )
    parser.add_argument(
        "--page-size",
        dest="page_size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Number of records to request per API page (default: {DEFAULT_PAGE_SIZE}).",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Include sessions with zero token usage in the CSV output.",
    )
    return parser.parse_args()


def load_environment() -> None:
    """Load environment variables from the project's .env file if present."""
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH)
    else:
        logger.warning(
            "No .env file found at %s; relying on existing environment variables.",
            ENV_PATH,
        )


def build_langfuse_client() -> Langfuse:
    """Initialise and return a Langfuse client using environment configuration."""
    required_keys = ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"]
    missing = [key for key in required_keys if not os.getenv(key)]
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(
            f"Missing required environment variables for Langfuse: {joined}"
        )

    return Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ["LANGFUSE_HOST"],
    )


def iter_sessions(
    client: Langfuse,
    *,
    page_size: int,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
) -> Iterator:
    page = 1
    while True:
        response = client.fetch_sessions(
            page=page,
            limit=page_size,
            from_timestamp=from_ts,
            to_timestamp=to_ts,
        )
        sessions = response.data or []
        for session in sessions:
            yield session
        meta = getattr(response, "meta", None)
        if not meta or meta.page >= meta.total_pages:
            break
        page += 1


def iter_traces(
    client: Langfuse,
    *,
    page_size: int,
    session_id: Optional[str] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
) -> Iterator[TraceWithDetails]:
    page = 1
    while True:
        response = client.fetch_traces(
            page=page,
            limit=page_size,
            session_id=session_id,
            from_timestamp=from_ts,
            to_timestamp=to_ts,
        )
        traces = response.data or []
        for trace in traces:
            yield trace
        meta = getattr(response, "meta", None)
        if not meta or meta.page >= meta.total_pages:
            break
        page += 1


def iter_observations(
    client: Langfuse,
    *,
    page_size: int,
    trace_id: Optional[str] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
) -> Iterator[Observation]:
    page = 1
    while True:
        response = client.fetch_observations(
            page=page,
            limit=page_size,
            trace_id=trace_id,
            from_start_time=from_ts,
            to_start_time=to_ts,
        )
        observations: Iterable[Observation] = response.data or []
        for observation in observations:
            yield observation
        meta = getattr(response, "meta", None)
        if not meta or meta.page >= meta.total_pages:
            break
        page += 1


def aggregate_usage(
    client: Langfuse,
    *,
    page_size: int,
    from_ts: Optional[datetime],
    to_ts: Optional[datetime],
) -> Tuple[Dict[Tuple[str, str], Dict[str, int]], Dict[str, int], set[str]]:
    """Return usage aggregated by (session_id, model) and overall per-session totals."""
    usage_by_session_model: Dict[Tuple[str, str], Dict[str, int]] = defaultdict(
        lambda: {"input": 0, "output": 0, "total": 0}
    )
    session_totals: Dict[str, int] = defaultdict(int)
    all_sessions: set[str] = set()

    logger.info("Fetching sessions from Langfuse")
    session_count = 0
    for session in iter_sessions(
        client, page_size=page_size, from_ts=from_ts, to_ts=to_ts
    ):
        session_id = getattr(session, "id", None)
        if not session_id:  # pragma: no cover - defensive guard
            logger.warning("Encountered session without id; skipping: %s", session)
            continue
        all_sessions.add(session_id)
        _ = session_totals[session_id]
        session_count += 1

        if session_count % 200 == 0:
            logger.info("Sessions processed: %d", session_count)

    logger.info(
        "Session scan complete: %d sessions processed, %d unique session ids tracked",
        session_count,
        len(all_sessions),
    )

    logger.info("Fetching traces and building trace-session map")
    trace_to_session: Dict[str, str] = {}
    trace_count = 0
    for trace in iter_traces(
        client,
        page_size=page_size,
        from_ts=from_ts,
        to_ts=to_ts,
    ):
        trace_id = getattr(trace, "id", None)
        session_id = getattr(trace, "session_id", None)
        if not trace_id or not session_id:
            continue
        trace_to_session[trace_id] = session_id
        if session_id not in session_totals:
            session_totals[session_id] = 0
            all_sessions.add(session_id)
        trace_count += 1

        if trace_count % 500 == 0:
            logger.info("Traces processed: %d", trace_count)

    logger.info(
        "Trace scan complete: %d traces mapped across %d sessions",
        trace_count,
        len({session for session in trace_to_session.values()}),
    )

    logger.info("Fetching observations and aggregating usage")
    observation_count = 0
    for observation in iter_observations(
        client,
        page_size=page_size,
        from_ts=from_ts,
        to_ts=to_ts,
    ):
        usage = getattr(observation, "usage", None)
        if not usage:
            continue
        trace_id = getattr(observation, "trace_id", None)
        if not trace_id:
            continue
        session_id = trace_to_session.get(trace_id)
        if not session_id:
            continue

        model = getattr(observation, "model", None) or getattr(
            observation, "model_id", None
        )
        model = model or "unknown"

        input_tokens = int(getattr(usage, "input", 0) or 0)
        output_tokens = int(getattr(usage, "output", 0) or 0)
        total_tokens = int(
            getattr(usage, "total", None) or (input_tokens + output_tokens)
        )

        key = (session_id, model)
        usage_by_session_model[key]["input"] += input_tokens
        usage_by_session_model[key]["output"] += output_tokens
        usage_by_session_model[key]["total"] += total_tokens
        session_totals[session_id] += total_tokens
        observation_count += 1

        if observation_count % 1000 == 0:
            logger.info("Observations processed: %d", observation_count)

    logger.info(
        "Observation scan complete: %d observations aggregated, %d session/model pairs recorded",
        observation_count,
        len(usage_by_session_model),
    )

    return usage_by_session_model, session_totals, all_sessions


def write_csv(
    output_path: Path,
    usage_by_session_model: Dict[Tuple[str, str], Dict[str, int]],
    session_totals: Dict[str, int],
    all_sessions: set[str],
    include_empty: bool,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[Tuple[str, str, Dict[str, int]]] = [
        (session_id, model, usage_by_session_model[(session_id, model)])
        for session_id, model in sorted(usage_by_session_model.keys())
    ]

    if include_empty:
        sessions_with_usage = {
            session_id for session_id, _ in usage_by_session_model.keys()
        }
        for session_id in sorted(all_sessions):
            if session_id in sessions_with_usage:
                continue
            if session_totals.get(session_id, 0) == 0:
                rows.append(
                    (session_id, "unknown", {"input": 0, "output": 0, "total": 0})
                )

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "session_id",
                "model",
                "input_tokens",
                "output_tokens",
                "total_tokens",
            ]
        )
        row_count = 0
        for session_id, model, usage in sorted(
            rows, key=lambda item: (item[0], item[1])
        ):
            writer.writerow(
                [
                    session_id,
                    model,
                    usage["input"],
                    usage["output"],
                    usage["total"],
                ]
            )
            row_count += 1

    logger.info("CSV rows written: %d", row_count)
    return row_count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    load_environment()

    try:
        client = build_langfuse_client()
    except SystemExit as exc:
        logger.error(str(exc))
        sys.exit(1)

    logger.info(
        "Fetching Langfuse usage with filters from_ts=%s, to_ts=%s",
        args.from_ts,
        args.to_ts,
    )

    try:
        usage_by_session_model, session_totals, all_sessions = aggregate_usage(
            client,
            page_size=args.page_size,
            from_ts=args.from_ts,
            to_ts=args.to_ts,
        )
    except Exception as exc:  # pragma: no cover - network/IO errors
        logger.error("Failed to fetch usage data: %s", exc)
        sys.exit(1)

    if not usage_by_session_model and not args.include_empty:
        logger.warning(
            "No usage records found; CSV will be empty. Use --include-empty to list idle sessions."
        )

    total_tokens = sum(session_totals.values())
    logger.info(
        "Aggregated totals: %d session/model pairs across %d sessions (total tokens=%d)",
        len(usage_by_session_model),
        len(session_totals),
        total_tokens,
    )

    row_count = write_csv(
        args.output,
        usage_by_session_model,
        session_totals,
        all_sessions,
        args.include_empty,
    )
    logger.info(
        "Wrote usage report to %s (rows=%d, sessions tracked=%d, total tokens=%d)",
        args.output,
        row_count,
        len(session_totals),
        total_tokens,
    )


if __name__ == "__main__":
    main()
