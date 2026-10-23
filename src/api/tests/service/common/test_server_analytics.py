"""Verify backend Umami delivery stays bounded, private, and fail-open."""

from concurrent.futures import Future
from threading import BoundedSemaphore
from types import SimpleNamespace

import pytest
from flask import request
from flaskr.service.common import analytics_policy, server_analytics
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
        user_id="allowed-user",
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


@pytest.mark.parametrize("sender", ["legacy", "cli"])
def test_excluded_accounts_are_not_queued(
    app: object, monkeypatch: pytest.MonkeyPatch, sender: str
) -> None:
    monkeypatch.setattr(
        analytics_policy, "get_config", lambda *_args: ["excluded-user"]
    )
    monkeypatch.setattr(
        server_analytics._EXECUTOR,
        "submit",
        lambda *_args: pytest.fail("excluded user data must not be queued"),
    )
    monkeypatch.setattr(
        server_analytics,
        "get_config",
        lambda *_args: pytest.fail("excluded user must not reach delivery config"),
    )

    if sender == "legacy":
        server_analytics.track_external_client_event(
            app,
            event_name="external_device_token_collected",
            attribution=_identity(),
            user_id="excluded-user",
        )
    else:
        server_analytics.track_cli_request_pageview(
            app,
            user_id="excluded-user",
            skill_version="2.7.1",
            caller_agent="codex",
            caller_agent_name="Codex",
            operation="course_list",
            outcome="success",
            duration_ms=0,
            route_template="/api/shifu/shifus",
            method="GET",
            timestamp=1792195200,
        )


def test_legacy_sender_uses_only_authenticated_request_user_for_exclusion(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_ids: list[object] = []

    def excluded(user_id: object) -> bool:
        checked_ids.append(user_id)
        return True

    monkeypatch.setattr(server_analytics, "is_umami_user_excluded", excluded)
    monkeypatch.setattr(
        server_analytics._EXECUTOR,
        "submit",
        lambda *_args: pytest.fail("excluded user data must not be queued"),
    )

    with app.test_request_context(
        query_string={"user_id": "query-user"},
        json={"user_id": "body-user"},
        headers={"X-User-Id": "header-user"},
    ):
        request.user = SimpleNamespace(user_id="authenticated-user")
        server_analytics.track_external_client_event(
            app,
            event_name="external_device_authorization_denied",
            attribution=_identity(),
        )
    with app.test_request_context(json={"user_id": "body-user"}):
        server_analytics.track_external_client_event(
            app,
            event_name="external_device_authorization_requested",
            attribution=_identity(),
        )

    assert checked_ids == ["authenticated-user", None]


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
                "headers": {"User-Agent": "Mozilla/5.0 AI-Shifu-Backend/1.0"},
                "timeout": (0.25, 0.5),
            },
        )
    ]


def test_track_cli_request_pageview_uses_authenticated_id_and_exact_private_payload(
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
    server_analytics.track_cli_request_pageview(
        app,
        user_id="authenticated-user",
        skill_version="2.7.1",
        caller_agent="grok-bot",
        caller_agent_name="Grok Bot",
        operation="content_save",
        outcome="success",
        duration_ms=250,
        route_template="/api/shifu/shifus/:shifu_bid/outlines/:outline_bid/mdflow",
        method="POST",
        timestamp=1792195200,
    )
    assert len(submitted) == 1
    delivery, collector, identity, pageview, user_agent = submitted[0]
    assert delivery is server_analytics._deliver_skill_request
    assert collector == "https://analytics.example.test/api/send"
    assert user_agent == "Mozilla/5.0 AI-Shifu-CLI/2.7.1 (Grok)"
    assert identity == {
        "website": "website-id",
        "id": "authenticated-user",
        "timestamp": 1792195200,
        "browser": "AI-Shifu CLI",
        "os": "Grok Bot",
        "device": "desktop",
    }
    assert pageview == {
        **identity,
        "hostname": "server.ai-shifu",
        "url": "/api/shifu/shifus/:shifu_bid/outlines/:outline_bid/mdflow",
        "tag": "skill_api_request_v2",
        "data": {
            "skill_id": "ai-shifu-course-creator",
            "skill_version_major": "v2",
            "caller_agent": "grok-bot",
            "operation": "content_save",
            "method": "POST",
            "outcome": "success",
            "duration_ms": 250,
        },
    }
    # Exact equality excludes raw environment, prompts, tokens, model names,
    # request URLs/query strings, course IDs, file names, and error text.


@pytest.mark.parametrize("capacity_full", [True, False])
def test_track_cli_request_pageview_queue_saturation_or_submit_failure_is_fail_open(
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
    server_analytics.track_cli_request_pageview(
        app,
        user_id="authenticated-user",
        skill_version="2.7.1",
        caller_agent="unknown",
        caller_agent_name="Unknown Agent",
        operation="course_list",
        outcome="success",
        duration_ms=1,
        route_template="/api/shifu/shifus",
        method="GET",
        timestamp=1792195200,
    )
    assert submitted == ([] if capacity_full else [True])
    if capacity_full:
        capacity.release()
    assert capacity.acquire(blocking=False)
    capacity.release()


@pytest.mark.parametrize(
    ("caller_agent", "os_name", "ua_name"),
    [
        ("crush", "Crush", "Crush"),
        ("hermes-agent", "Hermes Agent", "Hermes"),
        ("kilo-code", "Kilo Code", "Kilo Code"),
        ("trae", "TRAE", "TRAE"),
        ("vtcode", "VT Code", "VT Code"),
        ("workbuddy", "WorkBuddy", "WorkBuddy"),
        ("grok-bot", "Grok Bot", "Grok"),
        ("qwenwork", "QwenWork", "QwenWork"),
        ("cue", "Cue", "Cue"),
        ("muse", "Muse", "Muse"),
        ("manus", "Manus", "Manus"),
        ("doubao-work", "Doubao Work", "Doubao Work"),
        ("kimi", "Kimi Code", "Kimi Code"),
        ("grok-build", "Grok Build", "Grok-Build"),
        ("gemini-cli", "Gemini CLI", "Gemini CLI"),
        ("cline", "Cline", "Cline"),
        ("codex", "Codex", "Codex"),
        ("antigravity", "Antigravity", "Antigravity"),
        ("augment-cli", "Augment CLI", "Augment CLI"),
        ("opencode", "opencode", "opencode"),
        ("goose", "Goose", "Goose"),
        ("junie", "Junie", "Junie"),
        ("pi", "Pi", "Pi"),
        ("cowork", "Claude Cowork", "Claude Cowork"),
        ("claude-code", "Claude Code", "Claude-Code"),
        ("cursor-cli", "Cursor CLI", "Cursor CLI"),
        ("kiro", "Kiro", "Kiro"),
        ("openclaw", "OpenClaw", "OpenClaw"),
        ("github-copilot", "GitHub Copilot", "GitHub Copilot"),
        ("replit", "Replit", "Replit"),
        ("devin", "Devin", "Devin"),
        ("cursor", "Cursor", "Cursor"),
        ("zed", "Zed", "Zed"),
        ("hi", "hi", "hi"),
        ("sandbase-harness", "SandBase Harness", "SandBase Harness"),
        ("unknown", "Unknown Agent", "Unknown"),
    ],
)
@pytest.mark.parametrize("skill_version", ["2.7.1", "2.7.2"])
def test_track_cli_request_pageview_uses_cli_display_name_and_real_version(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    caller_agent: str,
    os_name: str,
    ua_name: str,
    skill_version: str,
) -> None:
    submitted = []

    def submit(*args: object) -> Future[None]:
        submitted.append(args)
        future: Future[None] = Future()
        future.set_result(None)
        return future

    monkeypatch.setattr(server_analytics._EXECUTOR, "submit", submit)
    monkeypatch.setattr(
        server_analytics,
        "get_config",
        lambda key, _default: (
            "https://analytics.example.test/script.js"
            if key == "ANALYTICS_UMAMI_SCRIPT"
            else "same-web-website"
        ),
    )
    server_analytics.track_cli_request_pageview(
        app,
        user_id="same-authenticated-account",
        skill_version=skill_version,
        caller_agent=caller_agent,
        caller_agent_name=os_name,
        operation="course_list",
        method="GET",
        outcome="success",
        duration_ms=1,
        route_template="/api/shifu/shifus",
        timestamp=1792195200,
    )
    assert len(submitted) == 1
    _, _, identity, pageview, user_agent = submitted[0]
    assert identity["os"] == pageview["os"] == os_name
    assert identity["id"] == pageview["id"] == "same-authenticated-account"
    assert user_agent == f"Mozilla/5.0 AI-Shifu-CLI/{skill_version} ({ua_name})"
    assert "name" not in pageview
    assert "data" not in identity


@pytest.mark.parametrize("identify_failure", [False, True])
def test_skill_delivery_attempts_identify_then_pageview_without_cache(
    monkeypatch: pytest.MonkeyPatch, identify_failure: bool
) -> None:
    calls = []

    def post(*args: object, **kwargs: object) -> SimpleNamespace:
        calls.append((args, kwargs))
        if identify_failure and len(calls) == 1:
            raise TimeoutError
        return SimpleNamespace(status_code=200, json=lambda: {"cache": "discard-me"})

    monkeypatch.setattr(server_analytics.requests, "post", post)
    identity = {
        "website": "site",
        "id": "authenticated-user",
        "browser": "AI-Shifu CLI",
        "os": "Codex",
        "device": "desktop",
        "timestamp": 1792195200,
    }
    pageview = {**identity, "hostname": "server.ai-shifu", "url": "/api/shifu/shifus"}
    server_analytics._deliver_skill_request(
        "https://analytics.example.test/api/send",
        identity,
        pageview,
        "Mozilla/5.0 AI-Shifu-CLI/2.7.1 (Codex)",
    )
    assert calls == [
        (
            ("https://analytics.example.test/api/send",),
            {
                "json": {"type": kind, "payload": payload},
                "headers": {"User-Agent": "Mozilla/5.0 AI-Shifu-CLI/2.7.1 (Codex)"},
                "timeout": (0.25, 0.5),
            },
        )
        for kind, payload in (("identify", identity), ("event", pageview))
    ]


@pytest.mark.parametrize(
    ("status", "body", "acknowledged"),
    [
        (200, {"beep": "boop"}, False),
        (200, {}, False),
        (200, [], False),
        (200, {"cache": ""}, False),
        (503, {"cache": "not-accepted"}, False),
        (200, {"cache": "accepted"}, True),
    ],
)
def test_skill_collector_acknowledgement_rejects_bot_filter_and_invalid_responses(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    body: object,
    acknowledged: bool,
) -> None:
    monkeypatch.setattr(
        server_analytics.requests,
        "post",
        lambda *_args, **_kwargs: SimpleNamespace(
            status_code=status, json=lambda: body
        ),
    )
    assert (
        server_analytics._send_skill_payload(
            "https://analytics.example.test/api/send", "event", {}, "fixed-ua"
        )
        is acknowledged
    )


@pytest.mark.parametrize(
    "invalid",
    [
        {"caller_agent": "private-agent"},
        {"caller_agent": "claude_code"},
        {"caller_agent": "hermes"},
        {"caller_agent": "grok_bot"},
        {"caller_agent": "qoderwork"},
        {"caller_agent_name": "private-agent"},
        {"caller_agent_name": "Codex"},
        {"caller_agent_name": "Unknown Agent (private-data)"},
        {"skill_version": "2.7.1 (private-data)"},
        {"skill_version": "2.7.1-rc.1"},
        {"skill_version": "1.2.3+" + "a" * 58},
        {"skill_version": "1234567.2.3"},
        {"skill_version": "2.7.1\r\nInjected: true"},
        {"skill_version": "1.2.3+" + "a" * 59},
        {"operation": "private-operation"},
        {"method": "POST"},
        {"route_template": "/api/shifu/shifus/private-resource"},
        {"route_template": "/api/shifu/shifus?token=secret"},
        {"timestamp": True},
        {"timestamp": -1},
        {"duration_ms": -1},
        {"duration_ms": True},
        {"user_id": ""},
    ],
)
def test_invalid_skill_contract_is_not_queued(
    app: object, monkeypatch: pytest.MonkeyPatch, invalid: dict[str, object]
) -> None:
    monkeypatch.setattr(
        server_analytics._EXECUTOR,
        "submit",
        lambda *_args: pytest.fail("invalid contract must not be queued"),
    )
    arguments = {
        "user_id": "authenticated-user",
        "skill_version": "2.7.1",
        "caller_agent": "unknown",
        "caller_agent_name": "Unknown Agent",
        "operation": "course_list",
        "outcome": "success",
        "duration_ms": 1,
        "route_template": "/api/shifu/shifus",
        "method": "GET",
        "timestamp": 1792195200,
        **invalid,
    }
    server_analytics.track_cli_request_pageview(app, **arguments)


def test_skill_pair_occupies_one_queue_slot_and_keeps_captured_timestamp(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    capacity = BoundedSemaphore(1)
    future: Future[None] = Future()
    submitted = []
    posted = []

    def submit(*args: object) -> Future[None]:
        submitted.append(args)
        return future

    monkeypatch.setattr(server_analytics, "_CAPACITY", capacity)
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
    arguments = {
        "user_id": "authenticated-user",
        "skill_version": "2.7.1",
        "caller_agent": "codex",
        "caller_agent_name": "Codex",
        "operation": "course_list",
        "outcome": "success",
        "duration_ms": 1,
        "route_template": "/api/shifu/shifus",
        "method": "GET",
        "timestamp": 1792195200,
    }
    server_analytics.track_cli_request_pageview(app, **arguments)
    server_analytics.track_cli_request_pageview(app, **arguments)
    assert len(submitted) == 1
    assert not capacity.acquire(blocking=False)

    def post(_url: object, **kwargs: object) -> SimpleNamespace:
        posted.append(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: {"cache": "discarded"})

    monkeypatch.setattr(server_analytics.requests, "post", post)
    delivery, *queued_arguments = submitted[0]
    # Executing the delayed job must use response time, never worker time.
    delivery(*queued_arguments)
    assert [call["json"]["payload"]["timestamp"] for call in posted] == [
        1792195200,
        1792195200,
    ]
    future.set_result(None)
    assert capacity.acquire(blocking=False)
    capacity.release()


@pytest.mark.parametrize("config_error", [False, True])
def test_skill_missing_configuration_is_fail_open(
    app: object, monkeypatch: pytest.MonkeyPatch, config_error: bool
) -> None:
    def get_config(*_args: object) -> str:
        if config_error:
            raise LookupError
        return ""

    monkeypatch.setattr(server_analytics, "get_config", get_config)
    monkeypatch.setattr(
        server_analytics._EXECUTOR,
        "submit",
        lambda *_args: pytest.fail("missing configuration"),
    )
    server_analytics.track_cli_request_pageview(
        app,
        user_id="authenticated-user",
        skill_version="2.7.1",
        caller_agent="codex",
        caller_agent_name="Codex",
        operation="course_list",
        outcome="success",
        duration_ms=0,
        route_template="/api/shifu/shifus",
        method="GET",
        timestamp=1792195200,
    )
