from types import SimpleNamespace

from flaskr.service.user.utils import get_user_language


def test_get_user_language_supports_language_attribute():
    user = SimpleNamespace(language="zh-CN")

    assert get_user_language(user) == "zh-CN"


def test_get_user_language_supports_user_language_attribute():
    user = SimpleNamespace(user_language="en_US")

    assert get_user_language(user) == "en-US"
