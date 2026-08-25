"""Provider adapters for billing campaign discounts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol

from flaskr.service.common.stripe_client import get_stripe_client_options

if TYPE_CHECKING:
    from flask import Flask


@dataclass(slots=True, frozen=True)
class ProviderDiscountCreateRequest:
    """Data required to create a campaign discount at a payment provider."""

    campaign_bid: str
    campaign_provider_discount_bid: str
    product_bid: str
    product_code: str
    product_provider_price_bid: str
    provider_product_id: str
    provider_price_id: str
    currency: str
    amount_off: int | None
    percent_off: Decimal | None
    duration: str
    metadata: dict[str, str]
    idempotency_key: str


@dataclass(slots=True, frozen=True)
class ProviderDiscountSnapshot:
    """Normalized provider discount snapshot."""

    provider_coupon_id: str
    provider_account_id: str
    livemode: bool | None
    valid: bool
    currency: str | None
    amount_off: int | None
    percent_off: Decimal | None
    duration: str
    metadata: dict[str, str] = field(default_factory=dict)


class CampaignDiscountProvider(Protocol):
    """Provider methods required by campaign discount publishing."""

    def create_campaign_discount(
        self, *, request: ProviderDiscountCreateRequest, app: object
    ) -> ProviderDiscountSnapshot:
        """Create a provider discount."""

    def retrieve_campaign_discount(
        self, *, provider_coupon_id: str, app: object
    ) -> ProviderDiscountSnapshot:
        """Retrieve a provider discount."""

    def retire_campaign_discount(
        self, *, provider_coupon_id: str, app: object
    ) -> ProviderDiscountSnapshot:
        """Retire a provider discount."""


class StripeCampaignDiscountProvider:
    """Stripe Coupon adapter for billing campaign discounts."""

    def create_campaign_discount(
        self, *, request: ProviderDiscountCreateRequest, app: Flask
    ) -> ProviderDiscountSnapshot:
        """Create a Stripe Coupon for one billing campaign SKU/price."""
        stripe, request_options = get_stripe_client_options(app)
        params: dict[str, Any] = {
            "duration": request.duration,
            "metadata": request.metadata,
            "idempotency_key": request.idempotency_key,
        }
        if request.amount_off is not None:
            params["amount_off"] = int(request.amount_off)
            params["currency"] = request.currency.lower()
        if request.percent_off is not None:
            params["percent_off"] = float(request.percent_off)
        coupon = stripe.Coupon.create(**params, **request_options)
        return _stripe_coupon_to_discount_snapshot(coupon)

    def retrieve_campaign_discount(
        self, *, provider_coupon_id: str, app: Flask
    ) -> ProviderDiscountSnapshot:
        """Retrieve a Stripe Coupon snapshot."""
        stripe, request_options = get_stripe_client_options(app)
        coupon = stripe.Coupon.retrieve(provider_coupon_id, **request_options)
        return _stripe_coupon_to_discount_snapshot(coupon)

    def retire_campaign_discount(
        self, *, provider_coupon_id: str, app: Flask
    ) -> ProviderDiscountSnapshot:
        """Delete a Stripe Coupon so new checkout sessions cannot use it."""
        stripe, request_options = get_stripe_client_options(app)
        coupon = stripe.Coupon.delete(provider_coupon_id, **request_options)
        return _stripe_coupon_to_discount_snapshot(coupon)


def _stripe_coupon_to_discount_snapshot(coupon: object) -> ProviderDiscountSnapshot:
    payload = coupon.to_dict() if hasattr(coupon, "to_dict") else dict(coupon or {})
    metadata = payload.get("metadata") or {}
    if hasattr(metadata, "to_dict"):
        metadata = metadata.to_dict()
    percent_off = payload.get("percent_off")
    return ProviderDiscountSnapshot(
        provider_coupon_id=str(payload.get("id") or ""),
        provider_account_id=str(payload.get("account") or ""),
        livemode=(
            payload.get("livemode")
            if payload.get("livemode") is None
            else bool(payload.get("livemode"))
        ),
        valid=bool(payload.get("valid", not bool(payload.get("deleted")))),
        currency=(
            str(payload.get("currency") or "").upper()
            if payload.get("currency")
            else None
        ),
        amount_off=(
            int(payload.get("amount_off"))
            if payload.get("amount_off") is not None
            else None
        ),
        percent_off=(
            Decimal(str(percent_off)).quantize(Decimal("0.01"))
            if percent_off is not None
            else None
        ),
        duration=str(payload.get("duration") or ""),
        metadata={str(key): str(value) for key, value in dict(metadata).items()},
    )
