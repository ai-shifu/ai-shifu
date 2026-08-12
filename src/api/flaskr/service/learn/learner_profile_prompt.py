"""Compose course instructions and learner data into one document prompt."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Protocol

from flaskr.util.prompt_loader import load_prompt_template


class _LearnerWithProfile(Protocol):
    learner_profile: str | None


LEARNER_PROFILE_PROMPT_MARKER = (
    "<!-- ai-shifu:composed-document-prompt:learner-profile:v2 -->"
)
_COMPOSITION_OPEN = "<composition_contract>"
_COMPOSITION_CLOSE = "</composition_contract>"
_COURSE_PROMPT_OPEN = "<course_prompt>"
_COURSE_PROMPT_CLOSE = "</course_prompt>"
_LEARNER_PROFILE_OPEN = '<learner_profile format="json-string">'
_LEARNER_PROFILE_CLOSE = "</learner_profile>"


@lru_cache(maxsize=1)
def _composition_contract() -> str:
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


def _parse_composed_course_prompt(prompt: str | None) -> str | None:
    """Recover the raw course prompt from a complete canonical envelope."""

    normalized_prompt = str(prompt or "").strip()
    contract_prefix = (
        f"{_COMPOSITION_OPEN}\n{LEARNER_PROFILE_PROMPT_MARKER}\n"
        f"{_composition_contract()}\n{_COMPOSITION_CLOSE}\n\n"
    )
    prompt_prefix = contract_prefix + _COURSE_PROMPT_OPEN + "\n"
    course_separator = f"\n{_COURSE_PROMPT_CLOSE}\n\n{_LEARNER_PROFILE_OPEN}\n"
    if not normalized_prompt.startswith(prompt_prefix):
        return None
    if course_separator not in normalized_prompt:
        return None

    course_and_profile = normalized_prompt.removeprefix(prompt_prefix)
    course_prompt, separator, trailing_content = course_and_profile.rpartition(
        course_separator
    )
    if not separator or not trailing_content.endswith(f"\n{_LEARNER_PROFILE_CLOSE}"):
        return None
    if not course_prompt.strip():
        return None

    profile_payload = trailing_content.removesuffix(f"\n{_LEARNER_PROFILE_CLOSE}")
    try:
        decoded_profile = json.loads(profile_payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(decoded_profile, str) or not decoded_profile.strip():
        return None
    if profile_payload != _encode_profile_as_json_string(decoded_profile):
        return None
    return course_prompt


def has_composed_learner_profile(prompt: str | None) -> bool:
    """Return whether ``prompt`` has the complete server-authored envelope."""

    return _parse_composed_course_prompt(prompt) is not None


def build_course_prompt(
    course_prompt: str | None,
    *,
    learner: _LearnerWithProfile | None,
) -> str | None:
    """Return one semantic envelope for course instructions and learner data."""

    if not course_prompt:
        return course_prompt

    supplied_prompt = str(course_prompt)
    parsed_course_prompt = _parse_composed_course_prompt(supplied_prompt)
    base_prompt = parsed_course_prompt or supplied_prompt
    if not base_prompt.strip():
        return course_prompt

    learner_profile = getattr(learner, "learner_profile", None) if learner else None
    normalized_profile = str(learner_profile or "").strip()
    if not normalized_profile:
        return base_prompt

    encoded_profile = _encode_profile_as_json_string(normalized_profile)
    return (
        f"{_COMPOSITION_OPEN}\n"
        f"{LEARNER_PROFILE_PROMPT_MARKER}\n"
        f"{_composition_contract()}\n"
        f"{_COMPOSITION_CLOSE}\n\n"
        f"{_COURSE_PROMPT_OPEN}\n"
        f"{base_prompt}\n"
        f"{_COURSE_PROMPT_CLOSE}\n\n"
        f"{_LEARNER_PROFILE_OPEN}\n"
        f"{encoded_profile}\n"
        f"{_LEARNER_PROFILE_CLOSE}"
    )
