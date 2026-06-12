from __future__ import annotations

from types import SimpleNamespace

import pytest

from flaskr.dao import db
from flaskr.service.billing.consts import BILLING_PRODUCT_TYPE_PLAN
from flaskr.service.billing.models import BillingProduct
from flaskr.service.common.models import ERROR_CODE
from flaskr.service.referral.models import (
    ReferralCampaign,
    ReferralCampaignRewardRule,
    ReferralInviteRelation,
    ReferralInviteReward,
)


@pytest.fixture(autouse=True)
def _isolate_referral_campaign_tables(app):
    with app.app_context():
        db.session.query(ReferralInviteReward).delete()
        db.session.query(ReferralInviteRelation).delete()
        db.session.query(ReferralCampaignRewardRule).delete()
        db.session.query(ReferralCampaign).delete()
        db.session.query(BillingProduct).filter(
            BillingProduct.product_code.in_(["creator-plan-monthly-pro"])
        ).delete(synchronize_session=False)
        db.session.commit()
        db.session.remove()
    yield
    with app.app_context():
        db.session.query(ReferralInviteReward).delete()
        db.session.query(ReferralInviteRelation).delete()
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
