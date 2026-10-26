"""Verify verification code errors behavior."""

from __future__ import annotations

import pytest
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user.verification_codes import consume_verification_code


def test_consume_verification_code_rejects_missing_identifier_as_param_error(
    app: object,
) -> None:
    with pytest.raises(AppError) as exc_info:
        consume_verification_code(app, identifier="", code="1234")

    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]
    assert "identifier" in exc_info.value.message


def test_consume_verification_code_rejects_missing_code_as_param_error(
    app: object,
) -> None:
    with pytest.raises(AppError) as exc_info:
        consume_verification_code(app, identifier="user@example.com", code="")

    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]
    assert "code" in exc_info.value.message


def test_consume_verification_code_rejects_empty_normalized_phone_as_param_error(
    app: object,
) -> None:
    with pytest.raises(AppError) as exc_info:
        consume_verification_code(app, identifier="+86", code="1234")

    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]
    assert "identifier" in exc_info.value.message


def test_explicit_email_kind_cannot_consume_an_sms_challenge(app: object) -> None:
    from tests.common.fixtures.fake_redis import FakeRedis

    identifier = "13800138000"
    code = "2468"
    sms_key = app.config["REDIS_KEY_PREFIX_PHONE_CODE"] + identifier
    fake_redis = FakeRedis()
    fake_redis.set(sms_key, code)

    with app.app_context(), pytest.raises(AppError) as exc_info:
        consume_verification_code(
            app,
            identifier=identifier,
            code=code,
            kind="email",
            cache_provider=fake_redis,
        )

    assert exc_info.value.code == ERROR_CODE["server.user.mailSendExpired"]
    assert fake_redis.get(sms_key) == code.encode()
