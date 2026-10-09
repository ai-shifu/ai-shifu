"""Original evidence, reference coverage and exercise arithmetic regressions."""

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from flaskr.service.learn.agent.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    Session,
    TurnDone,
)
from flaskr.service.learn.agent.engine.exercise_statistics import (
    RESULT_BYTES,
    ExerciseQuestion,
    SubmissionJudgment,
    _records,
    calculate_exercise_statistics,
    read_exercise_history,
)
from flaskr.service.learn.agent.engine.script import ScriptBundle
from flaskr.service.learn.agent.engine.tools import LESSON_OVER, Deps
from pydantic import ValidationError
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from scripts.mdf2_memory_quality.exercise import exercise_session


def _ctx(messages: list[ModelMessage]) -> SimpleNamespace:
    return SimpleNamespace(
        deps=Deps(
            memory={},
            user_memory={},
            exercise_history=tuple(messages),
            history_len=len(messages),
        ),
        messages=list(messages),
    )


def _fixture() -> SimpleNamespace:
    return _ctx(exercise_session({"corrected_questions": [1, 6, 10]}).messages)


def _questions(ctx: SimpleNamespace) -> list[ExerciseQuestion]:
    records = _records(ctx)
    assert records is not None
    rows = []
    at = 0
    for number in range(1, 12):
        count = 2 if number in {1, 6, 10} else 1
        rows.append(
            ExerciseQuestion(
                question=str(number),
                submissions=[
                    SubmissionJudgment(
                        reference=records[at + i]["reference"],
                        outcome="incorrect" if count == 2 and i == 0 else "correct",
                    )
                    for i in range(count)
                ],
                hints=count - 1,
                hints_before_first=0,
            )
        )
        at += count
    return rows


@pytest.mark.anyio
async def test_counts_preserve_early_corrections_and_derive_every_total() -> None:
    ctx = _fixture()
    before = ModelMessagesTypeAdapter.dump_json(ctx.messages)
    result = json.loads(await calculate_exercise_statistics(ctx, _questions(ctx)))
    assert result["status"] == "calculated"
    assert result["totals"] == {
        "passed": 11,
        "attempts": 14,
        "retries": 3,
        "failed_submissions": 3,
        "unverified_submissions": 0,
        "hints": 3,
        "first_correct": 8,
        "corrected": 3,
        "unanswered": 0,
        "unresolved_first": 0,
        "hint_questions": 3,
        "independent_first": 8,
    }
    assert [r["question"] for r in result["questions"] if not r["first_correct"]] == [
        "1",
        "6",
        "10",
    ]
    assert ModelMessagesTypeAdapter.dump_json(ctx.messages) == before
    assert not ctx.deps.memory
    assert not ctx.deps.user_memory


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mutation",
    ["missing", "unknown", "duplicate", "duplicate_question", "order", "hints"],
)
async def test_invalid_evidence_never_produces_successful_totals(mutation: str) -> None:
    ctx = _fixture()
    rows = _questions(ctx)
    if mutation == "missing":
        rows[0].submissions.pop()
    elif mutation == "unknown":
        rows[0].submissions[0].reference = "not-in-this-session"
    elif mutation == "duplicate":
        rows[0].submissions.append(rows[0].submissions[0])
    elif mutation == "duplicate_question":
        rows[1].question = rows[0].question
    elif mutation == "order":
        rows[0].submissions.reverse()
    else:
        rows[0].hints_before_first = 2
    result = json.loads(await calculate_exercise_statistics(ctx, rows))
    assert result["status"] != "calculated"
    assert "totals" not in result


@pytest.mark.anyio
async def test_unknown_and_unanswered_remain_unresolved_and_nonquiz_is_explicit() -> (
    None
):
    ctx = _fixture()
    records = _records(ctx)
    first = records[0]["reference"]
    rows = [
        ExerciseQuestion(
            question="1",
            submissions=[SubmissionJudgment(reference=first, outcome="unverified")],
        ),
        ExerciseQuestion(question="unanswered", submissions=[]),
    ]
    result = json.loads(
        await calculate_exercise_statistics(
            ctx, rows, [r["reference"] for r in records[1:]]
        )
    )
    assert result["totals"]["unresolved_first"] == 2
    assert result["totals"]["unanswered"] == 1
    assert (
        result["totals"]["first_correct"]
        == result["totals"]["corrected"]
        == result["totals"]["passed"]
        == 0
    )
    assert result["excluded_answers"] == 13


@pytest.mark.anyio
@pytest.mark.parametrize("text", ["中文é🙂" * 4000, '\n\t"\\' * 4000])
async def test_exact_pages_bound_utf8_json_and_freeze_during_the_run(text: str) -> None:
    messages = [
        ModelResponse(
            parts=[
                TextPart(text),
                ToolCallPart("interact", {"type": "text", "prompt": "Question"}, "q"),
            ]
        ),
        ModelRequest(parts=[ToolReturnPart("interact", "Learner wrote: " + text, "q")]),
        ModelResponse(parts=[TextPart("Original feedback " + text)]),
    ]
    ctx = _ctx(messages)
    source = ""
    offset = 0
    while True:
        encoded = await read_exercise_history(ctx, offset)
        assert len(encoded.encode()) <= RESULT_BYTES
        page = json.loads(encoded)
        source += page["text"]
        # Later model text must not move the pagination source.
        ctx.messages.append(ModelResponse(parts=[TextPart("Later writing.")]))
        if page["next_offset"] is None:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    records = json.loads(source)
    assert records[0]["answer"] == "Learner wrote: " + text
    assert records[0]["teaching"] == text
    assert records[0]["following_teaching"] == ["Original feedback " + text]
    assert (
        json.loads(await read_exercise_history(ctx, -1))["status"] == "invalid_offset"
    )
    assert (
        json.loads(await read_exercise_history(ctx, len(source) + 1))["status"]
        == "invalid_offset"
    )


@pytest.mark.anyio
async def test_rewind_reload_and_duplicate_pairing_cannot_reuse_old_references() -> (
    None
):
    ctx = _fixture()
    rows = _questions(ctx)
    messages = ModelMessagesTypeAdapter.validate_json(
        ModelMessagesTypeAdapter.dump_json(ctx.messages[:3])
    )
    rewound = _ctx(messages)
    assert (
        json.loads(await calculate_exercise_statistics(rewound, rows))["status"]
        == "invalid_coverage"
    )
    duplicate = _fixture()
    duplicate.messages.append(duplicate.messages[1])
    duplicate.deps.exercise_history = tuple(duplicate.messages)
    duplicate.deps.history_len = len(duplicate.messages)
    assert (
        json.loads(await read_exercise_history(duplicate))["status"]
        == "invalid_history"
    )
    other = _ctx([])
    assert (
        json.loads(await calculate_exercise_statistics(other, rows))["status"]
        == "invalid_coverage"
    )
    ctx.deps.finished = "done"
    assert await read_exercise_history(ctx) == LESSON_OVER
    assert await calculate_exercise_statistics(ctx, rows) == LESSON_OVER


@pytest.mark.parametrize("hints", [True, -1, "1", 201])
def test_hint_types_are_strict(hints: object) -> None:
    with pytest.raises(ValidationError):
        ExerciseQuestion(question="1", submissions=[], hints=hints)


@pytest.mark.anyio
async def test_engine_deferred_resume_reads_original_answer_and_feedback() -> None:
    step = 0

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal step
        step += 1
        assert {"read_exercise_history", "calculate_exercise_statistics"} <= {
            t.name for t in info.function_tools
        }
        if step == 1:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    json_args='{"type":"text","prompt":"What is 1+1?"}',
                    tool_call_id="q",
                )
            }
        elif step == 2:
            yield "Correct."
            yield {
                0: DeltaToolCall(
                    name="read_exercise_history", json_args="{}", tool_call_id="read"
                )
            }
        elif step == 3:
            page = next(p for p in messages[-1].parts if isinstance(p, ToolReturnPart))
            record = json.loads(json.loads(page.content)["text"])[0]
            assert record["answer"] == "Learner wrote: 2"
            assert record["following_teaching"] == ["Correct."]
            yield {
                0: DeltaToolCall(
                    name="calculate_exercise_statistics",
                    json_args=json.dumps(
                        {
                            "questions": [
                                {
                                    "question": "1",
                                    "submissions": [
                                        {
                                            "reference": record["reference"],
                                            "outcome": "correct",
                                        }
                                    ],
                                }
                            ]
                        }
                    ),
                    tool_call_id="calc",
                )
            }
        elif step == 4:
            result = json.loads(messages[-1].parts[0].content)
            assert result["totals"]["first_correct"] == 1
            yield {
                0: DeltaToolCall(
                    name="finish", json_args='{"summary":"Done"}', tool_call_id="end"
                )
            }
        else:
            yield ""

    engine = Engine(FunctionModel(stream_function=model), exercise_statistics=True)
    session = Session(script=ScriptBundle(script="Ask and report."))
    await _collect(engine.run_turn(session))
    session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(id="q", text="2"))
    )
    assert not any(isinstance(e, ErrorEvent) for e in events)
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "finished"


async def _collect(events: AsyncIterator[object]) -> list[object]:
    return [event async for event in events]


@pytest.mark.anyio
async def test_unknown_hint_counts_are_not_silently_zero() -> None:
    ctx = _fixture()
    rows = _questions(ctx)
    rows[1].hints = None
    rows[1].hints_before_first = None
    result = json.loads(await calculate_exercise_statistics(ctx, rows))
    assert result["questions"][1]["hints"] is None
    assert result["totals"]["hints"] is None
    assert result["totals"]["hint_questions"] is None
    assert result["totals"]["independent_first"] is None


@pytest.mark.anyio
async def test_large_report_is_refused_with_bounded_result() -> None:
    ctx = _ctx([])
    rows = [
        ExerciseQuestion(question=str(i) + "x" * 70, submissions=[]) for i in range(100)
    ]
    result = await calculate_exercise_statistics(ctx, rows)
    assert json.loads(result)["status"] == "report_too_large"
    assert len(result.encode()) <= RESULT_BYTES


@pytest.mark.anyio
async def test_projection_never_replaces_original_evidence_and_refusals_are_not_answers() -> (
    None
):
    ctx = _fixture()
    ctx.messages[1] = ModelResponse(parts=[TextPart("Projected excerpt")])
    records = _records(ctx)
    assert len(records) == 14
    assert records[0]["teaching"] == "Question 1: What is 1 + 1?"
    messages = list(ctx.deps.exercise_history[:3])
    messages[2] = ModelRequest(
        parts=[
            ToolReturnPart(
                "interact", "This question could not be shown.", "question-1-attempt-1"
            )
        ]
    )
    assert json.loads(await read_exercise_history(_ctx(messages)))["text"] == "[]"
    orphan = _ctx(
        [
            ModelRequest(
                parts=[ToolReturnPart("interact", "Learner wrote: lost", "orphan")]
            )
        ]
    )
    assert (
        json.loads(await read_exercise_history(orphan))["status"] == "invalid_history"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("boundary", ["continue", "new_answer"])
async def test_following_teaching_stops_at_the_next_learner_turn(boundary: str) -> None:
    messages = [
        ModelResponse(
            parts=[
                ToolCallPart("interact", {"type": "text", "prompt": "Question 1"}, "q")
            ]
        ),
        ModelRequest(parts=[ToolReturnPart("interact", "Learner wrote: 2", "q")]),
        ModelResponse(
            parts=[
                TextPart("Correct."),
                ToolCallPart("recall", {"key": "example"}, "read"),
            ]
        ),
        ModelRequest(parts=[ToolReturnPart("recall", "unavailable", "read")]),
        ModelResponse(parts=[TextPart("Same-turn explanation.")]),
        ModelRequest(
            parts=[UserPromptPart("continue")]
            if boundary == "continue"
            else [ToolReturnPart("interact", "Learner wrote: unrelated", "next")]
        ),
        ModelResponse(
            parts=[TextPart("Later inaccurate report or unrelated teaching.")]
        ),
    ]
    # The accepted-answer boundary helper is tested independently of orphan validation.
    from flaskr.service.learn.agent.engine.exercise_statistics import (
        _following_teaching,
    )

    text, following = _following_teaching(messages, 1)
    assert text == ["Correct.", "Same-turn explanation."]
    assert following is None


@pytest.mark.anyio
async def test_combined_teaching_preserves_context_and_stops_at_call_part() -> None:
    mixed = "Correct. Question 2: What is 3 + 4?"
    messages = [
        ModelResponse(
            parts=[
                ToolCallPart("interact", {"type": "text", "prompt": "Question 1"}, "q")
            ]
        ),
        ModelRequest(parts=[ToolReturnPart("interact", "Learner wrote: 2", "q")]),
        ModelResponse(
            parts=[
                TextPart(mixed),
                ToolCallPart(
                    "interact", {"type": "text", "prompt": "Question 2"}, "next"
                ),
                TextPart("After the next question's call."),
            ]
        ),
    ]
    records = _records(_ctx(messages))
    assert len(records) == 1
    assert records[0]["following_teaching"] == [mixed]
    assert records[0]["following_interaction"] == {
        "type": "text",
        "prompt": "Question 2",
    }


@pytest.mark.anyio
async def test_simultaneous_answers_share_explicit_teaching_context() -> None:
    messages = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    "interact", {"type": "text", "prompt": f"Question {i}"}, f"q{i}"
                )
                for i in (1, 2)
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart("interact", f"Learner wrote: {i + 1}", f"q{i}")
                for i in (1, 2)
            ]
        ),
        ModelResponse(
            parts=[TextPart("Question 1 is correct; question 2 needs correction.")]
        ),
    ]
    records = _records(_ctx(messages))
    assert len(records) == 2
    assert records[0]["answer_group"] == records[1]["answer_group"]
    assert records[0]["following_teaching"] == records[1]["following_teaching"]
    assert records[0]["question"] != records[1]["question"]


@pytest.mark.anyio
async def test_known_zero_hints_establishes_independence_when_before_first_is_omitted() -> (
    None
):
    ctx = _fixture()
    rows = _questions(ctx)
    for row in rows:
        if row.hints == 0:
            row.hints_before_first = None
    result = json.loads(await calculate_exercise_statistics(ctx, rows))
    assert result["totals"]["independent_first"] == 8
    assert all(
        r["hints_before_first"] == 0 for r in result["questions"] if r["hints"] == 0
    )
