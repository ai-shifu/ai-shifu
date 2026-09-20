"""Exercise persisted referral operator changes and rejected campaign payloads."""

import pytest
from flaskr.dao import db
from flaskr.service.referral import admin, campaign_admin
from flaskr.service.referral.consts import (
    REFERRAL_ABNORMAL_STATUS_REVIEWING,
    REFERRAL_RELATION_STATUS_ABNORMAL_REVIEWING,
    REFERRAL_RELATION_STATUS_REWARD_GENERATED,
    REFERRAL_REWARD_STATUS_FROZEN,
    REFERRAL_REWARD_STATUS_GENERATED,
)
from flaskr.service.referral.models import (
    ReferralCampaign,
    ReferralCampaignRewardRule,
    ReferralInviteRelation,
    ReferralInviteReward,
)

from tests.service.referral.test_referral_campaign_admin import (
    _payload,
    _seed_plan_product,
)
from tests.service.referral.test_referral_service import _seed_campaign


@pytest.fixture
def relation_reward(referral_app: object) -> object:
    _ = referral_app
    campaign, rule = _seed_campaign()
    relation = ReferralInviteRelation(
        relation_bid="operator-relation",
        campaign_bid=campaign.campaign_bid,
        reward_rule_bid=rule.reward_rule_bid,
        invite_code="OPERATOR",
        inviter_user_bid="inviter",
        invitee_user_bid="invitee",
        relation_status=REFERRAL_RELATION_STATUS_REWARD_GENERATED,
        metadata_json={"source": "original"},
    )
    reward = ReferralInviteReward(
        reward_bid="operator-reward",
        campaign_bid=campaign.campaign_bid,
        reward_rule_bid=rule.reward_rule_bid,
        relation_bid=relation.relation_bid,
        inviter_user_bid=relation.inviter_user_bid,
        invitee_user_bid=relation.invitee_user_bid,
        reward_status=REFERRAL_REWARD_STATUS_GENERATED,
        reward_credit_amount=rule.reward_credit_amount,
        billing_artifacts={},
    )
    db.session.add_all([relation, reward])
    db.session.commit()
    return relation, reward


def test_operator_status_update_persists_audit_note_and_preserves_metadata(
    referral_app: object, relation_reward: object
) -> None:
    relation, reward = relation_reward
    result = admin.update_operator_referral_status(
        referral_app,
        relation_bid=relation.relation_bid,
        operator_user_bid=" operator ",
        payload={
            "relation_status": "abnormal_reviewing",
            "abnormal_status": "reviewing",
            "reward_status": "frozen",
            "operator_note": " Verify invitation ",
        },
    )
    db.session.expire_all()
    saved = ReferralInviteRelation.query.filter_by(
        relation_bid=relation.relation_bid
    ).one()
    saved_reward = ReferralInviteReward.query.filter_by(
        reward_bid=reward.reward_bid
    ).one()
    assert result["relation_status"] == REFERRAL_RELATION_STATUS_ABNORMAL_REVIEWING
    assert saved.abnormal_status == REFERRAL_ABNORMAL_STATUS_REVIEWING
    assert saved_reward.reward_status == REFERRAL_REWARD_STATUS_FROZEN
    assert saved_reward.operator_note == "Verify invitation"
    assert saved.metadata_json["source"] == "original"
    assert saved.metadata_json["operator_note"] == "Verify invitation"
    assert saved.metadata_json["operator_user_bid"] == "operator"
    assert saved.metadata_json["operator_updated_at"].endswith("Z")


@pytest.mark.parametrize("operation", ["edit", "status"])
def test_campaign_edits_persist_operator_and_preserve_existing_metadata(
    referral_app: object, operation: str
) -> None:
    _seed_plan_product()
    created = campaign_admin.create_operator_referral_campaign(
        referral_app, operator_user_bid="first", payload=_payload()
    )
    bid = created["campaign_bid"]
    campaign = ReferralCampaign.query.filter_by(campaign_bid=bid).one()
    campaign.metadata_json = {"source": "original", "operator_user_bid": "first"}
    db.session.commit()
    for _ in range(2):
        if operation == "edit":
            campaign_admin.update_operator_referral_campaign(
                referral_app,
                operator_user_bid=" editor ",
                campaign_bid=bid,
                payload=_payload(campaign_name="Edited"),
            )
        else:
            campaign_admin.update_operator_referral_campaign_status(
                referral_app,
                operator_user_bid=" editor ",
                campaign_bid=bid,
                enabled=False,
            )
        db.session.expire_all()
        assert ReferralCampaign.query.filter_by(
            campaign_bid=bid
        ).one().metadata_json == {"source": "original", "operator_user_bid": "editor"}
    assert ReferralCampaignRewardRule.query.filter_by(campaign_bid=bid).count() == 1
