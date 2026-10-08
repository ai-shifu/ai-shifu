"""Keep cross-course references current without modifying classroom evidence."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from flaskr.service.learn.agent import run_agent
from flaskr.service.learn.agent.course_references import discard_course_references
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
    context,
)

__all__ = ["context"]

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import SimpleNamespace


@pytest.mark.parametrize("prefix", ["course:", "share:"])
@pytest.mark.parametrize("size", [10, 40000])
@pytest.mark.parametrize("prompt_only", [False, True])
def test_discard_removes_initial_snapshots_but_keeps_original_classroom_evidence(
    prefix: str, size: int, prompt_only: bool
) -> None:
    key = prefix + "a" * 32 + ":goal"
    old = "OLD</memory>" + "x" * size
    bundle = ScriptBundle(script="Teach." if prompt_only else f"Use {{{{{key}}}}}.")
    later = ModelRequest(
        parts=[UserPromptPart(old), ToolReturnPart("interact", old, "answer")]
    )
    session = Session(
        script=bundle,
        user_memory={} if prompt_only else {key: old},
        memory={} if prompt_only else {key: "spoof"},
        initial_variables={} if prompt_only else {key: old},
        messages=[
            ModelRequest(
                parts=[UserPromptPart(render_first_prompt(bundle, {key: old}))]
            ),
            later,
        ],
        answers={"pending": old},
        request_inputs=[old],
    )
    discard_course_references(session)
    assert old not in session.messages[0].parts[0].content
    assert key not in session.all_memory()
    assert not session.initial_variables
    assert session.messages[1] is later
    assert session.answers == {"pending": old}
    assert session.request_inputs == [old]
    before = session.dumps()
    discard_course_references(session)
    assert session.dumps() == before


def test_real_host_never_loads_source_even_when_author_declares_it(
    context: SimpleNamespace,
) -> None:
    seen = []

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        seen.extend(
            p.content
            for m in messages
            for p in m.parts
            if isinstance(p, UserPromptPart)
        )
        yield "Teach the lesson."

    engine = Engine(FunctionModel(stream_function=model))
    for _ in range(2):
        list(
            run_agent.run_agent_lesson(
                context.app,
                engine=engine,
                user_bid=context.user,
                shifu_bid=context.target,
                outline_bid=context.outline,
                script=context.reference_text,
                iter_turn=_drive,
            )
        )
    assert all("Source goal" not in p for p in seen)


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
