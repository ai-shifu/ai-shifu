"""feat: add lesson parent_id

Revision ID: b7ca8ba230d7
Revises: bd9e7152958f
Create Date: 2025-03-05 04:33:55.117116

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "b7ca8ba230d7"
down_revision = "bd9e7152958f"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("profile_item", schema=None) as batch_op:
        batch_op.alter_column(
            "profile_type",
            existing_type=mysql.INTEGER(display_width=11),
            comment="",
            existing_nullable=False,
        )
        batch_op.alter_column(
            "profile_value_type",
            existing_type=mysql.INTEGER(display_width=11),
            comment="",
            existing_nullable=False,
        )
        batch_op.alter_column(
            "profile_show_type",
            existing_type=mysql.INTEGER(display_width=11),
            comment="",
            existing_nullable=False,
        )
        batch_op.alter_column(
            "profile_prompt_type",
            existing_type=mysql.INTEGER(display_width=11),
            comment="",
            existing_nullable=False,
        )
        batch_op.alter_column(
            "profile_check_model",
            existing_type=mysql.VARCHAR(length=255),
            comment="",
            existing_nullable=False,
        )

    with op.batch_alter_table("profile_item_i18n", schema=None) as batch_op:
        batch_op.alter_column(
            "conf_type",
            existing_type=mysql.INTEGER(display_width=11),
            comment="",
            existing_nullable=False,
        )

    with op.batch_alter_table("user_profile", schema=None) as batch_op:
        batch_op.alter_column(
            "profile_type",
            existing_type=mysql.INTEGER(display_width=11),
            comment="",
            existing_nullable=False,
            existing_server_default=sa.text("'0'"),
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("user_profile", schema=None) as batch_op:
        batch_op.alter_column(
            "profile_type",
            existing_type=mysql.INTEGER(display_width=11),
            comment=None,
            existing_comment="",
            existing_nullable=False,
            existing_server_default=sa.text("'0'"),
        )

    with op.batch_alter_table("profile_item_i18n", schema=None) as batch_op:
        batch_op.alter_column(
            "conf_type",
            existing_type=mysql.INTEGER(display_width=11),
            comment=None,
            existing_comment="",
            existing_nullable=False,
        )

    with op.batch_alter_table("profile_item", schema=None) as batch_op:
        batch_op.alter_column(
            "profile_check_model",
            existing_type=mysql.VARCHAR(length=255),
            comment=None,
            existing_comment="",
            existing_nullable=False,
        )
        batch_op.alter_column(
            "profile_prompt_type",
            existing_type=mysql.INTEGER(display_width=11),
            comment=None,
            existing_comment="",
            existing_nullable=False,
        )
        batch_op.alter_column(
            "profile_show_type",
            existing_type=mysql.INTEGER(display_width=11),
            comment=None,
            existing_comment="",
            existing_nullable=False,
        )
        batch_op.alter_column(
            "profile_value_type",
            existing_type=mysql.INTEGER(display_width=11),
            comment=None,
            existing_comment="",
            existing_nullable=False,
        )
        batch_op.alter_column(
            "profile_type",
            existing_type=mysql.INTEGER(display_width=11),
            comment=None,
            existing_comment="",
            existing_nullable=False,
        )

    # ### end Alembic commands ###
