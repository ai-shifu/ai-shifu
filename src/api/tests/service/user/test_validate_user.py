"""Verify validate user behavior."""

from typing import Never

import jwt
import pytest
from flask import Flask
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user.common import validate_user


def test_validate_user_maps_invalid_algorithm_token_to_user_not_found(
    monkeypatch,
) -> None:
    app = Flask("validate-user-invalid-algorithm-tests")
    app.config["SECRET_KEY"] = "test-secret"
    app.config["ENVERIMENT"] = "prod"

    def _raise_invalid_algorithm(*_args: object, **_kwargs: object) -> Never:
        message = "The specified alg value is not allowed"
        raise jwt.exceptions.InvalidAlgorithmError(message)

    monkeypatch.setattr(jwt, "decode", _raise_invalid_algorithm)

    with pytest.raises(AppError) as exc_info:
        validate_user(app, "invalid-token")

    assert exc_info.value.code == ERROR_CODE["server.user.userNotFound"]
