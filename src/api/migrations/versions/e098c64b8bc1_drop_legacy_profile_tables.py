"""drop legacy profile variable tables

Revision ID: e098c64b8bc1
Revises: 47b629e4493d
Create Date: 2026-01-27 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "e098c64b8bc1"
down_revision = "47b629e4493d"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    # Drop children tables first.
    for table_name in ("profile_item_value", "profile_item_i18n", "profile_item"):
        if _table_exists(table_name):
            op.drop_table(table_name)

    if _table_exists("user_profile"):
        op.drop_table("user_profile")


def downgrade():
    """
    WARNING:
    This downgrade recreates legacy tables/schema only. It does NOT restore any legacy data.

    The companion backfill migration (Revision ID: 6b956399315e) has an irreversible
    downgrade (no-op). To fully roll back legacy data, restore from a database backup
    taken before upgrading.
    """
    if not _table_exists("user_profile"):
        op.create_table(
            "user_profile",
            sa.Column(
                "id",
                mysql.BIGINT(),
                autoincrement=True,
                nullable=False,
                comment="Unique ID",
            ),
            sa.Column(
                "user_id", sa.String(length=36), nullable=False, comment="User UUID"
            ),
            sa.Column(
                "profile_id", sa.String(length=36), nullable=False, comment="Profile ID"
            ),
            sa.Column(
                "profile_key",
                sa.String(length=255),
                nullable=False,
                comment="Profile key",
            ),
            sa.Column(
                "profile_value", sa.Text(), nullable=False, comment="Profile value"
            ),
            sa.Column(
                "profile_type",
                sa.Integer(),
                nullable=False,
                comment=(
                    "profile type: 2900=input_unconf, 2901=input_text, 2902=input_number, "
                    "2903=input_select, 2904=input_sex, 2905=input_date"
                ),
            ),
            sa.Column(
                "created", sa.TIMESTAMP(), nullable=False, comment="Creation time"
            ),
            sa.Column("updated", sa.TIMESTAMP(), nullable=False, comment="Update time"),
            sa.Column(
                "status",
                sa.Integer(),
                nullable=False,
                comment="0 for deleted, 1 for active",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("user_profile", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_user_profile_profile_id"), ["profile_id"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_user_profile_profile_key"), ["profile_key"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_user_profile_user_id"), ["user_id"], unique=False
            )

    if not _table_exists("profile_item"):
        op.create_table(
            "profile_item",
            sa.Column(
                "id",
                mysql.BIGINT(),
                autoincrement=True,
                nullable=False,
                comment="Unique ID",
            ),
            sa.Column(
                "profile_id", sa.String(length=36), nullable=False, comment="Profile ID"
            ),
            sa.Column(
                "parent_id",
                sa.String(length=36),
                nullable=False,
                comment="Parent ID: now is shifu_bid",
            ),
            sa.Column(
                "profile_index", sa.Integer(), nullable=False, comment="Profile index"
            ),
            sa.Column(
                "profile_key",
                sa.String(length=255),
                nullable=False,
                comment="Profile key",
            ),
            sa.Column(
                "profile_type",
                sa.Integer(),
                nullable=False,
                comment=(
                    "profile type: 2900=input_unconf, 2901=input_text, 2902=input_number, "
                    "2903=input_select, 2904=input_sex, 2905=input_date"
                ),
            ),
            sa.Column(
                "profile_value_type",
                sa.Integer(),
                nullable=False,
                comment="profile value type: 3001=all, 3002=specific",
            ),
            sa.Column(
                "profile_show_type",
                sa.Integer(),
                nullable=False,
                comment=(
                    "profile show type: 3001=all, 3002=user, 3003=course, 3004=hidden"
                ),
            ),
            sa.Column(
                "profile_remark", sa.Text(), nullable=False, comment="Profile remark"
            ),
            sa.Column(
                "profile_prompt_type",
                sa.Integer(),
                nullable=False,
                comment="profile prompt type: 3101=profile, 3102=item",
            ),
            sa.Column(
                "profile_raw_prompt",
                sa.Text(),
                nullable=False,
                comment="Profile raw prompt",
            ),
            sa.Column(
                "profile_prompt", sa.Text(), nullable=False, comment="Profile prompt"
            ),
            sa.Column(
                "profile_prompt_model",
                sa.Text(),
                nullable=False,
                comment="Profile prompt model",
            ),
            sa.Column(
                "profile_prompt_model_args",
                sa.Text(),
                nullable=False,
                comment="Profile prompt model args",
            ),
            sa.Column(
                "profile_color_setting",
                sa.String(length=255),
                nullable=False,
                comment="Profile color",
            ),
            sa.Column(
                "profile_script_id",
                sa.String(length=36),
                nullable=False,
                comment="Profile script id",
            ),
            sa.Column(
                "created", sa.TIMESTAMP(), nullable=False, comment="Creation time"
            ),
            sa.Column("updated", sa.TIMESTAMP(), nullable=False, comment="Update time"),
            sa.Column(
                "status",
                sa.Integer(),
                nullable=False,
                comment="0 for deleted, 1 for active",
            ),
            sa.Column(
                "created_by",
                sa.String(length=36),
                nullable=False,
                comment="Created by",
            ),
            sa.Column(
                "updated_by",
                sa.String(length=36),
                nullable=False,
                comment="Updated by",
            ),
            sa.Column(
                "is_hidden",
                sa.SmallInteger(),
                nullable=False,
                server_default=sa.text("0"),
                comment="Hidden flag: 0=visible, 1=hidden (custom variables only)",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("profile_id"),
        )
        with op.batch_alter_table("profile_item", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_profile_item_parent_id"), ["parent_id"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_profile_item_profile_key"), ["profile_key"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_profile_item_profile_script_id"),
                ["profile_script_id"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_profile_item_is_hidden"), ["is_hidden"], unique=False
            )

    if not _table_exists("profile_item_i18n"):
        op.create_table(
            "profile_item_i18n",
            sa.Column(
                "id",
                mysql.BIGINT(),
                autoincrement=True,
                nullable=False,
                comment="Unique ID",
            ),
            sa.Column(
                "parent_id", sa.String(length=36), nullable=False, comment="parent_id"
            ),
            sa.Column(
                "conf_type",
                sa.Integer(),
                nullable=False,
                comment="profile conf type: 3101=profile, 3102=item",
            ),
            sa.Column(
                "language",
                sa.String(length=255),
                nullable=False,
                comment="Language",
            ),
            sa.Column(
                "profile_item_remark",
                sa.Text(),
                nullable=False,
                comment="Profile item remark",
            ),
            sa.Column(
                "created", sa.TIMESTAMP(), nullable=False, comment="Creation time"
            ),
            sa.Column("updated", sa.TIMESTAMP(), nullable=False, comment="Update time"),
            sa.Column(
                "status",
                sa.Integer(),
                nullable=False,
                comment="0 for deleted, 1 for active",
            ),
            sa.Column(
                "created_by",
                sa.String(length=36),
                nullable=False,
                comment="Created by",
            ),
            sa.Column(
                "updated_by",
                sa.String(length=36),
                nullable=False,
                comment="Updated by",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("profile_item_i18n", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_profile_item_i18n_language"),
                ["language"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_profile_item_i18n_parent_id"),
                ["parent_id"],
                unique=False,
            )

    if not _table_exists("profile_item_value"):
        op.create_table(
            "profile_item_value",
            sa.Column(
                "id",
                mysql.BIGINT(),
                autoincrement=True,
                nullable=False,
                comment="Unique ID",
            ),
            sa.Column(
                "profile_id", sa.String(length=36), nullable=False, comment="Profile ID"
            ),
            sa.Column(
                "profile_item_id",
                sa.String(length=36),
                nullable=False,
                comment="Profile item ID",
            ),
            sa.Column(
                "profile_value", sa.Text(), nullable=False, comment="Profile value"
            ),
            sa.Column(
                "profile_value_index",
                sa.Integer(),
                nullable=False,
                comment="Profile value index",
            ),
            sa.Column(
                "created", sa.TIMESTAMP(), nullable=False, comment="Creation time"
            ),
            sa.Column("updated", sa.TIMESTAMP(), nullable=False, comment="Update time"),
            sa.Column(
                "status",
                sa.Integer(),
                nullable=False,
                comment="0 for deleted, 1 for active",
            ),
            sa.Column(
                "created_by",
                sa.String(length=36),
                nullable=False,
                comment="Created by",
            ),
            sa.Column(
                "updated_by",
                sa.String(length=36),
                nullable=False,
                comment="Updated by",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("profile_item_value", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_profile_item_value_profile_id"),
                ["profile_id"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_profile_item_value_profile_item_id"),
                ["profile_item_id"],
                unique=False,
            )
