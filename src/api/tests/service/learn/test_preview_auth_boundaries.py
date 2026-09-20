"""Verify preview token precedence and legacy collaborator permission formats."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, request
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn import preview_permissions as permissions


@pytest.mark.parametrize(
    ("kwargs", "token"),
    [
        (
            {
                "headers": {"Cookie": "token=cookie-token", "Token": "header-token"},
                "query_string": {"token": "query-token"},
            },
            "cookie-token",
        ),
        (
            {
                "headers": {"Token": "header-token"},
                "query_string": {"token": "query-token"},
            },
            "query-token",
        ),
        ({"headers": {"Authorization": "bEaReR bearer-token"}}, "bearer-token"),
        ({"method": "POST", "json": {"token": " body-token "}}, "body-token"),
        ({"headers": {"Authorization": "Basic ignored"}}, None),
    ],
)
def test_preview_auth_resolves_token_precedence_and_supported_transports(
    kwargs: dict, token: str | None
) -> None:
    app = Flask(__name__)
    with app.test_request_context(**kwargs):
        assert permissions._extract_preview_token() == token


def test_bypassed_preview_route_installs_only_a_validated_user(
    monkeypatch: object,
) -> None:
    app = Flask(__name__)
    user = SimpleNamespace(user_id="learner")
    validate = Mock(return_value=user)
    monkeypatch.setattr("flaskr.route.user.validate_user", validate)
    with app.test_request_context(headers={"Authorization": "Bearer token"}):
        assert permissions.resolve_preview_request_user(app) is user
        assert request.user is user
    validate.assert_called_once_with(app, "token")
    validate.reset_mock()
    with app.test_request_context(), pytest.raises(AppError) as error:
        permissions.resolve_preview_request_user(app)
    assert error.value.code == ERROR_CODE["server.user.userNotLogin"]
    validate.assert_not_called()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, set()),
        (" ", set()),
        ("VIEW", {"view"}),
        ('"read"', {"view"}),
        ('" "', set()),
        ("[1, 2, 4]", {"view", "edit", "publish"}),
        (("readonly", ""), {"view"}),
        ({"write", "publish"}, {"view", "edit", "publish"}),
        ("{}", set()),
        ("false", set()),
        (4, set()),
        ("unknown", set()),
    ],
)
def test_legacy_collaborator_values_map_only_to_known_permissions(
    raw: object, expected: set[str]
) -> None:
    assert (
        permissions._auth_types_to_permissions(permissions._normalize_auth_types(raw))
        == expected
    )


@pytest.mark.parametrize(
    ("user", "course", "error_key"),
    [
        (" ", "course", "server.user.userNotLogin"),
        ("user", " ", "server.shifu.shifuNotFound"),
    ],
)
def test_missing_preview_identity_is_rejected_before_database_lookup(
    monkeypatch: object, user: str, course: str, error_key: str
) -> None:
    lookup = Mock()
    monkeypatch.setattr(permissions, "_get_shifu_creator_bid", lookup)
    with pytest.raises(AppError) as error:
        permissions.require_shifu_preview_permission(Flask(__name__), user, course)
    assert error.value.code == ERROR_CODE[error_key]
    lookup.assert_not_called()


@pytest.mark.parametrize("creator", ["system", "regular-teacher"])
def test_demo_title_requires_system_ownership_when_not_explicitly_configured(
    monkeypatch: object, creator: str
) -> None:
    monkeypatch.setattr(
        permissions, "get_config", Mock(side_effect=RuntimeError("config unavailable"))
    )
    monkeypatch.setattr(
        permissions,
        "_load_course_rows",
        lambda _: [
            SimpleNamespace(title="AI-Shifu Creation Guide", created_user_bid=creator)
        ],
    )
    assert permissions.is_builtin_demo_shifu(Flask(__name__), "course") is (
        creator == "system"
    )


def test_configured_demo_bypasses_course_lookup_but_empty_course_does_not(
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(
        permissions,
        "get_config",
        lambda key, _default: " configured-demo " if key == "DEMO_SHIFU_BID" else "",
    )
    lookup = Mock()
    monkeypatch.setattr(permissions, "_load_course_rows", lookup)
    assert permissions.is_builtin_demo_shifu(Flask(__name__), "configured-demo") is True
    assert permissions.is_builtin_demo_shifu(Flask(__name__), " ") is False
    lookup.assert_not_called()
