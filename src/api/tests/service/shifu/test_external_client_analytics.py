"""Verify attributed course events preserve business outcomes."""

from types import SimpleNamespace

import pytest
from flask import g, request
from flaskr.route import user as user_route
from flaskr.service.common.skill_attribution import SkillIdentityInput
from flaskr.service.shifu import route


@pytest.fixture
def identity() -> SkillIdentityInput:
    return SkillIdentityInput(
        host_platform="lobster",
        skill_id="ai-shifu-course-creator",
        skill_version="1.9.0",
    )


def test_external_course_context_reports_start_and_success(
    app: object, monkeypatch: object, identity: SkillIdentityInput
) -> None:
    events: list[tuple[str, object]] = []
    monkeypatch.setattr(
        route,
        "get_session_skill_attribution",
        lambda _app, *, token: identity if token == "cli-token" else None,
    )
    monkeypatch.setattr(
        route,
        "track_external_client_event",
        lambda _app, *, event_name, attribution: events.append(
            (event_name, attribution)
        ),
    )

    with app.test_request_context(headers={"Token": "cli-token"}):
        request.user = SimpleNamespace(user_id="user-1")
        g.authenticated_session_token = "cli-token"
        with route._external_client_course_event(app, "creation"):
            pass

    assert events == [
        ("external_course_creation_started", identity),
        ("external_course_creation_completed", identity),
    ]


def test_external_course_context_reports_failure_and_preserves_error(
    app: object, monkeypatch: object, identity: SkillIdentityInput
) -> None:
    events: list[str] = []

    def get_attribution(_app: object, *, token: str) -> SkillIdentityInput:
        assert token == "cli-token"
        return identity

    def record_event(
        _app: object,
        *,
        event_name: str,
        attribution: object,
    ) -> None:
        assert attribution == identity
        events.append(event_name)

    monkeypatch.setattr(
        route,
        "get_session_skill_attribution",
        get_attribution,
    )
    monkeypatch.setattr(
        route,
        "track_external_client_event",
        record_event,
    )

    message = "original failure"
    with app.test_request_context(headers={"Token": "cli-token"}):
        request.user = SimpleNamespace(user_id="user-1")
        g.authenticated_session_token = "cli-token"
        with (
            pytest.raises(RuntimeError, match=message),
            route._external_client_course_event(app, "publish"),
        ):
            raise RuntimeError(message)

    assert events == [
        "external_course_publish_started",
        "external_course_publish_failed",
    ]


def test_external_course_context_uses_authenticated_cookie_token(
    app: object, monkeypatch: object, identity: SkillIdentityInput
) -> None:
    """A lower-priority header token cannot color a cookie-authenticated request."""
    observed_tokens: list[str] = []
    events: list[tuple[str, object]] = []

    def get_attribution(_app: object, *, token: str) -> SkillIdentityInput | None:
        observed_tokens.append(token)
        return identity if token == "cookie-token" else None

    monkeypatch.setattr(route, "get_session_skill_attribution", get_attribution)
    monkeypatch.setattr(
        route,
        "track_external_client_event",
        lambda _app, *, event_name, attribution: events.append(
            (event_name, attribution)
        ),
    )

    with app.test_request_context(
        headers={"Token": "different-header-token"},
        environ_overrides={"HTTP_COOKIE": "token=cookie-token"},
    ):
        request.user = SimpleNamespace(user_id="cookie-user")
        selected_token = user_route._extract_request_token()
        assert selected_token == "cookie-token"
        g.authenticated_session_token = selected_token
        with route._external_client_course_event(app, "creation"):
            pass

    assert observed_tokens == ["cookie-token"]
    assert events == [
        ("external_course_creation_started", identity),
        ("external_course_creation_completed", identity),
    ]
