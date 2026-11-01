"""Shared helpers for the operator admin route and service tests.

The operator admin tests authenticate every request as a stub operator, swap
``bcrypt`` for a cheap fake so user seeding stays fast, and read JSON bodies
from routes that always answer with HTTP 200 and an application ``code``.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest
    from flask.testing import FlaskClient

AUTH_HEADERS = {"Token": "test-token"}


def install_fake_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``bcrypt`` with a deterministic, fast stand-in."""
    monkeypatch.setitem(
        sys.modules,
        "bcrypt",
        SimpleNamespace(
            gensalt=lambda _rounds=12: b"salt",
            hashpw=lambda plain, salt: plain + b":" + salt,
            checkpw=lambda plain, hashed: hashed == plain + b":salt",
        ),
    )


def mock_operator(
    monkeypatch: pytest.MonkeyPatch,
    user_id: str = "operator-1",
    *,
    is_operator: bool = True,
) -> None:
    """Authenticate every request token as ``user_id``."""
    dummy_user = SimpleNamespace(
        user_id=user_id,
        is_operator=is_operator,
        is_creator=False,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: dummy_user,
        raising=False,
    )


def get_json(client: FlaskClient, path: str, **kwargs: object) -> dict:
    """GET ``path`` as the operator and return the JSON body of the 200 reply."""
    response = client.get(path, headers=AUTH_HEADERS, **kwargs)
    assert response.status_code == 200
    return response.get_json(force=True)


def post_json(client: FlaskClient, path: str, **kwargs: object) -> dict:
    """POST to ``path`` as the operator and return the JSON body of the 200 reply."""
    response = client.post(path, headers=AUTH_HEADERS, **kwargs)
    assert response.status_code == 200
    return response.get_json(force=True)


def get_ok(client: FlaskClient, path: str, **kwargs: object) -> dict:
    """Like ``get_json`` but also require a successful application code."""
    payload = get_json(client, path, **kwargs)
    assert payload["code"] == 0
    return payload


def post_ok(client: FlaskClient, path: str, **kwargs: object) -> dict:
    """Like ``post_json`` but also require a successful application code."""
    payload = post_json(client, path, **kwargs)
    assert payload["code"] == 0
    return payload
