from __future__ import annotations

import json
from datetime import datetime

from flask import Flask

from flaskr.i18n import _, get_current_language
from flaskr.service.common import raise_error
from flaskr.util.uuid import generate_id

from ...dao import db
from .dtos import (
    ColorSetting,
    DEFAULT_COLOR_SETTINGS,
    ProfileItemDefinition,
    ProfileOptionListDto,
    ProfileValueDto,
)
from .models import (
    PROFILE_CONF_TYPE_ITEM,
    PROFILE_TYPE_INPUT_SELECT,
    PROFILE_TYPE_INPUT_TEXT,
    PROFILE_TYPE_INPUT_UNCONF,
    CONST_PROFILE_SCOPE_SYSTEM,
    CONST_PROFILE_SCOPE_USER,
    CONST_PROFILE_TYPE_OPTION,
    CONST_PROFILE_TYPE_TEXT,
)
from .models_v2 import ProfileItem, ProfileItemI18n, ProfileItemValue


def get_color_setting(color_setting: str) -> ColorSetting:
    if color_setting:
        json_data = json.loads(color_setting)
        return ColorSetting(
            color=json_data["color"], text_color=json_data["text_color"]
        )
    return DEFAULT_COLOR_SETTINGS[0]


def get_next_color_setting(shifu_bid: str) -> ColorSetting:
    profile_items_count = ProfileItem.query.filter(
        ProfileItem.shifu_bid == shifu_bid, ProfileItem.deleted == 0
    ).count()
    return DEFAULT_COLOR_SETTINGS[
        (profile_items_count + 1) % len(DEFAULT_COLOR_SETTINGS)
    ]


def _profile_scope(shifu_bid: str) -> str:
    return CONST_PROFILE_SCOPE_SYSTEM if not shifu_bid else CONST_PROFILE_SCOPE_USER


def convert_profile_item_to_profile_item_definition(
    profile_item: ProfileItem,
) -> ProfileItemDefinition:
    profile_type = (
        CONST_PROFILE_TYPE_OPTION
        if profile_item.profile_type == PROFILE_TYPE_INPUT_SELECT
        else CONST_PROFILE_TYPE_TEXT
    )
    scope = _profile_scope(profile_item.shifu_bid)
    return ProfileItemDefinition(
        profile_item.profile_key,
        get_color_setting(profile_item.profile_color_setting),
        profile_type,
        _("PROFILE.PROFILE_TYPE_{}".format(profile_type).upper()),
        profile_item.profile_remark,
        scope,
        _("PROFILE.PROFILE_SCOPE_{}".format(scope).upper()),
        profile_item.profile_item_bid,
    )


def get_profile_item_definition_list(
    app: Flask, parent_id: str, type: str = "all"
) -> list[ProfileItemDefinition]:
    """
    Get profile item definitions.

    parent_id is the shifu_bid. Empty string means system scope.
    type: all/text/option
    """
    with app.app_context():
        query = ProfileItem.query.filter(
            ProfileItem.shifu_bid.in_([parent_id, ""]), ProfileItem.deleted == 0
        )
        if type == CONST_PROFILE_TYPE_TEXT:
            query = query.filter(ProfileItem.profile_type == PROFILE_TYPE_INPUT_TEXT)
        elif type == CONST_PROFILE_TYPE_OPTION:
            query = query.filter(ProfileItem.profile_type == PROFILE_TYPE_INPUT_SELECT)
        profile_item_list = query.order_by(ProfileItem.profile_index.asc()).all()
        if not profile_item_list:
            return []
        return [
            convert_profile_item_to_profile_item_definition(profile_item)
            for profile_item in profile_item_list
        ]


def get_profile_item_definition_option_list(
    app: Flask, parent_id: str
) -> list[ProfileValueDto]:
    with app.app_context():
        current_language = get_current_language()
        return get_profile_option_list(app, parent_id, current_language)


def add_profile_item_quick(app: Flask, parent_id: str, key: str, user_id: str):
    with app.app_context():
        if not parent_id:
            raise_error("server.profile.prarentRequired")
        if not key:
            raise_error("server.profile.keyRequire")
        ret = add_profile_item_quick_internal(app, parent_id, key, user_id)
        db.session.commit()
        return ret


def add_profile_item_quick_internal(app: Flask, parent_id: str, key: str, user_id: str):
    exist_profile_item_list = get_profile_item_definition_list(app, parent_id)
    for exist_profile_item in exist_profile_item_list:
        if exist_profile_item.profile_key == key:
            return exist_profile_item

    profile_item_bid = generate_id(app)
    profile_item = ProfileItem()
    profile_item.shifu_bid = parent_id
    profile_item.profile_item_bid = profile_item_bid
    profile_item.profile_key = key
    profile_item.profile_type = PROFILE_TYPE_INPUT_UNCONF
    profile_item.profile_remark = ""
    profile_item.profile_color_setting = str(get_next_color_setting(parent_id))
    profile_item.created_user_bid = user_id
    profile_item.updated_user_bid = user_id
    profile_item.deleted = 0
    db.session.add(profile_item)
    db.session.flush()
    return convert_profile_item_to_profile_item_definition(profile_item)


def save_profile_item(
    app: Flask,
    profile_id: str,
    parent_id: str,
    user_id: str,
    key: str,
    type: int,
    remark: str = "",
    items: list[ProfileValueDto] | None = None,
) -> ProfileItemDefinition:
    """
    Save (create/update) a profile item definition.

    profile_id is the profile_item_bid for v2 schema.
    parent_id is the shifu_bid. Empty string means system scope.
    """
    with app.app_context():
        if (not parent_id or parent_id == "") and user_id != "":
            raise_error("server.profile.systemProfileNotAllowUpdate")

        exist_system_profile_list = ProfileItem.query.filter(
            ProfileItem.shifu_bid == "",
            ProfileItem.deleted == 0,
        ).all()
        for exist_system_profile in exist_system_profile_list:
            if exist_system_profile.profile_key == key:
                raise_error("server.profile.systemProfileKeyExist")

        profile_item: ProfileItem | None
        if profile_id:
            profile_item = ProfileItem.query.filter(
                ProfileItem.profile_item_bid == profile_id,
                ProfileItem.shifu_bid == parent_id,
                ProfileItem.deleted == 0,
            ).first()
            if not profile_item:
                raise_error("server.profile.notFound")
            profile_item.updated_at = datetime.now()
            profile_item.updated_user_bid = user_id
            profile_item.profile_key = key
            profile_item.profile_type = type
            profile_item.profile_remark = remark or ""
            profile_item.profile_color_setting = str(get_next_color_setting(parent_id))
        else:
            profile_item = ProfileItem(
                shifu_bid=parent_id,
                profile_item_bid=generate_id(app),
                profile_key=key,
                profile_type=type,
                profile_remark=remark or "",
                profile_color_setting=str(get_next_color_setting(parent_id)),
                created_user_bid=user_id,
                updated_user_bid=user_id,
                deleted=0,
            )
            db.session.add(profile_item)
            profile_id = profile_item.profile_item_bid

        if not key:
            raise_error("server.profile.keyRequired")
        exist_item = ProfileItem.query.filter(
            ProfileItem.shifu_bid == parent_id,
            ProfileItem.profile_key == key,
            ProfileItem.profile_item_bid != profile_id,
            ProfileItem.deleted == 0,
        ).first()
        if exist_item:
            raise_error("server.profile.keyExist")

        if type == PROFILE_TYPE_INPUT_SELECT and not items:
            raise_error("server.profile.itemsRequired")

        current_language = get_current_language()

        if items:
            exist_profile_item_value_list = ProfileItemValue.query.filter(
                ProfileItemValue.profile_item_bid == profile_id,
            ).all()
            exist_profile_item_value_i18n_list = (
                ProfileItemI18n.query.filter(
                    ProfileItemI18n.parent_bid.in_(
                        [
                            item.profile_item_value_bid
                            for item in exist_profile_item_value_list
                        ]
                    ),
                    ProfileItemI18n.conf_type == PROFILE_CONF_TYPE_ITEM,
                    ProfileItemI18n.deleted == 0,
                ).all()
                if exist_profile_item_value_list
                else []
            )

            update_item_value_bids: list[str] = []

            for index, item in enumerate(items):
                profile_item_value = next(
                    (
                        p
                        for p in exist_profile_item_value_list
                        if p.profile_value == item.value
                    ),
                    None,
                )
                if not profile_item_value:
                    profile_item_value = ProfileItemValue(
                        profile_item_bid=profile_id,
                        profile_item_value_bid=generate_id(app),
                        profile_value=item.value or "",
                        profile_value_index=index,
                        created_user_bid=user_id,
                        updated_user_bid=user_id,
                        deleted=0,
                    )
                    db.session.add(profile_item_value)
                else:
                    profile_item_value.profile_value = item.value or ""
                    profile_item_value.profile_value_index = index
                    profile_item_value.updated_user_bid = user_id
                    profile_item_value.updated_at = datetime.now()
                    profile_item_value.deleted = 0

                update_item_value_bids.append(profile_item_value.profile_item_value_bid)

                profile_item_value_i18n = next(
                    (
                        i18n
                        for i18n in exist_profile_item_value_i18n_list
                        if i18n.parent_bid == profile_item_value.profile_item_value_bid
                        and i18n.language == current_language
                    ),
                    None,
                )
                if not profile_item_value_i18n:
                    profile_item_value_i18n = ProfileItemI18n(
                        parent_bid=profile_item_value.profile_item_value_bid,
                        language=current_language,
                        profile_item_remark=item.name or "",
                        conf_type=PROFILE_CONF_TYPE_ITEM,
                        created_user_bid=user_id,
                        updated_user_bid=user_id,
                        deleted=0,
                    )
                    db.session.add(profile_item_value_i18n)
                else:
                    profile_item_value_i18n.profile_item_remark = item.name or ""
                    profile_item_value_i18n.updated_user_bid = user_id
                    profile_item_value_i18n.updated_at = datetime.now()
                    profile_item_value_i18n.deleted = 0

            ProfileItemValue.query.filter(
                ProfileItemValue.profile_item_bid == profile_id,
                ProfileItemValue.profile_item_value_bid.notin_(update_item_value_bids),
                ProfileItemValue.deleted == 0,
            ).update(
                {
                    "deleted": 1,
                    "updated_user_bid": user_id,
                    "updated_at": datetime.now(),
                }
            )

            existing_value_bids = {
                item.profile_item_value_bid for item in exist_profile_item_value_list
            }
            removed_value_bids = list(existing_value_bids - set(update_item_value_bids))
            if removed_value_bids:
                ProfileItemI18n.query.filter(
                    ProfileItemI18n.parent_bid.in_(removed_value_bids),
                    ProfileItemI18n.conf_type == PROFILE_CONF_TYPE_ITEM,
                    ProfileItemI18n.deleted == 0,
                ).update(
                    {
                        "deleted": 1,
                        "updated_user_bid": user_id,
                        "updated_at": datetime.now(),
                    }
                )

        db.session.commit()
        return convert_profile_item_to_profile_item_definition(profile_item)


def delete_profile_item(app: Flask, user_id: str, profile_id: str) -> bool:
    with app.app_context():
        profile_item = ProfileItem.query.filter_by(profile_item_bid=profile_id).first()
        if not profile_item or profile_item.deleted != 0:
            raise_error("server.profile.notFound")
        if profile_item.shifu_bid == "" or profile_item.shifu_bid is None:
            raise_error("server.profile.systemProfileNotAllowDelete")

        profile_item.deleted = 1
        profile_item.updated_user_bid = user_id
        profile_item.updated_at = datetime.now()

        item_value_bids: list[str] = []
        if profile_item.profile_type == PROFILE_TYPE_INPUT_SELECT:
            item_value_bids.extend(
                [
                    item.profile_item_value_bid
                    for item in ProfileItemValue.query.filter_by(
                        profile_item_bid=profile_id, deleted=0
                    ).all()
                ]
            )

        if item_value_bids:
            ProfileItemValue.query.filter(
                ProfileItemValue.profile_item_bid == profile_id,
                ProfileItemValue.profile_item_value_bid.in_(item_value_bids),
                ProfileItemValue.deleted == 0,
            ).update(
                {
                    "deleted": 1,
                    "updated_user_bid": user_id,
                    "updated_at": datetime.now(),
                }
            )

        parent_bids = [profile_id] + item_value_bids
        ProfileItemI18n.query.filter(
            ProfileItemI18n.parent_bid.in_(parent_bids),
            ProfileItemI18n.deleted == 0,
        ).update(
            {
                "deleted": 1,
                "updated_user_bid": user_id,
                "updated_at": datetime.now(),
            }
        )

        db.session.commit()
        return True


def get_profile_info(app: Flask, profile_id: str) -> ProfileItem | None:
    profile_item = ProfileItem.query.filter(
        ProfileItem.profile_item_bid == profile_id,
        ProfileItem.deleted == 0,
    ).first()
    return profile_item


def get_profile_option_info(app: Flask, profile_id: str, language: str):
    profile_item = get_profile_info(app, profile_id)
    if not profile_item:
        return None
    profile_option_list = get_profile_option_list(app, profile_id, language)
    return ProfileOptionListDto(
        info=profile_item,
        list=profile_option_list,
    )


def get_profile_option_list(app: Flask, profile_id: str, language: str):
    profile_option_list = (
        ProfileItemValue.query.filter(
            ProfileItemValue.profile_item_bid == profile_id,
            ProfileItemValue.deleted == 0,
        )
        .order_by(ProfileItemValue.profile_value_index.asc())
        .all()
    )
    if not profile_option_list:
        return []

    profile_item_value_i18n_list = ProfileItemI18n.query.filter(
        ProfileItemI18n.parent_bid.in_(
            [item.profile_item_value_bid for item in profile_option_list]
        ),
        ProfileItemI18n.conf_type == PROFILE_CONF_TYPE_ITEM,
        ProfileItemI18n.deleted == 0,
    ).all()

    available_languages = set(item.language for item in profile_item_value_i18n_list)
    if len(available_languages) == 1 and language not in available_languages:
        language = list(available_languages)[0]

    profile_item_value_i18n_map = {
        (item.parent_bid, item.language): item for item in profile_item_value_i18n_list
    }

    return [
        ProfileValueDto(
            name=profile_item_value_i18n_map.get(
                (profile_option.profile_item_value_bid, language), ProfileItemI18n()
            ).profile_item_remark
            or "",
            value=profile_option.profile_value,
        )
        for profile_option in profile_option_list
    ]
