from cryptography.fernet import Fernet

from flaskr.service.billing import customization
from flaskr.service.billing.entitlements import grant_creator_manual_entitlement
from flaskr.service.billing.models import BillingEntitlement
from flaskr.service.common.models import AppException
from flaskr.util.datetime import now_utc
from flaskr.dao import db
from flaskr.common.shifu_context import clear_shifu_context, set_shifu_context
from flaskr.service.user import user as user_service


def test_creator_integration_uses_encrypted_unified_config_and_versions(
    app, monkeypatch
):
    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)

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


def test_expired_custom_payment_never_falls_back_to_platform(app, monkeypatch):
    app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)
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


def test_creator_branding_reuses_unified_config(app, monkeypatch):
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
