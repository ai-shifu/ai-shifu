from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from flaskr.service.config.funcs import get_config

logger = logging.getLogger(__name__)

LLM_CREDIT_1X_PER_1000_CONFIG = "LLM_CREDIT_1X_PER_1000_OUTPUT_TOKENS"
_LLM_CREDIT_1X_UNIT_DIVISOR = Decimal("1000")


def load_llm_credit_1x_per_1000_output_tokens() -> Decimal | None:
    """Return the fixed global LLM 1x anchor in credits per 1000 output tokens."""

    raw_value = get_config(LLM_CREDIT_1X_PER_1000_CONFIG, "")
    if raw_value is None or str(raw_value).strip() == "":
        logger.error(
            "%s is not configured; credit multipliers are disabled",
            LLM_CREDIT_1X_PER_1000_CONFIG,
        )
        return None
    try:
        value = Decimal(str(raw_value).strip())
    except (InvalidOperation, TypeError, ValueError):
        logger.error(
            "%s must be a positive decimal; got %r",
            LLM_CREDIT_1X_PER_1000_CONFIG,
            raw_value,
        )
        return None
    if value <= 0:
        logger.error(
            "%s must be greater than 0; got %s",
            LLM_CREDIT_1X_PER_1000_CONFIG,
            value,
        )
        return None
    return value


def load_llm_credit_1x_unit_cost() -> Decimal | None:
    """Return the fixed global LLM 1x anchor in credits per output token."""

    per_1000 = load_llm_credit_1x_per_1000_output_tokens()
    if per_1000 is None:
        return None
    return per_1000 / _LLM_CREDIT_1X_UNIT_DIVISOR
