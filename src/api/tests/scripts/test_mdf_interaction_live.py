"""Exercise the live adapter through the lesson gateway without a provider key."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flask import Flask, has_app_context
from pydantic_ai.messages import ModelRequest, ToolCallPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.tools import ToolDefinition
from scripts.mdf_interaction_live import build_live_model

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.mark.anyio
async def test_live_adapter_keeps_gateway_tools_and_usage_without_service_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.api import llm

    provider_calls = []
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

    def complete(**kwargs: object) -> Iterator[SimpleNamespace]:
        assert not has_app_context()
        assert kwargs["no-log"] is True
        provider_calls.append(kwargs)
        call = {
            "index": 0,
            "id": "test-tool-call",
            "function": {"name": "interact", "arguments": '{"question":"Choose?"}'},
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

    monkeypatch.setattr(llm.litellm, "completion", complete)
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

    assert len(provider_calls) == 1
    assert provider_calls[0]["model"] == "gpt-eval"
    assert provider_calls[0]["temperature"] == 0.2
    assert provider_calls[0]["messages"][0] == {
        "role": "system",
        "content": "Present the learner with two routes.",
    }
    assert provider_calls[0]["tools"][0]["function"]["name"] == "interact"
    assert isinstance(response.parts[0], ToolCallPart)
    assert response.parts[0].args_as_dict() == {"question": "Choose?"}
    assert response.usage.input_tokens == 13
    assert response.usage.output_tokens == 4
    assert llm.record_llm_usage is record_usage
    record_usage.assert_not_called()


def test_live_adapter_rejects_an_active_application_context() -> None:
    app = Flask(__name__)
    with (
        app.app_context(),
        pytest.raises(ValueError, match="requires a standalone process"),
        build_live_model("gpt-eval"),
    ):
        pytest.fail("live adapter entered a running application")
