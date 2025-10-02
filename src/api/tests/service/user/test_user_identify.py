class _FakeRedis:
    def get(self, key):
        return None

    def delete(self, key):
        return 1


def test_phone_flow_sets_user_identify(app):
    from flaskr.service.user import phone_flow
    from flaskr.service.user.models import UserInfo as UserEntity

    # Bypass code storage by using universal code
    with app.app_context():
        app.config["UNIVERSAL_VERIFICATION_CODE"] = "9999"

        # Monkeypatch redis in module scope
        phone_flow.redis = _FakeRedis()

        phone = "15500001111"
        token, created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code="9999"
        )

        # Verify persisted identifier on entity
        entity = UserEntity.query.filter_by(user_bid=token.userInfo.user_id).first()
        assert entity is not None
        assert entity.user_identify == phone


def test_email_flow_sets_user_identify(app):
    from flaskr.service.user import email_flow
    from flaskr.service.user.models import UserInfo as UserEntity

    with app.app_context():
        app.config["UNIVERSAL_VERIFICATION_CODE"] = "9999"
        email_flow.redis = _FakeRedis()

        raw_email = "TestUser@Example.com"
        token, created, _ctx = email_flow.verify_email_code(
            app, user_id=None, email=raw_email, code="9999"
        )

        entity = UserEntity.query.filter_by(user_bid=token.userInfo.user_id).first()
        assert entity is not None
        assert entity.user_identify == raw_email.lower()
