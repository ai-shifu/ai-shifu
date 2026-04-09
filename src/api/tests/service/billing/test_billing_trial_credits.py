from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace
import types

from flask import Flask, jsonify, request
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_CONFIG_KEY_NEW_CREATOR_TRIAL_CONFIG,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_GIFT,
)
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppException
from flaskr.service.user.consts import CREDENTIAL_STATE_VERIFIED, USER_STATE_REGISTERED
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.repository import create_user_entity

_API_ROOT = Path(__file__).resolve().parents[3]
_ROUTE_DIR = _API_ROOT / "flaskr" / "route"
_BILLING_ROUTE_FILE = _API_ROOT / "flaskr" / "service" / "billing" / "routes.py"


def _load_register_billing_routes():
    package_name = "flaskr.route"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(_ROUTE_DIR)]
        sys.modules[package_name] = package

    common_name = f"{package_name}.common"
    if common_name not in sys.modules:
        common_spec = importlib.util.spec_from_file_location(
            common_name,
            _ROUTE_DIR / "common.py",
        )
        assert common_spec is not None and common_spec.loader is not None
        common_module = importlib.util.module_from_spec(common_spec)
        sys.modules[common_name] = common_module
        common_spec.loader.exec_module(common_module)

    full_name = "flaskr.service.billing.routes"
    if full_name in sys.modules:
        return sys.modules[full_name].register_billing_routes

    spec = importlib.util.spec_from_file_location(full_name, _BILLING_ROUTE_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module.register_billing_routes


register_billing_routes = _load_register_billing_routes()


def _build_trial_config(
    *,
    enabled: int = 1,
    eligible_registered_after: str = "",
) -> str:
    return json.dumps(
        {
            "enabled": enabled,
            "program_code": "new_creator_v1",
            "credit_amount": "100.0000000000",
            "valid_days": 15,
            "eligible_registered_after": eligible_registered_after,
            "grant_trigger": "billing_overview",
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _seed_creator(
    *,
    user_bid: str,
    credential_specs: list[dict[str, object]],
) -> None:
    entity = create_user_entity(
        user_bid=user_bid,
        identify="creator@example.com",
        nickname="Creator",
        language="en-US",
        avatar="",
        state=USER_STATE_REGISTERED,
    )
    entity.is_creator = 1
    dao.db.session.flush()

    for index, spec in enumerate(credential_specs, start=1):
        created_at = spec["created_at"]
        assert isinstance(created_at, datetime)
        dao.db.session.add(
            AuthCredential(
                credential_bid=f"credential-{user_bid}-{index}",
                user_bid=user_bid,
                provider_name=str(spec.get("provider_name") or "email"),
                subject_id=str(spec.get("identifier") or f"{user_bid}-{index}"),
                subject_format="email",
                identifier=str(spec.get("identifier") or f"{user_bid}-{index}"),
                raw_profile='{"provider":"email","metadata":{}}',
                state=int(spec.get("state") or CREDENTIAL_STATE_VERIFIED),
                deleted=0,
                created_at=created_at,
                updated_at=created_at,
            )
        )

    dao.db.session.commit()


@pytest.fixture
def trial_billing_client():
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

    @app.errorhandler(AppException)
    def _handle_app_exception(error: AppException):
        response = jsonify({"code": error.code, "message": error.message})
        response.status_code = 200
        return response

    @app.before_request
    def _inject_request_user() -> None:
        request.user = SimpleNamespace(
            user_id=request.headers.get("X-User-Id", "creator-trial"),
            language="en-US",
            is_creator=request.headers.get("X-Creator", "1") == "1",
        )

    register_billing_routes(app=app)

    with app.app_context():
        dao.db.create_all()

    return app.test_client()


def test_billing_overview_grants_new_creator_trial_once(
    trial_billing_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = trial_billing_client.application
    monkeypatch.setattr(
        "flaskr.service.billing.funcs.get_config",
        lambda key, default=None: (
            _build_trial_config(eligible_registered_after="2026-04-05T00:00:00Z")
            if key == BILLING_CONFIG_KEY_NEW_CREATOR_TRIAL_CONFIG
            else default
        ),
    )

    with app.app_context():
        _seed_creator(
            user_bid="creator-trial",
            credential_specs=[
                {
                    "provider_name": "email",
                    "identifier": "creator@example.com",
                    "created_at": datetime(2026, 4, 8, 12, 0, 0),
                }
            ],
        )

    first_payload = trial_billing_client.get("/api/billing/overview").get_json(
        force=True
    )
    second_payload = trial_billing_client.get("/api/billing/overview").get_json(
        force=True
    )

    assert first_payload["code"] == 0
    assert first_payload["data"]["wallet"]["available_credits"] == 100
    assert first_payload["data"]["trial_offer"]["status"] == "granted"
    assert first_payload["data"]["trial_offer"]["granted_at"] is not None
    assert first_payload["data"]["trial_offer"]["expires_at"] is not None

    assert second_payload["code"] == 0
    assert second_payload["data"]["wallet"]["available_credits"] == 100
    assert second_payload["data"]["trial_offer"]["status"] == "granted"

    with app.app_context():
        wallet = CreditWallet.query.filter_by(creator_bid="creator-trial").one()
        buckets = CreditWalletBucket.query.filter_by(creator_bid="creator-trial").all()
        ledgers = CreditLedgerEntry.query.filter_by(creator_bid="creator-trial").all()

        assert wallet.available_credits == 100
        assert wallet.lifetime_granted_credits == 100
        assert len(buckets) == 1
        assert buckets[0].bucket_category == CREDIT_BUCKET_CATEGORY_FREE
        assert buckets[0].source_type == CREDIT_SOURCE_TYPE_GIFT
        assert buckets[0].source_bid == "new_creator_v1"
        assert len(ledgers) == 1
        assert ledgers[0].entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT
        assert ledgers[0].source_type == CREDIT_SOURCE_TYPE_GIFT
        assert ledgers[0].idempotency_key == "trial:new_creator_v1:creator-trial"


def test_billing_overview_does_not_grant_when_cutoff_missing(
    trial_billing_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = trial_billing_client.application
    monkeypatch.setattr(
        "flaskr.service.billing.funcs.get_config",
        lambda key, default=None: (
            _build_trial_config()
            if key == BILLING_CONFIG_KEY_NEW_CREATOR_TRIAL_CONFIG
            else default
        ),
    )

    with app.app_context():
        _seed_creator(
            user_bid="creator-trial",
            credential_specs=[
                {
                    "provider_name": "email",
                    "identifier": "creator@example.com",
                    "created_at": datetime(2026, 4, 8, 12, 0, 0),
                }
            ],
        )

    payload = trial_billing_client.get("/api/billing/overview").get_json(force=True)

    assert payload["code"] == 0
    assert payload["data"]["wallet"]["available_credits"] == 0
    assert payload["data"]["trial_offer"]["enabled"] is True
    assert payload["data"]["trial_offer"]["status"] == "ineligible"
    assert payload["data"]["trial_offer"]["granted_at"] is None

    with app.app_context():
        assert (
            CreditWalletBucket.query.filter_by(creator_bid="creator-trial").count() == 0
        )
        assert (
            CreditLedgerEntry.query.filter_by(creator_bid="creator-trial").count() == 0
        )


def test_billing_overview_uses_earliest_verified_credential_for_cutoff(
    trial_billing_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = trial_billing_client.application
    monkeypatch.setattr(
        "flaskr.service.billing.funcs.get_config",
        lambda key, default=None: (
            _build_trial_config(eligible_registered_after="2026-04-05T00:00:00Z")
            if key == BILLING_CONFIG_KEY_NEW_CREATOR_TRIAL_CONFIG
            else default
        ),
    )

    with app.app_context():
        _seed_creator(
            user_bid="creator-trial",
            credential_specs=[
                {
                    "provider_name": "google",
                    "identifier": "creator-google@example.com",
                    "created_at": datetime(2026, 4, 1, 9, 0, 0),
                },
                {
                    "provider_name": "email",
                    "identifier": "creator@example.com",
                    "created_at": datetime(2026, 4, 8, 9, 0, 0),
                },
            ],
        )

    payload = trial_billing_client.get("/api/billing/overview").get_json(force=True)

    assert payload["code"] == 0
    assert payload["data"]["wallet"]["available_credits"] == 0
    assert payload["data"]["trial_offer"]["status"] == "ineligible"

    with app.app_context():
        assert (
            CreditLedgerEntry.query.filter_by(creator_bid="creator-trial").count() == 0
        )
