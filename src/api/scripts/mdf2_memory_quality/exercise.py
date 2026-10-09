"""Synthetic attempt histories and evidence-based exercise report scoring."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    from flaskr.service.learn.agent.engine import Session
    from pydantic_ai.models import Model

GENERATION_SETTINGS = {"temperature": 0, "max_tokens": 2048}


def expected_report(case: dict[str, Any]) -> dict[str, Any]:
    """Derive counts from the fixture's known incorrect first submissions."""
    corrected = set(case["corrected_questions"])
    rows = [
        {
            "question": number,
            "first_correct": number not in corrected,
            "attempts": 2 if number in corrected else 1,
            "hints": 1 if number in corrected else 0,
        }
        for number in range(1, 12)
    ]
    return {
        "questions": rows,
        "totals": {
            "passed": len(rows),
            "first_correct": sum(row["first_correct"] for row in rows),
            "corrected": len(corrected),
            "attempts": sum(row["attempts"] for row in rows),
            "retries": sum(row["attempts"] - 1 for row in rows),
            "hints": sum(row["hints"] for row in rows),
        },
    }


def exercise_session(case: dict[str, Any]) -> Session:
    """Build original paired question/answer/feedback evidence without expected totals."""
    from flaskr.service.learn.agent.engine import ScriptBundle, Session
    from flaskr.service.learn.agent.engine.script import render_first_prompt
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    bundle = ScriptBundle(
        script=(
            "Review eleven numbered arithmetic questions, correcting incorrect answers. "
            "At the end, use original submissions and feedback to report each question's "
            "first_correct (boolean), attempts and hints (integer counts). A corrected "
            "answer never changes the first result. Continue buttons are not attempts. "
            "Output only one JSON object with questions and totals. Each questions row "
            "has question (integer ID), first_correct, attempts, hints. Totals has passed, "
            "first_correct, corrected, attempts, retries, hints, all integer counts. "
            "Include each question once, derive totals from its evidence and check them "
            "against the rows. Do not guess, change history, or store learner notes. "
            "Then finish without repeating the report."
        )
    )
    messages = [ModelRequest(parts=[UserPromptPart(render_first_prompt(bundle, {}))])]
    for number in range(1, 12):
        corrected = number in case["corrected_questions"]
        for attempt in range(1, (2 if corrected else 1) + 1):
            call_id = f"question-{number}-attempt-{attempt}"
            text = (
                f"Question {number}: What is {number} + 1?"
                if attempt == 1
                else "That answer is incorrect. Hint: add one, not three. Try again."
            )
            messages.extend(
                [
                    ModelResponse(
                        parts=[
                            TextPart(text),
                            ToolCallPart(
                                "interact",
                                {"type": "text", "prompt": f"Question {number}"},
                                call_id,
                            ),
                        ]
                    ),
                    ModelRequest(
                        parts=[
                            ToolReturnPart(
                                "interact",
                                "Learner wrote: "
                                + str(
                                    number + (3 if corrected and attempt == 1 else 1)
                                ),
                                call_id,
                            )
                        ]
                    ),
                ]
            )
        call_id = f"continue-{number}"
        messages.extend(
            [
                ModelResponse(
                    parts=[
                        TextPart(f"Correct. Question {number} has passed."),
                        ToolCallPart(
                            "interact",
                            {"type": "confirm", "prompt": "Continue"},
                            call_id,
                        ),
                    ]
                ),
                ModelRequest(
                    parts=[
                        ToolReturnPart("interact", "Learner pressed continue.", call_id)
                    ]
                ),
            ]
        )
    messages.append(ModelResponse(parts=[TextPart("All explanations are complete.")]))
    return Session.loads(
        Session(
            script=bundle,
            messages=messages,
            initial_variables={},
            turn=26,
        ).dumps()
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Never let JSON last-key-wins parsing hide conflicting reported values."""
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            message = "duplicate report key"
            raise ValueError(message)
        value[key] = item
    return value


def score_report(text: str, expected: dict[str, Any]) -> dict[str, bool]:
    """Reject plausible totals, swapped identities, duplicate rows and invalid types."""
    # Classroom output is Markdown; a single whole-output JSON fence is equivalent.
    fenced = re.fullmatch(
        r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", text.strip(), re.DOTALL
    )
    try:
        value = json.loads(
            fenced[1] if fenced else text, object_pairs_hook=_unique_object
        )
    except ValueError:
        value = None
    valid = isinstance(value, dict) and set(value) == {"questions", "totals"}
    rows = value["questions"] if valid else None
    totals = value["totals"] if valid else None
    shape = (
        isinstance(rows, list)
        and len(rows) == 11
        and all(
            isinstance(row, dict)
            and set(row) == {"question", "first_correct", "attempts", "hints"}
            and type(row["question"]) is int
            and type(row["first_correct"]) is bool
            and type(row["attempts"]) is int
            and type(row["hints"]) is int
            for row in rows
        )
        and isinstance(totals, dict)
        and set(totals) == set(expected["totals"])
        and all(type(count) is int for count in totals.values())
    )
    return {
        "valid_report": bool(valid and shape),
        "question_evidence": bool(shape)
        and sorted(rows, key=lambda row: row["question"]) == expected["questions"],
        "aggregate_evidence": bool(shape) and totals == expected["totals"],
    }


async def evaluate_exercise(case: dict[str, Any], model: Model) -> dict[str, Any]:
    """Score final model output against immutable original attempt evidence."""
    from flaskr.service.learn.agent.engine import (
        ContentDelta,
        ContinueTurn,
        Engine,
        ErrorEvent,
        MemoryUpdated,
        TurnDone,
    )
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    session = exercise_session(case)
    count = len(session.messages)
    original = ModelMessagesTypeAdapter.dump_json(session.messages)
    engine = Engine(
        model,
        memory_admission=True,
        memory_recall=True,
        recall_history_compaction=True,
        teaching_history_compaction=True,
        request_limit=6,
        model_settings=dict(GENERATION_SETTINGS),
    )
    events = [event async for event in engine.run_turn(session, ContinueTurn())]
    if (
        events
        and isinstance(events[-1], TurnDone)
        and events[-1].reason == "end"
        and any(isinstance(e, ContentDelta) and e.text.strip() for e in events)
        and not any(isinstance(e, ErrorEvent) for e in events)
    ):
        events.extend(
            [event async for event in engine.run_turn(session, ContinueTurn())]
        )
    text = "".join(event.text for event in events if isinstance(event, ContentDelta))
    done = [event for event in events if isinstance(event, TurnDone)]
    errors = [event for event in events if isinstance(event, ErrorEvent)]
    checks = {
        **score_report(text, expected_report(case)),
        "history_preserved": ModelMessagesTypeAdapter.dump_json(
            session.messages[:count]
        )
        == original,
        "memory_unchanged": not session.memory
        and not session.user_memory
        and not session.answer_hashes,
        "no_memory_events": not any(isinstance(e, MemoryUpdated) for e in events),
        "completed": bool(done) and done[-1].reason == "finished",
        "no_engine_errors": not errors,
    }
    return {
        "passed": all(checks.values()),
        "error": "engine_error" if errors else None,
        "checks": checks,
        "usage": done[-1].usage if done else {},
    }
