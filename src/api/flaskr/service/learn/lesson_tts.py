"""Build the streaming TTS processor a lesson speaks through.

Lifted out of the 1.0 run context so both engines can use it. Everything it needed from that
context was a value -- which course, which lesson, which learner, which tables -- so it takes them
as arguments and belongs to neither engine.

Returning None is normal, not a failure: a course with TTS switched off, settings that do not
validate, a provider that cannot be reached. The lesson is taught either way; it just is not
spoken.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.dao import cleanup_session_after

if TYPE_CHECKING:
    from flask import Flask

# What one synthesis request may carry when the deployment sets no limit of its own.
_DEFAULT_MAX_SEGMENT_CHARS = 300


def create_tts_processor(
    app: Flask,
    *,
    shifu_model: type,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bid: str,
    user_bid: str,
    generated_block_bid: str,
    learning_mode: str,
    position: int = 0,
    stream_element_number: int | None = None,
    stream_element_type: str | None = None,
    usage_scene: int | None = None,
) -> object | None:
    """Return the processor this lesson speaks through, or None if it is not spoken.

    Typed as `object` rather than `StreamingTTSProcessor`: naming that class here would reach into
    the tts service past its own entry point, which is the boundary this module is on the wrong
    side of. Callers drive it through `process_chunk` and `drain_ready_segments`.
    """
    try:
        from flaskr.common.config import get_config
        from flaskr.service.learn.learn_funcs import _resolve_runtime_tts_voice_id

        # Through the tts service's own entry point rather than reaching into its internals.
        from flaskr.service.tts.api import create_streaming_tts_processor
        from flaskr.service.tts.validation import validate_tts_settings_strict

        shifu_record = (
            shifu_model.query.filter(
                shifu_model.shifu_bid == shifu_bid,
                shifu_model.deleted == 0,
            )
            .order_by(shifu_model.id.desc())
            .first()
        )
        if not shifu_record or not getattr(shifu_record, "tts_enabled", False):
            return None

        provider_name = (
            (getattr(shifu_record, "tts_provider", "") or "").strip().lower()
        )
        if provider_name == "default":
            # The author chose no provider in particular; validation reads an empty string as
            # "use the deployment's".
            provider_name = ""
        try:
            validated = validate_tts_settings_strict(
                provider=provider_name,
                model=(getattr(shifu_record, "tts_model", "") or "").strip(),
                voice_id=(getattr(shifu_record, "tts_voice_id", "") or "").strip(),
                speed=getattr(shifu_record, "tts_speed", None),
                pitch=getattr(shifu_record, "tts_pitch", None),
                emotion=(getattr(shifu_record, "tts_emotion", "") or "").strip(),
            )
        except Exception as exc:
            app.logger.warning("TTS settings invalid; skip streaming TTS: %s", exc)
            return None

        if not validated:
            return None

        runtime_voice_id = _resolve_runtime_tts_voice_id(
            app,
            validated.provider,
            validated.voice_id,
            shifu_bid=shifu_bid,
        )
        max_segment_chars = (
            get_config("TTS_MAX_SEGMENT_CHARS") or _DEFAULT_MAX_SEGMENT_CHARS
        )
        return create_streaming_tts_processor(
            app=app,
            **({} if usage_scene is None else {"usage_scene": usage_scene}),
            generated_block_bid=generated_block_bid,
            outline_bid=outline_bid,
            progress_record_bid=progress_record_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            position=int(position or 0),
            voice_id=runtime_voice_id,
            speed=validated.speed,
            pitch=validated.pitch,
            emotion=validated.emotion,
            max_segment_chars=int(max_segment_chars),
            tts_provider=validated.provider,
            tts_model=validated.model,
            stream_element_number=stream_element_number,
            stream_element_type=stream_element_type,
            learning_mode=learning_mode,
        )
    except Exception as exc:
        app.logger.warning("Create TTS processor failed: %s", exc, exc_info=True)
        cleanup_session_after(exc, source="create tts processor")
        return None
