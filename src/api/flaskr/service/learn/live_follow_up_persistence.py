"""Persist transcript-only Gemini Live turns and non-billable client usage."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.learn.learn_dtos import ElementPayloadDTO, ElementType
from flaskr.service.learn.listen_element_payloads import _serialize_payload
from flaskr.service.learn.listen_element_queries import (
    _load_latest_active_element_row,
)
from flaskr.service.learn.listen_element_types import ELEMENT_TYPE_CODES
from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement
from flaskr.service.metering.api import (
    BillUsageRecord,
    UsageContext,
    record_llm_usage,
)
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
)
from sqlalchemy import func

from .live_follow_up_config import GEMINI_LIVE_MODEL_ID

if TYPE_CHECKING:
    from flask import Flask

_LIVE_TURN_NAMESPACE = uuid.UUID("53108c61-7df0-5264-8f6c-f1438f13fd2a")


class LiveFollowUpPersistenceError(RuntimeError):
    """Signal that a required transcript or usage write was not durable."""


def deterministic_live_turn_bid(
    session_bid: str,
    turn_index: int,
    kind: str,
) -> str:
    """Return a retry-stable UUID for one persisted artifact."""
    key = f"ai-shifu:gemini-live:{session_bid}:{int(turn_index)}:{kind}"
    return str(uuid.uuid5(_LIVE_TURN_NAMESPACE, key))


@dataclass(frozen=True)
class LiveTurnPersistenceContext:
    """Stable course and request fields shared by a Live session's turns."""

    session_bid: str
    user_bid: str
    shifu_bid: str
    outline_item_bid: str
    progress_record_bid: str
    anchor_element_bid: str
    preview_mode: bool
    learning_mode: str
    request_id: str = ""
    trace_id: str = ""


@dataclass(frozen=True)
class LiveTurnPersistenceInput:
    """Final transcript and usage snapshot for one terminal model turn."""

    turn_index: int
    user_transcript: str
    played_answer_transcript: str
    interrupted: bool
    usage_metadata: dict[str, Any] | None = None
    latency_ms: int = 0


@dataclass(frozen=True)
class LiveTurnPersistenceResult:
    """Identifiers written for one Live turn."""

    ask_block_bid: str = ""
    answer_block_bid: str = ""
    ask_element_bid: str = ""
    answer_element_bid: str = ""
    usage_bid: str = ""
    history_saved: bool = False


def _base_element_payload(
    context: LiveTurnPersistenceContext,
    turn: LiveTurnPersistenceInput,
    *,
    ask_element_bid: str | None = None,
) -> ElementPayloadDTO:
    return ElementPayloadDTO(
        anchor_element_bid=context.anchor_element_bid,
        ask_element_bid=ask_element_bid,
        interaction_mode="live_voice",
        live_session_bid=context.session_bid,
        live_turn_index=int(turn.turn_index),
        interrupted=bool(turn.interrupted),
    )


def _new_block(
    *,
    bid: str,
    context: LiveTurnPersistenceContext,
    content: str,
    role: int,
    block_type: int,
    position: int,
) -> LearnGeneratedBlock:
    return LearnGeneratedBlock(
        generated_block_bid=bid,
        progress_record_bid=context.progress_record_bid,
        user_bid=context.user_bid,
        block_bid="",
        outline_item_bid=context.outline_item_bid,
        shifu_bid=context.shifu_bid,
        type=block_type,
        role=role,
        generated_content=content,
        position=position,
        block_content_conf=content,
        generation_prompt=content if role == ROLE_STUDENT else "",
        liked=0,
        deleted=0,
        status=1,
    )


def _new_element(
    *,
    bid: str,
    block_bid: str,
    context: LiveTurnPersistenceContext,
    content: str,
    role: str,
    element_type: ElementType,
    element_index: int,
    run_event_seq: int,
    sequence_number: int,
    payload: ElementPayloadDTO,
) -> LearnGeneratedElement:
    return LearnGeneratedElement(
        element_bid=bid,
        progress_record_bid=context.progress_record_bid,
        user_bid=context.user_bid,
        generated_block_bid=block_bid,
        outline_item_bid=context.outline_item_bid,
        shifu_bid=context.shifu_bid,
        run_session_bid=context.session_bid,
        run_event_seq=run_event_seq,
        event_type="element",
        role=role,
        element_index=element_index,
        element_type=element_type.value,
        element_type_code=ELEMENT_TYPE_CODES[element_type],
        change_type="render",
        target_element_bid="",
        is_renderable=0,
        is_new=1,
        is_marker=0,
        sequence_number=sequence_number,
        is_speakable=0,
        audio_url="",
        audio_segments="[]",
        is_navigable=0,
        is_final=1,
        content_text=content,
        payload=_serialize_payload(payload),
        deleted=0,
        status=1,
    )


def _persist_transcript_history(
    context: LiveTurnPersistenceContext,
    turn: LiveTurnPersistenceInput,
) -> tuple[str, str, str, str, bool]:
    user_text = str(turn.user_transcript or "").strip()
    if not user_text:
        return "", "", "", "", False

    answer_text = str(turn.played_answer_transcript or "").strip()
    ask_block_bid = deterministic_live_turn_bid(
        context.session_bid, turn.turn_index, "ask-block"
    )
    answer_block_bid = deterministic_live_turn_bid(
        context.session_bid, turn.turn_index, "answer-block"
    )
    ask_element_bid = deterministic_live_turn_bid(
        context.session_bid, turn.turn_index, "ask-element"
    )
    answer_element_bid = deterministic_live_turn_bid(
        context.session_bid, turn.turn_index, "answer-element"
    )

    with unit_of_work():
        existing_blocks = {
            row.generated_block_bid
            for row in LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.generated_block_bid.in_(
                    [ask_block_bid, answer_block_bid]
                )
            ).all()
        }
        existing_elements = {
            row.element_bid
            for row in LearnGeneratedElement.query.filter(
                LearnGeneratedElement.element_bid.in_(
                    [ask_element_bid, answer_element_bid]
                )
            ).all()
        }
        max_block_position = int(
            db.session.query(func.max(LearnGeneratedBlock.position))
            .filter(
                LearnGeneratedBlock.progress_record_bid == context.progress_record_bid,
                LearnGeneratedBlock.deleted == 0,
            )
            .scalar()
            or 0
        )
        max_element_index = int(
            db.session.query(func.max(LearnGeneratedElement.element_index))
            .filter(
                LearnGeneratedElement.progress_record_bid
                == context.progress_record_bid,
                LearnGeneratedElement.deleted == 0,
            )
            .scalar()
            or 0
        )
        max_sequence_number = int(
            db.session.query(func.max(LearnGeneratedElement.sequence_number))
            .filter(
                LearnGeneratedElement.progress_record_bid
                == context.progress_record_bid,
                LearnGeneratedElement.deleted == 0,
            )
            .scalar()
            or 0
        )
        anchor_element = _load_latest_active_element_row(context.anchor_element_bid)
        anchor_element_index = max_element_index
        if (
            anchor_element is not None
            and anchor_element.progress_record_bid == context.progress_record_bid
        ):
            anchor_element_index = int(anchor_element.element_index or 0)

        if ask_block_bid not in existing_blocks:
            db.session.add(
                _new_block(
                    bid=ask_block_bid,
                    context=context,
                    content=user_text,
                    role=ROLE_STUDENT,
                    block_type=BLOCK_TYPE_MDASK_VALUE,
                    position=max_block_position + 1,
                )
            )
        if answer_block_bid not in existing_blocks:
            db.session.add(
                _new_block(
                    bid=answer_block_bid,
                    context=context,
                    content=answer_text,
                    role=ROLE_TEACHER,
                    block_type=BLOCK_TYPE_MDANSWER_VALUE,
                    position=max_block_position + 2,
                )
            )
        if ask_element_bid not in existing_elements:
            db.session.add(
                _new_element(
                    bid=ask_element_bid,
                    block_bid=ask_block_bid,
                    context=context,
                    content=user_text,
                    role="student",
                    element_type=ElementType.ASK,
                    element_index=anchor_element_index,
                    run_event_seq=int(turn.turn_index) * 2 + 1,
                    sequence_number=max_sequence_number + 1,
                    payload=_base_element_payload(context, turn),
                )
            )
        if answer_element_bid not in existing_elements:
            db.session.add(
                _new_element(
                    bid=answer_element_bid,
                    block_bid=answer_block_bid,
                    context=context,
                    content=answer_text,
                    role="teacher",
                    element_type=ElementType.ANSWER,
                    element_index=anchor_element_index,
                    run_event_seq=int(turn.turn_index) * 2 + 2,
                    sequence_number=max_sequence_number + 2,
                    payload=_base_element_payload(
                        context,
                        turn,
                        ask_element_bid=ask_element_bid,
                    ),
                )
            )

    return (
        ask_block_bid,
        answer_block_bid,
        ask_element_bid,
        answer_element_bid,
        True,
    )


_USAGE_COUNTER_KEYS = frozenset(
    {
        "cachedContentTokenCount",
        "candidatesTokenCount",
        "promptTokenCount",
        "responseTokenCount",
        "thoughtsTokenCount",
        "toolUsePromptTokenCount",
        "totalTokenCount",
    }
)
_USAGE_DETAIL_KEYS = frozenset(
    {
        "cacheTokensDetails",
        "candidatesTokensDetails",
        "promptTokensDetails",
        "responseTokensDetails",
        "toolUsePromptTokensDetails",
    }
)
_USAGE_MODALITIES = frozenset({"AUDIO", "IMAGE", "TEXT", "VIDEO"})
_MAX_CLIENT_USAGE_COUNT = 2_147_483_647


def _safe_usage_count(value: object) -> int | None:
    if type(value) is int:
        return min(_MAX_CLIENT_USAGE_COUNT, max(0, value))
    if type(value) is float and math.isfinite(value):
        return min(_MAX_CLIENT_USAGE_COUNT, max(0, int(value)))
    return None


def _safe_usage_metadata(value: object) -> dict[str, object]:
    """Allowlist untrusted browser-reported Gemini counters and modalities."""
    if not isinstance(value, dict):
        return {}
    safe: dict[str, object] = {}
    for key in _USAGE_COUNTER_KEYS:
        count = _safe_usage_count(value.get(key))
        if count is not None:
            safe[key] = count
    for key in _USAGE_DETAIL_KEYS:
        raw_details = value.get(key)
        if not isinstance(raw_details, list):
            continue
        details: list[dict[str, object]] = []
        for item in raw_details[:16]:
            if not isinstance(item, dict):
                continue
            modality = str(item.get("modality") or "").upper()
            token_count = _safe_usage_count(item.get("tokenCount"))
            if modality not in _USAGE_MODALITIES or token_count is None:
                continue
            details.append({"modality": modality, "tokenCount": token_count})
        if details:
            safe[key] = details
    return safe


def _usage_int(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if value is not None:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return 0
    return 0


def _persist_usage(
    app: Flask,
    context: LiveTurnPersistenceContext,
    turn: LiveTurnPersistenceInput,
    *,
    generated_block_bid: str,
) -> str:
    usage_bid = deterministic_live_turn_bid(
        context.session_bid, turn.turn_index, "usage"
    )
    existing = BillUsageRecord.query.filter(
        BillUsageRecord.usage_bid == usage_bid
    ).first()
    if existing is not None:
        return usage_bid

    usage = _safe_usage_metadata(turn.usage_metadata)
    prompt_tokens = _usage_int(usage, "promptTokenCount", "prompt_token_count")
    output_tokens = _usage_int(
        usage, "responseTokenCount", "response_token_count", "candidatesTokenCount"
    )
    total_tokens = _usage_int(usage, "totalTokenCount", "total_token_count")
    cached_tokens = _usage_int(
        usage, "cachedContentTokenCount", "cached_content_token_count"
    )
    if not total_tokens:
        total_tokens = min(
            _MAX_CLIENT_USAGE_COUNT,
            prompt_tokens + output_tokens,
        )
    recorded_usage_bid = record_llm_usage(
        app,
        UsageContext(
            user_bid=context.user_bid,
            shifu_bid=context.shifu_bid,
            outline_item_bid=context.outline_item_bid,
            progress_record_bid=context.progress_record_bid,
            generated_block_bid=generated_block_bid,
            request_id=context.request_id,
            trace_id=context.trace_id,
            usage_scene=(
                BILL_USAGE_SCENE_PREVIEW
                if context.preview_mode
                else BILL_USAGE_SCENE_PROD
            ),
            billable=0,
            learning_mode=context.learning_mode,
        ),
        usage_bid=usage_bid,
        provider="gemini",
        model=GEMINI_LIVE_MODEL_ID,
        is_stream=True,
        input=prompt_tokens,
        input_cache=cached_tokens,
        output=output_tokens,
        total=total_tokens,
        latency_ms=max(0, int(turn.latency_ms or 0)),
        extra={
            "usage_source": "gemini_live_follow_up_client_report",
            "usage_attestation": "client_reported_untrusted",
            "interaction_mode": "live_voice",
            "live_session_bid": context.session_bid,
            "live_turn_index": int(turn.turn_index),
            "gemini_usage": _safe_usage_metadata(usage),
        },
    )
    if recorded_usage_bid:
        return recorded_usage_bid
    message = "Gemini Live usage persistence failed"
    raise LiveFollowUpPersistenceError(message)


def persist_live_follow_up_turn(
    app: Flask,
    context: LiveTurnPersistenceContext,
    turn: LiveTurnPersistenceInput,
) -> LiveTurnPersistenceResult:
    """Idempotently persist transcript history, then a non-billable usage row."""
    (
        ask_block_bid,
        answer_block_bid,
        ask_element_bid,
        answer_element_bid,
        history_saved,
    ) = _persist_transcript_history(context, turn)
    usage_bid = _persist_usage(
        app,
        context,
        turn,
        generated_block_bid=answer_block_bid,
    )
    return LiveTurnPersistenceResult(
        ask_block_bid=ask_block_bid,
        answer_block_bid=answer_block_bid,
        ask_element_bid=ask_element_bid,
        answer_element_bid=answer_element_bid,
        usage_bid=usage_bid,
        history_saved=history_saved,
    )


def serialize_live_turn_result(result: LiveTurnPersistenceResult) -> str:
    """Return a compact JSON representation for low-level integration tests."""
    return json.dumps(result.__dict__, sort_keys=True, separators=(",", ":"))
