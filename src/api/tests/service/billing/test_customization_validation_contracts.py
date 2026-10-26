"""Exercise customization drafts and credential validation without SaaS storage."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import stripe
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from flask import Flask
from flaskr.service.billing import customization
from flaskr.service.common import contact_identifiers
from flaskr.service.common.models import AppError


@pytest.fixture(scope="module")
def credential_material() -> tuple[str, str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        .decode()
    )
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "customization.test")])
    start = datetime(2025, 1, 1, tzinfo=UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(start)
        .not_valid_after(start + timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    return (
        private,
        public,
        certificate.public_bytes(serialization.Encoding.PEM).decode(),
    )


@pytest.mark.parametrize("provider", ["pingxx", "alipay", "wechatpay", "wechat_oauth"])
@pytest.mark.parametrize("bare_base64", [False, True])
def test_provider_credentials_accept_valid_pem_and_bare_base64(
    provider: str, bare_base64: bool, credential_material: tuple[str, str, str]
) -> None:
    private, public, certificate = credential_material
    if bare_base64:
        private, public, certificate = (
            "".join(value.splitlines()[1:-1]) for value in credential_material
        )
    secret = {
        "private_key": private,
        "webhook_public_key": public,
        "app_private_key": private,
        "alipay_public_key": public,
        "platform_cert": certificate,
        "api_v3_key": "a" * 32,
    }
    customization._probe_provider_credentials(Flask(__name__), provider, {}, secret)


@pytest.mark.parametrize("provider", ["pingxx", "alipay", "wechatpay"])
def test_invalid_private_keys_fail_before_activation(provider: str) -> None:
    with pytest.raises(ValueError, match="Private key is not a valid PEM key"):
        customization._probe_provider_credentials(
            Flask(__name__),
            provider,
            {},
            {"api_v3_key": "a" * 32, "private_key": "eA==", "app_private_key": "eA=="},
        )


@pytest.mark.parametrize(
    ("parser_name", "expected"),
    [
        ("_parse_pem_public_key", "Public key is not a valid PEM key"),
        ("_parse_x509_certificate", "Certificate is not a valid PEM certificate"),
    ],
)
def test_invalid_public_credential_material_is_rejected(
    parser_name: str, expected: str
) -> None:
    with pytest.raises(ValueError, match=expected):
        getattr(customization, parser_name)("eA==")


@pytest.mark.parametrize(
    ("value", "error"),
    [("", "Private Key is required"), ("not base64!", "not valid PEM or base64")],
)
def test_invalid_pem_encoding_reports_a_configuration_error(
    value: str, error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        customization._normalize_pem(value, "PRIVATE KEY")


@pytest.mark.parametrize("key", ["a" * 31, "a" * 33, "中" * 32])
def test_wechat_api_key_length_is_measured_in_bytes(key: str) -> None:
    with pytest.raises(ValueError, match="must be 32 bytes"):
        customization._probe_provider_credentials(
            Flask(__name__), "wechatpay", {}, {"api_v3_key": key}
        )


def test_unknown_provider_cannot_be_verified() -> None:
    with pytest.raises(ValueError, match="Unsupported integration provider"):
        customization._probe_provider_credentials(Flask(__name__), "unknown", {}, {})


@pytest.mark.parametrize("api_version", ["", "2025-01-27.acacia"])
def test_stripe_probe_scopes_credentials_to_the_account_request(
    api_version: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    retrieve = Mock(return_value={"id": "account-test"})
    monkeypatch.setattr(stripe.Account, "retrieve", retrieve)
    customization._probe_provider_credentials(
        Flask(__name__),
        "stripe",
        {"publishable_key": "pk_test_custom", "api_version": api_version},
        {"secret_key": "sk_test_custom", "webhook_secret": "whsec_custom"},
    )
    expected = {"api_key": "sk_test_custom"}
    if api_version:
        expected["stripe_version"] = api_version
    retrieve.assert_called_once_with(**expected)


def test_stripe_probe_wraps_provider_error_without_exposing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("authentication failed")
    monkeypatch.setattr(stripe.Account, "retrieve", Mock(side_effect=failure))
    with pytest.raises(
        ValueError, match="Stripe credentials could not be verified"
    ) as raised:
        customization._probe_stripe_credentials(
            Flask(__name__),
            {"publishable_key": "pk_live_custom"},
            {"secret_key": "sk_live_custom", "webhook_secret": "whsec_custom"},
        )
    assert raised.value.__cause__ is failure
    assert "sk_live_custom" not in str(raised.value)


def test_callback_tokens_are_bound_to_the_integration_and_server_key() -> None:
    app = Flask(__name__)
    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    token = customization._build_callback_token(app, "integration-test")
    assert customization._verify_callback_token(app, token) == "integration-test"
    for invalid in [
        "",
        ".signature",
        "integration-test",
        token.replace("integration-test", "another-integration"),
        token + "x",
    ]:
        with pytest.raises(AppError):
            customization._verify_callback_token(app, invalid)
    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    with pytest.raises(AppError):
        customization._verify_callback_token(app, token)


@pytest.fixture
def draft_storage(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    funcs = SimpleNamespace(
        SaasUserConfigCreateDTO=SimpleNamespace,
        create_or_update_saas_user_config=Mock(),
        get_sass_config=Mock(return_value="{}"),
        soft_delete_saas_user_config=Mock(),
    )
    monkeypatch.setattr(customization, "_saas_funcs", lambda **_kwargs: funcs)
    return funcs


def test_admin_draft_round_trip_normalizes_supported_fields_and_encrypts_storage(
    draft_storage: SimpleNamespace,
) -> None:
    app = Flask(__name__)
    payload = {
        "branding_enabled": "yes",
        "custom_domain_enabled": True,
        "custom_wechat_enabled": "off",
        "custom_payment_enabled": "1",
        "config_status": " IN_PROGRESS ",
        "note": "x" * 600,
        "branding": {
            "logo_wide_url": "/storage/logo.png",
            "logo_square_url": "/api/storage/square.webp",
            "favicon_url": "/storage/favicon.ico",
            "home_url": "https://course.example.test",
        },
        "domain": {"host": " course.example.test "},
        "integrations": {
            "stripe": {
                "public_config": {
                    "publishable_key": " pk_test_customer ",
                    "currency": "usd",
                },
                "secret_config": {
                    "secret_key": " sk_test_customer ",
                    "webhook_secret": "whsec_customer",
                },
            }
        },
    }
    saved = customization.save_admin_creator_customization_draft(
        app,
        creator_bid=" creator-test ",
        creator_mobile=" admin@example.test ",
        payload=payload,
    )
    dto = draft_storage.create_or_update_saas_user_config.call_args.args[1]
    assert dto.user_bid == "creator-test"
    assert dto.key == "CUSTOMIZATION.ADMIN_DRAFT.CREATOR"
    assert dto.is_encrypted == 1
    assert saved["creator_mobile"] == "admin@example.test"
    assert saved["branding_enabled"] is True
    assert saved["custom_payment_enabled"] is True
    assert saved["custom_wechat_enabled"] is False
    assert saved["config_status"] == "in_progress"
    assert saved["note"] == "x" * 500
    assert saved["domain"] == {"host": "course.example.test"}
    assert (
        saved["integrations"]["stripe"]["secret_config"]["secret_key"]
        == "sk_test_customer"
    )
    assert saved["integrations"]["wechatpay"] == {
        "public_config": {},
        "secret_config": {},
    }
    draft_storage.get_sass_config.return_value = dto.value
    assert (
        customization.build_admin_creator_customization_draft(
            app, creator_bid="creator-test"
        )
        == saved
    )
    assert json.loads(dto.value) == saved
    customization.clear_admin_creator_customization_draft(
        app, creator_bid="creator-test"
    )
    draft_storage.soft_delete_saas_user_config.assert_called_once_with(
        app, user_bid="creator-test", key="CUSTOMIZATION.ADMIN_DRAFT.CREATOR"
    )


def test_contact_drafts_use_case_normalized_opaque_storage_identity(
    draft_storage: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        contact_identifiers, "get_config", lambda _key, _default="": "google,email"
    )
    app = Flask(__name__)
    for contact in [" Teacher@Example.Test ", "teacher@example.test"]:
        customization.save_admin_creator_customization_draft(
            app, creator_mobile=contact, payload={}
        )
    dtos = [
        call.args[1]
        for call in draft_storage.create_or_update_saas_user_config.call_args_list
    ]
    assert dtos[0].user_bid == dtos[1].user_bid
    assert len(dtos[0].user_bid) == 36
    assert dtos[0].key == "CUSTOMIZATION.ADMIN_DRAFT.MOBILE"
    assert "teacher" not in dtos[0].user_bid
    assert (
        customization._admin_draft_owner_bid(creator_bid=" creator-test ")
        == "billing-admin-draft:creator:creator-test"
    )
    assert "teacher" not in customization._admin_draft_owner_bid(
        creator_mobile="teacher@example.test"
    )


def test_draft_autosave_tolerates_partial_home_url_and_unknown_status(
    draft_storage: SimpleNamespace,
) -> None:
    del draft_storage
    saved = customization.save_admin_creator_customization_draft(
        Flask(__name__),
        creator_bid="creator-test",
        payload={"config_status": "unknown", "branding": {"home_url": "https://"}},
    )
    assert saved["config_status"] == "pending"
    assert saved["branding"]["home_url"] == ""


def test_optional_saas_storage_does_not_block_draft_editing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(customization, "_saas_funcs", lambda **_kwargs: None)
    app = Flask(__name__)
    result = customization.build_admin_creator_customization_draft(
        app, creator_bid="creator-test", creator_mobile="contact@example.test"
    )
    assert result["creator_mobile"] == "contact@example.test"
    assert result["config_status"] == "pending"
    saved = customization.save_admin_creator_customization_draft(
        app, creator_bid="creator-test", payload={"note": "unsaved locally"}
    )
    assert saved["note"] == "unsaved locally"
    customization.clear_admin_creator_customization_draft(app)
    customization.clear_admin_creator_customization_draft(
        app, creator_bid="creator-test"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("public_config", []),
        ("secret_config", None),
        ("public_config", {"secret_key": "should-not-be-public"}),
        ("secret_config", {"unknown": "disallowed"}),
    ],
)
def test_draft_rejects_fields_outside_provider_allowlist(
    field: str, value: object, draft_storage: SimpleNamespace
) -> None:
    payload = {
        "integrations": {
            "stripe": {"public_config": {}, "secret_config": {}, field: value}
        }
    }
    with pytest.raises(AppError):
        customization.save_admin_creator_customization_draft(
            Flask(__name__), creator_bid="creator-test", payload=payload
        )
    draft_storage.create_or_update_saas_user_config.assert_not_called()


@pytest.mark.parametrize(
    "value",
    [
        "https://untrusted.example.test/logo.png",
        "/storage/logo.svg",
        "/storage/logo.exe",
    ],
)
def test_draft_rejects_unmanaged_logo_sources(
    value: str, draft_storage: SimpleNamespace
) -> None:
    with pytest.raises(AppError):
        customization.save_admin_creator_customization_draft(
            Flask(__name__),
            creator_bid="creator-test",
            payload={"branding": {"logo_wide_url": value}},
        )
    draft_storage.create_or_update_saas_user_config.assert_not_called()
