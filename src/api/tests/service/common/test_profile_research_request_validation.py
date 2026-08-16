from __future__ import annotations

import pytest
from flaskr.service.common import profile_research_request_validation
from flaskr.service.common.models import AppException
from flaskr.service.common.profile_research_request_validation import (
    normalize_profile_research_session_id,
    profile_research_run_identity,
    profile_research_user_input,
)

_SESSION_ID = "0123456789abcdef0123456789abcdef"


def test_session_id_normalization_accepts_only_trimmed_lowercase_hex():
    assert normalize_profile_research_session_id(f"  {_SESSION_ID}  ") == _SESSION_ID

    for invalid in (None, False, "too-short", "G" * 32, "0" * 31):
        with pytest.raises(AppException):
            normalize_profile_research_session_id(invalid)


def test_user_input_validation_preserves_runtime_values():
    payload = {
        "user_input": {
            " preferred_style ": [" brief ", "full"],
        }
    }

    result = profile_research_user_input(payload, parameter_name="user_input")

    assert result == {" preferred_style ": [" brief ", "full"]}
    assert result is not payload["user_input"]
    assert profile_research_user_input({}, parameter_name="user_input") is None
    assert (
        profile_research_user_input({"user_input": {}}, parameter_name="user_input")
        is None
    )


@pytest.mark.parametrize(
    "raw_user_input",
    [
        "not-an-object",
        {"": ["answer"]},
        {"answer": "not-a-list"},
        {"answer": []},
        {"answer": [1]},
    ],
)
def test_user_input_validation_rejects_invalid_transport_shapes(raw_user_input):
    with pytest.raises(AppException):
        profile_research_user_input(
            {"user_input": raw_user_input},
            parameter_name="profile_onboarding_preview",
        )


def test_run_identity_normalizes_the_paired_cursor_and_request_id():
    assert profile_research_run_identity(
        {
            "expected_block_index": 2,
            "request_id": "  request-2  ",
        },
        parameter_name="profile_onboarding_session",
    ) == (2, "request-2")
    assert profile_research_run_identity(
        {}, parameter_name="profile_onboarding_session"
    ) == (None, None)
    assert profile_research_run_identity(
        {
            "expected_block_index": 0,
            "request_id": "r" * 128,
        },
        parameter_name="profile_onboarding_session",
    ) == (0, "r" * 128)


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_block_index": True, "request_id": "request"},
        {"expected_block_index": -1, "request_id": "request"},
        {"expected_block_index": 0, "request_id": " "},
        {"expected_block_index": 0, "request_id": "r" * 129},
    ],
)
def test_run_identity_rejects_invalid_cursor_or_request_id(payload):
    with pytest.raises(AppException):
        profile_research_run_identity(
            payload,
            parameter_name="profile_onboarding_session",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_block_index": 0},
        {"request_id": "request-without-index"},
    ],
)
def test_run_identity_uses_the_callers_envelope_for_unpaired_fields(
    monkeypatch, payload
):
    rejected_parameters: list[str] = []

    def reject(parameter_name: str) -> None:
        rejected_parameters.append(parameter_name)
        raise ValueError(parameter_name)

    monkeypatch.setattr(
        profile_research_request_validation,
        "raise_param_error",
        reject,
    )

    with pytest.raises(ValueError, match="profile_onboarding_preview"):
        profile_research_run_identity(
            payload,
            parameter_name="profile_onboarding_preview",
        )

    assert rejected_parameters == ["profile_onboarding_preview"]
