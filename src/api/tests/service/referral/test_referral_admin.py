from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flaskr.dao import db
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.models import (
    BillingOrder,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.referral.admin import get_operator_referral_detail
from flaskr.service.referral.consts import (
    REFERRAL_ABNORMAL_STATUS_NORMAL,
    REFERRAL_CAMPAIGN_STATUS_ACTIVE,
    REFERRAL_RELATION_STATUS_REWARD_GENERATED,
    REFERRAL_REWARD_STATUS_ACTIVE,
    REFERRAL_REWARD_STATUS_CANCELED,
    REFERRAL_REWARD_STATUS_PENDING_EFFECTIVE,
    REFERRAL_REWARD_STATUS_SKIPPED_CAP,
)
from flaskr.service.referral.models import (
    ReferralCampaign,
    ReferralInviteRelation,
    ReferralInviteReward,
)


def _relation(
    *,
    relation_bid: str,
    invitee_user_bid: str,
    invitee_mobile: str,
    inviter_user_bid: str = "inviter-admin-queue",
) -> ReferralInviteRelation:
    return ReferralInviteRelation(
        relation_bid=relation_bid,
        campaign_bid="campaign-admin-queue",
        reward_rule_bid="rule-admin-queue",
        invite_code="QUEUE01",
        inviter_user_bid=inviter_user_bid,
        invitee_user_bid=invitee_user_bid,
        invitee_mobile_snapshot=invitee_mobile,
        bound_at=datetime(2026, 6, 11, 9, 0, 0),
        registration_source="phone",
        reward_eligible=1,
        relation_status=REFERRAL_RELATION_STATUS_REWARD_GENERATED,
        abnormal_status=REFERRAL_ABNORMAL_STATUS_NORMAL,
        metadata_json={},
    )


def _reward(
    *,
    reward_bid: str,
    relation_bid: str,
    invitee_user_bid: str,
    bill_order_bid: str,
    status: int,
    created_at: datetime,
    inviter_user_bid: str = "inviter-admin-queue",
) -> ReferralInviteReward:
    return ReferralInviteReward(
        reward_bid=reward_bid,
        campaign_bid="campaign-admin-queue",
        reward_rule_bid="rule-admin-queue",
        relation_bid=relation_bid,
        inviter_user_bid=inviter_user_bid,
        invitee_user_bid=invitee_user_bid,
        reward_status=status,
        reward_target="inviter",
        reward_type="billing_plan_cycle",
        reward_product_code="creator-plan-monthly-pro",
        reward_cycle_count=1,
        reward_credit_amount=Decimal("1000.0000000000"),
        reward_credit_validity_days=30,
        reward_cap_scope="per_inviter",
        reward_cap_count=12,
        reward_timing_policy="immediate_extend_or_defer",
        rule_snapshot={},
        billing_artifacts={
            "bill_order_bid": bill_order_bid,
            "billing_subscription_bid": "sub-admin-queue",
            "wallet_bucket_bid": f"bucket-{bill_order_bid}",
            "ledger_bid": f"ledger-{bill_order_bid}",
        },
        effective_at=None,
        expires_at=None,
        created_at=created_at,
        updated_at=created_at,
    )


def _billing_artifacts(
    *,
    bill_order_bid: str,
    reward_bid: str,
    start_at: datetime,
    end_at: datetime,
    ledger_state: str,
) -> tuple[BillingOrder, CreditWalletBucket, CreditLedgerEntry]:
    order = BillingOrder(
        bill_order_bid=bill_order_bid,
        creator_bid="inviter-admin-queue",
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        product_bid="product-monthly-pro",
        subscription_bid="sub-admin-queue",
        currency="CNY",
        payable_amount=0,
        paid_amount=0,
        payment_provider="manual",
        channel="manual",
        provider_reference_id=f"referral-reward:{reward_bid}",
        status=BILLING_ORDER_STATUS_PAID,
        paid_at=start_at,
        metadata_json={
            "checkout_type": "referral_invitation_reward",
            "renewal_cycle_start_at": start_at.isoformat(),
            "renewal_cycle_end_at": end_at.isoformat(),
        },
    )
    bucket = CreditWalletBucket(
        wallet_bucket_bid=f"bucket-{bill_order_bid}",
        wallet_bid="wallet-admin-queue",
        creator_bid="inviter-admin-queue",
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        source_bid=bill_order_bid,
        priority=20,
        original_credits=Decimal("1000.0000000000"),
        available_credits=(
            Decimal("0.0000000000")
            if ledger_state == "reserved"
            else Decimal("1000.0000000000")
        ),
        reserved_credits=(
            Decimal("1000.0000000000")
            if ledger_state == "reserved"
            else Decimal("0.0000000000")
        ),
        consumed_credits=Decimal("0.0000000000"),
        expired_credits=Decimal("0.0000000000"),
        effective_from=start_at,
        effective_to=end_at,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
        metadata_json={},
    )
    ledger = CreditLedgerEntry(
        ledger_bid=f"ledger-{bill_order_bid}",
        creator_bid="inviter-admin-queue",
        wallet_bid="wallet-admin-queue",
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        source_bid=bill_order_bid,
        idempotency_key=f"grant:{bill_order_bid}",
        amount=Decimal("1000.0000000000"),
        balance_after=Decimal("1000.0000000000"),
        expires_at=end_at,
        consumable_from=start_at,
        metadata_json={"bucket_credit_state": ledger_state},
    )
    return order, bucket, ledger


def test_operator_referral_detail_includes_inviter_reward_queue(referral_app):
    with referral_app.app_context():
        campaign = ReferralCampaign(
            campaign_bid="campaign-admin-queue",
            campaign_code="domestic_creator_invite_202606",
            campaign_name="Domestic creator invite",
            campaign_status=REFERRAL_CAMPAIGN_STATUS_ACTIVE,
            feature_flag_key="",
            invite_route_template="/invite/{invite_code}",
            inviter_eligibility={},
            invitee_eligibility={},
            invitee_benefit_policy="existing_trial_only",
            rules_copy_i18n_key="module.referral.rules.domesticCreatorInvite",
            metadata_json={},
        )
        first_relation = _relation(
            relation_bid="relation-queue-first",
            invitee_user_bid="invitee-first",
            invitee_mobile="13900000001",
        )
        second_relation = _relation(
            relation_bid="relation-queue-second",
            invitee_user_bid="invitee-second",
            invitee_mobile="13900000002",
        )
        canceled_relation = _relation(
            relation_bid="relation-queue-canceled",
            invitee_user_bid="invitee-canceled",
            invitee_mobile="13900000003",
        )
        skipped_relation = _relation(
            relation_bid="relation-queue-skipped",
            invitee_user_bid="invitee-skipped",
            invitee_mobile="13900000004",
        )
        first_start = datetime(2026, 7, 1, 0, 0, 0)
        second_start = datetime(2026, 8, 1, 0, 0, 0)
        first_reward = _reward(
            reward_bid="reward-queue-first",
            relation_bid=first_relation.relation_bid,
            invitee_user_bid=first_relation.invitee_user_bid,
            bill_order_bid="order-queue-first",
            status=REFERRAL_REWARD_STATUS_PENDING_EFFECTIVE,
            created_at=datetime(2026, 6, 11, 10, 0, 0),
        )
        second_reward = _reward(
            reward_bid="reward-queue-second",
            relation_bid=second_relation.relation_bid,
            invitee_user_bid=second_relation.invitee_user_bid,
            bill_order_bid="order-queue-second",
            status=REFERRAL_REWARD_STATUS_ACTIVE,
            created_at=datetime(2026, 6, 11, 11, 0, 0),
        )
        canceled_reward = _reward(
            reward_bid="reward-queue-canceled",
            relation_bid=canceled_relation.relation_bid,
            invitee_user_bid=canceled_relation.invitee_user_bid,
            bill_order_bid="order-queue-canceled",
            status=REFERRAL_REWARD_STATUS_CANCELED,
            created_at=datetime(2026, 6, 11, 12, 0, 0),
        )
        skipped_reward = _reward(
            reward_bid="reward-queue-skipped",
            relation_bid=skipped_relation.relation_bid,
            invitee_user_bid=skipped_relation.invitee_user_bid,
            bill_order_bid="order-queue-skipped",
            status=REFERRAL_REWARD_STATUS_SKIPPED_CAP,
            created_at=datetime(2026, 6, 11, 13, 0, 0),
        )
        artifacts = [
            *_billing_artifacts(
                bill_order_bid="order-queue-second",
                reward_bid=second_reward.reward_bid,
                start_at=second_start,
                end_at=datetime(2026, 9, 1, 0, 0, 0),
                ledger_state="available",
            ),
            *_billing_artifacts(
                bill_order_bid="order-queue-first",
                reward_bid=first_reward.reward_bid,
                start_at=first_start,
                end_at=datetime(2026, 8, 1, 0, 0, 0),
                ledger_state="reserved",
            ),
        ]
        db.session.add_all(
            [
                campaign,
                first_relation,
                second_relation,
                canceled_relation,
                skipped_relation,
                first_reward,
                second_reward,
                canceled_reward,
                skipped_reward,
                *artifacts,
            ]
        )
        db.session.commit()

        detail = get_operator_referral_detail(
            referral_app,
            relation_bid=second_relation.relation_bid,
        )

        queue = detail["reward_queue"]
        assert [item["reward_bid"] for item in queue] == [
            "reward-queue-first",
            "reward-queue-second",
        ]
        assert [item["queue_index"] for item in queue] == [1, 2]
        assert queue[0]["invitee_mobile_snapshot"] == "13900000001"
        assert queue[0]["effective_at"] == "2026-07-01T00:00:00Z"
        assert queue[0]["expires_at"] == "2026-08-01T00:00:00Z"
        assert queue[0]["ledger_credit_state"] == "reserved"
        assert queue[0]["bill_order_bid"] == "order-queue-first"
        assert queue[0]["wallet_bucket_bid"] == "bucket-order-queue-first"
        assert queue[0]["ledger_bid"] == "ledger-order-queue-first"
        assert queue[1]["ledger_credit_state"] == "available"
