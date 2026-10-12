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
from flaskr.service.learn.agent.engine.answer_context import (
    authored_answer_section,
    project_answer_context,
)
from flaskr.service.learn.agent.engine.interaction import InteractionSpec
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
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
@pytest.mark.parametrize("normalized_case", ["exact", "variable", "hint", "both"])
@pytest.mark.parametrize("direction_rule", ["single", "multiple", "unspecified"])
async def test_sdk_receives_exact_local_author_rule_without_persisting_projection(
    reload: bool,
    compaction: bool,
    retry_saved_answer: bool,
    normalized_case: str,
    direction_rule: str,
) -> None:
    """Retain original answers and authored evidence through both history paths."""
    calls = 0
    original = "Cache reduces memory waits and DMA reduces I/O waits."
    hint = {
        "single": "Ask one genuinely missing aspect.",
        "multiple": "Ask two guiding questions together, about RISC and hardware threading.",
        "unspecified": "Give a checking direction and wait for a correction.",
    }[direction_rule]
    section = SECTION.replace("Ask one genuinely missing aspect.", hint)
    script = SCRIPT.replace(SECTION, section)

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
            if normalized_case in ("variable", "both"):
                spec["variable"] = "model_invented_key"
            if normalized_case in ("hint", "both"):
                spec["prompt"] = "Techniques and effects"
                spec.pop("placeholder")
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
            assert list(focused[0]) == ["status", "answer_id", "text", "notice"]
            assert focused[0]["answer_id"] == "focused-1"
            assert "## If the submission does not pass" in (info.instructions or "")
            assert "Do not combine the failed and passing branches" in (
                info.instructions or ""
            )
            assert (
                "Select the current feedback phase before using this reference"
                in focused[0]["notice"]
            )
            assert "conditional hint examples are alternatives" in focused[0]["notice"]
            assert focused[0]["text"] == section
            assert hint in focused[0]["text"]
            policy = info.instructions or ""
            assert (
                "only when the author limits the turn to one aspect or one question"
                in policy
            )
            assert (
                "If no count is authored, do not invent a one-question limit" in policy
            )
            assert "Preserve authored multiplicity" in focused[0]["notice"]
            assert "Preserve authored multiplicity" in next(
                t.description for t in info.function_tools if t.name == "interact"
            )
            system_policy = policy.split("# Review this returned interaction")[0]
            assert "Preserve authored multiplicity" in system_policy
            assert "the category title is optional" in focused[0]["text"]
            assert "Earlier answer" not in focused[0]["text"]
            assert original in ModelMessagesTypeAdapter.dump_json(messages).decode()
            assert "# Review this returned interaction" in (info.instructions or "")
            assert "feedback permitted at the current authored stage" in (
                info.instructions or ""
            )
            assert "A question followed by its own worked reasoning" in (
                info.instructions or ""
            )
            assert "leave the guiding question unanswered" in next(
                t.description for t in info.function_tools if t.name == "interact"
            )
            assert "An ordered checklist of the answer" in (info.instructions or "")
            assert "An internal list of all gaps is not the current hint" in (
                info.instructions or ""
            )
            assert "across both content and interaction fields" in (
                info.instructions or ""
            )
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
    session = await engine.new_session(script)
    await _events(engine.run_turn(session))
    assert session.pending[0].spec.variable is None
    assert session.pending[0].spec.placeholder == "Techniques and effects"
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
    assert session.script.script == script
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


@pytest.mark.parametrize(
    ("memory_keys", "script", "expected"),
    [
        (None, SCRIPT, False),
        (frozenset(), SCRIPT, True),
        (frozenset({"model_invented_key"}), SCRIPT, False),
        (frozenset(), SCRIPT + SECTION, False),
    ],
)
def test_only_host_rejected_variables_can_be_ignored_for_matching(
    memory_keys: frozenset[str] | None, script: str, expected: bool
) -> None:
    """Keep unrestricted, declared and ambiguous variable bindings conservative."""
    spec = _spec().model_copy(update={"variable": "model_invented_key"})
    messages = [
        ModelRequest(parts=[UserPromptPart(script)]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="interact",
                    args=spec.model_dump(),
                    tool_call_id="current",
                )
            ]
        ),
    ]
    before = ModelMessagesTypeAdapter.dump_json(messages)
    projected = project_answer_context(
        messages, script, {"current"}, memory_keys=memory_keys
    )
    assert (projected is not messages) == expected
    assert ModelMessagesTypeAdapter.dump_json(messages) == before
    if expected:
        assert json.loads(projected[0].parts[-1].content)["text"] == SECTION


async def _events(events: AsyncIterator[object]) -> list[object]:
    """Retain errors emitted by the streaming engine for assertions."""
    return [event async for event in events]
