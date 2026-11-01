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


def test_canonicalize_language_tag_normalizes_subtag_case() -> None:
    from flaskr.common.i18n_utils import canonicalize_language_tag

    assert canonicalize_language_tag("zh_hans_cn") == "zh-Hans-CN"
    assert canonicalize_language_tag("EN-us") == "en-US"
    assert canonicalize_language_tag("es-419") == "es-419"
    assert canonicalize_language_tag("--") == ""
    # Callers own whitespace handling.
    assert canonicalize_language_tag(" zh-cn") == " zh-CN"


def test_match_supported_language_prefers_exact_then_primary_subtag() -> None:
    from flaskr.common.i18n_utils import match_supported_language

    supported = ["en-US", "zh-CN", "zh-TW"]
    assert match_supported_language("zh-TW", supported) == "zh-TW"
    assert match_supported_language("zh-HK", supported) == "zh-CN"
    assert match_supported_language("EN-gb", supported) == "en-US"
    assert match_supported_language("fr-FR", supported) is None


def test_first_accept_language_returns_first_tag_without_quality() -> None:
    from flaskr.common.i18n_utils import first_accept_language

    assert first_accept_language("zh-CN,zh;q=0.9,en;q=0.8") == "zh-CN"
    assert first_accept_language(" en-us;q=0.9 , zh") == "en-us"
    assert first_accept_language("") is None
    assert first_accept_language(None) is None
    assert first_accept_language(",en") is None
    assert first_accept_language(";q=1") is None
