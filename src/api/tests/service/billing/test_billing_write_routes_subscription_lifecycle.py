from __future__ import annotations

import pytest
from tests.service.billing import (
    billing_write_routes_test_helpers as write_route_helpers,
)
from tests.service.billing.billing_write_routes_test_helpers import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_TRIAL_PRODUCT_BID,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXPIRED,
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
    PingxxOrder,
    StripeOrder,
    apply_billing_subscription_provider_update,
    billing_subscriptions_module,
    calculate_self_managed_billing_cycle_end,
    dao,
    datetime,
    grant_paid_order_credits,
    normalize_mysql_datetime,
    now_utc,
    sync_subscription_lifecycle_events,
    timedelta,
    to_utc_iso,
)


@pytest.fixture
def billing_write_client(monkeypatch):
    yield from write_route_helpers.billing_write_client(monkeypatch)


class TestBillingWriteRoutesSubscriptionLifecycle:
    def test_pingxx_subscription_checkout_and_sync_grant_initial_credits(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
            },
            headers={"X-Language": "zh-CN"},
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        assert checkout["code"] == 0
        assert checkout["data"]["provider"] == "pingxx"
        assert checkout["data"]["status"] == "pending"
        assert checkout["data"]["payment_mode"] == "subscription"
        assert checkout["data"]["payment_payload"]["credential"]["alipay_qr"] == (
            "https://pingxx.test/qr"
        )
        assert billing_write_client["pingxx_requests"][0]["subject"] == "月套餐·轻量版"
        assert billing_write_client["pingxx_requests"][0]["body"] == "月套餐·轻量版"

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).one()
            raw_order = PingxxOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid=bill_order_bid,
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PENDING
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_DRAFT
            assert subscription.billing_provider == "pingxx"
            assert subscription.provider_subscription_id == ""
            assert raw_order.status == 0
            assert raw_order.order_bid == ""
            assert raw_order.creator_bid == "creator-1"

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).one()
            product = BillingProduct.query.filter_by(
                product_bid=order.product_bid
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            raw_order = PingxxOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid=bill_order_bid,
            ).one()
            renewal_event = BillingRenewalEvent.query.filter_by(
                subscription_bid=subscription.subscription_bid,
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            ).one()
            expire_event = BillingRenewalEvent.query.filter_by(
                subscription_bid=subscription.subscription_bid,
                event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.provider_subscription_id == ""
            assert wallet.available_credits == 5
            assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
            assert bucket.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION
            assert subscription.current_period_start_at == order.paid_at
            assert bucket.effective_from == order.paid_at
            expected_period_end_at = calculate_self_managed_billing_cycle_end(
                product,
                cycle_start_at=order.paid_at,
            )
            assert subscription.current_period_end_at == expected_period_end_at
            assert bucket.effective_to == subscription.current_period_end_at
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            assert ledger.expires_at == subscription.current_period_end_at
            assert raw_order.status == 1
            assert raw_order.charge_id == "ch_billing_test"
            assert (
                PingxxOrder.query.filter_by(
                    biz_domain="billing",
                    bill_order_bid=bill_order_bid,
                ).count()
                == 1
            )
            assert renewal_event.scheduled_at == (
                subscription.current_period_end_at - timedelta(days=7)
            )
            assert expire_event.scheduled_at == subscription.current_period_end_at

    def test_pending_pingxx_subscription_order_can_refresh_checkout(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
            },
            headers={"X-Language": "zh-CN"},
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        refreshed = client.post(
            f"/api/billing/orders/{bill_order_bid}/checkout",
            headers={"X-Language": "zh-CN"},
        ).get_json(force=True)

        assert refreshed["code"] == 0
        assert refreshed["data"]["provider"] == "pingxx"
        assert refreshed["data"]["payment_mode"] == "subscription"
        assert refreshed["data"]["status"] == "pending"
        assert refreshed["data"]["payment_payload"]["credential"]["alipay_qr"] == (
            "https://pingxx.test/qr"
        )
        assert len(billing_write_client["pingxx_requests"]) == 2
        assert billing_write_client["pingxx_requests"][1]["order_bid"] == bill_order_bid
        assert billing_write_client["pingxx_requests"][1]["subject"] == "月套餐·轻量版"
        assert billing_write_client["pingxx_requests"][1]["body"] == "月套餐·轻量版"

    def test_subscription_checkout_reuses_same_pending_stripe_order_within_timeout(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        first_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)
        second_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)

        assert first_checkout["code"] == 0
        assert second_checkout["code"] == 0
        assert (
            second_checkout["data"]["bill_order_bid"]
            == first_checkout["data"]["bill_order_bid"]
        )
        assert second_checkout["data"]["reused_existing_order"] is True
        assert second_checkout["data"]["redirect_url"] == "https://stripe.test/checkout"
        assert len(billing_write_client["stripe_requests"]) == 1

        with app.app_context():
            orders = BillingOrder.query.filter_by(creator_bid="creator-1").all()
            assert len(orders) == 1
            assert orders[0].status == BILLING_ORDER_STATUS_PENDING
            assert orders[0].expires_at is not None

    def test_subscription_checkout_cancels_pending_order_when_switching_package(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        first_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)
        second_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly-pro",
                "payment_provider": "stripe",
                "action": "upgrade_immediate",
            },
        ).get_json(force=True)

        assert first_checkout["code"] == 0
        assert second_checkout["code"] == 0
        assert (
            second_checkout["data"]["bill_order_bid"]
            != first_checkout["data"]["bill_order_bid"]
        )

        with app.app_context():
            old_order = BillingOrder.query.filter_by(
                bill_order_bid=first_checkout["data"]["bill_order_bid"]
            ).one()
            new_order = BillingOrder.query.filter_by(
                bill_order_bid=second_checkout["data"]["bill_order_bid"]
            ).one()
            assert old_order.status == BILLING_ORDER_STATUS_CANCELED
            assert old_order.failure_code == "replaced_by_new_package"
            assert old_order.metadata_json["replaced_by_bill_order_bid"] == (
                new_order.bill_order_bid
            )
            assert new_order.status == BILLING_ORDER_STATUS_PENDING

    def test_expired_pending_order_is_timed_out_and_recreated_on_same_package_checkout(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        first_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)

        with app.app_context():
            old_order = BillingOrder.query.filter_by(
                bill_order_bid=first_checkout["data"]["bill_order_bid"]
            ).one()
            old_order.expires_at = now_utc() - timedelta(minutes=1)
            dao.db.session.add(old_order)
            dao.db.session.commit()

        second_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)

        assert second_checkout["code"] == 0
        assert (
            second_checkout["data"]["bill_order_bid"]
            != first_checkout["data"]["bill_order_bid"]
        )
        assert second_checkout["data"]["reused_existing_order"] is False

        with app.app_context():
            old_order = BillingOrder.query.filter_by(
                bill_order_bid=first_checkout["data"]["bill_order_bid"]
            ).one()
            assert old_order.status == BILLING_ORDER_STATUS_TIMEOUT
            assert old_order.failure_code == "timeout"

    def test_legacy_pending_order_without_expires_at_is_reused_within_timeout(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        first_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)

        with app.app_context():
            order = BillingOrder.query.filter_by(
                bill_order_bid=first_checkout["data"]["bill_order_bid"]
            ).one()
            order.expires_at = None
            order.created_at = now_utc() - timedelta(minutes=10)
            dao.db.session.add(order)
            dao.db.session.commit()

        second_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)

        assert second_checkout["code"] == 0
        assert (
            second_checkout["data"]["bill_order_bid"]
            == first_checkout["data"]["bill_order_bid"]
        )
        assert second_checkout["data"]["reused_existing_order"] is True

        with app.app_context():
            order = BillingOrder.query.filter_by(
                bill_order_bid=first_checkout["data"]["bill_order_bid"]
            ).one()
            assert order.expires_at is not None

    def test_legacy_pending_order_without_expires_at_times_out_and_recreates(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        first_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)

        with app.app_context():
            old_order = BillingOrder.query.filter_by(
                bill_order_bid=first_checkout["data"]["bill_order_bid"]
            ).one()
            old_order.expires_at = None
            old_order.created_at = now_utc() - timedelta(minutes=31)
            dao.db.session.add(old_order)
            dao.db.session.commit()

        second_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)

        assert second_checkout["code"] == 0
        assert (
            second_checkout["data"]["bill_order_bid"]
            != first_checkout["data"]["bill_order_bid"]
        )

        with app.app_context():
            old_order = BillingOrder.query.filter_by(
                bill_order_bid=first_checkout["data"]["bill_order_bid"]
            ).one()
            assert old_order.status == BILLING_ORDER_STATUS_TIMEOUT
            assert old_order.failure_code == "timeout"

    def test_pending_subscription_checkout_route_marks_expired_order_timeout(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
            },
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            order.expires_at = now_utc() - timedelta(minutes=1)
            dao.db.session.add(order)
            dao.db.session.commit()

        refreshed = client.post(
            f"/api/billing/orders/{bill_order_bid}/checkout",
        ).get_json(force=True)

        assert refreshed["code"] == ERROR_CODE["server.order.orderPayExpired"]

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            assert order.status == BILLING_ORDER_STATUS_TIMEOUT

    def test_pingxx_wechat_subscription_checkout_aligns_legacy_charge_extra(
        self, billing_write_client, monkeypatch
    ) -> None:
        client = billing_write_client["client"]

        def fake_get_config(key, default=None):
            if key == "PINGXX_APP_ID":
                return "app_billing_test"
            return default

        monkeypatch.setattr(
            "flaskr.service.billing.checkout.get_config",
            fake_get_config,
        )

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
                "channel": "wx_pub_qr",
            },
        ).get_json(force=True)

        assert checkout["code"] == 0
        request = billing_write_client["pingxx_requests"][0]
        assert request["channel"] == "wx_pub_qr"
        assert request["extra"]["app_id"] == "app_billing_test"
        assert request["extra"]["charge_extra"] == {
            "product_id": "bill-product-plan-monthly"
        }

    def test_subscription_checkout_and_sync_grant_initial_credits(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
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
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            raw_order = StripeOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid=bill_order_bid,
            ).one()
            renewal_event = BillingRenewalEvent.query.filter_by(
                subscription_bid=subscription.subscription_bid,
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.provider_subscription_id == "sub_provider_test"
            assert wallet.available_credits == 5
            assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
            assert bucket.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION
            assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
            assert bucket.available_credits == 5
            assert ledger.amount == 5
            assert raw_order.status == 1
            assert raw_order.checkout_session_id == "cs_billing_test"
            assert raw_order.payment_intent_id == "pi_billing_test"
            assert (
                StripeOrder.query.filter_by(
                    biz_domain="billing",
                    bill_order_bid=bill_order_bid,
                ).count()
                == 1
            )
            assert renewal_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
            assert renewal_event.scheduled_at == normalize_mysql_datetime(
                subscription.current_period_end_at
            )

    def test_cancel_and_resume_subscription_toggle_status(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-active",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="stripe",
                    provider_subscription_id="sub_provider_1",
                    provider_customer_id="cus_provider_1",
                    current_period_start_at=now - timedelta(days=1),
                    current_period_end_at=now + timedelta(days=29),
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={},
                    created_at=datetime(2026, 4, 8, 12, 0, 0),
                    updated_at=datetime(2026, 4, 8, 12, 0, 0),
                )
            )
            dao.db.session.commit()

        cancel_payload = client.post(
            "/api/billing/subscriptions/cancel",
            json={"subscription_bid": "sub-active"},
        ).get_json(force=True)
        assert cancel_payload["code"] == 0
        assert cancel_payload["data"]["status"] == "cancel_scheduled"
        assert cancel_payload["data"]["cancel_at_period_end"] is True

        with app.app_context():
            cancel_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-active",
                event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
            ).one()
            assert cancel_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING

        resume_payload = client.post(
            "/api/billing/subscriptions/resume",
            json={"subscription_bid": "sub-active"},
        ).get_json(force=True)
        assert resume_payload["code"] == 0
        assert resume_payload["data"]["status"] == "active"
        assert resume_payload["data"]["cancel_at_period_end"] is False

        with app.app_context():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-active"
            ).one()
            cancel_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-active",
                event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
            ).one()
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.cancel_at_period_end == 0
            assert subscription.metadata_json["provider"] == "stripe"
            assert (
                subscription.metadata_json["latest_event_type"] == "resume_subscription"
            )
            assert cancel_event.status == BILLING_RENEWAL_EVENT_STATUS_CANCELED

    def test_past_due_subscription_sets_grace_and_retry_event(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-past-due",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_retry",
                provider_customer_id="cus_provider_retry",
                current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
                current_period_end_at=datetime(2026, 5, 1, 0, 0, 0),
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=datetime(2026, 4, 1, 0, 0, 0),
                updated_at=datetime(2026, 4, 1, 0, 0, 0),
            )
            dao.db.session.add(subscription)
            dao.db.session.flush()
            sync_subscription_lifecycle_events(app, subscription)
            dao.db.session.commit()

            applied = apply_billing_subscription_provider_update(
                app,
                subscription,
                provider="stripe",
                event_type="customer.subscription.updated",
                payload={"created": 1775000000},
                data_object={
                    "id": "sub_provider_retry",
                    "status": "past_due",
                    "current_period_start": 1772000000,
                    "current_period_end": 1775003600,
                    "cancel_at_period_end": False,
                },
            )
            dao.db.session.commit()

            retry_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-past-due",
                event_type=BILLING_RENEWAL_EVENT_TYPE_RETRY,
            ).one()
            renewal_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-past-due",
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            ).one()
            assert applied is True
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE
            assert (
                subscription.grace_period_end_at == subscription.current_period_end_at
            )
            assert retry_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
            assert renewal_event.status == BILLING_RENEWAL_EVENT_STATUS_CANCELED

    def test_next_product_bid_schedules_downgrade_event(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-downgrade",
                creator_bid="creator-1",
                product_bid="bill-product-plan-yearly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_yearly",
                provider_customer_id="cus_provider_yearly",
                current_period_start_at=datetime(2026, 1, 1, 0, 0, 0),
                current_period_end_at=datetime(2027, 1, 1, 0, 0, 0),
                cancel_at_period_end=0,
                next_product_bid="bill-product-plan-monthly",
                metadata_json={},
                created_at=datetime(2026, 1, 1, 0, 0, 0),
                updated_at=datetime(2026, 1, 1, 0, 0, 0),
            )
            dao.db.session.add(subscription)
            dao.db.session.flush()
            sync_subscription_lifecycle_events(app, subscription)
            dao.db.session.commit()

            downgrade_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-downgrade",
                event_type=BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
            ).one()
            assert downgrade_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
            assert downgrade_event.scheduled_at == subscription.current_period_end_at

    def test_paid_upgrade_order_switches_subscription_product_and_reschedules(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]
        current_cycle_start = datetime(2026, 4, 1, 0, 0, 0)
        current_cycle_end = datetime(2026, 5, 1, 0, 0, 0)
        upgrade_paid_at = datetime(2026, 4, 8, 13, 0, 0)
        upgraded_cycle_end = datetime(2027, 4, 8, 13, 0, 0)

        with app.app_context():
            wallet = CreditWallet(
                wallet_bid="wallet-upgrade",
                creator_bid="creator-1",
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("0"),
                lifetime_granted_credits=Decimal("5.0000000000"),
                lifetime_consumed_credits=Decimal("2.0000000000"),
                last_settled_usage_id=0,
                version=0,
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            subscription = BillingSubscription(
                subscription_bid="sub-upgrade",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_upgrade",
                provider_customer_id="cus_provider_upgrade",
                current_period_start_at=current_cycle_start,
                current_period_end_at=current_cycle_end,
                cancel_at_period_end=0,
                next_product_bid="bill-product-plan-monthly",
                metadata_json={},
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            existing_bucket = CreditWalletBucket(
                wallet_bucket_bid="bucket-upgrade-existing",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-start-1",
                priority=20,
                original_credits=Decimal("5.0000000000"),
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("2.0000000000"),
                expired_credits=Decimal("0"),
                effective_from=current_cycle_start,
                effective_to=current_cycle_end,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "bill_order_bid": "bill-start-1",
                    "product_bid": "bill-product-plan-monthly",
                    "payment_provider": "stripe",
                },
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            existing_ledger = CreditLedgerEntry(
                ledger_bid="ledger-upgrade-existing",
                creator_bid="creator-1",
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid=existing_bucket.wallet_bucket_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-start-1",
                idempotency_key="grant:bill-start-1",
                amount=Decimal("5.0000000000"),
                balance_after=Decimal("5.0000000000"),
                expires_at=current_cycle_end,
                consumable_from=current_cycle_start,
                metadata_json={
                    "bill_order_bid": "bill-start-1",
                    "subscription_bid": "sub-upgrade",
                    "product_bid": "bill-product-plan-monthly",
                    "payment_provider": "stripe",
                    "grant_reason": "subscription",
                },
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            order = BillingOrder(
                bill_order_bid="billing-upgrade-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
                product_bid="bill-product-plan-yearly",
                subscription_bid="sub-upgrade",
                currency="CNY",
                payable_amount=99900,
                paid_amount=99900,
                payment_provider="stripe",
                channel="checkout_session",
                provider_reference_id="cs_upgrade_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=upgrade_paid_at,
                metadata_json={},
            )
            dao.db.session.add(wallet)
            dao.db.session.add(subscription)
            dao.db.session.add(existing_bucket)
            dao.db.session.add(existing_ledger)
            dao.db.session.add(order)
            dao.db.session.flush()

            granted = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            existing_bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-upgrade-existing"
            ).one()
            existing_ledger = CreditLedgerEntry.query.filter_by(
                ledger_bid="ledger-upgrade-existing"
            ).one()
            upgrade_ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid="billing-upgrade-1",
            ).one()
            subscription_buckets = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            ).all()
            upgrade_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-upgrade",
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            ).one()
            assert granted is True
            assert subscription.product_bid == "bill-product-plan-yearly"
            assert subscription.next_product_bid == ""
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.cancel_at_period_end == 0
            assert subscription.current_period_start_at == upgrade_paid_at
            assert subscription.current_period_end_at == upgraded_cycle_end
            assert wallet.available_credits == 10003
            assert len(subscription_buckets) == 1
            assert existing_bucket.source_bid == "billing-upgrade-1"
            assert existing_bucket.original_credits == 10005
            assert existing_bucket.available_credits == 10003
            assert existing_bucket.effective_from == upgrade_paid_at
            assert existing_bucket.effective_to == upgraded_cycle_end
            assert existing_ledger.expires_at == upgraded_cycle_end
            assert upgrade_ledger.wallet_bucket_bid == existing_bucket.wallet_bucket_bid
            assert upgrade_ledger.amount == 10000
            assert upgrade_ledger.expires_at == upgraded_cycle_end
            assert upgrade_ledger.consumable_from == upgrade_paid_at
            assert upgrade_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING

    def test_paid_renewal_order_applies_scheduled_next_product(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-renewal",
                creator_bid="creator-1",
                product_bid="bill-product-plan-yearly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_renewal",
                provider_customer_id="cus_provider_renewal",
                current_period_start_at=datetime(2026, 1, 1, 0, 0, 0),
                current_period_end_at=datetime(2027, 1, 1, 0, 0, 0),
                cancel_at_period_end=0,
                next_product_bid="bill-product-plan-monthly",
                metadata_json={},
                created_at=datetime(2026, 1, 1, 0, 0, 0),
                updated_at=datetime(2026, 1, 1, 0, 0, 0),
            )
            order = BillingOrder(
                bill_order_bid="bill-renewal-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                product_bid="bill-product-plan-monthly",
                subscription_bid="sub-renewal",
                currency="CNY",
                payable_amount=9900,
                paid_amount=9900,
                payment_provider="stripe",
                channel="checkout_session",
                provider_reference_id="cs_renewal_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=datetime(2027, 1, 1, 0, 0, 0),
                metadata_json={},
            )
            dao.db.session.add(subscription)
            dao.db.session.add(order)
            dao.db.session.flush()

            granted = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            renewal_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-renewal",
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            ).one()
            assert granted is True
            assert subscription.product_bid == "bill-product-plan-monthly"
            assert subscription.next_product_bid == ""
            assert renewal_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
            assert renewal_event.scheduled_at == subscription.current_period_end_at

    def test_paid_pingxx_renewal_before_cycle_start_keeps_current_period(
        self, billing_write_client, monkeypatch
    ) -> None:
        app = billing_write_client["app"]
        current_cycle_start = datetime(2026, 4, 1, 0, 0, 0)
        renewal_cycle_start = datetime(2026, 5, 1, 0, 0, 0)
        renewal_cycle_end = datetime(2026, 5, 30, 23, 59, 59)

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None) -> datetime:
                frozen_now = datetime(2026, 4, 24, 10, 0, 0)
                if tz is not None:
                    return frozen_now.replace(tzinfo=tz)
                return frozen_now

        monkeypatch.setattr(billing_subscriptions_module, "datetime", FrozenDateTime)
        monkeypatch.setattr(
            billing_subscriptions_module,
            "now_utc",
            lambda: datetime(2026, 4, 24, 10, 0, 0),
        )

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-pingxx-early-renewal",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=current_cycle_start,
                current_period_end_at=renewal_cycle_start,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            order = BillingOrder(
                bill_order_bid="bill-pingxx-renewal-early-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                product_bid="bill-product-plan-monthly",
                subscription_bid="sub-pingxx-early-renewal",
                currency="CNY",
                payable_amount=9900,
                paid_amount=9900,
                payment_provider="pingxx",
                channel="alipay_qr",
                provider_reference_id="ch_pingxx_renewal_early_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=datetime(2026, 4, 24, 9, 0, 0),
                metadata_json={
                    "provider_reference_type": "charge",
                    "renewal_cycle_start_at": to_utc_iso(renewal_cycle_start),
                    "renewal_cycle_end_at": to_utc_iso(renewal_cycle_end),
                },
            )
            wallet = CreditWallet(
                wallet_bid="wallet-pingxx-early-renewal",
                creator_bid="creator-1",
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("0"),
                lifetime_granted_credits=Decimal("3.0000000000"),
                lifetime_consumed_credits=Decimal("0"),
                last_settled_usage_id=0,
                version=0,
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            bucket = CreditWalletBucket(
                wallet_bucket_bid="bucket-pingxx-early-renewal",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-pingxx-start-early-1",
                priority=20,
                original_credits=Decimal("3.0000000000"),
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("0"),
                expired_credits=Decimal("0"),
                effective_from=current_cycle_start,
                effective_to=renewal_cycle_start,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "bill_order_bid": "bill-pingxx-start-early-1",
                    "subscription_bid": "sub-pingxx-early-renewal",
                    "product_bid": "bill-product-plan-monthly",
                    "payment_provider": "pingxx",
                },
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            dao.db.session.add(subscription)
            dao.db.session.add(wallet)
            dao.db.session.add(bucket)
            dao.db.session.add(order)
            dao.db.session.flush()

            granted = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-pingxx-early-renewal",
            ).one()
            grant_ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid="bill-pingxx-renewal-early-1",
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-pingxx-early-renewal"
            ).one()
            subscription_buckets = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            ).all()

            assert granted is True
            assert len(subscription_buckets) == 1
            assert bucket.source_bid == "bill-pingxx-renewal-early-1"
            assert bucket.available_credits == Decimal("3.0000000000")
            assert bucket.reserved_credits == Decimal("5.0000000000")
            assert bucket.effective_from == current_cycle_start
            assert bucket.effective_to == renewal_cycle_start
            assert wallet.available_credits == Decimal("3.0000000000")
            assert wallet.reserved_credits == Decimal("5.0000000000")
            assert grant_ledger.wallet_bucket_bid == bucket.wallet_bucket_bid
            assert grant_ledger.amount == Decimal("5.0000000000")
            assert grant_ledger.expires_at == renewal_cycle_end
            assert grant_ledger.consumable_from == renewal_cycle_start
            assert grant_ledger.metadata_json["bucket_credit_state"] == "reserved"
            assert subscription.current_period_start_at == current_cycle_start
            assert subscription.current_period_end_at == renewal_cycle_start
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE

    def test_paid_pingxx_renewal_after_cycle_end_shifts_cycle_from_payment_time(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]
        renewal_cycle_start = datetime(2026, 5, 1, 0, 0, 0)
        renewal_cycle_end = datetime(2026, 5, 30, 23, 59, 59)
        paid_at = datetime(2026, 6, 5, 10, 0, 0)

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-pingxx-late-renewal",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_EXPIRED,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
                current_period_end_at=renewal_cycle_start,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=datetime(2026, 4, 1, 0, 0, 0),
                updated_at=datetime(2026, 6, 1, 0, 0, 0),
            )
            order = BillingOrder(
                bill_order_bid="bill-pingxx-renewal-late-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                product_bid="bill-product-plan-monthly",
                subscription_bid="sub-pingxx-late-renewal",
                currency="CNY",
                payable_amount=9900,
                paid_amount=9900,
                payment_provider="pingxx",
                channel="alipay_qr",
                provider_reference_id="ch_pingxx_renewal_late_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=paid_at,
                metadata_json={
                    "provider_reference_type": "charge",
                    "renewal_cycle_start_at": to_utc_iso(renewal_cycle_start),
                    "renewal_cycle_end_at": to_utc_iso(renewal_cycle_end),
                },
            )
            dao.db.session.add(subscription)
            dao.db.session.add(order)
            dao.db.session.flush()

            granted = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid="bill-pingxx-renewal-late-1",
            ).one()
            order = BillingOrder.query.filter_by(
                bill_order_bid="bill-pingxx-renewal-late-1"
            ).one()
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-pingxx-late-renewal"
            ).one()

            assert granted is True
            assert bucket.effective_from == paid_at
            assert bucket.effective_to == datetime(2026, 7, 4, 15, 59, 59)
            assert order.metadata_json["applied_cycle_start_at"] == paid_at.isoformat()
            assert (
                order.metadata_json["applied_cycle_end_at"]
                == datetime(2026, 7, 4, 15, 59, 59).isoformat()
            )
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.current_period_start_at == paid_at
            assert subscription.current_period_end_at == datetime(
                2026, 7, 4, 15, 59, 59
            )

    def test_existing_subscription_grant_realigns_future_dated_cycle_on_replay(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]
        paid_at = datetime(2026, 4, 15, 13, 10, 37)
        corrupted_start_at = datetime(2026, 4, 17, 14, 31, 53)
        corrupted_end_at = datetime(2026, 4, 18, 14, 31, 53)

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-pingxx-start-repair-1",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_DRAFT,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=None,
                current_period_end_at=None,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=paid_at,
                updated_at=paid_at,
            )
            order = BillingOrder(
                bill_order_bid="bill-pingxx-start-repair-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                product_bid="bill-product-plan-monthly",
                subscription_bid="sub-pingxx-start-repair-1",
                currency="CNY",
                payable_amount=990,
                paid_amount=990,
                payment_provider="pingxx",
                channel="alipay_qr",
                provider_reference_id="ch_pingxx_start_repair_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=paid_at,
                metadata_json={},
            )
            dao.db.session.add(subscription)
            dao.db.session.add(order)
            dao.db.session.flush()

            initial_grant = grant_paid_order_credits(app, order)
            subscription.current_period_start_at = corrupted_start_at
            subscription.current_period_end_at = corrupted_end_at
            subscription.updated_at = corrupted_start_at
            dao.db.session.add(subscription)
            dao.db.session.commit()

            replay_grant = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            product = BillingProduct.query.filter_by(
                product_bid="bill-product-plan-monthly"
            ).one()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid="bill-pingxx-start-repair-1",
            ).one()
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-pingxx-start-repair-1"
            ).one()

            assert initial_grant is True
            assert replay_grant is False
            assert bucket.effective_from == paid_at
            assert bucket.effective_to == calculate_self_managed_billing_cycle_end(
                product,
                cycle_start_at=paid_at,
            )
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.current_period_start_at == bucket.effective_from
            assert subscription.current_period_end_at == bucket.effective_to

    def test_paid_subscription_start_reactivates_reused_expired_bucket(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]
        paid_at = datetime(2026, 6, 11, 14, 11, 8)
        expired_at = datetime(2026, 5, 5, 19, 22, 1)

        with app.app_context():
            product = BillingProduct.query.filter_by(
                product_bid="bill-product-plan-monthly"
            ).one()
            wallet = CreditWallet(
                wallet_bid="wallet-reactivate-expired",
                creator_bid="creator-1",
                available_credits=Decimal("0"),
                reserved_credits=Decimal("0"),
                lifetime_granted_credits=Decimal("1000.0000000000"),
                lifetime_consumed_credits=Decimal("9.8500000000"),
                last_settled_usage_id=0,
                version=0,
                created_at=expired_at,
                updated_at=expired_at,
            )
            subscription = BillingSubscription(
                subscription_bid="sub-reactivate-expired",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_DRAFT,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=None,
                current_period_end_at=None,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=paid_at,
                updated_at=paid_at,
            )
            expired_bucket = CreditWalletBucket(
                wallet_bucket_bid="bucket-reactivate-expired",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-trial-expired-1",
                priority=20,
                original_credits=Decimal("1000.0000000000"),
                available_credits=Decimal("0"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("9.8500000000"),
                expired_credits=Decimal("990.1500000000"),
                effective_from=datetime(2026, 4, 20, 19, 22, 1),
                effective_to=expired_at,
                status=CREDIT_BUCKET_STATUS_EXPIRED,
                metadata_json={
                    "bill_order_bid": "bill-trial-expired-1",
                    "subscription_bid": "sub-trial-expired",
                    "product_bid": BILLING_TRIAL_PRODUCT_BID,
                    "payment_provider": "manual",
                },
                created_at=datetime(2026, 4, 20, 19, 22, 1),
                updated_at=expired_at,
            )
            order = BillingOrder(
                bill_order_bid="bill-reactivate-expired-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                product_bid="bill-product-plan-monthly",
                subscription_bid="sub-reactivate-expired",
                currency="CNY",
                payable_amount=990,
                paid_amount=990,
                payment_provider="pingxx",
                channel="wx_pub_qr",
                provider_reference_id="ch_reactivate_expired_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=paid_at,
                metadata_json={},
            )
            dao.db.session.add(wallet)
            dao.db.session.add(subscription)
            dao.db.session.add(expired_bucket)
            dao.db.session.add(order)
            dao.db.session.flush()

            granted = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-reactivate-expired"
            ).one()
            grant_entry = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid="bill-reactivate-expired-1",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            ).one()
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-reactivate-expired"
            ).one()

            assert granted is True
            assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
            assert bucket.source_bid == "bill-reactivate-expired-1"
            assert bucket.available_credits == Decimal("5.0000000000")
            assert bucket.effective_from == paid_at
            assert bucket.effective_to == calculate_self_managed_billing_cycle_end(
                product,
                cycle_start_at=paid_at,
            )
            assert wallet.available_credits == Decimal("5.0000000000")
            assert grant_entry.wallet_bucket_bid == bucket.wallet_bucket_bid
            assert grant_entry.amount == Decimal("5.0000000000")
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE

    def test_paid_subscription_replay_repairs_existing_expired_bucket_status(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]
        paid_at = datetime(2026, 6, 11, 14, 11, 8)
        expired_at = datetime(2026, 5, 5, 19, 22, 1)

        with app.app_context():
            product = BillingProduct.query.filter_by(
                product_bid="bill-product-plan-monthly"
            ).one()
            cycle_end = calculate_self_managed_billing_cycle_end(
                product,
                cycle_start_at=paid_at,
            )
            wallet = CreditWallet(
                wallet_bid="wallet-repair-existing-expired",
                creator_bid="creator-1",
                available_credits=Decimal("50.0000000000"),
                reserved_credits=Decimal("0"),
                lifetime_granted_credits=Decimal("1050.0000000000"),
                lifetime_consumed_credits=Decimal("9.8500000000"),
                last_settled_usage_id=0,
                version=0,
                created_at=expired_at,
                updated_at=paid_at,
            )
            subscription = BillingSubscription(
                subscription_bid="sub-repair-existing-expired",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_DRAFT,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=None,
                current_period_end_at=None,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=paid_at,
                updated_at=paid_at,
            )
            expired_bucket = CreditWalletBucket(
                wallet_bucket_bid="bucket-repair-existing-expired",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-repair-existing-expired-1",
                priority=20,
                original_credits=Decimal("1050.0000000000"),
                available_credits=Decimal("50.0000000000"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("9.8500000000"),
                expired_credits=Decimal("990.1500000000"),
                effective_from=paid_at,
                effective_to=cycle_end,
                status=CREDIT_BUCKET_STATUS_EXPIRED,
                metadata_json={
                    "bill_order_bid": "bill-repair-existing-expired-1",
                    "subscription_bid": "sub-repair-existing-expired",
                    "product_bid": "bill-product-plan-monthly",
                    "payment_provider": "pingxx",
                },
                created_at=datetime(2026, 4, 20, 19, 22, 1),
                updated_at=paid_at,
            )
            order = BillingOrder(
                bill_order_bid="bill-repair-existing-expired-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                product_bid="bill-product-plan-monthly",
                subscription_bid="sub-repair-existing-expired",
                currency="CNY",
                payable_amount=990,
                paid_amount=990,
                payment_provider="pingxx",
                channel="wx_pub_qr",
                provider_reference_id="ch_repair_existing_expired_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=paid_at,
                metadata_json={},
            )
            grant_entry = CreditLedgerEntry(
                ledger_bid="ledger-repair-existing-expired",
                creator_bid="creator-1",
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid=expired_bucket.wallet_bucket_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid=order.bill_order_bid,
                idempotency_key=f"grant:{order.bill_order_bid}",
                amount=Decimal("50.0000000000"),
                balance_after=Decimal("50.0000000000"),
                expires_at=cycle_end,
                consumable_from=paid_at,
                metadata_json={
                    "bill_order_bid": order.bill_order_bid,
                    "subscription_bid": subscription.subscription_bid,
                    "product_bid": order.product_bid,
                    "payment_provider": "pingxx",
                    "grant_reason": "subscription",
                    "bucket_credit_state": "available",
                },
            )
            dao.db.session.add(wallet)
            dao.db.session.add(subscription)
            dao.db.session.add(expired_bucket)
            dao.db.session.add(order)
            dao.db.session.add(grant_entry)
            dao.db.session.flush()

            granted = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-repair-existing-expired"
            ).one()
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-repair-existing-expired"
            ).one()

            assert granted is False
            assert (
                CreditLedgerEntry.query.filter_by(
                    creator_bid="creator-1",
                    source_bid="bill-repair-existing-expired-1",
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                ).count()
                == 1
            )
            assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
            assert bucket.available_credits == Decimal("50.0000000000")
            assert bucket.effective_from == paid_at
            assert bucket.effective_to == cycle_end
            assert wallet.available_credits == Decimal("50.0000000000")
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.current_period_end_at == cycle_end
