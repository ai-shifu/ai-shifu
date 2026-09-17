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

USER = "user-bid"
SHIFU = "shifu-bid"
OUTLINE = "outline-bid"
SCRIPT = "# Lesson\n\nSome content."


class _Session:
    """Stands in for an engine session: only the fields the host reads."""

    def __init__(self, *, started: bool = False, pending: list | None = None) -> None:
        self.started = started
        self.pending = pending or []
        self.user_memory: dict = {}


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
        recorded.append(("save_session", kwargs))

    monkeypatch.setattr(run_agent, "stage_memory", _stage)
    monkeypatch.setattr(run_agent, "save_agent_session", _save)
    monkeypatch.setattr(run_agent, "load_agent_session", lambda *_a, **_k: None)
    monkeypatch.setattr(run_agent, "load_memory", lambda *_a, **_k: _Memory({}))
    return recorded


def _run(engine: _Engine, *, user_input: str | None = None, app: object = None) -> list:
    return list(
        run_agent.run_agent_lesson(
            app,
            engine=engine,
            script=SCRIPT,
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_bid=OUTLINE,
            user_input=user_input,
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
    assert [e.type for e in events] == [
        GeneratedType.CONTENT,
        GeneratedType.CONTENT,
        GeneratedType.BREAK,
    ]
    assert [e.content for e in events[:2]] == ["before", "pick"]


# --- when things are written -------------------------------------------------------------


def test_the_session_is_written_before_the_turn_says_it_is_over(calls: list) -> None:
    """Otherwise the learner is told a turn succeeded that the next request will not find."""
    engine = _Engine([ContentDelta(text="a"), TurnDone(reason="finished")])
    events = _run(engine)
    assert [name for name, _ in calls] == ["save_session"]
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
    assert [name for name, _ in calls] == ["stage_memory", "save_session"]


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
    assert [name for name, _ in calls] == ["stage_memory", "save_session"]
    assert events == []


def test_the_session_is_written_for_the_lesson_the_learner_is_on(calls: list) -> None:
    engine = _Engine([TurnDone(reason="end")])
    _run(engine)
    (_name, kwargs) = calls[0]
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
