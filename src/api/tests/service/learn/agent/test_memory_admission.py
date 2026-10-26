"""Validate independent structured request checks without network or provider bypasses."""

import asyncio
import json

import pytest
from flaskr.service.learn.agent.memory_admission import make_request_check
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("decision", [True, False, "malformed", "error"])
async def test_structured_decision_and_failures(decision: bool | str) -> None:
    calls = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append((messages, info))
        if decision == "error":
            message = "provider failed"
            raise RuntimeError(message)
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"allowed": decision})]
        )

    check = make_request_check(FunctionModel(model))
    assert await check("Please remember my pace.", "pace", "slow") is (decision is True)
    assert len(calls) == 1
    messages, info = calls[0]
    payload = next(
        p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)
    )
    assert json.loads(payload) == {
        "learner_input": "Please remember my pace.",
        "key": "pace",
        "value": "slow",
    }
    assert info.model_settings["max_tokens"] == 512


async def test_duplicate_concurrent_checks_and_distinct_call_budget() -> None:
    calls = []

    async def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(messages)
        await asyncio.sleep(0)
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"allowed": True})]
        )

    check = make_request_check(FunctionModel(model))
    assert (
        await asyncio.gather(
            *(check("Please remember this", "pace", "slow") for _ in range(5))
        )
        == [True] * 5
    )
    assert len(calls) == 1
    assert await check("Please remember this", "pace", "fast")
    assert await check("Please remember this", "goal", "project")
    assert not await check("Please remember this", "fourth", "refused")
    assert await check("Please remember this", "pace", "slow")
    assert len(calls) == 3


async def test_cancellation_is_not_converted_into_permission_or_a_normal_refusal() -> (
    None
):
    async def model(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await make_request_check(FunctionModel(model))(
            "Please remember this", "pace", "slow"
        )
