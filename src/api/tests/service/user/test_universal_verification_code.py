"""Keep unissued development codes out of ordinary authentication paths."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import email_flow, password_flow, phone_flow
from flaskr.service.user import utils as user_utils
from flaskr.service.user import verification_codes as codes
from flaskr.service.user.models import AuthCredential, UserVerifyCode
from flaskr.service.user.repository import create_user_entity, upsert_credential
from flaskr.util.datetime import now_utc

from tests.common.fixtures.fake_redis import FakeRedis

if TYPE_CHECKING:
    from flask import Flask


@pytest.fixture
def strict_app(app: Flask, monkeypatch: pytest.MonkeyPatch) -> Flask:
    monkeypatch.delitem(app.extensions, "development_verification_codes", raising=False)
    monkeypatch.setitem(
        app.config, "UNIVERSAL_VERIFICATION_CODE", f"{uuid.uuid4().int % 10000:04d}"
    )
    return app


@pytest.mark.parametrize("environment", ["production", "development"])
@pytest.mark.parametrize("identifier", ["Person@Example.com", "+8613800138000"])
def test_ordinary_entry_rejects_unissued_override_even_with_development_label(
    strict_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    identifier: str,
) -> None:
    monkeypatch.setitem(strict_app.config, "ENV", environment)
    database = Mock(return_value="expired")
    monkeypatch.setattr(codes, "_consume_latest_code_from_db", database)
    with strict_app.app_context(), pytest.raises(AppError):
        codes.consume_verification_code(
            strict_app,
            identifier=identifier,
            code=strict_app.config["UNIVERSAL_VERIFICATION_CODE"],
            cache_provider=FakeRedis(),
        )
    assert database.called


@pytest.mark.parametrize("kind", ["email", "sms"])
@pytest.mark.parametrize("age", [0, 301])
def test_override_value_must_be_issued_unexpired_and_single_use(
    strict_app: Flask, kind: str, age: int
) -> None:
    identifier = (
        f"{uuid.uuid4().hex[:12]}@example.com" if kind == "email" else "13800138001"
    )
    cache = FakeRedis()
    code = strict_app.config["UNIVERSAL_VERIFICATION_CODE"]
    with strict_app.app_context():
        record = UserVerifyCode(
            mail=identifier if kind == "email" else "",
            phone=identifier if kind == "sms" else "",
            verify_code=code,
            verify_code_type=2 if kind == "email" else 1,
            verify_code_send=1,
            verify_code_used=0,
            created=now_utc() - timedelta(seconds=age),
        )
        db.session.add(record)
        db.session.flush()
        if age:
            with pytest.raises(AppError):
                codes.consume_verification_code(
                    strict_app, identifier=identifier, code=code, cache_provider=cache
                )
            assert record.verify_code_used == 0
        else:
            codes.consume_verification_code(
                strict_app, identifier=identifier, code=code, cache_provider=cache
            )
            assert record.verify_code_used == 1
            with pytest.raises(AppError):
                codes.consume_verification_code(
                    strict_app, identifier=identifier, code=code, cache_provider=cache
                )
        db.session.rollback()


@pytest.mark.parametrize("kind", ["email", "sms"])
def test_unissued_override_uses_the_normal_wrong_attempt_budget(
    strict_app: Flask, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    identifier = "budget@example.com" if kind == "email" else "13800138002"
    cache = FakeRedis()
    database = Mock(return_value="invalid")
    monkeypatch.setattr(codes, "_consume_latest_code_from_db", database)
    with strict_app.app_context():
        for _ in range(codes.MAX_VERIFICATION_ATTEMPTS):
            with pytest.raises(AppError):
                codes.consume_verification_code(
                    strict_app,
                    identifier=identifier,
                    code=strict_app.config["UNIVERSAL_VERIFICATION_CODE"],
                    cache_provider=cache,
                )
        database.return_value = "ok"
        with pytest.raises(AppError):
            codes.consume_verification_code(
                strict_app, identifier=identifier, code="issued", cache_provider=cache
            )
    assert database.call_count == codes.MAX_VERIFICATION_ATTEMPTS


@pytest.mark.parametrize("kind", ["email", "sms"])
@pytest.mark.parametrize("operation", ["login", "set", "reset"])
@pytest.mark.parametrize("issued", [False, True])
def test_login_and_password_ownership_require_issued_code(
    strict_app: Flask, kind: str, operation: str, issued: bool
) -> None:
    user_bid = uuid.uuid4().hex
    identifier = (
        f"{user_bid[:12]}@example.com"
        if kind == "email"
        else f"139{int(user_bid[:10], 16) % 100000000:08d}"
    )
    with strict_app.app_context():
        create_user_entity(user_bid=user_bid, identify=identifier)
        upsert_credential(
            strict_app,
            user_bid=user_bid,
            provider_name="email" if kind == "email" else "phone",
            subject_id=identifier,
            subject_format="email" if kind == "email" else "phone",
            identifier=identifier,
            metadata={},
            verified=True,
        )
        db.session.commit()
        code = strict_app.config["UNIVERSAL_VERIFICATION_CODE"]
        if issued:
            db.session.add(
                UserVerifyCode(
                    mail=identifier if kind == "email" else "",
                    phone=identifier if kind == "sms" else "",
                    verify_code=code,
                    verify_code_type=2 if kind == "email" else 1,
                    verify_code_send=1,
                    verify_code_used=0,
                    created=now_utc(),
                )
            )
            db.session.commit()

        def verify() -> None:
            if operation == "login":
                if kind == "email":
                    email_flow.verify_email_code(
                        strict_app, user_id=None, email=identifier, code=code
                    )
                else:
                    phone_flow.verify_phone_code(
                        strict_app, user_id=None, phone=identifier, code=code
                    )
            elif operation == "set":
                password_flow.set_password(
                    strict_app,
                    user_bid=user_bid,
                    identifier=identifier,
                    code=code,
                    new_password="NewPassword123",
                )
            else:
                password_flow.reset_password(
                    strict_app,
                    identifier=identifier,
                    code=code,
                    new_password="NewPassword123",
                )

        if issued:
            verify()
        with pytest.raises(AppError):
            verify()
        assert AuthCredential.query.filter_by(
            user_bid=user_bid, provider_name="password"
        ).count() == (1 if issued and operation != "login" else 0)


@pytest.mark.parametrize("development", [False, True])
def test_configured_override_never_masks_failed_sms_delivery(
    strict_app: Flask, monkeypatch: pytest.MonkeyPatch, development: bool
) -> None:
    monkeypatch.setitem(
        strict_app.extensions, "development_verification_codes", development
    )
    monkeypatch.setattr(user_utils, "send_sms_code_ali", Mock(return_value=None))
    phone = "13800138003"
    with strict_app.app_context(), pytest.raises(AppError) as error:
        user_utils.send_sms_code(strict_app, phone, require_captcha=False)
    assert error.value.code == ERROR_CODE["server.common.unknownError"]
    with strict_app.app_context():
        record = (
            UserVerifyCode.query.filter_by(phone=phone)
            .order_by(UserVerifyCode.id.desc())
            .first()
        )
        assert record.verify_code_send == 0


@pytest.mark.parametrize("setting", ["", "   "])
def test_explicit_development_capability_without_code_stays_disabled(
    app: Flask, monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", setting)
    database = Mock(return_value="expired")
    monkeypatch.setattr(codes, "_consume_latest_code_from_db", database)
    with app.app_context(), pytest.raises(AppError):
        codes.consume_verification_code(
            app,
            identifier="test@example.com",
            code="unissued",
            cache_provider=FakeRedis(),
        )
    database.assert_called_once()


def test_explicit_development_code_does_not_touch_real_challenges(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(app.extensions, "development_verification_codes", value=True)
    database = Mock()
    monkeypatch.setattr(codes, "_consume_latest_code_from_db", database)
    cache = FakeRedis()
    cache.set("unrelated-challenge", "issued")
    with app.app_context():
        codes.consume_verification_code(
            app,
            identifier="test@example.com",
            code=app.config["UNIVERSAL_VERIFICATION_CODE"],
            cache_provider=cache,
        )
    database.assert_not_called()
    assert cache._store == {"unrelated-challenge": b"issued"}


def test_config_boolean_cannot_grant_development_capability(
    strict_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(strict_app.config, "development_verification_codes", value=True)
    with strict_app.app_context(), pytest.raises(AppError):
        codes.consume_verification_code(
            strict_app,
            identifier="test@example.com",
            code=strict_app.config["UNIVERSAL_VERIFICATION_CODE"],
            cache_provider=FakeRedis(),
        )


def test_runtime_harness_transport_preserves_real_issuance_and_single_use(
    strict_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    import runpy
    import sys
    from pathlib import Path
    from types import SimpleNamespace

    from flaskr.api.sms import aliyun as sms_aliyun

    # Restore the SDK method after executing the harness's isolated entry.
    monkeypatch.setattr(
        sms_aliyun.Dysmsapi20170525Client,
        "send_sms_with_options",
        sms_aliyun.Dysmsapi20170525Client.send_sms_with_options,
    )
    monkeypatch.setitem(sys.modules, "development_app", SimpleNamespace(app=strict_app))
    root = Path(__file__).resolve().parents[5]
    result = runpy.run_path(str(root / "scripts/harness/runtime_app.py"))
    assert result["app"] is strict_app
    for key in (
        "ALIBABA_CLOUD_SMS_ACCESS_KEY_ID",
        "ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET",
        "ALIBABA_CLOUD_SMS_SIGN_NAME",
        "ALIBABA_CLOUD_SMS_TEMPLATE_CODE",
    ):
        monkeypatch.setitem(strict_app.config, key, "runtime-harness-placeholder")
    phone = "13800138009"
    user_utils.send_sms_code(strict_app, phone, require_captcha=False)
    with strict_app.app_context():
        record = UserVerifyCode.query.filter_by(phone=phone).one()
        assert record.verify_code_send == 1
        assert record.verify_code_used == 0
        codes.consume_verification_code(
            strict_app, identifier=phone, code=record.verify_code
        )
        assert record.verify_code_used == 1
        with pytest.raises(AppError):
            codes.consume_verification_code(
                strict_app, identifier=phone, code=record.verify_code
            )
