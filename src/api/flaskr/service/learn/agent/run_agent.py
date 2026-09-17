"""Teach one lesson turn with the 2.0 engine, speaking the events 1.0 already produces.

This is the whole of a turn as the host sees it: pick up where the learner left off, decide what
this turn is a response to, run it, and hand back `RunMarkdownFlowDTO` events. What consumes those
-- persisting elements, TTS, the SSE frames -- is the existing 1.0 machinery, unchanged.

Three orderings here are not stylistic:

* **The session is saved before the turn's last event goes out.** The engine streams as it works,
  so a caller that forwarded a terminal event before the write leaves the learner believing a turn
  succeeded that the next request will not find -- answers, pending questions and the finished flag
  all revert.
* **Memory is staged, not committed, and staged before that save.** `stage_memory` writes through
  the profile writer without committing, and `save_agent_session` owns the transaction, so the two
  land together or not at all. A memory write that survived a failed session save would describe a
  learner who never said it.
* **The engine is given no memory store.** It runs on the bridge's producer thread, which has no
  app context and has no business doing synchronous database work. It emits `MemoryUpdated` and the
  host writes it here instead.

Nothing calls this yet: routing a lesson to it is the next change.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from flaskr.service.learn.agent.engine.engine import (
    ContinueTurn,
    InteractionResponseTurn,
    MessageTurn,
    StartTurn,
)
from flaskr.service.learn.agent.engine.events import ErrorEvent, MemoryUpdated, TurnDone
from flaskr.service.learn.agent.legacy_protocol import (
    UnrepresentableInteractionError,
    translate,
)
from flaskr.service.learn.agent.session_store import (
    StoredSessionUnusable,
    load_agent_session,
    save_agent_session,
)
from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO
from flaskr.service.learn.memory import (
    MemoryUpdate,
    VariableMemoryUpdate,
    load_memory,
    stage_memory,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Generator

    from flask import Flask
    from flaskr.service.learn.agent.engine.engine import Engine, TurnInput
    from flaskr.service.learn.agent.engine.events import Event
    from flaskr.service.learn.agent.engine.session import Session


def learner_values(user_input: str | dict | None) -> list[str]:
    """Flatten what the browser sent into the values the learner chose or typed.

    Every lesson input arrives as a map, including free text: the study client normalises a plain
    string to `{"input": ["..."]}` before sending it. Values are kept apart rather than joined,
    because a multi-select answer is several of them and the engine matches each against the
    option it came from.
    """
    if isinstance(user_input, str):
        return [user_input] if user_input.strip() else []
    if not isinstance(user_input, dict):
        return []
    values: list[str] = []
    for value in user_input.values():
        if isinstance(value, list):
            values.extend(str(item) for item in value if item is not None)
        elif value is not None:
            values.append(str(value))
    return [value for value in values if value.strip()]


def _turn_input(session: Session, values: list[str]) -> TurnInput:
    """Decide what this turn is: a start, an answer, a remark, or simply carrying on.

    A session holding a pending interaction answers it, even with nothing: the engine refuses every
    other turn type while one is pending, so anything else ends the turn with an error and leaves
    the question unasked. An empty answer is not usable, which makes the engine ask it again --
    which is what a learner who pressed send on an empty box should see.

    On the first turn the learner's words join the opening prompt, because that is what the engine
    does with a `MessageTurn` there. Elsewhere, input with nothing pending is a remark to react to.
    """
    # Everything but an interaction answer is prose, so several values become one message the way
    # the 1.0 path joins them.
    text = ",".join(values)
    if not session.started:
        return MessageTurn(text=text) if text else StartTurn()
    if session.pending:
        return InteractionResponseTurn(values=list(values))
    if text:
        return MessageTurn(text=text)
    return ContinueTurn()


def _load_or_start(
    app: Flask,
    engine: Engine,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    script: str,
    listen: bool,
) -> Callable[[], Any]:
    """Build the coroutine factory the bridge runs on its producer thread.

    Reading happens out here because it needs the app context this thread has; the session itself
    is built in there, because everything the engine touches has to be created on the loop that
    will drive it.

    What the course knows about the learner is read on every turn rather than once at the start.
    The engine has no memory store to read it for itself, and a stored session carries only the
    snapshot taken when it was last saved, so an author editing a learner's profile would otherwise
    never reach the lesson already in progress.
    """
    try:
        stored = load_agent_session(app, user_bid, outline_bid)
    except StoredSessionUnusable:
        # Written by code whose sessions this one cannot read. Starting over loses the
        # conversation, which is the point of comparing versions rather than parsing hopefully.
        stored = None
    user_memory = load_memory(app, user_bid, shifu_bid).as_variables()

    async def make_session() -> Session:
        if stored is not None:
            stored.user_memory = dict(user_memory)
            return stored
        session = await engine.new_session(script, user_id=user_bid, listen_mode=listen)
        session.user_memory = dict(user_memory)
        return session

    return make_session


def run_agent_lesson(
    app: Flask,
    *,
    engine: Engine,
    script: str,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    user_input: str | dict | None = None,
    listen: bool = False,
    heartbeat_interval: float = 0.5,
    iter_turn: Callable[..., Any] | None = None,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Run one turn of a 2.0 lesson and yield the 1.0 events it produces.

    `iter_turn` is injectable so a test can drive the turn without a thread; the default is the
    bridge, which runs the engine on its own loop and yields events as they arrive.
    """
    from flaskr.service.learn.agent.bridge import iter_turn as bridge_iter_turn

    run_turn_on_thread = iter_turn or bridge_iter_turn
    make_session = _load_or_start(
        app,
        engine,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        script=script,
        listen=listen,
    )
    # One turn is one generated block: TTS audio and element rows hang off this identifier, and a
    # turn is the smallest unit this engine produces that a learner sees as a whole.
    generated_block_bid = uuid.uuid4().hex
    values = learner_values(user_input)
    session_holder: dict[str, Session] = {}

    def make_events() -> AsyncIterator[Event]:
        async def events() -> AsyncIterator[Event]:
            session = await make_session()
            session_holder["session"] = session
            async for event in engine.run_turn(session, _turn_input(session, values)):
                yield event

        return events()

    pending_memory: list[MemoryUpdated] = []

    for event in run_turn_on_thread(make_events, heartbeat_interval=heartbeat_interval):
        if isinstance(event, MemoryUpdated):
            # Held rather than written now: the turn may still fail, and a memory write that
            # outlived a failed session save would describe a learner who never said it.
            pending_memory.append(event)
            continue

        if isinstance(event, (TurnDone, ErrorEvent)):
            session = session_holder.get("session")
            if session is not None:
                _persist(
                    app,
                    session,
                    memory=pending_memory,
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                )
                pending_memory = []

        try:
            yield from translate(
                event,
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
            )
        except UnrepresentableInteractionError:
            # The controls would ask something other than the model did, so they are not sent. The
            # question still is: `translate` builds it first and loses it with the raise, and a
            # learner shown neither has nothing to answer while the session keeps waiting for one.
            app.logger.warning(
                "interaction cannot be rendered as MarkdownFlow: user_bid=%s outline_bid=%s",
                user_bid,
                outline_bid,
                exc_info=True,
            )
            prompt = getattr(event, "spec", None) and event.spec.prompt
            if prompt and prompt.strip():
                yield RunMarkdownFlowDTO(
                    outline_bid=outline_bid,
                    generated_block_bid=generated_block_bid,
                    type=GeneratedType.CONTENT,
                    content=prompt,
                )


def _persist(
    app: Flask,
    session: Session,
    *,
    memory: list[MemoryUpdated],
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
) -> None:
    """Write what the turn produced, memory first so it commits with the session.

    `stage_memory` stages without committing and `save_agent_session` owns the transaction, so the
    two land together. Ordering them the other way would commit the session and leave the memory
    staged for whoever commits next.
    """
    # Session-scoped facts stay in the session, which `save_agent_session` serializes. Writing
    # them to the profile would leak a turn's working notes into preview, Ask and follow-up
    # prompts, and outlive the session that made sense of them. The `remember` tool defaults to
    # session scope, so this is the common case, not the rare one.
    durable = [update for update in memory if update.scope == "user"]
    if durable:
        stage_memory(
            app,
            user_bid,
            shifu_bid,
            MemoryUpdate(
                variables=[
                    VariableMemoryUpdate(
                        key=update.key,
                        value="" if update.value is None else str(update.value),
                    )
                    for update in durable
                ]
            ),
        )
    save_agent_session(
        app,
        session,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
    )
