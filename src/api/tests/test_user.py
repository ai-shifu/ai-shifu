from flaskr.dao import db
from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.user.models import UserInfo


def test_get_user_profiles_uses_user_fallbacks(app):
    with app.app_context():
        user = UserInfo(
            user_bid="user-profile-1",
            user_identify="user-profile@example.com",
            nickname="Tester",
            language="zh-CN",
        )
        db.session.add(user)
        db.session.commit()

        profiles = get_user_profiles(app, "user-profile-1", "course-1")
        assert profiles["sys_user_language"] == "zh-CN"
        assert profiles["sys_user_nickname"] == "Tester"
