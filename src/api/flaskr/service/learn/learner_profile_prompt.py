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
_NICKNAME_VARIABLE = "sys_user_nickname"
_BACKGROUND_VARIABLE = "sys_user_background"
_NICKNAME_VARIABLE_REFERENCE = f"{{{{{_NICKNAME_VARIABLE}}}}}"
_BACKGROUND_VARIABLE_REFERENCE = f"{{{{{_BACKGROUND_VARIABLE}}}}}"


@lru_cache(maxsize=1)
def _composition_contract() -> str:
    return load_prompt_template("learner_profile_context").strip()


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


def _encode_learner_variable(value: object) -> str:
    if isinstance(value, list):
        normalized_value = ", ".join(
            str(item) for item in value if item is not None and str(item).strip()
        )
    else:
        normalized_value = str(value or "")
    encoded = json.dumps(normalized_value or "UNKNOWN", ensure_ascii=False)
    return (
        encoded.replace("<", r"\u003c")
        .replace(">", r"\u003e")
        .replace("&", r"\u0026")
        .replace("{", r"\u007b")
        .replace("}", r"\u007d")
    )


def render_course_prompt_identity_variables(
    course_prompt: str | None,
    variables: Mapping[str, object] | None,
) -> str | None:
    """Resolve learner identity slots as boundary-safe JSON strings."""
    if not course_prompt:
        return course_prompt
    effective_variables = variables or {}
    rendered_prompt = str(course_prompt)
    for variable, reference in (
        (_NICKNAME_VARIABLE, _NICKNAME_VARIABLE_REFERENCE),
        (_BACKGROUND_VARIABLE, _BACKGROUND_VARIABLE_REFERENCE),
    ):
        if reference in rendered_prompt:
            rendered_prompt = rendered_prompt.replace(
                reference,
                _encode_learner_variable(effective_variables.get(variable)),
            )
    return rendered_prompt


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


def _parse_composed_course_prompt(prompt: str | None) -> str | None:
    """Recover the raw Course Prompt from the current variable envelope."""
    normalized_prompt = str(prompt or "").strip()
    split_envelope = _split_envelope(normalized_prompt)
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
