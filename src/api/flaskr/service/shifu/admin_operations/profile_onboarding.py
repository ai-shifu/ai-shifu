from __future__ import annotations

from typing import Any

from flask import Flask
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.profile_onboarding import (
    build_profile_onboarding_config_payload,
    get_profile_onboarding_config,
    update_profile_onboarding_config,
    validate_profile_onboarding_config_payload_size,
)


def get_operator_profile_onboarding_config(app: Flask) -> dict[str, Any]:
    return get_profile_onboarding_config()


def update_operator_profile_onboarding_config(
    app: Flask,
    *,
    payload: dict[str, Any],
    operator_user_bid: str,
) -> dict[str, Any]:
    return update_profile_onboarding_config(
        app,
        payload=payload,
        operator_user_bid=operator_user_bid,
    )


def create_operator_profile_onboarding_preview_session(
    app: Flask,
    *,
    operator_user_bid: str,
    markdownflow: str,
    document_prompt: str,
    config_revision: int,
    output_language: str,
) -> dict[str, Any]:
    """Create a course-neutral preview from the unsaved editor draft."""
    # Preview does not send the unsaved enabled switch. False serializes one
    # byte larger than true, so it safely represents either next saved value.
    preview_payload = build_profile_onboarding_config_payload(
        enabled=False,
        markdownflow=markdownflow,
        document_prompt=document_prompt,
        revision=int(config_revision) + 1,
        updated_by=operator_user_bid or "system",
    )
    validate_profile_onboarding_config_payload_size(preview_payload)

    from flaskr.service.profile_research.api import (
        PROFILE_ONBOARDING_PREVIEW_PURPOSE,
        ProfileResearchSessionBusy,
        ProfileResearchValidationError,
        start_profile_research_session,
    )

    try:
        return start_profile_research_session(
            app,
            user_bid=operator_user_bid,
            document=markdownflow,
            document_prompt=document_prompt,
            purpose=PROFILE_ONBOARDING_PREVIEW_PURPOSE,
            config_revision=config_revision,
            output_language=output_language,
        )
    except ProfileResearchSessionBusy:
        raise_error("server.profile.profileOnboardingBusy")
    except ProfileResearchValidationError:
        raise_param_error("markdownflow")


def stream_operator_profile_onboarding_preview_session(
    app: Flask,
    *,
    operator_user_bid: str,
    session_id: str,
    user_input: dict[str, list[str]] | None,
    expected_block_index: int | None = None,
    request_id: str | None = None,
):
    """Run one cursor step while enforcing owner and preview-purpose scope."""
    from flaskr.service.profile_research.api import (
        PROFILE_ONBOARDING_PREVIEW_PURPOSE,
        stream_profile_research_session,
    )

    return stream_profile_research_session(
        app,
        user_bid=operator_user_bid,
        session_id=session_id,
        user_input=user_input,
        expected_purpose=PROFILE_ONBOARDING_PREVIEW_PURPOSE,
        expected_block_index=expected_block_index,
        request_id=request_id,
    )
