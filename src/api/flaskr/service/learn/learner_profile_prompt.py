"""Compose the learner profile into the effective course prompt.

The learner profile is user-authored data. It remains subordinate to every
course instruction and is only attached when a course prompt already exists.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Protocol

from flaskr.util.prompt_loader import load_prompt_template


class _LearnerWithProfile(Protocol):
    learner_profile: str | None


LEARNER_PROFILE_PROMPT_MARKER = "<!-- ai-shifu:learner-profile:v1 -->"


@lru_cache(maxsize=1)
def _learner_profile_context_template() -> str:
    return load_prompt_template("learner_profile_context").strip()


def _encode_profile_as_json_string(learner_profile: str) -> str:
    """Encode profile data without exposing prompt or template boundaries."""

    encoded = json.dumps(learner_profile, ensure_ascii=False)
    return (
        encoded.replace("<", r"\u003c")
        .replace(">", r"\u003e")
        .replace("&", r"\u0026")
        .replace("{", r"\u007b")
        .replace("}", r"\u007d")
    )


def _build_learner_profile_prompt_tail(learner_profile: str | None) -> str:
    normalized_profile = str(learner_profile or "").strip()
    if not normalized_profile:
        return ""

    encoded_profile = _encode_profile_as_json_string(normalized_profile)
    return (
        _learner_profile_context_template()
        .replace(
            "{learner_profile_prompt_marker}",
            LEARNER_PROFILE_PROMPT_MARKER,
        )
        .replace(
            "{learner_profile}",
            encoded_profile,
        )
    )


def build_course_prompt(
    course_prompt: str | None,
    *,
    learner: _LearnerWithProfile | None,
) -> str | None:
    """Return the course prompt with the learner profile appended exactly once."""

    if not course_prompt:
        return course_prompt

    base_prompt = str(course_prompt).rstrip()
    if not base_prompt or LEARNER_PROFILE_PROMPT_MARKER in base_prompt:
        return base_prompt

    learner_profile = getattr(learner, "learner_profile", None) if learner else None
    tail = _build_learner_profile_prompt_tail(learner_profile)
    if not tail:
        return course_prompt
    return f"{base_prompt}\n\n{tail}"
