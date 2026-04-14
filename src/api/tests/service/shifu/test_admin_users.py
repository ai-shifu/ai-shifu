from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
import sys

from flaskr.dao import db
from flaskr.service.common.dtos import PageNationDTO
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.admin import get_operator_user_detail, list_operator_users
from flaskr.service.shifu.admin_dtos import AdminOperationUserSummaryDTO
from flaskr.service.shifu.models import (
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.user.consts import (
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import (
    AuthCredential,
    UserInfo as UserEntity,
    UserToken,
)
from flaskr.service.user.repository import create_user_entity, upsert_credential


@pytest.fixture(autouse=True)
def _mock_bcrypt_module(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "bcrypt",
        SimpleNamespace(
            gensalt=lambda rounds=12: b"salt",
            hashpw=lambda plain, salt: plain + b":" + salt,
            checkpw=lambda plain, hashed: hashed == plain + b":salt",
        ),
    )


@pytest.fixture(autouse=True)
def _isolate_tables(app):
    with app.app_context():
        db.session.query(LearnProgressRecord).delete()
        db.session.query(PublishedOutlineItem).delete()
        db.session.query(UserToken).delete()
        db.session.query(Order).delete()
        db.session.query(PublishedShifu).delete()
        db.session.query(DraftShifu).delete()
        db.session.query(AuthCredential).delete()
        db.session.query(UserEntity).delete()
        db.session.commit()
        db.session.remove()
    yield
    with app.app_context():
        db.session.query(LearnProgressRecord).delete()
        db.session.query(PublishedOutlineItem).delete()
        db.session.query(UserToken).delete()
        db.session.query(Order).delete()
        db.session.query(PublishedShifu).delete()
        db.session.query(DraftShifu).delete()
        db.session.query(AuthCredential).delete()
        db.session.query(UserEntity).delete()
        db.session.commit()
        db.session.remove()


def _mock_operator(
    monkeypatch,
    user_id: str = "operator-1",
    *,
    is_operator: bool = True,
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
    app,
    *,
    user_bid: str,
    identify: str,
    nickname: str,
    state: int,
    language: str = "en-US",
    is_creator: bool = False,
    is_operator: bool = False,
    created_at: datetime,
    updated_at: datetime,
    providers: list[tuple[str, str]] | None = None,
):
    entity = create_user_entity(
        user_bid=user_bid,
        identify=identify,
        nickname=nickname,
        language=language,
        state=state,
    )
    entity.is_creator = 1 if is_creator else 0
    entity.is_operator = 1 if is_operator else 0
    entity.created_at = created_at
    entity.updated_at = updated_at
    db.session.flush()

    for provider_name, identifier in providers or []:
        upsert_credential(
            app,
            user_bid=user_bid,
            provider_name=provider_name,
            subject_id=identifier,
            subject_format=provider_name,
            identifier=identifier,
            metadata={},
            verified=True,
        )
    db.session.commit()
    db.session.remove()


def _seed_course(
    *,
    model,
    shifu_bid: str,
    title: str,
    creator_user_bid: str,
    created_at: datetime,
    updated_at: datetime,
):
    course = model(
        shifu_bid=shifu_bid,
        title=title,
        created_user_bid=creator_user_bid,
        updated_user_bid=creator_user_bid,
    )
    course.created_at = created_at
    course.updated_at = updated_at
    db.session.add(course)
    db.session.commit()
    db.session.remove()
    return course


def _seed_success_order(
    *,
    order_bid: str,
    shifu_bid: str,
    user_bid: str,
    created_at: datetime,
):
    order = Order(
        order_bid=order_bid,
        shifu_bid=shifu_bid,
        user_bid=user_bid,
        status=ORDER_STATUS_SUCCESS,
    )
    order.created_at = created_at
    order.updated_at = created_at
    db.session.add(order)
    db.session.commit()
    db.session.remove()
    return order


def _seed_published_outline_item(
    *,
    shifu_bid: str,
    outline_item_bid: str,
    title: str,
    parent_bid: str,
    position: str,
    hidden: int = 0,
):
    outline_item = PublishedOutlineItem(
        shifu_bid=shifu_bid,
        outline_item_bid=outline_item_bid,
        title=title,
        parent_bid=parent_bid,
        position=position,
        hidden=hidden,
    )
    db.session.add(outline_item)
    db.session.commit()
    db.session.remove()
    return outline_item


def _seed_learn_progress(
    *,
    shifu_bid: str,
    outline_item_bid: str,
    user_bid: str,
    status: int,
    created_at: datetime,
):
    progress_record = LearnProgressRecord(
        progress_record_bid=f"progress-{user_bid}-{outline_item_bid}-{status}",
        shifu_bid=shifu_bid,
        outline_item_bid=outline_item_bid,
        user_bid=user_bid,
        status=status,
    )
    progress_record.created_at = created_at
    progress_record.updated_at = created_at
    db.session.add(progress_record)
    db.session.commit()
    db.session.remove()
    return progress_record


def _seed_user_token(*, user_bid: str, token: str, created_at: datetime):
    user_token = UserToken(
        user_id=user_bid,
        token=token,
    )
    user_token.created = created_at
    user_token.updated = created_at
    db.session.add(user_token)
    db.session.commit()
    db.session.remove()
    return user_token


def test_list_operator_users_returns_paginated_summaries_with_resolved_metadata(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="user-regular",
            identify="13800138000",
            nickname="Regular User",
            state=USER_STATE_REGISTERED,
            language="zh-CN",
            created_at=datetime(2026, 4, 1, 9, 0, 0),
            updated_at=datetime(2026, 4, 2, 9, 0, 0),
            providers=[("phone", "13800138000")],
        )
        _seed_user(
            app,
            user_bid="user-operator",
            identify="operator@example.com",
            nickname="Operator User",
            state=USER_STATE_PAID,
            language="en-US",
            is_creator=True,
            is_operator=True,
            created_at=datetime(2026, 4, 3, 9, 0, 0),
            updated_at=datetime(2026, 4, 4, 9, 0, 0),
            providers=[
                ("google", "operator@example.com"),
                ("email", "operator@example.com"),
            ],
        )

        result = list_operator_users(app, 1, 1, {})

    assert isinstance(result, PageNationDTO)
    assert result.total == 2
    assert len(result.data) == 1
    item = result.data[0]
    assert isinstance(item, AdminOperationUserSummaryDTO)
    assert item.user_bid == "user-operator"
    assert item.mobile == ""
    assert item.email == "operator@example.com"
    assert item.nickname == "Operator User"
    assert item.user_status == "paid"
    assert item.user_role == "operator"
    assert item.user_roles == ["operator", "creator"]
    assert item.login_methods == ["google", "email"]
    assert item.registration_source == "google"
    assert item.language == "en-US"
    assert item.learning_courses == []
    assert item.created_courses == []
    assert item.total_paid_amount == "0"
    assert item.last_login_at == ""
    assert item.last_learning_at == ""
    assert item.created_at == "2026-04-03 09:00:00"
    assert item.updated_at == "2026-04-04 09:00:00"


def test_list_operator_users_filters_by_identifier_status_role_and_created_time(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="user-a",
            identify="13900001111",
            nickname="Alice",
            state=USER_STATE_REGISTERED,
            is_creator=True,
            created_at=datetime(2026, 4, 1, 9, 0, 0),
            updated_at=datetime(2026, 4, 1, 10, 0, 0),
            providers=[("phone", "13900001111")],
        )
        _seed_user(
            app,
            user_bid="user-b",
            identify="13900002222",
            nickname="Bob",
            state=USER_STATE_TRAIL,
            created_at=datetime(2026, 4, 5, 9, 0, 0),
            updated_at=datetime(2026, 4, 5, 10, 0, 0),
            providers=[("phone", "13900002222")],
        )
        result = list_operator_users(
            app,
            1,
            20,
            {
                "identifier": "1111",
                "user_status": "registered",
                "user_role": "creator",
                "start_time": datetime(2026, 4, 1, 0, 0, 0),
                "end_time": datetime(2026, 4, 2, 23, 59, 59),
            },
        )

    assert result.total == 1
    assert [item.user_bid for item in result.data] == ["user-a"]
    assert result.data[0].mobile == "13900001111"
    assert result.data[0].user_role == "creator"
    assert result.data[0].user_roles == ["creator"]
    assert result.data[0].user_status == "registered"
    assert result.data[0].registration_source == "phone"
    assert result.data[0].learning_courses == []
    assert result.data[0].created_courses == []


def test_list_operator_users_filters_by_email_identifier(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="user-email",
            identify="user@example.com",
            nickname="Email User",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 6, 9, 0, 0),
            updated_at=datetime(2026, 4, 6, 10, 0, 0),
            providers=[("email", "user@example.com")],
        )

        result = list_operator_users(
            app,
            1,
            20,
            {
                "identifier": "user@example.com",
            },
        )

    assert result.total == 1
    assert result.data[0].user_bid == "user-email"
    assert result.data[0].email == "user@example.com"
    assert result.data[0].user_roles == ["regular"]
    assert result.data[0].registration_source == "email"
    assert result.data[0].learning_courses == []
    assert result.data[0].created_courses == []


def test_list_operator_users_returns_learning_and_created_courses(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="creator-user",
            identify="13800001111",
            nickname="Creator User",
            state=USER_STATE_REGISTERED,
            is_creator=True,
            created_at=datetime(2026, 4, 8, 9, 0, 0),
            updated_at=datetime(2026, 4, 8, 10, 0, 0),
            providers=[("phone", "13800001111")],
        )
        _seed_user(
            app,
            user_bid="learner-user",
            identify="13900002222",
            nickname="Learner User",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 7, 9, 0, 0),
            updated_at=datetime(2026, 4, 7, 10, 0, 0),
            providers=[("phone", "13900002222")],
        )
        _seed_course(
            model=DraftShifu,
            shifu_bid="course-created-draft",
            title="Draft Course",
            creator_user_bid="creator-user",
            created_at=datetime(2026, 4, 8, 11, 0, 0),
            updated_at=datetime(2026, 4, 8, 11, 30, 0),
        )
        _seed_course(
            model=PublishedShifu,
            shifu_bid="course-created-published",
            title="Published Course",
            creator_user_bid="creator-user",
            created_at=datetime(2026, 4, 6, 11, 0, 0),
            updated_at=datetime(2026, 4, 9, 11, 30, 0),
        )
        _seed_course(
            model=PublishedShifu,
            shifu_bid="course-learned",
            title="Learned Course",
            creator_user_bid="creator-user",
            created_at=datetime(2026, 4, 5, 11, 0, 0),
            updated_at=datetime(2026, 4, 5, 11, 30, 0),
        )
        _seed_success_order(
            order_bid="order-1",
            shifu_bid="course-learned",
            user_bid="learner-user",
            created_at=datetime(2026, 4, 10, 9, 0, 0),
        )
        _seed_success_order(
            order_bid="order-2",
            shifu_bid="course-created-published",
            user_bid="creator-user",
            created_at=datetime(2026, 4, 10, 10, 0, 0),
        )

        result = list_operator_users(app, 1, 20, {})

    assert result.total == 2
    assert [item.user_bid for item in result.data] == ["creator-user", "learner-user"]
    creator_item = result.data[0]
    learner_item = result.data[1]
    assert creator_item.user_role == "creator"
    assert learner_item.user_role == "learner"
    assert creator_item.user_roles == ["creator", "learner"]
    assert learner_item.user_roles == ["learner"]

    assert [course.course_name for course in creator_item.created_courses] == [
        "Published Course",
        "Draft Course",
        "Learned Course",
    ]
    assert [course.course_status for course in creator_item.created_courses] == [
        "published",
        "unpublished",
        "published",
    ]
    assert [course.course_name for course in creator_item.learning_courses] == [
        "Published Course"
    ]
    assert [course.course_name for course in learner_item.learning_courses] == [
        "Learned Course"
    ]
    assert learner_item.created_courses == []


def test_list_operator_users_filters_by_learner_role(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="learner-filter-user",
            identify="13700001111",
            nickname="Learner Filter",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 11, 9, 0, 0),
            updated_at=datetime(2026, 4, 11, 10, 0, 0),
            providers=[("phone", "13700001111")],
        )
        _seed_user(
            app,
            user_bid="regular-filter-user",
            identify="13700002222",
            nickname="Regular Filter",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 11, 9, 0, 0),
            updated_at=datetime(2026, 4, 11, 10, 0, 0),
            providers=[("phone", "13700002222")],
        )
        _seed_success_order(
            order_bid="order-learner-filter",
            shifu_bid="course-learner-filter",
            user_bid="learner-filter-user",
            created_at=datetime(2026, 4, 11, 11, 0, 0),
        )

        result = list_operator_users(app, 1, 20, {"user_role": "learner"})

    assert [item.user_bid for item in result.data] == ["learner-filter-user"]
    assert result.data[0].user_role == "learner"
    assert result.data[0].user_roles == ["learner"]


def test_get_operator_user_detail_returns_full_summary(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="detail-user",
            identify="detail@example.com",
            nickname="Detail User",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "detail@example.com")],
        )
        _seed_course(
            model=PublishedShifu,
            shifu_bid="detail-course",
            title="Detail Course",
            creator_user_bid="detail-user",
            created_at=datetime(2026, 4, 9, 11, 0, 0),
            updated_at=datetime(2026, 4, 9, 11, 30, 0),
        )

        item = get_operator_user_detail(app, "detail-user")

    assert item.user_bid == "detail-user"
    assert item.email == "detail@example.com"
    assert item.user_role == "creator"
    assert item.user_roles == ["creator"]
    assert [course.course_name for course in item.created_courses] == ["Detail Course"]
    assert item.learning_courses == []


def test_get_operator_user_detail_returns_registration_login_payment_and_learning_data(
    app,
):
    with app.app_context():
        _seed_user(
            app,
            user_bid="user-profile-rich",
            identify="rich@example.com",
            nickname="Rich User",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "rich@example.com")],
        )
        _seed_user_token(
            user_bid="user-profile-rich",
            token="token-1",
            created_at=datetime(2026, 4, 10, 8, 0, 0),
        )
        _seed_success_order(
            order_bid="order-rich-1",
            shifu_bid="course-rich-1",
            user_bid="user-profile-rich",
            created_at=datetime(2026, 4, 10, 9, 0, 0),
        )
        paid_order = Order.query.filter(Order.order_bid == "order-rich-1").first()
        paid_order.paid_price = Decimal("88.50")
        db.session.commit()
        _seed_learn_progress(
            shifu_bid="course-rich-1",
            outline_item_bid="lesson-rich-1",
            user_bid="user-profile-rich",
            status=LEARN_STATUS_IN_PROGRESS,
            created_at=datetime(2026, 4, 11, 10, 0, 0),
        )

        item = get_operator_user_detail(app, "user-profile-rich")

    assert item.registration_source == "email"
    assert item.last_login_at == "2026-04-10 08:00:00"
    assert item.total_paid_amount == "88.50"
    assert item.last_learning_at == "2026-04-11 10:00:00"


def test_get_operator_user_detail_returns_learning_progress_for_learning_courses(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="learner-progress-user",
            identify="13800003333",
            nickname="Learner Progress",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("phone", "13800003333")],
        )
        _seed_course(
            model=PublishedShifu,
            shifu_bid="learning-progress-course",
            title="Learning Progress Course",
            creator_user_bid="creator-user",
            created_at=datetime(2026, 4, 9, 11, 0, 0),
            updated_at=datetime(2026, 4, 9, 11, 30, 0),
        )
        _seed_published_outline_item(
            shifu_bid="learning-progress-course",
            outline_item_bid="chapter-1",
            title="Chapter 1",
            parent_bid="",
            position="1",
        )
        _seed_published_outline_item(
            shifu_bid="learning-progress-course",
            outline_item_bid="lesson-1",
            title="Lesson 1",
            parent_bid="chapter-1",
            position="1.1",
        )
        _seed_published_outline_item(
            shifu_bid="learning-progress-course",
            outline_item_bid="lesson-2",
            title="Lesson 2",
            parent_bid="chapter-1",
            position="1.2",
        )
        _seed_success_order(
            order_bid="order-learning-progress",
            shifu_bid="learning-progress-course",
            user_bid="learner-progress-user",
            created_at=datetime(2026, 4, 10, 9, 0, 0),
        )
        _seed_learn_progress(
            shifu_bid="learning-progress-course",
            outline_item_bid="lesson-1",
            user_bid="learner-progress-user",
            status=LEARN_STATUS_COMPLETED,
            created_at=datetime(2026, 4, 10, 9, 30, 0),
        )
        _seed_learn_progress(
            shifu_bid="learning-progress-course",
            outline_item_bid="lesson-2",
            user_bid="learner-progress-user",
            status=LEARN_STATUS_IN_PROGRESS,
            created_at=datetime(2026, 4, 10, 10, 0, 0),
        )

        item = get_operator_user_detail(app, "learner-progress-user")

    assert len(item.learning_courses) == 1
    assert item.learning_courses[0].course_name == "Learning Progress Course"
    assert item.learning_courses[0].completed_lesson_count == 1
    assert item.learning_courses[0].total_lesson_count == 2


def test_admin_operation_users_route_requires_operator(test_client, monkeypatch):
    _mock_operator(monkeypatch, is_operator=False)

    response = test_client.get(
        "/api/shifu/admin/operations/users",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 401


def test_admin_operation_users_route_returns_filtered_payload(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user(
            app,
            user_bid="user-route-1",
            identify="13812345678",
            nickname="Route Target",
            state=USER_STATE_UNREGISTERED,
            created_at=datetime(2026, 4, 6, 8, 0, 0),
            updated_at=datetime(2026, 4, 6, 12, 0, 0),
            providers=[("phone", "13812345678")],
        )
        _seed_user(
            app,
            user_bid="user-route-2",
            identify="paid@example.com",
            nickname="Other User",
            state=USER_STATE_PAID,
            is_operator=True,
            created_at=datetime(2026, 4, 7, 8, 0, 0),
            updated_at=datetime(2026, 4, 7, 12, 0, 0),
            providers=[("email", "paid@example.com")],
        )

    response = test_client.get(
        "/api/shifu/admin/operations/users",
        query_string={
            "page_index": 1,
            "page_size": 20,
            "nickname": "Route",
            "user_status": "unregistered",
        },
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["total"] == 1
    assert payload["data"]["items"] == [
        {
            "user_bid": "user-route-1",
            "mobile": "13812345678",
            "email": "",
            "nickname": "Route Target",
            "user_status": "unregistered",
            "user_role": "regular",
            "user_roles": ["regular"],
            "login_methods": ["phone"],
            "registration_source": "phone",
            "language": "en-US",
            "learning_courses": [],
            "created_courses": [],
            "total_paid_amount": "0",
            "last_login_at": "",
            "last_learning_at": "",
            "created_at": "2026-04-06 08:00:00",
            "updated_at": "2026-04-06 12:00:00",
        }
    ]


def test_admin_operation_user_detail_route_returns_payload(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user(
            app,
            user_bid="user-detail-route",
            identify="13812340000",
            nickname="Detail Route User",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 10, 8, 0, 0),
            updated_at=datetime(2026, 4, 10, 12, 0, 0),
            providers=[("phone", "13812340000")],
        )

    response = test_client.get(
        "/api/shifu/admin/operations/users/user-detail-route/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"] == {
        "user_bid": "user-detail-route",
        "mobile": "13812340000",
        "email": "",
        "nickname": "Detail Route User",
        "user_status": "registered",
        "user_role": "regular",
        "user_roles": ["regular"],
        "login_methods": ["phone"],
        "registration_source": "phone",
        "language": "en-US",
        "learning_courses": [],
        "created_courses": [],
        "total_paid_amount": "0",
        "last_login_at": "",
        "last_learning_at": "",
        "created_at": "2026-04-10 08:00:00",
        "updated_at": "2026-04-10 12:00:00",
    }
