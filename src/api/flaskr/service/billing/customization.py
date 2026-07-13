"""Course-owner customization backed by the SaaS unified config table."""

from __future__ import annotations

from io import BytesIO
from dataclasses import dataclass
import hashlib
import hmac
from importlib import import_module
import json
from typing import Any
from urllib.parse import urlsplit

from flask import Flask
from werkzeug.datastructures import FileStorage

from flaskr.service.common.oss_utils import OSS_PROFILE_COURSES
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.storage import upload_to_storage
from flaskr.service.config.funcs import get_config
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id

from .domains import build_creator_domain_bindings
from .entitlements import (
    resolve_creator_entitlement_state,
    serialize_creator_entitlements,
)
from .primitives import normalize_bid

BRANDING_KEY = "CUSTOMIZATION.BRANDING"
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


def build_creator_customization(app: Flask, creator_bid: str) -> dict[str, Any]:
    creator_bid = normalize_bid(creator_bid)
    with app.app_context():
        entitlement = resolve_creator_entitlement_state(creator_bid)
        return {
            "enabled": is_creator_customization_enabled(),
            "creator_bid": creator_bid,
            "capabilities": build_customization_capabilities(entitlement),
            "entitlements": serialize_creator_entitlements(entitlement).__json__(),
            "branding": resolve_creator_branding(creator_bid),
            "domains": build_creator_domain_bindings(app, creator_bid).__json__(),
            "integrations": [
                _serialize_active_integration(app, creator_bid, provider)
                for provider in INTEGRATION_PROVIDERS
            ],
        }


def build_customization_capabilities(entitlement) -> dict[str, bool]:
    enabled = is_creator_customization_enabled()
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
) -> str:
    """Validate and upload a course-owner logo through managed storage."""

    creator_bid = normalize_bid(creator_bid)
    with app.app_context():
        entitlement = resolve_creator_entitlement_state(creator_bid)
        _require_capability(entitlement.branding_enabled)

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

        result = upload_to_storage(
            app,
            file_content=BytesIO(content),
            object_key=(f"creator-branding/{creator_bid}/{generate_id(app)}{suffix}"),
            content_type=expected_content_type,
            profile=OSS_PROFILE_COURSES,
            warm_up=False,
        )
        return result.url


def save_creator_branding(
    app: Flask, creator_bid: str, payload: dict[str, Any]
) -> dict[str, str]:
    creator_bid = normalize_bid(creator_bid)
    with app.app_context():
        entitlement = resolve_creator_entitlement_state(creator_bid)
        _require_capability(entitlement.branding_enabled)
        value = {
            "logo_wide_url": _normalize_logo_url(
                payload.get("logo_wide_url"), "logo_wide_url"
            ),
            "logo_square_url": _normalize_logo_url(
                payload.get("logo_square_url"), "logo_square_url"
            ),
        }
        funcs = _saas_funcs()
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
    app: Flask, creator_bid: str, provider: str, payload: dict[str, Any]
) -> dict[str, Any]:
    creator_bid = normalize_bid(creator_bid)
    provider = _normalize_provider(provider)
    with app.app_context():
        entitlement = resolve_creator_entitlement_state(creator_bid)
        _require_capability(
            entitlement.custom_wechat_enabled
            if provider == "wechat_oauth"
            else entitlement.custom_payment_enabled
        )
        public_config = _normalize_config(provider, payload.get("public_config"), False)
        secret_config = _normalize_config(provider, payload.get("secret_config"), True)
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
        _activate_provider_config(app, creator_bid, provider, record)
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
        try:
            _validate_required_config(
                provider,
                dict(record.get("public_config") or {}),
                dict(record.get("secret_config") or {}),
            )
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
            verified_at=now_utc().isoformat(),
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
    value = _saas_funcs().get_sass_config(
        normalize_bid(creator_bid), BRANDING_KEY, default="{}"
    )
    payload = _load_json(value)
    return {
        "logo_wide_url": str(payload.get("logo_wide_url") or ""),
        "logo_square_url": str(payload.get("logo_square_url") or ""),
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
    return str(
        _saas_funcs().get_sass_config(
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


def _config_owner_bid(integration_bid: str) -> str:
    model = _saas_model()
    row = model.query.filter(
        model.config_bid == integration_bid,
        model.deleted == 0,
    ).first()
    return str(getattr(row, "user_bid", "") or "")


def _build_callback_token(app: Flask, integration_bid: str) -> str:
    key = str(app.config.get("CREATOR_INTEGRATION_ENCRYPTION_KEY") or "")
    digest = hmac.new(
        key.encode(), integration_bid.encode(), hashlib.sha256
    ).hexdigest()
    return f"{integration_bid}.{digest}"


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


def _require_capability(granted: bool) -> None:
    if not is_creator_customization_enabled() or not granted:
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


def _saas_funcs():
    return import_module("flaskr.plugins.ai_shifu_saas_plugin.src.service.config.funcs")


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
