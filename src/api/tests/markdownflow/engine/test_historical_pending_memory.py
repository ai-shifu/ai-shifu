"""Keep issued historical answer bindings without loosening new question admission."""

import json
from collections.abc import AsyncIterator

import pytest
from markdownflow.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    InteractionSpec,
    MemoryUpdated,
    PendingInteraction,
    ScriptBundle,
    Session,
    render_first_prompt,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel


def saved_pending_session(legacy: bool, count: int = 1) -> Session:
    bundle = ScriptBundle(
        script="\n".join(f"Collect %{{{{goal{index}}}}}." for index in range(count))
    )
    parts = [
        ToolCallPart(
            "interact",
            {
                "type": "text",
                "prompt": "Goal?",
                "variable" if legacy else "question": f"goal{index}",
            },
            f"old-{index}",
        )
        for index in range(count)
    ]
    session = Session(
        script=bundle,
        messages=[
            ModelRequest(parts=[UserPromptPart(render_first_prompt(bundle, {}))]),
            ModelResponse(parts=parts),
        ],
        pending=[
            PendingInteraction(
                f"old-{index}",
                InteractionSpec(type="text", prompt="Goal?", question=f"goal{index}"),
            )
            for index in range(count)
        ],
    )
    payload = session.to_dict()
    if legacy:
        for pending in payload["pending"]:
            pending["spec"]["variable"] = pending["spec"].pop("question")
    return Session.from_dict(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("readonly", [False, True])
async def test_only_issued_old_bindings_retain_admission_across_store_roundtrips(
    legacy: bool, count: int, readonly: bool
) -> None:
    session = saved_pending_session(legacy, count)
    old_calls = session.to_dict()["messages"][1]

    async def stream(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        yield "Continue with another question."
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="new-question",
                json_args=json.dumps(
                    {
                        "type": "text",
                        "prompt": "Again?",
                        "question": None if readonly else "goal0",
                    }
                ),
            )
        }

    engine = Engine(
        FunctionModel(stream_function=stream),
        memory_admission=True,
        memory_readonly_prefixes=("goal",) if readonly else (),
    )
    updates = []
    for index in range(count):
        session = Session.loads(session.dumps())
        events = [
            e
            async for e in engine.run_turn(
                session,
                InteractionResponseTurn(id=f"old-{index}", text=f"answer-{index}"),
            )
        ]
        assert not any(isinstance(e, ErrorEvent) for e in events), events
        updates.extend(e for e in events if isinstance(e, MemoryUpdated))
    assert session.memory == (
        {f"goal{i}": f"answer-{i}" for i in range(count)}
        if legacy and not readonly
        else {}
    )
    assert {e.key for e in updates} == (
        set(session.memory) if legacy and not readonly else set()
    )
    assert session.to_dict()["messages"][1] == old_calls
    assert session.pending[0].tool_call_id == "new-question"
    assert session.pending[0].spec.question is None
    assert (
        sum(
            isinstance(p, ToolReturnPart) and p.tool_name == "interact"
            for m in session.messages
            for p in m.parts
        )
        == count
    )
