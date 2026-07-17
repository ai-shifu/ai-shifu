from io import BytesIO
from importlib import import_module
from types import SimpleNamespace

from cryptography.fernet import Fernet
from PIL import Image
import pytest
from werkzeug.datastructures import FileStorage

from flaskr.service.billing import customization
from flaskr.service.billing.entitlements import grant_creator_manual_entitlement
from flaskr.service.billing.models import BillingEntitlement
from flaskr.service.common.models import AppException
from flaskr.util.datetime import now_utc
from flaskr.dao import db
from flaskr.common.shifu_context import clear_shifu_context, set_shifu_context
from flaskr.service.user import user as user_service


def _require_saas_config_plugin() -> None:
    try:
        import_module("flaskr.plugins.ai_shifu_saas_plugin")
    except ModuleNotFoundError as exc:
        if str(exc.name or "").startswith("flaskr.plugins.ai_shifu_saas_plugin"):
            pytest.skip("SaaS config plugin dependency is not installed")
        raise


def test_creator_integration_uses_encrypted_unified_config_and_versions(
    app, monkeypatch
):
    _require_saas_config_plugin()
    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)
    monkeypatch.setattr(
        customization, "_probe_provider_credentials", lambda *_args, **_kwargs: None
    )

    with app.app_context():
        grant_creator_manual_entitlement(
            app,
            "creator-custom-1",
            branding_enabled=True,
            custom_domain_enabled=True,
            custom_wechat_enabled=True,
            custom_payment_enabled=True,
        )

        draft = customization.save_creator_integration(
            app,
            "creator-custom-1",
            "stripe",
            {
                "public_config": {"publishable_key": "pk_test_owner"},
                "secret_config": {
                    "secret_key": "sk_test_owner",
                    "webhook_secret": "whsec_owner",
                },
            },
        )
        assert draft["status"] == "draft"
        assert draft["secret_configured"] is True
        assert "sk_test_owner" not in str(draft)

        verified = customization.verify_creator_integration(
            app,
            "creator-custom-1",
            "stripe",
            draft["integration_bid"],
        )
        assert verified["status"] == "verified"

        context = customization.resolve_provider_credential_context(
            app,
            creator_bid="creator-custom-1",
            provider="stripe",
        )
        assert context is not None
        assert context.integration_bid == draft["integration_bid"]
        assert context.secret_config["secret_key"] == "sk_test_owner"

        replacement = customization.save_creator_integration(
            app,
            "creator-custom-1",
            "stripe",
            {
                "public_config": {"publishable_key": "pk_test_owner_2"},
                "secret_config": {
                    "secret_key": "sk_test_owner_2",
                    "webhook_secret": "whsec_owner_2",
                },
            },
        )
        customization.verify_creator_integration(
            app, "creator-custom-1", "stripe", replacement["integration_bid"]
        )
        historic = customization.resolve_provider_credential_context(
            app,
            provider="stripe",
            callback_token=context.callback_token,
        )
        assert historic is not None
        assert historic.integration_bid == draft["integration_bid"]
        assert historic.secret_config["secret_key"] == "sk_test_owner"

        public_only_edit = customization.save_creator_integration(
            app,
            "creator-custom-1",
            "stripe",
            {
                "public_config": {"publishable_key": "pk_test_owner_3"},
                "secret_config": {},
            },
        )
        customization.verify_creator_integration(
            app,
            "creator-custom-1",
            "stripe",
            public_only_edit["integration_bid"],
        )
        edited_context = customization.resolve_provider_credential_context(
            app,
            creator_bid="creator-custom-1",
            provider="stripe",
        )
        assert edited_context is not None
        assert edited_context.public_config["publishable_key"] == "pk_test_owner_3"
        assert edited_context.secret_config["secret_key"] == "sk_test_owner_2"


def test_expired_custom_payment_never_falls_back_to_platform(app, monkeypatch):
    _require_saas_config_plugin()
    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)
    monkeypatch.setattr(
        customization, "_probe_provider_credentials", lambda *_args, **_kwargs: None
    )
    with app.app_context():
        grant_creator_manual_entitlement(
            app,
            "creator-expired-1",
            custom_payment_enabled=True,
        )
        draft = customization.save_creator_integration(
            app,
            "creator-expired-1",
            "stripe",
            {
                "public_config": {"publishable_key": "pk_expired"},
                "secret_config": {
                    "secret_key": "sk_expired",
                    "webhook_secret": "whsec_expired",
                },
            },
        )
        customization.verify_creator_integration(
            app, "creator-expired-1", "stripe", draft["integration_bid"]
        )
        entitlement = BillingEntitlement.query.filter_by(
            creator_bid="creator-expired-1", deleted=0
        ).first()
        entitlement.effective_to = now_utc()
        db.session.commit()

        try:
            customization.resolve_payment_integration_for_new_order(
                app, "creator-expired-1", "stripe"
            )
        except AppException:
            pass
        else:
            raise AssertionError("expired custom payment must block new checkout")


def test_callback_token_requires_valid_integration_secret_key(app):
    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = ""
    with pytest.raises(RuntimeError, match="CREATOR_INTEGRATION_ENCRYPTION_KEY"):
        customization._build_callback_token(app, "integration-1")

    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = "not-a-fernet-key"
    with pytest.raises(RuntimeError, match="CREATOR_INTEGRATION_ENCRYPTION_KEY"):
        customization._build_callback_token(app, "integration-1")

    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    token = customization._build_callback_token(app, "integration-1")
    assert token.startswith("integration-1.")


def test_stripe_credential_probe_rejects_fake_keys(app):
    app.config["TESTING"] = True

    with pytest.raises(ValueError, match="Stripe publishable key"):
        customization._probe_provider_credentials(
            app,
            "stripe",
            {"publishable_key": "fake-pk"},
            {"secret_key": "sk_test_valid", "webhook_secret": "whsec_valid"},
        )

    with pytest.raises(ValueError, match="Stripe secret key"):
        customization._probe_provider_credentials(
            app,
            "stripe",
            {"publishable_key": "pk_test_valid"},
            {"secret_key": "fake-sk", "webhook_secret": "whsec_valid"},
        )

    with pytest.raises(ValueError, match="Stripe webhook secret"):
        customization._probe_provider_credentials(
            app,
            "stripe",
            {"publishable_key": "pk_test_valid"},
            {"secret_key": "sk_test_valid", "webhook_secret": "fake-whsec"},
        )


def test_creator_integration_requires_encryption_key(app, monkeypatch):
    _require_saas_config_plugin()
    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = ""
    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)

    with app.app_context():
        grant_creator_manual_entitlement(
            app,
            "creator-missing-key",
            custom_payment_enabled=True,
        )

        with pytest.raises(RuntimeError, match="CREATOR_INTEGRATION_ENCRYPTION_KEY"):
            customization.save_creator_integration(
                app,
                "creator-missing-key",
                "stripe",
                {
                    "public_config": {"publishable_key": "pk_test_owner"},
                    "secret_config": {
                        "secret_key": "sk_test_owner",
                        "webhook_secret": "whsec_owner",
                    },
                },
            )


def test_creator_integration_probe_failure_does_not_activate(app, monkeypatch):
    _require_saas_config_plugin()
    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)

    with app.app_context():
        grant_creator_manual_entitlement(
            app,
            "creator-invalid-config",
            custom_payment_enabled=True,
        )
        draft = customization.save_creator_integration(
            app,
            "creator-invalid-config",
            "stripe",
            {
                "public_config": {"publishable_key": "not-a-publishable-key"},
                "secret_config": {
                    "secret_key": "not-a-secret-key",
                    "webhook_secret": "not-a-webhook-secret",
                },
            },
        )

        verified = customization.verify_creator_integration(
            app,
            "creator-invalid-config",
            "stripe",
            draft["integration_bid"],
        )

        assert verified["status"] == "failed"
        assert verified["last_error_code"] == "invalid_config"
        assert (
            customization.resolve_provider_credential_context(
                app, creator_bid="creator-invalid-config", provider="stripe"
            )
            is None
        )


def test_failed_integration_draft_keeps_existing_active_config(app, monkeypatch):
    _require_saas_config_plugin()
    app.config["TESTING"] = True
    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)

    with app.app_context():
        grant_creator_manual_entitlement(
            app,
            "creator-active-config",
            custom_payment_enabled=True,
        )
        current = customization.save_creator_integration(
            app,
            "creator-active-config",
            "stripe",
            {
                "public_config": {"publishable_key": "pk_test_current"},
                "secret_config": {
                    "secret_key": "sk_test_current",
                    "webhook_secret": "whsec_current",
                },
            },
        )
        assert (
            customization.verify_creator_integration(
                app,
                "creator-active-config",
                "stripe",
                current["integration_bid"],
            )["status"]
            == "verified"
        )
        funcs = customization._saas_funcs()
        active_key = customization.INTEGRATION_ACTIVE_KEY.format(provider="stripe")
        assert (
            funcs.get_sass_config("creator-active-config", active_key, default="")
            == current["integration_bid"]
        )
        assert (
            funcs.get_sass_config(
                "creator-active-config", "STRIPE_SECRET_KEY", default=""
            )
            == "sk_test_current"
        )

        invalid = customization.save_creator_integration(
            app,
            "creator-active-config",
            "stripe",
            {
                "public_config": {"publishable_key": "not-a-publishable-key"},
                "secret_config": {
                    "secret_key": "not-a-secret-key",
                    "webhook_secret": "not-a-webhook-secret",
                },
            },
        )
        assert invalid["status"] == "draft"
        assert (
            funcs.get_sass_config("creator-active-config", active_key, default="")
            == current["integration_bid"]
        )
        assert (
            funcs.get_sass_config(
                "creator-active-config", "STRIPE_SECRET_KEY", default=""
            )
            == "sk_test_current"
        )

        failed = customization.verify_creator_integration(
            app,
            "creator-active-config",
            "stripe",
            invalid["integration_bid"],
        )

        assert failed["status"] == "failed"
        assert (
            funcs.get_sass_config("creator-active-config", active_key, default="")
            == current["integration_bid"]
        )
        assert (
            funcs.get_sass_config(
                "creator-active-config", "STRIPE_PUBLISHABLE_KEY", default=""
            )
            == "pk_test_current"
        )
        assert (
            funcs.get_sass_config(
                "creator-active-config", "STRIPE_SECRET_KEY", default=""
            )
            == "sk_test_current"
        )
        context = customization.resolve_provider_credential_context(
            app, creator_bid="creator-active-config", provider="stripe"
        )
        assert context is not None
        assert context.integration_bid == current["integration_bid"]
        assert context.secret_config["secret_key"] == "sk_test_current"


def test_creator_branding_reuses_unified_config(app, monkeypatch):
    _require_saas_config_plugin()
    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)
    with app.app_context():
        grant_creator_manual_entitlement(
            app,
            "creator-brand-1",
            branding_enabled=True,
        )
        saved = customization.save_creator_branding(
            app,
            "creator-brand-1",
            {
                "logo_wide_url": "/storage/brand/wide.png",
                "logo_square_url": "/api/storage/brand/square.webp",
            },
        )
        assert saved == customization.resolve_creator_branding("creator-brand-1")


def test_creator_brand_logo_upload_uses_courses_oss_and_can_be_saved(app, monkeypatch):
    _require_saas_config_plugin()
    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)

    def fake_get_config(key, default=None):
        if key == "ALIBABA_CLOUD_OSS_COURSES_URL":
            return "https://courses-oss.example.com"
        if key == "ALIBABA_CLOUD_OSS_BASE_URL":
            return "https://default-oss.example.com"
        return default

    uploaded = {}

    def fake_upload_to_storage(_app, **kwargs):
        uploaded.update(kwargs)
        return SimpleNamespace(
            url=f"https://courses-oss.example.com/{kwargs['object_key']}",
        )

    monkeypatch.setattr(customization, "get_config", fake_get_config)
    monkeypatch.setattr(customization, "upload_to_storage", fake_upload_to_storage)

    with app.app_context():
        grant_creator_manual_entitlement(
            app,
            "creator-logo-1",
            branding_enabled=True,
        )
        logo = FileStorage(
            stream=BytesIO(b"\x89PNG\r\n\x1a\nlogo"),
            filename="wide.png",
            content_type="image/png",
        )
        url = customization.upload_creator_brand_logo(
            app,
            "creator-logo-1",
            logo,
        )
        saved = customization.save_creator_branding(
            app,
            "creator-logo-1",
            {"logo_wide_url": url, "logo_square_url": ""},
        )

        assert uploaded["profile"] == customization.OSS_PROFILE_COURSES
        assert uploaded["content_type"] == "image/png"
        assert uploaded["object_key"].startswith("creator-branding/creator-logo-1/")
        assert uploaded["object_key"].endswith(".png")
        assert saved["logo_wide_url"] == url


def test_unavailable_saas_plugin_keeps_optional_customization_reads_empty(
    app, monkeypatch
):
    def missing_plugin(name):
        if name.startswith("flaskr.plugins.ai_shifu_saas_plugin"):
            raise ModuleNotFoundError(name=name)
        return import_module(name)

    monkeypatch.setattr(customization, "import_module", missing_plugin)

    with app.app_context():
        assert customization.resolve_creator_branding("creator-without-plugin") == {
            "logo_wide_url": "",
            "logo_square_url": "",
        }
        assert (
            customization._active_version_bid(
                app,
                "creator-without-plugin",
                "stripe",
            )
            == ""
        )


def test_creator_brand_logo_upload_rejects_invalid_or_oversized_image(app, monkeypatch):
    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)
    with app.app_context():
        grant_creator_manual_entitlement(
            app,
            "creator-logo-invalid",
            branding_enabled=True,
        )
        invalid_contents = (
            b"not-a-png",
            b"\x89PNG\r\n\x1a\n" + b"x" * (customization._LOGO_MAX_BYTES + 1),
        )
        for content in invalid_contents:
            logo = FileStorage(
                stream=BytesIO(content),
                filename="wide.png",
                content_type="image/png",
            )
            try:
                customization.upload_creator_brand_logo(
                    app,
                    "creator-logo-invalid",
                    logo,
                )
            except AppException:
                pass
            else:
                raise AssertionError("invalid logo content must be rejected")


def test_creator_brand_logo_upload_normalizes_square_variant(app, monkeypatch):
    uploaded = {}

    def fake_upload_to_storage(_app, **kwargs):
        content = kwargs["file_content"].read()
        uploaded["content"] = content
        return type("UploadResult", (), {"url": "https://cdn.example.com/logo.png"})()

    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)
    monkeypatch.setattr(customization, "upload_to_storage", fake_upload_to_storage)

    with app.app_context():
        grant_creator_manual_entitlement(
            app,
            "creator-logo-square",
            branding_enabled=True,
        )
        image = Image.new("RGBA", (96, 48), (255, 0, 0, 255))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        logo = FileStorage(
            stream=buffer,
            filename="square.png",
            content_type="image/png",
        )
        customization.upload_creator_brand_logo(
            app,
            "creator-logo-square",
            logo,
            target="square",
        )

    with Image.open(BytesIO(uploaded["content"])) as normalized:
        assert normalized.size == (96, 96)


def test_creator_brand_logo_upload_preserves_wide_retina_variant(app, monkeypatch):
    uploaded = {}

    def fake_upload_to_storage(_app, **kwargs):
        content = kwargs["file_content"].read()
        uploaded["content"] = content
        return type("UploadResult", (), {"url": "https://cdn.example.com/logo.png"})()

    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)
    monkeypatch.setattr(customization, "upload_to_storage", fake_upload_to_storage)

    with app.app_context():
        grant_creator_manual_entitlement(
            app,
            "creator-logo-wide-retina",
            branding_enabled=True,
        )
        image = Image.new("RGBA", (440, 64), (0, 128, 255, 255))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        logo = FileStorage(
            stream=buffer,
            filename="wide.png",
            content_type="image/png",
        )
        customization.upload_creator_brand_logo(
            app,
            "creator-logo-wide-retina",
            logo,
            target="wide",
        )

    with Image.open(BytesIO(uploaded["content"])) as normalized:
        assert normalized.size == (440, 64)


def test_custom_wechat_identifiers_are_scoped_by_app_id(app, monkeypatch):
    set_shifu_context("shifu-1", "creator-wechat-1")
    monkeypatch.setattr(
        user_service,
        "resolve_creator_public_integrations",
        lambda creator_bid: {"wechat_oauth": {"app_id": "wx-owner-1"}},
    )
    try:
        assert user_service._wechat_identifiers(app, "openid-1", "unionid-1") == (
            "wx-owner-1:openid-1",
            "wx-owner-1:unionid-1",
        )
    finally:
        clear_shifu_context()


def test_custom_wechat_identifiers_fail_when_integration_resolution_fails(
    app, monkeypatch
):
    set_shifu_context("shifu-1", "creator-wechat-broken")
    monkeypatch.setattr(
        user_service,
        "resolve_creator_public_integrations",
        lambda creator_bid: (_ for _ in ()).throw(RuntimeError("resolver failed")),
    )
    try:
        with pytest.raises(RuntimeError, match="resolver failed"):
            user_service._wechat_identifiers(app, "openid-1", "unionid-1")
    finally:
        clear_shifu_context()


def test_custom_wechat_identifiers_require_custom_app_id(app, monkeypatch):
    set_shifu_context("shifu-1", "creator-wechat-missing-app")
    monkeypatch.setattr(
        user_service,
        "resolve_creator_public_integrations",
        lambda creator_bid: {"wechat_oauth": {"app_id": ""}},
    )
    try:
        with pytest.raises(RuntimeError, match="missing app_id"):
            user_service._wechat_identifiers(app, "openid-1", "unionid-1")
    finally:
        clear_shifu_context()
