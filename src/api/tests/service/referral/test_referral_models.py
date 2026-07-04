from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from flaskr.dao import db
from flaskr.service.referral.consts import (
    REFERRAL_ABNORMAL_STATUS_NORMAL,
    REFERRAL_CAMPAIGN_STATUS_ACTIVE,
    REFERRAL_INVITE_CODE_STATUS_ACTIVE,
    REFERRAL_INVITE_EVENT_LINK_CLICKED,
    REFERRAL_RELATION_STATUS_REGISTERED,
    REFERRAL_REWARD_STATUS_GENERATED,
    REFERRAL_REWARD_TARGET_INVITER,
    REFERRAL_REWARD_TYPE_BILLING_PLAN_CYCLE,
    REFERRAL_RULE_STATUS_ACTIVE,
    REFERRAL_TRIGGER_INVITED_REGISTRATION,
)
from flaskr.service.referral.models import (
    ReferralCampaign,
    ReferralCampaignRewardRule,
    ReferralInviteCode,
    ReferralInviteEvent,
    ReferralInviteRelation,
    ReferralInviteReward,
)


def test_referral_models_register_campaign_runtime_tables() -> None:
    tables = db.metadata.tables

    assert "referral_campaigns" in tables
    assert "referral_campaign_reward_rules" in tables
    assert "referral_invite_codes" in tables
    assert "referral_invite_events" in tables
    assert "referral_invite_relations" in tables
    assert "referral_invite_rewards" in tables

    campaign_table = tables["referral_campaigns"]
    assert "campaign_code" in campaign_table.c
    assert "feature_flag_key" in campaign_table.c
    assert "inviter_eligibility" in campaign_table.c

    rule_constraints = {
        constraint.name
        for constraint in ReferralCampaignRewardRule.__table__.constraints
        if getattr(constraint, "name", None)
    }
    assert "uq_referral_campaign_reward_rules_campaign_rule" in rule_constraints


def test_referral_model_rows_support_configured_campaign_and_reward_snapshot(
    referral_app,
):
    with referral_app.app_context():
        campaign = ReferralCampaign(
            campaign_bid="ref-campaign-model-1",
            campaign_code="domestic_creator_invite_202606_model",
            campaign_name="Domestic creator invite",
            campaign_status=REFERRAL_CAMPAIGN_STATUS_ACTIVE,
            feature_flag_key="",
            starts_at=datetime(2026, 6, 1),
            ends_at=datetime(2026, 7, 1),
            invite_route_template="/invite/{invite_code}",
            inviter_eligibility={"registered_phone_user": True},
            invitee_eligibility={"created_new_phone_user": True},
            invitee_benefit_policy="existing_trial_only",
            rules_copy_i18n_key="module.referral.rules.domesticCreatorInvite",
            metadata_json={"owner": "growth"},
        )
        rule = ReferralCampaignRewardRule(
            reward_rule_bid="ref-rule-model-1",
            campaign_bid=campaign.campaign_bid,
            rule_code="inviter_monthly_pro_first_12",
            rule_status=REFERRAL_RULE_STATUS_ACTIVE,
            trigger_event=REFERRAL_TRIGGER_INVITED_REGISTRATION,
            reward_target=REFERRAL_REWARD_TARGET_INVITER,
            reward_type=REFERRAL_REWARD_TYPE_BILLING_PLAN_CYCLE,
            reward_product_code="creator-plan-monthly-pro",
            reward_cycle_count=1,
            reward_credit_amount=Decimal("1000.0000000000"),
            reward_credit_validity_days=30,
            reward_cap_scope="per_inviter",
            reward_cap_count=12,
            reward_timing_policy="immediate_extend_or_defer",
            priority=10,
            metadata_json={"expected_price_amount": 19900},
        )
        invite_code = ReferralInviteCode(
            invite_code_bid="ref-code-model-1",
            campaign_bid=campaign.campaign_bid,
            inviter_user_bid="inviter-model-1",
            invite_code="ABC12345",
            status=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
            generated_at=datetime(2026, 6, 9, 10, 0, 0),
        )
        event = ReferralInviteEvent(
            event_bid="ref-event-model-1",
            campaign_bid=campaign.campaign_bid,
            event_type=REFERRAL_INVITE_EVENT_LINK_CLICKED,
            invite_code=invite_code.invite_code,
            inviter_user_bid=invite_code.inviter_user_bid,
            session_id="session-model-1",
            client_ip_hash="hash-ip",
            user_agent_hash="hash-ua",
            landing_path="/invite/ABC12345",
            metadata_json={"entry_source": "link"},
        )
        relation = ReferralInviteRelation(
            relation_bid="ref-relation-model-1",
            campaign_bid=campaign.campaign_bid,
            reward_rule_bid=rule.reward_rule_bid,
            invite_code=invite_code.invite_code,
            inviter_user_bid=invite_code.inviter_user_bid,
            invitee_user_bid="invitee-model-1",
            invitee_mobile_snapshot="15500009999",
            bound_at=datetime(2026, 6, 9, 10, 1, 0),
            registration_source="phone",
            reward_eligible=1,
            relation_status=REFERRAL_RELATION_STATUS_REGISTERED,
            abnormal_status=REFERRAL_ABNORMAL_STATUS_NORMAL,
            metadata_json={"referral_session_id": "session-model-1"},
        )
        reward = ReferralInviteReward(
            reward_bid="ref-reward-model-1",
            campaign_bid=campaign.campaign_bid,
            reward_rule_bid=rule.reward_rule_bid,
            relation_bid=relation.relation_bid,
            inviter_user_bid=invite_code.inviter_user_bid,
            invitee_user_bid=relation.invitee_user_bid,
            reward_status=REFERRAL_REWARD_STATUS_GENERATED,
            reward_target=REFERRAL_REWARD_TARGET_INVITER,
            reward_type=REFERRAL_REWARD_TYPE_BILLING_PLAN_CYCLE,
            reward_product_code=rule.reward_product_code,
            reward_cycle_count=rule.reward_cycle_count,
            reward_credit_amount=rule.reward_credit_amount,
            reward_credit_validity_days=rule.reward_credit_validity_days,
            reward_cap_scope=rule.reward_cap_scope,
            reward_cap_count=rule.reward_cap_count,
            reward_timing_policy=rule.reward_timing_policy,
            rule_snapshot=rule.to_snapshot(),
        )

        db.session.add_all([campaign, rule, invite_code, event, relation, reward])
        db.session.commit()

        assert (
            ReferralInviteReward.query.filter_by(reward_bid="ref-reward-model-1")
            .one()
            .rule_snapshot["reward_product_code"]
            == "creator-plan-monthly-pro"
        )


def test_referral_relation_prevents_duplicate_active_invitee_binding(referral_app):
    with referral_app.app_context():
        db.session.add(
            ReferralInviteRelation(
                relation_bid="ref-relation-unique-1",
                campaign_bid="ref-campaign-unique",
                reward_rule_bid="",
                invite_code="UNIQUE01",
                inviter_user_bid="inviter-unique-1",
                invitee_user_bid="invitee-unique-1",
                invitee_mobile_snapshot="15500008888",
                bound_at=datetime(2026, 6, 9, 11, 0, 0),
                registration_source="phone",
                reward_eligible=1,
                relation_status=REFERRAL_RELATION_STATUS_REGISTERED,
                abnormal_status=REFERRAL_ABNORMAL_STATUS_NORMAL,
            )
        )
        db.session.commit()

        db.session.add(
            ReferralInviteRelation(
                relation_bid="ref-relation-unique-2",
                campaign_bid="ref-campaign-unique",
                reward_rule_bid="",
                invite_code="UNIQUE02",
                inviter_user_bid="inviter-unique-2",
                invitee_user_bid="invitee-unique-1",
                invitee_mobile_snapshot="15500008888",
                bound_at=datetime(2026, 6, 9, 11, 1, 0),
                registration_source="phone",
                reward_eligible=1,
                relation_status=REFERRAL_RELATION_STATUS_REGISTERED,
                abnormal_status=REFERRAL_ABNORMAL_STATUS_NORMAL,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
