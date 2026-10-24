"""Verify validate user behavior."""

import time

import jwt
import pytest
from flask import Flask
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user.common import validate_user


def test_validate_user_maps_invalid_algorithm_token_to_user_not_found(
    monkeypatch: object,
) -> None:
    app = Flask("validate-user-invalid-algorithm-tests")
    app.config["SECRET_KEY"] = "test-secret"
    app.config["ENVERIMENT"] = "prod"

    def _raise_invalid_algorithm(*_args: object, **_kwargs: object) -> None:
        message = "The specified alg value is not allowed"
        raise jwt.exceptions.InvalidAlgorithmError(message)

    monkeypatch.setattr(jwt, "decode", _raise_invalid_algorithm)

    with pytest.raises(AppError) as exc_info:
        validate_user(app, "invalid-token")

    assert exc_info.value.code == ERROR_CODE["server.user.userNotFound"]


@pytest.mark.parametrize("user_id", [None, "", "   ", 123])
def test_validate_user_maps_invalid_user_id_claim_to_user_not_found(
    user_id: object,
) -> None:
    app = Flask("validate-user-claim-tests")
    app.config["SECRET_KEY"] = "test-secret"
    app.config["ENVERIMENT"] = "prod"
    claims = {"exp": int(time.time()) + 60}
    if user_id is not None:
        claims["user_id"] = user_id
    token = jwt.encode(claims, app.config["SECRET_KEY"], algorithm="HS256")

    with pytest.raises(AppError) as exc_info:
        validate_user(app, token)

    assert exc_info.value.code == ERROR_CODE["server.user.userNotFound"]
