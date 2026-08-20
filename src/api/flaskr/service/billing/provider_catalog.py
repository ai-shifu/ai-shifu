"""Provider catalog read adapters and local mapping validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from flask import Flask
from flaskr.service.common.stripe_client import get_stripe_client_options

from .consts import (
    BILLING_INTERVAL_DAY,
    BILLING_INTERVAL_LABELS,
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_NONE,
    BILLING_INTERVAL_YEAR,
    BILLING_MODE_ONE_TIME,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_TYPE_LABELS,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
)
from .primitives import normalize_bid, to_decimal

if TYPE_CHECKING:
    from .models import BillingProduct

_STRIPE_INTERVAL_BY_BILLING_INTERVAL = {
    BILLING_INTERVAL_DAY: "day",
    BILLING_INTERVAL_MONTH: "month",
    BILLING_INTERVAL_YEAR: "year",
}


@dataclass(slots=True)
class ProviderAccountSnapshot:
    provider: str
    account_id: str
    livemode: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderProductSnapshot:
    provider: str
    product_id: str
    active: bool
    livemode: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderPriceSnapshot:
    provider: str
    price_id: str
    product_id: str
    active: bool
    livemode: bool
    currency: str
    unit_amount: int | None
    price_type: str
    recurring_interval: str
    recurring_interval_count: int
    recurring_usage_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderCatalogSnapshot:
    account: ProviderAccountSnapshot
    product: ProviderProductSnapshot
    price: ProviderPriceSnapshot


@dataclass(slots=True)
class ProviderCatalogValidationIssue:
    code: str
    message: str
    expected: str = ""
    actual: str = ""


@dataclass(slots=True)
class ProviderPriceMappingValidationResult:
    valid: bool
    errors: list[ProviderCatalogValidationIssue] = field(default_factory=list)
    warnings: list[ProviderCatalogValidationIssue] = field(default_factory=list)


class ProviderCatalogReadError(RuntimeError):
    """Raised when a provider catalog object cannot be retrieved."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class StripeCatalogReadAdapter:
    """Read Stripe catalog objects and normalize them for billing services."""

    provider = "stripe"

    def _client_options(self, app: Flask) -> tuple[Any, dict[str, Any]]:
        return get_stripe_client_options(app)

    def retrieve_mapping_snapshot(
        self,
        app: Flask,
        *,
        provider_product_id: str,
        provider_price_id: str,
    ) -> ProviderCatalogSnapshot:
        stripe, request_options = self._client_options(app)
        normalized_product_id = normalize_bid(provider_product_id)
        normalized_price_id = normalize_bid(provider_price_id)
        if not normalized_product_id or not normalized_price_id:
            raise ProviderCatalogReadError(
                "stripe_catalog_reference_missing",
                "Stripe product and price identifiers are required",
            )

        try:
            account = _to_plain_dict(stripe.Account.retrieve(**request_options))
            product = _to_plain_dict(
                stripe.Product.retrieve(normalized_product_id, **request_options)
            )
            price = _to_plain_dict(
                stripe.Price.retrieve(normalized_price_id, **request_options)
            )
        except Exception as exc:
            raise ProviderCatalogReadError(
                "stripe_catalog_retrieve_failed",
                _build_safe_stripe_error_message(exc),
            ) from None

        return ProviderCatalogSnapshot(
            account=_normalize_stripe_account(account),
            product=_normalize_stripe_product(product),
            price=_normalize_stripe_price(price),
        )


def validate_provider_price_mapping(
    product: BillingProduct,
    snapshot: ProviderCatalogSnapshot,
    *,
    expected_provider_account_id: str,
    expected_livemode: bool,
    expected_provider_product_id: str,
    expected_provider_price_id: str,
) -> ProviderPriceMappingValidationResult:
    """Validate a local product against normalized provider catalog objects."""
    errors: list[ProviderCatalogValidationIssue] = []
    warnings: list[ProviderCatalogValidationIssue] = []

    _append_mismatch(
        errors,
        "provider_account_mismatch",
        "Stripe account does not match the expected account",
        expected_provider_account_id,
        snapshot.account.account_id,
    )
    _append_mismatch(
        errors,
        "provider_product_mismatch",
        "Stripe product does not match the expected product",
        expected_provider_product_id,
        snapshot.product.product_id,
    )
    _append_mismatch(
        errors,
        "provider_price_mismatch",
        "Stripe price does not match the expected price",
        expected_provider_price_id,
        snapshot.price.price_id,
    )
    _append_mismatch(
        errors,
        "price_product_mismatch",
        "Stripe price is not attached to the expected product",
        expected_provider_product_id,
        snapshot.price.product_id,
    )

    expected_livemode_label = _bool_label(expected_livemode)
    for code, actual in (
        ("product_livemode_mismatch", snapshot.product.livemode),
        ("price_livemode_mismatch", snapshot.price.livemode),
    ):
        if actual is not None and bool(actual) != expected_livemode:
            errors.append(
                ProviderCatalogValidationIssue(
                    code=code,
                    message="Stripe catalog mode does not match the expected mode",
                    expected=expected_livemode_label,
                    actual=_bool_label(bool(actual)),
                )
            )

    if not snapshot.product.active:
        errors.append(
            ProviderCatalogValidationIssue(
                code="provider_product_inactive",
                message="Stripe product is inactive",
            )
        )
    if not snapshot.price.active:
        errors.append(
            ProviderCatalogValidationIssue(
                code="provider_price_inactive",
                message="Stripe price is inactive",
            )
        )

    _append_mismatch(
        errors,
        "currency_mismatch",
        "Stripe price currency does not match the local product",
        str(product.currency or "").strip().lower(),
        snapshot.price.currency,
    )
    if snapshot.price.unit_amount is None:
        errors.append(
            ProviderCatalogValidationIssue(
                code="provider_price_unit_amount_missing",
                message="Stripe price must have a fixed unit amount",
            )
        )
    else:
        _append_mismatch(
            errors,
            "unit_amount_mismatch",
            "Stripe price amount does not match the local product",
            str(int(product.price_amount or 0)),
            str(snapshot.price.unit_amount),
        )

    product_type = int(product.product_type or 0)
    if product_type == BILLING_PRODUCT_TYPE_PLAN:
        _validate_plan_price(product, snapshot.price, errors)
    elif product_type == BILLING_PRODUCT_TYPE_TOPUP:
        _validate_topup_price(product, snapshot.price, errors)
    else:
        errors.append(
            ProviderCatalogValidationIssue(
                code="unsupported_product_type",
                message="Only plan and topup products can bind provider prices",
                expected=f"{BILLING_PRODUCT_TYPE_PLAN},{BILLING_PRODUCT_TYPE_TOPUP}",
                actual=str(product_type),
            )
        )

    _validate_product_metadata_warnings(product, snapshot.product.metadata, warnings)
    _validate_price_metadata_warnings(product, snapshot.price.metadata, warnings)

    return ProviderPriceMappingValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
    )


def _validate_plan_price(
    product: BillingProduct,
    price: ProviderPriceSnapshot,
    errors: list[ProviderCatalogValidationIssue],
) -> None:
    if int(product.billing_mode or 0) != BILLING_MODE_RECURRING:
        errors.append(
            ProviderCatalogValidationIssue(
                code="local_plan_billing_mode_invalid",
                message="Plan products must use recurring billing mode",
                expected=str(BILLING_MODE_RECURRING),
                actual=str(int(product.billing_mode or 0)),
            )
        )
    if price.price_type != "recurring":
        errors.append(
            ProviderCatalogValidationIssue(
                code="plan_requires_recurring_price",
                message="Plan products must bind a recurring Stripe price",
                expected="recurring",
                actual=price.price_type,
            )
        )
        return
    if price.recurring_usage_type != "licensed":
        errors.append(
            ProviderCatalogValidationIssue(
                code="plan_requires_licensed_recurring_price",
                message="Plan products must bind a licensed recurring Stripe price",
                expected="licensed",
                actual=price.recurring_usage_type,
            )
        )

    expected_interval = _STRIPE_INTERVAL_BY_BILLING_INTERVAL.get(
        int(product.billing_interval or BILLING_INTERVAL_NONE),
        "",
    )
    _append_mismatch(
        errors,
        "billing_interval_mismatch",
        "Stripe recurring interval does not match the local product",
        expected_interval,
        price.recurring_interval,
    )
    _append_mismatch(
        errors,
        "billing_interval_count_mismatch",
        "Stripe recurring interval count does not match the local product",
        str(int(product.billing_interval_count or 0)),
        str(price.recurring_interval_count),
    )


def _validate_topup_price(
    product: BillingProduct,
    price: ProviderPriceSnapshot,
    errors: list[ProviderCatalogValidationIssue],
) -> None:
    if int(product.billing_mode or 0) != BILLING_MODE_ONE_TIME:
        errors.append(
            ProviderCatalogValidationIssue(
                code="local_topup_billing_mode_invalid",
                message="Topup products must use one-time billing mode",
                expected=str(BILLING_MODE_ONE_TIME),
                actual=str(int(product.billing_mode or 0)),
            )
        )
    if int(product.billing_interval or 0) != BILLING_INTERVAL_NONE:
        errors.append(
            ProviderCatalogValidationIssue(
                code="local_topup_billing_interval_invalid",
                message="Topup products must not use a recurring billing interval",
                expected=str(BILLING_INTERVAL_NONE),
                actual=str(int(product.billing_interval or 0)),
            )
        )
    if int(product.billing_interval_count or 0) != 0:
        errors.append(
            ProviderCatalogValidationIssue(
                code="local_topup_billing_interval_count_invalid",
                message="Topup products must use a zero billing interval count",
                expected="0",
                actual=str(int(product.billing_interval_count or 0)),
            )
        )
    if price.price_type != "one_time":
        errors.append(
            ProviderCatalogValidationIssue(
                code="topup_requires_one_time_price",
                message="Topup products must bind a one-time Stripe price",
                expected="one_time",
                actual=price.price_type,
            )
        )


def _validate_product_metadata_warnings(
    product: BillingProduct,
    metadata: dict[str, Any],
    warnings: list[ProviderCatalogValidationIssue],
) -> None:
    for key, expected_value in (
        ("market", _expected_market_metadata(product)),
        ("plan_tier", _expected_plan_tier_metadata(product)),
        ("product_type", _product_type_label(product.product_type)),
    ):
        _validate_metadata_warning(
            warnings,
            metadata,
            expected_key=key,
            expected_value=expected_value,
            issue_code=f"product_metadata_{key}_mismatch",
            missing_issue_code=f"product_metadata_{key}_missing",
        )


def _validate_price_metadata_warnings(
    product: BillingProduct,
    metadata: dict[str, Any],
    warnings: list[ProviderCatalogValidationIssue],
) -> None:
    for key, expected_value in (
        ("product_code", str(product.product_code or "").strip()),
        ("credit_amount", _format_metadata_decimal(product.credit_amount)),
        ("billing_interval", _billing_interval_label(product.billing_interval)),
    ):
        _validate_metadata_warning(
            warnings,
            metadata,
            expected_key=key,
            expected_value=expected_value,
            issue_code=f"price_metadata_{key}_mismatch",
            missing_issue_code=f"price_metadata_{key}_missing",
        )


def _validate_metadata_warning(
    warnings: list[ProviderCatalogValidationIssue],
    metadata: dict[str, Any],
    *,
    expected_key: str,
    expected_value: str,
    issue_code: str,
    missing_issue_code: str,
) -> None:
    normalized_expected = str(expected_value or "").strip()
    if not normalized_expected:
        return
    actual = metadata.get(expected_key)
    actual_value = _normalize_metadata_compare_value(actual)
    if not actual_value:
        warnings.append(
            ProviderCatalogValidationIssue(
                code=missing_issue_code,
                message="Stripe metadata is missing an expected local product value",
                expected=normalized_expected,
                actual="",
            )
        )
        return
    if actual_value == normalized_expected:
        return
    warnings.append(
        ProviderCatalogValidationIssue(
            code=issue_code,
            message="Stripe metadata does not match the local product",
            expected=normalized_expected,
            actual=actual_value,
        )
    )


def _expected_market_metadata(product: BillingProduct) -> str:
    metadata = product.metadata_json if isinstance(product.metadata_json, dict) else {}
    explicit_market = str(metadata.get("market") or "").strip()
    if explicit_market:
        return explicit_market
    parts = str(product.product_code or "").strip().split("-")
    return parts[1] if len(parts) >= 3 and parts[0] == "creator" else ""


def _expected_plan_tier_metadata(product: BillingProduct) -> str:
    if int(product.product_type or 0) != BILLING_PRODUCT_TYPE_PLAN:
        return ""
    metadata = product.metadata_json if isinstance(product.metadata_json, dict) else {}
    for key in ("stripe_plan_tier", "plan_tier_code"):
        explicit_tier = str(metadata.get(key) or "").strip()
        if explicit_tier:
            return explicit_tier
    parts = str(product.product_code or "").strip().split("-")
    if len(parts) >= 4 and parts[0] == "creator":
        return parts[2]
    raw_tier = metadata.get("plan_tier")
    return str(raw_tier or "").strip()


def _product_type_label(value: Any) -> str:
    return BILLING_PRODUCT_TYPE_LABELS.get(int(value or 0), "")


def _billing_interval_label(value: Any) -> str:
    return BILLING_INTERVAL_LABELS.get(int(value or BILLING_INTERVAL_NONE), "")


def _format_metadata_decimal(value: Any) -> str:
    try:
        normalized = to_decimal(value)
    except (InvalidOperation, ValueError):
        return str(value or "").strip()
    if normalized == normalized.to_integral_value():
        return str(int(normalized))
    return format(normalized.normalize(), "f").rstrip("0").rstrip(".")


def _normalize_metadata_compare_value(value: Any) -> str:
    if isinstance(value, Decimal):
        return _format_metadata_decimal(value)
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return _format_metadata_decimal(text)
    except Exception:
        return text


def _append_mismatch(
    issues: list[ProviderCatalogValidationIssue],
    code: str,
    message: str,
    expected: str,
    actual: str,
) -> None:
    normalized_expected = str(expected or "").strip()
    normalized_actual = str(actual or "").strip()
    if normalized_expected and normalized_actual == normalized_expected:
        return
    issues.append(
        ProviderCatalogValidationIssue(
            code=code,
            message=message,
            expected=normalized_expected,
            actual=normalized_actual,
        )
    )


def _normalize_stripe_account(payload: dict[str, Any]) -> ProviderAccountSnapshot:
    return ProviderAccountSnapshot(
        provider="stripe",
        account_id=str(payload.get("id") or "").strip(),
        livemode=_coerce_optional_bool(payload.get("livemode")),
        raw=payload,
    )


def _normalize_stripe_product(payload: dict[str, Any]) -> ProviderProductSnapshot:
    return ProviderProductSnapshot(
        provider="stripe",
        product_id=str(payload.get("id") or "").strip(),
        active=bool(payload.get("active")),
        livemode=_coerce_optional_bool(payload.get("livemode")),
        metadata=_normalize_metadata(payload.get("metadata")),
        raw=payload,
    )


def _normalize_stripe_price(payload: dict[str, Any]) -> ProviderPriceSnapshot:
    recurring = _to_plain_dict(payload.get("recurring") or {})
    raw_unit_amount = payload.get("unit_amount")
    return ProviderPriceSnapshot(
        provider="stripe",
        price_id=str(payload.get("id") or "").strip(),
        product_id=_normalize_stripe_reference_id(payload.get("product")),
        active=bool(payload.get("active")),
        livemode=bool(payload.get("livemode")),
        currency=str(payload.get("currency") or "").strip().lower(),
        unit_amount=int(raw_unit_amount) if raw_unit_amount is not None else None,
        price_type=str(payload.get("type") or "").strip(),
        recurring_interval=str(recurring.get("interval") or "").strip(),
        recurring_interval_count=int(recurring.get("interval_count") or 0),
        recurring_usage_type=str(recurring.get("usage_type") or "").strip(),
        metadata=_normalize_metadata(payload.get("metadata")),
        raw=payload,
    )


def _normalize_stripe_reference_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or "").strip()
    if hasattr(value, "to_dict"):
        return str(_to_plain_dict(value).get("id") or "").strip()
    return str(value or "").strip()


def _normalize_metadata(value: Any) -> dict[str, Any]:
    payload = _to_plain_dict(value or {})
    return payload if isinstance(payload, dict) else {}


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    elif hasattr(value, "to_dict_recursive"):
        value = value.to_dict_recursive()
    if isinstance(value, dict):
        return dict(value)
    return {}


def _coerce_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _bool_label(value: bool) -> str:
    return "live" if value else "test"


def _build_safe_stripe_error_message(exc: Exception) -> str:
    status = getattr(exc, "http_status", None)
    code = getattr(exc, "code", None)
    if status or code:
        return (
            f"Stripe catalog retrieve failed ({status or 'unknown'} {code or 'error'})"
        )
    return f"Stripe catalog retrieve failed: {exc.__class__.__name__}"
