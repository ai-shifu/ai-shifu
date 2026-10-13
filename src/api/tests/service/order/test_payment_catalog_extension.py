"""Exercise catalog, discounts and hosted checkout without Stripe business branches."""

import hashlib
import hmac
import json
from dataclasses import replace
from datetime import UTC, timedelta
from decimal import Decimal
from typing import ClassVar

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import (
    campaign_discount_providers,
    campaign_provider_discounts,
    campaigns,
    provider_catalog,
    provider_catalog_sync,
    provider_price_mappings,
)
from flaskr.service.billing.campaign_discount_providers import (
    register_discount_provider,
)
from flaskr.service.billing.checkout import refund_billing_order, sync_billing_order
from flaskr.service.billing.consts import (
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PROVIDER_PRICE_STATUS_INVALID,
)
from flaskr.service.billing.models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
)
from flaskr.service.billing.provider_catalog import (
    ProviderAccountSnapshot,
    ProviderCatalogSnapshot,
    ProviderPriceSnapshot,
    ProviderProductSnapshot,
)
from flaskr.service.billing.provider_catalog_sync import (
    CatalogChange,
    apply_catalog_change,
    reconcile_provider_catalog,
)
from flaskr.service.billing.subscriptions import ensure_subscription_renewal_order
from flaskr.service.config import config_overrides
from flaskr.service.order import payment_providers, raw_snapshots
from flaskr.service.order.payment_providers.base import (
    PaymentNotificationResult,
    PaymentRefundRequest,
    PaymentRefundResult,
)
from flaskr.service.order.payment_providers.contracts import CheckoutTerms
from flaskr.util.datetime import now_utc
from sqlalchemy import MetaData

from tests.service.billing.test_campaign_provider_discounts import (
    _FakeCampaignDiscountProvider,
)
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    HostedFixtureProvider,
    HostedFixtureSnapshot,
    integration_app,
)

__all__ = ["integration_app"]

_table = HostedFixtureSnapshot.__table__.to_metadata(
    MetaData(), name="test_catalog_contract_snapshots"
)
for _index in _table.indexes:
    _index.name = "catalog_" + str(_index.name)


class CatalogSnapshot(dao.db.Model):
    __table__ = _table


class CatalogHostedProvider(HostedFixtureProvider):
    channel = "fixture-catalog"
    definition = replace(
        HostedFixtureProvider.definition,
        capabilities=replace(
            HostedFixtureProvider.definition.capabilities,
            catalog=True,
            discounts=True,
            refund=True,
        ),
    )
    checkout_terms: ClassVar[list[CheckoutTerms]] = []

    @classmethod
    def checkout_options(cls, terms: CheckoutTerms) -> dict:
        cls.checkout_terms.append(terms)
        return {
            "metadata": terms.metadata,
            "offer": terms.price_reference,
            "promotion": terms.discount_reference,
        }

    def _notification(self, payload: dict) -> PaymentNotificationResult:
        if payload.get("event") == "offer.retired":
            return PaymentNotificationResult(
                order_bid="", status="offer.retired", provider_payload=payload
            )
        agreement = payload.get("agreement")
        if agreement:
            payload = {
                **payload,
                "contract": {
                    "provider_reference": agreement["reference"],
                    "customer_reference": "customer-omega",
                    "status": {"live": "active", "ended": "canceled"}[
                        agreement["phase"]
                    ],
                    "period_start": agreement["since"],
                    "period_end": agreement["until"],
                },
            }
        return super()._notification(payload)

    def refund_payment(
        self, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult:
        del app
        assert request.metadata["provider_reference"] == request.order_bid
        return PaymentRefundResult(
            "refund-omega", {"decision": "accepted"}, "succeeded"
        )


class CatalogReader:
    def retrieve_account_snapshot(self, app: Flask) -> ProviderAccountSnapshot:
        del app
        return ProviderAccountSnapshot("fixture-catalog", "acct_test", livemode=False)

    def retrieve_mapping_snapshot(
        self, app: Flask, *, provider_product_id: str, provider_price_id: str
    ) -> ProviderCatalogSnapshot:
        return ProviderCatalogSnapshot(
            self.retrieve_account_snapshot(app),
            ProviderProductSnapshot(
                "fixture-catalog", provider_product_id, active=True, livemode=False
            ),
            ProviderPriceSnapshot(
                "fixture-catalog",
                provider_price_id,
                provider_product_id,
                active=True,
                livemode=False,
                currency="cny",
                unit_amount=990,
                price_type="recurring",
                recurring_interval="month",
                recurring_interval_count=1,
                recurring_usage_type="licensed",
            ),
        )

    def list_product_snapshots(self, app: Flask) -> list[ProviderProductSnapshot]:
        return [
            self.retrieve_mapping_snapshot(
                app,
                provider_product_id="catalog-product",
                provider_price_id="catalog-offer",
            ).product
        ]

    def list_price_snapshots(self, app: Flask) -> list[ProviderPriceSnapshot]:
        return [
            self.retrieve_mapping_snapshot(
                app,
                provider_product_id="catalog-product",
                provider_price_id="catalog-offer",
            ).price
        ]


@pytest.mark.parametrize("discount_percent", [Decimal(50), Decimal(100)])
def test_catalog_and_discount_extension_preserves_full_contract_checkout(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    discount_percent: Decimal,
) -> None:
    """A mapped recurring price and first-cycle discount must reach the new adapter."""
    app = integration_app
    monkeypatch.setattr(
        provider_catalog, "_CATALOG_READERS", dict(provider_catalog._CATALOG_READERS)
    )
    monkeypatch.setattr(
        campaign_discount_providers,
        "_DISCOUNT_PROVIDERS",
        dict(campaign_discount_providers._DISCOUNT_PROVIDERS),
    )
    payment_providers.register_payment_provider(CatalogHostedProvider)
    raw_snapshots.register_native_snapshot_model(
        "fixture-catalog", CatalogSnapshot, "alipay_order_bid"
    )
    provider_catalog.register_catalog_reader("fixture-catalog", CatalogReader)
    discounts = _FakeCampaignDiscountProvider()
    register_discount_provider("fixture-catalog", lambda: discounts)
    monkeypatch.setattr(provider_catalog_sync, "_CATALOG_NOTIFICATION_READERS", {})
    CatalogHostedProvider.checkout_terms.clear()
    CatalogSnapshot.__table__.create(dao.db.engine)
    try:
        with config_overrides(
            {
                "PAYMENT_CHANNELS_ENABLED": "fixture-catalog",
                "HOST_URL": "https://app.example.test",
            }
        ):
            with unit_of_work():
                mapping, _ = provider_price_mappings.upsert_provider_price_mapping(
                    product_bid="bill-product-plan-monthly",
                    provider="fixture-catalog",
                    provider_product_id="catalog-product",
                    provider_price_id="catalog-offer",
                    provider_account_id="acct_test",
                    livemode=False,
                )
                summary, _ = (
                    provider_price_mappings.validate_provider_price_mapping_row(mapping)
                )
                assert summary.valid, summary.errors
                provider_price_mappings.activate_provider_price_mapping(
                    mapping.provider_price_bid
                )
                now = now_utc()
                dao.db.session.add(
                    BillingCampaign(
                        campaign_bid="fixture-campaign",
                        name="Fixture",
                        benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
                        discount_type=BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
                        discount_percent=discount_percent,
                        enabled=1,
                        start_at=now - timedelta(days=1),
                        end_at=now + timedelta(days=1),
                        created_user_bid="operator",
                        updated_user_bid="operator",
                    )
                )
                dao.db.session.add(
                    BillingCampaignProduct(
                        campaign_bid="fixture-campaign",
                        product_bid="bill-product-plan-monthly",
                        product_type=BILLING_PRODUCT_TYPE_PLAN,
                        discount_type=BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
                        discount_percent=discount_percent,
                        campaign_price_amount=990
                        - int(Decimal(990) * discount_percent / 100),
                    )
                )
            published = (
                campaign_provider_discounts.publish_admin_campaign_provider_discounts(
                    app,
                    campaign_bid="fixture-campaign",
                    operator_user_bid="operator",
                    provider_name="fixture-catalog",
                )
            )
            assert campaigns._should_require_provider_discount_sync_for_benefit(
                BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT
            )
            campaign_provider_discounts.assert_campaign_provider_discounts_ready(
                app,
                campaign_bid="fixture-campaign",
                product_bids=["bill-product-plan-monthly"],
                provider="fixture-catalog",
            )
            assert len(published["items"]) == 1
            assert published["items"][0]["provider"] == "fixture-catalog"
            with app.test_client() as client:
                response = client.post(
                    "/api/billing/subscriptions/checkout",
                    json={
                        "product_bid": "bill-product-plan-monthly",
                        "payment_option": "fixture-catalog:fixture_checkout",
                    },
                ).get_json(force=True)
                assert response.get("code") == 0, response
                assert response["data"]["payment_action"]["type"] == "redirect"
                terms = CatalogHostedProvider.checkout_terms[-1]
                assert terms.price_reference == "catalog-offer"
                assert (
                    terms.discount_reference
                    == f"coupon_{discounts.created[0].campaign_provider_discount_bid}"
                )
                assert terms.amount == 990 - int(Decimal(990) * discount_percent / 100)
                assert terms.payment_mode == "subscription"
                assert "/payment/billing-result?bill_order_bid=" in terms.success_url
                assert "/stripe/" not in terms.success_url
                assert (
                    "subscription",
                    response["data"]["bill_order_bid"],
                ) in FixtureProvider.calls
                order = BillingOrder.query.filter_by(
                    bill_order_bid=response["data"]["bill_order_bid"]
                ).one()
                assert order.metadata_json["provider_price_id"] == "catalog-offer"
                assert order.payment_provider == "fixture-catalog"
                first_order_bid = order.bill_order_bid
                start = int(now_utc().replace(tzinfo=UTC).timestamp()) + 1
                end = start + 30 * 86400
                payload = {
                    **FixtureProvider.attempts[first_order_bid],
                    "state": "paid",
                    "agreement": {
                        "reference": "agreement-omega",
                        "phase": "live",
                        "since": start,
                        "until": end,
                    },
                }
                body = json.dumps(payload).encode()
                headers = {
                    "X-Fixture-Signature": hmac.new(
                        b"fixture-key", body, hashlib.sha256
                    ).hexdigest()
                }
                for _ in range(2):
                    assert (
                        client.post(
                            "/api/callback/payments/fixture-catalog",
                            data=body,
                            headers=headers,
                        ).status_code
                        == 200
                    )
                subscription = BillingSubscription.query.filter_by(
                    subscription_bid=order.subscription_bid
                ).one()
                assert subscription.provider_subscription_id == "agreement-omega"
                assert (
                    CreditLedgerEntry.query.filter_by(
                        source_bid=first_order_bid
                    ).count()
                    == 1
                )
                for operation in ("cancel", "resume"):
                    managed = client.post(
                        f"/api/billing/subscriptions/{operation}",
                        json={"subscription_bid": subscription.subscription_bid},
                    ).get_json(force=True)
                    assert managed.get("code") == 0, managed
                with unit_of_work():
                    renewal = ensure_subscription_renewal_order(app, subscription)
                assert renewal is not None
                FixtureProvider.attempts["agreement-omega"] = {
                    **payload,
                    "state": "unknown",
                    "amount": None,
                    "currency": None,
                    "agreement": {
                        "reference": "agreement-omega",
                        "phase": "live",
                        "since": end,
                        "until": end + 30 * 86400,
                    },
                }
                for _ in range(2):
                    synced = sync_billing_order(
                        app, "creator-1", renewal.bill_order_bid, {}
                    )
                    assert synced.status == "paid"
                assert (
                    CreditLedgerEntry.query.filter_by(
                        source_bid=renewal.bill_order_bid
                    ).count()
                    == 1
                )
                ledger_count = CreditLedgerEntry.query.count()
                refunded = refund_billing_order(app, "creator-1", first_order_bid, {})
                assert refunded.status == "refunded"
                assert CreditLedgerEntry.query.count() == ledger_count
            reconciled = reconcile_provider_catalog(app, provider="fixture-catalog")
            assert reconciled["provider"] == "fixture-catalog"
            assert reconciled["processed"] == 2
            price = CatalogReader().list_price_snapshots(app)[0]
            change = CatalogChange(
                account=CatalogReader().retrieve_account_snapshot(app),
                event_id="offer-retired",
                event_type="offer.retired",
                source="webhook",
                object_type="price",
                object_id=price.price_id,
                parent_object_id=price.product_id,
                occurred_at=now_utc() + timedelta(seconds=1),
                raw_payload={"offer_ref": "catalog-offer", "phase": "retired"},
            )

            def read_catalog_notification(
                _app: Flask, notification: PaymentNotificationResult
            ) -> tuple[CatalogChange, ProviderPriceSnapshot] | None:
                if notification.status != "offer.retired":
                    return None
                return change, replace(price, active=False)

            provider_catalog_sync.register_catalog_notification_reader(
                "fixture-catalog", read_catalog_notification
            )
            body = json.dumps(
                {"event": "offer.retired", "offer": "catalog-offer"}
            ).encode()
            headers = {
                "X-Fixture-Signature": hmac.new(
                    b"fixture-key", body, hashlib.sha256
                ).hexdigest()
            }
            with app.test_client() as client:
                # Invalid signatures cannot deactivate the mapping or enter the inbox.
                assert (
                    client.post(
                        "/api/callback/payments/fixture-catalog", data=body
                    ).status_code
                    == 400
                )
                assert (
                    provider_price_mappings.get_provider_price_mapping(
                        mapping.provider_price_bid
                    ).status
                    != BILLING_PROVIDER_PRICE_STATUS_INVALID
                )
                assert (
                    client.post(
                        "/api/callback/payments/fixture-catalog",
                        data=body,
                        headers=headers,
                    ).status_code
                    == 200
                )
                assert (
                    client.post(
                        "/api/callback/payments/fixture-catalog",
                        data=body,
                        headers=headers,
                    ).status_code
                    == 200
                )
            assert (
                apply_catalog_change(app, change, replace(price, active=False)).status
                == "duplicate"
            )
            assert (
                provider_price_mappings.get_provider_price_mapping(
                    mapping.provider_price_bid
                ).status
                == BILLING_PROVIDER_PRICE_STATUS_INVALID
            )
    finally:
        dao.db.session.remove()
        CatalogSnapshot.__table__.drop(dao.db.engine)
