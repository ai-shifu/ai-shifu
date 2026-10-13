"""Define the shared payment-provider contract for legacy orders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any

from .contracts import (
    CheckoutTerms,
    PaymentAction,
    PaymentDefinition,
    PaymentEvent,
    PaymentFacts,
    PaymentQueryTerms,
    SubscriptionFacts,
)


@dataclass(slots=True)
class PaymentRequest:
    """Data required to initiate a payment with an external provider."""

    order_bid: str
    user_bid: str
    shifu_bid: str
    amount: int
    channel: str
    currency: str
    subject: str
    body: str
    client_ip: str
    extra: dict[str, Any] = field(default_factory=dict)
    biz_domain: str = "order"
    payment_mode: str = "payment"


@dataclass(slots=True)
class PaymentCreationResult:
    """Response data returned after creating a payment."""

    provider_reference: str
    raw_response: dict[str, Any]
    client_secret: str | None = None
    checkout_session_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    action: PaymentAction | None = None


@dataclass(slots=True)
class PaymentNotificationResult:
    """Normalized data extracted from provider webhook notifications."""

    order_bid: str
    status: str
    provider_payload: dict[str, Any]
    charge_id: str | None = None
    facts: PaymentFacts | None = None
    subscription: SubscriptionFacts | None = None


@dataclass(slots=True)
class SubscriptionUpdateResult:
    """Actual contract state returned from subscription updates.

    Adapters normalize the contract status and explicitly report the boolean
    ``extra["cancel_at_period_end"]``; an accepted command is not confirmation.
    """

    provider_reference: str
    raw_response: dict[str, Any]
    status: str
    extra: dict[str, Any] = field(default_factory=dict)

    def confirmed_contract(
        self, *, cancel_at_period_end: bool
    ) -> SubscriptionFacts | None:
        """Require the requested renewal setting and a recognized live state."""
        status = str(self.status or "").strip().lower()
        reported_cancel = self.extra.get("cancel_at_period_end")
        if (
            status not in {"active", "trialing", "past_due", "paused"}
            or not isinstance(reported_cancel, bool)
            or reported_cancel != cancel_at_period_end
        ):
            return None
        return SubscriptionFacts(
            provider_reference=self.provider_reference,
            status=status,
            cancel_at_period_end=reported_cancel,
        )


@dataclass(slots=True)
class PaymentRefundRequest:
    """Original refund request, including a stable metadata idempotency key.

    Refund-capable adapters must honor ``metadata["idempotency_key"]`` when
    supplied: an uncertain transport or receipt-commit outcome can replay this
    exact request. Successful receipts are persisted before local finalization.
    """

    order_bid: str
    amount: int | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PaymentRefundResult:
    """Response payload returned from a refund request."""

    provider_reference: str
    raw_response: dict[str, Any]
    status: str

    def merge_receipt(self, received: PaymentRefundResult) -> PaymentRefundResult:
        """Combine receipts for one admitted operation without rewinding finality."""
        references_match = (
            not self.provider_reference
            or not received.provider_reference
            or self.provider_reference == received.provider_reference
        )
        terminal = {"succeeded", "failed", "canceled"}
        if (
            references_match
            and str(self.status or "").lower() not in terminal
            and str(received.status or "").lower() in terminal
        ):
            return replace(
                received,
                provider_reference=received.provider_reference
                or self.provider_reference,
            )
        if not self.provider_reference and received.provider_reference:
            return replace(self, provider_reference=received.provider_reference)
        return self


@dataclass(slots=True)
class PaymentCancellationResult:
    """Response returned after making a payment attempt unusable."""

    provider_reference: str
    raw_response: dict[str, Any]
    status: str

    @property
    def is_closed(self) -> bool:
        """Admit only confirmed closure; a completed payment is not closed."""
        return str(self.status or "").strip().lower() in {
            "canceled",
            "cancelled",
            "closed",
            "expired",
        }


@dataclass(frozen=True, slots=True)
class PaymentWebhookResponse:
    """Provider-owned protocol acknowledgement for a verified notification."""

    body: dict[str, str] | str
    status_code: int = 200


class PaymentProvider(ABC):
    """Base abstraction for payment providers."""

    channel: str = ""
    definition: PaymentDefinition = PaymentDefinition()

    @classmethod
    def describe_notification(
        cls, notification: PaymentNotificationResult
    ) -> PaymentEvent:
        """Expose normalized evidence; business code never needs the original envelope."""
        from .normalization import notification_facts

        facts = notification_facts(cls.channel, notification)
        return PaymentEvent(
            kind="refund"
            if facts.state == "refunded"
            else "contract"
            if notification.subscription is not None
            else "payment",
            refund_status="succeeded" if facts.state == "refunded" else None,
            payment=facts,
            contract=notification.subscription,
            order_reference=notification.order_bid,
            lookup_reference=notification.order_bid,
            updated_payment_reference=(facts.provider_reference or "")
            if notification.subscription is None or facts.state != "unknown"
            else "",
            contract_reference=notification.subscription.provider_reference
            if notification.subscription
            else "",
            customer_reference=notification.subscription.customer_reference
            if notification.subscription
            else "",
        )

    @classmethod
    def describe_query(
        cls, notification: PaymentNotificationResult, terms: PaymentQueryTerms
    ) -> PaymentEvent:
        """Interpret a queried result through the same explicit evidence contract."""
        event = cls.describe_notification(notification)
        reported_reference = (
            (event.contract.provider_reference if event.contract else None)
            if terms.is_contract
            else event.payment.provider_reference
        )
        if not reported_reference or reported_reference != terms.reference:
            message = "Payment query reference mismatch"
            raise RuntimeError(message)
        return replace(event, updated_payment_reference=terms.reference)

    @classmethod
    def checkout_options(cls, terms: CheckoutTerms) -> dict[str, Any]:
        """Serialize authorized billing terms without owning price or entitlement policy."""
        from flaskr.service.common.models import raise_error

        route = next(
            (item for item in cls.definition.routes if item.channel == terms.channel),
            None,
        )
        if route is None:
            raise_error("server.pay.payChannelNotSupport")
        if route.requires_open_id and not terms.open_id:
            raise_error("server.pay.wechatOpenIdRequired")
        return {
            "metadata": terms.metadata,
            **({"open_id": terms.open_id} if route.requires_open_id else {}),
            **(
                {"success_url": terms.success_url, "cancel_url": terms.cancel_url}
                if route.action == "redirect"
                else {}
            ),
        }

    @classmethod
    def read_payment_facts(cls, payload: dict[str, Any]) -> PaymentFacts:
        """Interpret saved snapshots without constructing a network client."""
        del payload
        return PaymentFacts()

    def webhook_response(self, *, succeeded: bool) -> PaymentWebhookResponse:
        """Acknowledge processing using the integration's notification protocol."""
        return PaymentWebhookResponse(
            {"code": "SUCCESS" if succeeded else "FAIL"},
            status_code=200 if succeeded else 400,
        )

    @abstractmethod
    def create_payment(
        self, *, request: PaymentRequest, app: object
    ) -> PaymentCreationResult:
        """Create a payment with the external provider."""

    def create_subscription(
        self, *, request: PaymentRequest, app: object
    ) -> PaymentCreationResult:
        """Create a provider-managed subscription checkout."""
        message = f"{self.__class__.__name__} does not support subscriptions"
        raise NotImplementedError(message)

    def cancel_subscription(
        self,
        *,
        subscription_bid: str,
        provider_subscription_id: str,
        app: object,
    ) -> SubscriptionUpdateResult:
        """Schedule or trigger subscription cancellation at the provider."""
        message = (
            f"{self.__class__.__name__} does not support subscription cancellation"
        )
        raise NotImplementedError(message)

    def resume_subscription(
        self,
        *,
        subscription_bid: str,
        provider_subscription_id: str,
        app: object,
    ) -> SubscriptionUpdateResult:
        """Resume a paused or cancel-scheduled provider subscription."""
        message = f"{self.__class__.__name__} does not support subscription resumption"
        raise NotImplementedError(message)

    def verify_webhook(
        self, *, headers: dict[str, str], raw_body: bytes | str, app: object
    ) -> PaymentNotificationResult:
        """Verify and normalize a provider webhook payload."""
        message = f"{self.__class__.__name__} does not support webhook verification"
        raise NotImplementedError(message)

    def handle_notification(
        self, *, payload: dict[str, Any], app: object
    ) -> PaymentNotificationResult:
        """Process provider webhook payloads."""
        return self.verify_webhook(
            headers=payload.get("headers", {}) or {},
            raw_body=payload.get("raw_body", ""),
            app=app,
        )

    def refund_payment(
        self, *, request: PaymentRefundRequest, app: object
    ) -> PaymentRefundResult:
        """Refund with the supplied stable key, returning the same operation on retry."""
        message = f"{self.__class__.__name__} does not support refunds"
        raise NotImplementedError(message)

    def cancel_payment(
        self,
        *,
        provider_reference: str,
        reference_type: str,
        app: object,
    ) -> PaymentCancellationResult:
        """Close an unpaid provider attempt before the order is repriced."""
        message = f"{self.__class__.__name__} does not support payment cancellation"
        raise NotImplementedError(message)

    def sync_payment_status(
        self, *, order_bid: str, provider_reference: str, app: object
    ) -> PaymentNotificationResult:
        """Synchronize payment status with the provider if supported."""
        _ = order_bid
        return self.sync_reference(
            provider_reference=provider_reference,
            reference_type=self.definition.operation_reference_type("query"),
            app=app,
        )

    def sync_reference(
        self, *, provider_reference: str, reference_type: str, app: object
    ) -> PaymentNotificationResult:
        """Synchronize a provider reference and return normalized state."""
        message = f"{self.__class__.__name__} does not support reference sync"
        raise NotImplementedError(message)

    def expire_checkout_session(
        self, *, session_id: str, app: object
    ) -> dict[str, Any]:
        """Expire an open provider checkout session if supported."""
        message = f"{self.__class__.__name__} does not support checkout session expiry"
        raise NotImplementedError(message)

    def build_jsapi_params(self, *, prepay_id: str) -> dict[str, str]:
        """Build client parameters for an existing JSAPI payment if supported."""
        message = f"{self.__class__.__name__} does not support JSAPI payments"
        raise NotImplementedError(message)
