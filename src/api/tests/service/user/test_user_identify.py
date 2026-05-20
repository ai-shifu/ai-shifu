import uuid


class _FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.deleted = []

    def get(self, key):
        return self.values.get(key)

    def delete(self, *keys):
        self.deleted.extend(keys)
        return len(keys)


def _reset_user_auth_tables():
    from flaskr.dao import db
    from flaskr.service.user.models import (
        AuthCredential,
        UserInfo as UserEntity,
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


def test_phone_flow_sets_user_identify(app):
    import flaskr.service.user.phone_flow as phone_flow
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


def test_email_flow_sets_user_identify(app):
    import flaskr.service.user.email_flow as email_flow
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


def test_send_email_code_stores_lowercase_identifier(app, monkeypatch):
    import flaskr.service.user.utils as user_utils
    from flaskr.dao import db
    from flaskr.service.user.models import UserVerifyCode
    from tests.common.fixtures.fake_redis import FakeRedis

    class _FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            self.sent_to = None

        def starttls(self):
            return None

        def login(self, *_args):
            return None

        def sendmail(self, _sender, recipient, _message):
            self.sent_to = recipient
            return None

        def quit(self):
            return None

    fake_redis = FakeRedis()
    monkeypatch.setattr(user_utils, "redis", fake_redis, raising=False)
    monkeypatch.setattr(user_utils.smtplib, "SMTP", _FakeSMTP, raising=False)
    monkeypatch.setattr(user_utils.random, "choices", lambda _chars, k: list("1234"))

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
        finally:
            UserVerifyCode.query.filter(
                UserVerifyCode.mail.in_([raw_email, normalized_email])
            ).delete(synchronize_session=False)
            db.session.commit()


def test_phone_flow_verifies_code_from_db_when_cache_missing(app):
    import flaskr.service.user.phone_flow as phone_flow
    from flaskr.dao import db
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


def test_phone_flow_normalizes_cn_prefix_when_verifying_db_code(app):
    import flaskr.service.user.phone_flow as phone_flow
    from flaskr.dao import db
    from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
    from flaskr.service.user.models import UserVerifyCode

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


def test_phone_flow_accepts_prefixed_pending_db_code(app):
    import flaskr.service.user.phone_flow as phone_flow
    from flaskr.dao import db
    from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
    from flaskr.service.user.models import UserVerifyCode

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


def test_consume_verification_code_accepts_prefixed_pending_cache_key(app):
    import flaskr.service.user.verification_codes as verification_codes
    from flaskr.dao import db
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


def test_phone_flow_bootstrap_sets_draft_owner_for_published_demo(app):
    import flaskr.service.user.phone_flow as phone_flow
    from flaskr.dao import db
    from flaskr.service.shifu.models import DraftShifu, PublishedShifu
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


def test_email_flow_verifies_code_from_db_when_cache_missing(app):
    import flaskr.service.user.email_flow as email_flow
    from flaskr.dao import db
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
