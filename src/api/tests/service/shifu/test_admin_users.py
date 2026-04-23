from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
import sys

from flaskr.dao import db
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.models import CreditWallet, CreditWalletBucket
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
)
from flaskr.service.common.dtos import PageNationDTO
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.admin import (
    grant_operator_user_credits,
    get_operator_user_credits,
    get_operator_user_detail,
    list_operator_users,
)
from flaskr.service.shifu.admin_dtos import (
    AdminOperationUserCreditGrantRequestDTO,
    AdminOperationUserSummaryDTO,
)
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_UNVERIFIED,
    CREDENTIAL_STATE_VERIFIED,
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
        db.session.query(CreditLedgerEntry).delete()
        db.session.query(BillingOrder).delete()
        db.session.query(CreditWalletBucket).delete()
        db.session.query(CreditWallet).delete()
        db.session.query(LearnProgressRecord).delete()
        db.session.query(AiCourseAuth).delete()
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
        db.session.query(CreditLedgerEntry).delete()
        db.session.query(BillingOrder).delete()
        db.session.query(CreditWalletBucket).delete()
        db.session.query(CreditWallet).delete()
        db.session.query(LearnProgressRecord).delete()
        db.session.query(AiCourseAuth).delete()
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


def _format_operator_datetime(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _build_active_window(
    *,
    start_days_ago: int = 14,
    end_days_ahead: int = 30,
) -> tuple[datetime, datetime]:
    now = datetime.now().replace(microsecond=0)
    return now - timedelta(days=start_days_ago), now + timedelta(days=end_days_ahead)


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
    paid_price: str = "0.00",
    payable_price: str = "0.00",
):
    order = Order(
        order_bid=order_bid,
        shifu_bid=shifu_bid,
        user_bid=user_bid,
        status=ORDER_STATUS_SUCCESS,
        paid_price=Decimal(paid_price),
        payable_price=Decimal(payable_price),
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


def _seed_credit_wallet(
    *,
    creator_bid: str,
    wallet_bid: str,
    available_credits: str,
):
    wallet = CreditWallet(
        wallet_bid=wallet_bid,
        creator_bid=creator_bid,
        available_credits=Decimal(available_credits),
    )
    db.session.add(wallet)
    db.session.commit()
    db.session.remove()
    return wallet


def _seed_billing_order(
    *,
    creator_bid: str,
    bill_order_bid: str,
    metadata_json: dict | None = None,
):
    order = BillingOrder(
        bill_order_bid=bill_order_bid,
        creator_bid=creator_bid,
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        product_bid="product-1",
        subscription_bid="subscription-1",
        currency="CNY",
        payable_amount=0,
        paid_amount=0,
        payment_provider="manual",
        channel="manual",
        provider_reference_id="",
        status=BILLING_ORDER_STATUS_PAID,
        metadata_json=metadata_json or {},
    )
    db.session.add(order)
    db.session.commit()
    db.session.remove()
    return order


def _seed_billing_subscription(
    *,
    creator_bid: str,
    subscription_bid: str,
    current_period_start_at: datetime,
    current_period_end_at: datetime,
    status: int = BILLING_SUBSCRIPTION_STATUS_ACTIVE,
):
    subscription = BillingSubscription(
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
        product_bid="product-1",
        status=status,
        billing_provider="manual",
        provider_subscription_id="",
        provider_customer_id="",
        current_period_start_at=current_period_start_at,
        current_period_end_at=current_period_end_at,
        cancel_at_period_end=0,
        next_product_bid="",
        metadata_json={},
    )
    db.session.add(subscription)
    db.session.commit()
    db.session.remove()
    return subscription


def _seed_credit_wallet_bucket(
    *,
    creator_bid: str,
    wallet_bid: str,
    bucket_bid: str,
    available_credits: str,
    bucket_category: int,
    source_type: int,
    effective_from: datetime,
    effective_to: datetime | None = None,
):
    bucket = CreditWalletBucket(
        wallet_bucket_bid=bucket_bid,
        wallet_bid=wallet_bid,
        creator_bid=creator_bid,
        bucket_category=bucket_category,
        source_type=source_type,
        source_bid=f"source-{bucket_bid}",
        priority=10,
        original_credits=Decimal(available_credits),
        available_credits=Decimal(available_credits),
        reserved_credits=Decimal("0"),
        consumed_credits=Decimal("0"),
        expired_credits=Decimal("0"),
        effective_from=effective_from,
        effective_to=effective_to,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
    )
    db.session.add(bucket)
    db.session.commit()
    db.session.remove()
    return bucket


def _seed_credit_ledger_entry(
    *,
    creator_bid: str,
    wallet_bid: str,
    wallet_bucket_bid: str,
    ledger_bid: str,
    entry_type: int,
    source_type: int,
    source_bid: str,
    amount: str,
    balance_after: str,
    created_at: datetime,
    expires_at: datetime | None = None,
    consumable_from: datetime | None = None,
    metadata_json: dict | None = None,
):
    entry = CreditLedgerEntry(
        ledger_bid=ledger_bid,
        creator_bid=creator_bid,
        wallet_bid=wallet_bid,
        wallet_bucket_bid=wallet_bucket_bid,
        entry_type=entry_type,
        source_type=source_type,
        source_bid=source_bid,
        idempotency_key=f"idempotency-{ledger_bid}",
        amount=Decimal(amount),
        balance_after=Decimal(balance_after),
        expires_at=expires_at,
        consumable_from=consumable_from,
        metadata_json=metadata_json or {},
    )
    entry.created_at = created_at
    entry.updated_at = created_at
    db.session.add(entry)
    db.session.commit()
    db.session.remove()
    return entry


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


def _seed_course_auth(
    *,
    course_id: str,
    user_id: str,
    created_at: datetime,
    status: int = 1,
):
    course_auth = AiCourseAuth(
        course_auth_id=f"course-auth-{user_id}-{course_id}",
        course_id=course_id,
        user_id=user_id,
        auth_type="[1]",
        status=status,
    )
    course_auth.created_at = created_at
    course_auth.updated_at = created_at
    db.session.add(course_auth)
    db.session.commit()
    db.session.remove()
    return course_auth


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
    assert item.created_at == _format_operator_datetime(datetime(2026, 4, 3, 9, 0, 0))
    assert item.updated_at == _format_operator_datetime(datetime(2026, 4, 4, 9, 0, 0))


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


def test_list_operator_users_caps_page_size(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="user-page-size-a",
            identify="13810000001",
            nickname="Page Size A",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 1, 9, 0, 0),
            updated_at=datetime(2026, 4, 1, 10, 0, 0),
            providers=[("phone", "13810000001")],
        )
        _seed_user(
            app,
            user_bid="user-page-size-b",
            identify="13810000002",
            nickname="Page Size B",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 2, 9, 0, 0),
            updated_at=datetime(2026, 4, 2, 10, 0, 0),
            providers=[("phone", "13810000002")],
        )

        result = list_operator_users(app, 1, 999, {})

    assert isinstance(result, PageNationDTO)
    assert result.page_size == 100
    assert result.total == 2
    assert len(result.data) == 2


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


def test_list_operator_users_includes_creator_credit_summaries(app):
    with app.app_context():
        active_start_at, active_end_at = _build_active_window()
        future_start_at = active_end_at + timedelta(days=1)
        _seed_user(
            app,
            user_bid="creator-credits-user",
            identify="creator-credits@example.com",
            nickname="Creator Credits",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 12, 9, 0, 0),
            updated_at=datetime(2026, 4, 12, 10, 0, 0),
            providers=[("email", "creator-credits@example.com")],
        )
        _seed_user(
            app,
            user_bid="regular-no-credits",
            identify="13810009999",
            nickname="Regular No Credits",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 11, 9, 0, 0),
            updated_at=datetime(2026, 4, 11, 10, 0, 0),
            providers=[("phone", "13810009999")],
        )
        _seed_credit_wallet(
            creator_bid="creator-credits-user",
            wallet_bid="wallet-creator-credits-user",
            available_credits="999.0000000000",
        )
        _seed_billing_subscription(
            creator_bid="creator-credits-user",
            subscription_bid="subscription-creator-credits-user",
            current_period_start_at=active_start_at,
            current_period_end_at=active_end_at,
        )
        _seed_credit_wallet_bucket(
            creator_bid="creator-credits-user",
            wallet_bid="wallet-creator-credits-user",
            bucket_bid="bucket-subscription-active",
            available_credits="12.5000000000",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            effective_from=active_start_at,
            effective_to=None,
        )
        _seed_credit_wallet_bucket(
            creator_bid="creator-credits-user",
            wallet_bid="wallet-creator-credits-user",
            bucket_bid="bucket-topup-active",
            available_credits="8.0000000000",
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            effective_from=active_start_at,
            effective_to=active_end_at + timedelta(days=15),
        )
        _seed_credit_wallet_bucket(
            creator_bid="creator-credits-user",
            wallet_bid="wallet-creator-credits-user",
            bucket_bid="bucket-topup-expired",
            available_credits="5.0000000000",
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            effective_from=active_start_at,
            effective_to=active_start_at - timedelta(hours=12),
        )
        _seed_credit_wallet_bucket(
            creator_bid="creator-credits-user",
            wallet_bid="wallet-creator-credits-user",
            bucket_bid="bucket-subscription-future",
            available_credits="9.0000000000",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            effective_from=future_start_at,
            effective_to=None,
        )

        result = list_operator_users(app, 1, 20, {})

    assert [item.user_bid for item in result.data] == [
        "creator-credits-user",
        "regular-no-credits",
    ]
    creator_item = result.data[0]
    regular_item = result.data[1]

    assert creator_item.available_credits == "20.50"
    assert creator_item.subscription_credits == "12.50"
    assert creator_item.topup_credits == "8"
    assert creator_item.credits_expire_at == _format_operator_datetime(active_end_at)
    assert creator_item.has_active_subscription is True
    assert regular_item.available_credits == ""
    assert regular_item.subscription_credits == ""
    assert regular_item.topup_credits == ""
    assert regular_item.credits_expire_at == ""
    assert regular_item.has_active_subscription is False


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
    assert item.available_credits == "0"
    assert item.subscription_credits == "0"
    assert item.topup_credits == "0"
    assert item.credits_expire_at == ""
    assert item.has_active_subscription is False


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
            paid_price="88.50",
            payable_price="88.50",
        )
        _seed_learn_progress(
            shifu_bid="course-rich-1",
            outline_item_bid="lesson-rich-1",
            user_bid="user-profile-rich",
            status=LEARN_STATUS_IN_PROGRESS,
            created_at=datetime(2026, 4, 11, 10, 0, 0),
        )

        item = get_operator_user_detail(app, "user-profile-rich")

    assert item.registration_source == "email"
    assert item.last_login_at == _format_operator_datetime(
        datetime(2026, 4, 10, 8, 0, 0)
    )
    assert item.total_paid_amount == "88.50"
    assert item.last_learning_at == _format_operator_datetime(
        datetime(2026, 4, 11, 10, 0, 0)
    )


def test_get_operator_user_credits_returns_summary_and_paginated_ledger(app):
    with app.app_context():
        active_start_at, active_end_at = _build_active_window()
        _seed_user(
            app,
            user_bid="credits-detail-user",
            identify="credits-detail@example.com",
            nickname="Credits Detail",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "credits-detail@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="credits-detail-user",
            wallet_bid="wallet-credits-detail-user",
            available_credits="18.0000000000",
        )
        _seed_billing_subscription(
            creator_bid="credits-detail-user",
            subscription_bid="subscription-credits-detail-user",
            current_period_start_at=active_start_at,
            current_period_end_at=active_end_at,
        )
        _seed_credit_wallet_bucket(
            creator_bid="credits-detail-user",
            wallet_bid="wallet-credits-detail-user",
            bucket_bid="bucket-credits-subscription",
            available_credits="10.0000000000",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            effective_from=active_start_at,
            effective_to=active_end_at,
        )
        _seed_credit_wallet_bucket(
            creator_bid="credits-detail-user",
            wallet_bid="wallet-credits-detail-user",
            bucket_bid="bucket-credits-topup",
            available_credits="8.0000000000",
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            effective_from=active_start_at,
            effective_to=active_end_at + timedelta(days=15),
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-detail-user",
            wallet_bid="wallet-credits-detail-user",
            wallet_bucket_bid="bucket-credits-subscription",
            ledger_bid="ledger-consume",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid="usage-1",
            amount="-2.5000000000",
            balance_after="18.0000000000",
            created_at=datetime(2026, 4, 16, 8, 0, 0),
            expires_at=active_end_at,
            consumable_from=active_start_at,
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-detail-user",
            wallet_bid="wallet-credits-detail-user",
            wallet_bucket_bid="bucket-credits-topup",
            ledger_bid="ledger-adjustment",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid="adjustment-1",
            amount="5.0000000000",
            balance_after="20.5000000000",
            created_at=datetime(2026, 4, 18, 8, 0, 0),
            expires_at=None,
            consumable_from=datetime(2026, 4, 18, 8, 0, 0),
            metadata_json={"note": "manual top up"},
        )

        result = get_operator_user_credits(
            app,
            user_bid="credits-detail-user",
            page_index=1,
            page_size=1,
        )

    assert result.summary.available_credits == "18"
    assert result.summary.subscription_credits == "10"
    assert result.summary.topup_credits == "8"
    assert result.summary.credits_expire_at == _format_operator_datetime(active_end_at)
    assert result.summary.has_active_subscription is True
    assert result.total == 2
    assert result.page == 1
    assert result.page_size == 1
    assert result.page_count == 2
    assert [item.ledger_bid for item in result.items] == ["ledger-adjustment"]
    assert result.items[0].entry_type == "adjustment"
    assert result.items[0].source_type == "manual"
    assert result.items[0].display_entry_type == "manual_credit"
    assert result.items[0].display_source_type == "manual"
    assert result.items[0].amount == "5"
    assert result.items[0].balance_after == "20.50"
    assert result.items[0].note == "manual top up"
    assert result.items[0].note_code == ""


def test_get_operator_user_credits_uses_empty_expiry_for_long_term_balances(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-long-term-user",
            identify="credits-long-term@example.com",
            nickname="Credits Long Term",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "credits-long-term@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="credits-long-term-user",
            wallet_bid="wallet-credits-long-term-user",
            available_credits="12.0000000000",
        )
        _seed_credit_wallet_bucket(
            creator_bid="credits-long-term-user",
            wallet_bid="wallet-credits-long-term-user",
            bucket_bid="bucket-credits-long-term",
            available_credits="12.0000000000",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=None,
        )

        result = get_operator_user_credits(
            app,
            user_bid="credits-long-term-user",
            page_index=1,
            page_size=20,
        )

    assert result.summary.available_credits == "12"
    assert result.summary.credits_expire_at == ""
    assert result.summary.has_active_subscription is False
    assert result.items == []


def test_get_operator_user_credits_maps_usage_rows_to_operator_display_codes(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-usage-user",
            identify="credits-usage@example.com",
            nickname="Credits Usage",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "credits-usage@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="credits-usage-user",
            wallet_bid="wallet-credits-usage-user",
            available_credits="9.0000000000",
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-usage-user",
            wallet_bid="wallet-credits-usage-user",
            wallet_bucket_bid="bucket-credits-usage",
            ledger_bid="ledger-preview-consume",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid="usage-preview-1",
            amount="-1.5000000000",
            balance_after="9.0000000000",
            created_at=datetime(2026, 4, 18, 9, 0, 0),
            metadata_json={"usage_scene": BILL_USAGE_SCENE_PREVIEW},
        )

        result = get_operator_user_credits(
            app,
            user_bid="credits-usage-user",
            page_index=1,
            page_size=20,
        )

    assert len(result.items) == 1
    assert result.items[0].display_entry_type == "preview_consume"
    assert result.items[0].display_source_type == "preview"
    assert result.items[0].note == ""
    assert result.items[0].note_code == "preview_consume"


def test_get_operator_user_credits_excludes_topup_from_available_without_subscription(
    app,
):
    with app.app_context():
        manual_grant_expires_at = datetime.now().replace(microsecond=0) + timedelta(
            days=3
        )
        active_start_at = manual_grant_expires_at - timedelta(days=10)
        _seed_user(
            app,
            user_bid="credits-manual-only-user",
            identify="credits-manual-only@example.com",
            nickname="Credits Manual Only",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "credits-manual-only@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="credits-manual-only-user",
            wallet_bid="wallet-credits-manual-only-user",
            available_credits="11.0000000000",
        )
        _seed_credit_wallet_bucket(
            creator_bid="credits-manual-only-user",
            wallet_bid="wallet-credits-manual-only-user",
            bucket_bid="bucket-manual-only-grant",
            available_credits="3.0000000000",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            effective_from=active_start_at,
            effective_to=manual_grant_expires_at,
        )
        _seed_credit_wallet_bucket(
            creator_bid="credits-manual-only-user",
            wallet_bid="wallet-credits-manual-only-user",
            bucket_bid="bucket-manual-only-topup",
            available_credits="8.0000000000",
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            effective_from=active_start_at,
            effective_to=manual_grant_expires_at + timedelta(days=30),
        )

        result = get_operator_user_credits(
            app,
            user_bid="credits-manual-only-user",
            page_index=1,
            page_size=20,
        )

    assert result.summary.available_credits == "3"
    assert result.summary.subscription_credits == "3"
    assert result.summary.topup_credits == "8"
    assert result.summary.credits_expire_at == _format_operator_datetime(
        manual_grant_expires_at
    )
    assert result.summary.has_active_subscription is False


def test_get_operator_user_credits_maps_manual_grant_display_codes(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-manual-grant-user",
            identify="credits-manual-grant@example.com",
            nickname="Credits Manual Grant",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "credits-manual-grant@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="credits-manual-grant-user",
            wallet_bid="wallet-credits-manual-grant-user",
            available_credits="5.0000000000",
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-manual-grant-user",
            wallet_bid="wallet-credits-manual-grant-user",
            wallet_bucket_bid="bucket-credits-manual-grant-user",
            ledger_bid="ledger-manual-grant",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid="manual-grant-source",
            amount="5.0000000000",
            balance_after="5.0000000000",
            created_at=datetime(2026, 4, 18, 9, 30, 0),
            expires_at=datetime(2026, 4, 25, 0, 0, 0),
            consumable_from=datetime(2026, 4, 18, 9, 30, 0),
            metadata_json={
                "grant_type": "manual_grant",
                "grant_source": "reward",
            },
        )

        result = get_operator_user_credits(
            app,
            user_bid="credits-manual-grant-user",
            page_index=1,
            page_size=20,
        )

    assert len(result.items) == 1
    assert result.items[0].display_entry_type == "manual_grant"
    assert result.items[0].display_source_type == "reward"
    assert result.items[0].note_code == "manual_grant"


def test_get_operator_user_detail_serializes_last_learning_at_using_app_timezone(app):
    with app.app_context():
        original_tz = app.config.get("TZ")
        app.config["TZ"] = "Asia/Shanghai"
        try:
            _seed_user(
                app,
                user_bid="tz-detail-user",
                identify="tz-detail-user@example.com",
                nickname="TZ Detail User",
                state=USER_STATE_PAID,
                created_at=datetime(2026, 4, 20, 9, 0, 0),
                updated_at=datetime(2026, 4, 20, 10, 0, 0),
                providers=[("email", "tz-detail-user@example.com")],
            )
            _seed_learn_progress(
                shifu_bid="course-tz-detail",
                outline_item_bid="lesson-tz-detail",
                user_bid="tz-detail-user",
                status=LEARN_STATUS_IN_PROGRESS,
                created_at=datetime(2026, 4, 22, 11, 56, 11),
            )

            result = get_operator_user_detail(app, "tz-detail-user")
        finally:
            app.config["TZ"] = original_tz

    assert result.last_learning_at == "2026-04-22T03:56:11Z"


def test_get_operator_user_credits_serializes_ledger_time_using_app_timezone(app):
    with app.app_context():
        original_tz = app.config.get("TZ")
        app.config["TZ"] = "Asia/Shanghai"
        try:
            _seed_user(
                app,
                user_bid="tz-credits-user",
                identify="tz-credits-user@example.com",
                nickname="TZ Credits User",
                state=USER_STATE_PAID,
                created_at=datetime(2026, 4, 20, 9, 0, 0),
                updated_at=datetime(2026, 4, 20, 10, 0, 0),
                providers=[("email", "tz-credits-user@example.com")],
            )
            _seed_credit_wallet(
                creator_bid="tz-credits-user",
                wallet_bid="wallet-tz-credits-user",
                available_credits="5",
            )
            _seed_credit_ledger_entry(
                creator_bid="tz-credits-user",
                wallet_bid="wallet-tz-credits-user",
                wallet_bucket_bid="bucket-tz-credits-user",
                ledger_bid="ledger-tz-credits-user",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                source_bid="order-tz-credits-user",
                amount="5",
                balance_after="5",
                created_at=datetime(2026, 4, 22, 16, 29, 9),
                expires_at=datetime(2026, 4, 29, 16, 29, 9),
                metadata_json={
                    "grant_type": "manual_grant",
                    "grant_source": "reward",
                },
            )

            result = get_operator_user_credits(
                app,
                user_bid="tz-credits-user",
                page_index=1,
                page_size=20,
            )
        finally:
            app.config["TZ"] = original_tz

    assert len(result.items) == 1
    assert result.items[0].created_at == "2026-04-22T08:29:09Z"
    assert result.items[0].expires_at == "2026-04-29T08:29:09Z"


def test_grant_operator_user_credits_creates_manual_grant_bucket_and_summary(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-grant-target",
            identify="credits-grant-target@example.com",
            nickname="Credits Grant Target",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "credits-grant-target@example.com")],
        )

        result = grant_operator_user_credits(
            app,
            user_bid="credits-grant-target",
            operator_user_bid="operator-1",
            payload=AdminOperationUserCreditGrantRequestDTO(
                request_id="grant-request-1",
                amount="5",
                grant_source="compensation",
                validity_preset="7d",
                note="ops support",
            ),
        )

        bucket = (
            CreditWalletBucket.query.filter_by(
                creator_bid="credits-grant-target",
            )
            .order_by(CreditWalletBucket.id.desc())
            .first()
        )
        ledger = (
            CreditLedgerEntry.query.filter_by(
                creator_bid="credits-grant-target",
            )
            .order_by(CreditLedgerEntry.id.desc())
            .first()
        )

    assert result.user_bid == "credits-grant-target"
    assert result.amount == "5"
    assert result.grant_source == "compensation"
    assert result.validity_preset == "7d"
    assert result.expires_at.endswith("Z")
    assert result.summary.available_credits == "5"
    assert result.summary.subscription_credits == "5"
    assert result.summary.topup_credits == "0"
    assert result.summary.credits_expire_at.endswith("Z")
    assert bucket is not None
    assert bucket.source_type == CREDIT_SOURCE_TYPE_MANUAL
    assert bucket.metadata_json["grant_source"] == "compensation"
    assert bucket.metadata_json["validity_preset"] == "7d"
    assert ledger is not None
    assert ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT
    assert ledger.source_type == CREDIT_SOURCE_TYPE_MANUAL
    assert ledger.metadata_json["grant_type"] == "manual_grant"
    assert ledger.metadata_json["grant_channel"] == "operator_user_management"


def test_grant_operator_user_credits_is_idempotent_for_repeated_request_id(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-grant-idempotent",
            identify="credits-grant-idempotent@example.com",
            nickname="Credits Grant Idempotent",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "credits-grant-idempotent@example.com")],
        )

        payload = AdminOperationUserCreditGrantRequestDTO(
            request_id="grant-request-idempotent",
            amount="5",
            grant_source="reward",
            validity_preset="1d",
            note="retry-safe",
        )
        first_result = grant_operator_user_credits(
            app,
            user_bid="credits-grant-idempotent",
            operator_user_bid="operator-1",
            payload=payload,
        )
        second_result = grant_operator_user_credits(
            app,
            user_bid="credits-grant-idempotent",
            operator_user_bid="operator-1",
            payload=payload,
        )

        ledger_entries = CreditLedgerEntry.query.filter_by(
            creator_bid="credits-grant-idempotent",
            deleted=0,
        ).all()

    assert first_result.ledger_bid
    assert second_result.ledger_bid == first_result.ledger_bid
    assert second_result.wallet_bucket_bid == first_result.wallet_bucket_bid
    assert len(ledger_entries) == 1


def test_grant_operator_user_credits_returns_persisted_payload_for_reused_request_id(
    app,
):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-grant-idempotent-persisted",
            identify="credits-grant-idempotent-persisted@example.com",
            nickname="Credits Grant Idempotent Persisted",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "credits-grant-idempotent-persisted@example.com")],
        )

        first_payload = AdminOperationUserCreditGrantRequestDTO(
            request_id="grant-request-idempotent-persisted",
            amount="5",
            grant_source="reward",
            validity_preset="1d",
            note="first grant",
        )
        second_payload = AdminOperationUserCreditGrantRequestDTO(
            request_id="grant-request-idempotent-persisted",
            amount="9",
            grant_source="compensation",
            validity_preset="7d",
            note="second grant",
        )
        first_result = grant_operator_user_credits(
            app,
            user_bid="credits-grant-idempotent-persisted",
            operator_user_bid="operator-1",
            payload=first_payload,
        )
        second_result = grant_operator_user_credits(
            app,
            user_bid="credits-grant-idempotent-persisted",
            operator_user_bid="operator-1",
            payload=second_payload,
        )

    assert second_result.ledger_bid == first_result.ledger_bid
    assert second_result.wallet_bucket_bid == first_result.wallet_bucket_bid
    assert second_result.amount == "5"
    assert second_result.grant_source == "reward"
    assert second_result.validity_preset == "1d"
    assert second_result.expires_at == first_result.expires_at


def test_list_operator_users_counts_redeem_orders_in_total_paid_amount(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="user-redeem",
            identify="redeem@example.com",
            nickname="Redeem User",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "redeem@example.com")],
        )
        _seed_success_order(
            order_bid="order-redeem-1",
            shifu_bid="course-redeem-1",
            user_bid="user-redeem",
            created_at=datetime(2026, 4, 10, 9, 0, 0),
            paid_price="0.00",
            payable_price="66.00",
        )

        result = list_operator_users(app, 1, 20, {"identifier": "redeem@"})

    assert result.total == 1
    assert result.data[0].user_bid == "user-redeem"
    assert result.data[0].total_paid_amount == "66"


def test_get_operator_user_detail_counts_redeem_orders_in_total_paid_amount(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="user-profile-redeem",
            identify="profile-redeem@example.com",
            nickname="Profile Redeem User",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "profile-redeem@example.com")],
        )
        _seed_success_order(
            order_bid="order-profile-redeem-1",
            shifu_bid="course-redeem-1",
            user_bid="user-profile-redeem",
            created_at=datetime(2026, 4, 10, 9, 0, 0),
            paid_price="0.00",
            payable_price="66.00",
        )

        item = get_operator_user_detail(app, "user-profile-redeem")

    assert item.total_paid_amount == "66"


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


def test_get_operator_user_detail_uses_latest_progress_state_for_completion(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="learner-latest-status-user",
            identify="13800004444",
            nickname="Learner Latest Status",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("phone", "13800004444")],
        )
        _seed_course(
            model=PublishedShifu,
            shifu_bid="latest-status-course",
            title="Latest Status Course",
            creator_user_bid="creator-user",
            created_at=datetime(2026, 4, 9, 11, 0, 0),
            updated_at=datetime(2026, 4, 9, 11, 30, 0),
        )
        _seed_published_outline_item(
            shifu_bid="latest-status-course",
            outline_item_bid="latest-status-chapter",
            title="Chapter",
            parent_bid="",
            position="1",
        )
        _seed_published_outline_item(
            shifu_bid="latest-status-course",
            outline_item_bid="latest-status-lesson",
            title="Lesson",
            parent_bid="latest-status-chapter",
            position="1.1",
        )
        _seed_success_order(
            order_bid="order-latest-status",
            shifu_bid="latest-status-course",
            user_bid="learner-latest-status-user",
            created_at=datetime(2026, 4, 10, 9, 0, 0),
        )
        _seed_learn_progress(
            shifu_bid="latest-status-course",
            outline_item_bid="latest-status-lesson",
            user_bid="learner-latest-status-user",
            status=LEARN_STATUS_COMPLETED,
            created_at=datetime(2026, 4, 10, 9, 30, 0),
        )
        _seed_learn_progress(
            shifu_bid="latest-status-course",
            outline_item_bid="latest-status-lesson",
            user_bid="learner-latest-status-user",
            status=0,
            created_at=datetime(2026, 4, 10, 10, 0, 0),
        )

        item = get_operator_user_detail(app, "learner-latest-status-user")

    assert item.learning_courses[0].completed_lesson_count == 0
    assert item.learning_courses[0].total_lesson_count == 1


def test_get_operator_user_detail_uses_latest_outline_snapshot_for_total_lessons(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="learner-latest-outline-user",
            identify="13800005555",
            nickname="Learner Latest Outline",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("phone", "13800005555")],
        )
        _seed_course(
            model=PublishedShifu,
            shifu_bid="latest-outline-course",
            title="Latest Outline Course",
            creator_user_bid="creator-user",
            created_at=datetime(2026, 4, 9, 11, 0, 0),
            updated_at=datetime(2026, 4, 9, 11, 30, 0),
        )
        _seed_published_outline_item(
            shifu_bid="latest-outline-course",
            outline_item_bid="latest-outline-chapter",
            title="Chapter",
            parent_bid="",
            position="1",
        )
        _seed_published_outline_item(
            shifu_bid="latest-outline-course",
            outline_item_bid="latest-outline-lesson",
            title="Lesson",
            parent_bid="latest-outline-chapter",
            position="1.1",
            hidden=0,
        )
        _seed_published_outline_item(
            shifu_bid="latest-outline-course",
            outline_item_bid="latest-outline-lesson",
            title="Lesson",
            parent_bid="latest-outline-chapter",
            position="1.1",
            hidden=1,
        )
        _seed_published_outline_item(
            shifu_bid="latest-outline-course",
            outline_item_bid="latest-outline-lesson-2",
            title="Lesson 2",
            parent_bid="latest-outline-chapter",
            position="1.2",
            hidden=0,
        )
        _seed_success_order(
            order_bid="order-latest-outline",
            shifu_bid="latest-outline-course",
            user_bid="learner-latest-outline-user",
            created_at=datetime(2026, 4, 10, 9, 0, 0),
        )

        item = get_operator_user_detail(app, "learner-latest-outline-user")

    assert item.learning_courses[0].total_lesson_count == 1


def test_list_operator_users_includes_shared_course_learners_in_learning_courses(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="shared-learner-user",
            identify="shared@example.com",
            nickname="Shared Learner",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 12, 9, 0, 0),
            updated_at=datetime(2026, 4, 12, 10, 0, 0),
            providers=[("email", "shared@example.com")],
        )
        _seed_user(
            app,
            user_bid="shared-creator-user",
            identify="creator@example.com",
            nickname="Shared Creator",
            state=USER_STATE_REGISTERED,
            is_creator=True,
            created_at=datetime(2026, 4, 11, 9, 0, 0),
            updated_at=datetime(2026, 4, 11, 10, 0, 0),
            providers=[("email", "creator@example.com")],
        )
        _seed_course(
            model=PublishedShifu,
            shifu_bid="shared-course",
            title="Shared Course",
            creator_user_bid="shared-creator-user",
            created_at=datetime(2026, 4, 11, 11, 0, 0),
            updated_at=datetime(2026, 4, 11, 11, 30, 0),
        )
        _seed_course_auth(
            course_id="shared-course",
            user_id="shared-learner-user",
            created_at=datetime(2026, 4, 12, 11, 0, 0),
        )

        result = list_operator_users(app, 1, 20, {"user_role": "learner"})

    assert [item.user_bid for item in result.data] == ["shared-learner-user"]
    assert result.data[0].user_role == "learner"
    assert [course.course_name for course in result.data[0].learning_courses] == [
        "Shared Course"
    ]


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
            "available_credits": "",
            "subscription_credits": "",
            "topup_credits": "",
            "credits_expire_at": "",
            "has_active_subscription": False,
            "last_login_at": "",
            "last_learning_at": "",
            "created_at": _format_operator_datetime(datetime(2026, 4, 6, 8, 0, 0)),
            "updated_at": _format_operator_datetime(datetime(2026, 4, 6, 12, 0, 0)),
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
        "available_credits": "",
        "subscription_credits": "",
        "topup_credits": "",
        "credits_expire_at": "",
        "has_active_subscription": False,
        "last_login_at": "",
        "last_learning_at": "",
        "created_at": _format_operator_datetime(datetime(2026, 4, 10, 8, 0, 0)),
        "updated_at": _format_operator_datetime(datetime(2026, 4, 10, 12, 0, 0)),
    }


def test_admin_operation_user_credits_route_returns_payload(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)

    with app.app_context():
        active_start_at, active_end_at = _build_active_window()
        _seed_user(
            app,
            user_bid="user-credits-route",
            identify="credits-route@example.com",
            nickname="Credits Route User",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 10, 8, 0, 0),
            updated_at=datetime(2026, 4, 10, 12, 0, 0),
            providers=[("email", "credits-route@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="user-credits-route",
            wallet_bid="wallet-credits-route",
            available_credits="7.0000000000",
        )
        _seed_billing_subscription(
            creator_bid="user-credits-route",
            subscription_bid="subscription-credits-route",
            current_period_start_at=active_start_at,
            current_period_end_at=active_end_at,
        )
        _seed_credit_wallet_bucket(
            creator_bid="user-credits-route",
            wallet_bid="wallet-credits-route",
            bucket_bid="bucket-credits-route",
            available_credits="7.0000000000",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            effective_from=active_start_at,
            effective_to=active_end_at,
        )
        _seed_billing_order(
            creator_bid="user-credits-route",
            bill_order_bid="order-route",
            metadata_json={"checkout_type": "subscription"},
        )
        _seed_credit_ledger_entry(
            creator_bid="user-credits-route",
            wallet_bid="wallet-credits-route",
            wallet_bucket_bid="bucket-credits-route",
            ledger_bid="ledger-grant-route",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-route",
            amount="7.0000000000",
            balance_after="7.0000000000",
            created_at=datetime(2026, 4, 10, 12, 0, 0),
            expires_at=active_end_at,
            consumable_from=datetime(2026, 4, 10, 12, 0, 0),
        )

    response = test_client.get(
        "/api/shifu/admin/operations/users/user-credits-route/credits",
        query_string={"page_index": 1, "page_size": 20},
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"] == {
        "summary": {
            "available_credits": "7",
            "subscription_credits": "7",
            "topup_credits": "0",
            "credits_expire_at": _format_operator_datetime(active_end_at),
            "has_active_subscription": True,
        },
        "items": [
            {
                "ledger_bid": "ledger-grant-route",
                "created_at": _format_operator_datetime(
                    datetime(2026, 4, 10, 12, 0, 0)
                ),
                "entry_type": "grant",
                "source_type": "subscription",
                "display_entry_type": "subscription_grant",
                "display_source_type": "subscription",
                "amount": "7",
                "balance_after": "7",
                "expires_at": _format_operator_datetime(active_end_at),
                "consumable_from": _format_operator_datetime(
                    datetime(2026, 4, 10, 12, 0, 0)
                ),
                "note": "",
                "note_code": "subscription_purchase",
            }
        ],
        "page": 1,
        "page_size": 20,
        "total": 1,
        "page_count": 1,
    }


def test_admin_operation_user_credit_grant_route_returns_payload(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user(
            app,
            user_bid="user-credit-grant-route",
            identify="credit-grant-route@example.com",
            nickname="Credit Grant Route User",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 20, 8, 0, 0),
            updated_at=datetime(2026, 4, 20, 12, 0, 0),
            providers=[("email", "credit-grant-route@example.com")],
        )

    response = test_client.post(
        "/api/shifu/admin/operations/users/user-credit-grant-route/credits/grant",
        json={
            "request_id": "route-grant-request-1",
            "amount": "3",
            "grant_source": "reward",
            "validity_preset": "1d",
            "note": "route check",
        },
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["user_bid"] == "user-credit-grant-route"
    assert payload["data"]["amount"] == "3"
    assert payload["data"]["grant_source"] == "reward"
    assert payload["data"]["validity_preset"] == "1d"
    assert payload["data"]["expires_at"].endswith("Z")
    assert payload["data"]["ledger_bid"]
    assert payload["data"]["wallet_bucket_bid"]
    assert payload["data"]["summary"]["available_credits"] == "3"
    assert payload["data"]["summary"]["credits_expire_at"].endswith("Z")
    assert payload["data"]["summary"]["has_active_subscription"] is False


def test_admin_operation_user_credit_grant_route_requires_operator(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch, is_operator=False)

    with app.app_context():
        _seed_user(
            app,
            user_bid="user-credit-grant-route-denied",
            identify="credit-grant-route-denied@example.com",
            nickname="Credit Grant Route Denied",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 20, 8, 0, 0),
            updated_at=datetime(2026, 4, 20, 12, 0, 0),
            providers=[("email", "credit-grant-route-denied@example.com")],
        )

    response = test_client.post(
        "/api/shifu/admin/operations/users/user-credit-grant-route-denied/credits/grant",
        json={
            "request_id": "route-grant-request-denied",
            "amount": "3",
            "grant_source": "reward",
            "validity_preset": "1d",
            "note": "route check",
        },
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 401


def test_admin_operation_user_detail_route_requires_operator(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch, is_operator=False)

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
    assert payload["code"] == 401


def test_admin_operation_user_credits_route_requires_operator(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch, is_operator=False)

    with app.app_context():
        _seed_user(
            app,
            user_bid="user-credits-route",
            identify="credits-route@example.com",
            nickname="Credits Route User",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 10, 8, 0, 0),
            updated_at=datetime(2026, 4, 10, 12, 0, 0),
            providers=[("email", "credits-route@example.com")],
        )

    response = test_client.get(
        "/api/shifu/admin/operations/users/user-credits-route/credits",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 401


def test_get_operator_user_detail_prefers_latest_auth_credential(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="user-latest-contact",
            identify="13800000000",
            nickname="Latest Contact",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 10, 8, 0, 0),
            updated_at=datetime(2026, 4, 10, 12, 0, 0),
            providers=[("phone", "13800000000"), ("email", "old@example.com")],
        )

        newer_phone = AuthCredential(
            credential_bid="credential-new-phone",
            user_bid="user-latest-contact",
            provider_name="phone",
            subject_id="13900000000",
            subject_format="phone",
            identifier="13900000000",
            raw_profile="{}",
            state=CREDENTIAL_STATE_VERIFIED,
            deleted=0,
            created_at=datetime(2026, 4, 10, 13, 0, 0),
            updated_at=datetime(2026, 4, 10, 13, 0, 0),
        )
        newer_email = AuthCredential(
            credential_bid="credential-new-email",
            user_bid="user-latest-contact",
            provider_name="email",
            subject_id="new@example.com",
            subject_format="email",
            identifier="new@example.com",
            raw_profile="{}",
            state=CREDENTIAL_STATE_VERIFIED,
            deleted=0,
            created_at=datetime(2026, 4, 10, 14, 0, 0),
            updated_at=datetime(2026, 4, 10, 14, 0, 0),
        )
        db.session.add_all([newer_phone, newer_email])
        db.session.commit()
        db.session.remove()

        result = get_operator_user_detail(app, "user-latest-contact")

    assert isinstance(result, AdminOperationUserSummaryDTO)
    assert result.mobile == "13900000000"
    assert result.email == "new@example.com"


def test_get_operator_user_detail_ignores_newer_unverified_auth_credential(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="user-latest-contact",
            identify="13800000000",
            nickname="Latest Contact",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 10, 8, 0, 0),
            updated_at=datetime(2026, 4, 10, 12, 0, 0),
            providers=[("phone", "13800000000"), ("email", "old@example.com")],
        )

        newer_verified_phone = AuthCredential(
            credential_bid="credential-new-phone",
            user_bid="user-latest-contact",
            provider_name="phone",
            subject_id="13900000000",
            subject_format="phone",
            identifier="13900000000",
            raw_profile="{}",
            state=CREDENTIAL_STATE_VERIFIED,
            deleted=0,
            created_at=datetime(2026, 4, 10, 13, 0, 0),
            updated_at=datetime(2026, 4, 10, 13, 0, 0),
        )
        newer_verified_email = AuthCredential(
            credential_bid="credential-new-email",
            user_bid="user-latest-contact",
            provider_name="email",
            subject_id="new@example.com",
            subject_format="email",
            identifier="new@example.com",
            raw_profile="{}",
            state=CREDENTIAL_STATE_VERIFIED,
            deleted=0,
            created_at=datetime(2026, 4, 10, 14, 0, 0),
            updated_at=datetime(2026, 4, 10, 14, 0, 0),
        )
        newest_unverified_phone = AuthCredential(
            credential_bid="credential-unverified-phone",
            user_bid="user-latest-contact",
            provider_name="phone",
            subject_id="13700000000",
            subject_format="phone",
            identifier="13700000000",
            raw_profile="{}",
            state=CREDENTIAL_STATE_UNVERIFIED,
            deleted=0,
            created_at=datetime(2026, 4, 10, 15, 0, 0),
            updated_at=datetime(2026, 4, 10, 15, 0, 0),
        )
        newest_unverified_email = AuthCredential(
            credential_bid="credential-unverified-email",
            user_bid="user-latest-contact",
            provider_name="email",
            subject_id="pending@example.com",
            subject_format="email",
            identifier="pending@example.com",
            raw_profile="{}",
            state=CREDENTIAL_STATE_UNVERIFIED,
            deleted=0,
            created_at=datetime(2026, 4, 10, 16, 0, 0),
            updated_at=datetime(2026, 4, 10, 16, 0, 0),
        )
        db.session.add_all(
            [
                newer_verified_phone,
                newer_verified_email,
                newest_unverified_phone,
                newest_unverified_email,
            ]
        )
        db.session.commit()
        db.session.remove()

        result = get_operator_user_detail(app, "user-latest-contact")

    assert isinstance(result, AdminOperationUserSummaryDTO)
    assert result.mobile == "13900000000"
    assert result.email == "new@example.com"


def test_get_operator_user_detail_normalizes_unknown_login_methods(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="user-unknown-login-method",
            identify="unknown@example.com",
            nickname="Unknown Login Method",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 10, 8, 0, 0),
            updated_at=datetime(2026, 4, 10, 12, 0, 0),
            providers=[("password", "unknown@example.com")],
        )

        result = get_operator_user_detail(app, "user-unknown-login-method")

    assert isinstance(result, AdminOperationUserSummaryDTO)
    assert result.login_methods == ["unknown", "email"]
