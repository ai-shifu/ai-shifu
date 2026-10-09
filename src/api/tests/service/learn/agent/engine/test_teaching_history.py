"""Exercise exact source reads and request-only long teaching projection."""

import asyncio
import json
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from flaskr.service.learn.agent.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    MessageTurn,
    Session,
    TurnDone,
)
from flaskr.service.learn.agent.engine.script import ScriptBundle
from flaskr.service.learn.agent.engine.teaching_history import (
    TEACHING_RESULT_BYTES,
    project_teaching_history,
    read_teaching,
)
from flaskr.service.learn.agent.engine.tools import LESSON_OVER, Deps
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel


def _history(text: str) -> list[ModelMessage]:
    return [
        ModelRequest(parts=[UserPromptPart("Full author script.")]),
        ModelResponse(
            parts=[TextPart(text), ToolCallPart("remember", {"value": text}, "write")],
            metadata={"original": True},
        ),
        ModelRequest(
            parts=[
                UserPromptPart("Complete long learner answer " * 1000),
                ToolReturnPart("remember", "stored", "write"),
            ]
        ),
        ModelResponse(parts=[TextPart("Previous teaching " * 1000)]),
        ModelRequest(
            parts=[
                ToolReturnPart("interact", "Complete most recent answer " * 1000, "q"),
                RetryPromptPart(
                    "Exact feedback.", tool_name="interact", tool_call_id="q"
                ),
            ]
        ),
        ModelResponse(parts=[TextPart("Most recent teaching " * 1000)]),
    ]


@pytest.mark.parametrize("text", ["x" * 6000, "中文é🙂" * 2000, '\n\t"\\' * 2000])
def test_only_old_long_text_changes_with_exact_metadata_calls_and_answers(
    text: str,
) -> None:
    history = _history(text)
    before = ModelMessagesTypeAdapter.dump_json(history)
    projected, sources = project_teaching_history(history)
    marker = json.loads(projected[1].parts[0].content)
    assert marker["status"] == "teaching_excerpt"
    assert marker["opening"] == text[:256]
    assert marker["ending"] == text[-128:]
    assert marker["characters"] == len(text)
    assert sources == {marker["reference"]: text}
    assert projected[1].metadata == history[1].metadata
    assert projected[1].parts[1] is history[1].parts[1]
    assert all(projected[i] is history[i] for i in (0, 2, 3, 4, 5))
    assert len(projected) == len(history)
    assert ModelMessagesTypeAdapter.dump_json(history) == before
    assert len(ModelMessagesTypeAdapter.dump_json(projected)) < len(before)
    assert project_teaching_history(history) == (projected, sources)


@pytest.mark.parametrize("size", [0, 10, 4094])
def test_small_teaching_remains_whole(size: int) -> None:
    history = _history("x" * size)
    assert project_teaching_history(history) == (history, {})


@pytest.mark.parametrize("length", [0, 2, 4])
def test_first_and_two_recent_turns_without_older_completed_boundary_stay_whole(
    length: int,
) -> None:
    history = _history("x" * 6000)[:length]
    assert project_teaching_history(history) == (history, {})


@pytest.mark.anyio
@pytest.mark.parametrize("text", ["abc" * 5000, "中文é🙂" * 4000, '\n\t"\\' * 4000])
async def test_bounded_pages_reconstruct_complete_original_unicode_and_escaping(
    text: str,
) -> None:
    _, sources = project_teaching_history(_history(text))
    reference = next(iter(sources))
    ctx = SimpleNamespace(
        deps=Deps(memory={}, user_memory={}, teaching_history=sources)
    )
    offset, chunks = 0, []
    while offset is not None:
        encoded = await read_teaching(ctx, reference, offset)
        assert len(encoded.encode("utf-8")) <= TEACHING_RESULT_BYTES
        page = json.loads(encoded)
        assert page["status"] == "found"
        assert page["offset"] == offset
        assert page["reference"] == reference
        assert page["text"]
        chunks.append(page["text"])
        assert page["next_offset"] is None or page["next_offset"] > offset
        offset = page["next_offset"]
    assert "".join(chunks) == text
    end = json.loads(await read_teaching(ctx, reference, len(text)))
    assert end["text"] == ""
    assert end["next_offset"] is None
    for invalid in (-1, len(text) + 1):
        assert json.loads(await read_teaching(ctx, reference, invalid)) == {
            "status": "invalid_offset"
        }
    assert sources[reference] == text


@pytest.mark.anyio
async def test_references_do_not_cross_sessions_rewinds_or_replaced_future_text() -> (
    None
):
    history = _history("Future exact teaching " * 1000)
    _, sources = project_teaching_history(history)
    reference = next(iter(sources))
    different = _history("Different lesson teaching " * 1000)
    snapshots = [
        {},
        project_teaching_history(history[:2])[1],
        project_teaching_history(different)[1],
    ]
    for snapshot in snapshots:
        ctx = SimpleNamespace(
            deps=Deps(memory={}, user_memory={}, teaching_history=snapshot)
        )
        assert json.loads(await read_teaching(ctx, reference)) == {
            "status": "unavailable"
        }
    ctx = SimpleNamespace(
        deps=Deps(memory={}, user_memory={}, teaching_history=sources, finished="done")
    )
    assert await read_teaching(ctx, reference) == LESSON_OVER


@pytest.mark.parametrize(
    "shape",
    [
        "valid",
        "duplicate_call",
        "duplicate_return",
        "unpaired",
        "wrong_name",
        "malformed",
        "future",
        "small",
        "recent",
        "bad_offset",
        "bad_next_offset",
        "bad_reference",
        "bad_text",
        "wrong_original",
    ],
)
def test_only_large_old_unique_recognized_read_results_shrink(shape: str) -> None:
    history = _history("x" * 6000)
    _, sources = project_teaching_history(history)
    reference = next(iter(sources))
    content = json.dumps(
        {
            "status": "found",
            "reference": reference,
            "offset": 0,
            "text": "x" * 6000,
            "next_offset": None,
        }
    )
    if shape == "malformed":
        content = "bad JSON " * 1000
    elif shape == "future":
        content = json.dumps({**json.loads(content), "new_field": True})
    elif shape == "small":
        content = json.dumps({"status": "unavailable"})
    elif shape in (
        "bad_offset",
        "bad_next_offset",
        "bad_reference",
        "bad_text",
        "wrong_original",
    ):
        value = json.loads(content)
        key, replacement = {
            "bad_offset": ("offset", True),
            "bad_next_offset": ("next_offset", True),
            "bad_reference": ("reference", [reference]),
            "bad_text": ("text", ["x"]),
            "wrong_original": ("text", "wrong" * 1000),
        }[shape]
        value[key] = replacement
        content = json.dumps(value)
    call = ToolCallPart(
        "other" if shape == "wrong_name" else "read_teaching",
        {"reference": reference},
        "read",
    )
    returned = ToolReturnPart("read_teaching", content, "read", metadata={"x": 1})
    # Insert after the original teaching: its content/position reference stays valid.
    history[2:2] = [ModelResponse(parts=[call]), ModelRequest(parts=[returned])]
    if shape == "duplicate_call":
        history[2].parts.append(call)
    elif shape == "duplicate_return":
        history[3].parts.append(returned)
    elif shape == "unpaired":
        history[2].parts.clear()
    elif shape == "recent":
        history[4].parts.insert(0, returned)
        history[3].parts.clear()
    projected, _ = project_teaching_history(history)
    if shape == "valid":
        marker = json.loads(projected[3].parts[0].content)
        assert marker["status"] == "teaching_read_compacted"
        assert marker["reference"] == reference
        assert projected[3].parts[0].metadata == {"x": 1}
    else:
        assert projected[3] == history[3]
        assert projected[4:] == history[4:]


def test_portable_defaults_have_no_new_tools_or_instructions() -> None:
    engine = Engine("test")
    assert engine.teaching_history_compaction is False
    assert "teaching_excerpt" not in engine.compose_instructions()


@pytest.mark.anyio
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("fail_first", [False, True])
async def test_actual_engine_preserves_answers_and_retrieves_original_after_reload_retry(
    enabled: bool, fail_first: bool
) -> None:
    text = "Original long teaching with exact CODE-712. " * 200
    history = _history(text)
    # Keep two recent turns, then ask a real pending interaction in the third.
    session = Session(script=ScriptBundle(script="Teach."))
    session.messages = history
    original = session.to_dict()["messages"]
    attempts, phase = 0, 0
    reference = next(iter(project_teaching_history(history)[1]))

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempts
        assert ("read_teaching" in {t.name for t in info.function_tools}) is enabled
        if phase == 0:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="pending",
                    json_args='{"type":"text","prompt":"Your complete answer?"}',
                )
            }
            return
        returns = [
            p
            for m in messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, ToolReturnPart)
        ]
        if returns[-1].tool_name == "read_teaching":
            assert (
                json.loads(returns[-1].content)["text"]
                == text[: json.loads(returns[-1].content)["next_offset"]]
            )
            yield "Use the exact code CODE-712 for the next step."
            return
        attempts += 1
        assert "Entire learner answer " * 1000 in str(returns[-1].content)
        first = messages[1].parts[0].content
        assert ('"teaching_excerpt"' in first) is enabled
        if fail_first and attempts == 1:
            message = "injected teaching-read transport failure"
            raise RuntimeError(message)
        if enabled:
            yield {
                0: DeltaToolCall(
                    name="read_teaching",
                    tool_call_id="fresh-read",
                    json_args=json.dumps({"reference": reference}),
                )
            }
        else:
            assert first == text
            yield "Continue using the complete original teaching."

    engine = Engine(
        FunctionModel(stream_function=model),
        memory_context_limit=32768,
        teaching_history_compaction=enabled,
    )
    await _events(engine, session, MessageTurn(text="Ask the next question."))
    assert session.pending
    phase = 1
    session = Session.loads(session.dumps())
    events = await _events(
        engine,
        session,
        InteractionResponseTurn(values=["Entire learner answer " * 1000]),
    )
    if fail_first:
        assert isinstance(events[-1], ErrorEvent)
        assert session.answers
        session = Session.loads(session.dumps())
        events = await _events(
            engine, session, MessageTurn(text="Retry without dropping the answer.")
        )
    assert isinstance(events[-1], TurnDone)
    assert not session.answers
    assert session.to_dict()["messages"][: len(original)] == original
    assert session.memory == {}
    assert session.user_memory == {}


async def _events(engine: Engine, session: Session, turn: object) -> list:
    return [event async for event in engine.run_turn(session, turn)]


@pytest.mark.anyio
async def test_one_engine_concurrently_reads_only_each_sessions_original_text() -> None:
    observed = []

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        if isinstance(messages[-1], ModelRequest) and isinstance(
            messages[-1].parts[-1], ToolReturnPart
        ):
            observed.append(json.loads(messages[-1].parts[-1].content)["text"])
            yield "Continue this lesson only."
        else:
            reference = json.loads(messages[1].parts[0].content)["reference"]
            await asyncio.sleep(0)
            yield {
                0: DeltaToolCall(
                    name="read_teaching",
                    tool_call_id="read",
                    json_args=json.dumps({"reference": reference}),
                )
            }

    engine = Engine(
        FunctionModel(stream_function=model), teaching_history_compaction=True
    )
    texts = ["Lesson A secret example " * 200, "Lesson B different example " * 200]
    sessions = [
        Session(script=ScriptBundle(script="Teach."), messages=_history(text))
        for text in texts
    ]
    originals = [session.to_dict()["messages"] for session in sessions]
    results = await asyncio.gather(
        *(
            _events(
                engine, session, MessageTurn(text="Read the exact earlier example.")
            )
            for session in sessions
        )
    )
    assert sorted(observed) == sorted(texts)
    assert all(isinstance(events[-1], TurnDone) for events in results)
    for session, original in zip(sessions, originals, strict=True):
        assert session.to_dict()["messages"][: len(original)] == original
