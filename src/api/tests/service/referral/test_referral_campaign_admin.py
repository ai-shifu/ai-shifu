from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from flaskr.dao import db
from flaskr.service.billing.consts import BILLING_PRODUCT_TYPE_PLAN
from flaskr.service.billing.models import BillingProduct
from flaskr.service.common.models import ERROR_CODE
from flaskr.service.referral.campaign_admin import (
    create_operator_referral_campaign,
    get_operator_referral_campaign_detail,
    list_operator_referral_campaigns,
    update_operator_referral_campaign,
    update_operator_referral_campaign_status,
)
from flaskr.service.referral.consts import (
    REFERRAL_CAMPAIGN_STATUS_ACTIVE,
    REFERRAL_CAMPAIGN_STATUS_PAUSED,
    REFERRAL_RELATION_STATUS_REWARD_GENERATED,
    REFERRAL_REWARD_CAP_SCOPE_PER_INVITER,
    REFERRAL_REWARD_STATUS_GENERATED,
    REFERRAL_RULE_STATUS_ACTIVE,
    REFERRAL_RULE_STATUS_PAUSED,
)
from flaskr.service.referral.models import (
    ReferralCampaign,
    ReferralCampaignRewardRule,
    ReferralInviteRelation,
    ReferralInviteReward,
)


def _seed_plan_product(product_code: str = "creator-plan-monthly-pro") -> None:
    db.session.add(
        BillingProduct(
            product_bid=f"product-{product_code}",
            product_code=product_code,
            product_type=BILLING_PRODUCT_TYPE_PLAN,
            display_name_i18n_key=f"module.billing.catalog.plans.{product_code}.title",
            description_i18n_key="",
        )
    )
    db.session.commit()


def _payload(**overrides):
    payload = {
        "campaign_code": "domestic_creator_invite_202606",
        "campaign_name": "Domestic creator invite",
        "enabled": True,
        "starts_at": "2026-06-01T00:00:00",
        "ends_at": "2026-12-31T23:59:59",
        "reward_product_code": "creator-plan-monthly-pro",
        "reward_cycle_count": 1,
        "reward_credit_amount": "1000",
        "reward_credit_validity_days": 30,
        "reward_cap_scope": "per_inviter",
        "reward_cap_count": 12,
        "feature_flag_key": "REFERRAL_INVITE_REWARDS_ENABLED",
        "invite_route_template": "/invite/{invite_code}",
        "inviter_eligibility": {"registered_phone_user": True},
        "invitee_eligibility": {"created_new_phone_user": True},
        "invitee_benefit_policy": "existing_trial_only",
        "rules_copy_i18n_key": "module.referral.rules.domesticCreatorInvite",
        "rule_code": "inviter_monthly_pro_first_12",
        "priority": 10,
    }
    payload.update(overrides)
    return payload


def test_operator_referral_campaign_create_list_detail_and_status(referral_app):
    with referral_app.app_context():
        _seed_plan_product()

        result = create_operator_referral_campaign(
            referral_app,
            operator_user_bid="operator-1",
            payload=_payload(),
        )

        campaign = ReferralCampaign.query.filter_by(
            campaign_bid=result["campaign_bid"]
        ).one()
        rule = ReferralCampaignRewardRule.query.filter_by(
            campaign_bid=campaign.campaign_bid
        ).one()
        assert campaign.campaign_status == REFERRAL_CAMPAIGN_STATUS_ACTIVE
        assert rule.rule_status == REFERRAL_RULE_STATUS_ACTIVE
        assert rule.reward_credit_amount == Decimal("1000")

        listed = list_operator_referral_campaigns(
            referral_app,
            page_index=1,
            page_size=20,
            filters={"keyword": "domestic", "status": "active"},
        )
        assert listed["total"] == 1
        assert listed["items"][0]["campaign_code"] == "domestic_creator_invite_202606"
        assert listed["items"][0]["computed_status"] == "active"
        assert listed["items"][0]["reward_cap_count"] == 12

        detail = get_operator_referral_campaign_detail(
            referral_app,
            campaign_bid=campaign.campaign_bid,
        )
        assert detail["campaign"]["rule_code"] == "inviter_monthly_pro_first_12"
        assert detail["campaign"]["inviter_eligibility"] == {
            "registered_phone_user": True
        }

        status = update_operator_referral_campaign_status(
            referral_app,
            operator_user_bid="operator-1",
            campaign_bid=campaign.campaign_bid,
            enabled=False,
        )
        assert status == {"campaign_bid": campaign.campaign_bid, "enabled": False}
        db.session.refresh(campaign)
        db.session.refresh(rule)
        assert campaign.campaign_status == REFERRAL_CAMPAIGN_STATUS_PAUSED
        assert rule.rule_status == REFERRAL_RULE_STATUS_PAUSED


def test_operator_referral_campaign_update_changes_future_rule_not_snapshot(
    referral_app,
):
    with referral_app.app_context():
        _seed_plan_product()
        result = create_operator_referral_campaign(
            referral_app,
            operator_user_bid="operator-1",
            payload=_payload(),
        )
        campaign_bid = result["campaign_bid"]
        rule = ReferralCampaignRewardRule.query.filter_by(
            campaign_bid=campaign_bid
        ).one()
        relation = ReferralInviteRelation(
            relation_bid="relation-snapshot",
            campaign_bid=campaign_bid,
            reward_rule_bid=rule.reward_rule_bid,
            invite_code="INVITE01",
            inviter_user_bid="inviter-1",
            invitee_user_bid="invitee-1",
            invitee_mobile_snapshot="13500000000",
            bound_at=datetime(2026, 6, 10, 10, 0, 0),
            registration_source="phone",
            reward_eligible=1,
            relation_status=REFERRAL_RELATION_STATUS_REWARD_GENERATED,
            abnormal_status=0,
            metadata_json={},
        )
        reward = ReferralInviteReward(
            reward_bid="reward-snapshot",
            campaign_bid=campaign_bid,
            reward_rule_bid=rule.reward_rule_bid,
            relation_bid=relation.relation_bid,
            inviter_user_bid="inviter-1",
            invitee_user_bid="invitee-1",
            reward_status=REFERRAL_REWARD_STATUS_GENERATED,
            reward_target="inviter",
            reward_type="billing_plan_cycle",
            reward_product_code="creator-plan-monthly-pro",
            reward_cycle_count=1,
            reward_credit_amount=Decimal("1000"),
            reward_credit_validity_days=30,
            reward_cap_scope=REFERRAL_REWARD_CAP_SCOPE_PER_INVITER,
            reward_cap_count=12,
            reward_timing_policy="immediate_extend_or_defer",
            rule_snapshot={"reward_credit_amount": "1000"},
            billing_artifacts={},
        )
        db.session.add_all([relation, reward])
        db.session.commit()

        update_operator_referral_campaign(
            referral_app,
            operator_user_bid="operator-2",
            campaign_bid=campaign_bid,
            payload=_payload(
                campaign_code="ignored-new-code",
                campaign_name="Updated invite",
                reward_credit_amount="1200",
                reward_cap_count=15,
                priority=20,
            ),
        )

        db.session.refresh(rule)
        db.session.refresh(reward)
        campaign = ReferralCampaign.query.filter_by(campaign_bid=campaign_bid).one()
        assert campaign.campaign_code == "domestic_creator_invite_202606"
        assert campaign.campaign_name == "Updated invite"
        assert rule.reward_credit_amount == Decimal("1200")
        assert rule.reward_cap_count == 15
        assert rule.priority == 20
        assert reward.rule_snapshot == {"reward_credit_amount": "1000"}


@pytest.mark.parametrize(
    "payload",
    [
        _payload(reward_product_code="missing-plan"),
        _payload(reward_credit_amount="0"),
        _payload(reward_cap_scope="per_inviter", reward_cap_count=""),
        _payload(ends_at="2026-05-01T00:00:00"),
        _payload(invitee_eligibility="{broken"),
    ],
)
def test_operator_referral_campaign_rejects_invalid_payload(referral_app, payload):
    with referral_app.app_context():
        _seed_plan_product()
        with pytest.raises(Exception) as exc_info:
            create_operator_referral_campaign(
                referral_app,
                operator_user_bid="operator-1",
                payload=payload,
            )
        assert (
            getattr(exc_info.value, "code", None)
            == ERROR_CODE["server.common.paramsError"]
        )


def test_operator_referral_campaign_rejects_enabling_ended_campaign(referral_app):
    with referral_app.app_context():
        _seed_plan_product()
        result = create_operator_referral_campaign(
            referral_app,
            operator_user_bid="operator-1",
            payload=_payload(
                enabled=False,
                starts_at=(datetime.now() - timedelta(days=60)).isoformat(),
                ends_at=(datetime.now() - timedelta(days=1)).isoformat(),
            ),
        )

        with pytest.raises(Exception) as exc_info:
            update_operator_referral_campaign_status(
                referral_app,
                operator_user_bid="operator-1",
                campaign_bid=result["campaign_bid"],
                enabled=True,
            )
        assert (
            getattr(exc_info.value, "code", None)
            == ERROR_CODE["server.common.paramsError"]
        )


def test_operator_referral_campaign_duplicate_code_is_rejected(referral_app):
    with referral_app.app_context():
        _seed_plan_product()
        create_operator_referral_campaign(
            referral_app,
            operator_user_bid="operator-1",
            payload=_payload(),
        )
        with pytest.raises(Exception) as exc_info:
            create_operator_referral_campaign(
                referral_app,
                operator_user_bid="operator-1",
                payload=_payload(rule_code="another-rule"),
            )
        assert (
            getattr(exc_info.value, "code", None)
            == ERROR_CODE["server.common.paramsError"]
        )
