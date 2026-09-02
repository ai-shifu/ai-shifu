"""Transcript-only Langfuse tracing for Gemini Live follow-up sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)

from .live_follow_up_config import GEMINI_LIVE_MODEL_ID

if TYPE_CHECKING:
    from flask import Flask

    from .live_follow_up_persistence import (
        LiveTurnPersistenceInput,
        LiveTurnPersistenceResult,
    )


def _usage_count(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        try:
            value = usage.get(key)
            if value is not None:
                return max(0, int(value))
        except (TypeError, ValueError):
            return 0
    return 0


class LiveFollowUpTrace:
    """Own one trace per browser session and one generation per model turn."""

    def __init__(
        self,
        app: Flask,
        *,
        session_bid: str,
        user_bid: str,
        shifu_bid: str,
        outline_item_bid: str,
    ) -> None:
        """Start a trace containing stable identifiers only."""
        self._app = app
        self._closed = False
        self._trace, self._root = create_trace_with_root_span(
            client=get_langfuse_client(),
            trace_payload={
                "id": session_bid,
                "name": "gemini_live_follow_up",
                "user_id": user_bid,
                "session_id": session_bid,
                "metadata": {
                    "live_session_bid": session_bid,
                    "shifu_bid": shifu_bid,
                    "outline_item_bid": outline_item_bid,
                    "interaction_mode": "live_voice",
                },
            },
            root_span_payload={"name": "gemini_live_follow_up_session"},
        )

    @property
    def trace_id(self) -> str:
        """Return the SDK-normalized trace identifier."""
        return str(getattr(self._trace, "trace_id", "") or "")

    def record_turn(
        self,
        turn: LiveTurnPersistenceInput,
        result: LiveTurnPersistenceResult,
    ) -> None:
        """Write final transcripts, counters, latency, and stable identifiers."""
        usage = dict(turn.usage_metadata or {})
        input_tokens = _usage_count(usage, "promptTokenCount", "prompt_token_count")
        output_tokens = _usage_count(
            usage,
            "responseTokenCount",
            "response_token_count",
            "candidatesTokenCount",
        )
        total_tokens = _usage_count(usage, "totalTokenCount", "total_token_count")
        if not total_tokens:
            total_tokens = input_tokens + output_tokens
        generation = self._root.generation(
            name="gemini_live_follow_up_turn",
            model=GEMINI_LIVE_MODEL_ID,
            input=(turn.user_transcript or None),
            metadata={
                "live_turn_index": int(turn.turn_index),
                "interrupted": bool(turn.interrupted),
                "latency_ms": max(0, int(turn.latency_ms or 0)),
                "ask_block_bid": result.ask_block_bid,
                "answer_block_bid": result.answer_block_bid,
                "usage_bid": result.usage_bid,
            },
        )
        generation.end(
            output=turn.played_answer_transcript or None,
            usage={
                "input": input_tokens,
                "output": output_tokens,
                "total": total_tokens,
            },
        )

    def close(self, *, end_reason: str) -> None:
        """End the root observation once, using a bounded reason only."""
        if self._closed:
            return
        self._closed = True
        finalize_langfuse_trace(
            trace=self._trace,
            root_span=self._root,
            root_span_payload={"metadata": {"end_reason": end_reason}},
        )
