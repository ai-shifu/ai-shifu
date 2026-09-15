"""Verify stale sessions do not block public account-recovery routes."""

import time

import jwt
import pytest
from flaskr.service.common.models import AppError

_DEPENDENCY_FAILURE_MESSAGE = "validation dependency failed"


@pytest.fixture
def expired_token(app: object) -> str:
    return jwt.encode(
        {
            "user_id": "expired-optional-session",
            "exp": int(time.time()) - 60,
        },
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )


@pytest.fixture
def claimless_token(app: object) -> str:
    return jwt.encode(
        {"exp": int(time.time()) + 60},
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/user/send_sms_code",
        "/api/user/console_send_sms_code",
        "/api/user/send_email_code",
        "/api/user/login_sms",
        "/api/user/login_email",
        "/api/user/submit-feedback",
    ],
)
@pytest.mark.parametrize("token_kind", ["invalid", "expired", "claimless"])
def test_public_recovery_routes_ignore_stale_optional_tokens(
    test_client: object,
    expired_token: str,
    claimless_token: str,
    path: str,
    token_kind: str,
) -> None:
    tokens = {
        "invalid": "not-a-jwt",
        "expired": expired_token,
        "claimless": claimless_token,
    }

    response = test_client.post(path, json={}, headers={"Token": tokens[token_kind]})
    body = response.get_json(force=True)

    assert response.status_code == 200
    assert body["code"] == 2001


def test_optional_token_validation_keeps_non_auth_failures_visible(
    test_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    import flaskr.route.user as user_routes

    def fail_validation(*_args: object, **_kwargs: object) -> None:
        raise AppError(_DEPENDENCY_FAILURE_MESSAGE, 9999)

    monkeypatch.setattr(user_routes, "validate_user", fail_validation)

    response = test_client.post(
        "/api/user/send_email_code",
        json={},
        headers={"Token": "token-that-reaches-validation"},
    )
    body = response.get_json(force=True)

    assert response.status_code == 200
    assert body["code"] == 9999


def test_google_oauth_start_preserves_expired_token_recovery(
    test_client: object, expired_token: str
) -> None:
    response = test_client.get(
        "/api/user/oauth/google",
        headers={"Token": expired_token},
    )

    assert response.get_json(force=True)["code"] == 1005
