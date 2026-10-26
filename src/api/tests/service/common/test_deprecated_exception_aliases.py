"""Renamed exception classes stay importable under their previous names."""

import importlib

import pytest

ALIASES = [
    ("flaskr.service.common", "AppException", "AppError"),
    ("flaskr.service.common.models", "AppException", "AppError"),
    ("flaskr.service.learn.exceptions", "PaidException", "PaidError"),
    ("flaskr.service.learn.exceptions", "BreakException", "BreakError"),
    ("flaskr.service.user.exceptions", "UserNotLoginException", "UserNotLoginError"),
    ("flaskr.service.tts.rpm_gate", "TTSRpmQueueTimeout", "TTSRpmQueueTimeoutError"),
    ("flaskr.service.tts.api", "TTSRpmQueueTimeout", "TTSRpmQueueTimeoutError"),
]


@pytest.mark.parametrize(("module_name", "old_name", "new_name"), ALIASES)
def test_old_exception_name_resolves_to_the_renamed_class(
    module_name: str, old_name: str, new_name: str
) -> None:
    module = importlib.import_module(module_name)

    with pytest.deprecated_call():
        alias = getattr(module, old_name)

    assert alias is getattr(module, new_name)


def test_unknown_attribute_still_raises_attribute_error() -> None:
    module = importlib.import_module("flaskr.service.common.models")

    with pytest.raises(AttributeError, match="NoSuchName"):
        _ = module.NoSuchName
