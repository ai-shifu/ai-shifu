"""Verify backend Umami delivery stays bounded, private, and fail-open."""

from concurrent.futures import Future
from types import SimpleNamespace

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
    app.config["ANALYTICS_UMAMI_SCRIPT"] = "https://analytics.example.test/script.js"
    app.config["ANALYTICS_UMAMI_SITE_ID"] = "website-id"

    server_analytics.track_external_client_event(
        app,
        event_name="external_course_creation_completed",
        attribution=_identity(),
        user_id="user-bid-1",
    )

    assert len(submitted) == 1
    _deliver, collector_url, payload = submitted[0]
    assert collector_url == "https://analytics.example.test/api/send"
    assert payload == {
        "website": "website-id",
        "hostname": "server.ai-shifu",
        "url": "/backend/external-client",
        "name": "external_course_creation_completed",
        "id": "user-bid-1",
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
        "url",
        "referrer",
    ):
        assert prohibited_key not in payload["data"]


def test_missing_config_or_attribution_is_a_noop(
    app: object, monkeypatch: object
) -> None:
    submit = SimpleNamespace(called=False)

    def unexpected_submit(*_args: object) -> None:
        submit.called = True

    monkeypatch.setattr(server_analytics._EXECUTOR, "submit", unexpected_submit)
    app.config["ANALYTICS_UMAMI_SCRIPT"] = ""
    app.config["ANALYTICS_UMAMI_SITE_ID"] = ""

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


def test_delivery_swallows_network_failures(monkeypatch: object) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError

    monkeypatch.setattr(server_analytics.requests, "post", fail)

    server_analytics._deliver("https://analytics.example.test/api/send", {})
