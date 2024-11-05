from flask import Flask


from .models import UserProfile
from ...dao import db
from ..user.models import User
from ...i18n import _
import datetime


class UserProfileDTO:
    def __init__(self, user_id, profile_key, profile_value, profile_type):
        self.user_id = user_id
        self.profile_key = profile_key
        self.profile_value = profile_value
        self.profile_type = profile_type

    def __json__(self):
        return {
            "user_id": self.user_id,
            "profile_key": self.profile_key,
            "profile_value": self.profile_value,
            "profile_type": self.profile_type,
        }


def get_profile_labels():

    return {
        "nickname": {"label": _("PROFILE.NICKNAME"), "mapping": "name", "default": ""},
        "user_background": {"label": _("PROFILE.USER_BACKGROUND")},
        "sex": {
            "label": _("PROFILE.SEX"),
            "mapping": "user_sex",
            "items": [
                _("PROFILE.SEX_MALE"),
                _("PROFILE.SEX_FEMALE"),
                _("PROFILE.SEX_SECRET"),
            ],
            "items_mapping": {
                0: _("PROFILE.SEX_SECRET"),
                1: _("PROFILE.SEX_MALE"),
                2: _("PROFILE.SEX_FEMALE"),
            },
            "default": 0,
        },
        "birth": {
            "label": _("PROFILE.BIRTH"),
            "mapping": "user_birth",
            "type": "date",
            "default": datetime.date(2003, 1, 1),
        },
        "avatar": {
            "label": _("PROFILE.AVATAR"),
            "mapping": "user_avatar",
            "type": "image",
            "default": "",
        },
        "industry": {"label": _("PROFILE.INDUSTRY")},
        "occupation": {
            "label": _("PROFILE.OCCUPATION"),
        },
        "language": {
            "label": _("PROFILE.LANGUAGE"),
            "items": ["中文", "English"],
            "mapping": "user_language",
            "items_mapping": {"zh-CN": "中文", "en-US": "English"},
            "default": "zh-CN",
        },
        "ai_tools": {
            "label": _("PROFILE.AI_TOOLS"),
            "items": ["GitHub Copilot", "通义灵码"],
            "items_mapping": {
                "GitHub_Copilot": "GitHub Copilot",
                "通义灵码": "通义灵码",
                "Cursor": "Cursor",
            },
        },
        "style": {
            "label": _("PROFILE.STYLE"),
            "items": ["幽默风趣", "严肃专业", "鼓励温暖"],
        },
        "programming": {
            "label": _("PROFILE.PROGRAMMING"),
            "items": ["完全没接触过", "学过但还无法编写程序", "会1门及以上语言"],
        },
        "user_os": {
            "label": _("PROFILE.USER_OS"),
            "items": [
                "Windows",
                "MacOS",
            ],
            "items_mapping": {"win": "Windows", "mac": "MacOS"},
        },
    }


def get_user_profile_by_user_id(
    app: Flask, user_id: str, profile_key: str
) -> UserProfileDTO:
    user_profile = UserProfile.query.filter_by(
        user_id=user_id, profile_key=profile_key
    ).first()
    if user_profile:
        return UserProfileDTO(
            user_profile.user_id,
            user_profile.profile_key,
            user_profile.profile_value,
            user_profile.profile_type,
        )
    return None


def save_user_profile(
    user_id: str, profile_key: str, profile_value: str, profile_type: int
):
    PROFILES_LABLES = get_profile_labels()
    user_profile = UserProfile.query.filter_by(
        user_id=user_id, profile_key=profile_key
    ).first()
    user_info = User.query.filter(User.user_id == user_id).first()
    if user_profile:
        user_profile.profile_value = profile_value
        user_profile.profile_type = profile_type
    else:
        user_profile = UserProfile(
            user_id=user_id,
            profile_key=profile_key,
            profile_value=profile_value,
            profile_type=profile_type,
        )
        db.session.add(user_profile)
    if profile_key in PROFILES_LABLES:
        profile_lable = PROFILES_LABLES[profile_key]
        if profile_lable.get("mapping"):
            if profile_lable.get("items_mapping"):
                profile_value = profile_lable["items_mapping"].get(
                    profile_value, profile_value
                )
            setattr(user_info, profile_lable["mapping"], profile_value)
    db.session.flush()
    return UserProfileDTO(
        user_profile.user_id,
        user_profile.profile_key,
        user_profile.profile_value,
        user_profile.profile_type,
    )


def save_user_profiles(app: Flask, user_id: str, profiles: dict):
    PROFILES_LABLES = get_profile_labels()
    app.logger.info("save user profiles:{}".format(profiles))
    user_info = User.query.filter(User.user_id == user_id).first()
    for key, value in profiles.items():
        user_profile = UserProfile.query.filter_by(
            user_id=user_id, profile_key=key
        ).first()
        if user_profile:
            user_profile.profile_value = value
        else:
            user_profile = UserProfile(
                user_id=user_id, profile_key=key, profile_value=value, profile_type=1
            )
            db.session.add(user_profile)
        if key in PROFILES_LABLES:
            profile_lable = PROFILES_LABLES[key]
            if profile_lable.get("mapping"):
                if profile_lable.get("items_mapping"):
                    value = profile_lable["items_mapping"].get(value, value)
                setattr(user_info, profile_lable["mapping"], value)
    db.session.flush()
    return True


def get_user_profiles(app: Flask, user_id: str, keys: list = None) -> dict:
    user_profiles = UserProfile.query.filter_by(user_id=user_id).all()
    result = {}
    if keys is None:
        for user_profile in user_profiles:
            result[user_profile.profile_key] = user_profile.profile_value
        return result
    for user_profile in user_profiles:
        if user_profile.profile_key in keys:
            result[user_profile.profile_key] = user_profile.profile_value
    return result


def get_user_profile_labels(app: Flask, user_id: str):
    user_profiles = UserProfile.query.filter_by(user_id=user_id).all()
    user_info = User.query.filter(User.user_id == user_id).first()
    PROFILES_LABLES = get_profile_labels()
    result = []
    if user_info:
        for key in PROFILES_LABLES:
            if PROFILES_LABLES[key].get("mapping"):
                item = {
                    "key": key,
                    "label": PROFILES_LABLES[key]["label"],
                    "type": PROFILES_LABLES[key].get(
                        "type", "select" if "items" in PROFILES_LABLES[key] else "text"
                    ),
                    "value": getattr(user_info, PROFILES_LABLES[key]["mapping"]),
                    "items": PROFILES_LABLES[key].get("items"),
                }
                if PROFILES_LABLES[key].get("items_mapping"):
                    item["value"] = PROFILES_LABLES[key]["items_mapping"].get(
                        getattr(user_info, PROFILES_LABLES[key]["mapping"]),
                        PROFILES_LABLES[key].get("items")[0],
                    )

                result.append(item)

    for user_profile in user_profiles:
        if user_profile.profile_key in PROFILES_LABLES:
            items = [key for key in result if key["key"] == user_profile.profile_key]
            item = items[0] if len(items) > 0 else None
            app.logger.info(
                "user_profile:{}-{}".format(
                    user_profile.profile_key, user_profile.profile_value
                )
            )
            if item is None:
                item = {
                    "key": user_profile.profile_key,
                    "label": PROFILES_LABLES[user_profile.profile_key]["label"],
                    "type": PROFILES_LABLES[user_profile.profile_key].get(
                        "type",
                        (
                            "select"
                            if "items" in PROFILES_LABLES[user_profile.profile_key]
                            else "text"
                        ),
                    ),
                    "value": user_profile.profile_value,
                    "items": (
                        PROFILES_LABLES[user_profile.profile_key]["items"]
                        if "items" in PROFILES_LABLES[user_profile.profile_key]
                        else None
                    ),
                }
                result.append(item)

            if PROFILES_LABLES[user_profile.profile_key].get("items_mapping"):
                item["value"] = PROFILES_LABLES[user_profile.profile_key][
                    "items_mapping"
                ][user_profile.profile_value]
            else:
                item["value"] = user_profile.profile_value
    return result


def update_user_profile_with_lable(app: Flask, user_id: str, profiles: list):
    PROFILES_LABLES = get_profile_labels()
    user_info = User.query.filter(User.user_id == user_id).first()
    if user_info:
        user_profiles = UserProfile.query.filter_by(user_id=user_id).all()
        for profile in profiles:
            app.logger.info(
                "update user profile:{}-{}".format(profile["key"], profile["value"])
            )
            user_profile_to_update = [
                p for p in user_profiles if p.profile_key == profile["key"]
            ]
            user_profile = (
                user_profile_to_update[0] if len(user_profile_to_update) > 0 else None
            )
            profile_lable = PROFILES_LABLES.get(profile["key"], None)
            profile_value = profile["value"]
            if profile_lable:
                if profile_lable.get("items_mapping"):
                    for k, v in profile_lable["items_mapping"].items():
                        if v == profile_value:
                            profile_value = k
                default_value = profile_lable.get("default", None)
                app.logger.info(
                    "default_value:{}, profile_value:{}".format(
                        default_value, profile_value
                    )
                )
                if (
                    profile_lable.get("mapping")
                    and (profile_value != default_value)
                    and getattr(user_info, profile_lable["mapping"]) != profile_value
                ):
                    app.logger.info(
                        "update user info: {} - {}".format(profile, profile_value)
                    )
                    setattr(user_info, profile_lable["mapping"], profile_value)
            else:
                app.logger.info("profile_lable not found:{}".format(profile["key"]))
            if user_profile and (profile_value != default_value):
                user_profile.profile_value = profile_value
        db.session.flush()
        return True
