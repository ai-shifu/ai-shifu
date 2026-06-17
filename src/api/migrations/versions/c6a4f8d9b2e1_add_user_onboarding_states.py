"""add user onboarding states

Revision ID: c6a4f8d9b2e1
Revises: 5a6b7c8d9e10
Create Date: 2026-06-17 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c6a4f8d9b2e1"
down_revision = "5a6b7c8d9e10"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if _table_exists("user_onboarding_states"):
        return

    op.create_table(
        "user_onboarding_states",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_bid",
            sa.String(length=32),
            nullable=False,
            server_default="",
            comment="User business identifier",
        ),
        sa.Column(
            "scene_key",
            sa.String(length=64),
            nullable=False,
            server_default="",
            comment="Onboarding scene key",
        ),
        sa.Column(
            "version",
            sa.String(length=32),
            nullable=False,
            server_default="v1",
            comment="Onboarding version",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="completed",
            comment="Onboarding state status",
        ),
        sa.Column(
            "trigger_source",
            sa.String(length=64),
            nullable=False,
            server_default="",
            comment="Trigger source",
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(),
            nullable=True,
            comment="Completion timestamp",
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
        sa.UniqueConstraint(
            "user_bid",
            "scene_key",
            "version",
            name="uk_user_onboarding_state_user_scene_version",
        ),
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_user_onboarding_states_user_bid",
        "user_onboarding_states",
        ["user_bid"],
    )
    op.create_index(
        "ix_user_onboarding_states_scene_key",
        "user_onboarding_states",
        ["scene_key"],
    )


def downgrade():
    if not _table_exists("user_onboarding_states"):
        return
    op.drop_index(
        "ix_user_onboarding_states_scene_key", table_name="user_onboarding_states"
    )
    op.drop_index(
        "ix_user_onboarding_states_user_bid", table_name="user_onboarding_states"
    )
    op.drop_table("user_onboarding_states")
