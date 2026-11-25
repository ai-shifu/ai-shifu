"""Verify the universal verification code is honored only outside production."""

import json
import logging
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import verification_codes as codes

from tests.common.fixtures.fake_redis import FakeRedis


def _post_json(client: object, path: str, payload: dict) -> tuple[object, dict]:
    resp = client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
    )
    return resp, json.loads(resp.data)


def _bare_app(**config: object) -> Flask:
    app = Flask(__name__)
    app.config.update(config)
    return app


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({"ENV": "production", "UNIVERSAL_VERIFICATION_CODE": "1024"}, None),
        ({"ENV": "Prod", "UNIVERSAL_VERIFICATION_CODE": "1024"}, None),
        ({"MODE": "production", "UNIVERSAL_VERIFICATION_CODE": "1024"}, None),
        # Fail closed: missing, empty or unrecognized ENV counts as production.
        ({"UNIVERSAL_VERIFICATION_CODE": "1024"}, None),
        ({"ENV": "", "MODE": "api", "UNIVERSAL_VERIFICATION_CODE": "1024"}, None),
        ({"ENV": "staging", "UNIVERSAL_VERIFICATION_CODE": "1024"}, None),
        ({"ENV": "prod-eu", "UNIVERSAL_VERIFICATION_CODE": "1024"}, None),
        ({"ENV": "development", "UNIVERSAL_VERIFICATION_CODE": ""}, None),
        ({"ENV": "development", "UNIVERSAL_VERIFICATION_CODE": "  "}, None),
        ({"ENV": "development"}, None),
        ({"ENV": "development", "UNIVERSAL_VERIFICATION_CODE": "1024"}, "1024"),
        ({"ENV": "testing", "UNIVERSAL_VERIFICATION_CODE": " 9999 "}, "9999"),
    ],
)
def test_universal_code_applies_only_when_set_outside_production(
    config: dict, expected: str | None
) -> None:
    assert codes.universal_verification_code(_bare_app(**config)) == expected


@pytest.mark.parametrize("kind", ["sms", "email"])
def test_production_ignores_universal_code_and_checks_the_real_challenge(
    app: object, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    monkeypatch.setitem(app.config, "ENV", "production")
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", "1024")
    database = Mock(return_value="expired")
    monkeypatch.setattr(codes, "_consume_latest_code_from_db", database)
    identifier = "person@example.com" if kind == "email" else "13800138000"

    with app.app_context(), pytest.raises(AppError) as error:
        codes.consume_verification_code(
            app,
            identifier=identifier,
            code="1024",
            kind=kind,
            cache_provider=FakeRedis(),
        )

    error_prefix = "mail" if kind == "email" else "sms"
    assert error.value.code == ERROR_CODE[f"server.user.{error_prefix}SendExpired"]
    database.assert_called()


@pytest.mark.parametrize("kind", ["sms", "email"])
def test_non_production_accepts_universal_code_without_touching_challenges(
    app: object, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    monkeypatch.setitem(app.config, "ENV", "development")
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", "1024")
    database = Mock(return_value="expired")
    monkeypatch.setattr(codes, "_consume_latest_code_from_db", database)
    identifier = "person@example.com" if kind == "email" else "13800138000"

    with app.app_context():
        codes.consume_verification_code(
            app,
            identifier=identifier,
            code="1024",
            kind=kind,
            cache_provider=FakeRedis(),
        )

    database.assert_not_called()


def test_production_sms_login_rejects_the_former_default_code(
    test_client: object, app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.user.models import AuthCredential

    monkeypatch.setitem(app.config, "ENV", "production")
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", "1024")
    phone = "13800138071"

    resp, body = _post_json(
        test_client,
        "/api/user/login_sms",
        {
            "mobile": phone,
            "sms_code": "1024",
            "language": "en-US",
            "login_context": "admin",
        },
    )

    assert resp.status_code == 200
    assert body["code"] == ERROR_CODE["server.user.smsSendExpired"]
    assert not (body.get("data") or {}).get("token")
    with app.app_context():
        assert AuthCredential.query.filter_by(identifier=phone).count() == 0


def test_production_password_reset_rejects_the_former_default_code(
    test_client: object, app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.user import phone_flow
    from flaskr.service.user.models import AuthCredential

    phone = "13800138072"
    with app.app_context():
        user_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code="9999"
        )
    user_bid = user_token.userInfo.user_id

    monkeypatch.setitem(app.config, "ENV", "production")
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", "1024")
    resp, body = _post_json(
        test_client,
        "/api/user/reset_password",
        {"identifier": phone, "code": "1024", "new_password": "Newpass123"},
    )

    assert resp.status_code == 200
    assert body["code"] == ERROR_CODE["server.user.smsSendExpired"]
    with app.app_context():
        assert (
            AuthCredential.query.filter_by(
                user_bid=user_bid, provider_name="password"
            ).count()
            == 0
        )


def test_production_sms_send_without_provider_fails_despite_universal_code(
    test_client: object, app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    import flaskr.service.user.utils as user_utils

    monkeypatch.setattr(
        user_utils, "send_sms_code_ali", lambda _app, _mobile, _code: None
    )
    monkeypatch.setitem(app.config, "ENV", "production")
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", "1024")

    resp, body = _post_json(
        test_client,
        "/api/user/console_send_sms_code",
        {"mobile": "13800138073"},
    )

    assert resp.status_code == 200
    assert body["code"] == ERROR_CODE["server.common.unknownError"]


@pytest.mark.parametrize(
    ("env", "fragment"),
    [("production", "ignored"), ("development", "is active")],
)
def test_startup_status_warns_without_revealing_the_code(
    caplog: pytest.LogCaptureFixture, env: str, fragment: str
) -> None:
    app = _bare_app(ENV=env, UNIVERSAL_VERIFICATION_CODE="secret-1024")

    with caplog.at_level(logging.WARNING):
        codes.log_universal_verification_code_status(app)

    assert fragment in caplog.text
    assert "secret-1024" not in caplog.text


def test_startup_status_is_silent_without_a_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        codes.log_universal_verification_code_status(
            _bare_app(ENV="production", UNIVERSAL_VERIFICATION_CODE="")
        )
    assert caplog.text == ""
