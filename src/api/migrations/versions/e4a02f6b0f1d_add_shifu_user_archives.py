"""add shifu_user_archives per-user archive table

Revision ID: e4a02f6b0f1d
Revises: dc61b7d3e0c0
Create Date: 2026-01-16 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e4a02f6b0f1d"
down_revision = "dc61b7d3e0c0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shifu_user_archives",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "shifu_bid",
            sa.String(length=32),
            nullable=False,
            index=True,
            server_default="",
            comment="Shifu business identifier",
        ),
        sa.Column(
            "user_bid",
            sa.String(length=32),
            nullable=False,
            index=True,
            server_default="",
            comment="User business identifier",
        ),
        sa.Column(
            "archived",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Archive flag: 0=active, 1=archived",
        ),
        sa.Column(
            "archived_at",
            sa.DateTime(),
            nullable=True,
            comment="Archived timestamp",
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
            onupdate=sa.func.now(),
            comment="Last update timestamp",
        ),
        sa.UniqueConstraint(
            "shifu_bid", "user_bid", name="uk_shifu_user_archive_bid_user"
        ),
        mysql_engine="InnoDB",
    )

    # Backfill owner archive state for existing archived courses
    op.execute(
        """
        INSERT INTO shifu_user_archives (shifu_bid, user_bid, archived, archived_at, created_at, updated_at)
        SELECT DISTINCT
            ds.shifu_bid,
            ds.created_user_bid,
            1,
            COALESCE(ds.archived_at, NOW()),
            NOW(),
            NOW()
        FROM shifu_draft_shifus ds
        WHERE ds.deleted = 0 AND ds.archived = 1
        ON DUPLICATE KEY UPDATE
            archived = VALUES(archived),
            archived_at = VALUES(archived_at),
            updated_at = VALUES(updated_at)
        """
    )


def downgrade():
    op.drop_table("shifu_user_archives")
