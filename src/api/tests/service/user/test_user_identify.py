"""Verify user identify behavior."""

import uuid

import pytest


class _FakeRedisLock:
    def __init__(self, locks: dict[str, bool], key: str) -> None:
        self._locks = locks
        self._key = key
        self._held = False

    def acquire(
        self, blocking: bool = True, blocking_timeout: int | None = None
    ) -> bool:
        _ = (blocking, blocking_timeout)
        if self._locks.get(self._key, False):
            return False
        self._locks[self._key] = True
        self._held = True
        return True

    def release(self) -> None:
        if self._held:
            self._locks.pop(self._key, None)
            self._held = False


class _FakeRedis:
    def __init__(self, values: object = None) -> None:
        self.values = dict(values or {})
        self.deleted = []
        self.locks: dict[str, bool] = {}

    def get(self, key: object) -> object:
        return self.values.get(key)

    def set(
        self,
        key: str,
        value: object,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
        *_args: object,
        **_kwargs: object,
    ) -> object:
        _ = (ex, px)
        if nx and key in self.values:
            return False
        if xx and key not in self.values:
            return False
        self.values[key] = value
        return True

    def incr(self, key: str, amount: int = 1) -> int:
        value = int(self.values.get(key, 0)) + amount
        self.values[key] = value
        return value

    def lock(
        self,
        key: str,
        timeout: int | None = None,
        blocking_timeout: int | None = None,
    ) -> _FakeRedisLock:
        _ = (timeout, blocking_timeout)
        return _FakeRedisLock(self.locks, key)

    def delete(self, *keys: str) -> object:
        self.deleted.extend(keys)
        for key in keys:
            self.values.pop(key, None)
        return len(keys)


def _reset_user_auth_tables() -> None:
    from flaskr.dao import db
    from flaskr.service.user.models import (
        AuthCredential,
    )
    from flaskr.service.user.models import (
        UserInfo as UserEntity,
    )
    from flaskr.service.user.models import (
        UserToken as UserTokenModel,
    )

    UserTokenModel.query.delete()
    AuthCredential.query.delete()
    UserEntity.query.delete()
    db.session.commit()


def _delete_shifu_pair(shifu_bid: str) -> None:
    from flaskr.dao import db
    from flaskr.service.shifu.models import DraftShifu, PublishedShifu

    PublishedShifu.query.filter_by(shifu_bid=shifu_bid).delete()
    DraftShifu.query.filter_by(shifu_bid=shifu_bid).delete()
    db.session.commit()


def _reset_shifu_tables() -> None:
    from flaskr.dao import db
    from flaskr.service.shifu.models import DraftShifu, PublishedShifu

    PublishedShifu.query.delete()
    DraftShifu.query.delete()
    db.session.commit()


def test_phone_flow_marks_temp_phone_claim_as_created_new_user(
    tmp_path: object, monkeypatch: object
) -> None:
    from flask import Flask
    from flaskr import dao
    from flaskr.service.user import phone_flow
    from flaskr.service.user.consts import (
        USER_STATE_REGISTERED,
        USER_STATE_UNREGISTERED,
    )
    from flaskr.service.user.models import AuthCredential
    from flaskr.service.user.models import UserInfo as UserEntity

    app = Flask(__name__)
    db_uri = f"sqlite:///{tmp_path / 'phone-claim.db'}"
    app.config.update(
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI=db_uri,
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": db_uri,
            "ai_shifu_admin": db_uri,
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TOKEN_EXPIRE_TIME=60 * 60,
        UNIVERSAL_VERIFICATION_CODE="9999",
        REDIS_KEY_PREFIX_PHONE_CODE="test:phone:",
        REDIS_KEY_PREFIX_USER="test:user:",
        ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO=False,
    )

    dao.db.init_app(app)

    fake_redis = _FakeRedis()
    monkeypatch.setattr(phone_flow, "redis", fake_redis, raising=False)
    monkeypatch.setattr(phone_flow, "init_first_course", lambda *_args: False)

    with app.app_context():
        dao.db.create_all()
        temp_user_bid = uuid.uuid4().hex
        phone = "15500006661"
        dao.db.session.add(
            UserEntity(
                user_bid=temp_user_bid,
                user_identify=temp_user_bid,
                nickname="",
                language="zh-CN",
                state=USER_STATE_UNREGISTERED,
                deleted=0,
            )
        )
        dao.db.session.commit()

        token, created_new_user, _ctx = phone_flow.verify_phone_code(
            app,
            user_id=temp_user_bid,
            phone=phone,
            code="9999",
            language="zh-CN",
            login_context="admin",
        )

        entity = UserEntity.query.filter_by(user_bid=temp_user_bid).first()
        credential = AuthCredential.query.filter_by(
            user_bid=temp_user_bid,
            provider_name="phone",
            identifier=phone,
        ).first()

        assert token.userInfo.user_id == temp_user_bid
        assert created_new_user is True
        assert entity is not None
        assert entity.user_identify == phone
        assert entity.state == USER_STATE_REGISTERED
        assert credential is not None


def test_email_flow_marks_temp_email_claim_as_created_new_user(
    tmp_path: object, monkeypatch: object
) -> None:
    from flask import Flask
    from flaskr import dao
    from flaskr.service.user import email_flow
    from flaskr.service.user.consts import (
        USER_STATE_REGISTERED,
        USER_STATE_UNREGISTERED,
    )
    from flaskr.service.user.models import AuthCredential
    from flaskr.service.user.models import UserInfo as UserEntity

    app = Flask(__name__)
    db_uri = f"sqlite:///{tmp_path / 'email-claim.db'}"
    app.config.update(
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI=db_uri,
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": db_uri,
            "ai_shifu_admin": db_uri,
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TOKEN_EXPIRE_TIME=60 * 60,
        UNIVERSAL_VERIFICATION_CODE="9999",
        REDIS_KEY_PREFIX_MAIL_CODE="test:email:",
        REDIS_KEY_PREFIX_USER="test:user:",
        ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO=False,
    )

    dao.db.init_app(app)

    monkeypatch.setattr(email_flow, "redis", _FakeRedis(), raising=False)
    monkeypatch.setattr(email_flow, "init_first_course", lambda *_args: False)

    with app.app_context():
        dao.db.create_all()
        temp_user_bid = uuid.uuid4().hex
        email = "guest@example.com"
        dao.db.session.add(
            UserEntity(
                user_bid=temp_user_bid,
                user_identify=temp_user_bid,
                nickname="",
                language="en-US",
                state=USER_STATE_UNREGISTERED,
                deleted=0,
            )
        )
        dao.db.session.commit()

        token, created_new_user, _ctx = email_flow.verify_email_code(
            app,
            user_id=temp_user_bid,
            email=email,
            code="9999",
            language="en-US",
        )

        entity = UserEntity.query.filter_by(user_bid=temp_user_bid).first()
        credential = AuthCredential.query.filter_by(
            user_bid=temp_user_bid,
            provider_name="email",
            identifier=email,
        ).first()

        assert token.userInfo.user_id == temp_user_bid
        assert created_new_user is True
        assert entity is not None
        assert entity.user_identify == email
        assert entity.state == USER_STATE_REGISTERED
        assert credential is not None


def test_phone_flow_sets_user_identify(app: object) -> None:
    from flaskr.service.user import phone_flow
    from flaskr.service.user.models import UserInfo as UserEntity

    # Bypass code storage by using universal code
    with app.app_context():
        app.config["UNIVERSAL_VERIFICATION_CODE"] = "9999"
        app.config["ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO"] = False

        # Monkeypatch redis in module scope
        phone_flow.redis = _FakeRedis()

        _reset_user_auth_tables()
        try:
            phone = "15500001111"
            token, _created, _ctx = phone_flow.verify_phone_code(
                app, user_id=None, phone=phone, code="9999"
            )

            # Verify persisted identifier on entity
            entity = UserEntity.query.filter_by(user_bid=token.userInfo.user_id).first()
            assert entity is not None
            assert entity.user_identify == phone
            assert entity.is_creator == 1
            assert entity.is_operator == 1
        finally:
            _reset_user_auth_tables()


def test_email_flow_sets_user_identify(app: object) -> None:
    from flaskr.service.user import email_flow
    from flaskr.service.user.models import UserInfo as UserEntity

    with app.app_context():
        app.config["UNIVERSAL_VERIFICATION_CODE"] = "9999"
        app.config["ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO"] = False
        email_flow.redis = _FakeRedis()

        _reset_user_auth_tables()
        try:
            raw_email = "TestUser@Example.com"
            token, _created, context = email_flow.verify_email_code(
                app, user_id=None, email=raw_email, code="9999"
            )

            entity = UserEntity.query.filter_by(user_bid=token.userInfo.user_id).first()
            assert entity is not None
            assert entity.user_identify == raw_email.lower()
            assert context["creator_granted_now"] is True
        finally:
            _reset_user_auth_tables()


def test_send_email_code_stores_lowercase_identifier(
    app: object, monkeypatch: object
) -> None:
    from email import message_from_string

    import flaskr.service.user.utils as user_utils
    from flaskr.dao import db
    from flaskr.service.common.models import AppError
    from flaskr.service.user.models import UserVerifyCode

    from tests.common.fixtures.fake_redis import FakeRedis

    class _FakeSMTP:
        sent_message = ""
        sent_to = ""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def starttls(self) -> None:
            return None

        def login(self, *_args: object) -> None:
            return None

        def sendmail(self, _sender: object, recipient: object, message: object) -> None:
            type(self).sent_to = recipient
            type(self).sent_message = message

        def quit(self) -> None:
            return None

    fake_redis = FakeRedis()
    monkeypatch.setattr(user_utils, "redis", fake_redis, raising=False)
    monkeypatch.setattr(user_utils.smtplib, "SMTP", _FakeSMTP, raising=False)
    fixed_digits = iter("1234")
    monkeypatch.setattr(user_utils.secrets, "choice", lambda _chars: next(fixed_digits))

    with app.app_context():
        app.config.update(
            REDIS_KEY_PREFIX_MAIL_CODE="test:mail:",
            REDIS_KEY_PREFIX_MAIL_LIMIT="test:mail-limit:",
            MAIL_CODE_EXPIRE_TIME=300,
            MAIL_CODE_INTERVAL=60,
            SMTP_SENDER="sender@example.com",
            SMTP_SERVER="smtp.example.com",
            SMTP_PORT=587,
            SMTP_USERNAME="sender@example.com",
            SMTP_PASSWORD="secret",
        )

        raw_email = "TestUser@Example.com"
        normalized_email = raw_email.lower()
        try:
            user_utils.send_email_code(app, raw_email)

            code_keys = [
                key
                for key in fake_redis._store
                if key.endswith("@example.com") and "limit" not in key
            ]
            assert code_keys == [
                f"{app.config['REDIS_KEY_PREFIX_MAIL_CODE']}{normalized_email}"
            ]
            assert fake_redis.get(code_keys[0]) == b"1234"
            assert all(raw_email not in key for key in fake_redis._store)

            record = UserVerifyCode.query.filter_by(mail=normalized_email).first()
            assert record is not None
            assert record.verify_code == "1234"
            assert record.verify_code_send == 1

            message = message_from_string(_FakeSMTP.sent_message)
            assert _FakeSMTP.sent_to == normalized_email
            assert message["Subject"] == "AI-Shifu verification code"
            parts = {part.get_content_type(): part for part in message.walk()}
            assert "text/plain" in parts
            assert "text/html" in parts
            plain_body = parts["text/plain"].get_payload(decode=True).decode()
            html_body = parts["text/html"].get_payload(decode=True).decode()
            assert "Verification code: 1234" in plain_body
            assert "It expires in 5 minutes" in plain_body
            assert "Verify your AI-Shifu account" in html_body
            assert "1234" in html_body
            assert "Please do not reply" in html_body

            with pytest.raises(AppError) as exc_info:
                user_utils.send_email_code(app, raw_email)
            assert exc_info.value.code == 1033
        finally:
            UserVerifyCode.query.filter(
                UserVerifyCode.mail.in_([raw_email, normalized_email])
            ).delete(synchronize_session=False)
            db.session.commit()


@pytest.mark.parametrize(
    ("policy_name", "identifier", "next_identifier", "expected_rate_code"),
    [
        ("_SMS_CHALLENGE_POLICY", "13800138000", "13800138001", 1012),
        (
            "_EMAIL_CHALLENGE_POLICY",
            "learner@example.com",
            "next@example.com",
            1033,
        ),
    ],
)
def test_prepare_verification_challenge_shares_limits_and_persistence(
    monkeypatch: object,
    policy_name: str,
    identifier: str,
    next_identifier: str,
    expected_rate_code: int,
) -> None:
    from types import SimpleNamespace

    import flaskr.service.user.utils as user_utils
    from flaskr.service.common.models import AppError

    from tests.common.fixtures.fake_redis import FakeRedis

    fake_redis = FakeRedis()
    captured_records: list[dict[str, object]] = []
    lock_observations: list[bool] = []
    monkeypatch.setattr(user_utils, "redis", fake_redis, raising=False)
    monkeypatch.setattr(user_utils.time, "time", lambda: 100)
    monkeypatch.setattr(
        user_utils.secrets,
        "choice",
        lambda _characters: "1",
    )

    def _capture_record(**kwargs: object) -> object:
        lock_key = fake_app.config[policy.code_prefix_config] + (
            f"attempts:{identifier}:lock"
        )
        lock_observations.append(fake_redis._locks.get(lock_key, False))
        captured_records.append(kwargs)
        return SimpleNamespace(verify_code_send=0)

    monkeypatch.setattr(
        user_utils,
        "create_and_commit_user_verify_code",
        _capture_record,
    )
    monkeypatch.setattr(
        user_utils,
        "_redis_prefix",
        lambda current_app, config_key: current_app.config[config_key],
    )

    fake_app = SimpleNamespace(
        config={
            "REDIS_KEY_PREFIX_IP_BAN": "test:ip-ban:",
            "REDIS_KEY_PREFIX_IP_LIMIT": "test:ip-limit:",
            "REDIS_KEY_PREFIX_PHONE_LIMIT": "test:phone-limit:",
            "REDIS_KEY_PREFIX_PHONE_CODE": "test:phone-code:",
            "REDIS_KEY_PREFIX_MAIL_LIMIT": "test:mail-limit:",
            "REDIS_KEY_PREFIX_MAIL_CODE": "test:mail-code:",
            "IP_SMS_LIMIT_COUNT": 2,
            "IP_SMS_LIMIT_TIME": 60,
            "IP_MAIL_LIMIT_COUNT": 2,
            "IP_MAIL_LIMIT_TIME": 60,
            "IP_BAN_TIME": 300,
            "SMS_CODE_INTERVAL": 60,
            "PHONE_CODE_EXPIRE_TIME": 300,
            "MAIL_CODE_INTERVAL": 60,
            "MAIL_CODE_EXPIRE_TIME": 300,
        }
    )
    policy = getattr(user_utils, policy_name)
    challenge = user_utils._prepare_verification_challenge(
        fake_app,
        identifier,
        "203.0.113.10",
        policy,
    )

    assert challenge.code == "1111"
    assert challenge.expire_in == 300
    assert (
        fake_redis.get(
            user_utils._redis_prefix(fake_app, policy.code_prefix_config) + identifier
        )
        == b"1111"
    )
    assert captured_records == [
        {
            "mail": identifier if policy.verify_code_type == 2 else None,
            "phone": identifier if policy.verify_code_type == 1 else None,
            "verify_code": "1111",
            "verify_code_type": policy.verify_code_type,
            "ip": "203.0.113.10",
        }
    ]
    assert lock_observations == [True]
    assert fake_redis._locks == {}

    with pytest.raises(AppError) as rate_error:
        user_utils._prepare_verification_challenge(
            fake_app,
            identifier,
            "203.0.113.10",
            policy,
        )
    assert rate_error.value.code == expected_rate_code

    with pytest.raises(AppError) as ip_error:
        user_utils._prepare_verification_challenge(
            fake_app,
            next_identifier,
            "203.0.113.10",
            policy,
        )
    assert ip_error.value.code == 9999


def test_send_email_code_uses_implicit_ssl_and_closes_failed_connection(
    app: object, monkeypatch: object
) -> None:
    import flaskr.service.user.utils as user_utils
    from flaskr.dao import db
    from flaskr.service.common.models import AppError
    from flaskr.service.user.models import UserVerifyCode

    from tests.common.fixtures.fake_redis import FakeRedis

    class _FailingSMTPSSL:
        initialized_with: tuple[object, object] | None = None
        quit_called = False

        def __init__(self, server: object, port: object) -> None:
            type(self).initialized_with = (server, port)

        def login(self, *_args: object) -> None:
            return None

        def sendmail(self, *_args: object) -> None:
            message = "simulated send failure"
            raise RuntimeError(message)

        def quit(self) -> None:
            type(self).quit_called = True

    fake_redis = FakeRedis()
    monkeypatch.setattr(user_utils, "redis", fake_redis, raising=False)
    monkeypatch.setattr(user_utils.smtplib, "SMTP_SSL", _FailingSMTPSSL)
    monkeypatch.setattr(
        user_utils.smtplib,
        "SMTP",
        lambda *_args, **_kwargs: pytest.fail("STARTTLS must not be used for port 465"),
    )
    fixed_digits = iter("2468")
    monkeypatch.setattr(user_utils.secrets, "choice", lambda _chars: next(fixed_digits))

    email = "ssl@example.com"
    smtp_config = {
        "REDIS_KEY_PREFIX_MAIL_CODE": "test:mail:",
        "REDIS_KEY_PREFIX_MAIL_LIMIT": "test:mail-limit:",
        "MAIL_CODE_EXPIRE_TIME": "300",
        "MAIL_CODE_INTERVAL": "60",
        "SMTP_SENDER": "sender@example.com",
        "SMTP_SERVER": "smtp.example.com",
        "SMTP_PORT": "465",
        "SMTP_USERNAME": "sender@example.com",
        "SMTP_PASSWORD": "secret",
    }
    for key, value in smtp_config.items():
        monkeypatch.setenv(key, value)
        app.config.enhanced._cache.pop(key, None)

    with app.app_context():
        try:
            with pytest.raises(AppError):
                user_utils.send_email_code(app, email)

            assert _FailingSMTPSSL.initialized_with == ("smtp.example.com", 465)
            assert _FailingSMTPSSL.quit_called is True
        finally:
            UserVerifyCode.query.filter_by(mail=email).delete(synchronize_session=False)
            db.session.commit()
            for key in smtp_config:
                app.config.enhanced._cache.pop(key, None)


def test_send_email_code_uses_requested_language_and_singular_expiry(
    app: object, monkeypatch: object
) -> None:
    from email import message_from_string
    from email.header import decode_header, make_header

    import flaskr.service.user.utils as user_utils
    from flaskr.dao import db
    from flaskr.service.user.models import UserVerifyCode

    from tests.common.fixtures.fake_redis import FakeRedis

    class _FakeSMTP:
        sent_message = ""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def starttls(self) -> None:
            return None

        def login(self, *_args: object) -> None:
            return None

        def sendmail(
            self, _sender: object, _recipient: object, message: object
        ) -> None:
            type(self).sent_message = message

        def quit(self) -> None:
            return None

    fake_redis = FakeRedis()
    monkeypatch.setattr(user_utils, "redis", fake_redis, raising=False)
    monkeypatch.setattr(user_utils.smtplib, "SMTP", _FakeSMTP, raising=False)
    fixed_digits = iter("5678")
    monkeypatch.setattr(user_utils.secrets, "choice", lambda _chars: next(fixed_digits))

    with app.app_context():
        app.config.update(
            REDIS_KEY_PREFIX_MAIL_CODE="test:mail:",
            REDIS_KEY_PREFIX_MAIL_LIMIT="test:mail-limit:",
            MAIL_CODE_INTERVAL=60,
            SMTP_SENDER="sender@example.com",
            SMTP_SERVER="smtp.example.com",
            SMTP_PORT=587,
            SMTP_USERNAME="sender@example.com",
            SMTP_PASSWORD="secret",
        )
        original_expire_time = app.config["MAIL_CODE_EXPIRE_TIME"]
        app.config["MAIL_CODE_EXPIRE_TIME"] = 60
        user_utils.set_language("en-US")
        email = "french@example.com"
        try:
            user_utils.send_email_code(app, email, language="fr-FR")

            message = message_from_string(_FakeSMTP.sent_message)
            subject = str(make_header(decode_header(message["Subject"])))
            assert subject == "Code de vérification AI-Shifu"
            parts = {part.get_content_type(): part for part in message.walk()}
            plain_body = parts["text/plain"].get_payload(decode=True).decode()
            html_body = parts["text/html"].get_payload(decode=True).decode()
            assert "Code de vérification : 5678" in plain_body
            assert "Il expire dans une minute." in plain_body
            assert "1 minutes" not in plain_body
            assert "Ce code expire dans une minute." in html_body
            assert "1 minutes" not in html_body
            assert '<html lang="fr-FR" dir="ltr">' in html_body

            _subject, _plain_body, arabic_html_body = (
                user_utils._format_email_verification_message(
                    "5678", 60, language="ar-SA"
                )
            )
            assert '<html lang="ar-SA" dir="rtl">' in arabic_html_body

            arabic_subject, _plain_body, arabic_variant_html_body = (
                user_utils._format_email_verification_message(
                    "5678", 60, language="ar-AE"
                )
            )
            assert arabic_subject == "رمز التحقق من AI-Shifu"
            assert '<html lang="ar-SA" dir="rtl">' in arabic_variant_html_body

            for expire_seconds, expected_duration in (
                (120, "دقيقتين"),
                (300, "5 دقائق"),
                (660, "11 دقيقةً"),
                (6000, "100 دقيقة"),
            ):
                _subject, arabic_plain_body, arabic_plural_html_body = (
                    user_utils._format_email_verification_message(
                        "5678", expire_seconds, language="ar-SA"
                    )
                )
                assert expected_duration in arabic_plain_body
                assert expected_duration in arabic_plural_html_body

            thai_subject, _plain_body, thai_html_body = (
                user_utils._format_email_verification_message("5678", 60, language="th")
            )
            assert thai_subject == "รหัสยืนยัน AI-Shifu"
            assert '<html lang="th-TH" dir="ltr">' in thai_html_body
            assert user_utils.get_current_language() == "en-US"
        finally:
            app.config["MAIL_CODE_EXPIRE_TIME"] = original_expire_time
            UserVerifyCode.query.filter_by(mail=email).delete(synchronize_session=False)
            db.session.commit()


def test_phone_flow_verifies_code_from_db_when_cache_missing(app: object) -> None:
    from flaskr.dao import db
    from flaskr.service.user import phone_flow
    from flaskr.service.user.models import UserVerifyCode

    with app.app_context():
        app.config["UNIVERSAL_VERIFICATION_CODE"] = "9999"
        app.config["ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO"] = False
        phone_flow.redis = _FakeRedis()

        phone = "15500002222"
        code = "1234"
        record = UserVerifyCode(
            phone=phone,
            mail="",
            verify_code=code,
            verify_code_type=1,
            verify_code_send=1,
            verify_code_used=0,
            user_ip="",
        )
        db.session.add(record)
        db.session.commit()

        token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code=code
        )
        assert token is not None

        updated = UserVerifyCode.query.filter_by(id=record.id).first()
        assert updated is not None
        assert updated.verify_code_used == 1


def test_phone_flow_normalizes_cn_prefix_when_verifying_db_code(app: object) -> None:
    from flaskr.dao import db
    from flaskr.service.user import phone_flow
    from flaskr.service.user.models import AuthCredential, UserVerifyCode
    from flaskr.service.user.models import UserInfo as UserEntity

    with app.app_context():
        app.config["UNIVERSAL_VERIFICATION_CODE"] = "9999"
        app.config["ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO"] = False
        phone_flow.redis = _FakeRedis()

        _reset_user_auth_tables()
        phone = "15500005555"
        code = "1234"
        record = UserVerifyCode(
            phone=phone,
            mail="",
            verify_code=code,
            verify_code_type=1,
            verify_code_send=1,
            verify_code_used=0,
            user_ip="",
        )
        db.session.add(record)
        db.session.commit()
        try:
            token, _created, _ctx = phone_flow.verify_phone_code(
                app, user_id=None, phone=f"+86{phone}", code=code
            )

            entity = UserEntity.query.filter_by(user_bid=token.userInfo.user_id).first()
            assert entity is not None
            assert entity.user_identify == phone
            credential = AuthCredential.query.filter_by(
                provider_name="phone",
                identifier=phone,
                user_bid=entity.user_bid,
            ).first()
            assert credential is not None

            updated = UserVerifyCode.query.filter_by(id=record.id).first()
            assert updated is not None
            assert updated.verify_code_used == 1
        finally:
            UserVerifyCode.query.filter_by(id=record.id).delete()
            _reset_user_auth_tables()


def test_phone_flow_accepts_prefixed_pending_db_code(app: object) -> None:
    from flaskr.dao import db
    from flaskr.service.user import phone_flow
    from flaskr.service.user.models import AuthCredential, UserVerifyCode
    from flaskr.service.user.models import UserInfo as UserEntity

    with app.app_context():
        app.config["UNIVERSAL_VERIFICATION_CODE"] = "9999"
        app.config["ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO"] = False
        phone_flow.redis = _FakeRedis()

        _reset_user_auth_tables()
        phone = "15500006666"
        code = "1234"
        record = UserVerifyCode(
            phone=f"+86{phone}",
            mail="",
            verify_code=code,
            verify_code_type=1,
            verify_code_send=1,
            verify_code_used=0,
            user_ip="",
        )
        db.session.add(record)
        db.session.commit()
        try:
            token, _created, _ctx = phone_flow.verify_phone_code(
                app, user_id=None, phone=f"+86{phone}", code=code
            )

            entity = UserEntity.query.filter_by(user_bid=token.userInfo.user_id).first()
            assert entity is not None
            assert entity.user_identify == phone
            credential = AuthCredential.query.filter_by(
                provider_name="phone",
                identifier=phone,
                user_bid=entity.user_bid,
            ).first()
            assert credential is not None

            updated = UserVerifyCode.query.filter_by(id=record.id).first()
            assert updated is not None
            assert updated.verify_code_used == 1
        finally:
            UserVerifyCode.query.filter_by(id=record.id).delete()
            _reset_user_auth_tables()


def test_consume_verification_code_accepts_prefixed_pending_cache_key(
    app: object,
) -> None:
    from flaskr.dao import db
    from flaskr.service.user import verification_codes
    from flaskr.service.user.models import UserVerifyCode

    with app.app_context():
        phone = "15500007777"
        code = "1234"
        prefix = app.config["REDIS_KEY_PREFIX_PHONE_CODE"]
        fake_redis = _FakeRedis({f"{prefix}+86{phone}": code})
        verification_codes.redis = fake_redis

        record = UserVerifyCode(
            phone=f"+86{phone}",
            mail="",
            verify_code=code,
            verify_code_type=1,
            verify_code_send=1,
            verify_code_used=0,
            user_ip="",
        )
        db.session.add(record)
        db.session.commit()
        try:
            verification_codes.consume_verification_code(
                app, identifier=f"+86{phone}", code=code
            )

            updated = UserVerifyCode.query.filter_by(id=record.id).first()
            assert updated is not None
            assert updated.verify_code_used == 1
            assert f"{prefix}{phone}" in fake_redis.deleted
            assert f"{prefix}+86{phone}" in fake_redis.deleted
        finally:
            UserVerifyCode.query.filter_by(id=record.id).delete()
            db.session.commit()


@pytest.mark.parametrize(
    ("identifier", "kind", "prefix_config"),
    [
        ("claimed@example.com", "email", "REDIS_KEY_PREFIX_MAIL_CODE"),
        ("15500008888", "sms", "REDIS_KEY_PREFIX_PHONE_CODE"),
    ],
)
def test_consumed_code_tombstone_blocks_db_fallback_before_commit(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    identifier: str,
    kind: str,
    prefix_config: str,
) -> None:
    from flaskr.service.common.models import AppError
    from flaskr.service.user import verification_codes

    code = "2468"
    code_key = app.config[prefix_config] + identifier
    attempt_key = f"{app.config[prefix_config]}attempts:{identifier}"
    fake_redis = _FakeRedis({code_key: code})
    verification_codes.redis = fake_redis
    db_fallback_calls: list[tuple[str, str]] = []

    def _consume_without_committing(
        _app: object,
        *,
        kind: str,
        identifier: str,
        code: str,
    ) -> str:
        _ = (_app, code)
        db_fallback_calls.append((kind, identifier))
        return "ok"

    monkeypatch.setattr(
        verification_codes,
        "_consume_latest_code_from_db",
        _consume_without_committing,
    )

    with app.app_context():
        verification_codes.consume_verification_code(
            app,
            identifier=identifier,
            code=code,
        )

        assert code_key not in fake_redis.values
        assert (
            fake_redis.values[attempt_key]
            == verification_codes.VERIFICATION_CODE_CONSUMED_MARKER
        )

        with pytest.raises(AppError):
            verification_codes.consume_verification_code(
                app,
                identifier=identifier,
                code=code,
            )

    assert db_fallback_calls == [(kind, identifier)]


def test_phone_flow_bootstrap_sets_draft_owner_for_published_demo(app: object) -> None:
    from flaskr.dao import db
    from flaskr.service.shifu.models import DraftShifu, PublishedShifu
    from flaskr.service.user import phone_flow
    from flaskr.service.user.models import UserInfo as UserEntity

    shifu_bid = uuid.uuid4().hex[:32]

    with app.app_context():
        app.config["UNIVERSAL_VERIFICATION_CODE"] = "9999"
        app.config["ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO"] = False
        phone_flow.redis = _FakeRedis()

        _reset_user_auth_tables()
        _reset_shifu_tables()
        try:
            db.session.add(
                PublishedShifu(
                    shifu_bid=shifu_bid,
                    title="Published demo",
                )
            )
            db.session.add(
                DraftShifu(
                    shifu_bid=shifu_bid,
                    title="Draft demo",
                )
            )
            db.session.commit()

            token, _created, _ctx = phone_flow.verify_phone_code(
                app,
                user_id=None,
                phone="15500003333",
                code="9999",
            )

            entity = UserEntity.query.filter_by(user_bid=token.userInfo.user_id).first()
            published = PublishedShifu.query.filter_by(shifu_bid=shifu_bid).first()
            draft = DraftShifu.query.filter_by(shifu_bid=shifu_bid).first()

            assert entity is not None
            assert published is not None
            assert draft is not None
            assert published.created_user_bid == entity.user_bid
            assert draft.created_user_bid == entity.user_bid
        finally:
            _delete_shifu_pair(shifu_bid)
            _reset_user_auth_tables()


def test_email_flow_verifies_code_from_db_when_cache_missing(app: object) -> None:
    from flaskr.dao import db
    from flaskr.service.user import email_flow
    from flaskr.service.user.models import UserVerifyCode

    with app.app_context():
        app.config["UNIVERSAL_VERIFICATION_CODE"] = "9999"
        app.config["ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO"] = False
        email_flow.redis = _FakeRedis()

        email = "test.user@example.com"
        code = "5678"
        record = UserVerifyCode(
            phone="",
            mail=email,
            verify_code=code,
            verify_code_type=2,
            verify_code_send=1,
            verify_code_used=0,
            user_ip="",
        )
        db.session.add(record)
        db.session.commit()

        token, _created, _ctx = email_flow.verify_email_code(
            app, user_id=None, email=email, code=code
        )
        assert token is not None

        updated = UserVerifyCode.query.filter_by(id=record.id).first()
        assert updated is not None
        assert updated.verify_code_used == 1


def test_email_flow_invalidates_code_after_five_failed_attempts(app: object) -> None:
    from flaskr.dao import db
    from flaskr.service.common.models import ERROR_CODE, AppError
    from flaskr.service.user import email_flow
    from flaskr.service.user.models import UserVerifyCode

    with app.app_context():
        app.config["UNIVERSAL_VERIFICATION_CODE"] = "9999"
        app.config["ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO"] = False

        email = "limited@example.com"
        code = "5678"
        code_key = app.config["REDIS_KEY_PREFIX_MAIL_CODE"] + email
        attempt_key = f"{app.config['REDIS_KEY_PREFIX_MAIL_CODE']}attempts:{email}"
        fake_redis = _FakeRedis({code_key: code})
        email_flow.redis = fake_redis

        record = UserVerifyCode(
            phone="",
            mail=email,
            verify_code=code,
            verify_code_type=2,
            verify_code_send=1,
            verify_code_used=0,
            user_ip="",
        )
        db.session.add(record)
        db.session.commit()

        for _attempt in range(5):
            with pytest.raises(AppError) as exc_info:
                email_flow.verify_email_code(
                    app,
                    user_id=None,
                    email=email,
                    code="0000",
                )
            assert exc_info.value.code == ERROR_CODE["server.common.unknownError"]

        assert fake_redis.values[attempt_key] == 5
        assert code_key not in fake_redis.values

        with pytest.raises(AppError) as exc_info:
            email_flow.verify_email_code(
                app,
                user_id=None,
                email=email,
                code=code,
            )
        assert exc_info.value.code == ERROR_CODE["server.common.unknownError"]

        updated = UserVerifyCode.query.filter_by(id=record.id).first()
        assert updated is not None
        assert updated.verify_code_used == 0
