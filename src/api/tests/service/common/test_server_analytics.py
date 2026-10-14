"""Verify backend Umami delivery stays bounded, private, and fail-open."""

from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock

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


def test_shared_event_queues_without_config_reads_and_delivers_exact_payload(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read config and send only on the bounded worker, with no request context data."""
    submitted = []
    settings = {
        "ANALYTICS_UMAMI_SCRIPT": "https://analytics.example.test/script.js",
        "ANALYTICS_UMAMI_SITE_ID": "website-id",
    }
    config = Mock(side_effect=lambda key, default="": settings.get(key, default))
    monkeypatch.setattr(server_analytics, "get_config", config)

    def submit(*args: object) -> Future:
        submitted.append(args)
        future = Future()
        future.set_result(None)
        return future

    monkeypatch.setattr(server_analytics._EXECUTOR, "submit", submit)
    sent = Mock()
    monkeypatch.setattr(server_analytics.requests, "post", sent)
    data = {"surface": "learner", "learning_mode": "read"}
    server_analytics.queue_server_event(
        app,
        event_name="learner_computed_example_streamed",
        route="/backend/lesson/computed-example",
        data=data,
    )
    config.assert_not_called()
    sent.assert_not_called()
    data["learning_mode"] = "private-mutated-value"
    worker, *args = submitted[0]
    worker(*args)
    assert sent.call_args.kwargs["json"] == {
        "type": "event",
        "payload": {
            "website": "website-id",
            "hostname": "server.ai-shifu",
            "url": "/backend/lesson/computed-example",
            "name": "learner_computed_example_streamed",
            "data": {"surface": "learner", "learning_mode": "read"},
        },
    }


@pytest.mark.parametrize(
    "failure", ["capacity", "submit", "config", "missing_config", "network"]
)
def test_shared_product_queue_failures_stay_fail_open(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    """Saturation, rejected work, config and network errors never interrupt callers."""
    from threading import BoundedSemaphore

    capacity = BoundedSemaphore(1)
    monkeypatch.setattr(server_analytics, "_CAPACITY", capacity)
    if failure == "capacity":
        capacity.acquire()
    queued = []

    def submit(*args: object) -> Future:
        if failure == "submit":
            raise RuntimeError
        queued.append(args)
        future = Future()
        future.set_result(None)
        return future

    monkeypatch.setattr(server_analytics._EXECUTOR, "submit", submit)

    def config(key: str, default: str = "") -> str:
        if failure == "config":
            raise LookupError
        if failure == "missing_config":
            return ""
        return {
            "ANALYTICS_UMAMI_SCRIPT": "https://analytics.example.test/script.js",
            "ANALYTICS_UMAMI_SITE_ID": "website-id",
        }.get(key, default)

    monkeypatch.setattr(server_analytics, "get_config", config)
    post = Mock(side_effect=TimeoutError)
    monkeypatch.setattr(server_analytics.requests, "post", post)
    server_analytics.queue_server_event(
        app,
        event_name="learner_computed_example_streamed",
        route="/backend/lesson/computed-example",
        data={"surface": "learner", "learning_mode": "listen"},
    )
    for worker, *args in queued:
        worker(*args)
    assert post.call_count == (1 if failure == "network" else 0)
    if failure == "capacity":
        assert queued == []
        capacity.release()
    assert capacity.acquire(blocking=False)
    capacity.release()


@pytest.mark.parametrize(
    "invalid",
    [
        {"event_name": "private event"},
        {"route": "https://private.test/?token=secret"},
        {"data": {"nested": {"private": "value"}}},
        {"data": {"value": float("nan")}},
        {"data": {"value": "x" * 241}},
        {"data": {"bad-key": "value"}},
        {"data": {1: "value"}},
        {"data": {f"field{i}": "x" for i in range(31)}},
        {"data": {f"field{i}": "x" * 200 for i in range(6)}},
    ],
)
def test_shared_queue_refuses_malformed_payload_without_transport(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    invalid: dict,
) -> None:
    """Reject invalid delivery shapes instead of silently altering their semantics."""
    submit = Mock()
    monkeypatch.setattr(server_analytics._EXECUTOR, "submit", submit)
    arguments = {
        "event_name": "learner_computed_example_streamed",
        "route": "/backend/lesson/computed-example",
        "data": {"surface": "learner", "learning_mode": "read"},
    }
    arguments.update(invalid)
    server_analytics.queue_server_event(app, **arguments)
    submit.assert_not_called()


def test_shared_queue_releases_capacity_after_asynchronous_worker_failure(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pending event consumes one slot; worker failure frees it for later events."""
    from threading import BoundedSemaphore

    monkeypatch.setattr(server_analytics, "_CAPACITY", BoundedSemaphore(1))
    futures = []

    def submit(*_args: object) -> Future:
        future = Future()
        futures.append(future)
        return future

    monkeypatch.setattr(server_analytics._EXECUTOR, "submit", submit)

    def emit() -> None:
        server_analytics.queue_server_event(
            app,
            event_name="learner_computed_example_streamed",
            route="/backend/lesson/computed-example",
            data={"surface": "learner", "learning_mode": "read"},
        )

    emit()
    emit()
    assert len(futures) == 1
    futures[0].set_exception(RuntimeError())
    emit()
    assert len(futures) == 2
    futures[1].set_result(None)
