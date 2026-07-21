from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flaskr.service.billing.models import CreditUsageRate
from flaskr.service.common.credit_rate_references import (
    load_llm_credit_1x_unit_cost,
)


def rate_unit_cost(rate: CreditUsageRate | None) -> Decimal | None:
    if rate is None:
        return None
    try:
        unit_size = max(int(rate.unit_size or 1), 1)
        return Decimal(str(rate.credits_per_unit or 0)) / Decimal(str(unit_size))
    except (InvalidOperation, TypeError, ValueError, ZeroDivisionError):
        return None


def format_credit_multiplier(value: Decimal | None) -> str | None:
    if value is None or value <= 0:
        return None
    rounded = value.quantize(Decimal("0.01"))
    text = format(rounded.normalize(), "f").rstrip("0").rstrip(".")
    return f"{text or '0'}x"


def load_default_llm_reference_cost(default_model: str | None = None) -> Decimal | None:
    """Backward-compatible alias for the fixed LLM 1x anchor.

    DEFAULT_LLM_MODEL no longer participates in multiplier calculation; it only
    decides which LLM is selected by default. Keep the old function name so
    existing callers share the fixed anchor without a broad rename.
    """

    _ = default_model
    return load_llm_credit_1x_unit_cost()


def resolve_llm_rate_identity(model: str) -> tuple[str, list[str]]:
    normalized = str(model or "").strip()
    if not normalized:
        return "", []
    try:
        from flaskr.api.llm import _resolve_billing_rate_identity

        return _resolve_billing_rate_identity(normalized)
    except Exception:
        if "/" in normalized:
            provider, actual_model = normalized.split("/", 1)
            return provider.strip(), [actual_model.strip(), normalized]
        return "", [normalized]
