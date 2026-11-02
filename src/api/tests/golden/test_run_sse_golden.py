"""Golden SSE transcript for a follow-up question on the learner ``/run`` endpoint.

The test drives ``PUT /api/learn/shifu/<shifu_bid>/run/<outline_bid>`` with an
``ask`` input end-to-end (route -> learn/host semaphore/queue/thread ->
``learn.ask`` -> element adapter) against the seeded golden shifu, then
normalizes the raw SSE byte stream (see ``tests/golden/normalize.py``) and
compares it against ``tests/golden/fixtures/run_ask_flow.sse.txt``.

Lesson turns are taught by the 2.0 engine, whose output is model-driven; their
SSE contract is covered by the agent host tests under ``tests/service/learn``.
The 1.0 lesson transcripts recorded here were removed with the 1.0 runtime.

Update mode: ``UPDATE_GOLDEN=1 pytest tests/golden/`` rewrites the fixtures.
"""

from __future__ import annotations

from tests.golden.conftest import (
    assert_or_update_golden,
    mock_validate_user,
    seed_golden_user,
)
from tests.golden.normalize import (
    IdNormalizer,
    normalize_sse_transcript,
    parse_sse_events,
)

RUN_HEADERS = {"Token": "golden-token"}


def _run_lesson(test_client: object, shifu: object, payload: object) -> str:
    response = test_client.put(
        f"/api/learn/shifu/{shifu.shifu_bid}/run/{shifu.lesson_bid}",
        json=payload,
        headers=RUN_HEADERS,
    )
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    return response.get_data(as_text=True)


def _prepare_user(app: object, monkeypatch: object, user_bid: str) -> None:
    seed_golden_user(app, user_bid)
    mock_validate_user(monkeypatch, user_bid)


def test_run_ask_flow_golden(
    app: object, test_client: object, monkeypatch: object, golden_shifu: object
) -> None:
    user_bid = "golden-user-ask-0001"
    _prepare_user(app, monkeypatch, user_bid)

    raw = _run_lesson(
        test_client,
        golden_shifu,
        {"input": {"input": ["What is a golden test?"]}, "input_type": "ask"},
    )

    events = parse_sse_events(raw)
    assert events, "ask transcript must not be empty"
    assert events[-1].get("type") == "done"
    assert events[-1].get("is_terminal") is True

    assert_or_update_golden(
        "run_ask_flow.sse.txt", normalize_sse_transcript(raw, IdNormalizer())
    )
