"""Exercise semantic derivatives without changing exact teaching evidence."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn.agent.engine import Engine, MessageTurn, Session, TurnDone
from flaskr.service.learn.agent.engine.script import ScriptBundle
from flaskr.service.learn.agent.engine.teaching_history import (
    project_teaching_history,
    read_teaching,
)
from flaskr.service.learn.agent.engine.teaching_summary import (
    SUMMARY_CACHE_ENTRIES,
    TeachingSummarizer,
    summarize_teaching_history,
)
from flaskr.service.learn.agent.engine.tools import Deps
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def history(
    turns: int = 3, text: str = "Exact old teaching. " * 400
) -> list[ModelMessage]:
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart("Exact author script")])
    ]
    for index in range(turns):
        messages.append(ModelResponse(parts=[TextPart(f"{index}: {text}")]))
        if index < turns - 1:
            messages.append(
                ModelRequest(parts=[UserPromptPart(f"Exact answer {index}")])
            )
    return messages


@pytest.mark.anyio
async def test_summary_retains_exact_opening_ending_original_reads_and_recent_turns() -> (
    None
):
    original = history()
    before = ModelMessagesTypeAdapter.dump_json(original)
    projected, sources = project_teaching_history(original)
    seen = []

    async def summarize(text: str) -> str:
        seen.append(text)
        return "Already explained the original concept and its distinction."

    cache: dict[str, str] = {}
    result = await summarize_teaching_history(
        projected, sources, cache, TeachingSummarizer("v1", summarize)
    )
    marker = json.loads(result[1].parts[0].content)
    assert marker["status"] == "teaching_summary"
    assert (
        marker["summary"]
        == "Already explained the original concept and its distinction."
    )
    assert seen == list(sources.values())
    assert marker["opening"] == seen[0][:256]
    assert marker["ending"] == seen[0][-128:]
    assert all(result[i] is original[i] for i in (0, 2, 3, 4, 5))
    assert len(result) == len(original)
    assert ModelMessagesTypeAdapter.dump_json(original) == before
    ctx = SimpleNamespace(
        deps=Deps(memory={}, user_memory={}, teaching_history=sources)
    )
    text, offset = "", 0
    while offset is not None:
        page = json.loads(await read_teaching(ctx, marker["reference"], offset))
        text += page["text"]
        offset = page["next_offset"]
    assert text == seen[0]
    assert (
        await summarize_teaching_history(
            projected, sources, cache, TeachingSummarizer("v1", summarize)
        )
        == result
    )
    assert len(seen) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "output", [None, "", "   ", "🙂" * 300, "\\" * 600, 42, "error"]
)
async def test_invalid_or_failed_output_falls_back_and_is_not_retried(
    output: object,
) -> None:
    projected, sources = project_teaching_history(history())
    calls = 0

    async def summarize(_text: str) -> object:
        nonlocal calls
        calls += 1
        if output == "error":
            message = "provider unavailable"
            raise RuntimeError(message)
        return output

    cache: dict[str, str] = {}
    for _ in range(2):
        assert (
            await summarize_teaching_history(
                projected, sources, cache, TeachingSummarizer("v1", summarize)
            )
            == projected
        )
    assert calls == 1
    assert list(cache.values()) == [""]


@pytest.mark.anyio
async def test_one_call_per_turn_bounded_cache_and_current_source_policy_binding() -> (
    None
):
    projected, sources = project_teaching_history(history(100))
    seen = []

    async def summarize(text: str) -> str:
        seen.append(text)
        return "Semantic overview."

    cache = {"stale-policy:unrelated-source": "Do not use."}
    provider = TeachingSummarizer("v1", summarize)
    for _ in range(70):
        await summarize_teaching_history(projected, sources, cache, provider)
        assert len(cache) <= SUMMARY_CACHE_ENTRIES
    assert len(seen) == SUMMARY_CACHE_ENTRIES
    assert "stale-policy:unrelated-source" not in cache
    assert all(key.startswith("v1:") for key in cache)
    assert next(iter(sources.values())) not in seen
    await summarize_teaching_history(
        projected, sources, cache, TeachingSummarizer("v2", summarize)
    )
    assert len(seen) == SUMMARY_CACHE_ENTRIES + 1
    assert len(cache) == 1
    assert all(key.startswith("v2:") for key in cache)
    # A different lesson or regenerated text cannot reuse the old digest.
    other, other_sources = project_teaching_history(
        history(text="Different original. " * 400)
    )
    await summarize_teaching_history(other, other_sources, cache, provider)
    assert len(seen) == SUMMARY_CACHE_ENTRIES + 2
    assert len(cache) == 1
    await summarize_teaching_history([], {}, cache, provider)
    assert cache == {}


@pytest.mark.anyio
async def test_oversized_complete_sources_are_never_truncated_or_sent() -> None:
    projected, sources = project_teaching_history(history(text="\u4e2d\u6587" * 10_000))

    async def summarize(_text: str) -> str:
        pytest.fail("oversized source reached summarizer")

    cache: dict[str, str] = {}
    assert (
        await summarize_teaching_history(
            projected, sources, cache, TeachingSummarizer("v1", summarize)
        )
        == projected
    )
    assert list(cache.values()) == [""]


@pytest.mark.anyio
async def test_cancellation_is_not_swallowed_as_an_optional_summary_failure() -> None:
    projected, sources = project_teaching_history(history())

    async def summarize(_text: str) -> str:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await summarize_teaching_history(
            projected, sources, {}, TeachingSummarizer("v1", summarize)
        )


@pytest.mark.anyio
async def test_engine_roundtrip_reuses_derivative_and_persists_only_original_messages() -> (
    None
):
    session = Session(script=ScriptBundle(script="Teach next."), messages=history())
    original = ModelMessagesTypeAdapter.dump_json(session.messages)
    seen = []

    async def summarize(source: str) -> str:
        seen.append(source)
        return "The earlier concept was already explained."

    async def stream(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        assert json.loads(messages[1].parts[0].content)["status"] == "teaching_summary"
        yield "Continue with the next concept."

    engine = Engine(
        FunctionModel(stream_function=stream),
        teaching_history_compaction=True,
        teaching_summarizer=TeachingSummarizer("v1", summarize),
    )
    events = [
        event async for event in engine.run_turn(session, MessageTurn(text="Next."))
    ]
    assert any(isinstance(event, TurnDone) for event in events)
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:6]) == original
    restored = Session.loads(session.dumps())
    assert restored.teaching_summaries == session.teaching_summaries
    assert restored.memory == {}
    # Re-project the same historical boundary without another paid request.
    projected, sources = project_teaching_history(restored.messages[:6])
    await summarize_teaching_history(
        projected, sources, restored.teaching_summaries, engine.teaching_summarizer
    )
    assert len(seen) == 1
    legacy = session.to_dict()
    legacy.pop("teaching_summaries")
    assert Session.from_dict(legacy).teaching_summaries == {}


def test_summary_option_requires_exact_history_reads() -> None:
    async def summarize(_text: str) -> str:
        return "overview"

    with pytest.raises(ValueError, match="require teaching history compaction"):
        Engine(
            FunctionModel(
                lambda _messages, _info: ModelResponse(parts=[TextPart("ok")])
            ),
            teaching_summarizer=TeachingSummarizer("v1", summarize),
        )
