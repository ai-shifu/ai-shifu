"""add user open id

Revision ID: 2c92dff25922
Revises: 418eeb59384d
Create Date: 2024-08-18 15:11:35.303983

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2c92dff25922"
down_revision = "418eeb59384d"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("user_info", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "user_open_id",
                sa.String(length=255),
                nullable=True,
                comment="user open id",
            )
        )
        batch_op.create_index(
            batch_op.f("ix_user_info_user_open_id"), ["user_open_id"], unique=False
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("user_info", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_info_user_open_id"))
        batch_op.drop_column("user_open_id")

    # ### end Alembic commands ###
