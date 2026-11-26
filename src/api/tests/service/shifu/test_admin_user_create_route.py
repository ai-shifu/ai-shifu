"""Verify the operator route that creates username + password accounts."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.service.shifu.admin_operations import route as route_module
from flaskr.service.user.models import AuthCredential, UserInfo, UserToken

from tests.service.shifu.admin_operation_helpers import mock_operator, post_json

if TYPE_CHECKING:
    from flask.testing import FlaskClient

_CREATE_URL = "/api/shifu/admin/operations/users"
# Generated per run so disposable fixtures are never mistaken for credentials.
_BODY = {
    "username": "route.user",
    "password": f"Pw{secrets.token_hex(8)}1",
    "nickname": "Route",
}


@pytest.fixture(autouse=True)
def _isolate_user_tables(app: object) -> object:
    def _clear() -> None:
        with app.app_context():
            db.session.query(UserToken).delete()
            db.session.query(AuthCredential).delete()
            db.session.query(UserInfo).delete()
            db.session.commit()

    _clear()
    yield
    _clear()


def _enable_login_methods(monkeypatch: pytest.MonkeyPatch, *methods: str) -> None:
    monkeypatch.setattr(
        route_module, "_get_login_methods_enabled", lambda: set(methods)
    )


def test_create_route_requires_operator(
    test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_operator(monkeypatch, is_operator=False)
    _enable_login_methods(monkeypatch, "phone", "password")

    assert post_json(test_client, _CREATE_URL, json=_BODY)["code"] == 401


def test_create_route_requires_password_login(
    app: object, test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_operator(monkeypatch)
    _enable_login_methods(monkeypatch, "phone")

    payload = post_json(test_client, _CREATE_URL, json=_BODY)

    assert payload["code"] == 1048
    with app.app_context():
        assert UserInfo.query.count() == 0


def test_create_route_returns_created_account(
    app: object, test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_operator(monkeypatch)
    _enable_login_methods(monkeypatch, "phone", "password")

    payload = post_json(test_client, _CREATE_URL, json=_BODY)

    assert payload["code"] == 0
    assert payload["data"]["username"] == "route.user"
    assert payload["data"]["user_bid"]
    assert "password" not in payload["data"]
    with app.app_context():
        user = UserInfo.query.filter_by(user_bid=payload["data"]["user_bid"]).one()
        assert user.nickname == "Route"


def test_create_route_rejects_malformed_payload(
    test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_operator(monkeypatch)
    _enable_login_methods(monkeypatch, "password")

    payload = post_json(test_client, _CREATE_URL, json={"username": "x"})

    assert payload["code"] != 0
