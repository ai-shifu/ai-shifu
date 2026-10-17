"""Protect Skill request attribution, authentication, and response boundaries."""

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Response, g, request
from flaskr.route import creator_analytics, user
from flaskr.service.common import skill_request_analytics as analytics
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu import route as shifu
from werkzeug.routing import Rule

HEADERS = {
    "Token": "header-token",
    "X-AI-Shifu-Skill": "ai-shifu-course-creator",
    "X-AI-Shifu-Skill-Version": "2.7.1",
    "X-AI-Shifu-Caller-Agent": "codex",
    "X-AI-Shifu-Caller-Agent-Name": "Codex",
}
COURSE = "/api/shifu/shifus/private-course"


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    recorded = []
    monkeypatch.setattr(
        analytics,
        "track_cli_request_pageview",
        lambda _app, **kwargs: recorded.append(kwargs),
    )
    monkeypatch.setattr(
        analytics,
        "now_utc",
        lambda: datetime(2026, 10, 17, tzinfo=UTC).replace(tzinfo=None),
    )
    teacher = SimpleNamespace(
        user_id="authenticated-user", is_creator=True, language="en-US"
    )
    monkeypatch.setattr(user, "validate_user", lambda _app, _token: teacher)
    monkeypatch.setattr(shifu, "shifu_permission_verification", lambda *_args: True)
    monkeypatch.setattr(shifu, "get_shifu_creator_bid", lambda *_args: "teacher")
    monkeypatch.setattr(shifu, "get_shifu_draft_list", lambda *_args: [])
    return recorded


def test_one_event_uses_authenticated_cookie_identity_and_bounded_metadata(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
) -> None:
    seen_tokens = []

    def authenticate(_app: object, token: str) -> SimpleNamespace:
        seen_tokens.append(token)
        return SimpleNamespace(user_id="cookie-user", language="en-US", is_creator=True)

    monkeypatch.setattr(user, "validate_user", authenticate)
    moments = iter([10.0, 10.25])
    monkeypatch.setattr(analytics, "monotonic", lambda: next(moments))
    test_client.set_cookie("token", "cookie-token")
    response = test_client.get(
        "/api/shifu/shifus?token=query-token&private_query=secret",
        headers={**HEADERS, "X-User-ID": "forged-user", "X-Model": "private-model"},
    )
    assert response.get_json(force=True)["code"] == 0
    assert seen_tokens == ["cookie-token"]
    assert events == [
        {
            "user_id": "cookie-user",
            "skill_version": "2.7.1",
            "caller_agent": "codex",
            "caller_agent_name": "Codex",
            "operation": "course_list",
            "outcome": "success",
            "duration_ms": 250,
            "route_template": "/api/shifu/shifus",
            "method": "GET",
            "timestamp": 1792195200,
        }
    ]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-AI-Shifu-Skill": "ai-shifu-course-creator"},
        {**HEADERS, "X-AI-Shifu-Skill": "different-skill"},
        {**HEADERS, "X-AI-Shifu-Skill-Version": "2.7.1 private-data"},
        {**HEADERS, "X-AI-Shifu-Skill-Version": "２.７.１"},
        {**HEADERS, "X-AI-Shifu-Skill-Version": "1" * 65},
        {**HEADERS, "X-AI-Shifu-Caller-Agent": "private-agent-name"},
        {
            **HEADERS,
            "X-AI-Shifu-Caller-Agent": "claude_code",
            "X-AI-Shifu-Caller-Agent-Name": "Claude Code",
        },
        {
            **HEADERS,
            "X-AI-Shifu-Caller-Agent": "hermes",
            "X-AI-Shifu-Caller-Agent-Name": "Hermes Agent",
        },
        {
            **HEADERS,
            "X-AI-Shifu-Caller-Agent": "grok_bot",
            "X-AI-Shifu-Caller-Agent-Name": "Grok Bot",
        },
        {
            **HEADERS,
            "X-AI-Shifu-Caller-Agent": "qoderwork",
            "X-AI-Shifu-Caller-Agent-Name": "QwenWork",
        },
        {**HEADERS, "X-AI-Shifu-Caller-Agent": "codex, cursor"},
        {**HEADERS, "X-AI-Shifu-Caller-Agent": ""},
        {
            key: value
            for key, value in HEADERS.items()
            if key != "X-AI-Shifu-Caller-Agent-Name"
        },
        {**HEADERS, "X-AI-Shifu-Caller-Agent-Name": ""},
        {**HEADERS, "X-AI-Shifu-Caller-Agent-Name": "Private Agent"},
        {**HEADERS, "X-AI-Shifu-Caller-Agent-Name": "Codex (private-data)"},
        {**HEADERS, "X-AI-Shifu-Caller-Agent-Name": "Hermes Agent"},
        {**HEADERS, "X-AI-Shifu-Caller-Agent-Name": "Unknown Agent"},
    ],
)
def test_absent_or_malformed_metadata_preserves_business_response_without_event(
    test_client: object, events: list[dict[str, object]], headers: dict[str, str]
) -> None:
    response = test_client.get(
        "/api/shifu/shifus", headers={"Token": "test", **headers}
    )
    assert response.get_json(force=True)["code"] == 0
    assert events == []


def test_explicit_unknown_agent_is_a_valid_low_cardinality_value(
    test_client: object, events: list[dict[str, object]]
) -> None:
    response = test_client.get(
        "/api/shifu/shifus",
        headers={
            **HEADERS,
            "X-AI-Shifu-Caller-Agent": "unknown",
            "X-AI-Shifu-Caller-Agent-Name": "Unknown Agent",
        },
    )
    assert response.get_json(force=True)["code"] == 0
    assert len(events) == 1
    assert events[0]["caller_agent"] == "unknown"
    assert events[0]["caller_agent_name"] == "Unknown Agent"


def test_failed_authentication_does_not_report_client_claimed_identity(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
) -> None:
    def reject(_app: object, _token: str) -> None:
        message = "not signed in"
        raise AppError(message, ERROR_CODE["server.user.userNotLogin"])

    monkeypatch.setattr(user, "validate_user", reject)
    response = test_client.get("/api/shifu/shifus", headers=HEADERS)
    assert response.get_json(force=True)["code"] != 0
    assert events == []


@pytest.mark.parametrize(
    ("body", "status", "outcome"),
    [
        ('{"code":0,"data":{"private":"secret"}}', 200, "success"),
        ('{"code":123,"message":"private error"}', 200, "failure"),
        ('{"code":0}', 503, "failure"),
        ('{"data":{"private":"secret"}}', 200, "failure"),
        ('{"code":false}', 200, "failure"),
        ('{"code":"0"}', 200, "failure"),
        ("broken json", 200, "failure"),
    ],
)
def test_outcome_reads_only_envelope_and_preserves_http_response(
    app: object,
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
    body: str,
    status: int,
    outcome: str,
) -> None:
    monkeypatch.setitem(
        app.view_functions,
        "get_shifu_list_api",
        lambda: Response(body, status=status, mimetype="application/json"),
    )
    response = test_client.get("/api/shifu/shifus", headers=HEADERS)
    assert response.status_code == status
    assert response.get_data(as_text=True) == body
    assert len(events) == 1
    assert events[0]["outcome"] == outcome


def test_actual_business_conflict_is_failure_even_with_http_200(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
) -> None:
    monkeypatch.setattr(shifu, "save_shifu_mdflow", lambda *_args: {"conflict": True})
    response = test_client.post(
        f"{COURSE}/outlines/private-outline/mdflow",
        json={"data": "private content", "base_revision": 1},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.get_json()["code"] == ERROR_CODE["server.shifu.draftConflict"]
    assert len(events) == 1
    assert events[0]["operation"] == "content_save"
    assert events[0]["outcome"] == "failure"
    assert events[0]["route_template"] == (
        "/api/shifu/shifus/:shifu_bid/outlines/:outline_bid/mdflow"
    )
    assert events[0]["method"] == "POST"
    assert "private" not in str(events)


@pytest.mark.parametrize(
    ("method", "path", "handler", "operation", "body"),
    [
        (
            "PUT",
            "/api/shifu/shifus",
            "create_shifu_draft",
            "course_create",
            {"name": "Private name"},
        ),
        ("POST", f"{COURSE}/publish", "publish_shifu_draft", "course_publish", {}),
    ],
)
def test_new_request_contract_suppresses_legacy_course_event_family(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
    method: str,
    path: str,
    handler: str,
    operation: str,
    body: dict[str, object],
) -> None:
    legacy = Mock()
    monkeypatch.setattr(shifu, "track_external_client_event", legacy)
    monkeypatch.setattr(shifu, handler, lambda *_args: {"shifu_bid": "course"})
    monkeypatch.setattr(
        shifu, "_resolve_publish_base_url", lambda *_args: "https://example.test"
    )
    response = test_client.open(path, method=method, json=body, headers=HEADERS)
    assert response.get_json(force=True)["code"] == 0
    legacy.assert_not_called()
    assert len(events) == 1
    assert events[0]["operation"] == operation


@pytest.mark.parametrize("agent_name", [None, "Private Agent", "Hermes Agent"])
def test_invalid_cli_display_metadata_preserves_legacy_course_events(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
    agent_name: str | None,
) -> None:
    legacy = Mock()
    monkeypatch.setattr(shifu, "track_external_client_event", legacy)
    monkeypatch.setattr(
        shifu,
        "get_session_skill_attribution_by_reference",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        shifu, "create_shifu_draft", lambda *_args: {"shifu_bid": "course"}
    )
    headers = {**HEADERS}
    if agent_name is None:
        headers.pop("X-AI-Shifu-Caller-Agent-Name")
    else:
        headers["X-AI-Shifu-Caller-Agent-Name"] = agent_name
    response = test_client.put(
        "/api/shifu/shifus", json={"name": "Private name"}, headers=headers
    )
    assert response.get_json(force=True)["code"] == 0
    assert events == []
    assert [call.kwargs["event_name"] for call in legacy.call_args_list] == [
        "external_course_creation_started",
        "external_course_creation_completed",
    ]


def test_upload_is_observed_without_collecting_file_names_or_contents(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
) -> None:
    monkeypatch.setattr(
        shifu, "upload_file", lambda *_args: "https://private.test/file"
    )
    response = test_client.post(
        "/api/shifu/upfile",
        data={"file": (BytesIO(b"private file content"), "private-file.txt")},
        headers=HEADERS,
    )
    assert response.get_json(force=True)["code"] == 0
    assert len(events) == 1
    assert events[0]["operation"] == "asset_upload"
    assert "private" not in str(events)


@pytest.mark.parametrize(
    ("path", "handler", "operation"),
    [
        ("query", "run_dsl", "analytics_query"),
        ("credit-detail", "run_credit_detail", "analytics_credit_detail"),
    ],
)
def test_creator_analytics_routes_use_same_account_and_request_contract(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
    path: str,
    handler: str,
    operation: str,
) -> None:
    monkeypatch.setattr(creator_analytics, handler, lambda *_args: {"rows": []})
    response = test_client.post(
        f"/api/creator-analytics/{path}", json={"private": "query"}, headers=HEADERS
    )
    assert response.get_json(force=True)["code"] == 0
    assert len(events) == 1
    assert events[0]["user_id"] == "authenticated-user"
    assert events[0]["operation"] == operation


def test_export_prepared_response_is_success_without_reading_download(
    app: object,
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
) -> None:
    def export(_app: object, _course: str, path: str) -> None:
        Path(path).write_text('{"private":"course content"}')

    monkeypatch.setattr(shifu, "export_shifu", export)
    response = test_client.get(f"{COURSE}/export", headers=HEADERS)
    assert response.status_code == 200
    assert response.get_data() == b'{"private":"course content"}'
    assert len(events) == 1
    assert events[0]["operation"] == "course_export"
    assert events[0]["outcome"] == "success"

    def unreadable_stream() -> object:
        pytest.fail("analytics must not consume download streams")
        yield b"unreachable"

    download = Response(
        unreadable_stream(), mimetype="application/json", direct_passthrough=True
    )
    download.headers["Content-Disposition"] = 'attachment; filename="private.json"'
    with app.test_request_context():
        assert analytics._request_outcome(download, "course_export") == "success"


def test_export_error_envelope_is_failure_and_other_streams_are_not_consumed(
    app: object,
) -> None:
    response = Response('{"code":1}', mimetype="application/json")
    assert analytics._request_outcome(response, "course_export") == "failure"
    unread = []

    def stream() -> object:
        unread.append(True)
        yield b'{"code":0}'

    response = Response(stream(), mimetype="application/json")
    with app.test_request_context():
        assert analytics._request_outcome(response, "course_list") == "failure"
    assert unread == []


def test_sender_failure_preserves_successful_operation(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        message = "sender unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(analytics, "track_cli_request_pageview", fail)
    response = test_client.get("/api/shifu/shifus", headers=HEADERS)
    assert response.get_json(force=True)["code"] == 0
    assert events == []


def test_reprocessing_response_does_not_duplicate_the_terminal_event(
    app: object,
    events: list[dict[str, object]],
) -> None:
    finish = next(
        hook
        for hook in app.after_request_funcs[None]
        if hook.__name__ == "finish_skill_request_analytics"
    )
    with app.test_request_context("/api/shifu/shifus", headers=HEADERS):
        g.skill_request_analytics = analytics._request_metadata()
        g.authenticated_session_attribution = "authenticated-session"
        request.user = SimpleNamespace(user_id="authenticated-user")
        response = Response('{"code":0}')
        assert finish(response) is response
        assert finish(response) is response
    assert len(events) == 1


def test_only_exact_allowlisted_methods_can_emit_request_events(
    app: object, test_client: object, events: list[dict[str, object]]
) -> None:
    rules = list(app.url_map.iter_rules())
    for endpoint, method in analytics.SKILL_API_OPERATIONS:
        matching = [
            rule
            for rule in rules
            if rule.endpoint == endpoint and method in rule.methods
        ]
        assert matching
        operation = analytics.SKILL_API_OPERATIONS[(endpoint, method)]
        for rule in matching:
            assert (
                analytics.safe_skill_route_template(rule, operation, method)
                == (analytics.SKILL_API_ROUTE_TEMPLATES[operation])
            )
    # Flask automatically supplies HEAD and OPTIONS, but neither is a Skill action.
    response = test_client.head("/api/shifu/shifus", headers=HEADERS)
    assert response.status_code == 200
    response = test_client.options("/api/shifu/shifus", headers=HEADERS)
    assert response.status_code == 200
    response = test_client.get("/api/config", headers=HEADERS)
    assert response.status_code == 200
    response = test_client.get("/not-an-api", headers=HEADERS)
    assert response.status_code == 200
    assert events == []


@pytest.mark.parametrize(
    "rule_path",
    [
        "/api/shifu/shifus/<shifu_bid>/detail",
        "/api/shifu/shifus/<uuid:shifu_bid>/detail",
        "/api/shifu/shifus/<any(one,two):shifu_bid>/detail",
    ],
)
def test_route_templates_remove_dynamic_values_and_converter_details(
    rule_path: str,
) -> None:
    rule = Rule(rule_path, endpoint="get_shifu_detail_api", methods=["GET"])
    assert analytics.safe_skill_route_template(rule, "course_get", "GET") == (
        "/api/shifu/shifus/:shifu_bid/detail"
    )


@pytest.mark.parametrize(
    ("rule", "operation", "method"),
    [
        (None, "course_get", "GET"),
        (
            Rule(
                "/api/shifu/shifus/private-course/detail",
                endpoint="get_shifu_detail_api",
                methods=["GET"],
            ),
            "course_get",
            "GET",
        ),
        (
            Rule(
                "/api/shifu/shifus/<shifu_bid>/detail?token=secret",
                endpoint="get_shifu_detail_api",
                methods=["GET"],
            ),
            "course_get",
            "GET",
        ),
        (
            Rule(
                "/api/shifu/shifus/<shifu_bid>/detail",
                endpoint="unlisted",
                methods=["GET"],
            ),
            "course_get",
            "GET",
        ),
        (
            Rule(
                "/api/shifu/shifus/<shifu_bid>/detail",
                endpoint="get_shifu_detail_api",
                methods=["POST"],
            ),
            "course_get",
            "GET",
        ),
    ],
)
def test_missing_or_unsafe_route_never_falls_back_to_request_path(
    rule: Rule | None, operation: str, method: str
) -> None:
    assert analytics.safe_skill_route_template(rule, operation, method) is None


def test_unsafe_route_skips_telemetry_but_retains_legacy_suppression(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
) -> None:
    legacy = Mock()
    monkeypatch.setattr(analytics, "safe_skill_route_template", lambda *_args: None)
    monkeypatch.setattr(shifu, "track_external_client_event", legacy)
    monkeypatch.setattr(
        shifu, "create_shifu_draft", lambda *_args: {"shifu_bid": "course"}
    )
    response = test_client.put(
        "/api/shifu/shifus?private_query=secret",
        json={"name": "Private name"},
        headers=HEADERS,
    )
    assert response.get_json(force=True)["code"] == 0
    assert events == []
    legacy.assert_not_called()


def test_response_timestamp_is_utc_under_non_utc_process_timezone(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict[str, object]],
) -> None:
    import os
    import time

    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is unavailable on this platform")
    original_timezone = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "Pacific/Honolulu")
    time.tzset()
    try:
        response = test_client.get("/api/shifu/shifus", headers=HEADERS)
        assert response.get_json(force=True)["code"] == 0
        assert events[0]["timestamp"] == 1792195200
    finally:
        if original_timezone is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_timezone
        time.tzset()
