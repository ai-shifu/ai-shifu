"""Stream one 2.0 (agent engine) lesson turn for run_script.

``runscript_v2._lesson_events`` chooses the engine and handles its fallbacks;
this module holds the 2.0 preview preparation and turn streaming. Collaborators
that tests patch on ``runscript_v2`` are resolved through that module.
"""

import contextlib
from collections.abc import Generator
from types import ModuleType

from flask import Flask
from flaskr.service.common.models import ERROR_CODE, AppError, raise_error
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.listen_elements import ListenElementRunAdapter
from flaskr.service.learn.runscript_v2_events import _make_audio_backfill_ready_event


def _runscript() -> ModuleType:
    """Resolve collaborators through ``runscript_v2`` so its patch points stay live."""
    from flaskr.service.learn import runscript_v2

    return runscript_v2


def _prepare_agent_preview(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    user_input: str | dict | None,
    reload_generated_block_bid: str | None,
    reload_element_bid: str | None,
    element_adapter: ListenElementRunAdapter,
) -> Generator[RunElementSSEMessageDTO, None, dict[str, object] | None]:
    """Open a 2.0 preview run, or replay a pending one.

    Returns the extra ``agent_lesson_events`` options, or ``None`` when a
    pending preview record was replayed and the request is already complete.
    """
    from flaskr.service.learn.agent.lesson_entry import require_teachable_preview

    preview_options: dict[str, object] = {}
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
            return None
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
    return preview_options


def _stream_agent_lesson(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    user_input: str | dict | None,
    reload_generated_block_bid: str | None,
    reload_element_bid: str | None,
    listen: bool,
    learning_mode: str,
    preview_mode: bool,
    element_adapter: ListenElementRunAdapter,
    heartbeat_interval: float,
) -> Generator[RunMarkdownFlowDTO | RunElementSSEMessageDTO, None, None]:
    """Teach one 2.0 turn and commit its staged elements before terminal DONE."""
    from flaskr.service.learn.agent.lesson_entry import agent_lesson_events

    preview_options = {}
    if preview_mode:
        preview_options = yield from _prepare_agent_preview(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_input=user_input,
            reload_generated_block_bid=reload_generated_block_bid,
            reload_element_bid=reload_element_bid,
            element_adapter=element_adapter,
        )
        if preview_options is None:
            return
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
        if (
            exc.code == ERROR_CODE["server.learn.agentInputBudgetExceeded"]
            and element_adapter is not None
        ):
            # A later tool request can be refused after text was shown. Persist its
            # buffered elements before surfacing the error, without sending DONE.
            yield from element_adapter.finalize_pending_blocks()
            _runscript()._commit_pending_step()
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
    _runscript()._commit_pending_step()
    if preview_mode:
        from flaskr.service.learn.agent.preview_history import preview_status_event

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
