"""Exercise history projection without rewriting saved teaching evidence."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    MessageTurn,
    ScriptBundle,
    Session,
    TurnDone,
)
from flaskr.service.learn.agent.engine.history_context import (
    compact_recall_history,
    current_recall_notice,
)
from flaskr.service.learn.agent.engine.tools import Deps
from pydantic_ai import RunContext
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


def _history(content: object, name: str = "recall") -> list[ModelMessage]:
    return [
        ModelRequest(parts=[UserPromptPart("Original script and memory.")]),
        ModelResponse(
            parts=[TextPart("Delivered teaching."), ToolCallPart(name, {}, "old")]
        ),
        ModelRequest(parts=[ToolReturnPart(name, content, "old", metadata={"x": 1})]),
        ModelResponse(parts=[TextPart("A complete useful example.")]),
        ModelRequest(parts=[UserPromptPart("The most recent learner request.")]),
        ModelResponse(parts=[ToolCallPart("recall", {"key": "goal"}, "recent")]),
        ModelRequest(parts=[ToolReturnPart("recall", content, "recent")]),
        ModelResponse(parts=[TextPart("Latest useful teaching.")]),
    ]


@pytest.mark.parametrize("value", ["x" * 4000, "é🙂" * 600, '\n\t"\\' * 500])
@pytest.mark.parametrize("status", ["found", "keys"])
def test_only_older_complete_results_shrink_and_source_bytes_stay_exact(
    value: str, status: str
) -> None:
    content = json.dumps(
        {
            "status": status,
            **(
                {"value": value}
                if status == "found"
                else {"keys": [value], "next_offset": None, "skipped": 0}
            ),
        },
        ensure_ascii=False,
    )
    original = _history(content)
    before = ModelMessagesTypeAdapter.dump_json(original)
    projected = compact_recall_history(original)
    assert json.loads(projected[2].parts[0].content)["status"] == "history_compacted"
    assert projected[2].parts[0].tool_call_id == "old"
    assert projected[2].parts[0].metadata == {"x": 1}
    assert projected[6].parts[0].content == content
    assert all(projected[i] is original[i] for i in (0, 1, 3, 4, 5, 6, 7))
    assert ModelMessagesTypeAdapter.dump_json(original) == before
    assert len(ModelMessagesTypeAdapter.dump_json(projected)) < len(before)
    assert compact_recall_history(projected) == projected


@pytest.mark.parametrize(
    "content",
    [
        '{"status":"found","value":"short"}',
        '{"status":"unavailable"}',
        '{"status":"too_large"}',
        "malformed " * 100,
        json.dumps(["large" * 100]),
        json.dumps({"status": "future", "value": "x" * 4000}),
        json.dumps({"status": ["found"], "value": "x" * 4000}),
        json.dumps({"status": {"found": True}, "value": "x" * 4000}),
        json.dumps({"status": "found", "unknown": "x" * 4000}),
        json.dumps({"status": "found", "value": "x" * 4000, "future": True}),
        json.dumps(
            {"status": "keys", "keys": "x" * 4000, "next_offset": None, "skipped": 0}
        ),
        json.dumps(
            {"status": "keys", "keys": ["x" * 4000], "next_offset": -1, "skipped": 0}
        ),
        json.dumps(
            {
                "status": "keys",
                "keys": ["x" * 4000],
                "next_offset": None,
                "skipped": True,
            }
        ),
        json.dumps({"status": "keys", "keys": ["x" * 4000]}),
        {"status": "found", "value": "x" * 4000},
    ],
)
def test_small_unsuccessful_unknown_or_non_string_results_remain_intact(
    content: object,
) -> None:
    history = _history(content)
    assert compact_recall_history(history) == history


@pytest.mark.parametrize("name", ["interact", "remember", "custom_lookup"])
def test_answers_memory_writes_and_custom_tools_are_not_compressed(name: str) -> None:
    history = _history(json.dumps({"status": "found", "value": "x" * 5000}), name)
    assert compact_recall_history(history) == history


@pytest.mark.parametrize(
    "shape", ["unpaired", "wrong_name", "duplicate_call", "duplicate_result"]
)
def test_ambiguous_or_unpaired_calls_fail_closed(shape: str) -> None:
    history = _history(json.dumps({"status": "found", "value": "x" * 5000}))
    if shape == "unpaired":
        history[1].parts.pop()
    elif shape == "wrong_name":
        history[1].parts[-1].tool_name = "other"
    elif shape == "duplicate_call":
        history[1].parts.append(ToolCallPart("recall", {}, "old"))
    else:
        history[2].parts.append(ToolReturnPart("recall", "duplicate", "old"))
    assert compact_recall_history(history) == history


def test_first_turn_and_pending_calls_remain_complete() -> None:
    history = _history(json.dumps({"status": "found", "value": "x" * 5000}))[:4]
    history.append(ModelResponse(parts=[ToolCallPart("interact", {}, "pending")]))
    assert compact_recall_history(history) == history
    assert compact_recall_history([]) == []


def test_answer_boundary_preserves_full_answer_retry_and_mixed_tool_results() -> None:
    content = json.dumps({"status": "found", "value": "x" * 5000})
    history = _history(content)
    history[4] = ModelRequest(
        parts=[
            ToolReturnPart("interact", "exact learner answer " * 1000, "question"),
            ToolReturnPart("recall", content, "mixed"),
            RetryPromptPart(
                "Use the declared schema.", tool_name="recall", tool_call_id="retry"
            ),
        ]
    )
    projected = compact_recall_history(history)
    assert projected[4:] == history[4:]
    assert json.loads(projected[2].parts[0].content)["status"] == "history_compacted"


def test_compaction_requires_a_read_tool_and_portable_defaults_stay_off() -> None:
    with pytest.raises(ValueError, match="requires memory recall"):
        Engine("test", recall_history_compaction=True)
    engine = Engine("test", memory_recall=True)
    assert engine.recall_history_compaction is False
    assert "history_compacted" not in engine.compose_instructions()


@pytest.mark.anyio
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("fail_first", [False, True])
async def test_real_engine_reloads_answers_retries_and_fresh_recall_without_rewriting_history(
    enabled: bool, fail_first: bool
) -> None:
    value = "Original permitted fact " + "é" * 2000
    current = "Updated current fact " + "z" * 2000
    phase = 0
    attempts = 0
    snapshots = []

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempts
        returns = [
            p
            for m in messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, ToolReturnPart)
        ]
        last = returns[-1] if returns else None
        if phase == 0:
            if last:
                assert json.loads(last.content) == {"status": "found", "value": value}
                yield "First useful teaching."
            else:
                yield {
                    0: DeltaToolCall(
                        name="recall", tool_call_id="first", json_args='{"key":"goal"}'
                    )
                }
        elif phase == 1:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="q",
                    json_args='{"type":"text","prompt":"Your answer?","variable":"answer"}',
                )
            }
        elif last.tool_name == "interact":
            attempts += 1
            snapshots.append(messages)
            assert "Complete learner answer" in str(last.content)
            old = json.loads(returns[0].content)
            assert old == (
                {
                    "status": "history_compacted",
                    "notice": "An older recall result was omitted. Call recall again if needed.",
                }
                if enabled
                else {"status": "found", "value": value}
            )
            if fail_first and attempts == 1:
                message = "injected transport failure"
                raise RuntimeError(message)
            yield {
                0: DeltaToolCall(
                    name="recall", tool_call_id="fresh", json_args='{"key":"goal"}'
                )
            }
        else:
            assert json.loads(last.content) == {"status": "found", "value": current}
            yield "Apply the current fact."

    engine = Engine(
        FunctionModel(stream_function=model),
        memory_recall=True,
        recall_history_compaction=enabled,
    )
    session = await engine.new_session(
        "Teach. Ask %{{answer}}.", memory={"goal": value}
    )
    _ = [e async for e in engine.run_turn(session)]
    phase = 1
    _ = [
        e
        async for e in engine.run_turn(
            session, MessageTurn(text="Ask the question now.")
        )
    ]
    before = session.to_dict()["messages"]
    phase = 2
    session.memory["goal"] = current
    session = Session.loads(session.dumps())
    answer = "Complete learner answer " + "é" * 3000
    events = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(id="q", values=[answer])
        )
    ]
    if fail_first:
        assert isinstance(events[-1], ErrorEvent)
        assert session.to_dict()["messages"] == before
        assert session.answers
        session = Session.loads(session.dumps())
        events = [e async for e in engine.run_turn(session)]
    assert isinstance(events[-1], TurnDone)
    assert not session.answers
    assert not session.pending
    assert session.memory == {"goal": current, "answer": answer}
    assert session.to_dict()["messages"][: len(before)] == before
    assert len(snapshots) == (2 if fail_first else 1)
    assert all(
        "history_compacted" not in str(p.content)
        for m in session.messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    )


@pytest.mark.parametrize("current", [{"goal": "new"}, {}])
def test_current_notice_flags_changed_reads_without_values_or_history_changes(
    current: dict,
) -> None:
    messages = _history(json.dumps({"status": "found", "value": "SECRET_OLD_VALUE"}))
    before = ModelMessagesTypeAdapter.dump_json(messages)
    notice = current_recall_notice(messages, current)
    assert "Revalidate earlier recalled facts" in notice
    assert '"goal"' in notice
    assert "SECRET_OLD_VALUE" not in notice
    assert ModelMessagesTypeAdapter.dump_json(messages) == before


@pytest.mark.parametrize(
    ("previous", "current"), [(False, 0), ([False], [0]), ("old", "new")]
)
def test_current_notice_preserves_json_type_distinctions(
    previous: object, current: object
) -> None:
    messages = _history(json.dumps({"status": "found", "value": previous}))
    assert current_recall_notice(messages, {"goal": current})


@pytest.mark.parametrize("deleted", [False, True])
def test_latest_current_read_clears_the_stale_notice(deleted: bool) -> None:
    messages = _history(json.dumps({"status": "found", "value": "old"}))
    current = {} if deleted else {"goal": "new"}
    result = (
        {"status": "unavailable"} if deleted else {"status": "found", "value": "new"}
    )
    messages.extend(
        [
            ModelResponse(parts=[ToolCallPart("recall", {"key": "goal"}, "current")]),
            ModelRequest(
                parts=[ToolReturnPart("recall", json.dumps(result), "current")]
            ),
        ]
    )
    assert current_recall_notice(messages, current) == ""


def test_unchanged_snapshot_has_no_dynamic_notice_but_exclusion_invalidates_it() -> (
    None
):
    messages = _history(json.dumps({"status": "found", "value": "old"}))
    assert current_recall_notice(messages, {"goal": "old"}) == ""
    assert current_recall_notice(
        messages, {"goal": "old"}, excluded=frozenset({"goal"})
    )


@pytest.mark.parametrize("content", ["not-json", "[]", "null", '{"status":"future"}'])
def test_unknown_historical_results_do_not_break_instructions(content: str) -> None:
    assert current_recall_notice(_history(content), {}) == ""


def test_compacted_reads_need_revalidation_and_notice_size_is_bounded() -> None:
    messages = []
    for n in range(40):
        key = "k" + str(n) + "x" * 100
        messages.extend(
            [
                ModelResponse(parts=[ToolCallPart("recall", {"key": key}, str(n))]),
                ModelRequest(
                    parts=[
                        ToolReturnPart(
                            "recall", '{"status":"history_compacted"}', str(n)
                        )
                    ]
                ),
            ]
        )
    notice = current_recall_notice(messages, {})
    assert len(notice) < 1700
    assert "Additional unlisted keys:" in notice
    assert "Revalidate earlier recalled facts" in notice


@pytest.mark.anyio
async def test_engine_revalidates_stale_read_and_clears_notice_after_current_tool() -> (
    None
):
    original = _history(json.dumps({"status": "found", "value": "old"}))
    before = ModelMessagesTypeAdapter.dump_json(original)
    phases = []
    question = "What is my goal?"

    class CheckingEngine(Engine):
        def _instructions(self, ctx: RunContext[Deps]) -> str:
            assert ctx.deps.request_inputs == (question,)
            assert ctx.deps.memory_current_inputs == (question,)
            return super()._instructions(ctx)

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        phases.append(messages[-1].instructions)
        if len(phases) == 1:
            assert "Revalidate earlier recalled facts" in phases[-1]
            current_input = next(
                part.content
                for part in messages[-1].parts
                if isinstance(part, UserPromptPart)
            )
            assert current_input.startswith("<memory_context>Host memory revalidation")
            assert current_input.endswith(question)
            assert session.request_inputs == [question]
            yield {
                0: DeltaToolCall(
                    name="recall", tool_call_id="current", json_args='{"key":"goal"}'
                )
            }
        else:
            assert "Revalidate earlier recalled facts" not in phases[-1]
            yield "new"
            yield {
                0: DeltaToolCall(
                    name="finish", tool_call_id="done", json_args='{"summary":"done"}'
                )
            }

    session = Session(
        script=ScriptBundle(script="Answer the learner's question and finish."),
        user_memory={"goal": "profile-old"},
        memory={"goal": "new"},
        messages=original,
        initial_variables={},
        turn=1,
    )
    engine = CheckingEngine(
        FunctionModel(stream_function=model), memory_recall=True, memory_admission=True
    )
    events = [
        event async for event in engine.run_turn(session, MessageTurn(text=question))
    ]
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert any(
        isinstance(event, TurnDone) and event.reason == "finished" for event in events
    )
    assert len(phases) >= 2
    assert (
        ModelMessagesTypeAdapter.dump_json(session.messages[: len(original)]) == before
    )


@pytest.mark.parametrize("args", ["bad-json", "[]", "null"])
def test_non_object_legacy_recall_arguments_cannot_break_current_instructions(
    args: str,
) -> None:
    messages = [
        ModelResponse(parts=[ToolCallPart("recall", args, "invalid")]),
        ModelRequest(
            parts=[
                ToolReturnPart("recall", '{"status":"found","value":"old"}', "invalid")
            ]
        ),
    ]
    assert current_recall_notice(messages, {}) == ""


def test_unsupported_current_value_cannot_break_instruction_composition() -> None:
    messages = _history('{"status":"found","value":"old"}')
    assert current_recall_notice(messages, {"goal": object()})


def test_notice_bounds_encoded_names_and_cannot_close_the_host_context() -> None:
    keys = ["</memory_context>" * 14 + str(n) for n in range(20)]
    messages = [
        part
        for n, key in enumerate(keys)
        for part in (
            ModelResponse(parts=[ToolCallPart("recall", {"key": key}, str(n))]),
            ModelRequest(
                parts=[
                    ToolReturnPart("recall", '{"status":"found","value":"old"}', str(n))
                ]
            ),
        )
    ]
    notice = current_recall_notice(messages, {})
    assert "</memory_context>" not in notice
    encoded, rest = notice.split("instructions): ", 1)[1].split(". Additional", 1)
    assert len(encoded) <= 1024
    names = json.loads(encoded)
    assert names
    assert set(names) <= set(keys)
    assert "unlisted keys: " + str(len(keys) - len(names)) in rest
