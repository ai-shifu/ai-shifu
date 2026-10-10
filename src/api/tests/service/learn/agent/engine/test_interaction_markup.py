"""Recover a text imitation of interact without treating it as a learner answer."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import (
    ContentDelta,
    Engine,
    ErrorEvent,
    InteractionRequest,
    InteractionResponseTurn,
    MemoryUpdated,
    Session,
    TurnDone,
)
from flaskr.service.learn.agent.engine.interaction_markup import (
    InteractionMarkupFilter,
    contains_interaction_markup,
)
from pydantic_ai.messages import ModelMessage, ModelRequest, RetryPromptPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio

MARKUP = '<interact type="text" prompt="Explain program control" variable="answer" />'
SPEC = {
    "type": "text",
    "prompt": "Explain program control",
    "placeholder": "Your answer",
    "variable": "answer",
}


def _said(events: list[object]) -> str:
    return "".join(e.text for e in events if isinstance(e, ContentDelta))


async def test_markup_is_retried_as_a_real_question_and_answer_survives_reload() -> (
    None
):
    calls = 0

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            for character in "Explain program control.\n" + MARKUP:
                yield character
        elif calls == 2:
            assert any(
                isinstance(p, RetryPromptPart)
                for m in messages
                if isinstance(m, ModelRequest)
                for p in m.parts
            )
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(SPEC), tool_call_id="question"
                )
            }
        else:
            yield "Your answer has been received."

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Ask for %{{answer}}, then explain it.")
    events = [e async for e in engine.run_turn(session)]
    assert calls == 2
    assert _said(events) == "Explain program control.\n"
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "interaction"
    assert len([e for e in events if isinstance(e, InteractionRequest)]) == 1
    assert not session.finished
    assert not session.memory
    restored = Session.loads(session.dumps())
    answer_events = [
        e
        async for e in engine.run_turn(
            restored, InteractionResponseTurn(text="Instructions run automatically.")
        )
    ]
    assert restored.memory["answer"] == "Instructions run automatically."
    assert len([e for e in answer_events if isinstance(e, MemoryUpdated)]) == 1


async def test_repeated_markup_has_a_bounded_retry_and_never_finishes() -> None:
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        yield MARKUP

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Ask a question and wait for an answer.")
    events = [e async for e in engine.run_turn(session)]
    assert calls == 2
    assert any(isinstance(e, ErrorEvent) for e in events)
    assert not any(isinstance(e, TurnDone) and e.reason == "finished" for e in events)
    assert not session.finished
    assert not session.pending
    assert not session.memory
    assert _said(events) == ""


async def test_finish_cannot_replace_a_refused_markup_question() -> None:
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield MARKUP
        elif calls == 2:
            yield {
                0: DeltaToolCall(
                    name="finish",
                    json_args='{"summary":"done"}',
                    tool_call_id="wrong-finish",
                )
            }
        else:
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(SPEC), tool_call_id="question"
                )
            }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Ask a question and wait.")
    events = [e async for e in engine.run_turn(session)]
    assert any(isinstance(e, InteractionRequest) for e in events)
    assert not session.finished
    assert events[-1].reason == "interaction"


async def test_same_response_markup_and_finish_does_not_complete_the_lesson() -> None:
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield MARKUP + "\n"
            yield {
                0: DeltaToolCall(
                    name="finish",
                    json_args='{"summary":"done"}',
                    tool_call_id="wrong-finish",
                )
            }
        else:
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(SPEC), tool_call_id="question"
                )
            }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Ask a question and wait.")
    events = [e async for e in engine.run_turn(session)]
    assert any(isinstance(e, InteractionRequest) for e in events)
    assert not session.finished
    assert MARKUP not in _said(events)


@pytest.mark.parametrize(
    "text",
    [
        "```xml\n" + MARKUP + "\n```",
        "  ~~~~xml\n" + MARKUP + "\n  ~~~~",
        "    " + MARKUP,
        "`" + MARKUP + "`",
        "A literal example: " + MARKUP,
        "<div>Ordinary visual content</div>",
    ],
)
async def test_code_and_ordinary_content_remain_verbatim(text: str) -> None:
    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        for character in text:
            yield character

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Teach the author-provided example.")
    events = [e async for e in engine.run_turn(session)]
    assert _said(events) == text
    assert events[-1].reason == "end"


async def test_an_exact_authored_literal_tag_is_not_a_tool_request() -> None:
    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        yield MARKUP

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Show this literal example:\n" + MARKUP)
    events = [e async for e in engine.run_turn(session)]
    assert _said(events) == MARKUP
    assert events[-1].reason == "end"


@pytest.mark.parametrize("tag", [MARKUP, "  " + MARKUP, MARKUP.replace(" />", ">")])
def test_stream_filter_is_independent_of_every_two_chunk_boundary(tag: str) -> None:
    source = "Ordinary prose.\n" + tag + "\nMore prose."
    for cut in range(len(source) + 1):
        filter_ = InteractionMarkupFilter()
        actual = (
            filter_.feed(source[:cut]) + filter_.feed(source[cut:]) + filter_.flush()
        )
        assert actual == "Ordinary prose.\nMore prose."
        assert filter_.invalid
    assert contains_interaction_markup(source, frozenset())


def test_ordinary_prose_streams_immediately_and_incomplete_tags_are_retained() -> None:
    filter_ = InteractionMarkupFilter()
    assert (
        filter_.feed("A paragraph without a newline") == "A paragraph without a newline"
    )
    assert filter_.flush() == ""
    incomplete = '<interact type="text"'
    assert filter_.feed(incomplete) == ""
    assert filter_.flush() == incomplete
    assert not filter_.invalid


async def test_a_real_interact_in_the_same_response_hides_only_the_textual_copy() -> (
    None
):
    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        yield "Explain program control.\n" + MARKUP
        yield {
            0: DeltaToolCall(
                name="interact", json_args=json.dumps(SPEC), tool_call_id="question"
            )
        }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Ask a question and wait.")
    events = [e async for e in engine.run_turn(session)]
    assert _said(events) == "Explain program control.\n"
    assert len(session.pending) == 1
    assert not session.finished
    assert events[-1].reason == "interaction"


async def test_invalid_interact_and_finish_cannot_bypass_markup_recovery() -> None:
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield MARKUP + "\n"
            yield {
                0: DeltaToolCall(
                    name="interact",
                    json_args='{"type":"invalid"}',
                    tool_call_id="bad-question",
                ),
                1: DeltaToolCall(
                    name="finish",
                    json_args='{"summary":"done"}',
                    tool_call_id="wrong-finish",
                ),
            }
        else:
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(SPEC), tool_call_id="question"
                )
            }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Ask a question and wait.")
    events = [e async for e in engine.run_turn(session)]
    assert any(isinstance(e, InteractionRequest) for e in events)
    assert not session.finished
    assert events[-1].reason == "interaction"
