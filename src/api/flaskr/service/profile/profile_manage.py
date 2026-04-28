from datetime import datetime
import hashlib

from flask import Flask
from markdown_flow import MarkdownFlow
from sqlalchemy import func, inspect, text

from ...dao import db
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.i18n import _
from flaskr.service.common import raise_error
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.util.uuid import generate_id
from .dtos import (
    ColorSetting,
    DEFAULT_COLOR_SETTINGS,
    ProfileItemDefinition,
)
from .models import (
    CONST_PROFILE_TYPE_TEXT,
    CONST_PROFILE_SCOPE_SYSTEM,
    CONST_PROFILE_SCOPE_USER,
    PROFILE_CONF_TYPE_PROFILE,
    PROFILE_SHOW_TYPE_ALL,
    PROFILE_TYPE_INPUT_TEXT,
    Variable,
)


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


def _build_color_from_definition(definition: Variable) -> ColorSetting:
    seed = (definition.key or "") + (definition.variable_bid or "")
    color_index = 0
    if seed and DEFAULT_COLOR_SETTINGS:
        digest = hashlib.md5(seed.encode("utf-8")).digest()
        color_index = int.from_bytes(digest[:4], "big") % len(DEFAULT_COLOR_SETTINGS)
    return DEFAULT_COLOR_SETTINGS[color_index]


def convert_variable_definition_to_profile_item_definition(
    definition: Variable,
) -> ProfileItemDefinition:
    """
    Convert variable definition model to legacy response DTO shape.
    """

    scope = (
        CONST_PROFILE_SCOPE_SYSTEM
        if definition.shifu_bid == ""
        else CONST_PROFILE_SCOPE_USER
    )
    return ProfileItemDefinition(
        definition.key,
        _build_color_from_definition(definition),
        "text",
        _("PROFILE.PROFILE_TYPE_TEXT"),
        "",
        scope,
        _("PROFILE.PROFILE_SCOPE_{}".format(scope).upper()),
        definition.variable_bid,
        bool(definition.is_hidden),
    )


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


def get_profile_item_definition_list(
    app: Flask, parent_id: str, type: str = "all"
) -> list[ProfileItemDefinition]:
    _ = type  # Kept for backward compatibility with existing callers.
    normalized_parent_id = parent_id or ""
    with app.app_context():
        definitions = (
            Variable.query.filter(
                Variable.shifu_bid.in_([normalized_parent_id, ""]),
                Variable.deleted == 0,
            )
            .order_by(Variable.id.asc())
            .all()
        )
        return [
            convert_variable_definition_to_profile_item_definition(item)
            for item in (definitions or [])
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
        target_items = (
            Variable.query.filter(
                Variable.shifu_bid == parent_id,
                Variable.deleted == 0,
                Variable.key.in_(profile_keys),
            )
            .order_by(Variable.id.asc())
            .all()
        )
        if target_items:
            for item in target_items:
                item.is_hidden = 1 if hidden else 0
                item.updated_at = datetime.now()
                item.updated_user_bid = user_id or ""
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
        app,
        parent_id=parent_id,
        profile_keys=unused_keys,
        hidden=True,
        user_id=user_id,
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
    bind = db.session.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "var_variables" not in tables and "profile_item" in tables:
        legacy_scope = (
            CONST_PROFILE_SCOPE_SYSTEM if not parent_id else CONST_PROFILE_SCOPE_USER
        )
        legacy_item = (
            db.session.execute(
                text(
                    """
                SELECT profile_id
                FROM profile_item
                WHERE parent_id = :parent_id
                  AND profile_key = :profile_key
                  AND status = 1
                ORDER BY id ASC
                LIMIT 1
                """
                ),
                {
                    "parent_id": parent_id or "",
                    "profile_key": key,
                },
            )
            .mappings()
            .first()
        )
        if legacy_item:
            return ProfileItemDefinition(
                key,
                DEFAULT_COLOR_SETTINGS[0],
                CONST_PROFILE_TYPE_TEXT,
                _("PROFILE.PROFILE_TYPE_TEXT"),
                "",
                legacy_scope,
                _("PROFILE.PROFILE_SCOPE_{}".format(legacy_scope).upper()),
                legacy_item["profile_id"],
                False,
            )

        profile_id = generate_id(app)
        next_index = db.session.execute(
            text("SELECT COALESCE(MAX(profile_index), 0) + 1 FROM profile_item")
        ).scalar_one()
        db.session.execute(
            text(
                """
                INSERT INTO profile_item (
                    profile_id,
                    parent_id,
                    profile_index,
                    profile_key,
                    profile_type,
                    profile_value_type,
                    profile_show_type,
                    profile_remark,
                    profile_prompt_type,
                    profile_raw_prompt,
                    profile_prompt,
                    profile_prompt_model,
                    profile_prompt_model_args,
                    profile_color_setting,
                    profile_script_id,
                    created,
                    updated,
                    status,
                    created_by,
                    updated_by
                ) VALUES (
                    :profile_id,
                    :parent_id,
                    :profile_index,
                    :profile_key,
                    :profile_type,
                    :profile_value_type,
                    :profile_show_type,
                    :profile_remark,
                    :profile_prompt_type,
                    :profile_raw_prompt,
                    :profile_prompt,
                    :profile_prompt_model,
                    :profile_prompt_model_args,
                    :profile_color_setting,
                    :profile_script_id,
                    NOW(),
                    NOW(),
                    1,
                    :created_by,
                    :updated_by
                )
                """
            ),
            {
                "profile_id": profile_id,
                "parent_id": parent_id or "",
                "profile_index": int(next_index or 1),
                "profile_key": key,
                "profile_type": PROFILE_TYPE_INPUT_TEXT,
                "profile_value_type": PROFILE_SHOW_TYPE_ALL,
                "profile_show_type": PROFILE_SHOW_TYPE_ALL,
                "profile_remark": "",
                "profile_prompt_type": PROFILE_CONF_TYPE_PROFILE,
                "profile_raw_prompt": "",
                "profile_prompt": "",
                "profile_prompt_model": "",
                "profile_prompt_model_args": "",
                "profile_color_setting": str(DEFAULT_COLOR_SETTINGS[0]),
                "profile_script_id": "",
                "created_by": user_id or "",
                "updated_by": user_id or "",
            },
        )
        return ProfileItemDefinition(
            key,
            DEFAULT_COLOR_SETTINGS[0],
            CONST_PROFILE_TYPE_TEXT,
            _("PROFILE.PROFILE_TYPE_TEXT"),
            "",
            legacy_scope,
            _("PROFILE.PROFILE_SCOPE_{}".format(legacy_scope).upper()),
            profile_id,
            False,
        )

    existing = (
        Variable.query.filter(
            Variable.key == key,
            Variable.shifu_bid.in_([parent_id, ""]),
            Variable.deleted == 0,
        )
        .order_by(Variable.id.asc())
        .first()
    )
    if existing:
        return convert_variable_definition_to_profile_item_definition(existing)

    definition = Variable(
        variable_bid=generate_id(app),
        shifu_bid=parent_id,
        key=key,
        is_hidden=0,
        deleted=0,
        created_user_bid=user_id or "",
        updated_user_bid=user_id or "",
    )
    db.session.add(definition)
    db.session.flush()
    return convert_variable_definition_to_profile_item_definition(definition)


def add_profile_i18n(
    app: Flask,
    parent_id: str,
    conf_type: int,
    language: str,
    profile_item_remark: str,
    user_id: str,
):
    bind = db.session.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "profile_item_i18n" not in tables:
        return

    existing = db.session.execute(
        text(
            """
            SELECT 1
            FROM profile_item_i18n
            WHERE parent_id = :parent_id
              AND conf_type = :conf_type
              AND language = :language
              AND status = 1
            LIMIT 1
            """
        ),
        {
            "parent_id": parent_id,
            "conf_type": conf_type,
            "language": language,
        },
    ).scalar_one_or_none()
    if existing:
        return

    db.session.execute(
        text(
            """
            INSERT INTO profile_item_i18n (
                parent_id,
                conf_type,
                language,
                profile_item_remark,
                created,
                updated,
                status,
                created_by,
                updated_by
            ) VALUES (
                :parent_id,
                :conf_type,
                :language,
                :profile_item_remark,
                NOW(),
                NOW(),
                1,
                :created_by,
                :updated_by
            )
            """
        ),
        {
            "parent_id": parent_id,
            "conf_type": conf_type,
            "language": language,
            "profile_item_remark": profile_item_remark or "",
            "created_by": user_id or "",
            "updated_by": user_id or "",
        },
    )


def save_profile_item(
    app: Flask,
    profile_id: str,
    parent_id: str,
    user_id: str,
    key: str,
):
    """
    Save (create/update) a custom variable definition.
    """

    with app.app_context():
        normalized_parent_id = parent_id or ""
        if normalized_parent_id == "" and user_id != "":
            raise_error("server.profile.systemProfileNotAllowUpdate")
        if not key:
            raise_error("server.profile.keyRequired")

        system_conflict_query = Variable.query.filter(
            Variable.shifu_bid == "",
            Variable.deleted == 0,
            Variable.key == key,
        )
        if profile_id:
            system_conflict_query = system_conflict_query.filter(
                Variable.variable_bid != profile_id
            )
        if system_conflict_query.first():
            raise_error("server.profile.systemProfileKeyExist")

        if profile_id:
            definition = Variable.query.filter(
                Variable.variable_bid == profile_id,
                Variable.shifu_bid == normalized_parent_id,
                Variable.deleted == 0,
            ).first()
            if not definition:
                raise_error("server.profile.notFound")

            exist_item = Variable.query.filter(
                Variable.shifu_bid == normalized_parent_id,
                Variable.deleted == 0,
                Variable.key == key,
                Variable.variable_bid != profile_id,
            ).first()
            if exist_item:
                raise_error("server.profile.keyExist")

            definition.key = key
            definition.updated_at = datetime.now()
            definition.updated_user_bid = user_id or ""
        else:
            exist_item = Variable.query.filter(
                Variable.shifu_bid == normalized_parent_id,
                Variable.deleted == 0,
                Variable.key == key,
            ).first()
            if exist_item:
                raise_error("server.profile.keyExist")

            definition = Variable(
                variable_bid=generate_id(app),
                shifu_bid=normalized_parent_id,
                key=key,
                is_hidden=0,
                deleted=0,
                created_user_bid=user_id or "",
                updated_user_bid=user_id or "",
            )
            db.session.add(definition)

        db.session.commit()
        return convert_variable_definition_to_profile_item_definition(definition)


def delete_profile_item(app: Flask, user_id: str, profile_id: str):
    with app.app_context():
        definition = Variable.query.filter(
            Variable.variable_bid == profile_id,
            Variable.deleted == 0,
        ).first()
        if not definition:
            raise_error("server.profile.notFound")
        if definition.shifu_bid == "" or definition.shifu_bid is None:
            raise_error("server.profile.systemProfileNotAllowDelete")

        definition.deleted = 1
        definition.updated_at = datetime.now()
        definition.updated_user_bid = user_id or ""
        db.session.commit()
        return True
