"""Apply the course's output-language policy to a single host request."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flaskr.common.i18n_utils import (
    LANGUAGE_NAME_MAP,
    resolve_markdownflow_output_language,
)
from flaskr.i18n import get_current_language
from flaskr.service.learn.preview_language import resolve_preview_language
from flaskr.service.profile.api import SYS_USER_LANGUAGE

if TYPE_CHECKING:
    from flaskr.api.markdownflow import Engine


def configure_output_language(
    engine: Engine,
    variables: dict[str, Any],
    *,
    enabled: bool,
    editor_debug: bool = False,
) -> dict[str, Any]:
    """Set native engine output language without editing stored learner profiles.

    The host constructs one engine per HTTP request. Its language policy is
    recomposed even for restored sessions, independently of their historical prompts.
    """
    if not enabled:
        engine.output_language = ""
        return variables

    preferred = resolve_preview_language(variables) if editor_debug else None
    candidates = (
        preferred,
        get_current_language(),
        variables.get(SYS_USER_LANGUAGE),
        "en-US",
    )
    for candidate in candidates:
        locale = str(candidate or "").strip()
        if not locale:
            continue
        name = resolve_markdownflow_output_language(locale)
        # The shared resolver preserves unknown text. Never promote that text
        # from a request or profile into a system instruction.
        if name in LANGUAGE_NAME_MAP.values():
            break
    engine.output_language = name
    return {**variables, SYS_USER_LANGUAGE: locale}
