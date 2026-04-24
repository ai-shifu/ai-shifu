from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


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
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PaymentCreationResult:
    """Response data returned after creating a payment."""

    provider_reference: str
    raw_response: Dict[str, Any]
    client_secret: Optional[str] = None
    checkout_session_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PaymentNotificationResult:
    """Normalized data extracted from provider webhook notifications."""

    order_bid: str
    status: str
    provider_payload: Dict[str, Any]
    charge_id: Optional[str] = None


@dataclass(slots=True)
class SubscriptionUpdateResult:
    """Normalized result returned from subscription state updates."""

    provider_reference: str
    raw_response: Dict[str, Any]
    status: str
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PaymentRefundRequest:
    """Request payload for initiating a refund."""

    order_bid: str
    amount: Optional[int] = None
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PaymentRefundResult:
    """Response payload returned from a refund request."""

    provider_reference: str
    raw_response: Dict[str, Any]
    status: str


class PaymentProvider(ABC):
    """Base abstraction for payment providers."""

    channel: str = ""

    @abstractmethod
    def create_payment(self, *, request: PaymentRequest, app) -> PaymentCreationResult:
        """Create a payment with the external provider."""

    def create_subscription(
        self, *, request: PaymentRequest, app
    ) -> PaymentCreationResult:
        """Create a provider-managed subscription checkout."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support subscriptions"
        )

    def cancel_subscription(
        self, *, subscription_bid: str, provider_subscription_id: str, app
    ) -> SubscriptionUpdateResult:
        """Schedule or trigger subscription cancellation at the provider."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support subscription cancellation"
        )

    def resume_subscription(
        self, *, subscription_bid: str, provider_subscription_id: str, app
    ) -> SubscriptionUpdateResult:
        """Resume a paused or cancel-scheduled provider subscription."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support subscription resumption"
        )

    def verify_webhook(
        self, *, headers: Dict[str, str], raw_body: bytes | str, app
    ) -> PaymentNotificationResult:
        """Verify and normalize a provider webhook payload."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support webhook verification"
        )

    def handle_notification(
        self, *, payload: Dict[str, Any], app
    ) -> PaymentNotificationResult:
        """Process provider webhook payloads."""
        return self.verify_webhook(
            headers=payload.get("headers", {}) or {},
            raw_body=payload.get("raw_body", ""),
            app=app,
        )

    def refund_payment(
        self, *, request: PaymentRefundRequest, app
    ) -> PaymentRefundResult:
        """Trigger a refund on the provider."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support refunds")

    def sync_payment_status(
        self, *, order_bid: str, provider_reference: str, app
    ) -> PaymentNotificationResult:
        """Synchronize payment status with the provider if supported."""
        return self.sync_reference(
            provider_reference=provider_reference,
            reference_type="payment",
            app=app,
        )

    def sync_reference(
        self, *, provider_reference: str, reference_type: str, app
    ) -> PaymentNotificationResult:
        """Synchronize a provider reference and return normalized state."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support reference sync"
        )
