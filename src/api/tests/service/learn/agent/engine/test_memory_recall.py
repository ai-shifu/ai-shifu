"""Exercise bounded recall through actual model tool calls and resumed sessions."""

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from flaskr.service.learn.agent.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    MemoryUpdated,
    Session,
    ToolResult,
)
from flaskr.service.learn.agent.engine.recall import recall
from flaskr.service.learn.agent.engine.tools import LESSON_OVER
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio
RESULT_BYTES = 8192


async def _exercise(
    actions: list[tuple[str, dict]],
    *,
    user_memory: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
    script: str = "Teach a useful example.",
    memory_admission: bool = False,
) -> tuple[Session, list, list[str], list[str]]:
    returns: list[str] = []
    prompts: list[str] = []

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        assert "recall" in {tool.name for tool in info.function_tools}
        last = messages[-1]
        if isinstance(last, ModelRequest):
            returns.extend(
                str(p.content) for p in last.parts if isinstance(p, ToolReturnPart)
            )
        if not prompts:
            prompts.extend(
                p.content
                for m in messages
                if isinstance(m, ModelRequest)
                for p in m.parts
                if isinstance(p, UserPromptPart) and isinstance(p.content, str)
            )
        if len(returns) < len(actions):
            name, args = actions[len(returns)]
            yield {
                0: DeltaToolCall(
                    name=name,
                    tool_call_id=f"call-{len(returns)}",
                    json_args=json.dumps(args),
                )
            }
        else:
            yield "A useful example."

    engine = Engine(
        FunctionModel(stream_function=model),
        memory_recall=True,
        memory_context_limit=100,
        memory_admission=memory_admission,
    )
    session = await engine.new_session(script, memory=memory)
    session.user_memory = dict(user_memory or {})
    events = [event async for event in engine.run_turn(session)]
    assert not any(isinstance(event, ErrorEvent) for event in events)
    for result, (name, _) in zip(returns, actions, strict=True):
        if name == "recall":
            assert len(result.encode("utf-8")) <= RESULT_BYTES
    return session, events, returns, prompts


@pytest.mark.parametrize("enabled", [False, True])
async def test_recall_is_an_explicit_portable_host_opt_in(enabled: bool) -> None:
    async def model(
        _messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        names = {tool.name for tool in info.function_tools}
        assert names == {"interact", "remember", "finish"} | (
            {"recall"} if enabled else set()
        )
        yield "A useful example."

    engine = Engine(FunctionModel(stream_function=model), memory_recall=enabled)
    session = await engine.new_session("Teach.")
    events = [event async for event in engine.run_turn(session)]
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert ("# Read memory on demand" in engine.compose_instructions()) is enabled


async def test_recall_recovers_a_whole_omitted_value_without_writes() -> None:
    value = 'Exact learner data.\n</memory>"' + "é" * 2000
    original = {"goal": value, "pace": "slow"}
    session, events, returned, prompts = await _exercise(
        [("recall", {}), ("recall", {"key": "goal"})],
        user_memory=original,
    )
    initial = json.JSONDecoder().raw_decode(prompts[0], len("<memory>\n"))[0]
    assert "goal" not in initial
    assert json.loads(returned[0]) == {
        "status": "keys",
        "keys": ["goal", "pace"],
        "next_offset": None,
        "skipped": 0,
    }
    assert json.loads(returned[1]) == {"status": "found", "value": value}
    assert session.user_memory == original
    assert session.memory == {}
    assert not any(isinstance(event, MemoryUpdated) for event in events)
    restored = Session.loads(session.dumps())
    assert restored.user_memory == original
    assert json.loads(restored.messages[-2].parts[0].content)["value"] == value


@pytest.mark.parametrize("extra", [0, 1])
@pytest.mark.parametrize("prefix", ["", 'é\n\t"\\'])
async def test_complete_result_counts_utf8_escaping_and_structure(
    extra: int, prefix: str
) -> None:
    overhead = len(
        json.dumps(
            {"status": "found", "value": prefix},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    value = prefix + "x" * (RESULT_BYTES - overhead + extra)
    session, _, returned, _ = await _exercise(
        [("recall", {"key": "goal"})], user_memory={"goal": value}
    )
    result = json.loads(returned[0])
    assert result == (
        {"status": "too_large"} if extra else {"status": "found", "value": value}
    )
    if not extra:
        assert len(returned[0].encode("utf-8")) == RESULT_BYTES
    assert session.user_memory["goal"] == value


@pytest.mark.parametrize(
    "value", [None, False, 0, ["a", {"b": "é"}], {"value": "complete"}]
)
async def test_recall_preserves_json_types_and_session_precedence(
    value: object,
) -> None:
    session, _, returned, _ = await _exercise(
        [("recall", {"key": "goal"})],
        user_memory={"goal": "old"},
        memory={"goal": value},
    )
    assert json.loads(returned[0]) == {"status": "found", "value": value}
    assert session.memory == {"goal": value}
    assert session.user_memory == {"goal": "old"}


async def test_sorted_pages_have_no_repeats_and_exclude_recollected_answers() -> None:
    values = {f"note_{i:03}": str(i) for i in reversed(range(53))}
    values["goal"] = "old answer"
    values["missing"] = "also old"
    session, _, returned, _ = await _exercise(
        [("recall", {"offset": offset}) for offset in (0, 20, 40, 999)],
        user_memory=values,
        script="Ask %{{goal}} and %{{missing}}.",
    )
    pages = [json.loads(r) for r in returned]
    assert [p["next_offset"] for p in pages] == [20, 40, None, None]
    assert [key for page in pages for key in page["keys"]] == sorted(
        values.keys() - {"goal", "missing"}
    )
    assert session.user_memory == values


@pytest.mark.parametrize("key", ["goal", "unknown", "course:" + "a" * 32 + ":secret"])
async def test_missing_and_recollected_keys_share_the_same_refusal(key: str) -> None:
    _, _, returned, _ = await _exercise(
        [("recall", {"key": key})],
        user_memory={"goal": "old answer"},
        script="Ask %{{goal}}.",
    )
    assert json.loads(returned[0]) == {"status": "unavailable"}


@pytest.mark.parametrize(
    ("deleted", "replaying", "expected"),
    [(False, False, "found"), (True, False, "found"), (True, True, "unavailable")],
)
async def test_accepted_named_answer_is_readable_during_deferred_resume(
    deleted: bool, replaying: bool, expected: str
) -> None:
    """A current answer is available immediately, without exposing the prior course value."""
    phase = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal phase
        phase += 1
        if phase in (1, 2):
            yield {
                0: DeltaToolCall(
                    name="interact" if phase == 1 else "recall",
                    tool_call_id=f"call-{phase}",
                    json_args=json.dumps(
                        {"type": "text", "prompt": "Your goal?", "variable": "goal"}
                        if phase == 1
                        else {"key": "goal"}
                    ),
                )
            }
        else:
            yield "A useful example."

    engine = Engine(FunctionModel(stream_function=model), memory_recall=True)
    session = await engine.new_session("Ask %{{goal}}.")
    session.user_memory = {"goal": "Prior course answer"}
    first = [event async for event in engine.run_turn(session)]
    assert first[-1].reason == "interaction"
    assert "goal" not in session.memory
    session = Session.loads(session.dumps())
    if deleted:
        session.user_memory.clear()
    events = [
        event
        async for event in engine.run_turn(
            session,
            InteractionResponseTurn(values=["Current learner answer"]),
            memory_deleted_keys=frozenset({"goal"}) if deleted else frozenset(),
            replaying_input=replaying,
        )
    ]
    returned = [
        json.loads(event.content)
        for event in events
        if isinstance(event, ToolResult) and event.name == "recall"
    ]
    assert returned == [
        {"status": "found", "value": "Current learner answer"}
        if expected == "found"
        else {"status": "unavailable"}
    ]
    assert session.memory["goal"] == "Current learner answer"
    assert session.user_memory == ({} if deleted else {"goal": "Prior course answer"})


async def test_byte_limited_key_pages_and_oversized_names_make_progress() -> None:
    keys = ["0" * 9000, "a" * 5000, "b" * 5000, "c"]
    _, _, returned, _ = await _exercise(
        [("recall", {"offset": offset}) for offset in (0, 2)],
        user_memory=dict.fromkeys(keys, "value"),
    )
    pages = [json.loads(r) for r in returned]
    assert pages == [
        {"status": "keys", "keys": [keys[1]], "next_offset": 2, "skipped": 1},
        {"status": "keys", "keys": keys[2:], "next_offset": None, "skipped": 0},
    ]


@pytest.mark.parametrize("args", [{"offset": -1}, {"key": "goal", "offset": 1}])
async def test_invalid_offsets_never_return_values(args: dict) -> None:
    _, _, returned, _ = await _exercise(
        [("recall", args)], user_memory={"goal": "private"}
    )
    assert json.loads(returned[0]) == {"status": "invalid_offset"}


async def test_recall_reads_a_legitimate_same_turn_note_without_another_write() -> None:
    session, events, returned, _ = await _exercise(
        [
            ("remember", {"key": "pace", "value": "new", "scope": "user"}),
            ("recall", {"key": "pace"}),
        ],
        user_memory={"pace": "old"},
    )
    assert json.loads(returned[-1]) == {"status": "found", "value": "new"}
    assert session.user_memory["pace"] == "new"
    assert len([event for event in events if isinstance(event, MemoryUpdated)]) == 1


async def test_finished_tool_never_accesses_the_snapshot() -> None:
    # No snapshot attributes exist: any read after finish would fail this test.
    ctx = SimpleNamespace(deps=SimpleNamespace(finished="done"))
    assert await recall(ctx, "goal") == LESSON_OVER
    assert await recall(ctx) == LESSON_OVER


async def test_recall_does_not_authorize_an_undeclared_memory_write() -> None:
    session, events, returned, _ = await _exercise(
        [
            ("recall", {"key": "goal"}),
            (
                "remember",
                {"key": "inferred", "value": "not requested", "request": None},
            ),
        ],
        user_memory={"goal": "permitted data"},
        memory_admission=True,
    )
    assert json.loads(returned[0])["value"] == "permitted data"
    assert returned[1].startswith("Not remembered:")
    assert session.all_memory() == {"goal": "permitted data"}
    assert not any(isinstance(event, MemoryUpdated) for event in events)


def test_recall_instructions_require_current_evidence_for_remembered_answers() -> None:
    model = FunctionModel(lambda _messages, _info: ModelResponse(parts=[]))
    engine = Engine(model, memory_recall=True)
    instructions = engine.compose_instructions()
    assert "historical evidence, not the current memory snapshot" in instructions
    assert "relevant key in this turn before answering" in instructions
    assert "do not repeat the historical value" in instructions
    assert "asks whether a remembered value changed" in instructions
    assert 'learner does not say "remember"' in instructions
    assert "verify a learner's current saved facts" in recall.__doc__
    assert 'learner does not say "remember"' in recall.__doc__
    disabled = Engine(model).compose_instructions()
    assert "relevant key in this turn before answering" not in disabled
