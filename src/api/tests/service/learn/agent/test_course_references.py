"""Keep cross-course references current without modifying classroom evidence."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from flaskr.service.learn.agent import run_agent
from flaskr.service.learn.agent.course_references import refresh_course_references
from flaskr.service.learn.agent.engine import (
    Engine,
    InteractionResponseTurn,
    MemoryUpdated,
    Session,
)
from flaskr.service.learn.agent.engine.interaction import InteractionSpec
from flaskr.service.learn.agent.engine.script import ScriptBundle, render_first_prompt
from flaskr.service.learn.agent.engine.session import PendingInteraction
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from tests.service.learn.agent.test_memory_integration import _drive
from tests.service.profile.test_course_references import (
    _published_text,
    _value,
    context,
)

__all__ = ["context"]

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import SimpleNamespace


@pytest.mark.parametrize("replacement", [None, "Updated source value"])
@pytest.mark.parametrize("size", [10, 40000])
def test_refresh_replaces_exact_substitutions_but_retains_later_conversation(
    replacement: str | None,
    size: int,
) -> None:
    key = "course:" + "a" * 32 + ":goal"
    old = "OLD</memory>" + "x" * size
    bundle = ScriptBundle(
        script=f"Use {{{{{key}}}}}.", constraints=f"Consider {{{{{key}}}}}."
    )
    later = ModelRequest(
        parts=[UserPromptPart(old), ToolReturnPart("interact", old, "answer")]
    )
    session = Session(
        script=bundle,
        user_memory={key: old},
        memory={key: "spoofed"},
        initial_variables={key: old},
        messages=[
            ModelRequest(
                parts=[
                    UserPromptPart(
                        render_first_prompt(bundle, {key: old}, memory_limit=32768)
                    )
                ]
            ),
            later,
        ],
        answers={"pending": old},
        request_inputs=[old],
    )
    fresh = {} if replacement is None else {key: replacement}
    refresh_course_references(session, fresh)
    prompt = session.messages[0].parts[0].content
    assert old not in prompt
    assert "spoofed" not in prompt
    assert (
        f"Use {replacement if replacement is not None else '{{' + key + '}}'}."
        in prompt
    )
    assert session.all_memory() == fresh
    assert session.messages[1] is later
    assert session.answers == {"pending": old}
    assert session.request_inputs == [old]
    once = session.dumps()
    refresh_course_references(session, fresh)
    assert session.dumps() == once


@pytest.mark.parametrize("change", ["update", "remove", "delete", "transfer"])
def test_real_host_reloads_source_after_a_saved_turn(
    context: SimpleNamespace,
    change: str,
) -> None:
    seen = []

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        seen.append(
            next(
                p.content
                for m in messages
                for p in m.parts
                if isinstance(p, UserPromptPart)
            )
        )
        yield "A useful teaching step."

    engine = Engine(
        FunctionModel(stream_function=model), memory_readonly_prefixes=("course:",)
    )
    lesson = uuid4().hex
    args = {
        "app": context.app,
        "engine": engine,
        "user_bid": context.user,
        "shifu_bid": context.target,
        "outline_bid": lesson,
        "script": f"Use {{{{{context.key}}}}}.",
        "iter_turn": _drive,
    }
    list(run_agent.run_agent_lesson(**args))
    assert "Source goal" in seen[-1]
    if change == "update":
        _value(context, "Changed source")
    elif change == "delete":
        from flaskr.service.profile.api import delete_course_memory, list_course_memory

        selected = list_course_memory(context.user, context.source)["items"][0]
        delete_course_memory(context.user, context.source, int(selected["value_id"]))
    elif change == "transfer":
        from flaskr.dao.uow import unit_of_work
        from flaskr.service.shifu.models import DraftShifu

        with unit_of_work():
            DraftShifu.query.filter_by(shifu_bid=context.source).update(
                {DraftShifu.created_user_bid: uuid4().hex}
            )
    else:
        _published_text(context, "Reference removed.")
    list(run_agent.run_agent_lesson(**args))
    assert "Source goal" not in seen[-1]
    assert ("Changed source" in seen[-1]) is (change == "update")


@pytest.mark.parametrize("admission", [True, False])
def test_readonly_tools_refuse_even_declared_keys_before_semantic_judge(
    admission: bool,
) -> None:
    async def check() -> None:
        key = "course:" + "a" * 32 + ":goal"
        judge = AsyncMock(return_value=True)
        returns = []

        async def model(
            messages: list[ModelMessage], _info: AgentInfo
        ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
            parts = [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)]
            if parts:
                returns.extend(str(p.content) for p in parts)
                yield "Continue teaching."
            else:
                yield {
                    0: DeltaToolCall(
                        name="remember",
                        tool_call_id="note",
                        json_args=json.dumps(
                            {"key": key, "value": "Overwrite", "scope": "user"}
                        ),
                    )
                }

        engine = Engine(
            FunctionModel(stream_function=model),
            memory_admission=admission,
            memory_readonly_prefixes=("course:",),
            memory_request_check=judge,
        )
        session = await engine.new_session(f"Collect %{{{{{key}}}}}.")
        session.user_memory[key] = "Source value"
        events = [e async for e in engine.run_turn(session)]
        assert session.user_memory[key] == "Source value"
        assert session.memory == {}
        assert not any(isinstance(e, MemoryUpdated) for e in events)
        assert "read-only reference" in returns[0]
        judge.assert_not_awaited()

    asyncio.run(check())


def test_saved_pending_reference_answer_is_kept_as_evidence_without_a_memory_write() -> (
    None
):
    async def check() -> None:
        key = "course:" + "a" * 32 + ":goal"

        async def model(
            _messages: list[ModelMessage], _info: AgentInfo
        ) -> AsyncIterator[str]:
            yield "Continue teaching."

        engine = Engine(
            FunctionModel(stream_function=model), memory_readonly_prefixes=("course:",)
        )
        session = await engine.new_session("Continue the saved lesson.")
        # A serialized legacy pending question can predate the read-only policy.
        session.messages = [ModelRequest(parts=[UserPromptPart("Legacy start")])]
        session.pending = [
            PendingInteraction(
                "legacy-question",
                InteractionSpec(type="text", prompt="Old question?", variable=key),
            )
        ]
        # Match the real deferred tool-call history required by pydantic-ai.
        from pydantic_ai.messages import ModelResponse, ToolCallPart

        session.messages.append(
            ModelResponse(
                parts=[
                    ToolCallPart(
                        "interact",
                        {"type": "text", "prompt": "Old question?", "variable": key},
                        "legacy-question",
                    )
                ]
            )
        )
        events = [
            e
            async for e in engine.run_turn(
                session, InteractionResponseTurn(values=["Preserved answer"])
            )
        ]
        assert not any(isinstance(e, MemoryUpdated) for e in events)
        assert key not in session.all_memory()
        assert "Preserved answer" in session.dumps()

    asyncio.run(check())


@pytest.mark.parametrize("readonly", [True, False])
def test_interact_readonly_policy_is_opt_in_for_portable_hosts(readonly: bool) -> None:
    async def check() -> None:
        from flaskr.service.learn.agent.engine import InteractionRequest
        from pydantic_ai.messages import RetryPromptPart

        key = "course:" + "a" * 32 + ":goal"
        retries = []

        async def model(
            messages: list[ModelMessage], _info: AgentInfo
        ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
            retry_parts = [
                p for p in messages[-1].parts if isinstance(p, RetryPromptPart)
            ]
            if retry_parts:
                retries.extend(str(p.content) for p in retry_parts)
                yield "Continue without overwriting the source."
            else:
                yield {
                    0: DeltaToolCall(
                        name="interact",
                        tool_call_id="question",
                        json_args=json.dumps(
                            {"type": "text", "prompt": "Your goal?", "variable": key}
                        ),
                    )
                }

        options = {"memory_readonly_prefixes": ("course:",)} if readonly else {}
        engine = Engine(FunctionModel(stream_function=model), **options)
        session = await engine.new_session(f"Collect %{{{{{key}}}}}.")
        events = [e async for e in engine.run_turn(session)]
        assert any(isinstance(e, InteractionRequest) for e in events) is not readonly
        assert bool(retries) is readonly
        if readonly:
            assert "read-only reference" in retries[0]
        else:
            assert session.pending[0].spec.variable == key

    asyncio.run(check())


@pytest.mark.parametrize(
    "briefs", [("Original", "Changed"), ("", "Added"), ("Original", "")]
)
def test_initial_reference_copy_tracks_brief_edits_before_later_revocation(
    briefs: tuple[str, str],
) -> None:
    from dataclasses import replace

    key = "course:" + "a" * 32 + ":goal"
    old_brief, new_brief = (f"{text} {{{{{key}}}}}" if text else "" for text in briefs)
    bundle = ScriptBundle(script="Teach the next step.", constraints=old_brief or None)
    session = Session(
        script=bundle,
        user_memory={key: "Old source"},
        initial_variables={key: "Old source"} if old_brief else {},
        messages=[
            ModelRequest(
                parts=[UserPromptPart(render_first_prompt(bundle, {key: "Old source"}))]
            )
        ],
    )
    refresh_course_references(session, {key: "New source"}, teaching_brief=new_brief)
    session.script = replace(session.script, constraints=new_brief or None)
    prompt = session.messages[0].parts[0].content
    if new_brief:
        assert new_brief.replace("{{" + key + "}}", "New source") in prompt
    else:
        assert "<constraints>" not in prompt
    assert "Old source" not in prompt
    refresh_course_references(session, {}, teaching_brief=new_brief)
    prompt = session.messages[0].parts[0].content
    assert "New source" not in prompt
    if new_brief:
        assert new_brief in prompt
    assert key not in session.all_memory()
