"""Handle Ping++ order for legacy orders."""

from flask import Flask

from .payment_providers import PaymentRequest, get_payment_provider
from .payment_providers.pingxx import PingxxProvider


def init_pingxx(app: Flask):
    """Initialize pingxx."""
    provider = _get_provider()
    client = provider.ensure_client(app)
    app.logger.info("init pingxx done")
    return client


def create_pingxx_order(
    app: Flask,
    order_no: object,
    app_id: object,
    channel: object,
    amount: object,
    client_ip: object,
    subject: object,
    body: object,
    extra: object = None,
):
    """Create pingxx order."""
    app.logger.info(
        "create pingxx order,order_no:%s app_id:%s channel:%s amount:%s client_ip:%s subject:%s body:%s extra:%s",
        order_no,
        app_id,
        channel,
        amount,
        client_ip,
        subject,
        body,
        extra,
    )
    provider = _get_provider()
    request = PaymentRequest(
        order_bid=order_no,
        user_bid="",
        shifu_bid="",
        amount=amount,
        channel=channel,
        currency="cny",
        subject=subject,
        body=body,
        client_ip=client_ip,
        extra={"app_id": app_id, "charge_extra": extra or {}},
    )
    result = provider.create_payment(request=request, app=app)
    order = result.raw_response
    app.logger.info("create pingxx order done")
    return order


def _get_provider() -> PingxxProvider:
    provider = get_payment_provider("pingxx")
    if not isinstance(provider, PingxxProvider):
        message = f"Expected PingxxProvider, got {provider.__class__.__name__}"
        raise TypeError(message)
    return provider
