"""Synthetic authored-rubric checks through normal, reloaded engine turns."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic_ai.models import Model

GENERATION_SETTINGS = {"temperature": 0, "max_tokens": 2048}
QUESTION_PROMPTS = {
    "FEATURES": "What are the main characteristics of a digital computer?",
    "PERIPHERALS": "Name an input device and explain its function.",
}


def grading_script(case: dict[str, Any]) -> str:
    """Keep the next question's required point outside the current rubric."""
    extra = (
        "Also require support for varied peripheral devices in FEATURES. "
        if case.get("require_peripherals")
        else ""
    )
    return (
        "Teach these two questions in order. Ask one text interaction at a time. "
        f"Use exactly {QUESTION_PROMPTS['FEATURES']!r} and "
        f"{QUESTION_PROMPTS['PERIPHERALS']!r} as their interaction prompts, "
        "including on retries, so the learner sees the actual question. "
        "Do not finish before both answers pass. "
        "First, ask FEATURES: What are the main characteristics of a digital "
        "computer? The required points are automatic continuous operation under "
        "program control, fast computation, high precision, large information "
        "storage capacity, and general-purpose use across many applications. "
        + extra
        + "Optional background: digital codes represent information. Claims that "
        "computers can understand every problem or never make errors are wrong. "
        "If the answer passes, explain briefly, then ask PERIPHERALS: Name an "
        "input device and explain its function. This second answer requires a "
        "peripheral device and its function. If either answer fails, explain the "
        "gap and collect a new answer to that same question before proceeding."
    )


async def evaluate_grading(case: dict[str, Any], model: Model) -> dict[str, Any]:
    """Check observable advancement/retry, never ask the model to score itself."""
    from flaskr.service.learn.agent.engine import (
        ContentDelta,
        ContinueTurn,
        Engine,
        ErrorEvent,
        InteractionRequest,
        InteractionResponseTurn,
        MemoryUpdated,
        Session,
        TurnDone,
    )
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    engine = Engine(
        model,
        memory_admission=True,
        memory_recall=True,
        recall_history_compaction=True,
        teaching_history_compaction=True,
        exercise_statistics=True,
        request_limit=12,
        model_settings=dict(GENERATION_SETTINGS),
    )
    session = await engine.new_session(grading_script(case))
    setup = [event async for event in engine.run_turn(session)]
    setup_ok = (
        not any(isinstance(event, ErrorEvent) for event in setup)
        and len(session.pending) == 1
        and session.pending[0].spec.type == "text"
        and session.pending[0].spec.prompt == QUESTION_PROMPTS["FEATURES"]
    )
    if not setup_ok:
        return {
            "passed": False,
            "error": "unexpected_initial_question",
            "usage": session.usage,
        }
    session = Session.loads(session.dumps())
    count = len(session.messages)
    original = ModelMessagesTypeAdapter.dump_json(session.messages)
    events = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(values=[case["answer"]])
        )
    ]
    # A content-only response gets one normal host continuation, not another answer.
    if events and isinstance(events[-1], TurnDone) and events[-1].reason == "end":
        events.extend(
            [event async for event in engine.run_turn(session, ContinueTurn())]
        )
    questions = [event for event in events if isinstance(event, InteractionRequest)]
    errors = [event for event in events if isinstance(event, ErrorEvent)]
    checks = {
        "expected_question": len(questions) == 1
        and questions[0].spec.type == "text"
        and questions[0].spec.prompt == QUESTION_PROMPTS[case["expected_question"]],
        "feedback_present": any(
            isinstance(event, ContentDelta) and event.text.strip() for event in events
        ),
        "waiting_for_answer": not session.finished
        and len(session.pending) == 1
        and bool(events)
        and isinstance(events[-1], TurnDone)
        and events[-1].reason == "interaction",
        "history_preserved": ModelMessagesTypeAdapter.dump_json(
            session.messages[:count]
        )
        == original,
        "memory_unchanged": not session.memory
        and not session.user_memory
        and not session.answer_hashes
        and not any(isinstance(event, MemoryUpdated) for event in events),
        "no_engine_errors": not errors,
    }
    return {
        "passed": all(checks.values()),
        "error": "engine_error" if errors else None,
        "checks": checks,
        "usage": session.usage,
    }
