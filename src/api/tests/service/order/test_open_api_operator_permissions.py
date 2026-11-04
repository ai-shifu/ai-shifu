"""Exercise operator Open API permissions through real HTTP and SQLite paths."""

from collections.abc import Iterator
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.order import funs as order_funs
from flaskr.service.order import open_api
from flaskr.service.order.consts import (
    ORDER_STATUS_REFUND,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TO_BE_PAID,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import AuthCredential, UserInfo


@pytest.fixture
def operator_partner(app: Flask) -> Iterator[SimpleNamespace]:
    operator_bid, creator_bid, learner_bid = (uuid4().hex for _ in range(3))
    course_bid, own_course_bid, order_bid = (uuid4().hex for _ in range(3))
    operator_key, creator_key = uuid4().hex, uuid4().hex
    learner_email, new_email = (f"{uuid4().hex}@example.test" for _ in range(2))
    with app.app_context():
        db.session.add_all(
            [
                UserInfo(
                    user_bid=operator_bid,
                    user_identify=f"{operator_bid}@example.test",
                    is_operator=1,
                    api_key=operator_key,
                ),
                UserInfo(
                    user_bid=creator_bid,
                    user_identify=f"{creator_bid}@example.test",
                    api_key=creator_key,
                ),
                UserInfo(user_bid=learner_bid, user_identify=learner_email),
                DraftShifu(shifu_bid=course_bid, created_user_bid=creator_bid),
                DraftShifu(shifu_bid=own_course_bid, created_user_bid=operator_bid),
                PublishedShifu(
                    shifu_bid=course_bid,
                    created_user_bid=creator_bid,
                    title="Partner course",
                    price=Decimal("100.00"),
                ),
                Order(
                    order_bid=order_bid,
                    user_bid=learner_bid,
                    shifu_bid=course_bid,
                    status=ORDER_STATUS_SUCCESS,
                ),
            ]
        )
        db.session.commit()
    yield SimpleNamespace(
        client=app.test_client(),
        operator_bid=operator_bid,
        creator_bid=creator_bid,
        learner_bid=learner_bid,
        course_bid=course_bid,
        own_course_bid=own_course_bid,
        order_bid=order_bid,
        new_email=new_email,
        headers={"X-User-Uid": operator_bid, "X-Api-Key": operator_key},
        creator_headers={"X-User-Uid": creator_bid, "X-Api-Key": creator_key},
        payload={
            "shifu_bid": course_bid,
            "user_identify": learner_email,
            "user_identify_type": "email",
        },
    )
    with app.app_context():
        db.session.rollback()
        user_bids = [operator_bid, creator_bid, learner_bid]
        user_bids.extend(
            row.user_bid for row in UserInfo.query.filter_by(user_identify=new_email)
        )
        Order.query.filter(Order.shifu_bid.in_([course_bid, own_course_bid])).delete()
        for model in (DraftShifu, PublishedShifu):
            model.query.filter(
                model.shifu_bid.in_([course_bid, own_course_bid])
            ).delete()
        AuthCredential.query.filter(AuthCredential.user_bid.in_(user_bids)).delete()
        UserInfo.query.filter(UserInfo.user_bid.in_(user_bids)).delete()
        db.session.commit()


@pytest.fixture
def reject_side_effects(
    app: Flask, operator_partner: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    calls = [Mock() for _ in range(4)]
    monkeypatch.setattr(open_api, "load_user_aggregate_by_identifier", calls[0])
    monkeypatch.setattr(open_api, "import_activation_order", calls[1])
    monkeypatch.setattr(open_api, "send_revoke_feishu", calls[2])
    monkeypatch.setattr(order_funs, "send_order_feishu", calls[3])
    yield
    for call in calls:
        call.assert_not_called()
    with app.app_context():
        assert Order.query.filter_by(shifu_bid=operator_partner.course_bid).count() == 1
        assert (
            Order.query.filter_by(order_bid=operator_partner.order_bid).one().status
            == ORDER_STATUS_SUCCESS
        )
        assert (
            UserInfo.query.filter_by(user_identify=operator_partner.new_email).count()
            == 0
        )
        assert (
            AuthCredential.query.filter_by(
                identifier=operator_partner.new_email
            ).count()
            == 0
        )


def test_operator_key_queries_another_creators_active_order(
    operator_partner: SimpleNamespace,
) -> None:
    response = operator_partner.client.post(
        "/api/open-api/v1/order/query",
        headers=operator_partner.headers,
        json=operator_partner.payload,
    )
    assert response.get_json(force=True) == {
        "code": 0,
        "message": "success",
        "data": {"authorized": True, "order_bid": operator_partner.order_bid},
    }


def test_operator_key_imports_foreign_course_learner_without_repeating_grant(
    app: Flask,
    operator_partner: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notify = Mock()
    monkeypatch.setattr(order_funs, "send_order_feishu", notify)
    payload = {**operator_partner.payload, "user_identify": operator_partner.new_email}
    granted = operator_partner.client.post(
        "/api/open-api/v1/order/grant",
        headers=operator_partner.headers,
        json=payload,
    ).get_json(force=True)
    assert granted["code"] == 0
    assert granted["message"] == "success"
    assert set(granted["data"]) == {"order_bid"}
    order_bid = granted["data"]["order_bid"]
    with app.app_context():
        learner = UserInfo.query.filter_by(
            user_identify=operator_partner.new_email
        ).one()
        credential = AuthCredential.query.filter_by(
            user_bid=learner.user_bid, provider_name="email", deleted=0
        ).one()
        assert credential.identifier == operator_partner.new_email
        order = Order.query.filter_by(order_bid=order_bid).one()
        assert order.user_bid == learner.user_bid
        assert order.shifu_bid == operator_partner.course_bid
        assert order.creator_bid == operator_partner.creator_bid
        assert order.granted_by_user_bid == operator_partner.operator_bid
        assert order.status == ORDER_STATUS_SUCCESS
        assert order.payment_channel == "open_api"
        assert order.payable_price == order.paid_price == Decimal("0.00")
    repeated = operator_partner.client.post(
        "/api/open-api/v1/order/grant",
        headers=operator_partner.headers,
        json=payload,
    ).get_json(force=True)
    assert repeated == granted
    queried = operator_partner.client.post(
        "/api/open-api/v1/order/query",
        headers=operator_partner.headers,
        json=payload,
    ).get_json(force=True)
    assert queried["code"] == 0
    assert queried["data"] == {"authorized": True, "order_bid": order_bid}
    with app.app_context():
        assert (
            Order.query.filter_by(
                user_bid=learner.user_bid, shifu_bid=operator_partner.course_bid
            ).count()
            == 1
        )
        assert (
            UserInfo.query.filter_by(user_identify=operator_partner.new_email).count()
            == 1
        )
    notify.assert_called_once_with(app, order_bid)


@pytest.mark.parametrize("use_operator_key", [True, False])
def test_grant_rejects_draft_only_course_before_learner_writes(
    app: Flask,
    operator_partner: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    use_operator_key: bool,
) -> None:
    notify = Mock()
    monkeypatch.setattr(order_funs, "send_order_feishu", notify)
    with app.app_context():
        PublishedShifu.query.filter_by(shifu_bid=operator_partner.course_bid).update(
            {"deleted": 1}
        )
        db.session.commit()
    headers = (
        operator_partner.headers
        if use_operator_key
        else operator_partner.creator_headers
    )
    payload = {**operator_partner.payload, "user_identify": operator_partner.new_email}
    response = operator_partner.client.post(
        "/api/open-api/v1/order/grant", headers=headers, json=payload
    ).get_json(force=True)
    assert response["code"] == ERROR_CODE["server.shifu.shifuNotFound"]
    with app.app_context():
        assert (
            UserInfo.query.filter_by(user_identify=operator_partner.new_email).count()
            == 0
        )
        assert (
            AuthCredential.query.filter_by(
                identifier=operator_partner.new_email
            ).count()
            == 0
        )
        assert Order.query.filter_by(shifu_bid=operator_partner.course_bid).count() == 1
    notify.assert_not_called()


def test_creator_grant_records_creator_as_granting_user(
    app: Flask,
    operator_partner: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(order_funs, "send_order_feishu", Mock())
    payload = {**operator_partner.payload, "user_identify": operator_partner.new_email}
    granted = operator_partner.client.post(
        "/api/open-api/v1/order/grant",
        headers=operator_partner.creator_headers,
        json=payload,
    ).get_json(force=True)
    assert granted["code"] == 0
    with app.app_context():
        order = Order.query.filter_by(order_bid=granted["data"]["order_bid"]).one()
        assert order.creator_bid == operator_partner.creator_bid
        assert order.granted_by_user_bid == operator_partner.creator_bid


@pytest.mark.parametrize("operation", ["query", "grant", "revoke"])
@pytest.mark.parametrize("forged_role", [False, True])
@pytest.mark.usefixtures("reject_side_effects")
def test_ordinary_key_cannot_manage_foreign_course_with_client_role_claims(
    app: Flask,
    operator_partner: SimpleNamespace,
    operation: str,
    forged_role: bool,
) -> None:
    with app.app_context():
        UserInfo.query.filter_by(user_bid=operator_partner.operator_bid).update(
            {"is_operator": 0}
        )
        db.session.commit()
    headers = operator_partner.headers.copy()
    payload = {**operator_partner.payload, "user_identify": operator_partner.new_email}
    if forged_role:
        headers.update(
            {"X-Is-Operator": "true", "X-Owner-Bid": operator_partner.creator_bid}
        )
        payload.update({"owner_bid": operator_partner.creator_bid, "is_operator": True})
    response = operator_partner.client.post(
        f"/api/open-api/v1/order/{operation}", headers=headers, json=payload
    )
    assert (
        response.get_json(force=True)["code"]
        == ERROR_CODE["server.openapi.courseOwnershipRequired"]
    )


@pytest.mark.parametrize("operation", ["query", "grant"])
@pytest.mark.parametrize(
    ("change", "error_key"),
    [
        ({"is_operator": 0}, "server.openapi.courseOwnershipRequired"),
        ({"deleted": 1}, "server.openapi.invalidApiKey"),
    ],
    ids=["role_removed", "account_deleted"],
)
def test_current_operator_status_takes_effect_on_next_request(
    app: Flask,
    operator_partner: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    change: dict[str, int],
    error_key: str,
) -> None:
    initial = operator_partner.client.post(
        f"/api/open-api/v1/order/{operation}",
        headers=operator_partner.headers,
        json=operator_partner.payload,
    ).get_json(force=True)
    assert initial["code"] == 0
    with app.app_context():
        UserInfo.query.filter_by(user_bid=operator_partner.operator_bid).update(change)
        db.session.commit()
    lookup, importer = Mock(), Mock()
    monkeypatch.setattr(open_api, "load_user_aggregate_by_identifier", lookup)
    monkeypatch.setattr(open_api, "import_activation_order", importer)
    rejected = operator_partner.client.post(
        f"/api/open-api/v1/order/{operation}",
        headers=operator_partner.headers,
        json=operator_partner.payload,
    ).get_json(force=True)
    assert rejected["code"] == ERROR_CODE[error_key]
    lookup.assert_not_called()
    importer.assert_not_called()
    with app.app_context():
        owner = UserInfo.query.filter_by(user_bid=operator_partner.operator_bid).one()
        assert owner.api_key == operator_partner.headers["X-Api-Key"]
        assert (
            Order.query.filter_by(order_bid=operator_partner.order_bid).one().status
            == ORDER_STATUS_SUCCESS
        )


@pytest.mark.parametrize("operation", ["query", "grant", "revoke"])
@pytest.mark.parametrize(
    "invalid",
    ["wrong_key", "mismatched_owner", "ordinary_key_operator_uid", "deleted_owner"],
)
@pytest.mark.usefixtures("reject_side_effects")
def test_invalid_operator_credentials_reject_before_learner_side_effects(
    app: Flask,
    operator_partner: SimpleNamespace,
    operation: str,
    invalid: str,
) -> None:
    headers = operator_partner.headers.copy()
    if invalid == "wrong_key":
        headers["X-Api-Key"] = uuid4().hex
    elif invalid == "mismatched_owner":
        headers["X-User-Uid"] = operator_partner.creator_bid
    elif invalid == "ordinary_key_operator_uid":
        headers["X-Api-Key"] = operator_partner.creator_headers["X-Api-Key"]
    else:
        with app.app_context():
            UserInfo.query.filter_by(user_bid=operator_partner.operator_bid).update(
                {"deleted": 1}
            )
            db.session.commit()
    response = operator_partner.client.post(
        f"/api/open-api/v1/order/{operation}",
        headers=headers,
        json={**operator_partner.payload, "user_identify": operator_partner.new_email},
    )
    assert (
        response.get_json(force=True)["code"]
        == ERROR_CODE["server.openapi.invalidApiKey"]
    )


@pytest.mark.usefixtures("reject_side_effects")
def test_operator_key_cannot_revoke_another_creators_order(
    operator_partner: SimpleNamespace,
) -> None:
    response = operator_partner.client.post(
        "/api/open-api/v1/order/revoke",
        headers=operator_partner.headers,
        json=operator_partner.payload,
    )
    assert (
        response.get_json(force=True)["code"]
        == ERROR_CODE["server.openapi.courseOwnershipRequired"]
    )


@pytest.mark.parametrize("operation", ["query", "grant", "revoke"])
@pytest.mark.parametrize("is_operator", [False, True])
@pytest.mark.parametrize("course_state", ["missing", "deleted"])
@pytest.mark.usefixtures("reject_side_effects")
def test_unavailable_course_rejects_all_roles_before_role_or_learner_lookup(
    app: Flask,
    operator_partner: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    is_operator: bool,
    course_state: str,
) -> None:
    course_bid = operator_partner.course_bid
    with app.app_context():
        UserInfo.query.filter_by(user_bid=operator_partner.operator_bid).update(
            {"is_operator": int(is_operator)}
        )
        if course_state == "deleted":
            for model in (DraftShifu, PublishedShifu):
                model.query.filter_by(shifu_bid=course_bid).update({"deleted": 1})
        else:
            course_bid = uuid4().hex
        db.session.commit()
    role_lookup = Mock()
    monkeypatch.setattr(open_api, "get_user_entity_by_bid", role_lookup)
    response = operator_partner.client.post(
        f"/api/open-api/v1/order/{operation}",
        headers=operator_partner.headers,
        json={
            **operator_partner.payload,
            "shifu_bid": course_bid,
            "user_identify": operator_partner.new_email,
        },
    )
    assert (
        response.get_json(force=True)["code"]
        == ERROR_CODE["server.shifu.courseNotFound"]
    )
    role_lookup.assert_not_called()


@pytest.mark.parametrize("owner_kind", ["ordinary", "operator"])
def test_course_owners_keep_query_grant_and_revoke_behavior(
    app: Flask,
    operator_partner: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    owner_kind: str,
) -> None:
    payload = operator_partner.payload.copy()
    headers = operator_partner.creator_headers
    order_bid = operator_partner.order_bid
    if owner_kind == "operator":
        headers = operator_partner.headers
        payload["shifu_bid"] = operator_partner.own_course_bid
        order_bid = uuid4().hex
        with app.app_context():
            db.session.add(
                Order(
                    order_bid=order_bid,
                    user_bid=operator_partner.learner_bid,
                    shifu_bid=operator_partner.own_course_bid,
                    status=ORDER_STATUS_SUCCESS,
                )
            )
            db.session.commit()
    importer, notify = Mock(), Mock()
    monkeypatch.setattr(open_api, "import_activation_order", importer)
    monkeypatch.setattr(open_api, "send_revoke_feishu", notify)
    queried = operator_partner.client.post(
        "/api/open-api/v1/order/query", headers=headers, json=payload
    ).get_json(force=True)
    assert queried["code"] == 0
    assert queried["data"] == {"authorized": True, "order_bid": order_bid}
    granted = operator_partner.client.post(
        "/api/open-api/v1/order/grant", headers=headers, json=payload
    ).get_json(force=True)
    assert granted["code"] == 0
    assert granted["data"] == {"order_bid": order_bid}
    importer.assert_not_called()
    notify.assert_not_called()
    revoked = operator_partner.client.post(
        "/api/open-api/v1/order/revoke", headers=headers, json=payload
    ).get_json(force=True)
    assert revoked["code"] == 0
    assert revoked["data"] == {"order_bid": order_bid, "status": "revoked"}
    with app.app_context():
        assert (
            Order.query.filter_by(order_bid=order_bid).one().status
            == ORDER_STATUS_REFUND
        )
    notify.assert_called_once_with(app, order_bid, payload["user_identify"])


@pytest.mark.parametrize("excluded", ["unpaid", "refunded", "deleted", "unknown_user"])
def test_operator_query_retains_exact_active_order_filters(
    app: Flask, operator_partner: SimpleNamespace, excluded: str
) -> None:
    payload = operator_partner.payload.copy()
    with app.app_context():
        order = Order.query.filter_by(order_bid=operator_partner.order_bid).one()
        if excluded == "deleted":
            order.deleted = 1
        elif excluded == "unknown_user":
            payload["user_identify"] = operator_partner.new_email
        else:
            order.status = (
                ORDER_STATUS_TO_BE_PAID if excluded == "unpaid" else ORDER_STATUS_REFUND
            )
        db.session.add_all(
            [
                Order(
                    order_bid=uuid4().hex,
                    user_bid=operator_partner.learner_bid,
                    shifu_bid=operator_partner.own_course_bid,
                    status=ORDER_STATUS_SUCCESS,
                ),
                Order(
                    order_bid=uuid4().hex,
                    user_bid=operator_partner.creator_bid,
                    shifu_bid=operator_partner.course_bid,
                    status=ORDER_STATUS_SUCCESS,
                ),
            ]
        )
        db.session.commit()
    response = operator_partner.client.post(
        "/api/open-api/v1/order/query", headers=operator_partner.headers, json=payload
    )
    assert response.get_json(force=True) == {
        "code": 0,
        "message": "success",
        "data": {"authorized": False, "order_bid": None},
    }
    with app.app_context():
        assert (
            UserInfo.query.filter_by(user_identify=operator_partner.new_email).count()
            == 0
        )


@pytest.mark.parametrize("operation", ["query", "grant"])
@pytest.mark.parametrize("owner_state", ["missing", "deleted"])
@pytest.mark.usefixtures("reject_side_effects")
def test_order_service_does_not_treat_missing_or_deleted_owner_as_operator(
    app: Flask,
    operator_partner: SimpleNamespace,
    operation: str,
    owner_state: str,
) -> None:
    owner_bid = operator_partner.operator_bid
    with app.app_context():
        if owner_state == "deleted":
            UserInfo.query.filter_by(user_bid=owner_bid).update({"deleted": 1})
            db.session.commit()
        else:
            owner_bid = uuid4().hex
        with pytest.raises(AppError) as error:
            getattr(open_api, f"open_api_{operation}_order")(
                app,
                owner_bid,
                operator_partner.course_bid,
                operator_partner.new_email,
                "email",
            )
    assert error.value.code == ERROR_CODE["server.openapi.courseOwnershipRequired"]
