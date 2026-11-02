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
    claims = {"exp": int(time.time()) + 60}
    if user_id is not None:
        claims["user_id"] = user_id
    token = jwt.encode(claims, app.config["SECRET_KEY"], algorithm="HS256")

    with pytest.raises(AppError) as exc_info:
        validate_user(app, token)

    assert exc_info.value.code == ERROR_CODE["server.user.userNotFound"]


def test_validate_user_never_treats_a_raw_user_id_as_a_session_token(
    monkeypatch: object,
) -> None:
    from flaskr.service.user import common

    app = Flask("validate-user-no-dev-bypass-tests")
    app.config["SECRET_KEY"] = "test-secret"
    # The retired dev branch loaded the token itself as a user id.
    app.config["ENVERIMENT"] = "dev"

    def _fail_load(user_id: str) -> None:
        message = f"user {user_id!r} must not be loaded from an unsigned token"
        raise AssertionError(message)

    monkeypatch.setattr(common, "_load_user_info", _fail_load)

    with pytest.raises(AppError) as exc_info:
        validate_user(app, "existing-user-bid")

    assert exc_info.value.code == ERROR_CODE["server.user.userNotFound"]
