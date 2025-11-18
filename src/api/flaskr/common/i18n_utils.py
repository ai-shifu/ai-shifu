"""Internationalization utility functions for common i18n operations."""

from flaskr.i18n import _


def get_markdownflow_output_language() -> str:
    """
    Get the output language string for MarkdownFlow based on current user language.

    This function retrieves the full language name (e.g., "English", "Simplified Chinese")
    configured in i18n that should be passed to MarkdownFlow's set_output_language() method.

    The mapping is configured in src/i18n/{locale}/modules/backend/common.json
    under the "outputLanguage" key:
    - en-US → "English"
    - zh-CN → "Simplified Chinese"
    - ja-JP → "Japanese" (future)
    - ko-KR → "Korean" (future)

    Returns:
        str: The full language name for MarkdownFlow output.
             Defaults to "English" if translation not found.

    Example:
        >>> from flaskr.i18n import set_language
        >>> set_language("zh-CN")
        >>> get_markdownflow_output_language()
        'Simplified Chinese'
        >>> set_language("en-US")
        >>> get_markdownflow_output_language()
        'English'
    """
    # Try to get the full language name from i18n
    output_language = _("server.common.outputLanguage")

    # If translation not found (returns the key itself), fall back to English
    if output_language == "server.common.outputLanguage":
        return "English"

    return output_language
