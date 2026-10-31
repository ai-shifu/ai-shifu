"""Keep unissued development codes out of ordinary authentication paths."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import email_flow, password_flow, phone_flow
from flaskr.service.user import utils as user_utils
from flaskr.service.user import verification_codes as codes
from flaskr.service.user.models import AuthCredential, UserToken, UserVerifyCode
from flaskr.service.user.password_utils import hash_password, verify_password
from flaskr.service.user.repository import (
    create_user_entity,
    set_password_hash,
    upsert_credential,
)
from flaskr.util.datetime import now_utc
from sqlalchemy import text

from tests.common.fixtures.fake_redis import FakeRedis

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask
    from sqlalchemy import ColumnElement, Table
    from sqlalchemy.engine import RowMapping


def _committed_rows(table: Table, *conditions: ColumnElement[bool]) -> list[RowMapping]:
    """Read durable state through a connection outside the ORM transaction."""
    with db.engine.connect() as connection:
        return list(connection.execute(table.select().where(*conditions)).mappings())


@pytest.fixture
def strict_app(app: Flask, monkeypatch: pytest.MonkeyPatch) -> Flask:
    monkeypatch.delitem(app.extensions, "development_verification_codes", raising=False)
    monkeypatch.setitem(
        app.config, "UNIVERSAL_VERIFICATION_CODE", f"{uuid.uuid4().int % 10000:04d}"
    )
    monkeypatch.setitem(app.config, "ENV", "development")
    monkeypatch.setitem(app.config, "MAIL_CODE_EXPIRE_TIME", 300)
    monkeypatch.setitem(app.config, "PHONE_CODE_EXPIRE_TIME", 300)
    return app


def test_mysql_verification_fixture_uses_strict_innodb(
    strict_app: Flask, record_property: Callable[[str, object], None]
) -> None:
    with strict_app.app_context():
        if db.engine.dialect.name != "mysql":
            pytest.skip("Set TEST_SQLALCHEMY_DATABASE_URI to disposable strict MySQL.")
        with db.engine.connect() as connection:
            version, mode, timezone = connection.execute(
                text("SELECT VERSION(), @@session.sql_mode, @@session.time_zone")
            ).one()
            engines = dict(
                connection.execute(
                    text(
                        "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN "
                        "('user_verify_code', 'user_users', "
                        "'user_auth_credentials', 'user_token')"
                    )
                ).all()
            )
        assert {"STRICT_ALL_TABLES", "STRICT_TRANS_TABLES"} & set(mode.split(","))
        assert timezone == "+00:00"
        assert len(engines) == 4
        assert set(engines.values()) == {"InnoDB"}
        record_property("mysql_version", version)
        record_property("mysql_sql_mode", mode)
        record_property("mysql_storage_engine", "InnoDB")


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
        f"{uuid.uuid4().hex[:12]}@example.com"
        if kind == "email"
        else f"138{uuid.uuid4().int % 100000000:08d}"
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
        record_id = record.id
        db.session.commit()
        if age:
            with pytest.raises(AppError), unit_of_work():
                codes.consume_verification_code(
                    strict_app, identifier=identifier, code=code, cache_provider=cache
                )
        else:
            with unit_of_work():
                codes.consume_verification_code(
                    strict_app, identifier=identifier, code=code, cache_provider=cache
                )
            # A fresh cache removes the consumed tombstone as a possible guard.
            with pytest.raises(AppError), unit_of_work():
                codes.consume_verification_code(
                    strict_app,
                    identifier=identifier,
                    code=code,
                    cache_provider=FakeRedis(),
                )
        rows = _committed_rows(UserVerifyCode.__table__, UserVerifyCode.id == record_id)
        assert rows[0]["verify_code_used"] == (0 if age else 1)


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
@pytest.mark.parametrize("challenge_state", ["unissued", "expired", "wrong", "issued"])
def test_login_and_password_ownership_require_issued_code(
    strict_app: Flask, kind: str, operation: str, challenge_state: str
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
        if operation == "reset":
            credential = upsert_credential(
                strict_app,
                user_bid=user_bid,
                provider_name="password",
                subject_id=identifier,
                subject_format="email" if kind == "email" else "phone",
                identifier=identifier,
                metadata={},
                verified=True,
            )
            set_password_hash(credential, hash_password("InitialPassword123"))
        db.session.commit()
        code = strict_app.config["UNIVERSAL_VERIFICATION_CODE"]
        if challenge_state != "unissued":
            db.session.add(
                UserVerifyCode(
                    mail=identifier if kind == "email" else "",
                    phone=identifier if kind == "sms" else "",
                    verify_code=(
                        f"{(int(code) + 1) % 10000:04d}"
                        if challenge_state == "wrong"
                        else code
                    ),
                    verify_code_type=2 if kind == "email" else 1,
                    verify_code_send=1,
                    verify_code_used=0,
                    created=(
                        now_utc() - timedelta(seconds=301)
                        if challenge_state == "expired"
                        else now_utc()
                    ),
                )
            )
            db.session.commit()

        verified_tokens: list[str] = []

        def verify() -> None:
            if operation == "login":
                if kind == "email":
                    result = email_flow.verify_email_code(
                        strict_app, user_id=None, email=identifier, code=code
                    )
                else:
                    result = phone_flow.verify_phone_code(
                        strict_app, user_id=None, phone=identifier, code=code
                    )
                assert result[0].userInfo.user_id == user_bid
                verified_tokens.append(result[0].token)
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

        issued = challenge_state == "issued"
        if issued:
            verify()
        else:
            with pytest.raises(AppError) as error:
                verify()
            prefix = "mail" if kind == "email" else "sms"
            suffix = "CheckError" if challenge_state == "wrong" else "SendExpired"
            assert error.value.code == ERROR_CODE[f"server.user.{prefix}{suffix}"]

        def snapshot() -> tuple[list[RowMapping], list[RowMapping], list[RowMapping]]:
            identifier_column = (
                UserVerifyCode.mail if kind == "email" else UserVerifyCode.phone
            )
            return (
                _committed_rows(
                    UserVerifyCode.__table__, identifier_column == identifier
                ),
                _committed_rows(UserToken.__table__, UserToken.user_id == user_bid),
                _committed_rows(
                    AuthCredential.__table__,
                    AuthCredential.user_bid == user_bid,
                    AuthCredential.provider_name == "password",
                    AuthCredential.deleted == 0,
                ),
            )

        challenge_rows, token_rows, password_rows = before_replay = snapshot()
        assert [row["verify_code_used"] for row in challenge_rows] == (
            [] if challenge_state == "unissued" else [int(issued)]
        )
        assert [row["token"] for row in token_rows] == verified_tokens
        assert len(password_rows) == int(
            operation == "reset" or (operation == "set" and issued)
        )
        if password_rows:
            stored_hash = json.loads(password_rows[0]["raw_profile"])["password_hash"]
            assert verify_password("NewPassword123", stored_hash) is issued
            if operation == "reset":
                assert verify_password("InitialPassword123", stored_hash) is not issued

        prefix = "mail" if kind == "email" else "sms"
        if issued:
            # Prove this business operation's committed code is unusable even
            # without its cache tombstone or password-already-set precheck.
            with pytest.raises(AppError) as consumed, unit_of_work():
                codes.consume_verification_code(
                    strict_app,
                    identifier=identifier,
                    code=code,
                    cache_provider=FakeRedis(),
                )
            assert consumed.value.code == ERROR_CODE[f"server.user.{prefix}SendExpired"]

        # Force cache-miss fallback before retrying the real business entry.
        codes.verification_cache_provider().delete(
            codes._verification_attempt_key(strict_app, kind, identifier)
        )
        with pytest.raises(AppError) as replay:
            verify()
        if issued and operation == "set":
            assert replay.value.code == ERROR_CODE["server.user.passwordAlreadySet"]
        else:
            suffix = "CheckError" if challenge_state == "wrong" else "SendExpired"
            assert replay.value.code == ERROR_CODE[f"server.user.{prefix}{suffix}"]
        assert snapshot() == before_replay


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
