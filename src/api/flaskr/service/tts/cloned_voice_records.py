"""Read and manage cloned voices created outside the course editor."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from flaskr.service.billing.api import to_decimal
from flaskr.service.common.models import raise_param_error
from flaskr.service.tts.models import TTS_CLONE_PROVIDER_MINIMAX, TTSMiniMaxClonedVoice
from flaskr.util.datetime import to_utc_iso

if TYPE_CHECKING:
    from flask import Flask

_VOICE_ID_RE = re.compile(r"^[A-Za-z](?=.{7,63}$)[A-Za-z0-9_-]*[A-Za-z0-9]$")


def is_valid_minimax_custom_voice_id(value: str) -> bool:
    """Return whether a MiniMax custom voice ID has a valid shape."""
    return bool(_VOICE_ID_RE.match(str(value or "").strip()))


def list_minimax_cloned_voices(
    app: Flask,
    *,
    owner_user_bid: str,
    shifu_bid: str = "",
    include_deleted: bool = False,
    provider: str = "",
) -> list[dict[str, object]]:
    """Return cloned voices registered for an owner."""
    owner_bid = _normalize_required(owner_user_bid, "owner_user_bid")
    normalized_provider = (provider or "").strip().lower()
    with app.app_context():
        query = TTSMiniMaxClonedVoice.query.filter(
            TTSMiniMaxClonedVoice.owner_user_bid == owner_bid
        )
        if normalized_provider:
            query = query.filter(TTSMiniMaxClonedVoice.provider == normalized_provider)
        if shifu_bid:
            query = query.filter(TTSMiniMaxClonedVoice.shifu_bid == shifu_bid)
        if not include_deleted:
            query = query.filter(TTSMiniMaxClonedVoice.deleted == 0)
        rows = query.order_by(
            TTSMiniMaxClonedVoice.created_at.desc(),
            TTSMiniMaxClonedVoice.id.desc(),
        ).all()
        return [serialize_minimax_cloned_voice(row) for row in rows]


def serialize_minimax_cloned_voice(row: TTSMiniMaxClonedVoice) -> dict[str, object]:
    """Serialize cloned voice metadata without provider credentials."""
    return {
        "voice_bid": row.voice_bid,
        "owner_user_bid": row.owner_user_bid,
        "shifu_bid": row.shifu_bid,
        "display_name": row.display_name,
        "provider": row.provider or TTS_CLONE_PROVIDER_MINIMAX,
        "voice_id": row.voice_id,
        "status": row.status,
        "status_msg": row.status_msg or "",
        "failure_reason": row.failure_reason or "",
        "retry_count": int(row.retry_count or 0),
        "source_capture_method": row.source_capture_method or "",
        "source_audio_url": row.source_audio_url or "",
        "source_audio_duration_ms": int(row.source_audio_duration_ms or 0),
        "normalized_audio_url": row.normalized_audio_url or "",
        "normalized_audio_duration_ms": int(row.normalized_audio_duration_ms or 0),
        "prompt_audio_url": row.prompt_audio_url or "",
        "prompt_audio_duration_ms": int(row.prompt_audio_duration_ms or 0),
        "minimax_demo_audio_url": row.minimax_demo_audio_url or "",
        "minimax_trace_id": row.minimax_trace_id or "",
        "billing_status": row.billing_status or "",
        "estimated_credits": str(to_decimal(row.estimated_credits)),
        "charged_credits": str(to_decimal(row.charged_credits)),
        "clone_usage_bid": row.clone_usage_bid or "",
        "created_at": to_utc_iso(row.created_at),
        "updated_at": to_utc_iso(row.updated_at),
        "ready_at": to_utc_iso(row.ready_at),
        "deleted": int(row.deleted or 0),
    }


def _normalize_required(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise_param_error(f"{field_name} is required")
    return normalized
