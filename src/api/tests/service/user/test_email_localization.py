"""Verify that email text and document language use the same locale."""

import pytest


@pytest.mark.parametrize(
    ("requested_language", "canonical_language"),
    [
        ("es-ES", "es-ES"),
        ("es_MX", "es-ES"),
        ("de_DE", "de-DE"),
        ("de_AT", "de-DE"),
        ("zz", "en-US"),
        ("---", "en-US"),
        ("en_GB", "en-US"),
        ("ar-SA", "ar-SA"),
        ("ur-PK", "ur-PK"),
        ("ur_IN", "ur-PK"),
        ("UR", "ur-PK"),
        ("AR_ae", "ar-SA"),
        ("th", "th-TH"),
        ("fr_CA", "fr-FR"),
        ("zh_TW", "zh-CN"),
        (None, "ar-SA"),
        ("", "ar-SA"),
    ],
)
def test_email_locale_matches_rendered_translations(
    app: object, requested_language: str | None, canonical_language: str
) -> None:
    import flaskr.service.user.utils as user_utils

    with app.app_context():
        previous_language = user_utils.get_current_language()
        user_utils.set_language("ar-SA")
        try:
            expected = user_utils._format_email_verification_message(
                "1234", 300, language=canonical_language
            )
            actual = user_utils._format_email_verification_message(
                "1234", 300, language=requested_language
            )
            assert actual == expected
            subject, plain_body, html_body = actual
            direction = "rtl" if canonical_language in {"ar-SA", "ur-PK"} else "ltr"
            assert f'<html lang="{canonical_language}" dir="{direction}">' in html_body
            assert '<div dir="ltr"' in html_body
            if canonical_language == "ur-PK":
                assert subject == "AI-Shifu تصدیقی کوڈ"
                assert "تصدیقی کوڈ: 1234" in plain_body
                assert "5 منٹ" in plain_body
            if canonical_language == "en-US":
                assert subject == "AI-Shifu verification code"
                assert "Verification code: 1234" in plain_body
                assert "It expires in 5 minutes" in plain_body
                assert "Verify your AI-Shifu account" in html_body
            assert user_utils.get_current_language() == "ar-SA"
        finally:
            user_utils.set_language(previous_language)
