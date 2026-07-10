from __future__ import annotations

import pytest

from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.user.verification_codes import consume_verification_code


def test_consume_verification_code_rejects_missing_identifier_as_param_error(app):
    with pytest.raises(AppException) as exc_info:
        consume_verification_code(app, identifier="", code="1234")

    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]
    assert "identifier" in exc_info.value.message


def test_consume_verification_code_rejects_missing_code_as_param_error(app):
    with pytest.raises(AppException) as exc_info:
        consume_verification_code(app, identifier="user@example.com", code="")

    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]
    assert "code" in exc_info.value.message


def test_consume_verification_code_rejects_empty_normalized_phone_as_param_error(app):
    with pytest.raises(AppException) as exc_info:
        consume_verification_code(app, identifier="+86", code="1234")

    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]
    assert "identifier" in exc_info.value.message
