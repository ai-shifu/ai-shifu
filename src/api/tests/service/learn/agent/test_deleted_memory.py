"""Deletion updates current memory and defeats stale in-flight writes."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.deleted_memory import refresh_deleted_memory
from flaskr.service.profile.api import delete_course_memory, list_course_memory
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.repository import create_user_entity
from markdownflow.engine import Engine, Session
from markdownflow.engine.memory_context import parse_initial_memory_prompt
from markdownflow.engine.script import ScriptBundle
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from tests.service.learn.agent.prompt_fixtures import expanded_initial_prompt
from tests.service.learn.agent.test_memory_integration import _drive

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from flask import Flask


@pytest.mark.parametrize("size", [10, 40000])
def test_refresh_removes_deleted_inputs_but_preserves_answers_and_tool_history(
    size: int,
) -> None:
    """Remove current facts from memory without rewriting saved prompt text."""
    value = "</memory>" + "x" * size
    bundle = ScriptBundle(
        script="Use {{goal}} at {{pace}} pace.", constraints="Consider {{goal}}."
    )
    prompt = expanded_initial_prompt(
        bundle, {"goal": value, "pace": "slow"}, memory_limit=32768
    )
    parsed = parse_initial_memory_prompt(prompt)
    assert parsed is not None
    saved_suffix = prompt[parsed.script_start :]
    later = ModelRequest(
        parts=[
            UserPromptPart("<memory>" + value),
            ToolReturnPart("remember", value, "call"),
        ]
    )
    session = Session(
        script=bundle,
        user_memory={"goal": value, "pace": "slow"},
        memory={"goal": value},
        answer_hashes={"goal": "old fingerprint"},
        initial_variables={"goal": value, "pace": "slow"},
        messages=[ModelRequest(parts=[UserPromptPart(prompt)]), later],
        answers={"pending": value},
        request_inputs=[value],
    )
    refresh_deleted_memory(session, frozenset({"goal"}))
    first = session.messages[0].parts[0].content
    current = parse_initial_memory_prompt(first)
    assert current is not None
    assert "goal" not in current.memory
    assert first[current.script_start :] == saved_suffix
    assert value in saved_suffix
    assert "goal" not in session.all_memory()
    assert "goal" not in session.answer_hashes
    assert session.initial_variables == {"goal": value, "pace": "slow"}
    assert session.messages[1] is later
    assert session.answers["pending"] == value
    assert session.request_inputs == [value]
    once = session.dumps()
    refresh_deleted_memory(session, frozenset({"goal"}))
    assert session.dumps() == once


def test_actual_host_drops_pre_delete_turn_write_and_allows_a_fresh_request(
    app: Flask,
) -> None:
    """Reject a stale in-flight write while accepting a later explicit request."""
    with app.app_context():
        user, course, lesson = uuid4().hex, uuid4().hex, uuid4().hex
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
            row = VariableValue(
                user_bid=user,
                shifu_bid=course,
                key="pace",
                value="old",
                variable_value_bid=uuid4().hex,
            )
            db.session.add(row)
        bid = row.id
        deleted = False

        async def model(
            messages: list[ModelMessage], _info: AgentInfo
        ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
            nonlocal deleted
            returned = any(isinstance(p, ToolReturnPart) for p in messages[-1].parts)
            if returned:
                yield "Useful lesson content."
                return
            if not deleted:
                delete_course_memory(user, course, bid)
                deleted = True
                value = "stale in-flight note"
            else:
                value = "fresh requested note"
            yield {
                0: DeltaToolCall(
                    name="remember",
                    tool_call_id=uuid4().hex,
                    json_args=json.dumps(
                        {"key": "pace", "value": value, "scope": "user"}
                    ),
                )
            }

        engine = Engine(
            FunctionModel(stream_function=model), memory_context_limit=32768
        )
        kwargs = {
            "app": app,
            "engine": engine,
            "script": "Teach at {{pace}} pace.",
            "user_bid": user,
            "shifu_bid": course,
            "outline_bid": lesson,
            "iter_turn": _drive,
        }
        list(run_agent.run_agent_lesson(**kwargs))
        assert list_course_memory(user, course)["items"] == []
        factory, _ = run_agent._load_or_start(
            app,
            engine,
            user_bid=user,
            shifu_bid=course,
            outline_bid=lesson,
            script=kwargs["script"],
            preview_mode=False,
        )
        resumed = asyncio.run(factory())
        assert "pace" not in resumed.all_memory()
        assert "old" not in resumed.messages[0].parts[0].content
        assert "Teach at {{pace}} pace." in resumed.messages[0].parts[0].content
        kwargs["outline_bid"] = uuid4().hex
        list(run_agent.run_agent_lesson(**kwargs))
        assert (
            list_course_memory(user, course)["items"][0]["value"]
            == "fresh requested note"
        )
        assert (
            session_store.load_agent_session(
                app, user, kwargs["outline_bid"]
            ).user_memory["pace"]
            == "fresh requested note"
        )
        factory, _ = run_agent._load_or_start(
            app,
            engine,
            user_bid=user,
            shifu_bid=course,
            outline_bid=lesson,
            script=kwargs["script"],
            preview_mode=False,
        )
        old_lesson = asyncio.run(factory())
        assert old_lesson.all_memory()["pace"] == "fresh requested note"
        assert "stale in-flight note" not in old_lesson.messages[0].parts[0].content


def test_unknown_initial_history_remains_classroom_evidence() -> None:
    session = Session(
        script=ScriptBundle(script="Teach."),
        memory={"goal": "old"},
        user_memory={"goal": "old"},
        messages=[ModelRequest(parts=[UserPromptPart("unrecognized legacy history")])],
    )
    refresh_deleted_memory(session, frozenset({"goal"}))
    assert not session.all_memory()
    assert session.messages[0].parts[0].content == "unrecognized legacy history"


@pytest.mark.parametrize("renamed", [False, True])
def test_saved_prompt_and_snapshot_survive_memory_changes_and_roundtrip(
    renamed: bool,
) -> None:
    """Refresh current memory while retaining the old prompt and initial snapshot."""

    async def scenario() -> None:
        """Exercise changed session values, optional renaming and repeated deletion."""
        original = "</memory>" + "original" * 6000

        async def model(
            _messages: list[ModelMessage], _info: AgentInfo
        ) -> AsyncIterator[str]:
            yield "A lesson."

        engine = Engine(
            FunctionModel(stream_function=model), memory_context_limit=32768
        )
        session = await engine.new_session(
            ScriptBundle(
                script="Use {{goal}} for {{sys_user_nickname}}.",
                constraints="Consider {{goal}}.",
            ),
            memory={
                "goal": original,
                "unused": "private",
                "sys_user_nickname": "Before",
            },
        )
        _ = [e async for e in engine.run_turn(session)]
        session.messages[0] = ModelRequest(
            parts=[
                UserPromptPart(
                    expanded_initial_prompt(
                        session.script, session.all_memory(), memory_limit=32768
                    )
                )
            ]
        )
        first = session.messages[0].parts[0].content
        assert "goal" not in json.JSONDecoder().raw_decode(first, len("<memory>\n"))[0]
        assert session.initial_variables == {
            "goal": original,
            "sys_user_nickname": "Before",
        }
        snapshot = dict(session.initial_variables)
        parsed = parse_initial_memory_prompt(first)
        assert parsed is not None
        saved_suffix = first[parsed.script_start :]
        session.memory["goal"] = "later changed value"
        session = Session.loads(session.dumps())
        if renamed:
            from flaskr.service.learn.agent.nickname import refresh_nickname

            refresh_nickname(session, {"sys_user_nickname": "After"})
        refresh_deleted_memory(session, frozenset({"goal"}))
        first = session.messages[0].parts[0].content
        current = parse_initial_memory_prompt(first)
        assert current is not None
        assert "goal" not in current.memory
        assert "goal" not in session.all_memory()
        assert current.memory["sys_user_nickname"] == ("After" if renamed else "Before")
        assert first[current.script_start :] == saved_suffix
        assert original in saved_suffix
        assert session.initial_variables == snapshot
        once = session.dumps()
        refresh_deleted_memory(session, frozenset({"goal"}))
        assert session.dumps() == once

    asyncio.run(scenario())
