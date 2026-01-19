"""normalize profile tables

Revision ID: d2c6f8a1b0e3
Revises: 56b765541144
Create Date: 2026-01-18 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d2c6f8a1b0e3"
down_revision = "56b765541144"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _table_has_rows(table_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    bind = op.get_bind()
    return bool(bind.execute(sa.text(f"SELECT 1 FROM {table_name} LIMIT 1")).scalar())


def _create_profile_user_profiles_table() -> None:
    op.create_table(
        "profile_user_profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="User business identifier",
        ),
        sa.Column(
            "profile_item_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Profile item business identifier",
        ),
        sa.Column(
            "profile_key",
            sa.String(length=255),
            nullable=False,
            server_default="",
            comment="Profile key",
        ),
        sa.Column(
            "profile_value",
            sa.Text(),
            nullable=False,
            comment="Profile value",
        ),
        sa.Column(
            "profile_type",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment=(
                "Profile type: 2900=input_unconf, 2901=input_text, 2902=input_number, "
                "2903=input_select, 2904=input_sex, 2905=input_date"
            ),
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Deletion flag: 0=active, 1=deleted",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Last update timestamp",
        ),
        comment="Profile user profiles",
        mysql_engine="InnoDB",
    )
    with op.batch_alter_table("profile_user_profiles", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_profile_user_profiles_user_bid"), ["user_bid"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_profile_user_profiles_profile_item_bid"),
            ["profile_item_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_profile_user_profiles_profile_key"),
            ["profile_key"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_profile_user_profiles_deleted"), ["deleted"], unique=False
        )


def _create_profile_items_table() -> None:
    op.create_table(
        "profile_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "profile_item_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Profile item business identifier",
        ),
        sa.Column(
            "shifu_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Shifu business identifier (empty for system)",
        ),
        sa.Column(
            "profile_index",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Profile index",
        ),
        sa.Column(
            "profile_key",
            sa.String(length=255),
            nullable=False,
            server_default="",
            comment="Profile key",
        ),
        sa.Column(
            "profile_type",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment=(
                "Profile type: 2900=input_unconf, 2901=input_text, 2902=input_number, "
                "2903=input_select, 2904=input_sex, 2905=input_date"
            ),
        ),
        sa.Column(
            "profile_value_type",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Profile value type: 3001=all, 3002=specific",
        ),
        sa.Column(
            "profile_show_type",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Profile show type: 3001=all, 3002=user, 3003=course, 3004=hidden",
        ),
        sa.Column(
            "profile_remark",
            sa.Text(),
            nullable=False,
            comment="Profile remark",
        ),
        sa.Column(
            "profile_prompt_type",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Profile prompt type: 3101=profile, 3102=item",
        ),
        sa.Column(
            "profile_raw_prompt",
            sa.Text(),
            nullable=False,
            comment="Profile raw prompt",
        ),
        sa.Column(
            "profile_prompt",
            sa.Text(),
            nullable=False,
            comment="Profile prompt",
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
            server_default="",
            comment="Profile color",
        ),
        sa.Column(
            "profile_script_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Profile script business identifier",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Deletion flag: 0=active, 1=deleted",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Creation timestamp",
        ),
        sa.Column(
            "created_user_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Creator user business identifier",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Last update timestamp",
        ),
        sa.Column(
            "updated_user_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Last updater user business identifier",
        ),
        sa.UniqueConstraint("profile_item_bid", name="uk_profile_items_bid"),
        comment="Profile items",
        mysql_engine="InnoDB",
    )
    with op.batch_alter_table("profile_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_profile_items_profile_item_bid"),
            ["profile_item_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_profile_items_shifu_bid"), ["shifu_bid"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_profile_items_profile_key"), ["profile_key"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_profile_items_profile_script_bid"),
            ["profile_script_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_profile_items_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_profile_items_created_user_bid"),
            ["created_user_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_profile_items_updated_user_bid"),
            ["updated_user_bid"],
            unique=False,
        )


def _create_profile_item_values_table() -> None:
    op.create_table(
        "profile_item_values",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "profile_item_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Profile item business identifier",
        ),
        sa.Column(
            "profile_item_value_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Profile item value business identifier",
        ),
        sa.Column(
            "profile_value",
            sa.Text(),
            nullable=False,
            comment="Profile value",
        ),
        sa.Column(
            "profile_value_index",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Profile value index",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Deletion flag: 0=active, 1=deleted",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Creation timestamp",
        ),
        sa.Column(
            "created_user_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Creator user business identifier",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Last update timestamp",
        ),
        sa.Column(
            "updated_user_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Last updater user business identifier",
        ),
        sa.UniqueConstraint(
            "profile_item_value_bid", name="uk_profile_item_values_bid"
        ),
        comment="Profile item values",
        mysql_engine="InnoDB",
    )
    with op.batch_alter_table("profile_item_values", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_profile_item_values_profile_item_bid"),
            ["profile_item_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_profile_item_values_profile_item_value_bid"),
            ["profile_item_value_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_profile_item_values_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_profile_item_values_created_user_bid"),
            ["created_user_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_profile_item_values_updated_user_bid"),
            ["updated_user_bid"],
            unique=False,
        )


def _create_profile_item_i18ns_table() -> None:
    op.create_table(
        "profile_item_i18ns",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "parent_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Parent business identifier",
        ),
        sa.Column(
            "conf_type",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Profile conf type: 3101=profile, 3102=item",
        ),
        sa.Column(
            "language",
            sa.String(length=255),
            nullable=False,
            server_default="",
            comment="Language",
        ),
        sa.Column(
            "profile_item_remark",
            sa.Text(),
            nullable=False,
            comment="Profile item remark",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Deletion flag: 0=active, 1=deleted",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Creation timestamp",
        ),
        sa.Column(
            "created_user_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Creator user business identifier",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Last update timestamp",
        ),
        sa.Column(
            "updated_user_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Last updater user business identifier",
        ),
        comment="Profile item i18n",
        mysql_engine="InnoDB",
    )
    with op.batch_alter_table("profile_item_i18ns", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_profile_item_i18ns_parent_bid"),
            ["parent_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_profile_item_i18ns_conf_type"),
            ["conf_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_profile_item_i18ns_language"),
            ["language"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_profile_item_i18ns_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_profile_item_i18ns_created_user_bid"),
            ["created_user_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_profile_item_i18ns_updated_user_bid"),
            ["updated_user_bid"],
            unique=False,
        )


def _backfill_profile_user_profiles() -> None:
    if not _table_exists("user_profile"):
        return
    if _table_has_rows("profile_user_profiles"):
        return
    op.execute(
        sa.text(
            """
            INSERT INTO profile_user_profiles (
                id,
                user_bid,
                profile_item_bid,
                profile_key,
                profile_value,
                profile_type,
                deleted,
                created_at,
                updated_at
            )
            SELECT
                id,
                user_id,
                profile_id,
                profile_key,
                profile_value,
                profile_type,
                CASE WHEN status = 1 THEN 0 ELSE 1 END,
                created,
                updated
            FROM user_profile
            ORDER BY id ASC
            """
        )
    )


def _backfill_profile_items() -> None:
    if not _table_exists("profile_item"):
        return
    if _table_has_rows("profile_items"):
        return
    op.execute(
        sa.text(
            """
            INSERT INTO profile_items (
                id,
                profile_item_bid,
                shifu_bid,
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
                profile_script_bid,
                deleted,
                created_at,
                created_user_bid,
                updated_at,
                updated_user_bid
            )
            SELECT
                id,
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
                CASE WHEN status = 1 THEN 0 ELSE 1 END,
                created,
                created_by,
                updated,
                updated_by
            FROM profile_item
            ORDER BY id ASC
            """
        )
    )


def _backfill_profile_item_values() -> None:
    if not _table_exists("profile_item_value"):
        return
    if _table_has_rows("profile_item_values"):
        return
    op.execute(
        sa.text(
            """
            INSERT INTO profile_item_values (
                id,
                profile_item_bid,
                profile_item_value_bid,
                profile_value,
                profile_value_index,
                deleted,
                created_at,
                created_user_bid,
                updated_at,
                updated_user_bid
            )
            SELECT
                id,
                profile_id,
                profile_item_id,
                profile_value,
                profile_value_index,
                CASE WHEN status = 1 THEN 0 ELSE 1 END,
                created,
                created_by,
                updated,
                updated_by
            FROM profile_item_value
            ORDER BY id ASC
            """
        )
    )


def _backfill_profile_item_i18ns() -> None:
    if not _table_exists("profile_item_i18n"):
        return
    if _table_has_rows("profile_item_i18ns"):
        return
    op.execute(
        sa.text(
            """
            INSERT INTO profile_item_i18ns (
                id,
                parent_bid,
                conf_type,
                language,
                profile_item_remark,
                deleted,
                created_at,
                created_user_bid,
                updated_at,
                updated_user_bid
            )
            SELECT
                id,
                parent_id,
                conf_type,
                language,
                profile_item_remark,
                CASE WHEN status = 1 THEN 0 ELSE 1 END,
                created,
                created_by,
                updated,
                updated_by
            FROM profile_item_i18n
            ORDER BY id ASC
            """
        )
    )


def upgrade():
    if not _table_exists("profile_user_profiles"):
        _create_profile_user_profiles_table()
    if not _table_exists("profile_items"):
        _create_profile_items_table()
    if not _table_exists("profile_item_values"):
        _create_profile_item_values_table()
    if not _table_exists("profile_item_i18ns"):
        _create_profile_item_i18ns_table()

    _backfill_profile_user_profiles()
    _backfill_profile_items()
    _backfill_profile_item_values()
    _backfill_profile_item_i18ns()


def downgrade():
    for table_name in (
        "profile_item_i18ns",
        "profile_item_values",
        "profile_items",
        "profile_user_profiles",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
