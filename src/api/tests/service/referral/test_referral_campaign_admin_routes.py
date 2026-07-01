from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from flaskr.dao import db
from flaskr.service.billing.consts import BILLING_PRODUCT_TYPE_PLAN
from flaskr.service.billing.models import BillingProduct
from flaskr.service.common.models import ERROR_CODE
from flaskr.service.referral.consts import (
    REFERRAL_ABNORMAL_STATUS_NORMAL,
    REFERRAL_INVITE_CODE_STATUS_ACTIVE,
    REFERRAL_INVITE_EVENT_LINK_CLICKED,
    REFERRAL_INVITE_EVENT_REGISTRATION_SUBMITTED,
    REFERRAL_RELATION_STATUS_REWARD_GENERATED,
)
from flaskr.service.referral.models import (
    ReferralCampaign,
    ReferralCampaignRewardRule,
    ReferralInviteCode,
    ReferralInviteEvent,
    ReferralInviteRelation,
    ReferralInviteReward,
)


@pytest.fixture(autouse=True)
def _isolate_referral_campaign_tables(app):
    with app.app_context():
        db.session.query(ReferralInviteEvent).delete()
        db.session.query(ReferralInviteReward).delete()
        db.session.query(ReferralInviteRelation).delete()
        db.session.query(ReferralInviteCode).delete()
        db.session.query(ReferralCampaignRewardRule).delete()
        db.session.query(ReferralCampaign).delete()
        db.session.query(BillingProduct).filter(
            BillingProduct.product_code.in_(["creator-plan-monthly-pro"])
        ).delete(synchronize_session=False)
        db.session.commit()
        db.session.remove()
    yield
    with app.app_context():
        db.session.query(ReferralInviteEvent).delete()
        db.session.query(ReferralInviteReward).delete()
        db.session.query(ReferralInviteRelation).delete()
        db.session.query(ReferralInviteCode).delete()
        db.session.query(ReferralCampaignRewardRule).delete()
        db.session.query(ReferralCampaign).delete()
        db.session.query(BillingProduct).filter(
            BillingProduct.product_code.in_(["creator-plan-monthly-pro"])
        ).delete(synchronize_session=False)
        db.session.commit()
        db.session.remove()


def _mock_operator(monkeypatch, user_id: str = "operator-1") -> None:
    dummy_user = SimpleNamespace(
        user_id=user_id,
        is_operator=True,
        is_creator=False,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: dummy_user,
        raising=False,
    )


def _seed_plan_product() -> None:
    db.session.add(
        BillingProduct(
            product_bid="product-referral-plan",
            product_code="creator-plan-monthly-pro",
            product_type=BILLING_PRODUCT_TYPE_PLAN,
            display_name_i18n_key="module.billing.catalog.plans.monthly.title",
            description_i18n_key="",
        )
    )
    db.session.commit()


def _payload():
    return {
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
        "feature_flag_key": "",
        "invite_route_template": "/invite/{invite_code}",
        "inviter_eligibility": {"registered_phone_user": True},
        "invitee_eligibility": {"created_new_phone_user": True},
        "invitee_benefit_policy": "existing_trial_only",
        "rules_copy_i18n_key": "module.referral.rules.domesticCreatorInvite",
        "rule_code": "inviter_monthly_pro_first_12",
        "priority": 10,
    }


def test_admin_operations_promotions_referral_campaign_routes_round_trip(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    with app.app_context():
        _seed_plan_product()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/referral-campaigns",
        json=_payload(),
        headers={"Token": "test-token"},
    )
    create_payload = create_response.get_json(force=True)
    assert create_payload["code"] == 0
    campaign_bid = create_payload["data"]["campaign_bid"]

    list_response = test_client.get(
        "/api/shifu/admin/operations/promotions/referral-campaigns?status=active",
        headers={"Token": "test-token"},
    )
    list_payload = list_response.get_json(force=True)
    assert list_payload["code"] == 0
    assert list_payload["data"]["total"] == 1
    assert list_payload["data"]["items"][0]["campaign_bid"] == campaign_bid

    detail_response = test_client.get(
        f"/api/shifu/admin/operations/promotions/referral-campaigns/{campaign_bid}",
        headers={"Token": "test-token"},
    )
    detail_payload = detail_response.get_json(force=True)
    assert detail_payload["code"] == 0
    assert (
        detail_payload["data"]["campaign"]["reward_credit_amount"] == "1000.0000000000"
    )

    update_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/referral-campaigns/{campaign_bid}",
        json={**_payload(), "campaign_name": "Updated invite", "priority": 20},
        headers={"Token": "test-token"},
    )
    assert update_response.get_json(force=True)["code"] == 0

    status_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/referral-campaigns/{campaign_bid}/status",
        json={"enabled": False},
        headers={"Token": "test-token"},
    )
    status_payload = status_response.get_json(force=True)
    assert status_payload["code"] == 0
    assert status_payload["data"]["enabled"] is False


def test_admin_operations_referral_campaign_record_routes_are_campaign_scoped(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    with app.app_context():
        _seed_plan_product()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/referral-campaigns",
        json=_payload(),
        headers={"Token": "test-token"},
    )
    campaign_bid = create_response.get_json(force=True)["data"]["campaign_bid"]
    with app.app_context():
        rule = ReferralCampaignRewardRule.query.filter_by(
            campaign_bid=campaign_bid
        ).one()
        invite_code = ReferralInviteCode(
            invite_code_bid="route-code-1",
            campaign_bid=campaign_bid,
            inviter_user_bid="route-inviter-1",
            invite_code="ROUTE001",
            status=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
            generated_at=datetime(2026, 6, 12, 10, 0, 0),
        )
        other_code = ReferralInviteCode(
            invite_code_bid="route-code-other",
            campaign_bid="other-campaign",
            inviter_user_bid="route-inviter-other",
            invite_code="OTHER001",
            status=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
            generated_at=datetime(2026, 6, 12, 9, 0, 0),
        )
        relation = ReferralInviteRelation(
            relation_bid="route-relation-1",
            campaign_bid=campaign_bid,
            reward_rule_bid=rule.reward_rule_bid,
            invite_code=invite_code.invite_code,
            inviter_user_bid=invite_code.inviter_user_bid,
            invitee_user_bid="route-invitee-1",
            invitee_mobile_snapshot="15500001234",
            bound_at=datetime(2026, 6, 12, 10, 5, 0),
            registration_source="phone",
            reward_eligible=1,
            relation_status=REFERRAL_RELATION_STATUS_REWARD_GENERATED,
            abnormal_status=REFERRAL_ABNORMAL_STATUS_NORMAL,
            metadata_json={},
        )
        other_relation = ReferralInviteRelation(
            relation_bid="route-relation-other",
            campaign_bid="other-campaign",
            reward_rule_bid="other-rule",
            invite_code=other_code.invite_code,
            inviter_user_bid=other_code.inviter_user_bid,
            invitee_user_bid="route-invitee-other",
            invitee_mobile_snapshot="15500005678",
            bound_at=datetime(2026, 6, 12, 10, 6, 0),
            registration_source="phone",
            reward_eligible=1,
            relation_status=REFERRAL_RELATION_STATUS_REWARD_GENERATED,
            abnormal_status=REFERRAL_ABNORMAL_STATUS_NORMAL,
            metadata_json={},
        )
        events = [
            ReferralInviteEvent(
                event_bid="route-event-click",
                campaign_bid=campaign_bid,
                event_type=REFERRAL_INVITE_EVENT_LINK_CLICKED,
                invite_code=invite_code.invite_code,
                inviter_user_bid=invite_code.inviter_user_bid,
                session_id="route-session-1",
                client_ip_hash="hash-ip",
                user_agent_hash="hash-ua",
                landing_path="/invite/ROUTE001",
                metadata_json={},
                created_at=datetime(2026, 6, 12, 10, 1, 0),
            ),
            ReferralInviteEvent(
                event_bid="route-event-submit",
                campaign_bid=campaign_bid,
                event_type=REFERRAL_INVITE_EVENT_REGISTRATION_SUBMITTED,
                invite_code=invite_code.invite_code,
                inviter_user_bid=invite_code.inviter_user_bid,
                session_id="route-session-1",
                client_ip_hash="hash-ip",
                user_agent_hash="hash-ua",
                landing_path="/invite/ROUTE001",
                metadata_json={},
                created_at=datetime(2026, 6, 12, 10, 4, 0),
            ),
        ]
        db.session.add_all([invite_code, other_code, relation, other_relation, *events])
        db.session.commit()

    relations_response = test_client.get(
        "/api/shifu/admin/operations/promotions/"
        f"referral-campaigns/{campaign_bid}/relations",
        headers={"Token": "test-token"},
    )
    relations_payload = relations_response.get_json(force=True)
    assert relations_payload["code"] == 0
    assert relations_payload["data"]["total"] == 1
    assert relations_payload["data"]["items"][0]["relation_bid"] == "route-relation-1"
    assert relations_payload["data"]["page_count"] == 1

    invitations_response = test_client.get(
        "/api/shifu/admin/operations/promotions/"
        f"referral-campaigns/{campaign_bid}/invitations",
        headers={"Token": "test-token"},
    )
    invitations_payload = invitations_response.get_json(force=True)
    assert invitations_payload["code"] == 0
    assert invitations_payload["data"]["total"] == 1
    invitation = invitations_payload["data"]["items"][0]
    assert invitation["invite_code"] == "ROUTE001"
    assert invitation["link_clicked_count"] == 1
    assert invitation["registration_submitted_count"] == 1
    assert invitation["successful_relation_count"] == 1
    assert invitation["latest_event_at"] == "2026-06-12T10:04:00Z"


def test_admin_operations_promotions_referral_campaign_rejects_invalid_status_filter(
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)

    response = test_client.get(
        "/api/shifu/admin/operations/promotions/referral-campaigns?status=invalid",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == ERROR_CODE["server.common.paramsError"]
