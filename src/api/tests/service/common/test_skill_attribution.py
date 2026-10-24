"""Verify strict, low-cardinality Skill attribution parsing."""

import pytest
from flaskr.service.common.models import AppError
from flaskr.service.common.skill_attribution import (
    parse_skill_attribution,
    parse_skill_identity,
)


@pytest.mark.parametrize(
    "host_platform",
    ["workbuddy", "doubao", "qclaw", "lobster", "codex", "direct"],
)
def test_attribution_accepts_allowlisted_canonical_values(
    host_platform: str,
) -> None:
    parsed = parse_skill_attribution(
        {
            "host_platform": host_platform,
            "skill_id": "ai-shifu-course-creator",
            "skill_version": "1.2.3",
            "handoff_id": "123e4567-e89b-12d3-a456-426614174000",
        },
        field_name="registration_attribution",
    )

    assert parsed is not None
    assert parsed.host_platform == host_platform
    assert parsed.skill_version == "1.2.3"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host_platform", "unknown"),
        ("skill_id", "untrusted-skill"),
        ("skill_version", ""),
        ("handoff_id", "not-a-uuid"),
    ],
)
def test_attribution_rejects_unbounded_or_invalid_dimensions(
    field: str, value: str
) -> None:
    payload = {
        "host_platform": "direct",
        "skill_id": "ai-shifu-course-creator",
        "skill_version": "1.0.0",
        "handoff_id": "123e4567-e89b-12d3-a456-426614174000",
    }
    payload[field] = value

    with pytest.raises(AppError):
        parse_skill_attribution(payload, field_name="registration_attribution")


def test_event_identity_does_not_accept_unknown_platform() -> None:
    with pytest.raises(AppError):
        parse_skill_identity(
            {
                "host_platform": "free-form-value",
                "skill_id": "ai-shifu-course-creator",
                "skill_version": "1.0.0",
            },
            field_name="event",
        )
