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

    async def stream(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, answer_id
            )
        else:
            reference = next(
                json.loads(p.content)
                for m in messages
                for p in m.parts
                if isinstance(p, UserPromptPart)
                and isinstance(p.content, str)
                and p.content.startswith('{"status":"authored_section"')
            )
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
