"""Shared pricing calculations."""

import decimal


def calculate_percentage_amount(
    base_amount: decimal.Decimal,
    percentage: decimal.Decimal,
) -> decimal.Decimal:
    """Return a percentage of a currency amount, rounded to minor units."""
    result = (
        decimal.Decimal(base_amount)
        * decimal.Decimal(percentage)
        / decimal.Decimal(100)
    )
    return result.quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP)
