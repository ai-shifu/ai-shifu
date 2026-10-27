"""Keep new raw prompt sections intact while refreshing their memory context."""

import pytest
from flaskr.service.learn.agent.deleted_memory import refresh_deleted_memory
from flaskr.service.learn.agent.nickname import refresh_nickname
from markdownflow.engine import ScriptBundle, Session, render_first_prompt
from markdownflow.engine.memory_context import parse_initial_memory_prompt
from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart

from tests.service.learn.agent.prompt_fixtures import expanded_initial_prompt


@pytest.mark.parametrize("memory_limit", [None, 150])
def test_raw_nickname_refresh_changes_only_initial_memory(
    memory_limit: int | None,
) -> None:
    bundle = ScriptBundle(
        script="Hello {{sys_user_nickname}}. Use {{goal}}.",
        constraints="Address {{sys_user_nickname}}; leave {{unknown}} intact.",
        extras={"example": "{{sys_user_nickname}} and {{goal}}"},
    )
    memory = {"sys_user_nickname": "Alex", "goal": "x" * 1000}
    prompt = render_first_prompt(bundle, memory, memory_limit=memory_limit)
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
    once = session.dumps()
    refresh_nickname(session, {"sys_user_nickname": "Sam"})
    assert session.dumps() == once


@pytest.mark.parametrize(
    ("old_brief", "new_brief"),
    [
        ("Use {{goal}} in {{sys_user_nickname}}'s example.", None),
        ("Use {{goal}} in {{sys_user_nickname}}'s example.", "New {{goal}} brief."),
        ("Use {{goal}} in {{sys_user_nickname}}'s example.", ""),
        (None, "Added {{goal}} brief."),
    ],
)
def test_raw_deletion_and_brief_refresh_preserve_authored_text_and_history(
    old_brief: str | None, new_brief: str | None
) -> None:
    bundle = ScriptBundle(
        script="Hello {{sys_user_nickname}}. Use {{goal}}.",
        constraints=old_brief,
        extras={"example": "{{goal}} must stay verbatim."},
    )
    prompt = render_first_prompt(
        bundle, {"goal": "Deleted fact", "sys_user_nickname": "Alex"}
    )
    tail = "\n\nMy syntax question contains {{goal}}."
    later = ModelRequest(
        parts=[
            UserPromptPart("My actual earlier answer."),
            ToolReturnPart("interact", "Learner wrote: Deleted fact", "old-answer"),
        ]
    )
    session = Session(
        script=bundle,
        memory={"goal": "Deleted fact"},
        user_memory={"goal": "Deleted fact", "sys_user_nickname": "Alex"},
        messages=[ModelRequest(parts=[UserPromptPart(prompt + tail)]), later],
        answers={"old-answer": "Learner wrote: Deleted fact"},
    )
    refresh_deleted_memory(session, frozenset({"goal"}), constraints=new_brief)
    refreshed = session.messages[0].parts[0].content
    parsed = parse_initial_memory_prompt(refreshed)
    assert parsed is not None
    assert parsed.memory == {"sys_user_nickname": "Alex"}
    assert "goal" not in session.all_memory()
    expected_brief = old_brief if new_brief is None else new_brief
    expected = f"<script>\n{bundle.script}\n</script>"
    if expected_brief:
        expected += f"\n\n<constraints>\n{expected_brief}\n</constraints>"
    expected += f'\n\n<extra name="example">\n{bundle.extras["example"]}\n</extra>'
    assert refreshed[parsed.script_start :] == expected + tail
    assert session.messages[1] is later
    assert session.answers == {"old-answer": "Learner wrote: Deleted fact"}


@pytest.mark.parametrize("operation", ["nickname", "delete"])
def test_original_script_with_expanded_brief_retains_existing_refresh(
    operation: str,
) -> None:
    bundle = ScriptBundle(
        script="Teach the next example.",
        constraints="Use {{goal}} with {{sys_user_nickname}}.",
    )
    memory = {"goal": "Old goal", "sys_user_nickname": "Alex"}
    prompt = expanded_initial_prompt(bundle, memory)
    session = Session(
        script=bundle,
        user_memory=dict(memory),
        messages=[ModelRequest(parts=[UserPromptPart(prompt)])],
    )
    if operation == "nickname":
        refresh_nickname(session, {"sys_user_nickname": "Sam"})
        expected = "Use Old goal with Sam."
    else:
        refresh_deleted_memory(session, frozenset({"goal"}))
        expected = 'Use <unavailable_learner_value name="goal" /> with Alex.'
    refreshed = session.messages[0].parts[0].content
    assert f"<script>\n{bundle.script}\n</script>" in refreshed
    assert f"<constraints>\n{expected}\n</constraints>" in refreshed
    assert "{{sys_user_nickname}}" not in refreshed
