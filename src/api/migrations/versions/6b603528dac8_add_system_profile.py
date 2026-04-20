"""add system profile

Revision ID: 6b603528dac8
Revises: 185e37df3252
Create Date: 2025-11-05 16:06:29.428922

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "6b603528dac8"
down_revision = "185e37df3252"
branch_labels = None
depends_on = None


def _has_column(table_name, column_name):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )


def upgrade():
    is_hidden_added = False
    if not _has_column("profile_item", "is_hidden"):
        with op.batch_alter_table("profile_item", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "is_hidden",
                    sa.SmallInteger(),
                    nullable=False,
                    server_default=sa.text("0"),
                    comment="Hidden flag: 0=visible, 1=hidden (custom variables only)",
                )
            )
        is_hidden_added = True

    from flaskr.service.profile.profile_manage import (
        add_profile_i18n,
        add_profile_item_quick_internal,
    )
    from flaskr.service.profile.models import PROFILE_CONF_TYPE_PROFILE
    from flask import current_app as app

    from flaskr.dao import db

    try:
        with app.app_context():
            item = add_profile_item_quick_internal(app, "", "sys_user_nickname", "")
            db.session.commit()
        add_profile_i18n(
            app,
            item.profile_id,
            PROFILE_CONF_TYPE_PROFILE,
            "en-US",
            "User Nickname",
            "",
        )
        add_profile_i18n(
            app, item.profile_id, PROFILE_CONF_TYPE_PROFILE, "zh-CN", "用户昵称", ""
        )
        add_profile_i18n(
            app,
            item.profile_id,
            PROFILE_CONF_TYPE_PROFILE,
            "qps-ploc",
            "User Nickname",
            "",
        )

        with app.app_context():
            item = add_profile_item_quick_internal(app, "", "sys_user_style", "")
            db.session.commit()
        add_profile_i18n(
            app, item.profile_id, PROFILE_CONF_TYPE_PROFILE, "en-US", "Style", ""
        )
        add_profile_i18n(
            app, item.profile_id, PROFILE_CONF_TYPE_PROFILE, "zh-CN", "授课风格", ""
        )
        add_profile_i18n(
            app, item.profile_id, PROFILE_CONF_TYPE_PROFILE, "qps-ploc", "Style", ""
        )

        with app.app_context():
            item = add_profile_item_quick_internal(app, "", "sys_user_background", "")
            db.session.commit()
        add_profile_i18n(
            app,
            item.profile_id,
            PROFILE_CONF_TYPE_PROFILE,
            "en-US",
            "User Background",
            "",
        )
        add_profile_i18n(
            app, item.profile_id, PROFILE_CONF_TYPE_PROFILE, "zh-CN", "用户职业背景", ""
        )
        add_profile_i18n(
            app,
            item.profile_id,
            PROFILE_CONF_TYPE_PROFILE,
            "qps-ploc",
            "User Background",
            "",
        )

        with app.app_context():
            item = add_profile_item_quick_internal(app, "", "sys_user_input", "")
            db.session.commit()
        add_profile_i18n(
            app, item.profile_id, PROFILE_CONF_TYPE_PROFILE, "en-US", "User Input", ""
        )
        add_profile_i18n(
            app, item.profile_id, PROFILE_CONF_TYPE_PROFILE, "zh-CN", "用户输入", ""
        )
        add_profile_i18n(
            app,
            item.profile_id,
            PROFILE_CONF_TYPE_PROFILE,
            "qps-ploc",
            "User Input",
            "",
        )

        with app.app_context():
            item = add_profile_item_quick_internal(app, "", "sys_user_language", "")
            db.session.commit()
        add_profile_i18n(
            app,
            item.profile_id,
            PROFILE_CONF_TYPE_PROFILE,
            "en-US",
            "User Language",
            "",
        )
        add_profile_i18n(
            app, item.profile_id, PROFILE_CONF_TYPE_PROFILE, "zh-CN", "用户语言", ""
        )
        add_profile_i18n(
            app,
            item.profile_id,
            PROFILE_CONF_TYPE_PROFILE,
            "qps-ploc",
            "User Language",
            "",
        )
    finally:
        if is_hidden_added and _has_column("profile_item", "is_hidden"):
            with op.batch_alter_table("profile_item", schema=None) as batch_op:
                batch_op.drop_column("is_hidden")
    pass


def downgrade():
    from flaskr.service.profile.models import ProfileItem, ProfileItemI18n
    from flask import current_app as app
    from flaskr.dao import db

    profile_keys = [
        "sys_user_nickname",
        "sys_user_style",
        "sys_user_background",
        "sys_user_input",
        "sys_user_language",
    ]
    with app.app_context():
        for profile_key in profile_keys:
            profile_item = ProfileItem.query.filter_by(profile_key=profile_key).first()
            if profile_item:
                profile_item.status = 0
                profile_item_i18n = ProfileItemI18n.query.filter_by(
                    parent_id=profile_item.id
                ).all()
                for profile_item_i18n in profile_item_i18n:
                    profile_item_i18n.status = 0
                db.session.commit()
    pass
