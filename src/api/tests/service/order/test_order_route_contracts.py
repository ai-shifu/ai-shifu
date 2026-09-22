"""Verify order HTTP authorization, request parsing and service boundaries."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.route import order
from flaskr.service.common.models import ERROR_CODE


@pytest.fixture
def routes(monkeypatch: pytest.MonkeyPatch, test_client: object) -> SimpleNamespace:
    user = SimpleNamespace(
        user_id="owner", is_creator=True, is_operator=False, language="en-US"
    )
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda *_: user)
    owner = Mock(return_value="owner")
    monkeypatch.setattr(order, "get_shifu_creator_bid", owner)
    return SimpleNamespace(
        client=test_client, user=user, owner=owner, headers={"Token": "test-token"}
    )


@pytest.mark.parametrize(
    ("path", "service", "extra", "expected"),
    [
        (
            "/stripe/sync",
            "sync_stripe_checkout_session",
            {"session_id": "session"},
            {"session_id": "session", "expected_user": "owner"},
        ),
        (
            "/payment/sync",
            "sync_native_payment_order",
            {"payment_channel": "wechatpay"},
            {"payment_channel": "wechatpay", "expected_user": "owner"},
        ),
        ("/payment-detail", "get_payment_details", {}, {"expected_user": "owner"}),
    ],
)
def test_payment_routes_bind_service_operation_to_authenticated_user(
    routes: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    app: object,
    path: str,
    service: str,
    extra: dict,
    expected: dict,
) -> None:
    invoke = Mock(return_value={"order_bid": "order", "status": "paid"})
    monkeypatch.setattr(order, service, invoke)
    response = routes.client.post(
        "/api/order" + path,
        json={"order_id": "order", "user_id": "forged"} | extra,
        headers=routes.headers,
    )
    assert response.get_json(force=True) == {
        "code": 0,
        "message": "success",
        "data": {"order_bid": "order", "status": "paid"},
    }
    invoke.assert_called_once_with(app, "order", **expected)


@pytest.mark.parametrize(
    "path", ["/stripe/sync", "/payment/sync", "/payment-detail", "/apply-discount"]
)
def test_missing_order_inputs_fail_before_service_invocation(
    routes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    invokes = []
    for name in (
        "sync_stripe_checkout_session",
        "sync_native_payment_order",
        "get_payment_details",
        "use_coupon_code",
    ):
        invoke = Mock()
        monkeypatch.setattr(order, name, invoke)
        invokes.append(invoke)
    payload = {"discount_code": "coupon"} if path == "/apply-discount" else {}
    response = routes.client.post(
        "/api/order" + path, json=payload, headers=routes.headers
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )
    assert all(invoke.call_count == 0 for invoke in invokes)


def test_missing_discount_code_is_rejected(routes: SimpleNamespace) -> None:
    response = routes.client.post(
        "/api/order/apply-discount", json={"order_id": "order"}, headers=routes.headers
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


@pytest.mark.parametrize(
    "path",
    [
        "/admin/orders",
        "/admin/orders/shifus",
        "/admin/orders/order",
        "/admin/orders/redemption-codes",
    ],
)
def test_admin_order_routes_reject_learner_role(
    routes: SimpleNamespace, path: str
) -> None:
    routes.user.is_creator = False
    response = routes.client.get("/api/order" + path, headers=routes.headers)
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.shifu.noPermission"]
    )


@pytest.mark.parametrize(
    "path", ["/admin/orders", "/admin/orders/shifus", "/admin/orders/redemption-codes"]
)
@pytest.mark.parametrize(
    "query",
    [
        {"page_index": "bad"},
        {"page_size": "bad"},
        {"page_index": "0"},
        {"page_size": "0"},
    ],
)
def test_admin_pagination_rejects_invalid_and_nonpositive_values(
    routes: SimpleNamespace, path: str, query: dict
) -> None:
    response = routes.client.get(
        "/api/order" + path, query_string=query, headers=routes.headers
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )


def test_order_list_and_detail_forward_authenticated_owner_scope(
    routes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, app: object
) -> None:
    listing = Mock(return_value={"items": [{"order_bid": "order"}], "total": 1})
    detail = Mock(return_value={"order_bid": "order"})
    monkeypatch.setattr(order, "list_orders", listing)
    monkeypatch.setattr(order, "get_order_detail", detail)
    filters = {
        "order_bid": "order",
        "user_bid": "buyer",
        "shifu_bid": "course",
        "status": "paid",
        "payment_channel": "stripe",
        "start_time": "2026-09-01",
        "end_time": "2026-09-20",
    }
    response = routes.client.get(
        "/api/order/admin/orders",
        query_string={"page_index": 2, "page_size": 3} | filters,
        headers=routes.headers,
    )
    assert response.get_json(force=True)["data"] == listing.return_value
    listing.assert_called_once_with(app, "owner", 2, 3, filters)
    response = routes.client.get(
        "/api/order/admin/orders/order", headers=routes.headers
    )
    assert response.get_json(force=True)["data"] == detail.return_value
    detail.assert_called_once_with(app, "owner", "order")


@pytest.mark.parametrize("published", [True, False])
def test_order_course_picker_only_lists_owned_courses(
    routes: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    app: object,
    published: bool,
) -> None:
    draft = Mock(return_value={"items": ["draft"]})
    live = Mock(return_value={"items": ["published"]})
    monkeypatch.setattr(order, "get_shifu_draft_list", draft)
    monkeypatch.setattr(order, "get_shifu_published_list", live)
    response = routes.client.get(
        "/api/order/admin/orders/shifus",
        query_string={
            "page_index": 2,
            "page_size": 3,
            "archived": "true",
            "published": str(published).lower(),
        },
        headers=routes.headers,
    )
    assert response.get_json(force=True)["code"] == 0
    if published:
        live.assert_called_once_with(app, "owner", 2, 3, creator_only=True)
        draft.assert_not_called()
    else:
        draft.assert_called_once_with(
            app, "owner", 2, 3, is_favorite=False, archived=True, creator_only=True
        )
        live.assert_not_called()


@pytest.mark.parametrize(
    ("start", "end", "expected_start", "expected_end"),
    [
        (
            "2026-09-20",
            "2026-09-20",
            datetime(2026, 9, 20),
            datetime(2026, 9, 20, 23, 59, 59),
        ),
        (
            "2026-09-20T08:00:00+08:00",
            "2026-09-20T01:00:00Z",
            datetime(2026, 9, 20),
            datetime(2026, 9, 20, 1),
        ),
        (" ", "", None, None),
    ],
)
def test_redemption_filters_normalize_dates_before_querying(
    routes: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    start: str,
    end: str,
    expected_start: datetime | None,
    expected_end: datetime | None,
) -> None:
    query = Mock(return_value={"items": []})
    monkeypatch.setattr(order, "list_creator_course_redemption_coupons", query)
    response = routes.client.get(
        "/api/order/admin/orders/redemption-codes",
        query_string={"start_time": start, "end_time": end},
        headers=routes.headers,
    )
    assert response.get_json(force=True)["code"] == 0
    filters = query.call_args.args[-1]
    assert filters["start_time"] == expected_start
    assert filters["end_time"] == expected_end


def test_invalid_redemption_date_never_queries_service(
    routes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = Mock()
    monkeypatch.setattr(order, "list_creator_course_redemption_coupons", query)
    response = routes.client.get(
        "/api/order/admin/orders/redemption-codes",
        query_string={"start_time": "invalid"},
        headers=routes.headers,
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )
    query.assert_not_called()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("1", True),
        ("false", False),
        ("0", False),
        (True, True),
        (False, False),
    ],
)
def test_redemption_status_normalizes_boolean_forms(
    routes: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    value: object,
    expected: bool,
) -> None:
    update = Mock(return_value={"enabled": expected})
    monkeypatch.setattr(order, "update_creator_course_redemption_coupon_status", update)
    response = routes.client.post(
        "/api/order/admin/orders/redemption-codes/coupon/status",
        json={"enabled": value},
        headers=routes.headers,
    )
    assert response.get_json(force=True)["data"] == {"enabled": expected}
    assert update.call_args.args[1:] == ("owner", "coupon", expected)


@pytest.mark.parametrize("value", [None, "unknown", {}, []])
def test_invalid_redemption_status_does_not_update_service(
    routes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    update = Mock()
    monkeypatch.setattr(order, "update_creator_course_redemption_coupon_status", update)
    response = routes.client.post(
        "/api/order/admin/orders/redemption-codes/coupon/status",
        json={"enabled": value},
        headers=routes.headers,
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )
    update.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {"course_id": ""},
        {"contact_type": "unknown"},
        {"mobile": ""},
        {"mobile": ", ,"},
        {"mobile": ",".join(["13800138000"] * 51)},
        {"lines": [None, " "]},
        {"lines": ["13800138000"] * 51},
        {"lines": ["invalid"]},
    ],
)
def test_activation_import_rejects_invalid_inputs_without_granting_access(
    routes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    grant = Mock()
    grant_entries = Mock()
    monkeypatch.setattr(order, "import_activation_orders", grant)
    monkeypatch.setattr(order, "import_activation_orders_from_entries", grant_entries)
    response = routes.client.post(
        "/api/order/admin/orders/import-activation",
        json={"course_id": "course", "mobile": "13800138000"} | payload,
        headers=routes.headers,
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )
    grant.assert_not_called()
    grant_entries.assert_not_called()


def test_activation_import_rejects_nonexistent_course_owner(
    routes: SimpleNamespace,
) -> None:
    routes.owner.return_value = ""
    response = routes.client.post(
        "/api/order/admin/orders/import-activation",
        json={"course_id": "missing", "mobile": "13800138000"},
        headers=routes.headers,
    )
    assert (
        response.get_json(force=True)["code"]
        == ERROR_CODE["server.shifu.shifuNotFound"]
    )


def test_activation_import_preserves_supplied_names_and_fills_missing_names(
    routes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, app: object
) -> None:
    course = Mock()
    grant = Mock(return_value={"success": [{"order_bid": "order"}], "failed": []})
    monkeypatch.setattr(order, "get_shifu_info", course)
    monkeypatch.setattr(order, "import_activation_orders_from_entries", grant)
    response = routes.client.post(
        "/api/order/admin/orders/import-activation",
        json={
            "course_id": "course",
            "contact_type": "email",
            "user_nick_name": "Fallback",
            "lines": [
                None,
                " ",
                "first@example.invalid,First",
                "second@example.invalid",
            ],
        },
        headers=routes.headers,
    )
    assert response.get_json(force=True)["code"] == 0
    course.assert_called_once_with(app, "course", preview_mode=False)
    assert grant.call_args.args[2] == "course"
    assert grant.call_args.kwargs == {"contact_type": "email"}
    entries = grant.call_args.args[1]
    assert len(entries) == 2
    assert [item["nickname"] for item in entries] == ["First", "Fallback"]


def test_activation_import_checks_expanded_entry_count(
    routes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    parse = Mock(side_effect=[[{"nickname": ""}], [{"nickname": ""}] * 51])
    grant = Mock()
    monkeypatch.setattr(order, "parse_import_activation_entries", parse)
    monkeypatch.setattr(order, "import_activation_orders_from_entries", grant)
    response = routes.client.post(
        "/api/order/admin/orders/import-activation",
        json={"course_id": "course", "lines": ["batch"]},
        headers=routes.headers,
    )
    assert (
        response.get_json(force=True)["code"] == ERROR_CODE["server.common.paramsError"]
    )
    grant.assert_not_called()
