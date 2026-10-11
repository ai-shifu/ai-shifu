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
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio

MARKUP = '<interact type="text" prompt="Explain program control" variable="answer" />'
PAIRED_MARKUP = MARKUP.removesuffix(" />") + "></interact>"
PAIRED_NAVIGATION = (
    '<interact type="single" prompt="Continue" options="[{"display":"Next"}]">'
    "</interact>"
)
SPEC = {
    "type": "text",
    "prompt": "Explain program control",
    "placeholder": "Your answer",
    "variable": "answer",
}


def _said(events: list[object]) -> str:
    return "".join(e.text for e in events if isinstance(e, ContentDelta))


@pytest.mark.parametrize("markup", [MARKUP, PAIRED_MARKUP])
async def test_markup_is_retried_as_a_real_question_and_answer_survives_reload(
    markup: str,
) -> None:
    calls = 0

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            for character in "Explain program control.\n" + markup:
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
        elif calls == 3:
            yield "Your answer has been received."
        elif calls == 4:
            yield {
                0: DeltaToolCall(
                    name="finish",
                    json_args='{"summary":"done"}',
                    tool_call_id="finish-after-answer",
                )
            }
        else:
            yield "After finish."

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
    final_events = [e async for e in engine.run_turn(restored)]
    assert restored.finished
    assert not any(isinstance(e, ErrorEvent) for e in final_events)
    assert final_events[-1].reason == "finished"


@pytest.mark.parametrize("markup", [MARKUP, PAIRED_MARKUP, PAIRED_NAVIGATION])
async def test_repeated_markup_has_a_bounded_retry_and_never_finishes(
    markup: str,
) -> None:
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        yield markup

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


@pytest.mark.parametrize("markup", [MARKUP, PAIRED_NAVIGATION])
async def test_finish_cannot_replace_a_refused_markup_question(markup: str) -> None:
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield markup
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


@pytest.mark.parametrize("markup", [MARKUP, PAIRED_NAVIGATION])
async def test_same_response_markup_and_finish_does_not_complete_the_lesson(
    markup: str,
) -> None:
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield markup + "\n"
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
    assert markup not in _said(events)


async def test_paired_navigation_after_an_answer_requires_an_actual_click() -> None:
    calls = 0
    navigation = {
        "type": "single",
        "prompt": "Continue",
        "options": [{"display": "Next"}],
    }

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            spec, call_id = SPEC, "answer"
        elif calls == 2:
            yield "Accepted.\n" + PAIRED_NAVIGATION
            return
        elif calls == 3:
            assert any(
                isinstance(p, RetryPromptPart) for m in messages for p in m.parts
            )
            spec, call_id = navigation, "navigation"
        else:
            assert calls == 4, "Unexpected extra model request"
            yield "The next question.\n"
            spec, call_id = SPEC, "next-question"
        yield {
            0: DeltaToolCall(
                name="interact", json_args=json.dumps(spec), tool_call_id=call_id
            )
        }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session(
        "Collect %{{answer}}, explain it, ask ?[Next], then ask another question."
    )
    _ = [event async for event in engine.run_turn(session)]
    restored = Session.loads(session.dumps())
    events = [
        event
        async for event in engine.run_turn(
            restored, InteractionResponseTurn(text="Original answer.")
        )
    ]
    assert calls == 3
    assert _said(events) == "Accepted.\n"
    assert len(restored.pending) == 1
    assert restored.pending[0].spec.type == "single"
    assert restored.memory["answer"] == "Original answer."
    assert not restored.finished
    assert not any(isinstance(e, ErrorEvent) for e in events)
    after_click = [
        event
        async for event in engine.run_turn(
            Session.loads(restored.dumps()), InteractionResponseTurn(values=["Next"])
        )
    ]
    assert calls == 4
    assert _said(after_click) == "The next question.\n"


@pytest.mark.parametrize(
    "text",
    [
        "```xml\n" + MARKUP + "\n```",
        "  ~~~~xml\n" + MARKUP + "\n  ~~~~",
        "    " + MARKUP,
        "`" + MARKUP + "`",
        "A literal example: " + MARKUP,
        "<div>Ordinary visual content</div>",
        "<interact-card>",
        "<interact:widget>",
        "```xml\n" + PAIRED_MARKUP + "\n```",
        "    " + PAIRED_MARKUP,
        "A literal example: " + PAIRED_MARKUP,
        "<interact>Illustrative content</interact>",
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


@pytest.mark.parametrize("markup", [MARKUP, PAIRED_MARKUP, PAIRED_NAVIGATION])
async def test_an_exact_authored_literal_tag_is_not_a_tool_request(markup: str) -> None:
    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        yield markup

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Show this literal example:\n" + markup)
    events = [e async for e in engine.run_turn(session)]
    assert _said(events) == markup
    assert events[-1].reason == "end"


@pytest.mark.parametrize(
    "tag",
    [
        MARKUP,
        "  " + MARKUP,
        MARKUP.replace(" />", ">"),
        PAIRED_MARKUP,
        PAIRED_NAVIGATION,
        "   " + PAIRED_MARKUP,
    ],
)
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


@pytest.mark.parametrize("markup", [MARKUP, PAIRED_MARKUP])
async def test_a_real_interact_in_the_same_response_hides_only_the_textual_copy(
    markup: str,
) -> None:
    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        yield "Explain program control.\n" + markup
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


async def test_saved_unfinished_markup_cannot_be_completed_by_a_new_finish() -> None:
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
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
    session.messages = [
        ModelRequest(parts=[UserPromptPart(content="Ask a question and wait.")]),
        ModelResponse(parts=[TextPart(content=MARKUP)]),
    ]
    session.turn = 1
    restored = Session.loads(session.dumps())
    events = [e async for e in engine.run_turn(restored)]
    assert any(isinstance(e, InteractionRequest) for e in events)
    assert not restored.finished
    assert events[-1].reason == "interaction"


async def test_an_intervening_read_does_not_discard_the_unanswered_question() -> None:
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield MARKUP
            yield {
                0: DeltaToolCall(
                    name="recall", json_args='{"key":"pace"}', tool_call_id="read"
                )
            }
        elif calls == 2:
            yield "Let's proceed."
        else:
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(SPEC), tool_call_id="question"
                )
            }

    engine = Engine(FunctionModel(stream_function=model), memory_recall=True)
    session = await engine.new_session(
        "Ask a question and wait.", memory={"pace": "steady"}
    )
    events = [e async for e in engine.run_turn(session)]
    assert calls == 3
    assert any(isinstance(e, InteractionRequest) for e in events)
    assert not session.finished
    assert session.memory == {"pace": "steady"}
    assert events[-1].reason == "interaction"
