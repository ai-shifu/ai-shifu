"""Keep nickname/deletion refresh compatible with both initial prompt formats."""

import pytest
from flaskr.service.learn.agent.deleted_memory import refresh_deleted_memory
from flaskr.service.learn.agent.nickname import refresh_nickname
from markdownflow.engine import ScriptBundle, Session, render_first_prompt
from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("where", ["script", "constraints", "both"])
def test_refresh_matches_each_host_section_independently(
    legacy: bool, where: str
) -> None:
    """A known script must not hide a legacy unknown in its separate teaching brief."""
    bundle = ScriptBundle(
        script="Hello {{sys_user_nickname}}."
        + (" Goal: {{goal}}." if where in ("script", "both") else ""),
        constraints="Address {{sys_user_nickname}}."
        + (" Goal: {{goal}}." if where in ("constraints", "both") else ""),
    )
    memory = {"sys_user_nickname": "Alex"}
    prompt = render_first_prompt(bundle, memory)
    if legacy:
        prompt = prompt.replace('<unavailable_learner_value name="goal" />', "{{goal}}")
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
    assert "Hello Sam." in first
    assert "Address Sam." in first
    assert "{{goal}}" not in first
    assert '<unavailable_learner_value name="goal" />' in first
    assert session.messages[1] is evidence

    refresh_deleted_memory(session, frozenset({"goal"}), current={"goal": "New goal"})
    first = session.messages[0].parts[0].content
    assert "New goal" in first
    assert "unavailable_learner_value" not in first
    refresh_deleted_memory(session, frozenset({"goal"}))
    first = session.messages[0].parts[0].content
    assert "New goal" not in first
    assert '<unavailable_learner_value name="goal" />' in first
    once = session.dumps()
    refresh_deleted_memory(session, frozenset({"goal"}))
    assert session.dumps() == once
    assert session.messages[1] is evidence
    assert session.script is bundle
