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
    answer_reference_instructions,
    authored_answer_reference,
    authored_answer_section,
    without_answer_reference,
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
            instructions = info.instructions or ""
            marker = '{"status":"authored_section"'
            focused = [json.loads(instructions[instructions.index(marker) :])]
            assert len(focused) == 1
            assert list(focused[0]) == [
                "status",
                "answer_id",
                "text",
                "ancestor_preambles",
                "notice",
            ]
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
    projected = authored_answer_reference(
        messages, script, {"current"}, memory_keys=memory_keys
    )
    assert (projected is not None) == expected
    assert ModelMessagesTypeAdapter.dump_json(messages) == before
    if expected:
        assert json.loads(projected)["text"] == SECTION


async def _events(events: AsyncIterator[object]) -> list[object]:
    """Retain errors emitted by the streaming engine for assertions."""
    return [event async for event in events]


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize(
    "rule",
    [
        "On a failed answer, choose one missing requirement and wait.",
        "On a failed answer, ask two guiding questions before waiting.",
        "On a failed answer, give the authored checking direction.",
    ],
)
async def test_later_answer_sdk_keeps_enclosing_rules_with_local_hint(
    reload: bool, rule: str
) -> None:
    """Project parent instructions without sibling answers or durable rewrites."""
    root = rule + "\n\n"
    unit = "# Unit\nKeep accepted parts while collecting a correction.\n\n"
    local = SECTION.replace(
        "Ask one genuinely missing aspect.",
        "Check processor, transfer, peripheral and software coverage.",
    )
    script = root + unit + SCRIPT.removeprefix("# Exercise\n\n").replace(SECTION, local)
    calls = 0

    async def model(
        _messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Inspect the actual request after resuming a later authored input."""
        nonlocal calls
        calls += 1
        if calls == 2:
            instructions = info.instructions or ""
            marker = '{"status":"authored_section"'
            refs = [json.loads(instructions[instructions.index(marker) :])]
            assert len(refs) == 1
            assert refs[0]["text"] == local
            assert refs[0]["ancestor_preambles"] == [root, unit]
            assert "Earlier answer" not in "".join(refs[0]["ancestor_preambles"])
            assert "Later answer" not in "".join(refs[0]["ancestor_preambles"])
        yield {
            0: DeltaToolCall(
                name="interact",
                json_args=json.dumps(
                    _spec().model_dump(exclude={"labelled_by_engine"})
                ),
                tool_call_id=f"scope-{calls}",
            )
        }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session(script)
    initial = await _events(engine.run_turn(session))
    assert not [e for e in initial if isinstance(e, ErrorEvent)]
    assert calls == 1
    if reload:
        session = Session.loads(session.dumps())
    original = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    events = await _events(
        engine.run_turn(session, InteractionResponseTurn(text="Actual answer"))
    )
    assert not [e for e in events if isinstance(e, ErrorEvent)]
    assert calls == 2
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == original
    assert not any(
        isinstance(p, UserPromptPart)
        and p.content.startswith('{"status":"authored_section"')
        for m in session.messages
        for p in m.parts
    )
    assert session.script.script == script


@pytest.mark.parametrize(
    "parent",
    [
        pytest.param("x" * 8192, id="oversized"),
        pytest.param("Keep {{learner_fact}} in view.", id="variable"),
    ],
)
def test_unprojectable_parent_does_not_present_a_local_only_rule(parent: str) -> None:
    """Keep the opaque answer binding while declining an incomplete focused copy."""
    script = parent + "\n\n" + SCRIPT
    messages = [
        ModelRequest(parts=[UserPromptPart(script)]),
        ModelResponse(
            parts=[ToolCallPart("interact", _spec().model_dump(), "current")]
        ),
    ]
    projected = authored_answer_reference(messages, script, {"current"})
    ref = json.loads(projected)
    assert ref["answer_id"] == "current"
    assert ref["text"] is None
    assert ref["ancestor_preambles"] == []
    assert messages[0].parts[0].content == script


def test_sibling_unit_introductions_do_not_become_current_rules() -> None:
    """A first heading at offset zero is not an implicit ancestor of later units."""
    earlier = "# Earlier unit\nExplain every missing point immediately.\n\n"
    current = "# Current unit\nChoose one missing point and wait.\n\n"
    script = (
        earlier
        + "?[...Earlier]\n\n"
        + current
        + "## Current warmup\n?[...Current warmup]\n\n"
        + SECTION
    )
    messages = [
        ModelRequest(parts=[UserPromptPart(script)]),
        ModelResponse(
            parts=[ToolCallPart("interact", _spec().model_dump(), "current")]
        ),
    ]
    projected = authored_answer_reference(messages, script, {"current"})
    ref = json.loads(projected)
    assert ref["text"] == SECTION
    assert ref["ancestor_preambles"] == [current]


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_current_feedback_instructions_end_with_complete_authored_scope(
    reload: bool,
) -> None:
    """An old question's user prompt must not own the current feedback policy."""
    root = (
        "On the first failed answer, select one concrete missing aspect and wait.\n\n"
    )
    local = SECTION.replace(
        "Ask one genuinely missing aspect.",
        "Possible checks include processor, transfer, peripheral and software coverage.",
    )
    script = root + SCRIPT.replace(SECTION, local)
    calls = 0

    async def model(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 2:
            instructions = info.instructions or ""
            marker = '{"status":"authored_section"'
            assert marker in instructions
            reference = json.loads(instructions[instructions.index(marker) :])
            assert reference["ancestor_preambles"] == [root]
            assert reference["text"] == local
            assert reference["answer_id"] == "current-policy-1"
            assert not any(
                isinstance(p, UserPromptPart)
                and isinstance(p.content, str)
                and p.content.startswith(marker)
                for m in messages
                for p in m.parts
            )
            assert any(
                isinstance(p, ToolReturnPart)
                and "Actual partial answer" in str(p.content)
                for m in messages
                for p in m.parts
            )
        yield {
            0: DeltaToolCall(
                name="interact",
                json_args=json.dumps(
                    _spec().model_dump(exclude={"labelled_by_engine"})
                ),
                tool_call_id=f"current-policy-{calls}",
            )
        }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session(script)
    await _events(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    events = await _events(
        engine.run_turn(session, InteractionResponseTurn(text="Actual partial answer"))
    )
    assert calls == 2
    assert not any(isinstance(e, ErrorEvent) for e in events)
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before
    assert not any(
        isinstance(m, ModelRequest)
        and "# Current authored feedback scope" in (m.instructions or "")
        for m in session.messages
    )


@pytest.mark.parametrize("suffix_present", [False, True])
def test_only_current_instruction_reference_is_removed_from_saved_history(
    suffix_present: bool,
) -> None:
    """Never erase an authored/learner lookalike or a different run's guidance."""
    reference = '{"status":"authored_section","answer_id":"current"}'
    suffix = answer_reference_instructions(reference)
    instructions = "Original current instructions" + (
        suffix if suffix_present else suffix + "Keep this unrelated trailing rule"
    )
    messages = [
        ModelRequest(parts=[UserPromptPart(reference)], instructions=instructions),
        ModelResponse(
            parts=[ToolCallPart("interact", {"prompt": reference}, "current")]
        ),
    ]
    before = ModelMessagesTypeAdapter.dump_json(messages)
    projected = without_answer_reference(messages, reference)
    assert projected[0].parts == messages[0].parts
    assert projected[1] is messages[1]
    assert projected[0].instructions == (
        "Original current instructions" if suffix_present else instructions
    )
    assert ModelMessagesTypeAdapter.dump_json(messages) == before
    assert without_answer_reference(messages, None) is messages


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_interrupted_teaching_keeps_answer_without_current_reference(
    reload: bool,
) -> None:
    """A projected instruction must not become stored evidence after stream failure."""
    calls = 0

    async def model(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    json_args=json.dumps(
                        _spec().model_dump(exclude={"labelled_by_engine"})
                    ),
                    tool_call_id="interrupted-answer",
                )
            }
        elif calls == 2:
            assert '{"status":"authored_section"' in (info.instructions or "")
            yield "Already delivered teaching. " * 200
            yield {
                0: DeltaToolCall(
                    name="read_exercise_history",
                    json_args=json.dumps(
                        {
                            "review": {
                                "phase": "clarification",
                                "answer_id": "interrupted-answer",
                                "submission_quote": "Original answer evidence",
                                "reason": "Answer the side question under the current author rules.",
                            }
                        }
                    ),
                    tool_call_id="lookup",
                )
            }
        else:
            message = "Interrupted provider"
            raise RuntimeError(message)

    engine = Engine(
        FunctionModel(stream_function=model),
        exercise_statistics=True,
        feedback_contract=True,
    )
    session = await engine.new_session(SCRIPT)
    await _events(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    events = await _events(
        engine.run_turn(
            session, InteractionResponseTurn(text="Original answer evidence")
        )
    )
    assert any(
        isinstance(e, ErrorEvent) and "Interrupted provider" in e.message
        for e in events
    )
    assert session.interrupted
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before
    raw = session.dumps()
    assert "Original answer evidence" in raw
    assert "Already delivered teaching" in raw
    assert not any(
        isinstance(m, ModelRequest)
        and "# Current authored feedback scope" in (m.instructions or "")
        for m in session.messages
    )
