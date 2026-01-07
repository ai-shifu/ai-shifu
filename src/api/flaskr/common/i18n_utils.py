"""Internationalization utility functions for common i18n operations."""

from flaskr.i18n import get_current_language

# Mapping of locale codes to language names in their native form
# Used for MarkdownFlow output language setting
LANGUAGE_NAME_MAP = {
    # Chinese
    "zh-CN": "简体中文",  # Simplified Chinese
    "zh-TW": "繁體中文",  # Traditional Chinese
    "zh-HK": "繁體中文",  # Traditional Chinese (Hong Kong)
    "zh": "简体中文",
    # English
    "en-US": "English",  # English (United States)
    "en-GB": "English",  # English (United Kingdom)
    "en-AU": "English",  # English (Australia)
    "en-CA": "English",  # English (Canada)
    "en": "English",
    # Japanese
    "ja-JP": "日本語",
    "ja": "日本語",
    # Korean
    "ko-KR": "한국어",
    "ko": "한국어",
    # French
    "fr-FR": "Français",  # French (France)
    "fr-CA": "Français",  # French (Canada)
    "fr": "Français",
    # German
    "de-DE": "Deutsch",
    "de-AT": "Deutsch",  # German (Austria)
    "de-CH": "Deutsch",  # German (Switzerland)
    "de": "Deutsch",
    # Spanish
    "es-ES": "Español",  # Spanish (Spain)
    "es-MX": "Español",  # Spanish (Mexico)
    "es-AR": "Español",  # Spanish (Argentina)
    "es": "Español",
    # Portuguese
    "pt-BR": "Português",  # Portuguese (Brazil)
    "pt-PT": "Português",  # Portuguese (Portugal)
    "pt": "Português",
    # Italian
    "it-IT": "Italiano",
    "it": "Italiano",
    # Russian
    "ru-RU": "Русский",
    "ru": "Русский",
    # Arabic
    "ar-SA": "العربية",  # Arabic (Saudi Arabia)
    "ar-AE": "العربية",  # Arabic (UAE)
    "ar": "العربية",
    # Hindi
    "hi-IN": "हिन्दी",
    "hi": "हिन्दी",
    # Thai
    "th-TH": "ไทย",
    "th": "ไทย",
    # Vietnamese
    "vi-VN": "Tiếng Việt",
    "vi": "Tiếng Việt",
    # Indonesian
    "id-ID": "Bahasa Indonesia",
    "id": "Bahasa Indonesia",
    # Dutch
    "nl-NL": "Nederlands",
    "nl-BE": "Nederlands",  # Dutch (Belgium)
    "nl": "Nederlands",
    # Polish
    "pl-PL": "Polski",
    "pl": "Polski",
    # Turkish
    "tr-TR": "Türkçe",
    "tr": "Türkçe",
    # Swedish
    "sv-SE": "Svenska",
    "sv": "Svenska",
    # Danish
    "da-DK": "Dansk",
    "da": "Dansk",
    # Norwegian
    "no-NO": "Norsk",
    "nb-NO": "Norsk",  # Norwegian Bokmål
    "no": "Norsk",
    # Finnish
    "fi-FI": "Suomi",
    "fi": "Suomi",
    # Greek
    "el-GR": "Ελληνικά",
    "el": "Ελληνικά",
    # Hebrew
    "he-IL": "עברית",
    "he": "עברית",
    # Czech
    "cs-CZ": "Čeština",
    "cs": "Čeština",
    # Hungarian
    "hu-HU": "Magyar",
    "hu": "Magyar",
    # Romanian
    "ro-RO": "Română",
    "ro": "Română",
    # Ukrainian
    "uk-UA": "Українська",
    "uk": "Українська",
    # Malay
    "ms-MY": "Bahasa Melayu",
    "ms": "Bahasa Melayu",
    # Bengali
    "bn-BD": "বাংলা",
    "bn-IN": "বাংলা",
    "bn": "বাংলা",
}

_LANGUAGE_CODE_LOOKUP = {code.lower(): name for code, name in LANGUAGE_NAME_MAP.items()}
_LANGUAGE_NAME_LOOKUP = {name.casefold(): name for name in LANGUAGE_NAME_MAP.values()}


def _resolve_output_language(language: str) -> str:
    raw_language = (language or "").strip()
    if not raw_language:
        return "English"

    normalized = raw_language.replace("_", "-")
    direct_match = LANGUAGE_NAME_MAP.get(normalized)
    if direct_match:
        return direct_match

    lookup_match = _LANGUAGE_CODE_LOOKUP.get(normalized.lower())
    if lookup_match:
        return lookup_match

    base_code = normalized.split("-")[0].lower()
    base_match = _LANGUAGE_CODE_LOOKUP.get(base_code)
    if base_match:
        return base_match

    name_match = _LANGUAGE_NAME_LOOKUP.get(raw_language.casefold())
    if name_match:
        return name_match

    return raw_language


def get_markdownflow_output_language() -> str:
    """
    Get the output language string for MarkdownFlow based on current user language.

    Returns:
        str: The full language name for MarkdownFlow output in native form.
             Examples: "简体中文" for zh-CN, "English" for en-US.
             Defaults to "English" if language not found, otherwise returns the input.
    """
    return _resolve_output_language(get_current_language())
