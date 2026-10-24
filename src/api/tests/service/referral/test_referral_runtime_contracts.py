"""Verify referral eligibility, cap accounting, repair, and billing boundaries."""

from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.i18n import _
from flaskr.service.billing.consts import CREDIT_LEDGER_ENTRY_TYPE_GRANT
from flaskr.service.billing.models import (
    BillingOrder,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.referral import service
from flaskr.service.referral.consts import (
    REFERRAL_CAMPAIGN_STATUS_PAUSED,
    REFERRAL_REWARD_STATUS_CANCELED,
    REFERRAL_REWARD_STATUS_GENERATED,
)
from flaskr.service.referral.models import ReferralInviteRelation, ReferralInviteReward
from flaskr.service.user.models import UserInfo
from flaskr.service.user.post_auth import PostAuthContext

from tests.common.fixtures.bill_products import build_bill_products
from tests.service.referral.test_referral_service import _seed_campaign
from tests.service.referral.test_referral_uow_failure_paths import _seed_invite_code


@pytest.mark.parametrize("matching_product", [True, False])
def test_post_auth_reward_checks_catalog_amount_and_grants_exactly_once(
    referral_app: object,
    matching_product: bool,
) -> None:
    campaign, rule = _seed_campaign()
    rule.reward_credit_amount = Decimal("12.3456789012")
    db.session.add_all(
        build_bill_products(
            product_bids=["bill-product-plan-monthly-pro"],
            overrides_by_bid={
                "bill-product-plan-monthly-pro": {
                    "credit_amount": Decimal("12.3456789012")
                    if matching_product
                    else Decimal(1000)
                }
            },
        )
    )
    db.session.add(UserInfo(user_bid="invitee", user_identify="13800138000"))
    db.session.commit()
    _seed_invite_code(campaign.campaign_bid, code="BILLREAL", inviter="inviter")
    context = PostAuthContext(
        user_id="invitee",
        source="sms",
        created_new_user=True,
        invite_code=" billreal ",
    )
    result = service.process_referral_post_auth(referral_app, context)
    if not matching_product:
        assert result.skipped_reason == "billing_grant_failed"
        assert result.created_relation is True
        assert result.created_reward is True
        assert BillingOrder.query.count() == 0
        assert CreditLedgerEntry.query.count() == 0
        assert ReferralInviteReward.query.one().billing_artifacts["grant_error"] == _(
            "server.billing.referralRewardProductMismatch"
        )
        return
    assert result.skipped_reason == "", (
        ReferralInviteReward.query.one().billing_artifacts
    )
    assert result.created_relation is True
    assert result.created_reward is True
    repeated = service.process_referral_post_auth(referral_app, context)
    assert repeated.created_reward is False
    assert repeated.reward_bid == result.reward_bid
    assert repeated.relation_bid == result.relation_bid
    db.session.expire_all()
    reward = ReferralInviteReward.query.one()
    relation = ReferralInviteRelation.query.one()
    order = BillingOrder.query.one()
    ledger = CreditLedgerEntry.query.filter_by(
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT
    ).one()
    bucket = CreditWalletBucket.query.one()
    assert reward.billing_artifacts["bill_order_bid"] == order.bill_order_bid
    assert relation.invitee_mobile_snapshot == "13800138000"
    assert reward.rule_snapshot["reward_credit_amount"] == "12.3456789012"
    assert reward.reward_credit_amount == Decimal("12.3456789012")
    assert ledger.amount == Decimal("12.35")
    assert bucket.original_credits == Decimal("12.35")
    assert order.payable_amount == 0
    assert order.paid_amount == 0
    assert order.provider_reference_id == f"referral-reward:{reward.reward_bid}"


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("existing-user", ""),
        ("empty-code", ""),
        ("unknown-code", "invite_code_not_found"),
        ("self-invite", "self_invite"),
        ("paused", "campaign_not_active"),
        ("missing-rule", "reward_rule_not_active"),
    ],
)
def test_ineligible_binding_does_not_create_reward_or_call_billing(
    referral_app: object, monkeypatch: object, case: str, reason: str
) -> None:
    campaign, rule = _seed_campaign()
    _seed_invite_code(campaign.campaign_bid, code="ELIGIBLE", inviter="inviter")
    context = PostAuthContext(
        user_id="invitee",
        source="sms",
        created_new_user=True,
        invite_code="ELIGIBLE",
    )
    if case == "existing-user":
        context = replace(context, created_new_user=False)
    elif case == "empty-code":
        context = replace(context, invite_code=" ")
    elif case == "unknown-code":
        context = replace(context, invite_code="missing")
    elif case == "self-invite":
        context = replace(context, user_id="inviter")
    elif case == "paused":
        campaign.campaign_status = REFERRAL_CAMPAIGN_STATUS_PAUSED
    elif case == "missing-rule":
        rule.deleted = 1
    db.session.commit()
    grant = Mock()
    monkeypatch.setattr(service, "grant_referral_plan_reward", grant)
    result = service.process_referral_post_auth(referral_app, context)
    assert result.skipped_reason == reason
    assert result.created_relation is False
    assert ReferralInviteRelation.query.count() == 0
    assert ReferralInviteReward.query.count() == 0
    grant.assert_not_called()


@pytest.mark.parametrize(
    ("scope", "cap", "reached"),
    [
        ("per_inviter", 1, False),
        ("per_campaign", 1, True),
        ("none", 1, False),
        ("unknown", 1, False),
        ("per_campaign", None, False),
        ("per_campaign", 0, False),
    ],
)
def test_reward_cap_counts_only_granted_rows_within_selected_scope(
    referral_app: object, scope: str, cap: int | None, reached: bool
) -> None:
    _ = referral_app
    campaign, rule = _seed_campaign()
    rule.reward_cap_scope = scope
    rule.reward_cap_count = cap
    for bid, inviter, status, deleted in (
        ("other-granted", "other", REFERRAL_REWARD_STATUS_GENERATED, 0),
        ("same-canceled", "inviter", REFERRAL_REWARD_STATUS_CANCELED, 0),
        ("same-deleted", "inviter", REFERRAL_REWARD_STATUS_GENERATED, 1),
    ):
        db.session.add(
            ReferralInviteReward(
                reward_bid=bid,
                relation_bid=bid,
                campaign_bid=campaign.campaign_bid,
                reward_rule_bid=rule.reward_rule_bid,
                inviter_user_bid=inviter,
                reward_status=status,
                deleted=deleted,
            )
        )
    db.session.commit()
    assert (
        service._cap_reached(
            rule=rule, inviter_user_bid="inviter", campaign_bid=campaign.campaign_bid
        )
        is reached
    )


@pytest.mark.parametrize("dry_run", [True, False])
def test_reward_retry_skips_completed_and_orphan_rows_and_continues_after_failure(
    referral_app: object, monkeypatch: object, dry_run: bool
) -> None:
    for bid in ("complete", "orphan", "failing", "success"):
        db.session.add(
            ReferralInviteReward(
                reward_bid=bid,
                relation_bid=bid,
                reward_status=REFERRAL_REWARD_STATUS_GENERATED,
                billing_artifacts={"bill_order_bid": "existing-order"}
                if bid == "complete"
                else None,
            )
        )
        if bid != "orphan":
            db.session.add(
                ReferralInviteRelation(relation_bid=bid, invitee_user_bid=bid)
            )
    db.session.commit()

    def grant(_app: object, *, reward: object) -> dict:
        if reward.reward_bid == "failing":
            reward.rule_snapshot = {"uncommitted": True}
            db.session.flush()
            message = "billing unavailable"
            raise RuntimeError(message)
        return {"bill_order_bid": "new-order"}

    mocked_grant = Mock(side_effect=grant)
    monkeypatch.setattr(service, "grant_referral_plan_reward", mocked_grant)
    result = service.retry_pending_referral_rewards(referral_app, dry_run=dry_run)
    assert [row["action"] for row in result] == [
        "skipped_missing_relation",
        "would_retry" if dry_run else "failed",
        "would_retry" if dry_run else "retried",
    ]
    db.session.expire_all()
    failed = ReferralInviteReward.query.filter_by(reward_bid="failing").one()
    succeeded = ReferralInviteReward.query.filter_by(reward_bid="success").one()
    assert failed.rule_snapshot != {"uncommitted": True}
    if dry_run:
        mocked_grant.assert_not_called()
        assert failed.billing_artifacts is None
        assert succeeded.billing_artifacts is None
    else:
        assert mocked_grant.call_count == 2
        assert failed.billing_artifacts["grant_error"] == "billing unavailable"
        assert failed.billing_artifacts["last_failed_at"].endswith("Z")
        assert succeeded.billing_artifacts == {"bill_order_bid": "new-order"}


@pytest.mark.parametrize(
    ("configured", "origin", "expected"),
    [
        (
            "https://configured.example/",
            "https://caller.example",
            "https://configured.example",
        ),
        ("", "https://caller.example, https://proxy.example", "https://caller.example"),
        ("", "null", "http://localhost"),
        ("", "", "http://localhost"),
    ],
)
def test_invite_url_origin_uses_config_then_request_fallback(
    referral_app: object,
    monkeypatch: object,
    configured: str,
    origin: str,
    expected: str,
) -> None:
    monkeypatch.setattr(service, "get_common_config", lambda _key, _default: configured)
    with referral_app.test_request_context("/", headers={"Origin": origin}):
        assert service._resolve_public_origin() == expected


@pytest.mark.parametrize(
    "origin",
    [
        "example.com",
        "ftp://example.com",
        "https://example.com/path",
        "https://example.com?query=1",
        "https://example.com#fragment",
    ],
)
def test_invite_origin_rejects_non_origin_configuration(origin: str) -> None:
    with pytest.raises(RuntimeError):
        service._normalize_origin(origin)


def test_invite_origin_requires_configuration_outside_http_request(
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(service, "get_common_config", lambda _key, _default: "")
    with pytest.raises(RuntimeError, match="HOST_URL must be configured"):
        service._resolve_public_origin()


def test_blank_inviter_and_invalid_event_are_rejected_without_persisting(
    referral_app: object,
) -> None:
    with pytest.raises(ValueError, match="inviter_user_bid"):
        service.build_invite_profile(referral_app, inviter_user_bid=" ")
    with pytest.raises(ValueError, match="unsupported"):
        service.record_invite_event(
            referral_app, service.InviteEventInput(event_type="invalid")
        )
    assert (
        service.build_invite_preview(referral_app, invite_code=" ").recognized is False
    )


def test_repeated_invite_code_collisions_leave_no_partial_new_inviter_row(
    referral_app: object,
    monkeypatch: object,
) -> None:
    campaign, _rule = _seed_campaign()
    _seed_invite_code(campaign.campaign_bid, code="COLLIDE1", inviter="original")
    generator = Mock(return_value="COLLIDE1")
    monkeypatch.setattr(service, "_generate_invite_code", generator)
    with pytest.raises(RuntimeError, match="unable to generate"):
        service.build_invite_profile(referral_app, inviter_user_bid="new-inviter")
    assert generator.call_count == 5
    assert service.ReferralInviteCode.query.count() == 1
    assert service.ReferralInviteCode.query.one().inviter_user_bid == "original"


@pytest.mark.parametrize(
    ("identifier", "masked"),
    [
        ("person@", "****"),
        ("@example.com", "****@example.com"),
        ("008613800138000", "138****8000"),
    ],
)
def test_identifier_masking_handles_partial_email_and_international_phone(
    identifier: str,
    masked: str,
) -> None:
    assert service.mask_identifier_snapshot(identifier) == masked


def test_post_auth_fields_hash_context_and_preserve_only_referral_inputs() -> None:
    payload = {
        "invite_code": " ABC123 ",
        "referral_session_id": " session ",
        "referral_entry_source": " invite ",
        "password": "excluded",
    }
    fields = service.extract_referral_post_auth_fields(
        payload, client_ip=" 192.0.2.1 ", user_agent=" Browser "
    )
    assert fields == {
        "invite_code": "ABC123",
        "referral_session_id": "session",
        "referral_entry_source": "invite",
        "client_ip_hash": service.hash_referral_context("192.0.2.1"),
        "user_agent_hash": service.hash_referral_context("Browser"),
    }
    assert len(fields["client_ip_hash"]) == 64
    assert len(fields["user_agent_hash"]) == 64
    assert service.hash_referral_context(" ") == ""
    assert payload["invite_code"] == " ABC123 "


def test_unlimited_invite_profile_keeps_remaining_count_unbounded(
    referral_app: object,
    monkeypatch: object,
) -> None:
    _campaign, rule = _seed_campaign()
    rule.reward_cap_scope = "none"
    rule.reward_cap_count = None
    db.session.commit()
    monkeypatch.setattr(
        service, "_resolve_public_origin", lambda: "https://example.test"
    )
    result = service.build_invite_profile(referral_app, inviter_user_bid="inviter")
    assert result.reward_cap_count is None
    assert result.reward_remaining_count is None
    assert result.reward_granted_count == 0
