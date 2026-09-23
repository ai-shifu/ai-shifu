"""Handle rate references for creator billing."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flaskr.service.billing.models import CreditUsageRate


def rate_unit_cost(rate: CreditUsageRate | None) -> Decimal | None:
    """Return rate unit cost."""
    if rate is None:
        return None
    try:
        unit_size = max(int(rate.unit_size or 1), 1)
        return Decimal(str(rate.credits_per_unit or 0)) / Decimal(str(unit_size))
    except (InvalidOperation, TypeError, ValueError, ZeroDivisionError):
        return None


def format_credit_multiplier(value: Decimal | None) -> str | None:
    """Format credit multiplier."""
    if value is None or value <= 0:
        return None
    rounded = value.quantize(Decimal("0.01"))
    if rounded == rounded.to_integral_value():
        # Whole numbers must not lose trailing zeros: stripping "30" to "3".
        text = str(int(rounded))
    else:
        text = format(rounded.normalize(), "f").rstrip("0").rstrip(".")
    return f"{text or '0'}x"


def resolve_llm_rate_identity(model: str) -> tuple[str, list[str]]:
    """Resolve LLM rate identity."""
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
