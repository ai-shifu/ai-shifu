import contextlib
import json
import queue
import threading
import time
import traceback
from typing import Any, Generator, Optional

from flask import Flask

from flaskr.service.common.models import AppException, raise_error
from flaskr.service.user.repository import load_user_aggregate
from flaskr.i18n import _

from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
    RunStatusDTO,
)
from flaskr.common.cache_provider import cache as cache_provider
from flaskr.dao import db
from flaskr.service.learn.const import INPUT_TYPE_ASK
from flaskr.service.shifu.shifu_struct_manager import (
    get_shifu_dto,
    get_outline_item_dto,
    ShifuInfoDto,
    ShifuOutlineItemDto,
    get_default_shifu_dto,
    get_shifu_struct,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.order.models import Order
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.learn.context_v2 import RunScriptContextV2
from flaskr.service.learn.listen_elements import ListenElementRunAdapter
import datetime
from flaskr.common.log import thread_local as log_thread_local
from flaskr.service.learn.exceptions import BreakException
from flaskr.i18n import get_current_language, set_language
from flaskr.common.shifu_context import (
    get_shifu_context_snapshot,
    apply_shifu_context_snapshot,
)

RUN_SCRIPT_TIMEOUT_SECONDS = 5 * 60
RUN_SCRIPT_STATUS_REFRESH_SECONDS = 30

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
        from flaskr.dao import redis_client

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
        from flaskr.dao import redis_client

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
) -> Optional[int]:
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


def run_script_inner(
    app: Flask,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    input: str | dict = None,
    input_type: str = None,
    reload_generated_block_bid: str = None,
    reload_element_bid: str = None,
    listen: bool = False,
    preview_mode: bool = False,
    stop_event: threading.Event | None = None,
    element_adapter: ListenElementRunAdapter | None = None,
    manage_app_context: bool = True,
) -> Generator[RunMarkdownFlowDTO | RunElementSSEMessageDTO, None, None]:
    """
    Core function for running course scripts
    """

    def _finalize_langfuse_if_available(
        context: RunScriptContextV2 | None,
    ) -> None:
        finalize_trace = getattr(context, "_finalize_langfuse_trace", None)
        if callable(finalize_trace):
            finalize_trace()

    def _run() -> Generator[RunMarkdownFlowDTO | RunElementSSEMessageDTO, None, None]:
        run_script_context: RunScriptContextV2 | None = None
        try:
            user_info = load_user_aggregate(user_bid)
            if not user_info:
                raise_error("USER.USER_NOT_FOUND")
            shifu_info: ShifuInfoDto = None
            outline_item_info: ShifuOutlineItemDto = None
            struct_info: HistoryItem = None
            if not outline_bid:
                app.logger.info("lesson_id is None")
                if not shifu_bid:
                    shifu_info = get_default_shifu_dto(app, preview_mode)
                else:
                    shifu_info = get_shifu_dto(app, shifu_bid, preview_mode)
                if not shifu_info:
                    raise_error("server.outline.hasNotLesson")
                shifu_bid = shifu_info.bid
            else:
                outline_item_info = get_outline_item_dto(app, outline_bid, preview_mode)
                if not outline_item_info:
                    raise_error("server.shifu.lessonNotFoundInCourse")
                shifu_bid = outline_item_info.shifu_bid
                shifu_info = get_shifu_dto(app, shifu_bid, preview_mode)
                if not shifu_info:
                    raise_error("server.shifu.courseNotFound")

            struct_info = get_shifu_struct(app, shifu_info.bid, preview_mode)
            if not struct_info:
                raise_error("server.shifu.shifuNotFound")
            if not outline_item_info:
                lesson_info = None
            else:
                lesson_info = outline_item_info
                app.logger.info(f"lesson_info: {lesson_info.__json__()}")

            if shifu_info.price > 0:
                success_buy_record = (
                    Order.query.filter(
                        Order.user_bid == user_bid,
                        Order.shifu_bid == shifu_bid,
                        Order.status == ORDER_STATUS_SUCCESS,
                        Order.deleted == 0,
                    )
                    .order_by(Order.id.desc())
                    .first()
                )
                if not success_buy_record:
                    is_paid = False
                else:
                    is_paid = True
            else:
                is_paid = True

            run_script_context = RunScriptContextV2(
                app=app,
                shifu_info=shifu_info,
                struct=struct_info,
                outline_item_info=outline_item_info,
                user_info=user_info,
                is_paid=is_paid,
                listen=listen,
                preview_mode=preview_mode,
            )

            run_script_context.set_input(input, input_type)

            def _iter_run_events(events):
                if element_adapter is None:
                    yield from events
                    return
                yield from element_adapter.process(events)

            if reload_generated_block_bid or reload_element_bid:
                if stop_event and stop_event.is_set():
                    app.logger.info("run_script_inner cancelled before reload")
                    db.session.rollback()
                    return
                yield from _iter_run_events(
                    run_script_context.reload(
                        app,
                        reload_generated_block_bid,
                        reload_element_bid=reload_element_bid,
                    )
                )
                db.session.commit()
            while run_script_context.has_next():
                app.logger.warning(
                    f"run_script_context.has_next(): {run_script_context.has_next()}"
                )
                if stop_event and stop_event.is_set():
                    app.logger.info("run_script_inner cancelled by stop_event")
                    db.session.rollback()
                    return
                app.logger.info("run_script_context.run")
                yield from _iter_run_events(run_script_context.run(app))
            _finalize_langfuse_if_available(run_script_context)
            db.session.commit()
        except BreakException:
            _finalize_langfuse_if_available(run_script_context)
            db.session.commit()
            app.logger.info("BreakException")
        except GeneratorExit:
            db.session.rollback()
            app.logger.info("GeneratorExit")
        except Exception:
            _finalize_langfuse_if_available(run_script_context)
            db.session.rollback()
            raise

    if manage_app_context:
        with app.app_context():
            yield from _run()
        return

    yield from _run()


def fmt(o):
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    else:
        return o.__json__()


def _to_sse_chunk(payload: object) -> str:
    return (
        "data: "
        + json.dumps(payload, default=fmt, ensure_ascii=False)
        + "\n\n".encode("utf-8").decode("utf-8")
    )


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


def run_script(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    input: str | dict = None,
    input_type: str = None,
    reload_generated_block_bid: str = None,
    reload_element_bid: str = None,
    listen: bool = False,
    preview_mode: bool = False,
    shifu_context_snapshot: Optional[dict[str, Any]] = None,
) -> Generator[str, None, None]:
    timeout = RUN_SCRIPT_TIMEOUT_SECONDS
    blocking_timeout = 1
    lock_retry_count = 5
    lock_retry_sleep_seconds = 0.2
    heartbeat_interval = float(app.config.get("SSE_HEARTBEAT_INTERVAL", 0.5))
    lock_key = _get_run_script_lock_key(app, user_bid, outline_bid)
    # Learner run SSE now always speaks the element protocol. The listen flag
    # still controls run-time behaviors such as segmented TTS generation.
    use_element_protocol = True
    element_adapter = ListenElementRunAdapter(
        app,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_bid=user_bid,
    )
    stream_element_adapter = element_adapter
    is_ask = input_type == INPUT_TYPE_ASK
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
        # Use SimpleQueue to avoid gevent-patched Queue lock contention in background threads.
        output_queue: queue.SimpleQueue = queue.SimpleQueue()
        # Capture logging context from the request thread so logs in the producer thread keep the same identifiers
        parent_request_id = getattr(log_thread_local, "request_id", None)
        parent_url = getattr(log_thread_local, "url", None)
        parent_client_ip = getattr(log_thread_local, "client_ip", None)
        # Capture language context from the request thread so i18n works in the producer thread
        parent_language = get_current_language()
        # Capture shifu context so background thread can reuse it (may be provided by caller)
        parent_shifu_context = shifu_context_snapshot or get_shifu_context_snapshot()
        producer_thread: threading.Thread | None = None

        def producer():
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
                res = run_script_inner(
                    app=app,
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                    input=input,
                    input_type=input_type,
                    reload_generated_block_bid=reload_generated_block_bid,
                    reload_element_bid=reload_element_bid,
                    listen=listen,
                    preview_mode=preview_mode,
                    stop_event=stop_event,
                    element_adapter=element_adapter,
                    manage_app_context=False,
                )
                try:
                    for item in res:
                        if stop_event.is_set():
                            break
                        if isinstance(item, RunMarkdownFlowDTO):
                            for converted_item in element_adapter.process([item]):
                                output_queue.put(("data", converted_item))
                            continue
                        output_queue.put(("data", item))
                except Exception as exc:
                    if stop_event.is_set():
                        app.logger.info(
                            "run_script producer stopped due to client disconnect: %s",
                            type(exc).__name__,
                        )
                        return
                    output_queue.put(("error", exc))
                finally:
                    with contextlib.suppress(Exception):
                        res.close()
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
            last_stream_type: str | None = None
            last_stream_done_is_terminal: bool | None = None

            def _should_suppress_live_payload(payload_obj: object) -> bool:
                payload_type = getattr(payload_obj, "type", None)
                if hasattr(payload_type, "value"):
                    payload_type = payload_type.value
                return bool(
                    use_element_protocol
                    and payload_type == GeneratedType.DONE.value
                    and not bool(getattr(payload_obj, "is_terminal", False))
                )

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
                            client_disconnected = True
                            stop_event.set()
                            app.logger.info(
                                "Client disconnected from SSE stream during heartbeat"
                            )
                            return
                        except (ConnectionError, BrokenPipeError, OSError) as exc:
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
                        payload_type = getattr(payload, "type", None)
                        if hasattr(payload_type, "value"):
                            payload_type = payload_type.value
                        yield (
                            "data: "
                            + json.dumps(payload, default=fmt, ensure_ascii=False)
                            + "\n\n".encode("utf-8").decode("utf-8")
                        )
                        if isinstance(payload_type, str):
                            last_stream_type = payload_type
                            if payload_type == GeneratedType.DONE.value:
                                last_stream_done_is_terminal = bool(
                                    getattr(payload, "is_terminal", False)
                                )
                            else:
                                last_stream_done_is_terminal = None
                    except GeneratorExit:
                        client_disconnected = True
                        stop_event.set()
                        app.logger.info(
                            "Client disconnected from SSE stream (GeneratorExit)"
                        )
                        return
                    except (ConnectionError, BrokenPipeError, OSError) as exc:
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

            if stream_error and not client_disconnected:
                if isinstance(stream_error, Exception):
                    app.logger.error("run_script error")
                    app.logger.error(stream_error)
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

                    if isinstance(stream_error, AppException):
                        app.logger.info(error_info)
                        error_content = str(stream_error)
                    else:
                        app.logger.error(error_info)
                        error_content = str(_("server.common.unknownError"))
                    yield _to_sse_chunk(
                        _make_terminal_event(
                            outline_bid=outline_bid,
                            event_type="error",
                            content=error_content,
                            element_adapter=stream_element_adapter,
                        )
                    )
                    last_stream_type = "error"
                    block_end_event = _make_terminal_event(
                        outline_bid=outline_bid,
                        event_type=GeneratedType.BREAK.value,
                        content="",
                        element_adapter=stream_element_adapter,
                        is_terminal=False if listen else None,
                    )
                    if not _should_suppress_live_payload(block_end_event):
                        yield _to_sse_chunk(block_end_event)
                        last_stream_type = (
                            GeneratedType.DONE.value
                            if use_element_protocol
                            else GeneratedType.BREAK.value
                        )
                        last_stream_done_is_terminal = (
                            False if use_element_protocol else None
                        )

            if not client_disconnected and not (
                use_element_protocol
                and last_stream_type == GeneratedType.DONE.value
                and last_stream_done_is_terminal is True
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
                last_stream_type = GeneratedType.DONE.value
                last_stream_done_is_terminal = True if use_element_protocol else None
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
    started_at = _get_run_script_started_at(app, user_bid, outline_bid)
    if started_at is None:
        return RunStatusDTO(is_running=False, running_time=0)
    return RunStatusDTO(
        is_running=True,
        running_time=max(0, int(time.time()) - started_at),
    )
