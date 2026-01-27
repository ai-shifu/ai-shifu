"""create profile variable tables

Revision ID: 716efaaeb662
Revises: d7a8e2f1b3c9
Create Date: 2026-01-27 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "716efaaeb662"
down_revision = "d7a8e2f1b3c9"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if not _table_exists("profile_variable_definitions"):
        op.create_table(
            "profile_variable_definitions",
            sa.Column(
                "id",
                mysql.BIGINT(),
                autoincrement=True,
                nullable=False,
                comment="Unique ID",
            ),
            sa.Column(
                "variable_bid",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("''"),
                comment="Variable business identifier",
            ),
            sa.Column(
                "shifu_bid",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("''"),
                comment="Shifu business identifier (empty=system scope)",
            ),
            sa.Column(
                "variable_key",
                sa.String(length=255),
                nullable=False,
                server_default=sa.text("''"),
                comment="Variable key",
            ),
            sa.Column(
                "is_hidden",
                sa.SmallInteger(),
                nullable=False,
                server_default=sa.text("0"),
                comment="Hidden flag: 0=visible, 1=hidden",
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
                server_default=sa.text("CURRENT_TIMESTAMP"),
                comment="Creation timestamp",
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
                comment="Last update timestamp",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table(
            "profile_variable_definitions", schema=None
        ) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_profile_variable_definitions_deleted"),
                ["deleted"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_profile_variable_definitions_is_hidden"),
                ["is_hidden"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_profile_variable_definitions_shifu_bid"),
                ["shifu_bid"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_profile_variable_definitions_variable_bid"),
                ["variable_bid"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_profile_variable_definitions_variable_key"),
                ["variable_key"],
                unique=False,
            )

    if not _table_exists("profile_variable_values"):
        op.create_table(
            "profile_variable_values",
            sa.Column(
                "id",
                mysql.BIGINT(),
                autoincrement=True,
                nullable=False,
                comment="Unique ID",
            ),
            sa.Column(
                "variable_value_bid",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("''"),
                comment="Variable value business identifier",
            ),
            sa.Column(
                "user_bid",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("''"),
                comment="User business identifier",
            ),
            sa.Column(
                "shifu_bid",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("''"),
                comment="Shifu business identifier (empty=global/system scope)",
            ),
            sa.Column(
                "variable_bid",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("''"),
                comment="Variable business identifier",
            ),
            sa.Column(
                "variable_key",
                sa.String(length=255),
                nullable=False,
                server_default=sa.text("''"),
                comment="Variable key (fallback lookup)",
            ),
            sa.Column(
                "variable_value",
                sa.Text(),
                nullable=False,
                server_default=sa.text("''"),
                comment="Variable value",
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
                server_default=sa.text("CURRENT_TIMESTAMP"),
                comment="Creation timestamp",
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
                comment="Last update timestamp",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("profile_variable_values", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_profile_variable_values_deleted"),
                ["deleted"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_profile_variable_values_shifu_bid"),
                ["shifu_bid"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_profile_variable_values_user_bid"),
                ["user_bid"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_profile_variable_values_variable_bid"),
                ["variable_bid"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_profile_variable_values_variable_key"),
                ["variable_key"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_profile_variable_values_variable_value_bid"),
                ["variable_value_bid"],
                unique=False,
            )


def downgrade():
    if _table_exists("profile_variable_values"):
        with op.batch_alter_table("profile_variable_values", schema=None) as batch_op:
            batch_op.drop_index(
                batch_op.f("ix_profile_variable_values_variable_value_bid")
            )
            batch_op.drop_index(batch_op.f("ix_profile_variable_values_variable_key"))
            batch_op.drop_index(batch_op.f("ix_profile_variable_values_variable_bid"))
            batch_op.drop_index(batch_op.f("ix_profile_variable_values_user_bid"))
            batch_op.drop_index(batch_op.f("ix_profile_variable_values_shifu_bid"))
            batch_op.drop_index(batch_op.f("ix_profile_variable_values_deleted"))
        op.drop_table("profile_variable_values")

    if _table_exists("profile_variable_definitions"):
        with op.batch_alter_table(
            "profile_variable_definitions", schema=None
        ) as batch_op:
            batch_op.drop_index(
                batch_op.f("ix_profile_variable_definitions_variable_key")
            )
            batch_op.drop_index(
                batch_op.f("ix_profile_variable_definitions_variable_bid")
            )
            batch_op.drop_index(batch_op.f("ix_profile_variable_definitions_shifu_bid"))
            batch_op.drop_index(batch_op.f("ix_profile_variable_definitions_is_hidden"))
            batch_op.drop_index(batch_op.f("ix_profile_variable_definitions_deleted"))
        op.drop_table("profile_variable_definitions")
