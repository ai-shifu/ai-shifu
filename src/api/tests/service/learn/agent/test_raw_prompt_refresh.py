"""Keep new raw prompt sections intact while refreshing their memory context."""

import pytest
from flaskr.service.learn.agent.deleted_memory import refresh_deleted_memory
from flaskr.service.learn.agent.nickname import refresh_nickname
from markdownflow.engine import ScriptBundle, Session, render_first_prompt
from markdownflow.engine.memory_context import parse_initial_memory_prompt
from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart

from tests.service.learn.agent.prompt_fixtures import expanded_initial_prompt


@pytest.mark.parametrize("expanded", [False, True])
@pytest.mark.parametrize("memory_limit", [None, 150])
def test_nickname_refresh_changes_only_initial_memory(
    memory_limit: int | None, expanded: bool
) -> None:
    bundle = ScriptBundle(
        script="Hello {{sys_user_nickname}}. Use {{goal}}.",
        constraints="Address {{sys_user_nickname}}; leave {{unknown}} intact.",
        extras={"example": "{{sys_user_nickname}} and {{goal}}"},
    )
    memory = {"sys_user_nickname": "Alex", "goal": "x" * 1000}
    render = expanded_initial_prompt if expanded else render_first_prompt
    prompt = render(bundle, memory, memory_limit=memory_limit)
    prompt += "\n\nMy original question contains {{goal}}."
    parsed = parse_initial_memory_prompt(prompt)
    assert parsed is not None
    suffix = prompt[parsed.script_start :]
    later = ModelRequest(
        parts=[
            UserPromptPart("I called myself Alex before."),
            ToolReturnPart("interact", "Learner wrote: Alex", "old-answer"),
        ]
    )
    session = Session(
        script=bundle,
        user_memory=dict(memory),
        initial_variables=dict(memory),
        messages=[ModelRequest(parts=[UserPromptPart(prompt)]), later],
        answers={"old-answer": "Learner wrote: Alex"},
    )
    refresh_nickname(session, {"sys_user_nickname": "Sam"})
    refreshed = session.messages[0].parts[0].content
    current = parse_initial_memory_prompt(refreshed)
    assert current is not None
    assert current.memory == {**parsed.memory, "sys_user_nickname": "Sam"}
    assert current.notice == parsed.notice
    assert refreshed[current.script_start :] == suffix
    assert session.messages[1] is later
    assert session.answers == {"old-answer": "Learner wrote: Alex"}
    assert session.initial_variables == memory
    once = session.dumps()
    refresh_nickname(session, {"sys_user_nickname": "Sam"})
    assert session.dumps() == once


@pytest.mark.parametrize("expanded", [False, True])
@pytest.mark.parametrize("recreated", [False, True])
def test_deletion_changes_only_memory_for_saved_prompt_formats(
    expanded: bool, recreated: bool
) -> None:
    bundle = ScriptBundle(
        script="Hello {{sys_user_nickname}}. Use {{goal}}.",
        constraints="Use {{goal}} in {{sys_user_nickname}}'s example.",
        extras={"example": "{{goal}} must stay verbatim."},
    )
    initial = {"goal": "Deleted fact", "sys_user_nickname": "Alex"}
    writer = expanded_initial_prompt if expanded else render_first_prompt
    prompt = writer(bundle, initial)
    tail = "\n\nMy syntax question contains {{goal}}."
    parsed = parse_initial_memory_prompt(prompt)
    assert parsed is not None
    suffix = prompt[parsed.script_start :] + tail
    later = ModelRequest(
        parts=[
            UserPromptPart("My actual earlier answer."),
            ToolReturnPart("interact", "Learner wrote: Deleted fact", "old-answer"),
        ]
    )
    session = Session(
        script=bundle,
        memory={"goal": "Deleted fact"},
        user_memory=dict(initial),
        initial_variables=dict(initial),
        messages=[ModelRequest(parts=[UserPromptPart(prompt + tail)]), later],
        answers={"old-answer": "Learner wrote: Deleted fact"},
    )
    current = {"goal": "Recreated fact"} if recreated else {}
    refresh_deleted_memory(session, frozenset({"goal"}), current=current)
    refreshed = session.messages[0].parts[0].content
    parsed = parse_initial_memory_prompt(refreshed)
    assert parsed is not None
    assert parsed.memory == {"sys_user_nickname": "Alex", **current}
    assert session.all_memory() == {"sys_user_nickname": "Alex", **current}
    assert refreshed[parsed.script_start :] == suffix
    assert session.initial_variables == initial
    assert session.messages[1] is later
    assert session.answers == {"old-answer": "Learner wrote: Deleted fact"}
    once = session.dumps()
    refresh_deleted_memory(session, frozenset({"goal"}), current=current)
    assert session.dumps() == once
