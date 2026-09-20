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


def _call(
    index: int = 0,
    name: str = "interact",
    arguments: str = '{"type":"confirm","prompt":"Continue?"}',
) -> dict:
    return {"index": index, "name": name, "arguments": arguments}


def test_a_model_that_calls_the_tool_can_teach(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _gateway(monkeypatch, [_Chunk(tool_call_deltas=[_call()])])

    result = capability.probe_model(_App(), "ark/some-model")

    assert result.can_teach is True
    # Probed through the same arguments a lesson uses: without these the answer is about a
    # different request than the one a turn makes.
    assert asked["emit_tool_calls"] is True
    assert asked["tools"][0]["function"]["name"] == "interact"
    assert asked["model"] == "ark/some-model"


def test_arguments_split_across_chunks_are_stitched_back_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider sends one call's arguments in pieces; the index is what joins them."""
    _gateway(
        monkeypatch,
        [
            _Chunk(tool_call_deltas=[_call(arguments='{"type":"conf')]),
            _Chunk(
                tool_call_deltas=[{"index": 0, "arguments": 'irm","prompt":"Go on?"}'}]
            ),
        ],
    )

    assert capability.probe_model(_App(), "m").can_teach is True


def test_a_call_that_never_completes_is_not_good_enough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fragments say the model reached for a tool, not that it produced a usable one.

    Approving on the fragment alone would pass a model that cannot actually give the learner
    controls -- the failure this probe exists to catch.
    """
    _gateway(
        monkeypatch,
        [
            _Chunk(
                tool_call_deltas=[_call(arguments='{"type":"conf')],
                finish_reason="tool_calls",
            )
        ],
    )

    result = capability.probe_model(_App(), "m")

    assert result.can_teach is False
    assert "did not complete" in result.detail


def test_a_stop_reason_with_nothing_behind_it_is_not_good_enough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider claiming a tool call while sending none has still sent none."""
    _gateway(monkeypatch, [_Chunk(finish_reason="tool_calls")])

    result = capability.probe_model(_App(), "m")

    assert result.can_teach is False
    assert "did not complete" in result.detail


def test_a_call_to_something_else_is_not_the_tool_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _gateway(monkeypatch, [_Chunk(tool_call_deltas=[_call(name="search")])])

    result = capability.probe_model(_App(), "m")

    assert result.can_teach is False
    assert "called search" in result.detail


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
