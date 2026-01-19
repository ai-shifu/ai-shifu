"""remove unused profile v2 fields

Revision ID: 1557fed81b2a
Revises: d2c6f8a1b0e3
Create Date: 2026-01-19 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1557fed81b2a"
down_revision = "d2c6f8a1b0e3"
branch_labels = None
depends_on = None


_REMOVE_COLUMNS = (
    "profile_value_type",
    "profile_show_type",
    "profile_prompt_type",
    "profile_raw_prompt",
    "profile_prompt",
    "profile_prompt_model",
    "profile_prompt_model_args",
    "profile_script_bid",
)


def upgrade():
    with op.batch_alter_table("profile_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_profile_items_profile_script_bid"))
        for column_name in _REMOVE_COLUMNS:
            batch_op.drop_column(column_name)


def downgrade():
    with op.batch_alter_table("profile_items", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "profile_value_type",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="Profile value type: 3001=all, 3002=specific",
            )
        )
        batch_op.add_column(
            sa.Column(
                "profile_show_type",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment=(
                    "Profile show type: 3001=all, 3002=user, 3003=course, 3004=hidden"
                ),
            )
        )
        batch_op.add_column(
            sa.Column(
                "profile_prompt_type",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="Profile prompt type: 3101=profile, 3102=item",
            )
        )
        batch_op.add_column(
            sa.Column(
                "profile_raw_prompt",
                sa.Text(),
                nullable=True,
                comment="Profile raw prompt",
            )
        )
        batch_op.add_column(
            sa.Column(
                "profile_prompt",
                sa.Text(),
                nullable=True,
                comment="Profile prompt",
            )
        )
        batch_op.add_column(
            sa.Column(
                "profile_prompt_model",
                sa.Text(),
                nullable=True,
                comment="Profile prompt model",
            )
        )
        batch_op.add_column(
            sa.Column(
                "profile_prompt_model_args",
                sa.Text(),
                nullable=True,
                comment="Profile prompt model args",
            )
        )
        batch_op.add_column(
            sa.Column(
                "profile_script_bid",
                sa.String(length=36),
                nullable=False,
                server_default="",
                comment="Profile script business identifier",
            )
        )
        batch_op.create_index(
            batch_op.f("ix_profile_items_profile_script_bid"),
            ["profile_script_bid"],
            unique=False,
        )
