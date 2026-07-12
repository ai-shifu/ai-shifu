"""add immutable shifu course slugs

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
            comment="Globally unique public course slug",
        ),
        sa.Column(
            "generation_source",
            sa.String(length=16),
            nullable=False,
            comment="Slug generation source: llm or fallback",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            comment="Creation timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shifu_bid", name="uk_shifu_course_slugs_shifu_bid"),
        sa.UniqueConstraint("slug", name="uk_shifu_course_slugs_slug"),
        comment="Immutable public slug bindings for shifus",
        mysql_engine="InnoDB",
    )


def downgrade():
    op.drop_table("shifu_course_slugs")
