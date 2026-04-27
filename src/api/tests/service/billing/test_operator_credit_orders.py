from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Flask

import flaskr.dao as dao
from flaskr.i18n import load_translations
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_TOPUP,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.dtos import (
    OperatorCreditOrderDetailDTO,
    OperatorCreditOrdersPageDTO,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    CreditLedgerEntry,
)
from flaskr.service.billing.read_models import (
    build_operator_credit_orders_page,
    get_operator_credit_order_detail,
)
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
from tests.common.fixtures.bill_products import build_bill_products


def _build_app() -> Flask:
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
    )
    dao.db.init_app(app)
    load_translations(app)
    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(build_bill_products())
        dao.db.session.add_all(
            [
                UserEntity(
                    user_bid="creator-1",
                    user_identify="creator1@example.com",
                    nickname="Creator One",
                ),
                UserEntity(
                    user_bid="creator-2",
                    user_identify="13800138000",
                    nickname="Creator Two",
                ),
            ]
        )
        dao.db.session.add_all(
            [
                AuthCredential(
                    credential_bid="cred-1-email",
                    user_bid="creator-1",
                    provider_name="email",
                    subject_id="creator1@example.com",
                    subject_format="email",
                    identifier="creator1@example.com",
                ),
                AuthCredential(
                    credential_bid="cred-2-phone",
                    user_bid="creator-2",
                    provider_name="phone",
                    subject_id="13800138000",
                    subject_format="phone",
                    identifier="13800138000",
                ),
            ]
        )
        dao.db.session.add_all(
            [
                BillingOrder(
                    bill_order_bid="bill-order-topup-1",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_TOPUP,
                    product_bid="bill-product-topup-small",
                    subscription_bid="",
                    currency="CNY",
                    payable_amount=19900,
                    paid_amount=19900,
                    payment_provider="pingxx",
                    channel="alipay_qr",
                    provider_reference_id="charge_topup_1",
                    status=BILLING_ORDER_STATUS_PAID,
                    paid_at=datetime(2026, 4, 27, 10, 0, 0),
                    created_at=datetime(2026, 4, 27, 9, 0, 0),
                    metadata_json={"checkout_type": "topup"},
                ),
                BillingOrder(
                    bill_order_bid="bill-order-plan-1",
                    creator_bid="creator-2",
                    order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                    product_bid="bill-product-plan-yearly",
                    subscription_bid="sub-1",
                    currency="CNY",
                    payable_amount=99900,
                    paid_amount=0,
                    payment_provider="stripe",
                    channel="checkout_session",
                    provider_reference_id="cs_plan_1",
                    status=BILLING_ORDER_STATUS_FAILED,
                    failure_code="card_declined",
                    failure_message="Card was declined",
                    failed_at=datetime(2026, 4, 26, 11, 0, 0),
                    created_at=datetime(2026, 4, 26, 10, 0, 0),
                ),
            ]
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-grant-topup-1",
                creator_bid="creator-1",
                wallet_bid="wallet-1",
                wallet_bucket_bid="bucket-1",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_TOPUP,
                source_bid="bill-order-topup-1",
                idempotency_key="grant:bill-order-topup-1",
                amount=Decimal("20.0000000000"),
                balance_after=Decimal("20.0000000000"),
                consumable_from=datetime(2026, 4, 27, 10, 0, 0),
                expires_at=datetime(2026, 5, 27, 10, 0, 0),
            )
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-grant-plan-1",
                creator_bid="creator-2",
                wallet_bid="wallet-2",
                wallet_bucket_bid="bucket-2",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-order-plan-1",
                idempotency_key="grant:bill-order-plan-1",
                amount=Decimal("22000.0000000000"),
                balance_after=Decimal("22000.0000000000"),
                consumable_from=datetime(2026, 4, 26, 10, 0, 0),
                expires_at=datetime(2027, 4, 26, 10, 0, 0),
            )
        )
        dao.db.session.commit()
    return app


def test_build_operator_credit_orders_page_returns_operator_view():
    app = _build_app()

    result = build_operator_credit_orders_page(
        app,
        creator_keyword="creator1@example.com",
        credit_order_kind="topup",
        payment_provider="pingxx",
        page_index=1,
        page_size=20,
    )

    assert isinstance(result, OperatorCreditOrdersPageDTO)
    assert result.total == 1
    assert result.items[0].bill_order_bid == "bill-order-topup-1"
    assert result.items[0].creator_email == "creator1@example.com"
    assert result.items[0].credit_order_kind == "topup"
    assert result.items[0].product_code == "creator-topup-small"
    assert result.items[0].product_name_key == (
        "module.billing.catalog.topups.creatorSmall.title"
    )
    assert result.items[0].credit_amount == 20
    assert result.items[0].valid_to is not None


def test_build_operator_credit_orders_page_supports_product_keyword_search():
    app = _build_app()

    result = build_operator_credit_orders_page(
        app,
        product_keyword="20 积分包",
        page_index=1,
        page_size=20,
    )

    assert result.total == 1
    assert result.items[0].bill_order_bid == "bill-order-topup-1"


def test_build_operator_credit_orders_page_keeps_orders_for_deleted_products():
    app = _build_app()

    with app.app_context():
        product_ref = (
            BillingProduct.query.filter(
                BillingProduct.product_bid == "bill-product-topup-small"
            )
            .order_by(BillingProduct.id.desc())
            .first()
        )
        assert product_ref is not None
        product_ref.deleted = 1
        dao.db.session.commit()

    result = build_operator_credit_orders_page(
        app,
        credit_order_kind="topup",
        page_index=1,
        page_size=20,
    )

    assert result.total == 1
    assert result.items[0].bill_order_bid == "bill-order-topup-1"
    assert result.items[0].product_code == "creator-topup-small"


def test_get_operator_credit_order_detail_returns_grant_and_metadata():
    app = _build_app()

    detail = get_operator_credit_order_detail(
        app,
        bill_order_bid="bill-order-topup-1",
    )

    assert isinstance(detail, OperatorCreditOrderDetailDTO)
    assert detail.order.bill_order_bid == "bill-order-topup-1"
    assert detail.order.creator_nickname == "Creator One"
    assert detail.metadata == {"checkout_type": "topup"}
    assert detail.grant is not None
    assert detail.grant.source_type == "topup"
    assert detail.grant.granted_credits == 20
    assert detail.grant.valid_from is not None
