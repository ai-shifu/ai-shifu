from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from flaskr.dao import db
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.promo.admin import _format_promotion_admin_datetime
from flaskr.service.promo.consts import (
    COUPON_APPLY_TYPE_SPECIFIC,
    COUPON_STATUS_USED,
    COUPON_TYPE_FIXED,
    COUPON_TYPE_PERCENT,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED,
    PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
    PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
    PROMO_CAMPAIGN_JOIN_TYPE_MANUAL,
)
from flaskr.service.promo.models import (
    Coupon,
    CouponUsage,
    PromoCampaign,
    PromoRedemption,
)
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity


@pytest.fixture(autouse=True)
def _isolate_tables(app):
    with app.app_context():
        db.session.query(PromoRedemption).delete()
        db.session.query(PromoCampaign).delete()
        db.session.query(CouponUsage).delete()
        db.session.query(Coupon).delete()
        db.session.query(Order).delete()
        db.session.query(PublishedShifu).delete()
        db.session.query(DraftShifu).delete()
        db.session.query(AuthCredential).delete()
        db.session.query(UserEntity).delete()
        db.session.commit()
        db.session.remove()
    yield
    with app.app_context():
        db.session.query(PromoRedemption).delete()
        db.session.query(PromoCampaign).delete()
        db.session.query(CouponUsage).delete()
        db.session.query(Coupon).delete()
        db.session.query(Order).delete()
        db.session.query(PublishedShifu).delete()
        db.session.query(DraftShifu).delete()
        db.session.query(AuthCredential).delete()
        db.session.query(UserEntity).delete()
        db.session.commit()
        db.session.remove()


def _mock_operator(
    monkeypatch, user_id: str = "operator-1", *, is_operator: bool = True
) -> None:
    dummy_user = SimpleNamespace(
        user_id=user_id,
        is_operator=is_operator,
        is_creator=False,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: dummy_user,
        raising=False,
    )


def _seed_user(
    user_bid: str, identifier: str, nickname: str, *, is_operator: bool = False
):
    user = UserEntity()
    user.user_bid = user_bid
    user.user_identify = identifier
    user.nickname = nickname
    user.is_operator = 1 if is_operator else 0
    db.session.add(user)

    credential = AuthCredential()
    credential.credential_bid = f"cred-{user_bid}"
    credential.user_bid = user_bid
    credential.provider_name = "email" if "@" in identifier else "phone"
    credential.subject_id = identifier
    credential.subject_format = credential.provider_name
    credential.identifier = identifier
    db.session.add(credential)
    return user


def _seed_course(shifu_bid: str, title: str, *, creator_user_bid: str = "operator-1"):
    course = PublishedShifu()
    course.shifu_bid = shifu_bid
    course.title = title
    course.price = Decimal("99.00")
    course.created_user_bid = creator_user_bid
    course.updated_user_bid = creator_user_bid
    db.session.add(course)
    return course


def _seed_order(
    order_bid: str,
    shifu_bid: str,
    user_bid: str,
    *,
    payable: str = "99.00",
    paid: str = "79.00",
):
    order = Order()
    order.order_bid = order_bid
    order.shifu_bid = shifu_bid
    order.user_bid = user_bid
    order.payable_price = Decimal(payable)
    order.paid_price = Decimal(paid)
    order.status = ORDER_STATUS_SUCCESS
    db.session.add(order)
    return order


def test_admin_promotions_coupons_route_requires_operator(test_client, monkeypatch):
    _mock_operator(monkeypatch, is_operator=False)

    response = test_client.get(
        "/api/shifu/admin/operations/promotions/coupons",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 401


def test_admin_promotions_coupon_routes_round_trip(app, test_client, monkeypatch):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_user("learner-1", "13812345678", "Learner")
        _seed_course("course-1", "Coupon Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Spring Batch",
            "code": "SPRINGBATCH",
            "usage_type": COUPON_APPLY_TYPE_SPECIFIC,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 3,
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    create_payload = create_response.get_json(force=True)
    coupon_bid = create_payload["data"]["coupon_bid"]

    assert create_response.status_code == 200
    assert create_payload["code"] == 0
    assert coupon_bid

    with app.app_context():
        coupon = Coupon.query.filter(Coupon.coupon_bid == coupon_bid).first()
        assert coupon is not None
        assert coupon.name == "Spring Batch"
        assert coupon.code == ""
        first_code = CouponUsage.query.filter(
            CouponUsage.coupon_bid == coupon_bid
        ).first()
        assert first_code is not None
        generated_usage_code = first_code.code
        first_code.user_bid = "learner-1"
        first_code.order_bid = "order-1"
        first_code.shifu_bid = "course-1"
        first_code.status = COUPON_STATUS_USED
        _seed_order("order-1", "course-1", "learner-1", paid="79.00")
        coupon.used_count = 1
        db.session.commit()

    list_response = test_client.get(
        "/api/shifu/admin/operations/promotions/coupons",
        query_string={"page_index": 1, "page_size": 20},
        headers={"Token": "test-token"},
    )
    list_payload = list_response.get_json(force=True)

    assert list_payload["code"] == 0
    assert list_payload["data"]["total"] == 1
    assert list_payload["data"]["summary"]["usage_count"] == 1
    assert list_payload["data"]["items"][0]["name"] == "Spring Batch"
    assert list_payload["data"]["items"][0]["course_name"] == "Coupon Course"

    filtered_list_response = test_client.get(
        "/api/shifu/admin/operations/promotions/coupons",
        query_string={
            "page_index": 1,
            "page_size": 20,
            "keyword": coupon_bid,
            "name": "Spring",
        },
        headers={"Token": "test-token"},
    )
    filtered_list_payload = filtered_list_response.get_json(force=True)

    assert filtered_list_payload["code"] == 0
    assert filtered_list_payload["data"]["total"] == 1
    assert filtered_list_payload["data"]["items"][0]["coupon_bid"] == coupon_bid

    code_filtered_response = test_client.get(
        "/api/shifu/admin/operations/promotions/coupons",
        query_string={
            "page_index": 1,
            "page_size": 20,
            "keyword": generated_usage_code,
        },
        headers={"Token": "test-token"},
    )
    code_filtered_payload = code_filtered_response.get_json(force=True)

    assert code_filtered_payload["code"] == 0
    assert code_filtered_payload["data"]["total"] == 1
    assert code_filtered_payload["data"]["items"][0]["coupon_bid"] == coupon_bid

    course_query_by_id_response = test_client.get(
        "/api/shifu/admin/operations/promotions/coupons",
        query_string={
            "page_index": 1,
            "page_size": 20,
            "shifu_bid": "course-1",
            "course_name": "course-1",
        },
        headers={"Token": "test-token"},
    )
    course_query_by_id_payload = course_query_by_id_response.get_json(force=True)

    assert course_query_by_id_payload["code"] == 0
    assert course_query_by_id_payload["data"]["total"] == 1
    assert course_query_by_id_payload["data"]["items"][0]["coupon_bid"] == coupon_bid

    course_query_by_name_response = test_client.get(
        "/api/shifu/admin/operations/promotions/coupons",
        query_string={
            "page_index": 1,
            "page_size": 20,
            "shifu_bid": "Coupon Course",
            "course_name": "Coupon Course",
        },
        headers={"Token": "test-token"},
    )
    course_query_by_name_payload = course_query_by_name_response.get_json(force=True)

    assert course_query_by_name_payload["code"] == 0
    assert course_query_by_name_payload["data"]["total"] == 1
    assert course_query_by_name_payload["data"]["items"][0]["coupon_bid"] == coupon_bid

    detail_response = test_client.get(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}",
        headers={"Token": "test-token"},
    )
    detail_payload = detail_response.get_json(force=True)

    assert detail_payload["code"] == 0
    assert detail_payload["data"]["coupon"]["coupon_bid"] == coupon_bid
    assert detail_payload["data"]["remaining_count"] == 2

    usage_response = test_client.get(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}/usages",
        query_string={"page_index": 1, "page_size": 20},
        headers={"Token": "test-token"},
    )
    usage_payload = usage_response.get_json(force=True)

    assert usage_payload["code"] == 0
    assert usage_payload["data"]["total"] == 1
    assert usage_payload["data"]["items"][0]["order_bid"] == "order-1"

    codes_response = test_client.get(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}/codes",
        query_string={"page_index": 1, "page_size": 20},
        headers={"Token": "test-token"},
    )
    codes_payload = codes_response.get_json(force=True)

    assert codes_payload["code"] == 0
    assert codes_payload["data"]["total"] == 3

    status_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}/status",
        json={"enabled": False},
        headers={"Token": "test-token"},
    )
    status_payload = status_response.get_json(force=True)

    assert status_payload["code"] == 0
    with app.app_context():
        coupon = Coupon.query.filter(Coupon.coupon_bid == coupon_bid).first()
        assert coupon is not None
        assert coupon.status == 0


def test_admin_promotions_generic_coupon_requires_code_and_quantity(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-1", "Coupon Course")
        db.session.commit()

    missing_code_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Generic Coupon",
            "usage_type": 801,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 10,
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    missing_code_payload = missing_code_response.get_json(force=True)

    assert missing_code_payload["code"] != 0

    missing_quantity_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Generic Coupon",
            "code": "SPRING2026",
            "usage_type": 801,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    missing_quantity_payload = missing_quantity_response.get_json(force=True)

    assert missing_quantity_payload["code"] != 0


def test_admin_promotions_serializes_coupon_times_from_shanghai_source_timezone(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-1", "Coupon Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Timezone Coupon",
            "code": "TZTEST",
            "usage_type": 801,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 10,
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "start_at": "2026-04-24 00:00:00",
            "end_at": "2026-04-24 23:59:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    coupon_bid = create_response.get_json(force=True)["data"]["coupon_bid"]

    list_response = test_client.get(
        "/api/shifu/admin/operations/promotions/coupons",
        query_string={"page_index": 1, "page_size": 20},
        headers={"Token": "test-token"},
    )
    list_payload = list_response.get_json(force=True)

    detail_response = test_client.get(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}",
        headers={"Token": "test-token"},
    )
    detail_payload = detail_response.get_json(force=True)

    assert list_payload["code"] == 0
    assert list_payload["data"]["items"][0]["start_at"] == "2026-04-23T16:00:00Z"
    assert list_payload["data"]["items"][0]["end_at"] == "2026-04-24T15:59:00Z"
    assert detail_payload["code"] == 0
    assert detail_payload["data"]["coupon"]["start_at"] == "2026-04-23T16:00:00Z"
    assert detail_payload["data"]["coupon"]["end_at"] == "2026-04-24T15:59:00Z"


def test_admin_promotions_single_use_coupon_generates_sub_codes_only(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-1", "Coupon Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Single Use Coupon",
            "usage_type": COUPON_APPLY_TYPE_SPECIFIC,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 2,
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    create_payload = create_response.get_json(force=True)

    assert create_response.status_code == 200
    assert create_payload["code"] == 0

    with app.app_context():
        coupon = Coupon.query.filter(
            Coupon.coupon_bid == create_payload["data"]["coupon_bid"]
        ).first()
        assert coupon is not None
        assert coupon.code == ""

        usages = (
            CouponUsage.query.filter(CouponUsage.coupon_bid == coupon.coupon_bid)
            .order_by(CouponUsage.id.asc())
            .all()
        )
        assert len(usages) == 2
        assert all(usage.code for usage in usages)
        assert all(usage.code != coupon.code for usage in usages)


def test_admin_promotions_single_use_coupon_rejects_unknown_course(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Single Use Coupon",
            "usage_type": COUPON_APPLY_TYPE_SPECIFIC,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 2,
            "scope_type": "single_course",
            "shifu_bid": "missing-course",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )

    assert create_response.get_json(force=True)["code"] != 0


def test_admin_promotions_single_use_coupon_rejects_oversized_batch(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-1", "Coupon Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Single Use Coupon",
            "usage_type": COUPON_APPLY_TYPE_SPECIFIC,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 2001,
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )

    assert create_response.get_json(force=True)["code"] != 0


def test_admin_promotions_coupon_usage_falls_back_to_order_course(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_user("learner-1", "13812345678", "Learner")
        _seed_course("course-1", "Coupon Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Generic Coupon",
            "code": "TONGYONG",
            "usage_type": 801,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 10,
            "scope_type": "all_courses",
            "shifu_bid": "",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    create_payload = create_response.get_json(force=True)
    coupon_bid = create_payload["data"]["coupon_bid"]

    with app.app_context():
        _seed_order("order-1", "course-1", "learner-1", paid="79.00")
        usage = CouponUsage()
        usage.coupon_usage_bid = "usage-1"
        usage.coupon_bid = coupon_bid
        usage.user_bid = "learner-1"
        usage.order_bid = "order-1"
        usage.code = "TONGYONG"
        usage.discount_type = COUPON_TYPE_FIXED
        usage.value = Decimal("20")
        usage.status = COUPON_STATUS_USED
        usage.shifu_bid = ""
        db.session.add(usage)
        db.session.commit()

    usage_response = test_client.get(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}/usages",
        query_string={"page_index": 1, "page_size": 20},
        headers={"Token": "test-token"},
    )
    usage_payload = usage_response.get_json(force=True)

    assert usage_payload["code"] == 0
    assert usage_payload["data"]["total"] == 1
    assert usage_payload["data"]["items"][0]["shifu_bid"] == "course-1"
    assert usage_payload["data"]["items"][0]["course_name"] == "Coupon Course"


def test_admin_promotions_coupon_usage_list_supports_keyword_filter(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_user("learner-1", "13812345678", "Learner One")
        _seed_user("learner-2", "learner2@example.com", "Learner Two")
        _seed_course("course-1", "Coupon Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Generic Coupon",
            "code": "TONGYONG",
            "usage_type": 801,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 10,
            "scope_type": "all_courses",
            "shifu_bid": "",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    coupon_bid = create_response.get_json(force=True)["data"]["coupon_bid"]

    with app.app_context():
        _seed_order("order-1", "course-1", "learner-1", paid="79.00")
        _seed_order("order-2", "course-1", "learner-2", paid="69.00")
        db.session.add_all(
            [
                CouponUsage(
                    coupon_usage_bid="usage-1",
                    coupon_bid=coupon_bid,
                    user_bid="learner-1",
                    order_bid="order-1",
                    code="TONGYONG-A",
                    discount_type=COUPON_TYPE_FIXED,
                    value=Decimal("20"),
                    status=COUPON_STATUS_USED,
                    shifu_bid="course-1",
                ),
                CouponUsage(
                    coupon_usage_bid="usage-2",
                    coupon_bid=coupon_bid,
                    user_bid="learner-2",
                    order_bid="order-2",
                    code="TONGYONG-B",
                    discount_type=COUPON_TYPE_FIXED,
                    value=Decimal("20"),
                    status=COUPON_STATUS_USED,
                    shifu_bid="course-1",
                ),
            ]
        )
        db.session.commit()

    usage_response = test_client.get(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}/usages",
        query_string={
            "page_index": 1,
            "page_size": 1,
            "keyword": "learner2@example.com",
        },
        headers={"Token": "test-token"},
    )
    usage_payload = usage_response.get_json(force=True)

    assert usage_payload["code"] == 0
    assert usage_payload["data"]["total"] == 1
    assert usage_payload["data"]["summary"]["usage_count"] == 1
    assert usage_payload["data"]["items"][0]["user_bid"] == "learner-2"
    assert usage_payload["data"]["items"][0]["order_bid"] == "order-2"


def test_admin_promotions_coupon_update_keeps_used_records_unchanged(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_user("learner-1", "13812345678", "Learner")
        _seed_course("course-1", "Coupon Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Spring Batch",
            "code": "SPRINGBATCH",
            "usage_type": COUPON_APPLY_TYPE_SPECIFIC,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 3,
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    coupon_bid = create_response.get_json(force=True)["data"]["coupon_bid"]

    with app.app_context():
        coupon = Coupon.query.filter(Coupon.coupon_bid == coupon_bid).first()
        used_code = (
            CouponUsage.query.filter(CouponUsage.coupon_bid == coupon_bid)
            .order_by(CouponUsage.id.asc())
            .first()
        )
        assert coupon is not None
        assert used_code is not None
        used_code.user_bid = "learner-1"
        used_code.order_bid = "order-1"
        used_code.shifu_bid = "course-1"
        used_code.status = COUPON_STATUS_USED
        _seed_order("order-1", "course-1", "learner-1", paid="79.00")
        coupon.used_count = 1
        used_code_bid = used_code.coupon_usage_bid
        used_code_value = str(used_code.value)
        used_code_discount_type = used_code.discount_type
        db.session.commit()

    update_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}",
        json={
            "name": "Updated Batch",
            "code": "SPRINGBATCH",
            "usage_type": COUPON_APPLY_TYPE_SPECIFIC,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 4,
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "start_at": "2026-04-25 10:00:00",
            "end_at": "2026-05-30 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    update_payload = update_response.get_json(force=True)

    assert update_payload["code"] == 0

    with app.app_context():
        coupon = Coupon.query.filter(Coupon.coupon_bid == coupon_bid).first()
        assert coupon is not None
        assert coupon.name == "Updated Batch"
        assert coupon.code == ""
        assert coupon.discount_type == COUPON_TYPE_FIXED
        assert str(coupon.value) == "20.00"
        assert coupon.total_count == 4

        used_code = CouponUsage.query.filter(
            CouponUsage.coupon_usage_bid == used_code_bid
        ).first()
        assert used_code is not None
        assert used_code.order_bid == "order-1"
        assert str(used_code.value) == used_code_value
        assert used_code.discount_type == used_code_discount_type
        assert used_code.shifu_bid == "course-1"

        unused_codes = CouponUsage.query.filter(
            CouponUsage.coupon_bid == coupon_bid,
            CouponUsage.deleted == 0,
            CouponUsage.order_bid == "",
        ).all()
        assert len(unused_codes) == 3
        assert all(code.shifu_bid == "course-1" for code in unused_codes)
        assert all(code.discount_type == COUPON_TYPE_FIXED for code in unused_codes)
        assert all(str(code.value) == "20.00" for code in unused_codes)


def test_admin_promotions_coupon_code_list_supports_keyword_filter(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_user("learner-1", "learner1@example.com", "Learner One")
        _seed_user("learner-2", "learner2@example.com", "Learner Two")
        _seed_course("course-1", "Coupon Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Spring Batch",
            "code": "SPRINGBATCH",
            "usage_type": COUPON_APPLY_TYPE_SPECIFIC,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 3,
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    coupon_bid = create_response.get_json(force=True)["data"]["coupon_bid"]

    with app.app_context():
        usages = (
            CouponUsage.query.filter(CouponUsage.coupon_bid == coupon_bid)
            .order_by(CouponUsage.id.asc())
            .all()
        )
        _seed_order("order-1", "course-1", "learner-1", paid="79.00")
        _seed_order("order-2", "course-1", "learner-2", paid="69.00")
        usages[0].user_bid = "learner-1"
        usages[0].order_bid = "order-1"
        usages[0].status = COUPON_STATUS_USED
        usages[1].user_bid = "learner-2"
        usages[1].order_bid = "order-2"
        usages[1].status = COUPON_STATUS_USED
        db.session.commit()

    code_response = test_client.get(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}/codes",
        query_string={"page_index": 1, "page_size": 1, "keyword": "order-2"},
        headers={"Token": "test-token"},
    )
    code_payload = code_response.get_json(force=True)

    assert code_payload["code"] == 0
    assert code_payload["data"]["total"] == 1
    assert code_payload["data"]["summary"]["usage_count"] == 1
    assert code_payload["data"]["items"][0]["user_bid"] == "learner-2"
    assert code_payload["data"]["items"][0]["order_bid"] == "order-2"


def test_admin_promotions_campaign_routes_round_trip(app, test_client, monkeypatch):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_user("learner-2", "learner@example.com", "Learner Two")
        _seed_course("course-2", "Campaign Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Early Bird",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-2",
            "discount_type": COUPON_TYPE_PERCENT,
            "value": "15",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "description": "Launch campaign",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    create_payload = create_response.get_json(force=True)
    promo_bid = create_payload["data"]["promo_bid"]

    assert create_payload["code"] == 0

    with app.app_context():
        _seed_order("order-2", "course-2", "learner-2", paid="84.15")
        redemption = PromoRedemption()
        redemption.redemption_bid = "redemption-1"
        redemption.promo_bid = promo_bid
        redemption.order_bid = "order-2"
        redemption.user_bid = "learner-2"
        redemption.shifu_bid = "course-2"
        redemption.promo_name = "Early Bird"
        redemption.discount_type = COUPON_TYPE_PERCENT
        redemption.value = Decimal("15")
        redemption.discount_amount = Decimal("14.85")
        redemption.status = PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED
        db.session.add(redemption)
        db.session.commit()

    list_response = test_client.get(
        "/api/shifu/admin/operations/promotions/campaigns",
        query_string={"page_index": 1, "page_size": 20},
        headers={"Token": "test-token"},
    )
    list_payload = list_response.get_json(force=True)

    assert list_payload["code"] == 0
    assert list_payload["data"]["total"] == 1
    assert list_payload["data"]["summary"]["usage_count"] == 1
    assert list_payload["data"]["items"][0]["name"] == "Early Bird"

    course_query_by_id_response = test_client.get(
        "/api/shifu/admin/operations/promotions/campaigns",
        query_string={
            "page_index": 1,
            "page_size": 20,
            "shifu_bid": "course-2",
            "course_name": "course-2",
        },
        headers={"Token": "test-token"},
    )
    course_query_by_id_payload = course_query_by_id_response.get_json(force=True)

    assert course_query_by_id_payload["code"] == 0
    assert course_query_by_id_payload["data"]["total"] == 1
    assert course_query_by_id_payload["data"]["items"][0]["promo_bid"] == promo_bid

    course_query_by_name_response = test_client.get(
        "/api/shifu/admin/operations/promotions/campaigns",
        query_string={
            "page_index": 1,
            "page_size": 20,
            "shifu_bid": "Campaign Course",
            "course_name": "Campaign Course",
        },
        headers={"Token": "test-token"},
    )
    course_query_by_name_payload = course_query_by_name_response.get_json(force=True)

    assert course_query_by_name_payload["code"] == 0
    assert course_query_by_name_payload["data"]["total"] == 1
    assert course_query_by_name_payload["data"]["items"][0]["promo_bid"] == promo_bid

    detail_response = test_client.get(
        f"/api/shifu/admin/operations/promotions/campaigns/{promo_bid}",
        headers={"Token": "test-token"},
    )
    detail_payload = detail_response.get_json(force=True)

    assert detail_payload["code"] == 0
    assert detail_payload["data"]["campaign"]["promo_bid"] == promo_bid
    assert (
        detail_payload["data"]["campaign"]["apply_type"]
        == PROMO_CAMPAIGN_JOIN_TYPE_EVENT
    )
    assert detail_payload["data"]["campaign"]["channel"] == "app"
    assert detail_payload["data"]["campaign"]["has_redemptions"] is True
    assert detail_payload["data"]["description"] == "Launch campaign"

    redemption_response = test_client.get(
        f"/api/shifu/admin/operations/promotions/campaigns/{promo_bid}/redemptions",
        query_string={"page_index": 1, "page_size": 20},
        headers={"Token": "test-token"},
    )
    redemption_payload = redemption_response.get_json(force=True)

    assert redemption_payload["code"] == 0
    assert redemption_payload["data"]["total"] == 1
    assert redemption_payload["data"]["items"][0]["order_bid"] == "order-2"


def test_admin_promotions_campaign_redemptions_support_keyword_filter(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_user("learner-1", "learner1@example.com", "Learner One")
        _seed_user("learner-2", "learner2@example.com", "Learner Two")
        _seed_course("course-2", "Campaign Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Early Bird",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-2",
            "discount_type": COUPON_TYPE_PERCENT,
            "value": "15",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "description": "Launch campaign",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    promo_bid = create_response.get_json(force=True)["data"]["promo_bid"]

    with app.app_context():
        _seed_order("order-1", "course-2", "learner-1", paid="84.15")
        _seed_order("order-2", "course-2", "learner-2", paid="74.15")
        db.session.add_all(
            [
                PromoRedemption(
                    redemption_bid="redemption-1",
                    promo_bid=promo_bid,
                    order_bid="order-1",
                    user_bid="learner-1",
                    shifu_bid="course-2",
                    promo_name="Early Bird",
                    discount_type=COUPON_TYPE_PERCENT,
                    value=Decimal("15"),
                    discount_amount=Decimal("14.85"),
                    status=PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
                ),
                PromoRedemption(
                    redemption_bid="redemption-2",
                    promo_bid=promo_bid,
                    order_bid="order-2",
                    user_bid="learner-2",
                    shifu_bid="course-2",
                    promo_name="Early Bird",
                    discount_type=COUPON_TYPE_PERCENT,
                    value=Decimal("15"),
                    discount_amount=Decimal("13.35"),
                    status=PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
                ),
            ]
        )
        db.session.commit()

    redemption_response = test_client.get(
        f"/api/shifu/admin/operations/promotions/campaigns/{promo_bid}/redemptions",
        query_string={
            "page_index": 1,
            "page_size": 1,
            "keyword": "learner2@example.com",
        },
        headers={"Token": "test-token"},
    )
    redemption_payload = redemption_response.get_json(force=True)

    assert redemption_payload["code"] == 0
    assert redemption_payload["data"]["total"] == 1
    assert redemption_payload["data"]["summary"]["usage_count"] == 1
    assert redemption_payload["data"]["items"][0]["user_bid"] == "learner-2"
    assert redemption_payload["data"]["items"][0]["order_bid"] == "order-2"


def test_admin_promotions_campaign_redemptions_summary_only_counts_applied(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_user("learner-1", "learner1@example.com", "Learner One")
        _seed_user("learner-2", "learner2@example.com", "Learner Two")
        _seed_course("course-2", "Campaign Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Early Bird",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-2",
            "discount_type": COUPON_TYPE_PERCENT,
            "value": "15",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "description": "Launch campaign",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    promo_bid = create_response.get_json(force=True)["data"]["promo_bid"]

    with app.app_context():
        _seed_order("order-1", "course-2", "learner-1", paid="84.15")
        _seed_order("order-2", "course-2", "learner-2", paid="74.15")
        db.session.add_all(
            [
                PromoRedemption(
                    redemption_bid="redemption-1",
                    promo_bid=promo_bid,
                    order_bid="order-1",
                    user_bid="learner-1",
                    shifu_bid="course-2",
                    promo_name="Early Bird",
                    discount_type=COUPON_TYPE_PERCENT,
                    value=Decimal("15"),
                    discount_amount=Decimal("14.85"),
                    status=PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
                ),
                PromoRedemption(
                    redemption_bid="redemption-2",
                    promo_bid=promo_bid,
                    order_bid="order-2",
                    user_bid="learner-2",
                    shifu_bid="course-2",
                    promo_name="Early Bird",
                    discount_type=COUPON_TYPE_PERCENT,
                    value=Decimal("15"),
                    discount_amount=Decimal("13.35"),
                    status=PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED,
                ),
            ]
        )
        db.session.commit()

    redemption_response = test_client.get(
        f"/api/shifu/admin/operations/promotions/campaigns/{promo_bid}/redemptions",
        query_string={"page_index": 1, "page_size": 20},
        headers={"Token": "test-token"},
    )
    redemption_payload = redemption_response.get_json(force=True)

    assert redemption_payload["code"] == 0
    assert redemption_payload["data"]["total"] == 2
    assert redemption_payload["data"]["summary"]["active"] == 1
    assert redemption_payload["data"]["summary"]["usage_count"] == 1
    assert redemption_payload["data"]["summary"]["discount_amount"] == "14.85"


def test_admin_promotions_campaign_route_rejects_overlap(app, test_client, monkeypatch):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-3", "Overlap Course")
        db.session.commit()

    first_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Window One",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
            "shifu_bid": "course-3",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "10",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    assert first_response.get_json(force=True)["code"] == 0

    second_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Window Two",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
            "shifu_bid": "course-3",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "5",
            "start_at": "2026-05-01 10:00:00",
            "end_at": "2026-05-20 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    second_payload = second_response.get_json(force=True)

    assert second_response.status_code == 200
    assert second_payload["code"] != 0


def test_admin_promotions_coupon_update_rejects_locked_fields(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-1", "Coupon Course")
        _seed_course("course-2", "Other Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Locked Coupon",
            "code": "LOCKED",
            "usage_type": 801,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 10,
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    coupon_bid = create_response.get_json(force=True)["data"]["coupon_bid"]

    update_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}",
        json={
            "name": "Locked Coupon Updated",
            "code": "CHANGED",
            "usage_type": 801,
            "discount_type": COUPON_TYPE_PERCENT,
            "value": "10",
            "total_count": 12,
            "scope_type": "single_course",
            "shifu_bid": "course-2",
            "start_at": "2026-04-25 10:00:00",
            "end_at": "2026-05-25 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )

    assert update_response.get_json(force=True)["code"] != 0


def test_admin_promotions_coupon_update_allows_changing_only_end_time(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-1", "Coupon Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Partial Coupon",
            "code": "PARTIAL",
            "usage_type": 801,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 10,
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    coupon_bid = create_response.get_json(force=True)["data"]["coupon_bid"]

    update_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}",
        json={
            "name": "Partial Coupon",
            "code": "PARTIAL",
            "usage_type": 801,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 10,
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "end_at": "2026-05-30 23:59",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )

    assert update_response.get_json(force=True)["code"] == 0

    with app.app_context():
        coupon = Coupon.query.filter(Coupon.coupon_bid == coupon_bid).first()
        assert coupon is not None
        assert coupon.start == datetime.strptime(
            "2026-04-24 10:00:00", "%Y-%m-%d %H:%M:%S"
        )
        assert coupon.end == datetime.strptime(
            "2026-05-30 23:59:00", "%Y-%m-%d %H:%M:%S"
        )


def test_admin_promotions_coupon_update_ignores_empty_start_time(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-1-empty-start", "Coupon Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Keep Start Coupon",
            "code": "KEEPSTART",
            "usage_type": 801,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 10,
            "scope_type": "single_course",
            "shifu_bid": "course-1-empty-start",
            "start_at": "2026-04-24 10:00:00",
            "end_at": "2026-05-24 10:00:00",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    coupon_bid = create_response.get_json(force=True)["data"]["coupon_bid"]

    update_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}",
        json={
            "name": "Keep Start Coupon Updated",
            "code": "KEEPSTART",
            "usage_type": 801,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 10,
            "scope_type": "single_course",
            "shifu_bid": "course-1-empty-start",
            "start_at": "",
            "end_at": "2026-05-30 23:59",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )

    assert update_response.get_json(force=True)["code"] == 0

    with app.app_context():
        coupon = Coupon.query.filter(Coupon.coupon_bid == coupon_bid).first()
        assert coupon is not None
        assert coupon.start == datetime.strptime(
            "2026-04-24 10:00:00", "%Y-%m-%d %H:%M:%S"
        )
        assert coupon.end == datetime.strptime(
            "2026-05-30 23:59:00", "%Y-%m-%d %H:%M:%S"
        )


def test_admin_promotions_coupon_status_rejects_enabling_expired_coupon(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-1", "Coupon Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/coupons",
        json={
            "name": "Expired Coupon",
            "code": "EXPIRED",
            "usage_type": 801,
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "total_count": 10,
            "scope_type": "single_course",
            "shifu_bid": "course-1",
            "start_at": "2000-01-01 10:00:00",
            "end_at": "2000-01-02 10:00:00",
            "enabled": False,
        },
        headers={"Token": "test-token"},
    )
    coupon_bid = create_response.get_json(force=True)["data"]["coupon_bid"]

    enable_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/coupons/{coupon_bid}/status",
        json={"enabled": True},
        headers={"Token": "test-token"},
    )

    assert enable_response.get_json(force=True)["code"] != 0


def test_admin_promotions_campaign_update_only_allows_name_description_time_and_apply_type(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-4", "Editable Campaign Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Editable Campaign",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-4",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "start_at": "2099-04-24 10:00:00",
            "end_at": "2099-05-24 10:00:00",
            "description": "Before",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    promo_bid = create_response.get_json(force=True)["data"]["promo_bid"]

    update_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/campaigns/{promo_bid}",
        json={
            "name": "Editable Campaign Updated",
            "apply_type": 2103,
            "shifu_bid": "course-4",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "start_at": "2099-04-25 10:00:00",
            "end_at": "2099-05-25 10:00:00",
            "description": "After",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )

    assert update_response.get_json(force=True)["code"] == 0

    with app.app_context():
        campaign = PromoCampaign.query.filter(
            PromoCampaign.promo_bid == promo_bid
        ).first()
        assert campaign is not None
        assert campaign.name == "Editable Campaign Updated"
        assert campaign.description == "After"
        assert campaign.apply_type == 2103
        assert campaign.channel == "app"
        assert str(campaign.value) == "20.00"


def test_admin_promotions_campaign_update_rejects_channel_and_value_change_before_redemption(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-4b", "Editable Campaign Course 2")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Editable Campaign",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-4b",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "start_at": "2099-04-24 10:00:00",
            "end_at": "2099-05-24 10:00:00",
            "description": "Before",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    promo_bid = create_response.get_json(force=True)["data"]["promo_bid"]

    update_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/campaigns/{promo_bid}",
        json={
            "name": "Editable Campaign Updated",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_MANUAL,
            "shifu_bid": "course-4b",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "25",
            "start_at": "2099-04-25 10:00:00",
            "end_at": "2099-05-25 10:00:00",
            "description": "After",
            "channel": "web",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )

    assert update_response.get_json(force=True)["code"] != 0


def test_admin_promotions_campaign_update_allows_changing_only_start_time(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-8", "Partial Campaign Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Partial Campaign",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-8",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "start_at": "2099-04-24 10:00:00",
            "end_at": "2099-05-24 10:00:00",
            "description": "Before",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    promo_bid = create_response.get_json(force=True)["data"]["promo_bid"]

    update_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/campaigns/{promo_bid}",
        json={
            "name": "Partial Campaign",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-8",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "start_at": "2099-04-25 10:30",
            "description": "Before",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )

    assert update_response.get_json(force=True)["code"] == 0

    with app.app_context():
        campaign = PromoCampaign.query.filter(
            PromoCampaign.promo_bid == promo_bid
        ).first()
        assert campaign is not None
        assert campaign.start_at == datetime.strptime(
            "2099-04-25 10:30:00", "%Y-%m-%d %H:%M:%S"
        )
        assert campaign.end_at == datetime.strptime(
            "2099-05-24 10:00:00", "%Y-%m-%d %H:%M:%S"
        )


def test_admin_promotions_campaign_update_ignores_null_end_time(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-8-null-end", "Partial Campaign Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Keep End Campaign",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-8-null-end",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "start_at": "2099-04-24 10:00:00",
            "end_at": "2099-05-24 10:00:00",
            "description": "Before",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    promo_bid = create_response.get_json(force=True)["data"]["promo_bid"]

    update_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/campaigns/{promo_bid}",
        json={
            "name": "Keep End Campaign Updated",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-8-null-end",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "start_at": "2099-04-25 10:30",
            "end_at": None,
            "description": "After",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )

    assert update_response.get_json(force=True)["code"] == 0

    with app.app_context():
        campaign = PromoCampaign.query.filter(
            PromoCampaign.promo_bid == promo_bid
        ).first()
        assert campaign is not None
        assert campaign.start_at == datetime.strptime(
            "2099-04-25 10:30:00", "%Y-%m-%d %H:%M:%S"
        )
        assert campaign.end_at == datetime.strptime(
            "2099-05-24 10:00:00", "%Y-%m-%d %H:%M:%S"
        )


def test_format_promotion_admin_datetime_accepts_string_value(app):
    with app.app_context():
        assert (
            _format_promotion_admin_datetime("2026-04-28 14:38:41")
            == "2026-04-28T06:38:41Z"
        )


def test_format_promotion_admin_datetime_returns_empty_for_invalid_string(app):
    with app.app_context():
        warning = Mock()
        app.logger.warning = warning

        assert _format_promotion_admin_datetime("not-a-datetime") == ""
        warning.assert_called_once()


def test_admin_promotions_campaign_update_rejects_apply_type_change_after_redemption(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_user("learner-3", "learner3@example.com", "Learner Three")
        _seed_course("course-5", "Locked Campaign Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Locked Campaign",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-5",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "start_at": "2099-04-24 10:00:00",
            "end_at": "2099-05-24 10:00:00",
            "description": "Before",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    promo_bid = create_response.get_json(force=True)["data"]["promo_bid"]

    with app.app_context():
        _seed_order("order-locked", "course-5", "learner-3", paid="79.00")
        redemption = PromoRedemption()
        redemption.redemption_bid = "redemption-locked"
        redemption.promo_bid = promo_bid
        redemption.order_bid = "order-locked"
        redemption.user_bid = "learner-3"
        redemption.shifu_bid = "course-5"
        redemption.promo_name = "Locked Campaign"
        redemption.discount_type = COUPON_TYPE_FIXED
        redemption.value = Decimal("20")
        redemption.discount_amount = Decimal("20")
        redemption.status = PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED
        db.session.add(redemption)
        db.session.commit()

    update_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/campaigns/{promo_bid}",
        json={
            "name": "Locked Campaign Updated",
            "apply_type": 2103,
            "shifu_bid": "course-5",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "start_at": "2099-04-25 10:00:00",
            "end_at": "2099-05-25 10:00:00",
            "description": "After",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )

    assert update_response.get_json(force=True)["code"] != 0


def test_admin_promotions_campaign_update_rejects_channel_and_value_change_after_redemption(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_user("learner-4", "learner4@example.com", "Learner Four")
        _seed_course("course-7", "Partially Locked Campaign Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Partially Locked Campaign",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-7",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "start_at": "2099-04-24 10:00:00",
            "end_at": "2099-05-24 10:00:00",
            "description": "Before",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    promo_bid = create_response.get_json(force=True)["data"]["promo_bid"]

    with app.app_context():
        _seed_order("order-channel-locked", "course-7", "learner-4", paid="79.00")
        redemption = PromoRedemption()
        redemption.redemption_bid = "redemption-channel-locked"
        redemption.promo_bid = promo_bid
        redemption.order_bid = "order-channel-locked"
        redemption.user_bid = "learner-4"
        redemption.shifu_bid = "course-7"
        redemption.promo_name = "Partially Locked Campaign"
        redemption.discount_type = COUPON_TYPE_FIXED
        redemption.value = Decimal("20")
        redemption.discount_amount = Decimal("20")
        redemption.status = PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED
        db.session.add(redemption)
        db.session.commit()

    update_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/campaigns/{promo_bid}",
        json={
            "name": "Partially Locked Campaign Updated",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-7",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "25",
            "start_at": "2099-04-25 10:00:00",
            "end_at": "2099-05-25 10:00:00",
            "description": "After",
            "channel": "web",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )

    assert update_response.get_json(force=True)["code"] != 0


def test_admin_promotions_campaign_status_rejects_enabling_ended_campaign(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-6", "Ended Campaign Course")
        db.session.commit()

    create_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Ended Campaign",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            "shifu_bid": "course-6",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "start_at": "2000-04-24 10:00:00",
            "end_at": "2000-05-24 10:00:00",
            "description": "Ended",
            "channel": "app",
            "enabled": False,
        },
        headers={"Token": "test-token"},
    )
    promo_bid = create_response.get_json(force=True)["data"]["promo_bid"]

    enable_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/campaigns/{promo_bid}/status",
        json={"enabled": True},
        headers={"Token": "test-token"},
    )

    assert enable_response.get_json(force=True)["code"] != 0


def test_admin_promotions_campaign_status_allows_manual_campaign_overlap_with_auto(
    app, test_client, monkeypatch
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user("operator-1", "operator@example.com", "Operator", is_operator=True)
        _seed_course("course-6-manual-overlap", "Overlap Campaign Course")
        db.session.commit()

    auto_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Auto Campaign",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
            "shifu_bid": "course-6-manual-overlap",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "20",
            "start_at": "2099-04-24 10:00:00",
            "end_at": "2099-05-24 10:00:00",
            "description": "Auto",
            "channel": "app",
            "enabled": True,
        },
        headers={"Token": "test-token"},
    )
    assert auto_response.get_json(force=True)["code"] == 0

    manual_response = test_client.post(
        "/api/shifu/admin/operations/promotions/campaigns",
        json={
            "name": "Manual Campaign",
            "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_MANUAL,
            "shifu_bid": "course-6-manual-overlap",
            "discount_type": COUPON_TYPE_FIXED,
            "value": "10",
            "start_at": "2099-05-01 10:00:00",
            "end_at": "2099-05-20 10:00:00",
            "description": "Manual",
            "channel": "app",
            "enabled": False,
        },
        headers={"Token": "test-token"},
    )
    promo_bid = manual_response.get_json(force=True)["data"]["promo_bid"]

    enable_response = test_client.post(
        f"/api/shifu/admin/operations/promotions/campaigns/{promo_bid}/status",
        json={"enabled": True},
        headers={"Token": "test-token"},
    )

    assert enable_response.get_json(force=True)["code"] == 0
