"""Choose and produce the events for one request: a lesson turn or a follow-up answer."""

import contextlib
import threading
from collections.abc import Generator

from flask import Flask
from flaskr.dao import (
    cleanup_session_after,
)
from flaskr.service.common.models import AppError, raise_error
from flaskr.service.learn.const import INPUT_TYPE_ASK
from flaskr.service.learn.elements.run_adapter import ListenElementRunAdapter
from flaskr.service.learn.exceptions import BreakError
from flaskr.service.learn.host.db_session import (
    _commit_pending_step,
    _discard_session_connection,
    _ensure_healthy_db_connection,
    _remove_db_session_safely,
)
from flaskr.service.learn.host.sse import _make_audio_backfill_ready_event
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
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
