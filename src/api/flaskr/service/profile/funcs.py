from flask import Flask


from .constants import SYS_USER_LANGUAGE, SYS_USER_NICKNAME
from .models import VariableValue
from ...dao import db
from typing import Optional

import logging
from flaskr.service.user.repository import (
    UserAggregate,
    _ensure_user_entity as ensure_user_entity,
    load_user_aggregate,
    update_user_entity_fields,
)
from ...i18n import _
import datetime
import uuid
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
    PROFILE_TYPE_INPUT_TEXT,
)
from flaskr.service.profile.dtos import ProfileToSave
from flaskr.service.user.dtos import UserProfileLabelDTO, UserProfileLabelItemDTO
from flaskr.service.user.repository import UserEntity

logger = logging.getLogger(__name__)

_LANGUAGE_BASE_DISPLAY = {
    "en": "English",
    "zh": "简体中文",
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


def _get_latest_variable_value(
    values: list[VariableValue],
    variable_key: str,
    shifu_bid: str,
    variable_bid: Optional[str] = None,
) -> Optional[VariableValue]:
    """
    Return the newest variable value row from a pre-fetched, id-desc sorted
    collection.

    Precedence:
    1) shifu scope (shifu_bid)
    2) global/system scope (empty shifu_bid)
    """
    target_shifu = shifu_bid or ""

    if variable_bid:
        scoped = next(
            (
                item
                for item in values
                if item.variable_bid == variable_bid and item.shifu_bid == target_shifu
            ),
            None,
        )
        if scoped:
            return scoped

    scoped = next(
        (
            item
            for item in values
            if item.key == variable_key and item.shifu_bid == target_shifu
        ),
        None,
    )
    if scoped:
        return scoped

    if not target_shifu:
        return None

    if variable_bid:
        fallback = next(
            (
                item
                for item in values
                if item.variable_bid == variable_bid and item.shifu_bid == ""
            ),
            None,
        )
        if fallback:
            return fallback

    return next(
        (item for item in values if item.key == variable_key and item.shifu_bid == ""),
        None,
    )


def _fetch_latest_variable_value(
    user_bid: str,
    variable_key: str,
    shifu_bid: str,
    variable_bid: Optional[str] = None,
) -> Optional[VariableValue]:
    """
    Fetch the newest variable value row for a user.

    Tries variable_bid first (when provided) and falls back to variable_key.
    """
    target_shifu = shifu_bid or ""
    try:
        if variable_bid:
            profile = (
                VariableValue.query.filter(
                    VariableValue.user_bid == user_bid,
                    VariableValue.shifu_bid == target_shifu,
                    VariableValue.variable_bid == variable_bid,
                    VariableValue.deleted == 0,
                )
                .order_by(VariableValue.id.desc())
                .first()
            )
            if profile:
                return profile

        return (
            VariableValue.query.filter(
                VariableValue.user_bid == user_bid,
                VariableValue.shifu_bid == target_shifu,
                VariableValue.key == variable_key,
                VariableValue.deleted == 0,
            )
            .order_by(VariableValue.id.desc())
            .first()
        )
    except Exception as exc:  # pragma: no cover - mixed migration envs
        logger.warning("Failed to fetch var_variable_values: %s", exc)
        return None


def _ensure_user_aggregate(user_id: str) -> Optional[UserAggregate]:
    aggregate = load_user_aggregate(user_id)
    if aggregate:
        return aggregate
    ensure_user_entity(user_id)
    return load_user_aggregate(user_id)


def _update_aggregate_field(
    aggregate: Optional[UserAggregate], mapping: str, value
) -> None:
    if not aggregate:
        return
    if mapping == "name":
        aggregate.nickname = value or ""
    elif mapping == "user_avatar":
        aggregate.avatar = value or ""
    elif mapping == "user_language":
        aggregate.language = value or ""
    elif mapping == "user_birth":
        aggregate.birthday = value


def _normalize_core_value(mapping: str, value):
    if mapping == "user_birth":
        if isinstance(value, datetime.date):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.date.fromisoformat(value)
            except ValueError:
                return None
        return None
    return value or ""


def _apply_core_mapping(user_id: str, mapping: str, value):
    entity = ensure_user_entity(user_id)
    normalized = _normalize_core_value(mapping, value)
    if mapping == "name":
        update_user_entity_fields(entity, nickname=normalized)
    elif mapping == "user_avatar":
        update_user_entity_fields(entity, avatar=normalized)
    elif mapping == "user_language":
        update_user_entity_fields(entity, language=normalized)
    elif mapping == "user_birth":
        update_user_entity_fields(entity, birthday=normalized)
    return normalized


def _current_core_value(aggregate: Optional[UserAggregate], mapping: str):
    if not aggregate:
        return None
    if mapping == "name":
        return aggregate.nickname
    if mapping == "user_avatar":
        return aggregate.avatar
    if mapping == "user_language":
        return aggregate.language
    if mapping == "user_birth":
        return aggregate.birthday
    return None


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
            "label": _("server.profile.nickname"),
            "mapping": "name",
            "default": "",
        },
        "sys_user_background": {"label": _("server.profile.userBackground")},
        "sex": {
            "label": _("server.profile.sex"),
            "mapping": "user_sex",
            "items": [
                _("server.profile.sexMale"),
                _("server.profile.sexFemale"),
                _("server.profile.sexSecret"),
            ],
            "items_mapping": {
                0: _("server.profile.sexSecret"),
                1: _("server.profile.sexMale"),
                2: _("server.profile.sexFemale"),
            },
            "default": 0,
        },
        "birth": {
            "label": _("server.profile.birth"),
            "mapping": "user_birth",
            "type": "date",
            "default": datetime.date(2003, 1, 1),
        },
        "avatar": {
            "label": _("server.profile.avatar"),
            "mapping": "user_avatar",
            "type": "image",
            "default": "",
        },
        "language": {
            "label": _("server.profile.language"),
            "items": ["中文", "English"],
            "mapping": "user_language",
            "items_mapping": {"zh-CN": "中文", "en-US": "English"},
            "default": "zh-CN",
        },
        "sys_user_style": {
            "label": _("server.profile.style"),
        },
    }


def get_user_profile_by_user_id(
    app: Flask, user_id: str, profile_key: str
) -> UserProfileDTO:
    user_profile = _fetch_latest_variable_value(
        user_bid=user_id,
        variable_key=profile_key,
        shifu_bid="",
    )
    if user_profile:
        return UserProfileDTO(
            user_profile.user_bid,
            user_profile.key,
            user_profile.value,
            PROFILE_TYPE_INPUT_TEXT,
        )
    return None


def save_user_profile(
    user_id: str, profile_key: str, profile_value: str, profile_type: int
):
    PROFILES_LABLES = get_profile_labels()
    existing_profile = _fetch_latest_variable_value(
        user_bid=user_id,
        variable_key=profile_key,
        shifu_bid="",
    )
    aggregate = _ensure_user_aggregate(user_id)
    user_profile = existing_profile
    if not existing_profile or existing_profile.value != profile_value:
        user_profile = VariableValue(
            variable_value_bid=uuid.uuid4().hex,
            user_bid=user_id,
            shifu_bid="",
            variable_bid="",
            key=profile_key,
            value=profile_value or "",
            deleted=0,
        )
        db.session.add(user_profile)
    if profile_key in PROFILES_LABLES:
        profile_lable = PROFILES_LABLES[profile_key]
        if profile_lable.get("mapping"):
            if profile_lable.get("items_mapping"):
                profile_value = profile_lable["items_mapping"].get(
                    profile_value, profile_value
                )
            normalized = _apply_core_mapping(
                user_id, profile_lable["mapping"], profile_value
            )
            _update_aggregate_field(aggregate, profile_lable["mapping"], normalized)
    db.session.flush()
    return UserProfileDTO(
        user_profile.user_bid,
        user_profile.key,
        user_profile.value,
        PROFILE_TYPE_INPUT_TEXT,
    )


def save_user_profiles(
    app: Flask, user_id: str, course_id: str, profiles: list[ProfileToSave]
) -> bool:
    PROFILES_LABLES = get_profile_labels()
    app.logger.info("save user profiles:%s", profiles)
    aggregate = _ensure_user_aggregate(user_id)
    profiles_items = get_profile_item_definition_list(app, course_id)

    candidate_shifus = [course_id or ""]
    if course_id:
        candidate_shifus.append("")

    try:
        user_values: list[VariableValue] = (
            VariableValue.query.filter(
                VariableValue.user_bid == user_id,
                VariableValue.deleted == 0,
                VariableValue.shifu_bid.in_(candidate_shifus),
            )
            .order_by(VariableValue.id.desc())
            .all()
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        app.logger.warning("Failed to load var_variable_values: %s", exc)
        user_values = []

    for profile in profiles:
        profile_item = next(
            (item for item in profiles_items if item.profile_key == profile.key), None
        )
        variable_bid = (profile.bid or "").strip() or (
            profile_item.profile_id if profile_item else ""
        )
        target_shifu = "" if profile.key in PROFILES_LABLES else (course_id or "")

        latest_value = _get_latest_variable_value(
            user_values,
            variable_key=profile.key,
            shifu_bid=target_shifu,
            variable_bid=variable_bid or None,
        )
        if not latest_value or latest_value.value != profile.value:
            user_value = VariableValue(
                variable_value_bid=generate_id(app),
                user_bid=user_id,
                shifu_bid=target_shifu,
                variable_bid=variable_bid,
                key=profile.key,
                value=profile.value or "",
                deleted=0,
            )
            db.session.add(user_value)
            user_values.insert(0, user_value)

        if profile.key in PROFILES_LABLES:
            profile_lable = PROFILES_LABLES[profile.key]
            if profile_lable.get("mapping"):
                if profile_lable.get("items_mapping"):
                    profile.value = profile_lable["items_mapping"].get(
                        profile.value, profile.value
                    )
                normalized = _apply_core_mapping(
                    user_id, profile_lable["mapping"], profile.value
                )
                _update_aggregate_field(aggregate, profile_lable["mapping"], normalized)

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

    candidate_shifus = [course_id or ""]
    if course_id:
        candidate_shifus.append("")

    try:
        user_values: list[VariableValue] = (
            VariableValue.query.filter(
                VariableValue.user_bid == user_id,
                VariableValue.deleted == 0,
                VariableValue.shifu_bid.in_(candidate_shifus),
            )
            .order_by(VariableValue.id.desc())
            .all()
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        app.logger.warning("Failed to load var_variable_values: %s", exc)
        user_values = []
    user_info: UserEntity = UserEntity.query.filter(
        UserEntity.user_bid == user_id
    ).first()
    result = {}
    for profile_item in profiles_items:
        user_value = (
            _get_latest_variable_value(
                user_values,
                variable_key=profile_item.profile_key,
                shifu_bid=course_id or "",
                variable_bid=(profile_item.profile_id or None),
            )
            if user_values
            else None
        )
        if user_value:
            result[profile_item.profile_key] = user_value.value
    if result.get(SYS_USER_LANGUAGE, None) is None:
        result[SYS_USER_LANGUAGE] = user_info.language if user_info else "en-US"
    if (
        result.get(SYS_USER_NICKNAME, None) is None
        or result.get(SYS_USER_NICKNAME, None) == ""
    ):
        result[SYS_USER_NICKNAME] = user_info.nickname if user_info else ""
    return result


def get_user_profile_labels(
    app: Flask, user_id: str, course_id: str
) -> UserProfileLabelDTO:
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
    candidate_shifus = [course_id or ""]
    if course_id:
        candidate_shifus.append("")

    try:
        user_values: list[VariableValue] = (
            VariableValue.query.filter(
                VariableValue.user_bid == user_id,
                VariableValue.deleted == 0,
                VariableValue.shifu_bid.in_(candidate_shifus),
            )
            .order_by(VariableValue.id.desc())
            .all()
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        app.logger.warning("Failed to load var_variable_values: %s", exc)
        user_values = []
    profiles_items = get_profile_item_definition_list(app, course_id)
    PROFILES_LABLES = get_profile_labels()
    aggregate = load_user_aggregate(user_id)
    language_value = aggregate.user_language if aggregate else "en-US"
    result = UserProfileLabelDTO(profiles=[], language=language_value)
    mapping_keys = []
    if aggregate:
        for key, meta in PROFILES_LABLES.items():
            mapping = meta.get("mapping")
            if not mapping:
                continue
            mapping_keys.append(key)
            raw_value = _current_core_value(aggregate, mapping)
            if raw_value is None:
                value_entry = (
                    _get_latest_variable_value(
                        user_values,
                        variable_key=key,
                        shifu_bid="",
                    )
                    if user_values
                    else None
                )
                if value_entry:
                    raw_value = value_entry.value
            display_value = raw_value
            if meta.get("items_mapping"):
                mapping_items = meta.get("items", [])
                default_value = mapping_items[0] if mapping_items else ""
                display_value = meta["items_mapping"].get(raw_value, default_value)
            result.profiles.append(
                UserProfileLabelItemDTO(
                    key=key,
                    label=meta["label"],
                    type=meta.get("type", "select" if "items" in meta else "text"),
                    value=display_value,
                    items=meta.get("items"),
                )
            )
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
        user_value = None
        profile_item = next(
            (item for item in profiles_items if item.profile_key == profile_key), None
        )
        if profile_item:
            if user_values:
                user_value = _get_latest_variable_value(
                    user_values,
                    variable_key=profile_key,
                    shifu_bid="",
                    variable_bid=profile_item.profile_id or None,
                )
        else:
            app.logger.info("profile_item not found:{}".format(profile_key))
        if user_value is None and user_values:
            user_value = _get_latest_variable_value(
                user_values,
                variable_key=profile_key,
                shifu_bid="",
            )
        if user_value:
            item["value"] = user_value.value
        result.profiles.append(
            UserProfileLabelItemDTO(
                key=item["key"],
                label=item["label"],
                type=item["type"],
                value=item["value"],
                items=item["items"],
            )
        )

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
    if isinstance(profiles, UserProfileLabelDTO):
        profiles = profiles.profiles or []
    elif isinstance(profiles, UserProfileLabelItemDTO):
        profiles = [profiles]

    if profiles and isinstance(profiles[0], UserProfileLabelItemDTO):
        profiles = [item.__json__() for item in profiles]

    aggregate = _ensure_user_aggregate(user_id)
    profile_items = get_profile_item_definition_list(app, course_id)

    if not profiles:
        db.session.flush()
        return True

    nickname = next((p for p in profiles if p.get("key") == "sys_user_nickname"), None)
    if nickname and not check_text_content(app, user_id, nickname.get("value")):
        raise_error("server.common.nicknameNotAllowed")

    background = next(
        (p for p in profiles if p.get("key") == "sys_user_background"), None
    )
    if background and not check_text_content(app, user_id, background.get("value")):
        raise_error("server.common.backgroundNotAllowed")

    candidate_shifus = [course_id or ""]
    if course_id:
        candidate_shifus.append("")

    try:
        user_values: list[VariableValue] = (
            VariableValue.query.filter(
                VariableValue.user_bid == user_id,
                VariableValue.deleted == 0,
                VariableValue.shifu_bid.in_(candidate_shifus),
            )
            .order_by(VariableValue.id.desc())
            .all()
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        app.logger.warning("Failed to load var_variable_values: %s", exc)
        user_values = []

    for profile in profiles:
        key = profile.get("key")
        if not key:
            continue
        profile_value = profile.get("value")
        profile_item = next(
            (
                item
                for item in profile_items
                if item.profile_key == key or item.profile_id == profile.get("id")
            ),
            None,
        )

        app.logger.info("update user profile:%s-%s", key, profile_value)

        profile_lable = PROFILES_LABLES.get(key, None)
        default_value = profile_lable.get("default", None) if profile_lable else None

        if profile_lable and profile_lable.get("items_mapping"):
            for source_value, mapped in profile_lable["items_mapping"].items():
                if mapped == profile_value:
                    profile_value = source_value
                    break

        app.logger.info("profile_value:%s", profile_value)
        mapping = profile_lable.get("mapping") if profile_lable else None
        if mapping and (
            update_all
            or (
                profile_value != default_value
                and _current_core_value(aggregate, mapping) != profile_value
            )
        ):
            app.logger.info(
                "update user info: %s - %s",
                key,
                profile_value,
            )
            normalized = _apply_core_mapping(user_id, mapping, profile_value)
            _update_aggregate_field(aggregate, mapping, normalized)
        elif not profile_lable:
            app.logger.info("profile_lable not found:%s", key)

        should_persist_value = (
            profile_value not in (None, "") and profile_value != default_value
        )
        if should_persist_value:
            latest_value = _get_latest_variable_value(
                user_values,
                variable_key=key,
                shifu_bid="",
                variable_bid=(profile_item.profile_id if profile_item else None),
            )
            if latest_value is None or latest_value.value != profile_value:
                variable_bid = profile_item.profile_id if profile_item else ""
                new_value = VariableValue(
                    variable_value_bid=generate_id(app),
                    user_bid=user_id,
                    shifu_bid="",
                    variable_bid=variable_bid,
                    key=key,
                    value=str(profile_value) if profile_value is not None else "",
                    deleted=0,
                )
                db.session.add(new_value)
                user_values.insert(0, new_value)
    db.session.flush()
    return True
