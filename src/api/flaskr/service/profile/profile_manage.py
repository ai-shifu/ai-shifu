from flask import Flask
from datetime import datetime
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
from .dtos import (
    ColorSetting,
    DEFAULT_COLOR_SETTINGS,
    ProfileItemDefination,
    TextProfileDto,
    SelectProfileDto,
    ProfileValueDto,
)

# from datetime import datetime
from flaskr.service.lesson.models import AICourse


# get color setting
def get_color_setting(color_setting: str):
    if color_setting:
        json_data = json.loads(color_setting)
        return ColorSetting(
            color=json_data["color"], text_color=json_data["text_color"]
        )
    return DEFAULT_COLOR_SETTINGS[0]


def get_next_corlor_setting(parent_id: str):
    profile_items_count = ProfileItem.query.filter(
        ProfileItem.parent_id == parent_id, ProfileItem.status == 1
    ).count()
    return DEFAULT_COLOR_SETTINGS[
        (profile_items_count + 1) % len(DEFAULT_COLOR_SETTINGS)
    ]


def get_profile_item_defination_list(app: Flask, parent_id: str, type: str = "all"):
    with app.app_context():
        query = ProfileItem.query.filter(
            ProfileItem.parent_id == parent_id, ProfileItem.status == 1
        )
        if type == "text":
            query = query.filter(ProfileItem.profile_type == PROFILE_TYPE_INPUT_TEXT)
        elif type == "option":
            query = query.filter(ProfileItem.profile_type == PROFILE_TYPE_INPUT_SELECT)
        elif type == "all":
            pass
        profile_item_list = query.order_by(ProfileItem.profile_index.asc()).all()
        if profile_item_list:
            return [
                ProfileItemDefination(
                    profile_item.profile_key,
                    get_color_setting(profile_item.profile_color_setting),
                    (
                        "option"
                        if profile_item.profile_type == PROFILE_TYPE_INPUT_SELECT
                        else "text"
                    ),
                )
                for profile_item in profile_item_list
            ]
        return []


def get_profile_item_defination_option_list(
    app: Flask, parent_id: str
) -> list[ProfileValueDto]:
    with app.app_context():
        profile_option_list = (
            ProfileItemValue.query.filter(
                ProfileItemValue.parent_id == parent_id, ProfileItemValue.status == 1
            )
            .order_by(ProfileItemValue.profile_value_index.asc())
            .all()
        )
        return [
            ProfileValueDto(
                profile_option.profile_value,
                profile_option.profile_value,
            )
            for profile_option in profile_option_list
        ]


# quick add profile item
def add_profile_item_quick(app: Flask, parent_id: str, key: str, user_id: str):
    with app.app_context():
        if not parent_id:
            raise_error("PROFILE.PRARENT_REQUIRED")
        if not key:
            raise_error("PROFILE.KEY_REQUIRE")
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
    profile_item = ProfileItem()
    profile_item.parent_id = parent_id
    profile_item.profile_id = profile_id
    profile_item.profile_key = key
    profile_item.profile_type = PROFILE_TYPE_INPUT_UNCONF
    profile_item.profile_show_type = PROFILE_SHOW_TYPE_HIDDEN
    profile_item.profile_remark = ""
    profile_item.profile_color_setting = str(get_next_corlor_setting(parent_id))
    profile_item.profile_prompt = ""
    profile_item.profile_prompt_type = 0
    profile_item.profile_prompt_model = ""
    profile_item.profile_prompt_model_args = "{}"
    profile_item.created_by = user_id
    profile_item.updated_by = user_id
    profile_item.status = 1
    db.session.add(profile_item)
    db.session.flush()
    app.logger.info(profile_item.profile_color_setting)
    return ProfileItemDefination(
        profile_item.profile_key,
        get_color_setting(profile_item.profile_color_setting),
        "option" if profile_item.profile_type == PROFILE_TYPE_INPUT_SELECT else "text",
    )


def save_profile_item(app: Flask, profile_item: ProfileItem):
    pass


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
            profile_color_setting=str(get_next_corlor_setting(parent_id)),
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
            (
                "option"
                if profile_item.profile_type == PROFILE_TYPE_INPUT_SELECT
                else "text"
            ),
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
            (
                "option"
                if profile_item.profile_type == PROFILE_TYPE_INPUT_SELECT
                else "text"
            ),
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
                (
                    "option"
                    if profile_item.profile_type == PROFILE_TYPE_INPUT_SELECT
                    else "text"
                ),
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


def save_profile_item_defination(
    app: Flask,
    user_id: str,
    scenario_id: str,
    profile: TextProfileDto | SelectProfileDto | None,
):
    app.logger.info(
        "save profile item defination:{} {}".format(profile.__class__.__name__, profile)
    )
    if profile is None:
        app.logger.info("profile is None")
        return
    scenario = AICourse.query.filter(AICourse.course_id == scenario_id).first()
    if scenario is None:
        raise_error("SCENARIO.NOT_FOUND")
    if isinstance(profile, TextProfileDto):
        app.logger.info("save text profile item defination:{}".format(profile))
        profile_item = ProfileItem.query.filter(
            ProfileItem.parent_id == scenario_id,
            ProfileItem.profile_key == profile.profile_key,
            ProfileItem.status == 1,
        ).first()
        if profile_item is None:

            profile_item = ProfileItem(
                profile_id=generate_id(app),
                parent_id=scenario_id,
                profile_key=profile.profile_key,
                profile_type=PROFILE_TYPE_INPUT_TEXT,
                profile_show_type=PROFILE_SHOW_TYPE_HIDDEN,
                profile_remark=profile.profile_intro,
                profile_color_setting=str(get_next_corlor_setting(scenario_id)),
                profile_prompt=profile.profile_prompt.prompt,
                profile_prompt_model=profile.profile_prompt.model,
                profile_prompt_model_args=str(profile.profile_prompt.temprature),
                created_by=user_id,
                updated_by=user_id,
                updated=datetime.now(),
                created=datetime.now(),
                status=1,
            )
            app.logger.info("save text profile item defination:{}".format(profile_item))
            db.session.add(profile_item)
        else:
            profile_item.profile_prompt = profile.profile_prompt.prompt
            profile_item.profile_prompt_model = profile.profile_prompt.model
            profile_item.profile_prompt_model_args = str(
                profile.profile_prompt.temprature
            )
            profile_item.updated_by = user_id
            profile_item.profile_remark = profile.profile_intro
            profile_item.updated = datetime.now()
        db.session.flush()

    elif isinstance(profile, SelectProfileDto):
        app.logger.info("save select profile item defination:{}".format(profile))
        profile_item = ProfileItem.query.filter(
            ProfileItem.parent_id == scenario_id,
            ProfileItem.profile_key == profile.profile_key,
            ProfileItem.status == 1,
        ).first()
        if profile_item is None:
            profile_item = ProfileItem(
                profile_id=generate_id(app),
                parent_id=scenario_id,
                profile_key=profile.profile_key,
                profile_type=PROFILE_TYPE_INPUT_SELECT,
                profile_show_type=PROFILE_SHOW_TYPE_HIDDEN,
                profile_remark=profile.profile_key,
                profile_color_setting=str(get_next_corlor_setting(scenario_id)),
                profile_prompt="",
                profile_prompt_model="",
                profile_prompt_model_args="{}",
                created_by=user_id,
                updated_by=user_id,
                updated=datetime.now(),
                created=datetime.now(),
                status=1,
            )
            app.logger.info(
                "save select profile item defination:{}".format(profile_item)
            )
            db.session.add(profile_item)
        else:
            profile_item.profile_prompt = ""
            profile_item.profile_prompt_model = ""
            profile_item.profile_prompt_model_args = "{}"
            profile_item.profile_remark = profile.profile_key
            profile_item.updated_by = user_id
            profile_item.updated = datetime.now()
            app.logger.info(
                "update select profile item defination:{}".format(profile_item)
            )

        app.logger.info("save select profile item defination:{}".format(profile_item))
        profile_item_id_list = []
        profile_item_value_list = ProfileItemValue.query.filter(
            ProfileItemValue.profile_id == profile_item.profile_id,
            ProfileItemValue.status == 1,
        ).all()
        for index, option in enumerate(profile.profile_options):
            if option.value is None or option.value == "":
                raise_error("PROFILE.OPTION_VALUE_REQUIRED")
            profile_item_value = next(
                (
                    item
                    for item in profile_item_value_list
                    if item.profile_value == option.value
                ),
                None,
            )
            if profile_item_value is None:
                profile_item_value = ProfileItemValue(
                    profile_id=profile_item.profile_id,
                    profile_item_id=generate_id(app),
                    profile_value=option.value,
                    profile_value_index=index,
                    created_by=user_id,
                    updated_by=user_id,
                    updated=datetime.now(),
                    created=datetime.now(),
                    status=1,
                )
                db.session.add(profile_item_value)
            else:
                profile_item_value.profile_value = option.value
                profile_item_value.updated_by = user_id
                profile_item_value.profile_value_index = index
                profile_item_value.updated = datetime.now()
            profile_item_id_list.append(profile_item_value.profile_item_id)
        ProfileItemValue.query.filter(
            ProfileItemValue.profile_id == profile_item.profile_id,
            ProfileItemValue.profile_item_id.notin_(profile_item_id_list),
            ProfileItemValue.status == 1,
        ).update({"status": 0})
        db.session.flush()
