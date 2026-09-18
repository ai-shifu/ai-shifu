"""Verify provider-side cancellation used before coupon repricing."""

from types import SimpleNamespace

from flaskr.service.order.payment_providers.alipay import AlipayProvider
from flaskr.service.order.payment_providers.pingxx import PingxxProvider
from flaskr.service.order.payment_providers.stripe import StripeProvider
from flaskr.service.order.payment_providers.wechatpay import WechatPayProvider


def test_pingxx_cancellation_reverses_the_charge(monkeypatch: object) -> None:
    reversed_ids: list[str] = []
    charge = SimpleNamespace(
        reverse=lambda charge_id: (
            reversed_ids.append(charge_id) or {"id": charge_id, "reversed": True}
        )
    )
    provider = PingxxProvider()
    monkeypatch.setattr(
        provider, "_ensure_client", lambda _app: SimpleNamespace(Charge=charge)
    )

    result = provider.cancel_payment(
        provider_reference="ch_old",
        reference_type="charge",
        app=SimpleNamespace(),
    )

    assert reversed_ids == ["ch_old"]
    assert result.status == "cancelled"


def test_wechat_cancellation_calls_close_order(monkeypatch: object) -> None:
    requests: list[tuple[str, str, str]] = []
    provider = WechatPayProvider()
    monkeypatch.setattr(
        "flaskr.service.order.payment_providers.wechatpay.get_config",
        lambda name, default="": (
            "merchant-1" if name == "WECHATPAY_MCH_ID" else default
        ),
    )

    def fake_request(*, method: str, path: str, body: str, app: object) -> dict:
        del app
        requests.append((method, path, body))
        return {}

    monkeypatch.setattr(
        provider,
        "_request",
        fake_request,
    )

    result = provider.cancel_payment(
        provider_reference="attempt-old",
        reference_type="trade",
        app=SimpleNamespace(),
    )

    assert requests == [
        (
            "POST",
            "/v3/pay/transactions/out-trade-no/attempt-old/close",
            '{"mchid":"merchant-1"}',
        )
    ]
    assert result.status == "cancelled"


def test_stripe_cancellation_expires_checkout_session(monkeypatch: object) -> None:
    expired: list[str] = []
    session = SimpleNamespace(
        expire=lambda session_id, **_kwargs: (
            expired.append(session_id) or {"id": session_id, "status": "expired"}
        )
    )
    provider = StripeProvider()
    monkeypatch.setattr(
        provider,
        "_client_options",
        lambda _app: (SimpleNamespace(checkout=SimpleNamespace(Session=session)), {}),
    )

    result = provider.cancel_payment(
        provider_reference="cs_old",
        reference_type="checkout_session",
        app=SimpleNamespace(),
    )

    assert expired == ["cs_old"]
    assert result.status == "cancelled"


def test_stripe_cancellation_recovers_when_session_is_already_expired(
    monkeypatch: object,
) -> None:
    session = SimpleNamespace(
        expire=lambda _session_id, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("already expired")
        ),
        retrieve=lambda session_id, **_kwargs: {
            "id": session_id,
            "status": "expired",
        },
    )
    provider = StripeProvider()
    monkeypatch.setattr(
        provider,
        "_client_options",
        lambda _app: (SimpleNamespace(checkout=SimpleNamespace(Session=session)), {}),
    )

    result = provider.cancel_payment(
        provider_reference="cs_expired",
        reference_type="checkout_session",
        app=SimpleNamespace(),
    )

    assert result.provider_reference == "cs_expired"
    assert result.status == "cancelled"


def test_stripe_cancellation_preserves_a_completed_checkout_session(
    monkeypatch: object,
) -> None:
    session = SimpleNamespace(
        expire=lambda _session_id, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("already complete")
        ),
        retrieve=lambda session_id, **_kwargs: {
            "id": session_id,
            "status": "complete",
            "payment_status": "paid",
        },
    )
    provider = StripeProvider()
    monkeypatch.setattr(
        provider,
        "_client_options",
        lambda _app: (SimpleNamespace(checkout=SimpleNamespace(Session=session)), {}),
    )

    result = provider.cancel_payment(
        provider_reference="cs_paid",
        reference_type="checkout_session",
        app=SimpleNamespace(),
    )

    assert result.status == "completed"
    assert result.raw_response["payment_status"] == "paid"


def test_pingxx_cancellation_recovers_an_already_reversed_charge(
    monkeypatch: object,
) -> None:
    charge = SimpleNamespace(
        reverse=lambda _charge_id: (_ for _ in ()).throw(
            RuntimeError("already reversed")
        ),
        retrieve=lambda charge_id: {"id": charge_id, "reversed": True},
    )
    provider = PingxxProvider()
    monkeypatch.setattr(
        provider, "_ensure_client", lambda _app: SimpleNamespace(Charge=charge)
    )

    result = provider.cancel_payment(
        provider_reference="ch_reversed",
        reference_type="charge",
        app=SimpleNamespace(),
    )

    assert result.status == "cancelled"


def test_alipay_cancellation_closes_trade(monkeypatch: object) -> None:
    class Model:
        out_trade_no = ""

    requests: list[str] = []

    class Client:
        def execute(self, request: object) -> str:
            requests.append(request.biz_model.out_trade_no)
            return '{"alipay_trade_close_response":{"code":"10000"}}'

    class Request:
        def __init__(self, *, biz_model: object) -> None:
            self.biz_model = biz_model

    provider = AlipayProvider()
    monkeypatch.setattr(provider, "_ensure_client", lambda _app: Client())
    monkeypatch.setattr(
        provider,
        "_load_sdk",
        lambda _app: {
            "AlipayTradeCloseModel": Model,
            "AlipayTradeCloseRequest": Request,
        },
    )

    result = provider.cancel_payment(
        provider_reference="attempt-old",
        reference_type="trade",
        app=SimpleNamespace(),
    )

    assert requests == ["attempt-old"]
    assert result.status == "cancelled"


def test_alipay_cancellation_recovers_an_already_closed_trade(
    monkeypatch: object,
) -> None:
    class Model:
        out_trade_no = ""

    class Client:
        def execute(self, _request: object) -> str:
            return '{"alipay_trade_close_response":{"code":"40004"}}'

    class Request:
        def __init__(self, *, biz_model: object) -> None:
            self.biz_model = biz_model

    provider = AlipayProvider()
    monkeypatch.setattr(provider, "_ensure_client", lambda _app: Client())
    monkeypatch.setattr(
        provider,
        "_load_sdk",
        lambda _app: {
            "AlipayTradeCloseModel": Model,
            "AlipayTradeCloseRequest": Request,
        },
    )
    monkeypatch.setattr(
        provider,
        "sync_reference",
        lambda **_kwargs: SimpleNamespace(
            provider_payload={"trade": {"trade_status": "TRADE_CLOSED"}}
        ),
    )

    result = provider.cancel_payment(
        provider_reference="attempt-closed",
        reference_type="trade",
        app=SimpleNamespace(),
    )

    assert result.status == "cancelled"


def test_wechat_cancellation_recovers_an_already_closed_trade(
    monkeypatch: object,
) -> None:
    provider = WechatPayProvider()
    monkeypatch.setattr(
        "flaskr.service.order.payment_providers.wechatpay.get_config",
        lambda name, default="": (
            "merchant-1" if name == "WECHATPAY_MCH_ID" else default
        ),
    )
    monkeypatch.setattr(
        provider,
        "_request",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("already closed")),
    )
    monkeypatch.setattr(
        provider,
        "sync_reference",
        lambda **_kwargs: SimpleNamespace(
            provider_payload={"trade": {"trade_state": "CLOSED"}}
        ),
    )

    result = provider.cancel_payment(
        provider_reference="attempt-closed",
        reference_type="trade",
        app=SimpleNamespace(),
    )

    assert result.status == "cancelled"
