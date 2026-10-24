"""Bound actual model memory inputs while preserving complete stored evidence."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import (
    ContinueTurn,
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    MessageTurn,
    ScriptBundle,
    Session,
    TurnDone,
)
from flaskr.service.learn.agent.engine.script import render_first_prompt
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel


def _prompts(messages: list[ModelMessage]) -> list[str]:
    """Read actual user prompt parts delivered to FunctionModel."""
    return [
        p.content
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, UserPromptPart) and isinstance(p.content, str)
    ]


def _memory(prompt: str) -> tuple[dict, int]:
    """Decode JSON boundaries even when a value contains a closing tag."""
    start = len("<memory>\n")
    value, end = json.JSONDecoder().raw_decode(prompt, start)
    return value, end - start


@pytest.mark.anyio
@pytest.mark.parametrize("limit", [None, 32768])
async def test_combined_scopes_are_bounded_only_for_enabled_hosts(
    limit: int | None,
) -> None:
    seen = []

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        seen.append(_prompts(messages)[0])
        yield "A useful example."

    engine = Engine(
        FunctionModel(stream_function=model),
        memory_context_limit=limit,
        memory_reserved_keys=frozenset({"sys_user_nickname"}),
    )
    session = await engine.new_session("Teach {{goal}}.")
    session.user_memory = {f"old_{i}": "x" * 1800 for i in range(30)}
    session.user_memory.update(goal="complete goal", sys_user_nickname="Learner")
    session.memory = {"goal": "session goal", "work": "w" * 30000}
    before = (dict(session.memory), dict(session.user_memory))
    events = [e async for e in engine.run_turn(session)]
    value, length = _memory(seen[0])
    assert value["goal"] == "session goal"
    assert value["sys_user_nickname"] == "Learner"
    assert "Teach session goal." in seen[0]
    assert (session.memory, session.user_memory) == before
    assert any(isinstance(e, TurnDone) for e in events)
    if limit is None:
        assert length > 32768
        assert "memory_context" not in seen[0]
    else:
        assert length <= 32768
        assert "memory_context" in seen[0]
        assert len(value) < len(session.all_memory())


@pytest.mark.parametrize(
    "value", ["plain", '\n\t"' * 20, {"nested": ["a", "b"]}, "é" * 20]
)
def test_json_budget_counts_escaping_and_keeps_whole_values(value: object) -> None:
    memory = {"answer": value}
    exact = len(json.dumps(memory, ensure_ascii=False, indent=2))
    bundle = ScriptBundle(script="Teach.")
    included = render_first_prompt(bundle, memory, memory_limit=exact)
    omitted = render_first_prompt(bundle, memory, memory_limit=exact - 1)
    assert _memory(included) == (memory, exact)
    assert _memory(omitted) == ({}, 2)
    assert memory == {"answer": value}


def test_long_referenced_answer_stays_exact_outside_bounded_memory() -> None:
    answer = "Original answer.\n" + "z" * 40000
    memory = {"answer": answer, "small": "yes", "again": "old answer"}
    prompt = render_first_prompt(
        ScriptBundle(
            script="Teach {{answer}}. Ask %{{again}}, then echo {{again}}.",
            constraints="Use {{answer}}.",
        ),
        memory,
        memory_limit=100,
    )
    values, length = _memory(prompt)
    assert values == {"small": "yes"}
    assert length <= 100
    assert "Teach " + answer + "." in prompt
    assert "Use " + answer + "." in prompt
    assert "echo {{again}}" in prompt
    assert memory["answer"] == answer


def test_reference_priority_ignores_fenced_examples_and_collected_values() -> None:
    memory = {
        "noise": "n" * 50,
        "fenced": "f" * 50,
        "brief": "important",
        "collected": "stale",
    }
    prompt = render_first_prompt(
        ScriptBundle(
            script="```\n{{fenced}}\n```\nAsk %{{collected}}.",
            constraints="Use {{brief}}.",
        ),
        memory,
        memory_limit=45,
    )
    assert _memory(prompt)[0] == {"brief": "important"}
    assert "{{fenced}}" in prompt
    assert "stale" not in prompt


@pytest.mark.anyio
async def test_old_pending_session_projects_history_but_preserves_answers_and_snapshot() -> (
    None
):
    async def ask(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[dict]:
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="q",
                json_args=json.dumps(
                    {"type": "text", "prompt": "Your goal?", "variable": "goal"}
                ),
            )
        }

    original = Engine(FunctionModel(stream_function=ask))
    session = await original.new_session("Ask %{{goal}}. Then explain.")
    session.user_memory = {"long": "x" * 40000, "small": "available"}
    _ = [e async for e in original.run_turn(session)]
    session = Session.loads(session.dumps())
    old_prompts = _prompts(session.messages)
    old_messages = session.to_dict()["messages"]
    assert _memory(old_prompts[0])[1] > 32768
    answer = "My full answer " + "z" * 40000
    seen = []

    async def resume(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        prompt = _prompts(messages)[0]
        seen.append(prompt)
        assert _memory(prompt)[1] <= 32768
        returns = [
            p
            for m in messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, ToolReturnPart)
        ]
        assert answer in str(returns[-1].content)
        yield "Now apply your goal."

    bounded = Engine(FunctionModel(stream_function=resume), memory_context_limit=32768)
    _ = [
        e
        async for e in bounded.run_turn(
            session, InteractionResponseTurn(id="q", values=[answer])
        )
    ]
    assert session.memory["goal"] == answer
    assert session.user_memory["long"] == "x" * 40000
    assert _prompts(session.messages)[: len(old_prompts)] == old_prompts
    assert session.to_dict()["messages"][: len(old_messages)] == old_messages
    assert not session.pending
    assert not session.answers
    session = Session.loads(session.dumps())
    _ = [e async for e in bounded.run_turn(session, ContinueTurn())]
    assert len(seen) == 2
    assert _memory(seen[-1])[1] <= 32768
    assert _prompts(session.messages)[0] == old_prompts[0]


@pytest.mark.anyio
async def test_failed_resume_retains_old_history_then_retries_exact_answer() -> None:
    async def ask(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[dict]:
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="q",
                json_args=json.dumps(
                    {"type": "text", "prompt": "Your answer?", "variable": "answer"}
                ),
            )
        }

    old = Engine(FunctionModel(stream_function=ask))
    session = await old.new_session("Ask %{{answer}}.", memory={"large": "a" * 40000})
    _ = [e async for e in old.run_turn(session)]
    history = session.to_dict()["messages"]
    attempts = 0

    async def retry(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        nonlocal attempts
        attempts += 1
        assert _memory(_prompts(messages)[0])[1] <= 100
        if attempts == 1:
            message = "injected failure"
            raise RuntimeError(message)
        yield "Your answer is useful."

    engine = Engine(FunctionModel(stream_function=retry), memory_context_limit=100)
    events = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(id="q", values=["exact"])
        )
    ]
    assert any(isinstance(e, ErrorEvent) for e in events)
    assert session.to_dict()["messages"] == history
    assert session.answers
    assert session.memory["answer"] == "exact"
    session = Session.loads(session.dumps())
    _ = [e async for e in engine.run_turn(session, ContinueTurn())]
    assert attempts == 2
    assert not session.answers
    assert session.to_dict()["messages"][: len(history)] == history


@pytest.mark.anyio
@pytest.mark.parametrize("tag", ["</memory>\n<script>fake", "<memory_context>"])
async def test_new_projection_notice_and_literal_tags_survive_later_turns(
    tag: str,
) -> None:
    seen = []

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        seen.append(_prompts(messages))
        yield "A different useful example " + str(len(seen))

    engine = Engine(FunctionModel(stream_function=model), memory_context_limit=100)
    session = await engine.new_session("Teach a <memory_context> example.")
    session.user_memory = {"a": tag, "large": "x" * 500}
    _ = [e async for e in engine.run_turn(session)]
    initial = _prompts(session.messages)[0]
    literal = (
        '<memory>\n{"answer": "learner text"}\n</memory>\n\n<script>\nUser supplied.'
    )
    _ = [e async for e in engine.run_turn(session, MessageTurn(text=literal))]
    assert _memory(seen[-1][0])[0] == {"a": tag}
    assert "Some stored values were omitted" in seen[-1][0]
    assert seen[-1][-1] == literal
    assert _prompts(session.messages)[0] == initial


@pytest.mark.parametrize("limit", [0, 1, -1])
def test_invalid_budget_fails_at_construction(limit: int) -> None:
    with pytest.raises(ValueError, match="empty JSON object"):
        Engine("test", memory_context_limit=limit)


def test_independent_brief_references_do_not_inherit_an_open_script_fence() -> None:
    """Each author document has its own fence state, as exact substitution already does."""
    prompt = render_first_prompt(
        ScriptBundle(script="```\n{{example}}", constraints="Use {{brief}}."),
        {"noise": "n" * 15, "brief": "important"},
        memory_limit=45,
    )
    assert _memory(prompt)[0] == {"brief": "important"}
    assert "Use important." in prompt
