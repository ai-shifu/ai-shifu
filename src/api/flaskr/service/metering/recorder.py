"""
Usage metering recorder.

Provides best-effort helpers to persist LLM and TTS usage records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from flask import Flask

from flaskr.dao import db
from flaskr.util.uuid import generate_id

from .models import BillingUsageRecord


@dataclass(frozen=True)
class UsageContext:
    """Context fields shared by usage records."""

    user_bid: str = ""
    shifu_bid: str = ""
    outline_item_bid: str = ""
    progress_record_bid: str = ""
    generated_block_bid: str = ""
    audio_bid: str = ""
    request_id: str = ""
    trace_id: str = ""
    usage_scene: int = 2
    billable: Optional[int] = None


def _resolve_billable(usage_scene: int, billable: Optional[int]) -> int:
    if billable is not None:
        return int(billable)
    if usage_scene in (0, 1):
        return 0
    return 1


def _persist_usage_record(app: Flask, record: BillingUsageRecord) -> bool:
    try:
        with app.app_context():
            db.session.add(record)
            db.session.commit()
        return True
    except Exception as exc:
        try:
            app.logger.error("Usage metering persist failed: %s", exc, exc_info=True)
        except Exception:
            pass
        try:
            db.session.rollback()
        except Exception:
            pass
        return False


def record_llm_usage(
    app: Flask,
    context: UsageContext,
    *,
    provider: str,
    model: str,
    is_stream: bool,
    input: int,
    output: int,
    total: int,
    latency_ms: int = 0,
    status: int = 0,
    error_message: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    usage_bid = generate_id(app)
    record = BillingUsageRecord(
        usage_bid=usage_bid,
        parent_usage_bid="",
        user_bid=context.user_bid or "",
        shifu_bid=context.shifu_bid or "",
        outline_item_bid=context.outline_item_bid or "",
        progress_record_bid=context.progress_record_bid or "",
        generated_block_bid=context.generated_block_bid or "",
        audio_bid=context.audio_bid or "",
        request_id=context.request_id or "",
        trace_id=context.trace_id or "",
        usage_type=1,
        record_level=0,
        usage_scene=int(context.usage_scene),
        provider=provider or "",
        model=model or "",
        is_stream=1 if is_stream else 0,
        input=int(input or 0),
        output=int(output or 0),
        total=int(total or 0),
        word_count=0,
        duration_ms=0,
        latency_ms=int(latency_ms or 0),
        segment_index=0,
        segment_count=0,
        billable=_resolve_billable(context.usage_scene, context.billable),
        status=int(status or 0),
        error_message=error_message or "",
        extra=extra or None,
    )
    if _persist_usage_record(app, record):
        return usage_bid
    return ""


def record_tts_usage(
    app: Flask,
    context: UsageContext,
    *,
    usage_bid: Optional[str] = None,
    provider: str,
    model: str,
    is_stream: bool,
    input: int,
    output: int,
    total: int,
    word_count: int,
    duration_ms: int,
    latency_ms: int = 0,
    record_level: int = 0,
    parent_usage_bid: str = "",
    segment_index: int = 0,
    segment_count: int = 0,
    status: int = 0,
    error_message: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    resolved_usage_bid = usage_bid or generate_id(app)
    record = BillingUsageRecord(
        usage_bid=resolved_usage_bid,
        parent_usage_bid=parent_usage_bid or "",
        user_bid=context.user_bid or "",
        shifu_bid=context.shifu_bid or "",
        outline_item_bid=context.outline_item_bid or "",
        progress_record_bid=context.progress_record_bid or "",
        generated_block_bid=context.generated_block_bid or "",
        audio_bid=context.audio_bid or "",
        request_id=context.request_id or "",
        trace_id=context.trace_id or "",
        usage_type=2,
        record_level=int(record_level or 0),
        usage_scene=int(context.usage_scene),
        provider=provider or "",
        model=model or "",
        is_stream=1 if is_stream else 0,
        input=int(input or 0),
        output=int(output or 0),
        total=int(total or 0),
        word_count=int(word_count or 0),
        duration_ms=int(duration_ms or 0),
        latency_ms=int(latency_ms or 0),
        segment_index=int(segment_index or 0),
        segment_count=int(segment_count or 0),
        billable=_resolve_billable(context.usage_scene, context.billable),
        status=int(status or 0),
        error_message=error_message or "",
        extra=extra or None,
    )
    if _persist_usage_record(app, record):
        return resolved_usage_bid
    return ""
