"""Shared request validation for profile-research run endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from flaskr.service.common.models import raise_param_error

_PROFILE_RESEARCH_SESSION_ID_LENGTH = 32
_PROFILE_RESEARCH_SESSION_ID_ALPHABET = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class ProfileResearchRunRequest:
    """Validated input for one learner or operator runtime step."""

    user_input: dict[str, list[str]] | None
    expected_block_index: int | None
    request_id: str | None


def normalize_profile_research_session_id(value: object) -> str:
    """Return a normalized runtime session ID or raise a parameter error."""
    if not isinstance(value, str) or not value.strip():
        raise_param_error("session_id")
    normalized = value.strip()
    if len(normalized) != _PROFILE_RESEARCH_SESSION_ID_LENGTH:
        raise_param_error("session_id")
    if not set(normalized).issubset(_PROFILE_RESEARCH_SESSION_ID_ALPHABET):
        raise_param_error("session_id")
    return normalized


def profile_research_user_input(
    payload: dict, *, parameter_name: str
) -> dict[str, list[str]] | None:
    """Validate the transport shape while preserving submitted string values."""
    if "user_input" not in payload:
        return None
    raw_user_input = payload["user_input"]
    if not isinstance(raw_user_input, dict):
        raise_param_error(parameter_name)
    normalized: dict[str, list[str]] = {}
    for raw_key, raw_values in raw_user_input.items():
        if (
            not isinstance(raw_key, str)
            or not raw_key.strip()
            or not isinstance(raw_values, list)
            or not raw_values
            or any(not isinstance(value, str) for value in raw_values)
        ):
            raise_param_error(parameter_name)
        normalized[raw_key] = list(raw_values)
    return normalized or None


def profile_research_run_identity(
    payload: dict, *, parameter_name: str
) -> tuple[int | None, str | None]:
    """Validate the paired cursor and idempotency identity for one run."""
    has_expected_block_index = "expected_block_index" in payload
    has_request_id = "request_id" in payload
    if has_expected_block_index != has_request_id:
        raise_param_error(parameter_name)
    if not has_expected_block_index:
        return None, None

    expected_block_index = payload["expected_block_index"]
    request_id = payload["request_id"]
    if (
        isinstance(expected_block_index, bool)
        or not isinstance(expected_block_index, int)
        or expected_block_index < 0
    ):
        raise_param_error("expected_block_index")
    if (
        not isinstance(request_id, str)
        or not request_id.strip()
        or len(request_id.strip()) > 128
    ):
        raise_param_error("request_id")
    return expected_block_index, request_id.strip()


def parse_profile_research_run_request(
    payload: dict, *, parameter_name: str
) -> ProfileResearchRunRequest:
    """Validate one complete run envelope with caller-specific error naming."""
    if set(payload) - {"user_input", "expected_block_index", "request_id"}:
        raise_param_error(parameter_name)
    user_input = profile_research_user_input(
        payload,
        parameter_name=parameter_name,
    )
    expected_block_index, request_id = profile_research_run_identity(
        payload,
        parameter_name=parameter_name,
    )
    return ProfileResearchRunRequest(
        user_input=user_input,
        expected_block_index=expected_block_index,
        request_id=request_id,
    )
