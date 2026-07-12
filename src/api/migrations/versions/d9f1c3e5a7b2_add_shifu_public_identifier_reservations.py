"""add shifu public identifier reservations

Revision ID: d9f1c3e5a7b2
Revises: c7e4a9d2f6b1
Create Date: 2026-07-12 14:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d9f1c3e5a7b2"
down_revision = "c7e4a9d2f6b1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shifu_public_identifiers",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column(
            "identifier",
            sa.String(length=48),
            nullable=False,
            comment="Globally unique public BID or slug",
        ),
        sa.Column(
            "shifu_bid",
            sa.String(length=32),
            nullable=False,
            comment="Canonical shifu business identifier",
        ),
        sa.Column(
            "identifier_type",
            sa.String(length=8),
            nullable=False,
            comment="Identifier kind: bid or slug",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            comment="UTC reservation timestamp",
        ),
        sa.CheckConstraint(
            "identifier_type IN ('bid', 'slug')",
            name="ck_shifu_public_identifiers_type",
        ),
        sa.CheckConstraint(
            "identifier_type <> 'bid' OR identifier = shifu_bid",
            name="ck_shifu_public_identifiers_bid_owner",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "identifier",
            name="uk_shifu_public_identifiers_identifier",
        ),
        comment="Atomic BID and slug reservations for public course routes",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_shifu_public_identifiers_shifu_bid",
        "shifu_public_identifiers",
        ["shifu_bid"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_shifu_public_identifiers_shifu_bid",
        table_name="shifu_public_identifiers",
    )
    op.drop_table("shifu_public_identifiers")
