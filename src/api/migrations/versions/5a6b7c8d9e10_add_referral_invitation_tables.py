"""add referral invitation tables

Revision ID: 5a6b7c8d9e10
Revises: c5d8e1f2a3b4
Create Date: 2026-06-09 18:20:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "5a6b7c8d9e10"
down_revision = "c5d8e1f2a3b4"
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column, sa.Column, sa.Column]:
    return (
        sa.Column(
            "deleted", sa.SmallInteger(), nullable=False, comment="Deletion flag"
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, comment="Creation timestamp"
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, comment="Last update timestamp"
        ),
    )


def upgrade():
    deleted_column, created_at_column, updated_at_column = _timestamps()
    op.create_table(
        "referral_campaigns",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "campaign_bid",
            sa.String(length=36),
            nullable=False,
            comment="Campaign business identifier",
        ),
        sa.Column(
            "campaign_code",
            sa.String(length=64),
            nullable=False,
            comment="Campaign code",
        ),
        sa.Column(
            "campaign_name",
            sa.String(length=255),
            nullable=False,
            comment="Campaign name",
        ),
        sa.Column(
            "campaign_status",
            sa.SmallInteger(),
            nullable=False,
            comment="Campaign status",
        ),
        sa.Column(
            "feature_flag_key",
            sa.String(length=128),
            nullable=False,
            comment="Feature flag key",
        ),
        sa.Column(
            "starts_at",
            sa.DateTime(),
            nullable=True,
            comment="Campaign start timestamp",
        ),
        sa.Column(
            "ends_at", sa.DateTime(), nullable=True, comment="Campaign end timestamp"
        ),
        sa.Column(
            "invite_route_template",
            sa.String(length=255),
            nullable=False,
            comment="Invite route template",
        ),
        sa.Column(
            "inviter_eligibility",
            sa.JSON(),
            nullable=True,
            comment="Inviter eligibility config",
        ),
        sa.Column(
            "invitee_eligibility",
            sa.JSON(),
            nullable=True,
            comment="Invitee eligibility config",
        ),
        sa.Column(
            "invitee_benefit_policy",
            sa.String(length=64),
            nullable=False,
            comment="Invitee benefit policy",
        ),
        sa.Column(
            "rules_copy_i18n_key",
            sa.String(length=128),
            nullable=False,
            comment="Rules copy i18n key",
        ),
        sa.Column("metadata", sa.JSON(), nullable=True, comment="Campaign metadata"),
        deleted_column.copy(),
        created_at_column.copy(),
        updated_at_column.copy(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_bid", name="uq_referral_campaigns_campaign_bid"),
        sa.UniqueConstraint(
            "campaign_code", name="uq_referral_campaigns_campaign_code"
        ),
        comment="Referral campaign configuration",
    )
    op.create_index(
        "ix_referral_campaigns_campaign_bid", "referral_campaigns", ["campaign_bid"]
    )
    op.create_index(
        "ix_referral_campaigns_campaign_code", "referral_campaigns", ["campaign_code"]
    )
    op.create_index("ix_referral_campaigns_deleted", "referral_campaigns", ["deleted"])
    op.create_index(
        "ix_referral_campaigns_status_window",
        "referral_campaigns",
        ["campaign_status", "starts_at", "ends_at"],
    )

    op.create_table(
        "referral_campaign_reward_rules",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "reward_rule_bid",
            sa.String(length=36),
            nullable=False,
            comment="Reward rule business identifier",
        ),
        sa.Column(
            "campaign_bid",
            sa.String(length=36),
            nullable=False,
            comment="Campaign business identifier",
        ),
        sa.Column(
            "rule_code",
            sa.String(length=64),
            nullable=False,
            comment="Campaign-local rule code",
        ),
        sa.Column(
            "rule_status", sa.SmallInteger(), nullable=False, comment="Rule status"
        ),
        sa.Column(
            "trigger_event",
            sa.String(length=64),
            nullable=False,
            comment="Reward trigger event",
        ),
        sa.Column(
            "reward_target",
            sa.String(length=32),
            nullable=False,
            comment="Reward target",
        ),
        sa.Column(
            "reward_type", sa.String(length=64), nullable=False, comment="Reward type"
        ),
        sa.Column(
            "reward_product_code",
            sa.String(length=64),
            nullable=False,
            comment="Reward billing product code",
        ),
        sa.Column(
            "reward_cycle_count",
            sa.Integer(),
            nullable=False,
            comment="Reward cycle count",
        ),
        sa.Column(
            "reward_credit_amount",
            sa.Numeric(precision=20, scale=10),
            nullable=True,
            comment="Expected reward credit amount",
        ),
        sa.Column(
            "reward_credit_validity_days",
            sa.Integer(),
            nullable=True,
            comment="Reward credit validity days",
        ),
        sa.Column(
            "reward_cap_scope",
            sa.String(length=64),
            nullable=False,
            comment="Reward cap scope",
        ),
        sa.Column(
            "reward_cap_count", sa.Integer(), nullable=True, comment="Reward cap count"
        ),
        sa.Column(
            "reward_timing_policy",
            sa.String(length=64),
            nullable=False,
            comment="Reward timing policy",
        ),
        sa.Column("priority", sa.Integer(), nullable=False, comment="Rule priority"),
        sa.Column(
            "starts_at", sa.DateTime(), nullable=True, comment="Rule start timestamp"
        ),
        sa.Column(
            "ends_at", sa.DateTime(), nullable=True, comment="Rule end timestamp"
        ),
        sa.Column("metadata", sa.JSON(), nullable=True, comment="Rule metadata"),
        deleted_column.copy(),
        created_at_column.copy(),
        updated_at_column.copy(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "reward_rule_bid", name="uq_referral_campaign_reward_rules_reward_rule_bid"
        ),
        sa.UniqueConstraint(
            "campaign_bid",
            "rule_code",
            name="uq_referral_campaign_reward_rules_campaign_rule",
        ),
        comment="Referral campaign reward rules",
    )
    op.create_index(
        "ix_referral_campaign_reward_rules_reward_rule_bid",
        "referral_campaign_reward_rules",
        ["reward_rule_bid"],
    )
    op.create_index(
        "ix_referral_campaign_reward_rules_campaign_status_priority",
        "referral_campaign_reward_rules",
        ["campaign_bid", "rule_status", "priority"],
    )
    op.create_index(
        "ix_referral_campaign_reward_rules_deleted",
        "referral_campaign_reward_rules",
        ["deleted"],
    )
    op.create_index(
        "ix_referral_campaign_reward_rules_priority",
        "referral_campaign_reward_rules",
        ["priority"],
    )
    op.create_index(
        "ix_referral_campaign_reward_rules_rule_status",
        "referral_campaign_reward_rules",
        ["rule_status"],
    )
    op.create_index(
        "ix_referral_campaign_reward_rules_starts_at",
        "referral_campaign_reward_rules",
        ["starts_at"],
    )
    op.create_index(
        "ix_referral_campaign_reward_rules_ends_at",
        "referral_campaign_reward_rules",
        ["ends_at"],
    )
    op.create_index(
        "ix_referral_campaign_reward_rules_trigger_event",
        "referral_campaign_reward_rules",
        ["trigger_event"],
    )

    op.create_table(
        "referral_invite_codes",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "invite_code_bid",
            sa.String(length=36),
            nullable=False,
            comment="Invite code business identifier",
        ),
        sa.Column(
            "campaign_bid",
            sa.String(length=36),
            nullable=False,
            comment="Campaign business identifier",
        ),
        sa.Column(
            "inviter_user_bid",
            sa.String(length=36),
            nullable=False,
            comment="Inviter user business identifier",
        ),
        sa.Column(
            "invite_code",
            sa.String(length=32),
            nullable=False,
            comment="Public invite code",
        ),
        sa.Column(
            "status", sa.SmallInteger(), nullable=False, comment="Invite code status"
        ),
        sa.Column(
            "generated_at", sa.DateTime(), nullable=False, comment="Generated timestamp"
        ),
        deleted_column.copy(),
        created_at_column.copy(),
        updated_at_column.copy(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "invite_code_bid", name="uq_referral_invite_codes_code_bid"
        ),
        sa.UniqueConstraint("invite_code", name="uq_referral_invite_codes_invite_code"),
        sa.UniqueConstraint(
            "campaign_bid",
            "inviter_user_bid",
            "deleted",
            name="uq_referral_invite_codes_campaign_inviter_active",
        ),
        comment="Referral invite codes",
    )
    op.create_index(
        "ix_referral_invite_codes_campaign_bid",
        "referral_invite_codes",
        ["campaign_bid"],
    )
    op.create_index(
        "ix_referral_invite_codes_campaign_status",
        "referral_invite_codes",
        ["campaign_bid", "status"],
    )
    op.create_index(
        "ix_referral_invite_codes_deleted", "referral_invite_codes", ["deleted"]
    )
    op.create_index(
        "ix_referral_invite_codes_invite_code_bid",
        "referral_invite_codes",
        ["invite_code_bid"],
    )
    op.create_index(
        "ix_referral_invite_codes_inviter_user_bid",
        "referral_invite_codes",
        ["inviter_user_bid"],
    )
    op.create_index(
        "ix_referral_invite_codes_status", "referral_invite_codes", ["status"]
    )

    op.create_table(
        "referral_invite_events",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "event_bid",
            sa.String(length=36),
            nullable=False,
            comment="Event business identifier",
        ),
        sa.Column(
            "campaign_bid",
            sa.String(length=36),
            nullable=False,
            comment="Campaign business identifier",
        ),
        sa.Column(
            "event_type",
            sa.String(length=64),
            nullable=False,
            comment="Invite event type",
        ),
        sa.Column(
            "invite_code", sa.String(length=32), nullable=False, comment="Invite code"
        ),
        sa.Column(
            "inviter_user_bid",
            sa.String(length=36),
            nullable=False,
            comment="Inviter user business identifier",
        ),
        sa.Column(
            "session_id",
            sa.String(length=64),
            nullable=False,
            comment="Frontend session identifier",
        ),
        sa.Column(
            "client_ip_hash",
            sa.String(length=128),
            nullable=False,
            comment="Hashed client IP",
        ),
        sa.Column(
            "user_agent_hash",
            sa.String(length=128),
            nullable=False,
            comment="Hashed user agent",
        ),
        sa.Column(
            "landing_path",
            sa.String(length=512),
            nullable=False,
            comment="Landing path",
        ),
        sa.Column("metadata", sa.JSON(), nullable=True, comment="Event metadata"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, comment="Creation timestamp"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_bid", name="uq_referral_invite_events_event_bid"),
        comment="Referral invite funnel events",
    )
    op.create_index(
        "ix_referral_invite_events_campaign_bid",
        "referral_invite_events",
        ["campaign_bid"],
    )
    op.create_index(
        "ix_referral_invite_events_campaign_type_created",
        "referral_invite_events",
        ["campaign_bid", "event_type", "created_at"],
    )
    op.create_index(
        "ix_referral_invite_events_created_at", "referral_invite_events", ["created_at"]
    )
    op.create_index(
        "ix_referral_invite_events_event_bid", "referral_invite_events", ["event_bid"]
    )
    op.create_index(
        "ix_referral_invite_events_event_type", "referral_invite_events", ["event_type"]
    )
    op.create_index(
        "ix_referral_invite_events_invite_code",
        "referral_invite_events",
        ["invite_code"],
    )
    op.create_index(
        "ix_referral_invite_events_inviter_user_bid",
        "referral_invite_events",
        ["inviter_user_bid"],
    )
    op.create_index(
        "ix_referral_invite_events_session_id", "referral_invite_events", ["session_id"]
    )

    op.create_table(
        "referral_invite_relations",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "relation_bid",
            sa.String(length=36),
            nullable=False,
            comment="Relation business identifier",
        ),
        sa.Column(
            "campaign_bid",
            sa.String(length=36),
            nullable=False,
            comment="Campaign business identifier",
        ),
        sa.Column(
            "reward_rule_bid",
            sa.String(length=36),
            nullable=False,
            comment="Reward rule business identifier",
        ),
        sa.Column(
            "invite_code", sa.String(length=32), nullable=False, comment="Invite code"
        ),
        sa.Column(
            "inviter_user_bid",
            sa.String(length=36),
            nullable=False,
            comment="Inviter user business identifier",
        ),
        sa.Column(
            "invitee_user_bid",
            sa.String(length=36),
            nullable=False,
            comment="Invitee user business identifier",
        ),
        sa.Column(
            "invitee_mobile_snapshot",
            sa.String(length=32),
            nullable=False,
            comment="Invitee mobile snapshot",
        ),
        sa.Column("bound_at", sa.DateTime(), nullable=False, comment="Bound timestamp"),
        sa.Column(
            "registration_source",
            sa.String(length=32),
            nullable=False,
            comment="Registration source",
        ),
        sa.Column(
            "reward_eligible",
            sa.SmallInteger(),
            nullable=False,
            comment="Reward eligible flag",
        ),
        sa.Column(
            "relation_status",
            sa.SmallInteger(),
            nullable=False,
            comment="Relation status",
        ),
        sa.Column(
            "abnormal_status",
            sa.SmallInteger(),
            nullable=False,
            comment="Abnormal status",
        ),
        sa.Column("metadata", sa.JSON(), nullable=True, comment="Relation metadata"),
        deleted_column.copy(),
        created_at_column.copy(),
        updated_at_column.copy(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("relation_bid", name="uq_referral_invite_relations_bid"),
        sa.UniqueConstraint(
            "invitee_user_bid",
            "deleted",
            name="uq_referral_invite_relations_invitee_active",
        ),
        comment="Referral invitee binding relations",
    )
    op.create_index(
        "ix_referral_invite_relations_abnormal_status",
        "referral_invite_relations",
        ["abnormal_status"],
    )
    op.create_index(
        "ix_referral_invite_relations_bound_at",
        "referral_invite_relations",
        ["bound_at"],
    )
    op.create_index(
        "ix_referral_invite_relations_campaign_bound",
        "referral_invite_relations",
        ["campaign_bid", "bound_at"],
    )
    op.create_index(
        "ix_referral_invite_relations_campaign_bid",
        "referral_invite_relations",
        ["campaign_bid"],
    )
    op.create_index(
        "ix_referral_invite_relations_deleted", "referral_invite_relations", ["deleted"]
    )
    op.create_index(
        "ix_referral_invite_relations_invitee_user_bid",
        "referral_invite_relations",
        ["invitee_user_bid"],
    )
    op.create_index(
        "ix_referral_invite_relations_inviter_campaign_status",
        "referral_invite_relations",
        ["inviter_user_bid", "campaign_bid", "relation_status"],
    )
    op.create_index(
        "ix_referral_invite_relations_inviter_user_bid",
        "referral_invite_relations",
        ["inviter_user_bid"],
    )
    op.create_index(
        "ix_referral_invite_relations_invite_code",
        "referral_invite_relations",
        ["invite_code"],
    )
    op.create_index(
        "ix_referral_invite_relations_relation_bid",
        "referral_invite_relations",
        ["relation_bid"],
    )
    op.create_index(
        "ix_referral_invite_relations_relation_status",
        "referral_invite_relations",
        ["relation_status"],
    )
    op.create_index(
        "ix_referral_invite_relations_reward_rule_bid",
        "referral_invite_relations",
        ["reward_rule_bid"],
    )

    op.create_table(
        "referral_invite_rewards",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "reward_bid",
            sa.String(length=36),
            nullable=False,
            comment="Reward business identifier",
        ),
        sa.Column(
            "campaign_bid",
            sa.String(length=36),
            nullable=False,
            comment="Campaign business identifier",
        ),
        sa.Column(
            "reward_rule_bid",
            sa.String(length=36),
            nullable=False,
            comment="Reward rule business identifier",
        ),
        sa.Column(
            "relation_bid",
            sa.String(length=36),
            nullable=False,
            comment="Relation business identifier",
        ),
        sa.Column(
            "inviter_user_bid",
            sa.String(length=36),
            nullable=False,
            comment="Inviter user business identifier",
        ),
        sa.Column(
            "invitee_user_bid",
            sa.String(length=36),
            nullable=False,
            comment="Invitee user business identifier",
        ),
        sa.Column(
            "reward_status", sa.SmallInteger(), nullable=False, comment="Reward status"
        ),
        sa.Column(
            "reward_target",
            sa.String(length=32),
            nullable=False,
            comment="Reward target",
        ),
        sa.Column(
            "reward_type", sa.String(length=64), nullable=False, comment="Reward type"
        ),
        sa.Column(
            "reward_product_code",
            sa.String(length=64),
            nullable=False,
            comment="Reward billing product code",
        ),
        sa.Column(
            "reward_cycle_count",
            sa.Integer(),
            nullable=False,
            comment="Reward cycle count",
        ),
        sa.Column(
            "reward_credit_amount",
            sa.Numeric(precision=20, scale=10),
            nullable=True,
            comment="Reward credit amount",
        ),
        sa.Column(
            "reward_credit_validity_days",
            sa.Integer(),
            nullable=True,
            comment="Reward credit validity days",
        ),
        sa.Column(
            "reward_cap_scope",
            sa.String(length=64),
            nullable=False,
            comment="Reward cap scope",
        ),
        sa.Column(
            "reward_cap_count", sa.Integer(), nullable=True, comment="Reward cap count"
        ),
        sa.Column(
            "reward_timing_policy",
            sa.String(length=64),
            nullable=False,
            comment="Reward timing policy",
        ),
        sa.Column("rule_snapshot", sa.JSON(), nullable=True, comment="Rule snapshot"),
        sa.Column(
            "billing_artifacts", sa.JSON(), nullable=True, comment="Billing artifacts"
        ),
        sa.Column(
            "operator_note",
            sa.String(length=500),
            nullable=False,
            comment="Operator note",
        ),
        sa.Column(
            "effective_at",
            sa.DateTime(),
            nullable=True,
            comment="Reward effective timestamp",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(),
            nullable=True,
            comment="Reward expiration timestamp",
        ),
        deleted_column.copy(),
        created_at_column.copy(),
        updated_at_column.copy(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reward_bid", name="uq_referral_invite_rewards_reward_bid"),
        sa.UniqueConstraint(
            "relation_bid",
            "reward_rule_bid",
            "deleted",
            name="uq_referral_invite_rewards_relation_rule_active",
        ),
        comment="Referral invite reward audit rows",
    )
    op.create_index(
        "ix_referral_invite_rewards_campaign_bid",
        "referral_invite_rewards",
        ["campaign_bid"],
    )
    op.create_index(
        "ix_referral_invite_rewards_deleted", "referral_invite_rewards", ["deleted"]
    )
    op.create_index(
        "ix_referral_invite_rewards_invitee_user_bid",
        "referral_invite_rewards",
        ["invitee_user_bid"],
    )
    op.create_index(
        "ix_referral_invite_rewards_inviter_campaign_status",
        "referral_invite_rewards",
        ["inviter_user_bid", "campaign_bid", "reward_status"],
    )
    op.create_index(
        "ix_referral_invite_rewards_inviter_user_bid",
        "referral_invite_rewards",
        ["inviter_user_bid"],
    )
    op.create_index(
        "ix_referral_invite_rewards_relation_bid",
        "referral_invite_rewards",
        ["relation_bid"],
    )
    op.create_index(
        "ix_referral_invite_rewards_reward_bid",
        "referral_invite_rewards",
        ["reward_bid"],
    )
    op.create_index(
        "ix_referral_invite_rewards_reward_rule_bid",
        "referral_invite_rewards",
        ["reward_rule_bid"],
    )
    op.create_index(
        "ix_referral_invite_rewards_reward_status",
        "referral_invite_rewards",
        ["reward_status"],
    )


def downgrade():
    op.drop_table("referral_invite_rewards")
    op.drop_table("referral_invite_relations")
    op.drop_table("referral_invite_events")
    op.drop_table("referral_invite_codes")
    op.drop_table("referral_campaign_reward_rules")
    op.drop_table("referral_campaigns")
