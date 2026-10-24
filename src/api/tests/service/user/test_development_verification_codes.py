"""Keep verification shortcuts behind an explicit nonproduction bootstrap."""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.common.config import EnvironmentConfigError
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import password_flow
from flaskr.service.user import utils as user_utils
from flaskr.service.user import verification_codes as codes
from flaskr.service.user.consts import CREDENTIAL_STATE_VERIFIED, USER_STATE_REGISTERED
from flaskr.service.user.models import (
    AuthCredential,
    UserInfo,
    UserToken,
    UserVerifyCode,
)
from flaskr.service.user.password_utils import verify_password
from flaskr.service.user.repository import get_password_hash
from flaskr.util.datetime import now_utc

from tests.common.fixtures.fake_redis import FakeRedis


@pytest.fixture
def verification_cache(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    cache = FakeRedis()
    monkeypatch.setattr(codes, "redis", cache)
    monkeypatch.setattr(codes, "distributed_lock_cache", cache)
    monkeypatch.setattr(user_utils, "redis", cache)
    return cache


def _identifier(kind: str) -> str:
    if kind == "email":
        return f"{uuid.uuid4().hex[:16]}@example.com"
    return f"155{uuid.uuid4().int % 100000000:08d}"


def _challenge(identifier: str, kind: str, state: str = "valid") -> UserVerifyCode:
    return UserVerifyCode(
        phone=identifier if kind == "sms" else "",
        mail=identifier if kind == "email" else "",
        verify_code="1357" if state == "wrong" else "2468",
        verify_code_type=1 if kind == "sms" else 2,
        verify_code_send=0 if state == "unsent" else 1,
        verify_code_used=1 if state == "used" else 0,
        created=now_utc() - timedelta(seconds=301 if state == "expired" else 1),
    )


@pytest.mark.parametrize("environment", ["production", "prod", "staging", "", None])
def test_development_bootstrap_refuses_non_development_environments(
    environment: str | None,
) -> None:
    app = Flask(__name__)
    app.config.update(ENV=environment, UNIVERSAL_VERIFICATION_CODE="2468")
    app.testing = True
    app.debug = True
    with pytest.raises(EnvironmentConfigError):
        codes.enable_development_verification_codes(app)
    assert codes.get_development_verification_code(app) is None


@pytest.mark.parametrize("environment", ["development", "testing", "production"])
def test_environment_and_flask_flags_alone_do_not_enable_bypass(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("development_verification_codes", "true")
    monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "2468")
    app = Flask(__name__)
    app.config.update(ENV=environment, UNIVERSAL_VERIFICATION_CODE="2468")
    app.testing = True
    app.debug = True
    assert codes.get_development_verification_code(app) is None


@pytest.mark.parametrize("environment", ["development", "testing"])
def test_explicit_development_shortcut_leaves_verification_state_untouched(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = Flask(__name__)
    app.config.update(ENV=environment, UNIVERSAL_VERIFICATION_CODE="2468")
    codes.enable_development_verification_codes(app)
    cache = FakeRedis()
    cache.set("existing-challenge", "1357")
    locked_consumer = Mock()
    monkeypatch.setattr(codes, "_consume_verification_code_locked", locked_consumer)
    codes.consume_verification_code(
        app, identifier="person@example.com", code=" 2468 ", cache_provider=cache
    )
    assert cache._store == {"existing-challenge": b"1357"}
    locked_consumer.assert_not_called()
    # Recheck at the use boundary even if an enabled app changes environment.
    app.config["ENV"] = "production"
    assert codes.get_development_verification_code(app) is None


@pytest.mark.parametrize("configured_code", [None, "", " \t", 2468, False])
def test_development_shortcut_requires_a_nonblank_string(
    configured_code: object,
) -> None:
    app = Flask(__name__)
    app.config.update(ENV="testing", UNIVERSAL_VERIFICATION_CODE=configured_code)
    codes.enable_development_verification_codes(app)
    assert codes.get_development_verification_code(app) is None


@pytest.mark.parametrize("kind", ["sms", "email"])
@pytest.mark.parametrize("environment", ["production", "development", "testing"])
def test_configured_code_without_capability_requires_a_sent_challenge(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    verification_cache: FakeRedis,
    kind: str,
    environment: str,
) -> None:
    monkeypatch.setitem(app.config, "ENV", environment)
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", "2468")
    monkeypatch.delitem(app.extensions, "development_verification_codes")
    with app.app_context(), pytest.raises(AppError) as error:
        codes.consume_verification_code(
            app,
            identifier=_identifier(kind),
            code=" 2468 ",
            kind=kind,
            cache_provider=verification_cache,
        )
    prefix = "sms" if kind == "sms" else "mail"
    assert error.value.code == ERROR_CODE[f"server.user.{prefix}SendExpired"]


@pytest.mark.parametrize("kind", ["sms", "email"])
@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("state", ["wrong", "expired", "used", "unsent"])
def test_production_universal_value_cannot_override_invalid_durable_challenge(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    verification_cache: FakeRedis,
    kind: str,
    cached: bool,
    state: str,
) -> None:
    monkeypatch.setitem(app.config, "ENV", "production")
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", "2468")
    identifier = _identifier(kind)
    prefix, _ttl = codes._verification_code_settings(app, kind)
    if cached:
        verification_cache.set(prefix + identifier, "2468")
    with app.app_context():
        record = _challenge(identifier, kind, state)
        db.session.add(record)
        db.session.flush()
        with pytest.raises(AppError) as error:
            codes.consume_verification_code(
                app, identifier=identifier, code="2468", kind=kind
            )
        error_prefix = "sms" if kind == "sms" else "mail"
        suffix = "CheckError" if state == "wrong" and not cached else "SendExpired"
        assert error.value.code == ERROR_CODE[f"server.user.{error_prefix}{suffix}"]
        assert record.verify_code_used == (1 if state == "used" else 0)
        db.session.rollback()


@pytest.mark.parametrize("kind", ["sms", "email"])
@pytest.mark.parametrize("cached", [False, True])
def test_production_can_consume_a_real_code_equal_to_the_legacy_setting_once(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    verification_cache: FakeRedis,
    kind: str,
    cached: bool,
) -> None:
    monkeypatch.setitem(app.config, "ENV", "production")
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", "2468")
    identifier = _identifier(kind)
    prefix, _ttl = codes._verification_code_settings(app, kind)
    if cached:
        verification_cache.set(prefix + identifier, "2468")
    with app.app_context():
        record = _challenge(identifier, kind)
        db.session.add(record)
        db.session.flush()
        codes.consume_verification_code(
            app, identifier=identifier, code="2468", kind=kind
        )
        assert record.verify_code_used == 1
        assert verification_cache.get(prefix + identifier) is None
        with pytest.raises(AppError) as replay:
            codes.consume_verification_code(
                app, identifier=identifier, code="2468", kind=kind
            )
        error_prefix = "sms" if kind == "sms" else "mail"
        assert replay.value.code == ERROR_CODE[f"server.user.{error_prefix}SendExpired"]
        db.session.rollback()


@pytest.mark.parametrize("kind", ["sms", "email"])
@pytest.mark.parametrize("operation", ["login", "reset", "set"])
def test_production_authentication_requires_issued_codes_and_preserves_normal_flows(
    app: object,
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    verification_cache: FakeRedis,
    kind: str,
    operation: str,
) -> None:
    monkeypatch.setitem(app.config, "ENV", "production")
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", "2468")
    identifier = _identifier(kind)
    user_bid = uuid.uuid4().hex
    provider = "phone" if kind == "sms" else "email"
    with app.app_context():
        db.session.add(
            UserInfo(
                user_bid=user_bid,
                user_identify=identifier,
                state=USER_STATE_REGISTERED,
                deleted=0,
            )
        )
        db.session.add(
            AuthCredential(
                credential_bid=uuid.uuid4().hex,
                user_bid=user_bid,
                provider_name=provider,
                subject_id=identifier,
                subject_format=provider,
                identifier=identifier,
                state=CREDENTIAL_STATE_VERIFIED,
                deleted=0,
            )
        )
        db.session.commit()

    def submit() -> int:
        if operation == "set":
            with app.app_context():
                try:
                    password_flow.set_password(
                        app,
                        user_bid=user_bid,
                        identifier=identifier,
                        code="2468",
                        new_password="Newpass123",
                    )
                except AppError as error:
                    return error.code
                return 0
        if operation == "reset":
            path = "reset_password"
            payload = {
                "identifier": identifier,
                "code": "2468",
                "new_password": "Newpass123",
            }
        elif kind == "sms":
            path = "login_sms"
            payload = {"mobile": identifier, "sms_code": "2468"}
        else:
            path = "login_email"
            payload = {"email": identifier, "code": "2468"}
        response = test_client.post(f"/api/user/{path}", json=payload)
        assert response.status_code == 200
        return response.get_json(force=True)["code"]

    error_prefix = "sms" if kind == "sms" else "mail"
    assert submit() == ERROR_CODE[f"server.user.{error_prefix}SendExpired"]
    with app.app_context():
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0
        assert (
            AuthCredential.query.filter_by(
                user_bid=user_bid, provider_name="password"
            ).count()
            == 0
        )
        record = _challenge(identifier, kind)
        db.session.add(record)
        db.session.commit()
        record_id = record.id
    prefix, _ttl = codes._verification_code_settings(app, kind)
    verification_cache.set(prefix + identifier, "2468")
    assert submit() == 0
    with app.app_context():
        assert db.session.get(UserVerifyCode, record_id).verify_code_used == 1
        if operation == "login":
            assert UserToken.query.filter_by(user_id=user_bid).count() == 1
        else:
            password_credential = AuthCredential.query.filter_by(
                user_bid=user_bid, provider_name="password"
            ).one()
            assert verify_password("Newpass123", get_password_hash(password_credential))
    if operation != "set":
        assert submit() == ERROR_CODE[f"server.user.{error_prefix}SendExpired"]


def test_production_sms_delivery_failure_cannot_use_legacy_universal_setting(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    verification_cache: FakeRedis,
) -> None:
    monkeypatch.setitem(app.config, "ENV", "production")
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", "2468")
    monkeypatch.setattr(user_utils, "send_sms_code_ali", Mock(return_value=None))
    identifier = _identifier("sms")
    with app.app_context(), pytest.raises(AppError) as error:
        user_utils.send_sms_code(app, identifier, require_captcha=False)
    assert error.value.code == ERROR_CODE["server.common.unknownError"]
    prefix, _ttl = codes._verification_code_settings(app, "sms")
    assert verification_cache.get(prefix + identifier) is None
    with app.app_context():
        record = UserVerifyCode.query.filter_by(phone=identifier).one()
        assert record.verify_code_send == 0
