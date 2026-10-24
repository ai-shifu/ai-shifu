"""Keep reported prefix-cache usage distinct from unsupported provider metadata."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn.agent import gateway_model as gateway
from flaskr.service.learn.agent.engine import ContinueTurn, Engine, Session
from pydantic_ai.models import ModelRequestParameters

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.anyio


def _chunk(usage: object, text: str = "Explanation.") -> SimpleNamespace:
    return SimpleNamespace(
        result=text, tool_call_deltas=[], finish_reason="stop", usage=usage
    )


async def _stream_usage(chunks: list[object]) -> object:
    response = gateway.GatewayStreamedResponse(
        model_request_parameters=ModelRequestParameters(),
        _model_name="cache-usage-test",
        _chunks=iter(chunks),
    )
    async for _ in response:
        pass
    return response.usage


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        (SimpleNamespace(prompt_tokens=100, completion_tokens=3, input_cache=40), 40),
        ({"prompt_tokens": 100, "completion_tokens": 3, "input_cache": 40}, 40),
        (
            {
                "prompt_tokens": 100,
                "completion_tokens": 3,
                "input_tokens_details": {"cached_tokens": 40},
            },
            40,
        ),
        (
            SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=3,
                prompt_tokens_details=SimpleNamespace(cached_tokens=40),
            ),
            40,
        ),
        (SimpleNamespace(prompt_tokens=100, completion_tokens=3, input_cache=0), 0),
    ],
)
async def test_supported_cache_usage_reaches_the_sdk(
    usage: object, expected: int
) -> None:
    result = await _stream_usage([_chunk(usage)])
    assert result.input_tokens == 100
    assert result.output_tokens == 3
    assert result.cache_read_tokens == expected
    assert result.details["mdf2_cache_reported_requests"] == 1
    assert result.details["mdf2_cache_reported_input_tokens"] == 100
    assert result.details["mdf2_cache_reported_read_tokens"] == expected


@pytest.mark.parametrize("cached", [None, -1, 101, True, "invalid", 1.5])
async def test_unknown_or_invalid_cache_counts_are_not_reported_zero(
    cached: object,
) -> None:
    result = await _stream_usage(
        [
            _chunk(
                SimpleNamespace(
                    prompt_tokens=100, completion_tokens=3, input_cache=cached
                )
            )
        ]
    )
    assert result.input_tokens == 100
    assert result.output_tokens == 3
    assert result.cache_read_tokens == 0
    assert "mdf2_cache_reported_requests" not in result.details


async def test_cumulative_stream_usage_is_not_added_twice() -> None:
    result = await _stream_usage(
        [
            _chunk(
                SimpleNamespace(prompt_tokens=100, completion_tokens=3, input_cache=40)
            ),
            _chunk(
                SimpleNamespace(prompt_tokens=120, completion_tokens=4, input_cache=60)
            ),
        ]
    )
    assert result.input_tokens == 120
    assert result.output_tokens == 4
    assert result.cache_read_tokens == 60
    assert result.details["mdf2_cache_reported_requests"] == 1
    assert result.details["mdf2_cache_reported_input_tokens"] == 120


async def test_nullable_direct_dictionary_field_does_not_override_shared_cache_policy() -> (
    None
):
    result = await _stream_usage(
        [
            _chunk(
                {
                    "prompt_tokens": 100,
                    "completion_tokens": 3,
                    "input_cache": None,
                    "prompt_tokens_details": {"cached_tokens": 40},
                }
            )
        ]
    )
    assert result.cache_read_tokens == 0
    assert "mdf2_cache_reported_requests" not in result.details


async def test_nested_object_in_dictionary_is_unknown_like_shared_gateway() -> None:
    result = await _stream_usage(
        [
            _chunk(
                {
                    "prompt_tokens": 100,
                    "completion_tokens": 3,
                    "prompt_tokens_details": SimpleNamespace(cached_tokens=40),
                }
            )
        ]
    )
    assert result.cache_read_tokens == 0
    assert "mdf2_cache_reported_requests" not in result.details


@pytest.mark.parametrize("prompt", [None, True, -1, 1.5, "100"])
async def test_missing_or_invalid_prompt_count_cannot_establish_cache_coverage(
    prompt: object,
) -> None:
    result = await _stream_usage(
        [
            _chunk(
                SimpleNamespace(
                    prompt_tokens=prompt, completion_tokens=3, input_cache=0
                )
            )
        ]
    )
    assert "mdf2_cache_reported_requests" not in result.details


async def test_cache_coverage_survives_reload_and_unknown_later_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usages = iter(
        [
            SimpleNamespace(prompt_tokens=100, completion_tokens=3, input_cache=40),
            SimpleNamespace(prompt_tokens=80, completion_tokens=3),
            SimpleNamespace(prompt_tokens=60, completion_tokens=3, input_cache=0),
        ]
    )
    calls = 0

    def chat(**kwargs: object) -> Iterator[SimpleNamespace]:
        nonlocal calls
        calls += 1
        kwargs["span"].generation(name=kwargs["generation_name"])
        yield _chunk(next(usages), text=f"Explanation number {calls}.")

    monkeypatch.setattr(gateway, "chat_llm", chat)
    model = gateway.GatewayModel(
        app=None,
        model="cache-usage-test",
        user_id="synthetic",
        span=SimpleNamespace(generation=lambda **_kwargs: None),
    )
    engine = Engine(model)
    session = await engine.new_session("Teach one short explanation per turn.")
    _ = [event async for event in engine.run_turn(session)]
    assert session.usage["cache_read_tokens"] == 40
    assert session.usage["cache_reported_requests"] == 1
    assert session.usage["cache_reported_input_tokens"] == 100
    session = Session.loads(session.dumps())
    _ = [event async for event in engine.run_turn(session, ContinueTurn())]
    assert session.usage["input_tokens"] == 180
    assert session.usage["cache_read_tokens"] == 40
    assert session.usage["cache_reported_requests"] == 1
    assert session.usage["cache_reported_input_tokens"] == 100
    _ = [event async for event in engine.run_turn(session, ContinueTurn())]
    assert session.usage["input_tokens"] == 240
    assert session.usage["cache_read_tokens"] == 40
    assert session.usage["cache_reported_requests"] == 2
    assert session.usage["cache_reported_input_tokens"] == 160
    assert session.usage["cache_reported_read_tokens"] == 40
    assert calls == 3
