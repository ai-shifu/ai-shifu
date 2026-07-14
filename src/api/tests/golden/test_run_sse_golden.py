"""Golden SSE transcripts for the learner ``/run`` endpoint.

Each test drives ``PUT /api/learn/shifu/<shifu_bid>/run/<outline_bid>``
end-to-end (route -> runscript_v2 lock/queue/thread -> RunScriptContextV2 ->
markdown-flow -> element adapter) against the seeded golden shifu, then
normalizes the raw SSE byte stream (see ``tests/golden/normalize.py``) and
compares it against a recorded fixture under ``tests/golden/fixtures/``.

Recorded scenarios (one fixture per scenario):

- ``run_fresh_start.sse.txt``     -- first run of the lesson, no prior progress
  (outline updates, preserved + LLM content, first interaction, terminal done)
- ``run_continue.sse.txt``        -- second call with empty input while the
  interaction is pending (validation-error content + re-rendered interaction)
- ``run_interaction_input.sse.txt`` -- submitting a button choice for the
  pending interaction (variable_update, final content block, completion tail)
- ``run_ask_flow.sse.txt``        -- follow-up ask (semaphore path) after the
  lesson reached the interaction

Update mode: ``UPDATE_GOLDEN=1 pytest tests/golden/`` rewrites the fixtures.

TODO (later Phase 0 batches): mid-stream error and resume-after-interruption
scenarios need fault injection points that do not exist as test seams yet;
they are listed in the master plan and intentionally not recorded here.
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


def _run_lesson(test_client, shifu, payload) -> str:
    response = test_client.put(
        f"/api/learn/shifu/{shifu.shifu_bid}/run/{shifu.lesson_bid}",
        json=payload,
        headers=RUN_HEADERS,
    )
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    return response.get_data(as_text=True)


def _prepare_user(app, monkeypatch, user_bid: str) -> None:
    seed_golden_user(app, user_bid)
    mock_validate_user(monkeypatch, user_bid)


def test_run_fresh_start_golden(app, test_client, monkeypatch, golden_shifu):
    user_bid = "golden-user-fresh-0001"
    _prepare_user(app, monkeypatch, user_bid)

    raw = _run_lesson(
        test_client,
        golden_shifu,
        {"input": None, "input_type": "start"},
    )

    events = parse_sse_events(raw)
    event_types = [event.get("type") for event in events]
    # Contract sanity: the transcript must be non-trivial before recording.
    assert "outline_item_update" in event_types
    assert "element" in event_types
    assert event_types[-1] == "done"
    assert events[-1].get("is_terminal") is True
    element_contents = [
        event["content"].get("content", "")
        for event in events
        if event.get("type") == "element" and isinstance(event.get("content"), dict)
    ]
    assert any("Hello golden learner." in content for content in element_contents)
    assert any("fav_color" in content for content in element_contents)

    assert_or_update_golden(
        "run_fresh_start.sse.txt", normalize_sse_transcript(raw, IdNormalizer())
    )


def test_run_continue_golden(app, test_client, monkeypatch, golden_shifu):
    user_bid = "golden-user-continue-0001"
    _prepare_user(app, monkeypatch, user_bid)

    # First call reaches the pending interaction (same as fresh_start).
    _run_lesson(test_client, golden_shifu, {"input": None, "input_type": "start"})
    # Second call: empty continue while the interaction still awaits input.
    raw = _run_lesson(
        test_client,
        golden_shifu,
        {"input": None, "input_type": "continue"},
    )

    events = parse_sse_events(raw)
    assert events, "continue transcript must not be empty"
    assert events[-1].get("type") == "done"
    assert events[-1].get("is_terminal") is True

    assert_or_update_golden(
        "run_continue.sse.txt", normalize_sse_transcript(raw, IdNormalizer())
    )


def test_run_interaction_input_golden(app, test_client, monkeypatch, golden_shifu):
    user_bid = "golden-user-interact-0001"
    _prepare_user(app, monkeypatch, user_bid)

    # Reach the interaction block first.
    first = _run_lesson(
        test_client, golden_shifu, {"input": None, "input_type": "start"}
    )
    assert any(
        "fav_color" in str(event.get("content", ""))
        for event in parse_sse_events(first)
    )

    # Submit the matching button choice for {{fav_color}}.
    raw = _run_lesson(
        test_client,
        golden_shifu,
        {"input": {"fav_color": ["red"]}, "input_type": "select"},
    )

    events = parse_sse_events(raw)
    event_types = [event.get("type") for event in events]
    assert "variable_update" in event_types
    assert event_types[-1] == "done"
    assert events[-1].get("is_terminal") is True
    element_contents = [
        event["content"].get("content", "")
        for event in events
        if event.get("type") == "element" and isinstance(event.get("content"), dict)
    ]
    assert any("Hello golden learner." in content for content in element_contents)

    assert_or_update_golden(
        "run_interaction_input.sse.txt", normalize_sse_transcript(raw, IdNormalizer())
    )


def test_run_ask_flow_golden(app, test_client, monkeypatch, golden_shifu):
    user_bid = "golden-user-ask-0001"
    _prepare_user(app, monkeypatch, user_bid)

    # Build lesson context first so the ask has history to anchor on.
    _run_lesson(test_client, golden_shifu, {"input": None, "input_type": "start"})

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
