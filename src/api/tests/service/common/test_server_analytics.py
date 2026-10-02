"""Verify backend Umami delivery stays bounded, private, and fail-open."""

from concurrent.futures import Future
from types import SimpleNamespace

import pytest
from flaskr.service.common import server_analytics
from flaskr.service.common.skill_attribution import SkillIdentityInput


def _identity(version: str = "2.7.1") -> SkillIdentityInput:
    return SkillIdentityInput(
        host_platform="workbuddy",
        skill_id="ai-shifu-course-creator",
        skill_version=version,
    )


def test_backend_event_contains_only_allowlisted_dimensions(
    app: object, monkeypatch: object
) -> None:
    submitted: list[tuple[object, ...]] = []

    def submit(*args: object) -> Future[None]:
        submitted.append(args)
        future: Future[None] = Future()
        future.set_result(None)
        return future

    monkeypatch.setattr(server_analytics._EXECUTOR, "submit", submit)
    settings = {
        "ANALYTICS_UMAMI_SCRIPT": "https://analytics.example.test/script.js",
        "ANALYTICS_UMAMI_SITE_ID": "website-id",
    }
    monkeypatch.setattr(
        server_analytics,
        "get_config",
        lambda key, default="": settings.get(key, default),
    )

    server_analytics.track_external_client_event(
        app,
        event_name="external_course_creation_completed",
        attribution=_identity(),
    )

    assert len(submitted) == 1
    _deliver, collector_url, payload = submitted[0]
    assert collector_url == "https://analytics.example.test/api/send"
    assert payload == {
        "website": "website-id",
        "hostname": "server.ai-shifu",
        "url": "/backend/external-client",
        "name": "external_course_creation_completed",
        "data": {
            "host_platform": "workbuddy",
            "skill_id": "ai-shifu-course-creator",
            "skill_version_major": "v2",
        },
    }
    assert set(payload["data"]) == {
        "host_platform",
        "skill_id",
        "skill_version_major",
    }
    for prohibited_key in (
        "token",
        "handoff_id",
        "course_id",
        "course_title",
        "prompt",
        "error",
        "referrer",
        "user_id",
        "user_bid",
        "id",
    ):
        assert prohibited_key not in payload
        assert prohibited_key not in payload["data"]
    assert "url" not in payload["data"]


def test_missing_config_or_attribution_is_a_noop(
    app: object, monkeypatch: object
) -> None:
    submit = SimpleNamespace(called=False)

    def unexpected_submit(*_args: object) -> None:
        submit.called = True

    monkeypatch.setattr(server_analytics._EXECUTOR, "submit", unexpected_submit)
    monkeypatch.setattr(server_analytics, "get_config", lambda *_args: "")

    server_analytics.track_external_client_event(
        app,
        event_name="external_course_creation_completed",
        attribution=_identity(),
    )
    server_analytics.track_external_client_event(
        app,
        event_name="external_course_creation_completed",
        attribution=None,
    )

    assert submit.called is False


def test_http_and_unicode_versions_are_rejected_without_interrupting(
    app: object, monkeypatch: object
) -> None:
    submitted: list[object] = []
    monkeypatch.setattr(
        server_analytics._EXECUTOR,
        "submit",
        lambda *_args: submitted.append(object()),
    )
    settings = {
        "ANALYTICS_UMAMI_SCRIPT": "http://analytics.example.test/script.js",
        "ANALYTICS_UMAMI_SITE_ID": "website-id",
    }
    monkeypatch.setattr(
        server_analytics,
        "get_config",
        lambda key, default="": settings.get(key, default),
    )

    server_analytics.track_external_client_event(
        app,
        event_name="external_device_authorization_requested",
        attribution=_identity("１２３４５６７８９０"),
    )

    assert submitted == []
    assert server_analytics._version_bucket("１２３４５６７８９０") == "unknown"


def test_persisted_config_lookup_failure_is_fail_open(
    app: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(
        server_analytics,
        "get_config",
        lambda *_args: (_ for _ in ()).throw(LookupError),
    )
    monkeypatch.setattr(
        server_analytics._EXECUTOR,
        "submit",
        lambda *_args: pytest.fail("event should not be queued"),
    )

    server_analytics.track_external_client_event(
        app,
        event_name="external_device_authorization_requested",
        attribution=_identity(),
    )


def test_delivery_swallows_network_failures(monkeypatch: object) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError

    monkeypatch.setattr(server_analytics.requests, "post", fail)

    server_analytics._deliver("https://analytics.example.test/api/send", {})
