"""add system profile

Revision ID: 6b603528dac8
Revises: 185e37df3252
Create Date: 2025-11-05 16:06:29.428922

"""

import uuid

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "6b603528dac8"
down_revision = "185e37df3252"
branch_labels = None
depends_on = None

PROFILE_CONF_TYPE_PROFILE = 3101
SYSTEM_PARENT_ID = ""
SYSTEM_USER_ID = ""

SYSTEM_PROFILES = (
    {
        "key": "sys_user_nickname",
        "labels": {
            "en-US": "User Nickname",
            "zh-CN": "用户昵称",
            "qps-ploc": "User Nickname",
        },
    },
    {
        "key": "sys_user_style",
        "labels": {
            "en-US": "Style",
            "zh-CN": "授课风格",
            "qps-ploc": "Style",
        },
    },
    {
        "key": "sys_user_background",
        "labels": {
            "en-US": "User Background",
            "zh-CN": "用户职业背景",
            "qps-ploc": "User Background",
        },
    },
    {
        "key": "sys_user_input",
        "labels": {
            "en-US": "User Input",
            "zh-CN": "用户输入",
            "qps-ploc": "User Input",
        },
    },
    {
        "key": "sys_user_language",
        "labels": {
            "en-US": "User Language",
            "zh-CN": "用户语言",
            "qps-ploc": "User Language",
        },
    },
)


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _now_expr(bind) -> str:
    return "NOW()" if bind.dialect.name == "mysql" else "CURRENT_TIMESTAMP"


def _profile_id_for_key(profile_key: str) -> str:
    return uuid.uuid5(
        uuid.NAMESPACE_URL, f"https://ai-shifu.com/system-profile/{profile_key}"
    ).hex


def _next_profile_index(bind) -> int:
    result = bind.execute(
        sa.text(
            """
            SELECT COALESCE(MAX(profile_index), -1) + 1
            FROM profile_item
            WHERE parent_id = :parent_id
            """
        ),
        {"parent_id": SYSTEM_PARENT_ID},
    ).scalar()
    return int(result or 0)


def _find_profile_item_id(bind, profile_key: str) -> str | None:
    return bind.execute(
        sa.text(
            """
            SELECT profile_id
            FROM profile_item
            WHERE parent_id = :parent_id
              AND profile_key = :profile_key
            ORDER BY status DESC, id ASC
            LIMIT 1
            """
        ),
        {
            "parent_id": SYSTEM_PARENT_ID,
            "profile_key": profile_key,
        },
    ).scalar()


def _ensure_profile_item(bind, profile_key: str) -> str:
    profile_id = _find_profile_item_id(bind, profile_key)
    now_expr = _now_expr(bind)

    if profile_id is None:
        profile_id = _profile_id_for_key(profile_key)
        bind.execute(
            sa.text(
                f"""
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
                    2901,
                    3001,
                    3002,
                    '',
                    3101,
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    {now_expr},
                    {now_expr},
                    1,
                    :created_by,
                    :updated_by
                )
                """
            ),
            {
                "profile_id": profile_id,
                "parent_id": SYSTEM_PARENT_ID,
                "profile_index": _next_profile_index(bind),
                "profile_key": profile_key,
                "created_by": SYSTEM_USER_ID,
                "updated_by": SYSTEM_USER_ID,
            },
        )
        return profile_id

    bind.execute(
        sa.text(
            f"""
            UPDATE profile_item
            SET status = 1,
                updated = {now_expr},
                updated_by = :updated_by
            WHERE parent_id = :parent_id
              AND profile_key = :profile_key
            """
        ),
        {
            "parent_id": SYSTEM_PARENT_ID,
            "profile_key": profile_key,
            "updated_by": SYSTEM_USER_ID,
        },
    )
    return profile_id


def _ensure_profile_i18n(
    bind,
    *,
    profile_id: str,
    language: str,
    label: str,
) -> None:
    now_expr = _now_expr(bind)
    existing = bind.execute(
        sa.text(
            """
            SELECT id
            FROM profile_item_i18n
            WHERE parent_id = :parent_id
              AND conf_type = :conf_type
              AND language = :language
            ORDER BY status DESC, id ASC
            LIMIT 1
            """
        ),
        {
            "parent_id": profile_id,
            "conf_type": PROFILE_CONF_TYPE_PROFILE,
            "language": language,
        },
    ).scalar()

    if existing is None:
        bind.execute(
            sa.text(
                f"""
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
                    {now_expr},
                    {now_expr},
                    1,
                    :created_by,
                    :updated_by
                )
                """
            ),
            {
                "parent_id": profile_id,
                "conf_type": PROFILE_CONF_TYPE_PROFILE,
                "language": language,
                "profile_item_remark": label,
                "created_by": SYSTEM_USER_ID,
                "updated_by": SYSTEM_USER_ID,
            },
        )
        return

    bind.execute(
        sa.text(
            f"""
            UPDATE profile_item_i18n
            SET profile_item_remark = :profile_item_remark,
                status = 1,
                updated = {now_expr},
                updated_by = :updated_by
            WHERE parent_id = :parent_id
              AND conf_type = :conf_type
              AND language = :language
            """
        ),
        {
            "parent_id": profile_id,
            "conf_type": PROFILE_CONF_TYPE_PROFILE,
            "language": language,
            "profile_item_remark": label,
            "updated_by": SYSTEM_USER_ID,
        },
    )


def upgrade():
    if not _table_exists("profile_item"):
        return

    bind = op.get_bind()
    has_i18n_table = _table_exists("profile_item_i18n")

    for profile in SYSTEM_PROFILES:
        profile_id = _ensure_profile_item(bind, profile["key"])
        if not has_i18n_table:
            continue
        for language, label in profile["labels"].items():
            _ensure_profile_i18n(
                bind,
                profile_id=profile_id,
                language=language,
                label=label,
            )


def downgrade():
    if not _table_exists("profile_item"):
        return

    bind = op.get_bind()
    now_expr = _now_expr(bind)
    has_i18n_table = _table_exists("profile_item_i18n")

    for profile in SYSTEM_PROFILES:
        bind.execute(
            sa.text(
                f"""
                UPDATE profile_item
                SET status = 0,
                    updated = {now_expr},
                    updated_by = :updated_by
                WHERE parent_id = :parent_id
                  AND profile_key = :profile_key
                """
            ),
            {
                "parent_id": SYSTEM_PARENT_ID,
                "profile_key": profile["key"],
                "updated_by": SYSTEM_USER_ID,
            },
        )

        if not has_i18n_table:
            continue

        bind.execute(
            sa.text(
                f"""
                UPDATE profile_item_i18n
                SET status = 0,
                    updated = {now_expr},
                    updated_by = :updated_by
                WHERE parent_id IN (
                    SELECT profile_id
                    FROM (
                        SELECT profile_id
                        FROM profile_item
                        WHERE parent_id = :parent_id
                          AND profile_key = :profile_key
                    ) profile_items
                )
                  AND conf_type = :conf_type
                """
            ),
            {
                "parent_id": SYSTEM_PARENT_ID,
                "profile_key": profile["key"],
                "conf_type": PROFILE_CONF_TYPE_PROFILE,
                "updated_by": SYSTEM_USER_ID,
            },
        )
