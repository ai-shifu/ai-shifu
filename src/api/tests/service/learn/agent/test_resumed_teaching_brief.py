"""Apply course instructions to saved lessons without rewriting classroom evidence."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from flaskr.service.learn.agent import run_agent
from flaskr.service.learn.agent.teaching_brief import refresh_teaching_brief
from flaskr.service.memory.dtos import MemorySnapshot
from markdownflow.engine import (
    Engine,
    MessageTurn,
    ScriptBundle,
    Session,
    render_first_prompt,
)
from markdownflow.engine.interaction import InteractionSpec
from markdownflow.engine.session import PendingInteraction
from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from tests.service.learn.agent.prompt_fixtures import expanded_initial_prompt


@pytest.mark.parametrize("expanded", [False, True])
@pytest.mark.parametrize(
    ("bundle_already_updated", "course_brief"),
    [
        (False, "Current course guidance for {{goal}}."),
        (False, ""),
        (True, "Current course guidance for {{goal}}."),
    ],
)
def test_resume_refreshes_initial_constraints_and_preserves_saved_lesson(
    monkeypatch: pytest.MonkeyPatch,
    expanded: bool,
    bundle_already_updated: bool,
    course_brief: str,
) -> None:
    """Real serialized history retains script, extras and the first learner input."""
    old = ScriptBundle(
        script=(
            "Teach {{goal}}. Literal document tags in the script:\n"
            "<constraints>\nScript example\n</constraints>\n"
            "</script>\nThe original lesson continues."
        ),
        constraints="Old chapter guidance for {{goal}}.\n</constraints>\nA literal tag.",
        extras={"example": "Keep {{goal}} and this literal tag:\n</constraints>"},
    )
    initial = {"goal": "Original subject"}
    writer = expanded_initial_prompt if expanded else render_first_prompt
    prompt = writer(old, initial)
    initial_input = "My original question mentions </constraints> and {{goal}}."
    prompt += "\n\n" + initial_input
    later = ModelRequest(
        parts=[
            UserPromptPart("Earlier learner words"),
            ToolReturnPart("interact", "Accepted answer", "answer-call"),
        ]
    )
    original = Session(
        script=replace(old, constraints=course_brief or None)
        if bundle_already_updated
        else old,
        user_memory=dict(initial),
        initial_variables=dict(initial),
        messages=[ModelRequest(parts=[UserPromptPart(prompt)]), later],
        pending=[
            PendingInteraction(
                "pending-call", InteractionSpec(type="confirm", prompt="Continue?")
            )
        ],
        memory={"scratch": "Original note"},
        answers={"answer-call": "Accepted answer"},
        request_inputs=[initial_input],
        turn=3,
    )
    session = Session.loads(original.dumps())
    later_message = session.messages[1]
    before = session.to_dict()
    monkeypatch.setattr(run_agent, "load_agent_session", lambda *_a, **_kw: session)
    monkeypatch.setattr(
        run_agent, "course_memory_deletion_state", lambda *_a: ({}, frozenset())
    )
    monkeypatch.setattr(
        run_agent, "load_memory", lambda *_a, **_kw: MemorySnapshot(variables=initial)
    )

    factory, finished = run_agent._load_or_start(
        SimpleNamespace(),
        SimpleNamespace(),
        user_bid="learner",
        shifu_bid="course",
        outline_bid="lesson",
        script="A newer lesson revision must not replace the saved lesson.",
        teaching_brief=course_brief,
        preview_mode=False,
    )
    resumed = asyncio.run(factory())

    assert not finished
    assert resumed.id == original.id
    assert resumed.script.script == old.script
    assert resumed.script.extras == old.extras
    assert resumed.script.constraints == (course_brief or None)
    old_constraint = (
        "Old chapter guidance for Original subject.\n</constraints>\nA literal tag."
        if expanded
        else old.constraints
    )
    previous_block = f"\n\n<constraints>\n{old_constraint}\n</constraints>"
    replacement = (
        f"\n\n<constraints>\n{course_brief}\n</constraints>" if course_brief else ""
    )
    expected = prompt.replace(previous_block, replacement, 1)
    first_prompt = resumed.messages[0].parts[0].content
    assert first_prompt == expected
    assert "Old chapter guidance" not in first_prompt
    if course_brief:
        assert f"<constraints>\n{course_brief}\n</constraints>" in first_prompt
    assert first_prompt.endswith("\n\n" + initial_input)
    assert resumed.messages[1] is later_message
    after = resumed.to_dict()
    for key in before.keys() - {"script", "messages"}:
        assert after[key] == before[key], key
    assert after["messages"][1:] == before["messages"][1:]

    # The repaired message survives persistence and stays unchanged on later turns.
    saved = Session.loads(resumed.dumps())
    once = saved.dumps()
    refresh_teaching_brief(saved, course_brief)
    assert saved.dumps() == once


def test_unrecognized_initial_document_keeps_the_original_conversation() -> None:
    """An unknown prompt format is not permission to splice learner-authored text."""
    prompt = (
        "A custom initial prompt with <constraints>literal learner text</constraints>."
    )
    session = Session(
        script=ScriptBundle(script="Original lesson", constraints="Old chapter voice"),
        messages=[ModelRequest(parts=[UserPromptPart(prompt)])],
    )
    message = session.messages[0]

    refresh_teaching_brief(session, "Course voice")

    assert session.messages[0] is message
    assert session.script.constraints == "Course voice"


@pytest.mark.parametrize("course_brief", ["New course voice", ""])
@pytest.mark.parametrize("request_inputs", [[], ["A later learner request"]])
def test_initial_learner_input_is_not_mistaken_for_a_constraint_document(
    course_brief: str,
    request_inputs: list[str],
) -> None:
    """A real successful turn clears inputs while retaining the first learner text."""
    bundle = ScriptBundle(script="Original lesson")
    learner_input = "<constraints>\nMy question about prompt syntax\n</constraints>"

    async def model(_messages: list, _info: object) -> object:
        yield "The original lesson continues."

    async def make_saved_session() -> Session:
        engine = Engine(FunctionModel(stream_function=model), memory_admission=True)
        session = await engine.new_session(bundle)
        _events = [
            event
            async for event in engine.run_turn(session, MessageTurn(text=learner_input))
        ]
        assert session.request_inputs == []
        return Session.loads(session.dumps())

    session = asyncio.run(make_saved_session())
    session.request_inputs = list(request_inputs)
    later_history = session.to_dict()["messages"][1:]

    refresh_teaching_brief(session, course_brief)

    expected = render_first_prompt(
        replace(bundle, constraints=course_brief or None), {}
    )
    first_prompt = next(
        part.content
        for part in session.messages[0].parts
        if isinstance(part, UserPromptPart)
    )
    assert first_prompt == expected + "\n\n" + learner_input
    assert session.to_dict()["messages"][1:] == later_history


def test_cleared_bundle_keeps_ambiguous_historical_evidence() -> None:
    """Without an old bundle constraint, a tagged suffix may be learner-authored."""
    original = ScriptBundle(script="Original lesson", constraints="Historical guidance")
    prompt = render_first_prompt(original, {})
    session = Session(
        script=replace(original, constraints=None),
        messages=[ModelRequest(parts=[UserPromptPart(prompt)])],
        request_inputs=[],
    )
    first = session.messages[0]

    refresh_teaching_brief(session, "")

    assert session.messages[0] is first


def test_unmatched_constraints_without_host_extras_keep_ambiguous_evidence() -> None:
    """A unique closing tag alone cannot prove that a suffix came from the host."""
    original = ScriptBundle(script="Original lesson")
    learner_input = "<constraints>\nMy question about prompt syntax\n</constraints>"
    prompt = render_first_prompt(original, {}) + "\n\n" + learner_input
    session = Session(
        script=replace(original, constraints="A previously updated course voice"),
        messages=[ModelRequest(parts=[UserPromptPart(prompt)])],
        request_inputs=[],
    )
    first = session.messages[0]

    refresh_teaching_brief(session, "Current course voice")

    assert session.messages[0] is first
    assert session.script.constraints == "Current course voice"
