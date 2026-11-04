"""Preserve saved classroom evidence when initial-message ownership is unknown."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.common.cache_provider import InMemoryCacheProvider
from flaskr.service.learn.agent import debug_session, run_agent, session_store
from flaskr.service.learn.agent.nickname import refresh_nickname
from flaskr.service.learn.agent.rewind import checkpoint_of, restore
from flaskr.service.learn.agent.teaching_brief import (
    INITIAL_TEACHING_BRIEF_KEY,
    record_initial_teaching_brief,
    refresh_teaching_brief,
)
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
from tests.service.learn.agent.test_resumed_nickname import _drive, _prompt


@pytest.mark.parametrize("expanded", [False, True])
@pytest.mark.parametrize(
    ("bundle_already_updated", "course_brief"),
    [
        (False, "Current course guidance for {{goal}}."),
        (False, ""),
        (True, "Current course guidance for {{goal}}."),
    ],
)
def test_resume_updates_bundle_and_preserves_unowned_initial_history(
    monkeypatch: pytest.MonkeyPatch,
    expanded: bool,
    bundle_already_updated: bool,
    course_brief: str,
) -> None:
    """Raw and expanded legacy messages remain intact despite bundle-only updates."""
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
    first_prompt = resumed.messages[0].parts[0].content
    assert first_prompt == prompt
    assert "Old chapter guidance" in first_prompt
    assert first_prompt.endswith("\n\n" + initial_input)
    assert resumed.messages[1] is later_message
    after = resumed.to_dict()
    for key in before.keys() - {"script", "messages"}:
        assert after[key] == before[key], key
    assert after["messages"][1:] == before["messages"][1:]

    # Persistence never upgrades unknown historical text into host-owned content.
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

    expected = render_first_prompt(bundle, {})
    first_prompt = next(
        part.content
        for part in session.messages[0].parts
        if isinstance(part, UserPromptPart)
    )
    assert first_prompt == expected + "\n\n" + learner_input
    assert session.to_dict()["messages"][1:] == later_history
    assert session.script.constraints == (course_brief or None)


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


@pytest.mark.parametrize("course_brief", ["", "Updated course guidance"])
def test_learner_input_equal_to_old_bundle_constraints_survives_refresh(
    course_brief: str,
) -> None:
    """An old host may copy learner-looking text into the bundle without owning it."""
    guidance = "Old guidance"
    learner_input = f"<constraints>\n{guidance}\n</constraints>"

    async def model(_messages: list, _info: object) -> object:
        yield "The original lesson continues."

    async def make_saved_session() -> Session:
        engine = Engine(FunctionModel(stream_function=model), memory_admission=True)
        session = await engine.new_session(ScriptBundle(script="Original lesson"))
        _events = [
            event
            async for event in engine.run_turn(session, MessageTurn(text=learner_input))
        ]
        assert session.request_inputs == []
        # Reproduce the old host: only its bundle snapshot is refreshed, leaving
        # the original first learner message unchanged.
        session.script = replace(session.script, constraints=guidance)
        return Session.loads(session.dumps())

    session = asyncio.run(make_saved_session())
    history = session.to_dict()["messages"]

    refresh_teaching_brief(session, course_brief)

    assert session.to_dict()["messages"] == history
    assert learner_input in next(
        part.content
        for part in session.messages[0].parts
        if isinstance(part, UserPromptPart)
    )
    assert session.script.constraints == (course_brief or None)


@pytest.mark.parametrize("initial_brief", ["Old guidance", ""])
@pytest.mark.parametrize("course_brief", ["Current course guidance", ""])
def test_fresh_host_provenance_survives_debug_storage_and_rewind(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    initial_brief: str,
    course_brief: str,
) -> None:
    """The real fresh producer proves its own range independently from learner text."""
    monkeypatch.setattr(debug_session, "get_redis_client", lambda: None)
    monkeypatch.setattr(debug_session, "cache", InMemoryCacheProvider())
    user, course, lesson, run = (uuid4().hex for _ in range(4))
    script = "Teach {{goal}}.\n<constraints>\nA literal script example\n</constraints>"
    learner_input = "<constraints>\nOld guidance\n</constraints>"
    seen = []

    async def model(messages: list, _info: object) -> object:
        seen.append(_prompt(messages))
        yield "The original lesson continues."

    def store() -> debug_session.DebugSessionStore:
        return debug_session.DebugSessionStore(
            app, user_bid=user, shifu_bid=course, outline_bid=lesson, run_bid=run
        )

    def run_turn(brief: str, first_input: str | None = None) -> None:
        list(
            run_agent.run_agent_lesson(
                app,
                engine=Engine(
                    FunctionModel(stream_function=model), memory_admission=True
                ),
                script=script,
                teaching_brief=brief,
                user_bid=user,
                shifu_bid=course,
                outline_bid=lesson,
                preview_mode=True,
                debug_store=store(),
                user_input=first_input,
                iter_turn=_drive,
            )
        )

    with app.app_context():
        run_turn(initial_brief, learner_input)
        saved = store().load(script=script)
        assert saved is not None
        assert saved.request_inputs == []
        first = saved.messages[0]
        marker = first.metadata[INITIAL_TEACHING_BRIEF_KEY]
        assert marker["constraints_length"] == (
            len(f"\n\n<constraints>\n{initial_brief}\n</constraints>")
            if initial_brief
            else 0
        )
        first.metadata["existing_host_metadata"] = "keep"
        session_store.save_agent_session(
            app,
            saved,
            user_bid=user,
            shifu_bid=course,
            outline_item_bid=lesson,
            preview_mode=True,
        )
        saved = session_store.load_agent_session(app, user, lesson, preview_mode=True)
        assert saved is not None
        assert saved.messages[0].metadata[INITIAL_TEACHING_BRIEF_KEY] == marker
        checkpoint = checkpoint_of(saved)
        saved.messages.append(ModelRequest(parts=[UserPromptPart("Discard this turn")]))
        restore(saved, checkpoint)
        assert saved.messages[0].metadata[INITIAL_TEACHING_BRIEF_KEY] == marker
        refresh_nickname(saved, {"sys_user_nickname": "A much longer current nickname"})
        before = _prompt(saved.messages)
        later = saved.to_dict()["messages"][1:]
        store().save(saved)

        run_turn(course_brief)
        resumed = store().load(script=script)
        assert resumed is not None

    expected = before
    old_block = (
        f"\n\n<constraints>\n{initial_brief}\n</constraints>" if initial_brief else ""
    )
    new_block = (
        f"\n\n<constraints>\n{course_brief}\n</constraints>" if course_brief else ""
    )
    script_document = f"<script>\n{script}\n</script>"
    expected = expected.replace(
        script_document + old_block, script_document + new_block, 1
    )
    assert seen[-1] == expected
    assert _prompt(resumed.messages) == expected
    assert expected.endswith("\n\n" + learner_input)
    assert resumed.to_dict()["messages"][1 : 1 + len(later)] == later
    assert resumed.messages[0].metadata["existing_host_metadata"] == "keep"
    assert INITIAL_TEACHING_BRIEF_KEY in resumed.messages[0].metadata
    once = resumed.dumps()
    refresh_teaching_brief(resumed, course_brief)
    assert resumed.dumps() == once

    # A changed document no longer matches its independent producer evidence.
    initial_part = next(
        part for part in resumed.messages[0].parts if isinstance(part, UserPromptPart)
    )
    initial_part.content = initial_part.content.replace("Teach", "Edited", 1)
    history = resumed.to_dict()["messages"]
    refresh_teaching_brief(resumed, "Another course voice")
    assert resumed.to_dict()["messages"] == history


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("marker", None),
        ("version", 2),
        ("part_index", 1),
        ("part_index", True),
        ("script_length", -1),
        ("script_length", 100000),
        ("constraints_length", -1),
        ("constraints_length", 100000),
        ("prefix_sha256", "tampered"),
    ],
)
def test_invalid_initial_provenance_never_authorizes_message_rewrites(
    field: str, value: object
) -> None:
    """Metadata is necessary but altered ranges or digests cannot authorize a splice."""
    bundle = ScriptBundle(script="Original lesson", constraints="Old guidance")
    session = Session(
        script=bundle,
        messages=[
            ModelRequest(
                parts=[UserPromptPart(render_first_prompt(bundle, {}))],
                metadata={"unrelated_host_key": "keep"},
            )
        ],
    )
    assert record_initial_teaching_brief(session, bundle)
    metadata = session.messages[0].metadata
    if field == "marker":
        metadata.pop(INITIAL_TEACHING_BRIEF_KEY)
    else:
        metadata[INITIAL_TEACHING_BRIEF_KEY][field] = value
    history = session.to_dict()["messages"]

    refresh_teaching_brief(session, "Current course voice")

    assert session.to_dict()["messages"] == history
    assert session.messages[0].metadata["unrelated_host_key"] == "keep"
