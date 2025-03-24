from flask import Flask
from .models import (
    ProfileItem,
    ProfileItemValue,
    ProfileItemI18n,
    PROFILE_TYPE_INPUT_UNCONF,
    PROFILE_SHOW_TYPE_HIDDEN,
    PROFILE_TYPE_INPUT_TEXT,
    PROFILE_TYPE_INPUT_SELECT,
    PROFILE_CONF_TYPE_PROFILE,
    PROFILE_CONF_TYPE_ITEM,
)
from ...dao import db
from flaskr.util.uuid import generate_id
import json
from flaskr.service.common import raise_error
from flaskr.common.swagger import register_schema_to_swagger

# from datetime import datetime


class ProfileItemDefinationDTO:
    pass


@register_schema_to_swagger
class ColorSetting:
    color: str  # the background color of the profile item
    text_color: str  # the text color of the profile item

    def __init__(self, color: str, text_color: str):
        self.color = color
        self.text_color = text_color

    def __json__(self):
        return {"color": self.color, "text_color": self.text_color}

    def __str__(self):
        return str(self.__json__())


DEFAULT_COLOR_SETTINGS = [
    ColorSetting(color="#FECACA", text_color="#DC2626"),  # red
    ColorSetting(color="#EA580C", text_color="#EA580C"),  # orange
    ColorSetting(color="#FEF08A", text_color="#CA8A04"),  # yellow
    ColorSetting(color="#BBF7D0", text_color="#22C55E"),  # green
    ColorSetting(color="#A5F3FC", text_color="#A5F3FC"),  # cyan
    ColorSetting(color="#BFDBFE", text_color="#2563EB"),  # blue
    ColorSetting(color="#DB2777", text_color="#DB2777"),  # pink
    ColorSetting(color="#FDE68A", text_color="#D97706"),  # amber
    ColorSetting(color="#D9F99D", text_color="#65A30D"),  # lime
    ColorSetting(color="#0D9488", text_color="#0D9488"),  # teal
    ColorSetting(color="#0284C7", text_color="#BAE6FD"),  # sky
    ColorSetting(color="#4F46E5", text_color="#C7D2FE"),  # indigo
]


# get color setting
def get_color_setting(color_setting: str):
    if color_setting:
        json_data = json.loads(color_setting)
        return ColorSetting(
            color=json_data["color"], text_color=json_data["text_color"]
        )
    return DEFAULT_COLOR_SETTINGS[0]


@register_schema_to_swagger
class ProfileItemDefination:
    profile_key: str  # the key of the profile item and could be used in prompt
    color_setting: ColorSetting  # the color setting of the profile item

    def __init__(self, profile_key: str, color_setting: ColorSetting):
        self.profile_key = profile_key
        self.color_setting = color_setting

    def __json__(self):
        return {"profile_key": self.profile_key, "color_setting": self.color_setting}

    def __str__(self):
        return str(self.__json__())


def get_next_corlor_setting(parent_id: str):
    profile_items_count = ProfileItem.query.filter(
        ProfileItem.parent_id == parent_id, ProfileItem.status == 1
    ).count()
    return DEFAULT_COLOR_SETTINGS[
        (profile_items_count + 1) % len(DEFAULT_COLOR_SETTINGS)
    ]


def get_profile_item_defination_list(app: Flask, parent_id: str):
    with app.app_context():
        profile_item_list = (
            ProfileItem.query.filter(
                ProfileItem.parent_id == parent_id, ProfileItem.status == 1
            )
            .order_by(ProfileItem.profile_index.asc())
            .all()
        )
        if profile_item_list:
            return [
                ProfileItemDefination(
                    profile_item.profile_key,
                    get_color_setting(profile_item.profile_color_setting),
                )
                for profile_item in profile_item_list
            ]
        return []


# quick add profile item
def add_profile_item_quick(app: Flask, parent_id: str, key: str, user_id: str):
    with app.app_context():
        ret = add_profile_item_quick_internal(app, parent_id, key, user_id)
        db.session.commit()
        return ret


# quick add profile item
def add_profile_item_quick_internal(app: Flask, parent_id: str, key: str, user_id: str):
    exist_profile_item_list = get_profile_item_defination_list(app, parent_id)
    if exist_profile_item_list:
        for exist_profile_item in exist_profile_item_list:
            if exist_profile_item.profile_key == key:
                return exist_profile_item
    profile_id = generate_id(app)
    profile_item = ProfileItem(
        parent_id=parent_id,
        profile_id=profile_id,
        profile_key=key,
        profile_type=PROFILE_TYPE_INPUT_UNCONF,
        profile_show_type=PROFILE_SHOW_TYPE_HIDDEN,
        profile_remark="",
        profile_color_setting=str(get_next_corlor_setting(parent_id)),
        profile_check_prompt="",
        profile_check_model="",
        profile_check_model_args="{}",
        created_by=user_id,
        updated_by=user_id,
        status=1,
    )
    db.session.add(profile_item)
    db.session.flush()
    return ProfileItemDefination(
        profile_item.profile_key,
        get_color_setting(profile_item.profile_color_setting),
    )


# add profile defination
def add_profile_item(
    app: Flask,
    parent_id: str,
    key: str,
    type: int,
    show_type: int,
    remark: str,
    user_id: str,
    profile_prompt: str = None,
    profile_check_model: str = None,
    profile_check_model_args: str = None,
    items: list[str] = [],
):
    with app.app_context():
        if not key:
            raise_error("PROFILE.KEY_REQUIRED")
        exist_item = ProfileItem.query.filter(
            ProfileItem.parent_id == parent_id, ProfileItem.profile_key == key
        ).first()
        if exist_item:
            raise_error("PROFILE.KEY_EXIST")

        if type == PROFILE_TYPE_INPUT_TEXT and not profile_prompt:
            raise_error("PROFILE.PROMPT_REQUIRED")
        if type == PROFILE_TYPE_INPUT_SELECT and not items:
            raise_error("PROFILE.ITEMS_REQUIRED")
        profile_id = generate_id(app)
        profile_item = ProfileItem(
            parent_id=parent_id,
            profile_id=profile_id,
            profile_key=key,
            profile_type=type,
            profile_show_type=show_type,
            profile_remark=remark,
            profile_color_setting=get_next_corlor_setting(parent_id),
            profile_check_prompt=profile_prompt,
            profile_check_model=profile_check_model,
            profile_check_model_args=profile_check_model_args,
            created_by=user_id,
            updated_by=user_id,
        )
        for index, item in enumerate(items):
            profile_item_value = ProfileItemValue(
                parent_id=parent_id,
                profile_id=profile_id,
                profile_item_id=generate_id(app),
                profile_value=item,
                profile_index=index,
                created_by=user_id,
                updated_by=user_id,
                status=1,
            )
            db.session.add(profile_item_value)
        db.session.commit()
        return ProfileItemDefination(
            profile_item.profile_key,
            get_color_setting(profile_item.profile_color_setting),
        )


def update_profile_item(
    app: Flask,
    profile_id: str,
    key: str,
    type: int,
    show_type: int,
    remark: str,
    user_id: str,
    profile_prompt: str = None,
    profile_check_model: str = None,
    profile_check_model_args: str = None,
    items: list[str] = [],
):
    with app.app_context():
        profile_item = ProfileItem.query.filter_by(profile_id=profile_id).first()
        if not profile_item:
            raise_error("PROFILE.NOT_FOUND")
        profile_item.profile_key = key
        profile_item.profile_type = type
        profile_item.profile_show_type = show_type
        profile_item.profile_remark = remark
        profile_item.profile_check_prompt = profile_prompt
        profile_item.profile_check_model = profile_check_model
        profile_item.profile_check_model_args = str(profile_check_model_args)
        profile_item.updated_by = user_id
        if type == PROFILE_TYPE_INPUT_TEXT and not profile_prompt:
            raise_error("PROFILE.PROMPT_REQUIRED")
        if type == PROFILE_TYPE_INPUT_SELECT:
            if len(items) == 0:
                raise_error("PROFILE.ITEMS_REQUIRED")
            profile_item_value = ProfileItemValue.query.filter_by(
                profile_id=profile_id
            ).all()
            for profile_item_value in profile_item_value:
                profile_item_value.profile_value = items[
                    profile_item_value.profile_index
                ]
                profile_item_value.updated_by = user_id
                profile_item_value.status = 1
        db.session.commit()
        return ProfileItemDefination(
            profile_item.profile_key,
            get_color_setting(profile_item.profile_color_setting),
        )


def get_profile_item_defination(app: Flask, parent_id: str, profile_key: str):
    with app.app_context():
        profile_item = ProfileItem.query.filter_by(
            parent_id=parent_id, profile_key=profile_key
        ).first()
        if profile_item:
            return ProfileItemDefination(
                profile_item.profile_key,
                get_color_setting(profile_item.profile_color_setting),
            )
        return None


def add_profile_i18n(
    app: Flask,
    parent_id: str,
    conf_type: int,
    language: str,
    profile_item_remark: str,
    user_id: str,
):
    with app.app_context():
        if conf_type == PROFILE_CONF_TYPE_PROFILE:
            profile_item = ProfileItem.query.filter(
                ProfileItem.profile_id == parent_id
            ).first()
        elif conf_type == PROFILE_CONF_TYPE_ITEM:
            profile_item = ProfileItemValue.query.filter(
                ProfileItemValue.profile_id == parent_id
            ).first()
        else:
            raise_error("PROFILE.CONF_TYPE_INVALID")
        if not profile_item:
            raise_error("PROFILE.NOT_FOUND")
        profile_i18n = ProfileItemI18n.query.filter(
            ProfileItemI18n.parent_id == parent_id,
            ProfileItemI18n.conf_type == conf_type,
            ProfileItemI18n.language == language,
            ProfileItemI18n.status == 1,
        ).first()
        if not profile_i18n:
            profile_i18n = ProfileItemI18n(
                i18n_id=generate_id(app),
                parent_id=parent_id,
                conf_type=conf_type,
                language=language,
                profile_item_remark=profile_item_remark,
                created_by=user_id,
                updated_by=user_id,
                status=1,
            )
        else:
            profile_i18n.profile_item_remark = profile_item_remark
            profile_i18n.updated_by = user_id
        db.session.merge(profile_i18n)
        db.session.commit()
        return profile_i18n


def delete_profile_item(app: Flask, profile_id: str):
    with app.app_context():
        profile_item = ProfileItem.query.filter_by(profile_id=profile_id).first()
        if not profile_item:
            raise_error("PROFILE.NOT_FOUND")
        profile_item.status = 0
        db.session.commit()
