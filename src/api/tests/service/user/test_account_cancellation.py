"""Verify operator-controlled account cancellation behavior."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from flaskr.dao import db
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
)
from flaskr.service.billing.models import BillingOrder, BillingSubscription
from flaskr.service.common.models import AppError
from flaskr.service.profile.models import VariableValue
from flaskr.service.shifu.admin_operations.courses_transfer_copy import (
    transfer_operator_published_courses,
)
from flaskr.service.shifu.admin_operations.user_credits import get_operator_user_credits
from flaskr.service.shifu.admin_operations.users import (
    get_operator_user_detail,
    list_operator_users,
)
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user import account_cancellation
from flaskr.service.user.account_cancellation import (
    cancel_account_subscription_renewals,
    cancel_user_account,
    execute_pending_account_cancellation,
    get_account_cancellation_preview,
    get_account_cancellation_status,
    request_user_account_cancellation,
)
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import (
    AuthCredential,
    UserAccountCancellation,
    UserInfo,
    UserToken,
    UserVerifyCode,
)
from flaskr.service.user.repository import create_user_entity, upsert_credential
from flaskr.util.datetime import now_utc


@pytest.fixture(autouse=True)
def _isolate_account_cancellation_tables(app: object) -> object:
    with app.app_context():
        db.session.query(UserAccountCancellation).delete()
        db.session.query(BillingOrder).delete()
        db.session.query(BillingSubscription).delete()
        db.session.query(UserToken).delete()
        db.session.query(UserVerifyCode).delete()
        db.session.query(VariableValue).delete()
        db.session.query(PublishedShifu).delete()
        db.session.query(DraftShifu).delete()
        db.session.query(AuthCredential).delete()
        db.session.query(UserInfo).delete()
        db.session.commit()
    yield
    with app.app_context():
        db.session.query(UserAccountCancellation).delete()
        db.session.query(BillingOrder).delete()
        db.session.query(BillingSubscription).delete()
        db.session.query(UserToken).delete()
        db.session.query(UserVerifyCode).delete()
        db.session.query(VariableValue).delete()
        db.session.query(PublishedShifu).delete()
        db.session.query(DraftShifu).delete()
        db.session.query(AuthCredential).delete()
        db.session.query(UserInfo).delete()
        db.session.commit()


def _seed_user(
    app: object,
    *,
    user_bid: str,
    identifier: str,
    is_operator: bool = False,
) -> UserInfo:
    user = create_user_entity(
        user_bid=user_bid,
        identify=identifier,
        nickname="Personal nickname",
        language="en-US",
        state=USER_STATE_REGISTERED,
    )
    user.is_operator = 1 if is_operator else 0
    user.learner_profile = "Personal learning profile"
    user.avatar = "https://example.com/private-avatar.png"
    user.api_key = "private-api-key"
    upsert_credential(
        app,
        user_bid=user_bid,
        provider_name="email",
        subject_id=identifier,
        subject_format="email",
        identifier=identifier,
        metadata={"name": "Private name"},
        verified=True,
    )
    return user


def _seed_course(model: type, *, shifu_bid: str, user_bid: str) -> None:
    db.session.add(
        model(
            shifu_bid=shifu_bid,
            title=f"Course {shifu_bid[:6]}",
            description="desc",
            avatar_res_bid="",
            keywords="",
            llm="gpt-test",
            llm_temperature=Decimal(0),
            llm_system_prompt="",
            price=Decimal(0),
            created_user_bid=user_bid,
            updated_user_bid=user_bid,
        )
    )


def test_preview_distinguishes_frozen_drafts_and_published_blockers(
    app: object,
) -> None:
    user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        _seed_user(app, user_bid=user_bid, identifier="learner@example.com")
        _seed_course(DraftShifu, shifu_bid="draft-only", user_bid=user_bid)
        _seed_course(DraftShifu, shifu_bid="published", user_bid=user_bid)
        _seed_course(PublishedShifu, shifu_bid="published", user_bid=user_bid)
        db.session.commit()

        preview = get_account_cancellation_preview(
            app, user_bid=user_bid, operator_user_bid="operator"
        )

        assert preview["draft_course_count"] == 1
        assert [item["shifu_bid"] for item in preview["published_courses"]] == [
            "published"
        ]
        assert preview["can_cancel"] is False
        assert preview["user"]["identifier"] == "learner@example.com"
        assert preview["blockers"] == [
            {"code": "published_course_transfer_required", "count": 1}
        ]
        assert {item["code"] for item in preview["warnings"]} == {
            "draft_courses_frozen"
        }


def test_cancel_deidentifies_account_and_preserves_draft(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid = uuid.uuid4().hex[:32]
    deleted_cache_keys: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.user.account_cancellation.redis.delete",
        deleted_cache_keys.append,
    )
    with app.app_context():
        _seed_user(
            app,
            user_bid="operator",
            identifier="13900000000",
            is_operator=True,
        ).nickname = "Support agent"
        user = _seed_user(app, user_bid=user_bid, identifier="cancel-me@example.com")
        _seed_course(DraftShifu, shifu_bid="kept-draft", user_bid=user_bid)
        db.session.add(
            UserToken(
                user_id=user_bid,
                token="secret-token",
                token_type=0,
                token_expired_at=now_utc() + timedelta(days=1),
            )
        )
        db.session.add(
            UserVerifyCode(
                mail="cancel-me@example.com",
                verify_code="123456",
            )
        )
        db.session.commit()
        preview = get_account_cancellation_preview(
            app, user_bid=user_bid, operator_user_bid="operator"
        )

        result = cancel_user_account(
            app,
            user_bid=user_bid,
            operator_user_bid="operator",
            cancellation_bid=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            preview_version=preview["preview_version"],
            reason="Requested by account owner",
        )

        db.session.refresh(user)
        assert result["status"] == "completed"
        assert user.deleted == 1
        assert user.user_identify.startswith("cancelled:user:")
        assert user.nickname == ""
        assert user.learner_profile == ""
        assert user.avatar == ""
        assert user.api_key == ""
        assert user.cancelled_at is not None
        assert (
            DraftShifu.query.filter_by(shifu_bid="kept-draft", deleted=0).count() == 1
        )
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0
        assert UserVerifyCode.query.filter_by(mail="cancel-me@example.com").count() == 0
        credential = AuthCredential.query.filter_by(user_bid=user_bid).one()
        assert credential.deleted == 1
        assert credential.identifier.startswith("cancelled:identifier:")
        assert credential.raw_profile == "{}"
        audit = UserAccountCancellation.query.filter_by(user_bid=user_bid).one()
        assert audit.reason == "Requested by account owner"
        assert "identifier" not in audit.retention_snapshot
        assert deleted_cache_keys == [
            "ai-shifu:user:secret-token",
            "ai-shifu:user:secret-token:row",
        ]

        cancelled_users = list_operator_users(app, 1, 20, {"user_status": "cancelled"})
        assert cancelled_users.total == 1
        assert cancelled_users.data[0].user_status == "cancelled"
        assert "cancellation_reason" not in cancelled_users.data[0].model_dump()

        cancelled_detail = get_operator_user_detail(app, user_bid)
        assert cancelled_detail.user_status == "cancelled"
        assert cancelled_detail.cancellation_reason == "Requested by account owner"
        assert cancelled_detail.cancellation_operator_mobile == "13900000000"
        assert cancelled_detail.cancellation_operator_nickname == "Support agent"

        cancelled_credits = get_operator_user_credits(
            app,
            user_bid=user_bid,
            page_index=1,
            page_size=20,
        )
        assert cancelled_credits.total == 0


def test_cancel_rejects_stale_preview_without_partial_mutation(app: object) -> None:
    user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        user = _seed_user(app, user_bid=user_bid, identifier="safe@example.com")
        db.session.commit()

        with pytest.raises(AppError):
            cancel_user_account(
                app,
                user_bid=user_bid,
                operator_user_bid="operator",
                cancellation_bid=uuid.uuid4().hex,
                idempotency_key=uuid.uuid4().hex,
                preview_version="stale",
                reason="Requested by account owner",
            )

        db.session.refresh(user)
        assert user.deleted == 0
        assert UserAccountCancellation.query.count() == 0


def test_async_cancellation_persists_then_completes(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid = uuid.uuid4().hex[:32]
    dispatched: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.user.account_cancellation.enqueue_account_cancellation",
        lambda _app, *, cancellation_bid: dispatched.append(cancellation_bid),
    )
    with app.app_context():
        _seed_user(app, user_bid=user_bid, identifier="async@example.com")
        db.session.commit()
        preview = get_account_cancellation_preview(
            app, user_bid=user_bid, operator_user_bid="operator"
        )
        cancellation_bid = uuid.uuid4().hex

        accepted = request_user_account_cancellation(
            app,
            user_bid=user_bid,
            operator_user_bid="operator",
            cancellation_bid=cancellation_bid,
            idempotency_key=cancellation_bid,
            preview_version=preview["preview_version"],
            reason="Requested by account owner",
        )

        assert accepted["status"] == "pending"
        assert dispatched == [cancellation_bid]
        assert (
            get_account_cancellation_status(
                app, user_bid=user_bid, cancellation_bid=cancellation_bid
            )["status"]
            == "pending"
        )
        assert dispatched == [cancellation_bid]

        completed = execute_pending_account_cancellation(
            app, cancellation_bid=cancellation_bid
        )

        assert completed["status"] == "completed"
        assert UserInfo.query.filter_by(user_bid=user_bid).one().deleted == 1


def test_status_atomically_reenqueues_a_stale_cancellation(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid = uuid.uuid4().hex[:32]
    dispatched: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.user.account_cancellation.enqueue_account_cancellation",
        lambda _app, *, cancellation_bid: dispatched.append(cancellation_bid),
    )
    with app.app_context():
        _seed_user(app, user_bid=user_bid, identifier="stale-task@example.com")
        db.session.commit()
        preview = get_account_cancellation_preview(
            app, user_bid=user_bid, operator_user_bid="operator"
        )
        cancellation_bid = uuid.uuid4().hex
        request_user_account_cancellation(
            app,
            user_bid=user_bid,
            operator_user_bid="operator",
            cancellation_bid=cancellation_bid,
            idempotency_key=cancellation_bid,
            preview_version=preview["preview_version"],
            reason="Requested by account owner",
        )
        cancellation = UserAccountCancellation.query.filter_by(
            cancellation_bid=cancellation_bid
        ).one()
        cancellation.requested_at = now_utc() - timedelta(minutes=11)
        db.session.commit()

        first = get_account_cancellation_status(
            app, user_bid=user_bid, cancellation_bid=cancellation_bid
        )
        second = get_account_cancellation_status(
            app, user_bid=user_bid, cancellation_bid=cancellation_bid
        )

        assert first["status"] == "pending"
        assert second["status"] == "pending"
        assert dispatched == [cancellation_bid, cancellation_bid]


def test_worker_rechecks_blockers_without_rejecting_volatile_preview_changes(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid = uuid.uuid4().hex[:32]
    monkeypatch.setattr(
        "flaskr.service.user.account_cancellation.enqueue_account_cancellation",
        lambda *_args, **_kwargs: None,
    )
    with app.app_context():
        _seed_user(app, user_bid=user_bid, identifier="volatile@example.com")
        db.session.commit()
        preview = get_account_cancellation_preview(
            app, user_bid=user_bid, operator_user_bid="operator"
        )
        cancellation_bid = uuid.uuid4().hex
        request_user_account_cancellation(
            app,
            user_bid=user_bid,
            operator_user_bid="operator",
            cancellation_bid=cancellation_bid,
            idempotency_key=cancellation_bid,
            preview_version=preview["preview_version"],
            reason="Requested by account owner",
        )
        db.session.add(
            UserToken(
                user_id=user_bid,
                token="new-session-after-confirmation",
                token_type=0,
                token_expired_at=now_utc() + timedelta(days=1),
            )
        )
        db.session.commit()

        completed = execute_pending_account_cancellation(
            app, cancellation_bid=cancellation_bid
        )

        assert completed["status"] == "completed"
        assert UserInfo.query.filter_by(user_bid=user_bid).one().deleted == 1


def test_async_cancellation_rolls_back_and_can_retry(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid = uuid.uuid4().hex[:32]
    monkeypatch.setattr(
        "flaskr.service.user.account_cancellation.enqueue_account_cancellation",
        lambda *_args, **_kwargs: None,
    )
    with app.app_context():
        user = _seed_user(app, user_bid=user_bid, identifier="retry@example.com")
        token = UserToken(
            user_id=user_bid,
            token="retry-token",
            token_type=0,
            token_expired_at=now_utc() + timedelta(days=1),
        )
        db.session.add(token)
        db.session.commit()
        preview = get_account_cancellation_preview(
            app, user_bid=user_bid, operator_user_bid="operator"
        )
        cancellation_bid = uuid.uuid4().hex
        request_user_account_cancellation(
            app,
            user_bid=user_bid,
            operator_user_bid="operator",
            cancellation_bid=cancellation_bid,
            idempotency_key=cancellation_bid,
            preview_version=preview["preview_version"],
            reason="Requested by account owner",
        )
        original_tombstone = account_cancellation._tombstone
        monkeypatch.setattr(
            "flaskr.service.user.account_cancellation._tombstone",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError()),
        )

        with pytest.raises(RuntimeError):
            execute_pending_account_cancellation(app, cancellation_bid=cancellation_bid)

        db.session.refresh(user)
        assert user.deleted == 0
        assert UserToken.query.filter_by(user_id=user_bid).count() == 1
        failed = UserAccountCancellation.query.filter_by(
            cancellation_bid=cancellation_bid
        ).one()
        assert failed.status == "failed"
        assert failed.failure_code == "execution_failed"
        assert failed.attempt_count == 1

        monkeypatch.setattr(
            "flaskr.service.user.account_cancellation._tombstone",
            original_tombstone,
        )
        retried = request_user_account_cancellation(
            app,
            user_bid=user_bid,
            operator_user_bid="operator",
            cancellation_bid=cancellation_bid,
            idempotency_key=cancellation_bid,
            preview_version=preview["preview_version"],
            reason="Requested by account owner",
        )
        assert retried["status"] == "pending"
        assert (
            execute_pending_account_cancellation(
                app, cancellation_bid=cancellation_bid
            )["status"]
            == "completed"
        )


def test_cancel_subscription_renewals_prepares_manual_subscription(
    app: object,
) -> None:
    user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        _seed_user(app, user_bid=user_bid, identifier="subscriber@example.com")
        subscription = BillingSubscription(
            subscription_bid=uuid.uuid4().hex,
            creator_bid=user_bid,
            product_bid="product",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
        )
        db.session.add(subscription)
        db.session.commit()

        result = cancel_account_subscription_renewals(
            app, user_bid=user_bid, operator_user_bid="operator"
        )

        db.session.refresh(subscription)
        assert result["cancelled_subscription_count"] == 1
        assert subscription.cancel_at_period_end == 1
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
        assert result["preview"]["subscription_renewal_count"] == 0


def test_preview_warns_about_paid_preorder_for_manual_refund(app: object) -> None:
    user_bid = uuid.uuid4().hex[:32]
    subscription_bid = uuid.uuid4().hex
    with app.app_context():
        _seed_user(app, user_bid=user_bid, identifier="preorder@example.com")
        db.session.add(
            BillingOrder(
                bill_order_bid=uuid.uuid4().hex,
                creator_bid=user_bid,
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                product_bid="future-product",
                subscription_bid=subscription_bid,
                currency="CNY",
                payable_amount=9900,
                paid_amount=9900,
                payment_provider="pingxx",
                channel="wechat",
                provider_reference_id="paid-preorder",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=now_utc(),
                metadata_json={
                    "checkout_type": "subscription_preorder",
                    "preorder_state": "pending_effective",
                },
            )
        )
        db.session.commit()

        preview = get_account_cancellation_preview(
            app, user_bid=user_bid, operator_user_bid="operator"
        )

        assert preview["paid_preorder_count"] == 1
        assert preview["can_cancel"] is True
        assert preview["blockers"] == []
        assert {item["code"] for item in preview["warnings"]} == {
            "paid_preorder_refund_required"
        }


def test_batch_transfer_moves_published_courses_and_matching_drafts(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_bid = uuid.uuid4().hex[:32]
    target_bid = uuid.uuid4().hex[:32]
    target_email = "new-owner@example.com"
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.courses_transfer_copy._clear_shifu_permission_cache",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.courses_transfer_copy._clear_shifu_creator_cache",
        lambda *_args: None,
    )
    with app.app_context():
        _seed_user(app, user_bid=source_bid, identifier="old-owner@example.com")
        target = _seed_user(app, user_bid=target_bid, identifier=target_email)
        target.is_creator = 1
        for shifu_bid in ("published-one", "published-two"):
            _seed_course(DraftShifu, shifu_bid=shifu_bid, user_bid=source_bid)
            _seed_course(PublishedShifu, shifu_bid=shifu_bid, user_bid=source_bid)
        _seed_course(DraftShifu, shifu_bid="draft-only", user_bid=source_bid)
        db.session.commit()

        result = transfer_operator_published_courses(
            app,
            previous_creator_user_bid=source_bid,
            contact_type="email",
            identifier=target_email,
            operator_user_bid="operator",
        )

        assert result["transferred_course_count"] == 2
        assert result["target_creator_user_bid"] == target_bid
        assert PublishedShifu.query.filter_by(created_user_bid=target_bid).count() == 2
        assert DraftShifu.query.filter_by(created_user_bid=target_bid).count() == 2
        assert (
            DraftShifu.query.filter_by(
                shifu_bid="draft-only", created_user_bid=source_bid
            ).count()
            == 1
        )
