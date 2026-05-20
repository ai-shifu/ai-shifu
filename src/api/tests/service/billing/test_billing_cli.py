from __future__ import annotations

from datetime import datetime, timedelta
import json
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing import notifications as billing_notifications
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILL_SYS_CONFIG_SEEDS,
    BILLING_TRIAL_PRODUCT_BID,
    CREDIT_USAGE_RATE_SEEDS,
)
from flaskr.service.billing.cli import register_billing_commands
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditUsageRate,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.queries import calculate_self_managed_billing_cycle_end
from flaskr.service.config.models import Config
from flaskr.service.shifu.models import AiCourseAuth
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.repository import (
    create_user_entity,
    load_user_aggregate_by_identifier,
    upsert_credential,
)
from tests.common.fixtures.bill_products import build_bill_products


@pytest.fixture
def billing_cli_runner():
    app = Flask(__name__)
    app.testing = True

    @app.cli.group()
    def console():
        """Test console root."""

    register_billing_commands(console)
    return app.test_cli_runner()


@pytest.fixture
def billing_cli_db_app():
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
        SECRET_KEY="billing-cli-test-secret",
        REDIS_KEY_PREFIX="billing-cli-test:",
    )
    dao.db.init_app(app)

    @app.cli.group()
    def console():
        """Test console root."""

    register_billing_commands(console)

    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _seed_billing_cli_user(
    app: Flask,
    *,
    user_bid: str,
    identify: str,
    phone: str = "",
    email: str = "",
    is_creator: bool = False,
) -> None:
    entity = create_user_entity(
        user_bid=user_bid,
        identify=identify,
        nickname="CLI User",
        language="en-US",
        avatar="",
        state=USER_STATE_REGISTERED,
    )
    entity.is_creator = 1 if is_creator else 0

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
    if email:
        normalized_email = email.lower()
        upsert_credential(
            app,
            user_bid=user_bid,
            provider_name="email",
            subject_id=normalized_email,
            subject_format="email",
            identifier=normalized_email,
            metadata={},
            verified=True,
        )


def _seed_billing_cli_course_auth(
    *,
    auth_bid: str,
    user_bid: str,
    course_bid: str,
    auth_types: list[str],
) -> None:
    dao.db.session.add(
        AiCourseAuth(
            course_auth_id=auth_bid,
            course_id=course_bid,
            user_id=user_bid,
            auth_type=json.dumps(auth_types),
            status=1,
        )
    )


def test_billing_backfill_settlement_cli_requires_explicit_scope(
    billing_cli_runner,
) -> None:
    result = billing_cli_runner.invoke(
        args=["console", "billing", "backfill-settlement"]
    )

    assert result.exit_code != 0
    assert "Pass --usage-bid, a usage id range, or --all" in result.output


def test_billing_backfill_settlement_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.backfill_bill_usage_settlement",
        lambda app, **kwargs: {
            "status": "completed",
            "processed_count": 2,
            "backfill": True,
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "backfill-settlement",
            "--usage-id-start",
            "10",
            "--usage-id-end",
            "12",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "completed"
    assert payload["processed_count"] == 2
    assert payload["kwargs"]["usage_id_start"] == 10
    assert payload["kwargs"]["usage_id_end"] == 12


def test_billing_backfill_trial_plans_cli_requires_explicit_scope(
    billing_cli_runner,
) -> None:
    result = billing_cli_runner.invoke(
        args=["console", "billing", "backfill-trial-plans"]
    )

    assert result.exit_code != 0
    assert "Pass --creator-bid or --all for trial plan backfill." in result.output


def test_billing_backfill_trial_plans_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.backfill_missing_creator_trial_credits",
        lambda app, **kwargs: {
            "status": "completed",
            "granted_count": 2,
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "backfill-trial-plans",
            "--all",
            "--limit",
            "3",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "completed"
    assert payload["granted_count"] == 2
    assert payload["kwargs"]["limit"] == 3


def test_billing_backfill_authoring_permission_creators_cli_requires_explicit_scope(
    billing_cli_runner,
) -> None:
    result = billing_cli_runner.invoke(
        args=["console", "billing", "backfill-authoring-permission-creators"]
    )

    assert result.exit_code != 0
    assert "Pass --user-bid, --course-bid, or --all" in result.output


def test_billing_backfill_authoring_permission_creators_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.backfill_authoring_permission_creators",
        lambda app, **kwargs: {
            "status": "completed",
            "role_granted_count": 1,
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "backfill-authoring-permission-creators",
            "--all",
            "--limit",
            "4",
            "--dry-run",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "completed"
    assert payload["role_granted_count"] == 1
    assert payload["kwargs"]["limit"] == 4
    assert payload["kwargs"]["dry_run"] is True


def test_billing_rebuild_wallets_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.rebuild_credit_wallet_snapshots",
        lambda app, **kwargs: {
            "status": "rebuilt",
            "wallet_count": 1,
            "wallets": [{"wallet_bid": "wallet-1"}],
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "rebuild-wallets",
            "--creator-bid",
            "creator-cli-1",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "rebuilt"
    assert payload["kwargs"]["creator_bid"] == "creator-cli-1"


def test_billing_repair_topup_expiry_cli_requires_creator_bid(
    billing_cli_runner,
) -> None:
    result = billing_cli_runner.invoke(
        args=["console", "billing", "repair-topup-expiry"]
    )

    assert result.exit_code != 0
    assert "Pass --creator-bid for topup expiry repair." in result.output


def test_billing_repair_topup_expiry_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.repair_topup_grant_expiries",
        lambda app, **kwargs: {
            "status": "repaired",
            "repaired_bucket_count": 1,
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "repair-topup-expiry",
            "--creator-bid",
            "creator-cli-1",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "repaired"
    assert payload["kwargs"]["creator_bid"] == "creator-cli-1"


def test_billing_repair_bucket_status_cli_requires_explicit_scope(
    billing_cli_runner,
) -> None:
    result = billing_cli_runner.invoke(
        args=["console", "billing", "repair-bucket-status"]
    )

    assert result.exit_code != 0
    assert (
        "Pass --creator-bid or --wallet-bucket-bid for bucket status repair."
        in result.output
    )


def test_billing_repair_bucket_status_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.repair_credit_bucket_runtime_statuses",
        lambda app, **kwargs: {
            "status": "repaired",
            "repaired_bucket_count": 1,
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "repair-bucket-status",
            "--wallet-bucket-bid",
            "bucket-cli-1",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "repaired"
    assert payload["kwargs"]["wallet_bucket_bid"] == "bucket-cli-1"


def test_billing_repair_subscription_cycle_cli_requires_explicit_scope(
    billing_cli_runner,
) -> None:
    result = billing_cli_runner.invoke(
        args=["console", "billing", "repair-subscription-cycle"]
    )

    assert result.exit_code != 0
    assert (
        "Pass --creator-bid or --subscription-bid for subscription cycle repair."
        in result.output
    )


def test_billing_repair_subscription_cycle_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.repair_subscription_cycle_mismatches",
        lambda app, **kwargs: {
            "status": "repaired",
            "repaired_subscription_count": 1,
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "repair-subscription-cycle",
            "--creator-bid",
            "creator-cli-1",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "repaired"
    assert payload["kwargs"]["creator_bid"] == "creator-cli-1"


def test_billing_reconcile_order_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.reconcile_billing_provider_reference",
        lambda app, **kwargs: {
            "status": "paid",
            "bill_order_bid": "bill-order-cli-1",
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "reconcile-order",
            "--bill-order-bid",
            "bill-order-cli-1",
            "--payment-provider",
            "stripe",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "paid"
    assert payload["kwargs"]["payment_provider"] == "stripe"


def test_billing_retry_renewal_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.retry_billing_renewal_event",
        lambda app, **kwargs: {
            "status": "applied",
            "renewal_event_bid": kwargs.get("renewal_event_bid"),
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "retry-renewal",
            "--renewal-event-bid",
            "renewal-event-cli-1",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "applied"
    assert payload["renewal_event_bid"] == "renewal-event-cli-1"


def test_billing_requeue_subscription_purchase_sms_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.requeue_subscription_purchase_sms",
        lambda app, **kwargs: {
            "status": "enqueued",
            "bill_order_bid": kwargs.get("bill_order_bid"),
            "enqueued": True,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "requeue-subscription-purchase-sms",
            "--bill-order-bid",
            "bill-order-cli-sms-1",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "enqueued"
    assert payload["bill_order_bid"] == "bill-order-cli-sms-1"
    assert payload["enqueued"] is True


def test_billing_rebuild_daily_aggregates_cli_requires_explicit_scope(
    billing_cli_runner,
) -> None:
    result = billing_cli_runner.invoke(
        args=["console", "billing", "rebuild-daily-aggregates"]
    )

    assert result.exit_code != 0
    assert "Pass --date-from/--date-to or --all" in result.output


def test_billing_rebuild_daily_aggregates_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.rebuild_daily_aggregates",
        lambda app, **kwargs: {
            "status": "rebuilt",
            "day_count": 3,
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "rebuild-daily-aggregates",
            "--creator-bid",
            "creator-cli-1",
            "--shifu-bid",
            "shifu-cli-1",
            "--date-from",
            "2026-04-08",
            "--date-to",
            "2026-04-10",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "rebuilt"
    assert payload["day_count"] == 3
    assert payload["kwargs"]["creator_bid"] == "creator-cli-1"
    assert payload["kwargs"]["shifu_bid"] == "shifu-cli-1"
    assert payload["kwargs"]["date_from"] == "2026-04-08"
    assert payload["kwargs"]["date_to"] == "2026-04-10"


def test_billing_grant_plan_cli_grants_manual_plan_by_phone_identify(
    billing_cli_db_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()
    enqueue_calls: list[str] = []

    def _fake_enqueue(app: Flask, *, bill_order_bid: str) -> dict[str, object]:
        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            notification_payload = order.metadata_json["notifications"][
                "subscription_purchase_sms"
            ]
            assert notification_payload["status"] == "pending"
        enqueue_calls.append(bill_order_bid)
        return {
            "status": "enqueued",
            "bill_order_bid": bill_order_bid,
            "enqueued": True,
        }

    monkeypatch.setattr(
        "flaskr.service.billing.cli.enqueue_subscription_purchase_sms",
        _fake_enqueue,
    )

    with billing_cli_db_app.app_context():
        dao.db.session.add_all(
            build_bill_products(product_bids=["bill-product-plan-monthly"])
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="creator-cli-phone",
            identify="creator-cli-phone",
            phone="13800138000",
            is_creator=False,
        )
        dao.db.session.commit()

    result = runner.invoke(
        args=[
            "console",
            "billing",
            "grant-plan",
            "--identify",
            "13800138000",
            "--product-code",
            "creator-plan-monthly",
            "--note",
            "ops grant",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "granted"
    assert payload["creator_bid"] == "creator-cli-phone"
    assert payload["creator_role_granted"] is True
    assert payload["product_code"] == "creator-plan-monthly"
    assert payload["mobile"] == "13800138000"
    assert payload["sms_enqueue_status"] == "enqueued"
    assert payload["sms_enqueued"] is True
    assert enqueue_calls == [payload["bill_order_bid"]]

    with billing_cli_db_app.app_context():
        aggregate = load_user_aggregate_by_identifier("13800138000")
        wallet = CreditWallet.query.filter_by(creator_bid="creator-cli-phone").one()
        order = BillingOrder.query.filter_by(creator_bid="creator-cli-phone").one()
        subscription = BillingSubscription.query.filter_by(
            creator_bid="creator-cli-phone"
        ).one()
        pending_events = BillingRenewalEvent.query.filter_by(
            subscription_bid=subscription.subscription_bid,
            status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
        ).all()

        assert aggregate is not None
        assert aggregate.is_creator is True
        assert wallet.available_credits == Decimal("5.0000000000")
        assert order.status == BILLING_ORDER_STATUS_PAID
        assert order.payment_provider == "manual"
        assert order.payable_amount == 0
        assert order.paid_amount == 0
        assert order.metadata_json["checkout_type"] == "manual_grant"
        assert order.metadata_json["note"] == "ops grant"
        assert (
            order.metadata_json["notifications"]["subscription_purchase_sms"]["status"]
            == "pending"
        )
        assert subscription.billing_provider == "manual"
        assert subscription.current_period_start_at is not None
        assert subscription.current_period_end_at is not None
        product = BillingProduct.query.filter_by(
            product_code="creator-plan-monthly"
        ).one()
        expected_period_end_at = calculate_self_managed_billing_cycle_end(
            product,
            cycle_start_at=order.paid_at,
        )
        assert subscription.current_period_end_at == expected_period_end_at
        assert len(pending_events) == 1
        assert pending_events[0].event_type == BILLING_RENEWAL_EVENT_TYPE_EXPIRE
        assert pending_events[0].scheduled_at == expected_period_end_at


def test_billing_grant_credits_cli_grants_visible_manual_credits(
    billing_cli_db_app: Flask,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()

    with billing_cli_db_app.app_context():
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="creator-cli-credit",
            identify="creator-cli-credit",
            phone="13800138001",
            is_creator=True,
        )
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="sub-cli-credit-active",
                creator_bid="creator-cli-credit",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="manual",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=datetime.now() - timedelta(days=1),
                current_period_end_at=datetime.now() + timedelta(days=30),
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
            )
        )
        dao.db.session.commit()

    result = runner.invoke(
        args=[
            "console",
            "billing",
            "grant-credits",
            "--identify",
            "13800138001",
            "--amount",
            "12.5",
            "--grant-source",
            "compensation",
            "--name",
            "模型扣费补偿",
            "--note",
            "DeepSeek 费率补偿",
            "--operator-user-bid",
            "operator-cli-1",
        ]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "granted"
    assert payload["creator_bid"] == "creator-cli-credit"
    assert payload["mobile"] == "13800138001"
    assert payload["amount"] == 12.5
    assert payload["grant_source"] == "compensation"
    assert payload["validity_preset"] == "align_subscription"
    assert payload["display_name"] == "模型扣费补偿"
    assert payload["note"] == "DeepSeek 费率补偿"
    assert payload["operator_user_bid"] == "operator-cli-1"
    assert payload["request_id"].startswith("cli:")

    with billing_cli_db_app.app_context():
        wallet = CreditWallet.query.filter_by(creator_bid="creator-cli-credit").one()
        bucket = CreditWalletBucket.query.filter_by(
            creator_bid="creator-cli-credit"
        ).one()
        ledger = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-cli-credit"
        ).one()

        assert wallet.available_credits == Decimal("12.5000000000")
        assert bucket.available_credits == Decimal("12.5000000000")
        assert bucket.metadata_json["grant_source"] == "compensation"
        assert bucket.metadata_json["validity_preset"] == "align_subscription"
        assert "display_name" not in bucket.metadata_json
        assert "note" not in bucket.metadata_json
        assert ledger.wallet_bucket_bid == bucket.wallet_bucket_bid
        assert ledger.amount == Decimal("12.5000000000")
        assert ledger.metadata_json["grant_source"] == "compensation"
        assert ledger.metadata_json["display_name"] == "模型扣费补偿"
        assert ledger.metadata_json["name"] == "模型扣费补偿"
        assert ledger.metadata_json["note"] == "DeepSeek 费率补偿"
        assert ledger.metadata_json["operator_user_bid"] == "operator-cli-1"
        assert ledger.metadata_json["grant_channel"] == "operator_cli"
        assert (
            ledger.idempotency_key == f"operator_manual_grant:{payload['request_id']}"
        )


def test_billing_grant_credits_cli_reuses_request_id(
    billing_cli_db_app: Flask,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()

    with billing_cli_db_app.app_context():
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="creator-cli-credit-idempotent",
            identify="creator-cli-credit-idempotent@example.com",
            email="creator-cli-credit-idempotent@example.com",
            is_creator=True,
        )
        dao.db.session.commit()

    args = [
        "console",
        "billing",
        "grant-credits",
        "--user-bid",
        "creator-cli-credit-idempotent",
        "--amount",
        "3",
        "--grant-source",
        "reward",
        "--validity-preset",
        "1d",
        "--name",
        "运营奖励",
        "--note",
        "活动奖励",
    ]
    first = runner.invoke(args=args)
    second = runner.invoke(args=args)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    first_payload = json.loads(first.output)
    second_payload = json.loads(second.output)
    assert first_payload["status"] == "granted"
    assert second_payload["status"] == "noop_existing"
    assert second_payload["request_id"] == first_payload["request_id"]
    assert second_payload["ledger_bid"] == first_payload["ledger_bid"]

    with billing_cli_db_app.app_context():
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-cli-credit-idempotent"
        ).one()
        assert wallet.available_credits == Decimal("3.0000000000")
        assert (
            CreditLedgerEntry.query.filter_by(
                creator_bid="creator-cli-credit-idempotent"
            ).count()
            == 1
        )


def test_billing_backfill_trial_plans_cli_grants_missing_trials_for_creators(
    billing_cli_db_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()
    monkeypatch.setattr(
        "flaskr.service.billing.trials._is_billing_enabled",
        lambda: True,
    )

    with billing_cli_db_app.app_context():
        dao.db.session.add_all(
            build_bill_products(
                product_bids=[
                    "bill-product-plan-trial",
                    "bill-product-plan-monthly",
                ]
            )
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="creator-cli-trial-missing",
            identify="creator-cli-trial-missing@example.com",
            email="creator-cli-trial-missing@example.com",
            is_creator=True,
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="creator-cli-trial-existing",
            identify="creator-cli-trial-existing@example.com",
            email="creator-cli-trial-existing@example.com",
            is_creator=True,
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="creator-cli-trial-paid",
            identify="creator-cli-trial-paid@example.com",
            email="creator-cli-trial-paid@example.com",
            is_creator=True,
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="creator-cli-non-creator",
            identify="creator-cli-non-creator@example.com",
            email="creator-cli-non-creator@example.com",
            is_creator=False,
        )
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="sub-cli-trial-existing",
                creator_bid="creator-cli-trial-existing",
                product_bid=BILLING_TRIAL_PRODUCT_BID,
                status=BILLING_SUBSCRIPTION_STATUS_DRAFT,
                billing_provider="manual",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=datetime.now() - timedelta(days=1),
                current_period_end_at=datetime.now() + timedelta(days=14),
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={"trial_bootstrap": True},
            )
        )
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="sub-cli-trial-paid",
                creator_bid="creator-cli-trial-paid",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_cli_trial_paid",
                provider_customer_id="cus_provider_cli_trial_paid",
                current_period_start_at=datetime.now() - timedelta(days=1),
                current_period_end_at=datetime.now() + timedelta(days=30),
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
            )
        )
        dao.db.session.commit()

    result = runner.invoke(args=["console", "billing", "backfill-trial-plans", "--all"])

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "completed"
    assert payload["creator_count"] == 3
    assert payload["granted_count"] == 1
    assert payload["skipped_count"] == 2

    records_by_bid = {item["creator_bid"]: item for item in payload["records"]}
    assert records_by_bid["creator-cli-trial-missing"]["status"] == "granted"
    assert records_by_bid["creator-cli-trial-existing"]["reason"] == (
        "trial_subscription_exists"
    )
    assert records_by_bid["creator-cli-trial-paid"]["reason"] == (
        "active_subscription_exists"
    )

    with billing_cli_db_app.app_context():
        granted_subscription = BillingSubscription.query.filter_by(
            creator_bid="creator-cli-trial-missing"
        ).one()
        granted_order = BillingOrder.query.filter_by(
            creator_bid="creator-cli-trial-missing"
        ).one()
        granted_wallet = CreditWallet.query.filter_by(
            creator_bid="creator-cli-trial-missing"
        ).one()

        assert granted_subscription.product_bid == BILLING_TRIAL_PRODUCT_BID
        assert granted_subscription.billing_provider == "manual"
        assert granted_order.product_bid == BILLING_TRIAL_PRODUCT_BID
        assert granted_order.payment_provider == "manual"
        assert granted_wallet.available_credits == Decimal("100.0000000000")
        assert (
            BillingSubscription.query.filter_by(
                creator_bid="creator-cli-non-creator"
            ).count()
            == 0
        )


def test_billing_backfill_authoring_permission_creators_dry_run_does_not_mutate(
    billing_cli_db_app: Flask,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()

    with billing_cli_db_app.app_context():
        dao.db.session.add_all(
            build_bill_products(product_bids=[BILLING_TRIAL_PRODUCT_BID])
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="authoring-cli-dry-run",
            identify="authoring-cli-dry-run@example.com",
            email="authoring-cli-dry-run@example.com",
            is_creator=False,
        )
        _seed_billing_cli_course_auth(
            auth_bid="auth-authoring-cli-dry-run",
            user_bid="authoring-cli-dry-run",
            course_bid="course-authoring-cli-dry-run",
            auth_types=["edit"],
        )
        dao.db.session.commit()

    result = runner.invoke(
        args=[
            "console",
            "billing",
            "backfill-authoring-permission-creators",
            "--all",
            "--dry-run",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "completed"
    assert payload["role_would_grant_count"] == 1
    assert payload["role_granted_count"] == 0
    assert payload["trial_granted_count"] == 0

    with billing_cli_db_app.app_context():
        user = UserEntity.query.filter_by(user_bid="authoring-cli-dry-run").one()
        assert user.is_creator == 0
        assert (
            BillingOrder.query.filter_by(creator_bid="authoring-cli-dry-run").count()
            == 0
        )


def test_billing_backfill_authoring_permission_creators_grants_roles_and_trials(
    billing_cli_db_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()
    monkeypatch.setattr(
        "flaskr.service.billing.trials._is_billing_enabled",
        lambda: True,
    )

    with billing_cli_db_app.app_context():
        dao.db.session.add_all(
            build_bill_products(product_bids=[BILLING_TRIAL_PRODUCT_BID])
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="authoring-cli-edit",
            identify="authoring-cli-edit@example.com",
            email="authoring-cli-edit@example.com",
            is_creator=False,
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="authoring-cli-publish",
            identify="authoring-cli-publish@example.com",
            email="authoring-cli-publish@example.com",
            is_creator=False,
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="authoring-cli-view",
            identify="authoring-cli-view@example.com",
            email="authoring-cli-view@example.com",
            is_creator=False,
        )
        _seed_billing_cli_course_auth(
            auth_bid="auth-authoring-cli-edit",
            user_bid="authoring-cli-edit",
            course_bid="course-authoring-cli",
            auth_types=["edit"],
        )
        _seed_billing_cli_course_auth(
            auth_bid="auth-authoring-cli-publish",
            user_bid="authoring-cli-publish",
            course_bid="course-authoring-cli",
            auth_types=["edit", "publish"],
        )
        _seed_billing_cli_course_auth(
            auth_bid="auth-authoring-cli-view",
            user_bid="authoring-cli-view",
            course_bid="course-authoring-cli",
            auth_types=["view"],
        )
        dao.db.session.commit()

    result = runner.invoke(
        args=[
            "console",
            "billing",
            "backfill-authoring-permission-creators",
            "--all",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "completed"
    assert payload["role_granted_count"] == 2
    assert payload["role_skipped_count"] == 1
    assert payload["trial_granted_count"] == 2
    assert payload["trial_skipped_count"] == 1

    records_by_bid = {item["creator_bid"]: item for item in payload["records"]}
    assert records_by_bid["authoring-cli-view"]["role_reason"] == (
        "non_authoring_permission"
    )

    with billing_cli_db_app.app_context():
        edit_user = UserEntity.query.filter_by(user_bid="authoring-cli-edit").one()
        publish_user = UserEntity.query.filter_by(
            user_bid="authoring-cli-publish"
        ).one()
        view_user = UserEntity.query.filter_by(user_bid="authoring-cli-view").one()
        assert edit_user.is_creator == 1
        assert publish_user.is_creator == 1
        assert view_user.is_creator == 0
        assert (
            BillingOrder.query.filter_by(creator_bid="authoring-cli-edit").count() == 1
        )
        assert (
            BillingOrder.query.filter_by(creator_bid="authoring-cli-publish").count()
            == 1
        )
        assert (
            BillingOrder.query.filter_by(creator_bid="authoring-cli-view").count() == 0
        )


def test_billing_grant_plan_cli_accepts_explicit_effective_to(
    billing_cli_db_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()
    expected_effective_to = "2030-05-01T12:30:00"

    monkeypatch.setattr(
        "flaskr.service.billing.cli.enqueue_subscription_purchase_sms",
        lambda app, *, bill_order_bid: {
            "status": "enqueued",
            "bill_order_bid": bill_order_bid,
            "enqueued": True,
        },
    )

    with billing_cli_db_app.app_context():
        dao.db.session.add_all(
            build_bill_products(product_bids=["bill-product-plan-monthly"])
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="creator-cli-explicit-end",
            identify="creator-cli-explicit-end@example.com",
            email="creator-cli-explicit-end@example.com",
            is_creator=True,
        )
        dao.db.session.commit()

    result = runner.invoke(
        args=[
            "console",
            "billing",
            "grant-plan",
            "--identify",
            "creator-cli-explicit-end@example.com",
            "--product-code",
            "creator-plan-monthly",
            "--effective-to",
            expected_effective_to,
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "granted"
    assert payload["current_period_end_at"] == expected_effective_to

    with billing_cli_db_app.app_context():
        order = BillingOrder.query.filter_by(
            creator_bid="creator-cli-explicit-end"
        ).one()
        subscription = BillingSubscription.query.filter_by(
            creator_bid="creator-cli-explicit-end"
        ).one()
        expire_event = BillingRenewalEvent.query.filter_by(
            subscription_bid=subscription.subscription_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
        ).one()

        assert subscription.current_period_end_at == datetime.fromisoformat(
            expected_effective_to
        )
        assert order.metadata_json["effective_to"] == expected_effective_to
        assert billing_notifications._resolve_notification_date_text(
            billing_cli_db_app,
            order,
        ).startswith("2030-05-01 12:30")
        assert expire_event.scheduled_at == datetime.fromisoformat(
            expected_effective_to
        )


def test_billing_grant_plan_cli_upgrades_active_manual_subscription(
    billing_cli_db_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()
    expected_effective_to = "2030-05-01T12:30:00"

    monkeypatch.setattr(
        "flaskr.service.billing.cli.enqueue_subscription_purchase_sms",
        lambda app, *, bill_order_bid: {
            "status": "enqueued",
            "bill_order_bid": bill_order_bid,
            "enqueued": True,
        },
    )

    with billing_cli_db_app.app_context():
        dao.db.session.add_all(
            build_bill_products(
                product_bids=[
                    "bill-product-plan-trial",
                    "bill-product-plan-yearly-premium",
                ]
            )
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="creator-cli-trial-upgrade",
            identify="creator-cli-trial-upgrade@example.com",
            email="creator-cli-trial-upgrade@example.com",
            is_creator=True,
        )
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="sub-cli-trial-upgrade",
                creator_bid="creator-cli-trial-upgrade",
                product_bid="bill-product-plan-trial",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="manual",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=datetime.now() - timedelta(days=1),
                current_period_end_at=datetime.now() + timedelta(days=14),
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={"trial_bootstrap": True},
            )
        )
        dao.db.session.commit()

    result = runner.invoke(
        args=[
            "console",
            "billing",
            "grant-plan",
            "--identify",
            "creator-cli-trial-upgrade@example.com",
            "--product-code",
            "creator-plan-yearly-premium",
            "--effective-to",
            expected_effective_to,
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "granted"
    assert payload["current_period_end_at"] == expected_effective_to

    with billing_cli_db_app.app_context():
        order = BillingOrder.query.filter_by(
            creator_bid="creator-cli-trial-upgrade"
        ).one()
        subscription = BillingSubscription.query.filter_by(
            creator_bid="creator-cli-trial-upgrade"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-cli-trial-upgrade"
        ).one()
        expire_event = BillingRenewalEvent.query.filter_by(
            subscription_bid=subscription.subscription_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
        ).one()

        assert (
            BillingSubscription.query.filter_by(
                creator_bid="creator-cli-trial-upgrade"
            ).count()
            == 1
        )
        assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE
        assert order.subscription_bid == "sub-cli-trial-upgrade"
        assert order.metadata_json["effective_to"] == expected_effective_to
        assert order.metadata_json["applied_cycle_end_at"] == expected_effective_to
        assert subscription.subscription_bid == "sub-cli-trial-upgrade"
        assert subscription.product_bid == "bill-product-plan-yearly-premium"
        assert subscription.billing_provider == "manual"
        assert subscription.current_period_end_at == datetime.fromisoformat(
            expected_effective_to
        )
        assert wallet.available_credits == Decimal("22000.0000000000")
        assert billing_notifications._resolve_notification_date_text(
            billing_cli_db_app,
            order,
        ).startswith("2030-05-01 12:30")
        assert expire_event.scheduled_at == datetime.fromisoformat(
            expected_effective_to
        )


def test_billing_grant_plan_cli_returns_noop_for_same_active_plan_without_sms(
    billing_cli_db_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()

    def _unexpected_enqueue(app: Flask, *, bill_order_bid: str) -> dict[str, object]:
        raise AssertionError(f"unexpected enqueue for {bill_order_bid}")

    monkeypatch.setattr(
        "flaskr.service.billing.cli.enqueue_subscription_purchase_sms",
        _unexpected_enqueue,
    )

    with billing_cli_db_app.app_context():
        dao.db.session.add_all(
            build_bill_products(product_bids=["bill-product-plan-monthly"])
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="creator-cli-noop",
            identify="creator-cli-noop@example.com",
            email="creator-cli-noop@example.com",
            is_creator=True,
        )
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="sub-cli-noop-1",
                creator_bid="creator-cli-noop",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_noop_1",
                provider_customer_id="cus_provider_noop_1",
                current_period_start_at=datetime.now() - timedelta(days=1),
                current_period_end_at=datetime.now() + timedelta(days=30),
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
            )
        )
        dao.db.session.commit()

    result = runner.invoke(
        args=[
            "console",
            "billing",
            "grant-plan",
            "--identify",
            "creator-cli-noop@example.com",
            "--product-code",
            "creator-plan-monthly",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "noop_active"
    assert payload["bill_order_bid"] is None

    with billing_cli_db_app.app_context():
        assert BillingOrder.query.filter_by(creator_bid="creator-cli-noop").count() == 0


def test_billing_grant_plan_cli_rejects_when_provider_managed_subscription_exists(
    billing_cli_db_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()

    def _unexpected_enqueue(app: Flask, *, bill_order_bid: str) -> dict[str, object]:
        raise AssertionError(f"unexpected enqueue for {bill_order_bid}")

    monkeypatch.setattr(
        "flaskr.service.billing.cli.enqueue_subscription_purchase_sms",
        _unexpected_enqueue,
    )

    with billing_cli_db_app.app_context():
        dao.db.session.add_all(
            build_bill_products(
                product_bids=[
                    "bill-product-plan-monthly",
                    "bill-product-plan-yearly",
                ]
            )
        )
        _seed_billing_cli_user(
            billing_cli_db_app,
            user_bid="creator-cli-email",
            identify="creator-cli-email@example.com",
            email="creator-cli-email@example.com",
            is_creator=True,
        )
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="sub-cli-active-1",
                creator_bid="creator-cli-email",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_active_1",
                provider_customer_id="cus_provider_active_1",
                current_period_start_at=datetime.now() - timedelta(days=1),
                current_period_end_at=datetime.now() + timedelta(days=30),
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
            )
        )
        dao.db.session.commit()

    result = runner.invoke(
        args=[
            "console",
            "billing",
            "grant-plan",
            "--identify",
            "CREATOR-CLI-EMAIL@example.com",
            "--product-bid",
            "bill-product-plan-yearly",
        ]
    )

    assert result.exit_code != 0
    assert "active provider-managed subscription" in result.output

    with billing_cli_db_app.app_context():
        assert (
            BillingOrder.query.filter_by(creator_bid="creator-cli-email").count() == 0
        )


def test_billing_seed_bootstrap_data_cli_is_idempotent(
    billing_cli_db_app: Flask,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()

    first_result = runner.invoke(args=["console", "billing", "seed-bootstrap-data"])
    second_result = runner.invoke(args=["console", "billing", "seed-bootstrap-data"])

    first_payload = json.loads(first_result.output)
    second_payload = json.loads(second_result.output)

    assert first_result.exit_code == 0
    assert second_result.exit_code == 0
    assert first_payload["rates"]["inserted"] == len(CREDIT_USAGE_RATE_SEEDS)
    assert first_payload["configs"]["inserted"] == len(BILL_SYS_CONFIG_SEEDS)
    assert second_payload["rates"]["updated"] == len(CREDIT_USAGE_RATE_SEEDS)
    assert second_payload["configs"]["updated"] == len(BILL_SYS_CONFIG_SEEDS)
    assert second_payload["products"]["count"] == 0

    with billing_cli_db_app.app_context():
        assert CreditUsageRate.query.count() == len(CREDIT_USAGE_RATE_SEEDS)
        assert Config.query.count() == len(BILL_SYS_CONFIG_SEEDS)


def test_billing_upsert_product_cli_allows_manual_custom_product_values(
    billing_cli_db_app: Flask,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()
    base_args = [
        "console",
        "billing",
        "upsert-product",
        "--product-bid",
        "bill-product-custom-cli",
        "--product-code",
        "creator-custom-cli",
        "--product-type",
        "custom",
        "--billing-mode",
        "manual",
        "--billing-interval",
        "none",
        "--billing-interval-count",
        "0",
        "--display-name-i18n-key",
        "module.billing.catalog.custom.cli.title",
        "--description-i18n-key",
        "module.billing.catalog.custom.cli.description",
        "--currency",
        "usd",
        "--price-amount",
        "2599",
        "--credit-amount",
        "42.5000000000",
        "--allocation-interval",
        "manual",
        "--auto-renew-enabled",
        "0",
        "--status",
        "active",
        "--sort-order",
        "120",
        "--entitlement-json",
        '{"support_tier":"priority"}',
        "--metadata-json",
        '{"badge":"launch"}',
    ]

    first_result = runner.invoke(args=base_args)
    second_result = runner.invoke(
        args=[
            *base_args[:-2],
            "--metadata-json",
            '{"badge":"updated","segment":"enterprise"}',
        ]
    )

    first_payload = json.loads(first_result.output)
    second_payload = json.loads(second_result.output)

    assert first_result.exit_code == 0
    assert second_result.exit_code == 0
    assert first_payload["created"] is True
    assert second_payload["created"] is False
    assert second_payload["product_bid"] == "bill-product-custom-cli"

    with billing_cli_db_app.app_context():
        product = BillingProduct.query.filter_by(
            product_bid="bill-product-custom-cli"
        ).one()
        assert product.product_code == "creator-custom-cli"
        assert product.currency == "USD"
        assert product.price_amount == 2599
        assert str(product.credit_amount) == "42.5000000000"
        assert product.metadata_json == {
            "badge": "updated",
            "segment": "enterprise",
        }
        assert product.entitlement_payload == {"support_tier": "priority"}
