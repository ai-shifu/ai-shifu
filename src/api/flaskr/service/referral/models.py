"""SQLAlchemy models for referral campaign and invite rewards."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT
from flaskr.util.datetime import now_utc

from flaskr.dao import db

from .consts import (
    REFERRAL_ABNORMAL_STATUS_NORMAL,
    REFERRAL_CAMPAIGN_STATUS_DRAFT,
    REFERRAL_INVITE_CODE_STATUS_ACTIVE,
    REFERRAL_RELATION_STATUS_REGISTERED,
    REFERRAL_REWARD_STATUS_GENERATED,
    REFERRAL_REWARD_TARGET_INVITER,
    REFERRAL_REWARD_TIMING_IMMEDIATE_EXTEND_OR_DEFER,
    REFERRAL_REWARD_TYPE_BILLING_PLAN_CYCLE,
    REFERRAL_RULE_STATUS_DRAFT,
    REFERRAL_TRIGGER_INVITED_REGISTRATION,
)


REFERRAL_CREDIT_NUMERIC = Numeric(20, 10)


class ReferralTableMixin:
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Primary key")
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Deletion flag",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=now_utc,
        comment="Creation timestamp",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=now_utc,
        onupdate=now_utc,
        comment="Last update timestamp",
    )


class ReferralCampaign(ReferralTableMixin, db.Model):
    __tablename__ = "referral_campaigns"
    __table_args__ = (
        UniqueConstraint("campaign_bid", name="uq_referral_campaigns_campaign_bid"),
        UniqueConstraint("campaign_code", name="uq_referral_campaigns_campaign_code"),
        Index(
            "ix_referral_campaigns_status_window",
            "campaign_status",
            "starts_at",
            "ends_at",
        ),
        {"comment": "Referral campaign configuration"},
    )

    campaign_bid = Column(String(36), nullable=False, default="", index=True)
    campaign_code = Column(String(64), nullable=False, default="", index=True)
    campaign_name = Column(String(255), nullable=False, default="")
    campaign_status = Column(
        SmallInteger,
        nullable=False,
        default=REFERRAL_CAMPAIGN_STATUS_DRAFT,
        index=True,
    )
    feature_flag_key = Column(String(128), nullable=False, default="")
    starts_at = Column(DateTime, nullable=True, index=True)
    ends_at = Column(DateTime, nullable=True, index=True)
    invite_route_template = Column(String(255), nullable=False, default="")
    inviter_eligibility = Column(JSON, nullable=True)
    invitee_eligibility = Column(JSON, nullable=True)
    invitee_benefit_policy = Column(String(64), nullable=False, default="")
    rules_copy_i18n_key = Column(String(128), nullable=False, default="")
    metadata_json = Column("metadata", JSON, nullable=True)


class ReferralCampaignRewardRule(ReferralTableMixin, db.Model):
    __tablename__ = "referral_campaign_reward_rules"
    __table_args__ = (
        UniqueConstraint(
            "reward_rule_bid",
            name="uq_referral_campaign_reward_rules_reward_rule_bid",
        ),
        UniqueConstraint(
            "campaign_bid",
            "rule_code",
            name="uq_referral_campaign_reward_rules_campaign_rule",
        ),
        Index(
            "ix_referral_campaign_reward_rules_campaign_status_priority",
            "campaign_bid",
            "rule_status",
            "priority",
        ),
        {"comment": "Referral campaign reward rules"},
    )

    reward_rule_bid = Column(String(36), nullable=False, default="", index=True)
    campaign_bid = Column(String(36), nullable=False, default="", index=True)
    rule_code = Column(String(64), nullable=False, default="")
    rule_status = Column(
        SmallInteger,
        nullable=False,
        default=REFERRAL_RULE_STATUS_DRAFT,
        index=True,
    )
    trigger_event = Column(
        String(64),
        nullable=False,
        default=REFERRAL_TRIGGER_INVITED_REGISTRATION,
        index=True,
    )
    reward_target = Column(
        String(32),
        nullable=False,
        default=REFERRAL_REWARD_TARGET_INVITER,
    )
    reward_type = Column(
        String(64),
        nullable=False,
        default=REFERRAL_REWARD_TYPE_BILLING_PLAN_CYCLE,
    )
    reward_product_code = Column(String(64), nullable=False, default="")
    reward_cycle_count = Column(Integer, nullable=False, default=1)
    reward_credit_amount = Column(REFERRAL_CREDIT_NUMERIC, nullable=True)
    reward_credit_validity_days = Column(Integer, nullable=True)
    reward_cap_scope = Column(String(64), nullable=False, default="none")
    reward_cap_count = Column(Integer, nullable=True)
    reward_timing_policy = Column(
        String(64),
        nullable=False,
        default=REFERRAL_REWARD_TIMING_IMMEDIATE_EXTEND_OR_DEFER,
    )
    priority = Column(Integer, nullable=False, default=0, index=True)
    starts_at = Column(DateTime, nullable=True, index=True)
    ends_at = Column(DateTime, nullable=True, index=True)
    metadata_json = Column("metadata", JSON, nullable=True)

    def to_snapshot(self) -> dict[str, object]:
        amount = self.reward_credit_amount
        return {
            "reward_rule_bid": self.reward_rule_bid,
            "rule_code": self.rule_code,
            "trigger_event": self.trigger_event,
            "reward_target": self.reward_target,
            "reward_type": self.reward_type,
            "reward_product_code": self.reward_product_code,
            "reward_cycle_count": self.reward_cycle_count,
            "reward_credit_amount": str(amount) if amount is not None else None,
            "reward_credit_validity_days": self.reward_credit_validity_days,
            "reward_cap_scope": self.reward_cap_scope,
            "reward_cap_count": self.reward_cap_count,
            "reward_timing_policy": self.reward_timing_policy,
            "priority": self.priority,
            "metadata": self.metadata_json or {},
        }


class ReferralInviteCode(ReferralTableMixin, db.Model):
    __tablename__ = "referral_invite_codes"
    __table_args__ = (
        UniqueConstraint("invite_code_bid", name="uq_referral_invite_codes_code_bid"),
        UniqueConstraint("invite_code", name="uq_referral_invite_codes_invite_code"),
        UniqueConstraint(
            "campaign_bid",
            "inviter_user_bid",
            "deleted",
            name="uq_referral_invite_codes_campaign_inviter_active",
        ),
        Index(
            "ix_referral_invite_codes_campaign_status",
            "campaign_bid",
            "status",
        ),
        {"comment": "Referral invite codes"},
    )

    invite_code_bid = Column(String(36), nullable=False, default="", index=True)
    campaign_bid = Column(String(36), nullable=False, default="", index=True)
    inviter_user_bid = Column(String(36), nullable=False, default="", index=True)
    invite_code = Column(String(32), nullable=False, default="")
    status = Column(
        SmallInteger,
        nullable=False,
        default=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
        index=True,
    )
    generated_at = Column(DateTime, nullable=False, default=now_utc)


class ReferralInviteEvent(db.Model):
    __tablename__ = "referral_invite_events"
    __table_args__ = (
        UniqueConstraint("event_bid", name="uq_referral_invite_events_event_bid"),
        Index(
            "ix_referral_invite_events_campaign_type_created",
            "campaign_bid",
            "event_type",
            "created_at",
        ),
        Index("ix_referral_invite_events_invite_code", "invite_code"),
        {"comment": "Referral invite funnel events"},
    )

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Primary key")
    event_bid = Column(String(36), nullable=False, default="", index=True)
    campaign_bid = Column(String(36), nullable=False, default="", index=True)
    event_type = Column(String(64), nullable=False, default="", index=True)
    invite_code = Column(String(32), nullable=False, default="")
    inviter_user_bid = Column(String(36), nullable=False, default="", index=True)
    session_id = Column(String(64), nullable=False, default="", index=True)
    client_ip_hash = Column(String(128), nullable=False, default="")
    user_agent_hash = Column(String(128), nullable=False, default="")
    landing_path = Column(String(512), nullable=False, default="")
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc, index=True)


class ReferralInviteRelation(ReferralTableMixin, db.Model):
    __tablename__ = "referral_invite_relations"
    __table_args__ = (
        UniqueConstraint("relation_bid", name="uq_referral_invite_relations_bid"),
        UniqueConstraint(
            "invitee_user_bid",
            "deleted",
            name="uq_referral_invite_relations_invitee_active",
        ),
        Index(
            "ix_referral_invite_relations_inviter_campaign_status",
            "inviter_user_bid",
            "campaign_bid",
            "relation_status",
        ),
        Index(
            "ix_referral_invite_relations_campaign_bound",
            "campaign_bid",
            "bound_at",
        ),
        {"comment": "Referral invitee binding relations"},
    )

    relation_bid = Column(String(36), nullable=False, default="", index=True)
    campaign_bid = Column(String(36), nullable=False, default="", index=True)
    reward_rule_bid = Column(String(36), nullable=False, default="", index=True)
    invite_code = Column(String(32), nullable=False, default="", index=True)
    inviter_user_bid = Column(String(36), nullable=False, default="", index=True)
    invitee_user_bid = Column(String(36), nullable=False, default="", index=True)
    invitee_mobile_snapshot = Column(String(32), nullable=False, default="")
    bound_at = Column(DateTime, nullable=False, default=now_utc, index=True)
    registration_source = Column(String(32), nullable=False, default="phone")
    reward_eligible = Column(SmallInteger, nullable=False, default=0)
    relation_status = Column(
        SmallInteger,
        nullable=False,
        default=REFERRAL_RELATION_STATUS_REGISTERED,
        index=True,
    )
    abnormal_status = Column(
        SmallInteger,
        nullable=False,
        default=REFERRAL_ABNORMAL_STATUS_NORMAL,
        index=True,
    )
    metadata_json = Column("metadata", JSON, nullable=True)


class ReferralInviteReward(ReferralTableMixin, db.Model):
    __tablename__ = "referral_invite_rewards"
    __table_args__ = (
        UniqueConstraint("reward_bid", name="uq_referral_invite_rewards_reward_bid"),
        UniqueConstraint(
            "relation_bid",
            "reward_rule_bid",
            "deleted",
            name="uq_referral_invite_rewards_relation_rule_active",
        ),
        Index(
            "ix_referral_invite_rewards_inviter_campaign_status",
            "inviter_user_bid",
            "campaign_bid",
            "reward_status",
        ),
        {"comment": "Referral invite reward audit rows"},
    )

    reward_bid = Column(String(36), nullable=False, default="", index=True)
    campaign_bid = Column(String(36), nullable=False, default="", index=True)
    reward_rule_bid = Column(String(36), nullable=False, default="", index=True)
    relation_bid = Column(String(36), nullable=False, default="", index=True)
    inviter_user_bid = Column(String(36), nullable=False, default="", index=True)
    invitee_user_bid = Column(String(36), nullable=False, default="", index=True)
    reward_status = Column(
        SmallInteger,
        nullable=False,
        default=REFERRAL_REWARD_STATUS_GENERATED,
        index=True,
    )
    reward_target = Column(
        String(32),
        nullable=False,
        default=REFERRAL_REWARD_TARGET_INVITER,
    )
    reward_type = Column(
        String(64),
        nullable=False,
        default=REFERRAL_REWARD_TYPE_BILLING_PLAN_CYCLE,
    )
    reward_product_code = Column(String(64), nullable=False, default="")
    reward_cycle_count = Column(Integer, nullable=False, default=1)
    reward_credit_amount = Column(REFERRAL_CREDIT_NUMERIC, nullable=True)
    reward_credit_validity_days = Column(Integer, nullable=True)
    reward_cap_scope = Column(String(64), nullable=False, default="")
    reward_cap_count = Column(Integer, nullable=True)
    reward_timing_policy = Column(String(64), nullable=False, default="")
    rule_snapshot = Column(JSON, nullable=True)
    billing_artifacts = Column(JSON, nullable=True)
    operator_note = Column(String(500), nullable=False, default="")
    effective_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
