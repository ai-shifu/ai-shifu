"""Exercise the live adapter through the lesson gateway without a provider key."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flask import Flask, has_app_context
from pydantic_ai.messages import ModelRequest, ToolCallPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.tools import ToolDefinition
from scripts.mdf_interaction_live import build_live_model
from scripts.mdf_interaction_question_judge import (
    QUESTION_JUDGE_INSTRUCTIONS,
    judge_question,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


@pytest.fixture
def configure_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[str, str], tuple[Mock, Mock]]:
    """Return one fake tool call through the real gateway and record its request."""
    from flaskr.api import llm

    record_usage = Mock(side_effect=AssertionError("application usage write"))
    monkeypatch.setattr(llm, "record_llm_usage", record_usage)
    monkeypatch.setattr(llm, "MODEL_ALIAS_MAP", {"gpt-eval": ("openai", "gpt-eval")})
    monkeypatch.setattr(
        llm,
        "PROVIDER_STATES",
        {
            "openai": llm.ProviderState(
                enabled=True, params={"api_key": "test-key"}, models=["gpt-eval"]
            )
        },
    )

    def complete(
        tool_name: str, arguments: str, **kwargs: object
    ) -> Iterator[SimpleNamespace]:
        assert not has_app_context()
        assert kwargs["no-log"] is True
        call = {
            "index": 0,
            "id": "test-tool-call",
            "function": {"name": tool_name, "arguments": arguments},
        }
        yield SimpleNamespace(
            id="test-response",
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=None, tool_calls=[call]),
                    finish_reason="tool_calls",
                )
            ],
            usage=None,
        )
        yield SimpleNamespace(
            id="test-response",
            choices=[],
            usage=SimpleNamespace(
                prompt_tokens=13, completion_tokens=4, total_tokens=17
            ),
        )

    def configure(tool_name: str, arguments: str) -> tuple[Mock, Mock]:
        completion = Mock(
            side_effect=lambda **kwargs: complete(tool_name, arguments, **kwargs)
        )
        monkeypatch.setattr(llm.litellm, "completion", completion)
        return completion, record_usage

    return configure


@pytest.mark.anyio
async def test_live_adapter_keeps_gateway_tools_and_usage_without_service_writes(
    configure_provider: Callable[[str, str], tuple[Mock, Mock]],
) -> None:
    from flaskr.api import llm

    completion, record_usage = configure_provider("interact", '{"question":"Choose?"}')
    with build_live_model("gpt-eval") as model:
        response = await model.request(
            [
                ModelRequest(
                    parts=[UserPromptPart("Choose a route.")],
                    instructions="Present the learner with two routes.",
                )
            ],
            {"temperature": 0.2},
            ModelRequestParameters(
                function_tools=[
                    ToolDefinition(
                        name="interact",
                        parameters_json_schema={"type": "object"},
                    )
                ],
            ),
        )

    completion.assert_called_once()
    request = completion.call_args.kwargs
    assert request["model"] == "openai/responses/gpt-eval"
    assert request["store"] is False
    assert request["temperature"] == 0.2
    assert request["messages"][0] == {
        "role": "system",
        "content": "Present the learner with two routes.",
    }
    assert request["tools"][0]["function"]["name"] == "interact"
    assert isinstance(response.parts[0], ToolCallPart)
    assert response.parts[0].args_as_dict() == {"question": "Choose?"}
    assert response.usage.input_tokens == 13
    assert response.usage.output_tokens == 4
    assert llm.record_llm_usage is record_usage
    record_usage.assert_not_called()


@pytest.mark.anyio
async def test_question_judge_sends_its_own_prompt_and_output_tool_through_gateway(
    configure_provider: Callable[[str, str], tuple[Mock, Mock]],
) -> None:
    completion, record_usage = configure_provider(
        "final_result",
        '{"asked":true,"reason":"The request preserves the required scope."}',
    )
    question = "哪种路线能最快到达学校？"
    prose = "请选出到学校用时最短的路线。"

    with build_live_model("gpt-eval") as model:
        judgment = await judge_question(model, intended_question=question, prose=prose)

    assert judgment.asked is True
    assert judgment.reason == "The request preserves the required scope."
    completion.assert_called_once()
    request = completion.call_args.kwargs
    assert request["model"] == "openai/responses/gpt-eval"
    assert request["store"] is False
    assert request["temperature"] == 0
    assert request["max_tokens"] == 512
    system, user = request["messages"]
    assert system == {"role": "system", "content": QUESTION_JUDGE_INSTRUCTIONS.strip()}
    assert user["role"] == "user"
    assert json.loads(user["content"]) == {
        "intended_question": question,
        "prose": prose,
    }
    (tool,) = request["tools"]
    assert tool["function"]["name"] == "final_result"
    assert tool["function"]["parameters"]["properties"]["asked"] == {"type": "boolean"}
    record_usage.assert_not_called()


def test_live_adapter_rejects_an_active_application_context() -> None:
    app = Flask(__name__)
    with (
        app.app_context(),
        pytest.raises(ValueError, match="requires a standalone process"),
        build_live_model("gpt-eval"),
    ):
        pytest.fail("live adapter entered a running application")
