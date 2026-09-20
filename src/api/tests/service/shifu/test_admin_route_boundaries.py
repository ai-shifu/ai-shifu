"""Exercise operator HTTP authorization, normalization, and service forwarding."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu.admin_operations import route as admin_routes

PREFIX = "/api/shifu/admin/operations"
HEADERS = {"Token": "operator-test-token"}


@pytest.fixture(autouse=True)
def operator_user(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    user = SimpleNamespace(
        user_id="operator", is_operator=True, is_creator=True, language="en-US"
    )
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda _app, _token: user)
    return user


@pytest.mark.parametrize(
    ("path", "service", "positional", "keywords"),
    [
        ("courses/overview", "get_operator_course_overview", (), {}),
        ("orders/overview", "get_operator_order_overview", (), {}),
        ("orders/credits/overview", "build_operator_credit_orders_overview", (), {}),
        (
            "credit-notifications/overview",
            "get_operator_credit_notification_overview",
            (),
            {},
        ),
        (
            "credit-notifications/config",
            "get_operator_credit_notification_config",
            (),
            {},
        ),
        (
            "credit-notifications/templates",
            "list_operator_credit_notification_templates",
            (),
            {},
        ),
        (
            "credit-notifications/email-templates",
            "list_operator_credit_notification_email_templates",
            (),
            {},
        ),
        (
            "credit-notifications/notification",
            "get_operator_credit_notification_detail",
            (),
            {"notification_bid": "notification"},
        ),
        ("config/rates", "get_operator_rate_config", (), {}),
        ("referrals/overview", "get_operator_referral_overview", (), {}),
        (
            "referrals/relation",
            "get_operator_referral_detail",
            (),
            {"relation_bid": "relation"},
        ),
        ("orders/order/detail", "get_operator_order_detail", ("order",), {}),
        (
            "users/user/cancellation-preview",
            "get_account_cancellation_preview",
            (),
            {"user_bid": "user", "operator_user_bid": "operator"},
        ),
        (
            "users/user/cancellations/cancellation",
            "get_account_cancellation_status",
            (),
            {"user_bid": "user", "cancellation_bid": "cancellation"},
        ),
        (
            "users/user/credits/usages/usage/detail",
            "get_operator_user_credit_usage_detail",
            (),
            {"user_bid": "user", "usage_bid": "usage"},
        ),
    ],
)
def test_operator_read_routes_forward_identifiers_and_preserve_service_payload(
    test_client: object,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    service: str,
    positional: tuple,
    keywords: dict,
) -> None:
    handler = Mock(return_value={"id": "result", "total": 3})
    monkeypatch.setattr(admin_routes, service, handler)
    response = test_client.get(f"{PREFIX}/{path}", headers=HEADERS)
    assert response.get_json(force=True) == {
        "code": 0,
        "message": "success",
        "data": {"id": "result", "total": 3},
    }
    handler.assert_called_once_with(app, *positional, **keywords)


@pytest.mark.parametrize(
    ("method", "path", "service", "body", "keywords"),
    [
        (
            "POST",
            "credit-notifications/config",
            "update_operator_credit_notification_config",
            {"enabled": False},
            {"payload": {"enabled": False}, "operator_user_bid": "operator"},
        ),
        (
            "POST",
            "config/rates",
            "update_operator_rate_config",
            {"rate": "2.5"},
            {"payload": {"rate": "2.5"}, "operator_user_bid": "operator"},
        ),
        (
            "POST",
            "credit-notifications/templates/sync",
            "sync_operator_credit_notification_template",
            {"notification_type": "low_balance", "template_code": "template"},
            {"notification_type": "low_balance", "template_code": "template"},
        ),
        (
            "POST",
            "credit-notifications/email-templates",
            "save_operator_credit_notification_email_template",
            {"subject": "Subject"},
            {"payload": {"subject": "Subject"}, "operator_user_bid": "operator"},
        ),
        (
            "PUT",
            "credit-notifications/email-templates/template",
            "save_operator_credit_notification_email_template",
            {"subject": "Updated"},
            {
                "payload": {"subject": "Updated"},
                "notification_template_bid": "template",
                "operator_user_bid": "operator",
            },
        ),
        (
            "PUT",
            "credit-notifications/email-templates/template/status",
            "update_operator_credit_notification_email_template_status",
            {"template_status": "active"},
            {
                "notification_template_bid": "template",
                "template_status": "active",
                "operator_user_bid": "operator",
            },
        ),
        (
            "POST",
            "credit-notifications/dry-run",
            "dry_run_operator_credit_notifications",
            {"notification_type": "expired", "creator_bid": "teacher"},
            {"notification_type": "expired", "creator_bid": "teacher"},
        ),
        (
            "POST",
            "credit-notifications/notification/requeue",
            "requeue_operator_credit_notification",
            {},
            {"notification_bid": "notification", "operator_user_bid": "operator"},
        ),
        (
            "POST",
            "referrals/relation/status",
            "update_operator_referral_status",
            {"status": "active"},
            {
                "relation_bid": "relation",
                "operator_user_bid": "operator",
                "payload": {"status": "active"},
            },
        ),
        (
            "POST",
            "referrals/relation/adjustment",
            "update_operator_referral_status",
            {"amount": 10},
            {
                "relation_bid": "relation",
                "operator_user_bid": "operator",
                "payload": {"amount": 10},
            },
        ),
        (
            "POST",
            "users/user/cancel-subscription-renewals",
            "cancel_account_subscription_renewals",
            {},
            {"user_bid": "user", "operator_user_bid": "operator"},
        ),
        (
            "POST",
            "users/user/cancel",
            "request_user_account_cancellation",
            {
                "cancellation_bid": "task",
                "preview_version": "version",
                "reason": "requested",
            },
            {
                "user_bid": "user",
                "operator_user_bid": "operator",
                "cancellation_bid": "task",
                "idempotency_key": "task",
                "preview_version": "version",
                "reason": "requested",
            },
        ),
    ],
)
def test_operator_write_routes_forward_operator_identity_and_validated_payload(
    test_client: object,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    service: str,
    body: dict,
    keywords: dict,
) -> None:
    handler = Mock(return_value={"saved": True})
    monkeypatch.setattr(admin_routes, service, handler)
    response = test_client.open(
        f"{PREFIX}/{path}", method=method, json=body, headers=HEADERS
    )
    assert response.get_json(force=True)["data"] == {"saved": True}
    handler.assert_called_once_with(app, **keywords)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "credit-notifications/config"),
        ("POST", "config/rates"),
        ("POST", "credit-notifications/templates/sync"),
        ("POST", "credit-notifications/email-templates"),
        ("PUT", "credit-notifications/email-templates/template"),
        ("PUT", "credit-notifications/email-templates/template/status"),
        ("POST", "credit-notifications/dry-run"),
        ("POST", "referrals/relation/status"),
        ("POST", "referrals/relation/adjustment"),
        ("POST", "promotions/referral-campaigns"),
        ("POST", "promotions/referral-campaigns/campaign"),
        ("POST", "promotions/referral-campaigns/campaign/status"),
        ("POST", "users/user/cancel"),
        ("POST", "users/user/transfer-published-courses"),
        ("POST", "courses/course/copy"),
        ("POST", "courses/course/transfer-creator"),
        ("POST", "voice-clones"),
        ("POST", "users/user/credits/grant"),
        ("POST", "users/user/packages/grant"),
    ],
)
def test_operator_mutations_reject_non_object_json(
    test_client: object,
    method: str,
    path: str,
) -> None:
    response = test_client.open(
        f"{PREFIX}/{path}", method=method, json=["unexpected"], headers=HEADERS
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


@pytest.mark.parametrize(
    ("method", "path", "service"),
    [
        (
            "GET",
            "credit-notifications/config",
            "get_operator_credit_notification_config",
        ),
        (
            "POST",
            "credit-notifications/config",
            "update_operator_credit_notification_config",
        ),
        ("POST", "referrals/relation/adjustment", "update_operator_referral_status"),
        ("GET", "users/user/cancellation-preview", "get_account_cancellation_preview"),
        ("POST", "users/user/cancel", "request_user_account_cancellation"),
        ("POST", "courses/course/transfer-creator", "transfer_operator_course_creator"),
    ],
)
def test_non_operators_are_rejected_before_mutation_or_account_information_loads(
    test_client: object,
    operator_user: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    service: str,
) -> None:
    operator_user.is_operator = False
    handler = Mock()
    monkeypatch.setattr(admin_routes, service, handler)
    response = test_client.open(
        f"{PREFIX}/{path}", method=method, json={}, headers=HEADERS
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.shifu.noPermission"]
    )
    handler.assert_not_called()


@pytest.mark.parametrize(
    ("path", "service", "positional"),
    [
        ("courses", "list_operator_courses", True),
        ("orders", "list_operator_orders", True),
        ("referrals", "list_operator_referrals", False),
        ("credit-notifications", "list_operator_credit_notifications", False),
        ("voice-clones", "list_operator_voice_clones", False),
    ],
)
def test_operator_list_routes_normalize_utc_windows_and_forward_pagination(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    service: str,
    positional: bool,
) -> None:
    handler = Mock(return_value={"data": [], "total": 0})
    monkeypatch.setattr(admin_routes, service, handler)
    response = test_client.get(
        f"{PREFIX}/{path}",
        headers=HEADERS,
        query_string={
            "page_index": "2",
            "page_size": "3",
            "start_time": "2026-09-01T08:00:00+08:00",
            "end_time": "2026-09-02",
            "course_query": " course ",
            "relation_status": "901",
            "status": "",
            "minimax_status_code": "0",
        },
    )
    assert response.get_json(force=True)["data"] == {"data": [], "total": 0}
    call = handler.call_args
    if positional:
        assert call.args[1:3] == (2, 3)
        filters = call.args[3]
    else:
        assert call.kwargs["page_index"] == 2
        assert call.kwargs["page_size"] == 3
        filters = call.kwargs["filters"]
    assert filters["start_time"] == datetime(2026, 9, 1)
    assert filters["end_time"] == datetime(2026, 9, 2, 23, 59, 59)
    if path == "voice-clones":
        assert filters["minimax_status_code"] == 0
    if path in {"courses", "orders"}:
        assert filters["course_query"] == "course"


@pytest.mark.parametrize(
    ("path", "query"),
    [
        ("courses", {"page_index": "0"}),
        ("courses", {"page_size": "bad"}),
        (
            "courses",
            {"updated_start_time": "2026-09-02", "updated_end_time": "2026-09-01"},
        ),
        ("orders", {"status": "not-a-number"}),
        ("orders", {"start_time": "2026-09-03", "end_time": "2026-09-01"}),
        ("referrals", {"relation_status": "-1"}),
        ("voice-clones", {"minimax_status_code": "-1"}),
        ("voice-clones", {"provider": "unknown"}),
    ],
)
def test_operator_list_routes_reject_invalid_filter_boundaries(
    test_client: object, path: str, query: dict
) -> None:
    response = test_client.get(f"{PREFIX}/{path}", headers=HEADERS, query_string=query)
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


@pytest.mark.parametrize(
    "path",
    [
        "courses/course/copy",
        "courses/course/transfer-creator",
        "users/user/transfer-published-courses",
    ],
)
@pytest.mark.parametrize(
    ("body", "methods"),
    [
        ({"contact_type": "google", "identifier": "a@example.com"}, "google"),
        ({"contact_type": "email", "identifier": "a@example.com"}, "phone"),
        ({"contact_type": "email", "identifier": "bad-email"}, "email"),
        ({"contact_type": "phone", "identifier": "123"}, "phone"),
        (
            {"contact_type": "email", "identifier": ["a@example.com", "b@example.com"]},
            "email",
        ),
        ({"contact_type": "email", "identifier": "x" * 321}, "email"),
        ({"contact_type": "email", "identifier": {}}, "email"),
    ],
)
def test_course_copy_and_transfer_reject_unsupported_or_ambiguous_contacts(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    body: dict,
    methods: str,
) -> None:
    monkeypatch.setattr(admin_routes, "get_config", lambda _key, _default=None: methods)
    response = test_client.post(f"{PREFIX}/{path}", json=body, headers=HEADERS)
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


def test_transfer_courses_accepts_google_email_login_and_deduplicates_contacts(
    test_client: object,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admin_routes, "get_config", lambda _key, _default=None: ["google"]
    )
    handler = Mock(return_value={"transferred": 2})
    monkeypatch.setattr(admin_routes, "transfer_operator_published_courses", handler)
    response = test_client.post(
        f"{PREFIX}/users/teacher/transfer-published-courses",
        headers=HEADERS,
        json={
            "contact_type": " EMAIL ",
            "identifier": [None, " A@Example.com ", "a@example.com"],
        },
    )
    assert response.get_json(force=True)["data"] == {"transferred": 2}
    handler.assert_called_once_with(
        app,
        previous_creator_user_bid="teacher",
        contact_type="email",
        identifier="a@example.com",
        operator_user_bid="operator",
    )


def test_operator_service_errors_preserve_application_error_contract(
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = Mock(
        side_effect=AppError(
            "Course not found", status_code=ERROR_CODE["server.shifu.shifuNotFound"]
        )
    )
    monkeypatch.setattr(admin_routes, "get_operator_course_overview", handler)
    response = test_client.get(f"{PREFIX}/courses/overview", headers=HEADERS)
    assert (
        response.get_json(force=True)["code"]
        == ERROR_CODE["server.shifu.shifuNotFound"]
    )


@pytest.mark.parametrize(
    ("value", "expected"), [(True, True), (False, False), ("  ", True)]
)
def test_boolean_filters_keep_typed_values_and_blank_default(
    value: object, expected: bool
) -> None:
    assert (
        admin_routes._parse_boolean_query_param(
            value, field_name="active", default=True
        )
        is expected
    )


def test_blank_datetime_filter_is_omitted() -> None:
    assert admin_routes._parse_datetime_filter("  ", field_name="start_time") is None
