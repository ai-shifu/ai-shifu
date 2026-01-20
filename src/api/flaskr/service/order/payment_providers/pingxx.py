from __future__ import annotations

import os
from typing import Dict, Any

from flask import Flask

from flaskr.service.config import get_config

from .base import PaymentProvider, PaymentRequest, PaymentCreationResult
from . import register_payment_provider


_PINGPP_CLIENT: Any | None = None
_PINGPP_IMPORT_ERROR: Exception | None = None


def _get_pingpp_client() -> Any:
    global _PINGPP_CLIENT, _PINGPP_IMPORT_ERROR
    if _PINGPP_CLIENT is not None:
        return _PINGPP_CLIENT
    if _PINGPP_IMPORT_ERROR is not None:
        raise _PINGPP_IMPORT_ERROR
    try:
        import pingpp  # type: ignore

        _PINGPP_CLIENT = pingpp
        return pingpp
    except Exception as exc:  # pragma: no cover
        _PINGPP_IMPORT_ERROR = exc
        raise


class PingxxProvider(PaymentProvider):
    """Ping++ payment provider implementation."""

    channel = "pingxx"

    def __init__(self) -> None:
        self._client_initialized = False

    def _ensure_client(self, app: Flask) -> Any:
        """Configure pingpp client once per process."""
        try:
            client = _get_pingpp_client()
        except Exception as exc:  # pragma: no cover
            app.logger.error("Pingxx dependency is not available: %s", exc)
            raise RuntimeError("Pingxx dependency is not available") from exc

        if self._client_initialized:
            return client

        api_key = get_config("PINGXX_SECRET_KEY")
        private_key_path = get_config("PINGXX_PRIVATE_KEY_PATH")
        if not private_key_path:
            app.logger.error("PINGXX_PRIVATE_KEY_PATH is not configured")
            raise RuntimeError("Pingxx private key path missing")
        if not os.path.exists(private_key_path):
            app.logger.error("Pingxx private key not found at %s", private_key_path)
            raise FileNotFoundError(private_key_path)

        client.api_key = api_key
        client.private_key_path = private_key_path
        self._client_initialized = True
        app.logger.info("Pingxx client initialized")
        return client

    def ensure_client(self, app: Flask) -> Any:
        """Public wrapper for configuring the pingpp client."""
        return self._ensure_client(app)

    def create_payment(
        self, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        client = self._ensure_client(app)
        provider_options: Dict[str, Any] = request.extra or {}
        app_id = provider_options.get("app_id") or get_config("PINGXX_APP_ID")
        charge_extra = provider_options.get("charge_extra", {})

        charge = client.Charge.create(
            order_no=request.order_bid,
            app=dict(id=app_id),
            channel=request.channel,
            amount=request.amount,
            client_ip=request.client_ip,
            currency=request.currency,
            subject=request.subject,
            body=request.body,
            extra=charge_extra,
        )

        return PaymentCreationResult(
            provider_reference=charge["id"],
            raw_response=charge,
            extra={
                "credential": charge.get("credential"),
            },
        )

    def retrieve_charge(self, *, charge_id: str, app: Flask):
        client = self._ensure_client(app)
        return client.Charge.retrieve(charge_id)


register_payment_provider(PingxxProvider)
