"""Exercise persisted referral operator changes and rejected campaign payloads."""

from datetime import timedelta

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.referral import admin, campaign_admin
from flaskr.service.referral.consts import (
    REFERRAL_ABNORMAL_STATUS_NORMAL,
    REFERRAL_ABNORMAL_STATUS_REVIEWING,
    REFERRAL_CAMPAIGN_STATUS_ACTIVE,
    REFERRAL_CAMPAIGN_STATUS_DRAFT,
    REFERRAL_CAMPAIGN_STATUS_PAUSED,
    REFERRAL_INVITE_CODE_STATUS_ACTIVE,
    REFERRAL_RELATION_STATUS_ABNORMAL_REVIEWING,
    REFERRAL_RELATION_STATUS_REWARD_GENERATED,
    REFERRAL_REWARD_STATUS_CANCELED,
    REFERRAL_REWARD_STATUS_FROZEN,
    REFERRAL_REWARD_STATUS_GENERATED,
)
from flaskr.service.referral.models import (
    ReferralCampaign,
    ReferralCampaignRewardRule,
    ReferralInviteCode,
    ReferralInviteRelation,
    ReferralInviteReward,
)
from flaskr.util.datetime import now_utc

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


@pytest.mark.parametrize(
    "field", ["relation_status", "abnormal_status", "reward_status"]
)
def test_invalid_operator_status_rolls_back_all_changes(
    referral_app: object, relation_reward: object, field: str
) -> None:
    relation, reward = relation_reward
    payload = {"relation_status": "canceled", field: "invalid"}
    with pytest.raises(AppError):
        admin.update_operator_referral_status(
            referral_app,
            relation_bid=relation.relation_bid,
            operator_user_bid="operator",
            payload=payload,
        )
    db.session.expire_all()
    assert relation.relation_status == REFERRAL_RELATION_STATUS_REWARD_GENERATED
    assert reward.reward_status == REFERRAL_REWARD_STATUS_GENERATED
    assert relation.metadata_json == {"source": "original"}


def test_missing_reward_rejects_status_update_without_changing_relation(
    referral_app: object, relation_reward: object
) -> None:
    relation, reward = relation_reward
    db.session.delete(reward)
    db.session.commit()
    with pytest.raises(AppError):
        admin.update_operator_referral_status(
            referral_app,
            relation_bid=relation.relation_bid,
            operator_user_bid="operator",
            payload={"relation_status": "canceled", "reward_status": "canceled"},
        )
    db.session.expire_all()
    assert relation.relation_status == REFERRAL_RELATION_STATUS_REWARD_GENERATED


def test_overview_excludes_deleted_relations_and_canceled_rewards(
    referral_app: object, relation_reward: object
) -> None:
    relation, reward = relation_reward
    relation.abnormal_status = REFERRAL_ABNORMAL_STATUS_REVIEWING
    reward.reward_status = REFERRAL_REWARD_STATUS_CANCELED
    db.session.add(
        ReferralInviteRelation(
            relation_bid="deleted", invitee_user_bid="deleted-user", deleted=1
        )
    )
    db.session.commit()
    assert admin.get_operator_referral_overview(referral_app) == {
        "total_relations": 1,
        "abnormal_relations": 1,
        "generated_rewards": 0,
    }


@pytest.mark.parametrize("field", ["relation_status", "abnormal_status"])
def test_relation_filter_rejects_nonnumeric_status(
    referral_app: object, field: str
) -> None:
    with pytest.raises(AppError):
        admin.list_operator_referrals(
            referral_app, page_index=1, page_size=10, filters={field: "invalid"}
        )


@pytest.mark.parametrize("operation", ["detail", "update"])
def test_missing_operator_relation_is_rejected(
    referral_app: object, operation: str
) -> None:
    if operation == "detail":
        with pytest.raises(AppError):
            admin.get_operator_referral_detail(referral_app, relation_bid="missing")
    else:
        with pytest.raises(AppError):
            admin.update_operator_referral_status(
                referral_app,
                relation_bid="missing",
                operator_user_bid="operator",
                payload={},
            )


@pytest.mark.parametrize(
    "overrides",
    [
        {"campaign_code": ""},
        {"campaign_name": ""},
        {"reward_product_code": ""},
        {"reward_cap_scope": "invalid"},
        {"reward_cap_count": None},
        {"reward_cap_count": 0},
        {"reward_cycle_count": "bad"},
        {"reward_credit_amount": "bad"},
        {"reward_credit_amount": "0"},
        {"reward_credit_validity_days": -1},
        {"enabled": "maybe"},
        {"priority": "high"},
        {"starts_at": "invalid-date"},
        {"inviter_eligibility": "{"},
        {"invitee_eligibility": "[]"},
        {"invitee_eligibility": 1},
        {"reward_product_code": "missing"},
        {"starts_at": "2000-01-01", "ends_at": "2000-02-01", "enabled": "yes"},
    ],
)
def test_invalid_campaign_fields_leave_no_campaign_or_rule(
    referral_app: object, overrides: dict
) -> None:
    _seed_plan_product()
    with pytest.raises(AppError):
        campaign_admin.create_operator_referral_campaign(
            referral_app, operator_user_bid="operator", payload=_payload(**overrides)
        )
    assert ReferralCampaign.query.count() == 0
    assert ReferralCampaignRewardRule.query.count() == 0


def test_campaign_normalizes_json_boolean_and_unlimited_reward_policy(
    referral_app: object,
) -> None:
    _seed_plan_product()
    result = campaign_admin.create_operator_referral_campaign(
        referral_app,
        operator_user_bid="operator",
        payload=_payload(
            enabled="no",
            starts_at="",
            ends_at=None,
            inviter_eligibility='{"registered_phone_user": true}',
            invitee_eligibility="",
            reward_cap_scope="none",
            reward_cap_count=12,
            priority="",
            rule_code="",
        ),
    )
    campaign = ReferralCampaign.query.filter_by(
        campaign_bid=result["campaign_bid"]
    ).one()
    rule = ReferralCampaignRewardRule.query.filter_by(
        campaign_bid=campaign.campaign_bid
    ).one()
    assert campaign.campaign_status == REFERRAL_CAMPAIGN_STATUS_DRAFT
    assert campaign.starts_at is None
    assert campaign.ends_at is None
    assert campaign.inviter_eligibility == {"registered_phone_user": True}
    assert campaign.invitee_eligibility == {}
    assert rule.reward_cap_count is None
    assert rule.priority == 0
    assert rule.rule_code == f"{campaign.campaign_code}_invited_registration"


@pytest.mark.parametrize("status", ["not_started", "ended", "inactive", "invalid"])
def test_campaign_status_filter_matches_runtime_window(
    referral_app: object, status: str
) -> None:
    now = now_utc()
    for label, starts, ends, state in (
        ("not_started", now + timedelta(days=1), None, REFERRAL_CAMPAIGN_STATUS_ACTIVE),
        ("ended", None, now - timedelta(days=1), REFERRAL_CAMPAIGN_STATUS_ACTIVE),
        ("inactive", None, None, REFERRAL_CAMPAIGN_STATUS_PAUSED),
    ):
        db.session.add(
            ReferralCampaign(
                campaign_bid=label,
                campaign_code=label,
                campaign_name=label,
                starts_at=starts,
                ends_at=ends,
                campaign_status=state,
            )
        )
    db.session.commit()
    if status == "invalid":
        with pytest.raises(AppError):
            campaign_admin.list_operator_referral_campaigns(
                referral_app, page_index=1, page_size=10, filters={"status": status}
            )
        return
    result = campaign_admin.list_operator_referral_campaigns(
        referral_app, page_index=1, page_size=10, filters={"status": status}
    )
    assert result["total"] == 1
    assert result["items"][0]["campaign_bid"] == status
    assert result["items"][0]["computed_status"] == status


@pytest.mark.parametrize("status", [str(REFERRAL_INVITE_CODE_STATUS_ACTIVE), "invalid"])
def test_invitation_filters_use_generated_time_and_status(
    referral_app: object, status: str
) -> None:
    campaign, _rule = _seed_campaign()
    now = now_utc()
    db.session.add(
        ReferralInviteCode(
            invite_code_bid="code-row",
            invite_code="FILTER01",
            campaign_bid=campaign.campaign_bid,
            inviter_user_bid="inviter",
            status=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
            generated_at=now,
        )
    )
    db.session.commit()
    filters = {
        "status": status,
        "invite_code": "FILTER01",
        "start_time": now,
        "end_time": now,
    }
    if status == "invalid":
        with pytest.raises(AppError):
            admin.list_operator_referral_campaign_invitations(
                referral_app,
                campaign_bid=campaign.campaign_bid,
                page_index=1,
                page_size=10,
                filters=filters,
            )
        return
    result = admin.list_operator_referral_campaign_invitations(
        referral_app,
        campaign_bid=campaign.campaign_bid,
        page_index=1,
        page_size=10,
        filters=filters,
    )
    assert result["total"] == 1
    assert result["items"][0]["invite_code"] == "FILTER01"


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


def test_campaign_update_rebuilds_missing_rule_and_status_requires_rule(
    referral_app: object,
) -> None:
    _seed_plan_product()
    campaign, rule = _seed_campaign()
    bid = campaign.campaign_bid
    db.session.delete(rule)
    db.session.commit()
    with pytest.raises(AppError):
        campaign_admin.update_operator_referral_campaign_status(
            referral_app,
            operator_user_bid="operator",
            campaign_bid=bid,
            enabled=False,
        )
    campaign_admin.update_operator_referral_campaign(
        referral_app,
        operator_user_bid="operator",
        campaign_bid=bid,
        payload=_payload(enabled=False),
    )
    db.session.expire_all()
    assert ReferralCampaignRewardRule.query.filter_by(campaign_bid=bid).count() == 1
    assert campaign.campaign_status == REFERRAL_CAMPAIGN_STATUS_PAUSED


def test_operator_lists_return_empty_pages_when_window_excludes_all_rows(
    referral_app: object,
    relation_reward: object,
) -> None:
    relation, _reward = relation_reward
    future = now_utc() + timedelta(days=2)
    campaign = ReferralCampaign.query.filter_by(
        campaign_bid=relation.campaign_bid
    ).one()
    campaign.ends_at = future - timedelta(days=1)
    db.session.commit()
    relations = admin.list_operator_referrals(
        referral_app,
        page_index=1,
        page_size=10,
        filters={
            "start_time": future,
            "end_time": future + timedelta(days=1),
            "relation_status": str(REFERRAL_RELATION_STATUS_REWARD_GENERATED),
            "abnormal_status": str(REFERRAL_ABNORMAL_STATUS_NORMAL),
        },
    )
    campaigns = campaign_admin.list_operator_referral_campaigns(
        referral_app,
        page_index=1,
        page_size=10,
        filters={"start_time": future, "end_time": future + timedelta(days=1)},
    )
    invitations = admin.list_operator_referral_campaign_invitations(
        referral_app,
        campaign_bid=campaign.campaign_bid,
        page_index=1,
        page_size=10,
        filters={},
    )
    for result in (relations, campaigns, invitations):
        assert result["total"] == 0
        assert result["items"] == []
        assert result["page_count"] == 0


def test_missing_campaign_is_rejected_and_duplicate_rule_does_not_insert_campaign(
    referral_app: object,
) -> None:
    _seed_plan_product()
    created = campaign_admin.create_operator_referral_campaign(
        referral_app,
        operator_user_bid="operator",
        payload=_payload(),
    )
    with pytest.raises(AppError):
        campaign_admin.get_operator_referral_campaign_detail(
            referral_app, campaign_bid="missing"
        )
    with pytest.raises(AppError):
        campaign_admin.create_operator_referral_campaign(
            referral_app,
            operator_user_bid="operator",
            payload=_payload(campaign_code="second-campaign"),
        )
    assert ReferralCampaign.query.one().campaign_bid == created["campaign_bid"]
    assert ReferralCampaignRewardRule.query.count() == 1
