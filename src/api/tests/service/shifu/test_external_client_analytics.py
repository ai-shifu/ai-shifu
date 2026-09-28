"""Verify attributed course events preserve business outcomes."""

from types import SimpleNamespace

import pytest
from flask import request
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
    events: list[tuple[str, object, str]] = []
    monkeypatch.setattr(
        route,
        "get_session_skill_attribution",
        lambda _app, *, token: identity if token == "cli-token" else None,
    )
    monkeypatch.setattr(
        route,
        "track_external_client_event",
        lambda _app, *, event_name, attribution, user_id="": events.append(
            (event_name, attribution, user_id)
        ),
    )

    with app.test_request_context(headers={"Token": "cli-token"}):
        request.user = SimpleNamespace(user_id="user-1")
        with route._external_client_course_event(app, "creation"):
            pass

    assert events == [
        ("external_course_creation_started", identity, "user-1"),
        ("external_course_creation_completed", identity, "user-1"),
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
        user_id: str = "",
    ) -> None:
        assert attribution == identity
        assert user_id == "user-1"
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
        with (
            pytest.raises(RuntimeError, match=message),
            route._external_client_course_event(app, "publish"),
        ):
            raise RuntimeError(message)

    assert events == [
        "external_course_publish_started",
        "external_course_publish_failed",
    ]
