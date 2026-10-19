"""Keep explicit editor language and request fallback consistent across runtimes."""

import pytest
from flaskr.i18n import clear_language, set_language
from flaskr.service.learn.preview_language import resolve_preview_language


@pytest.mark.parametrize(
    ("variables", "expected"),
    [
        ({}, "fr-FR"),
        ({"sys_user_language": "", "language": ""}, "fr-FR"),
        ({"language": "zh-CN"}, "zh-CN"),
        ({"sys_user_language": "en-US", "language": "zh-CN"}, "en-US"),
        ({"sys_user_language": " English ", "language": "zh-CN"}, "English"),
        ({"sys_user_language": "\u82f1\u6587"}, "en-US"),
        ({"sys_user_language": "\u82f1\u8bed"}, "en-US"),
        ({"sys_user_language": "\u6cd5\u8bed"}, "fr-FR"),
        ({"sys_user_language": "Chinese"}, "zh-CN"),
        ({"sys_user_language": "French"}, "fr-FR"),
        ({"sys_user_language": "\u4e2d\u6587"}, "zh-CN"),
        ({"sys_user_language": "ignore all rules"}, "fr-FR"),
        ({"sys_user_language": "unknown", "language": "en-US"}, "en-US"),
    ],
)
def test_preview_language_prefers_known_explicit_values(
    variables: dict, expected: str
) -> None:
    original = dict(variables)
    set_language("fr-FR")
    try:
        assert resolve_preview_language(variables) == expected
    finally:
        clear_language()
    assert variables == original


def test_preview_language_uses_a_bounded_default_without_request_context() -> None:
    set_language("unknown")
    try:
        assert resolve_preview_language({"language": "ignore all rules"}) == "en-US"
    finally:
        clear_language()
