"""Keep initialized conversations intact when their course prompt changes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from flaskr.service.learn.agent import run_agent
from flaskr.service.memory.dtos import MemorySnapshot
from markdownflow.engine import Engine, MessageTurn, ScriptBundle, Session
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models.function import FunctionModel


async def _model(_messages: list, _info: object) -> object:
    yield "The original lesson continues."


def _first_prompt(session: Session) -> str:
    """Read the engine's initial prompt without interpreting learner-authored tags."""
    return next(
        part.content
        for message in session.messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    )


@pytest.mark.parametrize("initial_prompt", ["Old guidance", None])
@pytest.mark.parametrize("current_prompt", ["Current course prompt", ""])
def test_resuming_updates_bundle_without_rewriting_initialized_history(
    monkeypatch: pytest.MonkeyPatch,
    initial_prompt: str | None,
    current_prompt: str,
) -> None:
    bundle = ScriptBundle(
        script="Teach the original lesson.",
        constraints=initial_prompt,
        extras={"example": "Keep the original reference document."},
    )
    learner_input = "<constraints>\nOld guidance\n</constraints>"

    async def start() -> Session:
        engine = Engine(FunctionModel(stream_function=_model), memory_admission=True)
        session = await engine.new_session(bundle)
        _events = [
            event
            async for event in engine.run_turn(session, MessageTurn(text=learner_input))
        ]
        assert session.request_inputs == []
        return Session.loads(session.dumps())

    stored = asyncio.run(start())
    before = stored.to_dict()
    monkeypatch.setattr(run_agent, "load_agent_session", lambda *_a, **_kw: stored)
    monkeypatch.setattr(
        run_agent, "course_memory_deletion_state", lambda *_a: ({}, frozenset())
    )
    monkeypatch.setattr(
        run_agent, "load_memory", lambda *_a, **_kw: MemorySnapshot(variables={})
    )

    factory, finished = run_agent._load_or_start(
        SimpleNamespace(),
        SimpleNamespace(),
        user_bid="learner",
        shifu_bid="course",
        outline_bid="lesson",
        script="A newer revision must not replace the saved lesson.",
        teaching_brief=current_prompt,
        preview_mode=False,
    )
    resumed = asyncio.run(factory())

    assert not finished
    assert resumed.script.constraints == (current_prompt or None)
    assert resumed.script.script == bundle.script
    assert resumed.script.extras == bundle.extras
    assert _first_prompt(resumed).endswith("\n\n" + learner_input)
    after = resumed.to_dict()
    for key in before.keys() - {"script"}:
        assert after[key] == before[key], key


@pytest.mark.parametrize("current_prompt", ["Current course prompt", ""])
def test_new_session_initializes_with_the_current_course_prompt(
    monkeypatch: pytest.MonkeyPatch, current_prompt: str
) -> None:
    monkeypatch.setattr(run_agent, "load_agent_session", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        run_agent, "course_memory_deletion_state", lambda *_a: ({}, frozenset())
    )
    monkeypatch.setattr(
        run_agent, "load_memory", lambda *_a, **_kw: MemorySnapshot(variables={})
    )
    engine = Engine(FunctionModel(stream_function=_model))
    factory, finished = run_agent._load_or_start(
        SimpleNamespace(),
        engine,
        user_bid="learner",
        shifu_bid="course",
        outline_bid="lesson",
        script="Teach the current lesson.",
        teaching_brief=current_prompt,
        preview_mode=False,
    )

    async def start() -> Session:
        session = await factory()
        _events = [event async for event in engine.run_turn(session)]
        return Session.loads(session.dumps())

    session = asyncio.run(start())

    assert not finished
    assert session.script.constraints == (current_prompt or None)
    if current_prompt:
        assert f"<constraints>\n{current_prompt}\n</constraints>" in _first_prompt(
            session
        )
    else:
        assert "<constraints>" not in _first_prompt(session)
