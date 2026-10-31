"""Verify native language labels reach generated prompts."""

from flaskr.common.i18n_utils import resolve_markdownflow_output_language


def test_french_locale_uses_native_language_name() -> None:
    assert resolve_markdownflow_output_language("fr-FR") == "Français"
    assert resolve_markdownflow_output_language("fr_FR") == "Français"


def test_existing_english_and_chinese_names_are_unchanged() -> None:
    assert resolve_markdownflow_output_language("en-US") == "English"
    assert resolve_markdownflow_output_language("zh-CN") == "简体中文"


def test_arabic_and_thai_locales_use_native_language_names() -> None:
    assert resolve_markdownflow_output_language("ar-SA") == "العربية"
    assert resolve_markdownflow_output_language("th-TH") == "ไทย"


def test_urdu_variants_use_native_output_language_name() -> None:
    for locale in ("ur", "ur-PK", "ur_IN", "UR_pk", "اردو"):
        assert resolve_markdownflow_output_language(locale) == "اردو"
