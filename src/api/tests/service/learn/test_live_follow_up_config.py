"""Verify server-owned Gemini Live course configuration contracts."""

import pytest
from flaskr.common.config import ENV_VARS
from flaskr.service.learn import live_follow_up_config
from flaskr.service.learn.live_follow_up_config import (
    GEMINI_LIVE_MODEL_ID,
    normalize_live_follow_up_course_config,
    resolve_course_follow_up_model,
)


@pytest.mark.parametrize(
    ("configured", "enabled"),
    [(None, False), (False, False), ("false", False), ("true", True), (True, True)],
)
def test_credential_rotation_defaults_off_and_requires_explicit_enablement(
    monkeypatch: pytest.MonkeyPatch, configured: object, enabled: bool
) -> None:
    assert ENV_VARS["GEMINI_LIVE_ROTATION_ENABLED"].default is False
    monkeypatch.setattr(
        live_follow_up_config, "get_config", lambda *_a, **_k: configured
    )
    assert live_follow_up_config.is_gemini_live_rotation_enabled() is enabled


@pytest.mark.parametrize(
    ("course_model", "outline_models"),
    [
        (GEMINI_LIVE_MODEL_ID, ()),
        ("gpt-text", (GEMINI_LIVE_MODEL_ID,)),
    ],
)
def test_course_contract_rejects_live_in_any_primary_model_field(
    course_model: str,
    outline_models: tuple[str, ...],
) -> None:
    _normalized, error_field = normalize_live_follow_up_course_config(
        course_model=course_model,
        course_follow_up_model="gpt-text",
        provider_config={},
        outline_models=outline_models,
    )

    assert error_field == "model"


@pytest.mark.parametrize(
    ("provider_config", "error_field"),
    [
        (
            {
                "provider": "dify",
                "mode": "provider_only",
                "config": {"live_voice": "Kore"},
            },
            "provider",
        ),
        (
            {
                "provider": "llm",
                "mode": "provider_then_llm",
                "config": {"live_voice": "Kore"},
            },
            "mode",
        ),
        (
            {
                "provider": "llm",
                "mode": "provider_only",
                "config": {"live_voice": "InventedVoice"},
            },
            "live_voice",
        ),
    ],
)
def test_outline_live_follow_up_enforces_course_provider_and_voice(
    provider_config: dict[str, object],
    error_field: str,
) -> None:
    _normalized, actual_error = normalize_live_follow_up_course_config(
        course_model="gpt-main",
        course_follow_up_model="gpt-follow-up",
        provider_config=provider_config,
        outline_follow_up_models=(GEMINI_LIVE_MODEL_ID,),
    )

    assert actual_error == error_field


def test_outline_live_follow_up_defaults_official_voice() -> None:
    normalized, error_field = normalize_live_follow_up_course_config(
        course_model="gpt-main",
        course_follow_up_model="gpt-follow-up",
        provider_config={},
        outline_follow_up_models=(GEMINI_LIVE_MODEL_ID,),
    )

    assert error_field is None
    assert normalized == {
        "provider": "llm",
        "mode": "provider_only",
        "config": {"live_voice": "Kore"},
    }


def test_live_primary_never_becomes_implicit_follow_up_model() -> None:
    assert resolve_course_follow_up_model(GEMINI_LIVE_MODEL_ID, "") == ""
    assert (
        resolve_course_follow_up_model(GEMINI_LIVE_MODEL_ID, "gpt-follow-up")
        == "gpt-follow-up"
    )
    assert resolve_course_follow_up_model("gpt-main", "") == "gpt-main"
