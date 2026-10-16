"""Verify backend Umami delivery stays bounded, private, and fail-open."""

from concurrent.futures import Future
from threading import BoundedSemaphore
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


def test_delivery_uses_application_identity_accepted_by_collector_bot_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        server_analytics.requests,
        "post",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    payload = {"website": "site", "name": "skill_api_request_v1"}
    server_analytics._deliver("https://analytics.example.test/api/send", payload)
    assert calls == [
        (
            ("https://analytics.example.test/api/send",),
            {
                "json": {"type": "event", "payload": payload},
                "headers": {"User-Agent": "Mozilla/5.0 AIShifu/1.0"},
                "timeout": (0.25, 0.5),
            },
        )
    ]


def test_skill_event_uses_authenticated_distinct_id_and_exact_private_payload(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    submitted = []

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
    server_analytics.track_skill_request_event(
        app,
        user_id="authenticated-user",
        skill_version="2.7.1",
        caller_agent="grok_bot",
        operation="content_save",
        outcome="success",
        duration_ms=250,
    )
    assert len(submitted) == 1
    assert submitted[0][2] == {
        "website": "website-id",
        "hostname": "server.ai-shifu",
        "url": "/backend/skill",
        "name": "skill_api_request_v1",
        "id": "authenticated-user",
        "data": {
            "skill_id": "ai-shifu-course-creator",
            "skill_version_major": "v2",
            "caller_agent": "grok_bot",
            "operation": "content_save",
            "outcome": "success",
            "duration_ms": 250,
        },
    }
    # Exact equality excludes raw environment, prompts, tokens, model names,
    # request URLs/query strings, course IDs, file names, and error text.


@pytest.mark.parametrize("capacity_full", [True, False])
def test_skill_event_queue_saturation_or_submit_failure_is_fail_open(
    app: object, monkeypatch: pytest.MonkeyPatch, capacity_full: bool
) -> None:
    capacity = BoundedSemaphore(1)
    if capacity_full:
        capacity.acquire()
    monkeypatch.setattr(server_analytics, "_CAPACITY", capacity)
    settings = {
        "ANALYTICS_UMAMI_SCRIPT": "https://analytics.example.test/script.js",
        "ANALYTICS_UMAMI_SITE_ID": "website-id",
    }
    monkeypatch.setattr(
        server_analytics,
        "get_config",
        lambda key, default="": settings.get(key, default),
    )
    submitted = []

    def fail(*_args: object) -> None:
        submitted.append(True)
        message = "executor stopped"
        raise RuntimeError(message)

    monkeypatch.setattr(server_analytics._EXECUTOR, "submit", fail)
    server_analytics.track_skill_request_event(
        app,
        user_id="authenticated-user",
        skill_version="2.7.1",
        caller_agent="unknown",
        operation="course_list",
        outcome="success",
        duration_ms=1,
    )
    assert submitted == ([] if capacity_full else [True])
    if capacity_full:
        capacity.release()
    assert capacity.acquire(blocking=False)
    capacity.release()
