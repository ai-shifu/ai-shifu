"""Resolve the editor's explicit language before falling back to the request."""

from typing import Any

from flaskr.common.i18n_utils import (
    LANGUAGE_NAME_MAP,
    resolve_markdownflow_output_language,
)
from flaskr.i18n import get_current_language
from flaskr.service.profile.api import SYS_USER_LANGUAGE

# The existing editor field accepts free text, including these common names.
_NAME_ALIASES = {
    "chinese": "zh-CN",
    "french": "fr-FR",
    "\u4e2d\u6587": "zh-CN",
    "\u82f1\u6587": "en-US",
    "\u82f1\u8bed": "en-US",
    "\u6cd5\u6587": "fr-FR",
    "\u6cd5\u8bed": "fr-FR",
}


def resolve_preview_language(
    variables: dict[str, Any], *, request_language: str | None = None
) -> str:
    """Prefer the visible teaching-language field over its legacy alias.

    Unknown text is never used as a model instruction. Call at the HTTP boundary
    to capture the request fallback before streaming clears its i18n context.
    """
    for candidate in (
        variables.get(SYS_USER_LANGUAGE),
        variables.get("language"),
        request_language or get_current_language(),
        "en-US",
    ):
        raw = str(candidate or "").strip()
        if not raw:
            continue
        locale = _NAME_ALIASES.get(raw.casefold(), raw)
        if resolve_markdownflow_output_language(locale) in LANGUAGE_NAME_MAP.values():
            return locale
    return "en-US"
