"""Verify user identify behavior."""

import uuid


class _FakeRedis:
    def __init__(self, values: object = None) -> None:
        self.values = dict(values or {})
        self.deleted = []

    def get(self, key: object) -> object:
        return self.values.get(key)

    def delete(self, *keys: str) -> object:
        self.deleted.extend(keys)
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
            token, _created, _ctx = email_flow.verify_email_code(
                app, user_id=None, email=raw_email, code="9999"
            )

            entity = UserEntity.query.filter_by(user_bid=token.userInfo.user_id).first()
            assert entity is not None
            assert entity.user_identify == raw_email.lower()
        finally:
            _reset_user_auth_tables()


def test_send_email_code_stores_lowercase_identifier(
    app: object, monkeypatch: object
) -> None:
    from email import message_from_string

    import flaskr.service.user.utils as user_utils
    from flaskr.dao import db
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
        finally:
            UserVerifyCode.query.filter(
                UserVerifyCode.mail.in_([raw_email, normalized_email])
            ).delete(synchronize_session=False)
            db.session.commit()


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
