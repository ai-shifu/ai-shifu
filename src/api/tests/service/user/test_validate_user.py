import pytest
import jwt

from flask import Flask

from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.user.common import validate_user


def test_validate_user_maps_invalid_algorithm_token_to_user_not_found(monkeypatch):
    app = Flask("validate-user-invalid-algorithm-tests")
    app.config["SECRET_KEY"] = "test-secret"
    app.config["ENVERIMENT"] = "prod"

    def _raise_invalid_algorithm(*_args, **_kwargs):
        raise jwt.exceptions.InvalidAlgorithmError(
            "The specified alg value is not allowed"
        )

    monkeypatch.setattr(jwt, "decode", _raise_invalid_algorithm)

    with pytest.raises(AppException) as exc_info:
        validate_user(app, "invalid-token")

    assert exc_info.value.code == ERROR_CODE["server.user.userNotFound"]
