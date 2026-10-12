"""Require an explicit feedback branch before supported answer prose is visible."""

import json
from collections.abc import AsyncIterator, Callable

import pytest
from flaskr.service.learn.agent.engine import (
    ContinueTurn,
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    InteractionSpec,
    Session,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    RetryPromptPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from .test_direction_feedback import (
    DISPLAY,
    RULE,
    SCRIPT,
    WRONG,
    _call,
    _collect,
    _direction,
    _text,
)


def _review(phase: str = "accepted", **updates: object) -> dict:
    return {
        "answer_id": "original",
        "phase": phase,
        "submission_quote": WRONG,
        "rule_quote": RULE if phase == "authored_help" else None,
        "reason": "The actual correction history permits this branch.",
        **updates,
    }


def _engine(stream: Callable[[list[ModelMessage], AgentInfo], AsyncIterator]) -> Engine:
    return Engine(
        FunctionModel(stream_function=stream),
        memory_recall=True,
        exercise_statistics=True,
        teaching_history_compaction=True,
        request_limit=2,
        feedback_contract=True,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_later_question_accepts_help_rule_from_the_lesson_header(
    reload: bool,
) -> None:
    calls = 0
    rule = "After two failed attempts, explain fully."
    script = "# Lesson\n" + rule + "\n## First\n?[...First]\n## Second\n?[...Second]\n"

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "First"}, "original"
            )
        elif calls == 2:
            yield "First answer accepted."
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Second",
                    "review": _review(),
                },
                "second",
            )
        else:
            yield "Authored later-stage help under the lesson-wide rule."
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Second",
                    "review": _review(
                        "authored_help", answer_id="second", rule_quote=rule
                    ),
                },
                "help",
            )

    engine = _engine(stream)
    engine.limits.request_limit = 1
    session = await engine.new_session(script)
    await _collect(engine.run_turn(session))
    await _collect(engine.run_turn(session, InteractionResponseTurn(text=WRONG)))
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "Authored later-stage help under the lesson-wide rule."
    assert session.pending[0].tool_call_id == "help"
    assert calls == 3


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("interact", {"type": "text", "prompt": "Try again", "placeholder": "Answer"}),
        ("finish", {"summary": "premature"}),
        ("remember", {"key": "unseen", "value": "must not write"}),
        ("recall", {}),
        ("read_exercise_history", {}),
        ("read_teaching", {"reference": "missing"}),
        ("calculate_exercise_statistics", {"questions": [{"question": "fake"}]}),
        ("", {}),
    ],
)
async def test_omitting_phase_cannot_release_worked_prose_or_side_effects(
    name: str, args: dict
) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Unreviewed worked answer must never become teaching."
            if name:
                yield {
                    0: DeltaToolCall(
                        name=name, json_args=json.dumps(args), tool_call_id="bad"
                    )
                }
        else:
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "direction": _direction(),
                },
                "correction",
            )

    engine = _engine(stream)
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == DISPLAY
    assert calls == 3  # One rejected response, one correction; no planning request.
    assert session.pending[0].tool_call_id == "correction"
    assert not session.finished
    assert session.memory == session.user_memory == {}
    raw = ModelMessagesTypeAdapter.dump_json(session.messages).decode()
    assert "Unreviewed worked answer" not in raw
    assert "correct the whole" in raw or "feedback branch" in raw
    from flaskr.service.learn.agent.gateway_model import map_messages

    assert all(
        message.get("content") or message.get("tool_calls")
        for message in map_messages(session.messages)
        if message["role"] == "assistant"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("phase", ["accepted", "clarification", "authored_help"])
@pytest.mark.parametrize("reload", [False, True])
async def test_declared_ordinary_branches_keep_authored_behavior_without_planning(
    phase: str, reload: bool
) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        assert (
            "review"
            in next(
                t for t in info.function_tools if t.name == "interact"
            ).parameters_json_schema["properties"]
        )
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        else:
            yield "Authored ordinary feedback."
            yield _call(
                {
                    "type": "single" if phase == "accepted" else "text",
                    "prompt": "",
                    "options": [{"display": "Next", "value": "Next"}]
                    if phase == "accepted"
                    else [],
                    "placeholder": None if phase == "accepted" else "Answer",
                    "review": _review(phase),
                },
                "next",
            )

    engine = _engine(stream)
    engine.limits.request_limit = 1
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "Authored ordinary feedback."
    assert calls == 2
    assert session.pending[0].tool_call_id == "next"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "review",
    [
        _review(answer_id="invented"),
        _review(submission_quote="authored sample mistake"),
        _review("authored_help", rule_quote="invented rule"),
        _review("authored_help", rule_quote=None),
        _review(reason=" "),
    ],
)
async def test_invalid_phase_provenance_retries_before_any_body(review: dict) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Invalid phase prose."
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "review": review,
                },
                "bad",
            )
        else:
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "direction": _direction(),
                },
                "correction",
            )

    engine = _engine(stream)
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == DISPLAY
    assert (
        "Invalid phase prose"
        not in ModelMessagesTypeAdapter.dump_json(session.messages).decode()
    )


@pytest.mark.anyio
async def test_lookup_before_feedback_and_paginated_report_inherit_declared_phase() -> (
    None
):
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield {
                0: DeltaToolCall(name="recall", json_args="{}", tool_call_id="lookup")
            }
        elif calls in (3, 4):
            yield "Report part."
            args = {"review": _review()} if calls == 3 else {}
            yield {
                0: DeltaToolCall(
                    name="read_exercise_history",
                    json_args=json.dumps(args),
                    tool_call_id=f"page-{calls}",
                )
            }
        else:
            yield "Report end."
            yield _call(
                {
                    "type": "single",
                    "prompt": "",
                    "options": [{"display": "Next", "value": "Next"}],
                },
                "next",
            )

    engine = _engine(stream)
    engine.limits.request_limit = 4
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "Report part.Report part.Report end."
    assert calls == 5
    assert session.pending[0].tool_call_id == "next"


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_unreviewed_provider_failure_keeps_original_answer_for_recovery(
    reload: bool,
) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Unreviewed partial reasoning."
            message = "provider interrupted before declaring feedback"
            raise RuntimeError(message)
        else:
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "direction": _direction(),
                },
                "correction",
            )

    engine = _engine(stream)
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    events = [
        e async for e in engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    ]
    assert _text(events) == ""
    assert any(isinstance(e, ErrorEvent) for e in events)
    assert session.answers["original"] == "Learner wrote: " + WRONG
    assert ModelMessagesTypeAdapter.dump_json(session.messages) == before
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(engine.run_turn(session, ContinueTurn()))
    assert _text(events) == DISPLAY
    assert session.pending[0].tool_call_id == "correction"


@pytest.mark.anyio
async def test_unsupported_text_anchor_keeps_ordinary_stream_without_review() -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        else:
            yield "Ordinary unsupported feedback."
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Follow-up"}, "next"
            )

    engine = _engine(stream)
    session = await engine.new_session(
        "Teach an open conversation without a uniquely authored input."
    )
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "Ordinary unsupported feedback."
    assert calls == 2


@pytest.mark.anyio
@pytest.mark.parametrize("retry_branch", ["omitted", "changed"])
@pytest.mark.parametrize("guard", ["host", "readonly"])
async def test_rejected_review_neither_displays_nor_commits_its_branch(
    retry_branch: str, guard: str
) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Rejected reviewed prose."
            yield _call(
                {
                    "type": "text",
                    "prompt": "Rejected" if guard == "host" else "",
                    "placeholder": "Answer",
                    "variable": "locked_value" if guard == "readonly" else None,
                    "review": _review(),
                },
                "rejected",
            )
        elif retry_branch == "omitted" and calls == 3:
            yield "Undeclared retry prose."
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "undeclared"
            )
        elif retry_branch == "omitted":
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "direction": _direction(),
                },
                "correction",
            )
        else:
            yield "Valid clarification."
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "review": _review("clarification"),
                },
                "clarification",
            )

    engine = _engine(stream)
    engine.limits.request_limit = 3
    engine.memory_readonly_prefixes = ("locked_",)
    engine.interaction_check = lambda spec: (
        "rejected by host" if spec.prompt == "Rejected" else None
    )
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == (
        DISPLAY if retry_branch == "omitted" else "Valid clarification."
    )
    assert session.pending[0].tool_call_id == (
        "correction" if retry_branch == "omitted" else "clarification"
    )
    raw = ModelMessagesTypeAdapter.dump_json(session.messages).decode()
    assert "Rejected reviewed prose" not in raw
    assert "Undeclared retry prose" not in raw
    assert calls == (4 if retry_branch == "omitted" else 3)


@pytest.mark.anyio
async def test_failed_inherited_interaction_preserves_prior_successful_review() -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Accepted report page."
            yield {
                0: DeltaToolCall(
                    name="read_exercise_history",
                    json_args=json.dumps({"review": _review()}),
                    tool_call_id="page",
                )
            }
        elif calls == 3:
            yield "Rejected inherited prose."
            yield _call(
                {"type": "text", "prompt": "Rejected", "placeholder": "Answer"},
                "rejected",
            )
        else:
            yield "Valid inherited continuation."
            yield _call({"type": "text", "prompt": "", "placeholder": "Answer"}, "next")

    engine = _engine(stream)
    engine.limits.request_limit = 3
    engine.interaction_check = lambda spec: (
        "rejected by host" if spec.prompt == "Rejected" else None
    )
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "Accepted report page.Valid inherited continuation."
    assert session.pending[0].tool_call_id == "next"
    assert calls == 4
    assert (
        "Rejected inherited prose"
        not in ModelMessagesTypeAdapter.dump_json(session.messages).decode()
    )


@pytest.mark.anyio
@pytest.mark.parametrize("parallel", [False, True])
@pytest.mark.parametrize("review_first", [False, True])
async def test_schema_rejection_hides_whole_response_and_requires_new_branch(
    parallel: bool, review_first: bool
) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Schema-rejected prose."
            parts = [
                DeltaToolCall(
                    name="read_exercise_history",
                    json_args=json.dumps(
                        {
                            "offset": "not an integer",
                            "review": _review() if not parallel else None,
                        }
                    ),
                    tool_call_id="invalid",
                )
            ]
            if parallel:
                reviewed = DeltaToolCall(
                    name="recall",
                    json_args=json.dumps({"review": _review()}),
                    tool_call_id="reviewed",
                )
                parts.insert(0 if review_first else 1, reviewed)
            yield dict(enumerate(parts))
        else:
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "direction": _direction(),
                },
                "correction",
            )

    engine = _engine(stream)
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == DISPLAY
    assert session.pending[0].tool_call_id == "correction"
    assert calls == 3
    assert (
        "Schema-rejected prose"
        not in ModelMessagesTypeAdapter.dump_json(session.messages).decode()
    )


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["provider", "tool"])
async def test_failure_after_successful_page_saves_only_already_visible_prose(
    failure: str,
) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Visible accepted page."
            yield {
                0: DeltaToolCall(
                    name="read_exercise_history",
                    json_args=json.dumps({"review": _review()}),
                    tool_call_id="page",
                )
            }
        else:
            yield "Undisplayed failed continuation."
            if failure == "provider":
                message = "provider interrupted"
                raise RuntimeError(message)
            yield _call(
                {"type": "text", "prompt": "Crash", "placeholder": "Answer"}, "crash"
            )

    def check(spec: InteractionSpec) -> None:
        if spec.prompt == "Crash":
            message = "host interrupted"
            raise RuntimeError(message)

    engine = _engine(stream)
    engine.interaction_check = check
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = [
        e async for e in engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    ]
    assert _text(events) == "Visible accepted page."
    assert any(isinstance(e, ErrorEvent) for e in events)
    assert session.interrupted
    raw = ModelMessagesTypeAdapter.dump_json(session.messages).decode()
    assert "Visible accepted page" in raw
    assert "Undisplayed failed continuation" not in raw


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("transport", ["text", "values"])
@pytest.mark.parametrize("branch", ["direction", "review"])
async def test_feedback_copies_explicit_returned_id_from_host_reference(
    reload: bool, transport: str, branch: str
) -> None:
    calls = 0
    answer_id = "call_provider_opaque_731"

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, answer_id
            )
        else:
            instructions = info.instructions or ""
            marker = '{"status":"authored_section"'
            reference = json.loads(instructions[instructions.index(marker) :])
            assert instructions.count(marker) == 1
            copied = reference["answer_id"]
            assert copied == answer_id
            assert copied != "Answer"
            args = {"type": "text", "prompt": "", "placeholder": "Answer"}
            if branch == "direction":
                args["direction"] = {**_direction(), "answer_id": copied}
            else:
                yield "Valid clarification."
                args["review"] = _review("clarification", answer_id=copied)
            yield _call(args, "next")

    engine = _engine(stream)
    engine.limits.request_limit = 1
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    turn = (
        InteractionResponseTurn(text=WRONG)
        if transport == "text"
        else InteractionResponseTurn(values=[WRONG])
    )
    events = await _collect(engine.run_turn(session, turn))
    assert _text(events) == (
        DISPLAY if branch == "direction" else "Valid clarification."
    )
    assert session.pending[0].tool_call_id == "next"
    assert calls == 2
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before
    assert not any(
        isinstance(p, UserPromptPart)
        and isinstance(p.content, str)
        and p.content.startswith('{"status":"authored_section"')
        for m in session.messages
        for p in m.parts
    )


@pytest.mark.anyio
@pytest.mark.parametrize("branch", ["direction", "review"])
async def test_unknown_feedback_id_retry_supplies_exact_supported_id(
    branch: str,
) -> None:
    calls = 0
    answer_id = "call_provider_opaque_953"

    async def stream(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, answer_id
            )
        else:
            selected = "course_answer_variable" if calls == 2 else answer_id
            if calls == 3:
                retry = [
                    p.content
                    for m in messages
                    for p in m.parts
                    if isinstance(p, RetryPromptPart)
                ]
                assert any(answer_id in str(content) for content in retry)
            args = {"type": "text", "prompt": "", "placeholder": "Answer"}
            if branch == "direction":
                args["direction"] = {**_direction(), "answer_id": selected}
            else:
                yield "Hidden invalid ID." if calls == 2 else "Valid clarification."
                args["review"] = _review("clarification", answer_id=selected)
            yield _call(args, "bad" if calls == 2 else "next")

    engine = _engine(stream)
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == (
        DISPLAY if branch == "direction" else "Valid clarification."
    )
    assert session.pending[0].tool_call_id == "next"
    assert calls == 3


@pytest.mark.anyio
@pytest.mark.parametrize("rejection", ["text", "host"])
async def test_retry_sees_delivery_status_and_regenerates_hidden_feedback(
    rejection: str,
) -> None:
    calls = 0

    async def stream(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Undisplayed passing explanation."
            if rejection == "host":
                yield _call(
                    {
                        "type": "single",
                        "prompt": "Rejected",
                        "options": [{"display": "Next"}],
                        "review": _review(),
                    },
                    "rejected",
                )
        else:
            from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

            assert not any(
                "Undisplayed passing explanation" in part.content
                for message in messages
                if isinstance(message, ModelResponse)
                for part in message.parts
                if isinstance(part, TextPart)
            )
            retries = [
                part
                for message in messages
                for part in message.parts
                if isinstance(part, RetryPromptPart)
            ]
            assert any("not displayed" in str(part.content) for part in retries)
            assert any("regenerate" in str(part.content).lower() for part in retries)
            if rejection == "host":
                assert any(
                    isinstance(part, ToolCallPart) and part.tool_call_id == "rejected"
                    for message in messages
                    for part in message.parts
                )
                assert any("rejected by host" in str(part.content) for part in retries)
            yield "Regenerated authored explanation before navigation."
            yield _call(
                {
                    "type": "single",
                    "prompt": "",
                    "options": [{"display": "Next"}],
                    "review": _review(),
                },
                "next",
            )

    engine = _engine(stream)
    engine.interaction_check = lambda spec: (
        "rejected by host" if spec.prompt == "Rejected" else None
    )
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "Regenerated authored explanation before navigation."
    assert session.pending[0].tool_call_id == "next"
    raw = ModelMessagesTypeAdapter.dump_json(session.messages).decode()
    assert "Undisplayed passing explanation" not in raw
    assert "not displayed" in raw
    assert calls == 3


@pytest.mark.anyio
@pytest.mark.parametrize("rejection", ["text", "host", "schema"])
@pytest.mark.parametrize("phase", ["accepted", "clarification", "authored_help"])
@pytest.mark.parametrize("terminal", ["interact", "finish"])
async def test_rejected_prose_cannot_be_replaced_by_only_an_ordinary_control(
    rejection: str, phase: str, terminal: str
) -> None:
    calls = 0

    async def stream(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Undisplayed explanation must be regenerated, not restored verbatim."
            if rejection != "text":
                yield _call(
                    {
                        "type": "invalid" if rejection == "schema" else "text",
                        "prompt": "Rejected",
                        "review": _review(phase),
                    },
                    "rejected",
                )
        elif calls == 3:
            # A valid internal reason and a question in prompt do not replace prose.
            args = (
                {
                    "summary": "Internal summary is not visible feedback",
                    "review": _review(phase),
                }
                if terminal == "finish"
                else {
                    "type": "text",
                    "prompt": "What is stored-program operation?",
                    "review": _review(phase),
                }
            )
            yield {
                0: DeltaToolCall(
                    name=terminal,
                    json_args=json.dumps(args),
                    tool_call_id="control-only",
                )
            }
        else:
            retries = [
                p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)
            ]
            assert any("regenerate" in str(p.content).lower() for p in retries)
            yield "New authored explanation delivered with its control."
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "review": _review(phase),
                },
                "complete",
            )

    engine = _engine(stream)
    engine.limits.request_limit = 3
    engine.interaction_check = lambda spec: (
        "rejected by host" if spec.prompt == "Rejected" else None
    )
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "New authored explanation delivered with its control."
    assert session.pending[0].tool_call_id == "complete"
    assert calls == 4
    assert not session.finished
    assert not any(isinstance(event, ErrorEvent) for event in events)
    raw = ModelMessagesTypeAdapter.dump_json(session.messages).decode()
    assert "Undisplayed explanation must" not in raw


@pytest.mark.anyio
@pytest.mark.parametrize("reject_control", [False, True])
async def test_authored_control_only_feedback_without_rejected_prose_stays_valid(
    reject_control: bool,
) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        else:
            yield _call(
                {
                    "type": "text",
                    "prompt": "Rejected" if reject_control and calls == 2 else "",
                    "placeholder": "Answer",
                    "review": _review("clarification"),
                },
                "replacement" if reject_control and calls == 3 else "control",
            )

    engine = _engine(stream)
    engine.interaction_check = lambda spec: (
        "rejected by host" if spec.prompt == "Rejected" else None
    )
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == ""
    assert session.pending[0].tool_call_id == (
        "replacement" if reject_control else "control"
    )
    assert calls == (3 if reject_control else 2)


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("terminal", ["interact", "finish"])
@pytest.mark.parametrize("lookup_first", [False, True])
async def test_initial_acceptance_cannot_omit_feedback_content(
    reload: bool, terminal: str, lookup_first: bool
) -> None:
    calls = 0

    async def stream(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if any(
            isinstance(p, ToolReturnPart) and p.tool_name == "finish"
            for m in messages
            for p in m.parts
        ):
            yield ""
            return
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
            return
        if lookup_first and calls == 2:
            yield {
                0: DeltaToolCall(
                    name="recall",
                    json_args=json.dumps({"review": _review()}),
                    tool_call_id="lookup",
                )
            }
            return
        rejected = calls == (3 if lookup_first else 2)
        if not rejected:
            retries = [
                p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)
            ]
            assert any("content" in str(p.content).lower() for p in retries)
            yield "Accepted answer with its authored explanation."
        args = (
            {"summary": "Accepted"}
            if terminal == "finish"
            else {"type": "single", "prompt": "Next", "options": [{"display": "Next"}]}
        )
        if not lookup_first:
            args["review"] = _review()
        yield {
            0: DeltaToolCall(
                name=terminal if rejected else "interact",
                json_args=json.dumps(
                    args
                    if rejected
                    else {
                        "type": "single",
                        "prompt": "",
                        "options": [{"display": "Next"}],
                        **({"review": _review()} if not lookup_first else {}),
                    }
                ),
                tool_call_id="omitted" if rejected else "complete",
            )
        }

    engine = _engine(stream)
    engine.limits.request_limit = 3
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "Accepted answer with its authored explanation."
    assert not session.finished
    assert session.pending[0].tool_call_id == "complete"
    assert calls == (4 if lookup_first else 3)


@pytest.mark.anyio
@pytest.mark.parametrize("foreign_quote", [False, True])
async def test_accepted_control_only_feedback_needs_an_actual_authored_rule(
    foreign_quote: bool,
) -> None:
    terminal = "interact"
    calls = 0
    rule = "After accepting an answer, show only the next control without explanation."

    async def stream(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if any(
            isinstance(p, ToolReturnPart) and p.tool_name == "finish"
            for m in messages
            for p in m.parts
        ):
            yield ""
            return
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
            return
        args = (
            {"summary": "Accepted"}
            if terminal == "finish"
            else {"type": "single", "prompt": "", "options": [{"display": "Next"}]}
        )
        args["review"] = _review(
            rule_quote="Foreign control-only rule"
            if foreign_quote and calls == 2
            else rule
        )
        yield {
            0: DeltaToolCall(
                name=terminal, json_args=json.dumps(args), tool_call_id="control"
            )
        }

    engine = _engine(stream)
    engine.limits.request_limit = 3
    session = await engine.new_session(rule + "\n" + SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == ""
    assert calls == (3 if foreign_quote else 2)
    assert session.finished == (terminal == "finish")


@pytest.mark.anyio
@pytest.mark.parametrize("deliver_at_lookup", [False, True])
async def test_lookup_alone_cannot_clear_undelivered_prose_but_a_visible_page_can(
    deliver_at_lookup: bool,
) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Rejected explanation."
        elif calls == 3:
            if deliver_at_lookup:
                yield "Replacement explanation before a successful lookup."
            yield {
                0: DeltaToolCall(
                    name="recall",
                    json_args=json.dumps({"review": _review()}),
                    tool_call_id="lookup",
                )
            }
        else:
            if calls == 5:
                yield "Replacement explanation with the final interaction."
            # The lookup committed a branch; terminal tools may inherit it.
            yield _call({"type": "text", "prompt": "", "placeholder": "Answer"}, "next")

    engine = _engine(stream)
    engine.limits.request_limit = 4
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == (
        "Replacement explanation before a successful lookup."
        if deliver_at_lookup
        else "Replacement explanation with the final interaction."
    )
    assert calls == (4 if deliver_at_lookup else 5)
    assert session.pending[0].tool_call_id == "next"


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("terminal", ["interact", "finish"])
async def test_retry_reports_missing_prose_and_invalid_rule_together(
    reload: bool, terminal: str
) -> None:
    """Repair both withheld content and source provenance within the existing retry."""
    calls = 0

    async def stream(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Undeclared explanation that was never displayed."
        elif calls == 3:
            args = (
                {"summary": "Not visible teaching"}
                if terminal == "finish"
                else {"type": "text", "prompt": "", "placeholder": "Answer"}
            )
            args["review"] = _review("authored_help", rule_quote="Invented rule")
            yield {
                0: DeltaToolCall(
                    name=terminal,
                    json_args=json.dumps(args),
                    tool_call_id="two-problems",
                )
            }
        else:
            retry = [
                p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)
            ][-1]
            assert "rule_quote" in str(retry.content)
            assert "not displayed" in str(retry.content)
            yield "New authored explanation with its exact current source."
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "review": _review("authored_help"),
                },
                "repaired",
            )

    engine = _engine(stream)
    engine.limits.request_limit = 3
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "New authored explanation with its exact current source."
    assert session.pending[0].tool_call_id == "repaired"
    assert calls == 4
    assert not session.finished


def test_retry_projection_preserves_successful_pages_and_raw_validation_errors() -> (
    None
):
    from flaskr.service.learn.agent.engine.direction import feedback_retry_history
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart

    accepted = ModelResponse(parts=[TextPart("Already displayed page.")])
    rejected = ModelResponse(
        parts=[
            TextPart("Undisplayed page."),
            ToolCallPart("interact", {"type": "invalid"}, "failed-control"),
        ]
    )
    retry = RetryPromptPart(
        content=[
            {
                "type": "string_type",
                "loc": ("type",),
                "msg": "Invalid control",
                "input": 4,
            }
        ],
        tool_name="interact",
        tool_call_id="failed-control",
    )
    request = ModelRequest(parts=[retry])
    messages = [accepted, rejected, request]
    before = ModelMessagesTypeAdapter.dump_json(messages)
    projected = feedback_retry_history(messages, {id(rejected)})
    assert projected[0] is accepted
    assert projected[1].parts == rejected.parts[1:]
    assert projected[-1].parts[0].tool_call_id == "failed-control"
    assert "Invalid control" in projected[-1].parts[0].content
    assert "not displayed" in projected[-1].parts[0].content
    assert ModelMessagesTypeAdapter.dump_json(messages) == before
    assert feedback_retry_history(projected, {id(rejected)}) is projected


@pytest.mark.anyio
@pytest.mark.parametrize("legacy_limit", ["missing", "null"])
async def test_saved_legacy_direction_can_resume_its_original_answer(
    legacy_limit: str,
) -> None:
    from pydantic_ai.messages import ToolCallPart

    calls = 0
    correct = "The program and data are stored before execution."

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "direction": _direction(),
                },
                "legacy-correction",
            )
        else:
            yield "Accepted complete correction."
            yield _call(
                {
                    "type": "single",
                    "prompt": "",
                    "options": [{"display": "Next"}],
                    "review": _review(
                        answer_id="legacy-correction", submission_quote=correct
                    ),
                },
                "next",
            )

    engine = _engine(stream)
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    await _collect(engine.run_turn(session, InteractionResponseTurn(text=WRONG)))
    for message in session.messages:
        for part in message.parts:
            if (
                isinstance(part, ToolCallPart)
                and part.tool_call_id == "legacy-correction"
            ):
                args = part.args_as_dict()
                if legacy_limit == "missing":
                    args["direction"].pop("aspect_limit")
                else:
                    args["direction"]["aspect_limit"] = None
                args["direction"].pop("accepted_quotes")
                part.args = json.dumps(args)
    session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=correct))
    )
    assert _text(events) == "Accepted complete correction."
    assert session.pending[0].tool_call_id == "next"
    assert calls == 3


def test_rejected_text_with_thinking_does_not_leave_an_empty_provider_assistant() -> (
    None
):
    from flaskr.service.learn.agent.engine.direction import feedback_retry_history
    from flaskr.service.learn.agent.gateway_model import map_messages
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ThinkingPart

    rejected = ModelResponse(
        parts=[ThinkingPart("Private reasoning."), TextPart("Undisplayed explanation.")]
    )
    request = ModelRequest(parts=[RetryPromptPart("Declare the feedback branch.")])
    projected = feedback_retry_history([rejected, request], {id(rejected)})
    assert projected == [projected[-1]]
    assert all(
        message.get("content") or message.get("tool_calls")
        for message in map_messages(projected)
        if message["role"] == "assistant"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("tag_review", [False, True])
async def test_textual_interaction_reports_markup_and_feedback_errors_together(
    reload: bool, tag_review: bool
) -> None:
    """Repair rejected prose and a text imitation in the same existing retry."""
    calls = 0
    tag = '<interact type="text" prompt="Answer"'
    if tag_review:
        tag += " review='" + json.dumps(_review("clarification")) + "'"
    tag += " /></interact>"

    async def stream(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Undisplayed explanation with a fake control.\n" + tag
        else:
            retry = [
                p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)
            ][-1]
            assert "Declare the feedback branch" in str(retry.content)
            assert "tag as text instead of calling a tool" in str(retry.content)
            assert "No question was created" in str(retry.content)
            yield "New explanation supplied together with its real control."
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "review": _review("clarification"),
                },
                "repaired",
            )

    engine = _engine(stream)
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "New explanation supplied together with its real control."
    assert session.pending[0].tool_call_id == "repaired"
    assert calls == 3
    assert not session.finished
    assert not session.memory
    raw = session.dumps()
    assert "Undisplayed explanation with a fake control" not in raw
    assert tag not in _text(events)


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("phase", ["accepted", "clarification", "authored_help"])
async def test_control_only_retry_retains_native_feedback_recovery(
    reload: bool, phase: str
) -> None:
    """Keep native-tool and complete-content guidance after rejected text is projected out."""
    calls = 0

    async def stream(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        args = {"type": "text", "prompt": "", "placeholder": "Answer"}
        if calls == 1:
            yield _call(args, "original")
        elif calls == 2:
            yield 'Undisplayed explanation.\n<interact type="text" />'
        elif calls == 3:
            yield _call({**args, "review": _review(phase)}, "control-only")
        else:
            retry = [
                p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)
            ][-1]
            assert "Earlier feedback prose was not displayed" in str(retry.content)
            assert "Use actual tool calls, not textual interaction tags" in str(
                retry.content
            )
            assert "applicable branch in the same response" in str(retry.content)
            assert (
                "Undisplayed explanation"
                not in ModelMessagesTypeAdapter.dump_json(messages).decode()
            )
            yield "Fresh explanation with its native control."
            yield _call({**args, "review": _review(phase)}, "complete")

    engine = _engine(stream)
    # Match the three generations already spent by the failed real turn.
    engine.limits.request_limit = 3
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "Fresh explanation with its native control."
    assert session.pending[0].tool_call_id == "complete"
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert not session.finished
    assert not session.memory
    assert calls == 4


def test_pending_feedback_retry_notice_is_idempotent_without_rejected_prose() -> None:
    """A repeated request projection retains the latest recovery notice exactly once."""
    from flaskr.service.learn.agent.engine.direction import feedback_retry_history
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart

    successful = ModelResponse(parts=[TextPart("Earlier displayed page.")])
    request = ModelRequest(
        parts=[RetryPromptPart(content="Earlier feedback prose was not displayed.")]
    )
    messages = [successful, request]
    projected = feedback_retry_history(messages, set(), feedback_text_pending=True)
    repeated = feedback_retry_history(projected, set(), feedback_text_pending=True)
    assert repeated == projected
    assert repeated[0] is successful
    assert messages[-1] is request
    notice = str(repeated[-1].parts[0].content)
    assert notice.count("Use actual tool calls, not textual interaction tags") == 1
    assert feedback_retry_history(messages, set()) is messages


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_unmatched_conditional_hint_keeps_actual_contradiction_in_current_scope(
    reload: bool,
) -> None:
    """Require an explicit fallback without a host selecting the matching case."""
    rule = "Select one missing aspect and wait for a correction."
    criterion = "store instructions in memory"
    sample = "If the learner only mentions saving a disk file, ask about preparation, fetching and automatic sequencing."
    script = (
        rule
        + "\n\n## Question\n?[...Answer]\n\n### Acceptance\nPrepare the program; store instructions in memory; execute automatically.\n\n### Hints\n"
        + sample
    )
    actual = "Instructions need not be stored in memory before execution."
    calls = 0

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        else:
            instructions = info.instructions or ""
            marker = '{"status":"authored_section"'
            reference = json.loads(instructions[instructions.index(marker) :])
            assert sample in reference["text"]
            assert "When no conditional example matches" in reference["notice"]
            assert "actual submission" in reference["notice"]
            assert "compound criterion" in reference["notice"]
            assert actual in ModelMessagesTypeAdapter.dump_json(messages).decode()
            tool = next(t for t in info.function_tools if t.name == "interact")
            assert "exact clause" in json.dumps(tool.parameters_json_schema).lower()
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "direction": {
                        "answer_id": "original",
                        "rule_quote": rule,
                        "aspect_limit": 1,
                        "accepted_quotes": [],
                        "focuses": [
                            {
                                "criterion_quote": criterion,
                                "submission_quote": actual,
                                "observed_issue": "Denies instruction storage before execution.",
                                "guiding_question": "Where can the processor fetch its next instruction?",
                            }
                        ],
                    },
                },
                "correction",
            )

    engine = _engine(stream)
    session = await engine.new_session(script)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=actual))
    )
    assert not any(isinstance(e, ErrorEvent) for e in events)
    assert calls == 2
    assert (
        _text(events)
        == "> " + actual + "\n\nWhere can the processor fetch its next instruction?"
    )
    assert session.pending[0].tool_call_id == "correction"
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before
