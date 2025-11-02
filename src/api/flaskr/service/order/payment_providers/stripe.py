from __future__ import annotations

from typing import Any, Dict

from flask import Flask

from flaskr.common.config import get_config

from .base import (
    PaymentProvider,
    PaymentRequest,
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentRefundRequest,
    PaymentRefundResult,
)
from . import register_payment_provider


class StripeProvider(PaymentProvider):
    """Stripe payment provider implementation."""

    channel = "stripe"

    def __init__(self) -> None:
        self._client_initialized = False
        self._stripe = None

    def _ensure_client(self, app: Flask):
        if self._client_initialized and self._stripe is not None:
            return self._stripe
        try:
            import stripe  # type: ignore
        except ImportError as exc:  # pragma: no cover - surfaced during runtime
            app.logger.error("Stripe SDK is not installed")
            raise RuntimeError("Stripe SDK is required for Stripe payments") from exc

        secret_key = get_config("STRIPE_SECRET_KEY")
        if not secret_key:
            app.logger.error("STRIPE_SECRET_KEY configuration is missing")
            raise RuntimeError("STRIPE_SECRET_KEY must be configured for Stripe")

        stripe.api_key = secret_key
        api_version = get_config("STRIPE_API_VERSION")
        if api_version:
            stripe.api_version = api_version

        self._stripe = stripe
        self._client_initialized = True
        app.logger.info("Stripe client initialized")
        return stripe

    def create_payment(
        self, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        stripe = self._ensure_client(app)
        options: Dict[str, Any] = request.extra or {}
        mode = (options.get("mode") or request.channel or "payment_intent").lower()
        metadata = options.get("metadata", {}) or {}
        if hasattr(metadata, "to_dict"):
            metadata = metadata.to_dict()
        metadata.setdefault("order_bid", request.order_bid)
        metadata.setdefault("user_bid", request.user_bid)
        metadata.setdefault("shifu_bid", request.shifu_bid)

        if mode == "checkout_session":
            success_url = options.get("success_url") or get_config("STRIPE_SUCCESS_URL")
            cancel_url = options.get("cancel_url") or get_config("STRIPE_CANCEL_URL")
            if not success_url or not cancel_url:
                raise RuntimeError(
                    "Stripe checkout session requires success and cancel URLs"
                )

            session_params = options.get("session_params", {})
            params: Dict[str, Any] = {
                "mode": "payment",
                "success_url": success_url,
                "cancel_url": cancel_url,
                **session_params,
            }

            line_items = options.get("line_items")
            if not line_items:
                raise RuntimeError("Stripe checkout session requires line items")
            params["line_items"] = line_items

            customer_email = options.get("customer_email")
            if customer_email:
                params["customer_email"] = customer_email

            payment_intent_data = options.get("payment_intent_data", {})
            existing_metadata = payment_intent_data.get("metadata")
            if existing_metadata:
                if hasattr(existing_metadata, "to_dict"):
                    existing_metadata = existing_metadata.to_dict()
                metadata.update(existing_metadata)
            payment_intent_data["metadata"] = metadata
            params["payment_intent_data"] = payment_intent_data

            session = stripe.checkout.Session.create(**params)
            session_dict = session.to_dict()
            payment_intent_id = session_dict.get("payment_intent")
            latest_charge_id = ""
            payment_intent_object: Dict[str, Any] = {}
            if payment_intent_id:
                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                payment_intent_object = payment_intent.to_dict()
                latest_charge_id = payment_intent_object.get("latest_charge", "") or ""

            return PaymentCreationResult(
                provider_reference=session_dict["id"],
                raw_response=session_dict,
                client_secret=session_dict.get("client_secret"),
                checkout_session_id=session_dict["id"],
                extra={
                    "payment_intent_id": payment_intent_id or "",
                    "latest_charge_id": latest_charge_id,
                    "payment_intent_object": payment_intent_object,
                    "metadata": metadata,
                    "url": session_dict.get("url", ""),
                },
            )

        # Default to payment intent flow
        intent_params = options.get("payment_intent_params", {})
        intent = stripe.PaymentIntent.create(
            amount=request.amount,
            currency=request.currency,
            metadata=metadata,
            **intent_params,
        )
        intent_dict = intent.to_dict()

        return PaymentCreationResult(
            provider_reference=intent_dict["id"],
            raw_response=intent_dict,
            client_secret=intent_dict.get("client_secret"),
            extra={
                "latest_charge_id": intent_dict.get("latest_charge", "") or "",
                "payment_intent_object": intent_dict,
                "metadata": metadata,
            },
        )

    def handle_notification(
        self, *, payload: Dict[str, Any], app: Flask
    ) -> PaymentNotificationResult:
        stripe = self._ensure_client(app)
        webhook_secret = get_config("STRIPE_WEBHOOK_SECRET")
        if not webhook_secret:
            app.logger.error("STRIPE_WEBHOOK_SECRET configuration is missing")
            raise RuntimeError("STRIPE_WEBHOOK_SECRET must be configured for Stripe")

        raw_body = payload.get("raw_body", "")
        if isinstance(raw_body, bytes):
            raw_body_str = raw_body.decode("utf-8")
        else:
            raw_body_str = str(raw_body or "")
        sig_header = payload.get("sig_header", "")
        if not sig_header:
            raise RuntimeError("Stripe signature header missing")

        try:
            event = stripe.Webhook.construct_event(
                raw_body_str, sig_header, webhook_secret
            )
        except Exception as exc:  # pragma: no cover - handled in caller
            app.logger.error("Stripe webhook signature verification failed: %s", exc)
            raise

        data_object = event.get("data", {}).get("object", {}) or {}
        metadata = data_object.get("metadata", {}) or {}
        order_bid = metadata.get("order_bid", "")
        charge_id = data_object.get("latest_charge") or ""
        if not charge_id:
            charges = data_object.get("charges", {}).get("data", [])
            if charges:
                charge_id = charges[0].get("id", "")

        return PaymentNotificationResult(
            order_bid=order_bid,
            status=event.get("type", ""),
            provider_payload=event,
            charge_id=charge_id,
        )

    def refund_payment(
        self, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult:
        stripe = self._ensure_client(app)
        params: Dict[str, Any] = {}
        if request.amount is not None:
            params["amount"] = request.amount
        if request.reason:
            params["reason"] = request.reason

        metadata = request.metadata or {}
        if hasattr(metadata, "to_dict"):
            metadata = metadata.to_dict()
        metadata.setdefault("order_bid", request.order_bid)
        params["metadata"] = metadata

        payment_intent_id = metadata.get("payment_intent_id")
        charge_id = metadata.get("charge_id")
        if payment_intent_id:
            params["payment_intent"] = payment_intent_id
        elif charge_id:
            params["charge"] = charge_id
        else:
            raise RuntimeError(
                "Stripe refund requires payment_intent_id or charge_id metadata"
            )

        refund = stripe.Refund.create(**params)
        refund_dict = refund.to_dict()

        return PaymentRefundResult(
            provider_reference=refund_dict.get("id", ""),
            raw_response=refund_dict,
            status=refund_dict.get("status", ""),
        )


register_payment_provider(StripeProvider)
