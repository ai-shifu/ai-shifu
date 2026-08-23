"""Verify billing write routes preorder behavior."""

from __future__ import annotations

import pytest

from tests.service.billing import (
    billing_write_routes_test_helpers as write_route_helpers,
)
from tests.service.billing.billing_write_routes_test_helpers import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_TRIAL_PRODUCT_BID,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    ERROR_CODE,
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
    Decimal,
    billing_checkout_module,
    billing_subscriptions_module,
    calculate_self_managed_billing_cycle_end,
    dao,
    datetime,
    grant_paid_order_credits,
    mark_preorder_effective_applied,
    normalize_mysql_datetime,
    now_utc,
    self_managed_cycle_end_after_boundary,
    timedelta,
    to_utc_iso,
)


def test_mark_preorder_effective_applied_preserves_terminal_preorder_states() -> None:
    absorbed_order = BillingOrder(
        bill_order_bid="bill-preorder-absorbed-state",
        metadata_json={
            "checkout_type": "subscription_preorder",
            "preorder_state": "absorbed_by_upgrade",
        },
    )
    pending_order = BillingOrder(
        bill_order_bid="bill-preorder-pending-state",
        metadata_json={
            "checkout_type": "subscription_preorder",
            "preorder_state": "pending_effective",
        },
    )

    mark_preorder_effective_applied(absorbed_order)
    mark_preorder_effective_applied(pending_order)

    assert absorbed_order.metadata_json["preorder_state"] == "absorbed_by_upgrade"
    assert "effective_applied_at" not in absorbed_order.metadata_json
    assert pending_order.metadata_json["preorder_state"] == "effective_applied"
    assert pending_order.metadata_json["effective_applied_at"]


@pytest.fixture
def billing_write_client(monkeypatch: object) -> object:
    yield from write_route_helpers.billing_write_client(monkeypatch)


class TestBillingWriteRoutesPreorder:
    """Verify billing write routes preorder behavior."""

    def test_subscription_checkout_allows_cycle_end_preorder_while_active(
        self, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_end = now + timedelta(days=25)

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-preorder-active",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly-pro",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="pingxx",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=now - timedelta(days=5),
                    current_period_end_at=current_period_end,
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={},
                    created_at=now - timedelta(days=5),
                    updated_at=now - timedelta(days=5),
                )
            )
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
                "action": "preorder",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["checkout_type"] == "subscription_preorder"
        assert payload["data"]["effective_mode"] == "cycle_end"
        assert payload["data"]["current_product_bid"] == "bill-product-plan-monthly-pro"
        assert payload["data"]["target_product_bid"] == "bill-product-plan-monthly"
        assert payload["data"]["payable_amount"] == 990

        with app.app_context():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-preorder-active",
            ).one()
            order = BillingOrder.query.filter_by(
                bill_order_bid=payload["data"]["bill_order_bid"],
            ).one()

            assert subscription.next_product_bid == ""
            assert subscription.current_period_end_at == current_period_end
            assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
            assert order.status == BILLING_ORDER_STATUS_PENDING
            assert order.metadata_json["checkout_type"] == "subscription_preorder"
            assert order.metadata_json["preorder_state"] == "pending_effective"
            assert order.metadata_json["renewal_cycle_start_at"] == to_utc_iso(
                current_period_end
            )

    @pytest.mark.parametrize(
        ("subscription_provider", "payment_provider"),
        [
            ("stripe", "pingxx"),
            ("pingxx", "alipay"),
        ],
    )
    def test_subscription_checkout_rejects_preorder_for_managed_or_mismatched_provider(
        self,
        billing_write_client: object,
        monkeypatch: object,
        subscription_provider: str,
        payment_provider: str,
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-preorder-provider-guard",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly-pro",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider=subscription_provider,
                    provider_subscription_id=(
                        "stripe-sub-provider-guard"
                        if subscription_provider == "stripe"
                        else ""
                    ),
                    provider_customer_id="customer-provider-guard",
                    current_period_start_at=now - timedelta(days=5),
                    current_period_end_at=now + timedelta(days=25),
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={},
                    created_at=now - timedelta(days=5),
                    updated_at=now - timedelta(days=5),
                )
            )
            dao.db.session.commit()

        if payment_provider == "alipay":
            monkeypatch.setattr(
                "flaskr.service.order.payment_channel_resolution.get_config",
                lambda key, default=None: (
                    "pingxx,alipay" if key == "PAYMENT_CHANNELS_ENABLED" else default
                ),
            )

        payload = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": payment_provider,
                "action": "preorder",
            },
        ).get_json(force=True)

        assert (
            payload["code"]
            == ERROR_CODE["server.billing.subscriptionPreorderProviderUnsupported"]
        )

    def test_subscription_checkout_rejects_second_preorder_while_active(
        self, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_end = now + timedelta(days=25)

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-preorder-existing",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly-pro",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="pingxx",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=now - timedelta(days=5),
                    current_period_end_at=current_period_end,
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={},
                    created_at=now - timedelta(days=5),
                    updated_at=now - timedelta(days=5),
                )
            )
            dao.db.session.add(
                BillingOrder(
                    bill_order_bid="bill-preorder-existing",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                    product_bid="bill-product-plan-monthly",
                    subscription_bid="sub-preorder-existing",
                    currency="CNY",
                    payable_amount=990,
                    paid_amount=990,
                    payment_provider="pingxx",
                    channel="alipay_qr",
                    provider_reference_id="ch_preorder_existing",
                    status=BILLING_ORDER_STATUS_PAID,
                    paid_at=now - timedelta(minutes=5),
                    metadata_json={
                        "checkout_type": "subscription_preorder",
                        "preorder_state": "pending_effective",
                        "renewal_cycle_start_at": to_utc_iso(current_period_end),
                    },
                    created_at=now - timedelta(minutes=5),
                    updated_at=now - timedelta(minutes=5),
                )
            )
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
                "action": "preorder",
            },
        )
        payload = response.get_json(force=True)

        assert (
            payload["code"]
            == ERROR_CODE["server.billing.subscriptionPreorderAlreadyExists"]
        )

    def test_subscription_checkout_ignores_unpaid_preorder_attempt(
        self, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_end = now + timedelta(days=25)

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-preorder-unpaid-attempt",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly-pro",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="pingxx",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=now - timedelta(days=5),
                    current_period_end_at=current_period_end,
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={},
                    created_at=now - timedelta(days=5),
                    updated_at=now - timedelta(days=5),
                )
            )
            dao.db.session.add(
                BillingOrder(
                    bill_order_bid="bill-preorder-unpaid-attempt",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                    product_bid="bill-product-plan-monthly",
                    subscription_bid="sub-preorder-unpaid-attempt",
                    currency="CNY",
                    payable_amount=990,
                    paid_amount=0,
                    payment_provider="pingxx",
                    channel="alipay_qr",
                    provider_reference_id="ch_preorder_unpaid_attempt",
                    status=BILLING_ORDER_STATUS_PENDING,
                    metadata_json={
                        "checkout_type": "subscription_preorder",
                        "preorder_state": "pending_effective",
                        "renewal_cycle_start_at": to_utc_iso(current_period_end),
                    },
                    created_at=now - timedelta(minutes=5),
                    updated_at=now - timedelta(minutes=5),
                )
            )
            dao.db.session.commit()

        payload = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
                "action": "preorder",
            },
        ).get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["checkout_type"] == "subscription_preorder"
        assert payload["data"]["effective_mode"] == "cycle_end"

        with app.app_context():
            old_order = BillingOrder.query.filter_by(
                bill_order_bid="bill-preorder-unpaid-attempt",
            ).one()
            new_order = BillingOrder.query.filter_by(
                bill_order_bid=payload["data"]["bill_order_bid"],
            ).one()

            assert old_order.status == BILLING_ORDER_STATUS_PENDING
            assert old_order.metadata_json["preorder_state"] == "pending_effective"
            assert new_order.status == BILLING_ORDER_STATUS_PENDING
            assert new_order.metadata_json["checkout_type"] == "subscription_preorder"
            assert new_order.metadata_json["preorder_state"] == "pending_effective"

    def test_subscription_checkout_rechecks_preorder_after_subscription_lock(
        self,
        billing_write_client: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_start = now - timedelta(days=5)
        current_period_end = now + timedelta(days=25)

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-preorder-lock-race",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly-pro",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=current_period_start,
                current_period_end_at=current_period_end,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            dao.db.session.add(subscription)
            dao.db.session.commit()

        def fake_lock_subscription_for_checkout(
            subscription: BillingSubscription,
        ) -> BillingSubscription:
            dao.db.session.add(
                BillingOrder(
                    bill_order_bid="bill-preorder-lock-race",
                    creator_bid=subscription.creator_bid,
                    order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                    product_bid="bill-product-plan-monthly",
                    subscription_bid=subscription.subscription_bid,
                    currency="CNY",
                    payable_amount=990,
                    paid_amount=990,
                    payment_provider="pingxx",
                    channel="alipay_qr",
                    provider_reference_id="ch_preorder_lock_race",
                    status=BILLING_ORDER_STATUS_PAID,
                    paid_at=now - timedelta(minutes=1),
                    metadata_json={
                        "checkout_type": "subscription_preorder",
                        "preorder_state": "pending_effective",
                    },
                    created_at=now - timedelta(minutes=1),
                    updated_at=now - timedelta(minutes=1),
                )
            )
            dao.db.session.flush()
            return subscription

        monkeypatch.setattr(
            billing_checkout_module,
            "_lock_subscription_for_checkout",
            fake_lock_subscription_for_checkout,
            raising=False,
        )

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
                "action": "preorder",
            },
        ).get_json(force=True)

        assert (
            response["code"]
            == ERROR_CODE["server.billing.subscriptionPreorderAlreadyExists"]
        )

    def test_paid_preorder_sync_reserves_credits_and_sets_next_product(
        self, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_start = now - timedelta(days=5)
        current_period_end = now + timedelta(days=25)

        with app.app_context():
            wallet = CreditWallet(
                wallet_bid="wallet-preorder-sync",
                creator_bid="creator-1",
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("0"),
                lifetime_granted_credits=Decimal("100.0000000000"),
                lifetime_consumed_credits=Decimal("97.0000000000"),
                last_settled_usage_id=0,
                version=0,
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            subscription = BillingSubscription(
                subscription_bid="sub-preorder-sync",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly-pro",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=current_period_start,
                current_period_end_at=current_period_end,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            bucket = CreditWalletBucket(
                wallet_bucket_bid="bucket-preorder-sync",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-preorder-current-cycle",
                priority=20,
                original_credits=Decimal("100.0000000000"),
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("97.0000000000"),
                expired_credits=Decimal("0"),
                effective_from=current_period_start,
                effective_to=current_period_end,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "bill_order_bid": "bill-preorder-current-cycle",
                    "subscription_bid": "sub-preorder-sync",
                    "product_bid": "bill-product-plan-monthly-pro",
                    "payment_provider": "pingxx",
                },
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            dao.db.session.add(wallet)
            dao.db.session.add(subscription)
            dao.db.session.add(bucket)
            dao.db.session.commit()

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
                "action": "preorder",
            },
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]
        assert checkout["code"] == 0

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-preorder-sync",
            ).one()
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            product = BillingProduct.query.filter_by(
                product_bid=order.product_bid
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-preorder-sync",
            ).one()
            grant_ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            downgrade_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-preorder-sync",
                event_type=BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
            ).one()

            assert order.status == BILLING_ORDER_STATUS_PAID
            assert order.metadata_json["preorder_state"] == "pending_effective"
            assert subscription.product_bid == "bill-product-plan-monthly-pro"
            assert subscription.next_product_bid == "bill-product-plan-monthly"
            assert subscription.metadata_json["preorder_order_bid"] == bill_order_bid
            assert subscription.current_period_start_at == current_period_start
            assert subscription.current_period_end_at == current_period_end
            assert bucket.source_bid == bill_order_bid
            assert bucket.available_credits == Decimal("3.0000000000")
            assert bucket.reserved_credits == Decimal("5.0000000000")
            assert bucket.effective_from == current_period_start
            assert bucket.effective_to == current_period_end
            assert wallet.available_credits == Decimal("3.0000000000")
            assert wallet.reserved_credits == Decimal("5.0000000000")
            assert grant_ledger.metadata_json["bucket_credit_state"] == "reserved"
            assert grant_ledger.consumable_from == current_period_end
            assert grant_ledger.expires_at == self_managed_cycle_end_after_boundary(
                product,
                current_period_end,
            )
            assert downgrade_event.scheduled_at == normalize_mysql_datetime(
                current_period_end
            )

        replayed_sync = client.post(
            f"/api/billing/orders/{bill_order_bid}/sync"
        ).get_json(force=True)
        assert replayed_sync["code"] == 0
        assert replayed_sync["data"]["status"] == "paid"

        with app.app_context():
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-preorder-sync",
            ).one()

            assert bucket.available_credits == Decimal("3.0000000000")
            assert bucket.reserved_credits == Decimal("5.0000000000")
            assert bucket.effective_from == current_period_start
            assert bucket.effective_to == current_period_end
            assert wallet.available_credits == Decimal("3.0000000000")
            assert wallet.reserved_credits == Decimal("5.0000000000")

    def test_paid_preorder_replay_repairs_future_dated_shared_bucket(
        self,
        billing_write_client: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        app = billing_write_client["app"]
        current_period_start = datetime(2026, 6, 24, 7, 35, 58)
        current_period_end = datetime(2026, 7, 23, 15, 59, 59)
        next_period_end = datetime(2026, 8, 22, 15, 59, 59)
        replayed_at = datetime(2026, 7, 20, 0, 0, 0)
        monkeypatch.setattr(
            billing_subscriptions_module,
            "now_utc",
            lambda: replayed_at,
        )

        with app.app_context():
            wallet = CreditWallet(
                wallet_bid="wallet-preorder-damaged-replay",
                creator_bid="creator-1",
                available_credits=Decimal("234.7800000000"),
                reserved_credits=Decimal("2050.0000000000"),
                lifetime_granted_credits=Decimal("4050.0000000000"),
                lifetime_consumed_credits=Decimal("315.2400000000"),
                last_settled_usage_id=0,
                version=0,
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            subscription = BillingSubscription(
                subscription_bid="sub-preorder-damaged-replay",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly-pro",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=current_period_start,
                current_period_end_at=current_period_end,
                cancel_at_period_end=0,
                next_product_bid="bill-product-plan-monthly",
                metadata_json={
                    "preorder_order_bid": "bill-preorder-damaged-replay",
                },
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            order = BillingOrder(
                bill_order_bid="bill-preorder-damaged-replay",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                product_bid="bill-product-plan-monthly",
                subscription_bid=subscription.subscription_bid,
                currency="CNY",
                payable_amount=990,
                paid_amount=990,
                payment_provider="pingxx",
                channel="alipay_qr",
                provider_reference_id="ch_preorder_damaged_replay",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=current_period_end - timedelta(days=5),
                metadata_json={
                    "checkout_type": "subscription_preorder",
                    "preorder_state": "pending_effective",
                    "renewal_cycle_start_at": to_utc_iso(current_period_end),
                    "renewal_cycle_end_at": to_utc_iso(next_period_end),
                },
            )
            bucket = CreditWalletBucket(
                wallet_bucket_bid="bucket-preorder-damaged-replay",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid=order.bill_order_bid,
                priority=20,
                original_credits=Decimal("4050.0000000000"),
                available_credits=Decimal("1684.7600000000"),
                reserved_credits=Decimal("2050.0000000000"),
                consumed_credits=Decimal("315.2400000000"),
                expired_credits=Decimal("0"),
                effective_from=current_period_end,
                effective_to=next_period_end,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "bill_order_bid": order.bill_order_bid,
                    "subscription_bid": subscription.subscription_bid,
                    "product_bid": order.product_bid,
                    "payment_provider": "pingxx",
                },
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            grant_ledger = CreditLedgerEntry(
                ledger_bid="ledger-preorder-damaged-replay",
                creator_bid="creator-1",
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid=bucket.wallet_bucket_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid=order.bill_order_bid,
                idempotency_key=f"grant:{order.bill_order_bid}",
                amount=Decimal("50.0000000000"),
                balance_after=Decimal("1684.7600000000"),
                expires_at=next_period_end,
                consumable_from=current_period_end,
                metadata_json={
                    "bill_order_bid": order.bill_order_bid,
                    "subscription_bid": subscription.subscription_bid,
                    "product_bid": order.product_bid,
                    "payment_provider": "pingxx",
                    "grant_reason": "subscription",
                    "bucket_credit_state": "reserved",
                    "reserved_until": to_utc_iso(current_period_end),
                },
                created_at=current_period_end - timedelta(days=5),
                updated_at=current_period_end - timedelta(days=5),
            )
            dao.db.session.add(wallet)
            dao.db.session.add(subscription)
            dao.db.session.add(order)
            dao.db.session.add(bucket)
            dao.db.session.add(grant_ledger)
            dao.db.session.flush()

            granted = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-preorder-damaged-replay",
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()

            assert granted is False
            assert bucket.available_credits == Decimal("1684.7600000000")
            assert bucket.reserved_credits == Decimal("2050.0000000000")
            assert bucket.effective_from == current_period_start
            assert bucket.effective_to == current_period_end
            assert wallet.available_credits == Decimal("1684.7600000000")
            assert wallet.reserved_credits == Decimal("2050.0000000000")

    def test_paid_same_plan_preorder_sync_reserves_until_cycle_boundary(
        self, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_start = now - timedelta(days=5)
        current_period_end = now + timedelta(days=25)

        with app.app_context():
            wallet = CreditWallet(
                wallet_bid="wallet-preorder-same-plan-sync",
                creator_bid="creator-1",
                available_credits=Decimal("105.0000000000"),
                reserved_credits=Decimal("0"),
                lifetime_granted_credits=Decimal("105.0000000000"),
                lifetime_consumed_credits=Decimal("0"),
                last_settled_usage_id=0,
                version=0,
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            subscription = BillingSubscription(
                subscription_bid="sub-preorder-same-plan-sync",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=current_period_start,
                current_period_end_at=current_period_end,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            bucket = CreditWalletBucket(
                wallet_bucket_bid="bucket-preorder-same-plan-sync",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-preorder-same-plan-current",
                priority=20,
                original_credits=Decimal("105.0000000000"),
                available_credits=Decimal("105.0000000000"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("0"),
                expired_credits=Decimal("0"),
                effective_from=current_period_start,
                effective_to=current_period_end,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "bill_order_bid": "bill-preorder-same-plan-current",
                    "subscription_bid": "sub-preorder-same-plan-sync",
                    "product_bid": "bill-product-plan-monthly",
                    "payment_provider": "pingxx",
                },
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            dao.db.session.add(wallet)
            dao.db.session.add(subscription)
            dao.db.session.add(bucket)
            dao.db.session.commit()

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
                "action": "preorder",
            },
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]
        assert checkout["code"] == 0
        assert checkout["data"]["checkout_type"] == "subscription_preorder"

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-preorder-same-plan-sync",
            ).one()
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            product = BillingProduct.query.filter_by(
                product_bid=order.product_bid,
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-preorder-same-plan-sync",
            ).one()
            grant_ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            downgrade_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-preorder-same-plan-sync",
                event_type=BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
            ).first()
            expected_cycle_end = self_managed_cycle_end_after_boundary(
                product,
                current_period_end,
            )

            assert order.status == BILLING_ORDER_STATUS_PAID
            assert order.metadata_json["preorder_state"] == "pending_effective"
            assert subscription.product_bid == "bill-product-plan-monthly"
            assert subscription.next_product_bid == "bill-product-plan-monthly"
            assert subscription.metadata_json["preorder_order_bid"] == bill_order_bid
            assert subscription.current_period_start_at == current_period_start
            assert subscription.current_period_end_at == current_period_end
            assert bucket.source_bid == bill_order_bid
            assert bucket.available_credits == Decimal("105.0000000000")
            assert bucket.reserved_credits == Decimal("5.0000000000")
            assert bucket.effective_from == current_period_start
            assert bucket.effective_to == current_period_end
            assert wallet.available_credits == Decimal("105.0000000000")
            assert wallet.reserved_credits == Decimal("5.0000000000")
            assert wallet.lifetime_granted_credits == Decimal("110.0000000000")
            assert grant_ledger.metadata_json["bucket_credit_state"] == "reserved"
            assert grant_ledger.consumable_from == current_period_end
            assert grant_ledger.expires_at == expected_cycle_end
            assert downgrade_event is not None
            assert downgrade_event.scheduled_at == normalize_mysql_datetime(
                current_period_end
            )

        upgrade_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly-pro",
                "payment_provider": "pingxx",
                "action": "upgrade_immediate",
            },
        ).get_json(force=True)
        assert upgrade_checkout["code"] == 0
        assert upgrade_checkout["data"]["status"] == "pending"
        assert upgrade_checkout["data"]["prepaid_offset_amount"] == 990
        assert upgrade_checkout["data"]["payable_amount"] == 18910
        assert upgrade_checkout["data"]["preorder_order_bid"] == bill_order_bid

    def test_subscription_checkout_allows_trial_upgrade_when_plan_tier_uses_sort_order(
        self, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_start = now - timedelta(days=1)
        current_period_end = now + timedelta(days=14)

        with app.app_context():
            for product_bid in [
                BILLING_TRIAL_PRODUCT_BID,
                "bill-product-plan-monthly",
            ]:
                product = BillingProduct.query.filter_by(
                    product_bid=product_bid,
                ).one()
                metadata = (
                    dict(product.metadata_json)
                    if isinstance(product.metadata_json, dict)
                    else {}
                )
                metadata.pop("plan_tier", None)
                product.metadata_json = metadata
            subscription = BillingSubscription(
                subscription_bid="sub-trial-upgrade-sort-order",
                creator_bid="creator-1",
                product_bid=BILLING_TRIAL_PRODUCT_BID,
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="manual",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=current_period_start,
                current_period_end_at=current_period_end,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            dao.db.session.add(subscription)
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
                "action": "upgrade_immediate",
            },
        ).get_json(force=True)

        assert response["code"] == 0
        assert response["data"]["status"] == "pending"
        assert response["data"]["checkout_type"] == "subscription"
        assert response["data"]["effective_mode"] == "immediate"
        assert response["data"]["current_product_bid"] == BILLING_TRIAL_PRODUCT_BID
        assert response["data"]["target_product_bid"] == "bill-product-plan-monthly"
        assert response["data"]["payable_amount"] == 990

        with app.app_context():
            order = BillingOrder.query.filter_by(
                bill_order_bid=response["data"]["bill_order_bid"],
            ).one()
            assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE
            assert order.payment_provider == "pingxx"
            assert order.metadata_json["current_product_bid"] == (
                BILLING_TRIAL_PRODUCT_BID
            )

    def test_subscription_checkout_preorder_uses_sort_order_when_plan_tier_missing(
        self, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_start = now - timedelta(days=5)
        current_period_end = now + timedelta(days=25)

        with app.app_context():
            target_product = BillingProduct.query.filter_by(
                product_bid="bill-product-plan-monthly",
            ).one()
            target_metadata = (
                dict(target_product.metadata_json)
                if isinstance(target_product.metadata_json, dict)
                else {}
            )
            target_metadata.pop("plan_tier", None)
            target_product.metadata_json = target_metadata
            subscription = BillingSubscription(
                subscription_bid="sub-preorder-missing-target-tier",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly-pro",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=current_period_start,
                current_period_end_at=current_period_end,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            dao.db.session.add(subscription)
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
                "action": "preorder",
            },
        ).get_json(force=True)

        assert response["code"] == 0
        assert response["data"]["status"] == "pending"
        assert response["data"]["checkout_type"] == "subscription_preorder"
        assert response["data"]["current_product_bid"] == (
            "bill-product-plan-monthly-pro"
        )
        assert response["data"]["target_product_bid"] == "bill-product-plan-monthly"

    def test_subscription_checkout_rejects_stacked_same_plan_preorder_after_cycle_extended(
        self, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_start = now - timedelta(days=5)

        with app.app_context():
            product = BillingProduct.query.filter_by(
                product_bid="bill-product-plan-monthly",
            ).one()
            max_single_prepaid_end = calculate_self_managed_billing_cycle_end(
                product,
                cycle_start_at=now,
            )
            assert max_single_prepaid_end is not None
            current_period_end = max_single_prepaid_end + timedelta(days=30)
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-preorder-stacked-same-plan",
                    creator_bid="creator-1",
                    product_bid=product.product_bid,
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="pingxx",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=current_period_start,
                    current_period_end_at=current_period_end,
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={},
                    created_at=current_period_start,
                    updated_at=current_period_start,
                )
            )
            dao.db.session.commit()

        payload = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
                "action": "preorder",
            },
        ).get_json(force=True)

        assert (
            payload["code"]
            == ERROR_CODE["server.billing.subscriptionPreorderAlreadyExists"]
        )

        with app.app_context():
            renewal_orders = BillingOrder.query.filter_by(
                subscription_bid="sub-preorder-stacked-same-plan",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            ).all()
            assert renewal_orders == []

    def test_subscription_checkout_immediate_upgrade_absorbs_paid_preorder_after_paid(
        self, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_start = now - timedelta(days=5)
        current_period_end = now + timedelta(days=25)

        with app.app_context():
            wallet = CreditWallet(
                wallet_bid="wallet-preorder-upgrade",
                creator_bid="creator-1",
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("5.0000000000"),
                lifetime_granted_credits=Decimal("105.0000000000"),
                lifetime_consumed_credits=Decimal("97.0000000000"),
                last_settled_usage_id=0,
                version=0,
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-preorder-upgrade",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly-pro",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="pingxx",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=current_period_start,
                    current_period_end_at=current_period_end,
                    cancel_at_period_end=0,
                    next_product_bid="bill-product-plan-monthly",
                    metadata_json={"preorder_order_bid": "bill-preorder-paid"},
                    created_at=current_period_start,
                    updated_at=current_period_start,
                )
            )
            dao.db.session.add(
                BillingOrder(
                    bill_order_bid="bill-preorder-paid",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                    product_bid="bill-product-plan-monthly",
                    subscription_bid="sub-preorder-upgrade",
                    currency="CNY",
                    payable_amount=990,
                    paid_amount=990,
                    payment_provider="pingxx",
                    channel="alipay_qr",
                    provider_reference_id="ch_preorder_paid",
                    status=BILLING_ORDER_STATUS_PAID,
                    paid_at=now - timedelta(minutes=5),
                    metadata_json={
                        "checkout_type": "subscription_preorder",
                        "preorder_state": "pending_effective",
                        "renewal_cycle_start_at": to_utc_iso(current_period_end),
                    },
                    created_at=now - timedelta(minutes=5),
                    updated_at=now - timedelta(minutes=5),
                )
            )
            dao.db.session.add(wallet)
            dao.db.session.add(
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-preorder-upgrade",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid="bill-preorder-paid",
                    priority=20,
                    original_credits=Decimal("105.0000000000"),
                    available_credits=Decimal("3.0000000000"),
                    reserved_credits=Decimal("5.0000000000"),
                    consumed_credits=Decimal("97.0000000000"),
                    expired_credits=Decimal("0"),
                    effective_from=current_period_start,
                    effective_to=current_period_end,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={"bill_order_bid": "bill-preorder-paid"},
                    created_at=current_period_start,
                    updated_at=current_period_start,
                )
            )
            dao.db.session.add(
                CreditLedgerEntry(
                    ledger_bid="ledger-preorder-upgrade",
                    creator_bid="creator-1",
                    wallet_bid=wallet.wallet_bid,
                    wallet_bucket_bid="bucket-preorder-upgrade",
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid="bill-preorder-paid",
                    idempotency_key="grant:bill-preorder-paid",
                    amount=Decimal("5.0000000000"),
                    balance_after=Decimal("3.0000000000"),
                    expires_at=current_period_end + timedelta(days=30),
                    consumable_from=current_period_end,
                    metadata_json={
                        "bill_order_bid": "bill-preorder-paid",
                        "subscription_bid": "sub-preorder-upgrade",
                        "product_bid": "bill-product-plan-monthly",
                        "payment_provider": "pingxx",
                        "grant_reason": "subscription_renewal",
                        "bucket_credit_state": "reserved",
                        "reserved_until": to_utc_iso(current_period_end),
                    },
                    created_at=now - timedelta(minutes=5),
                    updated_at=now - timedelta(minutes=5),
                )
            )
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-yearly-lite",
                "payment_provider": "pingxx",
                "action": "upgrade_immediate",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["status"] == "pending"
        assert payload["data"]["prepaid_offset_amount"] == 990
        assert payload["data"]["payable_amount"] == 799010

        with app.app_context():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-preorder-upgrade",
            ).one()
            preorder_order = BillingOrder.query.filter_by(
                bill_order_bid="bill-preorder-paid",
            ).one()
            upgrade_order = BillingOrder.query.filter_by(
                bill_order_bid=payload["data"]["bill_order_bid"],
            ).one()
            wallet = CreditWallet.query.filter_by(
                wallet_bid="wallet-preorder-upgrade",
            ).one()
            bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-preorder-upgrade",
            ).one()
            preorder_ledger = CreditLedgerEntry.query.filter_by(
                ledger_bid="ledger-preorder-upgrade",
            ).one()

            assert subscription.next_product_bid == "bill-product-plan-monthly"
            assert subscription.metadata_json["preorder_order_bid"] == (
                "bill-preorder-paid"
            )
            assert upgrade_order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE
            assert upgrade_order.payable_amount == 799010
            assert upgrade_order.metadata_json["preorder_order_bid"] == (
                "bill-preorder-paid"
            )
            assert preorder_order.status == BILLING_ORDER_STATUS_PAID
            assert preorder_order.metadata_json["preorder_state"] == (
                "pending_effective"
            )
            assert bucket.available_credits == Decimal("3.0000000000")
            assert bucket.reserved_credits == Decimal("5.0000000000")
            assert bucket.original_credits == Decimal("105.0000000000")
            assert wallet.available_credits == Decimal("3.0000000000")
            assert wallet.reserved_credits == Decimal("5.0000000000")
            assert wallet.lifetime_granted_credits == Decimal("105.0000000000")
            assert preorder_ledger.metadata_json["bucket_credit_state"] == "reserved"

        sync = client.post(
            f"/api/billing/orders/{payload['data']['bill_order_bid']}/sync"
        ).get_json(force=True)
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-preorder-upgrade",
            ).one()
            preorder_order = BillingOrder.query.filter_by(
                bill_order_bid="bill-preorder-paid",
            ).one()
            upgrade_order = BillingOrder.query.filter_by(
                bill_order_bid=payload["data"]["bill_order_bid"],
            ).one()
            wallet = CreditWallet.query.filter_by(
                wallet_bid="wallet-preorder-upgrade",
            ).one()
            bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-preorder-upgrade",
            ).one()
            preorder_ledger = CreditLedgerEntry.query.filter_by(
                ledger_bid="ledger-preorder-upgrade",
            ).one()

            assert subscription.product_bid == "bill-product-plan-yearly-lite"
            assert subscription.next_product_bid == ""
            assert "preorder_order_bid" not in subscription.metadata_json
            assert preorder_order.status == BILLING_ORDER_STATUS_PAID
            assert preorder_order.metadata_json["preorder_state"] == (
                "absorbed_by_upgrade"
            )
            assert preorder_ledger.metadata_json["absorbed_by_bill_order_bid"] == (
                upgrade_order.bill_order_bid
            )
            assert bucket.reserved_credits == Decimal("0E-10")
            assert wallet.reserved_credits == Decimal("0E-10")
            assert wallet.lifetime_granted_credits == Decimal("5105.0000000000")

    def test_subscription_checkout_rejects_paid_preorder_offset_provider_mismatch(
        self, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_start = now - timedelta(days=5)
        current_period_end = now + timedelta(days=25)

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-preorder-upgrade-provider-mismatch",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly-pro",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="pingxx",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=current_period_start,
                    current_period_end_at=current_period_end,
                    cancel_at_period_end=0,
                    next_product_bid="bill-product-plan-monthly",
                    metadata_json={
                        "preorder_order_bid": "bill-preorder-paid-provider-mismatch"
                    },
                    created_at=current_period_start,
                    updated_at=current_period_start,
                )
            )
            dao.db.session.add(
                BillingOrder(
                    bill_order_bid="bill-preorder-paid-provider-mismatch",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                    product_bid="bill-product-plan-monthly",
                    subscription_bid="sub-preorder-upgrade-provider-mismatch",
                    currency="CNY",
                    payable_amount=990,
                    paid_amount=990,
                    payment_provider="pingxx",
                    channel="alipay_qr",
                    provider_reference_id="ch_preorder_paid_provider_mismatch",
                    status=BILLING_ORDER_STATUS_PAID,
                    paid_at=now - timedelta(minutes=5),
                    metadata_json={
                        "checkout_type": "subscription_preorder",
                        "preorder_state": "pending_effective",
                        "renewal_cycle_start_at": to_utc_iso(current_period_end),
                    },
                    created_at=now - timedelta(minutes=5),
                    updated_at=now - timedelta(minutes=5),
                )
            )
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-yearly-lite",
                "payment_provider": "stripe",
                "action": "upgrade_immediate",
            },
        )
        payload = response.get_json(force=True)

        assert (
            payload["code"]
            == ERROR_CODE["server.billing.subscriptionPreorderProviderUnsupported"]
        )
        with app.app_context():
            upgrade_order = BillingOrder.query.filter_by(
                subscription_bid="sub-preorder-upgrade-provider-mismatch",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
            ).first()
            assert upgrade_order is None

    def test_subscription_checkout_allows_immediate_upgrade_with_unpaid_preorder_attempt(
        self, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_start = now - timedelta(days=5)
        current_period_end = now + timedelta(days=25)

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-preorder-pending-upgrade",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly-pro",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="pingxx",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=current_period_start,
                    current_period_end_at=current_period_end,
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={},
                    created_at=current_period_start,
                    updated_at=current_period_start,
                )
            )
            dao.db.session.add(
                BillingOrder(
                    bill_order_bid="bill-preorder-pending",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                    product_bid="bill-product-plan-monthly",
                    subscription_bid="sub-preorder-pending-upgrade",
                    currency="CNY",
                    payable_amount=990,
                    paid_amount=0,
                    payment_provider="pingxx",
                    channel="alipay_qr",
                    provider_reference_id="ch_preorder_pending",
                    status=BILLING_ORDER_STATUS_PENDING,
                    metadata_json={
                        "checkout_type": "subscription_preorder",
                        "preorder_state": "pending_effective",
                        "renewal_cycle_start_at": to_utc_iso(current_period_end),
                    },
                    created_at=now - timedelta(minutes=5),
                    updated_at=now - timedelta(minutes=5),
                )
            )
            dao.db.session.commit()

        payload = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-yearly-lite",
                "payment_provider": "pingxx",
                "action": "upgrade_immediate",
            },
        ).get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["checkout_type"] == "subscription"
        assert payload["data"]["effective_mode"] == "immediate"
        assert payload["data"]["prepaid_offset_amount"] == 0

        with app.app_context():
            preorder_order = BillingOrder.query.filter_by(
                bill_order_bid="bill-preorder-pending",
            ).one()
            upgrade_order = BillingOrder.query.filter_by(
                subscription_bid="sub-preorder-pending-upgrade",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
            ).first()

            assert upgrade_order is not None
            assert upgrade_order.status == BILLING_ORDER_STATUS_PENDING
            assert upgrade_order.metadata_json["prepaid_offset_amount"] == 0
            assert preorder_order.status == BILLING_ORDER_STATUS_PENDING
            assert preorder_order.metadata_json["preorder_state"] == (
                "pending_effective"
            )
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-preorder-pending-upgrade",
            ).one()
            assert subscription.product_bid == "bill-product-plan-monthly-pro"
            assert subscription.next_product_bid == ""
            assert not preorder_order.metadata_json.get("absorbed_by_bill_order_bid")

    def test_terminal_preorder_order_cannot_reactivate_subscription(
        self, billing_write_client: object
    ) -> None:
        app = billing_write_client["app"]
        now = now_utc()
        current_period_start = now - timedelta(days=5)
        current_period_end = now + timedelta(days=25)
        renewal_cycle_end = current_period_end + timedelta(days=30)

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-absorbed-preorder-replay",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly-pro",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=current_period_start,
                current_period_end_at=current_period_end,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=current_period_start,
                updated_at=current_period_start,
            )
            order = BillingOrder(
                bill_order_bid="bill-preorder-absorbed-replay",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                product_bid="bill-product-plan-monthly",
                subscription_bid="sub-absorbed-preorder-replay",
                currency="CNY",
                payable_amount=990,
                paid_amount=990,
                payment_provider="pingxx",
                channel="alipay_qr",
                provider_reference_id="ch_preorder_absorbed_replay",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=now - timedelta(days=1),
                metadata_json={
                    "checkout_type": "subscription_preorder",
                    "preorder_state": "absorbed_by_upgrade",
                    "absorbed_by_bill_order_bid": "bill-upgrade-absorbed-replay",
                    "renewal_cycle_start_at": to_utc_iso(current_period_end),
                    "renewal_cycle_end_at": to_utc_iso(renewal_cycle_end),
                },
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
            )
            dao.db.session.add(subscription)
            dao.db.session.add(order)
            dao.db.session.flush()

            activated = (
                billing_subscriptions_module.activate_subscription_for_paid_order(
                    app,
                    order,
                    subscription=subscription,
                    force=True,
                )
            )
            dao.db.session.commit()

            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-absorbed-preorder-replay",
            ).one()
            order = BillingOrder.query.filter_by(
                bill_order_bid="bill-preorder-absorbed-replay",
            ).one()

            assert activated is False
            assert subscription.product_bid == "bill-product-plan-monthly-pro"
            assert subscription.next_product_bid == ""
            assert order.metadata_json["preorder_state"] == "absorbed_by_upgrade"

    def test_subscription_checkout_rejects_zero_payable_upgrade_with_paid_preorder(
        self, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_end = now + timedelta(days=25)

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-preorder-zero-upgrade",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly-pro",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="pingxx",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=now - timedelta(days=5),
                    current_period_end_at=current_period_end,
                    cancel_at_period_end=0,
                    next_product_bid="bill-product-plan-monthly",
                    metadata_json={"preorder_order_bid": "bill-preorder-zero-paid"},
                    created_at=now - timedelta(days=5),
                    updated_at=now - timedelta(days=5),
                )
            )
            dao.db.session.add(
                BillingOrder(
                    bill_order_bid="bill-preorder-zero-paid",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                    product_bid="bill-product-plan-monthly",
                    subscription_bid="sub-preorder-zero-upgrade",
                    currency="CNY",
                    payable_amount=800000,
                    paid_amount=800000,
                    payment_provider="pingxx",
                    channel="alipay_qr",
                    provider_reference_id="ch_preorder_zero_paid",
                    status=BILLING_ORDER_STATUS_PAID,
                    paid_at=now - timedelta(minutes=5),
                    metadata_json={
                        "checkout_type": "subscription_preorder",
                        "preorder_state": "pending_effective",
                        "renewal_cycle_start_at": to_utc_iso(current_period_end),
                    },
                    created_at=now - timedelta(minutes=5),
                    updated_at=now - timedelta(minutes=5),
                )
            )
            dao.db.session.commit()

        payload = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-yearly-lite",
                "payment_provider": "pingxx",
                "action": "upgrade_immediate",
            },
        ).get_json(force=True)

        assert (
            payload["code"]
            == ERROR_CODE["server.billing.subscriptionUpgradeAmountInvalid"]
        )
        assert billing_write_client["pingxx_requests"] == []

        with app.app_context():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-preorder-zero-upgrade",
            ).one()
            preorder_order = BillingOrder.query.filter_by(
                bill_order_bid="bill-preorder-zero-paid",
            ).one()
            upgrade_order = BillingOrder.query.filter_by(
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
                product_bid="bill-product-plan-yearly-lite",
            ).first()

            assert subscription.product_bid == "bill-product-plan-monthly-pro"
            assert subscription.next_product_bid == "bill-product-plan-monthly"
            assert preorder_order.metadata_json["preorder_state"] == (
                "pending_effective"
            )
            assert upgrade_order is None
