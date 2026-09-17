"""add learn agent sessions.

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-09-17 16:20:00.000000

Additive only: one new table, nothing existing is touched. Nothing reads or writes it yet.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "c3e5a7b9d1f2"
down_revision = "b2d4f6a8c0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learn_agent_sessions",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "agent_session_bid",
            sa.String(length=36),
            nullable=False,
            comment="Agent session business identifier",
        ),
        sa.Column(
            "user_bid",
            sa.String(length=36),
            nullable=False,
            comment="User business identifier",
        ),
        sa.Column(
            "shifu_bid",
            sa.String(length=36),
            nullable=False,
            comment="Shifu business identifier",
        ),
        sa.Column(
            "outline_item_bid",
            sa.String(length=36),
            nullable=False,
            comment="Outline item business identifier",
        ),
        sa.Column(
            "session_data",
            mysql.LONGTEXT(),
            nullable=False,
            comment="Engine session document as JSON",
        ),
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            comment="Engine session schema version this row was written with",
        ),
        sa.Column(
            "pydantic_ai_version",
            sa.String(length=32),
            nullable=False,
            comment="pydantic-ai version that produced the stored message history",
        ),
        sa.Column(
            "turn",
            sa.Integer(),
            nullable=False,
            comment="Turns taken so far in this session",
        ),
        sa.Column(
            "finished",
            sa.SmallInteger(),
            nullable=False,
            comment="Whether the lesson reached its end",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Whether the row is deleted",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="Creation time"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="Update time"),
        sa.PrimaryKeyConstraint("id"),
        comment="Agent lesson sessions",
    )
    op.create_index(
        "ix_learn_agent_sessions_agent_session_bid",
        "learn_agent_sessions",
        ["agent_session_bid"],
    )
    op.create_index(
        "ix_learn_agent_sessions_user_bid", "learn_agent_sessions", ["user_bid"]
    )
    op.create_index(
        "ix_learn_agent_sessions_shifu_bid", "learn_agent_sessions", ["shifu_bid"]
    )
    op.create_index(
        "ix_learn_agent_sessions_outline_item_bid",
        "learn_agent_sessions",
        ["outline_item_bid"],
    )
    op.create_index(
        "idx_learn_agent_sessions_user_outline",
        "learn_agent_sessions",
        ["user_bid", "outline_item_bid"],
    )


def downgrade():
    op.drop_index(
        "idx_learn_agent_sessions_user_outline", table_name="learn_agent_sessions"
    )
    op.drop_index(
        "ix_learn_agent_sessions_outline_item_bid", table_name="learn_agent_sessions"
    )
    op.drop_index(
        "ix_learn_agent_sessions_shifu_bid", table_name="learn_agent_sessions"
    )
    op.drop_index("ix_learn_agent_sessions_user_bid", table_name="learn_agent_sessions")
    op.drop_index(
        "ix_learn_agent_sessions_agent_session_bid", table_name="learn_agent_sessions"
    )
    op.drop_table("learn_agent_sessions")
