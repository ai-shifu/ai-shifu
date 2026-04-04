import uuid
from types import SimpleNamespace

from flaskr.dao import db
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.utils import (
    ensure_admin_creator_and_demo_permissions,
    get_user_language,
)


def test_get_user_language_supports_language_attribute():
    user = SimpleNamespace(language="zh-CN")

    assert get_user_language(user) == "zh-CN"


def test_get_user_language_supports_user_language_attribute():
    user = SimpleNamespace(user_language="en_US")

    assert get_user_language(user) == "en-US"


def test_admin_login_auto_grant_keeps_operator_unchanged(app):
    user_bid = uuid.uuid4().hex[:32]

    with app.app_context():
        user = UserEntity(
            user_bid=user_bid,
            user_identify=f"{user_bid}@example.com",
            nickname="OperatorCheck",
            language="en-US",
            state=USER_STATE_REGISTERED,
        )
        db.session.add(user)
        db.session.commit()

        ensure_admin_creator_and_demo_permissions(
            app,
            user_bid,
            "en-US",
            "admin",
        )
        db.session.commit()

        stored = UserEntity.query.filter_by(user_bid=user_bid).first()
        assert stored is not None
        assert stored.is_creator == 1
        assert stored.is_operator == 0
