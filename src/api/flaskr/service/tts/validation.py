from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import Flask

from flaskr.api.tts import get_tts_provider
from flaskr.service.common.models import raise_error_with_args
from flaskr.service.tts.minimax_voice_clone import is_valid_minimax_custom_voice_id
from flaskr.service.tts.models import (
    TTSMiniMaxClonedVoice,
    TTS_MINIMAX_CLONE_STATUS_READY,
)


SUPPORTED_TTS_PROVIDERS = {
    "minimax",
    "volcengine",
    "volcengine_http",
    "baidu",
    "aliyun",
    "tencent",
}
PROVIDERS_REQUIRING_MODEL = {"minimax", "volcengine"}


@dataclass(frozen=True)
class StrictTTSSettings:
    provider: str
    model: str
    voice_id: str
    speed: float
    pitch: int
    emotion: str


def _raise_param_error(message: str) -> None:
    raise_error_with_args("server.common.paramsError", param_message=message)


def _to_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        _raise_param_error(f"Invalid {field_name}: {value!r}")


def _to_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        _raise_param_error(f"Invalid {field_name}: {value!r}")


def validate_tts_settings_strict(
    *,
    provider: str,
    model: str,
    voice_id: str,
    speed: Any,
    pitch: Any,
    emotion: str,
) -> StrictTTSSettings:
    """
    Validate strict, DB-driven TTS settings.

    Notes:
    - Provider, voice_id, speed, and pitch must be explicit (no "system default").
    - `model` is required for providers that expose model/resource selection.
    """
    normalized_provider = (provider or "").strip().lower()
    if not normalized_provider:
        _raise_param_error("TTS provider is required when TTS is enabled")
    if normalized_provider not in SUPPORTED_TTS_PROVIDERS:
        _raise_param_error(f"Unsupported TTS provider: {normalized_provider}")

    normalized_voice_id = (voice_id or "").strip()
    if not normalized_voice_id:
        _raise_param_error("TTS voice_id is required when TTS is enabled")

    normalized_model = (model or "").strip()
    if normalized_provider in PROVIDERS_REQUIRING_MODEL and not normalized_model:
        _raise_param_error(
            f"TTS model is required for provider '{normalized_provider}'"
        )

    speed_value = _to_float(speed, "tts_speed")
    pitch_value = _to_int(pitch, "tts_pitch")
    emotion_value = (emotion or "").strip()

    provider_instance = get_tts_provider(normalized_provider)
    cfg = provider_instance.get_provider_config()

    # Validate ranges
    if speed_value < float(cfg.speed.min) or speed_value > float(cfg.speed.max):
        _raise_param_error(
            f"TTS speed out of range for provider '{normalized_provider}': "
            f"{speed_value} (expected {cfg.speed.min}-{cfg.speed.max})"
        )
    if pitch_value < int(cfg.pitch.min) or pitch_value > int(cfg.pitch.max):
        _raise_param_error(
            f"TTS pitch out of range for provider '{normalized_provider}': "
            f"{pitch_value} (expected {cfg.pitch.min}-{cfg.pitch.max})"
        )

    # Validate selectable values (if provider exposes them to frontend)
    allowed_voices = {
        (v.get("value") or "").strip()
        for v in (cfg.voices or [])
        if (v.get("value") or "").strip()
    }
    if allowed_voices and normalized_voice_id not in allowed_voices:
        if normalized_provider == "minimax" and is_valid_minimax_custom_voice_id(
            normalized_voice_id
        ):
            pass
        else:
            _raise_param_error(
                f"Invalid TTS voice_id for provider '{normalized_provider}': {normalized_voice_id}"
            )

    if cfg.models:
        allowed_models = {
            (m.get("value") or "").strip()
            for m in (cfg.models or [])
            if (m.get("value") or "").strip()
        }
        if (
            normalized_provider in PROVIDERS_REQUIRING_MODEL
            and normalized_model not in allowed_models
        ):
            _raise_param_error(
                f"Invalid TTS model for provider '{normalized_provider}': {normalized_model}"
            )

    if cfg.supports_emotion:
        allowed_emotions = {
            (e.get("value") or "").strip()
            for e in (cfg.emotions or [])
            if e.get("value") is not None
        }
        if emotion_value and allowed_emotions and emotion_value not in allowed_emotions:
            _raise_param_error(
                f"Invalid TTS emotion for provider '{normalized_provider}': {emotion_value}"
            )
    elif emotion_value:
        _raise_param_error(
            f"TTS emotion is not supported for provider '{normalized_provider}'"
        )

    # Volcengine: enforce resource-id consistency between model and voice.
    if normalized_provider == "volcengine":
        voice_resource_id = ""
        for voice in cfg.voices or []:
            if (voice.get("value") or "").strip() == normalized_voice_id:
                voice_resource_id = (voice.get("resource_id") or "").strip()
                break
        if voice_resource_id and normalized_model != voice_resource_id:
            _raise_param_error(
                "Volcengine TTS model must match voice resource_id: "
                f"{voice_resource_id}"
            )

    return StrictTTSSettings(
        provider=normalized_provider,
        model=normalized_model,
        voice_id=normalized_voice_id,
        speed=speed_value,
        pitch=pitch_value,
        emotion=emotion_value,
    )


def assert_minimax_preview_voice_available(
    app: Flask, *, voice_id: str, owner_user_bid: str
) -> None:
    """Reject a MiniMax preview voice id that would fail at the provider.

    Built-in MiniMax voices are always allowed. A custom (clone) voice id shares
    the same character shape as built-in ids, so it passes local format
    validation even when it was never created, has failed, or belongs to another
    account. Such an id only surfaces as ``2054 - voice id not exist`` after the
    external call, aborting the preview stream. Fail fast instead: accept a
    custom id only when a ready, non-deleted clone row exists and belongs to the
    requesting creator.
    """
    normalized_voice_id = (voice_id or "").strip()
    if not normalized_voice_id:
        _raise_param_error("TTS voice_id is required when TTS is enabled")

    provider_config = get_tts_provider("minimax").get_provider_config()
    built_in_voice_ids = {
        (voice.get("value") or "").strip()
        for voice in (provider_config.voices or [])
        if (voice.get("value") or "").strip()
    }
    if normalized_voice_id in built_in_voice_ids:
        return

    # Custom clone voices are private per creator. Always scope the lookup by the
    # requesting owner so an empty/whitespace owner cannot bypass the filter and
    # preview another creator's clone. An empty owner therefore matches nothing
    # and is rejected below, exactly like an unknown voice.
    normalized_owner = (owner_user_bid or "").strip()
    ready_clone = None
    if normalized_owner:
        with app.app_context():
            ready_clone = (
                TTSMiniMaxClonedVoice.query.filter(
                    TTSMiniMaxClonedVoice.voice_id == normalized_voice_id,
                    TTSMiniMaxClonedVoice.status == TTS_MINIMAX_CLONE_STATUS_READY,
                    TTSMiniMaxClonedVoice.deleted == 0,
                    TTSMiniMaxClonedVoice.owner_user_bid == normalized_owner,
                )
                .order_by(TTSMiniMaxClonedVoice.id.desc())
                .first()
            )

    if ready_clone is None:
        app.logger.warning(
            "Rejecting MiniMax preview voice_id %s for owner %s: "
            "no ready cloned voice found",
            normalized_voice_id,
            normalized_owner or "-",
        )
        _raise_param_error(f"TTS voice is not available: {normalized_voice_id}")
