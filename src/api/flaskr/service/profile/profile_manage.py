from flask import Flask
from datetime import datetime
import json
from markdown_flow import MarkdownFlow
from .models import (
    ProfileItem,
    ProfileItemValue,
    ProfileItemI18n,
    ProfileVariableDefinition,
    PROFILE_TYPE_INPUT_UNCONF,
    PROFILE_SHOW_TYPE_HIDDEN,
    PROFILE_TYPE_INPUT_TEXT,
    PROFILE_TYPE_INPUT_SELECT,
    PROFILE_CONF_TYPE_PROFILE,
    PROFILE_CONF_TYPE_ITEM,
)
from ...dao import db
from sqlalchemy import func
from flaskr.util.uuid import generate_id
from flaskr.service.common import raise_error
from .dtos import (
    ColorSetting,
    DEFAULT_COLOR_SETTINGS,
    ProfileItemDefinition,
    TextProfileDto,
    SelectProfileDto,
    ProfileValueDto,
    ProfileOptionListDto,
)
from flaskr.i18n import _

from .models import (
    CONST_PROFILE_TYPE_TEXT,
    CONST_PROFILE_TYPE_OPTION,
    CONST_PROFILE_SCOPE_SYSTEM,
    CONST_PROFILE_SCOPE_USER,
)

from flaskr.service.shifu.models import PublishedShifu, DraftShifu, DraftOutlineItem
from flaskr.common.i18n_utils import get_markdownflow_output_language


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


def _collect_used_variables(app: Flask, shifu_bid: str) -> set[str]:
    """
    Collect variable names referenced across the latest mdflow content
    for all draft outline items under a shifu.
    """
    with app.app_context():
        latest_ids_subquery = (
            db.session.query(
                DraftOutlineItem.outline_item_bid,
                func.max(DraftOutlineItem.id).label("latest_id"),
            )
            .filter(
                DraftOutlineItem.shifu_bid == shifu_bid,
                DraftOutlineItem.deleted == 0,
            )
            .group_by(DraftOutlineItem.outline_item_bid)
            .subquery()
        )

        outline_items = (
            DraftOutlineItem.query.join(
                latest_ids_subquery,
                DraftOutlineItem.id == latest_ids_subquery.c.latest_id,
            )
            .filter(DraftOutlineItem.deleted == 0)
            .all()
        )

        used_variables: set[str] = set()
        for item in outline_items:
            if not item.content:
                continue
            try:
                markdown_flow = MarkdownFlow(item.content).set_output_language(
                    get_markdownflow_output_language()
                )
                for var in markdown_flow.extract_variables() or []:
                    if var:
                        used_variables.add(var)
            except Exception as exc:  # pragma: no cover - defensive
                app.logger.warning(
                    "Failed to parse MarkdownFlow for outline %s: %s", item.id, exc
                )
        return used_variables


def get_unused_profile_keys(app: Flask, shifu_bid: str) -> list[str]:
    """
    Determine custom profile keys that are not referenced in any outline content.
    """
    definitions = get_profile_item_definition_list(app, parent_id=shifu_bid)
    used_variables = _collect_used_variables(app, shifu_bid)
    unused_keys: list[str] = []
    for definition in definitions:
        if (
            definition.profile_scope == CONST_PROFILE_SCOPE_USER
            and definition.profile_key
            and definition.profile_key not in used_variables
        ):
            unused_keys.append(definition.profile_key)
    return unused_keys


def convert_profile_item_to_profile_item_definition(
    profile_item: ProfileItem,
) -> ProfileItemDefinition:
    return ProfileItemDefinition(
        profile_item.profile_key,
        get_color_setting(profile_item.profile_color_setting),
        (
            "option"
            if profile_item.profile_type == PROFILE_TYPE_INPUT_SELECT
            else "text"
        ),
        _(
            "PROFILE.PROFILE_TYPE_{}".format(
                (
                    "option"
                    if profile_item.profile_type == PROFILE_TYPE_INPUT_SELECT
                    else "text"
                )
            ).upper()
        ),
        profile_item.profile_remark,
        (
            CONST_PROFILE_SCOPE_SYSTEM
            if profile_item.parent_id == ""
            else CONST_PROFILE_SCOPE_USER
        ),
        _(
            "PROFILE.PROFILE_SCOPE_{}".format(
                CONST_PROFILE_SCOPE_SYSTEM
                if profile_item.parent_id == ""
                else CONST_PROFILE_SCOPE_USER
            ).upper()
        ),
        profile_item.profile_id,
        bool(profile_item.is_hidden),
    )


def convert_variable_definition_to_profile_item_definition(
    definition: ProfileVariableDefinition,
) -> ProfileItemDefinition:
    """
    Convert new minimal variable definition model to legacy DTO shape.

    The current refactor keeps only `is_hidden` in DB. All variables are treated
    as text variables, and the rest of the DTO fields are derived.
    """

    scope = (
        CONST_PROFILE_SCOPE_SYSTEM
        if definition.shifu_bid == ""
        else CONST_PROFILE_SCOPE_USER
    )
    return ProfileItemDefinition(
        definition.variable_key,
        DEFAULT_COLOR_SETTINGS[0],
        "text",
        _("PROFILE.PROFILE_TYPE_TEXT"),
        "",
        scope,
        _("PROFILE.PROFILE_SCOPE_{}".format(scope).upper()),
        definition.variable_bid,
        bool(definition.is_hidden),
    )


# get profile item definition list
# type: all, text, option
# parent_id: scenario_id, profile_id
# author: yfge
# date: 2025-04-21
def get_profile_item_definition_list(
    app: Flask, parent_id: str, type: str = "all"
) -> list[ProfileItemDefinition]:
    with app.app_context():
        if type == CONST_PROFILE_TYPE_OPTION:
            # Option/enum variables are no longer supported after refactor.
            return []

        # Prefer new table, fallback to legacy tables when DB is not migrated yet.
        try:
            definitions = (
                ProfileVariableDefinition.query.filter(
                    ProfileVariableDefinition.shifu_bid.in_([parent_id, ""]),
                    ProfileVariableDefinition.deleted == 0,
                )
                .order_by(ProfileVariableDefinition.id.asc())
                .all()
            )
            if definitions:
                return [
                    convert_variable_definition_to_profile_item_definition(item)
                    for item in definitions
                ]
        except Exception as exc:  # pragma: no cover - defensive fallback
            app.logger.warning("Failed to load profile variable definitions: %s", exc)

        query = ProfileItem.query.filter(
            ProfileItem.parent_id.in_([parent_id, ""]), ProfileItem.status == 1
        )
        if type == CONST_PROFILE_TYPE_TEXT:
            query = query.filter(ProfileItem.profile_type == PROFILE_TYPE_INPUT_TEXT)
        app.logger.info(type)
        profile_item_list = query.order_by(ProfileItem.profile_index.asc()).all()
        return [
            convert_profile_item_to_profile_item_definition(profile_item)
            for profile_item in (profile_item_list or [])
        ]


def update_profile_item_hidden_state(
    app: Flask, parent_id: str, profile_keys: list[str], hidden: bool, user_id: str
) -> list[ProfileItemDefinition]:
    """
    Update is_hidden flag for given custom profile keys.
    """
    if not parent_id:
        raise_error("server.profile.parentIdRequired")
    if not profile_keys:
        return get_profile_item_definition_list(app, parent_id=parent_id)

    with app.app_context():
        try:
            target_items = (
                ProfileVariableDefinition.query.filter(
                    ProfileVariableDefinition.shifu_bid == parent_id,
                    ProfileVariableDefinition.deleted == 0,
                    ProfileVariableDefinition.variable_key.in_(profile_keys),
                )
                .order_by(ProfileVariableDefinition.id.asc())
                .all()
            )
            if target_items:
                for item in target_items:
                    item.is_hidden = 1 if hidden else 0
                    item.updated_at = datetime.now()
                db.session.commit()
            return get_profile_item_definition_list(app, parent_id=parent_id)
        except Exception as exc:  # pragma: no cover - defensive fallback
            app.logger.warning("Failed to update profile hidden state: %s", exc)

        target_items = (
            ProfileItem.query.filter(
                ProfileItem.parent_id == parent_id,
                ProfileItem.status == 1,
                ProfileItem.profile_key.in_(profile_keys),
            )
            .order_by(ProfileItem.profile_index.asc())
            .all()
        )
        if target_items:
            for item in target_items:
                item.is_hidden = 1 if hidden else 0
                item.updated = datetime.now()
                item.updated_by = user_id
            db.session.commit()
        return get_profile_item_definition_list(app, parent_id=parent_id)


def hide_unused_profile_items(
    app: Flask, parent_id: str, user_id: str
) -> list[ProfileItemDefinition]:
    """
    Hide all custom profile items that are not referenced in any outline content.
    """
    unused_keys = get_unused_profile_keys(app, parent_id)
    if not unused_keys:
        return get_profile_item_definition_list(app, parent_id=parent_id)
    return update_profile_item_hidden_state(
        app, parent_id=parent_id, profile_keys=unused_keys, hidden=True, user_id=user_id
    )


def get_profile_variable_usage(app: Flask, parent_id: str) -> dict:
    """
    Return custom profile keys split by whether they are referenced in any outline content.
    """
    if not parent_id:
        raise_error("server.profile.parentIdRequired")

    definitions = get_profile_item_definition_list(app, parent_id=parent_id)
    used_variables = _collect_used_variables(app, parent_id)

    used_keys: list[str] = []
    unused_keys: list[str] = []
    for definition in definitions:
        if definition.profile_scope != CONST_PROFILE_SCOPE_USER:
            continue
        key = definition.profile_key
        if not key:
            continue
        if key in used_variables:
            used_keys.append(key)
        else:
            unused_keys.append(key)

    return {
        "used_keys": used_keys,
        "unused_keys": unused_keys,
    }


def get_profile_item_definition_option_list(
    app: Flask, parent_id: str
) -> list[ProfileValueDto]:
    # Option/enum variables are no longer supported after refactor.
    return []


# quick add profile item
def add_profile_item_quick(app: Flask, parent_id: str, key: str, user_id: str):
    with app.app_context():
        if not parent_id:
            raise_error("server.profile.prarentRequired")
        if not key:
            raise_error("server.profile.keyRequire")
        ret = add_profile_item_quick_internal(app, parent_id, key, user_id)
        db.session.commit()
        return ret


# quick add profile item
def add_profile_item_quick_internal(app: Flask, parent_id: str, key: str, user_id: str):
    # Prefer new table, fallback to legacy when DB is not migrated yet.
    try:
        existing = (
            ProfileVariableDefinition.query.filter(
                ProfileVariableDefinition.variable_key == key,
                ProfileVariableDefinition.shifu_bid.in_([parent_id, ""]),
                ProfileVariableDefinition.deleted == 0,
            )
            .order_by(ProfileVariableDefinition.id.asc())
            .first()
        )
        if existing:
            return convert_variable_definition_to_profile_item_definition(existing)

        definition = ProfileVariableDefinition(
            variable_bid=generate_id(app),
            shifu_bid=parent_id,
            variable_key=key,
            is_hidden=0,
            deleted=0,
        )
        db.session.add(definition)
        db.session.flush()
        return convert_variable_definition_to_profile_item_definition(definition)
    except Exception as exc:  # pragma: no cover - defensive fallback
        app.logger.warning("Failed to quick-add profile variable: %s", exc)

    exist_profile_item_list = get_profile_item_definition_list(app, parent_id)
    for exist_profile_item in exist_profile_item_list or []:
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
    return convert_profile_item_to_profile_item_definition(profile_item)


# add profile defination
def save_profile_item(
    app: Flask,
    profile_id: str,
    parent_id: str,
    user_id: str,
    key: str,
    type: int,
    show_type: int = PROFILE_SHOW_TYPE_HIDDEN,
    remark: str = "",
    profile_prompt: str = None,
    profile_prompt_model: str = None,
    profile_prompt_model_args: str = None,
    items: list[ProfileValueDto] = None,
):
    """
    Save (create/update) a custom variable definition.

    After the variable table refactor, the definition table only stores:
    - variable_key
    - is_hidden

    Other legacy fields (type/remark/options/prompt/etc.) are ignored.
    """

    from flaskr.service.common.models import AppException

    with app.app_context():
        if (not parent_id or parent_id == "") and user_id != "":
            raise_error("server.profile.systemProfileNotAllowUpdate")
        if not key:
            raise_error("server.profile.keyRequired")

        try:
            system_conflict = ProfileVariableDefinition.query.filter(
                ProfileVariableDefinition.shifu_bid == "",
                ProfileVariableDefinition.deleted == 0,
                ProfileVariableDefinition.variable_key == key,
            ).first()
            if system_conflict:
                raise_error("server.profile.systemProfileKeyExist")

            if profile_id:
                definition = ProfileVariableDefinition.query.filter(
                    ProfileVariableDefinition.variable_bid == profile_id,
                    ProfileVariableDefinition.shifu_bid == parent_id,
                    ProfileVariableDefinition.deleted == 0,
                ).first()
                if not definition:
                    raise_error("server.profile.notFound")
                definition.variable_key = key
                definition.updated_at = datetime.now()
            else:
                exist_item = ProfileVariableDefinition.query.filter(
                    ProfileVariableDefinition.shifu_bid == parent_id,
                    ProfileVariableDefinition.deleted == 0,
                    ProfileVariableDefinition.variable_key == key,
                ).first()
                if exist_item:
                    raise_error("server.profile.keyExist")
                definition = ProfileVariableDefinition(
                    variable_bid=generate_id(app),
                    shifu_bid=parent_id,
                    variable_key=key,
                    is_hidden=0,
                    deleted=0,
                )
                db.session.add(definition)

            db.session.commit()
            return convert_variable_definition_to_profile_item_definition(definition)
        except AppException:
            raise
        except Exception as exc:  # pragma: no cover - defensive fallback
            app.logger.warning(
                "Failed to save profile variable definition in new table: %s", exc
            )

        # Legacy fallback (pre-refactor schema): keep minimal text variable support.
        if profile_id:
            profile_item = ProfileItem.query.filter(
                ProfileItem.profile_id == profile_id,
                ProfileItem.parent_id == parent_id,
                ProfileItem.status == 1,
            ).first()
            if not profile_item:
                raise_error("server.profile.notFound")
            profile_item.profile_key = key
            profile_item.updated = datetime.now()
            profile_item.updated_by = user_id
            db.session.commit()
            return convert_profile_item_to_profile_item_definition(profile_item)

        exist_item = ProfileItem.query.filter(
            ProfileItem.parent_id == parent_id,
            ProfileItem.profile_key == key,
            ProfileItem.status == 1,
        ).first()
        if exist_item:
            raise_error("server.profile.keyExist")

        profile_item = ProfileItem(
            parent_id=parent_id,
            profile_id=generate_id(app),
            profile_key=key,
            profile_type=PROFILE_TYPE_INPUT_TEXT,
            profile_show_type=PROFILE_SHOW_TYPE_HIDDEN,
            profile_remark="",
            profile_color_setting=str(get_next_corlor_setting(parent_id)),
            profile_prompt="",
            profile_prompt_model="",
            profile_prompt_model_args="{}",
            created_by=user_id,
            updated_by=user_id,
            status=1,
        )
        db.session.add(profile_item)
        db.session.commit()
        return convert_profile_item_to_profile_item_definition(profile_item)


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
            raise_error("server.profile.notFound")
        profile_item.profile_key = key
        profile_item.profile_type = type
        profile_item.profile_show_type = show_type
        profile_item.profile_remark = remark
        profile_item.profile_check_prompt = profile_prompt
        profile_item.profile_check_model = profile_check_model
        profile_item.profile_check_model_args = str(profile_check_model_args)
        profile_item.updated_by = user_id
        if type == PROFILE_TYPE_INPUT_TEXT and not profile_prompt:
            raise_error("server.profile.promptRequired")
        if type == PROFILE_TYPE_INPUT_SELECT:
            if len(items) == 0:
                raise_error("server.profile.itemsRequired")
            profile_item_value = ProfileItemValue.query.filter_by(
                profile_id=profile_id, status=1
            ).all()
            for profile_item_value in profile_item_value:
                profile_item_value.profile_value = items[
                    profile_item_value.profile_index
                ]
                profile_item_value.updated_by = user_id
                profile_item_value.status = 1
        db.session.commit()
        return convert_profile_item_to_profile_item_definition(profile_item)


def get_profile_item_defination(app: Flask, parent_id: str, profile_key: str):
    with app.app_context():
        profile_item = ProfileItem.query.filter_by(
            parent_id=parent_id, profile_key=profile_key
        ).first()
        if profile_item:
            return convert_profile_item_to_profile_item_definition(profile_item)
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
                ProfileItem.profile_id == parent_id,
                ProfileItem.status == 1,
            ).first()
        elif conf_type == PROFILE_CONF_TYPE_ITEM:
            profile_item = ProfileItemValue.query.filter(
                ProfileItemValue.profile_id == parent_id
            ).first()
        else:
            raise_error("server.profile.confTypeInvalid")
        if not profile_item:
            raise_error("server.profile.notFound")
        profile_i18n = ProfileItemI18n.query.filter(
            ProfileItemI18n.parent_id == parent_id,
            ProfileItemI18n.conf_type == conf_type,
            ProfileItemI18n.language == language,
            ProfileItemI18n.status == 1,
        ).first()
        if not profile_i18n:
            profile_i18n = ProfileItemI18n(
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


def delete_profile_item(app: Flask, user_id: str, profile_id: str):
    from flaskr.service.common.models import AppException

    with app.app_context():
        try:
            definition = ProfileVariableDefinition.query.filter(
                ProfileVariableDefinition.variable_bid == profile_id,
                ProfileVariableDefinition.deleted == 0,
            ).first()
            if not definition:
                raise_error("server.profile.notFound")
            if definition.shifu_bid == "" or definition.shifu_bid is None:
                raise_error("server.profile.systemProfileNotAllowDelete")

            definition.deleted = 1
            definition.updated_at = datetime.now()
            db.session.commit()
            return True
        except AppException:
            raise
        except Exception as exc:  # pragma: no cover - defensive fallback
            app.logger.warning("Failed to delete profile variable definition: %s", exc)

        profile_item = ProfileItem.query.filter_by(profile_id=profile_id).first()
        if not profile_item:
            raise_error("server.profile.notFound")
        if profile_item.parent_id == "" or profile_item.parent_id is None:
            raise_error("server.profile.systemProfileNotAllowDelete")
        profile_item.status = 0
        item_ids = [profile_id]
        if profile_item.profile_type == PROFILE_TYPE_INPUT_SELECT:
            item_ids.extend(
                [
                    item.profile_item_id
                    for item in ProfileItemValue.query.filter_by(
                        profile_id=profile_id
                    ).all()
                ]
            )

        app.logger.info(item_ids)
        if len(item_ids) > 0:
            ProfileItemValue.query.filter(
                ProfileItemValue.profile_id == profile_id,
                ProfileItemValue.profile_item_id.in_(item_ids),
            ).update({"status": 0, "updated_by": user_id, "updated": datetime.now()})
            ProfileItemI18n.query.filter(
                ProfileItemI18n.parent_id.in_(item_ids),
                ProfileItemI18n.status == 1,
            ).update(
                {
                    "status": 0,
                    "updated_by": user_id,
                    "updated": datetime.now(),
                }
            )
        db.session.commit()
        return True


def save_profile_item_defination(
    app: Flask,
    user_id: str,
    scenario_id: str,
    profile: TextProfileDto | SelectProfileDto | None,
) -> ProfileItem:
    app.logger.info(
        "save profile item defination:{} {}".format(profile.__class__.__name__, profile)
    )
    if profile is None:
        app.logger.info("profile is None")
        return
    scenario = (
        PublishedShifu.query.filter(PublishedShifu.shifu_bid == scenario_id)
        .order_by(PublishedShifu.id.desc())
        .first()
    )
    if scenario is None:
        scenario = (
            DraftShifu.query.filter(DraftShifu.shifu_bid == scenario_id)
            .order_by(DraftShifu.id.desc())
            .first()
        )
    if scenario is None:
        raise_error("server.scenario.notFound")
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
                profile_prompt_model_args=str(profile.profile_prompt.temperature),
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
                profile.profile_prompt.temperature
            )

            profile_item.profile_raw_prompt = profile.profile_prompt.prompt
            profile_item.profile_prompt = profile.profile_prompt.prompt

            app.logger.info(
                "save text profile item defination:{}".format(
                    profile_item.profile_prompt
                )
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
                raise_error("server.profile.optionValueRequired")
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
    return profile_item


def get_profile_info(app: Flask, profile_id: str):
    profile_item = ProfileItem.query.filter(
        ProfileItem.profile_id == profile_id,
        ProfileItem.status == 1,
    ).first()
    if not profile_item:
        return None
    return profile_item


def get_profile_option_info(app: Flask, profile_id: str, language: str):
    profile_item = ProfileItem.query.filter(
        ProfileItem.profile_id == profile_id,
        ProfileItem.status == 1,
    ).first()
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
            ProfileItemValue.profile_id == profile_id, ProfileItemValue.status == 1
        )
        .order_by(ProfileItemValue.profile_value_index.asc())
        .all()
    )
    if profile_option_list:
        profile_item_value_i18n_list = ProfileItemI18n.query.filter(
            ProfileItemI18n.parent_id.in_(
                [item.profile_item_id for item in profile_option_list]
            ),
            ProfileItemI18n.conf_type == PROFILE_CONF_TYPE_ITEM,
        ).all()

        available_languages = set(
            item.language for item in profile_item_value_i18n_list
        )

        if len(available_languages) == 1 and language not in available_languages:
            language = list(available_languages)[0]

        profile_item_value_i18n_map = {
            (item.parent_id, item.language): item
            for item in profile_item_value_i18n_list
        }
    else:
        profile_item_value_i18n_map = {}
        profile_option_list = []
    return [
        ProfileValueDto(
            name=profile_item_value_i18n_map.get(
                (profile_option.profile_item_id, language), ProfileItemI18n()
            ).profile_item_remark
            or "",
            value=profile_option.profile_value,
        )
        for profile_option in profile_option_list
    ]
