"""Stable Gemini Live follow-up model and voice contracts."""

from __future__ import annotations

import json
from itertools import chain
from typing import Literal

from flaskr.service.config import get_config

GEMINI_LIVE_MODEL_ID = "gemini-3.1-flash-live-preview"
GEMINI_LIVE_MODEL_ALLOWLIST = frozenset({GEMINI_LIVE_MODEL_ID})
DEFAULT_GEMINI_LIVE_VOICE = "Kore"

# Google documents these identifiers as the 30 prebuilt voiceName values
# supported by native-audio models. Keep the provider identifiers stable; the
# frontend may localize the accompanying style labels independently.
GEMINI_LIVE_VOICE_STYLES: tuple[tuple[str, str], ...] = (
    ("Zephyr", "Bright"),
    ("Puck", "Upbeat"),
    ("Charon", "Informative"),
    ("Kore", "Firm"),
    ("Fenrir", "Excitable"),
    ("Leda", "Youthful"),
    ("Orus", "Firm"),
    ("Aoede", "Breezy"),
    ("Callirrhoe", "Easy-going"),
    ("Autonoe", "Bright"),
    ("Enceladus", "Breathy"),
    ("Iapetus", "Clear"),
    ("Umbriel", "Easy-going"),
    ("Algieba", "Smooth"),
    ("Despina", "Smooth"),
    ("Erinome", "Clear"),
    ("Algenib", "Gravelly"),
    ("Rasalgethi", "Informative"),
    ("Laomedeia", "Upbeat"),
    ("Achernar", "Soft"),
    ("Alnilam", "Firm"),
    ("Schedar", "Even"),
    ("Gacrux", "Mature"),
    ("Pulcherrima", "Forward"),
    ("Achird", "Friendly"),
    ("Zubenelgenubi", "Casual"),
    ("Vindemiatrix", "Gentle"),
    ("Sadachbia", "Lively"),
    ("Sadaltager", "Knowledgeable"),
    ("Sulafat", "Warm"),
)
GEMINI_LIVE_VOICE_IDS = frozenset(
    voice_id for voice_id, _style in GEMINI_LIVE_VOICE_STYLES
)

FollowUpInteractionMode = Literal["text", "live_voice"]


def _config_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_gemini_live_enabled() -> bool:
    """Return whether the global Gemini Live kill switch is enabled."""
    return _config_bool(get_config("GEMINI_LIVE_ENABLED", default=False))


def is_gemini_live_rotation_enabled() -> bool:
    """Allow bounded early credential replacement only after explicit rollout."""
    return _config_bool(get_config("GEMINI_LIVE_ROTATION_ENABLED", default=False))


def is_live_follow_up_model(model: object) -> bool:
    """Match a model against the server-owned Live allowlist."""
    return str(model or "").strip() in GEMINI_LIVE_MODEL_ALLOWLIST


def get_follow_up_interaction_mode(model: object) -> FollowUpInteractionMode:
    """Resolve the backend-owned interaction mode for a configured model."""
    return "live_voice" if is_live_follow_up_model(model) else "text"


def resolve_course_follow_up_model(
    primary_model: object,
    follow_up_model: object,
) -> str:
    """Resolve the course fallback without treating a Live primary as valid.

    Text courses historically use their primary model when no dedicated
    follow-up model is configured. Live models are follow-up-only, so a
    malformed legacy primary value must not silently activate Live voice.
    """
    normalized_follow_up = str(follow_up_model or "").strip()
    if normalized_follow_up:
        return normalized_follow_up
    normalized_primary = str(primary_model or "").strip()
    return "" if is_live_follow_up_model(normalized_primary) else normalized_primary


def is_valid_live_voice(voice_id: object) -> bool:
    """Validate an exact provider voiceName identifier."""
    return str(voice_id or "").strip() in GEMINI_LIVE_VOICE_IDS


def get_gemini_live_voice_options() -> list[dict[str, str]]:
    """Return JSON-ready voice metadata in the documented provider order."""
    return [
        {"voice_id": voice_id, "style": style}
        for voice_id, style in GEMINI_LIVE_VOICE_STYLES
    ]


def normalize_live_follow_up_provider_config(
    model: object,
    provider_config: object,
) -> tuple[dict[str, object], str | None]:
    """Normalize and validate the provider contract for a follow-up model.

    The returned error field is suitable for a bounded parameter error. Live
    sessions are deliberately restricted to the built-in LLM in provider-only
    mode; external workflows and knowledge providers cannot proxy Live audio.
    """
    parsed: dict[str, object] = {}
    if isinstance(provider_config, dict):
        parsed = provider_config
    elif isinstance(provider_config, str) and provider_config.strip():
        try:
            loaded = json.loads(provider_config)
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            parsed = loaded
    provider = str(parsed.get("provider") or "llm").strip().lower()
    mode = str(parsed.get("mode") or "provider_only").strip().lower()
    raw_config = parsed.get("config")
    config = dict(raw_config) if isinstance(raw_config, dict) else {}

    voice_value = config.get("live_voice")
    normalized_voice = str(voice_value or "").strip()
    if normalized_voice and normalized_voice not in GEMINI_LIVE_VOICE_IDS:
        return {
            "provider": provider,
            "mode": mode,
            "config": config,
        }, "live_voice"

    if is_live_follow_up_model(model):
        if provider != "llm":
            return {
                "provider": provider,
                "mode": mode,
                "config": config,
            }, "provider"
        if mode != "provider_only":
            return {
                "provider": provider,
                "mode": mode,
                "config": config,
            }, "mode"
        config["live_voice"] = normalized_voice or DEFAULT_GEMINI_LIVE_VOICE
    elif normalized_voice:
        # Preserve a valid teacher selection when switching temporarily back to
        # a text follow-up model.
        config["live_voice"] = normalized_voice

    return {
        "provider": provider,
        "mode": mode,
        "config": config,
    }, None


def normalize_live_follow_up_course_config(
    *,
    course_model: object,
    course_follow_up_model: object,
    provider_config: object,
    outline_models: tuple[object, ...] = (),
    outline_follow_up_models: tuple[object, ...] = (),
) -> tuple[dict[str, object], str | None]:
    """Validate every model-bearing field in an imported or copied course.

    Live is valid only in follow-up model fields. If any course or outline
    follow-up selects Live, the single course-level provider configuration must
    satisfy the built-in ``llm + provider_only`` and official voice contract.
    """
    primary_models = chain((course_model,), outline_models)
    has_live_primary = any(is_live_follow_up_model(model) for model in primary_models)
    follow_up_models = tuple(chain((course_follow_up_model,), outline_follow_up_models))
    validation_model = (
        GEMINI_LIVE_MODEL_ID
        if any(is_live_follow_up_model(model) for model in follow_up_models)
        else course_follow_up_model
    )
    normalized, error_field = normalize_live_follow_up_provider_config(
        validation_model,
        provider_config,
    )
    if has_live_primary:
        return normalized, "model"
    return normalized, error_field
