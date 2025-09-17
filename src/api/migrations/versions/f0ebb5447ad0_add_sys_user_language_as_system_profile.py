"""Add sys_user_language as system profile

Revision ID: f0ebb5447ad0
Revises: 8d807c14ad21
Create Date: 2025-09-17 01:45:33.755369

"""

# revision identifiers, used by Alembic.
revision = "f0ebb5447ad0"
down_revision = "8d807c14ad21"
branch_labels = None
depends_on = None


def upgrade():
    from flask import current_app as app
    from flaskr.service.profile.profile_manage import (
        save_profile_item,
        add_profile_i18n,
    )
    from flaskr.service.profile.models import (
        PROFILE_TYPE_INPUT_TEXT,
        PROFILE_SHOW_TYPE_HIDDEN,
        PROFILE_CONF_TYPE_PROFILE,
    )
    from flaskr.service.profile.constants import SYS_USER_LANGUAGE

    with app.app_context():
        # Create sys_user_language as a system profile
        profile_info = save_profile_item(
            app,
            parent_id="",  # Empty string indicates system-level profile
            profile_id=None,
            user_id="",
            key=SYS_USER_LANGUAGE,
            type=PROFILE_TYPE_INPUT_TEXT,
            show_type=PROFILE_SHOW_TYPE_HIDDEN,
            remark="User language",
            profile_prompt="",  # No prompt needed, value is computed dynamically
            profile_prompt_model="",
            profile_prompt_model_args="{}",
            items=[],
        )

        # Add i18n for Chinese
        add_profile_i18n(
            app,
            parent_id=profile_info.profile_id,
            conf_type=PROFILE_CONF_TYPE_PROFILE,
            language="zh-CN",
            profile_item_remark="用户语言",
            user_id="",
        )

        # Add i18n for English
        add_profile_i18n(
            app,
            parent_id=profile_info.profile_id,
            conf_type=PROFILE_CONF_TYPE_PROFILE,
            language="en-US",
            profile_item_remark="User Language",
            user_id="",
        )


def downgrade():
    # Delete the sys_user_language profile and its i18n entries
    from flask import current_app as app
    from flaskr.service.profile.models import ProfileItem, ProfileItemI18n
    from flaskr.service.profile.constants import SYS_USER_LANGUAGE
    from flaskr.dao import db

    with app.app_context():
        # Find the sys_user_language profile
        profile_item = ProfileItem.query.filter(
            ProfileItem.parent_id == "",
            ProfileItem.profile_key == SYS_USER_LANGUAGE,
            ProfileItem.status == 1,
        ).first()

        if profile_item:
            # Delete i18n entries
            ProfileItemI18n.query.filter(
                ProfileItemI18n.parent_id == profile_item.profile_id,
            ).delete()

            # Delete the profile item
            db.session.delete(profile_item)

        db.session.commit()
