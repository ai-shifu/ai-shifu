"""add versioned shifu course slugs

Revision ID: c7e4a9d2f6b1
Revises: f6b2a4d8c9e0
Create Date: 2026-07-12 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c7e4a9d2f6b1"
down_revision = "f6b2a4d8c9e0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shifu_course_slugs",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column(
            "shifu_bid",
            sa.String(length=32),
            nullable=False,
            comment="Shifu business identifier",
        ),
        sa.Column(
            "slug",
            sa.String(length=48),
            nullable=False,
            comment="Globally unique and permanently reserved public course slug",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            comment="Monotonic slug version within the shifu",
        ),
        sa.Column(
            "is_current",
            sa.SmallInteger(),
            nullable=True,
            comment="Current marker: 1=current, NULL=historical alias",
        ),
        sa.Column(
            "generation_source",
            sa.String(length=16),
            nullable=False,
            comment="Slug generation source: llm, fallback, or manual",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            comment="Creation timestamp",
        ),
        sa.Column(
            "retired_at",
            sa.DateTime(),
            nullable=True,
            comment="UTC timestamp when this slug became a historical alias",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_shifu_course_slugs_positive_version",
        ),
        sa.CheckConstraint(
            "is_current IS NULL OR is_current = 1",
            name="ck_shifu_course_slugs_current_marker",
        ),
        sa.CheckConstraint(
            "((is_current IS NOT NULL AND retired_at IS NULL) OR "
            "(is_current IS NULL AND retired_at IS NOT NULL))",
            name="ck_shifu_course_slugs_retirement_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uk_shifu_course_slugs_slug"),
        sa.UniqueConstraint(
            "shifu_bid",
            "version",
            name="uk_shifu_course_slugs_version",
        ),
        sa.UniqueConstraint(
            "shifu_bid",
            "is_current",
            name="uk_shifu_course_slugs_current",
        ),
        comment="Current and historical public slug records for shifus",
        mysql_engine="InnoDB",
    )


def downgrade():
    op.drop_table("shifu_course_slugs")
