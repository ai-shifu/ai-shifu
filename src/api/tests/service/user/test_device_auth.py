"""Verify the device authorization flow used by command-line clients."""

import json

import pytest
from flaskr.service.common.models import AppError
from flaskr.service.user.device_auth import (
    STATUS_APPROVED,
    STATUS_DENIED,
    STATUS_PENDING,
    approve_device_authorization,
    create_device_authorization,
    deny_device_authorization,
    format_user_code,
    get_device_authorization,
    normalize_user_code,
    poll_device_authorization,
)

USER_ID = "test-user-bid-0001"


def _start(app: object) -> dict:
    return create_device_authorization(
        app,
        device_name="MacBook-Pro",
        device_os="macOS 15",
        client_version="1.2.6",
        client_ip="203.0.113.7",
    )


def test_full_flow_issues_token_after_approval(app: object) -> None:
    with app.test_request_context():
        started = _start(app)

        pending = get_device_authorization(app, user_code=started["user_code"])
        assert pending["device_name"] == "MacBook-Pro"
        assert pending["device_os"] == "macOS 15"

        waiting = poll_device_authorization(app, device_code=started["device_code"])
        assert waiting["status"] == STATUS_PENDING
        assert waiting["token"] == ""

        approve_device_authorization(
            app, user_code=started["user_code"], user_id=USER_ID
        )

        issued = poll_device_authorization(app, device_code=started["device_code"])
        assert issued["status"] == STATUS_APPROVED
        assert issued["token"]


def test_verification_url_never_carries_the_device_code(app: object) -> None:
    """The device code is the CLI's secret; leaking it would leak the token."""
    with app.test_request_context():
        started = _start(app)

        assert started["device_code"] not in started["verification_uri_complete"]
        assert started["device_code"] not in started["verification_uri"]
        assert started["user_code"] in started["verification_uri_complete"]


def test_token_can_only_be_collected_once(app: object) -> None:
    with app.test_request_context():
        started = _start(app)
        approve_device_authorization(
            app, user_code=started["user_code"], user_id=USER_ID
        )
        assert poll_device_authorization(app, device_code=started["device_code"])[
            "token"
        ]

        with pytest.raises(AppError):
            poll_device_authorization(app, device_code=started["device_code"])


def test_denied_request_stops_the_client(app: object) -> None:
    with app.test_request_context():
        started = _start(app)
        deny_device_authorization(app, user_code=started["user_code"])

        result = poll_device_authorization(app, device_code=started["device_code"])
        assert result["status"] == STATUS_DENIED
        assert result["token"] == ""


def test_request_cannot_be_approved_twice(app: object) -> None:
    with app.test_request_context():
        started = _start(app)
        approve_device_authorization(
            app, user_code=started["user_code"], user_id=USER_ID
        )

        with pytest.raises(AppError):
            approve_device_authorization(
                app, user_code=started["user_code"], user_id=USER_ID
            )


def test_unknown_pairing_code_is_rejected(app: object) -> None:
    with app.test_request_context(), pytest.raises(AppError):
        get_device_authorization(app, user_code="XXX-XXX")


def test_pairing_code_guessing_is_rate_limited(app: object) -> None:
    with app.test_request_context():
        attacker_ip = "198.51.100.9"
        max_attempts = int(app.config.get("DEVICE_AUTH_MAX_LOOKUP_ATTEMPTS", 10))

        for _ in range(max_attempts):
            with pytest.raises(AppError):
                get_device_authorization(
                    app, user_code="AAA-AAA", client_ip=attacker_ip
                )

        # A valid code must now be refused too: the IP is out of attempts.
        started = _start(app)
        with pytest.raises(AppError):
            get_device_authorization(
                app, user_code=started["user_code"], client_ip=attacker_ip
            )


def test_pairing_code_is_accepted_in_any_readable_form(app: object) -> None:
    with app.test_request_context():
        started = _start(app)
        typed_by_hand = started["user_code"].replace("-", "").lower()

        pending = get_device_authorization(app, user_code=typed_by_hand)
        assert pending["user_code"] == started["user_code"]


def test_user_code_helpers_round_trip() -> None:
    assert normalize_user_code(" ac4-7hk ") == "AC47HK"
    assert format_user_code("AC47HK") == "AC4-7HK"


def test_approval_requires_a_user(app: object) -> None:
    with app.test_request_context():
        started = _start(app)
        with pytest.raises(AppError):
            approve_device_authorization(
                app, user_code=started["user_code"], user_id=""
            )


def test_authorize_route_returns_pairing_material(test_client: object) -> None:
    response = test_client.post(
        "/api/user/device/authorize",
        data=json.dumps({"device_name": "CI runner", "device_os": "Linux"}),
        content_type="application/json",
    )
    body = response.get_json(force=True)

    assert response.status_code == 200
    assert body["code"] == 0
    assert body["data"]["user_code"]
    assert body["data"]["device_code"]
    assert body["data"]["interval"] >= 1


def test_token_route_reports_pending_without_erroring(test_client: object) -> None:
    started = test_client.post(
        "/api/user/device/authorize",
        data=json.dumps({}),
        content_type="application/json",
    ).get_json(force=True)["data"]

    response = test_client.post(
        "/api/user/device/token",
        data=json.dumps({"device_code": started["device_code"]}),
        content_type="application/json",
    )
    body = response.get_json(force=True)

    assert response.status_code == 200
    assert body["code"] == 0
    assert body["data"]["status"] == STATUS_PENDING
