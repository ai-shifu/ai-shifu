"""Language context is current configuration, never learner history."""

import copy

import pytest
from flaskr.service.learn.agent.engine import Engine
from flaskr.service.learn.agent.engine.output_language import language_request_history
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel


@pytest.mark.parametrize("language", ["English", "French", "", None])
def test_projection_replaces_only_engine_context_and_keeps_tool_pairing(
    language: str | None,
) -> None:
    original = [
        ModelRequest(parts=[UserPromptPart(content="Teach in the original language.")]),
        ModelResponse(parts=[ToolCallPart("interact", {}, "question")]),
        ModelRequest(parts=[ToolReturnPart("interact", "stable-answer", "question")]),
    ]
    old_projection = language_request_history(original, "Old language")
    snapshot = copy.deepcopy(old_projection)
    projected = language_request_history(old_projection, language)
    assert old_projection == snapshot
    assert projected[:3] == original
    assert len(projected) == (3 if language is None else 4)
    assert "Old language" not in str(projected)
    assert language_request_history(projected, None) == original
    if language:
        assert (
            f"current output language is {language}" in projected[-1].parts[0].content
        )
    elif language == "":
        assert "Multilingual teaching is disabled" in projected[-1].parts[0].content


def test_native_configuration_is_independent_of_host_extensions() -> None:
    engine = Engine(
        FunctionModel(lambda *_: None), extra_instructions="Host capability."
    )
    before = engine.compose_instructions()
    engine.output_language = "English"
    configured = engine.compose_instructions(uses_v1_syntax=True)
    assert "Host capability." in configured
    assert "current output language is English" in configured
    assert "For Display//value translate only Display" in configured
    engine.output_language = None
    assert engine.compose_instructions() == before
