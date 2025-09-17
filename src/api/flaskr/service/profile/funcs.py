from flask import Flask


from .models import UserProfile
from ...dao import db
from ..user.models import User
from ..user.utils import get_user_language
from ...i18n import _
import datetime
from ..check_risk.funcs import add_risk_control_result
from flaskr.api.check import (
    check_text,
    CHECK_RESULT_PASS,
    CHECK_RESULT_REJECT,
)
from flaskr.util.uuid import generate_id
from flaskr.service.common import raise_error
from flaskr.service.profile.profile_manage import get_profile_item_definition_list
from flaskr.service.profile.models import (
    PROFILE_TYPE_INPUT_SELECT,
    PROFILE_TYPE_INPUT_TEXT,
    CONST_PROFILE_TYPE_OPTION,
)
from flaskr.service.profile.dtos import ProfileToSave


SYS_USER_LANGUAGE = "sys_user_language"

_LANGUAGE_BASE_DISPLAY = {
    "en": "English",
    "zh": "中文",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "ja": "日本語",
    "ko": "한국어",
    "ru": "Русский",
    "it": "Italiano",
    "pt": "Português",
    "ar": "العربية",
    "hi": "हिंदी",
    "vi": "Tiếng Việt",
    "th": "ไทย",
    "id": "Bahasa Indonesia",
    "ms": "Bahasa Melayu",
    "tr": "Türkçe",
    "pl": "Polski",
}

_LANGUAGE_SPECIFIC_DISPLAY = {
    "zh-TW": "繁体中文",
    "zh-HK": "繁体中文",
    "zh-MO": "繁体中文",
    "zh-Hant": "繁体中文",
}

_DEFAULT_LANGUAGE_DISPLAY = "English"


def _language_display_value(language_code: str) -> str:
    """Return a human readable representation for a language code."""
    if not language_code:
        return _DEFAULT_LANGUAGE_DISPLAY

    if language_code in _LANGUAGE_SPECIFIC_DISPLAY:
        return _LANGUAGE_SPECIFIC_DISPLAY[language_code]

    base_code = language_code.split("-")[0]
    return _LANGUAGE_BASE_DISPLAY.get(base_code, language_code)


def check_text_content(
    app: Flask,
    user_id: str,
    input: str,
):
    check_id = generate_id(app)
    res = check_text(app, check_id, input, user_id)
    add_risk_control_result(
        app,
        check_id,
        user_id,
        input,
        res.provider,
        res.check_result,
        str(res.raw_data),
        1 if res.check_result == CHECK_RESULT_PASS else 0,
        "check_text",
    )
    if res.check_result == CHECK_RESULT_REJECT:
        return False
    return True


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


def get_profile_labels(course_id: str = None):
    # language = get_current_language()
    return {
        "sys_user_nickname": {
            "label": _("PROFILE.NICKNAME"),
            "mapping": "name",
            "default": "",
        },
        "sys_user_background": {"label": _("PROFILE.USER_BACKGROUND")},
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
        "language": {
            "label": _("PROFILE.LANGUAGE"),
            "items": ["中文", "English"],
            "mapping": "user_language",
            "items_mapping": {"zh-CN": "中文", "en-US": "English"},
            "default": "zh-CN",
        },
        "sys_user_style": {
            "label": _("PROFILE.STYLE"),
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
            profile_id="",
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


def save_user_profiles(
    app: Flask, user_id: str, course_id: str, profiles: list[ProfileToSave]
):
    PROFILES_LABLES = get_profile_labels()
    app.logger.info("save user profiles:{}".format(profiles))
    user_info = User.query.filter(User.user_id == user_id).first()
    profiles_items = get_profile_item_definition_list(app, course_id)
    for profile in profiles:
        profile_item = next(
            (item for item in profiles_items if item.profile_key == profile.key), None
        )
        profile_id = ""
        if profile_item:
            profile_type = (
                PROFILE_TYPE_INPUT_SELECT
                if profile_item.profile_type == CONST_PROFILE_TYPE_OPTION
                else PROFILE_TYPE_INPUT_TEXT
            )
            profile_id = profile_item.profile_id
            app.logger.info("profile_id:{}".format(profile_id))
        else:
            profile_type = 1
            profile_id = ""
        user_profile: UserProfile = (
            UserProfile.query.filter(
                UserProfile.user_id == user_id,
                UserProfile.profile_id == profile_id,
            )
            .order_by(UserProfile.id.desc())
            .first()
        )
        if not user_profile:
            user_profile: UserProfile = (
                UserProfile.query.filter(
                    UserProfile.user_id == user_id,
                    UserProfile.profile_key == profile.key,
                )
                .order_by(UserProfile.id.desc())
                .first()
            )
        if user_profile:
            user_profile.profile_value = profile.value
            user_profile.profile_type = profile_type
            user_profile.profile_id = profile_id
            user_profile.status = 1
        else:
            user_profile = UserProfile(
                user_id=user_id,
                profile_key=profile.key,
                profile_value=profile.value,
                profile_type=profile_type,
                profile_id=profile_id,
                status=1,
            )
            db.session.add(user_profile)
        if profile.key in PROFILES_LABLES:
            profile_lable = PROFILES_LABLES[profile.key]
            if profile_lable.get("mapping"):
                if profile_lable.get("items_mapping"):
                    profile.value = profile_lable["items_mapping"].get(
                        profile.value, profile.value
                    )
                setattr(user_info, profile_lable["mapping"], profile.value)
    db.session.flush()
    return True


def get_user_profiles(app: Flask, user_id: str, course_id: str) -> dict:
    """
    Get user profiles
    Args:
        app: Flask application instance
        user_id: User id
        course_id: Course id
    Returns:
        dict: User profiles
    """
    profiles_items = get_profile_item_definition_list(app, course_id)
    user_profiles = UserProfile.query.filter_by(user_id=user_id).all()
    user_info = User.query.filter(User.user_id == user_id).first()
    result = {}

    language_code = get_user_language(user_info) if user_info else None
    result[SYS_USER_LANGUAGE] = _language_display_value(language_code)

    for profile_item in profiles_items:
        user_profile = next(
            (
                item
                for item in user_profiles
                if item.profile_id == profile_item.profile_id
            ),
            None,
        )
        if not user_profile:
            user_profile = next(
                (
                    item
                    for item in user_profiles
                    if item.profile_key == profile_item.profile_key
                ),
                None,
            )
        if user_profile:
            result[profile_item.profile_key] = user_profile.profile_value
    return result


def get_user_profile_labels(app: Flask, user_id: str, course_id: str) -> list:
    """
    Get user profile labels
    Args:
        app: Flask application instance
        user_id: User id
        course_id: Course id
    Returns:
        list: User profile labels
    """
    app.logger.info("get user profile labels:{}".format(course_id))
    user_profiles: list[UserProfile] = (
        UserProfile.query.filter_by(user_id=user_id)
        .order_by(UserProfile.id.desc())
        .all()
    )
    user_info: User = User.query.filter(User.user_id == user_id).first()
    profiles_items = get_profile_item_definition_list(app, course_id)
    PROFILES_LABLES = get_profile_labels()
    result = []
    mapping_keys = []
    if user_info:
        for key in PROFILES_LABLES.keys():
            if PROFILES_LABLES[key].get("mapping"):
                mapping_keys.append(key)
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
    for key in PROFILES_LABLES.keys():
        if key in mapping_keys:
            continue
        profile_key = key
        item = {
            "key": profile_key,
            "label": PROFILES_LABLES[profile_key]["label"],
            "type": PROFILES_LABLES[profile_key].get(
                "type",
                ("select" if "items" in PROFILES_LABLES[profile_key] else "text"),
            ),
            "value": "",
            "items": (
                PROFILES_LABLES[profile_key]["items"]
                if "items" in PROFILES_LABLES[profile_key]
                else None
            ),
        }
        profile_item = next(
            (item for item in profiles_items if item.profile_key == profile_key), None
        )
        if profile_item:
            user_profile = next(
                (
                    item
                    for item in user_profiles
                    if item.profile_id == profile_item.profile_id
                ),
                None,
            )
        else:
            app.logger.info("profile_item not found:{}".format(profile_key))
        if not user_profile:
            user_profile = next(
                (item for item in user_profiles if item.profile_key == profile_key),
                None,
            )
        if user_profile:
            app.logger.info("user_profile:{}".format(user_profile.profile_value))
            item["value"] = user_profile.profile_value
        result.append(item)
    return result


def update_user_profile_with_lable(
    app: Flask,
    user_id: str,
    profiles: list,
    update_all: bool = False,
    course_id: str = None,
):
    app.logger.info("update user profile with lable:{}".format(course_id))
    PROFILES_LABLES = get_profile_labels(course_id)
    user_info = User.query.filter(User.user_id == user_id).first()
    profile_items = get_profile_item_definition_list(app, course_id)
    if user_info:
        # check nickname
        nickname = [p for p in profiles if p["key"] == "sys_user_nickname"]
        if nickname and not check_text_content(app, user_id, nickname[0]["value"]):
            raise_error("COMMON.NICKNAME_NOT_ALLOWED")
        background = [p for p in profiles if p["key"] == "sys_user_background"]
        if background and not check_text_content(app, user_id, background[0]["value"]):
            raise_error("COMMON.BACKGROUND_NOT_ALLOWED")
        user_profiles = (
            UserProfile.query.filter_by(user_id=user_id)
            .order_by(UserProfile.id.desc())
            .all()
        )
        for profile in profiles:
            profile_item = next(
                (item for item in profile_items if item.profile_key == profile["key"]),
                None,
            )
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
                if profile_lable.get("mapping") and (
                    update_all
                    or (
                        (profile_value != default_value)
                        and getattr(user_info, profile_lable["mapping"])
                        != profile_value
                    )
                ):
                    app.logger.info(
                        "update user info: {} - {}".format(profile, profile_value)
                    )
                    setattr(user_info, profile_lable["mapping"], profile_value)
            else:
                app.logger.info("profile_lable not found:{}".format(profile["key"]))
            if user_profile:
                if profile_item:
                    user_profile.profile_id = profile_item.profile_id
                else:
                    app.logger.warning(
                        "profile_item not found:{}".format(profile["key"])
                    )
                user_profile.status = 1
                if (
                    bool(profile_value)
                    and (profile_value != default_value)
                    and user_profile.profile_value != profile_value
                ):
                    user_profile.profile_value = profile_value
            elif not profile_lable.get("mapping"):
                user_profile = UserProfile(
                    user_id=user_id,
                    profile_key=profile["key"],
                    profile_value=profile_value,
                    profile_type=profile_item.profile_type if profile_item else 1,
                    profile_id=profile_item.profile_id if profile_item else "",
                    status=1,
                )
                db.session.add(user_profile)
        db.session.flush()
        return True


def get_user_variable_by_variable_id(app: Flask, user_id: str, variable_id: str):
    user_profile = (
        UserProfile.query.filter(
            UserProfile.user_id == user_id, UserProfile.profile_id == variable_id
        )
        .order_by(UserProfile.id.desc())
        .first()
    )
    if user_profile:
        return user_profile.profile_value
    else:
        return None
