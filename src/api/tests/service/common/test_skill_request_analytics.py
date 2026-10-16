"""Protect Skill request attribution, authentication, and response boundaries."""

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

HEADERS = {
    "Token": "header-token",
    "X-AI-Shifu-Skill": "ai-shifu-course-creator",
    "X-AI-Shifu-Skill-Version": "2.7.1",
    "X-AI-Shifu-Caller-Agent": "codex",
}
COURSE = "/api/shifu/shifus/private-course"


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    recorded = []
    monkeypatch.setattr(
        analytics,
        "track_skill_request_event",
        lambda _app, **kwargs: recorded.append(kwargs),
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
            "operation": "course_list",
            "outcome": "success",
            "duration_ms": 250,
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
        {**HEADERS, "X-AI-Shifu-Caller-Agent": "codex, cursor"},
        {**HEADERS, "X-AI-Shifu-Caller-Agent": ""},
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
        headers={**HEADERS, "X-AI-Shifu-Caller-Agent": "unknown"},
    )
    assert response.get_json(force=True)["code"] == 0
    assert len(events) == 1
    assert events[0]["caller_agent"] == "unknown"


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

    monkeypatch.setattr(analytics, "track_skill_request_event", fail)
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
        assert any(
            rule.endpoint == endpoint and method in rule.methods for rule in rules
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
