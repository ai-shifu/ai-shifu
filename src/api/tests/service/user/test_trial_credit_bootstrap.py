from __future__ import annotations

import importlib
import json
import uuid
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.framework.plugin import plugin_manager as plugin_manager_module
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_TRIAL_PRODUCT_BID,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
)
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.password_utils import hash_password
from flaskr.service.user.repository import (
    create_user_entity,
    set_password_hash,
    upsert_credential,
)
from flaskr.service.user.token_store import token_store
from flaskr.service.user.utils import generate_token
from tests.common.fixtures.bill_products import build_bill_products
from tests.common.fixtures.fake_redis import FakeRedis


def _load_user_route_handlers():
    common_module = importlib.import_module("flaskr.route.common")
    user_module = importlib.import_module("flaskr.route.user")
    return user_module.register_user_handler, common_module.register_common_handler


register_user_handler, register_common_handler = _load_user_route_handlers()


def _post_json(client, path: str, payload: dict, headers: dict | None = None):
    return client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
        headers=headers or {},
    )


@pytest.fixture
def user_trial_client(monkeypatch, tmp_path):
    import flaskr.service.billing.auth_hooks as _billing_auth_hooks  # noqa: F401
    from flaskr.service.user.auth.providers import password as _password_provider  # noqa: F401
    from flaskr.service.user.auth.providers import phone as _phone_provider  # noqa: F401
    import flaskr.service.user.email_flow as email_flow
    import flaskr.service.user.phone_flow as phone_flow
    import flaskr.service.user.utils as user_utils

    db_path = tmp_path / "user-trial.db"
    db_uri = f"sqlite:///{db_path}"
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI=db_uri,
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": db_uri,
            "ai_shifu_admin": db_uri,
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY="test-secret-key",
        TOKEN_EXPIRE_TIME=60 * 60,
        UNIVERSAL_VERIFICATION_CODE="9999",
        REDIS_KEY_PREFIX="test:",
        REDIS_KEY_PREFIX_USER="test:user:",
        REDIS_KEY_PREFIX_PHONE_CODE="test:phone:",
        REDIS_KEY_PREFIX_MAIL_CODE="test:mail:",
        REDIS_KEY_PREFIX_IP_BAN="test:ipban:",
        REDIS_KEY_PREFIX_IP_LIMIT="test:iplimit:",
        ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO=False,
        ENVERIMENT="prod",
        TZ="UTC",
    )

    dao.db.init_app(app)
    register_common_handler(app)
    register_user_handler(app, "/api/user")

    fake_redis = FakeRedis()
    monkeypatch.setattr(phone_flow, "redis", fake_redis, raising=False)
    monkeypatch.setattr(email_flow, "redis", fake_redis, raising=False)
    monkeypatch.setattr(user_utils, "redis", fake_redis, raising=False)
    monkeypatch.setattr(dao, "redis_client", fake_redis, raising=False)
    token_store._cache = fake_redis

    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()

    return app.test_client()


def _seed_registered_user(
    app,
    *,
    identifier: str,
    provider_name: str,
    subject_format: str,
    is_creator: bool,
) -> str:
    user_bid = uuid.uuid4().hex
    entity = create_user_entity(
        user_bid=user_bid,
        identify=identifier,
        nickname="Trial User",
        language="en-US",
        state=USER_STATE_REGISTERED,
    )
    entity.is_creator = 1 if is_creator else 0
    upsert_credential(
        app,
        user_bid=user_bid,
        provider_name=provider_name,
        subject_id=identifier,
        subject_format=subject_format,
        identifier=identifier,
        metadata={},
        verified=True,
    )
    dao.db.session.commit()
    return user_bid


def _assert_trial_bootstrapped(user_bid: str) -> None:
    wallet = CreditWallet.query.filter_by(creator_bid=user_bid, deleted=0).one()
    order = BillingOrder.query.filter_by(creator_bid=user_bid, deleted=0).one()
    subscription = BillingSubscription.query.filter_by(
        creator_bid=user_bid,
        deleted=0,
    ).one()
    ledgers = CreditLedgerEntry.query.filter_by(
        creator_bid=user_bid,
        deleted=0,
    ).all()

    assert wallet.available_credits == Decimal("100.0000000000")
    assert order.product_bid == BILLING_TRIAL_PRODUCT_BID
    assert order.payment_provider == "manual"
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert subscription.product_bid == BILLING_TRIAL_PRODUCT_BID
    assert subscription.billing_provider == "manual"
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert len(ledgers) == 1
    assert ledgers[0].entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT
    assert ledgers[0].source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION


def test_verify_sms_code_admin_login_bootstraps_trial_once(
    user_trial_client,
):
    app = user_trial_client.application
    app.config["ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO"] = True
    phone = f"155{uuid.uuid4().int % 100000000:08d}"

    first_response = _post_json(
        user_trial_client,
        "/api/user/verify_sms_code",
        {
            "mobile": phone,
            "sms_code": "9999",
            "login_context": "admin",
        },
    )
    second_response = _post_json(
        user_trial_client,
        "/api/user/verify_sms_code",
        {
            "mobile": phone,
            "sms_code": "9999",
            "login_context": "admin",
        },
    )

    assert first_response.status_code == 200
    assert first_response.get_json(force=True)["code"] == 0
    assert second_response.status_code == 200
    assert second_response.get_json(force=True)["code"] == 0

    with app.app_context():
        user = UserEntity.query.filter_by(user_identify=phone, deleted=0).first()
        assert user is not None
        assert user.is_creator == 1
        _assert_trial_bootstrapped(user.user_bid)
        assert (
            BillingOrder.query.filter_by(creator_bid=user.user_bid, deleted=0).count()
            == 1
        )


def test_ensure_admin_creator_bootstraps_trial_for_existing_user_once(
    user_trial_client,
):
    app = user_trial_client.application
    app.config["ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO"] = True
    email = f"{uuid.uuid4().hex[:10]}@example.com"

    with app.app_context():
        user_bid = _seed_registered_user(
            app,
            identifier=email,
            provider_name="email",
            subject_format="email",
            is_creator=False,
        )
        token = generate_token(app, user_bid)
        dao.db.session.commit()

    first_response = user_trial_client.post(
        "/api/user/ensure_admin_creator",
        headers={"Token": token},
    )
    second_response = user_trial_client.post(
        "/api/user/ensure_admin_creator",
        headers={"Token": token},
    )

    assert first_response.status_code == 200
    assert first_response.get_json(force=True)["code"] == 0
    assert second_response.status_code == 200
    assert second_response.get_json(force=True)["code"] == 0

    with app.app_context():
        user = UserEntity.query.filter_by(user_bid=user_bid, deleted=0).one()
        assert user.is_creator == 1
        _assert_trial_bootstrapped(user_bid)
        assert (
            BillingOrder.query.filter_by(creator_bid=user_bid, deleted=0).count() == 1
        )


def test_password_login_existing_creator_does_not_bootstrap_trial_again(
    user_trial_client,
):
    app = user_trial_client.application
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    password = "Abcd1234"

    with app.app_context():
        user_bid = _seed_registered_user(
            app,
            identifier=email,
            provider_name="email",
            subject_format="email",
            is_creator=True,
        )
        password_credential = upsert_credential(
            app,
            user_bid=user_bid,
            provider_name="password",
            subject_id=email,
            subject_format="email",
            identifier=email,
            metadata={},
            verified=True,
        )
        set_password_hash(password_credential, hash_password(password))
        dao.db.session.commit()

    response = _post_json(
        user_trial_client,
        "/api/user/login_password",
        {"identifier": email, "password": password},
    )

    assert response.status_code == 200
    assert response.get_json(force=True)["code"] == 0

    with app.app_context():
        assert (
            CreditWallet.query.filter_by(creator_bid=user_bid, deleted=0).count() == 0
        )
        assert (
            BillingOrder.query.filter_by(creator_bid=user_bid, deleted=0).count() == 0
        )
        assert (
            BillingSubscription.query.filter_by(creator_bid=user_bid, deleted=0).count()
            == 0
        )


def test_password_login_non_creator_does_not_grant_trial(
    user_trial_client,
):
    app = user_trial_client.application
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    password = "Abcd1234"

    with app.app_context():
        user_bid = _seed_registered_user(
            app,
            identifier=email,
            provider_name="email",
            subject_format="email",
            is_creator=False,
        )
        password_credential = upsert_credential(
            app,
            user_bid=user_bid,
            provider_name="password",
            subject_id=email,
            subject_format="email",
            identifier=email,
            metadata={},
            verified=True,
        )
        set_password_hash(password_credential, hash_password(password))
        dao.db.session.commit()

    response = _post_json(
        user_trial_client,
        "/api/user/login_password",
        {"identifier": email, "password": password},
    )

    assert response.status_code == 200
    assert response.get_json(force=True)["code"] == 0

    with app.app_context():
        assert (
            CreditWallet.query.filter_by(creator_bid=user_bid, deleted=0).count() == 0
        )
        assert (
            BillingOrder.query.filter_by(creator_bid=user_bid, deleted=0).count() == 0
        )


def test_post_auth_extension_failures_do_not_block_trial_bootstrap(
    user_trial_client,
):
    app = user_trial_client.application
    app.config["ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO"] = True
    email = f"{uuid.uuid4().hex[:10]}@example.com"

    with app.app_context():
        user_bid = _seed_registered_user(
            app,
            identifier=email,
            provider_name="email",
            subject_format="email",
            is_creator=False,
        )
        token = generate_token(app, user_bid)
        dao.db.session.commit()

    def _failing_post_auth_handler(_context, *, app):
        raise RuntimeError("boom")

    handlers = plugin_manager_module.plugin_manager.extension_functions.setdefault(
        "run_post_auth_extensions",
        [],
    )
    handlers.insert(0, _failing_post_auth_handler)
    try:
        response = user_trial_client.post(
            "/api/user/ensure_admin_creator",
            headers={"Token": token},
        )
    finally:
        handlers.remove(_failing_post_auth_handler)

    assert response.status_code == 200
    assert response.get_json(force=True)["code"] == 0

    with app.app_context():
        _assert_trial_bootstrapped(user_bid)
