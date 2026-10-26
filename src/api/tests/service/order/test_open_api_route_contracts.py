"""Exercise partner HTTP authentication and normalized order request contracts."""

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.route import open_api
from flaskr.service.common.models import ERROR_CODE
from flaskr.service.user.models import UserInfo


@pytest.fixture
def partner(app: Flask, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    user_bid = uuid4().hex
    with app.app_context():
        user = UserInfo(user_bid=user_bid, api_key="test-partner-key")
        db.session.add(user)
        db.session.commit()
    calls = {}
    for name in ("query", "grant", "revoke"):
        calls[name] = Mock(return_value={"operation": name})
        monkeypatch.setattr(open_api, f"open_api_{name}_order", calls[name])
    yield SimpleNamespace(
        client=app.test_client(),
        calls=calls,
        user_bid=user_bid,
        headers={"X-User-Uid": user_bid, "X-Api-Key": "test-partner-key"},
        payload={
            "shifu_bid": "course",
            "user_identify": "learner@example.test",
            "user_identify_type": "email",
        },
    )
    with app.app_context():
        db.session.rollback()
        UserInfo.query.filter_by(user_bid=user_bid).delete()
        db.session.commit()


@pytest.mark.parametrize("operation", ["query", "grant", "revoke"])
@pytest.mark.parametrize("encoding", ["json", "form"])
def test_partner_routes_normalize_inputs_and_bind_authenticated_owner(
    app: Flask,
    partner: SimpleNamespace,
    operation: str,
    encoding: str,
) -> None:
    payload = {
        "shifu_bid": " course ",
        "user_identify": " learner@example.test ",
        "user_identify_type": " EMAIL ",
        "owner_bid": "forged-owner",
    }
    response = partner.client.post(
        f"/api/open-api/v1/order/{operation}",
        headers={key: f" {value} " for key, value in partner.headers.items()},
        **({"json": payload} if encoding == "json" else {"data": payload}),
    )
    assert response.get_json(force=True) == {
        "code": 0,
        "message": "success",
        "data": {"operation": operation},
    }
    partner.calls[operation].assert_called_once_with(
        app, partner.user_bid, "course", "learner@example.test", "email"
    )
    assert sum(call.call_count for call in partner.calls.values()) == 1


@pytest.mark.parametrize("operation", ["query", "grant", "revoke"])
@pytest.mark.parametrize(
    "invalid", ["missing_uid", "missing_key", "unknown_uid", "wrong_key", "deleted"]
)
def test_partner_auth_failure_never_reaches_order_services(
    app: Flask,
    partner: SimpleNamespace,
    operation: str,
    invalid: str,
) -> None:
    headers = partner.headers.copy()
    if invalid == "missing_uid":
        headers.pop("X-User-Uid")
    elif invalid == "missing_key":
        headers["X-Api-Key"] = " "
    elif invalid == "unknown_uid":
        headers["X-User-Uid"] = "unknown-user"
    elif invalid == "wrong_key":
        headers["X-Api-Key"] = "wrong-key"
    else:
        with app.app_context():
            UserInfo.query.filter_by(user_bid=partner.user_bid).update({"deleted": 1})
            db.session.commit()
    response = partner.client.post(
        f"/api/open-api/v1/order/{operation}",
        headers=headers,
        json=partner.payload,
    )
    assert (
        response.get_json(force=True)["code"]
        == ERROR_CODE["server.openapi.invalidApiKey"]
    )
    assert all(call.call_count == 0 for call in partner.calls.values())


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"shifu_bid": " "},
        {"shifu_bid": "course", "user_identify": " "},
        {
            "shifu_bid": "course",
            "user_identify": "learner",
            "user_identify_type": "username",
        },
    ],
)
def test_partner_parameter_failure_never_reaches_service(
    partner: SimpleNamespace,
    payload: dict,
) -> None:
    response = partner.client.post(
        "/api/open-api/v1/order/grant",
        headers=partner.headers,
        json=payload,
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )
    assert all(call.call_count == 0 for call in partner.calls.values())


def test_partner_request_defaults_identifier_type_to_phone(
    app: Flask,
    partner: SimpleNamespace,
) -> None:
    response = partner.client.post(
        "/api/open-api/v1/order/query",
        headers=partner.headers,
        json={"shifu_bid": "course", "user_identify": " 13800138000 "},
    )
    assert response.get_json(force=True)["code"] == 0
    partner.calls["query"].assert_called_once_with(
        app, partner.user_bid, "course", "13800138000", "phone"
    )


def test_malformed_json_is_reported_as_missing_parameters(
    partner: SimpleNamespace,
) -> None:
    response = partner.client.post(
        "/api/open-api/v1/order/query",
        headers=partner.headers,
        data=b"{broken",
        content_type="application/json",
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )
    assert all(call.call_count == 0 for call in partner.calls.values())
