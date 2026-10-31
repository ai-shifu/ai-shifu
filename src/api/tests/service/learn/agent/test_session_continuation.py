"""Saved learning and preview sessions continue with their course variables."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from uuid import uuid4

from flaskr.dao import db
from flaskr.i18n import clear_language, set_language
from flaskr.service.learn.agent import debug_session, run_agent
from flaskr.service.learn.memory.dtos import MemorySnapshot
from flaskr.service.profile.models import VariableValue
from markdownflow.engine import Engine, Session
from markdownflow.engine.script import ScriptBundle, render_first_prompt
from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.service.learn.agent.test_memory_integration import _drive

if TYPE_CHECKING:
    import pytest


def test_learning_resume_preserves_saved_inputs_and_answers_with_current_course_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Continue the same lesson without rewriting its initial prompt or snapshots."""
    old = {
        "language": "Old language",
        "avatar": "Old avatar",
        "sys_user_style": "Old style",
    }
    current = {"language": "Python", "sex": "Course label"}
    bundle = ScriptBundle(
        script="Teach {{language}} and ask ?[%{{sys_user_style}}...Answer?]"
    )
    earlier = ModelRequest(parts=[UserPromptPart(render_first_prompt(bundle, old))])
    later = ModelRequest(
        parts=[
            UserPromptPart("Earlier learner words"),
            ToolReturnPart("interact", "Accepted course answer", "style-answer"),
        ]
    )
    session = Session(
        script=bundle,
        user_memory=dict(old),
        initial_variables=dict(old),
        messages=[earlier, later],
        memory={"scratch": "Session-only note"},
        answers={"pending": "Earlier response"},
        request_inputs=["Original request"],
        turn=3,
    )
    session.record_answer("sys_user_style", "Accepted course answer")
    history = session.to_dict()["messages"]
    monkeypatch.setattr(run_agent, "load_agent_session", lambda *_a, **_kw: session)
    monkeypatch.setattr(
        run_agent, "course_memory_deletion_state", lambda *_a: ({}, frozenset())
    )
    monkeypatch.setattr(
        run_agent, "load_memory", lambda *_a, **_kw: MemorySnapshot(variables=current)
    )
    engine = SimpleNamespace(output_language=None)
    set_language("fr-FR")
    try:
        factory, finished = run_agent._load_or_start(
            SimpleNamespace(),
            engine,
            user_bid="learner",
            shifu_bid="course",
            outline_bid="lesson",
            script=bundle.script,
            preview_mode=False,
            use_learner_language=True,
        )
        resumed = asyncio.run(factory())
    finally:
        clear_language()

    assert not finished
    assert resumed.id == session.id
    assert resumed.turn == 3
    assert resumed.all_memory() == {
        **current,
        "sys_user_language": "fr-FR",
        "scratch": "Session-only note",
        "sys_user_style": "Accepted course answer",
    }
    assert "sys_user_style" in resumed.answered_memory_keys()
    assert resumed.initial_variables == old
    assert resumed.to_dict()["messages"] == history
    assert resumed.messages[0] is earlier
    assert resumed.messages[1] is later
    assert resumed.answers == {"pending": "Earlier response"}
    assert resumed.request_inputs == ["Original request"]
    assert engine.output_language == "Français"


def test_debug_user_scope_note_survives_next_request_without_ui_variable_echo(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preview notes survive persistence without a variable echo from the editor."""
    values = {}
    cache = SimpleNamespace(
        get=values.get,
        setex=lambda key, _ttl, value: values.__setitem__(key, value),
    )
    monkeypatch.setattr(debug_session, "cache", cache)
    user, course, lesson, run = (uuid4().hex for _ in range(4))
    script = "Teach {{language}} and ask for confirmation."

    def store() -> debug_session.DebugSessionStore:
        return debug_session.DebugSessionStore(
            app, user_bid=user, shifu_bid=course, outline_bid=lesson, run_bid=run
        )

    calls = 0

    async def model(_messages: list, _info: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {
                0: DeltaToolCall(
                    name="remember",
                    tool_call_id="course-note",
                    json_args=json.dumps(
                        {"scope": "user", "key": "language", "value": "Python"}
                    ),
                )
            }
        elif calls == 2:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="continue-question",
                    json_args=json.dumps(
                        {
                            "type": "single",
                            "prompt": "Continue?",
                            "options": [{"display": "Continue", "value": "continue"}],
                        }
                    ),
                )
            }
        else:
            yield "We will use the selected programming language."

    with app.app_context():
        first_id = None
        for answer in (None, {"input": ["continue"]}):
            list(
                run_agent.run_agent_lesson(
                    app,
                    engine=Engine(FunctionModel(stream_function=model)),
                    script=script,
                    user_bid=user,
                    shifu_bid=course,
                    outline_bid=lesson,
                    preview_mode=True,
                    debug_store=store(),
                    preview_variables={},
                    user_input=answer,
                    iter_turn=_drive,
                )
            )
            saved = store().load(script=script)
            assert saved.user_memory["language"] == "Python"
            if first_id is None:
                first_id = saved.id
            else:
                assert saved.id == first_id
        assert VariableValue.query.filter_by(user_bid=user).count() == 0
        db.session.remove()
