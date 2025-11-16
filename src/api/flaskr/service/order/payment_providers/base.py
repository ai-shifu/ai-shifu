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

    def handle_notification(
        self, *, payload: Dict[str, Any], app
    ) -> PaymentNotificationResult:
        """Process provider webhook payloads."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support notifications"
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
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support status sync"
        )
