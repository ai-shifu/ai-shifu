import uuid


class _FakeRedis:
    def get(self, key):
        return None

    def delete(self, key):
        return 1


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
