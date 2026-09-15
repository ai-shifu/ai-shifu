"""add course creation attribution

Revision ID: b3e5f7a9c1d2
Revises: b2d4f6a8c0e1
Create Date: 2026-09-11 16:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "b3e5f7a9c1d2"
down_revision: str | None = "b2d4f6a8c0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable registration and course attribution storage."""
    op.create_table(
        "user_registration_attributions",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "user_bid",
            sa.String(length=32),
            nullable=False,
            comment="Registered user business identifier",
        ),
        sa.Column(
            "registration_source",
            sa.String(length=32),
            nullable=False,
            comment="Stable registration source",
        ),
        sa.Column(
            "source_product",
            sa.String(length=32),
            nullable=False,
            comment="Stable source product identifier",
        ),
        sa.Column(
            "handoff_id",
            sa.String(length=36),
            nullable=False,
            comment="Cross-system handoff UUID",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            comment="Attribution creation timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "handoff_id",
            name="uk_user_registration_attribution_handoff_id",
        ),
        sa.UniqueConstraint(
            "user_bid",
            name="uk_user_registration_attribution_user_bid",
        ),
    )
    op.create_table(
        "shifu_course_creation_attributions",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "shifu_bid",
            sa.String(length=32),
            nullable=False,
            comment="Shifu business identifier",
        ),
        sa.Column(
            "created_user_bid",
            sa.String(length=32),
            nullable=False,
            comment="Teacher business identifier at creation time",
        ),
        sa.Column(
            "creation_source",
            sa.String(length=32),
            nullable=False,
            comment="Stable course creation source",
        ),
        sa.Column(
            "source_product",
            sa.String(length=32),
            nullable=False,
            comment="Stable source product identifier",
        ),
        sa.Column(
            "handoff_id",
            sa.String(length=36),
            nullable=False,
            comment="Cross-system handoff UUID",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            comment="Attribution creation timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "handoff_id",
            name="uk_shifu_course_creation_attribution_handoff_id",
        ),
        sa.UniqueConstraint(
            "shifu_bid",
            name="uk_shifu_course_creation_attribution_shifu_bid",
        ),
    )
    op.create_index(
        op.f("ix_shifu_course_creation_attributions_created_user_bid"),
        "shifu_course_creation_attributions",
        ["created_user_bid"],
        unique=False,
    )


def downgrade() -> None:
    """Drop immutable registration and course attribution storage."""
    op.drop_index(
        op.f("ix_shifu_course_creation_attributions_created_user_bid"),
        table_name="shifu_course_creation_attributions",
    )
    op.drop_table("shifu_course_creation_attributions")
    op.drop_table("user_registration_attributions")
