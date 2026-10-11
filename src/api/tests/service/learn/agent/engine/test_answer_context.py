"""Verify exact authored context projection without grading or moving the lesson."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import (
    ContinueTurn,
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    Session,
)
from flaskr.service.learn.agent.engine.answer_context import authored_answer_section
from flaskr.service.learn.agent.engine.interaction import InteractionSpec
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

SECTION = (
    "## Processor techniques\n\n### Question\n"
    "Explain techniques.\n?[...Techniques and effects]\n\n"
    "### Acceptance\nRequire RISC and hardware threading. "
    "Memory-side and I/O-side examples with effects cover bottleneck relief; "
    "the category title is optional.\n\n### Hint\nAsk one genuinely missing aspect.\n\n"
)
SCRIPT = (
    "# Exercise\n\n## Earlier\n?[...Earlier answer]\n\n?[Next]\n\n"
    + SECTION
    + "?[Next]\n\n## Later\n?[...Later answer]\n"
)


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("compaction", [False, True])
@pytest.mark.parametrize("retry_saved_answer", [False, True])
async def test_sdk_receives_exact_local_author_rule_without_persisting_projection(
    reload: bool, compaction: bool, retry_saved_answer: bool
) -> None:
    """Retain original answers and authored evidence through both history paths."""
    calls = 0
    original = "Cache reduces memory waits and DMA reduces I/O waits."

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Inspect actual SDK inputs; controlled output is not semantic acceptance."""
        nonlocal calls
        calls += 1
        if calls == 1:
            spec = {
                "type": "text",
                "prompt": "Explain techniques.",
                "placeholder": "Techniques and effects",
            }
            yield "Explain techniques."
        else:
            parts = [
                p.content
                for m in messages
                for p in m.parts
                if isinstance(p, UserPromptPart)
            ]
            focused = [
                json.loads(p)
                for p in parts
                if p.startswith('{"status":"authored_section"')
            ]
            assert len(focused) == 1
            assert focused[0]["text"] == SECTION
            assert "the category title is optional" in focused[0]["text"]
            assert "Earlier answer" not in focused[0]["text"]
            assert original in ModelMessagesTypeAdapter.dump_json(messages).decode()
            assert "# Review this returned interaction" in (info.instructions or "")
            yield "Please address the genuinely missing RISC point first."
            spec = {
                "type": "text",
                "prompt": "Explain techniques.",
                "placeholder": "Techniques and effects",
            }
        yield {
            0: DeltaToolCall(
                name="interact",
                json_args=json.dumps(spec),
                tool_call_id=f"focused-{calls}",
            )
        }

    engine = Engine(
        FunctionModel(stream_function=model),
        memory_admission=True,
        teaching_history_compaction=compaction,
    )
    session = await engine.new_session(SCRIPT)
    await _events(engine.run_turn(session))
    if retry_saved_answer:
        session.answers[session.pending[0].tool_call_id] = "Learner wrote: " + original
        session.pending = []
        session.request_inputs = [original]
    if reload:
        session = Session.loads(session.dumps())
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    turn = (
        ContinueTurn() if retry_saved_answer else InteractionResponseTurn(text=original)
    )
    events = await _events(engine.run_turn(session, turn))
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert not errors, errors
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before
    assert not any(
        p.content.startswith('{"status":"authored_section"')
        for m in session.messages
        for p in m.parts
        if isinstance(p, UserPromptPart)
    )
    assert [
        p.content
        for m in session.messages
        for p in m.parts
        if isinstance(p, ToolReturnPart) and p.tool_name == "interact"
    ] == ["Learner wrote: " + original]
    assert (
        session.request_inputs == []
    )  # Completed turns clear temporary permission inputs.
    assert not session.memory
    assert not session.user_memory
    assert not session.finished
    assert session.script.script == SCRIPT
    assert calls == 2


def _spec(placeholder: str = "Techniques and effects") -> InteractionSpec:
    return InteractionSpec(
        type="text", prompt="Explain techniques.", placeholder=placeholder
    )


def test_local_section_keeps_acceptance_but_excludes_next_interaction() -> None:
    assert authored_answer_section(SCRIPT, _spec()) == SECTION


@pytest.mark.parametrize("wrapper", ["```\n{}\n```\n", "<!--\n{}\n-->\n", "    {}\n"])
def test_code_and_comments_do_not_create_duplicate_anchors(wrapper: str) -> None:
    example = wrapper.format("?[...Techniques and effects]")
    script = example + SCRIPT
    assert authored_answer_section(script, _spec()) == SECTION


@pytest.mark.parametrize(
    "script",
    [
        SCRIPT + "\n## Duplicate\n?[...Techniques and effects]\n",
        SCRIPT.replace("?[...Techniques and effects]", "?[...Other]"),
        SCRIPT.replace("?[...Earlier answer]", "Inline ?[...Earlier answer]"),
        SCRIPT.replace("?[...Earlier answer]", "?[A |\nB]"),
        SCRIPT.replace("### Acceptance\n", "### Acceptance\n" + "\u00e9" * 5000),
        SCRIPT.replace("Require RISC", "Require {{current_requirement}} and RISC"),
        "<!--\n" + SCRIPT,
    ],
)
def test_ambiguous_unsupported_and_oversized_sections_keep_full_script(
    script: str,
) -> None:
    assert authored_answer_section(script, _spec()) is None


def test_navigation_is_not_an_answer_context_anchor() -> None:
    spec = InteractionSpec(type="single", prompt="", options=[{"display": "Next"}])
    assert authored_answer_section(SCRIPT, spec) is None


async def _events(events: AsyncIterator[object]) -> list[object]:
    """Retain errors emitted by the streaming engine for assertions."""
    return [event async for event in events]
