from __future__ import annotations

import base64
import json
import uuid
from dataclasses import replace
from typing import Any

from flask import Response, current_app, stream_with_context

from flaskr.api.tts import (
    get_default_audio_settings,
    get_default_voice_settings,
    is_tts_configured,
    synthesize_text,
)
from flaskr.service.common import raise_error
from flaskr.service.common.models import raise_param_error
from flaskr.service.metering import UsageContext, record_tts_usage
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.service.tts import preprocess_for_tts
from flaskr.service.tts.pipeline import split_text_for_tts
from flaskr.service.tts.validation import validate_tts_settings_strict
from flaskr.util.uuid import generate_id


def _build_tts_preview_usage_metadata(
    voice_settings: Any,
    audio_settings: Any,
) -> dict[str, object]:
    return {
        "voice_id": getattr(voice_settings, "voice_id", "") or "",
        "speed": getattr(voice_settings, "speed", None),
        "pitch": getattr(voice_settings, "pitch", None),
        "emotion": getattr(voice_settings, "emotion", "") or "",
        "volume": getattr(voice_settings, "volume", None),
        "format": getattr(audio_settings, "format", "mp3") or "mp3",
        "sample_rate": getattr(audio_settings, "sample_rate", 24000) or 24000,
    }


def build_tts_preview_response(
    json_data: dict | None,
    *,
    request_user_id: str = "",
    request_user_is_creator: bool = False,
) -> Response:
    app = current_app._get_current_object()
    payload = json_data or {}
    provider_name = (payload.get("provider") or "").strip().lower()
    model = (payload.get("model") or "").strip()
    voice_id = payload.get("voice_id") or ""
    speed_raw = payload.get("speed")
    pitch_raw = payload.get("pitch")
    emotion = payload.get("emotion", "")
    text = payload.get(
        "text",
        "你好，这是语音合成的试听效果。Hello, this is a preview of text-to-speech.",
    )

    validated = validate_tts_settings_strict(
        provider=provider_name,
        model=model,
        voice_id=voice_id,
        speed=speed_raw,
        pitch=pitch_raw,
        emotion=emotion,
    )

    if not is_tts_configured(validated.provider):
        raise_param_error(f"TTS provider is not configured: {validated.provider}")

    if len(text) > 200:
        text = text[:200]

    voice_settings = get_default_voice_settings(validated.provider)
    voice_settings.voice_id = validated.voice_id
    voice_settings.speed = validated.speed
    voice_settings.pitch = validated.pitch
    voice_settings.emotion = validated.emotion

    segments = split_text_for_tts(text, provider_name=validated.provider)
    if not segments:
        raise_error("TTS_PREVIEW_FAILED")

    audio_settings = get_default_audio_settings(validated.provider)
    safe_audio_settings = replace(audio_settings, format="mp3")
    audio_bid = uuid.uuid4().hex
    cleaned_text = preprocess_for_tts(text or "")
    runtime_billable = 1 if request_user_is_creator else 0
    usage_context = UsageContext(
        user_bid=str(request_user_id or "").strip(),
        shifu_bid="",
        audio_bid=audio_bid,
        usage_scene=BILL_USAGE_SCENE_DEBUG,
        billable=runtime_billable,
    )
    parent_usage_bid = generate_id(app)
    usage_metadata = _build_tts_preview_usage_metadata(
        voice_settings=voice_settings,
        audio_settings=safe_audio_settings,
    )

    def event_stream():
        total_duration_ms = 0
        total_word_count = 0
        try:
            for index, segment_text in enumerate(segments):
                result = synthesize_text(
                    text=segment_text,
                    voice_settings=voice_settings,
                    audio_settings=safe_audio_settings,
                    model=validated.model or None,
                    provider_name=validated.provider,
                )
                total_duration_ms += int(result.duration_ms or 0)
                word_count = int(getattr(result, "word_count", 0) or 0)
                total_word_count += word_count
                record_tts_usage(
                    app,
                    usage_context,
                    provider=validated.provider,
                    model=validated.model or "",
                    is_stream=True,
                    input=len(segment_text or ""),
                    output=len(segment_text or ""),
                    total=len(segment_text or ""),
                    word_count=word_count,
                    duration_ms=int(result.duration_ms or 0),
                    latency_ms=0,
                    record_level=1,
                    parent_usage_bid=parent_usage_bid,
                    segment_index=index,
                    segment_count=0,
                    extra=usage_metadata,
                )
                audio_base64 = base64.b64encode(result.audio_data).decode("utf-8")
                payload = {
                    "outline_bid": "",
                    "generated_block_bid": "",
                    "type": "audio_segment",
                    "content": {
                        "segment_index": index,
                        "audio_data": audio_base64,
                        "duration_ms": int(result.duration_ms or 0),
                        "is_final": False,
                    },
                }
                yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

            record_tts_usage(
                app,
                usage_context,
                usage_bid=parent_usage_bid,
                provider=validated.provider,
                model=validated.model or "",
                is_stream=True,
                input=len(text or ""),
                output=len(cleaned_text or ""),
                total=len(cleaned_text or ""),
                word_count=total_word_count,
                duration_ms=total_duration_ms,
                latency_ms=0,
                record_level=0,
                parent_usage_bid="",
                segment_index=0,
                segment_count=len(segments),
                extra=usage_metadata,
            )
            payload = {
                "outline_bid": "",
                "generated_block_bid": "",
                "type": "audio_complete",
                "content": {
                    "audio_url": "",
                    "audio_bid": audio_bid,
                    "duration_ms": total_duration_ms,
                },
            }
            yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
        except GeneratorExit:
            current_app.logger.info("client closed tts preview stream early")
            raise
        except Exception:
            current_app.logger.error("TTS preview stream failed", exc_info=True)
            raise

    return Response(
        stream_with_context(event_stream()),
        headers={"Cache-Control": "no-cache"},
        mimetype="text/event-stream",
    )
