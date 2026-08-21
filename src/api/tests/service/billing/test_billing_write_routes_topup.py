"""Verify billing write routes topup behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.service.billing import (
    billing_write_routes_test_helpers as write_route_helpers,
)
from tests.service.billing.billing_write_routes_test_helpers import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_TRIAL_PRODUCT_BID,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_TOPUP,
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
    Decimal,
    PingxxOrder,
    StripeOrder,
    add_active_subscription,
    add_trial_subscription_state,
    dao,
    now_utc,
    repair_topup_grant_expiries,
    seed_creator_user,
    timedelta,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def billing_write_client(monkeypatch) -> Iterator[dict[str, object]]:
    yield from write_route_helpers.billing_write_client(monkeypatch)


class TestBillingWriteRoutesTopup:
    """Verify billing write routes topup behavior."""

    def test_topup_checkout_and_sync_mark_order_paid(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        add_active_subscription(app, subscription_bid="sub-topup-paid-1")

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
            headers={"X-Language": "zh-CN"},
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        assert checkout["data"]["status"] == "pending"
        assert checkout["data"]["payment_payload"]["credential"]["alipay_qr"] == (
            "https://pingxx.test/qr"
        )
        assert billing_write_client["pingxx_requests"][0]["subject"] == "20 积分包"
        assert billing_write_client["pingxx_requests"][0]["body"] == "20 积分包"

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            raw_order = PingxxOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid=bill_order_bid,
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert order.paid_at is not None
            assert wallet.available_credits == 20
            assert wallet.reserved_credits == Decimal("0E-10")
            assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP
            assert bucket.source_type == CREDIT_SOURCE_TYPE_TOPUP
            assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
            assert bucket.available_credits == 20
            assert ledger.amount == 20
            assert ledger.wallet_bucket_bid == bucket.wallet_bucket_bid
            assert raw_order.status == 1
            assert raw_order.charge_id == "ch_billing_test"
            assert (
                PingxxOrder.query.filter_by(
                    biz_domain="billing",
                    bill_order_bid=bill_order_bid,
                ).count()
                == 1
            )

    def test_stripe_topup_checkout_keeps_one_time_line_item(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        add_active_subscription(app, subscription_bid="sub-topup-stripe-1")

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "stripe",
            },
            headers={"X-Language": "zh-CN"},
        ).get_json(force=True)

        assert checkout["code"] == 0
        assert checkout["data"]["provider"] == "stripe"
        stripe_request = billing_write_client["stripe_requests"][-1]
        assert stripe_request["extra"]["session_params"]["mode"] == "payment"
        price_data = stripe_request["extra"]["line_items"][0]["price_data"]
        assert price_data["unit_amount"] == 5000
        assert "recurring" not in price_data

    def test_topup_grant_expires_with_current_subscription_period(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()
        current_period_start_at = now - timedelta(days=3)
        current_period_end_at = now + timedelta(days=27)
        add_active_subscription(
            app,
            subscription_bid="sub-topup-active-1",
            current_period_start_at=current_period_start_at,
            current_period_end_at=current_period_end_at,
        )

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            assert bucket.effective_to == current_period_end_at
            assert ledger.expires_at == current_period_end_at

    def test_repeated_topup_reuses_single_bucket_and_tracks_latest_source(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        current_period_end_at = now_utc() + timedelta(days=30)
        add_active_subscription(
            app,
            subscription_bid="sub-topup-repeat-1",
            current_period_end_at=current_period_end_at,
        )

        first_checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        first_order_bid = first_checkout["data"]["bill_order_bid"]
        first_sync = client.post(
            f"/api/billing/orders/{first_order_bid}/sync"
        ).get_json(force=True)

        with app.app_context():
            initial_bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=first_order_bid,
            ).one()
            initial_bucket_bid = initial_bucket.wallet_bucket_bid

        second_checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        second_order_bid = second_checkout["data"]["bill_order_bid"]
        second_sync = client.post(
            f"/api/billing/orders/{second_order_bid}/sync"
        ).get_json(force=True)

        assert first_sync["code"] == 0
        assert second_sync["code"] == 0

        with app.app_context():
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            topup_buckets = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            ).all()
            second_ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=second_order_bid,
            ).one()

            assert len(topup_buckets) == 1
            assert topup_buckets[0].wallet_bucket_bid == initial_bucket_bid
            assert topup_buckets[0].source_bid == second_order_bid
            assert topup_buckets[0].available_credits == 40
            assert topup_buckets[0].effective_to == current_period_end_at
            assert wallet.available_credits == 40
            assert second_ledger.wallet_bucket_bid == initial_bucket_bid
            assert second_ledger.expires_at == current_period_end_at

    def test_trial_then_paid_then_topup_prefers_paid_subscription_for_overview_and_expiry(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        seed_creator_user(app, creator_bid="creator-1")
        add_trial_subscription_state(
            app,
            subscription_bid="sub-trial-paid-then-topup",
            bill_order_bid="bill-trial-paid-then-topup",
            wallet_bid="wallet-trial-paid-then-topup",
            wallet_bucket_bid="bucket-trial-paid-then-topup",
            ledger_bid="ledger-trial-paid-then-topup",
        )

        paid_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
            },
        ).get_json(force=True)
        paid_order_bid = paid_checkout["data"]["bill_order_bid"]
        paid_sync = client.post(f"/api/billing/orders/{paid_order_bid}/sync").get_json(
            force=True
        )
        with app.app_context():
            paid_subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
            ).one()
            paid_subscription.current_period_end_at = (
                paid_subscription.current_period_start_at + timedelta(days=1)
            )
            dao.db.session.commit()

        topup_checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        topup_order_bid = topup_checkout["data"]["bill_order_bid"]
        topup_sync = client.post(
            f"/api/billing/orders/{topup_order_bid}/sync"
        ).get_json(force=True)
        overview = client.get("/api/billing/overview").get_json(force=True)

        assert paid_sync["code"] == 0
        assert topup_sync["code"] == 0
        assert overview["code"] == 0

        with app.app_context():
            paid_subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
            ).one()
            subscription_buckets = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            ).all()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=topup_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=topup_order_bid,
            ).one()

            assert paid_subscription.current_period_end_at is not None
            assert (
                BillingSubscription.query.filter_by(creator_bid="creator-1").count()
                == 1
            )
            assert len(subscription_buckets) == 1
            assert subscription_buckets[0].source_bid == paid_order_bid
            assert subscription_buckets[0].available_credits == Decimal(
                "105.0000000000"
            )
            assert bucket.effective_to == paid_subscription.current_period_end_at
            assert ledger.expires_at == paid_subscription.current_period_end_at

        assert (
            overview["data"]["subscription"]["subscription_bid"]
            == paid_subscription.subscription_bid
        )
        assert (
            overview["data"]["subscription"]["product_bid"]
            == "bill-product-plan-monthly"
        )

    def test_trial_then_topup_then_paid_realigns_existing_topup_expiry(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        seed_creator_user(app, creator_bid="creator-1")
        add_trial_subscription_state(
            app,
            subscription_bid="sub-trial-topup-then-paid",
            bill_order_bid="bill-trial-topup-then-paid",
            wallet_bid="wallet-trial-topup-then-paid",
            wallet_bucket_bid="bucket-trial-topup-then-paid",
            ledger_bid="ledger-trial-topup-then-paid",
        )
        with app.app_context():
            trial_subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-trial-topup-then-paid"
            ).one()
            trial_end = trial_subscription.current_period_end_at

        topup_checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        topup_order_bid = topup_checkout["data"]["bill_order_bid"]
        topup_sync = client.post(
            f"/api/billing/orders/{topup_order_bid}/sync"
        ).get_json(force=True)

        assert topup_sync["code"] == 0

        with app.app_context():
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=topup_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=topup_order_bid,
            ).one()
            assert bucket.effective_to == trial_end
            assert ledger.expires_at == trial_end

        paid_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)
        paid_order_bid = paid_checkout["data"]["bill_order_bid"]
        paid_sync = client.post(f"/api/billing/orders/{paid_order_bid}/sync").get_json(
            force=True
        )

        assert paid_sync["code"] == 0

        with app.app_context():
            paid_subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
            ).one()
            subscription_buckets = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            ).all()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=topup_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=topup_order_bid,
            ).one()

            assert paid_subscription.current_period_end_at is not None
            assert (
                BillingSubscription.query.filter_by(creator_bid="creator-1").count()
                == 1
            )
            assert len(subscription_buckets) == 1
            assert subscription_buckets[0].source_bid == paid_order_bid
            assert subscription_buckets[0].available_credits == Decimal(
                "105.0000000000"
            )
            assert bucket.effective_to == paid_subscription.current_period_end_at
            assert ledger.expires_at == paid_subscription.current_period_end_at
            assert bucket.effective_to != trial_end

    def test_topup_checkout_rejects_without_active_subscription(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)

        assert checkout["code"] != 0

    def test_repair_topup_grant_expiries_updates_only_misaligned_expiry_fields(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]
        now = now_utc()
        trial_end = now + timedelta(days=15)
        paid_end = now + timedelta(days=1)
        topup_paid_at = now + timedelta(minutes=5)

        with app.app_context():
            wallet = CreditWallet(
                wallet_bid="wallet-repair-1",
                creator_bid="creator-1",
                available_credits=Decimal("20.0000000000"),
                reserved_credits=Decimal("0"),
                lifetime_granted_credits=Decimal("20.0000000000"),
                lifetime_consumed_credits=Decimal("0"),
                last_settled_usage_id=0,
                version=0,
                created_at=now,
                updated_at=now,
            )
            dao.db.session.add(wallet)
            dao.db.session.add_all(
                [
                    BillingSubscription(
                        subscription_bid="sub-trial-repair",
                        creator_bid="creator-1",
                        product_bid=BILLING_TRIAL_PRODUCT_BID,
                        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                        billing_provider="manual",
                        provider_subscription_id="",
                        provider_customer_id="",
                        current_period_start_at=now,
                        current_period_end_at=trial_end,
                        cancel_at_period_end=0,
                        next_product_bid="",
                        metadata_json={"trial": True},
                        created_at=now,
                        updated_at=now,
                    ),
                    BillingSubscription(
                        subscription_bid="sub-paid-repair",
                        creator_bid="creator-1",
                        product_bid="bill-product-plan-monthly",
                        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                        billing_provider="stripe",
                        provider_subscription_id="sub_provider_repair",
                        provider_customer_id="cus_provider_repair",
                        current_period_start_at=now,
                        current_period_end_at=paid_end,
                        cancel_at_period_end=0,
                        next_product_bid="",
                        metadata_json={},
                        created_at=now,
                        updated_at=now,
                    ),
                    BillingOrder(
                        bill_order_bid="bill-topup-repair-1",
                        creator_bid="creator-1",
                        order_type=BILLING_ORDER_TYPE_TOPUP,
                        product_bid="bill-product-topup-small",
                        subscription_bid="",
                        currency="CNY",
                        payable_amount=5000,
                        paid_amount=5000,
                        payment_provider="pingxx",
                        channel="alipay_qr",
                        provider_reference_id="ch_topup_repair_1",
                        status=BILLING_ORDER_STATUS_PAID,
                        paid_at=topup_paid_at,
                        metadata_json={"checkout_type": "topup"},
                        created_at=topup_paid_at,
                        updated_at=topup_paid_at,
                    ),
                    CreditWalletBucket(
                        wallet_bucket_bid="bucket-topup-repair-1",
                        wallet_bid="wallet-repair-1",
                        creator_bid="creator-1",
                        bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                        source_type=CREDIT_SOURCE_TYPE_TOPUP,
                        source_bid="bill-topup-repair-1",
                        priority=30,
                        original_credits=Decimal("20.0000000000"),
                        available_credits=Decimal("20.0000000000"),
                        reserved_credits=Decimal("0"),
                        consumed_credits=Decimal("0"),
                        expired_credits=Decimal("0"),
                        effective_from=topup_paid_at,
                        effective_to=trial_end,
                        status=CREDIT_BUCKET_STATUS_ACTIVE,
                        metadata_json={"bill_order_bid": "bill-topup-repair-1"},
                        created_at=topup_paid_at,
                        updated_at=topup_paid_at,
                    ),
                    CreditLedgerEntry(
                        ledger_bid="ledger-topup-repair-1",
                        creator_bid="creator-1",
                        wallet_bid="wallet-repair-1",
                        wallet_bucket_bid="bucket-topup-repair-1",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                        source_type=CREDIT_SOURCE_TYPE_TOPUP,
                        source_bid="bill-topup-repair-1",
                        idempotency_key="grant:bill-topup-repair-1",
                        amount=Decimal("20.0000000000"),
                        balance_after=Decimal("20.0000000000"),
                        expires_at=trial_end,
                        consumable_from=topup_paid_at,
                        metadata_json={"bill_order_bid": "bill-topup-repair-1"},
                        created_at=topup_paid_at,
                        updated_at=topup_paid_at,
                    ),
                ]
            )
            dao.db.session.commit()

            result = repair_topup_grant_expiries(app, creator_bid="creator-1")

            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-topup-repair-1"
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                ledger_bid="ledger-topup-repair-1"
            ).one()

            assert result.status == "repaired"
            assert result.inspected_bucket_count == 1
            assert result.repaired_bucket_count == 1
            assert result.repaired_ledger_count == 1
            assert result.skipped_bucket_bids == []
            assert bucket.effective_to == paid_end
            assert ledger.expires_at == paid_end
            assert wallet.available_credits == Decimal("20.0000000000")
            assert wallet.reserved_credits == Decimal("0E-10")
            assert wallet.version == 0

    def test_topup_checkout_uses_pingxx_default_channel_when_provider_omitted(
        self, billing_write_client, monkeypatch
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        add_active_subscription(app, subscription_bid="sub-topup-default-provider-1")

        def fake_get_config(key, default=None) -> object:
            if key == "PAYMENT_CHANNELS_ENABLED":
                return "pingxx"
            return default

        monkeypatch.setattr(
            "flaskr.service.order.payment_channel_resolution.get_config",
            fake_get_config,
        )

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
            },
        ).get_json(force=True)

        assert checkout["code"] == 0
        assert checkout["data"]["provider"] == "pingxx"
        assert checkout["data"]["status"] == "pending"
        assert checkout["data"]["payment_payload"]["credential"]["alipay_qr"] == (
            "https://pingxx.test/qr"
        )
        assert billing_write_client["pingxx_requests"][0]["channel"] == "alipay_qr"

    def test_topup_sync_rebuilds_wallet_snapshot_from_bucket_balances(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        add_active_subscription(app, subscription_bid="sub-topup-rebuild-1")

        with app.app_context():
            existing_free_credit_created_at = now_utc()
            dao.db.session.add(
                CreditWallet(
                    wallet_bid="wallet-creator-1",
                    creator_bid="creator-1",
                    available_credits=Decimal("999.0000000000"),
                    reserved_credits=Decimal("0"),
                    lifetime_granted_credits=Decimal("100.0000000000"),
                    lifetime_consumed_credits=Decimal("0"),
                    last_settled_usage_id=0,
                    version=0,
                    created_at=existing_free_credit_created_at,
                    updated_at=existing_free_credit_created_at,
                )
            )
            dao.db.session.add(
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-existing-free",
                    wallet_bid="wallet-creator-1",
                    creator_bid="creator-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
                    source_type=CREDIT_SOURCE_TYPE_GIFT,
                    source_bid="gift-existing",
                    priority=10,
                    original_credits=Decimal("100.0000000000"),
                    available_credits=Decimal("100.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=existing_free_credit_created_at,
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                    created_at=existing_free_credit_created_at,
                    updated_at=existing_free_credit_created_at,
                )
            )
            dao.db.session.commit()

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            new_bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            raw_order = StripeOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid=bill_order_bid,
            ).one()
            assert wallet.available_credits == Decimal("120.0000000000")
            assert wallet.reserved_credits == Decimal("0E-10")
            assert new_bucket.bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP
            assert new_bucket.source_type == CREDIT_SOURCE_TYPE_TOPUP
            assert new_bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
            assert raw_order.status == 1
            assert raw_order.checkout_session_id == "cs_billing_test"
            assert raw_order.payment_intent_id == "pi_billing_test"
