"""Retiring learner profile onboarding compatibility protocol."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from flaskr.service.common.models import raise_param_error
from flaskr.service.common.profile_onboarding import (
    ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS,
    PROFILE_ONBOARDING_STATE_KEY,
    load_profile_onboarding_config_payload,
)
from flaskr.service.profile.dtos import ProfileToSave
from flaskr.service.profile.funcs import (
    check_text_content,
    get_user_profiles,
    save_user_profiles,
)
from flaskr.service.profile.models import VariableValue
from flaskr.util.datetime import now_utc, to_utc_iso
from flaskr.util.uuid import generate_id
from markdown_flow import BlockType, InteractionParser, MarkdownFlow

if TYPE_CHECKING:
    from flask import Flask

__all__ = ["complete_profile_onboarding"]


_LEGACY_ANSWER_VARIABLE_PREFIX = "__profile_onboarding_legacy_answer_"
_MARKDOWNFLOW_VARIABLE_PREFIX = "?[%{{"
_ECMASCRIPT_TRIM_CHARACTERS = frozenset(
    {
        "\u0009",  # CHARACTER TABULATION
        "\u000a",  # LINE FEED
        "\u000b",  # LINE TABULATION
        "\u000c",  # FORM FEED
        "\u000d",  # CARRIAGE RETURN
        "\u0020",  # SPACE
        "\u00a0",  # NO-BREAK SPACE
        "\u1680",  # OGHAM SPACE MARK
        "\u2000",  # EN QUAD
        "\u2001",  # EM QUAD
        "\u2002",  # EN SPACE
        "\u2003",  # EM SPACE
        "\u2004",  # THREE-PER-EM SPACE
        "\u2005",  # FOUR-PER-EM SPACE
        "\u2006",  # SIX-PER-EM SPACE
        "\u2007",  # FIGURE SPACE
        "\u2008",  # PUNCTUATION SPACE
        "\u2009",  # THIN SPACE
        "\u200a",  # HAIR SPACE
        "\u2028",  # LINE SEPARATOR
        "\u2029",  # PARAGRAPH SEPARATOR
        "\u202f",  # NARROW NO-BREAK SPACE
        "\u205f",  # MEDIUM MATHEMATICAL SPACE
        "\u3000",  # IDEOGRAPHIC SPACE
        "\ufeff",  # ZERO WIDTH NO-BREAK SPACE
    }
)

if TYPE_CHECKING:
    from flask import Flask


def _now_iso() -> str:
    return to_utc_iso(now_utc().replace(microsecond=0)) or ""


def _has_onboarding_state(user_id: str) -> bool:
    return (
        VariableValue.query.filter(
            VariableValue.user_bid == user_id,
            VariableValue.shifu_bid == "",
            VariableValue.key == PROFILE_ONBOARDING_STATE_KEY,
            VariableValue.deleted == 0,
        ).first()
        is not None
    )


def _write_onboarding_state(
    app: Flask, user_id: str, *, skipped: bool, version: int
) -> None:
    state_payload = {
        "status": "skipped" if skipped else "completed",
        "version": version,
        "updated_at": _now_iso(),
    }
    db.session.add(
        VariableValue(
            variable_value_bid=generate_id(app),
            user_bid=user_id,
            shifu_bid="",
            variable_bid="",
            key=PROFILE_ONBOARDING_STATE_KEY,
            value=json.dumps(state_payload, ensure_ascii=False),
            deleted=0,
        )
    )


def _current_values_for_response(app: Flask, user_id: str) -> dict[str, str]:
    profiles = get_user_profiles(app, user_id, "")
    return {
        key: str(profiles.get(key) or "")
        for key in ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS
    }


def _is_legacy_profile_onboarding_variable_safe(variable_name: str) -> bool:
    """Match the variable-name subset understood by the retiring web parser."""
    # The old client's assignment capture accepts one or more non-whitespace,
    # non-`}` characters. U+FEFF is JavaScript whitespace but Python does not
    # classify it as whitespace, so keep this compatibility predicate explicit.
    return bool(variable_name) and all(
        character not in {"}", "\ufeff"} and not character.isspace()
        for character in variable_name
    )


def _replace_legacy_interaction_variable(
    content: str, *, raw_variable: str | None, synthetic_name: str
) -> str:
    """Project an official interaction onto the retiring client's safe subset."""
    stripped_content = content.strip()
    if raw_variable is None:
        return f"?[%{{{{{synthetic_name}}}}}{stripped_content[2:]}"

    # Replace the entire raw marker value, including whitespace the official
    # parser normalizes away but the retiring client cannot safely consume.
    variable_start = len(_MARKDOWNFLOW_VARIABLE_PREFIX)
    return (
        stripped_content[:variable_start]
        + synthetic_name
        + stripped_content[variable_start + len(raw_variable) :]
    )


def _extract_official_interaction_raw_variable(content: str) -> str:
    """Read marker text only after InteractionParser confirmed an assignment."""
    stripped_content = content.strip()
    marker_end = stripped_content.find("}}", len(_MARKDOWNFLOW_VARIABLE_PREFIX))
    if marker_end < 0:
        msg = "official interaction variable cannot be projected"
        raise ValueError(msg)
    return stripped_content[len(_MARKDOWNFLOW_VARIABLE_PREFIX) : marker_end]


def _strip_retiring_web_whitespace(value: str) -> str:
    """Match the old parser's JavaScript trim for projected button values."""
    start = 0
    end = len(value)
    while start < end and value[start] in _ECMASCRIPT_TRIM_CHARACTERS:
        start += 1
    while end > start and value[end - 1] in _ECMASCRIPT_TRIM_CHARACTERS:
        end -= 1
    return value[start:end]


def _plan_legacy_interaction_button_projection(
    *, parsed_interaction: dict[str, Any]
) -> tuple[list[str], bool] | None:
    """Plan the exact subset of official buttons the old parser can represent."""
    buttons = parsed_interaction.get("buttons")
    if not isinstance(buttons, list) or not buttons:
        return None

    projected_values: list[str] = []
    requires_synthetic_variable = bool(parsed_interaction.get("is_multi_select"))
    for button in buttons:
        if not isinstance(button, dict):
            return None
        display = button.get("display")
        value = button.get("value")
        if not isinstance(display, str) or not isinstance(value, str):
            return None
        projected_value = _strip_retiring_web_whitespace(value)
        projected_values.append(projected_value)
        if projected_value != value or not projected_value or "|" in projected_value:
            requires_synthetic_variable = True

    # The retiring parser treats one option (or a leading ellipsis) as a text
    # prompt rather than as a button choice, so it cannot preserve that answer.
    if len(projected_values) < 2 or projected_values[0].startswith("..."):
        requires_synthetic_variable = True

    return projected_values, requires_synthetic_variable


def _render_legacy_interaction_button_values(
    *, projected_values: list[str], variable_name: str
) -> str:
    """Render values as old-parser choices, omitting unsupported free text."""
    return f"?[%{{{{{variable_name}}}}} {' | '.join(projected_values)}]"


def _project_legacy_profile_onboarding_markdownflow(document: str) -> str:
    """Give the one-release legacy wire assignment-shaped interactions."""
    flow = MarkdownFlow(document=document)
    interaction_parser = InteractionParser()
    existing_variables = {
        str(variable).strip()
        for variable in flow.extract_variables()
        if str(variable).strip()
    }
    projected_parts: list[str] = []
    document_cursor = 0
    synthetic_index = 0
    changed = False

    for block in flow.get_all_blocks():
        original_content = str(block.content)
        block_start = document.find(original_content, document_cursor)
        if block_start < 0:
            msg = "official MarkdownFlow block cannot be projected"
            raise ValueError(msg)
        block_end = block_start + len(original_content)
        projected_parts.append(document[document_cursor:block_start])

        content = original_content
        if block.block_type == BlockType.INTERACTION:
            parsed_interaction = interaction_parser.parse(content)
            button_projection = _plan_legacy_interaction_button_projection(
                parsed_interaction=parsed_interaction,
            )
            buttons_require_synthetic_variable = bool(
                button_projection and button_projection[1]
            )
            variable_name = parsed_interaction.get("variable")
            official_variable = (
                variable_name if isinstance(variable_name, str) else None
            )
            legacy_variable = official_variable
            raw_variable = (
                _extract_official_interaction_raw_variable(content)
                if official_variable is not None
                else None
            )
            if (
                official_variable is None
                or raw_variable != official_variable
                or not _is_legacy_profile_onboarding_variable_safe(official_variable)
                or buttons_require_synthetic_variable
            ):
                base_name = f"{_LEGACY_ANSWER_VARIABLE_PREFIX}{synthetic_index}"
                synthetic_name = base_name
                collision_index = 1
                while synthetic_name in existing_variables:
                    synthetic_name = f"{base_name}_{collision_index}"
                    collision_index += 1
                existing_variables.add(synthetic_name)
                synthetic_index += 1
                legacy_variable = synthetic_name
                content = _replace_legacy_interaction_variable(
                    content,
                    raw_variable=raw_variable,
                    synthetic_name=synthetic_name,
                )
                changed = True
            if legacy_variable is None:
                msg = "legacy interaction variable cannot be projected"
                raise ValueError(msg)
            if button_projection is not None:
                content = _render_legacy_interaction_button_values(
                    projected_values=button_projection[0],
                    variable_name=legacy_variable,
                )
                changed = True
        projected_parts.append(content)
        document_cursor = block_end

    if not changed:
        return document
    projected_parts.append(document[document_cursor:])
    return "".join(projected_parts)


def _normalize_submitted_variables(raw_variables: object) -> dict[str, str]:
    if raw_variables is None:
        return {}
    if not isinstance(raw_variables, dict):
        raise_param_error("variables")
    # Old clients submit every variable declared by the configured MarkdownFlow.
    # Keep that wire compatible while persisting only the historical sys_* fields.
    return {
        key: str(value or "").strip()
        for key, value in raw_variables.items()
        if key in ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS and str(value or "").strip()
    }


def complete_profile_onboarding(
    app: Flask,
    *,
    user_id: str,
    skipped: bool,
    variables: dict[str, object] | None,
) -> dict[str, object]:
    """Complete profile onboarding."""
    config_payload = load_profile_onboarding_config_payload()
    normalized_variables = _normalize_submitted_variables(variables)
    if not skipped:
        nickname = normalized_variables.get("sys_user_nickname")
        if nickname and not check_text_content(app, user_id, nickname):
            raise_param_error("sys_user_nickname")
        background = normalized_variables.get("sys_user_background")
        if background and not check_text_content(app, user_id, background):
            raise_param_error("sys_user_background")
        save_user_profiles(
            app,
            user_id,
            "",
            [
                ProfileToSave(key=key, value=value, bid=None)
                for key, value in normalized_variables.items()
            ],
        )

    _write_onboarding_state(
        app,
        user_id,
        skipped=skipped,
        version=int(
            config_payload.get("revision") or config_payload.get("version") or 0
        ),
    )
    db.session.flush()
    return {
        "completed": True,
        "skipped": bool(skipped),
        "variables": normalized_variables,
    }
