"""Custom domain binding helpers for creator billing v1.1."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.util.timezone import serialize_with_app_timezone
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_DOMAIN_BINDING_STATUS_DISABLED,
    BILLING_DOMAIN_BINDING_STATUS_FAILED,
    BILLING_DOMAIN_BINDING_STATUS_LABELS,
    BILLING_DOMAIN_BINDING_STATUS_PENDING,
    BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
    BILLING_DOMAIN_SSL_STATUS_LABELS,
    BILLING_DOMAIN_SSL_STATUS_NOT_REQUESTED,
    BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
    BILLING_DOMAIN_VERIFICATION_METHOD_LABELS,
)
from .dtos import (
    BillingDomainBindResultDTO,
    BillingDomainBindingDTO,
    BillingDomainBindingsDTO,
    RuntimeBillingDomainDTO,
)
from .entitlements import resolve_creator_entitlement_state
from .models import BillingDomainBinding
from .primitives import normalize_bid as _normalize_bid
from .value_objects import JsonObjectMap

_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

_DOMAIN_BINDING_ACTIONS = {"bind", "verify", "disable"}

_DOMAIN_VERIFICATION_METHOD_CODES = {
    label: code for code, label in BILLING_DOMAIN_VERIFICATION_METHOD_LABELS.items()
}


@dataclass(slots=True, frozen=True)
class DomainVerificationResult:
    creator_bid: str
    action: str
    binding: BillingDomainBindingDTO

    def to_task_payload(self) -> dict[str, Any]:
        return {
            "creator_bid": self.creator_bid,
            "action": self.action,
            "binding": self.binding.__json__(),
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_task_payload()[key]


def build_creator_domain_bindings(
    app: Flask,
    creator_bid: str,
    *,
    timezone_name: str | None = None,
) -> BillingDomainBindingsDTO:
    """Return the creator domain binding list and entitlement gate state."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        entitlement_state = resolve_creator_entitlement_state(normalized_creator_bid)
        custom_domain_enabled = bool(entitlement_state.custom_domain_enabled)
        rows = (
            BillingDomainBinding.query.filter(
                BillingDomainBinding.deleted == 0,
                BillingDomainBinding.creator_bid == normalized_creator_bid,
            )
            .order_by(
                BillingDomainBinding.status.asc(),
                BillingDomainBinding.updated_at.desc(),
                BillingDomainBinding.id.desc(),
            )
            .all()
        )
        return BillingDomainBindingsDTO(
            creator_bid=normalized_creator_bid,
            custom_domain_enabled=custom_domain_enabled,
            items=[
                _serialize_domain_binding(
                    app,
                    row,
                    timezone_name=timezone_name,
                    custom_domain_enabled=custom_domain_enabled,
                )
                for row in rows
            ],
        )


def manage_creator_domain_binding(
    app: Flask,
    creator_bid: str,
    payload: dict[str, Any],
    *,
    timezone_name: str | None = None,
) -> BillingDomainBindResultDTO:
    """Bind, verify, or disable a creator custom domain."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    action = _normalize_action(payload.get("action"))
    normalized_binding_bid = _normalize_bid(payload.get("domain_binding_bid"))
    normalized_host = normalize_domain_host(
        payload.get("host"),
        strict=action == "bind" and not normalized_binding_bid,
    )

    with app.app_context():
        entitlement_state = resolve_creator_entitlement_state(normalized_creator_bid)
        custom_domain_enabled = bool(entitlement_state.custom_domain_enabled)

        if action in {"bind", "verify"} and not custom_domain_enabled:
            raise_error("server.billing.customDomainDisabled")

        if action == "bind":
            binding = _bind_creator_domain(
                app,
                creator_bid=normalized_creator_bid,
                host=normalized_host,
                domain_binding_bid=normalized_binding_bid,
                verification_method=payload.get("verification_method"),
            )
        elif action == "verify":
            binding = _verify_creator_domain(
                creator_bid=normalized_creator_bid,
                host=normalized_host,
                domain_binding_bid=normalized_binding_bid,
                verification_token=payload.get("verification_token"),
            )
        else:
            binding = _disable_creator_domain(
                creator_bid=normalized_creator_bid,
                host=normalized_host,
                domain_binding_bid=normalized_binding_bid,
            )

        db.session.add(binding)
        db.session.commit()
        return BillingDomainBindResultDTO(
            action=action,
            binding=_serialize_domain_binding(
                app,
                binding,
                timezone_name=timezone_name,
                custom_domain_enabled=custom_domain_enabled,
            ),
        )


def verify_domain_binding(
    app: Flask,
    *,
    creator_bid: str = "",
    domain_binding_bid: str = "",
    host: Any = "",
    verification_token: Any = "",
    timezone_name: str | None = None,
) -> DomainVerificationResult:
    """Verify one domain binding by business id or host for background tasks."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_domain_binding_bid = _normalize_bid(domain_binding_bid)
    normalized_host = normalize_domain_host(host, strict=False)

    with app.app_context():
        binding = _load_domain_binding_for_task(
            creator_bid=normalized_creator_bid,
            domain_binding_bid=normalized_domain_binding_bid,
            host=normalized_host,
        )
        if binding is None:
            raise_error("server.billing.domainBindingNotFound")

        binding_creator_bid = _normalize_bid(binding.creator_bid)
        result = manage_creator_domain_binding(
            app,
            binding_creator_bid,
            {
                "action": "verify",
                "domain_binding_bid": binding.domain_binding_bid,
                "host": binding.host,
                "verification_token": (
                    _normalize_bid(verification_token)
                    or _normalize_bid(binding.verification_token)
                ),
            },
            timezone_name=timezone_name,
        )
        return DomainVerificationResult(
            creator_bid=binding_creator_bid,
            action=result.action,
            binding=result.binding,
        )


def resolve_creator_bid_by_host(app: Flask, host: Any) -> str | None:
    """Resolve a verified creator custom domain back to creator_bid."""

    normalized_host = normalize_domain_host(host, strict=False)
    if not normalized_host:
        return None

    with app.app_context():
        binding = (
            BillingDomainBinding.query.filter(
                BillingDomainBinding.deleted == 0,
                BillingDomainBinding.host == normalized_host,
                BillingDomainBinding.status == BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
            )
            .order_by(BillingDomainBinding.id.desc())
            .first()
        )
        if binding is None:
            return None

        entitlement_state = resolve_creator_entitlement_state(binding.creator_bid)
        if not bool(entitlement_state.custom_domain_enabled):
            return None

        return _normalize_bid(binding.creator_bid) or None


def resolve_runtime_domain_result(
    app: Flask,
    host: Any,
    *,
    creator_bid: str = "",
) -> RuntimeBillingDomainDTO:
    """Return runtime-config domain metadata for the current request host."""

    normalized_host = normalize_domain_host(host, strict=False)
    normalized_creator_bid = _normalize_bid(creator_bid)
    if not normalized_host:
        return RuntimeBillingDomainDTO(
            request_host=None,
            matched=False,
            is_custom_domain=False,
            creator_bid=normalized_creator_bid or None,
            domain_binding_bid=None,
            host=None,
            binding_status=None,
        )

    with app.app_context():
        binding = (
            BillingDomainBinding.query.filter(
                BillingDomainBinding.deleted == 0,
                BillingDomainBinding.host == normalized_host,
            )
            .order_by(BillingDomainBinding.id.desc())
            .first()
        )
        if binding is None:
            return RuntimeBillingDomainDTO(
                request_host=normalized_host,
                matched=False,
                is_custom_domain=False,
                creator_bid=normalized_creator_bid or None,
                domain_binding_bid=None,
                host=None,
                binding_status=None,
            )

        binding_creator_bid = _normalize_bid(binding.creator_bid)
        entitlement_state = resolve_creator_entitlement_state(binding_creator_bid)
        custom_domain_enabled = bool(entitlement_state.custom_domain_enabled)
        creator_matches = not normalized_creator_bid or (
            normalized_creator_bid == binding_creator_bid
        )
        is_custom_domain = bool(
            creator_matches
            and custom_domain_enabled
            and binding.status == BILLING_DOMAIN_BINDING_STATUS_VERIFIED
        )
        return RuntimeBillingDomainDTO(
            request_host=normalized_host,
            matched=True,
            is_custom_domain=is_custom_domain,
            creator_bid=binding_creator_bid if is_custom_domain else None,
            domain_binding_bid=binding.domain_binding_bid if is_custom_domain else None,
            host=binding.host if is_custom_domain else None,
            binding_status=BILLING_DOMAIN_BINDING_STATUS_LABELS.get(
                binding.status,
                "pending",
            ),
        )


def normalize_domain_host(value: Any, *, strict: bool = True) -> str:
    """Normalize a host string into a lowercase custom-domain host."""

    raw = str(value or "").strip()
    if not raw:
        if strict:
            raise_param_error("host")
        return ""

    candidate = raw
    if "://" not in candidate:
        candidate = f"//{candidate}"
    parsed = urlsplit(candidate)
    host = str(parsed.hostname or "").strip().rstrip(".").lower()
    if not host:
        if strict:
            raise_param_error("host")
        return ""

    try:
        normalized_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        if strict:
            raise_param_error("host")
        return ""

    if _is_invalid_host(normalized_host):
        if strict:
            raise_param_error("host")
        return ""

    return normalized_host


def _bind_creator_domain(
    app: Flask,
    *,
    creator_bid: str,
    host: str,
    domain_binding_bid: str,
    verification_method: Any,
) -> BillingDomainBinding:
    if not host:
        raise_param_error("host")

    existing_host_binding = (
        BillingDomainBinding.query.filter(
            BillingDomainBinding.deleted == 0,
            BillingDomainBinding.host == host,
        )
        .order_by(BillingDomainBinding.id.desc())
        .first()
    )
    if (
        existing_host_binding is not None
        and _normalize_bid(existing_host_binding.creator_bid) != creator_bid
    ):
        raise_error("server.billing.domainHostConflict")

    binding = _load_creator_domain_binding(
        creator_bid=creator_bid,
        domain_binding_bid=domain_binding_bid,
        host=host,
    )
    if binding is None:
        binding = BillingDomainBinding(
            domain_binding_bid=generate_id(app),
            creator_bid=creator_bid,
            host=host,
        )
    elif binding.status == BILLING_DOMAIN_BINDING_STATUS_VERIFIED and (
        _normalize_bid(binding.host) == host
    ):
        return binding

    binding.host = host
    binding.status = BILLING_DOMAIN_BINDING_STATUS_PENDING
    binding.verification_method = _normalize_verification_method(verification_method)
    binding.verification_token = generate_id(app)
    binding.last_verified_at = None
    binding.ssl_status = BILLING_DOMAIN_SSL_STATUS_NOT_REQUESTED
    binding.metadata_json = {
        **_as_dict(binding.metadata_json).to_metadata_json(),
        "verification_error": "",
        "verification_record_name": _build_verification_record_name(host),
        "verification_record_value": binding.verification_token,
        "updated_by": "creator_bind",
    }
    return binding


def _verify_creator_domain(
    *,
    creator_bid: str,
    host: str,
    domain_binding_bid: str,
    verification_token: Any,
) -> BillingDomainBinding:
    binding = _load_creator_domain_binding(
        creator_bid=creator_bid,
        domain_binding_bid=domain_binding_bid,
        host=host,
    )
    if binding is None:
        raise_error("server.billing.domainBindingNotFound")

    normalized_token = _normalize_bid(verification_token)
    if not normalized_token:
        raise_param_error("verification_token")

    metadata = _as_dict(binding.metadata_json).to_metadata_json()
    if normalized_token == _normalize_bid(binding.verification_token):
        binding.status = BILLING_DOMAIN_BINDING_STATUS_VERIFIED
        binding.last_verified_at = datetime.now()
        metadata["verification_error"] = ""
        metadata["verified_by"] = "creator_verify"
    else:
        binding.status = BILLING_DOMAIN_BINDING_STATUS_FAILED
        metadata["verification_error"] = "token_mismatch"
    binding.metadata_json = metadata
    return binding


def _disable_creator_domain(
    *,
    creator_bid: str,
    host: str,
    domain_binding_bid: str,
) -> BillingDomainBinding:
    binding = _load_creator_domain_binding(
        creator_bid=creator_bid,
        domain_binding_bid=domain_binding_bid,
        host=host,
    )
    if binding is None:
        raise_error("server.billing.domainBindingNotFound")

    binding.status = BILLING_DOMAIN_BINDING_STATUS_DISABLED
    binding.metadata_json = {
        **_as_dict(binding.metadata_json).to_metadata_json(),
        "verification_error": "",
        "updated_by": "creator_disable",
    }
    return binding


def _load_creator_domain_binding(
    *,
    creator_bid: str,
    domain_binding_bid: str = "",
    host: str = "",
) -> BillingDomainBinding | None:
    query = BillingDomainBinding.query.filter(
        BillingDomainBinding.deleted == 0,
        BillingDomainBinding.creator_bid == creator_bid,
    )
    if domain_binding_bid:
        query = query.filter(
            BillingDomainBinding.domain_binding_bid == domain_binding_bid
        )
    elif host:
        query = query.filter(BillingDomainBinding.host == host)
    else:
        return None
    return query.order_by(BillingDomainBinding.id.desc()).first()


def _load_domain_binding_for_task(
    *,
    creator_bid: str = "",
    domain_binding_bid: str = "",
    host: str = "",
) -> BillingDomainBinding | None:
    query = BillingDomainBinding.query.filter(BillingDomainBinding.deleted == 0)
    if creator_bid:
        query = query.filter(BillingDomainBinding.creator_bid == creator_bid)
    if domain_binding_bid:
        query = query.filter(
            BillingDomainBinding.domain_binding_bid == domain_binding_bid
        )
    elif host:
        query = query.filter(BillingDomainBinding.host == host)
    else:
        raise_param_error("domain_binding_bid")
    return query.order_by(BillingDomainBinding.id.desc()).first()


def _serialize_domain_binding(
    app: Flask,
    row: BillingDomainBinding,
    *,
    timezone_name: str | None = None,
    custom_domain_enabled: bool = False,
) -> BillingDomainBindingDTO:
    metadata = _as_dict(row.metadata_json)
    verification_record_name = str(
        metadata.get("verification_record_name")
        or _build_verification_record_name(row.host)
    )
    verification_record_value = str(
        metadata.get("verification_record_value") or row.verification_token or ""
    )
    return BillingDomainBindingDTO(
        domain_binding_bid=row.domain_binding_bid,
        creator_bid=row.creator_bid,
        host=row.host,
        status=BILLING_DOMAIN_BINDING_STATUS_LABELS.get(row.status, "pending"),
        verification_method=BILLING_DOMAIN_VERIFICATION_METHOD_LABELS.get(
            row.verification_method,
            "dns_txt",
        ),
        verification_token=row.verification_token,
        verification_record_name=verification_record_name,
        verification_record_value=verification_record_value,
        last_verified_at=serialize_with_app_timezone(
            app,
            row.last_verified_at,
            timezone_name,
        ),
        ssl_status=BILLING_DOMAIN_SSL_STATUS_LABELS.get(
            row.ssl_status,
            "not_requested",
        ),
        is_effective=bool(
            custom_domain_enabled
            and row.status == BILLING_DOMAIN_BINDING_STATUS_VERIFIED
        ),
        metadata=metadata.to_metadata_json(),
    )


def _normalize_action(value: Any) -> str:
    normalized = _normalize_bid(value) or "bind"
    if normalized not in _DOMAIN_BINDING_ACTIONS:
        raise_param_error("action")
    return normalized


def _normalize_verification_method(value: Any) -> int:
    normalized = _normalize_bid(value)
    if not normalized:
        return BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT
    if normalized in _DOMAIN_VERIFICATION_METHOD_CODES:
        return _DOMAIN_VERIFICATION_METHOD_CODES[normalized]
    try:
        method_code = int(normalized)
    except (TypeError, ValueError):
        raise_param_error("verification_method")
    if method_code not in BILLING_DOMAIN_VERIFICATION_METHOD_LABELS:
        raise_param_error("verification_method")
    return method_code


def _build_verification_record_name(host: str) -> str:
    return f"_ai-shifu.{host}"


def _is_invalid_host(host: str) -> bool:
    if len(host) > 255 or "." not in host:
        return True
    if host == "localhost":
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    labels = host.split(".")
    if any(not label or len(label) > 63 for label in labels):
        return True
    return any(_DOMAIN_LABEL_RE.fullmatch(label) is None for label in labels)


def _as_dict(value: Any) -> JsonObjectMap:
    if isinstance(value, dict):
        return JsonObjectMap(values={str(key): item for key, item in value.items()})
    return JsonObjectMap()
