"""Synthesize learner-facing TTS audio for generated blocks and editor previews."""

import base64
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, replace

from flask import Flask
from flaskr.api.tts import (
    AudioSettings,
    VoiceSettings,
    get_default_audio_settings,
    get_default_voice_settings,
    get_tts_provider,
    is_tts_configured,
    synthesize_text,
)
from flaskr.dao.uow import unit_of_work
from flaskr.service.common import raise_error, raise_error_with_args
from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    AudioSegmentDTO,
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.listen_element_matching import (
    get_speakable_text_elements,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
)
from flaskr.service.metering import UsageContext, record_tts_usage
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.shifu.models import (
    DraftShifu,
    PublishedShifu,
)
from flaskr.service.tts import (
    has_speakable_text,
    preprocess_for_tts,
    resolve_tts_billable_chars,
)
from flaskr.service.tts.api import (
    TTSRpmQueueTimeoutError,
    create_streaming_tts_processor,
    find_ready_cloned_voice,
    find_tracked_cloned_voice,
    get_clone_provider_spec,
)
from flaskr.service.tts.audio_record_utils import (
    build_completed_audio_record,
    save_audio_record,
)
from flaskr.service.tts.audio_utils import (
    concat_audio_best_effort,
    get_audio_duration_ms,
)
from flaskr.service.tts.models import (
    AUDIO_STATUS_COMPLETED,
    TTS_MINIMAX_CLONE_STATUS_READY,
    LearnGeneratedAudio,
)
from flaskr.service.tts.pipeline import split_text_for_tts
from flaskr.service.tts.subtitle_utils import (
    append_subtitle_cue,
    normalize_subtitle_cues,
)
from flaskr.service.tts.tts_handler import upload_audio_to_oss
from flaskr.service.tts.validation import validate_tts_settings_strict
from flaskr.util import generate_id


def _resolve_runtime_tts_voice_id(
    app: Flask, provider: str, voice_id: str, *, shifu_bid: str
) -> str:
    """Return a voice id that is safe to send to the provider at runtime.

    Cloned voice ids share the character shape of built-in ids, so a stale DB
    value can pass local shape validation and fail only after the external API
    call (e.g. MiniMax `2054 - voice id not exist`). For learner-facing audio
    generation, keep built-in voices and clone ids that are verified by a ready
    local row, while falling back when this shifu explicitly points at a local
    cloned voice row that is not ready yet.

    Note: when this shifu tracks no row for the id, any ready clone row of the
    same provider lets it through regardless of owner. Operator-registered rows
    carry an empty shifu_bid, so this global fallback is what makes them usable
    in courses; it knowingly skips owner scoping at runtime (unlike preview)
    and tightening it is tracked separately.
    """
    normalized_provider = (provider or "").strip().lower()
    normalized_voice_id = (voice_id or "").strip()
    if get_clone_provider_spec(normalized_provider) is None or not normalized_voice_id:
        return normalized_voice_id

    provider_config = get_tts_provider(normalized_provider).get_provider_config()
    built_in_voice_ids = {
        (voice.get("value") or "").strip()
        for voice in (provider_config.voices or [])
        if (voice.get("value") or "").strip()
    }
    if normalized_voice_id in built_in_voice_ids:
        return normalized_voice_id

    # If this shifu tracks a local clone row for the selected voice id, only
    # accept it when the latest row is ready. This prevents preview/runtime
    # from trying to use a clone that is still queued or has already failed.
    normalized_shifu_bid = (shifu_bid or "").strip()
    cloned_voice = find_tracked_cloned_voice(
        provider=normalized_provider,
        voice_id=normalized_voice_id,
        shifu_bid=normalized_shifu_bid,
    )
    if cloned_voice and cloned_voice.status == TTS_MINIMAX_CLONE_STATUS_READY:
        return normalized_voice_id
    if cloned_voice:
        app.logger.warning(
            "%s TTS voice_id %s for shifu %s is tracked locally but not ready; falling back to a default voice",
            normalized_provider,
            normalized_voice_id,
            normalized_shifu_bid,
        )
    else:
        ready_clone = find_ready_cloned_voice(
            provider=normalized_provider,
            voice_id=normalized_voice_id,
        )
        if ready_clone:
            return normalized_voice_id

    default_voice_settings = get_default_voice_settings(normalized_provider)
    fallback_voice_id = (getattr(default_voice_settings, "voice_id", "") or "").strip()
    if not fallback_voice_id and built_in_voice_ids:
        fallback_voice_id = min(built_in_voice_ids)
    app.logger.warning(
        "%s TTS voice_id %s is not a current built-in voice or ready cloned voice; falling back to %s",
        normalized_provider,
        normalized_voice_id,
        fallback_voice_id,
    )
    return fallback_voice_id or normalized_voice_id


def _resolve_shifu_tts_settings(
    app: Flask,
    *,
    shifu_bid: str,
    preview_mode: bool,
) -> tuple[str, str, VoiceSettings, AudioSettings]:
    shifu_model = DraftShifu if preview_mode else PublishedShifu
    shifu = (
        shifu_model.query.filter(
            shifu_model.shifu_bid == shifu_bid,
            shifu_model.deleted == 0,
        )
        .order_by(shifu_model.id.desc())
        .first()
    )
    if not shifu:
        raise_error("server.shifu.shifuNotFound")

    if not getattr(shifu, "tts_enabled", False):
        raise_error("server.shifu.ttsNotEnabled")

    provider = (getattr(shifu, "tts_provider", "") or "").strip().lower()
    tts_model = (getattr(shifu, "tts_model", "") or "").strip()
    voice_id = (getattr(shifu, "tts_voice_id", "") or "").strip()
    speed_raw = getattr(shifu, "tts_speed", None)
    pitch_raw = getattr(shifu, "tts_pitch", None)
    emotion = (getattr(shifu, "tts_emotion", "") or "").strip()

    validated = validate_tts_settings_strict(
        provider=provider,
        model=tts_model,
        voice_id=voice_id,
        speed=speed_raw,
        pitch=pitch_raw,
        emotion=emotion,
    )

    runtime_voice_id = _resolve_runtime_tts_voice_id(
        app,
        validated.provider,
        validated.voice_id,
        shifu_bid=shifu_bid,
    )

    voice_settings = get_default_voice_settings(validated.provider)
    voice_settings.voice_id = runtime_voice_id
    voice_settings.speed = validated.speed
    voice_settings.pitch = validated.pitch
    voice_settings.emotion = validated.emotion

    audio_settings = get_default_audio_settings(validated.provider)

    return validated.provider, validated.model, voice_settings, audio_settings


def _yield_tts_segments(
    *,
    text: str,
    provider: str,
    tts_model: str,
    voice_settings: object,
    audio_settings: object,
) -> Iterator[tuple[int, bytes, int, str, int, int, int]]:
    provider_name = (provider or "").strip().lower()
    if not provider_name:
        error_message = "TTS provider is required"
        raise ValueError(error_message)
    if not is_tts_configured(provider_name):
        message = f"TTS provider is not configured: {provider_name}"
        raise ValueError(message)

    segments = split_text_for_tts(text, provider_name=provider_name)
    if not segments:
        error_message = "No speakable text after preprocessing"
        raise ValueError(error_message)

    safe_audio_settings = replace(audio_settings, format="mp3")
    for index, segment_text in enumerate(segments):
        segment_start = time.monotonic()
        result = synthesize_text(
            text=segment_text,
            voice_settings=voice_settings,
            audio_settings=safe_audio_settings,
            model=(tts_model or "").strip() or None,
            provider_name=provider_name,
        )
        latency_ms = int((time.monotonic() - segment_start) * 1000)
        yield (
            index,
            result.audio_data,
            int(result.duration_ms or 0),
            segment_text,
            int(result.word_count or 0),
            int(getattr(result, "usage_characters", 0) or 0),
            latency_ms,
        )


def _build_tts_usage_metadata(
    *, voice_settings: object, audio_settings: object
) -> dict:
    return {
        "voice_id": voice_settings.voice_id or "",
        "speed": voice_settings.speed,
        "pitch": voice_settings.pitch,
        "emotion": voice_settings.emotion,
        "volume": voice_settings.volume,
        "format": audio_settings.format or "mp3",
        "sample_rate": audio_settings.sample_rate or 24000,
    }


def _build_tts_usage_context(
    *,
    user_bid: str,
    shifu_bid: str,
    audio_bid: str,
    usage_scene: int,
    outline_item_bid: str | None = None,
    progress_record_bid: str | None = None,
    generated_block_bid: str | None = None,
    learning_mode: str = "",
) -> UsageContext:
    kwargs = {
        "user_bid": user_bid,
        "shifu_bid": shifu_bid,
        "audio_bid": audio_bid,
        "usage_scene": usage_scene,
    }
    if outline_item_bid is not None:
        kwargs["outline_item_bid"] = outline_item_bid
    if progress_record_bid is not None:
        kwargs["progress_record_bid"] = progress_record_bid
    if generated_block_bid is not None:
        kwargs["generated_block_bid"] = generated_block_bid
    normalized_learning_mode = str(learning_mode or "").strip().lower()
    if normalized_learning_mode in {"read", "listen", "classroom"}:
        kwargs["learning_mode"] = normalized_learning_mode
    return UsageContext(**kwargs)


def _finalize_tts_stream_audio(
    app: Flask,
    *,
    audio_parts: list[bytes],
    subtitle_cues: list[dict] | None,
    audio_bid: str,
    audio_settings: object,
    voice_settings: object,
    tts_model: str,
    cleaned_text: str,
    segment_count: int,
    persist_audio: bool,
    generated_block_bid: str = "",
    progress_record_bid: str = "",
    user_bid: str = "",
    shifu_bid: str = "",
    position: int | None = None,
) -> tuple[str, int]:
    final_audio = concat_audio_best_effort(audio_parts)
    if not final_audio:
        message = "No audio data produced"
        raise ValueError(message)

    duration_ms = int(get_audio_duration_ms(final_audio, audio_format="mp3") or 0)
    oss_url, bucket_name = upload_audio_to_oss(app, final_audio, audio_bid)

    if persist_audio:
        object_key = f"tts-audio/{audio_bid}.mp3"
        audio_record = build_completed_audio_record(
            audio_bid=audio_bid,
            generated_block_bid=generated_block_bid,
            position=int(position or 0),
            progress_record_bid=progress_record_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            oss_url=oss_url,
            oss_bucket=bucket_name or "",
            oss_object_key=object_key,
            duration_ms=duration_ms,
            file_size=len(final_audio),
            audio_format=audio_settings.format or "mp3",
            sample_rate=audio_settings.sample_rate or 24000,
            voice_settings=voice_settings,
            tts_model=tts_model or "",
            text_length=len(cleaned_text or ""),
            segment_count=segment_count,
            subtitle_cues=subtitle_cues,
        )
        with unit_of_work():
            save_audio_record(audio_record)

    return oss_url, duration_ms


def _yield_with_tts_error_mapping(
    app: Flask,
    *,
    unknown_error_log: str,
    body: object,
) -> Iterator[object]:
    try:
        yield from body()
    except ValueError as exc:
        raise_error_with_args("server.common.paramsError", param_message=str(exc))
    except TTSRpmQueueTimeoutError as exc:
        # The TTS provider's RPM quota is saturated. This is expected
        # backpressure, not a crash: log at WARNING (so it does not page ops as
        # an ERROR) and surface a retryable message instead of a generic
        # unknown error.
        app.logger.warning("%s: %s", unknown_error_log, exc)
        raise_error("server.learn.ttsRateLimited")
    except Exception:
        app.logger.exception(unknown_error_log)
        raise_error("server.common.unknownError")


# --- Per-(user, outline) TTS synthesis concurrency gate --------------------
#
# A client that enters listen mode may fan out block-audio synthesis for a whole
# lesson at once, which can saturate the shared provider RPM gate. This counting
# semaphore caps how many block-audio syntheses a single learner runs in parallel
# for one outline. It mirrors the ask semaphore in runscript_v2 (Redis Lua
# counter, TTL leak-protection, fail-open when Redis is unavailable).

DEFAULT_MAX_PARALLEL_TTS_SYNTH_COUNT = 6
# Leak protection: the counter self-expires this long after the last acquire, in
# case a release is ever missed (the finally block normally releases far sooner).
TTS_SYNTH_SEM_TTL_SECONDS = 300

_LUA_ACQUIRE_TTS_SYNTH_SLOT = """
local key = KEYS[1]
local max_count = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local current = tonumber(redis.call('get', key) or '0')
if current < max_count then
    redis.call('set', key, current + 1, 'EX', ttl)
    return 1
end
return 0
"""

_LUA_RELEASE_TTS_SYNTH_SLOT = """
local key = KEYS[1]
local current = tonumber(redis.call('get', key) or '0')
if current > 0 then
    redis.call('decr', key)
end
return 1
"""


def _get_max_parallel_tts_synth_count(app: Flask) -> int:
    try:
        return int(
            app.config.get(
                "MAX_PARALLEL_TTS_SYNTH_COUNT",
                DEFAULT_MAX_PARALLEL_TTS_SYNTH_COUNT,
            )
        )
    except (TypeError, ValueError):
        return DEFAULT_MAX_PARALLEL_TTS_SYNTH_COUNT


def _get_tts_synth_sem_key(app: Flask, user_bid: str, outline_bid: str) -> str:
    return (
        app.config.get("REDIS_KEY_PREFIX", "")
        + ":tts_synth_sem:"
        + user_bid
        + ":"
        + outline_bid
    )


# Outcomes of a TTS-synthesis slot acquisition.
_TTS_SLOT_ACQUIRED = "acquired"  # a real Redis slot was reserved -> must release
_TTS_SLOT_FULL = "full"  # cap reached -> shed the request
_TTS_SLOT_BYPASS = "bypass"  # limiter inactive -> proceed, nothing to release


def _tts_synth_sem_acquire(app: Flask, user_bid: str, outline_bid: str) -> str:
    """Try to reserve a TTS-synthesis slot.

    Returns one of:
    - ``_TTS_SLOT_ACQUIRED``: a Redis slot was actually reserved; the caller must
      release it.
    - ``_TTS_SLOT_FULL``: the cap is reached; the caller should shed the request.
    - ``_TTS_SLOT_BYPASS``: the limiter is inactive (disabled, incomplete key, or
      Redis unavailable/erroring); proceed without a slot and do NOT release, so a
      fail-open acquire can never decrement a slot it did not reserve.
    """
    max_count = _get_max_parallel_tts_synth_count(app)
    if max_count <= 0 or not user_bid or not outline_bid:
        return _TTS_SLOT_BYPASS
    try:
        from flaskr.dao import get_redis_client

        redis_client = get_redis_client()
        if redis_client is None:
            return _TTS_SLOT_BYPASS  # fail open when Redis is unavailable
        result = redis_client.eval(
            _LUA_ACQUIRE_TTS_SYNTH_SLOT,
            1,
            _get_tts_synth_sem_key(app, user_bid, outline_bid),
            str(max_count),
            str(TTS_SYNTH_SEM_TTL_SECONDS),
        )
        return _TTS_SLOT_ACQUIRED if bool(result) else _TTS_SLOT_FULL
    except Exception as exc:
        app.logger.warning(
            "tts_synth_sem_acquire failed, failing open: user_bid=%s outline_bid=%s error=%s",
            user_bid,
            outline_bid,
            repr(exc),
        )
        return _TTS_SLOT_BYPASS  # fail open


def _tts_synth_sem_release(app: Flask, user_bid: str, outline_bid: str) -> None:
    """Release a TTS-synthesis slot (no-op when the cap is disabled)."""
    if _get_max_parallel_tts_synth_count(app) <= 0 or not user_bid or not outline_bid:
        return
    try:
        from flaskr.dao import get_redis_client

        redis_client = get_redis_client()
        if redis_client is None:
            return
        redis_client.eval(
            _LUA_RELEASE_TTS_SYNTH_SLOT,
            1,
            _get_tts_synth_sem_key(app, user_bid, outline_bid),
        )
    except Exception as exc:
        app.logger.warning(
            "tts_synth_sem_release failed: user_bid=%s outline_bid=%s error=%s",
            user_bid,
            outline_bid,
            repr(exc),
        )


def _yield_tts_synthesis(
    app: Flask,
    *,
    user_bid: str,
    outline_bid: str,
    unknown_error_log: str,
    body: object,
) -> Iterator[object]:
    """Run a TTS synthesis body under a per-(user, outline) concurrency slot.

    Cache-hit paths never reach here, so they do not consume a slot. When the
    per-(user, outline) cap is already full, the request is shed (yields nothing
    and returns) instead of piling onto the shared provider RPM queue; the client
    treats the block as having no audio yet and retries later.
    """
    slot = _tts_synth_sem_acquire(app, user_bid, outline_bid)
    if slot == _TTS_SLOT_FULL:
        app.logger.warning(
            "tts synthesis concurrency limit reached; shedding request | user_bid=%s outline_bid=%s",
            user_bid,
            outline_bid,
        )
        return
    try:
        yield from _yield_with_tts_error_mapping(
            app,
            unknown_error_log=unknown_error_log,
            body=body,
        )
    finally:
        # Only release a slot we actually reserved; a fail-open bypass never
        # incremented the counter, so it must not decrement it.
        if slot == _TTS_SLOT_ACQUIRED:
            _tts_synth_sem_release(app, user_bid, outline_bid)


def _record_stream_segment_usage(
    app: Flask,
    usage_context: UsageContext,
    *,
    provider: str,
    tts_model: str,
    segment_text: str,
    word_count: int,
    usage_characters: int,
    duration_ms: int,
    latency_ms: int,
    parent_usage_bid: str,
    segment_index: int,
    usage_metadata: dict,
) -> None:
    segment_length = len(segment_text or "")
    output_chars = resolve_tts_billable_chars(segment_text, usage_characters)
    record_tts_usage(
        app,
        usage_context,
        provider=provider,
        model=tts_model or "",
        is_stream=True,
        input=segment_length,
        output=output_chars,
        total=output_chars,
        word_count=int(word_count or 0),
        duration_ms=int(duration_ms or 0),
        latency_ms=int(latency_ms or 0),
        record_level=1,
        parent_usage_bid=parent_usage_bid,
        segment_index=segment_index,
        segment_count=0,
        extra=usage_metadata,
    )


def _record_stream_summary_usage(
    app: Flask,
    usage_context: UsageContext,
    *,
    usage_bid: str,
    provider: str,
    tts_model: str,
    raw_text: str,
    cleaned_text: str,
    total_word_count: int,
    total_output_chars: int,
    duration_ms: int,
    segment_count: int,
    usage_metadata: dict,
) -> None:
    raw_length = len(raw_text or "")
    cleaned_length = len(cleaned_text or "")
    output_chars = total_output_chars or cleaned_length
    record_tts_usage(
        app,
        usage_context,
        usage_bid=usage_bid,
        provider=provider,
        model=tts_model or "",
        is_stream=True,
        input=raw_length,
        output=output_chars,
        total=output_chars,
        word_count=total_word_count,
        duration_ms=int(duration_ms or 0),
        latency_ms=0,
        record_level=0,
        parent_usage_bid="",
        segment_index=0,
        segment_count=segment_count,
        extra=usage_metadata,
    )


def _build_audio_segment_message(
    *,
    outline_bid: str,
    generated_block_bid: str,
    segment_index: int,
    audio_data: bytes,
    duration_ms: int,
    position: int | None = None,
    stream_element_number: int | None = None,
    stream_element_type: str | None = None,
    av_contract: dict | None = None,
    subtitle_cues: list[dict] | None = None,
) -> RunMarkdownFlowDTO:
    content_kwargs = {
        "segment_index": segment_index,
        "audio_data": base64.b64encode(audio_data).decode("utf-8"),
        "duration_ms": duration_ms,
        "is_final": False,
    }
    if position is not None:
        content_kwargs["position"] = position
    if stream_element_number is not None:
        content_kwargs["stream_element_number"] = stream_element_number
    if stream_element_type is not None:
        content_kwargs["stream_element_type"] = stream_element_type
    if av_contract is not None:
        content_kwargs["av_contract"] = av_contract
    if subtitle_cues:
        content_kwargs["subtitle_cues"] = normalize_subtitle_cues(subtitle_cues)

    return RunMarkdownFlowDTO(
        outline_bid=outline_bid or "",
        generated_block_bid=generated_block_bid or "",
        type=GeneratedType.AUDIO_SEGMENT,
        content=AudioSegmentDTO(**content_kwargs),
    )


def _build_audio_complete_message(
    *,
    outline_bid: str,
    generated_block_bid: str,
    audio_url: str,
    audio_bid: str,
    duration_ms: int,
    position: int | None = None,
    stream_element_number: int | None = None,
    stream_element_type: str | None = None,
    av_contract: dict | None = None,
    subtitle_cues: list[dict] | None = None,
) -> RunMarkdownFlowDTO:
    content_kwargs = {
        "audio_url": audio_url or "",
        "audio_bid": audio_bid or "",
        "duration_ms": int(duration_ms or 0),
    }
    if position is not None:
        content_kwargs["position"] = position
    if stream_element_number is not None:
        content_kwargs["stream_element_number"] = stream_element_number
    if stream_element_type is not None:
        content_kwargs["stream_element_type"] = stream_element_type
    if av_contract is not None:
        content_kwargs["av_contract"] = av_contract
    if subtitle_cues:
        content_kwargs["subtitle_cues"] = normalize_subtitle_cues(subtitle_cues)

    return RunMarkdownFlowDTO(
        outline_bid=outline_bid or "",
        generated_block_bid=generated_block_bid or "",
        type=GeneratedType.AUDIO_COMPLETE,
        content=AudioCompleteDTO(**content_kwargs),
    )


def _build_tts_done_message(
    *,
    outline_bid: str,
    generated_block_bid: str,
) -> RunMarkdownFlowDTO:
    return RunMarkdownFlowDTO(
        outline_bid=outline_bid or "",
        generated_block_bid=generated_block_bid or "",
        type=GeneratedType.DONE,
        content="",
    )


def _subtitle_cues_from_audio_record(
    audio_record: LearnGeneratedAudio | None,
) -> list[dict]:
    if audio_record is None:
        return []
    return normalize_subtitle_cues(getattr(audio_record, "subtitle_cues", None))


def _audio_record_matches_speakable_text(
    audio_record: LearnGeneratedAudio | None,
    speakable_text: str,
) -> bool:
    if audio_record is None or not getattr(audio_record, "oss_url", ""):
        return False

    cleaned_text = preprocess_for_tts(speakable_text or "")
    expected_length = len(cleaned_text or "")
    if expected_length <= 0:
        return False

    subtitle_cues = _subtitle_cues_from_audio_record(audio_record)
    cue_text = preprocess_for_tts(
        " ".join(str(cue.get("text") or "") for cue in subtitle_cues)
    )
    if cue_text:
        return cue_text == cleaned_text

    record_text_length = int(getattr(audio_record, "text_length", 0) or 0)
    return record_text_length > 0 and record_text_length == expected_length


def _has_speakable_tts_segment(text: str) -> bool:
    """Return whether text still contains speakable content after TTS cleanup."""
    cleaned = preprocess_for_tts(text or "")
    return bool(cleaned and len(cleaned.strip()) >= 2 and has_speakable_text(cleaned))


def _float_settings_match(left: object, right: object) -> bool:
    try:
        return abs(float(left) - float(right)) < 0.0001
    except (TypeError, ValueError):
        return False


def _audio_record_matches_tts_settings(
    audio_record: LearnGeneratedAudio | None,
    *,
    voice_settings: object,
    tts_model: str,
) -> bool:
    if audio_record is None:
        return False

    record_voice_id = (getattr(audio_record, "voice_id", "") or "").strip()
    current_voice_id = (getattr(voice_settings, "voice_id", "") or "").strip()
    if record_voice_id != current_voice_id:
        return False

    record_model = (getattr(audio_record, "model", "") or "").strip()
    current_model = (tts_model or "").strip()
    if record_model != current_model:
        return False

    record_settings = getattr(audio_record, "voice_settings", None)
    if not isinstance(record_settings, dict):
        record_settings = {}

    if not _float_settings_match(
        record_settings.get("speed", 1.0), getattr(voice_settings, "speed", 1.0)
    ):
        return False
    if not _float_settings_match(
        record_settings.get("volume", 1.0), getattr(voice_settings, "volume", 1.0)
    ):
        return False
    if int(record_settings.get("pitch", 0) or 0) != int(
        getattr(voice_settings, "pitch", 0) or 0
    ):
        return False
    return (record_settings.get("emotion", "") or "") == (
        getattr(voice_settings, "emotion", "") or ""
    )


def _yield_stream_tts_audio_segments(
    *,
    app: Flask,
    text: str,
    provider: str,
    tts_model: str,
    voice_settings: object,
    audio_settings: object,
    usage_context: UsageContext,
    parent_usage_bid: str,
    usage_metadata: dict,
    outline_bid: str,
    generated_block_bid: str,
    audio_parts: list[bytes],
    subtitle_cues: list[dict],
    stats: dict,
    position: int | None = None,
    av_contract: dict | None = None,
) -> Iterator[RunMarkdownFlowDTO]:
    for (
        index,
        audio_data,
        duration_ms,
        segment_text,
        word_count,
        usage_characters,
        latency_ms,
    ) in _yield_tts_segments(
        text=text,
        provider=provider,
        tts_model=tts_model,
        voice_settings=voice_settings,
        audio_settings=audio_settings,
    ):
        audio_parts.append(audio_data)
        append_subtitle_cue(
            subtitle_cues,
            text=segment_text,
            duration_ms=int(duration_ms or 0),
            segment_index=index,
            position=int(position or 0),
        )
        stats["segment_count"] = int(stats.get("segment_count", 0)) + 1
        stats["total_word_count"] = int(stats.get("total_word_count", 0)) + int(
            word_count or 0
        )
        segment_output_chars = resolve_tts_billable_chars(
            segment_text,
            int(usage_characters or 0),
        )
        stats["total_output_chars"] = int(stats.get("total_output_chars", 0)) + int(
            segment_output_chars or 0
        )
        _record_stream_segment_usage(
            app,
            usage_context,
            provider=provider,
            tts_model=tts_model,
            segment_text=segment_text,
            word_count=int(word_count or 0),
            usage_characters=int(usage_characters or 0),
            duration_ms=int(duration_ms or 0),
            latency_ms=int(latency_ms or 0),
            parent_usage_bid=parent_usage_bid,
            segment_index=index,
            usage_metadata=usage_metadata,
        )
        yield _build_audio_segment_message(
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
            segment_index=index,
            audio_data=audio_data,
            duration_ms=duration_ms,
            position=position,
            av_contract=av_contract,
            subtitle_cues=subtitle_cues,
        )


def _yield_run_tts_audio_events(
    *,
    app: Flask,
    text: str,
    provider: str,
    tts_model: str,
    voice_settings: object,
    generated_block: LearnGeneratedBlock,
    user_bid: str,
    shifu_bid: str,
    preview_mode: bool,
    position: int | None = None,
    stream_element_number: int | None = None,
    stream_element_type: str | None = None,
    learning_mode: str = "",
) -> Iterator[RunMarkdownFlowDTO]:
    from flaskr.common.config import get_config

    max_segment_chars = get_config("TTS_MAX_SEGMENT_CHARS") or 300
    processor = create_streaming_tts_processor(
        app=app,
        generated_block_bid=generated_block.generated_block_bid or "",
        outline_bid=generated_block.outline_item_bid or "",
        progress_record_bid=generated_block.progress_record_bid or "",
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        position=int(position or 0),
        voice_id=getattr(voice_settings, "voice_id", "") or "",
        speed=getattr(voice_settings, "speed", 1.0),
        pitch=getattr(voice_settings, "pitch", 0),
        emotion=getattr(voice_settings, "emotion", "") or "",
        max_segment_chars=int(max_segment_chars or 300),
        tts_provider=provider,
        tts_model=tts_model,
        stream_element_number=stream_element_number,
        stream_element_type=stream_element_type,
        usage_scene=BILL_USAGE_SCENE_PREVIEW if preview_mode else BILL_USAGE_SCENE_PROD,
        learning_mode=learning_mode,
    )
    emitted_audio_complete = False
    for event in processor.process_chunk(text or ""):
        emitted_audio_complete = emitted_audio_complete or (
            event.type == GeneratedType.AUDIO_COMPLETE
        )
        yield event
    for event in processor.finalize(commit=True):
        emitted_audio_complete = emitted_audio_complete or (
            event.type == GeneratedType.AUDIO_COMPLETE
        )
        yield event
    if not emitted_audio_complete:
        message = "TTS stream finalized without audio_complete"
        raise RuntimeError(message)


def _audio_stream_element_type(element: object) -> str:
    element_type = getattr(element, "element_type", "") or ""
    return str(getattr(element_type, "value", element_type) or "")


@dataclass
class _BlockAudioRequest:
    """Resolved inputs shared by every generated-block audio path."""

    app: Flask
    shifu_bid: str
    generated_block_bid: str
    user_bid: str
    preview_mode: bool
    listen: bool
    generated_block: LearnGeneratedBlock
    raw_text: str
    provider: object
    tts_model: object
    voice_settings: object
    audio_settings: object

    @property
    def outline_bid(self) -> str:
        return self.generated_block.outline_item_bid or ""

    def done_message(self) -> object:
        return _build_tts_done_message(
            outline_bid=self.outline_bid,
            generated_block_bid=self.generated_block_bid,
        )


def _resolve_existing_single_block_audio(
    req: _BlockAudioRequest,
) -> LearnGeneratedAudio | None:
    existing_audios = (
        LearnGeneratedAudio.query.filter(
            LearnGeneratedAudio.generated_block_bid == req.generated_block_bid,
            LearnGeneratedAudio.user_bid == req.user_bid,
            LearnGeneratedAudio.shifu_bid == req.shifu_bid,
            LearnGeneratedAudio.status == AUDIO_STATUS_COMPLETED,
            LearnGeneratedAudio.deleted == 0,
        )
        .order_by(LearnGeneratedAudio.id.desc())
        .all()
    )
    return next(
        (
            audio
            for audio in existing_audios
            if _audio_record_matches_speakable_text(audio, req.raw_text)
            and _audio_record_matches_tts_settings(
                audio,
                voice_settings=req.voice_settings,
                tts_model=req.tts_model,
            )
            and audio.oss_url
        ),
        None,
    )


def _yield_existing_single_block_audio(
    req: _BlockAudioRequest,
    existing_audio: LearnGeneratedAudio,
) -> Iterator[object]:
    yield _build_audio_complete_message(
        outline_bid=req.outline_bid,
        generated_block_bid=req.generated_block_bid,
        audio_url=existing_audio.oss_url,
        audio_bid=existing_audio.audio_bid,
        duration_ms=existing_audio.duration_ms or 0,
        subtitle_cues=_subtitle_cues_from_audio_record(existing_audio),
    )


def _require_speakable_block_text(raw_text: str) -> str:
    cleaned_text = preprocess_for_tts(raw_text)
    if not cleaned_text or len(cleaned_text.strip()) < 2:
        raise_error_with_args(
            "server.common.paramsError",
            param_message="No speakable text available for TTS synthesis",
        )
    return cleaned_text


def _yield_single_block_audio(req: _BlockAudioRequest) -> Iterator[object]:
    _require_speakable_block_text(req.raw_text)

    def _generate_single_audio() -> Iterator[object]:
        yield from _yield_run_tts_audio_events(
            app=req.app,
            text=req.raw_text,
            provider=req.provider,
            tts_model=req.tts_model,
            voice_settings=req.voice_settings,
            generated_block=req.generated_block,
            user_bid=req.user_bid,
            shifu_bid=req.shifu_bid,
            preview_mode=req.preview_mode,
            learning_mode="listen" if req.listen else "read",
        )

    yield from _yield_tts_synthesis(
        req.app,
        user_bid=req.user_bid,
        outline_bid=req.outline_bid,
        unknown_error_log="TTS streaming synthesis failed",
        body=_generate_single_audio,
    )


def _yield_preview_single_block_audio(req: _BlockAudioRequest) -> Iterator[object]:
    app = req.app
    generated_block = req.generated_block
    cleaned_text = _require_speakable_block_text(req.raw_text)

    audio_bid = uuid.uuid4().hex
    usage_context = _build_tts_usage_context(
        user_bid=req.user_bid,
        shifu_bid=req.shifu_bid,
        audio_bid=audio_bid,
        usage_scene=BILL_USAGE_SCENE_PREVIEW,
        outline_item_bid=generated_block.outline_item_bid,
        progress_record_bid=generated_block.progress_record_bid,
        generated_block_bid=generated_block.generated_block_bid,
        learning_mode="listen" if req.listen else "read",
    )
    parent_usage_bid = generate_id(app)
    usage_metadata = _build_tts_usage_metadata(
        voice_settings=req.voice_settings,
        audio_settings=req.audio_settings,
    )
    stats = {"segment_count": 0, "total_word_count": 0}
    audio_parts: list[bytes] = []
    subtitle_cues: list[dict] = []

    def _generate_preview_audio() -> Iterator[object]:
        yield from _yield_stream_tts_audio_segments(
            app=app,
            text=req.raw_text,
            provider=req.provider,
            tts_model=req.tts_model,
            voice_settings=req.voice_settings,
            audio_settings=req.audio_settings,
            usage_context=usage_context,
            parent_usage_bid=parent_usage_bid,
            usage_metadata=usage_metadata,
            outline_bid=generated_block.outline_item_bid or "",
            generated_block_bid=generated_block.generated_block_bid or "",
            audio_parts=audio_parts,
            subtitle_cues=subtitle_cues,
            stats=stats,
        )
        segment_count = int(stats.get("segment_count", 0))
        total_word_count = int(stats.get("total_word_count", 0))
        total_output_chars = int(stats.get("total_output_chars", 0))

        oss_url, duration_ms = _finalize_tts_stream_audio(
            app,
            audio_parts=audio_parts,
            subtitle_cues=subtitle_cues,
            audio_bid=audio_bid,
            audio_settings=req.audio_settings,
            voice_settings=req.voice_settings,
            tts_model=req.tts_model,
            cleaned_text=cleaned_text,
            segment_count=segment_count,
            persist_audio=False,
        )

        _record_stream_summary_usage(
            app,
            usage_context,
            usage_bid=parent_usage_bid,
            provider=req.provider,
            tts_model=req.tts_model,
            raw_text=req.raw_text,
            cleaned_text=cleaned_text,
            total_word_count=total_word_count,
            total_output_chars=total_output_chars,
            duration_ms=int(duration_ms or 0),
            segment_count=segment_count,
            usage_metadata=usage_metadata,
        )

        yield _build_audio_complete_message(
            outline_bid=generated_block.outline_item_bid or "",
            generated_block_bid=generated_block.generated_block_bid or "",
            audio_url=oss_url,
            audio_bid=audio_bid,
            duration_ms=int(duration_ms or 0),
            subtitle_cues=subtitle_cues,
        )

    yield from _yield_tts_synthesis(
        app,
        user_bid=req.user_bid,
        outline_bid=req.outline_bid,
        unknown_error_log="Preview listen fallback TTS synthesis failed",
        body=_generate_preview_audio,
    )


def _yield_listen_block_without_elements(
    req: _BlockAudioRequest,
) -> Iterator[object]:
    """Listen-mode audio for a block that has no speakable final elements."""
    app = req.app
    if req.preview_mode:
        existing_audio = _resolve_existing_single_block_audio(req)
        if existing_audio:
            yield from _yield_existing_single_block_audio(req, existing_audio)
            yield req.done_message()
            return
        yield from _yield_preview_single_block_audio(req)
        yield req.done_message()
        return

    # Non-preview historical blocks may have generated_content but
    # no learn_generated_elements. Fall back to synthesizing audio
    # from the raw block text instead of failing.
    if not _has_speakable_tts_segment(req.raw_text):
        app.logger.info(
            "skip listen-mode TTS for non-speakable generated block | shifu_bid=%s | generated_block_bid=%s | user_bid=%s",
            req.shifu_bid,
            req.generated_block_bid,
            req.user_bid,
        )
        yield req.done_message()
        return

    def _generate_legacy_audio() -> Iterator[object]:
        yield from _yield_run_tts_audio_events(
            app=app,
            text=req.raw_text,
            provider=req.provider,
            tts_model=req.tts_model,
            voice_settings=req.voice_settings,
            generated_block=req.generated_block,
            user_bid=req.user_bid,
            shifu_bid=req.shifu_bid,
            preview_mode=req.preview_mode,
            position=0,
            learning_mode="listen",
        )

    yield from _yield_tts_synthesis(
        app,
        user_bid=req.user_bid,
        outline_bid=req.outline_bid,
        unknown_error_log="Legacy listen TTS synthesis failed",
        body=_generate_legacy_audio,
    )
    yield req.done_message()


def _load_cached_segment_audio(
    req: _BlockAudioRequest,
    speakable_segments: list[str],
) -> dict[int, LearnGeneratedAudio]:
    """Map each segment position to its newest matching completed audio record."""
    expected_segment_count = len(speakable_segments)
    existing_by_position: dict[int, LearnGeneratedAudio] = {}
    existing_records = (
        LearnGeneratedAudio.query.filter(
            LearnGeneratedAudio.generated_block_bid == req.generated_block_bid,
            LearnGeneratedAudio.user_bid == req.user_bid,
            LearnGeneratedAudio.shifu_bid == req.shifu_bid,
            LearnGeneratedAudio.status == AUDIO_STATUS_COMPLETED,
            LearnGeneratedAudio.deleted == 0,
        )
        .order_by(LearnGeneratedAudio.position.asc(), LearnGeneratedAudio.id.desc())
        .all()
    )
    for record in existing_records:
        pos = int(getattr(record, "position", 0) or 0)
        if pos in existing_by_position:
            continue
        if not record.oss_url:
            continue
        if pos < 0 or pos >= expected_segment_count:
            continue
        if not _audio_record_matches_speakable_text(record, speakable_segments[pos]):
            continue
        if not _audio_record_matches_tts_settings(
            record,
            voice_settings=req.voice_settings,
            tts_model=req.tts_model,
        ):
            continue
        existing_by_position[pos] = record
    return existing_by_position


def _cached_segment_audio_message(
    req: _BlockAudioRequest,
    record: LearnGeneratedAudio,
    position: int,
    element: object,
) -> object:
    return _build_audio_complete_message(
        outline_bid=req.outline_bid,
        generated_block_bid=req.generated_block_bid,
        audio_url=record.oss_url,
        audio_bid=record.audio_bid,
        duration_ms=int(record.duration_ms or 0),
        position=position,
        stream_element_number=element.element_index,
        stream_element_type=_audio_stream_element_type(element),
        subtitle_cues=_subtitle_cues_from_audio_record(record),
    )


def _yield_listen_block_audio(req: _BlockAudioRequest) -> Iterator[object]:
    """Listen-mode audio: one segment per speakable final element."""
    from flaskr.service.learn.listen_element_history import (
        get_final_elements_for_generated_block,
    )

    final_elements = get_final_elements_for_generated_block(
        generated_block_bid=req.generated_block_bid,
        user_bid=req.user_bid,
        shifu_bid=req.shifu_bid,
    )
    speakable_elements = get_speakable_text_elements(final_elements)
    speakable_segments = [
        str(element.content_text or "") for element in speakable_elements
    ]
    if not speakable_segments:
        yield from _yield_listen_block_without_elements(req)
        return

    expected_segment_count = len(speakable_segments)
    speakable_positions = [
        pos
        for pos, segment_text in enumerate(speakable_segments)
        if _has_speakable_tts_segment(segment_text)
    ]
    existing_by_position = _load_cached_segment_audio(req, speakable_segments)

    # Skipped non-speakable positions never produce audio records, so
    # the cache fast-path must only require the speakable positions.
    if expected_segment_count and all(
        pos in existing_by_position for pos in speakable_positions
    ):
        for pos in speakable_positions:
            yield _cached_segment_audio_message(
                req, existing_by_position[pos], pos, speakable_elements[pos]
            )
        yield req.done_message()
        return

    def _generate_av_audio() -> Iterator[object]:
        for position, element in enumerate(speakable_elements):
            speakable_text = str(element.content_text or "")
            # Skip before the cache lookup so historical records for
            # non-speakable positions never replay, matching the
            # cache fast-path above.
            if position not in speakable_positions:
                continue

            if position in existing_by_position:
                yield _cached_segment_audio_message(
                    req, existing_by_position[position], position, element
                )
                continue

            yield from _yield_run_tts_audio_events(
                app=req.app,
                text=speakable_text,
                provider=req.provider,
                tts_model=req.tts_model,
                voice_settings=req.voice_settings,
                generated_block=req.generated_block,
                user_bid=req.user_bid,
                shifu_bid=req.shifu_bid,
                preview_mode=req.preview_mode,
                position=position,
                stream_element_number=element.element_index,
                stream_element_type=_audio_stream_element_type(element),
                learning_mode="listen",
            )

    yield from _yield_tts_synthesis(
        req.app,
        user_bid=req.user_bid,
        outline_bid=req.outline_bid,
        unknown_error_log="AV TTS synthesis failed",
        body=_generate_av_audio,
    )
    yield req.done_message()


def stream_generated_block_audio(
    app: Flask,
    *,
    shifu_bid: str,
    generated_block_bid: str,
    user_bid: str,
    preview_mode: bool,
    listen: bool = False,
) -> Iterator[object]:
    """Stream generated block audio."""
    with app.app_context():
        generated_block = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.user_bid == user_bid,
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.generated_block_bid == generated_block_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
        ).first()
        if not generated_block:
            raise_error("server.learn.generatedBlockNotFound")

        raw_text = generated_block.generated_content or ""

        provider, tts_model, voice_settings, _audio_settings = (
            _resolve_shifu_tts_settings(
                app,
                shifu_bid=shifu_bid,
                preview_mode=preview_mode,
            )
        )
        req = _BlockAudioRequest(
            app=app,
            shifu_bid=shifu_bid,
            generated_block_bid=generated_block_bid,
            user_bid=user_bid,
            preview_mode=preview_mode,
            listen=listen,
            generated_block=generated_block,
            raw_text=raw_text,
            provider=provider,
            tts_model=tts_model,
            voice_settings=voice_settings,
            audio_settings=_audio_settings,
        )

        if not listen:
            existing_audio = _resolve_existing_single_block_audio(req)
            if existing_audio:
                yield from _yield_existing_single_block_audio(req, existing_audio)
                return

        if listen:
            yield from _yield_listen_block_audio(req)
            return

        yield from _yield_single_block_audio(req)


def stream_preview_tts_audio(
    app: Flask,
    *,
    shifu_bid: str,
    user_bid: str,
    text: str,
    preview_mode: bool,
) -> Iterator[object]:
    """Stream preview TTS audio."""
    with app.app_context():
        provider, tts_model, voice_settings, audio_settings = (
            _resolve_shifu_tts_settings(
                app,
                shifu_bid=shifu_bid,
                preview_mode=preview_mode,
            )
        )

        cleaned_text = preprocess_for_tts(text or "")
        if not cleaned_text or len(cleaned_text.strip()) < 2:
            raise_error_with_args(
                "server.common.paramsError",
                param_message="No speakable text available for TTS synthesis",
            )

        audio_bid = uuid.uuid4().hex
        usage_scene = (
            BILL_USAGE_SCENE_PREVIEW if preview_mode else BILL_USAGE_SCENE_PROD
        )
        usage_context = _build_tts_usage_context(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            audio_bid=audio_bid,
            usage_scene=usage_scene,
            learning_mode="listen",
        )
        parent_usage_bid = generate_id(app)
        usage_metadata = _build_tts_usage_metadata(
            voice_settings=voice_settings,
            audio_settings=audio_settings,
        )
        stats = {"segment_count": 0, "total_word_count": 0}
        audio_parts: list[bytes] = []
        subtitle_cues: list[dict] = []

        def _generate_preview_audio() -> Iterator[object]:
            yield from _yield_stream_tts_audio_segments(
                app=app,
                text=text or "",
                provider=provider,
                tts_model=tts_model,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                usage_context=usage_context,
                parent_usage_bid=parent_usage_bid,
                usage_metadata=usage_metadata,
                outline_bid="",
                generated_block_bid="",
                audio_parts=audio_parts,
                subtitle_cues=subtitle_cues,
                stats=stats,
            )
            segment_count = int(stats.get("segment_count", 0))
            total_word_count = int(stats.get("total_word_count", 0))
            total_output_chars = int(stats.get("total_output_chars", 0))

            oss_url, duration_ms = _finalize_tts_stream_audio(
                app,
                audio_parts=audio_parts,
                subtitle_cues=subtitle_cues,
                audio_bid=audio_bid,
                audio_settings=audio_settings,
                voice_settings=voice_settings,
                tts_model=tts_model,
                cleaned_text=cleaned_text,
                segment_count=segment_count,
                persist_audio=False,
            )

            _record_stream_summary_usage(
                app,
                usage_context,
                usage_bid=parent_usage_bid,
                provider=provider,
                tts_model=tts_model,
                raw_text=text or "",
                cleaned_text=cleaned_text,
                total_word_count=total_word_count,
                total_output_chars=total_output_chars,
                duration_ms=int(duration_ms or 0),
                segment_count=segment_count,
                usage_metadata=usage_metadata,
            )

            yield _build_audio_complete_message(
                outline_bid="",
                generated_block_bid="",
                audio_url=oss_url,
                audio_bid=audio_bid,
                duration_ms=int(duration_ms or 0),
                subtitle_cues=subtitle_cues,
            )

        yield from _yield_with_tts_error_mapping(
            app,
            unknown_error_log="Preview TTS streaming failed",
            body=_generate_preview_audio,
        )
