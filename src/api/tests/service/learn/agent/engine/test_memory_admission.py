"""Exercise declared-or-requested admission through actual engine tool calls."""

import asyncio
import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from flaskr.service.learn.agent.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    MemoryUpdated,
    MessageTurn,
    ScriptBundle,
    Session,
)
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio
REQUEST = "Please remember that I prefer short explanations."


def _note_model(notes: list[dict], returns: list[str]) -> FunctionModel:
    """Try the supplied notes once, then continue after their acknowledgements."""

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        last = messages[-1]
        parts = (
            [p for p in last.parts if isinstance(p, ToolReturnPart)]
            if isinstance(last, ModelRequest)
            else []
        )
        if parts:
            returns.extend(str(p.content) for p in parts)
            yield "Continue teaching."
        else:
            yield {
                i: DeltaToolCall(
                    name="remember",
                    tool_call_id=f"note-{i}",
                    json_args=json.dumps(note),
                )
                for i, note in enumerate(notes)
            }

    return FunctionModel(stream_function=model)


@pytest.mark.parametrize(
    ("script", "allowed"),
    [
        ("Collect %{{pace}}.", True),
        ("Read {{pace}}.", False),
        ("```md\nCollect %{{pace}}.\n```", False),
        ("Teach the lesson.", False),
    ],
)
async def test_only_main_script_collection_declarations_grant_permission(
    script: str, allowed: bool
) -> None:
    """References, briefs, substitutions and fenced examples cannot grant write permission."""
    check = AsyncMock(return_value=True)
    returns = []
    engine = Engine(
        _note_model([{"key": "pace", "value": "slow"}], returns),
        memory_admission=True,
        memory_request_check=check,
    )
    session = await engine.new_session(
        ScriptBundle(
            script=script,
            constraints="Collect %{{pace}}.",
            extras={"example": "%{{pace}}"},
        )
    )
    events = [event async for event in engine.run_turn(session)]
    assert session.memory == ({"pace": "slow"} if allowed else {})
    assert session.user_memory == {}
    assert len([e for e in events if isinstance(e, MemoryUpdated)]) == int(allowed)
    assert returns[0].startswith("remembered " if allowed else "Not remembered:")
    check.assert_not_awaited()


@pytest.mark.parametrize(
    ("evidence", "quote", "key", "decision", "allowed"),
    [
        (REQUEST, REQUEST, "pace", True, True),
        (REQUEST, REQUEST, "pace", False, False),
        (
            "I prefer short explanations.",
            "I prefer short explanations.",
            "pace",
            False,
            False,
        ),
        (REQUEST, None, "pace", True, False),
        (REQUEST, "Please remember", "pace", True, False),
        ("Ordinary answer", REQUEST, "pace", True, False),
        (REQUEST, REQUEST, "sys_user_nickname", True, False),
        ("x" * 4097, "x" * 4097, "pace", True, False),
    ],
)
async def test_undeclared_notes_require_exact_real_input_and_independent_approval(
    evidence: str, quote: str | None, key: str, decision: bool, allowed: bool
) -> None:
    """Accepted explicit requests become durable course notes; every refusal is inert."""
    check = AsyncMock(return_value=decision)
    returns = []
    engine = Engine(
        _note_model([{"key": key, "value": "short", "request": quote}], returns),
        memory_admission=True,
        memory_request_check=check,
    )
    session = await engine.new_session("Teach the lesson.")
    events = [e async for e in engine.run_turn(session, MessageTurn(text=evidence))]
    assert session.memory == {}
    assert session.user_memory == ({key: "short"} if allowed else {})
    writes = [e for e in events if isinstance(e, MemoryUpdated)]
    assert len(writes) == int(allowed)
    if allowed:
        assert writes[0].scope == "user"
        check.assert_awaited_once_with(REQUEST, key, "short")
    elif quote != evidence or key.startswith("sys_") or len(evidence) > 4096:
        check.assert_not_awaited()
    assert not session.request_inputs
    assert not any(isinstance(e, ErrorEvent) for e in events)


async def _ask(
    spec: dict, check: AsyncMock, notes: list[dict], script: str = "Ask a question."
) -> tuple[Engine, Session]:
    """Pause at a real deferred interaction before attempting memory writes."""
    phase = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal phase
        phase += 1
        if phase == 1:
            yield "Here is the question."
            yield {
                0: DeltaToolCall(
                    name="interact", tool_call_id="question", json_args=json.dumps(spec)
                )
            }
        elif phase == 2:
            yield {
                i: DeltaToolCall(
                    name="remember",
                    tool_call_id=f"note-{i}",
                    json_args=json.dumps(note),
                )
                for i, note in enumerate(notes)
            }
        else:
            yield "Continue teaching."

    engine = Engine(
        FunctionModel(stream_function=model),
        memory_admission=True,
        memory_request_check=check,
    )
    session = await engine.new_session(script)
    _ = [e async for e in engine.run_turn(session)]
    return engine, Session.loads(session.dumps())


@pytest.mark.parametrize(
    ("kind", "values", "text", "allowed"),
    [
        ("text", [REQUEST], None, True),
        ("text", [], REQUEST, True),
        ("single_or_text", [], REQUEST, True),
        ("single_or_text", [REQUEST], None, True),
        ("single_or_text", ["pick", REQUEST], None, False),
        ("multi_or_text", ["pick", REQUEST], None, True),
        ("single", ["pick"], REQUEST, False),
        ("confirm", [], REQUEST, False),
    ],
)
async def test_only_accepted_free_text_is_request_evidence(
    kind: str, values: list[str], text: str | None, allowed: bool
) -> None:
    """Pure choices, confirm payloads and discarded extra values cannot manufacture consent."""
    check = AsyncMock(return_value=True)
    spec = {"type": kind, "prompt": "Tell me", "variable": "guessed"}
    if kind != "text":
        spec["options"] = [{"display": "Pick", "value": "pick"}]
    engine, session = await _ask(
        spec, check, [{"key": "pace", "value": "short", "request": REQUEST}]
    )
    assert session.pending[0].spec.variable is None
    events = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(values=values, text=text)
        )
    ]
    assert session.memory == {}
    assert session.user_memory == ({"pace": "short"} if allowed else {})
    assert len([e for e in events if isinstance(e, MemoryUpdated)]) == int(allowed)
    assert check.await_count == int(allowed)


async def test_option_display_and_stored_request_are_never_free_text() -> None:
    check = AsyncMock(return_value=True)
    for field in ("display", "value"):
        option = {"display": "Pick", "value": "pick", field: REQUEST}
        engine, session = await _ask(
            {"type": "single_or_text", "prompt": "Pick", "options": [option]},
            check,
            [{"key": "pace", "value": "short", "request": REQUEST}],
        )
        _ = [
            e
            async for e in engine.run_turn(
                session, InteractionResponseTurn(values=[REQUEST])
            )
        ]
        assert not session.user_memory
    check.assert_not_awaited()


async def test_judge_failure_refuses_without_interrupting_teaching() -> None:
    check = AsyncMock(side_effect=RuntimeError("judge unavailable"))
    engine = Engine(
        _note_model([{"key": "pace", "value": "short", "request": REQUEST}], []),
        memory_admission=True,
        memory_request_check=check,
    )
    session = await engine.new_session("Teach.")
    events = [e async for e in engine.run_turn(session, MessageTurn(text=REQUEST))]
    assert not session.user_memory
    assert events[-1].reason == "end"
    assert not any(isinstance(e, ErrorEvent) for e in events)


async def test_concurrent_checked_notes_recheck_capacity_after_awaiting() -> None:
    """Two approved tools racing for the last slot cannot both pass the old snapshot."""

    async def check(*_args: str) -> bool:
        await asyncio.sleep(0)
        return True

    engine = Engine(
        _note_model(
            [{"key": k, "value": "short", "request": REQUEST} for k in ("a", "b")], []
        ),
        memory_admission=True,
        memory_request_check=check,
    )
    session = await engine.new_session("Teach.")
    session.user_memory = {f"old_{i}": "kept" for i in range(99)}
    _ = [e async for e in engine.run_turn(session, MessageTurn(text=REQUEST))]
    assert len(session.user_memory) == 100


async def test_old_session_pending_variable_cannot_bypass_admission() -> None:
    check = AsyncMock(return_value=False)
    engine, session = await _ask(
        {"type": "text", "prompt": "Tell me"},
        check,
        [{"key": "pace", "value": "short"}],
    )
    session.pending[0].spec.variable = "legacy_guessed"
    _ = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(text="ordinary answer")
        )
    ]
    assert session.memory == session.user_memory == {}


async def test_queued_answers_retry_and_round_trip_preserve_only_pending_evidence() -> (
    None
):
    """Two answers wait together; a failed resume retains evidence, a successful one clears it."""
    phase = 0
    check = AsyncMock(return_value=True)

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal phase
        phase += 1
        if phase == 1:
            yield {
                i: DeltaToolCall(
                    name="interact",
                    tool_call_id=f"q-{i}",
                    json_args=json.dumps({"type": "text", "prompt": f"Question {i}"}),
                )
                for i in range(2)
            }
        elif phase == 2:
            message = "provider temporarily unavailable"
            raise RuntimeError(message)
        elif phase in (3, 5):
            yield {
                0: DeltaToolCall(
                    name="remember",
                    tool_call_id=f"note-{phase}",
                    json_args=json.dumps(
                        {"key": f"pace_{phase}", "value": "short", "request": REQUEST}
                    ),
                )
            }
        else:
            yield "Continue teaching."

    engine = Engine(
        FunctionModel(stream_function=model),
        memory_admission=True,
        memory_request_check=check,
    )
    session = await engine.new_session("Ask two questions.")
    _ = [e async for e in engine.run_turn(session)]
    _ = [
        e async for e in engine.run_turn(session, InteractionResponseTurn(text=REQUEST))
    ]
    session = Session.loads(session.dumps())
    assert session.request_inputs == [REQUEST]
    failed = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(text="ordinary answer")
        )
    ]
    assert any(isinstance(e, ErrorEvent) for e in failed)
    session = Session.loads(session.dumps())
    assert session.request_inputs == [REQUEST, "ordinary answer"]
    _ = [e async for e in engine.run_turn(session)]
    assert session.user_memory == {"pace_3": "short"}
    assert not session.request_inputs
    _ = [e async for e in engine.run_turn(session)]
    assert session.user_memory == {"pace_3": "short"}
    check.assert_awaited_once()


async def test_declared_answer_keeps_its_exact_long_value() -> None:
    """Admission restricts who may name a variable, not the answer's original length."""
    check = AsyncMock(return_value=False)
    engine, session = await _ask(
        {"type": "text", "prompt": "Your goal?", "variable": "goal"},
        check,
        [],
        script="Collect %{{goal}}.",
    )
    assert session.pending[0].spec.variable == "goal"
    answer = "é" * 4000
    events = [
        e async for e in engine.run_turn(session, InteractionResponseTurn(text=answer))
    ]
    assert session.memory["goal"] == answer
    assert any(
        isinstance(e, MemoryUpdated) and e.source == "interaction" for e in events
    )
    check.assert_not_awaited()


@pytest.mark.parametrize("key", ["language", "sex", "birth", "avatar"])
async def test_host_reserved_account_keys_need_script_declarations(key: str) -> None:
    """An approved request must not reach legacy keys that the writer routes globally."""
    check = AsyncMock(return_value=True)
    for declared in (False, True):
        engine = Engine(
            _note_model(
                [
                    {
                        "key": key,
                        "value": "requested",
                        "request": REQUEST,
                        "scope": "user",
                    }
                ],
                [],
            ),
            memory_admission=True,
            memory_reserved_keys=frozenset({key}),
            memory_request_check=check,
        )
        session = await engine.new_session(
            f"Collect %{{{{{key}}}}}." if declared else "Teach."
        )
        _ = [e async for e in engine.run_turn(session, MessageTurn(text=REQUEST))]
        assert session.user_memory == ({key: "requested"} if declared else {})
    check.assert_not_awaited()


@pytest.mark.parametrize("change", ["finish", "count", "budget"])
async def test_async_approval_cannot_use_a_stale_write_permission(change: str) -> None:
    """Side effects between checking and writing cannot bypass terminal or capacity guards."""
    from types import SimpleNamespace

    from flaskr.service.learn.agent.engine.tools import Deps, remember

    deps = Deps(
        memory={}, user_memory={}, memory_keys=frozenset(), request_inputs=(REQUEST,)
    )

    async def check(*_args: str) -> bool:
        if change == "finish":
            deps.finished = "done"
        elif change == "count":
            deps.user_memory.update({f"old_{i}": "kept" for i in range(100)})
        else:
            deps.user_memory["old"] = "é" * 32_768
        await asyncio.sleep(0)
        return True

    deps.memory_request_check = check
    await remember(
        SimpleNamespace(deps=deps), key="pace", value="short", request=REQUEST
    )
    assert "pace" not in deps.user_memory
    assert not deps.memory_updates


@pytest.mark.parametrize("limit", ["count", "budget", "value", "finished"])
async def test_invalid_writes_do_not_spend_semantic_checks(limit: str) -> None:
    """Deterministic refusal comes before extra provider calls."""
    check = AsyncMock(return_value=True)
    engine = Engine(
        _note_model(
            [
                {
                    "key": "pace",
                    "value": "x" * (2001 if limit == "value" else 1),
                    "request": REQUEST,
                }
            ],
            [],
        ),
        memory_admission=True,
        memory_request_check=check,
    )
    session = await engine.new_session("Teach.")
    if limit == "count":
        session.user_memory = {f"old_{i}": "kept" for i in range(100)}
    elif limit == "budget":
        session.user_memory = {"old": "é" * 32_768}
    elif limit == "finished":
        session.finished = True
    _ = [e async for e in engine.run_turn(session, MessageTurn(text=REQUEST))]
    assert "pace" not in session.user_memory
    check.assert_not_awaited()


@pytest.mark.parametrize("started", [False, True])
async def test_unrelated_continue_cannot_reuse_a_failed_message_request(
    started: bool,
) -> None:
    """Only retrying deferred answers retains evidence; a new continue has no learner input."""
    phase = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal phase
        phase += 1
        if started and phase == 1:
            yield "Teach the first part."
        elif phase == (2 if started else 1):
            message = "temporary model failure"
            raise RuntimeError(message)
        elif phase == (3 if started else 2):
            yield {
                0: DeltaToolCall(
                    name="remember",
                    tool_call_id="stale",
                    json_args=json.dumps(
                        {"key": "pace", "value": "short", "request": REQUEST}
                    ),
                )
            }
        else:
            yield "Teach the next part."

    check = AsyncMock(return_value=True)
    engine = Engine(
        FunctionModel(stream_function=model),
        memory_admission=True,
        memory_request_check=check,
    )
    session = await engine.new_session("Teach.")
    if started:
        _ = [e async for e in engine.run_turn(session)]
    failed = [e async for e in engine.run_turn(session, MessageTurn(text=REQUEST))]
    assert any(isinstance(e, ErrorEvent) for e in failed)
    session = Session.loads(session.dumps())
    _ = [e async for e in engine.run_turn(session)]
    assert not session.user_memory
    check.assert_not_awaited()


@pytest.mark.parametrize("enabled", [False, True])
async def test_model_facing_memory_policy_matches_the_host_capability(
    enabled: bool,
) -> None:
    """Portable hosts retain natural declarations and preference notes in prompt and tools."""
    seen = []

    async def model(
        _messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        remember_tool = next(
            tool for tool in info.function_tools if tool.name == "remember"
        )
        assert (
            "request" in remember_tool.parameters_json_schema.get("required", [])
        ) is enabled
        if enabled:
            assert (
                "EXACTLY"
                in remember_tool.parameters_json_schema["properties"]["request"][
                    "description"
                ]
            )
        seen.extend(
            tool.description
            for tool in info.function_tools
            if tool.name in ("interact", "remember")
        )
        yield "Teach the next part."

    engine = Engine(FunctionModel(stream_function=model), memory_admission=enabled)
    instructions = engine.compose_instructions()
    if enabled:
        assert "Only record variables the main script declares" in instructions
        assert "complete verbatim free-text input" in instructions
        assert "before your next `interact` or `finish`" in instructions
        assert (
            "Also call `remember` when the learner states a preference"
            not in instructions
        )
    else:
        assert (
            "Also call `remember` when the learner states a preference" in instructions
        )
        assert '"store it as X"' in instructions
        assert "Only record variables the main script declares" not in instructions
    session = await engine.new_session("Teach.")
    _ = [event async for event in engine.run_turn(session)]
    assert len(seen) == 2
    for description in seen:
        assert (
            "Only record variables the main script declares" in description
        ) is enabled
        assert (
            "Also call `remember` when the learner states a preference" in description
        ) is not enabled
