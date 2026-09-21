"""Exercise billing maintenance commands through Click and real database writes."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.billing import cli
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.user.repository import load_user_aggregate
from flaskr.util.datetime import now_utc

from tests.common.fixtures.bill_products import build_bill_products
from tests.service.billing import test_billing_cli as cli_fixtures
from tests.service.billing.test_billing_cli import (
    _seed_billing_cli_course_auth,
    _seed_billing_cli_user,
)

if TYPE_CHECKING:
    from flask import Flask


# Share the isolated SQLite fixture without changing the common test configuration.
billing_cli_db_app = cli_fixtures.billing_cli_db_app


def _product_args() -> list[str]:
    return [
        "console",
        "billing",
        "upsert-product",
        "--product-bid",
        "product-test",
        "--product-code",
        "product-code",
        "--product-type",
        "plan",
        "--billing-mode",
        "recurring",
        "--billing-interval",
        "month",
        "--display-name-i18n-key",
        "module.billing.test.title",
        "--description-i18n-key",
        "module.billing.test.description",
        "--price-amount",
        "1000",
        "--credit-amount",
        "5",
        "--allocation-interval",
        "per_cycle",
    ]


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("rebuild-wallets", "Pass --creator-bid, --wallet-bid, or --all"),
        ("audit-credit-state", "Pass --creator-bid or --all"),
        ("reconcile-order", "Pass --bill-order-bid or --provider-reference-id"),
        ("run-renewal-event", "Pass a renewal event, subscription, or creator target"),
        (
            "retry-renewal",
            "Pass a renewal event, subscription, creator, or bill order target",
        ),
        ("requeue-subscription-purchase-sms", "Pass --bill-order-bid"),
    ],
)
def test_maintenance_commands_reject_unscoped_mutations(
    command: str, message: str, billing_cli_db_app: Flask
) -> None:
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=["console", "billing", command]
    )
    assert result.exit_code == 1
    assert message in result.output
    assert BillingOrder.query.count() == 0
    assert CreditLedgerEntry.query.count() == 0


@pytest.mark.parametrize(
    "field",
    ["product-bid", "product-code", "display-name-i18n-key", "description-i18n-key"],
)
def test_product_command_rejects_whitespace_required_values(
    field: str, billing_cli_db_app: Flask
) -> None:
    args = _product_args()
    args[args.index(f"--{field}") + 1] = " "
    result = billing_cli_db_app.test_cli_runner().invoke(args=args)
    assert result.exit_code == 1
    assert f"--{field} is required" in result.output
    assert BillingProduct.query.count() == 0


@pytest.mark.parametrize("option", ["metadata-json", "entitlement-json"])
@pytest.mark.parametrize(
    ("value", "valid", "message"),
    [
        ("not-json", False, "must be valid JSON"),
        ("[]", False, "must decode to a JSON object"),
        ("null", True, ""),
        ('{"enabled":true}', True, ""),
    ],
)
def test_product_command_validates_optional_json_before_persisting(
    option: str, value: str, valid: bool, message: str, billing_cli_db_app: Flask
) -> None:
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=[*_product_args(), f"--{option}", value]
    )
    assert result.exit_code == (0 if valid else 1), result.output
    if valid:
        product = BillingProduct.query.one()
        stored = (
            product.metadata_json
            if option == "metadata-json"
            else product.entitlement_payload
        )
        assert stored == json.loads(value)
    else:
        assert message in result.output
        assert BillingProduct.query.count() == 0


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ([], "Pass exactly one"),
        (["--identify", "one", "--user-bid", "two"], "Pass exactly one"),
        (["--user-bid", "absent"], "No user found for target"),
        (["--user-bid", "test", "--request-id", "x" * 101], "--request-id must be 100"),
        (["--user-bid", "test", "--name", "x" * 129], "--name must be 128"),
        (["--user-bid", "test", "--note", "x" * 256], "--note must be 255"),
    ],
)
def test_manual_credit_command_rejects_ambiguous_missing_and_oversized_inputs(
    extra: list[str], message: str, billing_cli_db_app: Flask
) -> None:
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=["console", "billing", "grant-credits", "--amount", "5", *extra]
    )
    assert result.exit_code == 1
    assert message in result.output
    assert CreditLedgerEntry.query.count() == 0
    assert CreditWalletBucket.query.count() == 0


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--identify", " "], "--identify is required"),
        (["--identify", "teacher", "--note", "x" * 256], "--note must be 255"),
        (["--identify", "teacher"], "Pass exactly one"),
        (
            ["--identify", "teacher", "--product-bid", "one", "--product-code", "two"],
            "Pass exactly one",
        ),
        (
            ["--identify", "absent", "--product-bid", "one"],
            "No user found for identify",
        ),
    ],
)
def test_manual_plan_command_rejects_invalid_identity_and_product_selection(
    extra: list[str], message: str, billing_cli_db_app: Flask
) -> None:
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=["console", "billing", "grant-plan", *extra]
    )
    assert result.exit_code == 1
    assert message in result.output
    assert BillingSubscription.query.count() == 0
    assert BillingOrder.query.count() == 0


@pytest.mark.parametrize(
    ("effective_to", "message"),
    [
        ("invalid", "--effective-to must be a valid"),
        ("2000-01-01", "--effective-to must be later than now"),
    ],
)
def test_manual_plan_invalid_period_rolls_back_new_creator_role(
    effective_to: str, message: str, billing_cli_db_app: Flask
) -> None:
    _seed_billing_cli_user(
        billing_cli_db_app,
        user_bid="teacher-test",
        identify="teacher@example.test",
        email="teacher@example.test",
    )
    db.session.add_all(build_bill_products(product_bids=["bill-product-plan-monthly"]))
    db.session.commit()
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=[
            "console",
            "billing",
            "grant-plan",
            "--identify",
            "teacher@example.test",
            "--product-bid",
            "bill-product-plan-monthly",
            "--effective-to",
            effective_to,
        ]
    )
    assert result.exit_code == 1
    assert message.lower() in result.output.lower()
    db.session.expire_all()
    assert load_user_aggregate("teacher-test").is_creator is False
    assert BillingOrder.query.count() == 0
    assert BillingSubscription.query.count() == 0


@pytest.mark.parametrize("failure", ["grant-rejected", "event-failure"])
def test_manual_plan_command_rolls_back_grant_and_role_and_does_not_send_sms(
    failure: str, billing_cli_db_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_billing_cli_user(
        billing_cli_db_app,
        user_bid="teacher-test",
        identify="teacher@example.test",
        email="teacher@example.test",
    )
    db.session.add_all(build_bill_products(product_bids=["bill-product-plan-monthly"]))
    db.session.commit()
    sender = Mock()
    monkeypatch.setattr(cli, "enqueue_subscription_purchase_sms", sender)
    if failure == "grant-rejected":
        original_grant = cli.grant_paid_order_credits

        def reject_after_grant(*args: object, **kwargs: object) -> bool:
            assert original_grant(*args, **kwargs)
            db.session.flush()
            assert CreditLedgerEntry.query.count() == 1
            return False

        monkeypatch.setattr(cli, "grant_paid_order_credits", reject_after_grant)
    else:
        monkeypatch.setattr(
            cli,
            "_enforce_manual_subscription_expire_event",
            Mock(side_effect=RuntimeError("event write failed")),
        )
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=[
            "console",
            "billing",
            "grant-plan",
            "--identify",
            "teacher@example.test",
            "--product-bid",
            "bill-product-plan-monthly",
        ]
    )
    assert result.exit_code == 1
    if failure == "grant-rejected":
        assert "did not create a new credit grant" in result.output
    else:
        assert str(result.exception) == "event write failed"
    db.session.expire_all()
    assert load_user_aggregate("teacher-test").is_creator is False
    assert BillingOrder.query.count() == 0
    assert BillingSubscription.query.count() == 0
    assert CreditWalletBucket.query.count() == 0
    assert CreditLedgerEntry.query.count() == 0
    sender.assert_not_called()


@pytest.mark.parametrize("command", ["activate", "validate", "retire", "inspect"])
def test_provider_price_command_reports_missing_mapping_as_operator_error(
    command: str, billing_cli_db_app: Flask
) -> None:
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=[
            "console",
            "billing",
            "provider-price",
            command,
            "--provider-price-bid",
            "absent",
        ]
    )
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "code" in result.output
    assert "mapping_not_found" in result.output


def test_provider_price_bind_missing_product_leaves_no_mapping(
    billing_cli_db_app: Flask,
) -> None:
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=[
            "console",
            "billing",
            "provider-price",
            "bind",
            "--product-bid",
            "absent",
            "--provider-account-id",
            "acct_test",
            "--provider-product-id",
            "prod_test",
            "--provider-price-id",
            "price_test",
        ]
    )
    assert result.exit_code == 1
    assert "product_not_found" in result.output


def test_rebuild_all_empty_aggregates_reports_noop_without_writes(
    billing_cli_db_app: Flask,
) -> None:
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=["console", "billing", "rebuild-daily-aggregates", "--all"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "status": "noop",
        "creator_bid": None,
        "shifu_bid": None,
        "date_from": None,
        "date_to": None,
        "day_count": 0,
    }


def test_run_renewal_command_reports_missing_target_without_creating_order(
    billing_cli_db_app: Flask,
) -> None:
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=["console", "billing", "run-renewal-event", "--creator-bid", "absent"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "event_not_found"
    assert BillingOrder.query.count() == 0


@pytest.mark.parametrize(
    ("auth_type", "eligible"),
    [
        ("", False),
        ("null", False),
        ('"edit"', True),
        ('" "', False),
        ('{"edit":true}', False),
        ("read,publish", True),
    ],
)
def test_authoring_backfill_parses_legacy_auth_and_keeps_dry_run_read_only(
    auth_type: str, eligible: bool, billing_cli_db_app: Flask
) -> None:
    _seed_billing_cli_user(
        billing_cli_db_app, user_bid="teacher-test", identify="teacher-test"
    )
    _seed_billing_cli_course_auth(
        auth_bid="auth-test",
        user_bid="teacher-test",
        course_bid="course-test",
        auth_types=[],
    )
    from flaskr.service.shifu.models import AiCourseAuth

    AiCourseAuth.query.one().auth_type = auth_type
    db.session.commit()
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=[
            "console",
            "billing",
            "backfill-authoring-permission-creators",
            "--course-bid",
            "course-test",
            "--user-bid",
            "teacher-test",
            "--dry-run",
        ]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["records"][0]["role_status"] == (
        "would_grant" if eligible else "skipped"
    )
    assert load_user_aggregate("teacher-test").is_creator is False
    assert BillingSubscription.query.count() == 0


def test_authoring_backfill_ignores_missing_users_and_limits_selected_auth_rows(
    billing_cli_db_app: Flask,
) -> None:
    _seed_billing_cli_course_auth(
        auth_bid="auth-missing",
        user_bid="missing",
        course_bid="course-test",
        auth_types=["edit"],
    )
    _seed_billing_cli_course_auth(
        auth_bid="auth-later",
        user_bid="later",
        course_bid="course-test",
        auth_types=["edit"],
    )
    db.session.commit()
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=[
            "console",
            "billing",
            "backfill-authoring-permission-creators",
            "--all",
            "--limit",
            "1",
        ]
    )
    assert result.exit_code == 0, result.output
    records = json.loads(result.output)["records"]
    assert len(records) == 1
    assert records[0]["creator_bid"] == "missing"
    assert records[0]["role_reason"] == "user_not_found"


def test_grant_plan_refuses_downgrade_without_mutating_current_subscription(
    billing_cli_db_app: Flask,
) -> None:
    _seed_billing_cli_user(
        billing_cli_db_app,
        user_bid="teacher-test",
        identify="teacher@example.test",
        email="teacher@example.test",
        is_creator=True,
    )
    products = build_bill_products(
        product_bids=["bill-product-plan-monthly", "bill-product-plan-yearly"]
    )
    products[0].sort_order = 1
    products[1].sort_order = 2
    subscription = BillingSubscription(
        subscription_bid="sub-active",
        creator_bid="teacher-test",
        product_bid=products[1].product_bid,
        billing_provider="manual",
        status=7202,
        current_period_start_at=now_utc(),
        current_period_end_at=now_utc() + timedelta(days=30),
    )
    db.session.add_all([*products, subscription])
    db.session.commit()
    result = billing_cli_db_app.test_cli_runner().invoke(
        args=[
            "console",
            "billing",
            "grant-plan",
            "--identify",
            "teacher@example.test",
            "--product-code",
            products[0].product_code,
        ]
    )
    assert result.exit_code == 1
    assert "only supports upgrades to a higher-tier plan" in result.output
    db.session.expire_all()
    assert subscription.product_bid == products[1].product_bid
    assert BillingOrder.query.count() == 0
