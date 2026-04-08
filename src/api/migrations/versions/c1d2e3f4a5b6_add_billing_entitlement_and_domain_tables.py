"""add billing entitlement and domain tables

Revision ID: c1d2e3f4a5b6
Revises: ab12cd34ef56
Create Date: 2026-04-08 21:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "c1d2e3f4a5b6"
down_revision = "ab12cd34ef56"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_entitlements",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "entitlement_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing entitlement business identifier",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "source_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Entitlement source type code",
        ),
        sa.Column(
            "source_bid",
            sa.String(length=36),
            nullable=False,
            comment="Entitlement source business identifier",
        ),
        sa.Column(
            "branding_enabled",
            sa.SmallInteger(),
            nullable=False,
            comment="Branding enabled flag",
        ),
        sa.Column(
            "custom_domain_enabled",
            sa.SmallInteger(),
            nullable=False,
            comment="Custom domain enabled flag",
        ),
        sa.Column(
            "priority_class",
            sa.SmallInteger(),
            nullable=False,
            comment="Priority class code",
        ),
        sa.Column(
            "max_concurrency",
            sa.Integer(),
            nullable=False,
            comment="Max concurrency",
        ),
        sa.Column(
            "analytics_tier",
            sa.SmallInteger(),
            nullable=False,
            comment="Analytics tier code",
        ),
        sa.Column(
            "support_tier",
            sa.SmallInteger(),
            nullable=False,
            comment="Support tier code",
        ),
        sa.Column(
            "feature_payload",
            sa.JSON(),
            nullable=True,
            comment="Entitlement feature payload",
        ),
        sa.Column(
            "effective_from",
            sa.DateTime(),
            nullable=False,
            comment="Effective from timestamp",
        ),
        sa.Column(
            "effective_to",
            sa.DateTime(),
            nullable=True,
            comment="Effective to timestamp",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entitlement_bid",
            name="uq_billing_entitlements_entitlement_bid",
        ),
        comment="Billing entitlements",
    )
    with op.batch_alter_table("billing_entitlements", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_entitlements_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_entitlements_creator_effective_to",
            ["creator_bid", "effective_to"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_entitlements_deleted"),
            ["deleted"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_entitlements_effective_from"),
            ["effective_from"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_entitlements_effective_to"),
            ["effective_to"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_entitlements_entitlement_bid"),
            ["entitlement_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_entitlements_source_bid"),
            ["source_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_entitlements_source_type"),
            ["source_type"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_entitlements_source_type_source_bid",
            ["source_type", "source_bid"],
            unique=False,
        )

    op.create_table(
        "billing_domain_bindings",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "domain_binding_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing domain binding business identifier",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "host",
            sa.String(length=255),
            nullable=False,
            comment="Custom domain host",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Domain binding status code",
        ),
        sa.Column(
            "verification_method",
            sa.SmallInteger(),
            nullable=False,
            comment="Verification method code",
        ),
        sa.Column(
            "verification_token",
            sa.String(length=255),
            nullable=False,
            comment="Verification token",
        ),
        sa.Column(
            "last_verified_at",
            sa.DateTime(),
            nullable=True,
            comment="Last verified timestamp",
        ),
        sa.Column(
            "ssl_status",
            sa.SmallInteger(),
            nullable=False,
            comment="SSL status code",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Domain binding metadata",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "domain_binding_bid",
            name="uq_billing_domain_bindings_domain_binding_bid",
        ),
        sa.UniqueConstraint(
            "host",
            name="uq_billing_domain_bindings_host",
        ),
        comment="Billing domain bindings",
    )
    with op.batch_alter_table("billing_domain_bindings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_domain_bindings_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_domain_bindings_creator_status",
            ["creator_bid", "status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_domain_bindings_deleted"),
            ["deleted"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_domain_bindings_domain_binding_bid"),
            ["domain_binding_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_domain_bindings_host"),
            ["host"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_domain_bindings_status"),
            ["status"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("billing_domain_bindings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_billing_domain_bindings_status"))
        batch_op.drop_index(batch_op.f("ix_billing_domain_bindings_host"))
        batch_op.drop_index(batch_op.f("ix_billing_domain_bindings_domain_binding_bid"))
        batch_op.drop_index("ix_billing_domain_bindings_creator_status")
        batch_op.drop_index(batch_op.f("ix_billing_domain_bindings_creator_bid"))
        batch_op.drop_index(batch_op.f("ix_billing_domain_bindings_deleted"))

    op.drop_table("billing_domain_bindings")

    with op.batch_alter_table("billing_entitlements", schema=None) as batch_op:
        batch_op.drop_index("ix_billing_entitlements_source_type_source_bid")
        batch_op.drop_index(batch_op.f("ix_billing_entitlements_source_type"))
        batch_op.drop_index(batch_op.f("ix_billing_entitlements_source_bid"))
        batch_op.drop_index(batch_op.f("ix_billing_entitlements_entitlement_bid"))
        batch_op.drop_index(batch_op.f("ix_billing_entitlements_effective_to"))
        batch_op.drop_index(batch_op.f("ix_billing_entitlements_effective_from"))
        batch_op.drop_index("ix_billing_entitlements_creator_effective_to")
        batch_op.drop_index(batch_op.f("ix_billing_entitlements_creator_bid"))
        batch_op.drop_index(batch_op.f("ix_billing_entitlements_deleted"))

    op.drop_table("billing_entitlements")
