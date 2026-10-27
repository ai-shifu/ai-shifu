"""Execute learning sessions and stream their results."""

import contextlib
import json
import queue
import sys
import threading
import time
import traceback
import uuid
from collections.abc import Generator
from datetime import datetime

from flask import Flask
from flaskr.common.cache_provider import cache as cache_provider
from flaskr.common.log import thread_local as log_thread_local
from flaskr.common.shifu_context import (
    apply_shifu_context_snapshot,
    get_shifu_context_snapshot,
)
from flaskr.dao import (
    cleanup_session_after,
    db,
    invalidate_session,
    is_abnormal_stream_termination,
    is_protocol_interrupt_error,
)
from flaskr.dao.uow import unit_of_work
from flaskr.i18n import _, get_current_language, set_language
from flaskr.service.common.models import AppError, raise_error
from flaskr.service.learn.const import INPUT_TYPE_ASK
from flaskr.service.learn.exceptions import BreakError
from flaskr.service.learn.learn_dtos import (
    AudioBackfillReadyDTO,
    GeneratedType,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
    RunStatusDTO,
)
from flaskr.service.learn.listen_elements import ListenElementRunAdapter
from flaskr.service.learn.request_stream import RequestCompletion
from flaskr.util.datetime import to_utc_iso
from sqlalchemy import text as sa_text
from sqlalchemy.exc import InterfaceError, OperationalError, ResourceClosedError

RUN_SCRIPT_TIMEOUT_SECONDS = 5 * 60
RUN_SCRIPT_STATUS_REFRESH_SECONDS = 30

# Default max parallel ask (follow-up) requests per (user, outline).
# Actual value is read from Flask config (see MAX_PARALLEL_ASK_COUNT in config.py).
DEFAULT_MAX_PARALLEL_ASK_COUNT = 3


def _remove_db_session_safely(app: Flask, *, source: str) -> None:
    # In finally blocks sys.exc_info still sees a propagating
    # SystemExit/GeneratorExit that never reached an except handler
    # (raised during IO inside the generator frame); discard the connection
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


def _follow_up_events(
    *,
    app: Flask,
    user_bid: str,
    outline_bid: str,
    user_input: str | dict | None,
    reload_generated_block_bid: str | None,
    reload_element_bid: str | None,
    listen: bool,
    learning_mode: str,
    preview_mode: bool,
    stop_event: threading.Event,
    element_adapter: ListenElementRunAdapter,
) -> Generator[RunMarkdownFlowDTO | RunElementSSEMessageDTO, None, None]:
    """Answer a follow-up question, owning its database session like a lesson step."""
    from flaskr.service.learn.ask import FollowUpCancelledError, follow_up_events

    try:
        _ensure_healthy_db_connection(app)
        yield from element_adapter.process(
            follow_up_events(
                app,
                user_bid=user_bid,
                outline_bid=outline_bid,
                user_input=user_input,
                reload_generated_block_bid=reload_generated_block_bid,
                reload_element_bid=reload_element_bid,
                listen=listen,
                learning_mode=learning_mode,
                preview_mode=preview_mode,
                stop_event=stop_event,
            )
        )
        _commit_pending_step()
    except BreakError:
        _commit_pending_step()
        app.logger.info("BreakError")
    except (FollowUpCancelledError, GeneratorExit):
        # The close lands at an arbitrary point (client disconnect), so the
        # connection's protocol state is unknowable: discard it, never roll back.
        _discard_session_connection(source="follow-up cancelled")
        app.logger.info("follow-up stream closed")
    except Exception as exc:
        cleanup_session_after(exc, source="follow-up stream error")
        raise
    finally:
        _remove_db_session_safely(app, source="follow-up")


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
    """Produce this lesson's events: every lesson is taught by the 2.0 engine.

    The lock this runs inside, the element adapter, TTS and the SSE framing are shared with the
    follow-up path, which `learn.ask` answers beside the lesson.

    A lesson with no script is completed as it stands, the way 1.0 finished a lesson with no
    blocks: the outline moves on and the learner is handed the next lesson.
    """
    if input_type == INPUT_TYPE_ASK:
        yield from _follow_up_events(
            app=app,
            user_bid=user_bid,
            outline_bid=outline_bid,
            user_input=user_input,
            reload_generated_block_bid=reload_generated_block_bid,
            reload_element_bid=reload_element_bid,
            listen=listen,
            learning_mode=learning_mode,
            preview_mode=preview_mode,
            stop_event=stop_event,
            element_adapter=element_adapter,
        )
        return
    if not _teaches_with_agent(
        shifu_bid=shifu_bid,
        input_type=input_type,
        reload_generated_block_bid=reload_generated_block_bid,
        reload_element_bid=reload_element_bid,
    ):
        raise_error("server.shifu.courseNotFound")
    from flaskr.api.markdownflow import TurnCapacityError
    from flaskr.service.learn.agent.lesson_entry import (
        DiscardedTurnError,
        LessonNotTeachable,
        agent_lesson_events,
        complete_empty_lesson,
        require_teachable_preview,
    )

    # Logged per request: it is what a decision to raise the worker's turn ceiling is based on.
    app.logger.info(
        "teaching with the 2.0 engine: shifu_bid=%s outline_bid=%s",
        shifu_bid,
        outline_bid,
    )
    # Replace a pooled connection an interrupted stream left desynced before any lesson read.
    _ensure_healthy_db_connection(app)
    try:
        preview_options = {}
        if preview_mode:
            require_teachable_preview(
                app,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
            )
            from flaskr.service.learn.agent.preview_history import (
                begin_preview_run,
                pending_preview_record,
                preview_status_event,
            )
            from flaskr.service.learn.agent.run_agent import learner_values

            if reload_element_bid or reload_generated_block_bid:
                from flaskr.service.learn.agent.preview_rewind import (
                    plan_preview_rewind,
                )
                from flaskr.service.learn.agent.rewind import RewindUnavailableError

                try:
                    plan_preview_rewind(
                        app,
                        user_bid=user_bid,
                        shifu_bid=shifu_bid,
                        outline_bid=outline_bid,
                        anchor=reload_element_bid or reload_generated_block_bid,
                        answering=bool(learner_values(user_input)),
                    )
                except RewindUnavailableError:
                    raise_error("server.learn.agentRewindUnavailable")
            if not learner_values(user_input) and not (
                reload_generated_block_bid or reload_element_bid
            ):
                restored = pending_preview_record(
                    app,
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                )
                if restored is not None:
                    update = preview_status_event(
                        app,
                        user_bid=user_bid,
                        shifu_bid=shifu_bid,
                        outline_bid=outline_bid,
                    )
                    if update is not None:
                        yield update
                    for element in restored.elements:
                        yield RunElementSSEMessageDTO(
                            type="element",
                            event_type="element",
                            content=element,
                            generated_block_bid=element.generated_block_bid,
                        )
                    yield RunElementSSEMessageDTO(
                        type="done", event_type="done", content="", is_terminal=True
                    )
                    return
            preview_options["preview_generation"] = begin_preview_run(
                app,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                run_bid=element_adapter.run_session_bid,
            )
            update = preview_status_event(
                app,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                generation=preview_options["preview_generation"],
            )
            if update is not None:
                yield update
        agent_events = agent_lesson_events(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_input=user_input,
            listen=listen,
            learning_mode=learning_mode,
            preview_mode=preview_mode,
            heartbeat_interval=heartbeat_interval,
            reload_generated_block_bid=reload_generated_block_bid,
            reload_element_bid=reload_element_bid,
            **preview_options,
        )
        # Final snapshots are staged by the adapter on DONE. Adapt here so the commit and
        # readiness notification precede terminal DONE, on which the browser closes SSE.
        adapted_events = (
            element_adapter.process(agent_events)
            if element_adapter is not None
            else agent_events
        )
        ready_by_block: dict[str, list[str]] = {}
        terminal_done = None
        try:
            for payload in adapted_events:
                if (
                    isinstance(payload, RunElementSSEMessageDTO)
                    and payload.type == GeneratedType.DONE.value
                    and payload.is_terminal
                ):
                    terminal_done = payload
                else:
                    yield payload
        except AppError as exc:
            if element_adapter is not None and not isinstance(exc, DiscardedTurnError):
                # A turn can fail after text was shown: a refused tool request, a provider
                # error after output started, or an exhausted recovery. The engine keeps
                # that text in its saved session and continues after it, so persist the
                # buffered elements before surfacing the error, without sending DONE.
                # Errors raised before any output leave nothing pending, and a turn a
                # concurrent reset discarded must leave nothing behind.
                yield from element_adapter.finalize_pending_blocks()
                _commit_pending_step()
            raise
        finally:
            # A disconnect must also close the engine bridge and its turn slot.
            with contextlib.suppress(Exception):
                adapted_events.close()
            with contextlib.suppress(Exception):
                agent_events.close()
        if element_adapter is not None:
            # Fallback narration is finalized in storage without a live patch. Include it
            # from the adapter's snapshots instead of relying only on emitted elements.
            for (
                block_bid,
                element_bid,
            ) in element_adapter.finalized_element_identities():
                ready_by_block.setdefault(block_bid, []).append(element_bid)
        _commit_pending_step()
        if preview_mode:
            update = preview_status_event(
                app,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                generation=preview_options["preview_generation"],
            )
            if update is not None:
                yield update
        for block_bid, element_bids in ready_by_block.items():
            yield _make_audio_backfill_ready_event(block_bid, element_bids)
        if terminal_done is not None:
            yield terminal_done
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
            # A lesson with no script has no turn to take the learner back to.
            raise_error("server.learn.agentRewindUnavailable")
        app.logger.info(
            "completing a lesson with no script: shifu_bid=%s outline_bid=%s",
            shifu_bid,
            outline_bid,
        )
        events = complete_empty_lesson(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            preview_mode=preview_mode,
        )
        # Adapt here, as a lesson turn does, so the next-lesson element the adapter stages
        # is committed before the stream ends rather than discarded with the session.
        yield from (
            element_adapter.process(events) if element_adapter is not None else events
        )
        _commit_pending_step()


def _teaches_with_agent(
    *,
    shifu_bid: str,
    input_type: str | None,
    reload_generated_block_bid: str | None,
    reload_element_bid: str | None,
) -> bool:
    """Whether this request runs a 2.0 lesson turn.

    Every identified course does, except a follow-up question: it runs beside the lesson under
    its own semaphore rather than through the lesson's turn loop. Regenerating a past block or
    element is a 2.0 turn too; 2.0 takes its own session back (`agent.rewind`).
    """
    del (
        reload_generated_block_bid,
        reload_element_bid,
    )  # kept for the call sites; no longer decide
    if not str(shifu_bid or "").strip():
        return False
    return input_type != INPUT_TYPE_ASK


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
                        # Poll the thread-safe queue at the heartbeat interval.
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
