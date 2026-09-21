"""Verify integration versioning against the optional SaaS storage boundary."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet
from flask import Flask
from flaskr.service.billing import customization
from flaskr.service.common.models import AppError


@pytest.fixture
def integration_store(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Provide only the external plugin port; keep billing lifecycle code real."""
    rows: dict[str, dict] = {}
    configs: dict[tuple, str] = {}
    app = Flask(__name__)
    app.testing = True
    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

    def create_version(_app: Flask, **values: object) -> None:
        assert values["is_encrypted"] is True
        rows[values["config_bid"]] = dict(values)

    def update_version(_app: Flask, **values: object) -> None:
        assert values["is_encrypted"] is True
        rows[values["config_bid"]].update(values)

    def create_config(_app: Flask, dto: SimpleNamespace) -> None:
        configs[(dto.user_bid, dto.key)] = dto.value

    def latest(creator: str, provider: str) -> str:
        bids = [
            bid
            for bid, row in rows.items()
            if row["user_bid"] == creator
            and row["key"]
            == customization.INTEGRATION_VERSION_KEY.format(provider=provider)
        ]
        if not bids:
            message = "No integration version"
            raise AppError(message, 9999)
        return bids[-1]

    funcs = SimpleNamespace(
        SaasUserConfigCreateDTO=SimpleNamespace,
        create_versioned_saas_user_config=create_version,
        update_saas_user_config_version=update_version,
        create_or_update_saas_user_config=create_config,
        get_sass_config=lambda user, key, default="": configs.get((user, key), default),
        get_saas_user_config_value_by_bid=lambda _app, bid: rows.get(bid, {}).get(
            "value"
        ),
        soft_delete_saas_user_config=lambda _app, user, key: configs.pop(
            (user, key), None
        ),
    )
    monkeypatch.setattr(customization, "_saas_funcs", lambda **_kwargs: funcs)
    monkeypatch.setattr(customization, "_latest_version_bid", latest)
    monkeypatch.setattr(
        customization,
        "_config_owner_bid",
        lambda bid: rows.get(bid, {}).get("user_bid", ""),
    )
    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)
    monkeypatch.setattr(
        customization,
        "resolve_creator_entitlement_state",
        lambda _creator: SimpleNamespace(
            custom_payment_enabled=True, custom_wechat_enabled=True
        ),
    )
    monkeypatch.setattr(
        customization,
        "get_config",
        lambda name, default=None: (
            "https://service.example.test" if name == "HOST_URL" else default
        ),
    )
    return SimpleNamespace(app=app, rows=rows, configs=configs)


def _save(store: SimpleNamespace, *, public_only: bool = False) -> dict:
    return customization.save_creator_integration(
        store.app,
        "teacher-test",
        "stripe",
        {
            "public_config": {
                "publishable_key": "pk_test_new" if public_only else "pk_test_original",
                "alipay_enabled": True,
            },
            "secret_config": {}
            if public_only
            else {"secret_key": "sk_test_only", "webhook_secret": "whsec_test_only"},
        },
    )


def test_new_integration_version_preserves_secrets_and_old_callback_identity(
    integration_store: SimpleNamespace,
) -> None:
    store = integration_store
    first = _save(store)
    assert (
        customization.verify_creator_integration(
            store.app, "teacher-test", "stripe", first["integration_bid"]
        )["status"]
        == "verified"
    )
    first_context = customization.resolve_provider_credential_context(
        store.app, creator_bid="teacher-test", provider="stripe"
    )
    second = _save(store, public_only=True)
    assert second["integration_bid"] != first["integration_bid"]
    assert second["secret_configured_fields"] == ["secret_key", "webhook_secret"]
    assert "sk_test_only" not in str(second)
    assert (
        customization.verify_creator_integration(
            store.app, "teacher-test", "stripe", second["integration_bid"]
        )["status"]
        == "verified"
    )
    context = customization.resolve_payment_integration_for_new_order(
        store.app, "teacher-test", "stripe"
    )
    assert context.integration_bid == second["integration_bid"]
    assert context.secret_config["secret_key"] == "sk_test_only"
    assert context.public_config["publishable_key"] == "pk_test_new"
    assert store.configs[("teacher-test", "STRIPE_ALIPAY_ENABLED")] == "true"
    old = customization.resolve_provider_credential_context(
        store.app, provider="stripe", callback_token=first_context.callback_token
    )
    assert old.integration_bid == first["integration_bid"]
    assert old.public_config["publishable_key"] == "pk_test_original"


@pytest.mark.parametrize("failure", ["missing-config", "provider"])
def test_failed_verification_does_not_replace_the_active_integration(
    failure: str,
    integration_store: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = integration_store
    first = _save(store)
    customization.verify_creator_integration(
        store.app, "teacher-test", "stripe", first["integration_bid"]
    )
    second = _save(store, public_only=True)
    if failure == "missing-config":
        row = store.rows[second["integration_bid"]]
        payload = json.loads(row["value"])
        payload["secret_config"] = {}
        row["value"] = json.dumps(payload)
    else:
        monkeypatch.setattr(
            customization,
            "_probe_provider_credentials",
            Mock(side_effect=ValueError("Provider could not verify account")),
        )
    result = customization.verify_creator_integration(
        store.app, "teacher-test", "stripe", second["integration_bid"]
    )
    assert result["status"] == "failed"
    assert result["last_error_code"] == "invalid_config"
    assert "sk_test_only" not in str(result)
    active = customization.resolve_provider_credential_context(
        store.app, creator_bid="teacher-test", provider="stripe"
    )
    assert active.integration_bid == first["integration_bid"]
    assert (
        json.loads(store.rows[second["integration_bid"]]["value"])["status"] == "failed"
    )


def test_disable_removes_active_pointer_but_retains_signed_historical_callback(
    integration_store: SimpleNamespace,
) -> None:
    store = integration_store
    saved = _save(store)
    customization.verify_creator_integration(
        store.app, "teacher-test", "stripe", saved["integration_bid"]
    )
    context = customization.resolve_provider_credential_context(
        store.app, creator_bid="teacher-test", provider="stripe"
    )
    result = customization.disable_creator_integration(
        store.app, "teacher-test", "stripe"
    )
    assert result["status"] == "disabled"
    assert (
        customization.resolve_provider_credential_context(
            store.app, creator_bid="teacher-test", provider="stripe"
        )
        is None
    )
    historic = customization.resolve_provider_credential_context(
        store.app, provider="stripe", callback_token=context.callback_token
    )
    assert historic.integration_bid == saved["integration_bid"]
    assert len(store.rows) == 1
    with pytest.raises(AppError):
        customization.disable_creator_integration(store.app, "teacher-test", "stripe")


@pytest.mark.parametrize("mismatch", ["provider", "owner", "record-owner"])
def test_credential_context_never_crosses_account_or_provider_boundary(
    mismatch: str, integration_store: SimpleNamespace
) -> None:
    store = integration_store
    saved = _save(store)
    provider = "alipay" if mismatch == "provider" else "stripe"
    creator = "other-teacher" if mismatch == "owner" else "teacher-test"
    if mismatch == "record-owner":
        row = store.rows[saved["integration_bid"]]
        payload = json.loads(row["value"])
        payload["creator_bid"] = "other-teacher"
        row["value"] = json.dumps(payload)
    assert (
        customization.resolve_provider_credential_context(
            store.app,
            creator_bid=creator,
            provider=provider,
            integration_bid=saved["integration_bid"],
        )
        is None
    )


@pytest.mark.parametrize("operation", ["save", "verify", "payment"])
def test_integration_entry_points_reject_unsupported_provider(
    operation: str, integration_store: SimpleNamespace
) -> None:
    app = integration_store.app
    callback = {
        "save": lambda: customization.save_creator_integration(
            app, "teacher-test", "unknown", {}
        ),
        "verify": lambda: customization.verify_creator_integration(
            app, "teacher-test", "unknown"
        ),
        "payment": lambda: customization.resolve_payment_integration_for_new_order(
            app, "teacher-test", "wechat_oauth"
        ),
    }[operation]
    with pytest.raises(AppError):
        callback()
    assert integration_store.rows == {}


@pytest.mark.parametrize("feature_enabled", [False, True])
def test_existing_custom_payment_configuration_never_silently_falls_back_to_platform(
    feature_enabled: bool,
    integration_store: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = integration_store
    saved = _save(store)
    customization.verify_creator_integration(
        store.app, "teacher-test", "stripe", saved["integration_bid"]
    )
    monkeypatch.setattr(
        customization, "is_creator_customization_enabled", lambda: feature_enabled
    )
    if feature_enabled:
        store.configs.pop(
            (
                "teacher-test",
                customization.INTEGRATION_ACTIVE_KEY.format(provider="stripe"),
            )
        )
    with pytest.raises(AppError):
        customization.resolve_payment_integration_for_new_order(
            store.app, "teacher-test", "stripe"
        )
