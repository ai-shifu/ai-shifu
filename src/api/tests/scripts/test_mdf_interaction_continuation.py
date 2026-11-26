"""Check live advancement with recorded responses and the real course engine."""

from __future__ import annotations

import asyncio

import pytest
from scripts.evaluate_mdf_interactions import Case, Replay, evaluate_case

from scripts import evaluate_mdf_interactions as evaluator


def _run_case(case: Case) -> dict[str, object]:
    """Exercise the live path without network calls."""
    return asyncio.run(evaluate_case(case, Replay(case.replay).model))


def test_live_answer_continues_until_the_lesson_finishes() -> None:
    question = "Which tool would you use?"
    case = Case.model_validate(
        {
            "id": "live-continuation",
            "source": "synthetic",
            "tags": ["single"],
            "teaching_prompt": (
                f"{question}\n?[{{{{{question}}}}} Small scoop//scoop | Large spoon//spoon]"
                "\nExplain how to use the selected tool."
            ),
            "steps": [
                {"action": "start", "expected": {"outcome": "interaction"}},
                {
                    "action": "answer",
                    "values": ["scoop"],
                    "expected": {
                        "outcome": "finished",
                        "prose_once": [
                            "Hold the scoop level.",
                            "Then fill it to the mark.",
                        ],
                        "memory": {question: "scoop"},
                    },
                },
            ],
            "replay": [
                {
                    "text": question,
                    "calls": [
                        {
                            "name": "interact",
                            "args": {
                                "type": "single",
                                "question": question,
                                "options": [
                                    {"display": "Small scoop", "value": "scoop"},
                                    {"display": "Large spoon", "value": "spoon"},
                                ],
                            },
                        }
                    ],
                },
                {"text": "Hold the scoop level."},
                {"text": "Then fill it to the mark."},
                {"calls": [{"name": "finish", "args": {"summary": "Used a scoop"}}]},
            ],
        }
    )

    result = _run_case(case)

    assert result["status"] == "recovered_pass"
    assert result["retries"] == 0
    assert result["model_requests"] == 4
    assert result["automatic_continuations"] == 2
    start, answer = result["steps"]
    assert start["turn_outcomes"] == ["interaction"]
    assert answer["turn_outcomes"] == ["end", "end", "finished"]
    assert answer["memory"] == {question: "scoop"}
    assert answer["prose"] == "Hold the scoop level.\n\nThen fill it to the mark."


@pytest.mark.parametrize(
    "text",
    [
        "  \n",
        '<memory>\n{"known_fact": "Example"}\n</memory>',
        "Pick a tool.\n\n?[Small scoop | Large spoon]",
    ],
)
def test_live_step_stops_when_no_more_teaching_can_be_delivered(text: str) -> None:
    case = Case.model_validate(
        {
            "id": "live-stop",
            "source": "synthetic",
            "tags": ["single"],
            "teaching_prompt": "Pick a tool.\n?[Small scoop | Large spoon]",
            "steps": [{"action": "start", "expected": {"outcome": "interaction"}}],
            "replay": [
                {"text": text},
                {"calls": [{"name": "finish", "args": {}}]},
            ],
        }
    )

    result = _run_case(case)

    assert result["status"] == "behavior_failure"
    assert result["model_requests"] == 1
    assert result["automatic_continuations"] == 0
    (step,) = result["steps"]
    assert step["turn_outcomes"] == ["end"]


def test_live_reports_exhausted_continuations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(evaluator, "MAX_AUTOMATIC_CONTINUATIONS", 1)
    case = Case.model_validate(
        {
            "id": "live-continuation-limit",
            "source": "synthetic",
            "tags": ["single"],
            "teaching_prompt": "Explain how to use a scoop.",
            "steps": [{"action": "start", "expected": {"outcome": "finished"}}],
            "replay": [
                {"text": "Choose a scoop that holds the amount you need."},
                {"text": "Hold the scoop level and fill it to the mark."},
                {"calls": [{"name": "finish", "args": {}}]},
            ],
        }
    )

    result = _run_case(case)

    assert result["status"] == "behavior_failure"
    assert result["model_requests"] == 2
    assert result["automatic_continuations"] == 1
    assert "step_1.continuation_limit" in result["failures"]
