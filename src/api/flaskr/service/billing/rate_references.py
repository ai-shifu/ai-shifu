from __future__ import annotations

from decimal import Decimal

from flaskr.service.common.credit_rate_references import (  # noqa: F401  re-exported
    load_llm_credit_1x_unit_cost,
)


def format_credit_multiplier(value: Decimal | None) -> str | None:
    if value is None or value <= 0:
        return None
    rounded = value.quantize(Decimal("0.01"))
    text = format(rounded.normalize(), "f").rstrip("0").rstrip(".")
    return f"{text or '0'}x"


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
