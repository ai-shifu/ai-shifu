"""Request-local report guidance must follow real reads and calculations."""

import json

import pytest
from flaskr.service.learn.agent.engine import Engine, exercise_statistics
from flaskr.service.learn.agent.engine.exercise_statistics import (
    ExerciseQuestion,
    SubmissionJudgment,
    _records,
    calculate_exercise_statistics,
    read_exercise_history,
)
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models.function import FunctionModel

from tests.service.learn.agent.engine.test_exercise_statistics import _fixture


def _engine(enabled: bool = True) -> Engine:
    return Engine(FunctionModel(lambda *_: None), exercise_statistics=enabled)


def test_reporting_reminder_is_conditional_and_disabled_for_portable_hosts() -> None:
    ctx = _fixture()
    enabled = _engine()._instructions(ctx)
    assert "Current exercise-report status" in enabled
    assert "offset=0" in enabled
    assert "Only when the script requests" in enabled
    assert "Current exercise-report status" not in _engine(enabled=False)._instructions(
        ctx
    )


@pytest.mark.anyio
async def test_paginated_reads_advance_only_in_contiguous_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(exercise_statistics, "RESULT_BYTES", 1024)
    ctx = _fixture()
    original = ModelMessagesTypeAdapter.dump_json(ctx.messages)
    first = json.loads(await read_exercise_history(ctx))
    assert first["next_offset"] is not None
    offset = first["next_offset"]
    notice = _engine()._instructions(ctx)
    assert f"offset={offset}" in notice
    await read_exercise_history(ctx, offset + 1)
    assert f"offset={offset}" in _engine()._instructions(ctx)
    await read_exercise_history(ctx, -1)
    assert f"offset={offset}" in _engine()._instructions(ctx)
    while offset is not None:
        page = json.loads(await read_exercise_history(ctx, offset))
        offset = page["next_offset"]
    assert "Original submissions have been read completely" in _engine()._instructions(
        ctx
    )
    assert "calculate_exercise_statistics" in _engine()._instructions(ctx)
    assert ModelMessagesTypeAdapter.dump_json(ctx.messages) == original


@pytest.mark.anyio
async def test_only_successful_calculation_supplies_current_totals() -> None:
    ctx = _fixture()
    records = _records(ctx)
    assert records is not None
    offset = 0
    while offset is not None:
        offset = json.loads(await read_exercise_history(ctx, offset))["next_offset"]
    rows = [
        ExerciseQuestion(
            question=str(index),
            submissions=[
                SubmissionJudgment(reference=r["reference"], outcome="correct")
            ],
            hints=0,
        )
        for index, r in enumerate(records)
    ]
    result = json.loads(await calculate_exercise_statistics(ctx, rows))
    assert result["status"] == "calculated"
    notice = _engine()._instructions(ctx)
    assert "Successful calculator totals for this turn" in notice
    assert json.dumps(result["totals"], separators=(",", ":")) in notice
    await calculate_exercise_statistics(ctx, rows[:-1])
    assert "Successful calculator totals for this turn" not in _engine()._instructions(
        ctx
    )


@pytest.mark.anyio
async def test_report_state_does_not_carry_to_another_turn() -> None:
    ctx = _fixture()
    offset = 0
    while offset is not None:
        offset = json.loads(await read_exercise_history(ctx, offset))["next_offset"]
    assert "Original submissions have been read completely" in _engine()._instructions(
        ctx
    )
    fresh = _fixture()
    assert "offset=0" in _engine()._instructions(fresh)
