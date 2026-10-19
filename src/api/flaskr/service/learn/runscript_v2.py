"""Execute learning sessions and stream their results."""

import contextlib
import queue
import sys
import threading
import time
import uuid
from collections.abc import Generator
from typing import TYPE_CHECKING

from flask import Flask
from flaskr.common.cache_provider import cache as cache_provider
from flaskr.common.log import thread_local as log_thread_local
from flaskr.common.shifu_context import (
    apply_shifu_context_snapshot,
    get_shifu_context_snapshot,
)
from flaskr.dao import (
    db,
    invalidate_session,
    is_abnormal_stream_termination,
    is_protocol_interrupt_error,
)
from flaskr.dao.uow import unit_of_work
from flaskr.i18n import (
    _,  # noqa: F401  # kept patchable on the pre-split module path
    get_current_language,
    set_language,
)
from flaskr.service.common.models import (
    ERROR_CODE,  # noqa: F401  # re-exported public API
    AppError,  # noqa: F401  # re-exported public API
    raise_error,
)
from flaskr.service.learn.agent.routing import uses_agent_engine
from flaskr.service.learn.const import INPUT_TYPE_ASK
from flaskr.service.learn.context_v2 import RunScriptContextV2
from flaskr.service.learn.exceptions import BreakError
from flaskr.service.learn.learn_dtos import (
    AudioBackfillReadyDTO,  # noqa: F401  # re-exported public API
    GeneratedType,  # noqa: F401  # re-exported public API
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
    RunStatusDTO,
)
from flaskr.service.learn.listen_elements import ListenElementRunAdapter
from flaskr.service.learn.runscript_v2_agent import _stream_agent_lesson
from flaskr.service.learn.runscript_v2_events import (
    _extract_audio_backfill_ready_element_bid,
    _is_retryable_llm_stream_connection_error,  # noqa: F401  # re-exported public API
    _log_run_script_stream_error,  # noqa: F401  # re-exported public API
    _make_audio_backfill_ready_event,
    _make_terminal_event,  # noqa: F401  # re-exported public API
    _to_sse_chunk,  # noqa: F401  # re-exported public API
    fmt,  # noqa: F401  # re-exported public API
)
from flaskr.service.learn.runscript_v2_stream import (
    _drain_output_queue,
    _refresh_run_script_status,
    _RunStreamState,
    _stream_busy_events,
    _stream_closing_events,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.shifu_struct_manager import (
    ShifuInfoDto,
    ShifuOutlineItemDto,
    get_outline_item_dto,
    get_shifu_dto,
    get_shifu_struct,
)
from flaskr.service.user.repository import load_user_aggregate
from flaskr.util.datetime import (
    to_utc_iso,  # noqa: F401  # re-exported public API
)
from sqlalchemy import text as sa_text
from sqlalchemy.exc import InterfaceError, OperationalError, ResourceClosedError

if TYPE_CHECKING:
    from flaskr.service.shifu.shifu_history_manager import HistoryItem

RUN_SCRIPT_TIMEOUT_SECONDS = 5 * 60
RUN_SCRIPT_STATUS_REFRESH_SECONDS = 30

# Default max parallel ask (follow-up) requests per (user, outline).
# Actual value is read from Flask config (see MAX_PARALLEL_ASK_COUNT in config.py).
DEFAULT_MAX_PARALLEL_ASK_COUNT = 3


def _remove_db_session_safely(app: Flask, *, source: str) -> None:
    # In finally blocks sys.exc_info still sees a propagating
    # GreenletExit/GeneratorExit that never reached an except handler
    # (injected into IO inside the generator frame); discard the connection
    # before removal in that case instead of letting remove() emit a
    # ROLLBACK on a possibly desynced stream. Uses this module's ``db`` so
    # tests that monkeypatch runscript_v2.db keep working.
    exc = sys.exc_info()[1]
    if exc is not None and is_abnormal_stream_termination(exc):
        invalidate_session(source=source, session=db.session)
    try:
        db.session.remove()
    except Exception:
        app.logger.warning("%s db session cleanup failed", source, exc_info=True)


# Shared termination classification lives in flaskr.dao; keep the historical
# module-level name because tests and callers import it from here.
_is_protocol_desync_error = is_protocol_interrupt_error


def _discard_session_connection(*, source: str) -> None:
    """Drop the session's DB connection instead of returning it to the pool.

    Used when the streaming generator terminates abnormally: the close (or a
    protocol error) can leave an unconsumed response owed on the wire, and
    rolling back on such a connection consumes stale packets and returns a
    poisoned connection to the pool. Delegates to the shared dao helper,
    which resolves the REAL Session through the scoped registry -
    scoped_session does not proxy ``Session.invalidate``, so calling
    ``db.session.invalidate()`` directly raises AttributeError and silently
    does nothing.
    """
    invalidate_session(source=source, session=db.session)


# Number of connection checkouts to probe before giving up: the pool may hold
# more than one poisoned connection, so retry a couple of fresh checkouts.
_CONNECTION_PROBE_ATTEMPTS = 3


def _ensure_healthy_db_connection(app: Flask) -> None:
    """Drop pooled connections whose MySQL protocol stream is desynced.

    A streaming run interrupted mid-IO can return a connection to the pool
    with an unread response packet still buffered. pool_pre_ping cannot catch
    this: the ping reads the stale packet and "succeeds", leaving every later
    query on that connection off by one response, which surfaces as
    ResourceClosedError on SELECTs and pymysql 2014 "Command Out of Sync" on
    rollback. Probe with a nonce echo before the run touches business tables;
    on any mismatch invalidate the connection and retry on a fresh checkout.
    The probe leaves the session transaction open so the run keeps using the
    verified connection.
    """
    last_error: Exception | None = None
    for attempt in range(1, _CONNECTION_PROBE_ATTEMPTS + 1):
        nonce = uuid.uuid4().hex
        try:
            echoed = db.session.execute(
                sa_text("SELECT :nonce"), {"nonce": nonce}
            ).scalar()
            if echoed == nonce:
                return
            last_error = None
            app.logger.warning(
                "db connection probe echoed %r instead of the nonce "
                "(attempt %d/%d); invalidating desynced connection",
                echoed,
                attempt,
                _CONNECTION_PROBE_ATTEMPTS,
            )
        except (ResourceClosedError, OperationalError, InterfaceError) as exc:
            last_error = exc
            app.logger.warning(
                "db connection probe failed (attempt %d/%d); "
                "invalidating desynced connection: %s",
                attempt,
                _CONNECTION_PROBE_ATTEMPTS,
                exc,
            )
        # Session.invalidate() both resets the session state WITHOUT emitting
        # SQL and discards the raw connection - a rollback here would send a
        # ROLLBACK on the very stream that just proved desynced.
        _discard_session_connection(source="db connection probe failure")
    if last_error is not None:
        raise last_error
    message = (
        "db connection probe kept returning mismatched results; "
        "no healthy connection available"
    )
    raise RuntimeError(message)


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


def _commit_pending_step() -> None:
    """Make rows staged between run steps durable.

    ``RunRecorder`` bounds the per-step writes; this checkpoint runs only at
    step boundaries (after a reload rewind, after the stream completes, and
    on ``BreakError``) so collaborators that still stage rows with plain
    flushes never span a ``yield``. The block stages nothing itself: the
    commit is the point.
    """
    with unit_of_work():
        pass


def _finalize_langfuse_if_available(
    context: RunScriptContextV2 | None,
) -> None:
    finalize_trace = getattr(context, "_finalize_langfuse_trace", None)
    if callable(finalize_trace):
        finalize_trace()


def _remember_audio_backfill_ready_element(
    payload: object,
    ready_element_bids_by_block_bid: dict[str, list[str]],
) -> None:
    extracted = _extract_audio_backfill_ready_element_bid(payload)
    if extracted is None:
        return
    generated_block_bid, element_bid = extracted
    element_bids = ready_element_bids_by_block_bid.setdefault(
        generated_block_bid,
        [],
    )
    if element_bid not in element_bids:
        element_bids.append(element_bid)


def _iter_run_events(
    events: object,
    ready_element_bids_by_block_bid: dict[str, list[str]],
    element_adapter: ListenElementRunAdapter | None,
) -> Generator[object, None, None]:
    if element_adapter is None:
        for event in events:
            _remember_audio_backfill_ready_element(
                event,
                ready_element_bids_by_block_bid,
            )
            yield event
        return
    for event in element_adapter.process(events):
        _remember_audio_backfill_ready_element(
            event,
            ready_element_bids_by_block_bid,
        )
        yield event


def _iter_audio_backfill_ready_events(
    ready_element_bids_by_block_bid: dict[str, list[str]],
    input_type: str | None,
) -> Generator[object, None, None]:
    if input_type == INPUT_TYPE_ASK:
        return
    for (
        generated_block_bid,
        element_bids,
    ) in ready_element_bids_by_block_bid.items():
        if not generated_block_bid:
            continue
        yield _make_audio_backfill_ready_event(
            generated_block_bid,
            element_bids,
        )


def _build_run_script_context(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    listen: bool,
    learning_mode: str,
    preview_mode: bool,
    stop_event: threading.Event | None,
) -> RunScriptContextV2:
    """Resolve the learner, course, and payment state for one 1.0 run."""
    resolved_shifu_bid = shifu_bid
    user_info = load_user_aggregate(user_bid)
    if not user_info:
        raise_error("USER.USER_NOT_FOUND")
    shifu_info: ShifuInfoDto = None
    outline_item_info: ShifuOutlineItemDto = None
    struct_info: HistoryItem = None
    if not outline_bid:
        app.logger.info("lesson_id is None")
        if not resolved_shifu_bid:
            raise_error("server.shifu.courseNotFound")
        shifu_info = get_shifu_dto(app, resolved_shifu_bid, preview_mode)
        resolved_shifu_bid = shifu_info.bid
    else:
        outline_item_info = get_outline_item_dto(app, outline_bid, preview_mode)
        resolved_shifu_bid = outline_item_info.shifu_bid
        shifu_info = get_shifu_dto(app, resolved_shifu_bid, preview_mode)

    struct_info = get_shifu_struct(app, shifu_info.bid, preview_mode)
    if not struct_info:
        raise_error("server.shifu.shifuNotFound")
    if not outline_item_info:
        lesson_info = None
    else:
        lesson_info = outline_item_info
        app.logger.info("lesson_info: %s", lesson_info.__json__())

    if shifu_info.price > 0:
        success_buy_record = (
            Order.query.filter(
                Order.user_bid == user_bid,
                Order.shifu_bid == resolved_shifu_bid,
                Order.status == ORDER_STATUS_SUCCESS,
                Order.deleted == 0,
            )
            .order_by(Order.id.desc())
            .first()
        )
        is_paid = bool(success_buy_record)
    else:
        is_paid = True

    return RunScriptContextV2(
        app=app,
        shifu_info=shifu_info,
        struct=struct_info,
        outline_item_info=outline_item_info,
        user_info=user_info,
        is_paid=is_paid,
        listen=listen,
        learning_mode=learning_mode,
        preview_mode=preview_mode,
        stop_event=stop_event,
    )


def _run_script_steps(
    app: Flask,
    run_script_context: RunScriptContextV2,
    ready_element_bids_by_block_bid: dict[str, list[str]],
    *,
    input_type: str | None,
    reload_generated_block_bid: str | None,
    reload_element_bid: str | None,
    stop_event: threading.Event | None,
    element_adapter: ListenElementRunAdapter | None,
) -> Generator[RunMarkdownFlowDTO | RunElementSSEMessageDTO, None, None]:
    """Run an optional reload, then every remaining step of the lesson."""
    if reload_generated_block_bid or reload_element_bid:
        if stop_event and stop_event.is_set():
            app.logger.info("run_script_inner cancelled before reload")
            # Cancellation means the client walked away mid-stream: an
            # exchange may have been interrupted, so discard rather
            # than roll back on a possibly desynced connection.
            _discard_session_connection(source="run_script_inner stop_event cancel")
            return
        yield from _iter_run_events(
            run_script_context.reload(
                app,
                reload_generated_block_bid,
                reload_element_bid=reload_element_bid,
            ),
            ready_element_bids_by_block_bid,
            element_adapter,
        )
        _commit_pending_step()
        yield from _iter_audio_backfill_ready_events(
            ready_element_bids_by_block_bid, input_type
        )
        ready_element_bids_by_block_bid.clear()
    while run_script_context.has_next():
        app.logger.warning(
            "run_script_context.has_next(): %s", run_script_context.has_next()
        )
        if stop_event and stop_event.is_set():
            app.logger.info("run_script_inner cancelled by stop_event")
            _discard_session_connection(source="run_script_inner stop_event cancel")
            return
        app.logger.info("run_script_context.run")
        yield from _iter_run_events(
            run_script_context.run(app),
            ready_element_bids_by_block_bid,
            element_adapter,
        )
    _finalize_langfuse_if_available(run_script_context)
    _commit_pending_step()
    yield from _iter_audio_backfill_ready_events(
        ready_element_bids_by_block_bid, input_type
    )


def _run_script_inner_events(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    user_input: str | dict | None,
    input_type: str | None,
    reload_generated_block_bid: str | None,
    reload_element_bid: str | None,
    listen: bool,
    learning_mode: str,
    preview_mode: bool,
    stop_event: threading.Event | None,
    element_adapter: ListenElementRunAdapter | None,
) -> Generator[RunMarkdownFlowDTO | RunElementSSEMessageDTO, None, None]:
    run_script_context: RunScriptContextV2 | None = None
    try:
        _ensure_healthy_db_connection(app)
        run_script_context = _build_run_script_context(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            listen=listen,
            learning_mode=learning_mode,
            preview_mode=preview_mode,
            stop_event=stop_event,
        )

        run_script_context.set_input(user_input, input_type)

        ready_element_bids_by_block_bid: dict[str, list[str]] = {}
        yield from _run_script_steps(
            app,
            run_script_context,
            ready_element_bids_by_block_bid,
            input_type=input_type,
            reload_generated_block_bid=reload_generated_block_bid,
            reload_element_bid=reload_element_bid,
            stop_event=stop_event,
            element_adapter=element_adapter,
        )
    except BreakError:
        _finalize_langfuse_if_available(run_script_context)
        _commit_pending_step()
        yield from _iter_audio_backfill_ready_events(
            ready_element_bids_by_block_bid, input_type
        )
        app.logger.info("BreakError")
    except GeneratorExit:
        # The close lands at an arbitrary yield point (client disconnect),
        # so the connection's protocol state is unknowable: this is the
        # exact checkin path the pool-level desync detector caught in
        # production. Discard the connection instead of rolling back on it.
        _discard_session_connection(source="run_script_inner GeneratorExit")
        app.logger.info("GeneratorExit")
    except Exception as exc:
        _finalize_langfuse_if_available(run_script_context)
        if _is_protocol_desync_error(exc):
            # Rolling back on a desynced connection consumes stale packets
            # ("Command Out of Sync") and re-pools the poisoned stream.
            _discard_session_connection(source="run_script_inner stream error")
        else:
            db.session.rollback()
        raise
    finally:
        _remove_db_session_safely(app, source="run_script_inner")


def run_script_inner(
    app: Flask,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    user_input: str | dict | None = None,
    input_type: str | None = None,
    reload_generated_block_bid: str | None = None,
    reload_element_bid: str | None = None,
    listen: bool = False,
    learning_mode: str = "read",
    preview_mode: bool = False,
    stop_event: threading.Event | None = None,
    element_adapter: ListenElementRunAdapter | None = None,
    manage_app_context: bool = True,
) -> Generator[RunMarkdownFlowDTO | RunElementSSEMessageDTO, None, None]:
    """Core function for running course scripts."""

    def _run() -> Generator[RunMarkdownFlowDTO | RunElementSSEMessageDTO, None, None]:
        return _run_script_inner_events(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_input=user_input,
            input_type=input_type,
            reload_generated_block_bid=reload_generated_block_bid,
            reload_element_bid=reload_element_bid,
            listen=listen,
            learning_mode=learning_mode,
            preview_mode=preview_mode,
            stop_event=stop_event,
            element_adapter=element_adapter,
        )

    if manage_app_context:
        with app.app_context():
            yield from _run()
        return

    yield from _run()


def _lesson_events(
    *,
    app: Flask,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    user_input: str | dict | None,
    input_type: str | None,
    reload_generated_block_bid: str | None,
    reload_element_bid: str | None,
    listen: bool,
    learning_mode: str,
    preview_mode: bool,
    stop_event: threading.Event,
    element_adapter: ListenElementRunAdapter,
    heartbeat_interval: float,
) -> Generator[RunMarkdownFlowDTO | RunElementSSEMessageDTO, None, None]:
    """Produce this lesson's events with whichever engine teaches it.

    The choice is per deployment, not per course row: FLOW_ENGINE_V2_ENABLED
    enables 2.0 for all courses here; deployments with the flag disabled retain 1.0.

    Everything downstream is shared -- the lock this runs inside, the element adapter, TTS, the SSE
    framing -- so serialisation and persistence hold for both engines without being reimplemented.
    """
    if _teaches_with_agent(
        shifu_bid=shifu_bid,
        input_type=input_type,
        reload_generated_block_bid=reload_generated_block_bid,
        reload_element_bid=reload_element_bid,
    ):
        from flaskr.service.learn.agent.bridge import TurnCapacityError
        from flaskr.service.learn.agent.lesson_entry import LessonNotTeachable

        # The only record of how much traffic 2.0 carries: the decision is per deployment, so it
        # cannot be counted from the database. It is what a decision to raise the worker's turn
        # ceiling would be based on.
        app.logger.info(
            "teaching with the 2.0 engine: shifu_bid=%s outline_bid=%s",
            shifu_bid,
            outline_bid,
        )
        try:
            yield from _stream_agent_lesson(
                app,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                user_input=user_input,
                reload_generated_block_bid=reload_generated_block_bid,
                reload_element_bid=reload_element_bid,
                listen=listen,
                learning_mode=learning_mode,
                preview_mode=preview_mode,
                element_adapter=element_adapter,
                heartbeat_interval=heartbeat_interval,
            )
        except TurnCapacityError:
            # This worker is already running as many turns as it can. Refusing is the bridge's
            # deliberate choice over queueing -- a request parked waiting for a slot has not
            # started its stream, so the learner sees a page that simply hangs. Logged at warning
            # because sustained capacity refusals are the signal to raise the ceiling.
            app.logger.warning(
                "2.0 turn refused, worker at capacity: shifu_bid=%s outline_bid=%s",
                shifu_bid,
                outline_bid,
            )
            # Translated to an AppError because the stream's error handler shows an AppError's own
            # message and renders everything else as "unknown error". Being told the system is
            # busy is something a learner can act on; being told nothing is not.
            raise_error("server.learn.agentTurnCapacity")
        except LessonNotTeachable:
            if reload_generated_block_bid or reload_element_bid:
                # Going back needs the 2.0 session taken back too, which 1.0 cannot do: it would
                # rewrite history and leave the session on its old branch.
                raise_error("server.learn.agentRewindUnavailable")
            # A course selected for 2.0 whose lesson has no script: 1.0 knows what to do with that,
            # and refusing the learner over a configuration mistake would be worse.
            app.logger.warning(
                "agent engine has no script for this lesson, using 1.0: "
                "shifu_bid=%s outline_bid=%s",
                shifu_bid,
                outline_bid,
            )
            # The adapter was built for the agent engine, which writes an element only once it is
            # final. 1.0 relies on each update being written -- a mid-stream refresh reads the
            # latest row -- so this run gets the adapter back the way 1.0 expects it.
            element_adapter.persist_only_final = False
        else:
            return

    yield from run_script_inner(
        app=app,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_input=user_input,
        input_type=input_type,
        reload_generated_block_bid=reload_generated_block_bid,
        reload_element_bid=reload_element_bid,
        listen=listen,
        learning_mode=learning_mode,
        preview_mode=preview_mode,
        stop_event=stop_event,
        element_adapter=element_adapter,
        manage_app_context=False,
    )


def _teaches_with_agent(
    *,
    shifu_bid: str,
    input_type: str | None,
    reload_generated_block_bid: str | None,
    reload_element_bid: str | None,
) -> bool:
    """Whether this particular request goes to the 2.0 engine.

    The deployment must enable 2.0. A follow-up question still keeps the 1.0
    path: it runs beside the lesson under its own semaphore rather than through
    the lesson's turn loop.

    Regenerating a past block or element goes to 2.0 like everything else. It used to go to 1.0,
    which regenerated from rows 2.0 wrote and left the 2.0 session where it was, so the page and
    the lesson disagreed from then on. 2.0 takes its own session back now (`agent.rewind`).
    """
    del (
        reload_generated_block_bid,
        reload_element_bid,
    )  # kept for the call sites; no longer decide
    if not uses_agent_engine(shifu_bid):
        return False
    return input_type != INPUT_TYPE_ASK


def _acquire_run_slot(
    app: Flask,
    *,
    is_ask: bool,
    lock_key: str,
    user_bid: str,
    outline_bid: str,
) -> tuple[object | None, bool]:
    """Take the ask semaphore or the lesson mutex; return ``(lock, acquired)``."""
    timeout = RUN_SCRIPT_TIMEOUT_SECONDS
    blocking_timeout = 1
    lock_retry_count = 5
    lock_retry_sleep_seconds = 0.2
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
    return lock, acquired


def _run_producer(
    app: Flask,
    *,
    parent_request_id: object,
    parent_url: object,
    parent_client_ip: object,
    parent_language: str,
    parent_shifu_context: dict[str, object] | None,
    lesson_kwargs: dict[str, object],
    stop_event: threading.Event,
    output_queue: queue.SimpleQueue,
    element_adapter: ListenElementRunAdapter,
) -> None:
    """Background thread body: run the lesson and feed the SSE output queue."""
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
        res = _lesson_events(**lesson_kwargs)
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
                # own cleanup). Discard the connection; when
                # run_script_inner already invalidated and removed the
                # session this resolves a fresh registry Session and
                # invalidating it is a harmless no-op.
                _discard_session_connection(source="run_script producer abort")
            _remove_db_session_safely(app, source="run_script producer")
            output_queue.put(("done", None))


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
    lock, acquired = _acquire_run_slot(
        app,
        is_ask=is_ask,
        lock_key=lock_key,
        user_bid=user_bid,
        outline_bid=outline_bid,
    )

    if not acquired:
        yield from _stream_busy_events(
            app,
            is_ask=is_ask,
            user_bid=user_bid,
            outline_bid=outline_bid,
            stream_element_adapter=stream_element_adapter,
            use_element_protocol=use_element_protocol,
        )
        return

    stop_event = threading.Event()
    # Use SimpleQueue to avoid gevent-patched Queue lock contention in background threads.
    output_queue: queue.SimpleQueue = queue.SimpleQueue()
    # Language must be handed in by the route handler: this generator body
    # first runs during WSGI response iteration, and on Flask >= 3.1 the
    # request teardown (which clears the request-scoped language) has
    # already executed by then, so get_current_language() here would only
    # ever see the default. The fallback keeps direct callers working.
    producer_kwargs = {
        # Capture logging context from the request thread so logs in the producer
        # thread keep the same identifiers
        "parent_request_id": getattr(log_thread_local, "request_id", None),
        "parent_url": getattr(log_thread_local, "url", None),
        "parent_client_ip": getattr(log_thread_local, "client_ip", None),
        "parent_language": language or get_current_language(),
        # Capture shifu context so background thread can reuse it (may be provided by caller)
        "parent_shifu_context": (
            shifu_context_snapshot or get_shifu_context_snapshot()
        ),
        "lesson_kwargs": {
            "app": app,
            "user_bid": user_bid,
            "shifu_bid": shifu_bid,
            "outline_bid": outline_bid,
            "user_input": user_input,
            "input_type": input_type,
            "reload_generated_block_bid": reload_generated_block_bid,
            "reload_element_bid": reload_element_bid,
            "listen": runtime_listen,
            "learning_mode": learning_mode,
            "preview_mode": preview_mode,
            "stop_event": stop_event,
            "element_adapter": element_adapter,
            "heartbeat_interval": heartbeat_interval,
        },
        "stop_event": stop_event,
        "output_queue": output_queue,
        "element_adapter": element_adapter,
    }
    producer_thread: threading.Thread | None = None
    try:
        producer_thread = threading.Thread(
            target=_run_producer,
            args=(app,),
            kwargs=producer_kwargs,
            name="run_script_stream_producer",
            daemon=True,
        )
        producer_thread.start()

        state = _RunStreamState(run_started_at=int(time.time()))
        _refresh_run_script_status(
            app,
            state,
            is_ask=is_ask,
            user_bid=user_bid,
            outline_bid=outline_bid,
            force=True,
        )
        yield from _drain_output_queue(
            app,
            state,
            output_queue,
            stop_event=stop_event,
            heartbeat_interval=heartbeat_interval,
            stream_element_adapter=stream_element_adapter,
            use_element_protocol=use_element_protocol,
            is_ask=is_ask,
            user_bid=user_bid,
            outline_bid=outline_bid,
        )
        yield from _stream_closing_events(
            app,
            state,
            outline_bid=outline_bid,
            stream_element_adapter=stream_element_adapter,
            use_element_protocol=use_element_protocol,
            runtime_listen=runtime_listen,
        )
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


def get_run_status(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
) -> RunStatusDTO:
    """Return run status."""
    _ = shifu_bid  # noqa: F811 - discards the unused argument locally
    started_at = _get_run_script_started_at(app, user_bid, outline_bid)
    if started_at is None:
        return RunStatusDTO(is_running=False, running_time=0)
    return RunStatusDTO(
        is_running=True,
        running_time=max(0, int(time.time()) - started_at),
    )
