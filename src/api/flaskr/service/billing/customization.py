"""Course-owner customization backed by the SaaS unified config table."""

from __future__ import annotations

from io import BytesIO
from dataclasses import dataclass
import base64
import binascii
import hashlib
import hmac
from importlib import import_module
import json
from typing import Any
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from flask import Flask
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from flaskr.service.common.oss_utils import OSS_PROFILE_COURSES
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.storage import upload_to_storage
from flaskr.service.config.funcs import get_config
from flaskr.util.datetime import now_utc, to_utc_iso
from flaskr.util.uuid import generate_id

from .domains import build_creator_domain_bindings
from .entitlements import (
    grant_creator_manual_entitlement,
    resolve_creator_entitlement_state,
    serialize_creator_entitlements,
)
from .primitives import normalize_bid

BRANDING_KEY = "CUSTOMIZATION.BRANDING"
ADMIN_DRAFT_KEY = "CUSTOMIZATION.ADMIN_DRAFT"
INTEGRATION_ACTIVE_KEY = "CUSTOMIZATION.INTEGRATION.{provider}.ACTIVE"
INTEGRATION_VERSION_KEY = "CUSTOMIZATION.INTEGRATION.{provider}.VERSION"
INTEGRATION_PROVIDERS = (
    "wechat_oauth",
    "pingxx",
    "stripe",
    "alipay",
    "wechatpay",
)
PAYMENT_PROVIDERS = set(INTEGRATION_PROVIDERS) - {"wechat_oauth"}

_PROVIDER_CONFIG_KEYS = {
    "wechat_oauth": {
        "public": {"app_id": "WECHAT_APP_ID"},
        "secret": {"app_secret": "WECHAT_APP_SECRET"},
    },
    "pingxx": {
        "public": {"app_id": "PINGXX_APP_ID"},
        "secret": {
            "secret_key": "PINGXX_SECRET_KEY",
            "private_key": "PINGXX_PRIVATE_KEY",
            "webhook_public_key": "PINGXX_WEBHOOK_PUBLIC_KEY",
        },
    },
    "stripe": {
        "public": {
            "publishable_key": "STRIPE_PUBLISHABLE_KEY",
            "api_version": "STRIPE_API_VERSION",
            "currency": "STRIPE_DEFAULT_CURRENCY",
            "alipay_enabled": "STRIPE_ALIPAY_ENABLED",
            "wechatpay_enabled": "STRIPE_WECHAT_PAY_ENABLED",
        },
        "secret": {
            "secret_key": "STRIPE_SECRET_KEY",
            "webhook_secret": "STRIPE_WEBHOOK_SECRET",
        },
    },
    "alipay": {
        "public": {"app_id": "ALIPAY_APP_ID", "gateway_url": "ALIPAY_GATEWAY_URL"},
        "secret": {
            "app_private_key": "ALIPAY_APP_PRIVATE_KEY",
            "alipay_public_key": "ALIPAY_PUBLIC_KEY",
        },
    },
    "wechatpay": {
        "public": {
            "app_id": "WECHATPAY_APP_ID",
            "mch_id": "WECHATPAY_MCH_ID",
            "merchant_serial_no": "WECHATPAY_MERCHANT_SERIAL_NO",
            "base_url": "WECHATPAY_BASE_URL",
        },
        "secret": {
            "api_v3_key": "WECHATPAY_API_V3_KEY",
            "private_key": "WECHATPAY_PRIVATE_KEY",
            "platform_cert": "WECHATPAY_PLATFORM_CERT",
        },
    },
}

_PROVIDER_FIELDS = {
    "wechat_oauth": ({"app_id"}, {"app_secret"}),
    "pingxx": (
        {"app_id"},
        {"secret_key", "private_key", "webhook_public_key"},
    ),
    "stripe": ({"publishable_key"}, {"secret_key", "webhook_secret"}),
    "alipay": ({"app_id"}, {"app_private_key", "alipay_public_key"}),
    "wechatpay": (
        {"app_id", "mch_id", "merchant_serial_no"},
        {"api_v3_key", "private_key", "platform_cert"},
    ),
}
_OPTIONAL_PUBLIC_FIELDS = {
    "pingxx": {"channels"},
    "stripe": {"api_version", "currency", "alipay_enabled", "wechatpay_enabled"},
    "alipay": {"gateway_url"},
    "wechatpay": {"base_url"},
}
_LOGO_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_LOGO_MAX_BYTES = 2 * 1024 * 1024
_LOGO_MAX_PIXELS = 12_000_000
_LOGO_VARIANTS = {"wide", "square"}
_LOGO_WIDE_CSS_SIZE = (220, 32)
_LOGO_SQUARE_CSS_SIZE = (32, 32)
_LOGO_MAX_DEVICE_SCALE = 3
_LOGO_WIDE_MAX_SIZE = (
    _LOGO_WIDE_CSS_SIZE[0] * _LOGO_MAX_DEVICE_SCALE,
    _LOGO_WIDE_CSS_SIZE[1] * _LOGO_MAX_DEVICE_SCALE,
)
_LOGO_SQUARE_MAX_SIZE = (
    _LOGO_SQUARE_CSS_SIZE[0] * _LOGO_MAX_DEVICE_SCALE,
    _LOGO_SQUARE_CSS_SIZE[1] * _LOGO_MAX_DEVICE_SCALE,
)


@dataclass(slots=True, frozen=True)
class ProviderCredentialContext:
    integration_bid: str
    creator_bid: str
    provider: str
    public_config: dict[str, Any]
    secret_config: dict[str, Any]
    callback_token: str


def is_creator_customization_enabled() -> bool:
    return _to_bool(get_config("CREATOR_CUSTOMIZATION_ENABLED", False))


def build_creator_customization(
    app: Flask,
    creator_bid: str,
    *,
    force_enabled: bool = False,
) -> dict[str, Any]:
    creator_bid = normalize_bid(creator_bid)
    with app.app_context():
        entitlement = resolve_creator_entitlement_state(creator_bid)
        return {
            "enabled": force_enabled or is_creator_customization_enabled(),
            "creator_bid": creator_bid,
            "capabilities": build_customization_capabilities(
                entitlement,
                force_enabled=force_enabled,
            ),
            "entitlements": serialize_creator_entitlements(entitlement).__json__(),
            "branding": resolve_creator_branding(creator_bid),
            "domains": build_creator_domain_bindings(app, creator_bid).__json__(),
            "integrations": [
                _serialize_active_integration(app, creator_bid, provider)
                for provider in INTEGRATION_PROVIDERS
            ],
        }


def build_admin_creator_customization_draft(
    app: Flask,
    *,
    creator_bid: str = "",
    creator_mobile: str = "",
) -> dict[str, Any]:
    owner_bid = _admin_draft_owner_bid(
        creator_bid=creator_bid,
        creator_mobile=creator_mobile,
    )
    with app.app_context():
        value = _saas_funcs(required=False)
        if value is None:
            return _empty_admin_creator_customization_draft(
                creator_mobile=creator_mobile
            )
        payload = _load_json(
            value.get_sass_config(owner_bid, ADMIN_DRAFT_KEY, default="{}")
        )
        return _normalize_admin_creator_customization_draft(
            payload,
            creator_mobile=creator_mobile,
        )


def save_admin_creator_customization_draft(
    app: Flask,
    *,
    creator_bid: str = "",
    creator_mobile: str = "",
    payload: dict[str, Any],
) -> dict[str, Any]:
    owner_bid = _admin_draft_owner_bid(
        creator_bid=creator_bid,
        creator_mobile=creator_mobile,
    )
    normalized = _normalize_admin_creator_customization_draft(
        payload,
        creator_mobile=creator_mobile,
    )
    with app.app_context():
        funcs = _saas_funcs(required=False)
        if funcs is None:
            return normalized
        funcs.create_or_update_saas_user_config(
            app,
            funcs.SaasUserConfigCreateDTO(
                user_bid=owner_bid,
                key=ADMIN_DRAFT_KEY,
                value=_dump_json(normalized),
                is_encrypted=1,
                remark="Admin billing customization draft",
            ),
        )
    return normalized


def clear_admin_creator_customization_draft(
    app: Flask,
    *,
    creator_bid: str = "",
    creator_mobile: str = "",
) -> None:
    if not normalize_bid(creator_bid) and not str(creator_mobile or "").strip():
        return
    owner_bid = _admin_draft_owner_bid(
        creator_bid=creator_bid,
        creator_mobile=creator_mobile,
    )
    funcs = _saas_funcs(required=False)
    if funcs is None:
        return
    with app.app_context():
        funcs.soft_delete_saas_user_config(
            app,
            user_bid=owner_bid,
            key=ADMIN_DRAFT_KEY,
        )


def upload_admin_creator_draft_logo(
    app: Flask,
    *,
    creator_bid: str = "",
    creator_mobile: str = "",
    file: FileStorage,
    target: str = "wide",
) -> str:
    owner_bid = _admin_draft_owner_bid(
        creator_bid=creator_bid,
        creator_mobile=creator_mobile,
    )
    normalized_target = _normalize_logo_target(target)
    filename = str(file.filename or "").strip()
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    expected_content_type = _LOGO_CONTENT_TYPES.get(suffix)
    content = file.stream.read(_LOGO_MAX_BYTES + 1)
    if (
        expected_content_type is None
        or not content
        or len(content) > _LOGO_MAX_BYTES
        or _detect_logo_content_type(content) != expected_content_type
    ):
        raise_param_error("file")

    normalized_content = _normalize_logo_image(
        content,
        suffix=suffix,
        target=normalized_target,
    )
    result = upload_to_storage(
        app,
        file_content=BytesIO(normalized_content),
        object_key=f"creator-branding-drafts/{owner_bid}/{generate_id(app)}{suffix}",
        content_type=expected_content_type,
        profile=OSS_PROFILE_COURSES,
        warm_up=False,
    )
    return result.url


def build_customization_capabilities(
    entitlement,
    *,
    force_enabled: bool = False,
) -> dict[str, bool]:
    enabled = force_enabled or is_creator_customization_enabled()
    return {
        "branding": enabled and bool(entitlement.branding_enabled),
        "custom_domain": enabled and bool(entitlement.custom_domain_enabled),
        "custom_wechat": enabled and bool(entitlement.custom_wechat_enabled),
        "custom_payment": enabled and bool(entitlement.custom_payment_enabled),
    }


def upload_creator_brand_logo(
    app: Flask,
    creator_bid: str,
    file: FileStorage,
    target: str = "wide",
    *,
    allow_when_customization_disabled: bool = False,
) -> str:
    """Validate and upload a course-owner logo through managed storage."""

    creator_bid = normalize_bid(creator_bid)
    normalized_target = _normalize_logo_target(target)
    with app.app_context():
        entitlement = resolve_creator_entitlement_state(creator_bid)
        _require_capability(
            entitlement.branding_enabled,
            allow_when_customization_disabled=allow_when_customization_disabled,
        )

        filename = str(file.filename or "").strip()
        suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        expected_content_type = _LOGO_CONTENT_TYPES.get(suffix)
        content = file.stream.read(_LOGO_MAX_BYTES + 1)
        if (
            expected_content_type is None
            or not content
            or len(content) > _LOGO_MAX_BYTES
            or _detect_logo_content_type(content) != expected_content_type
        ):
            raise_param_error("file")

        normalized_content = _normalize_logo_image(
            content,
            suffix=suffix,
            target=normalized_target,
        )

        result = upload_to_storage(
            app,
            file_content=BytesIO(normalized_content),
            object_key=(f"creator-branding/{creator_bid}/{generate_id(app)}{suffix}"),
            content_type=expected_content_type,
            profile=OSS_PROFILE_COURSES,
            warm_up=False,
        )
        return result.url


def save_creator_branding(
    app: Flask,
    creator_bid: str,
    payload: dict[str, Any],
    *,
    allow_when_customization_disabled: bool = False,
) -> dict[str, str]:
    creator_bid = normalize_bid(creator_bid)
    with app.app_context():
        entitlement = resolve_creator_entitlement_state(creator_bid)
        _require_capability(
            entitlement.branding_enabled,
            allow_when_customization_disabled=allow_when_customization_disabled,
        )
        value = {
            "logo_wide_url": _normalize_logo_url(
                payload.get("logo_wide_url"), "logo_wide_url"
            ),
            "logo_square_url": _normalize_logo_url(
                payload.get("logo_square_url"), "logo_square_url"
            ),
        }
        funcs = _saas_funcs(required=False)
        if funcs is None:
            grant_creator_manual_entitlement(
                app,
                creator_bid,
                branding_enabled=entitlement.branding_enabled,
                custom_domain_enabled=entitlement.custom_domain_enabled,
                custom_wechat_enabled=entitlement.custom_wechat_enabled,
                custom_payment_enabled=entitlement.custom_payment_enabled,
                branding=value,
            )
            return value

        funcs.create_or_update_saas_user_config(
            app,
            funcs.SaasUserConfigCreateDTO(
                user_bid=creator_bid,
                key=BRANDING_KEY,
                value=_dump_json(value),
                is_encrypted=0,
                remark="Course-owner brand profile",
            ),
        )
        return value


def save_creator_integration(
    app: Flask,
    creator_bid: str,
    provider: str,
    payload: dict[str, Any],
    *,
    allow_when_customization_disabled: bool = False,
) -> dict[str, Any]:
    creator_bid = normalize_bid(creator_bid)
    provider = _normalize_provider(provider)
    with app.app_context():
        entitlement = resolve_creator_entitlement_state(creator_bid)
        _require_capability(
            entitlement.custom_wechat_enabled
            if provider == "wechat_oauth"
            else entitlement.custom_payment_enabled,
            allow_when_customization_disabled=allow_when_customization_disabled,
        )
        public_config = _normalize_config(provider, payload.get("public_config"), False)
        secret_config = _normalize_config(provider, payload.get("secret_config"), True)
        previous_record = _load_active_record(creator_bid, provider)
        if previous_record:
            previous_secret_config = dict(previous_record.get("secret_config") or {})
            if previous_secret_config:
                secret_config = {**previous_secret_config, **secret_config}
        integration_bid = generate_id(app)
        record = {
            "integration_bid": integration_bid,
            "provider": provider,
            "status": "draft",
            "public_config": public_config,
            "secret_config": secret_config,
            "callback_token": _build_callback_token(app, integration_bid),
            "verified_at": None,
            "last_error_code": "",
            "last_error_message": "",
        }
        _saas_funcs().create_versioned_saas_user_config(
            app,
            user_bid=creator_bid,
            key=INTEGRATION_VERSION_KEY.format(provider=provider),
            value=_dump_json(record),
            is_encrypted=True,
            remark=f"Course-owner {provider} integration version",
            updated_by=creator_bid,
            config_bid=integration_bid,
        )
        return _serialize_integration(app, creator_bid, record)


def verify_creator_integration(
    app: Flask, creator_bid: str, provider: str, integration_bid: str = ""
) -> dict[str, Any]:
    creator_bid = normalize_bid(creator_bid)
    provider = _normalize_provider(provider)
    with app.app_context():
        record = _load_integration_record(
            app,
            integration_bid or _latest_version_bid(app, creator_bid, provider),
            expected_creator_bid=creator_bid,
            expected_provider=provider,
        )
        public_config = dict(record.get("public_config") or {})
        secret_config = dict(record.get("secret_config") or {})
        try:
            _validate_required_config(provider, public_config, secret_config)
            _probe_provider_credentials(app, provider, public_config, secret_config)
        except ValueError as exc:
            record.update(
                status="failed",
                last_error_code="invalid_config",
                last_error_message=str(exc)[:255],
            )
            _save_integration_record(app, record)
            return _serialize_integration(app, creator_bid, record)

        record.update(
            status="verified",
            verified_at=to_utc_iso(now_utc()),
            last_error_code="",
            last_error_message="",
        )
        _save_integration_record(app, record)
        funcs = _saas_funcs()
        funcs.create_or_update_saas_user_config(
            app,
            funcs.SaasUserConfigCreateDTO(
                user_bid=creator_bid,
                key=INTEGRATION_ACTIVE_KEY.format(provider=provider),
                value=record["integration_bid"],
                is_encrypted=0,
                remark=f"Active course-owner {provider} integration",
            ),
        )
        _activate_provider_config(app, creator_bid, provider, record)
        return _serialize_integration(app, creator_bid, record)


def disable_creator_integration(
    app: Flask, creator_bid: str, provider: str
) -> dict[str, Any]:
    creator_bid = normalize_bid(creator_bid)
    provider = _normalize_provider(provider)
    with app.app_context():
        active_bid = _active_version_bid(app, creator_bid, provider)
        if not active_bid:
            raise_param_error("provider")
        record = _load_integration_record(
            app,
            active_bid,
            expected_creator_bid=creator_bid,
            expected_provider=provider,
        )
        record["status"] = "disabled"
        _save_integration_record(app, record)
        _saas_funcs().soft_delete_saas_user_config(
            app,
            creator_bid,
            INTEGRATION_ACTIVE_KEY.format(provider=provider),
        )
        return _serialize_integration(app, creator_bid, record)


def resolve_creator_branding(creator_bid: str) -> dict[str, str]:
    funcs = _saas_funcs(required=False)
    if funcs is None:
        return _resolve_entitlement_branding(creator_bid)
    value = funcs.get_sass_config(
        normalize_bid(creator_bid), BRANDING_KEY, default="{}"
    )
    payload = _load_json(value)
    resolved = {
        "logo_wide_url": str(payload.get("logo_wide_url") or ""),
        "logo_square_url": str(payload.get("logo_square_url") or ""),
    }
    if resolved["logo_wide_url"] or resolved["logo_square_url"]:
        return resolved
    return _resolve_entitlement_branding(creator_bid)


def _resolve_entitlement_branding(creator_bid: str) -> dict[str, str]:
    entitlement = resolve_creator_entitlement_state(creator_bid)
    feature_payload = entitlement.feature_payload.to_metadata_json()
    branding_payload = feature_payload.get("branding")
    branding = branding_payload if isinstance(branding_payload, dict) else {}
    return {
        "logo_wide_url": str(branding.get("logo_wide_url") or ""),
        "logo_square_url": str(branding.get("logo_square_url") or ""),
    }


def resolve_creator_public_integrations(creator_bid: str) -> dict[str, dict[str, Any]]:
    result = {}
    for provider in INTEGRATION_PROVIDERS:
        record = _load_active_record(creator_bid, provider)
        if record and record.get("status") == "verified":
            result[provider] = dict(record.get("public_config") or {})
    return result


def resolve_provider_credential_context(
    app: Flask,
    *,
    creator_bid: str = "",
    provider: str = "",
    integration_bid: str = "",
    callback_token: str = "",
) -> ProviderCredentialContext | None:
    with app.app_context():
        if callback_token:
            integration_bid = _verify_callback_token(app, callback_token)
        if not integration_bid:
            integration_bid = _active_version_bid(
                app, normalize_bid(creator_bid), _normalize_provider(provider)
            )
        if not integration_bid:
            return None
        record = _load_integration_record(app, integration_bid)
        if provider and record.get("provider") != _normalize_provider(provider):
            return None
        if creator_bid and record.get("creator_bid") not in {None, "", creator_bid}:
            return None
        owner_bid = _config_owner_bid(integration_bid)
        if creator_bid and owner_bid != normalize_bid(creator_bid):
            return None
        return ProviderCredentialContext(
            integration_bid=integration_bid,
            creator_bid=owner_bid,
            provider=str(record["provider"]),
            public_config=dict(record.get("public_config") or {}),
            secret_config=dict(record.get("secret_config") or {}),
            callback_token=str(record.get("callback_token") or ""),
        )


def resolve_payment_integration_for_new_order(
    app: Flask, creator_bid: str, provider: str
) -> ProviderCredentialContext | None:
    """Resolve an eligible active merchant config or preserve global behavior."""

    creator_bid = normalize_bid(creator_bid)
    provider = _normalize_provider(provider)
    if provider not in PAYMENT_PROVIDERS:
        raise_param_error("provider")
    entitlement = resolve_creator_entitlement_state(creator_bid)
    customization_enabled = is_creator_customization_enabled()
    if not customization_enabled or not entitlement.custom_payment_enabled:
        if _has_any_active_payment_integration(app, creator_bid):
            raise_error("server.pay.payChannelNotSupport")
        return None
    context = resolve_provider_credential_context(
        app, creator_bid=creator_bid, provider=provider
    )
    if context is None:
        raise_error("server.pay.payChannelNotSupport")
    return context


def _has_any_active_payment_integration(app: Flask, creator_bid: str) -> bool:
    return any(
        _active_version_bid(app, creator_bid, provider)
        for provider in PAYMENT_PROVIDERS
    )


def build_provider_config_overrides(
    context: ProviderCredentialContext,
) -> dict[str, Any]:
    mapping = _PROVIDER_CONFIG_KEYS[context.provider]
    values: dict[str, Any] = {}
    for section, source in (
        ("public", context.public_config),
        ("secret", context.secret_config),
    ):
        for source_key, config_key in mapping[section].items():
            if source_key in source:
                values[config_key] = source[source_key]
    return values


def _serialize_active_integration(
    app: Flask, creator_bid: str, provider: str
) -> dict[str, Any]:
    record = _load_active_record(creator_bid, provider)
    if record is None:
        return {
            "provider": provider,
            "status": "unconfigured",
            "public_config": {},
            "secret_configured": False,
            "callback_url": "",
        }
    return _serialize_integration(app, creator_bid, record)


def _serialize_integration(
    app: Flask, creator_bid: str, record: dict[str, Any]
) -> dict[str, Any]:
    callback_url = ""
    if record.get("provider") in PAYMENT_PROVIDERS:
        origin = str(get_config("HOST_URL", "") or "").rstrip("/")
        if origin:
            callback_url = (
                f"{origin}/api/order/webhooks/{record['provider']}/"
                f"{record.get('callback_token', '')}"
            )
    return {
        "integration_bid": record.get("integration_bid", ""),
        "provider": record.get("provider", ""),
        "status": record.get("status", "draft"),
        "public_config": dict(record.get("public_config") or {}),
        "secret_configured": bool(record.get("secret_config")),
        "callback_url": callback_url,
        "verified_at": record.get("verified_at"),
        "last_error_code": record.get("last_error_code", ""),
        "last_error_message": record.get("last_error_message", ""),
    }


def _load_active_record(creator_bid: str, provider: str) -> dict[str, Any] | None:
    from flask import current_app

    integration_bid = _active_version_bid(current_app, creator_bid, provider)
    if not integration_bid:
        return None
    return _load_integration_record(
        current_app,
        integration_bid,
        expected_creator_bid=creator_bid,
        expected_provider=provider,
    )


def _active_version_bid(app: Flask, creator_bid: str, provider: str) -> str:
    funcs = _saas_funcs(required=False)
    if funcs is None:
        return ""
    return str(
        funcs.get_sass_config(
            creator_bid,
            INTEGRATION_ACTIVE_KEY.format(provider=provider),
            default="",
        )
        or ""
    ).strip()


def _latest_version_bid(app: Flask, creator_bid: str, provider: str) -> str:
    model = _saas_model()
    row = (
        model.query.filter(
            model.user_bid == creator_bid,
            model.key == INTEGRATION_VERSION_KEY.format(provider=provider),
            model.deleted == 0,
        )
        .order_by(model.created_at.desc(), model.id.desc())
        .first()
    )
    if row is None:
        raise_param_error("provider")
    return str(row.config_bid)


def _load_integration_record(
    app: Flask,
    integration_bid: str,
    *,
    expected_creator_bid: str = "",
    expected_provider: str = "",
) -> dict[str, Any]:
    value = _saas_funcs().get_saas_user_config_value_by_bid(app, integration_bid)
    if value is None:
        raise_param_error("integration_bid")
    record = _load_json(value)
    if expected_provider and record.get("provider") != expected_provider:
        raise_param_error("provider")
    if (
        expected_creator_bid
        and _config_owner_bid(integration_bid) != expected_creator_bid
    ):
        raise_error("server.shifu.noPermission")
    return record


def _save_integration_record(app: Flask, record: dict[str, Any]) -> None:
    _saas_funcs().update_saas_user_config_version(
        app,
        config_bid=str(record["integration_bid"]),
        value=_dump_json(record),
        is_encrypted=True,
    )


def _activate_provider_config(
    app: Flask, creator_bid: str, provider: str, record: dict[str, Any]
) -> None:
    funcs = _saas_funcs()
    for section, encrypted in (("public", 0), ("secret", 1)):
        source = dict(record.get(f"{section}_config") or {})
        for source_key, config_key in _PROVIDER_CONFIG_KEYS[provider][section].items():
            if source_key not in source:
                continue
            value = source[source_key]
            if isinstance(value, bool):
                value = "true" if value else "false"
            funcs.create_or_update_saas_user_config(
                app,
                funcs.SaasUserConfigCreateDTO(
                    user_bid=creator_bid,
                    key=config_key,
                    value=str(value),
                    is_encrypted=encrypted,
                    remark=f"Active {provider} course-owner config",
                ),
            )
    if provider in {"alipay", "wechatpay"}:
        origin = str(get_config("HOST_URL", "") or "").rstrip("/")
        if origin:
            callback_key = (
                "ALIPAY_WEBHOOK_URL"
                if provider == "alipay"
                else "WECHATPAY_WEBHOOK_URL"
            )
            callback_url = (
                f"{origin}/api/order/webhooks/{provider}/"
                f"{record.get('callback_token', '')}"
            )
            funcs.create_or_update_saas_user_config(
                app,
                funcs.SaasUserConfigCreateDTO(
                    user_bid=creator_bid,
                    key=callback_key,
                    value=callback_url,
                    is_encrypted=0,
                    remark=f"Active {provider} webhook URL",
                ),
            )


def _probe_provider_credentials(
    app: Flask,
    provider: str,
    public_config: dict[str, Any],
    secret_config: dict[str, Any],
) -> None:
    """Validate credentials before promoting an integration to active use."""
    if provider == "stripe":
        _probe_stripe_credentials(app, public_config, secret_config)
        return
    if provider == "pingxx":
        _parse_pem_private_key(secret_config.get("private_key"))
        _parse_pem_public_key(secret_config.get("webhook_public_key"))
        return
    if provider == "alipay":
        _parse_pem_private_key(secret_config.get("app_private_key"))
        _parse_pem_public_key(secret_config.get("alipay_public_key"))
        return
    if provider == "wechatpay":
        api_v3_key = str(secret_config.get("api_v3_key") or "").strip()
        if len(api_v3_key.encode("utf-8")) != 32:
            raise ValueError("WeChat Pay API v3 key must be 32 bytes")
        _parse_pem_private_key(secret_config.get("private_key"))
        _parse_x509_certificate(secret_config.get("platform_cert"))
        return
    if provider == "wechat_oauth":
        return
    raise ValueError(f"Unsupported integration provider: {provider}")


def _probe_stripe_credentials(
    app: Flask,
    public_config: dict[str, Any],
    secret_config: dict[str, Any],
) -> None:
    publishable_key = str(public_config.get("publishable_key") or "").strip()
    secret_key = str(secret_config.get("secret_key") or "").strip()
    webhook_secret = str(secret_config.get("webhook_secret") or "").strip()
    if not publishable_key.startswith(("pk_live_", "pk_test_")):
        raise ValueError("Stripe publishable key must start with pk_live_ or pk_test_")
    if not secret_key.startswith(("sk_live_", "sk_test_")):
        raise ValueError("Stripe secret key must start with sk_live_ or sk_test_")
    if not webhook_secret.startswith("whsec_"):
        raise ValueError("Stripe webhook secret must start with whsec_")
    if app.config.get("TESTING"):
        return
    try:
        import stripe  # type: ignore

        request_options: dict[str, Any] = {"api_key": secret_key}
        api_version = str(public_config.get("api_version") or "").strip()
        if api_version:
            request_options["stripe_version"] = api_version
        stripe.Account.retrieve(**request_options)
    except Exception as exc:  # noqa: BLE001 - surface provider probe failure
        raise ValueError("Stripe credentials could not be verified") from exc


def _parse_pem_private_key(value: Any) -> None:
    pem = _normalize_pem(value, "PRIVATE KEY")
    try:
        serialization.load_pem_private_key(pem, password=None)
    except (TypeError, ValueError) as exc:
        raise ValueError("Private key is not a valid PEM key") from exc


def _parse_pem_public_key(value: Any) -> None:
    pem = _normalize_pem(value, "PUBLIC KEY")
    try:
        serialization.load_pem_public_key(pem)
    except (TypeError, ValueError) as exc:
        raise ValueError("Public key is not a valid PEM key") from exc


def _parse_x509_certificate(value: Any) -> None:
    pem = _normalize_pem(value, "CERTIFICATE")
    try:
        x509.load_pem_x509_certificate(pem)
    except ValueError as exc:
        raise ValueError("Certificate is not a valid PEM certificate") from exc


def _normalize_pem(value: Any, label: str) -> bytes:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label.title()} is required")
    if "-----BEGIN" in text:
        return text.encode("utf-8")
    compact = "".join(text.split())
    try:
        base64.b64decode(compact, validate=True)
    except binascii.Error as exc:
        raise ValueError(f"{label.title()} is not valid PEM or base64") from exc
    lines = "\n".join(compact[i : i + 64] for i in range(0, len(compact), 64))
    return f"-----BEGIN {label}-----\n{lines}\n-----END {label}-----\n".encode("ascii")


def _config_owner_bid(integration_bid: str) -> str:
    model = _saas_model()
    row = model.query.filter(
        model.config_bid == integration_bid,
        model.deleted == 0,
    ).first()
    return str(getattr(row, "user_bid", "") or "")


def _build_callback_token(app: Flask, integration_bid: str) -> str:
    key = _require_creator_integration_secret_key(app)
    digest = hmac.new(
        key.encode(), integration_bid.encode(), hashlib.sha256
    ).hexdigest()
    return f"{integration_bid}.{digest}"


def _require_creator_integration_secret_key(app: Flask) -> str:
    key = str(app.config.get("CREATOR_INTEGRATION_ENCRYPTION_KEY") or "").strip()
    if not key:
        raise RuntimeError("CREATOR_INTEGRATION_ENCRYPTION_KEY must be configured")
    try:
        Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("CREATOR_INTEGRATION_ENCRYPTION_KEY is invalid") from exc
    return key


def _verify_callback_token(app: Flask, token: str) -> str:
    integration_bid, separator, signature = str(token or "").partition(".")
    if (
        not separator
        or not integration_bid
        or not hmac.compare_digest(_build_callback_token(app, integration_bid), token)
    ):
        raise_error("server.shifu.noPermission")
    return integration_bid


def _normalize_provider(value: Any) -> str:
    provider = normalize_bid(value).lower()
    if provider not in INTEGRATION_PROVIDERS:
        raise_param_error("provider")
    return provider


def _normalize_config(provider: str, value: Any, secret: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise_param_error("secret_config" if secret else "public_config")
    public_fields, secret_fields = _PROVIDER_FIELDS[provider]
    allowed = (
        secret_fields
        if secret
        else public_fields | _OPTIONAL_PUBLIC_FIELDS.get(provider, set())
    )
    if set(value) - allowed:
        raise_param_error("secret_config" if secret else "public_config")
    return {
        str(key): item.strip() if isinstance(item, str) else item
        for key, item in value.items()
        if item is not None and item != ""
    }


def _validate_required_config(
    provider: str, public_config: dict[str, Any], secret_config: dict[str, Any]
) -> None:
    public_fields, secret_fields = _PROVIDER_FIELDS[provider]
    missing = sorted(
        {key for key in public_fields if not public_config.get(key)}
        | {key for key in secret_fields if not secret_config.get(key)}
    )
    if missing:
        raise ValueError("Missing required configuration: " + ", ".join(missing))


def _require_capability(
    granted: bool,
    *,
    allow_when_customization_disabled: bool = False,
) -> None:
    if (
        not allow_when_customization_disabled and not is_creator_customization_enabled()
    ) or not granted:
        raise_error("server.shifu.noPermission")


def _normalize_logo_url(value: Any, field: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    path = parsed.path
    suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    storage_hosts = {
        parsed_config.hostname.lower()
        for config_key in (
            "ALIBABA_CLOUD_OSS_BASE_URL",
            "ALIBABA_CLOUD_OSS_COURSES_URL",
        )
        if (parsed_config := urlsplit(str(get_config(config_key, "") or ""))).hostname
    }
    is_managed_host = bool(parsed.hostname and parsed.hostname.lower() in storage_hosts)
    is_local_storage = not parsed.netloc and path.startswith(
        ("/storage/", "/api/storage/")
    )
    if suffix not in _LOGO_CONTENT_TYPES or not (is_managed_host or is_local_storage):
        raise_param_error(field)
    return raw


def _detect_logo_content_type(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _normalize_logo_target(value: Any) -> str:
    normalized = str(value or "wide").strip().lower()
    if normalized not in _LOGO_VARIANTS:
        raise_param_error("target")
    return normalized


def _normalize_logo_image(content: bytes, *, suffix: str, target: str) -> bytes:
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > _LOGO_MAX_PIXELS:
                raise_param_error("file")
            normalized_image = ImageOps.exif_transpose(image)
            if target == "square":
                rendered = _contain_logo_without_upscale(
                    normalized_image,
                    _LOGO_SQUARE_MAX_SIZE,
                )
                canvas_size = (
                    min(_LOGO_SQUARE_MAX_SIZE[0], max(rendered.width, rendered.height)),
                    min(_LOGO_SQUARE_MAX_SIZE[1], max(rendered.width, rendered.height)),
                )
                canvas = _create_logo_canvas(
                    size=canvas_size,
                    suffix=suffix,
                    source_mode=rendered.mode,
                )
                offset = (
                    (canvas_size[0] - rendered.width) // 2,
                    (canvas_size[1] - rendered.height) // 2,
                )
                _paste_logo(canvas, rendered, offset)
                return _save_logo_image(canvas, suffix=suffix)

            rendered = _contain_logo_without_upscale(
                normalized_image,
                _LOGO_WIDE_MAX_SIZE,
            )
            return _save_logo_image(rendered, suffix=suffix)
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
        raise_param_error("file")


def _contain_logo_without_upscale(
    image: Image.Image,
    size: tuple[int, int],
) -> Image.Image:
    rendered = image.copy()
    if rendered.width > size[0] or rendered.height > size[1]:
        rendered.thumbnail(size, Image.Resampling.LANCZOS)
    return rendered


def _create_logo_canvas(
    *,
    size: tuple[int, int],
    suffix: str,
    source_mode: str,
) -> Image.Image:
    if suffix in {".jpg", ".jpeg"}:
        return Image.new("RGB", size, (255, 255, 255))
    if "A" in source_mode:
        return Image.new("RGBA", size, (255, 255, 255, 0))
    return Image.new("RGB", size, (255, 255, 255))


def _paste_logo(
    canvas: Image.Image,
    rendered: Image.Image,
    offset: tuple[int, int],
) -> None:
    if "A" in rendered.getbands():
        canvas.paste(rendered, offset, rendered)
        return
    canvas.paste(rendered, offset)


def _save_logo_image(image: Image.Image, *, suffix: str) -> bytes:
    output = BytesIO()
    save_kwargs: dict[str, Any] = {}
    if suffix == ".webp":
        save_format = "WEBP"
    elif suffix in {".jpg", ".jpeg"}:
        save_format = "JPEG"
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        save_kwargs["quality"] = 95
    else:
        save_format = "PNG"
        if image.mode not in {"RGB", "RGBA", "L"}:
            image = image.convert("RGBA")
    image.save(output, format=save_format, **save_kwargs)
    return output.getvalue()


def _saas_funcs(*, required: bool = True):
    try:
        return import_module(
            "flaskr.plugins.ai_shifu_saas_plugin.src.service.config.funcs"
        )
    except ModuleNotFoundError as exc:
        if not str(exc.name or "").startswith("flaskr.plugins.ai_shifu_saas_plugin"):
            raise
        if required:
            raise RuntimeError("SaaS config plugin is not installed") from exc
        return None


def _saas_model():
    return import_module(
        "flaskr.plugins.ai_shifu_saas_plugin.src.service.config.models"
    ).SaasUserConfig


def _load_json(value: Any) -> dict[str, Any]:
    try:
        payload = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _dump_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _admin_draft_owner_bid(*, creator_bid: str = "", creator_mobile: str = "") -> str:
    normalized_creator_bid = normalize_bid(creator_bid)
    if normalized_creator_bid:
        return f"billing-admin-draft:creator:{normalized_creator_bid}"

    normalized_creator_mobile = str(creator_mobile or "").strip()
    if not normalized_creator_mobile:
        raise_param_error("creator_mobile")
    mobile_digest = hashlib.sha256(
        normalized_creator_mobile.encode("utf-8")
    ).hexdigest()
    return f"billing-admin-draft:mobile:{mobile_digest}"


def _empty_admin_creator_customization_draft(
    *, creator_mobile: str = ""
) -> dict[str, Any]:
    return {
        "creator_mobile": str(creator_mobile or "").strip(),
        "branding_enabled": False,
        "custom_domain_enabled": False,
        "custom_wechat_enabled": False,
        "custom_payment_enabled": False,
        "config_status": "pending",
        "note": "",
        "branding": {
            "logo_wide_url": "",
            "logo_square_url": "",
        },
        "domain": {
            "host": "",
        },
        "integrations": {
            provider: {"public_config": {}, "secret_config": {}}
            for provider in INTEGRATION_PROVIDERS
        },
    }


def _normalize_admin_creator_customization_draft(
    payload: dict[str, Any],
    *,
    creator_mobile: str = "",
) -> dict[str, Any]:
    base = _empty_admin_creator_customization_draft(creator_mobile=creator_mobile)
    result = dict(base)
    result["creator_mobile"] = str(
        payload.get("creator_mobile") or creator_mobile or ""
    ).strip()
    for key in (
        "branding_enabled",
        "custom_domain_enabled",
        "custom_wechat_enabled",
        "custom_payment_enabled",
    ):
        result[key] = _to_bool(payload.get(key))

    config_status = str(payload.get("config_status") or "pending").strip().lower()
    result["config_status"] = (
        config_status
        if config_status in {"pending", "in_progress", "completed", "exception"}
        else "pending"
    )
    result["note"] = str(payload.get("note") or "")[:500]

    branding_payload = payload.get("branding")
    if isinstance(branding_payload, dict):
        result["branding"] = {
            "logo_wide_url": _normalize_logo_url(
                branding_payload.get("logo_wide_url"), "logo_wide_url"
            )
            if branding_payload.get("logo_wide_url")
            else "",
            "logo_square_url": _normalize_logo_url(
                branding_payload.get("logo_square_url"), "logo_square_url"
            )
            if branding_payload.get("logo_square_url")
            else "",
        }

    domain_payload = payload.get("domain")
    if isinstance(domain_payload, dict):
        result["domain"] = {"host": str(domain_payload.get("host") or "").strip()}

    integrations_payload = payload.get("integrations")
    if isinstance(integrations_payload, dict):
        normalized_integrations = {}
        for provider in INTEGRATION_PROVIDERS:
            provider_payload = integrations_payload.get(provider)
            if isinstance(provider_payload, dict):
                normalized_integrations[provider] = {
                    "public_config": _normalize_config(
                        provider, provider_payload.get("public_config"), False
                    ),
                    "secret_config": {},
                }
            else:
                normalized_integrations[provider] = {
                    "public_config": {},
                    "secret_config": {},
                }
        result["integrations"] = normalized_integrations

    return result
