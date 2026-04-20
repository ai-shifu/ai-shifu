"""create variable tables

Revision ID: 716efaaeb662
Revises: ef7dbc5a8be3
Create Date: 2026-01-27 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "716efaaeb662"
down_revision = "ef7dbc5a8be3"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if not _table_exists("var_variables"):
        op.create_table(
            "var_variables",
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
                comment=(
                    "Shifu business identifier (empty means system/global scope; "
                    "otherwise the variable belongs to the specified Shifu)"
                ),
            ),
            sa.Column(
                "key",
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
                "created_user_bid",
                sa.String(length=36),
                nullable=False,
                comment="Creator user business identifier",
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
                comment="Last update timestamp",
            ),
            sa.Column(
                "updated_user_bid",
                sa.String(length=36),
                nullable=False,
                comment="Last updater user business identifier",
            ),
            sa.PrimaryKeyConstraint("id"),
            comment=(
                "Variable definition table for MarkdownFlow-based shifu. Defines variables "
                "referenced in course content (via MarkdownFlow markers) and used to collect "
                "learner inputs. Variables can be scoped to a specific Shifu or defined at "
                "system scope (empty shifu_bid). This table stores definitions only; per-user "
                "variable values are stored in the user variable table."
            ),
        )
        with op.batch_alter_table("var_variables", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_var_variables_created_user_bid"),
                ["created_user_bid"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_var_variables_deleted"),
                ["deleted"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_var_variables_is_hidden"),
                ["is_hidden"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_var_variables_key"),
                ["key"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_var_variables_shifu_bid"),
                ["shifu_bid"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_var_variables_updated_user_bid"),
                ["updated_user_bid"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_var_variables_variable_bid"),
                ["variable_bid"],
                unique=False,
            )

    if not _table_exists("var_variable_values"):
        op.create_table(
            "var_variable_values",
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
                comment="Shifu business identifier (empty=global/system scope)",
            ),
            sa.Column(
                "user_bid",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("''"),
                comment="User business identifier",
            ),
            sa.Column(
                "key",
                sa.String(length=255),
                nullable=False,
                server_default=sa.text("''"),
                comment="Variable key (fallback lookup)",
            ),
            sa.Column(
                "value",
                sa.Text(),
                nullable=False,
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
            comment=(
                "User variable value table for variables. Stores the actual values entered "
                "during learning for variables defined in var_variables. Each record represents "
                "a user's value for a variable within a Shifu or global/system scope. Important: "
                "This table stores user data (values), not variable definitions."
            ),
        )
        with op.batch_alter_table("var_variable_values", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_var_variable_values_deleted"),
                ["deleted"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_var_variable_values_key"),
                ["key"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_var_variable_values_shifu_bid"),
                ["shifu_bid"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_var_variable_values_user_bid"),
                ["user_bid"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_var_variable_values_variable_bid"),
                ["variable_bid"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_var_variable_values_variable_value_bid"),
                ["variable_value_bid"],
                unique=False,
            )


def downgrade():
    if _table_exists("var_variable_values"):
        with op.batch_alter_table("var_variable_values", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_var_variable_values_variable_value_bid"))
            batch_op.drop_index(batch_op.f("ix_var_variable_values_variable_bid"))
            batch_op.drop_index(batch_op.f("ix_var_variable_values_user_bid"))
            batch_op.drop_index(batch_op.f("ix_var_variable_values_shifu_bid"))
            batch_op.drop_index(batch_op.f("ix_var_variable_values_key"))
            batch_op.drop_index(batch_op.f("ix_var_variable_values_deleted"))
        op.drop_table("var_variable_values")

    if _table_exists("var_variables"):
        with op.batch_alter_table("var_variables", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_var_variables_variable_bid"))
            batch_op.drop_index(batch_op.f("ix_var_variables_updated_user_bid"))
            batch_op.drop_index(batch_op.f("ix_var_variables_shifu_bid"))
            batch_op.drop_index(batch_op.f("ix_var_variables_key"))
            batch_op.drop_index(batch_op.f("ix_var_variables_is_hidden"))
            batch_op.drop_index(batch_op.f("ix_var_variables_deleted"))
            batch_op.drop_index(batch_op.f("ix_var_variables_created_user_bid"))
        op.drop_table("var_variables")
