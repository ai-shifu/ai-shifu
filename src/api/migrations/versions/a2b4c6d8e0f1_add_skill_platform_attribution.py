"""Add Skill platform attribution records.

Revision ID: a2b4c6d8e0f1
Revises: fde432bceab4
Create Date: 2026-09-22 14:35:00
"""

from alembic import op
import sqlalchemy as sa

revision = "a2b4c6d8e0f1"
down_revision = "fde432bceab4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_skill_attributions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_bid", sa.String(length=32), nullable=False),
        sa.Column("host_platform", sa.String(length=32), nullable=False),
        sa.Column("skill_id", sa.String(length=100), nullable=False),
        sa.Column("skill_version", sa.String(length=32), nullable=False),
        sa.Column("handoff_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("handoff_id", name="uk_user_skill_attribution_handoff_id"),
        sa.UniqueConstraint("user_bid", name="uk_user_skill_attribution_user_bid"),
    )
    op.create_table(
        "shifu_skill_attributions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shifu_bid", sa.String(length=32), nullable=False),
        sa.Column("user_bid", sa.String(length=32), nullable=False),
        sa.Column("host_platform", sa.String(length=32), nullable=False),
        sa.Column("skill_id", sa.String(length=100), nullable=False),
        sa.Column("skill_version", sa.String(length=32), nullable=False),
        sa.Column("handoff_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("handoff_id", name="uk_shifu_skill_attribution_handoff_id"),
        sa.UniqueConstraint("shifu_bid", name="uk_shifu_skill_attribution_shifu_bid"),
    )
    op.create_index(
        "ix_shifu_skill_attributions_user_bid", "shifu_skill_attributions", ["user_bid"]
    )
    op.create_table(
        "skill_journey_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_bid", sa.String(length=36), nullable=False),
        sa.Column("user_bid", sa.String(length=32), nullable=False),
        sa.Column("shifu_bid", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("host_platform", sa.String(length=32), nullable=False),
        sa.Column("skill_id", sa.String(length=100), nullable=False),
        sa.Column("skill_version", sa.String(length=32), nullable=False),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_bid", name="uk_skill_journey_event_bid"),
    )
    op.create_index(
        "ix_skill_journey_events_user_bid", "skill_journey_events", ["user_bid"]
    )
    op.create_index(
        "ix_skill_journey_events_shifu_bid", "skill_journey_events", ["shifu_bid"]
    )
    op.create_index(
        "ix_skill_journey_events_event_name", "skill_journey_events", ["event_name"]
    )
    op.create_index(
        "ix_skill_journey_events_created_at", "skill_journey_events", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("skill_journey_events")
    op.drop_table("shifu_skill_attributions")
    op.drop_table("user_skill_attributions")
