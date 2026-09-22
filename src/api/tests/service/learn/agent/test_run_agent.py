"""Cover one turn of a 2.0 lesson: what it asks the engine for, and what it writes when.

The orderings are the point here. A turn that told the learner it finished before its session was
written loses the answers on the next request, and memory that outlived a failed save describes a
learner who never said it. Each of those is asserted by recording the order of the calls rather
than by checking the end state, which looks identical either way.
"""

from __future__ import annotations

import logging

import pytest
from flaskr.service.learn.agent import run_agent
from flaskr.service.learn.agent.engine.events import (
    ContentDelta,
    ErrorEvent,
    InteractionRequest,
    MemoryUpdated,
    TurnDone,
)
from flaskr.service.learn.agent.engine.interaction import InteractionSpec, Option
from flaskr.service.learn.agent.session_store import StoredSessionUnusable
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW

USER = "user-bid"
SHIFU = "shifu-bid"
OUTLINE = "outline-bid"
PROGRESS = "progress-record-bid"
SCRIPT = "# Lesson\n\nSome content."


class _Session:
    """Stands in for an engine session: only the fields the host reads."""

    def __init__(self, *, started: bool = False, pending: list | None = None) -> None:
        self.started = started
        self.pending = pending or []
        self.user_memory: dict = {}
        self.turn = 0
        self.finished = False


class _Record:
    """Stands in for the locked progress record a turn writes under."""

    def __init__(self) -> None:
        self.status = 602


class _Memory:
    """Stands in for a memory snapshot: the host only projects it to variables."""

    def __init__(self, variables: dict) -> None:
        self._variables = variables

    def as_variables(self) -> dict:
        return dict(self._variables)


class _Engine:
    """Records the turn it was asked for and replays a fixed script of events."""

    def __init__(self, events: list, session: _Session | None = None) -> None:
        self._events = events
        self._session = session or _Session()
        self.turns: list = []
        self.new_session_calls: list[dict] = []

    async def new_session(self, script: str, **kwargs: object) -> _Session:
        self.new_session_calls.append({"script": script, **kwargs})
        return self._session

    def run_turn(self, _session: _Session, turn: object = None) -> object:
        self.turns.append(turn)

        async def events() -> object:
            for event in self._events:
                yield event

        return events()


def _drive(make_events: object, **_kwargs: object) -> object:
    """Run the async iterator to completion on this thread, standing in for the bridge."""
    import asyncio

    async def collect() -> list:
        return [event async for event in make_events()]

    return iter(asyncio.run(collect()))


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, object]]:
    """Record every write the host makes, in order."""
    recorded: list[tuple[str, object]] = []

    def _stage(_app: object, _user: str, _shifu: str, update: object) -> bool:
        recorded.append(("stage_memory", update))
        return True

    def _save(_app: object, _session: object, **kwargs: object) -> None:
        stage = kwargs.pop("stage", None)
        if stage is not None:
            stage()
        recorded.append(("save_session", kwargs))

    def _record_content(**kwargs: object) -> None:
        recorded.append(("record_content", kwargs))

    monkeypatch.setattr(run_agent, "stage_memory", _stage)
    monkeypatch.setattr(run_agent, "save_agent_session", _save)
    monkeypatch.setattr(run_agent, "load_agent_session", lambda *_a, **_k: None)
    monkeypatch.setattr(run_agent, "load_memory", lambda *_a, **_k: _Memory({}))
    monkeypatch.setattr(run_agent, "record_turn_content", _record_content)
    monkeypatch.setattr(run_agent, "_open_turn", lambda *_a, **_k: PROGRESS)
    monkeypatch.setattr(run_agent, "claim_for_writing", lambda **_k: _Record())
    monkeypatch.setattr(run_agent, "mark_lesson_finished", lambda _r: None)

    def _resolve(_app: object, **kwargs: object) -> list:
        recorded.append(("resolve_outline", kwargs))
        return []

    def _apply(_app: object, **kwargs: object) -> None:
        recorded.append(("apply_outline", kwargs))

    monkeypatch.setattr(run_agent, "resolve_outline_progression", _resolve)
    monkeypatch.setattr(run_agent, "apply_outline_progression", _apply)
    return recorded


def _run(
    engine: _Engine,
    *,
    user_input: str | None = None,
    app: object = None,
    listen: bool = False,
) -> list:
    return list(
        run_agent.run_agent_lesson(
            app,
            engine=engine,
            script=SCRIPT,
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_bid=OUTLINE,
            user_input=user_input,
            listen=listen,
            iter_turn=_drive,
        )
    )


# --- what the turn is --------------------------------------------------------------------


def test_a_learner_who_has_not_started_begins_the_lesson(
    calls: list,
) -> None:
    engine = _Engine([TurnDone(reason="end")])
    _run(engine)
    assert engine.turns[0].type == "start"
    assert calls  # the session was written


def test_a_started_lesson_with_nothing_said_carries_on(calls: list) -> None:
    engine = _Engine([TurnDone(reason="end")], session=_Session(started=True))
    _run(engine)
    assert engine.turns[0].type == "continue"
    assert calls


def test_input_while_a_question_is_pending_is_read_as_its_answer(calls: list) -> None:
    """That is what the learner was asked for, so it must not arrive as a side remark."""
    engine = _Engine(
        [TurnDone(reason="end")],
        session=_Session(started=True, pending=[object()]),
    )
    _run(engine, user_input="B")
    turn = engine.turns[0]
    assert turn.type == "interaction.response"
    assert turn.values == ["B"]
    assert calls


def test_input_with_no_question_pending_is_a_remark_to_react_to(calls: list) -> None:
    engine = _Engine([TurnDone(reason="end")], session=_Session(started=True))
    _run(engine, user_input="why?")
    turn = engine.turns[0]
    assert turn.type == "message"
    assert turn.text == "why?"
    assert calls


def test_blank_input_still_answers_the_pending_question_with_nothing(
    calls: list,
) -> None:
    """Blank input answers the pending question with nothing rather than skipping it.

    The engine refuses every other turn type while one is pending, so a continue would end the turn
    with an error and leave the question unasked. An empty answer is unusable, so the engine asks
    it again -- which is what pressing send on an empty box should do.
    """
    engine = _Engine(
        [TurnDone(reason="end")],
        session=_Session(started=True, pending=[object()]),
    )
    _run(engine, user_input="   ")
    turn = engine.turns[0]
    assert turn.type == "interaction.response"
    assert turn.values == []
    assert calls


def test_a_learner_who_says_something_on_the_first_turn_is_heard(calls: list) -> None:
    """The engine joins a first-turn message to the opening prompt; a start turn drops it."""
    engine = _Engine([TurnDone(reason="end")])
    _run(engine, user_input="explain this simply")
    turn = engine.turns[0]
    assert turn.type == "message"
    assert turn.text == "explain this simply"
    assert calls


@pytest.mark.usefixtures("calls")
def test_a_lesson_resumed_from_storage_is_not_started_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = _Session(started=True)
    monkeypatch.setattr(run_agent, "load_agent_session", lambda *_a, **_k: stored)
    engine = _Engine([TurnDone(reason="end")])
    _run(engine)
    assert engine.new_session_calls == []
    assert engine.turns[0].type == "continue"


@pytest.mark.usefixtures("calls")
def test_a_session_this_code_cannot_read_starts_the_lesson_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Comparing versions is only worth doing if an unreadable row leads somewhere."""

    def _raise(*_a: object, **_k: object) -> None:
        raise StoredSessionUnusable

    monkeypatch.setattr(run_agent, "load_agent_session", _raise)
    engine = _Engine([TurnDone(reason="end")])
    _run(engine)
    assert engine.new_session_calls
    assert engine.turns[0].type == "start"


# --- what reaches the learner ------------------------------------------------------------


@pytest.mark.usefixtures("calls")
def test_lesson_text_reaches_the_learner_as_content() -> None:
    engine = _Engine([ContentDelta(text="hello"), TurnDone(reason="end")])
    events = _run(engine)
    assert [e.type for e in events] == [GeneratedType.CONTENT, GeneratedType.BREAK]
    assert events[0].content == "hello"


@pytest.mark.usefixtures("calls")
def test_every_event_of_a_turn_shares_one_generated_block() -> None:
    """Element rows and TTS audio hang off it, so a turn has to be one block to a learner."""
    engine = _Engine(
        [ContentDelta(text="a"), ContentDelta(text="b"), TurnDone(reason="finished")]
    )
    events = _run(engine)
    assert len({e.generated_block_bid for e in events}) == 1


@pytest.mark.usefixtures("calls")
def test_a_memory_write_does_not_reach_the_learner_as_an_event() -> None:
    """It is a write, not something to render; 1.0 sends variable updates from its own path."""
    engine = _Engine([MemoryUpdated(key="name", value="Ada"), TurnDone(reason="end")])
    events = _run(engine)
    assert [e.type for e in events] == [GeneratedType.BREAK]


class _App:
    """Only what this module touches on the app: somewhere to log a refused interaction.

    The shared `app` fixture yields None when SKIP_APP_FIXTURE is set, and this path dereferences
    `app.logger`, so the test would fail on the attribute rather than on the behaviour.
    """

    logger = logging.getLogger("test_run_agent")


@pytest.mark.usefixtures("calls")
def test_an_interaction_the_grammar_cannot_carry_does_not_stop_the_turn() -> None:
    """The rest of the turn still stands; the learner loses the controls, not the lesson."""
    engine = _Engine(
        [
            ContentDelta(text="before"),
            InteractionRequest(
                id="i1",
                spec=InteractionSpec(
                    type="single",
                    prompt="pick",
                    options=[Option(display="A | B")],
                    variable="v",
                ),
            ),
            TurnDone(reason="end"),
        ]
    )
    events = _run(engine, app=_App())
    # The prompt joins the text and stands in for the controls; the text's block closes after it.
    assert [e.type for e in events] == [
        GeneratedType.CONTENT,
        GeneratedType.CONTENT,
        GeneratedType.BREAK,
        GeneratedType.BREAK,
    ]
    assert [e.content for e in events[:2]] == ["before", "pick"]


# --- when things are written -------------------------------------------------------------


def test_the_session_is_written_before_the_turn_says_it_is_over(calls: list) -> None:
    """Otherwise the learner is told a turn succeeded that the next request will not find."""
    engine = _Engine([ContentDelta(text="a"), TurnDone(reason="finished")])
    events = _run(engine)
    assert [name for name, _ in calls] == ["record_content", "save_session"]
    assert events[-1].type == GeneratedType.DONE


def test_memory_is_staged_before_the_session_that_commits_it(calls: list) -> None:
    """`stage_memory` does not commit; `save_agent_session` owns the transaction they share."""
    engine = _Engine(
        [
            MemoryUpdated(key="name", value="Ada", scope="user"),
            TurnDone(reason="finished"),
        ]
    )
    _run(engine)
    # The block is staged inside the session's own transaction, so a turn's elements can never
    # reference a block that landed without the session they belong to.
    assert [name for name, _ in calls] == [
        "stage_memory",
        "record_content",
        "save_session",
    ]


def test_every_memory_write_of_a_turn_lands_in_one_patch(calls: list) -> None:
    engine = _Engine(
        [
            MemoryUpdated(key="a", value="1", scope="user"),
            MemoryUpdated(key="b", value="2", scope="user"),
            TurnDone(reason="end"),
        ]
    )
    _run(engine)
    (staged,) = [update for name, update in calls if name == "stage_memory"]
    assert [(v.key, v.value) for v in staged.variables] == [("a", "1"), ("b", "2")]


def test_a_memory_value_is_stored_as_text(calls: list) -> None:
    """The variable writer takes strings; anything else has to be rendered as one."""
    engine = _Engine(
        [MemoryUpdated(key="n", value=42, scope="user"), TurnDone(reason="end")]
    )
    _run(engine)
    (staged,) = [update for name, update in calls if name == "stage_memory"]
    assert staged.variables[0].value == "42"


def test_a_failed_turn_still_writes_what_it_produced(calls: list) -> None:
    """The learner said it and the model heard it; losing that would replay a finished exchange."""
    engine = _Engine(
        [
            MemoryUpdated(key="name", value="Ada", scope="user"),
            ErrorEvent(message="boom"),
        ]
    )
    events = _run(engine)
    assert [name for name, _ in calls] == [
        "stage_memory",
        "record_content",
        "save_session",
    ]
    assert events == []


def test_the_session_is_written_for_the_lesson_the_learner_is_on(calls: list) -> None:
    engine = _Engine([TurnDone(reason="end")])
    _run(engine)
    kwargs = next(kw for name, kw in calls if name == "save_session")
    assert kwargs["user_bid"] == USER
    assert kwargs["shifu_bid"] == SHIFU
    assert kwargs["outline_item_bid"] == OUTLINE


# --- what is worth keeping ---------------------------------------------------------------


def test_only_what_outlives_the_session_is_written_to_the_profile(calls: list) -> None:
    """`remember` defaults to session scope: a turn's working notes are not facts about a learner.

    Writing them through the profile would leak into preview, Ask and follow-up prompts and
    outlive the session that made sense of them.
    """
    engine = _Engine(
        [
            MemoryUpdated(key="current_exercise", value="fractions", scope="session"),
            MemoryUpdated(key="pace", value="slow", scope="user"),
            TurnDone(reason="end"),
        ]
    )
    _run(engine)
    (staged,) = [update for name, update in calls if name == "stage_memory"]
    assert [(v.key, v.value) for v in staged.variables] == [("pace", "slow")]


@pytest.mark.usefixtures("calls")
def test_a_turn_that_only_notes_something_for_itself_writes_no_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[str] = []
    monkeypatch.setattr(
        run_agent, "stage_memory", lambda *_a, **_k: recorded.append("staged")
    )
    engine = _Engine(
        [
            MemoryUpdated(key="note", value="x", scope="session"),
            TurnDone(reason="end"),
        ]
    )
    _run(engine)
    assert recorded == []


def test_what_the_course_knows_about_the_learner_reaches_a_new_session(
    monkeypatch: pytest.MonkeyPatch, calls: list
) -> None:
    """The engine has no memory store to read it for itself."""
    monkeypatch.setattr(
        run_agent, "load_memory", lambda *_a, **_k: _Memory({"pace": "slow"})
    )
    session = _Session()
    engine = _Engine([TurnDone(reason="end")], session=session)
    _run(engine)
    assert session.user_memory == {"pace": "slow"}
    assert calls


def test_a_resumed_session_sees_a_profile_edited_since_it_was_saved(
    monkeypatch: pytest.MonkeyPatch, calls: list
) -> None:
    """A stored session carries the snapshot taken when it was saved, which may be hours old."""
    stored = _Session(started=True)
    stored.user_memory = {"pace": "slow"}
    monkeypatch.setattr(run_agent, "load_agent_session", lambda *_a, **_k: stored)
    monkeypatch.setattr(
        run_agent, "load_memory", lambda *_a, **_k: _Memory({"pace": "fast"})
    )
    _run(_Engine([TurnDone(reason="end")], session=stored))
    assert stored.user_memory == {"pace": "fast"}
    assert calls


# --- what the browser actually sends -----------------------------------------------------
#
# Every lesson input arrives as a map: the study client normalises even a plain string to
# `{"input": ["..."]}` before sending it, so a path that only accepts `str` receives nothing.


@pytest.mark.parametrize(
    ("sent", "expected"),
    [
        pytest.param(
            {"input": ["hello"]}, ["hello"], id="free-text-as-the-client-sends-it"
        ),
        pytest.param({"feeling": ["Good"]}, ["Good"], id="a-named-answer"),
        pytest.param(
            {"topics": ["a", "b"]}, ["a", "b"], id="multi-select-keeps-every-choice"
        ),
        pytest.param({"input": []}, [], id="nothing-chosen"),
        pytest.param({"input": ["   "]}, [], id="whitespace-is-not-an-answer"),
        pytest.param({"a": "x"}, ["x"], id="an-unwrapped-value"),
        pytest.param("plain", ["plain"], id="a-bare-string-still-works"),
        pytest.param(None, [], id="nothing-sent"),
        pytest.param(42, [], id="not-an-input-shape"),
    ],
)
def test_the_values_a_learner_chose_survive_the_wire_format(
    sent: object, expected: list[str]
) -> None:
    assert run_agent.learner_values(sent) == expected


def test_a_selected_answer_reaches_the_pending_interaction(calls: list) -> None:
    """A clicked choice arrives in the shape the browser sends."""
    engine = _Engine(
        [TurnDone(reason="end")],
        session=_Session(started=True, pending=[object()]),
    )
    _run(engine, user_input={"feeling": ["Good"]})
    turn = engine.turns[0]
    assert turn.type == "interaction.response"
    assert turn.values == ["Good"]
    assert calls


def test_every_choice_of_a_multi_select_reaches_the_engine(calls: list) -> None:
    """Joining them into one string would leave the engine matching a value no option has."""
    engine = _Engine(
        [TurnDone(reason="end")],
        session=_Session(started=True, pending=[object()]),
    )
    _run(engine, user_input={"topics": ["a", "b"]})
    assert engine.turns[0].values == ["a", "b"]
    assert calls


# --- a lesson reset while the turn was running -------------------------------------------


def test_a_turn_whose_lesson_was_reset_while_it_ran_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, calls: list
) -> None:
    """A first turn holds no session row, so the reset had nothing to clear.

    Writing it afterwards would hand the learner back the conversation they had just cleared. The
    check runs before anything is staged, because staged-and-abandoned memory would be committed
    by whoever commits next.
    """
    monkeypatch.setattr(run_agent, "claim_for_writing", lambda **_k: None)
    engine = _Engine(
        [
            MemoryUpdated(key="name", value="Ada", scope="user"),
            TurnDone(reason="finished"),
        ]
    )

    class _App:
        import logging

        logger = logging.getLogger("test_run_agent")

    _run(engine, app=_App())

    assert calls == []


def test_the_block_a_turn_records_is_the_one_its_elements_reference(
    calls: list,
) -> None:
    """A different identifier here would leave every element of the turn orphaned."""
    engine = _Engine([ContentDelta(text="a"), TurnDone(reason="end")])
    events = _run(engine)

    staged = next(kw for name, kw in calls if name == "record_content")
    assert staged["generated_block_bid"] == events[0].generated_block_bid


# --- a turn is written once -------------------------------------------------------------


def test_an_error_followed_by_a_proper_ending_writes_the_turn_once(
    calls: list,
) -> None:
    """The engine does exactly this when a pending question gets a blank answer.

    It emits a retryable error, re-asks the question, and ends the turn properly. Treating the
    error as terminal would write the turn twice and stage its block twice under one identifier.
    """
    engine = _Engine(
        [
            ErrorEvent(message="needs an answer", retryable=True),
            InteractionRequest(
                id="i1",
                spec=InteractionSpec(
                    type="single", prompt="q", options=[Option(display="A")]
                ),
            ),
            TurnDone(reason="interaction"),
        ]
    )
    _run(engine)

    assert [name for name, _ in calls].count("record_content") == 1
    assert [name for name, _ in calls].count("save_session") == 1


def test_a_turn_that_only_fails_is_still_written(calls: list) -> None:
    """The engine returns after a bare error for failures it cannot continue past.

    What the turn produced still has to land, or the learner replays an exchange that happened.
    """
    engine = _Engine([ErrorEvent(message="boom")])
    _run(engine)

    assert [name for name, _ in calls].count("save_session") == 1


def test_a_finished_lesson_is_marked_where_progress_is_read(
    monkeypatch: pytest.MonkeyPatch, calls: list
) -> None:
    """Progress comes from the record's status, not from the session's own flag."""
    marked: list[object] = []
    monkeypatch.setattr(run_agent, "mark_lesson_finished", marked.append)

    session = _Session()
    session.finished = True
    engine = _Engine([TurnDone(reason="finished")], session=session)
    _run(engine)

    assert len(marked) == 1
    assert calls


def test_a_lesson_still_in_progress_is_not_marked_finished(
    monkeypatch: pytest.MonkeyPatch, calls: list
) -> None:
    marked: list[object] = []
    monkeypatch.setattr(run_agent, "mark_lesson_finished", marked.append)

    engine = _Engine([TurnDone(reason="end")])
    _run(engine)

    assert marked == []
    assert calls


# --- previewing writes no learner progress -----------------------------------------------


def test_previewing_a_lesson_writes_no_progress_for_the_learner(
    monkeypatch: pytest.MonkeyPatch, calls: list
) -> None:
    """The author is the same person as the learner, with the same lesson identifier.

    A progress record, a block or a completion written here would show up as a lesson they took.
    """
    resolved: list[bool] = []
    monkeypatch.setattr(
        run_agent, "_open_turn", lambda *_a, **_k: resolved.append(True) or PROGRESS
    )

    session = _Session()
    session.finished = True
    engine = _Engine([ContentDelta(text="draft"), TurnDone(reason="finished")], session)
    list(
        run_agent.run_agent_lesson(
            None,
            engine=engine,
            script=SCRIPT,
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_bid=OUTLINE,
            preview_mode=True,
            iter_turn=_drive,
        )
    )

    assert resolved == []
    assert [name for name, _ in calls] == ["save_session"]


def test_previewing_still_stores_its_own_session(calls: list) -> None:
    """Otherwise the preview would restart from the top on every turn."""
    engine = _Engine([TurnDone(reason="end")])
    list(
        run_agent.run_agent_lesson(
            None,
            engine=engine,
            script=SCRIPT,
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_bid=OUTLINE,
            preview_mode=True,
            iter_turn=_drive,
        )
    )

    kwargs = next(kw for name, kw in calls if name == "save_session")
    assert kwargs["preview_mode"] is True


# --- what the turn taught ----------------------------------------------------------------


def test_the_block_records_what_the_turn_taught(calls: list) -> None:
    """The 1.0 run reads this column for the assistant's side when it builds model context.

    It does not fall back to the element rows, so a course moving back off the allowlist would
    otherwise resume with its own questions answered by silence.
    """
    engine = _Engine(
        [
            ContentDelta(text="Hello "),
            ContentDelta(text="world."),
            TurnDone(reason="end"),
        ]
    )
    _run(engine)

    staged = next(kw for name, kw in calls if name == "record_content")
    assert staged["content"] == "Hello world."


# --- a turn that dies before it finishes -------------------------------------------------


def test_a_turn_that_fails_before_any_event_retires_its_block(
    monkeypatch: pytest.MonkeyPatch, calls: list
) -> None:
    """The block is reserved before the turn streams, so a turn that dies leaves it behind.

    An empty block is an empty assistant turn, which the 1.0 run would read as part of the
    conversation if the course moved back off the allowlist.
    """
    retired: list[str] = []
    monkeypatch.setattr(
        run_agent,
        "_retire_block",
        lambda _app, **kwargs: retired.append(kwargs["generated_block_bid"]),
    )

    def _explodes(_make_events: object, **_kwargs: object) -> object:
        message = "provider is down"
        raise RuntimeError(message)

    engine = _Engine([])
    with pytest.raises(RuntimeError):
        list(
            run_agent.run_agent_lesson(
                None,
                engine=engine,
                script=SCRIPT,
                user_bid=USER,
                shifu_bid=SHIFU,
                outline_bid=OUTLINE,
                iter_turn=_explodes,
            )
        )

    assert len(retired) == 1
    assert calls == []


@pytest.mark.usefixtures("calls")
def test_a_learner_closing_the_page_retires_the_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A disconnect is the common case, so GeneratorExit has to reach the cleanup too."""
    retired: list[str] = []
    monkeypatch.setattr(
        run_agent,
        "_retire_block",
        lambda _app, **kwargs: retired.append(kwargs["generated_block_bid"]),
    )

    engine = _Engine([ContentDelta(text="a"), TurnDone(reason="end")])
    stream = run_agent.run_agent_lesson(
        None,
        engine=engine,
        script=SCRIPT,
        user_bid=USER,
        shifu_bid=SHIFU,
        outline_bid=OUTLINE,
        iter_turn=_drive,
    )
    next(stream)
    stream.close()

    assert len(retired) == 1


def test_a_preview_has_no_block_to_retire(monkeypatch: pytest.MonkeyPatch) -> None:
    """A preview reserves nothing, so there is nothing to clean up."""
    retired: list[str] = []
    monkeypatch.setattr(
        run_agent, "_retire_block", lambda *_a, **_k: retired.append("called")
    )
    monkeypatch.setattr(run_agent, "load_agent_session", lambda *_a, **_k: None)
    monkeypatch.setattr(run_agent, "load_memory", lambda *_a, **_k: _Memory({}))

    def _explodes(_make_events: object, **_kwargs: object) -> object:
        message = "provider is down"
        raise RuntimeError(message)

    with pytest.raises(RuntimeError):
        list(
            run_agent.run_agent_lesson(
                None,
                engine=_Engine([]),
                script=SCRIPT,
                user_bid=USER,
                shifu_bid=SHIFU,
                outline_bid=OUTLINE,
                preview_mode=True,
                iter_turn=_explodes,
            )
        )

    assert retired == []


# --- listening is delivery, not a generation mode ------------------------------------------


@pytest.mark.usefixtures("calls")
def test_the_engine_is_never_put_into_its_own_listen_mode() -> None:
    """The whole approach rests on this: the engine teaches, the host speaks.

    Its listen mode keeps author-marked verbatim content only 64% of the time against 99% in
    ordinary mode, and drops images the author marked to keep. A session also stores the flag, so
    switching it on once would keep it on for every later read-mode turn.
    """
    engine = _Engine([TurnDone(reason="end")])
    _run(engine, listen=True)

    (call,) = engine.new_session_calls
    assert call["listen_mode"] is False


@pytest.mark.usefixtures("calls")
def test_a_lesson_whose_course_has_no_tts_is_taught_in_silence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A course with TTS switched off still teaches; the learner just hears nothing."""
    monkeypatch.setattr(
        "flaskr.service.learn.agent.listen.create_tts_processor",
        lambda *_a, **_k: None,
    )

    class _App:
        import logging

        logger = logging.getLogger("test_run_agent")

    engine = _Engine([ContentDelta(text="a"), TurnDone(reason="end")])
    events = _run(engine, listen=True, app=_App())

    assert [e.type for e in events] == [GeneratedType.CONTENT, GeneratedType.BREAK]


@pytest.mark.usefixtures("calls")
def test_a_sentence_is_shown_before_it_is_spoken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text first, then its audio -- the order the 1.0 lesson sends them in.

    The browser treats a passage marked speakable with no audio yet as buffering and waits rather
    than moving on. An audio event that arrives before the text it belongs to has no element to
    attach to, so it is dropped; the text then arrives marked speakable and its audio never comes,
    and the learner watches a spinner for the rest of the lesson.
    """

    class _Processor:
        def process_chunk(self, text: str) -> list[str]:
            return [f"audio:{text}"]

        def drain_ready_segments(self) -> list[str]:
            return []

        def finalize(self, *, commit: bool) -> list[str]:  # noqa: ARG002
            return []

    monkeypatch.setattr(
        "flaskr.service.learn.agent.listen.create_tts_processor",
        lambda *_a, **_k: _Processor(),
    )

    class _App:
        import logging

        logger = logging.getLogger("test_run_agent")

    engine = _Engine([ContentDelta(text="Hello."), TurnDone(reason="end")])
    events = _run(engine, listen=True, app=_App())

    kinds = [
        "audio" if isinstance(e, str) else e.type.value if e.type else "?"
        for e in events
    ]
    assert kinds.index(GeneratedType.CONTENT.value) < kinds.index("audio"), kinds


@pytest.mark.usefixtures("calls")
def test_audio_finished_while_the_lesson_wrote_on_is_collected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthesis runs behind the text, so finished segments have to be picked up as it goes.

    `process_chunk` can only emit what is ready at the instant it is called. Segments that finish
    afterwards sit in the processor until something drains them, and a lesson that only drained at
    the end would leave the learner silent through the whole turn.
    """
    drained: list[int] = []

    class _Processor:
        def process_chunk(self, _text: str) -> list[str]:
            return []

        def drain_ready_segments(self) -> list[str]:
            drained.append(1)
            return [f"audio:ready-{len(drained)}"]

        def finalize(self, *, commit: bool) -> list[str]:  # noqa: ARG002
            return []

    monkeypatch.setattr(
        "flaskr.service.learn.agent.listen.create_tts_processor",
        lambda *_a, **_k: _Processor(),
    )

    class _App:
        import logging

        logger = logging.getLogger("test_run_agent")

    engine = _Engine(
        [ContentDelta(text="a"), ContentDelta(text="b"), TurnDone(reason="end")]
    )
    events = _run(engine, listen=True, app=_App())

    assert drained, "audio that finished between chunks was never collected"
    assert "audio:ready-1" in [e for e in events if isinstance(e, str)]


@pytest.mark.usefixtures("calls")
def test_a_listening_lesson_is_sent_as_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each page of a listening lesson is its own element, so its audio can be bound to it.

    Audio binding keeps one page per element. A lesson sent as a single undivided element
    therefore keeps only one page's audio and leaves every other page marked speakable with
    nothing to play, which the browser waits on rather than skipping.
    """

    class _Processor:
        def process_chunk(self, _text: str) -> list[str]:
            return []

        def drain_ready_segments(self) -> list[str]:
            return []

        def finalize(self, *, commit: bool) -> list[str]:  # noqa: ARG002
            return []

    monkeypatch.setattr(
        "flaskr.service.learn.agent.listen.create_tts_processor",
        lambda *_a, **_k: _Processor(),
    )

    class _App:
        import logging

        logger = logging.getLogger("test_run_agent")

    engine = _Engine(
        [
            ContentDelta(text="First page.\n\n"),
            ContentDelta(text='<div class="card">shown</div>\n\n'),
            ContentDelta(text="Second page."),
            TurnDone(reason="end"),
        ]
    )
    events = _run(engine, listen=True, app=_App())

    pages = [
        part[2]
        for e in events
        if not isinstance(e, str)
        for part in (e.get_mdflow_stream_parts() or [])
    ]
    assert pages, "a listening lesson carried no page numbers at all"
    assert len(set(pages)) > 1, f"the whole lesson landed on one page: {pages}"
    assert pages == sorted(pages), f"pages went backwards: {pages}"

    said = "".join(
        str(e.content)
        for e in events
        if not isinstance(e, str) and e.type == GeneratedType.CONTENT
    )
    assert said == 'First page.\n\n<div class="card">shown</div>\n\nSecond page.'


@pytest.mark.usefixtures("calls")
def test_a_reading_lesson_is_not_paged() -> None:
    """Paging exists to bind audio. A lesson nobody is listening to keeps its current shape."""
    engine = _Engine(
        [ContentDelta(text="a\n\n<div>b</div>\n\nc"), TurnDone(reason="end")]
    )
    events = _run(engine, listen=False)

    assert not [
        part
        for e in events
        if not isinstance(e, str)
        for part in (e.get_mdflow_stream_parts() or [])
    ]


@pytest.mark.usefixtures("calls")
def test_no_lesson_text_escapes_a_listening_turn_unpaged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every piece of text in a listening turn carries a page, whichever path produced it.

    Paged and unpaged text cannot share a turn: the unpaged kind is gathered into one element
    holding the whole lesson, which sits beside the paged ones marked speakable, is never
    finalised, and is retired at the end without notifying the browser. The learner then waits on
    audio for it forever. One unpaged line does it -- the prompt beside a question was exactly
    that, and it is why this is asserted over the whole turn rather than per call site.
    """

    class _Processor:
        def process_chunk(self, _text: str) -> list[str]:
            return []

        def drain_ready_segments(self) -> list[str]:
            return []

        def finalize(self, *, commit: bool) -> list[str]:  # noqa: ARG002
            return []

    monkeypatch.setattr(
        "flaskr.service.learn.agent.listen.create_tts_processor",
        lambda *_a, **_k: _Processor(),
    )

    class _App:
        import logging

        logger = logging.getLogger("test_run_agent")

    engine = _Engine(
        [
            ContentDelta(text="Teaching.\n\n"),
            InteractionRequest(
                id="i1",
                spec=InteractionSpec(
                    type="single",
                    prompt="Which of these do you agree with?",
                    options=[Option(display="Yes"), Option(display="No")],
                    variable="v",
                ),
            ),
            TurnDone(reason="end"),
        ]
    )
    events = _run(engine, listen=True, app=_App())

    unpaged = [
        str(e.content)[:60]
        for e in events
        if not isinstance(e, str)
        and e.type == GeneratedType.CONTENT
        and not e.get_mdflow_stream_parts()
    ]
    assert not unpaged, f"text left a listening turn without a page: {unpaged}"


@pytest.mark.usefixtures("calls")
@pytest.mark.parametrize("listen", [False, True], ids=["reading", "listening"])
def test_verbatim_markers_never_reach_the_learner(
    monkeypatch: pytest.MonkeyPatch, listen: bool
) -> None:
    """The script's `===` markers come back in the engine's text; a 1.0 lesson never shows them.

    They were rendered, spoken and subtitled. What they wrap is the lesson and is kept.
    """

    class _Processor:
        def process_chunk(self, _text: str) -> list[str]:
            return []

        def drain_ready_segments(self) -> list[str]:
            return []

        def finalize(self, *, commit: bool) -> list[str]:  # noqa: ARG002
            return []

    monkeypatch.setattr(
        "flaskr.service.learn.agent.listen.create_tts_processor",
        lambda *_a, **_k: _Processor(),
    )

    class _App:
        import logging

        logger = logging.getLogger("test_run_agent")

    engine = _Engine(
        [
            ContentDelta(text="My goal: ==="),
            ContentDelta(text="=help a million people=="),
            ContentDelta(text="= and that is why.\n"),
            TurnDone(reason="end"),
        ]
    )
    events = _run(engine, listen=listen, app=_App())

    said = "".join(
        str(e.content)
        for e in events
        if not isinstance(e, str) and e.type == GeneratedType.CONTENT
    )
    assert "===" not in said
    assert "help a million people" in said
    assert said.startswith("My goal: help a million people and that is why.")


@pytest.mark.usefixtures("calls")
@pytest.mark.parametrize("listen", [False, True], ids=["reading", "listening"])
def test_the_closing_sentence_comes_before_the_question_it_leads_to(
    monkeypatch: pytest.MonkeyPatch, listen: bool
) -> None:
    """A lesson's last line usually has no newline after it, and the question follows it.

    Held until the end of the turn, that line was sent after the question's controls, so the last
    thing in the learner's history was text. The browser reads a history that does not end in a
    question as a lesson to continue, and asked the engine to go on with nothing -- which re-asked
    the question, and again on the next reload.
    """

    class _Processor:
        def process_chunk(self, _text: str) -> list[str]:
            return []

        def drain_ready_segments(self) -> list[str]:
            return []

        def finalize(self, *, commit: bool) -> list[str]:  # noqa: ARG002
            return []

    monkeypatch.setattr(
        "flaskr.service.learn.agent.listen.create_tts_processor",
        lambda *_a, **_k: _Processor(),
    )

    class _App:
        import logging

        logger = logging.getLogger("test_run_agent")

    engine = _Engine(
        [
            ContentDelta(text="Which of these do you agree with?"),
            InteractionRequest(
                id="i1",
                spec=InteractionSpec(
                    type="single",
                    prompt="",
                    options=[Option(display="Yes"), Option(display="No")],
                    variable="v",
                ),
            ),
            TurnDone(reason="end"),
        ]
    )
    events = [
        e for e in _run(engine, listen=listen, app=_App()) if not isinstance(e, str)
    ]

    kinds = [e.type for e in events]
    assert GeneratedType.CONTENT in kinds
    assert GeneratedType.INTERACTION in kinds
    question = kinds.index(GeneratedType.INTERACTION)
    assert question > max(
        i for i, k in enumerate(kinds) if k == GeneratedType.CONTENT
    ), "lesson text was sent after the question it leads to"
    # The text's block is closed before the question, as a 1.0 lesson closes it: history is
    # ordered by the moment of writing, and the question must be the last thing written.
    assert GeneratedType.BREAK in kinds[:question]


@pytest.mark.usefixtures("calls")
def test_an_author_previewing_in_listening_mode_hears_the_lesson(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A preview gets an identifier for its audio, unwritten, as the 1.0 run's preview does.

    The spoken track hangs each piece of audio off a progress record. A preview writes none, and
    an empty identifier left the author listening to silence with nothing to show for it.
    """
    spoken: list[str] = []

    class _Processor:
        def process_chunk(self, text: str) -> list[str]:
            spoken.append(text)
            return []

        def drain_ready_segments(self) -> list[str]:
            return []

        def finalize(self, *, commit: bool) -> list[str]:  # noqa: ARG002
            return []

    asked: dict = {}

    def _factory(_app: object, **kwargs: object) -> object:
        asked.update(kwargs)
        return _Processor()

    monkeypatch.setattr(
        "flaskr.service.learn.agent.listen.create_tts_processor", _factory
    )
    monkeypatch.setattr(run_agent, "generate_id", lambda _app: "preview-progress")

    class _App:
        import logging

        logger = logging.getLogger("test_run_agent")

    engine = _Engine([ContentDelta(text="Teaching.\n"), TurnDone(reason="end")])
    list(
        run_agent.run_agent_lesson(
            _App(),
            engine=engine,
            script=SCRIPT,
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_bid=OUTLINE,
            preview_mode=True,
            listen=True,
            iter_turn=_drive,
        )
    )

    assert spoken, "the preview was silent"
    assert asked["progress_record_bid"] == "preview-progress"


@pytest.mark.usefixtures("calls")
@pytest.mark.parametrize(
    ("preview_mode", "expected"),
    [
        pytest.param(True, BILL_USAGE_SCENE_PREVIEW, id="preview"),
        pytest.param(False, None, id="learner"),
    ],
)
def test_a_preview_s_audio_is_not_billed_as_a_lesson_taken(
    monkeypatch: pytest.MonkeyPatch, preview_mode: bool, expected: object
) -> None:
    """An author previewing is not a learner taking the course.

    Counting their listening as production overstates what the course cost to teach, in the
    billing record and in every report drawn from it.
    """
    asked: dict = {}

    class _Processor:
        def process_chunk(self, _text: str) -> list[str]:
            return []

        def drain_ready_segments(self) -> list[str]:
            return []

        def finalize(self, *, commit: bool) -> list[str]:  # noqa: ARG002
            return []

    def _factory(_app: object, **kwargs: object) -> object:
        asked.update(kwargs)
        return _Processor()

    monkeypatch.setattr(
        "flaskr.service.learn.agent.listen.create_tts_processor", _factory
    )
    monkeypatch.setattr(run_agent, "generate_id", lambda _app: "preview-progress")
    monkeypatch.setattr(run_agent, "_open_turn", lambda *_a, **_k: PROGRESS)

    class _App:
        import logging

        logger = logging.getLogger("test_run_agent")

    engine = _Engine([ContentDelta(text="Teaching.\n"), TurnDone(reason="end")])
    list(
        run_agent.run_agent_lesson(
            _App(),
            engine=engine,
            script=SCRIPT,
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_bid=OUTLINE,
            preview_mode=preview_mode,
            listen=True,
            iter_turn=_drive,
        )
    )

    assert asked["usage_scene"] == expected


# --- a question asked twice ---------------------------------------------------------------


def _contents(events: list) -> list[str]:
    return [str(e.content) for e in events if e.type == GeneratedType.CONTENT]


@pytest.mark.usefixtures("calls")
def test_a_question_the_lesson_just_asked_is_not_asked_again() -> None:
    """The model writes the question into the lesson and passes it to `interact` as well.

    Both reached the learner, one after the other: the narration ended on the question and the
    same sentence appeared again on its own line above the buttons.
    """
    engine = _Engine(
        [
            ContentDelta(text="第一个问题：你会编程吗？"),
            InteractionRequest(
                id="q1",
                spec=InteractionSpec(
                    type="single",
                    prompt="你会编程吗？",
                    options=[Option(display="会", value="会")],
                ),
            ),
            TurnDone(reason="interaction"),
        ]
    )
    events = _run(engine)
    assert _contents(events) == ["第一个问题：你会编程吗？"]
    assert any(e.type == GeneratedType.INTERACTION for e in events)


@pytest.mark.usefixtures("calls")
def test_a_question_the_lesson_did_not_ask_still_reaches_the_learner() -> None:
    """Often the prompt is the only place the model asks; suppressing it leaves nothing to answer."""
    engine = _Engine(
        [
            ContentDelta(text="一人公司的第一课讲完了。"),
            InteractionRequest(
                id="q1",
                spec=InteractionSpec(
                    type="single",
                    prompt="你会编程吗？",
                    options=[Option(display="会", value="会")],
                ),
            ),
            TurnDone(reason="interaction"),
        ]
    )
    events = _run(engine)
    assert _contents(events) == ["一人公司的第一课讲完了。", "你会编程吗？"]


@pytest.mark.usefixtures("calls")
def test_the_same_words_earlier_in_the_turn_do_not_suppress_the_question() -> None:
    """A repetition is what is dropped, not a phrase the lesson happened to use before.

    The check looks only at the end of the narration: matching anywhere would silence a question
    whose words the lesson used a paragraph ago, and the learner would face bare buttons.
    """
    engine = _Engine(
        [
            ContentDelta(text="你会编程吗？这个问题我们稍后再谈。"),
            ContentDelta(text="先说说我自己的经历，我做过很多年的研发工作，" * 6),
            InteractionRequest(
                id="q1",
                spec=InteractionSpec(
                    type="single",
                    prompt="你会编程吗？",
                    options=[Option(display="会", value="会")],
                ),
            ),
            TurnDone(reason="interaction"),
        ]
    )
    events = _run(engine)
    assert _contents(events)[-1] == "你会编程吗？"


# --- telling the outline the lesson is over -----------------------------------------------


class _LoggingApp:
    """Just enough Flask for a path that only logs: the warning must not replace the failure."""

    def __init__(self) -> None:
        """Collect what was logged instead of writing it anywhere."""
        self.warnings: list[str] = []
        self.logger = self

    def warning(self, message: str, *args: object, **_kwargs: object) -> None:
        """Record a warning the way the app's logger would emit one."""
        self.warnings.append(message % args if args else message)

    def info(self, message: str, *args: object, **_kwargs: object) -> None:
        """Swallow an informational line, which no test asserts on."""


def _finished_engine() -> _Engine:
    session = _Session()
    session.finished = True
    return _Engine([TurnDone(reason="finished")], session=session)


def _outline_update(bid: str, status: object, *, has_children: bool = False) -> object:
    from flaskr.service.learn.learn_dtos import OutlineItemUpdateDTO

    return OutlineItemUpdateDTO(
        outline_bid=bid, title=bid, status=status, has_children=has_children
    )


@pytest.mark.usefixtures("calls")
def test_a_finished_lesson_tells_the_outline_before_the_stream_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The browser stops reading on the terminal event, so anything after it is never seen.

    Sent at all, these are what ticks the lesson off, ends its chapter and hands the learner on;
    without them a finished lesson still called itself unfinished and the page kept asking for
    more of it.
    """
    from flaskr.service.learn.learn_dtos import LearnStatus

    updates = [
        _outline_update("outline-bid", LearnStatus.COMPLETED),
        _outline_update("next-lesson", LearnStatus.IN_PROGRESS),
    ]
    monkeypatch.setattr(
        run_agent, "resolve_outline_progression", lambda *_a, **_k: updates
    )
    events = _run(_finished_engine())
    types = [e.type for e in events]
    assert types == [GeneratedType.OUTLINE_ITEM_UPDATE] * 2 + [GeneratedType.DONE]
    assert [e.outline_bid for e in events[:2]] == ["outline-bid", "next-lesson"]


@pytest.mark.usefixtures("calls")
def test_a_finished_lesson_records_what_it_changed_in_the_outline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A learner who comes back tomorrow is told by the database, not by the stream."""
    from flaskr.service.learn.learn_dtos import LearnStatus

    updates = [_outline_update("outline-bid", LearnStatus.COMPLETED)]
    monkeypatch.setattr(
        run_agent, "resolve_outline_progression", lambda *_a, **_k: updates
    )
    applied: list[object] = []
    monkeypatch.setattr(
        run_agent,
        "apply_outline_progression",
        lambda _app, **kwargs: applied.append(kwargs["updates"]),
    )
    _run(_finished_engine())
    assert applied == [updates]


@pytest.mark.usefixtures("calls")
def test_a_preview_does_not_move_the_author_through_their_own_course(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The author is looking at a lesson, not taking one."""
    asked: list[object] = []
    monkeypatch.setattr(
        run_agent,
        "resolve_outline_progression",
        lambda *_a, **_k: asked.append(1) or [],
    )
    events = list(
        run_agent.run_agent_lesson(
            None,
            engine=_finished_engine(),
            script=SCRIPT,
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_bid=OUTLINE,
            user_input=None,
            listen=False,
            preview_mode=True,
            iter_turn=_drive,
        )
    )
    assert asked == []
    assert [e.type for e in events] == [GeneratedType.DONE]


_UNAVAILABLE = "outline unavailable"


@pytest.mark.usefixtures("calls")
def test_an_outline_that_cannot_be_read_does_not_cost_the_learner_the_lesson(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """They finished it and the turn is saved; a missing tick is the cheaper loss."""

    def _boom(*_a: object, **_k: object) -> list:
        raise RuntimeError(_UNAVAILABLE)

    monkeypatch.setattr(run_agent, "resolve_outline_progression", _boom)
    events = _run(_finished_engine(), app=_LoggingApp())
    assert [e.type for e in events] == [GeneratedType.DONE]


@pytest.mark.usefixtures("calls")
def test_a_turn_a_reset_discarded_does_not_advance_the_outline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The learner asked to take the lesson again; the turn in flight must not undo that.

    A reset clears the progress the turn started from, and the turn is dropped. Advancing the
    outline anyway would write the completion straight back and carry the learner past the lesson
    they had just asked to retake.
    """
    monkeypatch.setattr(run_agent, "claim_for_writing", lambda **_k: None)
    asked: list[object] = []
    monkeypatch.setattr(
        run_agent,
        "resolve_outline_progression",
        lambda *_a, **_k: asked.append(1) or [],
    )
    events = _run(_finished_engine(), app=_LoggingApp())
    assert asked == []
    assert [e.type for e in events] == [GeneratedType.DONE]
