"""Shared Stripe SDK configuration helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flaskr.service.config import get_config

if TYPE_CHECKING:
    from flask import Flask


class StripeClientConfigError(RuntimeError):
    """Raised when Stripe SDK or credentials are unavailable."""


def ensure_stripe_client(app: Flask) -> object:
    """Ensure stripe client."""
    try:
        import stripe  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - surfaced during runtime
        app.logger.exception("Stripe SDK is not installed")
        message = "Stripe SDK is required for Stripe operations"
        raise StripeClientConfigError(message) from exc
    return stripe


def build_stripe_request_options() -> dict[str, object]:
    """Build stripe request options."""
    secret_key = get_config("STRIPE_SECRET_KEY")
    if not secret_key:
        message = "STRIPE_SECRET_KEY must be configured for Stripe"
        raise StripeClientConfigError(message)

    request_options: dict[str, Any] = {"api_key": secret_key}
    api_version = get_config("STRIPE_API_VERSION")
    if api_version:
        request_options["stripe_version"] = api_version
    return request_options


def get_stripe_client_options(app: Flask) -> tuple[object, dict[str, object]]:
    """Return stripe client options."""
    return ensure_stripe_client(app), build_stripe_request_options()
