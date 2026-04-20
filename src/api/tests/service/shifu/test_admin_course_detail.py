from __future__ import annotations

import sys
from types import SimpleNamespace
from datetime import datetime
from decimal import Decimal

import pytest

from flaskr.dao import db
from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.learn.const import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_RESET,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnLessonFeedback,
    LearnProgressRecord,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS, ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.models import Order
from flaskr.service.promo.consts import (
    COUPON_STATUS_USED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
)
from flaskr.service.promo.models import CouponUsage, PromoRedemption
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_CONTENT_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    UNIT_TYPE_VALUE_GUEST,
    UNIT_TYPE_VALUE_NORMAL,
    UNIT_TYPE_VALUE_TRIAL,
)
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.admin import (
    get_operator_course_chapter_detail,
    get_operator_course_detail,
)
from flaskr.service.user.models import (
    AuthCredential,
    UserInfo as UserEntity,
    UserToken,
)
from flaskr.service.user.repository import create_user_entity, upsert_credential


def _clear_tables() -> None:
    db.session.query(LearnLessonFeedback).delete()
    db.session.query(LearnGeneratedBlock).delete()
    db.session.query(LearnProgressRecord).delete()
    db.session.query(PromoRedemption).delete()
    db.session.query(CouponUsage).delete()
    db.session.query(Order).delete()
    db.session.query(UserToken).delete()
    db.session.query(AiCourseAuth).delete()
    db.session.query(DraftOutlineItem).delete()
    db.session.query(PublishedOutlineItem).delete()
    db.session.query(DraftShifu).delete()
    db.session.query(PublishedShifu).delete()
    db.session.query(AuthCredential).delete()
    db.session.query(UserEntity).delete()
    db.session.commit()
    db.session.remove()


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
        _clear_tables()
    yield
    with app.app_context():
        _clear_tables()


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


def _seed_user(app, *, user_bid: str, email: str = "", phone: str = "") -> None:
    identify = email or phone or user_bid
    create_user_entity(
        user_bid=user_bid,
        identify=identify,
        nickname=f"user-{user_bid[:6]}",
        language="en-US",
        state=1,
    )
    if email:
        upsert_credential(
            app,
            user_bid=user_bid,
            provider_name="email",
            subject_id=email,
            subject_format="email",
            identifier=email,
            metadata={},
            verified=True,
        )
    if phone:
        upsert_credential(
            app,
            user_bid=user_bid,
            provider_name="phone",
            subject_id=phone,
            subject_format="phone",
            identifier=phone,
            metadata={},
            verified=True,
        )
    db.session.flush()


def _set_user_flags(
    *,
    user_bid: str,
    is_creator: int = 0,
    is_operator: int = 0,
) -> None:
    user = (
        UserEntity.query.filter(
            UserEntity.user_bid == user_bid, UserEntity.deleted == 0
        )
        .order_by(UserEntity.id.desc())
        .first()
    )
    assert user is not None
    user.is_creator = is_creator
    user.is_operator = is_operator
    db.session.flush()


def _seed_progress(
    *,
    shifu_bid: str,
    outline_item_bid: str,
    user_bid: str,
    status: int,
    created_at: datetime,
    updated_at: datetime,
) -> None:
    db.session.add(
        LearnProgressRecord(
            progress_record_bid=f"progress-{user_bid}-{outline_item_bid}-{status}",
            shifu_bid=shifu_bid,
            outline_item_bid=outline_item_bid,
            user_bid=user_bid,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
        )
    )


def _seed_paid_order(
    *,
    shifu_bid: str,
    user_bid: str,
    paid_price: str,
    created_at: datetime,
) -> None:
    db.session.add(
        Order(
            order_bid=f"order-{user_bid}-{shifu_bid}",
            shifu_bid=shifu_bid,
            user_bid=user_bid,
            paid_price=Decimal(paid_price),
            payable_price=Decimal(paid_price),
            status=ORDER_STATUS_SUCCESS,
            created_at=created_at,
            updated_at=created_at,
        )
    )


def _seed_coupon_usage(
    *,
    coupon_usage_bid: str,
    order_bid: str,
    shifu_bid: str,
    user_bid: str,
    code: str = "FULLREDEEM",
) -> None:
    db.session.add(
        CouponUsage(
            coupon_usage_bid=coupon_usage_bid,
            coupon_bid=f"coupon-{coupon_usage_bid}",
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            order_bid=order_bid,
            code=code,
            status=COUPON_STATUS_USED,
            deleted=0,
        )
    )


def _seed_promo_redemption(
    *,
    redemption_bid: str,
    promo_bid: str,
    order_bid: str,
    shifu_bid: str,
    user_bid: str,
    discount_amount: str,
    promo_name: str = "Full Redeem Promo",
) -> None:
    db.session.add(
        PromoRedemption(
            redemption_bid=redemption_bid,
            promo_bid=promo_bid,
            order_bid=order_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            promo_name=promo_name,
            discount_amount=Decimal(discount_amount),
            status=PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
            deleted=0,
        )
    )


def _seed_course_permission(
    *,
    shifu_bid: str,
    user_bid: str,
    created_at: datetime,
) -> None:
    db.session.add(
        AiCourseAuth(
            course_auth_id=f"auth-{user_bid}-{shifu_bid}",
            course_id=shifu_bid,
            user_id=user_bid,
            auth_type='["view"]',
            status=1,
            created_at=created_at,
            updated_at=created_at,
        )
    )


def _seed_user_token(
    *,
    user_bid: str,
    token: str,
    created_at: datetime,
) -> None:
    db.session.add(
        UserToken(
            user_id=user_bid,
            token=token,
            created=created_at,
            updated=created_at,
        )
    )
    db.session.flush()


def _seed_course(
    *,
    shifu_bid: str,
    creator_user_bid: str,
    created_at: datetime,
    updated_at: datetime,
) -> None:
    db.session.add(
        DraftShifu(
            shifu_bid=shifu_bid,
            title="Draft Detail Course",
            description="draft",
            avatar_res_bid="",
            keywords="",
            llm="gpt-test",
            llm_temperature=Decimal("0"),
            llm_system_prompt="",
            price=Decimal("199.00"),
            deleted=0,
            created_at=created_at,
            created_user_bid=creator_user_bid,
            updated_at=updated_at,
            updated_user_bid=creator_user_bid,
        )
    )
    db.session.add(
        PublishedShifu(
            shifu_bid=shifu_bid,
            title="Published Detail Course",
            description="published",
            avatar_res_bid="",
            keywords="",
            llm="gpt-test",
            llm_temperature=Decimal("0"),
            llm_system_prompt="",
            price=Decimal("99.00"),
            deleted=0,
            created_at=created_at,
            created_user_bid=creator_user_bid,
            updated_at=created_at,
            updated_user_bid=creator_user_bid,
        )
    )


def _seed_outline(
    *,
    shifu_bid: str,
    model,
    outline_item_bid: str,
    title: str,
    position: str,
    parent_bid: str = "",
    hidden: int = 0,
    item_type: int = 402,
    updated_at: datetime,
    updated_user_bid: str = "creator-1",
    content: str = "",
    llm_system_prompt: str = "",
) -> None:
    db.session.add(
        model(
            outline_item_bid=outline_item_bid,
            shifu_bid=shifu_bid,
            title=title,
            parent_bid=parent_bid,
            position=position,
            hidden=hidden,
            type=item_type,
            llm="",
            llm_temperature=0,
            llm_system_prompt=llm_system_prompt,
            ask_enabled_status=0,
            ask_llm="",
            ask_llm_temperature=0,
            ask_llm_system_prompt="",
            content=content,
            deleted=0,
            created_at=updated_at,
            created_user_bid="creator-1",
            updated_at=updated_at,
            updated_user_bid=updated_user_bid,
        )
    )


def test_admin_operation_course_detail_route_returns_latest_detail(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    monkeypatch.setattr(
        "flaskr.service.shifu.admin.get_course_visit_count_30d",
        lambda _app, _shifu_bid: 7,
    )
    created_at = datetime(2026, 4, 1, 9, 0, 0)
    updated_at = datetime(2026, 4, 3, 15, 30, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        _seed_user(app, user_bid="modifier-1", phone="13900001234")
        _seed_course(
            shifu_bid="course-detail",
            creator_user_bid="creator-1",
            created_at=created_at,
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="chapter-1",
            title="Chapter 1",
            position="1",
            item_type=UNIT_TYPE_VALUE_GUEST,
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="lesson-1",
            title="Lesson 1",
            parent_bid="chapter-1",
            position="1.1",
            item_type=UNIT_TYPE_VALUE_TRIAL,
            updated_at=updated_at,
            updated_user_bid="modifier-1",
            content="# Lesson 1 content",
            llm_system_prompt="lesson system prompt",
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="lesson-2",
            title="Lesson 2",
            parent_bid="chapter-1",
            position="1.2",
            hidden=1,
            updated_at=updated_at,
            updated_user_bid="modifier-1",
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=PublishedOutlineItem,
            outline_item_bid="published-chapter",
            title="Published Chapter",
            position="1",
            updated_at=created_at,
        )
        db.session.add_all(
            [
                LearnProgressRecord(
                    progress_record_bid="progress-1",
                    shifu_bid="course-detail",
                    outline_item_bid="lesson-1",
                    user_bid="learner-1",
                    status=LEARN_STATUS_COMPLETED,
                    block_position=0,
                    deleted=0,
                    created_at=updated_at,
                    updated_at=updated_at,
                ),
                LearnProgressRecord(
                    progress_record_bid="progress-2",
                    shifu_bid="course-detail",
                    outline_item_bid="lesson-1",
                    user_bid="learner-2",
                    status=LEARN_STATUS_IN_PROGRESS,
                    block_position=0,
                    deleted=0,
                    created_at=updated_at,
                    updated_at=updated_at,
                ),
                LearnProgressRecord(
                    progress_record_bid="progress-3",
                    shifu_bid="course-detail",
                    outline_item_bid="lesson-1",
                    user_bid="learner-reset",
                    status=LEARN_STATUS_RESET,
                    block_position=0,
                    deleted=0,
                    created_at=updated_at,
                    updated_at=updated_at,
                ),
                Order(
                    order_bid="order-1",
                    shifu_bid="course-detail",
                    user_bid="learner-1",
                    paid_price=Decimal("88.00"),
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=updated_at,
                    updated_at=updated_at,
                ),
                Order(
                    order_bid="order-2",
                    shifu_bid="course-detail",
                    user_bid="learner-2",
                    paid_price=Decimal("66.00"),
                    status=ORDER_STATUS_TO_BE_PAID,
                    deleted=0,
                    created_at=updated_at,
                    updated_at=updated_at,
                ),
                LearnGeneratedBlock(
                    generated_block_bid="follow-1",
                    progress_record_bid="progress-1",
                    user_bid="learner-1",
                    block_bid="",
                    outline_item_bid="lesson-1",
                    shifu_bid="course-detail",
                    type=BLOCK_TYPE_MDASK_VALUE,
                    role=ROLE_STUDENT,
                    generated_content="Question 1",
                    position=1,
                    block_content_conf="",
                    status=1,
                    deleted=0,
                    created_at=updated_at,
                    updated_at=updated_at,
                ),
                LearnGeneratedBlock(
                    generated_block_bid="follow-ignore-role",
                    progress_record_bid="progress-1",
                    user_bid="learner-1",
                    block_bid="",
                    outline_item_bid="lesson-1",
                    shifu_bid="course-detail",
                    type=BLOCK_TYPE_MDASK_VALUE,
                    role=ROLE_TEACHER,
                    generated_content="Ignore",
                    position=2,
                    block_content_conf="",
                    status=1,
                    deleted=0,
                    created_at=updated_at,
                    updated_at=updated_at,
                ),
                LearnGeneratedBlock(
                    generated_block_bid="follow-ignore-type",
                    progress_record_bid="progress-2",
                    user_bid="learner-2",
                    block_bid="",
                    outline_item_bid="lesson-1",
                    shifu_bid="course-detail",
                    type=BLOCK_TYPE_CONTENT_VALUE,
                    role=ROLE_STUDENT,
                    generated_content="Ignore",
                    position=3,
                    block_content_conf="",
                    status=1,
                    deleted=0,
                    created_at=updated_at,
                    updated_at=updated_at,
                ),
                LearnLessonFeedback(
                    bid="feedback-1",
                    lesson_feedback_bid="feedback-1",
                    shifu_bid="course-detail",
                    outline_item_bid="lesson-1",
                    progress_record_bid="progress-1",
                    user_bid="learner-1",
                    score=5,
                    comment="Great",
                    mode="read",
                    deleted=0,
                    created_at=updated_at,
                    updated_at=updated_at,
                ),
                LearnLessonFeedback(
                    bid="feedback-2",
                    lesson_feedback_bid="feedback-2",
                    shifu_bid="course-detail",
                    outline_item_bid="lesson-2",
                    progress_record_bid="progress-2",
                    user_bid="learner-2",
                    score=3,
                    comment="Okay",
                    mode="read",
                    deleted=0,
                    created_at=updated_at,
                    updated_at=updated_at,
                ),
                LearnLessonFeedback(
                    bid="feedback-deleted",
                    lesson_feedback_bid="feedback-deleted",
                    shifu_bid="course-detail",
                    outline_item_bid="lesson-1",
                    progress_record_bid="progress-2",
                    user_bid="learner-2",
                    score=4,
                    comment="Ignore",
                    mode="read",
                    deleted=1,
                    created_at=updated_at,
                    updated_at=updated_at,
                ),
            ]
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["basic_info"] == {
        "shifu_bid": "course-detail",
        "course_name": "Draft Detail Course",
        "course_status": "published",
        "creator_user_bid": "creator-1",
        "creator_mobile": "13800001234",
        "creator_email": "",
        "creator_nickname": "user-creato",
        "created_at": "2026-04-01 09:00:00",
        "updated_at": "2026-04-03 15:30:00",
    }
    assert payload["data"]["metrics"] == {
        "visit_count_30d": 7,
        "learner_count": 2,
        "order_count": 1,
        "order_amount": "88",
        "follow_up_count": 1,
        "rating_score": "4.0",
    }
    assert payload["data"]["chapters"] == [
        {
            "outline_item_bid": "chapter-1",
            "title": "Chapter 1",
            "parent_bid": "",
            "position": "1",
            "node_type": "chapter",
            "learning_permission": "guest",
            "is_visible": True,
            "content_status": "empty",
            "follow_up_count": 1,
            "rating_count": 2,
            "modifier_user_bid": "creator-1",
            "modifier_mobile": "13800001234",
            "modifier_email": "",
            "modifier_nickname": "user-creato",
            "updated_at": "2026-04-03 15:30:00",
            "children": [
                {
                    "outline_item_bid": "lesson-1",
                    "title": "Lesson 1",
                    "parent_bid": "chapter-1",
                    "position": "1.1",
                    "node_type": "lesson",
                    "learning_permission": "free",
                    "is_visible": True,
                    "content_status": "has",
                    "follow_up_count": 1,
                    "rating_count": 1,
                    "modifier_user_bid": "modifier-1",
                    "modifier_mobile": "13900001234",
                    "modifier_email": "",
                    "modifier_nickname": "user-modifi",
                    "updated_at": "2026-04-03 15:30:00",
                    "children": [],
                },
                {
                    "outline_item_bid": "lesson-2",
                    "title": "Lesson 2",
                    "parent_bid": "chapter-1",
                    "position": "1.2",
                    "node_type": "lesson",
                    "learning_permission": "paid",
                    "is_visible": False,
                    "content_status": "empty",
                    "follow_up_count": 0,
                    "rating_count": 1,
                    "modifier_user_bid": "modifier-1",
                    "modifier_mobile": "13900001234",
                    "modifier_email": "",
                    "modifier_nickname": "user-modifi",
                    "updated_at": "2026-04-03 15:30:00",
                    "children": [],
                },
            ],
        }
    ]


def test_admin_operation_course_detail_route_sorts_numeric_positions_and_surfaces_unknown_permission(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    updated_at = datetime(2026, 4, 3, 15, 30, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        _seed_course(
            shifu_bid="course-detail",
            creator_user_bid="creator-1",
            created_at=updated_at,
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="chapter-10",
            title="Chapter 10",
            position="10",
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="chapter-2",
            title="Chapter 2",
            position="2",
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="lesson-2",
            title="Lesson 2",
            parent_bid="chapter-2",
            position="2.2",
            item_type=0,
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="lesson-10",
            title="Lesson 10",
            parent_bid="chapter-2",
            position="2.10",
            item_type=UNIT_TYPE_VALUE_TRIAL,
            updated_at=updated_at,
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert [chapter["outline_item_bid"] for chapter in payload["data"]["chapters"]] == [
        "chapter-2",
        "chapter-10",
    ]
    assert [
        lesson["outline_item_bid"]
        for lesson in payload["data"]["chapters"][0]["children"]
    ] == ["lesson-2", "lesson-10"]
    assert payload["data"]["chapters"][0]["children"][0]["learning_permission"] == (
        "unknown"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/shifu/admin/operations/courses/course-detail/detail",
        "/api/shifu/admin/operations/courses/course-detail/chapters/lesson-1/detail",
        "/api/shifu/admin/operations/courses/course-detail/users?page=1&page_size=20",
    ],
)
def test_admin_operation_course_detail_routes_require_operator(
    test_client,
    monkeypatch,
    path,
):
    _mock_operator(monkeypatch, is_operator=False)

    response = test_client.get(path, headers={"Token": "test-token"})
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 401


def test_admin_operation_course_chapter_detail_route_returns_prompt_content(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    updated_at = datetime(2026, 4, 3, 15, 30, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        _seed_course(
            shifu_bid="course-detail",
            creator_user_bid="creator-1",
            created_at=updated_at,
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="lesson-1",
            title="Lesson 1",
            position="1.1",
            parent_bid="chapter-1",
            updated_at=updated_at,
            content="# Lesson 1 content",
            llm_system_prompt="lesson system prompt",
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/chapters/lesson-1/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"] == {
        "outline_item_bid": "lesson-1",
        "title": "Lesson 1",
        "content": "# Lesson 1 content",
        "llm_system_prompt": "lesson system prompt",
        "llm_system_prompt_source": "lesson",
    }


def test_admin_operation_course_chapter_detail_route_falls_back_to_chapter_and_course(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    updated_at = datetime(2026, 4, 3, 15, 30, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        db.session.add(
            DraftShifu(
                shifu_bid="course-detail",
                title="Draft Detail Course",
                description="draft",
                avatar_res_bid="",
                keywords="",
                llm="gpt-test",
                llm_temperature=Decimal("0"),
                llm_system_prompt="course system prompt",
                price=Decimal("199.00"),
                deleted=0,
                created_at=updated_at,
                created_user_bid="creator-1",
                updated_at=updated_at,
                updated_user_bid="creator-1",
            )
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="chapter-1",
            title="Chapter 1",
            position="1",
            updated_at=updated_at,
            llm_system_prompt="chapter system prompt",
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="lesson-1",
            title="Lesson 1",
            position="1.1",
            parent_bid="chapter-1",
            updated_at=updated_at,
            content="# Lesson 1 content",
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/chapters/lesson-1/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"] == {
        "outline_item_bid": "lesson-1",
        "title": "Lesson 1",
        "content": "# Lesson 1 content",
        "llm_system_prompt": "chapter system prompt",
        "llm_system_prompt_source": "chapter",
    }


def test_admin_operation_course_chapter_detail_route_falls_back_to_course(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    updated_at = datetime(2026, 4, 3, 15, 30, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        db.session.add(
            DraftShifu(
                shifu_bid="course-detail",
                title="Draft Detail Course",
                description="draft",
                avatar_res_bid="",
                keywords="",
                llm="gpt-test",
                llm_temperature=Decimal("0"),
                llm_system_prompt="course system prompt",
                price=Decimal("199.00"),
                deleted=0,
                created_at=updated_at,
                created_user_bid="creator-1",
                updated_at=updated_at,
                updated_user_bid="creator-1",
            )
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="chapter-1",
            title="Chapter 1",
            position="1",
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="lesson-1",
            title="Lesson 1",
            position="1.1",
            parent_bid="chapter-1",
            updated_at=updated_at,
            content="# Lesson 1 content",
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/chapters/lesson-1/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"] == {
        "outline_item_bid": "lesson-1",
        "title": "Lesson 1",
        "content": "# Lesson 1 content",
        "llm_system_prompt": "course system prompt",
        "llm_system_prompt_source": "course",
    }


def test_admin_operation_course_detail_route_keeps_empty_draft_outline(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    created_at = datetime(2026, 4, 1, 9, 0, 0)
    updated_at = datetime(2026, 4, 3, 15, 30, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        _seed_course(
            shifu_bid="course-detail",
            creator_user_bid="creator-1",
            created_at=created_at,
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=PublishedOutlineItem,
            outline_item_bid="published-chapter",
            title="Published Chapter",
            position="1",
            updated_at=created_at,
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["basic_info"]["course_name"] == "Draft Detail Course"
    assert payload["data"]["chapters"] == []


def test_admin_operation_course_detail_route_ignores_soft_deleted_latest_outline_revision(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    updated_at = datetime(2026, 4, 3, 15, 30, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        _seed_course(
            shifu_bid="course-detail",
            creator_user_bid="creator-1",
            created_at=updated_at,
            updated_at=updated_at,
        )
        db.session.add(
            DraftOutlineItem(
                outline_item_bid="chapter-1",
                shifu_bid="course-detail",
                title="Chapter 1",
                parent_bid="",
                position="1",
                hidden=0,
                type=UNIT_TYPE_VALUE_GUEST,
                llm="",
                llm_temperature=0,
                llm_system_prompt="",
                ask_enabled_status=0,
                ask_llm="",
                ask_llm_temperature=0,
                ask_llm_system_prompt="",
                content="",
                deleted=0,
                created_at=updated_at,
                created_user_bid="creator-1",
                updated_at=updated_at,
                updated_user_bid="creator-1",
            )
        )
        db.session.add(
            DraftOutlineItem(
                outline_item_bid="chapter-1",
                shifu_bid="course-detail",
                title="Chapter 1 deleted",
                parent_bid="",
                position="1",
                hidden=0,
                type=UNIT_TYPE_VALUE_GUEST,
                llm="",
                llm_temperature=0,
                llm_system_prompt="",
                ask_enabled_status=0,
                ask_llm="",
                ask_llm_temperature=0,
                ask_llm_system_prompt="",
                content="",
                deleted=1,
                created_at=updated_at,
                created_user_bid="creator-1",
                updated_at=updated_at,
                updated_user_bid="creator-1",
            )
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["chapters"] == []


def test_admin_operation_course_detail_route_rejects_missing_course(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)

    response = test_client.get(
        "/api/shifu/admin/operations/courses/missing-course/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 4008


def test_admin_operation_course_chapter_detail_route_rejects_missing_outline_item(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    updated_at = datetime(2026, 4, 3, 15, 30, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        _seed_course(
            shifu_bid="course-detail",
            creator_user_bid="creator-1",
            created_at=updated_at,
            updated_at=updated_at,
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/chapters/missing-lesson/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 4009


def test_get_operator_course_detail_rejects_blank_shifu_bid_with_params_error(app):
    with pytest.raises(AppException) as exc_info:
        get_operator_course_detail(app, shifu_bid="   ")

    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_get_operator_course_chapter_detail_rejects_blank_params_with_params_error(
    app,
):
    with pytest.raises(AppException) as exc_info:
        get_operator_course_chapter_detail(
            app,
            shifu_bid="   ",
            outline_item_bid="lesson-1",
        )
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_admin_operation_course_users_route_returns_course_related_users(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    created_at = datetime(2026, 4, 1, 9, 0, 0)
    updated_at = datetime(2026, 4, 3, 15, 30, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        _seed_user(app, user_bid="student-1", phone="13900001234")
        _seed_user(app, user_bid="student-2", email="student2@example.com")
        _set_user_flags(user_bid="creator-1", is_creator=1)
        _seed_course(
            shifu_bid="course-detail",
            creator_user_bid="creator-1",
            created_at=created_at,
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="chapter-1",
            title="Chapter 1",
            position="1",
            item_type=UNIT_TYPE_VALUE_GUEST,
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="lesson-1",
            title="Lesson 1",
            parent_bid="chapter-1",
            position="1.1",
            item_type=UNIT_TYPE_VALUE_TRIAL,
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="lesson-2",
            title="Lesson 2",
            parent_bid="chapter-1",
            position="1.2",
            item_type=UNIT_TYPE_VALUE_NORMAL,
            updated_at=updated_at,
        )
        _seed_progress(
            shifu_bid="course-detail",
            outline_item_bid="lesson-1",
            user_bid="student-1",
            status=LEARN_STATUS_IN_PROGRESS,
            created_at=datetime(2026, 4, 4, 10, 0, 0),
            updated_at=datetime(2026, 4, 4, 10, 5, 0),
        )
        _seed_progress(
            shifu_bid="course-detail",
            outline_item_bid="lesson-1",
            user_bid="student-2",
            status=LEARN_STATUS_COMPLETED,
            created_at=datetime(2026, 4, 2, 9, 0, 0),
            updated_at=datetime(2026, 4, 2, 9, 10, 0),
        )
        _seed_progress(
            shifu_bid="course-detail",
            outline_item_bid="lesson-2",
            user_bid="student-2",
            status=LEARN_STATUS_COMPLETED,
            created_at=datetime(2026, 4, 3, 9, 0, 0),
            updated_at=datetime(2026, 4, 3, 9, 10, 0),
        )
        _seed_paid_order(
            shifu_bid="course-detail",
            user_bid="student-1",
            paid_price="99.00",
            created_at=datetime(2026, 4, 5, 8, 0, 0),
        )
        _seed_course_permission(
            shifu_bid="course-detail",
            user_bid="student-2",
            created_at=datetime(2026, 4, 2, 8, 30, 0),
        )
        _seed_user_token(
            user_bid="student-1",
            token="token-1",
            created_at=datetime(2026, 4, 5, 9, 0, 0),
        )
        _seed_user_token(
            user_bid="creator-1",
            token="token-creator",
            created_at=datetime(2026, 4, 6, 9, 0, 0),
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/users?page=1&page_size=20",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["total"] == 3

    items_by_user_bid = {item["user_bid"]: item for item in payload["data"]["items"]}
    assert set(items_by_user_bid) == {"creator-1", "student-1", "student-2"}

    creator_item = items_by_user_bid["creator-1"]
    assert creator_item["mobile"] == "13800001234"
    assert creator_item["user_role"] == "creator"
    assert creator_item["learning_status"] == "not_started"
    assert creator_item["learned_lesson_count"] == 0
    assert creator_item["total_lesson_count"] == 2
    assert creator_item["joined_at"] == "2026-04-01 09:00:00"
    assert creator_item["last_login_at"] == "2026-04-06 09:00:00"

    paid_item = items_by_user_bid["student-1"]
    assert paid_item["mobile"] == "13900001234"
    assert paid_item["user_role"] == "student"
    assert paid_item["learned_lesson_count"] == 1
    assert paid_item["total_lesson_count"] == 2
    assert paid_item["learning_status"] == "learning"
    assert paid_item["is_paid"] is True
    assert paid_item["total_paid_amount"] == "99"
    assert paid_item["joined_at"] == "2026-04-04 10:00:00"
    assert paid_item["last_learning_at"] == "2026-04-04 10:05:00"
    assert paid_item["last_login_at"] == "2026-04-05 09:00:00"

    completed_item = items_by_user_bid["student-2"]
    assert completed_item["email"] == "student2@example.com"
    assert completed_item["user_role"] == "student"
    assert completed_item["learned_lesson_count"] == 2
    assert completed_item["total_lesson_count"] == 2
    assert completed_item["learning_status"] == "completed"
    assert completed_item["is_paid"] is False
    assert completed_item["joined_at"] == "2026-04-02 08:30:00"


def test_admin_operation_course_users_route_applies_filters(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    created_at = datetime(2026, 4, 1, 9, 0, 0)
    updated_at = datetime(2026, 4, 3, 15, 30, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        _seed_user(app, user_bid="student-1", phone="13900001234")
        _set_user_flags(user_bid="creator-1", is_creator=1)
        _seed_course(
            shifu_bid="course-detail",
            creator_user_bid="creator-1",
            created_at=created_at,
            updated_at=updated_at,
        )
        _seed_outline(
            shifu_bid="course-detail",
            model=DraftOutlineItem,
            outline_item_bid="lesson-1",
            title="Lesson 1",
            position="1",
            item_type=UNIT_TYPE_VALUE_NORMAL,
            updated_at=updated_at,
        )
        _seed_progress(
            shifu_bid="course-detail",
            outline_item_bid="lesson-1",
            user_bid="student-1",
            status=LEARN_STATUS_COMPLETED,
            created_at=datetime(2026, 4, 4, 10, 0, 0),
            updated_at=datetime(2026, 4, 4, 10, 5, 0),
        )
        _seed_paid_order(
            shifu_bid="course-detail",
            user_bid="student-1",
            paid_price="299.00",
            created_at=datetime(2026, 4, 5, 8, 0, 0),
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/users?page=1&page_size=20"
        "&payment_status=paid&learning_status=completed&keyword=1390",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["total"] == 1
    item = payload["data"]["items"][0]
    assert item["user_bid"] == "student-1"
    assert item["total_paid_amount"] == "299"


def test_admin_operation_course_detail_metrics_include_full_coupon_redemptions(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    monkeypatch.setattr(
        "flaskr.service.shifu.admin.get_course_visit_count_30d",
        lambda _app, _shifu_bid: 0,
    )
    created_at = datetime(2026, 4, 1, 9, 0, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        _seed_course(
            shifu_bid="course-detail",
            creator_user_bid="creator-1",
            created_at=created_at,
            updated_at=created_at,
        )
        db.session.add_all(
            [
                Order(
                    order_bid="order-direct-paid",
                    shifu_bid="course-detail",
                    user_bid="user-direct-paid",
                    payable_price=Decimal("88.00"),
                    paid_price=Decimal("88.00"),
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=created_at,
                    updated_at=created_at,
                ),
                Order(
                    order_bid="order-full-coupon",
                    shifu_bid="course-detail",
                    user_bid="user-full-coupon",
                    payable_price=Decimal("66.00"),
                    paid_price=Decimal("0.00"),
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=created_at,
                    updated_at=created_at,
                ),
                Order(
                    order_bid="order-activation",
                    shifu_bid="course-detail",
                    user_bid="user-activation",
                    payable_price=Decimal("0.00"),
                    paid_price=Decimal("0.00"),
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=created_at,
                    updated_at=created_at,
                ),
            ]
        )
        _seed_coupon_usage(
            coupon_usage_bid="coupon-usage-full-coupon",
            order_bid="order-full-coupon",
            shifu_bid="course-detail",
            user_bid="user-full-coupon",
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["metrics"]["order_count"] == 3
    assert payload["data"]["metrics"]["order_amount"] == "154"


def test_admin_operation_course_detail_metrics_include_full_promo_redemptions(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    monkeypatch.setattr(
        "flaskr.service.shifu.admin.get_course_visit_count_30d",
        lambda _app, _shifu_bid: 0,
    )
    created_at = datetime(2026, 4, 2, 9, 0, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        _seed_course(
            shifu_bid="course-detail",
            creator_user_bid="creator-1",
            created_at=created_at,
            updated_at=created_at,
        )
        db.session.add_all(
            [
                Order(
                    order_bid="order-direct-paid",
                    shifu_bid="course-detail",
                    user_bid="user-direct-paid",
                    payable_price=Decimal("88.00"),
                    paid_price=Decimal("88.00"),
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=created_at,
                    updated_at=created_at,
                ),
                Order(
                    order_bid="order-full-promo",
                    shifu_bid="course-detail",
                    user_bid="user-full-promo",
                    payable_price=Decimal("66.00"),
                    paid_price=Decimal("0.00"),
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=created_at,
                    updated_at=created_at,
                ),
            ]
        )
        _seed_promo_redemption(
            redemption_bid="promo-redemption-full",
            promo_bid="promo-full",
            order_bid="order-full-promo",
            shifu_bid="course-detail",
            user_bid="user-full-promo",
            discount_amount="66.00",
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["metrics"]["order_count"] == 2
    assert payload["data"]["metrics"]["order_amount"] == "154"


def test_admin_operation_course_detail_metrics_prefer_paid_price_and_fallback_to_payable_price(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    monkeypatch.setattr(
        "flaskr.service.shifu.admin.get_course_visit_count_30d",
        lambda _app, _shifu_bid: 0,
    )
    created_at = datetime(2026, 4, 3, 9, 0, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        _seed_course(
            shifu_bid="course-detail",
            creator_user_bid="creator-1",
            created_at=created_at,
            updated_at=created_at,
        )
        db.session.add_all(
            [
                Order(
                    order_bid="order-direct-paid",
                    shifu_bid="course-detail",
                    user_bid="user-direct-paid",
                    payable_price=Decimal("88.00"),
                    paid_price=Decimal("88.00"),
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=created_at,
                    updated_at=created_at,
                ),
                Order(
                    order_bid="order-partial-discount",
                    shifu_bid="course-detail",
                    user_bid="user-partial-discount",
                    payable_price=Decimal("49.00"),
                    paid_price=Decimal("19.00"),
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=created_at,
                    updated_at=created_at,
                ),
                Order(
                    order_bid="order-external-paid",
                    shifu_bid="course-detail",
                    user_bid="user-external-paid",
                    payable_price=Decimal("66.00"),
                    paid_price=Decimal("0.00"),
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=created_at,
                    updated_at=created_at,
                ),
            ]
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["metrics"]["order_count"] == 3
    assert payload["data"]["metrics"]["order_amount"] == "173"


def test_admin_operation_course_detail_metrics_include_successful_orders_across_channels(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)
    monkeypatch.setattr(
        "flaskr.service.shifu.admin.get_course_visit_count_30d",
        lambda _app, _shifu_bid: 0,
    )
    created_at = datetime(2026, 4, 4, 9, 0, 0)

    with app.app_context():
        _seed_user(app, user_bid="creator-1", phone="13800001234")
        _seed_course(
            shifu_bid="course-detail",
            creator_user_bid="creator-1",
            created_at=created_at,
            updated_at=created_at,
        )
        db.session.add_all(
            [
                Order(
                    order_bid="order-manual-paid",
                    shifu_bid="course-detail",
                    user_bid="user-manual-paid",
                    payable_price=Decimal("88.00"),
                    paid_price=Decimal("88.00"),
                    payment_channel="manual",
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=created_at,
                    updated_at=created_at,
                ),
                Order(
                    order_bid="order-manual-external-redeem",
                    shifu_bid="course-detail",
                    user_bid="user-manual-redeem",
                    payable_price=Decimal("66.00"),
                    paid_price=Decimal("0.00"),
                    payment_channel="manual",
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=created_at,
                    updated_at=created_at,
                ),
                Order(
                    order_bid="order-openapi-external-redeem",
                    shifu_bid="course-detail",
                    user_bid="user-openapi-redeem",
                    payable_price=Decimal("99.00"),
                    paid_price=Decimal("0.00"),
                    payment_channel="open_api",
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=created_at,
                    updated_at=created_at,
                ),
                Order(
                    order_bid="order-activation-zero",
                    shifu_bid="course-detail",
                    user_bid="user-activation-zero",
                    payable_price=Decimal("0.00"),
                    paid_price=Decimal("0.00"),
                    payment_channel="manual",
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=created_at,
                    updated_at=created_at,
                ),
            ]
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/admin/operations/courses/course-detail/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["metrics"]["order_count"] == 4
    assert payload["data"]["metrics"]["order_amount"] == "253"


@pytest.mark.parametrize(
    ("query_string", "expected_param"),
    [
        ("page=abc&page_size=20", "page"),
        ("page=1&page_size=xyz", "page_size"),
        ("page=0&page_size=20", "page"),
        ("page=1&page_size=0", "page_size"),
    ],
)
def test_admin_operation_course_users_route_rejects_invalid_pagination_params(
    test_client,
    monkeypatch,
    query_string,
    expected_param,
):
    _mock_operator(monkeypatch)

    response = test_client.get(
        f"/api/shifu/admin/operations/courses/course-detail/users?{query_string}",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == ERROR_CODE["server.common.paramsError"]
    assert payload["message"] == f"Params Error {expected_param}"
