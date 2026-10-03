"""Expose the stable payment-provider lookup boundary."""

from flaskr.service.order.payment_providers import get_payment_provider

__all__ = ["get_payment_provider"]
