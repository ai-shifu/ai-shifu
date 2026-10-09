"""Keep successful completion separate from evidence-correct exercise statistics."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING

import pytest
from pydantic_ai.messages import ModelRequest, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from scripts.mdf2_memory_quality import exercise

from scripts import evaluate_mdf2_memory as quality

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

pytestmark = pytest.mark.anyio
CASES = [case for case in quality.load_cases() if case["family"] == "exercise"]


def summary_model(
    text: str,
    *,
    fail: bool = False,
    finish_later: bool = False,
    use_tools: bool = True,
    original_labels: bool = False,
    full_labels: bool = False,
    expression_labels: bool = False,
    long_expression_labels: bool = False,
    swap_sources: bool = False,
) -> FunctionModel:
    phase = 0
    source = ""
    reported = False

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal phase, source, reported
        phase += 1
        assert {"interact", "finish"} <= {tool.name for tool in info.function_tools}
        # Original paired wrong and corrected answers must reach the actual model.
        returns = [
            part
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart) and part.tool_name == "interact"
        ]
        assert len(returns) == 25  # fourteen answers and eleven continue buttons
        if fail:
            message = "Injected provider failure; never include details in a report."
            raise RuntimeError(message)
        last = next(
            (
                part
                for part in reversed(messages[-1].parts)
                if isinstance(part, ToolReturnPart)
            ),
            None,
        )
        if use_tools and phase == 1:
            yield {
                0: DeltaToolCall(
                    name="read_exercise_history", json_args="{}", tool_call_id="read-1"
                )
            }
            return
        if use_tools and last and last.tool_name == "read_exercise_history":
            page = json.loads(last.content)
            source += page["text"]
            if page["next_offset"] is not None:
                yield {
                    0: DeltaToolCall(
                        name="read_exercise_history",
                        json_args=json.dumps({"offset": page["next_offset"]}),
                        tool_call_id=f"read-{phase}",
                    )
                }
                return
            grouped = {}
            for record in json.loads(source):
                number = int(record["question"]["prompt"].split()[-1])
                correct = record["answer"] == f"Learner wrote: {number + 1}"
                row = grouped.setdefault(
                    number,
                    {
                        "question": str(number),
                        "submissions": [],
                        "hints": 0,
                        "hints_before_first": 0,
                    },
                )
                row["submissions"].append(
                    {
                        "reference": record["reference"],
                        "outcome": "correct" if correct else "incorrect",
                    }
                )
                row["hints"] += not correct
            if original_labels:
                for number, row in grouped.items():
                    row["question"] = (
                        f"Question {number}: What is {number} + 1?"
                        if full_labels
                        else f"Question {number}"
                    )
            if swap_sources:
                grouped[3]["submissions"], grouped[4]["submissions"] = (
                    grouped[4]["submissions"],
                    grouped[3]["submissions"],
                )
            if expression_labels:
                for number, row in grouped.items():
                    prefix = "Question " if long_expression_labels else "Q"
                    row["question"] = f"{prefix}{number}: {number} + 1"
            yield {
                0: DeltaToolCall(
                    name="calculate_exercise_statistics",
                    json_args=json.dumps({"questions": list(grouped.values())}),
                    tool_call_id="calc",
                )
            }
            return
        if not reported:
            yield text
            reported = True
            if finish_later:
                return
        yield {
            0: DeltaToolCall(
                name="finish", tool_call_id="done", json_args='{"summary":"done"}'
            )
        }

    return FunctionModel(stream_function=stream)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
async def test_statistics_require_correct_rows_and_totals_after_real_reload(
    case: dict,
) -> None:
    result = await exercise.evaluate_exercise(
        case, summary_model(json.dumps(exercise.expected_report(case)))
    )
    assert result["passed"], result
    assert all(result["checks"].values())
    assert result["calculation_diagnostic"] == {"status": "ok"}


def test_fixture_contains_answers_not_the_expected_report() -> None:
    from flaskr.service.learn.agent.engine.script import render_first_prompt

    session = exercise.exercise_session(CASES[0])
    assert session.messages[0].parts[0].content == render_first_prompt(
        session.script, {}
    )
    assert "Learner wrote: 4" in session.dumps()  # wrong first answer to 1 + 1
    assert "Learner wrote: 2" in session.dumps()  # corrected first question
    assert (
        exercise.expected_report(CASES[0])["totals"]
        == exercise.expected_report(CASES[1])["totals"]
    )
    assert (
        exercise.expected_report(CASES[0])["questions"]
        != exercise.expected_report(CASES[1])["questions"]
    )


@pytest.mark.parametrize(
    "mode",
    [
        "swapped",
        "wrong_total",
        "duplicate",
        "missing",
        "bool_count",
        "wrong_type",
        "empty",
        "trailing",
    ],
)
async def test_finished_plausible_or_malformed_reports_fail(mode: str) -> None:
    case = CASES[0]
    value = copy.deepcopy(exercise.expected_report(case))
    if mode == "swapped":
        value = exercise.expected_report(CASES[1])
    elif mode == "wrong_total":
        value["totals"]["attempts"] -= 1
    elif mode == "duplicate":
        value["questions"][1] = value["questions"][0]
    elif mode == "missing":
        value["questions"].pop()
    elif mode == "bool_count":
        value["questions"][1]["attempts"] = True
    elif mode == "wrong_type":
        value["questions"][1]["first_correct"] = 1
    text = "" if mode == "empty" else json.dumps(value)
    if mode == "trailing":
        text += " All totals match."
    result = await exercise.evaluate_exercise(case, summary_model(text))
    assert not result["passed"], result
    assert result["checks"]["completed"]
    assert result["error"] is None  # semantic or format failure, not provider outage
    if mode == "swapped":
        assert result["checks"]["aggregate_evidence"]
        assert not result["checks"]["question_evidence"]


async def test_one_host_continuation_can_finish_but_cannot_replace_failed_report() -> (
    None
):
    case = CASES[0]
    text = json.dumps(exercise.expected_report(case))
    result = await exercise.evaluate_exercise(
        case, summary_model(text, finish_later=True)
    )
    assert result["passed"], result


@pytest.mark.parametrize("fence", ["json", ""])
async def test_markdown_json_fence_preserves_semantic_checks(fence: str) -> None:
    case = CASES[0]
    for value, passed in [
        (exercise.expected_report(case), True),
        (exercise.expected_report(CASES[1]), False),
    ]:
        text = f"```{fence}\n{json.dumps(value)}\n```"
        result = await exercise.evaluate_exercise(case, summary_model(text))
        assert result["passed"] is passed, result
        assert result["checks"]["valid_report"]


@pytest.mark.parametrize("extra", ["before", "after", "second_report", "duplicate_key"])
def test_markdown_normalization_cannot_hide_extra_or_conflicting_reports(
    extra: str,
) -> None:
    value = exercise.expected_report(CASES[0])
    text = f"```json\n{json.dumps(value)}\n```"
    if extra == "before":
        text = "Narrative claiming success.\n" + text
    elif extra == "after":
        text += "\nNarrative claiming success."
    elif extra == "second_report":
        text += "\n" + text
    else:
        text = json.dumps(value).replace('"passed": 11', '"passed": 0, "passed": 11')
    assert not any(exercise.score_report(text, value).values())


async def test_provider_errors_remain_errors_and_do_not_expose_raw_details() -> None:
    result = await exercise.evaluate_exercise(CASES[0], summary_model("", fail=True))
    assert not result["passed"]
    assert result["error"] == "engine_error"
    assert "Injected provider" not in json.dumps(result)


async def test_cli_dispatch_and_reports_keep_selected_family_and_settings() -> None:
    results = await quality.evaluate(
        [CASES[0]],
        lambda _family: summary_model(json.dumps(exercise.expected_report(CASES[0]))),
        1,
    )
    value = quality.report([CASES[0]], results, 1)
    assert value["passed"], value
    assert not value["full_catalog"]
    assert value["exercise_generation_settings"] == exercise.GENERATION_SETTINGS
    assert "scripts/mdf2_memory_quality/exercise.py" in value["fingerprints"]
    assert "Learner wrote:" not in json.dumps(value)


async def test_stored_history_mutation_cannot_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.learn.agent.engine import Engine

    original = Engine.run_turn

    async def mutate(
        engine: object, session: object, *args: object, **kwargs: object
    ) -> AsyncIterator[object]:
        async for event in original(engine, session, *args, **kwargs):
            yield event
        session.messages[0].parts[0].content += " Unexpected mutation."

    monkeypatch.setattr(Engine, "run_turn", mutate)
    result = await exercise.evaluate_exercise(
        CASES[0], summary_model(json.dumps(exercise.expected_report(CASES[0])))
    )
    assert not result["passed"]
    assert not result["checks"]["history_preserved"]


async def test_correct_report_without_tools_is_not_protocol_acceptance() -> None:
    case = CASES[0]
    result = await exercise.evaluate_exercise(
        case, summary_model(json.dumps(exercise.expected_report(case)), use_tools=False)
    )
    assert result["checks"]["question_evidence"]
    assert result["checks"]["aggregate_evidence"]
    assert not result["checks"]["calculated_evidence"]
    assert result["calculation_diagnostic"] == {"status": "no_calculation"}
    assert not result["passed"]


@pytest.mark.parametrize(
    "label_style", ["prompt", "title", "expression", "long_expression"]
)
async def test_calculator_original_labels_preserve_original_question_identity(
    label_style: str,
) -> None:
    case = CASES[0]
    result = await exercise.evaluate_exercise(
        case,
        summary_model(
            json.dumps(exercise.expected_report(case)),
            original_labels=True,
            full_labels=label_style == "title",
            expression_labels=label_style in {"expression", "long_expression"},
            long_expression_labels=label_style == "long_expression",
        ),
    )
    assert result["passed"]


async def test_swapped_original_references_fail_even_with_identical_counts() -> None:
    case = CASES[0]
    result = await exercise.evaluate_exercise(
        case,
        summary_model(json.dumps(exercise.expected_report(case)), swap_sources=True),
    )
    assert result["checks"]["question_evidence"]
    assert result["checks"]["aggregate_evidence"]
    assert not result["checks"]["calculated_evidence"]
    assert result["calculation_diagnostic"] == {
        "status": "incorrect_calculation_or_grouping"
    }
    assert not result["passed"]


@pytest.mark.parametrize(
    "label",
    [
        "Question 1: What is 2 + 1?",
        "Question 01",
        "Question 1 extra",
        "Question 12",
        "Q1: 2 + 1",
        "Question 1: 2 + 1",
    ],
)
def test_question_label_aliases_do_not_hide_wrong_or_invented_titles(
    label: str,
) -> None:
    with pytest.raises(ValueError, match="invalid fixture question label"):
        exercise._question_number(label)
