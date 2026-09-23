"""Validate low-cardinality attribution supplied by AI Shifu Skills."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from flaskr.service.common.models import raise_param_error

ALLOWED_HOST_PLATFORMS = frozenset(
    {"workbuddy", "doubao", "qclaw", "lobster", "codex", "direct"}
)
ALLOWED_SKILL_IDS = frozenset({"ai-shifu-course-creator"})
_REQUIRED_KEYS = frozenset({"host_platform", "skill_id", "skill_version", "handoff_id"})
ALLOWED_SKILL_EVENT_NAMES = frozenset(
    {
        "authorization_completed",
        "course_creation_started",
        "course_creation_completed",
        "course_import_started",
        "course_import_completed",
        "course_publish_started",
        "course_publish_completed",
    }
)


@dataclass(frozen=True)
class SkillAttributionInput:
    """Validated immutable attribution for one Skill handoff."""

    host_platform: str
    skill_id: str
    skill_version: str
    handoff_id: str


@dataclass(frozen=True)
class SkillIdentityInput:
    """Validated low-cardinality Skill identity attached to a journey event."""

    host_platform: str
    skill_id: str
    skill_version: str


def parse_skill_attribution(
    value: object, *, field_name: str
) -> SkillAttributionInput | None:
    """Validate an optional attribution payload without accepting free dimensions."""
    if value is None:
        return None
    if not isinstance(value, dict) or frozenset(value) != _REQUIRED_KEYS:
        raise_param_error(field_name)

    host_platform = value.get("host_platform")
    skill_id = value.get("skill_id")
    skill_version = value.get("skill_version")
    handoff_id = value.get("handoff_id")
    if host_platform not in ALLOWED_HOST_PLATFORMS:
        raise_param_error(f"{field_name}.host_platform")
    if skill_id not in ALLOWED_SKILL_IDS:
        raise_param_error(f"{field_name}.skill_id")
    if not isinstance(skill_version, str) or not skill_version.strip():
        raise_param_error(f"{field_name}.skill_version")
    if len(skill_version) > 32:
        raise_param_error(f"{field_name}.skill_version")
    if not isinstance(handoff_id, str):
        raise_param_error(f"{field_name}.handoff_id")
    try:
        canonical_handoff_id = str(UUID(handoff_id))
    except (AttributeError, TypeError, ValueError):
        raise_param_error(f"{field_name}.handoff_id")
    if handoff_id != canonical_handoff_id:
        raise_param_error(f"{field_name}.handoff_id")

    return SkillAttributionInput(
        host_platform=host_platform,
        skill_id=skill_id,
        skill_version=skill_version.strip(),
        handoff_id=canonical_handoff_id,
    )


def parse_skill_identity(value: object, *, field_name: str) -> SkillIdentityInput:
    """Validate the shared platform, Skill and version event dimensions."""
    if not isinstance(value, dict):
        raise_param_error(field_name)
    host_platform = value.get("host_platform")
    skill_id = value.get("skill_id")
    skill_version = value.get("skill_version")
    if host_platform not in ALLOWED_HOST_PLATFORMS:
        raise_param_error(f"{field_name}.host_platform")
    if skill_id not in ALLOWED_SKILL_IDS:
        raise_param_error(f"{field_name}.skill_id")
    if not isinstance(skill_version, str) or not skill_version.strip():
        raise_param_error(f"{field_name}.skill_version")
    normalized_version = skill_version.strip()
    if len(normalized_version) > 32:
        raise_param_error(f"{field_name}.skill_version")
    return SkillIdentityInput(
        host_platform=host_platform,
        skill_id=skill_id,
        skill_version=normalized_version,
    )
