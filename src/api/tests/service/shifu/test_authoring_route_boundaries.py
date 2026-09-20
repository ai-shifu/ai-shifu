"""Protect authoring HTTP permissions, patch semantics, and revision responses."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.service.shifu import route as shifu_routes

PREFIX = "/api/shifu"


COURSE = f"{PREFIX}/shifus/course"


HEADERS = {"Token": "authoring-test-token"}


@pytest.fixture(autouse=True)
def authoring_user(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    user = SimpleNamespace(
        user_id="teacher", is_creator=True, is_operator=False, language="en-US"
    )
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda _app, _token: user)
    monkeypatch.setattr(
        shifu_routes, "shifu_permission_verification", Mock(return_value=True)
    )
    monkeypatch.setattr(
        shifu_routes, "get_shifu_creator_bid", Mock(return_value="teacher")
    )
    return user


@pytest.mark.parametrize(("raw", "expected"), [("true", True), (False, False)])
def test_favorite_route_normalizes_boolean_values(
    test_client: object,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    raw: object,
    expected: bool,
) -> None:
    handler = Mock(return_value={"favorite": expected})
    monkeypatch.setattr(shifu_routes, "mark_or_unmark_favorite_shifu", handler)
    response = test_client.post(
        f"{COURSE}/favorite", json={"is_favorite": raw}, headers=HEADERS
    )
    assert response.get_json(force=True)["data"] == {"favorite": expected}
    handler.assert_called_once_with(app, "teacher", "course", expected)
