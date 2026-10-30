"""Retired global profile snapshots cannot reappear through resumed sessions."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.i18n import clear_language, set_language
from flaskr.service.learn.agent import debug_session, run_agent, session_store
from flaskr.service.learn.agent.retired_profile_memory import (
    PROFILE_MEMORY_VERSION_KEY,
    mark_profile_memory_current,
    refresh_retired_profile_memory,
)
from flaskr.service.learn.agent.rewind import checkpoint_of, restore
from flaskr.service.learn.memory.dtos import MemorySnapshot
from flaskr.service.profile.api import RETIRED_PROFILE_KEYS
from flaskr.service.profile.models import VariableValue
from markdownflow.engine import Engine, Session
from markdownflow.engine.memory_context import parse_initial_memory_prompt
from markdownflow.engine.script import ScriptBundle, render_first_prompt
from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.service.learn.agent.test_memory_integration import _drive


@pytest.mark.parametrize("key", sorted(RETIRED_PROFILE_KEYS))
def test_retired_global_snapshots_are_removed_without_rewriting_classroom_evidence(
    key: str,
) -> None:
    old = "Historical profile value"
    bundle = ScriptBundle(script=f"Teach {{{{{key}}}}}.")
    later = ModelRequest(
        parts=[UserPromptPart(old), ToolReturnPart("interact", old, "answer")]
    )
    session = Session(
        script=bundle,
        user_memory={key: old, "goal": "Course goal"},
        initial_variables={key: old, "goal": "Course goal"},
        messages=[
            ModelRequest(
                parts=[
                    UserPromptPart(
                        render_first_prompt(bundle, {key: old, "goal": "Course goal"})
                    )
                ]
            ),
            later,
        ],
        answers={"pending": old},
        request_inputs=[old],
    )
    original = parse_initial_memory_prompt(session.messages[0].parts[0].content)
    assert original is not None
    suffix = session.messages[0].parts[0].content[original.script_start :]

    refresh_retired_profile_memory(session, {"goal": "Course goal"})

    assert session.all_memory() == {"goal": "Course goal"}
    assert session.initial_variables == {"goal": "Course goal"}
    content = session.messages[0].parts[0].content
    parsed = parse_initial_memory_prompt(content)
    assert parsed is not None
    assert parsed.memory == {"goal": "Course goal"}
    assert content[parsed.script_start :] == suffix
    assert session.messages[1] is later
    assert session.answers == {"pending": old}
    assert session.request_inputs == [old]
    once = session.dumps()
    refresh_retired_profile_memory(session, {"goal": "Course goal"})
    assert session.dumps() == once


@pytest.mark.parametrize("current", [{}, {"sys_user_style": "Current course answer"}])
@pytest.mark.parametrize("authored", [False, True])
def test_accepted_course_answers_survive_retired_host_snapshot_refresh(
    current: dict[str, str], authored: bool
) -> None:
    key = "sys_user_style"
    bundle = ScriptBundle(
        script="Ask ?[%{{sys_user_style}}...Style?]" if authored else "Teach."
    )
    session = Session(
        script=bundle,
        user_memory={key: "Historical global style"},
        initial_variables={key: "Historical global style"},
        messages=[
            ModelRequest(parts=[UserPromptPart(render_first_prompt(bundle, {}))])
        ],
    )
    session.record_answer(key, "Accepted course answer")

    refresh_retired_profile_memory(session, current)

    expected = (
        current.get(key, "Accepted course answer")
        if authored
        else "Accepted course answer"
    )
    assert session.memory[key] == expected
    assert key in session.answered_memory_keys()
    assert session.initial_variables[key] == expected
    assert "Historical global style" not in session.dumps()


def test_session_only_course_note_keeps_precedence_over_persisted_values() -> None:
    bundle = ScriptBundle(script="Teach {{language}}.")
    session = Session(
        script=bundle,
        user_memory={"language": "Historical global language"},
        memory={"language": "Session-only course note"},
        initial_variables={"language": "Historical global language"},
        messages=[
            ModelRequest(
                parts=[
                    UserPromptPart(
                        render_first_prompt(
                            bundle, {"language": "Historical global language"}
                        )
                    )
                ]
            )
        ],
    )

    refresh_retired_profile_memory(session, {"language": "Persisted course value"})

    assert session.memory == {"language": "Session-only course note"}
    assert session.initial_variables == {"language": "Session-only course note"}
    assert not session.answered_memory_keys()
    parsed = parse_initial_memory_prompt(session.messages[0].parts[0].content)
    assert parsed is not None
    assert parsed.memory == {"language": "Session-only course note"}


@pytest.mark.parametrize("debug", [False, True])
def test_host_resume_uses_scoped_values_and_keeps_accepted_answers(
    monkeypatch: pytest.MonkeyPatch, debug: bool
) -> None:
    old = dict.fromkeys(RETIRED_PROFILE_KEYS, "Historical global value")
    current = {"language": "Course programming language", "sex": "Course label"}
    bundle = ScriptBundle(script="Teach {{language}} and ask ?[%{{birth}}...Answer?]")
    session = Session(
        script=bundle,
        user_memory=old,
        initial_variables=dict(old),
        messages=[
            ModelRequest(parts=[UserPromptPart(render_first_prompt(bundle, old))])
        ],
    )
    session.record_answer("birth", "Accepted answer")
    monkeypatch.setattr(run_agent, "load_agent_session", lambda *_a, **_kw: session)
    monkeypatch.setattr(
        run_agent, "course_memory_deletion_state", lambda *_a: ({}, frozenset())
    )
    monkeypatch.setattr(
        run_agent, "load_memory", lambda *_a, **_kw: MemorySnapshot(variables=current)
    )
    store = SimpleNamespace(load=lambda **_kw: session) if debug else None
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
            preview_mode=debug,
            debug_store=store,
            preview_variables=dict(current),
            use_learner_language=True,
        )
        resumed = asyncio.run(factory())
    finally:
        clear_language()

    assert not finished
    assert resumed.all_memory() == {
        **current,
        "sys_user_language": "fr-FR",
        "birth": "Accepted answer",
    }
    assert "birth" in resumed.answered_memory_keys()
    assert resumed.initial_variables == {**current, "birth": "Accepted answer"}
    assert "Historical global value" not in resumed.dumps()
    assert engine.output_language == "Français"


@pytest.mark.parametrize("legacy", [False, True])
def test_debug_user_scope_note_survives_next_request_without_ui_variable_echo(
    app: object, monkeypatch: pytest.MonkeyPatch, legacy: bool
) -> None:
    """A preview remember call must survive even when its value equals the old snapshot."""
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

    if legacy:
        bundle = ScriptBundle(script=script)
        store().save(
            Session(
                script=bundle,
                user_memory={"language": "Python"},
                initial_variables={"language": "Python"},
                messages=[
                    ModelRequest(
                        parts=[
                            UserPromptPart(
                                render_first_prompt(bundle, {"language": "Python"})
                            )
                        ]
                    )
                ],
            )
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
            assert (
                json.loads(next(iter(values.values())))[PROFILE_MEMORY_VERSION_KEY] == 1
            )
        assert VariableValue.query.filter_by(user_bid=user).count() == 0
        db.session.remove()


@pytest.mark.parametrize("current_scope", [False, True])
def test_database_session_roundtrips_one_time_profile_retirement_marker(
    app: object, current_scope: bool
) -> None:
    """The host metadata distinguishes old globals from later equal-value course notes."""
    user, course, lesson = (uuid4().hex for _ in range(3))
    session = Session(
        script=ScriptBundle(script="Teach {{language}}."),
        user_memory={"language": "Python"},
    )
    if current_scope:
        mark_profile_memory_current(session)

    def save(value: Session) -> None:
        session_store.save_agent_session(
            app, value, user_bid=user, shifu_bid=course, outline_item_bid=lesson
        )

    with app.app_context():
        save(session)
        loaded = session_store.load_agent_session(app, user, lesson)
        refresh_retired_profile_memory(loaded, {})
        assert loaded.user_memory == ({"language": "Python"} if current_scope else {})
        loaded.user_memory["language"] = "Python"
        save(loaded)
        reloaded = session_store.load_agent_session(app, user, lesson)
        refresh_retired_profile_memory(reloaded, {})
        assert reloaded.user_memory["language"] == "Python"
        assert reloaded.id == session.id


@pytest.mark.parametrize("legacy_checkpoint", [False, True])
def test_rewind_keeps_retirement_and_later_user_scope_course_notes(
    legacy_checkpoint: bool,
) -> None:
    """Rewind restores turn state without restoring retired host snapshots."""
    bundle = ScriptBundle(script="Teach {{language}}.")
    session = Session(
        script=bundle,
        user_memory={"language": "Historical global value"},
        initial_variables={"language": "Historical global value"},
        messages=[
            ModelRequest(
                parts=[
                    UserPromptPart(
                        render_first_prompt(
                            bundle, {"language": "Historical global value"}
                        )
                    )
                ]
            )
        ],
    )
    if legacy_checkpoint:
        checkpoint = checkpoint_of(session)
    refresh_retired_profile_memory(session, {})
    if not legacy_checkpoint:
        checkpoint = checkpoint_of(session)
    session.user_memory["language"] = "Python"

    restore(session, checkpoint)
    refresh_retired_profile_memory(session, {})

    assert session.user_memory["language"] == "Python"
    assert session.initial_variables == {}
    assert "Historical global value" not in session.dumps()
    parsed = parse_initial_memory_prompt(session.messages[0].parts[0].content)
    assert parsed is not None
    assert parsed.memory == {}
