from flaskr.dao import db
from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.user.common import get_user_info, update_user_info
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


def test_get_user_profiles_prefers_user_entity_for_mapped_system_keys(app):
    with app.app_context():
        user = UserInfo(
            user_bid="user-profile-2",
            user_identify="user-profile-2@example.com",
            nickname="LatestName",
            language="en-US",
        )
        db.session.add(user)
        db.session.add(
            Variable(
                variable_bid="var-sys-user-nickname",
                shifu_bid="",
                key="sys_user_nickname",
                is_hidden=0,
                deleted=0,
            )
        )
        db.session.add(
            Variable(
                variable_bid="var-sys-user-language",
                shifu_bid="",
                key="sys_user_language",
                is_hidden=0,
                deleted=0,
            )
        )
        db.session.add(
            VariableValue(
                variable_value_bid="value-old-nickname",
                variable_bid="var-sys-user-nickname",
                shifu_bid="",
                user_bid="user-profile-2",
                key="sys_user_nickname",
                value="OldName",
                deleted=0,
            )
        )
        db.session.add(
            VariableValue(
                variable_value_bid="value-old-language",
                variable_bid="var-sys-user-language",
                shifu_bid="",
                user_bid="user-profile-2",
                key="sys_user_language",
                value="zh-CN",
                deleted=0,
            )
        )
        db.session.commit()

        profiles = get_user_profiles(app, "user-profile-2", "course-1")
        assert profiles["sys_user_nickname"] == "LatestName"
        assert profiles["sys_user_language"] == "en-US"


def test_update_user_info_updates_both_name_and_language_profiles(app):
    with app.app_context():
        user = UserInfo(
            user_bid="user-profile-3",
            user_identify="user-profile-3@example.com",
            nickname="Before",
            language="en-US",
        )
        db.session.add(user)
        db.session.commit()

        auth_user = get_user_info(app, "user-profile-3")
        update_user_info(app, auth_user, name="After", language="zh-CN")

        stored = (
            VariableValue.query.filter(
                VariableValue.user_bid == "user-profile-3",
                VariableValue.shifu_bid == "",
                VariableValue.deleted == 0,
                VariableValue.key.in_(["sys_user_nickname", "sys_user_language"]),
            )
            .order_by(VariableValue.id.asc())
            .all()
        )
        latest_by_key = {}
        for row in stored:
            latest_by_key[row.key] = row.value

        assert latest_by_key["sys_user_nickname"] == "After"
        assert latest_by_key["sys_user_language"] == "zh-CN"
