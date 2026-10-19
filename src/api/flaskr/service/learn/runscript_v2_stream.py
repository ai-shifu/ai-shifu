"""Relay run_script producer output to the SSE client.

The consumer side of ``run_script``: the queue relay with heartbeats, status
refresh, and the closing error/DONE events. Collaborators that tests patch on
``runscript_v2`` are resolved through that module at call time.
"""

import json
import queue
import threading
import time
from collections.abc import Generator
from dataclasses import dataclass
from types import ModuleType

from flask import Flask
from flaskr.service.common.models import AppError
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.listen_elements import ListenElementRunAdapter
from flaskr.service.learn.runscript_v2_events import (
    _is_retryable_llm_stream_connection_error,
    _log_run_script_stream_error,
    _make_terminal_event,
    _to_sse_chunk,
    fmt,
)


def _runscript() -> ModuleType:
    """Resolve collaborators through ``runscript_v2`` so its patch points stay live."""
    from flaskr.service.learn import runscript_v2

    return runscript_v2


@dataclass
class _RunStreamState:
    """Mutable bookkeeping shared by the SSE consumer loop and its tail."""

    run_started_at: int
    status_last_refreshed_at: float = 0.0
    stream_error: Exception | None = None
    client_disconnected: bool = False
    done_received: bool = False
    last_stream_type: str | None = None
    last_stream_done_is_terminal: bool | None = None


def _refresh_run_script_status(
    app: Flask,
    state: _RunStreamState,
    *,
    is_ask: bool,
    user_bid: str,
    outline_bid: str,
    force: bool = False,
) -> None:
    # Ask requests do not own the run-script status slot; skip tracking.
    if is_ask:
        return
    now = time.time()
    if (
        not force
        and now - state.status_last_refreshed_at
        < _runscript().RUN_SCRIPT_STATUS_REFRESH_SECONDS
    ):
        return
    _runscript()._set_run_script_status(
        app, user_bid, outline_bid, state.run_started_at
    )
    state.status_last_refreshed_at = now


def _should_suppress_live_payload(
    payload_obj: object, *, use_element_protocol: bool
) -> bool:
    payload_type = getattr(payload_obj, "type", None)
    if hasattr(payload_type, "value"):
        payload_type = payload_type.value
    return bool(
        use_element_protocol
        and payload_type == GeneratedType.DONE.value
        and not bool(getattr(payload_obj, "is_terminal", False))
    )


def _drain_output_queue(
    app: Flask,
    state: _RunStreamState,
    output_queue: queue.SimpleQueue,
    *,
    stop_event: threading.Event,
    heartbeat_interval: float,
    stream_element_adapter: ListenElementRunAdapter | None,
    use_element_protocol: bool,
    is_ask: bool,
    user_bid: str,
    outline_bid: str,
) -> Generator[str, None, None]:
    """Relay producer output as SSE chunks, with heartbeats while idle.

    Returns when the producer is done, reports an error, or the client goes
    away. A close (``GeneratorExit``) at a yield marks the client as
    disconnected and stops the producer before the close continues outward.
    """

    def _refresh_status() -> None:
        _refresh_run_script_status(
            app, state, is_ask=is_ask, user_bid=user_bid, outline_bid=outline_bid
        )

    while True:
        kind: str
        payload: object
        try:
            kind, payload = output_queue.get_nowait()
        except queue.Empty:
            if state.done_received or state.client_disconnected:
                break
            _refresh_status()
            if heartbeat_interval > 0:
                # Keep waiting cooperative under gevent while polling a thread-safe queue.
                time.sleep(heartbeat_interval)
            else:
                time.sleep(0.01)
            try:
                kind, payload = output_queue.get_nowait()
            except queue.Empty:
                if heartbeat_interval <= 0:
                    continue
                try:
                    heartbeat_payload = (
                        stream_element_adapter.make_ephemeral_message(
                            event_type="heartbeat",
                            content="",
                        )
                        if stream_element_adapter is not None
                        else {"type": "heartbeat"}
                    )
                    yield _to_sse_chunk(heartbeat_payload)
                except GeneratorExit:
                    state.client_disconnected = True
                    stop_event.set()
                    app.logger.info(
                        "Client disconnected from SSE stream during heartbeat"
                    )
                    return
                except (ConnectionError, BrokenPipeError, OSError) as exc:
                    state.client_disconnected = True
                    stop_event.set()
                    app.logger.info(
                        "Client disconnected from SSE stream during heartbeat: %s",
                        repr(exc),
                    )
                    break
                continue

        if kind == "data":
            try:
                _refresh_status()
                if _should_suppress_live_payload(
                    payload, use_element_protocol=use_element_protocol
                ):
                    continue
                payload_type = getattr(payload, "type", None)
                if hasattr(payload_type, "value"):
                    payload_type = payload_type.value
                yield (
                    "data: "
                    + json.dumps(payload, default=fmt, ensure_ascii=False)
                    + b"\n\n".decode("utf-8")
                )
                if isinstance(payload_type, str):
                    state.last_stream_type = payload_type
                    if payload_type == GeneratedType.DONE.value:
                        state.last_stream_done_is_terminal = bool(
                            getattr(payload, "is_terminal", False)
                        )
                    else:
                        state.last_stream_done_is_terminal = None
            except GeneratorExit:
                state.client_disconnected = True
                stop_event.set()
                app.logger.info("Client disconnected from SSE stream (GeneratorExit)")
                return
            except (ConnectionError, BrokenPipeError, OSError) as exc:
                state.client_disconnected = True
                stop_event.set()
                app.logger.info("Client disconnected from SSE stream: %s", repr(exc))
                break
        elif kind == "error":
            if isinstance(payload, Exception):
                state.stream_error = payload
            else:
                state.stream_error = Exception(str(payload))
            break
        elif kind == "done":
            state.done_received = True
            break


def _stream_closing_events(
    app: Flask,
    state: _RunStreamState,
    *,
    outline_bid: str,
    stream_element_adapter: ListenElementRunAdapter | None,
    use_element_protocol: bool,
    runtime_listen: bool,
) -> Generator[str, None, None]:
    """Emit the error/block-end events for a failed run and the terminal DONE."""
    stream_error = state.stream_error
    if (
        stream_error
        and not state.client_disconnected
        and isinstance(stream_error, Exception)
    ):
        _log_run_script_stream_error(app, stream_error)
        if isinstance(stream_error, AppError):
            error_content = str(stream_error)
        elif _is_retryable_llm_stream_connection_error(stream_error):
            error_content = str(_runscript()._("server.learn.llmStreamInterrupted"))
        else:
            error_content = str(_runscript()._("server.common.unknownError"))
        yield _to_sse_chunk(
            _make_terminal_event(
                outline_bid=outline_bid,
                event_type="error",
                content=error_content,
                element_adapter=stream_element_adapter,
            )
        )
        state.last_stream_type = "error"
        block_end_event = _make_terminal_event(
            outline_bid=outline_bid,
            event_type=GeneratedType.BREAK.value,
            content="",
            element_adapter=stream_element_adapter,
            is_terminal=False if runtime_listen else None,
        )
        if not _should_suppress_live_payload(
            block_end_event, use_element_protocol=use_element_protocol
        ):
            yield _to_sse_chunk(block_end_event)
            state.last_stream_type = (
                GeneratedType.DONE.value
                if use_element_protocol
                else GeneratedType.BREAK.value
            )
            state.last_stream_done_is_terminal = False if use_element_protocol else None

    if not state.client_disconnected and not (
        use_element_protocol
        and state.last_stream_type == GeneratedType.DONE.value
        and state.last_stream_done_is_terminal is True
    ):
        yield _to_sse_chunk(
            _make_terminal_event(
                outline_bid=outline_bid,
                event_type=GeneratedType.DONE.value,
                content="",
                element_adapter=stream_element_adapter,
                is_terminal=True if use_element_protocol else None,
            )
        )
        state.last_stream_type = GeneratedType.DONE.value
        state.last_stream_done_is_terminal = True if use_element_protocol else None


def _stream_busy_events(
    app: Flask,
    *,
    is_ask: bool,
    user_bid: str,
    outline_bid: str,
    stream_element_adapter: ListenElementRunAdapter | None,
    use_element_protocol: bool,
) -> Generator[str, None, None]:
    """Tell the client another run already owns this lesson."""
    app.logger.warning(
        "run_script acquisition failed (is_ask=%s): user_bid=%s outline_bid=%s",
        is_ask,
        user_bid,
        outline_bid,
    )
    busy_content = str(_runscript()._("server.learn.outputInProgress"))
    terminal_events = (
        [("error", busy_content), (GeneratedType.DONE.value, "")]
        if use_element_protocol
        else [
            ("error", busy_content),
            (GeneratedType.BREAK.value, ""),
            (GeneratedType.DONE.value, ""),
        ]
    )
    for event_type, content in terminal_events:
        yield _to_sse_chunk(
            _make_terminal_event(
                outline_bid=outline_bid,
                event_type=event_type,
                content=content,
                element_adapter=stream_element_adapter,
                is_terminal=(
                    True
                    if use_element_protocol and event_type == GeneratedType.DONE.value
                    else None
                ),
            )
        )
