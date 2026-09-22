"""Protect authoring HTTP permissions, patch semantics, and revision responses."""

import uuid
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import request
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu import route as shifu_routes
from flaskr.service.shifu.models import AiCourseAuth

PREFIX = "/api/shifu"
COURSE = f"{PREFIX}/shifus/course"
OUTLINE = f"{COURSE}/outlines/outline"
HEADERS = {"Token": "authoring-test-token"}


@pytest.fixture(autouse=True)
def authoring_user(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    user = SimpleNamespace(
        user_id="teacher", is_creator=True, is_operator=False, language="en-US"
    )
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda _app, _token: user)
    monkeypatch.setattr(
        shifu_routes, "shifu_permission_verification", Mock(return_value=True)
    )
    monkeypatch.setattr(
        shifu_routes, "get_shifu_creator_bid", Mock(return_value="teacher")
    )
    return user


@pytest.fixture
def preview_model(monkeypatch: pytest.MonkeyPatch) -> Mock:
    monkeypatch.setattr(shifu_routes, "assert_creator_debug_allowed", Mock())
    monkeypatch.setattr(shifu_routes, "admit_creator_usage", Mock())
    monkeypatch.setattr(
        shifu_routes,
        "get_latest_shifu_draft",
        Mock(
            return_value=SimpleNamespace(
                shifu_bid="course", ask_llm="1", id=1, __tablename__="draft_shifus"
            )
        ),
    )
    resolver = Mock(return_value=("configured-text-model", {}))
    monkeypatch.setattr(shifu_routes, "resolve_course_selection", resolver)
    return resolver


@pytest.mark.parametrize(
    ("method", "path", "service", "body", "arguments"),
    [
        (
            "PUT",
            f"{PREFIX}/shifus",
            "create_shifu_draft",
            {"name": "Course", "description": "Description"},
            ("teacher", "Course", "Description", "", []),
        ),
        (
            "GET",
            f"{COURSE}/detail",
            "get_shifu_draft_info",
            None,
            ("teacher", "course", "https://learning.example"),
        ),
        (
            "POST",
            f"{COURSE}/publish",
            "publish_shifu_draft",
            {},
            ("teacher", "course", "https://learning.example"),
        ),
        (
            "PATCH",
            f"{COURSE}/outlines/reorder",
            "reorder_outline_tree",
            {"outlines": [{"id": "outline"}]},
            ("teacher", "course", [{"id": "outline"}]),
        ),
        (
            "PUT",
            f"{COURSE}/outlines/batch",
            "create_outlines_batch",
            {"outlines": [{"name": "Lesson"}]},
            ("teacher", "course", [{"name": "Lesson"}], ""),
        ),
        (
            "PUT",
            f"{COURSE}/outlines",
            "create_outline",
            {"name": "Lesson", "is_hidden": "TRUE"},
            ("teacher", "course", None, "Lesson", None, None, True),
        ),
        (
            "POST",
            OUTLINE,
            "modify_unit",
            {"name": "Lesson", "is_hidden": "false"},
            ("teacher", "course", "outline", "Lesson", None, None, False, None),
        ),
        ("GET", f"{OUTLINE}/mdflow", "get_shifu_mdflow", None, ("course", "outline")),
        (
            "POST",
            f"{OUTLINE}/mdflow/parse",
            "parse_shifu_mdflow",
            {"data": "Content"},
            ("course", "outline", "Content"),
        ),
        ("GET", f"{COURSE}/outlines", "get_outline_tree", None, ("teacher", "course")),
        (
            "POST",
            f"{PREFIX}/url-upfile",
            "upload_url",
            {"url": "https://example.com/resource"},
            ("teacher", "https://example.com/resource"),
        ),
        (
            "POST",
            f"{PREFIX}/get-video-info",
            "get_video_info",
            {"url": "https://example.com/video"},
            ("teacher", "https://example.com/video"),
        ),
    ],
)
def test_authoring_routes_preserve_service_parameters_and_response_data(
    test_client: object,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    service: str,
    body: dict | None,
    arguments: tuple,
) -> None:
    handler = Mock(return_value={"revision": 3, "items": []})
    monkeypatch.setattr(shifu_routes, service, handler)
    monkeypatch.setattr(
        shifu_routes,
        "_resolve_publish_base_url",
        lambda _app: "https://learning.example",
    )
    response = test_client.open(path, method=method, json=body, headers=HEADERS)
    assert response.get_json(force=True)["data"] == {"revision": 3, "items": []}
    handler.assert_called_once_with(app, *arguments)


@pytest.mark.parametrize(
    ("action", "archived"), [("archive", True), ("unarchive", False)]
)
def test_archive_routes_resolve_legacy_shifu_id_path_and_return_final_state(
    test_client: object,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    archived: bool,
) -> None:
    handler = Mock()
    monkeypatch.setattr(shifu_routes, f"{action}_shifu", handler)
    response = test_client.post(f"{COURSE}/{action}", headers=HEADERS)
    assert response.get_json(force=True)["data"] == {"archived": archived}
    handler.assert_called_once_with(app, "teacher", "course")
    shifu_routes.shifu_permission_verification.assert_called_once_with(
        app, "teacher", "course", "view"
    )


def test_course_list_normalizes_pagination_favorites_and_archive_state(
    test_client: object,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = Mock(return_value={"data": [], "total": 0})
    monkeypatch.setattr(shifu_routes, "get_shifu_draft_list", handler)
    response = test_client.get(
        f"{PREFIX}/shifus?page_index=2&page_size=4&is_favorite=TRUE&archived=true",
        headers=HEADERS,
    )
    assert response.get_json(force=True)["code"] == 0
    handler.assert_called_once()
    assert handler.call_args.args == (app, "teacher", 2, 4, True, True)


@pytest.mark.parametrize(
    "query", ["page_index=bad", "page_size=bad", "page_index=-1", "page_size=0"]
)
def test_course_list_rejects_invalid_pagination(
    test_client: object, query: str
) -> None:
    response = test_client.get(f"{PREFIX}/shifus?{query}", headers=HEADERS)
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


@pytest.mark.parametrize(("raw", "expected"), [("true", True), (False, False)])
def test_favorite_route_normalizes_boolean_values(
    test_client: object,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    raw: object,
    expected: bool,
) -> None:
    handler = Mock(return_value={"favorite": expected})
    monkeypatch.setattr(shifu_routes, "mark_or_unmark_favorite_shifu", handler)
    response = test_client.post(
        f"{COURSE}/favorite", json={"is_favorite": raw}, headers=HEADERS
    )
    assert response.get_json(force=True)["data"] == {"favorite": expected}
    handler.assert_called_once_with(app, "teacher", "course", expected)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PUT", f"{PREFIX}/shifus", {}),
        ("POST", f"{COURSE}/favorite", {"is_favorite": 1}),
        ("PATCH", f"{COURSE}/outlines/reorder", [1]),
        ("PUT", f"{COURSE}/outlines", [1]),
        ("PUT", f"{COURSE}/outlines/batch", [1]),
        ("POST", f"{PREFIX}/url-upfile", {}),
        ("POST", f"{PREFIX}/get-video-info", {}),
    ],
)
def test_authoring_routes_reject_invalid_payload_shapes_or_required_fields(
    test_client: object,
    method: str,
    path: str,
    body: object,
) -> None:
    response = test_client.open(path, method=method, json=body, headers=HEADERS)
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


@pytest.mark.parametrize(
    "body",
    [
        {"ask_enabled_status": "bad"},
        {"ask_enabled_status": -1},
        {"ask_temperature": "bad"},
        {"ask_temperature": -0.1},
        {"ask_temperature": 2.1},
        {"ask_provider_config": "{"},
        {"ask_provider_config": []},
        {"ask_provider_config": {"provider": "unsupported"}},
        {"ask_provider_config": {"mode": "unsupported"}},
        {"ask_provider_config": {"config": []}},
    ],
)
def test_course_details_validate_ask_configuration_before_saving(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    body: dict,
) -> None:
    handler = Mock()
    monkeypatch.setattr(shifu_routes, "save_shifu_draft_info", handler)
    response = test_client.post(f"{COURSE}/detail", json=body, headers=HEADERS)
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )
    handler.assert_not_called()


@pytest.mark.parametrize("provider_config", ["", "{}"])
def test_course_details_normalize_explicit_settings_but_preserve_omitted_fields(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    provider_config: str,
) -> None:
    handler = Mock(return_value={"saved": True})
    monkeypatch.setattr(shifu_routes, "save_shifu_draft_info", handler)
    monkeypatch.setattr(
        shifu_routes,
        "_resolve_publish_base_url",
        lambda _app: "https://learning.example",
    )
    response = test_client.post(
        f"{COURSE}/detail",
        headers=HEADERS,
        json={
            "ask_enabled_status": str(min(shifu_routes.SUPPORTED_ASK_ENABLED_STATUSES)),
            "ask_temperature": "1.5",
            "ask_model": "2",
            "ask_system_prompt": 456,
            "ask_provider_config": provider_config,
            "tts_provider": " MINIMAX ",
            "default_listen_mode_enabled": "true",
            "use_learner_language": "TRUE",
        },
    )
    assert response.get_json(force=True)["data"] == {"saved": True}
    kwargs = handler.call_args.kwargs
    assert kwargs["ask_temperature"] == 1.5
    assert kwargs["ask_model"] == "2"
    assert kwargs["ask_system_prompt"] == "456"
    assert kwargs["tts_provider"] == "minimax"
    assert kwargs["default_listen_mode_enabled"] is True
    assert kwargs["use_learner_language"] is True
    assert kwargs["tts_enabled"] is None
    assert kwargs["tts_speed"] is None
    assert kwargs["tts_pitch"] is None


def test_course_details_reject_provider_specific_invalid_fields(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        shifu_routes,
        "validate_ask_provider_specific_config",
        lambda _provider, _config: (False, "bot_id"),
    )
    response = test_client.post(
        f"{COURSE}/detail", headers=HEADERS, json={"ask_provider_config": {}}
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


@pytest.mark.parametrize(
    ("method", "path", "is_creator"),
    [
        ("GET", f"{PREFIX}/shifus", False),
        ("PUT", f"{PREFIX}/shifus", False),
        ("POST", f"{COURSE}/detail", True),
    ],
)
def test_creator_and_course_permission_denials_stop_authoring_requests(
    test_client: object,
    authoring_user: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    is_creator: bool,
) -> None:
    authoring_user.is_creator = is_creator
    monkeypatch.setattr(
        shifu_routes, "shifu_permission_verification", Mock(return_value=False)
    )
    response = test_client.open(
        path, method=method, json={"name": "Course"}, headers=HEADERS
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.shifu.noPermission"]
    )


@pytest.mark.parametrize(
    ("method", "path", "json_data", "view_args"),
    [
        ("GET", "/?shifu_bid=course&token=query-token", None, {}),
        ("GET", "/?shifu_id=course&token=query-token", None, {}),
        ("POST", "/", {"token": "body-token", "shifu_bid": "course"}, {}),
        ("POST", "/", {"token": "body-token", "shifu_id": "course"}, {}),
    ],
)
def test_permission_decorator_resolves_legacy_query_and_json_identifiers(
    app: object,
    method: str,
    path: str,
    json_data: dict | None,
    view_args: dict,
) -> None:
    handler = Mock(return_value="result")
    decorated = shifu_routes.ShifuTokenValidation(shifu_routes.ShifuPermission.EDIT)(
        handler
    )
    with app.test_request_context(path, method=method, json=json_data):
        request.user = SimpleNamespace(user_id="teacher")
        request.view_args = view_args
        assert decorated() == "result"
    shifu_routes.shifu_permission_verification.assert_called_once_with(
        app, "teacher", "course", "edit"
    )


@pytest.mark.parametrize("path", ["/?shifu_bid=course", "/?token=test"])
def test_permission_decorator_requires_both_token_and_course(
    app: object, path: str
) -> None:
    decorated = shifu_routes.ShifuTokenValidation()(Mock())
    with app.test_request_context(path):
        request.user = SimpleNamespace(user_id="teacher")
        request.view_args = {}
        with pytest.raises(AppError) as error:
            decorated()
    assert error.value.code == ERROR_CODE["server.common.paramsError"]


@pytest.mark.parametrize(
    ("creator", "owner", "expected"),
    [
        (False, "teacher", "server.shifu.noPermission"),
        (True, "", "server.shifu.shifuNotFound"),
        (True, "other", "server.shifu.noPermission"),
    ],
)
def test_sharing_permissions_require_the_actual_course_owner(
    test_client: object,
    authoring_user: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    creator: bool,
    owner: str,
    expected: str,
) -> None:
    authoring_user.is_creator = creator
    monkeypatch.setattr(shifu_routes, "get_shifu_creator_bid", Mock(return_value=owner))
    response = test_client.get(f"{COURSE}/permissions", headers=HEADERS)
    assert response.get_json(force=True)["code"] == ERROR_CODE[expected]


@pytest.mark.parametrize(
    "contact_data",
    [
        " A@Example.com，a@example.com\nB@example.com",
        [None, "A@Example.com", "a@example.com", "B@example.com"],
    ],
)
def test_permission_grants_normalize_google_email_contacts_and_deduplicate(
    test_client: object,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    contact_data: object,
) -> None:
    monkeypatch.setattr(
        shifu_routes, "get_config", lambda _key, _default=None: ["google"]
    )
    handler = Mock(return_value=2)
    monkeypatch.setattr(shifu_routes, "grant_shifu_permissions", handler)
    response = test_client.post(
        f"{COURSE}/permissions/grant",
        headers=HEADERS,
        json={"contact_type": "email", "permission": "edit", "contacts": contact_data},
    )
    assert response.get_json(force=True)["data"] == {"count": 2}
    handler.assert_called_once_with(
        app,
        shifu_bid="course",
        owner_id="teacher",
        contact_type="email",
        contacts=["a@example.com", "b@example.com"],
        permission="edit",
    )


@pytest.mark.parametrize(
    ("body", "methods"),
    [
        (
            {
                "contact_type": "unsupported",
                "permission": "view",
                "contacts": ["a@example.com"],
            },
            "email",
        ),
        (
            {
                "contact_type": "email",
                "permission": "view",
                "contacts": ["a@example.com"],
            },
            "phone",
        ),
        (
            {
                "contact_type": "email",
                "permission": "owner",
                "contacts": ["a@example.com"],
            },
            "email",
        ),
        ({"contact_type": "email", "permission": "view", "contacts": {}}, "email"),
        (
            {"contact_type": "email", "permission": "view", "contacts": ["invalid"]},
            "email",
        ),
        ({"contact_type": "phone", "permission": "view", "contacts": ["123"]}, "phone"),
        (
            {"contact_type": "email", "permission": "view", "contacts": ["a" * 321]},
            "email",
        ),
    ],
)
def test_permission_grants_validate_contact_type_permission_and_identifier(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    body: dict,
    methods: str,
) -> None:
    monkeypatch.setattr(shifu_routes, "get_config", lambda _key, _default=None: methods)
    response = test_client.post(
        f"{COURSE}/permissions/grant", headers=HEADERS, json=body
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


@pytest.mark.parametrize(
    ("user_bid", "expected"),
    [("", "server.common.paramsError"), ("teacher", "server.shifu.noPermission")],
)
def test_permission_removal_requires_a_non_owner_target(
    test_client: object, user_bid: str, expected: str
) -> None:
    response = test_client.post(
        f"{COURSE}/permissions/remove", headers=HEADERS, json={"user_id": user_bid}
    )
    assert response.get_json(force=True)["code"] == ERROR_CODE[expected]


@pytest.mark.parametrize(
    ("operation", "service", "body"),
    [
        ("", "save_shifu_mdflow", {"data": "content", "base_revision": "3"}),
        (
            "/history/restore",
            "restore_shifu_mdflow_history_version",
            {"version_id": "2", "base_revision": "3"},
        ),
    ],
)
def test_mdflow_mutations_preserve_revision_conflicts_as_structured_responses(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    service: str,
    body: dict,
) -> None:
    handler = Mock(return_value={"conflict": True, "meta": {"revision": 7}})
    monkeypatch.setattr(shifu_routes, service, handler)
    response = test_client.post(
        f"{OUTLINE}/mdflow{operation}", headers=HEADERS, json=body
    )
    assert response.status_code == 200
    payload = response.get_json(force=True)
    assert payload["code"] == ERROR_CODE["server.shifu.draftConflict"]
    assert payload["data"] == {"meta": {"revision": 7}}
    assert handler.call_args.args[-1] == 3


def test_mdflow_save_returns_only_the_new_revision_on_success(
    test_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = Mock(return_value={"new_revision": 8})
    monkeypatch.setattr(shifu_routes, "save_shifu_mdflow", handler)
    response = test_client.post(
        f"{OUTLINE}/mdflow", headers=HEADERS, json={"data": "content"}
    )
    assert response.get_json(force=True)["data"] == {"new_revision": 8}


@pytest.mark.parametrize(
    ("operation", "body"),
    [
        ("", {"base_revision": "bad"}),
        ("/history/restore", {"version_id": "bad"}),
        ("/history/restore", {"version_id": 0}),
        ("/history/restore", {"version_id": 1, "base_revision": "bad"}),
    ],
)
def test_mdflow_revision_parameters_must_be_integers(
    test_client: object, operation: str, body: dict
) -> None:
    response = test_client.post(
        f"{OUTLINE}/mdflow{operation}", headers=HEADERS, json=body
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


@pytest.mark.parametrize("limit", ["bad", "0", "201"])
def test_mdflow_history_limits_are_bounded(test_client: object, limit: str) -> None:
    response = test_client.get(
        f"{OUTLINE}/mdflow/history?limit={limit}", headers=HEADERS
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


def test_mdflow_history_forwards_limit_and_version_validation(
    test_client: object, app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = Mock(return_value={"versions": []})
    monkeypatch.setattr(shifu_routes, "get_shifu_mdflow_history", handler)
    response = test_client.get(f"{OUTLINE}/mdflow/history?limit=200", headers=HEADERS)
    assert response.get_json(force=True)["data"] == {"versions": []}
    handler.assert_called_once_with(app, "course", "outline", 200)
    response = test_client.get(f"{OUTLINE}/mdflow/history/0", headers=HEADERS)
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


def test_file_upload_forwards_uploaded_bytes_and_defaults_resource_identifier(
    test_client: object, app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = Mock(return_value={"resource_id": "uploaded"})
    monkeypatch.setattr(shifu_routes, "upload_file", handler)
    response = test_client.post(
        f"{PREFIX}/upfile",
        headers=HEADERS,
        data={"file": (BytesIO(b"content"), "notes.txt")},
    )
    assert response.get_json(force=True)["data"] == {"resource_id": "uploaded"}
    assert handler.call_args.args[:3] == (app, "teacher", "")
    assert handler.call_args.args[3].filename == "notes.txt"


def test_file_upload_requires_a_file(test_client: object) -> None:
    response = test_client.post(f"{PREFIX}/upfile", headers=HEADERS, data={})
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


def test_export_download_cleans_temporary_file_after_response(
    test_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    exported = []

    def export(_app: object, shifu_bid: str, target: str) -> None:
        assert shifu_bid == "course"
        path = Path(target)
        path.write_text('{"course":"export"}')
        exported.append(path)

    monkeypatch.setattr(shifu_routes, "export_shifu", export)
    response = test_client.get(f"{COURSE}/export", headers=HEADERS)
    assert response.status_code == 200
    assert response.get_json(force=True) == {"course": "export"}
    assert "course.json" in response.headers["Content-Disposition"]
    assert not exported[0].exists()
    assert not exported[0].parent.exists()


def test_builtin_demo_preview_skips_creator_billing_admission(
    test_client: object,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shifu_routes, "is_builtin_demo_shifu", lambda _app, _bid: True)
    admission = Mock()
    preview = Mock(return_value={"url": "preview"})
    monkeypatch.setattr(shifu_routes, "admit_creator_preview_usage", admission)
    monkeypatch.setattr(shifu_routes, "preview_shifu_draft", preview)
    monkeypatch.setattr(
        shifu_routes,
        "_resolve_publish_base_url",
        lambda _app: "https://learning.example",
    )
    response = test_client.post(
        f"{COURSE}/preview", headers=HEADERS, json={"variables": {"level": "beginner"}}
    )
    assert response.get_json(force=True)["data"] == {"url": "preview"}
    admission.assert_not_called()
    preview.assert_called_once_with(
        app, "teacher", "course", {"level": "beginner"}, "https://learning.example"
    )


def test_permission_list_returns_strongest_share_and_filters_unusable_accounts(
    test_client: object,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shifu_bid = uuid.uuid4().hex
    monkeypatch.setattr(
        shifu_routes, "get_config", lambda _key, _default=None: "google"
    )
    aggregates = {
        bid: SimpleNamespace(
            user_bid=bid, email=f"{bid}@example.com", mobile="", nickname=bid
        )
        for bid in ("publish", "edit", "view", "unknown", "no-contact")
    }
    aggregates["no-contact"].email = ""
    monkeypatch.setattr(shifu_routes, "load_user_aggregate", aggregates.get)
    with app.app_context():
        for bid, permission in [
            ("", "view"),
            ("teacher", "publish"),
            ("missing", "view"),
            ("unknown", "unsupported"),
            ("no-contact", "view"),
            ("publish", '["view", "edit", "publish"]'),
            ("edit", '["2"]'),
            ("view", "view"),
        ]:
            db.session.add(
                AiCourseAuth(
                    course_id=shifu_bid, user_id=bid, auth_type=permission, status=1
                )
            )
        db.session.flush()
        try:
            response = test_client.get(
                f"{PREFIX}/shifus/{shifu_bid}/permissions", headers=HEADERS
            )
            payload = response.get_json(force=True)
            assert payload["code"] == 0
            assert {
                item["user_id"]: item["permission"] for item in payload["data"]["items"]
            } == {"publish": "publish", "edit": "edit", "view": "view"}
        finally:
            db.session.rollback()


@pytest.mark.parametrize(
    ("contact_type", "methods"), [("google", "google"), ("email", "phone")]
)
def test_permission_listing_rejects_unavailable_contact_types(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    contact_type: str,
    methods: str,
) -> None:
    monkeypatch.setattr(shifu_routes, "get_config", lambda _key, _default=None: methods)
    response = test_client.get(
        f"{COURSE}/permissions",
        query_string={"contact_type": contact_type},
        headers=HEADERS,
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


def test_publish_origin_prefers_the_verified_first_forwarded_host(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolve_owner = Mock(return_value="domain-owner")
    resolve_origin = Mock(return_value="https://custom.example")
    monkeypatch.setattr(
        "flaskr.service.billing.api.resolve_creator_bid_by_host", resolve_owner
    )
    monkeypatch.setattr(
        "flaskr.service.billing.api.resolve_effective_custom_origin", resolve_origin
    )
    with app.test_request_context(
        "/", headers={"X-Forwarded-Host": " custom.example, proxy.example "}
    ):
        assert shifu_routes._resolve_publish_base_url(app) == "https://custom.example"
    resolve_owner.assert_called_once_with(app, "custom.example")
    resolve_origin.assert_called_once_with(app, "domain-owner")


@pytest.mark.parametrize("owner_lookup_fails", [False, True])
def test_publish_origin_recovers_from_domain_lookup_failures(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    owner_lookup_fails: bool,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.api.resolve_creator_bid_by_host",
        Mock(side_effect=RuntimeError("lookup failed")),
    )
    monkeypatch.setattr(
        "flaskr.common.shifu_context.get_shifu_creator_bid", lambda: "teacher"
    )
    resolve_origin = (
        Mock(side_effect=RuntimeError("owner lookup failed"))
        if owner_lookup_fails
        else Mock(return_value="https://owner.example")
    )
    monkeypatch.setattr(
        "flaskr.service.billing.api.resolve_effective_custom_origin", resolve_origin
    )
    monkeypatch.setattr(
        shifu_routes, "_get_request_base_url", lambda: "https://default.example"
    )
    with app.test_request_context("/"):
        result = shifu_routes._resolve_publish_base_url(app)
    assert result == (
        "https://default.example" if owner_lookup_fails else "https://owner.example"
    )


@pytest.mark.parametrize("temperature", ["invalid", -0.1, 2.1])
def test_ask_preview_rejects_invalid_temperature_before_model_invocation(
    test_client: object,
    preview_model: Mock,
    temperature: object,
) -> None:
    response = test_client.post(
        f"{PREFIX}/ask/preview",
        headers=HEADERS,
        json={
            "query": "Question",
            "shifu_bid": "course",
            "ask_model": "gpt-4o-mini",
            "ask_temperature": temperature,
        },
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )
    preview_model.assert_called_once()


def test_ask_preview_propagates_unconfigured_course_model_error(
    test_client: object,
    preview_model: Mock,
) -> None:
    preview_model.side_effect = AppError(
        "Model selection not configured",
        ERROR_CODE["server.llm.modelSelectionNotConfigured"],
    )
    response = test_client.post(
        f"{PREFIX}/ask/preview",
        headers=HEADERS,
        json={
            "query": "Question",
            "shifu_bid": "course",
            "provider": "llm",
            "mode": "provider_only",
            "config": {},
        },
    )
    assert (
        response.get_json(force=True)["code"]
        == ERROR_CODE["server.llm.modelSelectionNotConfigured"]
    )
    assert preview_model.call_args.args[0] == "1"


def test_ask_preview_rejects_live_audio_models(
    test_client: object, monkeypatch: pytest.MonkeyPatch, preview_model: Mock
) -> None:
    monkeypatch.setattr(
        "flaskr.service.learn.api.is_live_follow_up_model", lambda _model: True
    )
    response = test_client.post(
        f"{PREFIX}/ask/preview",
        headers=HEADERS,
        json={
            "query": "Question",
            "shifu_bid": "course",
            "ask_model": "live-model",
        },
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )
    preview_model.assert_not_called()


@pytest.mark.parametrize(
    ("user_bid", "owner_bid", "error_code"),
    [
        ("", "teacher", "server.user.userNotLogin"),
        ("teacher", "", "server.shifu.shifuNotFound"),
    ],
)
def test_debug_preview_requires_an_authenticated_user_and_existing_course_owner(
    test_client: object,
    authoring_user: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    user_bid: str,
    owner_bid: str,
    error_code: str,
) -> None:
    authoring_user.user_id = user_bid
    monkeypatch.setattr(
        shifu_routes, "get_shifu_creator_bid", Mock(return_value=owner_bid)
    )
    response = test_client.post(
        f"{PREFIX}/ask/preview",
        headers=HEADERS,
        json={
            "query": "Question",
            "shifu_bid": "course",
            "ask_model": "gpt-4o-mini",
        },
    )
    assert response.get_json(force=True)["code"] == ERROR_CODE[error_code]


def test_voice_clone_requires_source_audio(test_client: object) -> None:
    response = test_client.post(
        f"{PREFIX}/tts/minimax/voices/clone", headers=HEADERS, data={}
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


def test_tts_configuration_route_returns_provider_capabilities(
    test_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.api.tts.get_all_provider_configs", lambda: {"providers": ["minimax"]}
    )
    response = test_client.get(f"{PREFIX}/tts/config", headers=HEADERS)
    assert response.get_json(force=True)["data"] == {"providers": ["minimax"]}
