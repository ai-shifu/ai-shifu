from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
import sys

from flaskr.dao import db
from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.shifu import admin as admin_module
from flaskr.service.shifu.admin_operations import user_credits as user_credits_module
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing import (
    referral_reward_grants as referral_reward_grants_module,
)
from flaskr.service.billing.bucket_categories import resolve_credit_bucket_priority
from flaskr.service.billing.models import CreditWallet, CreditWalletBucket
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.models import Order
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu.admin_operations.users import (
    get_operator_user_detail,
    get_operator_user_overview,
    list_operator_users,
)
from flaskr.service.shifu.admin_operations.user_credits import (
    get_operator_user_grant_bootstrap,
    grant_operator_user_credits,
    grant_operator_user_package,
    get_operator_user_credit_usage_detail,
    get_operator_user_credits,
)
from flaskr.service.shifu.admin_dtos import (
    AdminOperationUserCreditGrantRequestDTO,
    AdminOperationUserPackageGrantRequestDTO,
    AdminOperationUserListDTO,
    AdminOperationUserOverviewDTO,
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
from tests.common.fixtures.billing_products import build_bill_products


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
        db.session.query(BillUsageRecord).delete()
        db.session.query(LearnGeneratedElement).delete()
        db.session.query(LearnGeneratedBlock).delete()
        db.session.query(BillingOrder).delete()
        db.session.query(BillingSubscription).delete()
        db.session.query(BillingProduct).delete()
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
        db.session.query(BillUsageRecord).delete()
        db.session.query(LearnGeneratedElement).delete()
        db.session.query(LearnGeneratedBlock).delete()
        db.session.query(BillingOrder).delete()
        db.session.query(BillingSubscription).delete()
        db.session.query(BillingProduct).delete()
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


def _z(value):
    """Serialize a datetime the way flaskr.route.common.fmt does (UTC ISO 'Z')."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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
    credential_created_at: datetime | None = None,
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
        credential = upsert_credential(
            app,
            user_bid=user_bid,
            provider_name=provider_name,
            subject_id=identifier,
            subject_format=provider_name,
            identifier=identifier,
            metadata={},
            verified=True,
        )
        if credential_created_at:
            credential.created_at = credential_created_at
            credential.updated_at = credential_created_at
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
    product_bid: str = "product-1",
    status: int = BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    billing_provider: str = "manual",
    provider_subscription_id: str = "",
    provider_customer_id: str = "",
):
    subscription = BillingSubscription(
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
        product_bid=product_bid,
        status=status,
        billing_provider=billing_provider,
        provider_subscription_id=provider_subscription_id,
        provider_customer_id=provider_customer_id,
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


def _seed_bill_usage_record(
    *,
    usage_bid: str,
    user_bid: str,
    shifu_bid: str,
    progress_record_bid: str,
    outline_item_bid: str,
    usage_type: int,
    usage_scene: int,
    created_at: datetime,
    extra: dict | None = None,
    generated_block_bid: str = "",
    parent_usage_bid: str = "",
    record_level: int = 0,
    total: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    word_count: int = 0,
    duration_ms: int = 0,
    segment_index: int = 0,
    segment_count: int = 0,
):
    usage = BillUsageRecord(
        usage_bid=usage_bid,
        parent_usage_bid=parent_usage_bid,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_item_bid,
        progress_record_bid=progress_record_bid,
        generated_block_bid=generated_block_bid,
        audio_bid="",
        request_id=f"request-{usage_bid}",
        trace_id=f"trace-{usage_bid}",
        usage_type=usage_type,
        record_level=record_level,
        usage_scene=usage_scene,
        provider="openai",
        model="gpt-4o-mini",
        input=input_tokens,
        output=output_tokens,
        total=total,
        word_count=word_count,
        duration_ms=duration_ms,
        segment_index=segment_index,
        segment_count=segment_count,
        billable=1,
        status=0,
        extra=extra or {},
    )
    usage.created_at = created_at
    usage.updated_at = created_at
    db.session.add(usage)
    db.session.commit()
    db.session.remove()
    return usage


def _seed_generated_block(
    *,
    generated_block_bid: str,
    progress_record_bid: str,
    user_bid: str,
    shifu_bid: str,
    outline_item_bid: str,
    generated_content: str,
    created_at: datetime,
):
    block = LearnGeneratedBlock(
        generated_block_bid=generated_block_bid,
        progress_record_bid=progress_record_bid,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_item_bid,
        generated_content=generated_content,
        status=1,
    )
    block.created_at = created_at
    block.updated_at = created_at
    db.session.add(block)
    db.session.commit()
    db.session.remove()
    return block


def _seed_generated_element(
    *,
    element_bid: str,
    generated_block_bid: str,
    progress_record_bid: str,
    user_bid: str,
    shifu_bid: str,
    outline_item_bid: str,
    content_text: str,
    audio_segments: str,
    sequence_number: int,
    created_at: datetime,
):
    element = LearnGeneratedElement(
        element_bid=element_bid,
        generated_block_bid=generated_block_bid,
        progress_record_bid=progress_record_bid,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_item_bid,
        event_type="element",
        element_type="text",
        is_speakable=1,
        content_text=content_text,
        audio_segments=audio_segments,
        sequence_number=sequence_number,
        status=1,
    )
    element.created_at = created_at
    element.updated_at = created_at
    db.session.add(element)
    db.session.commit()
    db.session.remove()
    return element


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

    assert isinstance(result, AdminOperationUserListDTO)
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
    assert item.last_login_at is None
    assert item.last_learning_at is None
    assert item.created_at == datetime(2026, 4, 3, 9, 0, 0)
    assert item.updated_at == datetime(2026, 4, 4, 9, 0, 0)


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


def test_list_operator_users_filters_creator_role_includes_operator_creators(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="operator-creator",
            identify="13900003333",
            nickname="Operator Creator",
            state=USER_STATE_REGISTERED,
            is_creator=True,
            is_operator=True,
            created_at=datetime(2026, 4, 3, 9, 0, 0),
            updated_at=datetime(2026, 4, 3, 10, 0, 0),
            providers=[("phone", "13900003333")],
        )
        _seed_user(
            app,
            user_bid="creator-only",
            identify="13900004444",
            nickname="Creator Only",
            state=USER_STATE_REGISTERED,
            is_creator=True,
            created_at=datetime(2026, 4, 2, 9, 0, 0),
            updated_at=datetime(2026, 4, 2, 10, 0, 0),
            providers=[("phone", "13900004444")],
        )

        result = list_operator_users(
            app,
            1,
            20,
            {
                "user_role": "creator",
            },
        )

    assert [item.user_bid for item in result.data] == [
        "operator-creator",
        "creator-only",
    ]
    assert result.data[0].user_roles == ["operator", "creator"]
    assert result.data[1].user_roles == ["creator"]


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


def test_list_operator_users_returns_overview_summary_and_applies_quick_filters(
    app, monkeypatch
):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 6, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(admin_module, "datetime", FixedDateTime)

    with app.app_context():
        _seed_user(
            app,
            user_bid="user-guest",
            identify="guest@example.com",
            nickname="Guest User",
            state=USER_STATE_UNREGISTERED,
            created_at=datetime(2026, 5, 5, 9, 0, 0),
            updated_at=datetime(2026, 5, 5, 10, 0, 0),
            providers=[("email", "guest@example.com")],
        )
        _seed_user(
            app,
            user_bid="user-creator",
            identify="creator@example.com",
            nickname="Creator User",
            state=USER_STATE_REGISTERED,
            is_creator=True,
            created_at=datetime(2026, 5, 1, 9, 0, 0),
            updated_at=datetime(2026, 5, 1, 10, 0, 0),
            providers=[("email", "creator@example.com")],
            credential_created_at=datetime(2026, 5, 1, 9, 0, 0),
        )
        _seed_user(
            app,
            user_bid="user-learner",
            identify="learner@example.com",
            nickname="Learner User",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "learner@example.com")],
            credential_created_at=datetime(2026, 4, 20, 9, 0, 0),
        )
        _seed_user(
            app,
            user_bid="user-paid",
            identify="paid@example.com",
            nickname="Paid User",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 1, 9, 0, 0),
            updated_at=datetime(2026, 4, 1, 10, 0, 0),
            providers=[("email", "paid@example.com")],
            credential_created_at=datetime(2026, 5, 2, 8, 0, 0),
        )
        _seed_learn_progress(
            shifu_bid="course-learning-active",
            outline_item_bid="lesson-learning-active",
            user_bid="user-learner",
            status=LEARN_STATUS_IN_PROGRESS,
            created_at=datetime(2026, 5, 4, 8, 0, 0),
        )
        _seed_success_order(
            order_bid="order-paid-recent",
            shifu_bid="course-paid-recent",
            user_bid="user-paid",
            created_at=datetime(2026, 5, 3, 8, 0, 0),
        )

        overview = get_operator_user_overview(app)
        result = list_operator_users(app, 1, 20, {})
        learner_result = list_operator_users(app, 1, 20, {"quick_filter": "learner"})
        recent_paid_result = list_operator_users(
            app, 1, 20, {"quick_filter": "paid_last_30d"}
        )
        registered_result = list_operator_users(
            app, 1, 20, {"quick_filter": "registered"}
        )
        recent_registered_result = list_operator_users(
            app, 1, 20, {"quick_filter": "registered_last_30d"}
        )

    assert isinstance(result, AdminOperationUserListDTO)
    assert isinstance(overview, AdminOperationUserOverviewDTO)
    assert overview.total_user_count == 4
    assert overview.registered_user_count == 3
    assert overview.creator_user_count == 1
    assert overview.learner_user_count == 2
    assert overview.paid_user_count == 1
    assert overview.created_last_30d_user_count == 3
    assert overview.registered_last_30d_user_count == 3
    assert overview.learning_active_30d_user_count == 1
    assert overview.paid_last_30d_user_count == 1
    assert overview.guest_user_count == 1
    assert [item.user_bid for item in registered_result.data] == [
        "user-creator",
        "user-learner",
        "user-paid",
    ]
    assert [item.user_bid for item in recent_registered_result.data] == [
        "user-creator",
        "user-learner",
        "user-paid",
    ]
    assert [item.user_bid for item in learner_result.data] == [
        "user-learner",
        "user-paid",
    ]
    assert [item.user_bid for item in recent_paid_result.data] == ["user-paid"]


def test_list_operator_users_recent_windows_exclude_future_records_and_keep_microseconds(
    app, monkeypatch
):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 6, 23, 59, 59, 250000, tzinfo=tz)

    monkeypatch.setattr(admin_module, "datetime", FixedDateTime)

    with app.app_context():
        _seed_user(
            app,
            user_bid="user-created-in-range",
            identify="created-in-range@example.com",
            nickname="Created In Range",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 5, 6, 23, 59, 59, 125000),
            updated_at=datetime(2026, 5, 6, 23, 59, 59, 125000),
            providers=[("email", "created-in-range@example.com")],
            credential_created_at=datetime(2026, 5, 6, 23, 59, 59, 125000),
        )
        _seed_user(
            app,
            user_bid="user-created-future",
            identify="created-future@example.com",
            nickname="Created Future",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 5, 6, 23, 59, 59, 750000),
            updated_at=datetime(2026, 5, 6, 23, 59, 59, 750000),
            providers=[("email", "created-future@example.com")],
            credential_created_at=datetime(2026, 5, 6, 23, 59, 59, 750000),
        )
        _seed_user(
            app,
            user_bid="user-learning-in-range",
            identify="learning-in-range@example.com",
            nickname="Learning In Range",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 1, 9, 0, 0),
            updated_at=datetime(2026, 4, 1, 9, 0, 0),
            providers=[("email", "learning-in-range@example.com")],
            credential_created_at=datetime(2026, 4, 1, 9, 0, 0),
        )
        _seed_user(
            app,
            user_bid="user-learning-future",
            identify="learning-future@example.com",
            nickname="Learning Future",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 4, 1, 10, 0, 0),
            updated_at=datetime(2026, 4, 1, 10, 0, 0),
            providers=[("email", "learning-future@example.com")],
            credential_created_at=datetime(2026, 4, 1, 10, 0, 0),
        )
        _seed_user(
            app,
            user_bid="user-paid-in-range",
            identify="paid-in-range@example.com",
            nickname="Paid In Range",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 1, 8, 0, 0),
            updated_at=datetime(2026, 4, 1, 8, 0, 0),
            providers=[("email", "paid-in-range@example.com")],
            credential_created_at=datetime(2026, 4, 1, 8, 0, 0),
        )
        _seed_user(
            app,
            user_bid="user-paid-future",
            identify="paid-future@example.com",
            nickname="Paid Future",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 1, 9, 0, 0),
            updated_at=datetime(2026, 4, 1, 9, 0, 0),
            providers=[("email", "paid-future@example.com")],
            credential_created_at=datetime(2026, 4, 1, 9, 0, 0),
        )
        _seed_learn_progress(
            shifu_bid="course-learning-in-range",
            outline_item_bid="lesson-learning-in-range",
            user_bid="user-learning-in-range",
            status=LEARN_STATUS_IN_PROGRESS,
            created_at=datetime(2026, 5, 6, 23, 59, 59, 125000),
        )
        _seed_learn_progress(
            shifu_bid="course-learning-future",
            outline_item_bid="lesson-learning-future",
            user_bid="user-learning-future",
            status=LEARN_STATUS_IN_PROGRESS,
            created_at=datetime(2026, 5, 6, 23, 59, 59, 750000),
        )
        _seed_success_order(
            order_bid="order-paid-in-range",
            shifu_bid="course-paid-in-range",
            user_bid="user-paid-in-range",
            created_at=datetime(2026, 5, 6, 23, 59, 59, 125000),
        )
        _seed_success_order(
            order_bid="order-paid-future",
            shifu_bid="course-paid-future",
            user_bid="user-paid-future",
            created_at=datetime(2026, 5, 6, 23, 59, 59, 750000),
        )

        overview = get_operator_user_overview(app)
        created_last_30d_result = list_operator_users(
            app, 1, 20, {"quick_filter": "created_last_30d"}
        )
        learning_active_result = list_operator_users(
            app, 1, 20, {"quick_filter": "learning_active_30d"}
        )
        paid_last_30d_result = list_operator_users(
            app, 1, 20, {"quick_filter": "paid_last_30d"}
        )

    assert overview.created_last_30d_user_count == 1
    assert overview.learning_active_30d_user_count == 1
    assert overview.paid_last_30d_user_count == 1
    assert [item.user_bid for item in created_last_30d_result.data] == [
        "user-created-in-range"
    ]
    assert [item.user_bid for item in learning_active_result.data] == [
        "user-learning-in-range"
    ]
    assert [item.user_bid for item in paid_last_30d_result.data] == [
        "user-paid-in-range"
    ]


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

    assert isinstance(result, AdminOperationUserListDTO)
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
        creator_detail = get_operator_user_detail(app, "creator-user")
        learner_detail = get_operator_user_detail(app, "learner-user")

    assert result.total == 2
    assert [item.user_bid for item in result.data] == ["creator-user", "learner-user"]
    creator_item = result.data[0]
    learner_item = result.data[1]
    assert creator_item.user_role == "creator"
    assert learner_item.user_role == "learner"
    assert creator_item.user_roles == ["creator", "learner"]
    assert learner_item.user_roles == ["learner"]

    assert creator_item.created_course_count == 3
    assert creator_item.learning_course_count == 1
    assert learner_item.learning_course_count == 1
    assert learner_item.created_course_count == 0
    assert creator_item.created_courses == []
    assert creator_item.learning_courses == []
    assert learner_item.learning_courses == []
    assert learner_item.created_courses == []

    assert [course.course_name for course in creator_detail.created_courses] == [
        "Published Course",
        "Draft Course",
        "Learned Course",
    ]
    assert [course.course_status for course in creator_detail.created_courses] == [
        "published",
        "unpublished",
        "published",
    ]
    assert [course.course_name for course in creator_detail.learning_courses] == [
        "Published Course"
    ]
    assert [course.course_name for course in learner_detail.learning_courses] == [
        "Learned Course"
    ]


def test_user_course_count_maps_use_lightweight_course_rows(app, monkeypatch):
    load_calls = []

    def fake_load_latest_shifus(model, **kwargs):
        load_calls.append(("latest", model.__name__, kwargs.get("lightweight")))
        return []

    def fake_load_latest_courses_by_shifu_bids(
        model,
        shifu_bids,
        *,
        lightweight=False,
    ):
        load_calls.append(("by_bids", model.__name__, tuple(shifu_bids), lightweight))
        return []

    monkeypatch.setattr(
        admin_module,
        "_load_latest_shifus",
        fake_load_latest_shifus,
    )
    monkeypatch.setattr(
        admin_module,
        "_load_latest_courses_by_shifu_bids",
        fake_load_latest_courses_by_shifu_bids,
    )

    with app.app_context():
        created_count_map, learning_count_map = (
            admin_module._load_operator_user_course_count_maps(["user-no-activity"])
        )

    assert created_count_map == {"user-no-activity": 0}
    assert learning_count_map == {"user-no-activity": 0}
    assert load_calls == [
        ("latest", "DraftShifu", True),
        ("latest", "PublishedShifu", True),
        ("by_bids", "DraftShifu", (), True),
        ("by_bids", "PublishedShifu", (), True),
    ]


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
    assert creator_item.credits_expire_at == active_end_at
    assert creator_item.has_active_subscription is True
    assert regular_item.available_credits == ""
    assert regular_item.subscription_credits == ""
    assert regular_item.topup_credits == ""
    assert regular_item.credits_expire_at is None
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
    assert item.credits_expire_at is None
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
    assert item.last_login_at == datetime(2026, 4, 10, 8, 0, 0)
    assert item.total_paid_amount == "88.50"
    assert item.last_learning_at == datetime(2026, 4, 11, 10, 0, 0)


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
    assert result.summary.credits_expire_at == active_end_at
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


def test_get_operator_user_credits_handles_invalid_source_type(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-invalid-source-user",
            identify="credits-invalid-source@example.com",
            nickname="Invalid Source",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "credits-invalid-source@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="credits-invalid-source-user",
            wallet_bid="wallet-credits-invalid-source-user",
            available_credits="1.0000000000",
        )
        entry = _seed_credit_ledger_entry(
            creator_bid="credits-invalid-source-user",
            wallet_bid="wallet-credits-invalid-source-user",
            wallet_bucket_bid="bucket-invalid-source",
            ledger_bid="ledger-invalid-source",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid="adjustment-invalid-source",
            amount="1.0000000000",
            balance_after="1.0000000000",
            created_at=datetime(2026, 4, 18, 8, 0, 0),
        )
        entry.source_type = ""
        db.session.add(entry)
        db.session.commit()

        result = get_operator_user_credits(
            app,
            user_bid="credits-invalid-source-user",
            page_index=1,
            page_size=20,
        )

    assert result.total == 1
    assert result.items[0].display_source_type == "manual"


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
    assert result.summary.credits_expire_at is None
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


def test_get_operator_user_credits_enriches_consume_rows_with_course_context(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-context-user",
            identify="credits-context@example.com",
            nickname="Credits Context",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "credits-context@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="credits-context-user",
            wallet_bid="wallet-credits-context-user",
            available_credits="9.0000000000",
        )
        _seed_course(
            model=PublishedShifu,
            shifu_bid="course-context",
            title="Context Course",
            creator_user_bid="credits-context-user",
            created_at=datetime(2026, 4, 10, 8, 0, 0),
            updated_at=datetime(2026, 4, 10, 8, 0, 0),
        )
        _seed_published_outline_item(
            shifu_bid="course-context",
            outline_item_bid="chapter-context",
            title="Context Chapter",
            parent_bid="",
            position="1",
        )
        _seed_published_outline_item(
            shifu_bid="course-context",
            outline_item_bid="lesson-context",
            title="Context Lesson",
            parent_bid="chapter-context",
            position="1.1",
        )
        _seed_bill_usage_record(
            usage_bid="usage-context",
            user_bid="learner-context-user",
            shifu_bid="course-context",
            progress_record_bid="progress-context",
            outline_item_bid="lesson-context",
            usage_type=BILL_USAGE_TYPE_TTS,
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
            created_at=datetime(2026, 4, 18, 9, 0, 0),
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-context-user",
            wallet_bid="wallet-credits-context-user",
            wallet_bucket_bid="bucket-credits-context",
            ledger_bid="ledger-context-consume",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid="usage-context",
            amount="-1.5000000000",
            balance_after="9.0000000000",
            created_at=datetime(2026, 4, 18, 9, 0, 0),
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-context-user",
            wallet_bid="wallet-credits-context-user",
            wallet_bucket_bid="bucket-credits-context",
            ledger_bid="ledger-context-grant",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid="manual-context",
            amount="3.0000000000",
            balance_after="12.0000000000",
            created_at=datetime(2026, 4, 18, 10, 0, 0),
        )

        result = get_operator_user_credits(
            app,
            user_bid="credits-context-user",
            page_index=1,
            page_size=20,
        )

    rows_by_bid = {item.ledger_bid: item for item in result.items}
    consume_item = rows_by_bid["ledger-context-consume"]
    assert consume_item.usage_bid == "usage-context"
    assert consume_item.course_bid == "course-context"
    assert consume_item.course_name == "Context Course"
    assert consume_item.chapter_title == "Context Chapter"
    assert consume_item.lesson_title == "Context Lesson"
    assert consume_item.usage_scene == "preview"
    assert consume_item.usage_mode == "listen"

    grant_item = rows_by_bid["ledger-context-grant"]
    assert grant_item.usage_bid == ""
    assert grant_item.course_bid == ""
    assert grant_item.course_name == ""
    assert grant_item.chapter_title == ""
    assert grant_item.lesson_title == ""
    assert grant_item.usage_scene == ""
    assert grant_item.usage_mode == ""


def test_get_operator_user_credits_loads_order_metadata_only_for_order_sources(
    app,
    monkeypatch,
):
    captured_source_bids: list[str] = []
    original_load_billing_order_map = user_credits_module._load_billing_order_map

    def capture_order_source_bids(source_bids):
        captured_source_bids.extend(list(source_bids))
        return original_load_billing_order_map(source_bids)

    monkeypatch.setattr(
        user_credits_module,
        "_load_billing_order_map",
        capture_order_source_bids,
    )

    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-order-source-user",
            identify="credits-order-source@example.com",
            nickname="Credits Order Source",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "credits-order-source@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="credits-order-source-user",
            wallet_bid="wallet-credits-order-source-user",
            available_credits="9.0000000000",
        )
        _seed_billing_order(
            creator_bid="credits-order-source-user",
            bill_order_bid="order-source-1",
            metadata_json={"checkout_type": "subscription"},
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-order-source-user",
            wallet_bid="wallet-credits-order-source-user",
            wallet_bucket_bid="bucket-order-source",
            ledger_bid="ledger-order-source-grant",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-source-1",
            amount="3.0000000000",
            balance_after="12.0000000000",
            created_at=datetime(2026, 4, 18, 10, 0, 0),
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-order-source-user",
            wallet_bid="wallet-credits-order-source-user",
            wallet_bucket_bid="bucket-order-source",
            ledger_bid="ledger-order-source-consume",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid="usage-source-1",
            amount="-1.0000000000",
            balance_after="11.0000000000",
            created_at=datetime(2026, 4, 18, 11, 0, 0),
        )

        result = get_operator_user_credits(
            app,
            user_bid="credits-order-source-user",
            page_index=1,
            page_size=20,
        )

    assert result.total == 2
    assert captured_source_bids == ["order-source-1"]


def test_get_operator_user_credits_filters_consume_grant_and_other_rows(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-filter-user",
            identify="credits-filter@example.com",
            nickname="Credits Filter",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "credits-filter@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="credits-filter-user",
            wallet_bid="wallet-credits-filter-user",
            available_credits="20.0000000000",
        )
        _seed_course(
            model=DraftShifu,
            shifu_bid="course-ask",
            title="Ask Mastery",
            creator_user_bid="credits-filter-user",
            created_at=datetime(2026, 4, 10, 8, 0, 0),
            updated_at=datetime(2026, 4, 10, 8, 0, 0),
        )
        _seed_course(
            model=DraftShifu,
            shifu_bid="course-listen",
            title="Listen Basics",
            creator_user_bid="credits-filter-user",
            created_at=datetime(2026, 4, 10, 9, 0, 0),
            updated_at=datetime(2026, 4, 10, 9, 0, 0),
        )
        _seed_billing_order(
            creator_bid="credits-filter-user",
            bill_order_bid="order-subscription-filter",
            metadata_json={"checkout_type": "subscription"},
        )
        _seed_billing_order(
            creator_bid="credits-filter-user",
            bill_order_bid="order-trial-filter",
            metadata_json={"checkout_type": "trial_bootstrap"},
        )
        _seed_bill_usage_record(
            usage_bid="usage-ask-filter",
            user_bid="credits-filter-user",
            shifu_bid="course-ask",
            progress_record_bid="progress-ask-filter",
            outline_item_bid="lesson-ask-filter",
            usage_type=BILL_USAGE_TYPE_LLM,
            usage_scene=BILL_USAGE_SCENE_PROD,
            created_at=datetime(2026, 4, 18, 9, 0, 0),
            extra={"generation_name": "lesson_ask/filter"},
        )
        _seed_bill_usage_record(
            usage_bid="usage-listen-filter",
            user_bid="credits-filter-user",
            shifu_bid="course-listen",
            progress_record_bid="progress-listen-filter",
            outline_item_bid="lesson-listen-filter",
            usage_type=BILL_USAGE_TYPE_TTS,
            usage_scene=BILL_USAGE_SCENE_PROD,
            created_at=datetime(2026, 4, 18, 10, 0, 0),
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-filter-user",
            wallet_bid="wallet-credits-filter-user",
            wallet_bucket_bid="bucket-consume-filter",
            ledger_bid="ledger-consume-ask-filter",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid="usage-ask-filter",
            amount="-1.0000000000",
            balance_after="19.0000000000",
            created_at=datetime(2026, 4, 18, 9, 0, 0),
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-filter-user",
            wallet_bid="wallet-credits-filter-user",
            wallet_bucket_bid="bucket-consume-filter",
            ledger_bid="ledger-consume-listen-filter",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid="usage-listen-filter",
            amount="-2.0000000000",
            balance_after="17.0000000000",
            created_at=datetime(2026, 4, 18, 10, 0, 0),
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-filter-user",
            wallet_bid="wallet-credits-filter-user",
            wallet_bucket_bid="bucket-grant-filter",
            ledger_bid="ledger-grant-subscription-filter",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-subscription-filter",
            amount="5.0000000000",
            balance_after="22.0000000000",
            created_at=datetime(2026, 4, 18, 11, 0, 0),
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-filter-user",
            wallet_bid="wallet-credits-filter-user",
            wallet_bucket_bid="bucket-grant-filter",
            ledger_bid="ledger-grant-trial-filter",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-trial-filter",
            amount="3.0000000000",
            balance_after="25.0000000000",
            created_at=datetime(2026, 4, 18, 12, 0, 0),
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-filter-user",
            wallet_bid="wallet-credits-filter-user",
            wallet_bucket_bid="bucket-other-filter",
            ledger_bid="ledger-expire-filter",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="expire-filter",
            amount="-4.0000000000",
            balance_after="21.0000000000",
            created_at=datetime(2026, 4, 18, 13, 0, 0),
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-filter-user",
            wallet_bid="wallet-credits-filter-user",
            wallet_bucket_bid="bucket-other-filter",
            ledger_bid="ledger-refund-filter",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_REFUND,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid="refund-filter",
            amount="1.0000000000",
            balance_after="22.0000000000",
            created_at=datetime(2026, 4, 18, 14, 0, 0),
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-filter-user",
            wallet_bid="wallet-credits-filter-user",
            wallet_bucket_bid="bucket-other-filter",
            ledger_bid="ledger-manual-debit-filter",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid="manual-debit-filter",
            amount="-1.0000000000",
            balance_after="21.0000000000",
            created_at=datetime(2026, 4, 18, 15, 0, 0),
        )

        consume_id_result = get_operator_user_credits(
            app,
            user_bid="credits-filter-user",
            page_index=1,
            page_size=20,
            filters={
                "credit_type": "consume",
                "course_query": "course-ask",
                "usage_mode": "ask",
            },
        )
        consume_name_result = get_operator_user_credits(
            app,
            user_bid="credits-filter-user",
            page_index=1,
            page_size=20,
            filters={
                "credit_type": "consume",
                "course_query": "Ask",
                "usage_mode": "ask",
            },
        )
        grant_result = get_operator_user_credits(
            app,
            user_bid="credits-filter-user",
            page_index=1,
            page_size=20,
            filters={
                "credit_type": "grant",
                "grant_source": "trial_subscription",
            },
        )
        other_result = get_operator_user_credits(
            app,
            user_bid="credits-filter-user",
            page_index=1,
            page_size=20,
            filters={"credit_type": "other"},
        )

    assert [item.ledger_bid for item in consume_id_result.items] == [
        "ledger-consume-ask-filter"
    ]
    assert consume_id_result.total == 1

    assert [item.ledger_bid for item in consume_name_result.items] == [
        "ledger-consume-ask-filter"
    ]
    assert consume_name_result.total == 1

    assert [item.ledger_bid for item in grant_result.items] == [
        "ledger-grant-trial-filter"
    ]
    assert grant_result.total == 1

    assert [item.ledger_bid for item in other_result.items] == [
        "ledger-manual-debit-filter",
        "ledger-refund-filter",
        "ledger-expire-filter",
    ]
    assert other_result.total == 3


def test_get_operator_user_credits_keeps_consume_rows_without_usage_when_unfiltered(
    app,
):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-missing-usage-user",
            identify="credits-missing-usage@example.com",
            nickname="Credits Missing Usage",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "credits-missing-usage@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="credits-missing-usage-user",
            wallet_bid="wallet-credits-missing-usage-user",
            available_credits="8.0000000000",
        )
        _seed_credit_ledger_entry(
            creator_bid="credits-missing-usage-user",
            wallet_bid="wallet-credits-missing-usage-user",
            wallet_bucket_bid="bucket-consume-missing-usage",
            ledger_bid="ledger-consume-missing-usage",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid="usage-missing",
            amount="-1.0000000000",
            balance_after="7.0000000000",
            created_at=datetime(2026, 4, 18, 9, 0, 0),
        )

        unfiltered_result = get_operator_user_credits(
            app,
            user_bid="credits-missing-usage-user",
            page_index=1,
            page_size=20,
            filters={"credit_type": "consume"},
        )
        filtered_result = get_operator_user_credits(
            app,
            user_bid="credits-missing-usage-user",
            page_index=1,
            page_size=20,
            filters={
                "credit_type": "consume",
                "usage_mode": "ask",
            },
        )

    assert [item.ledger_bid for item in unfiltered_result.items] == [
        "ledger-consume-missing-usage"
    ]
    assert unfiltered_result.total == 1
    assert filtered_result.total == 0


def test_get_operator_user_credits_empty_consume_filter_does_not_scan_usage_rows(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-empty-consume-user",
            identify="credits-empty-consume@example.com",
            nickname="Credits Empty Consume",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "credits-empty-consume@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="credits-empty-consume-user",
            wallet_bid="wallet-credits-empty-consume-user",
            available_credits="8.0000000000",
        )
        _seed_bill_usage_record(
            usage_bid="usage-other-user",
            user_bid="other-user",
            shifu_bid="course-other-user",
            progress_record_bid="progress-other-user",
            outline_item_bid="lesson-other-user",
            usage_type=BILL_USAGE_TYPE_LLM,
            usage_scene=BILL_USAGE_SCENE_PROD,
            created_at=datetime(2026, 4, 18, 9, 0, 0),
            extra={"generation_name": "lesson_ask/filter"},
        )

        result = get_operator_user_credits(
            app,
            user_bid="credits-empty-consume-user",
            page_index=1,
            page_size=20,
            filters={
                "credit_type": "consume",
                "usage_mode": "ask",
            },
        )

    assert result.total == 0
    assert result.items == []


def test_get_operator_user_credit_usage_detail_returns_generated_content(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="usage-detail-owner",
            identify="usage-detail-owner@example.com",
            nickname="Usage Detail Owner",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "usage-detail-owner@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="usage-detail-owner",
            wallet_bid="wallet-usage-detail-owner",
            available_credits="9.0000000000",
        )
        _seed_course(
            model=PublishedShifu,
            shifu_bid="course-usage-detail",
            title="Usage Detail Course",
            creator_user_bid="usage-detail-owner",
            created_at=datetime(2026, 4, 10, 8, 0, 0),
            updated_at=datetime(2026, 4, 10, 8, 0, 0),
        )
        _seed_published_outline_item(
            shifu_bid="course-usage-detail",
            outline_item_bid="chapter-usage-detail",
            title="Usage Detail Chapter",
            parent_bid="",
            position="1",
        )
        _seed_published_outline_item(
            shifu_bid="course-usage-detail",
            outline_item_bid="lesson-usage-detail",
            title="Usage Detail Lesson",
            parent_bid="chapter-usage-detail",
            position="1.1",
        )
        _seed_generated_block(
            generated_block_bid="block-usage-detail",
            progress_record_bid="progress-usage-detail",
            user_bid="learner-usage-detail",
            shifu_bid="course-usage-detail",
            outline_item_bid="lesson-usage-detail",
            generated_content="This is the generated answer.",
            created_at=datetime(2026, 4, 18, 9, 0, 0),
        )
        _seed_bill_usage_record(
            usage_bid="usage-detail-llm",
            user_bid="learner-usage-detail",
            shifu_bid="course-usage-detail",
            progress_record_bid="progress-usage-detail",
            outline_item_bid="lesson-usage-detail",
            generated_block_bid="block-usage-detail",
            usage_type=BILL_USAGE_TYPE_LLM,
            usage_scene=BILL_USAGE_SCENE_PROD,
            input_tokens=100,
            output_tokens=20,
            total=120,
            created_at=datetime(2026, 4, 18, 9, 0, 0),
        )
        _seed_credit_ledger_entry(
            creator_bid="usage-detail-owner",
            wallet_bid="wallet-usage-detail-owner",
            wallet_bucket_bid="bucket-usage-detail",
            ledger_bid="ledger-usage-detail",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid="usage-detail-llm",
            amount="-2.5000000000",
            balance_after="7.5000000000",
            created_at=datetime(2026, 4, 18, 9, 1, 0),
        )

        result = get_operator_user_credit_usage_detail(
            app,
            user_bid="usage-detail-owner",
            usage_bid="usage-detail-llm",
        )

    assert result.usage_bid == "usage-detail-llm"
    assert result.course_name == "Usage Detail Course"
    assert result.lesson_title == "Usage Detail Lesson"
    assert result.chapter_title == "Usage Detail Chapter"
    assert result.total_consumed_credits == "2.50"
    assert len(result.items) == 1
    assert result.items[0].content == "This is the generated answer."
    assert result.items[0].consumed_credits == "2.50"
    assert result.items[0].input_tokens == 100
    assert result.items[0].output_tokens == 20


def test_get_operator_user_credit_usage_detail_uses_ledger_owner_not_usage_user(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="usage-detail-wallet-owner",
            identify="usage-detail-wallet-owner@example.com",
            nickname="Usage Detail Wallet Owner",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "usage-detail-wallet-owner@example.com")],
        )
        _seed_user(
            app,
            user_bid="usage-detail-other-owner",
            identify="usage-detail-other-owner@example.com",
            nickname="Usage Detail Other Owner",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "usage-detail-other-owner@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="usage-detail-wallet-owner",
            wallet_bid="wallet-usage-detail-wallet-owner",
            available_credits="9.0000000000",
        )
        _seed_generated_block(
            generated_block_bid="block-usage-detail-owner",
            progress_record_bid="progress-usage-detail-owner",
            user_bid="actual-learner-user",
            shifu_bid="course-usage-detail-owner",
            outline_item_bid="lesson-usage-detail-owner",
            generated_content="Owner detail content",
            created_at=datetime(2026, 4, 18, 9, 0, 0),
        )
        _seed_bill_usage_record(
            usage_bid="usage-detail-owner-check",
            user_bid="actual-learner-user",
            shifu_bid="course-usage-detail-owner",
            progress_record_bid="progress-usage-detail-owner",
            outline_item_bid="lesson-usage-detail-owner",
            generated_block_bid="block-usage-detail-owner",
            usage_type=BILL_USAGE_TYPE_LLM,
            usage_scene=BILL_USAGE_SCENE_PROD,
            total=100,
            segment_count=2,
            created_at=datetime(2026, 4, 18, 9, 0, 0),
        )
        _seed_credit_ledger_entry(
            creator_bid="usage-detail-wallet-owner",
            wallet_bid="wallet-usage-detail-wallet-owner",
            wallet_bucket_bid="bucket-usage-detail-owner",
            ledger_bid="ledger-usage-detail-owner",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid="usage-detail-owner-check",
            amount="-1.0000000000",
            balance_after="8.0000000000",
            created_at=datetime(2026, 4, 18, 9, 1, 0),
        )

        result = get_operator_user_credit_usage_detail(
            app,
            user_bid="usage-detail-wallet-owner",
            usage_bid="usage-detail-owner-check",
        )
        with pytest.raises(AppException):
            get_operator_user_credit_usage_detail(
                app,
                user_bid="usage-detail-other-owner",
                usage_bid="usage-detail-owner-check",
            )

    assert result.items[0].content == "Owner detail content"


def test_get_operator_user_credit_usage_detail_returns_tts_segment_rows(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="usage-detail-tts-owner",
            identify="usage-detail-tts-owner@example.com",
            nickname="Usage Detail TTS Owner",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            updated_at=datetime(2026, 4, 9, 10, 0, 0),
            providers=[("email", "usage-detail-tts-owner@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="usage-detail-tts-owner",
            wallet_bid="wallet-usage-detail-tts-owner",
            available_credits="9.0000000000",
        )
        _seed_generated_element(
            element_bid="element-tts-1",
            generated_block_bid="block-usage-detail-tts",
            progress_record_bid="progress-usage-detail-tts",
            user_bid="learner-usage-detail-tts",
            shifu_bid="course-usage-detail-tts",
            outline_item_bid="lesson-usage-detail-tts",
            content_text="First narration.",
            audio_segments='[{"segment_index": 0}]',
            sequence_number=1,
            created_at=datetime(2026, 4, 18, 9, 0, 0),
        )
        _seed_generated_element(
            element_bid="element-tts-2",
            generated_block_bid="block-usage-detail-tts",
            progress_record_bid="progress-usage-detail-tts",
            user_bid="learner-usage-detail-tts",
            shifu_bid="course-usage-detail-tts",
            outline_item_bid="lesson-usage-detail-tts",
            content_text="Second narration.",
            audio_segments='[{"segment_index": 1}]',
            sequence_number=2,
            created_at=datetime(2026, 4, 18, 9, 0, 1),
        )
        _seed_bill_usage_record(
            usage_bid="usage-detail-tts",
            user_bid="learner-usage-detail-tts",
            shifu_bid="course-usage-detail-tts",
            progress_record_bid="progress-usage-detail-tts",
            outline_item_bid="lesson-usage-detail-tts",
            generated_block_bid="block-usage-detail-tts",
            usage_type=BILL_USAGE_TYPE_TTS,
            usage_scene=BILL_USAGE_SCENE_PROD,
            total=100,
            created_at=datetime(2026, 4, 18, 9, 0, 0),
        )
        _seed_bill_usage_record(
            usage_bid="usage-detail-tts-segment-1",
            parent_usage_bid="usage-detail-tts",
            record_level=1,
            user_bid="learner-usage-detail-tts",
            shifu_bid="course-usage-detail-tts",
            progress_record_bid="progress-usage-detail-tts",
            outline_item_bid="lesson-usage-detail-tts",
            generated_block_bid="block-usage-detail-tts",
            usage_type=BILL_USAGE_TYPE_TTS,
            usage_scene=BILL_USAGE_SCENE_PROD,
            total=25,
            word_count=3,
            duration_ms=1000,
            segment_index=0,
            segment_count=0,
            created_at=datetime(2026, 4, 18, 9, 0, 1),
        )
        _seed_bill_usage_record(
            usage_bid="usage-detail-tts-segment-2",
            parent_usage_bid="usage-detail-tts",
            record_level=1,
            user_bid="learner-usage-detail-tts",
            shifu_bid="course-usage-detail-tts",
            progress_record_bid="progress-usage-detail-tts",
            outline_item_bid="lesson-usage-detail-tts",
            generated_block_bid="block-usage-detail-tts",
            usage_type=BILL_USAGE_TYPE_TTS,
            usage_scene=BILL_USAGE_SCENE_PROD,
            total=75,
            word_count=4,
            duration_ms=2000,
            segment_index=1,
            segment_count=0,
            created_at=datetime(2026, 4, 18, 9, 0, 2),
        )
        _seed_credit_ledger_entry(
            creator_bid="usage-detail-tts-owner",
            wallet_bid="wallet-usage-detail-tts-owner",
            wallet_bucket_bid="bucket-usage-detail-tts",
            ledger_bid="ledger-usage-detail-tts",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid="usage-detail-tts",
            amount="-4.0000000000",
            balance_after="5.0000000000",
            created_at=datetime(2026, 4, 18, 9, 1, 0),
        )

        result = get_operator_user_credit_usage_detail(
            app,
            user_bid="usage-detail-tts-owner",
            usage_bid="usage-detail-tts",
        )

    assert [item.content for item in result.items] == [
        "First narration.",
        "Second narration.",
    ]
    assert [item.consumed_credits for item in result.items] == ["1", "3"]
    assert [item.word_count for item in result.items] == [3, 4]
    assert [item.duration_ms for item in result.items] == [1000, 2000]
    assert [item.segment_count for item in result.items] == [2, 2]


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
    assert result.summary.credits_expire_at == manual_grant_expires_at
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

    assert result.last_learning_at == datetime(2026, 4, 22, 11, 56, 11)


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
    assert result.items[0].created_at == datetime(2026, 4, 22, 16, 29, 9)
    assert result.items[0].expires_at == datetime(2026, 4, 29, 16, 29, 9)


def test_grant_operator_user_credits_creates_manual_grant_bucket_and_summary(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-grant-target",
            identify="credits-grant-target@example.com",
            nickname="Credits Grant Target",
            state=USER_STATE_PAID,
            is_creator=True,
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
                display_name="模型扣费补偿",
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
    assert result.grant_type == "manual_credit"
    assert result.grant_source == "compensation"
    assert result.validity_preset == "7d"
    assert result.expires_at is not None
    assert result.display_name == "模型扣费补偿"
    assert result.note == "ops support"
    assert result.summary.available_credits == "5"
    assert result.summary.subscription_credits == "5"
    assert result.summary.topup_credits == "0"
    assert result.summary.credits_expire_at is not None
    assert bucket is not None
    assert bucket.source_type == CREDIT_SOURCE_TYPE_MANUAL
    assert bucket.metadata_json["grant_source"] == "compensation"
    assert bucket.metadata_json["validity_preset"] == "7d"
    assert "display_name" not in bucket.metadata_json
    assert "note" not in bucket.metadata_json
    assert ledger is not None
    assert ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT
    assert ledger.source_type == CREDIT_SOURCE_TYPE_MANUAL
    assert ledger.metadata_json["grant_type"] == "manual_grant"
    assert ledger.metadata_json["operator_user_bid"] == "operator-1"
    assert ledger.metadata_json["grant_channel"] == "operator_user_management"
    assert ledger.metadata_json["display_name"] == "模型扣费补偿"
    assert ledger.metadata_json["note"] == "ops support"


def test_grant_operator_user_credits_is_idempotent_for_repeated_request_id(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-grant-idempotent",
            identify="credits-grant-idempotent@example.com",
            nickname="Credits Grant Idempotent",
            state=USER_STATE_PAID,
            is_creator=True,
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


def test_grant_operator_user_referral_reward_stacks_bucket_and_expiry(app, monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 21, 0, 0, 0, tzinfo=tz)

    monkeypatch.setattr(referral_reward_grants_module, "datetime", FixedDateTime)
    monkeypatch.setattr(admin_module, "datetime", FixedDateTime)
    monkeypatch.setattr(
        user_credits_module, "now_utc", lambda: datetime(2026, 4, 21, 0, 0, 0)
    )

    with app.app_context():
        _seed_user(
            app,
            user_bid="referral-reward-target",
            identify="referral-reward-target@example.com",
            nickname="Referral Reward Target",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "referral-reward-target@example.com")],
        )

        first_result = grant_operator_user_credits(
            app,
            user_bid="referral-reward-target",
            operator_user_bid="operator-1",
            payload=AdminOperationUserCreditGrantRequestDTO(
                request_id="referral-reward-request-1",
                amount="1000",
                grant_type="referral_reward",
                grant_source="reward",
                validity_preset="1m",
                note="first referral",
            ),
        )
        second_result = grant_operator_user_credits(
            app,
            user_bid="referral-reward-target",
            operator_user_bid="operator-1",
            payload=AdminOperationUserCreditGrantRequestDTO(
                request_id="referral-reward-request-2",
                amount="800",
                grant_type="referral_reward",
                grant_source="reward",
                validity_preset="1m",
                note="second referral",
            ),
        )

        buckets = CreditWalletBucket.query.filter_by(
            creator_bid="referral-reward-target",
            deleted=0,
        ).all()
        ledgers = (
            CreditLedgerEntry.query.filter_by(
                creator_bid="referral-reward-target",
                deleted=0,
            )
            .order_by(CreditLedgerEntry.id.asc())
            .all()
        )
        bootstrap = get_operator_user_grant_bootstrap(
            app,
            user_bid="referral-reward-target",
        )

    assert first_result.grant_type == "referral_reward"
    assert first_result.expires_at == datetime(2026, 5, 21, 0, 0, 0)
    assert second_result.grant_type == "referral_reward"
    assert second_result.expires_at == datetime(2026, 6, 21, 0, 0, 0)
    assert second_result.wallet_bucket_bid == first_result.wallet_bucket_bid
    assert second_result.amount == "800"
    assert second_result.summary.available_credits == "1800"
    assert len(buckets) == 1
    assert buckets[0].metadata_json["grant_type"] == "referral_reward"
    assert buckets[0].metadata_json["validity_strategy"] == "stack_by_reward_scene"
    assert Decimal(str(buckets[0].available_credits)) == Decimal("1800")
    assert len(ledgers) == 2
    assert ledgers[0].expires_at == ledgers[1].expires_at == buckets[0].effective_to
    assert Decimal(ledgers[1].metadata_json["reward_credits"]) == Decimal("800")
    assert ledgers[1].metadata_json["previous_effective_to"]
    assert ledgers[1].metadata_json["new_effective_to"]
    assert bootstrap.referral_reward_summary.available_credits == "1800"
    assert bootstrap.referral_reward_summary.expires_at == second_result.expires_at
    assert bootstrap.referral_reward_summary.grant_count == 2


def test_grant_operator_user_referral_reward_extends_empty_active_bucket(
    app, monkeypatch
):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 21, 0, 0, 0, tzinfo=tz)

    monkeypatch.setattr(referral_reward_grants_module, "datetime", FixedDateTime)

    with app.app_context():
        _seed_user(
            app,
            user_bid="referral-reward-empty-active",
            identify="referral-reward-empty-active@example.com",
            nickname="Referral Reward Empty Active",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "referral-reward-empty-active@example.com")],
        )
        _seed_credit_wallet(
            creator_bid="referral-reward-empty-active",
            wallet_bid="wallet-referral-reward-empty-active",
            available_credits="0",
        )
        db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid="bucket-referral-reward-empty-active",
                wallet_bid="wallet-referral-reward-empty-active",
                creator_bid="referral-reward-empty-active",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                source_bid="referral_reward",
                priority=resolve_credit_bucket_priority(
                    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
                ),
                original_credits=Decimal("1000"),
                available_credits=Decimal("0"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("1000"),
                expired_credits=Decimal("0"),
                effective_from=datetime(2026, 4, 1, 0, 0, 0),
                effective_to=datetime(2026, 5, 21, 0, 0, 0),
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "grant_type": "referral_reward",
                    "validity_strategy": "stack_by_reward_scene",
                },
            )
        )
        db.session.commit()

        result = grant_operator_user_credits(
            app,
            user_bid="referral-reward-empty-active",
            operator_user_bid="operator-1",
            payload=AdminOperationUserCreditGrantRequestDTO(
                request_id="referral-reward-empty-active-request",
                amount="1000",
                grant_type="referral_reward",
                grant_source="reward",
                validity_preset="1m",
                note="extend empty active bucket",
            ),
        )

        buckets = CreditWalletBucket.query.filter_by(
            creator_bid="referral-reward-empty-active",
            deleted=0,
        ).all()

    assert result.wallet_bucket_bid == "bucket-referral-reward-empty-active"
    assert result.expires_at == datetime(2026, 6, 21, 0, 0, 0)
    assert result.note == "extend empty active bucket"
    assert len(buckets) == 1
    assert buckets[0].effective_to == datetime(2026, 6, 21, 0, 0, 0)
    assert Decimal(str(buckets[0].available_credits)) == Decimal("1000")


def test_grant_operator_user_referral_reward_is_idempotent_for_repeated_request_id(
    app,
):
    with app.app_context():
        _seed_user(
            app,
            user_bid="referral-reward-idempotent",
            identify="referral-reward-idempotent@example.com",
            nickname="Referral Reward Idempotent",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "referral-reward-idempotent@example.com")],
        )

        payload = AdminOperationUserCreditGrantRequestDTO(
            request_id="referral-reward-idempotent-request",
            amount="1000",
            grant_type="referral_reward",
            grant_source="reward",
            validity_preset="1m",
            note="retry-safe referral",
        )
        first_result = grant_operator_user_credits(
            app,
            user_bid="referral-reward-idempotent",
            operator_user_bid="operator-1",
            payload=payload,
        )
        second_result = grant_operator_user_credits(
            app,
            user_bid="referral-reward-idempotent",
            operator_user_bid="operator-1",
            payload=payload,
        )

        buckets = CreditWalletBucket.query.filter_by(
            creator_bid="referral-reward-idempotent",
            deleted=0,
        ).all()
        ledger_entries = CreditLedgerEntry.query.filter_by(
            creator_bid="referral-reward-idempotent",
            deleted=0,
        ).all()

    assert first_result.ledger_bid
    assert second_result.ledger_bid == first_result.ledger_bid
    assert second_result.wallet_bucket_bid == first_result.wallet_bucket_bid
    assert second_result.summary.available_credits == "1000"
    assert second_result.note == "retry-safe referral"
    assert len(buckets) == 1
    assert len(ledger_entries) == 1


def test_grant_operator_user_referral_reward_rejects_non_integer_amount(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="referral-reward-invalid-amount",
            identify="referral-reward-invalid-amount@example.com",
            nickname="Referral Reward Invalid Amount",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "referral-reward-invalid-amount@example.com")],
        )

        with pytest.raises(AppException):
            grant_operator_user_credits(
                app,
                user_bid="referral-reward-invalid-amount",
                operator_user_bid="operator-1",
                payload=AdminOperationUserCreditGrantRequestDTO(
                    request_id="referral-reward-invalid-amount-request",
                    amount="1000.5",
                    grant_type="referral_reward",
                    grant_source="reward",
                    validity_preset="1m",
                ),
            )


def test_grant_operator_user_credits_accepts_legacy_manual_grant_type(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-grant-legacy-manual-type",
            identify="credits-grant-legacy-manual-type@example.com",
            nickname="Credits Grant Legacy Manual Type",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "credits-grant-legacy-manual-type@example.com")],
        )

        result = grant_operator_user_credits(
            app,
            user_bid="credits-grant-legacy-manual-type",
            operator_user_bid="operator-1",
            payload=AdminOperationUserCreditGrantRequestDTO(
                request_id="grant-request-legacy-manual-type",
                amount="5",
                grant_type="manual_grant",
                grant_source="reward",
                validity_preset="1d",
                note="legacy type",
            ),
        )

    assert result.grant_type == "manual_credit"
    assert result.note == "legacy type"


def test_grant_operator_user_credits_rejects_unknown_grant_type(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-grant-unknown-type",
            identify="credits-grant-unknown-type@example.com",
            nickname="Credits Grant Unknown Type",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "credits-grant-unknown-type@example.com")],
        )

        with pytest.raises(AppException) as exc_info:
            grant_operator_user_credits(
                app,
                user_bid="credits-grant-unknown-type",
                operator_user_bid="operator-1",
                payload=AdminOperationUserCreditGrantRequestDTO(
                    request_id="grant-request-unknown-type",
                    amount="5",
                    grant_type="unknown_type",
                    grant_source="reward",
                    validity_preset="1d",
                    note="invalid type",
                ),
            )
        ledger_count = CreditLedgerEntry.query.filter_by(
            creator_bid="credits-grant-unknown-type",
            deleted=0,
        ).count()

    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]
    assert "grant_type" in exc_info.value.message
    assert ledger_count == 0


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
            is_creator=True,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "credits-grant-idempotent-persisted@example.com")],
        )

        first_payload = AdminOperationUserCreditGrantRequestDTO(
            request_id="grant-request-idempotent-persisted",
            amount="5",
            grant_source="reward",
            validity_preset="1d",
            display_name="first display",
            note="first grant",
        )
        second_payload = AdminOperationUserCreditGrantRequestDTO(
            request_id="grant-request-idempotent-persisted",
            amount="9",
            grant_source="compensation",
            validity_preset="7d",
            display_name="second display",
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
    assert second_result.display_name == "first display"
    assert second_result.note == "first grant"


def test_grant_operator_user_credits_rejects_regular_user_targets(app):
    with app.app_context():
        _seed_user(
            app,
            user_bid="credits-grant-regular",
            identify="credits-grant-regular@example.com",
            nickname="Credits Grant Regular",
            state=USER_STATE_PAID,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "credits-grant-regular@example.com")],
        )

        with pytest.raises(AppException) as exc_info:
            grant_operator_user_credits(
                app,
                user_bid="credits-grant-regular",
                operator_user_bid="operator-1",
                payload=AdminOperationUserCreditGrantRequestDTO(
                    request_id="grant-request-regular",
                    amount="5",
                    grant_source="reward",
                    validity_preset="1d",
                    note="unsupported target",
                ),
            )

    assert (
        exc_info.value.code
        == ERROR_CODE["server.billing.adminPlanGrantRoleUnsupported"]
    )


def test_get_operator_user_grant_bootstrap_returns_active_plans(app):
    with app.app_context():
        db.session.add_all(
            build_bill_products(product_bids=["bill-product-plan-monthly"])
        )
        _seed_user(
            app,
            user_bid="package-bootstrap-target",
            identify="package-bootstrap-target@example.com",
            nickname="Package Bootstrap Target",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "package-bootstrap-target@example.com")],
        )
        _seed_billing_subscription(
            creator_bid="package-bootstrap-target",
            subscription_bid="subscription-package-bootstrap-target",
            product_bid="bill-product-plan-monthly",
            current_period_start_at=datetime(2026, 4, 20, 9, 0, 0),
            current_period_end_at=datetime(2099, 5, 20, 23, 59, 59),
        )

        result = get_operator_user_grant_bootstrap(
            app,
            user_bid="package-bootstrap-target",
        )

    assert len(result.plans) == 1
    assert result.plans[0].product_bid == "bill-product-plan-monthly"
    assert (
        result.current_subscription_product_display_name_i18n_key
        == "module.billing.catalog.plans.creatorMonthly.title"
    )
    assert result.notification_status == "template_pending"


def test_grant_operator_user_package_creates_manual_paid_order_and_summary(app):
    with app.app_context():
        db.session.add_all(
            build_bill_products(product_bids=["bill-product-plan-monthly"])
        )
        _seed_user(
            app,
            user_bid="package-grant-target",
            identify="package-grant-target@example.com",
            nickname="Package Grant Target",
            state=USER_STATE_PAID,
            is_operator=True,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "package-grant-target@example.com")],
        )

        result = grant_operator_user_package(
            app,
            user_bid="package-grant-target",
            operator_user_bid="operator-1",
            payload=AdminOperationUserPackageGrantRequestDTO(
                request_id="package-grant-request-1",
                product_bid="bill-product-plan-monthly",
                note="ops package",
            ),
        )

        order = (
            BillingOrder.query.filter_by(
                creator_bid="package-grant-target",
                bill_order_bid=result.bill_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        subscription = (
            BillingSubscription.query.filter_by(
                creator_bid="package-grant-target",
                subscription_bid=result.subscription_bid,
            )
            .order_by(BillingSubscription.id.desc())
            .first()
        )
        ledger = (
            CreditLedgerEntry.query.filter_by(
                creator_bid="package-grant-target",
                source_bid=result.bill_order_bid,
            )
            .order_by(CreditLedgerEntry.id.desc())
            .first()
        )

    assert result.user_bid == "package-grant-target"
    assert result.product_bid == "bill-product-plan-monthly"
    assert result.notification_status == "template_pending"
    assert result.summary.available_credits == "5"
    assert result.summary.subscription_credits == "5"
    assert result.current_period_start_at is not None
    assert result.current_period_end_at is not None
    assert order is not None
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert order.payment_provider == "manual"
    assert order.metadata_json["checkout_type"] == "admin_manual_plan_grant"
    assert order.metadata_json["operator_user_bid"] == "operator-1"
    assert order.metadata_json["request_id"] == "package-grant-request-1"
    assert (
        order.metadata_json["notification_extensions"]["admin_manual_plan_grant"][
            "operator_user_bid"
        ]
        == "operator-1"
    )
    assert (
        order.metadata_json["notification_extensions"]["admin_manual_plan_grant"][
            "status"
        ]
        == "template_pending"
    )
    assert subscription is not None
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert subscription.metadata_json["operator_user_bid"] == "operator-1"
    assert subscription.metadata_json["request_id"] == "package-grant-request-1"
    assert ledger is not None
    assert ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT
    assert ledger.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION
    assert ledger.metadata_json["bill_order_bid"] == result.bill_order_bid


def test_grant_operator_user_package_is_idempotent_for_repeated_request_id(app):
    with app.app_context():
        db.session.add_all(
            build_bill_products(product_bids=["bill-product-plan-monthly"])
        )
        _seed_user(
            app,
            user_bid="package-grant-idempotent",
            identify="package-grant-idempotent@example.com",
            nickname="Package Grant Idempotent",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "package-grant-idempotent@example.com")],
        )

        payload = AdminOperationUserPackageGrantRequestDTO(
            request_id="package-grant-idempotent-request",
            product_bid="bill-product-plan-monthly",
            note="retry-safe package",
        )
        first_result = grant_operator_user_package(
            app,
            user_bid="package-grant-idempotent",
            operator_user_bid="operator-1",
            payload=payload,
        )
        second_result = grant_operator_user_package(
            app,
            user_bid="package-grant-idempotent",
            operator_user_bid="operator-1",
            payload=payload,
        )
        orders = BillingOrder.query.filter_by(
            creator_bid="package-grant-idempotent",
            deleted=0,
        ).all()

    assert second_result.bill_order_bid == first_result.bill_order_bid
    assert second_result.subscription_bid == first_result.subscription_bid
    assert len(orders) == 1


def test_grant_operator_user_package_upgrades_active_pingxx_subscription(app):
    with app.app_context():
        db.session.add_all(
            build_bill_products(
                product_bids=[
                    "bill-product-plan-monthly",
                    "bill-product-plan-yearly",
                ]
            )
        )
        _seed_user(
            app,
            user_bid="package-grant-pingxx-upgrade",
            identify="package-grant-pingxx-upgrade@example.com",
            nickname="Package Grant Pingxx Upgrade",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "package-grant-pingxx-upgrade@example.com")],
        )
        _seed_billing_subscription(
            creator_bid="package-grant-pingxx-upgrade",
            subscription_bid="sub-package-grant-pingxx-upgrade",
            product_bid="bill-product-plan-monthly",
            billing_provider="pingxx",
            current_period_start_at=datetime.now() - timedelta(days=1),
            current_period_end_at=datetime.now() + timedelta(days=29),
        )

        result = grant_operator_user_package(
            app,
            user_bid="package-grant-pingxx-upgrade",
            operator_user_bid="operator-1",
            payload=AdminOperationUserPackageGrantRequestDTO(
                request_id="package-grant-pingxx-upgrade-request",
                product_bid="bill-product-plan-yearly",
                note="ops package upgrade",
            ),
        )

        order = (
            BillingOrder.query.filter_by(
                creator_bid="package-grant-pingxx-upgrade",
                bill_order_bid=result.bill_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        subscription = (
            BillingSubscription.query.filter_by(
                creator_bid="package-grant-pingxx-upgrade",
                subscription_bid=result.subscription_bid,
            )
            .order_by(BillingSubscription.id.desc())
            .first()
        )

    assert result.product_bid == "bill-product-plan-yearly"
    assert order is not None
    assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE
    assert order.payment_provider == "manual"
    assert subscription is not None
    assert subscription.product_bid == "bill-product-plan-yearly"
    assert subscription.billing_provider == "pingxx"


def test_grant_operator_user_package_rejects_active_stripe_subscription(app):
    with app.app_context():
        db.session.add_all(
            build_bill_products(
                product_bids=[
                    "bill-product-plan-monthly",
                    "bill-product-plan-yearly",
                ]
            )
        )
        _seed_user(
            app,
            user_bid="package-grant-stripe-conflict",
            identify="package-grant-stripe-conflict@example.com",
            nickname="Package Grant Stripe Conflict",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 9, 0, 0),
            updated_at=datetime(2026, 4, 20, 10, 0, 0),
            providers=[("email", "package-grant-stripe-conflict@example.com")],
        )
        _seed_billing_subscription(
            creator_bid="package-grant-stripe-conflict",
            subscription_bid="sub-package-grant-stripe-conflict",
            product_bid="bill-product-plan-monthly",
            billing_provider="stripe",
            provider_subscription_id="sub_provider_package_grant_stripe_conflict",
            provider_customer_id="cus_package_grant_stripe_conflict",
            current_period_start_at=datetime.now() - timedelta(days=1),
            current_period_end_at=datetime.now() + timedelta(days=29),
        )

        with pytest.raises(AppException) as exc_info:
            grant_operator_user_package(
                app,
                user_bid="package-grant-stripe-conflict",
                operator_user_bid="operator-1",
                payload=AdminOperationUserPackageGrantRequestDTO(
                    request_id="package-grant-stripe-conflict-request",
                    product_bid="bill-product-plan-yearly",
                    note="ops package conflict",
                ),
            )

    assert (
        exc_info.value.code
        == ERROR_CODE["server.billing.adminPlanGrantProviderManagedConflict"]
    )


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
        detail = get_operator_user_detail(app, "shared-learner-user")

    assert [item.user_bid for item in result.data] == ["shared-learner-user"]
    assert result.data[0].user_role == "learner"
    assert result.data[0].learning_course_count == 1
    assert result.data[0].learning_courses == []
    assert [course.course_name for course in detail.learning_courses] == [
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


def test_admin_operation_users_overview_route_requires_operator(
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch, is_operator=False)

    response = test_client.get(
        "/api/shifu/admin/operations/users/overview",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 401


def test_admin_operation_users_overview_route_returns_payload(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)

    with app.app_context():
        _seed_user(
            app,
            user_bid="user-overview-route-1",
            identify="overview-route-1@example.com",
            nickname="Overview Route User 1",
            state=USER_STATE_REGISTERED,
            created_at=datetime(2026, 5, 1, 8, 0, 0),
            updated_at=datetime(2026, 5, 1, 8, 0, 0),
            providers=[("email", "overview-route-1@example.com")],
            credential_created_at=datetime(2026, 5, 1, 8, 0, 0),
        )
        _seed_user(
            app,
            user_bid="user-overview-route-2",
            identify="13812340001",
            nickname="Overview Route User 2",
            state=USER_STATE_UNREGISTERED,
            created_at=datetime(2026, 5, 2, 8, 0, 0),
            updated_at=datetime(2026, 5, 2, 8, 0, 0),
        )

    response = test_client.get(
        "/api/shifu/admin/operations/users/overview",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["total_user_count"] == 2
    assert payload["data"]["registered_user_count"] == 1
    assert payload["data"]["guest_user_count"] == 1


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
    assert "summary" not in payload["data"]
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
            "learning_course_count": 0,
            "created_courses": [],
            "created_course_count": 0,
            "total_paid_amount": "0",
            "available_credits": "",
            "subscription_credits": "",
            "topup_credits": "",
            "credits_expire_at": None,
            "has_active_subscription": False,
            "last_login_at": None,
            "last_learning_at": None,
            "created_at": _z(datetime(2026, 4, 6, 8, 0, 0)),
            "updated_at": _z(datetime(2026, 4, 6, 12, 0, 0)),
        }
    ]


@pytest.mark.parametrize(
    ("query_string", "expected_param"),
    [
        ("page_index=1&page_size=20&user_status=invalid", "user_status"),
        ("page_index=1&page_size=20&user_role=invalid", "user_role"),
        ("page_index=1&page_size=20&start_time=not-a-date", "start_time"),
        (
            "page_index=1&page_size=20&start_time=2026-05-02&end_time=2026-05-01",
            "start_time",
        ),
    ],
)
def test_admin_operation_users_route_rejects_invalid_filter_params(
    test_client,
    monkeypatch,
    query_string,
    expected_param,
):
    _mock_operator(monkeypatch)

    response = test_client.get(
        f"/api/shifu/admin/operations/users?{query_string}",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == ERROR_CODE["server.common.paramsError"]
    assert payload["message"] == f"Params Error {expected_param}"


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
        "learning_course_count": 0,
        "created_courses": [],
        "created_course_count": 0,
        "total_paid_amount": "0",
        "available_credits": "",
        "subscription_credits": "",
        "topup_credits": "",
        "credits_expire_at": None,
        "has_active_subscription": False,
        "last_login_at": None,
        "last_learning_at": None,
        "created_at": _z(datetime(2026, 4, 10, 8, 0, 0)),
        "updated_at": _z(datetime(2026, 4, 10, 12, 0, 0)),
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
        _seed_course(
            model=PublishedShifu,
            shifu_bid="course-preview-route",
            title="Preview Route Course",
            creator_user_bid="user-credits-route",
            created_at=datetime(2026, 4, 9, 8, 0, 0),
            updated_at=datetime(2026, 4, 9, 9, 0, 0),
        )
        _seed_bill_usage_record(
            usage_bid="usage-preview-route",
            user_bid="user-credits-route",
            shifu_bid="course-preview-route",
            progress_record_bid="progress-preview-route",
            outline_item_bid="lesson-preview-route",
            usage_type=BILL_USAGE_TYPE_LLM,
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
            created_at=datetime(2026, 4, 10, 12, 30, 0),
            extra={"generation_name": "learn_preview"},
            input_tokens=100,
            output_tokens=50,
            total=150,
        )
        _seed_credit_ledger_entry(
            creator_bid="user-credits-route",
            wallet_bid="wallet-credits-route",
            wallet_bucket_bid="bucket-credits-route",
            ledger_bid="ledger-preview-route",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid="usage-preview-route",
            amount="-1.0000000000",
            balance_after="6.0000000000",
            created_at=datetime(2026, 4, 10, 12, 30, 0),
            metadata_json={"usage_bid": "usage-preview-route"},
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
            "credits_expire_at": _z(active_end_at),
            "has_active_subscription": True,
        },
        "items": [
            {
                "ledger_bid": "ledger-preview-route",
                "created_at": _z(datetime(2026, 4, 10, 12, 30, 0)),
                "entry_type": "consume",
                "source_type": "usage",
                "display_entry_type": "consume",
                "display_source_type": "usage",
                "amount": "-1",
                "balance_after": "6",
                "expires_at": None,
                "consumable_from": None,
                "note": "",
                "note_code": "",
                "usage_bid": "usage-preview-route",
                "course_bid": "course-preview-route",
                "course_name": "Preview Route Course",
                "chapter_title": "",
                "lesson_title": "",
                "usage_scene": "preview",
                "usage_mode": "learn",
            },
            {
                "ledger_bid": "ledger-grant-route",
                "created_at": _z(datetime(2026, 4, 10, 12, 0, 0)),
                "entry_type": "grant",
                "source_type": "subscription",
                "display_entry_type": "subscription_grant",
                "display_source_type": "subscription",
                "amount": "7",
                "balance_after": "7",
                "expires_at": _z(active_end_at),
                "consumable_from": _z(datetime(2026, 4, 10, 12, 0, 0)),
                "note": "",
                "note_code": "subscription_purchase",
                "usage_bid": "",
                "course_bid": "",
                "course_name": "",
                "chapter_title": "",
                "lesson_title": "",
                "usage_scene": "",
                "usage_mode": "",
            },
        ],
        "page": 1,
        "page_size": 20,
        "total": 2,
        "page_count": 1,
    }

    scene_response = test_client.get(
        "/api/shifu/admin/operations/users/user-credits-route/credits",
        query_string={
            "page_index": 1,
            "page_size": 20,
            "credit_type": "consume",
            "usage_scene": "preview",
        },
        headers={"Token": "test-token"},
    )
    scene_payload = scene_response.get_json(force=True)

    assert scene_response.status_code == 200
    assert scene_payload["code"] == 0
    assert scene_payload["data"]["total"] == 1
    assert scene_payload["data"]["items"][0]["usage_scene"] == "preview"


def test_admin_operation_user_credits_route_rejects_inverted_time_range(
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)

    response = test_client.get(
        "/api/shifu/admin/operations/users/user-credits-route/credits"
        "?page_index=1&page_size=20&start_time=2026-05-02&end_time=2026-05-01",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == ERROR_CODE["server.common.paramsError"]
    assert payload["message"] == "Params Error start_time"


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
            is_creator=True,
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


def test_admin_operation_user_grant_bootstrap_route_returns_active_plans(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)

    with app.app_context():
        db.session.add_all(
            build_bill_products(product_bids=["bill-product-plan-monthly"])
        )
        _seed_user(
            app,
            user_bid="user-grant-bootstrap-route",
            identify="user-grant-bootstrap-route@example.com",
            nickname="Grant Bootstrap Route User",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 8, 0, 0),
            updated_at=datetime(2026, 4, 20, 12, 0, 0),
            providers=[("email", "user-grant-bootstrap-route@example.com")],
        )
        _seed_billing_subscription(
            creator_bid="user-grant-bootstrap-route",
            subscription_bid="subscription-user-grant-bootstrap-route",
            product_bid="bill-product-plan-monthly",
            current_period_start_at=datetime(2026, 4, 20, 8, 0, 0),
            current_period_end_at=datetime(2099, 5, 20, 23, 59, 59),
        )

    response = test_client.get(
        "/api/shifu/admin/operations/users/user-grant-bootstrap-route/credit-grant/bootstrap",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["notification_status"] == "template_pending"
    assert (
        payload["data"]["current_subscription_product_display_name_i18n_key"]
        == "module.billing.catalog.plans.creatorMonthly.title"
    )
    assert payload["data"]["plans"][0]["product_bid"] == "bill-product-plan-monthly"


def test_admin_operation_user_grant_bootstrap_route_requires_operator(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch, is_operator=False)

    with app.app_context():
        _seed_user(
            app,
            user_bid="user-grant-bootstrap-route-denied",
            identify="user-grant-bootstrap-route-denied@example.com",
            nickname="Grant Bootstrap Route Denied",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 8, 0, 0),
            updated_at=datetime(2026, 4, 20, 12, 0, 0),
            providers=[("email", "user-grant-bootstrap-route-denied@example.com")],
        )

    response = test_client.get(
        "/api/shifu/admin/operations/users/user-grant-bootstrap-route-denied/credit-grant/bootstrap",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 401


def test_admin_operation_user_package_grant_route_returns_payload(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch)

    with app.app_context():
        db.session.add_all(
            build_bill_products(product_bids=["bill-product-plan-monthly"])
        )
        _seed_user(
            app,
            user_bid="user-package-grant-route",
            identify="user-package-grant-route@example.com",
            nickname="Package Grant Route User",
            state=USER_STATE_PAID,
            is_operator=True,
            created_at=datetime(2026, 4, 20, 8, 0, 0),
            updated_at=datetime(2026, 4, 20, 12, 0, 0),
            providers=[("email", "user-package-grant-route@example.com")],
        )

    response = test_client.post(
        "/api/shifu/admin/operations/users/user-package-grant-route/packages/grant",
        json={
            "request_id": "route-package-grant-request-1",
            "product_bid": "bill-product-plan-monthly",
            "note": "route package check",
        },
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["user_bid"] == "user-package-grant-route"
    assert payload["data"]["product_bid"] == "bill-product-plan-monthly"
    assert payload["data"]["bill_order_bid"]
    assert payload["data"]["subscription_bid"]
    assert payload["data"]["notification_status"] == "template_pending"
    assert payload["data"]["summary"]["available_credits"] == "5"
    assert payload["data"]["current_period_end_at"].endswith("Z")


def test_admin_operation_user_package_grant_route_requires_operator(
    app,
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch, is_operator=False)

    with app.app_context():
        db.session.add_all(
            build_bill_products(product_bids=["bill-product-plan-monthly"])
        )
        _seed_user(
            app,
            user_bid="user-package-grant-route-denied",
            identify="user-package-grant-route-denied@example.com",
            nickname="Package Grant Route Denied",
            state=USER_STATE_PAID,
            is_creator=True,
            created_at=datetime(2026, 4, 20, 8, 0, 0),
            updated_at=datetime(2026, 4, 20, 12, 0, 0),
            providers=[("email", "user-package-grant-route-denied@example.com")],
        )

    response = test_client.post(
        "/api/shifu/admin/operations/users/user-package-grant-route-denied/packages/grant",
        json={
            "request_id": "route-package-grant-request-denied",
            "product_bid": "bill-product-plan-monthly",
            "note": "route denied",
        },
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 401


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


def test_registration_source_map_skips_user_query_when_users_argument_is_empty(
    app, monkeypatch
):
    class ForbiddenUserQuery:
        def filter(self, *_args, **_kwargs):
            raise AssertionError("expected no user query when users=[] is provided")

    with app.app_context():
        monkeypatch.setattr(
            admin_module.UserEntity,
            "query",
            ForbiddenUserQuery(),
            raising=False,
        )

        result = admin_module._load_operator_user_registration_source_map(
            ["user-1", "user-2"],
            users=[],
            credential_rows=[
                SimpleNamespace(
                    user_bid="user-1",
                    provider_name="email",
                    created_at=datetime(2026, 5, 1, 10, 0, 0),
                    id=1,
                )
            ],
        )

    assert result == {"user-1": "email"}


def test_registration_source_map_skips_unknown_provider_when_supported_one_exists(app):
    with app.app_context():
        result = admin_module._load_operator_user_registration_source_map(
            ["user-1"],
            users=[],
            credential_rows=[
                SimpleNamespace(
                    user_bid="user-1",
                    provider_name="password",
                    created_at=datetime(2026, 5, 1, 10, 0, 0),
                    id=1,
                ),
                SimpleNamespace(
                    user_bid="user-1",
                    provider_name="email",
                    created_at=datetime(2026, 5, 1, 10, 5, 0),
                    id=2,
                ),
            ],
        )

    assert result == {"user-1": "email"}


def test_contact_map_skips_user_query_when_users_argument_is_empty(app, monkeypatch):
    class ForbiddenUserQuery:
        def filter(self, *_args, **_kwargs):
            raise AssertionError("expected no user query when users=[] is provided")

    with app.app_context():
        monkeypatch.setattr(
            admin_module.UserEntity,
            "query",
            ForbiddenUserQuery(),
            raising=False,
        )

        result = admin_module._load_operator_user_contact_map(
            ["user-1", "user-2"],
            users=[],
            credential_rows=[
                SimpleNamespace(
                    user_bid="user-1",
                    provider_name="phone",
                    state=CREDENTIAL_STATE_VERIFIED,
                    identifier="13800000000",
                    id=1,
                )
            ],
        )

    assert result["user-1"]["mobile"] == "13800000000"
    assert result["user-1"]["login_methods"] == ["phone"]
    assert result["user-2"] == {"mobile": "", "email": "", "login_methods": []}
