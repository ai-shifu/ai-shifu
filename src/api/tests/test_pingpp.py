from flaskr.service.order.payment_providers.base import PaymentCreationResult


def test_init_pingxx_uses_provider(app, monkeypatch):
    from flaskr.service.order import pingxx_order

    class FakeProvider:
        def __init__(self):
            self.called = False

        def ensure_client(self, _app):
            self.called = True
            return "client"

    provider = FakeProvider()
    monkeypatch.setattr(pingxx_order, "_get_provider", lambda: provider)

    client = pingxx_order.init_pingxx(app)
    assert client == "client"
    assert provider.called is True


def test_create_pingxx_order_builds_request(app, monkeypatch):
    from flaskr.service.order import pingxx_order

    captured = {}

    class FakeProvider:
        def create_payment(self, *, request, app):
            _ = app
            captured["request"] = request
            return PaymentCreationResult(
                provider_reference="ref", raw_response={"id": "ch"}
            )

    monkeypatch.setattr(pingxx_order, "_get_provider", lambda: FakeProvider())

    order = pingxx_order.create_pingxx_order(
        app,
        order_no="order-1",
        app_id="app-1",
        channel="wx_pub_qr",
        amount=100,
        client_ip="127.0.0.1",
        subject="AI",
        body="AI",
        extra={"product_id": "prod-1"},
    )

    assert order["id"] == "ch"
    request = captured["request"]
    assert request.order_bid == "order-1"
    assert request.amount == 100
    assert request.channel == "wx_pub_qr"
    assert request.extra["app_id"] == "app-1"
    assert request.extra["charge_extra"]["product_id"] == "prod-1"
