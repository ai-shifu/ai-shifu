from __future__ import annotations

from typing import Any

from flaskr.dao import db
from flaskr.service.tts.models import (
    AUDIO_STATUS_COMPLETED,
    LearnGeneratedAudio,
)


def build_voice_settings_payload(voice_settings: Any) -> dict[str, Any]:
    return {
        "speed": getattr(voice_settings, "speed", 1.0),
        "pitch": getattr(voice_settings, "pitch", 0),
        "emotion": getattr(voice_settings, "emotion", ""),
        "volume": getattr(voice_settings, "volume", 1.0),
    }


def build_completed_audio_record(
    *,
    audio_bid: str,
    generated_block_bid: str,
    progress_record_bid: str,
    user_bid: str,
    shifu_bid: str,
    oss_url: str,
    oss_bucket: str,
    oss_object_key: str,
    duration_ms: int,
    file_size: int,
    voice_settings: Any,
    tts_model: str,
    text_length: int,
    segment_count: int,
    position: int = 0,
    audio_format: str = "mp3",
    sample_rate: int = 24000,
) -> LearnGeneratedAudio:
    return LearnGeneratedAudio(
        audio_bid=audio_bid or "",
        generated_block_bid=generated_block_bid or "",
        position=int(position or 0),
        progress_record_bid=progress_record_bid or "",
        user_bid=user_bid or "",
        shifu_bid=shifu_bid or "",
        oss_url=oss_url or "",
        oss_bucket=oss_bucket or "",
        oss_object_key=oss_object_key or "",
        duration_ms=int(duration_ms or 0),
        file_size=int(file_size or 0),
        audio_format=audio_format or "mp3",
        sample_rate=int(sample_rate or 24000),
        voice_id=getattr(voice_settings, "voice_id", "") or "",
        voice_settings=build_voice_settings_payload(voice_settings),
        model=tts_model or "",
        text_length=int(text_length or 0),
        segment_count=int(segment_count or 0),
        status=AUDIO_STATUS_COMPLETED,
    )


def save_audio_record(
    audio_record: LearnGeneratedAudio, *, commit: bool = True
) -> None:
    db.session.add(audio_record)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
