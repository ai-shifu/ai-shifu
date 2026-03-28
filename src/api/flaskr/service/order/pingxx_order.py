from flask import Flask

from .payment_providers import PaymentRequest, get_payment_provider
from .payment_providers.pingxx import PingxxProvider


def init_pingxx(app: Flask):
    provider = _get_provider()
    client = provider.ensure_client(app)
    app.logger.info("init pingxx done")
    return client


def create_pingxx_order(
    app: Flask, order_no, app_id, channel, amount, client_ip, subject, body, extra=None
):
    app.logger.info(
        "create pingxx order,order_no:{} app_id:{} channel:{} amount:{} client_ip:{} subject:{} body:{} extra:{}".format(
            order_no, app_id, channel, amount, client_ip, subject, body, extra
        )
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
        raise TypeError(f"Expected PingxxProvider, got {provider.__class__.__name__}")
    return provider
