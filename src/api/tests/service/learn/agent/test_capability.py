"""Cover how a model's fitness for a 2.0 lesson is decided.

The decision is made by asking the model, not by looking it up: every model this deployment
routes through its own gateway is reported as unable to call tools by
`litellm.supports_function_calling`, while those models do call them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flaskr.service.learn.agent import capability

if TYPE_CHECKING:
    import pytest


class _App:
    logger = logging.getLogger("test_capability")


class _Chunk:
    def __init__(
        self, tool_call_deltas: list | None = None, finish_reason: str = ""
    ) -> None:
        self.tool_call_deltas = tool_call_deltas or []
        self.finish_reason = finish_reason


def _gateway(monkeypatch: pytest.MonkeyPatch, chunks: object) -> dict:
    """Stand in for the gateway, recording what the probe asked it for."""
    asked: dict = {}
    monkeypatch.setattr(
        capability,
        "create_trace_with_root_span",
        lambda **_kwargs: (object(), object()),
    )
    monkeypatch.setattr(capability, "get_langfuse_client", object)
    monkeypatch.setattr(capability, "finalize_langfuse_trace", asked.update)

    def _chat_llm(**kwargs: object) -> object:
        asked.update(kwargs)
        if isinstance(chunks, Exception):
            raise chunks
        return iter(chunks)

    monkeypatch.setattr(capability, "chat_llm", _chat_llm)
    return asked


def test_a_model_that_calls_the_tool_can_teach(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _gateway(monkeypatch, [_Chunk(tool_call_deltas=[{"index": 0}])])

    result = capability.probe_model(_App(), "ark/some-model")

    assert result.can_teach is True
    # Probed through the same arguments a lesson uses: without these the answer is about a
    # different request than the one a turn makes.
    assert asked["emit_tool_calls"] is True
    assert asked["tools"][0]["function"]["name"] == "interact"
    assert asked["model"] == "ark/some-model"


def test_a_provider_that_reports_a_tool_call_stop_counts_as_calling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Some providers report the stop reason without a delta the probe can see."""
    _gateway(monkeypatch, [_Chunk(finish_reason="tool_calls")])

    assert capability.probe_model(_App(), "m").can_teach is True


def test_a_model_that_answers_in_prose_cannot_teach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It would write the question as text, and the learner would have nothing to answer."""
    _gateway(monkeypatch, [_Chunk(finish_reason="stop")])

    result = capability.probe_model(_App(), "m")

    assert result.can_teach is False
    assert "stopped on stop" in result.detail


def test_a_model_that_cannot_be_reached_cannot_teach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure is an answer too, and the detail says which one it was."""
    _gateway(monkeypatch, RuntimeError("Model no-such-model is not supported"))

    result = capability.probe_model(_App(), "no-such-model")

    assert result.can_teach is False
    assert "the gateway call failed" in result.detail
    assert "not supported" in result.detail
