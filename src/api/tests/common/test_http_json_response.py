"""Keep API data inert in browsers while preserving response serialization."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest
from flask import Flask, Response, request
from flaskr.common.http import make_common_response
from flaskr.route import order
from flaskr.service.learn.live_follow_up_routes import _make_live_response


@pytest.mark.parametrize(
    "content",
    [
        "<script>alert(document.domain)</script>",
        '<svg onload="alert(1)"></svg>',
        '</script><img src="x" onerror="alert(1)">',
    ],
)
def test_untrusted_api_data_is_served_as_json(content: str) -> None:
    app = Flask(__name__)

    @app.get("/echo")
    def echo() -> Response:
        return make_common_response({"content": request.args["content"]})

    response = app.test_client().get("/echo", query_string={"content": content})

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.get_json() == {
        "code": 0,
        "message": "success",
        "data": {"content": content},
    }


def test_common_response_preserves_custom_values_without_app_context() -> None:
    class ExampleDTO:
        def __json__(self) -> dict[str, str]:
            return {"label": "caf\u00e9"}

    response = make_common_response(
        {
            "dto": ExampleDTO(),
            "amount": Decimal("12.340"),
            "date": date(2026, 11, 1),
            "naive": datetime(2026, 11, 1, 2, 3, 4),
            "utc": datetime(2026, 11, 1, 2, 3, 4, tzinfo=UTC),
            "offset": datetime(
                2026, 11, 1, 10, 3, 4, tzinfo=timezone(timedelta(hours=8))
            ),
            "missing": None,
        }
    )

    assert response.get_json()["data"] == {
        "dto": {"label": "caf\u00e9"},
        "amount": "12.340",
        "date": "2026-11-01",
        "naive": "2026-11-01T02:03:04Z",
        "utc": "2026-11-01T02:03:04Z",
        "offset": "2026-11-01T02:03:04Z",
        "missing": None,
    }
    assert "caf\u00e9" in response.get_data(as_text=True)
    assert make_common_response(None).get_json()["data"] == {}


@pytest.mark.parametrize("status", [202, 400, 409])
def test_legacy_stripe_route_preserves_provider_status(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    app = Flask(__name__)
    order.register_order_handler(app, "/api/order")
    handler = Mock(return_value=({"accepted": False}, status))
    monkeypatch.setattr(order, "handle_stripe_webhook", handler)

    response = app.test_client().post(
        "/api/order/stripe/webhook",
        data=b'{"signed":true}',
        headers={"Stripe-Signature": "signature"},
    )

    assert response.status_code == status
    assert response.mimetype == "application/json"
    assert response.get_json()["data"] == {"accepted": False}
    handler.assert_called_once_with(app, b'{"signed":true}', "signature")


def test_live_follow_up_response_retains_json_and_no_sniff_headers() -> None:
    response = _make_live_response({"session_bid": "session"})

    assert response.mimetype == "application/json"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.get_json()["data"] == {"session_bid": "session"}
