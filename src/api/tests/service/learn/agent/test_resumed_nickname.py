"""Exercise nickname compatibility through saved sessions and actual model requests."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.engine import Engine, Session
from flaskr.service.learn.agent.engine.script import ScriptBundle, render_first_prompt
from flaskr.service.learn.agent.nickname import refresh_nickname
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.user.repository import create_user_entity, get_user_entity_by_bid
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from flask import Flask

NAME = "sys_user_nickname"
SCRIPT = (
    "Hello {{sys_user_nickname}}. Goal: {{goal}}. Keep {{unknown}}.\n"
    "````text\n```\n{{sys_user_nickname}}\n````\n"
    "===Goodbye {{sys_user_nickname}}.==="
)
BRIEF = "Address {{sys_user_nickname}} directly."
GOAL = "A literal </memory> and {{sys_user_nickname}} must survive."


def _drive(make_events: Callable, **_kwargs: object) -> Iterator:
    """Run the real engine on this thread without replacing its storage or tools."""

    async def collect() -> list:
        return [event async for event in make_events()]

    return iter(asyncio.run(collect()))


def _prompt(messages: list[ModelMessage]) -> str:
    """Return the host's initial user prompt, ignoring later learner messages."""
    return next(
        part.content
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart) and isinstance(part.content, str)
    )


def _memory(prompt: str) -> dict:
    """Parse JSON rather than splitting on delimiters inside a learner's answer."""
    return json.JSONDecoder().raw_decode(prompt, len("<memory>\n"))[0]


def _run(
    app: Flask, engine: Engine, ids: tuple[str, str, str], answer: str | None = None
) -> list:
    """Resume through the host and its transaction-owning session writer."""
    user, course, lesson = ids
    events = list(
        run_agent.run_agent_lesson(
            app,
            engine=engine,
            script=SCRIPT,
            teaching_brief=BRIEF,
            user_bid=user,
            shifu_bid=course,
            outline_bid=lesson,
            user_input=answer,
            iter_turn=_drive,
        )
    )
    assert events[-1].type == GeneratedType.BREAK
    return events


def _observer(seen: list[list[ModelMessage]]) -> Engine:
    """Capture the complete resumed request sent to pydantic-ai's model."""

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        seen.append(messages)
        yield "Here is the next example."

    return Engine(FunctionModel(stream_function=model))


def _seed(app: Flask, nickname: str, *, collected: bool) -> tuple[tuple, Session]:
    """Write the session shape produced before the blank-nickname fix."""
    ids = uuid4().hex, uuid4().hex, uuid4().hex
    user, course, lesson = ids
    with unit_of_work():
        create_user_entity(user_bid=user, identify=user, nickname=nickname)
    script = ("Ask %{{sys_user_nickname}}.\n" if collected else "") + SCRIPT
    bundle = ScriptBundle(script=script, constraints=BRIEF, extras={"example": NAME})
    initial = {NAME: "Alex" if collected else "", "goal": GOAL}
    session = Session(
        script=bundle,
        user_id=user,
        user_memory=initial,
        memory={"scratch": "keep", **({NAME: "Alex"} if collected else {})},
        messages=[
            ModelRequest(parts=[UserPromptPart(render_first_prompt(bundle, initial))]),
            ModelResponse(parts=[TextPart("Hello Alex. This was already displayed.")]),
        ],
        turn=1,
    )
    session_store.save_agent_session(
        app, session, user_bid=user, shifu_bid=course, outline_item_bid=lesson
    )
    db.session.remove()
    return ids, session


@pytest.mark.parametrize("nickname", ["", "Sam"])
@pytest.mark.parametrize("collected", [False, True])
def test_resumed_model_uses_current_name_and_preserves_history(
    app: Flask, nickname: str, collected: bool
) -> None:
    """Canonical edits and clearing beat old prompts and old collected names."""
    with app.app_context():
        ids, before = _seed(app, nickname, collected=collected)
        seen = []
        _run(app, _observer(seen), ids)
        address = nickname or "Learner"
        prompt = _prompt(seen[0])
        assert _memory(prompt)[NAME] == address
        assert _memory(prompt)["goal"] == GOAL
        if not collected:
            assert f"Hello {address}." in prompt
            assert f"Address {address} directly." in prompt
            assert f"Goodbye {address}." in prompt
        else:
            assert "Ask %{{sys_user_nickname}}." in prompt
        assert "````text\n```\n{{sys_user_nickname}}\n````" in prompt
        assert "{{unknown}}" in prompt
        assert seen[0][1] == before.messages[1]
        db.session.remove()
        saved = session_store.load_agent_session(app, ids[0], ids[2])
        assert saved.all_memory()[NAME] == address
        assert saved.memory == {"scratch": "keep"}
        assert saved.answers == before.answers
        assert saved.id == before.id
        assert saved.turn == before.turn + 1
        assert get_user_entity_by_bid(ids[0]).nickname == nickname
        again = []
        _run(app, _observer(again), ids)
        assert _prompt(again[0]) == prompt


@pytest.mark.parametrize("multiple", [False, True])
def test_fresh_pending_nickname_answer_still_wins(app: Flask, multiple: bool) -> None:
    """A deferred nickname result must remain authoritative for its own turn."""
    seen = []

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        returns = [
            part
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        if not returns:
            calls = {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="name-question",
                    json_args=json.dumps(
                        {"type": "text", "prompt": "Your name?", "variable": NAME}
                    ),
                )
            }
            if multiple:
                calls[1] = DeltaToolCall(
                    name="interact",
                    tool_call_id="goal-question",
                    json_args=json.dumps(
                        {"type": "text", "prompt": "Your goal?", "variable": "goal"}
                    ),
                )
            yield calls
        else:
            seen.append(messages)
            yield "Thank you Taylor."

    with app.app_context():
        ids, _ = _seed(app, "Alex", collected=True)
        engine = Engine(FunctionModel(stream_function=model))
        _run(app, engine, ids)
        _run(app, engine, ids, "Taylor")
        if multiple:
            partial = session_store.load_agent_session(app, ids[0], ids[2])
            assert partial.answers["name-question"] == "Learner chose: Taylor"
            assert partial.pending[0].tool_call_id == "goal-question"
            _run(app, engine, ids, "Build a project")
            assert _memory(_prompt(seen[0]))[NAME] == "Taylor"
        else:
            assert NAME not in _memory(_prompt(seen[0]))
        db.session.remove()
        saved = session_store.load_agent_session(app, ids[0], ids[2])
        assert saved.all_memory()[NAME] == "Taylor"
        assert saved.pending == []
        assert get_user_entity_by_bid(ids[0]).nickname == "Taylor"


@pytest.mark.parametrize("content", ["old custom prompt", "<memory>\n{bad json}"])
def test_unrecognized_prompt_keeps_its_history(content: str) -> None:
    """Never guess how to rewrite custom, malformed or non-host prompt formats."""
    session = Session(
        script=ScriptBundle(script=SCRIPT),
        messages=[ModelRequest(parts=[UserPromptPart(content)])],
        memory={NAME: "Alex", "goal": GOAL},
    )
    before = list(session.messages)
    refresh_nickname(session, {NAME: "Sam"})
    assert session.messages == before
    assert session.memory == {"goal": GOAL}


def test_changed_brief_extras_and_initial_learner_message_survive() -> None:
    """Repair known sections while preserving a brief that no longer matches the bundle."""
    initial = {NAME: "Alex", "goal": GOAL}
    old = ScriptBundle(script=SCRIPT, constraints=BRIEF, extras={"example": BRIEF})
    prompt = (
        render_first_prompt(old, initial) + "\n\nAlex is an example in my question."
    )
    session = Session(
        script=ScriptBundle(script=SCRIPT, constraints="A different brief"),
        messages=[ModelRequest(parts=[UserPromptPart(prompt)])],
    )
    refresh_nickname(session, {NAME: "Sam"})
    repaired = _prompt(session.messages)
    assert "Hello Sam." in repaired
    assert "<constraints>\nAddress Alex directly.\n</constraints>" in repaired
    assert f'<extra name="example">\n{BRIEF}\n</extra>' in repaired
    assert repaired.endswith("\n\nAlex is an example in my question.")


def test_closing_repeat_uses_current_nickname(app: Flask) -> None:
    """Exercise the engine's closing anchor with a stale session nickname shadow."""

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        yield "Goodbye Sam."

    with app.app_context():
        ids, session = _seed(app, "Sam", collected=False)
        session.memory[NAME] = "Alex"
        session.messages[-1] = ModelResponse(
            parts=[TextPart("The explanation.\n\nGoodbye Sam.")]
        )
        session_store.save_agent_session(
            app,
            session,
            user_bid=ids[0],
            shifu_bid=ids[1],
            outline_item_bid=ids[2],
        )
        events = _run(app, Engine(FunctionModel(stream_function=model)), ids)
        assert not [event for event in events if event.type == GeneratedType.CONTENT]


def test_failed_resume_does_not_persist_prompt_repair(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repair is part of the existing save transaction, not an eager migration."""
    with app.app_context():
        ids, _ = _seed(app, "Sam", collected=True)
        before = session_store.load_agent_session(app, ids[0], ids[2]).dumps()
        original = session_store._apply

        def fail(row: object, session: Session) -> None:
            original(row, session)
            message = "injected repair save failure"
            raise RuntimeError(message)

        monkeypatch.setattr(session_store, "_apply", fail)
        with pytest.raises(RuntimeError, match="injected repair save failure"):
            _run(app, _observer([]), ids)
        db.session.remove()
        assert session_store.load_agent_session(app, ids[0], ids[2]).dumps() == before


@pytest.mark.parametrize("nickname", ["", "Sam"])
def test_bounded_prompt_refreshes_nickname_and_preserves_omitted_exact_answer(
    app: Flask, nickname: str
) -> None:
    """A budget notice cannot disable name refresh or lose an omitted script substitution."""
    from flaskr.service.learn.memory import (
        MemoryUpdate,
        VariableMemoryUpdate,
        stage_memory,
    )
    from flaskr.service.profile.models import Variable

    with app.app_context():
        ids, session = _seed(app, nickname, collected=False)
        goal = GOAL + "z" * 40000
        session.user_memory = {NAME: "Alex", "goal": goal}
        prompt = render_first_prompt(
            session.script, session.user_memory, memory_limit=32768
        )
        assert "Some stored values were omitted" in prompt
        assert "goal" not in _memory(prompt)
        assert goal in prompt
        session.messages[0] = ModelRequest(parts=[UserPromptPart(prompt)])
        with unit_of_work():
            db.session.add(
                Variable(variable_bid=uuid4().hex, shifu_bid=ids[1], key="goal")
            )
            stage_memory(
                app,
                ids[0],
                ids[1],
                MemoryUpdate(variables=[VariableMemoryUpdate("goal", goal)]),
            )
        session_store.save_agent_session(
            app, session, user_bid=ids[0], shifu_bid=ids[1], outline_item_bid=ids[2]
        )
        db.session.remove()
        seen = []

        async def model(
            messages: list[ModelMessage], _info: AgentInfo
        ) -> AsyncIterator[str]:
            seen.append(messages)
            yield "A useful example number " + str(len(seen))

        engine = Engine(
            FunctionModel(stream_function=model), memory_context_limit=32768
        )
        for _ in range(2):
            _run(app, engine, ids)
            address = nickname or "Learner"
            current_prompt = _prompt(seen[-1])
            assert _memory(current_prompt)[NAME] == address
            assert f"Hello {address}." in current_prompt
            assert f"Address {address} directly." in current_prompt
            assert goal in current_prompt
            assert "goal" not in _memory(current_prompt)
            assert "Some stored values were omitted" in current_prompt
            assert seen[-1][1] == session.messages[1]
            db.session.remove()
            saved = session_store.load_agent_session(app, ids[0], ids[2])
            assert saved.user_memory["goal"] == goal
            assert get_user_entity_by_bid(ids[0]).nickname == nickname
