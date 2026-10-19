"""SSE framing, terminal events, and stream-error helpers for run_script.

These helpers are pure: they build or classify payloads and never touch the
database, cache, or lock state that ``runscript_v2`` owns.
"""

import json
import traceback
from collections.abc import Generator
from datetime import datetime

from flask import Flask
from flaskr.service.common.models import AppError
from flaskr.service.learn.learn_dtos import (
    AudioBackfillReadyDTO,
    GeneratedType,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.listen_elements import ListenElementRunAdapter
from flaskr.util.datetime import to_utc_iso


def fmt(o: object) -> object:
    """Serialize a value for the shared API response envelope."""
    if isinstance(o, datetime):
        return to_utc_iso(o)
    return o.__json__()


def _to_sse_chunk(payload: object) -> str:
    return (
        "data: "
        + json.dumps(payload, default=fmt, ensure_ascii=False)
        + b"\n\n".decode("utf-8")
    )


def _log_run_script_stream_error(app: Flask, stream_error: Exception) -> None:
    """Log a run-script stream error, keeping handled AppErrors off ERROR.

    Unexpected errors are logged at ERROR for operational alerting, while a
    handled, user-facing AppError is logged at INFO so it stays out of the
    alert stream but remains diagnosable.
    """
    error_traceback = "".join(
        traceback.format_exception(
            type(stream_error),
            stream_error,
            stream_error.__traceback__,
        )
    )
    error_info = {
        "name": type(stream_error).__name__,
        "description": str(stream_error),
        "traceback": error_traceback,
    }

    if isinstance(stream_error, AppError):
        # AppError is already a handled, user-facing business error (for example,
        # a stale lesson URL after a course republish). Keep it out of ERROR-level
        # operational alerts while preserving enough context for diagnostics.
        app.logger.info("run_script handled app exception")
        app.logger.info(error_info)
        return

    app.logger.error("run_script error")
    app.logger.error(error_info)


def _iter_exception_chain(error: BaseException) -> Generator[BaseException, None, None]:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _is_retryable_llm_stream_connection_error(stream_error: Exception) -> bool:
    for exc in _iter_exception_chain(stream_error):
        if isinstance(exc, (ConnectionError, TimeoutError)):
            return True

        exc_module = (exc.__class__.__module__ or "").lower()
        exc_name = (exc.__class__.__name__ or "").lower()
        message = str(exc).lower()

        if "litellm" in exc_module and "apiconnectionerror" in exc_name:
            return True

        if any(
            marker in message
            for marker in (
                "apiconnectionerror",
                "httpx.readerror",
                "httpcore.readerror",
                "incompleteread",
                "record layer failure",
                "[ssl]",
            )
        ):
            return True

    return False


def _make_terminal_event(
    *,
    outline_bid: str,
    event_type: str,
    content: str,
    element_adapter: ListenElementRunAdapter | None,
    is_terminal: bool | None = None,
) -> RunMarkdownFlowDTO | RunElementSSEMessageDTO:
    if element_adapter is not None:
        return element_adapter.make_ephemeral_message(
            event_type=event_type,
            content=content,
            is_terminal=is_terminal,
        )

    legacy_type = (
        GeneratedType.CONTENT if event_type == "error" else GeneratedType(event_type)
    )
    return RunMarkdownFlowDTO(
        outline_bid=outline_bid,
        generated_block_bid="",
        type=legacy_type,
        content=content,
    )


def _extract_audio_backfill_ready_element_bid(
    payload: object,
) -> tuple[str, str] | None:
    if not isinstance(payload, RunElementSSEMessageDTO):
        return None
    if payload.event_type != "element":
        return None

    content = payload.content
    generated_block_bid = (
        payload.generated_block_bid or getattr(content, "generated_block_bid", "") or ""
    )
    element_bid = getattr(content, "element_bid", "") or ""
    if (
        not generated_block_bid
        or not element_bid
        or not bool(getattr(content, "is_final", False))
    ):
        return None

    return generated_block_bid, element_bid


def _make_audio_backfill_ready_event(
    generated_block_bid: str,
    element_bids: list[str],
) -> RunElementSSEMessageDTO:
    return RunElementSSEMessageDTO(
        type=GeneratedType.AUDIO_BACKFILL_READY.value,
        event_type=GeneratedType.AUDIO_BACKFILL_READY.value,
        generated_block_bid=generated_block_bid,
        content=AudioBackfillReadyDTO(
            generated_block_bid=generated_block_bid,
            element_bids=element_bids,
        ),
    )
