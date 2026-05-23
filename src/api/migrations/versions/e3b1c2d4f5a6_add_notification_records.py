"""add notification records

Revision ID: e3b1c2d4f5a6
Revises: d2f4a7c9b8e1
Create Date: 2026-05-21 16:25:00.000000

"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "e3b1c2d4f5a6"
down_revision = "d2f4a7c9b8e1"
branch_labels = None
depends_on = None

CONFIG_KEY = "BILL_CREDIT_NOTIFICATION_SMS_CONFIG"
CONFIG_BID = "bill-config-credit-notification-sms"

DEFAULT_POLICY = {
    "enabled": False,
    "channel": "sms",
    "types": {
        "credit_expiring": {
            "enabled": False,
            "template_code": "",
            "windows": ["7d", "3d", "1d", "0d"],
            "merge_same_creator": True,
        },
        "credit_granted": {
            "enabled": False,
            "template_code": "",
        },
        "low_balance": {
            "enabled": False,
            "template_code": "",
            "thresholds": [{"kind": "fixed", "value": "0"}],
        },
    },
    "softlimit": {
        "enabled": False,
        "threshold": {"kind": "fixed", "value": "0"},
        "teacher_page_alert": True,
        "disable_debug": True,
        "sms_enabled": False,
    },
    "frequency": {
        "per_mobile_per_day": 3,
        "per_creator_per_type_per_day": 1,
    },
    "quiet_hours": {
        "enabled": False,
        "start": "22:00",
        "end": "09:00",
        "timezone": "Asia/Shanghai",
    },
    "blacklist": {
        "creator_bids": [],
        "mobiles": [],
    },
    "opt_out": {
        "creator_bids": [],
        "mobiles": [],
    },
    "budget": {
        "daily_sms_limit": 0,
        "dry_run_required": True,
        "sms_unit_cost": "0",
    },
}


def upgrade():
    op.create_table(
        "notification_records",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "notification_bid",
            sa.String(length=36),
            nullable=False,
            comment="Notification business identifier",
        ),
        sa.Column(
            "notification_type",
            sa.String(length=64),
            nullable=False,
            comment="Notification type",
        ),
        sa.Column(
            "channel",
            sa.String(length=32),
            nullable=False,
            comment="Delivery channel",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "target_user_bid",
            sa.String(length=36),
            nullable=False,
            comment="Target user business identifier",
        ),
        sa.Column(
            "mobile_snapshot",
            sa.String(length=32),
            nullable=False,
            comment="Recipient mobile snapshot",
        ),
        sa.Column(
            "source_type",
            sa.String(length=64),
            nullable=False,
            comment="Notification source type",
        ),
        sa.Column(
            "source_bid",
            sa.String(length=36),
            nullable=False,
            comment="Notification source business identifier",
        ),
        sa.Column(
            "dedupe_key",
            sa.String(length=255),
            nullable=False,
            comment="Notification idempotency key",
        ),
        sa.Column(
            "status",
            sa.String(length=64),
            nullable=False,
            comment="Notification delivery status",
        ),
        sa.Column(
            "template_code",
            sa.String(length=128),
            nullable=False,
            comment="SMS template code snapshot",
        ),
        sa.Column(
            "template_params",
            sa.JSON(),
            nullable=True,
            comment="Template parameters snapshot",
        ),
        sa.Column(
            "policy_snapshot",
            sa.JSON(),
            nullable=True,
            comment="Notification policy snapshot",
        ),
        sa.Column(
            "provider_response",
            sa.JSON(),
            nullable=True,
            comment="Provider response summary",
        ),
        sa.Column(
            "error_code",
            sa.String(length=128),
            nullable=False,
            comment="Error code",
        ),
        sa.Column(
            "error_message",
            sa.String(length=1024),
            nullable=False,
            comment="Error message",
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(),
            nullable=True,
            comment="Notification requested timestamp",
        ),
        sa.Column(
            "attempted_at",
            sa.DateTime(),
            nullable=True,
            comment="Last delivery attempt timestamp",
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(),
            nullable=True,
            comment="Provider accepted timestamp",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Notification metadata",
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
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notification_bid",
            name="uq_notification_records_notification_bid",
        ),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_records_dedupe_key"),
        comment="Notification delivery records",
    )
    op.create_index(
        op.f("ix_notification_records_deleted"),
        "notification_records",
        ["deleted"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_records_notification_type"),
        "notification_records",
        ["notification_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_records_channel"),
        "notification_records",
        ["channel"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_records_creator_bid"),
        "notification_records",
        ["creator_bid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_records_target_user_bid"),
        "notification_records",
        ["target_user_bid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_records_mobile_snapshot"),
        "notification_records",
        ["mobile_snapshot"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_records_source_type"),
        "notification_records",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_records_source_bid"),
        "notification_records",
        ["source_bid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_records_status"),
        "notification_records",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_records_requested_at"),
        "notification_records",
        ["requested_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_records_attempted_at"),
        "notification_records",
        ["attempted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_records_sent_at"),
        "notification_records",
        ["sent_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_records_status_type_created",
        "notification_records",
        ["status", "notification_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_records_creator_created",
        "notification_records",
        ["creator_bid", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_records_source_type_source_bid",
        "notification_records",
        ["source_type", "source_bid"],
        unique=False,
    )
    op.create_table(
        "notification_templates",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "notification_template_bid",
            sa.String(length=36),
            nullable=False,
            comment="Notification template business identifier",
        ),
        sa.Column(
            "channel",
            sa.String(length=32),
            nullable=False,
            comment="Notification channel",
        ),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
            comment="Notification provider",
        ),
        sa.Column(
            "template_code",
            sa.String(length=128),
            nullable=False,
            comment="Provider template code",
        ),
        sa.Column(
            "template_name",
            sa.String(length=255),
            nullable=False,
            comment="Provider template name",
        ),
        sa.Column(
            "template_content",
            sa.Text(),
            nullable=True,
            comment="Provider template content",
        ),
        sa.Column(
            "template_status",
            sa.String(length=64),
            nullable=False,
            comment="Provider template audit status",
        ),
        sa.Column(
            "template_type",
            sa.String(length=64),
            nullable=False,
            comment="Provider template type",
        ),
        sa.Column(
            "variable_attribute",
            sa.JSON(),
            nullable=True,
            comment="Provider variable attribute payload",
        ),
        sa.Column(
            "provider_response",
            sa.JSON(),
            nullable=True,
            comment="Provider template query response summary",
        ),
        sa.Column(
            "placeholders",
            sa.JSON(),
            nullable=True,
            comment="Parsed template placeholders",
        ),
        sa.Column(
            "sync_status",
            sa.String(length=64),
            nullable=False,
            comment="Template sync status",
        ),
        sa.Column(
            "error_code",
            sa.String(length=128),
            nullable=False,
            comment="Template sync error code",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Template sync error message",
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(),
            nullable=True,
            comment="Last provider sync timestamp",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Notification template metadata",
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
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notification_template_bid",
            name="uq_notification_templates_template_bid",
        ),
        sa.UniqueConstraint(
            "channel",
            "provider",
            "template_code",
            name="uq_notification_templates_channel_provider_code",
        ),
        comment="Notification provider template metadata",
    )
    op.create_index(
        op.f("ix_notification_templates_deleted"),
        "notification_templates",
        ["deleted"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_templates_notification_template_bid"),
        "notification_templates",
        ["notification_template_bid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_templates_channel"),
        "notification_templates",
        ["channel"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_templates_provider"),
        "notification_templates",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_templates_template_code"),
        "notification_templates",
        ["template_code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_templates_template_status"),
        "notification_templates",
        ["template_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_templates_template_type"),
        "notification_templates",
        ["template_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_templates_sync_status"),
        "notification_templates",
        ["sync_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_templates_last_synced_at"),
        "notification_templates",
        ["last_synced_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_templates_provider_status",
        "notification_templates",
        ["provider", "sync_status"],
        unique=False,
    )

    sys_configs = sa.table(
        "sys_configs",
        sa.column("config_bid", sa.String),
        sa.column("key", sa.String),
        sa.column("value", sa.Text),
        sa.column("is_encrypted", sa.SmallInteger),
        sa.column("remark", sa.Text),
        sa.column("deleted", sa.SmallInteger),
        sa.column("updated_by", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    bind = op.get_bind()
    existing = bind.execute(
        sa.text(
            "select id from sys_configs where `key` = :key and deleted = 0 limit 1"
        ),
        {"key": CONFIG_KEY},
    ).first()
    if existing is None:
        bind.execute(
            sys_configs.insert().values(
                config_bid=CONFIG_BID,
                key=CONFIG_KEY,
                value=json.dumps(DEFAULT_POLICY, separators=(",", ":"), sort_keys=True),
                is_encrypted=0,
                remark="Credit notification SMS policy config",
                deleted=0,
                updated_by="system",
                created_at=sa.func.now(),
                updated_at=sa.func.now(),
            )
        )


def downgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "update sys_configs set deleted = 1 where `key` = :key and config_bid = :config_bid"
        ),
        {"key": CONFIG_KEY, "config_bid": CONFIG_BID},
    )
    op.drop_table("notification_templates")
    op.drop_table("notification_records")
