"""Privacy and payload contracts for Gemini Live Langfuse tracing."""

from __future__ import annotations

from flask import Flask
from flaskr.service.learn import live_follow_up_trace as trace_module
from flaskr.service.learn.live_follow_up_config import GEMINI_LIVE_MODEL_ID
from flaskr.service.learn.live_follow_up_persistence import (
    LiveTurnPersistenceInput,
    LiveTurnPersistenceResult,
)


class _FakeGeneration:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.end_calls: list[dict[str, object]] = []

    def end(self, **kwargs: object) -> None:
        self.end_calls.append(kwargs)


class _FakeRoot:
    def __init__(self) -> None:
        self.generations: list[_FakeGeneration] = []

    def generation(self, **kwargs: object) -> _FakeGeneration:
        generation = _FakeGeneration(**kwargs)
        self.generations.append(generation)
        return generation


class _FakeTrace:
    trace_id = "a" * 32


def _walk(value: object) -> list[object]:
    values = [value]
    if isinstance(value, dict):
        for key, item in value.items():
            values.extend(_walk(key))
            values.extend(_walk(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            values.extend(_walk(item))
    return values


def test_live_trace_records_only_final_transcripts_ids_latency_and_usage(
    monkeypatch: object,
) -> None:
    trace = _FakeTrace()
    root = _FakeRoot()
    client = object()
    created: list[dict[str, object]] = []
    finalized: list[dict[str, object]] = []

    def fake_create_trace_with_root_span(**kwargs: object) -> tuple[object, object]:
        created.append(kwargs)
        return trace, root

    def fake_finalize_langfuse_trace(**kwargs: object) -> object:
        finalized.append(kwargs)
        return kwargs["trace"]

    def fake_get_langfuse_client() -> object:
        return client

    monkeypatch.setattr(
        trace_module,
        "create_trace_with_root_span",
        fake_create_trace_with_root_span,
    )
    monkeypatch.setattr(
        trace_module,
        "finalize_langfuse_trace",
        fake_finalize_langfuse_trace,
    )
    monkeypatch.setattr(
        trace_module,
        "get_langfuse_client",
        fake_get_langfuse_client,
    )

    live_trace = trace_module.LiveFollowUpTrace(
        Flask("live-follow-up-trace-test"),
        session_bid="session-1",
        user_bid="user-1",
        shifu_bid="course-1",
        outline_item_bid="outline-1",
    )
    live_trace.record_turn(
        LiveTurnPersistenceInput(
            turn_index=3,
            user_transcript="final learner transcript",
            played_answer_transcript="final played answer",
            interrupted=True,
            latency_ms=321,
            usage_metadata={
                "promptTokenCount": 11,
                "responseTokenCount": 7,
                "totalTokenCount": 18,
                "promptTokensDetails": [{"modality": "AUDIO", "tokenCount": 10}],
                "raw_audio": "raw-audio-sentinel",
                "ticket": "ticket-sentinel",
                "api_key": "api-key-sentinel",
                "raw_error": "raw-error-sentinel",
                "resumption_handle": "handle-sentinel",
            },
        ),
        LiveTurnPersistenceResult(
            ask_block_bid="ask-block-1",
            answer_block_bid="answer-block-1",
            usage_bid="usage-1",
            history_saved=True,
        ),
    )
    live_trace.close(end_reason="ended_by_user")
    live_trace.close(end_reason="raw-error-sentinel")

    assert live_trace.trace_id == "a" * 32
    assert created == [
        {
            "client": client,
            "trace_payload": {
                "id": "session-1",
                "name": "gemini_live_follow_up",
                "user_id": "user-1",
                "session_id": "session-1",
                "metadata": {
                    "live_session_bid": "session-1",
                    "shifu_bid": "course-1",
                    "outline_item_bid": "outline-1",
                    "interaction_mode": "live_voice",
                },
            },
            "root_span_payload": {"name": "gemini_live_follow_up_session"},
        }
    ]
    assert len(root.generations) == 1
    generation = root.generations[0]
    assert generation.kwargs == {
        "name": "gemini_live_follow_up_turn",
        "model": GEMINI_LIVE_MODEL_ID,
        "input": "final learner transcript",
        "metadata": {
            "live_turn_index": 3,
            "interrupted": True,
            "latency_ms": 321,
            "ask_block_bid": "ask-block-1",
            "answer_block_bid": "answer-block-1",
            "usage_bid": "usage-1",
        },
    }
    assert generation.end_calls == [
        {
            "output": "final played answer",
            "usage": {"input": 11, "output": 7, "total": 18},
        }
    ]
    assert finalized == [
        {
            "trace": trace,
            "root_span": root,
            "root_span_payload": {"metadata": {"end_reason": "ended_by_user"}},
        }
    ]

    delivered_values = _walk(
        {
            "created": created,
            "generation": generation.kwargs,
            "generation_end": generation.end_calls,
            "finalized": finalized,
        }
    )
    for prohibited in (
        "raw_audio",
        "raw-audio-sentinel",
        "ticket",
        "ticket-sentinel",
        "api_key",
        "api-key-sentinel",
        "raw_error",
        "raw-error-sentinel",
        "resumption_handle",
        "handle-sentinel",
        "promptTokensDetails",
    ):
        assert prohibited not in delivered_values
