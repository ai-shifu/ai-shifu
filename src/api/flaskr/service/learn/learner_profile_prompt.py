"""Compose course instructions and runtime learner variables into one prompt."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import TYPE_CHECKING

from flaskr.service.common.phone_numbers import is_valid_sms_mobile
from flaskr.util.prompt_loader import load_prompt_template

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


LEARNER_PROFILE_PROMPT_MARKER = (
    "<!-- ai-shifu:composed-document-prompt:learner-profile -->"
)
_COMPOSITION_OPEN = "<composition_contract>"
_COMPOSITION_CLOSE = "</composition_contract>"
_COURSE_PROMPT_OPEN = "<course_prompt>"
_COURSE_PROMPT_CLOSE = "</course_prompt>"
_LEARNER_CONTEXT_OPEN = "<learner_context>"
_LEARNER_CONTEXT_CLOSE = "</learner_context>"
_PREFERRED_ADDRESS_OPEN = "<preferred_address>"
_PREFERRED_ADDRESS_CLOSE = "</preferred_address>"
_LEARNER_BACKGROUND_OPEN = "<learner_background>"
_LEARNER_BACKGROUND_CLOSE = "</learner_background>"
_SERIALIZED_PROFILE_OPEN = '<learner_profile format="json-string">'
_SERIALIZED_PROFILE_CLOSE = "</learner_profile>"
_NICKNAME_VARIABLE = "sys_user_nickname"
_BACKGROUND_VARIABLE = "sys_user_background"
_NICKNAME_VARIABLE_REFERENCE = f"{{{{{_NICKNAME_VARIABLE}}}}}"
_BACKGROUND_VARIABLE_REFERENCE = f"{{{{{_BACKGROUND_VARIABLE}}}}}"


@lru_cache(maxsize=1)
def _composition_contract() -> str:
    return load_prompt_template("learner_profile_context").strip()


def _encode_profile_as_json_string(learner_profile: str) -> str:
    """Encode data from the previous serialized envelope for validation."""
    encoded = json.dumps(learner_profile, ensure_ascii=False)
    return (
        encoded.replace("<", r"\u003c")
        .replace(">", r"\u003e")
        .replace("&", r"\u0026")
        .replace("{", r"\u007b")
        .replace("}", r"\u007d")
    )


def _has_preferred_address(
    variables: Mapping[str, object],
    nickname_identifiers: Iterable[object],
) -> bool:
    value = variables.get(_NICKNAME_VARIABLE)
    if isinstance(value, list):
        return False
    nickname = str(value or "").strip()
    if (
        not nickname
        or len(nickname) > 64
        or "@" in nickname
        or is_valid_sms_mobile(nickname)
    ):
        return False

    nickname_key = nickname.casefold()
    return not any(
        nickname_key == str(identifier or "").strip().casefold()
        for identifier in nickname_identifiers
        if str(identifier or "").strip()
    )


def _variable_learner_context(
    variables: Mapping[str, object] | None,
    nickname_identifiers: Iterable[object] = (),
) -> str:
    effective_variables = variables or {}
    sections: list[str] = []
    if _has_preferred_address(effective_variables, nickname_identifiers):
        sections.append(
            f"{_PREFERRED_ADDRESS_OPEN}\n"
            f"{_NICKNAME_VARIABLE_REFERENCE}\n"
            f"{_PREFERRED_ADDRESS_CLOSE}"
        )
    sections.append(
        f"{_LEARNER_BACKGROUND_OPEN}\n"
        f"{_BACKGROUND_VARIABLE_REFERENCE}\n"
        f"{_LEARNER_BACKGROUND_CLOSE}"
    )
    return "\n".join(sections)


def _split_envelope(prompt: str) -> tuple[str, str] | None:
    envelope_prefix = f"{_COMPOSITION_OPEN}\n{LEARNER_PROFILE_PROMPT_MARKER}\n"
    contract_separator = f"\n{_COMPOSITION_CLOSE}\n\n{_COURSE_PROMPT_OPEN}\n"
    if not prompt.startswith(envelope_prefix):
        return None
    contract_and_content = prompt.removeprefix(envelope_prefix)
    contract, separator, content = contract_and_content.partition(contract_separator)
    if not separator or not contract.strip():
        return None
    return contract, content


def _parse_variable_composed_course_prompt(prompt: str) -> str | None:
    split_envelope = _split_envelope(prompt)
    if split_envelope is None:
        return None
    _, course_and_context = split_envelope
    course_separator = f"\n{_COURSE_PROMPT_CLOSE}\n\n{_LEARNER_CONTEXT_OPEN}\n"
    course_prompt, separator, trailing_content = course_and_context.rpartition(
        course_separator
    )
    if not separator or not course_prompt.strip():
        return None
    if not trailing_content.endswith(f"\n{_LEARNER_CONTEXT_CLOSE}"):
        return None
    learner_context = trailing_content.removesuffix(f"\n{_LEARNER_CONTEXT_CLOSE}")
    allowed_contexts = {
        _variable_learner_context({}),
        _variable_learner_context(
            {
                _NICKNAME_VARIABLE: "value",
            }
        ),
    }
    if learner_context not in allowed_contexts:
        return None
    return course_prompt


def _parse_serialized_composed_course_prompt(prompt: str) -> str | None:
    split_envelope = _split_envelope(prompt)
    if split_envelope is None:
        return None
    _, course_and_profile = split_envelope
    course_separator = f"\n{_COURSE_PROMPT_CLOSE}\n\n{_SERIALIZED_PROFILE_OPEN}\n"
    course_prompt, separator, trailing_content = course_and_profile.rpartition(
        course_separator
    )
    if not separator or not course_prompt.strip():
        return None
    if not trailing_content.endswith(f"\n{_SERIALIZED_PROFILE_CLOSE}"):
        return None
    profile_payload = trailing_content.removesuffix(f"\n{_SERIALIZED_PROFILE_CLOSE}")
    try:
        decoded_profile = json.loads(profile_payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(decoded_profile, str) or not decoded_profile.strip():
        return None
    if profile_payload != _encode_profile_as_json_string(decoded_profile):
        return None
    return course_prompt


def _parse_composed_course_prompt(prompt: str | None) -> str | None:
    """Recover the raw Course Prompt from either complete envelope shape."""
    normalized_prompt = str(prompt or "").strip()
    return _parse_variable_composed_course_prompt(
        normalized_prompt
    ) or _parse_serialized_composed_course_prompt(normalized_prompt)


def build_course_prompt(
    course_prompt: str | None,
    *,
    variables: Mapping[str, object] | None,
    nickname_identifiers: Iterable[object] = (),
) -> str | None:
    """Combine Course Prompt instructions with runtime learner variable slots."""
    if not course_prompt:
        return course_prompt

    supplied_prompt = str(course_prompt)
    parsed_course_prompt = _parse_composed_course_prompt(supplied_prompt)
    base_prompt = parsed_course_prompt or supplied_prompt
    if not base_prompt.strip():
        return course_prompt

    learner_context = _variable_learner_context(variables, nickname_identifiers)

    return (
        f"{_COMPOSITION_OPEN}\n"
        f"{LEARNER_PROFILE_PROMPT_MARKER}\n"
        f"{_composition_contract()}\n"
        f"{_COMPOSITION_CLOSE}\n\n"
        f"{_COURSE_PROMPT_OPEN}\n"
        f"{base_prompt}\n"
        f"{_COURSE_PROMPT_CLOSE}\n\n"
        f"{_LEARNER_CONTEXT_OPEN}\n"
        f"{learner_context}\n"
        f"{_LEARNER_CONTEXT_CLOSE}"
    )
