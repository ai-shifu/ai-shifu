"""Original evidence, reference coverage and exercise arithmetic regressions."""

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from markdownflow.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    Session,
    TurnDone,
)
from markdownflow.engine.exercise_statistics import (
    RESULT_BYTES,
    ExerciseQuestion,
    SubmissionJudgment,
    _records,
    calculate_exercise_statistics,
    read_exercise_history,
)
from markdownflow.engine.script import ScriptBundle
from markdownflow.engine.tools import LESSON_OVER, Deps
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
                        hint_after=count == 2 and i == 0,
                    )
                    for i in range(count)
                ],
                hints=count - 1,
                hints_before_first=0,
                hint_before=False,
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


def _with_navigation() -> SimpleNamespace:
    """Retain a next-step click represented as an ordinary single choice."""
    messages = list(_fixture().messages)
    messages.extend(
        [
            ModelResponse(
                parts=[
                    ToolCallPart(
                        "interact",
                        {"type": "single", "options": ["Next question"]},
                        "navigation",
                    )
                ]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        "interact", "Learner chose: Next question", "navigation"
                    )
                ]
            ),
        ]
    )
    return _ctx(messages)


@pytest.mark.anyio
async def test_navigation_requires_explicit_exclusion_and_reports_the_missing_reference() -> (
    None
):
    ctx = _with_navigation()
    before = ModelMessagesTypeAdapter.dump_json(ctx.messages)
    records = _records(ctx)
    assert records is not None
    assert len(records) == 15
    navigation = records[-1]["reference"]
    rows = _questions(ctx)
    refused = json.loads(await calculate_exercise_statistics(ctx, rows))
    assert refused["status"] == "invalid_coverage"
    assert refused["missing_references"] == [navigation]
    assert refused["unknown_references"] == refused["duplicate_references"] == []
    assert not refused["diagnostics_truncated"]
    assert "totals" not in refused
    assert ctx.deps.exercise_report_totals is None
    repaired = json.loads(await calculate_exercise_statistics(ctx, rows, [navigation]))
    assert repaired["status"] == "calculated"
    assert repaired["excluded_answers"] == 1
    assert repaired["totals"]["attempts"] == 14
    assert repaired["totals"]["first_correct"] == 8
    assert ModelMessagesTypeAdapter.dump_json(ctx.messages) == before


@pytest.mark.anyio
async def test_coverage_diagnostics_distinguish_missing_unknown_and_duplicate_references() -> (
    None
):
    ctx = _fixture()
    records = _records(ctx)
    assert records is not None
    rows = _questions(ctx)
    missing = rows[0].submissions[0].reference
    rows[0].submissions[0].reference = "unknown-reference"
    duplicated = rows[1].submissions[0]
    rows[1].submissions.append(duplicated)
    result = json.loads(await calculate_exercise_statistics(ctx, rows))
    assert result["missing_references"] == [missing]
    assert result["unknown_references"] == ["unknown-reference"]
    assert result["duplicate_references"] == [duplicated.reference]
    assert result["reference_counts"] == {"missing": 1, "unknown": 1, "duplicate": 1}
    assert not result["diagnostics_truncated"]
    assert all(record["answer"] not in json.dumps(result) for record in records)


@pytest.mark.anyio
async def test_coverage_diagnostics_keep_utf8_byte_bounds_and_full_counts() -> None:
    ctx = _fixture()
    rows = [
        ExerciseQuestion(
            question=str(i),
            submissions=[
                SubmissionJudgment(
                    reference=("\u0000🙂" * 35) + str(i), outcome="correct"
                )
            ],
        )
        for i in range(100)
    ]
    raw = await calculate_exercise_statistics(ctx, rows)
    result = json.loads(raw)
    assert len(raw.encode()) <= RESULT_BYTES
    assert result["status"] == "invalid_coverage"
    assert "totals" not in result
    assert result["reference_counts"] == {"missing": 14, "unknown": 100, "duplicate": 0}
    assert result["diagnostics_truncated"]
    assert len(result["unknown_references"]) < 100
    assert ctx.deps.exercise_report_totals is None


@pytest.mark.anyio
async def test_sdk_repairs_navigation_coverage_without_counting_clicks_as_answers() -> (
    None
):
    ctx = _with_navigation()
    rows = _questions(ctx)
    calls = 0
    repair = False

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls, repair
        calls += 1
        results = [
            part for part in messages[-1].parts if isinstance(part, ToolReturnPart)
        ]
        latest = results[-1] if results else None
        args: dict[str, object] = {}
        if latest is None or latest.tool_name not in {
            "read_exercise_history",
            "calculate_exercise_statistics",
        }:
            name = "read_exercise_history"
        elif latest.tool_name == "read_exercise_history":
            page = json.loads(latest.content)
            if page["next_offset"] is not None:
                name = "read_exercise_history"
                args = {"offset": page["next_offset"]}
            else:
                assert "excluded" in (info.instructions or "")
                name = "calculate_exercise_statistics"
                args = {"questions": [row.model_dump() for row in rows]}
        else:
            result = json.loads(latest.content)
            if result["status"] == "invalid_coverage":
                assert not repair
                repair = True
                name = "calculate_exercise_statistics"
                args = {
                    "questions": [row.model_dump() for row in rows],
                    "excluded": result["missing_references"],
                }
            else:
                assert result["status"] == "calculated"
                assert result["totals"]["attempts"] == 14
                assert result["excluded_answers"] == 1
                name = "finish"
                args = {"summary": "Report complete."}
        yield {
            0: DeltaToolCall(
                name=name, json_args=json.dumps(args), tool_call_id=f"call-{calls}"
            )
        }

    engine = Engine(FunctionModel(stream_function=model), exercise_statistics=True)
    session = Session(
        script=ScriptBundle(script="Report the exercise results."),
        messages=ctx.messages,
    )
    events = await _collect(engine.run_turn(session))
    assert repair
    assert calls <= 12
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "finished"


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
@pytest.mark.parametrize(
    ("outcomes", "attempts", "retries", "first", "unverified"),
    [
        (["incorrect", "not_answer", "correct"], 2, 1, False, 0),
        (["not_answer", "correct"], 1, 0, True, 0),
        (["not_answer"], 0, 0, None, 0),
        (["not_answer", "unverified"], 1, 0, None, 1),
    ],
)
async def test_knowledge_questions_preserve_evidence_without_inflating_attempts(
    outcomes: list[str],
    attempts: int,
    retries: int,
    first: bool | None,
    unverified: int,
) -> None:
    ctx = _fixture()
    records = _records(ctx)
    assert records is not None
    before = ModelMessagesTypeAdapter.dump_json(ctx.messages)
    row = ExerciseQuestion(
        question="1",
        submissions=[
            SubmissionJudgment(reference=record["reference"], outcome=outcome)
            for record, outcome in zip(records, outcomes, strict=False)
        ],
    )
    result = json.loads(
        await calculate_exercise_statistics(
            ctx, [row], [r["reference"] for r in records[len(outcomes) :]]
        )
    )
    assert result["status"] == "calculated"
    actual = result["questions"][0]
    assert actual["attempts"] == attempts
    assert actual["retries"] == retries
    assert actual["first_correct"] is first
    assert actual["unverified_submissions"] == unverified
    assert actual["non_answer_messages"] == 1
    assert actual["failed_submissions"] == outcomes.count("incorrect")
    assert actual["hints"] is None
    assert result["totals"]["non_answer_messages"] == 1
    assert result["totals"]["unanswered"] == (attempts == 0)
    assert ModelMessagesTypeAdapter.dump_json(ctx.messages) == before


@pytest.mark.anyio
@pytest.mark.parametrize("projected", [False, True])
@pytest.mark.parametrize("initial_help", ["none", "teaching", "placeholder"])
async def test_original_rounds_support_pre_answer_and_correction_hint_totals(
    projected: bool,
    initial_help: str,
) -> None:
    explanation = "Adding one means taking the next integer. " * 130
    correction = "Incorrect. Add one to two, not three. Try again."
    initial = "We will give hints after errors. What is 2 + 1?"
    help_text = "Start at two and move one integer forward."
    if initial_help == "teaching":
        initial += " " + help_text
    placeholder = help_text if initial_help == "placeholder" else "Your answer"
    messages = [
        ModelResponse(
            parts=[
                TextPart(initial),
                ToolCallPart(
                    "interact",
                    {"type": "text", "prompt": "Answer", "placeholder": placeholder},
                    "ask",
                ),
            ]
        ),
        ModelRequest(
            parts=[ToolReturnPart("interact", "Learner wrote: Please explain.", "ask")]
        ),
        ModelResponse(
            parts=[
                TextPart(explanation),
                TextPart("Return to the same question."),
                ToolCallPart("interact", {"type": "text", "prompt": "Answer"}, "first"),
            ]
        ),
        ModelRequest(parts=[ToolReturnPart("interact", "Learner wrote: 5", "first")]),
        ModelResponse(
            parts=[
                TextPart(correction),
                ToolCallPart("interact", {"type": "text", "prompt": "Retry"}, "retry"),
            ]
        ),
        ModelRequest(parts=[ToolReturnPart("interact", "Learner wrote: 3", "retry")]),
        ModelResponse(parts=[TextPart("Correct. Here is the final explanation.")]),
    ]
    ctx = _ctx(messages)
    ctx.deps.exercise_history = tuple(messages)
    original = ModelMessagesTypeAdapter.dump_json(messages)
    if projected:
        ctx.messages = [ModelResponse(parts=[TextPart("Short teaching summary.")])]
    text = ""
    offset = 0
    while offset is not None:
        page = json.loads(await read_exercise_history(ctx, offset))
        text += page["text"]
        offset = page["next_offset"]
    records = json.loads(text)
    assert records[0]["teaching"] == initial
    assert records[0]["question"]["placeholder"] == placeholder
    assert records[0]["following_teaching"] == [
        explanation,
        "Return to the same question.",
    ]
    assert records[1]["following_teaching"] == [correction]
    assert records[2]["following_teaching"] == [
        "Correct. Here is the final explanation."
    ]
    # These are supplied semantic judgments; this check does not grade teaching.
    row = ExerciseQuestion(
        question="1",
        submissions=[
            SubmissionJudgment(
                reference=record["reference"], outcome=outcome, hint_after=hint
            )
            for record, outcome, hint in zip(
                records,
                ["not_answer", "incorrect", "correct"],
                [True, True, False],
                strict=True,
            )
        ],
        hint_before=initial_help != "none",
    )
    result = json.loads(await calculate_exercise_statistics(ctx, [row]))
    assert result["status"] == "calculated"
    assert result["totals"]["hints"] == 2 + (initial_help != "none")
    assert result["questions"][0]["hints_before_first"] == 1 + (initial_help != "none")
    assert result["totals"]["attempts"] == 2
    assert result["totals"]["non_answer_messages"] == 1
    assert result["totals"]["first_correct"] == 0
    assert (
        ModelMessagesTypeAdapter.dump_json(list(ctx.deps.exercise_history)) == original
    )


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
@pytest.mark.parametrize("outcome", ["correct", "not_answer"])
async def test_engine_deferred_resume_reads_original_answer_and_feedback(
    outcome: str,
) -> None:
    step = 0
    learner_input = "2" if outcome == "correct" else "Please explain before I answer."
    teaching = "Correct." if outcome == "correct" else "Here is an explanation."

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal step
        step += 1
        assert {"read_exercise_history", "calculate_exercise_statistics"} <= {
            t.name for t in info.function_tools
        }
        assert "not_answer" in json.dumps(
            next(
                t.parameters_json_schema
                for t in info.function_tools
                if t.name == "calculate_exercise_statistics"
            )
        )
        schema = next(
            t.parameters_json_schema
            for t in info.function_tools
            if t.name == "calculate_exercise_statistics"
        )
        question_schema = schema["$defs"]["ExerciseQuestion"]["properties"]
        timing = question_schema["hints_before_first"]["description"]
        assert "first actual answer attempt" in timing
        assert "not_answer" in timing
        assert "null" in timing
        assert "author" in question_schema["hints"]["description"]
        assert (
            "before and after the first actual answer"
            in (question_schema["hints"]["description"])
        )
        assert "two rounds" in question_schema["hints"]["description"]
        assert "round evidence" in question_schema["hint_before"]["description"]
        assert (
            "first record's teaching" in question_schema["hint_before"]["description"]
        )
        assert "not following_teaching" in question_schema["hint_before"]["description"]
        assert (
            "qualifying placeholder help"
            in question_schema["hint_before"]["description"]
        )
        submission_schema = schema["$defs"]["SubmissionJudgment"]["properties"]
        assert "following_teaching" in submission_schema["hint_after"]["description"]
        assert "answer_group" in submission_schema["hint_after"]["description"]
        assert "not also hint_before" in submission_schema["hint_after"]["description"]
        assert "course logistics and question-only teaching" in (
            info.instructions or ""
        )
        assert "Count every qualifying teaching round" in (info.instructions or "")
        assert "Quote the actual submitted mistake" in (info.instructions or "")
        assert "not evidence of personal misconceptions" in next(
            t.description
            for t in info.function_tools
            if t.name == "calculate_exercise_statistics"
        )
        if step == 1:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    json_args='{"type":"text","prompt":"What is 1+1?"}',
                    tool_call_id="q",
                )
            }
        elif step == 2:
            assert "offset=0" in (info.instructions or "")
            yield teaching
            yield {
                0: DeltaToolCall(
                    name="read_exercise_history", json_args="{}", tool_call_id="read"
                )
            }
        elif step == 3:
            assert "Original submissions have been read completely" in (
                info.instructions or ""
            )
            assert "both before and after the first actual answer" in (
                info.instructions or ""
            )
            assert "first record's teaching" in (info.instructions or "")
            assert "not also hint_before" in (info.instructions or "")
            assert "qualifying placeholder help" in (info.instructions or "")
            page = next(p for p in messages[-1].parts if isinstance(p, ToolReturnPart))
            record = json.loads(json.loads(page.content)["text"])[0]
            assert record["answer"] == "Learner wrote: " + learner_input
            assert record["following_teaching"] == [teaching]
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
                                            "outcome": outcome,
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
            assert "Successful calculator totals for this turn" in (
                info.instructions or ""
            )
            assert "Personal review evidence" in (info.instructions or "")
            assert "a missing category label alone" in (info.instructions or "")
            assert "do not turn authored examples into personal mistakes" in (
                info.instructions or ""
            )
            result = json.loads(messages[-1].parts[0].content)
            assert result["totals"]["first_correct"] == (outcome == "correct")
            assert result["totals"]["attempts"] == (outcome == "correct")
            assert result["totals"].get("non_answer_messages", 0) == (
                outcome == "not_answer"
            )
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
        engine.run_turn(session, InteractionResponseTurn(id="q", text=learner_input))
    )
    assert not any(isinstance(e, ErrorEvent) for e in events)
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "finished"


@pytest.mark.anyio
@pytest.mark.parametrize("before_first", [0, 1, None])
async def test_non_answer_classification_does_not_determine_hint_timing(
    before_first: int | None,
) -> None:
    ctx = _ctx(
        [
            ModelResponse(
                parts=[
                    TextPart("What is 1+1?"),
                    ToolCallPart("interact", {"type": "text"}, "question"),
                ]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        "interact",
                        "Learner wrote: Please explain addition.",
                        "question",
                    )
                ]
            ),
            ModelResponse(
                parts=[
                    TextPart("Addition combines quantities. Now give your answer."),
                    ToolCallPart("interact", {"type": "text"}, "answer"),
                ]
            ),
            ModelRequest(
                parts=[ToolReturnPart("interact", "Learner wrote: 2", "answer")]
            ),
            ModelResponse(parts=[TextPart("Correct.")]),
        ]
    )
    records = _records(ctx)
    assert records is not None
    assert len(records) == 2
    # Round classifications remain supplied judgments, not runtime text grading.
    row = ExerciseQuestion(
        question="1",
        submissions=[
            SubmissionJudgment(
                reference=records[0]["reference"],
                outcome="not_answer",
                hint_after=None if before_first is None else bool(before_first),
            ),
            SubmissionJudgment(
                reference=records[1]["reference"], outcome="correct", hint_after=False
            ),
        ],
        hint_before=False,
    )
    result = json.loads(await calculate_exercise_statistics(ctx, [row]))
    assert result["status"] == "calculated"
    assert result["totals"]["attempts"] == 1
    assert result["totals"]["non_answer_messages"] == 1
    assert result["totals"]["first_correct"] == 1
    assert result["totals"]["hints"] == before_first
    assert result["totals"]["independent_first"] == (
        None if before_first is None else int(before_first == 0)
    )


async def _collect(events: AsyncIterator[object]) -> list[object]:
    return [event async for event in events]


@pytest.mark.anyio
async def test_unknown_hint_counts_are_not_silently_zero() -> None:
    ctx = _fixture()
    rows = _questions(ctx)
    rows[1].hints = None
    rows[1].hints_before_first = None
    rows[1].submissions[0].hint_after = None
    rows[1].hint_before = None
    result = json.loads(await calculate_exercise_statistics(ctx, rows))
    assert result["questions"][1]["hints"] is None
    assert result["totals"]["hints"] is None
    assert result["totals"]["hint_questions"] is None
    assert result["totals"]["independent_first"] is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("hint", "total", "before"), [(False, 0, 0), (True, 1, None), (None, None, None)]
)
async def test_unanswered_hint_timing_preserves_known_zero_and_unknown_evidence(
    hint: bool | None, total: int | None, before: int | None
) -> None:
    ctx = _fixture()
    records = _records(ctx)
    assert records is not None
    row = ExerciseQuestion(
        question="1",
        hint_before=False,
        submissions=[
            SubmissionJudgment(
                reference=records[0]["reference"], outcome="not_answer", hint_after=hint
            )
        ],
    )
    result = json.loads(
        await calculate_exercise_statistics(
            ctx, [row], [r["reference"] for r in records[1:]]
        )
    )
    assert result["status"] == "calculated"
    actual = result["questions"][0]
    assert actual["attempts"] == 0
    assert actual["hints"] == total
    assert actual["hints_before_first"] == before


@pytest.mark.anyio
@pytest.mark.parametrize("missing_round", [False, True])
async def test_scalar_counts_cannot_override_or_replace_round_evidence(
    missing_round: bool,
) -> None:
    ctx = _fixture()
    rows = _questions(ctx)
    rows[0].hints = 0
    if missing_round:
        rows[0].submissions[0].hint_after = None
    ctx.deps.exercise_report_totals = {"hints": 0}
    result = json.loads(await calculate_exercise_statistics(ctx, rows))
    assert result["status"] == "invalid_hint_counts"
    assert result["derived_hints"] == (None if missing_round else 1)
    assert "totals" not in result
    assert ctx.deps.exercise_report_totals is None
    rows[0].hints = None
    result = json.loads(await calculate_exercise_statistics(ctx, rows))
    assert result["status"] == "calculated"
    assert result["totals"]["hints"] == (None if missing_round else 3)


@pytest.mark.anyio
@pytest.mark.parametrize("second_hint", [True, False, None])
async def test_shared_answer_group_hints_count_once_or_reject_conflicting_flags(
    second_hint: bool | None,
) -> None:
    ctx = _ctx(
        [
            ModelResponse(
                parts=[
                    TextPart("Give both parts of the answer."),
                    ToolCallPart("interact", {"type": "text"}, "a"),
                    ToolCallPart("interact", {"type": "text"}, "b"),
                ]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart("interact", "Learner wrote: first part", "a"),
                    ToolReturnPart("interact", "Learner wrote: second part", "b"),
                ]
            ),
            ModelResponse(parts=[TextPart("One hint for the combined answer.")]),
        ]
    )
    records = _records(ctx)
    assert records is not None
    row = ExerciseQuestion(
        question="1",
        hint_before=False,
        submissions=[
            SubmissionJudgment(
                reference=record["reference"], outcome="incorrect", hint_after=hint
            )
            for record, hint in zip(records, [True, second_hint], strict=True)
        ],
    )
    result = json.loads(await calculate_exercise_statistics(ctx, [row]))
    if second_hint is True:
        assert result["status"] == "calculated"
        assert result["totals"]["hints"] == 1
        assert result["questions"][0]["hints_before_first"] == 0
    else:
        assert result["status"] == "conflicting_hint_round"
        assert "totals" not in result


@pytest.mark.anyio
async def test_initial_teaching_hint_contributes_to_total_and_first_answer_timing() -> (
    None
):
    ctx = _fixture()
    rows = _questions(ctx)
    rows[1].hint_before = True
    rows[1].hints = None
    rows[1].hints_before_first = None
    result = json.loads(await calculate_exercise_statistics(ctx, rows))
    assert result["status"] == "calculated"
    assert result["questions"][1]["hints"] == 1
    assert result["questions"][1]["hints_before_first"] == 1
    assert result["totals"]["hints"] == 4
    assert result["totals"]["independent_first"] == 7


@pytest.mark.parametrize("flag", ["true", 0, [], {}])
def test_hint_round_flags_are_strict_booleans_or_unknown(flag: object) -> None:
    with pytest.raises(ValidationError):
        SubmissionJudgment(reference="answer", outcome="correct", hint_after=flag)
    with pytest.raises(ValidationError):
        ExerciseQuestion(question="1", submissions=[], hint_before=flag)


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
async def test_existing_41_question_report_keeps_its_original_byte_capacity() -> None:
    ctx = _ctx([])
    rows = [ExerciseQuestion(question=str(i), submissions=[]) for i in range(41)]
    raw = await calculate_exercise_statistics(ctx, rows)
    result = json.loads(raw)
    assert result["status"] == "calculated"
    assert len(raw.encode()) <= RESULT_BYTES
    assert len(result["questions"]) == 41
    assert result["totals"]["unanswered"] == 41
    assert all("non_answer_messages" not in row for row in result["questions"])
    assert "non_answer_messages" not in result["totals"]


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
    from markdownflow.engine.exercise_statistics import (
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
