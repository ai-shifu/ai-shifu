"""Define constants for usage metering."""

from __future__ import annotations

from flaskr.i18n import _

# Use 4-digit numeric codes starting with "1" to distinguish from legacy enums.
BILL_USAGE_TYPE_LLM = 1101
BILL_USAGE_TYPE_TTS = 1102

BILL_USAGE_SCENE_DEBUG = 1201
BILL_USAGE_SCENE_PREVIEW = 1202
BILL_USAGE_SCENE_PROD = 1203

BILL_USAGE_TYPE_DICT = {
    _("server.metering.usageTypeLlm"): BILL_USAGE_TYPE_LLM,
    _("server.metering.usageTypeTts"): BILL_USAGE_TYPE_TTS,
}

BILL_USAGE_SCENE_DICT = {
    _("server.metering.usageSceneDebug"): BILL_USAGE_SCENE_DEBUG,
    _("server.metering.usageScenePreview"): BILL_USAGE_SCENE_PREVIEW,
    _("server.metering.usageSceneProduction"): BILL_USAGE_SCENE_PROD,
}

_LEGACY_USAGE_TYPE_MAP = {
    1: BILL_USAGE_TYPE_LLM,
    2: BILL_USAGE_TYPE_TTS,
}

_LEGACY_USAGE_SCENE_MAP = {
    0: BILL_USAGE_SCENE_DEBUG,
    1: BILL_USAGE_SCENE_PREVIEW,
    2: BILL_USAGE_SCENE_PROD,
}


def normalize_usage_type(
    value: object, *, default: int = BILL_USAGE_TYPE_LLM, strict: bool = False
) -> int:
    """Normalize usage type."""
    if value is None or value == "":
        if strict:
            message = "usage_type is required"
            raise ValueError(message)
        return default
    try:
        numeric_value = int(value)
    except (TypeError, ValueError):
        numeric_value = None
    if numeric_value in (BILL_USAGE_TYPE_LLM, BILL_USAGE_TYPE_TTS):
        return int(numeric_value)
    if numeric_value in _LEGACY_USAGE_TYPE_MAP:
        return _LEGACY_USAGE_TYPE_MAP[numeric_value]
    if strict:
        message = "usage_type is invalid"
        raise ValueError(message)
    return default


def normalize_usage_scene(
    value: object, *, default: int = BILL_USAGE_SCENE_PROD, strict: bool = False
) -> int:
    """Normalize usage scene."""
    if value is None or value == "":
        if strict:
            message = "usage_scene is required"
            raise ValueError(message)
        return default
    try:
        numeric_value = int(value)
    except (TypeError, ValueError):
        numeric_value = None
    if numeric_value in (
        BILL_USAGE_SCENE_DEBUG,
        BILL_USAGE_SCENE_PREVIEW,
        BILL_USAGE_SCENE_PROD,
    ):
        return int(numeric_value)
    if numeric_value in _LEGACY_USAGE_SCENE_MAP:
        return _LEGACY_USAGE_SCENE_MAP[numeric_value]
    if strict:
        message = "usage_scene is invalid"
        raise ValueError(message)
    return default
