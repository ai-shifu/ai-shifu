"""Memory refresh preserves both old expanded and new unexpanded prompt bodies."""

import pytest
from flaskr.service.learn.agent.deleted_memory import refresh_deleted_memory
from flaskr.service.learn.agent.nickname import refresh_nickname
from markdownflow.engine import ScriptBundle, Session, render_first_prompt
from markdownflow.engine.memory_context import parse_initial_memory_prompt
from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart

from tests.service.learn.agent.prompt_fixtures import expanded_initial_prompt


@pytest.mark.parametrize("expanded", [False, True])
def test_memory_refresh_preserves_saved_authored_sections(expanded: bool) -> None:
    """Recreation and deletion affect current memory, never the saved prompt body."""
    bundle = ScriptBundle(
        script="Hello {{sys_user_nickname}}. Goal: {{goal}}.",
        constraints="Address {{sys_user_nickname}}. Goal: {{goal}}.",
    )
    memory = {"sys_user_nickname": "Alex"}
    render = expanded_initial_prompt if expanded else render_first_prompt
    prompt = render(bundle, memory)
    parsed = parse_initial_memory_prompt(prompt)
    assert parsed is not None
    saved_suffix = prompt[parsed.script_start :]
    evidence = ModelRequest(
        parts=[
            UserPromptPart("Keep literal {{goal}} in my syntax question."),
            ToolReturnPart("remember", {"literal": "{{goal}}"}, "original-call"),
        ]
    )
    session = Session(
        script=bundle,
        user_memory=dict(memory),
        initial_variables=dict(memory),
        messages=[ModelRequest(parts=[UserPromptPart(prompt)]), evidence],
    )
    refresh_nickname(session, {"sys_user_nickname": "Sam"})
    first = session.messages[0].parts[0].content
    current = parse_initial_memory_prompt(first)
    assert current is not None
    assert current.memory == {"sys_user_nickname": "Sam"}
    assert first[current.script_start :] == saved_suffix

    refresh_deleted_memory(session, frozenset({"goal"}), current={"goal": "New goal"})
    first = session.messages[0].parts[0].content
    current = parse_initial_memory_prompt(first)
    assert current is not None
    assert current.memory == {"sys_user_nickname": "Sam", "goal": "New goal"}
    assert first[current.script_start :] == saved_suffix
    refresh_deleted_memory(session, frozenset({"goal"}))
    first = session.messages[0].parts[0].content
    current = parse_initial_memory_prompt(first)
    assert current is not None
    assert current.memory == {"sys_user_nickname": "Sam"}
    assert first[current.script_start :] == saved_suffix
    assert "goal" not in session.all_memory()
    assert session.initial_variables == memory
    once = session.dumps()
    refresh_deleted_memory(session, frozenset({"goal"}))
    assert session.dumps() == once
    assert session.messages[1] is evidence
    assert session.script is bundle
