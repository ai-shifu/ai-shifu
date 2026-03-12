class _FakeRedis:
    def get(self, key):
        return None

    def delete(self, key):
        return 1


def test_phone_flow_sets_user_identify(app):
    import flaskr.service.user.phone_flow as phone_flow
    from flaskr.dao import db
    from flaskr.service.user.models import UserInfo as UserEntity
    from flaskr.service.user.models import UserVerifyCode

    with app.app_context():
        # Monkeypatch redis in module scope
        phone_flow.redis = _FakeRedis()

        phone = "15500001111"
        code = "9999"
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
        token, created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code=code
        )

        # Verify persisted identifier on entity
        entity = UserEntity.query.filter_by(user_bid=token.userInfo.user_id).first()
        assert entity is not None
        assert entity.user_identify == phone


def test_email_flow_sets_user_identify(app):
    import flaskr.service.user.email_flow as email_flow
    from flaskr.dao import db
    from flaskr.service.user.models import UserInfo as UserEntity
    from flaskr.service.user.models import UserVerifyCode

    with app.app_context():
        email_flow.redis = _FakeRedis()

        raw_email = "TestUser@Example.com"
        code = "9999"
        record = UserVerifyCode(
            phone="",
            mail=raw_email.lower(),
            verify_code=code,
            verify_code_type=2,
            verify_code_send=1,
            verify_code_used=0,
            user_ip="",
        )
        db.session.add(record)
        db.session.commit()
        token, created, _ctx = email_flow.verify_email_code(
            app, user_id=None, email=raw_email, code=code
        )

        entity = UserEntity.query.filter_by(user_bid=token.userInfo.user_id).first()
        assert entity is not None
        assert entity.user_identify == raw_email.lower()


def test_phone_flow_verifies_code_from_db_when_cache_missing(app):
    import flaskr.service.user.phone_flow as phone_flow
    from flaskr.dao import db
    from flaskr.service.user.models import UserVerifyCode

    with app.app_context():
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


def test_email_flow_verifies_code_from_db_when_cache_missing(app):
    import flaskr.service.user.email_flow as email_flow
    from flaskr.dao import db
    from flaskr.service.user.models import UserVerifyCode

    with app.app_context():
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
