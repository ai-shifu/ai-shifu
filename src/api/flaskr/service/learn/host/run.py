"""Run one learning request: take its lock, stream its events over SSE and release it."""

import contextlib
import json
import queue
import threading
import time
from collections.abc import Generator

from flask import Flask
from flaskr.common.cache_provider import cache as cache_provider
from flaskr.common.log import thread_local as log_thread_local
from flaskr.common.shifu_context import (
    apply_shifu_context_snapshot,
    get_shifu_context_snapshot,
)
from flaskr.i18n import _, get_current_language, set_language
from flaskr.service.common.models import AppError
from flaskr.service.learn.const import INPUT_TYPE_ASK
from flaskr.service.learn.elements.run_adapter import ListenElementRunAdapter
from flaskr.service.learn.host.db_session import (
    _discard_session_connection,
    _remove_db_session_safely,
)
from flaskr.service.learn.host.lesson import _lesson_events, _teaches_with_agent
from flaskr.service.learn.host.sse import (
    _is_retryable_llm_stream_connection_error,
    _log_run_script_stream_error,
    _make_terminal_event,
    _to_sse_chunk,
    fmt,
)
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunMarkdownFlowDTO,
    RunStatusDTO,
)
from flaskr.service.learn.request_stream import RequestCompletion

RUN_SCRIPT_TIMEOUT_SECONDS = 5 * 60
RUN_SCRIPT_STATUS_REFRESH_SECONDS = 30
# Upper bound on one blocking queue read when SSE heartbeats are disabled, so
# the run status keeps being refreshed while the producer is quiet.
RUN_SCRIPT_IDLE_WAIT_SECONDS = 1.0

# Default max parallel ask (follow-up) requests per (user, outline).
# Actual value is read from Flask config (see MAX_PARALLEL_ASK_COUNT in config.py).
DEFAULT_MAX_PARALLEL_ASK_COUNT = 3


def _get_max_parallel_ask_count(app: Flask) -> int:
    try:
        return int(
            app.config.get("MAX_PARALLEL_ASK_COUNT", DEFAULT_MAX_PARALLEL_ASK_COUNT)
        )
    except (TypeError, ValueError):
        return DEFAULT_MAX_PARALLEL_ASK_COUNT


# Lua scripts for atomic ask semaphore operations
_LUA_ACQUIRE_ASK_SLOT = """
local key = KEYS[1]
local max_count = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local current = tonumber(redis.call('get', key) or '0')
if current < max_count then
    redis.call('set', key, current + 1, 'EX', ttl)
    return 1
end
return 0
"""

_LUA_RELEASE_ASK_SLOT = """
local key = KEYS[1]
local current = tonumber(redis.call('get', key) or '0')
if current > 0 then
    redis.call('decr', key)
end
return 1
"""


def _get_ask_sem_key(app: Flask, user_bid: str, outline_bid: str) -> str:
    return (
        app.config.get("REDIS_KEY_PREFIX", "")
        + ":ask_sem:"
        + user_bid
        + ":"
        + outline_bid
    )


def _ask_sem_acquire(app: Flask, user_bid: str, outline_bid: str) -> bool:
    """Try to acquire an ask semaphore slot. Returns True if slot acquired."""
    try:
        from flaskr.dao import get_redis_client

        redis_client = get_redis_client()
        if redis_client is None:
            return True  # fail open when Redis is unavailable
        result = redis_client.eval(
            _LUA_ACQUIRE_ASK_SLOT,
            1,
            _get_ask_sem_key(app, user_bid, outline_bid),
            str(_get_max_parallel_ask_count(app)),
            str(RUN_SCRIPT_TIMEOUT_SECONDS),
        )
        return bool(result)
    except Exception as exc:
        app.logger.warning(
            "ask_sem_acquire failed, failing open: user_bid=%s outline_bid=%s error=%s",
            user_bid,
            outline_bid,
            repr(exc),
        )
        return True  # fail open


def _ask_sem_release(app: Flask, user_bid: str, outline_bid: str) -> None:
    """Release an ask semaphore slot."""
    try:
        from flaskr.dao import get_redis_client

        redis_client = get_redis_client()
        if redis_client is None:
            return
        redis_client.eval(
            _LUA_RELEASE_ASK_SLOT,
            1,
            _get_ask_sem_key(app, user_bid, outline_bid),
        )
    except Exception as exc:
        app.logger.warning(
            "ask_sem_release failed: user_bid=%s outline_bid=%s error=%s",
            user_bid,
            outline_bid,
            repr(exc),
        )


def _get_run_script_lock_key(app: Flask, user_bid: str, outline_bid: str) -> str:
    return (
        app.config.get("REDIS_KEY_PREFIX")
        + ":run_script:"
        + user_bid
        + ":"
        + outline_bid
    )


def _get_run_script_status_key(app: Flask, user_bid: str, outline_bid: str) -> str:
    return _get_run_script_lock_key(app, user_bid, outline_bid) + ":running"


def _set_run_script_status(
    app: Flask, user_bid: str, outline_bid: str, started_at: int
) -> None:
    try:
        cache_provider.setex(
            _get_run_script_status_key(app, user_bid, outline_bid),
            RUN_SCRIPT_TIMEOUT_SECONDS,
            str(started_at),
        )
    except Exception as exc:
        app.logger.warning(
            "failed to set run_script status: user_bid=%s outline_bid=%s error=%s",
            user_bid,
            outline_bid,
            repr(exc),
        )


def _clear_run_script_status(app: Flask, user_bid: str, outline_bid: str) -> None:
    try:
        cache_provider.delete(_get_run_script_status_key(app, user_bid, outline_bid))
    except Exception as exc:
        app.logger.warning(
            "failed to clear run_script status: user_bid=%s outline_bid=%s error=%s",
            user_bid,
            outline_bid,
            repr(exc),
        )


def _get_run_script_started_at(
    app: Flask, user_bid: str, outline_bid: str
) -> int | None:
    try:
        raw = cache_provider.get(_get_run_script_status_key(app, user_bid, outline_bid))
    except Exception as exc:
        app.logger.warning(
            "failed to read run_script status: user_bid=%s outline_bid=%s error=%s",
            user_bid,
            outline_bid,
            repr(exc),
        )
        return None

    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    try:
        return int(raw)
    except (TypeError, ValueError):
        app.logger.warning(
            "invalid run_script status payload: user_bid=%s outline_bid=%s payload=%r",
            user_bid,
            outline_bid,
            raw,
        )
        return None


def run_script(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    user_input: str | dict | None = None,
    input_type: str | None = None,
    reload_generated_block_bid: str | None = None,
    reload_element_bid: str | None = None,
    listen: bool = False,
    learning_mode: str = "read",
    preview_mode: bool = False,
    shifu_context_snapshot: dict[str, object] | None = None,
    language: str | None = None,
) -> Generator[str, None, None]:
    """Run script."""
    timeout = RUN_SCRIPT_TIMEOUT_SECONDS
    blocking_timeout = 1
    lock_retry_count = 5
    lock_retry_sleep_seconds = 0.2
    heartbeat_interval = float(app.config.get("SSE_HEARTBEAT_INTERVAL", 0.5))
    lock_key = _get_run_script_lock_key(app, user_bid, outline_bid)
    is_ask = input_type == INPUT_TYPE_ASK
    runtime_listen = bool(listen) and not is_ask
    # Learner run SSE now always speaks the element protocol. The listen flag
    # still controls run-time behaviors such as segmented TTS generation.
    use_element_protocol = True
    # Decided here as well as in `_lesson_events`, because the adapter is built before the
    # producer starts and needs to know which engine it is serving. The predicate reads the
    # deployment's flag and this request's own arguments, so asking twice costs nothing and
    # cannot disagree.
    teaches_with_agent = _teaches_with_agent(
        shifu_bid=shifu_bid,
        input_type=input_type,
        reload_generated_block_bid=reload_generated_block_bid,
        reload_element_bid=reload_element_bid,
    )
    element_adapter = ListenElementRunAdapter(
        app,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_bid=user_bid,
        persist_only_final=teaches_with_agent,
    )
    stream_element_adapter = element_adapter
    completion = RequestCompletion()
    if is_ask:
        # Ask (follow-up) requests use a counting semaphore instead of the main mutex
        # so they can run in parallel with the main lesson stream (up to
        # MAX_PARALLEL_ASK_COUNT, configurable via Flask config).
        lock = None
        acquired = _ask_sem_acquire(app, user_bid, outline_bid)
        if not acquired:
            app.logger.warning(
                "ask semaphore full: user_bid=%s outline_bid=%s max=%s",
                user_bid,
                outline_bid,
                _get_max_parallel_ask_count(app),
            )
    else:
        lock = cache_provider.lock(
            lock_key, timeout=timeout, blocking_timeout=blocking_timeout
        )
        acquired = False
        for attempt in range(lock_retry_count + 1):
            if lock.acquire(blocking=True):
                acquired = True
                break
            if attempt < lock_retry_count:
                app.logger.info(
                    "run_script lock busy, retrying: user_bid=%s outline_bid=%s attempt=%s/%s",
                    user_bid,
                    outline_bid,
                    attempt + 1,
                    lock_retry_count + 1,
                )
                time.sleep(lock_retry_sleep_seconds)

    if acquired:
        stop_event = threading.Event()
        # SimpleQueue is a lock-free thread-safe queue shared with the producer thread.
        output_queue: queue.SimpleQueue = queue.SimpleQueue()
        # Capture logging context from the request thread so logs in the producer thread keep the same identifiers
        parent_request_id = getattr(log_thread_local, "request_id", None)
        parent_url = getattr(log_thread_local, "url", None)
        parent_client_ip = getattr(log_thread_local, "client_ip", None)
        # Language must be handed in by the route handler: this generator body
        # first runs during WSGI response iteration, and on Flask >= 3.1 the
        # request teardown (which clears the request-scoped language) has
        # already executed by then, so get_current_language() here would only
        # ever see the default. The fallback keeps direct callers working.
        parent_language = language or get_current_language()
        # Capture shifu context so background thread can reuse it (may be provided by caller)
        parent_shifu_context = shifu_context_snapshot or get_shifu_context_snapshot()
        producer_thread: threading.Thread | None = None

        def producer() -> None:
            # Propagate logging thread-local context into this background thread
            if parent_request_id:
                log_thread_local.request_id = parent_request_id
            if parent_url:
                log_thread_local.url = parent_url
            if parent_client_ip:
                log_thread_local.client_ip = parent_client_ip
            # Propagate language context into this background thread
            set_language(parent_language)
            # Propagate shifu context into this background thread
            apply_shifu_context_snapshot(parent_shifu_context)
            # Keep the producer thread as the sole owner of the app context for
            # the streaming generator to avoid cross-thread context teardown.
            with app.app_context():
                res = _lesson_events(
                    app=app,
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                    user_input=user_input,
                    input_type=input_type,
                    reload_generated_block_bid=reload_generated_block_bid,
                    reload_element_bid=reload_element_bid,
                    listen=runtime_listen,
                    learning_mode=learning_mode,
                    preview_mode=preview_mode,
                    stop_event=stop_event,
                    element_adapter=element_adapter,
                    heartbeat_interval=heartbeat_interval,
                )
                producer_exc: BaseException | None = None
                exhausted = False
                try:
                    for item in res:
                        if stop_event.is_set():
                            break
                        if isinstance(item, RunMarkdownFlowDTO):
                            for converted_item in element_adapter.process([item]):
                                output_queue.put(("data", converted_item))
                            continue
                        output_queue.put(("data", item))
                    else:
                        # for/else: only a fully exhausted generator reaches
                        # here - every break (stop_event) leaves it False.
                        exhausted = True
                except Exception as exc:
                    producer_exc = exc
                    if stop_event.is_set():
                        app.logger.info(
                            "run_script producer stopped due to client disconnect: %s",
                            type(exc).__name__,
                        )
                    else:
                        output_queue.put(("error", exc))
                except BaseException as exc:
                    producer_exc = exc
                    raise
                finally:
                    with contextlib.suppress(Exception):
                        res.close()
                    if not exhausted or producer_exc is not None:
                        # Anything short of natural exhaustion may have
                        # interrupted a DB exchange (the close above injects
                        # GeneratorExit into the generator's yield point, and
                        # element_adapter.process runs outside the generator's
                        # own cleanup). Discard the connection; when the
                        # lesson or follow-up already invalidated and removed
                        # the session this resolves a fresh registry Session
                        # and invalidating it is a harmless no-op.
                        _discard_session_connection(source="run_script producer abort")
                    _remove_db_session_safely(app, source="run_script producer")
                    output_queue.put(("done", None))

        try:
            producer_thread = threading.Thread(
                target=producer, name="run_script_stream_producer", daemon=True
            )
            producer_thread.start()

            run_started_at = int(time.time())
            status_last_refreshed_at = 0.0

            def _refresh_run_script_status(force: bool = False) -> None:
                # Ask requests do not own the run-script status slot; skip tracking.
                if is_ask:
                    return
                nonlocal status_last_refreshed_at
                now = time.time()
                if (
                    not force
                    and now - status_last_refreshed_at
                    < RUN_SCRIPT_STATUS_REFRESH_SECONDS
                ):
                    return
                _set_run_script_status(app, user_bid, outline_bid, run_started_at)
                status_last_refreshed_at = now

            _refresh_run_script_status(force=True)

            stream_error: Exception | None = None
            client_disconnected = False
            done_received = False

            def _should_suppress_live_payload(payload_obj: object) -> bool:
                payload_type = getattr(payload_obj, "type", None)
                if hasattr(payload_type, "value"):
                    payload_type = payload_type.value
                return bool(
                    use_element_protocol
                    and payload_type == GeneratedType.DONE.value
                    and not bool(getattr(payload_obj, "is_terminal", False))
                )

            # The heartbeat deadline is tracked separately from queue reads, so a
            # queued event is forwarded as soon as it arrives instead of waiting
            # out the rest of a heartbeat interval.
            next_heartbeat_at = time.monotonic() + heartbeat_interval
            while True:
                kind: str
                payload: object
                try:
                    kind, payload = output_queue.get_nowait()
                except queue.Empty:
                    if done_received or client_disconnected:
                        break
                    _refresh_run_script_status()
                    if heartbeat_interval > 0:
                        wait_seconds = max(0.0, next_heartbeat_at - time.monotonic())
                    else:
                        wait_seconds = RUN_SCRIPT_IDLE_WAIT_SECONDS
                    try:
                        kind, payload = output_queue.get(timeout=wait_seconds)
                    except queue.Empty:
                        if heartbeat_interval <= 0:
                            continue
                        next_heartbeat_at = time.monotonic() + heartbeat_interval
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
                            completion.cancel()
                            client_disconnected = True
                            stop_event.set()
                            app.logger.info(
                                "Client disconnected from SSE stream during heartbeat"
                            )
                            return
                        except (ConnectionError, BrokenPipeError, OSError) as exc:
                            completion.cancel()
                            client_disconnected = True
                            stop_event.set()
                            app.logger.info(
                                "Client disconnected from SSE stream during heartbeat: %s",
                                repr(exc),
                            )
                            break
                        continue

                if kind == "data":
                    try:
                        _refresh_run_script_status()
                        if _should_suppress_live_payload(payload):
                            continue
                        chunk = (
                            "data: "
                            + json.dumps(payload, default=fmt, ensure_ascii=False)
                            + b"\n\n".decode("utf-8")
                        )
                        completion.record_serialized(payload)
                        yield chunk
                        next_heartbeat_at = time.monotonic() + heartbeat_interval
                        if completion.terminal_sent:
                            break
                    except GeneratorExit:
                        completion.cancel()
                        client_disconnected = True
                        stop_event.set()
                        app.logger.info(
                            "Client disconnected from SSE stream (GeneratorExit)"
                        )
                        return
                    except (ConnectionError, BrokenPipeError, OSError) as exc:
                        completion.cancel()
                        client_disconnected = True
                        stop_event.set()
                        app.logger.info(
                            "Client disconnected from SSE stream: %s", repr(exc)
                        )
                        break
                elif kind == "error":
                    if isinstance(payload, Exception):
                        stream_error = payload
                    else:
                        stream_error = Exception(str(payload))
                    break
                elif kind == "done":
                    done_received = True
                    break

            if (
                stream_error
                and not client_disconnected
                and isinstance(stream_error, Exception)
            ):
                _log_run_script_stream_error(app, stream_error)
                if isinstance(stream_error, AppError):
                    error_content = str(stream_error)
                elif _is_retryable_llm_stream_connection_error(stream_error):
                    error_content = str(_("server.learn.llmStreamInterrupted"))
                else:
                    error_content = str(_("server.common.unknownError"))
                yield _to_sse_chunk(
                    _make_terminal_event(
                        outline_bid=outline_bid,
                        event_type="error",
                        content=error_content,
                        element_adapter=stream_element_adapter,
                    )
                )
                block_end_event = _make_terminal_event(
                    outline_bid=outline_bid,
                    event_type=GeneratedType.BREAK.value,
                    content="",
                    element_adapter=stream_element_adapter,
                    is_terminal=False if runtime_listen else None,
                )
                if not _should_suppress_live_payload(block_end_event):
                    yield _to_sse_chunk(block_end_event)

            if completion.needs_terminal:
                terminal = _make_terminal_event(
                    outline_bid=outline_bid,
                    event_type=GeneratedType.DONE.value,
                    content="",
                    element_adapter=stream_element_adapter,
                    is_terminal=True if use_element_protocol else None,
                )
                chunk = _to_sse_chunk(terminal)
                completion.record_serialized(terminal)
                yield chunk
        finally:
            stop_event.set()
            if producer_thread is not None:
                producer_thread.join(timeout=0.1)
            if producer_thread is not None and producer_thread.is_alive():
                app.logger.warning("run_script producer thread did not stop in time")

            if is_ask:
                _ask_sem_release(app, user_bid, outline_bid)
            else:
                with contextlib.suppress(Exception):
                    lock.release()
                _clear_run_script_status(app, user_bid, outline_bid)
    else:
        app.logger.warning(
            "run_script acquisition failed (is_ask=%s): user_bid=%s outline_bid=%s",
            is_ask,
            user_bid,
            outline_bid,
        )
        busy_content = str(_("server.learn.outputInProgress"))
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
                        if use_element_protocol
                        and event_type == GeneratedType.DONE.value
                        else None
                    ),
                )
            )


def get_run_status(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
) -> RunStatusDTO:
    """Return run status."""
    _ = shifu_bid
    started_at = _get_run_script_started_at(app, user_bid, outline_bid)
    if started_at is None:
        return RunStatusDTO(is_running=False, running_time=0)
    return RunStatusDTO(
        is_running=True,
        running_time=max(0, int(time.time()) - started_at),
    )
