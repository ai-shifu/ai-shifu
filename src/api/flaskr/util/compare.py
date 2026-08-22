"""Provide compare utilities."""

import decimal


def compare_decimal(a: object, b: object):
    """Compare decimal."""
    a_temp = decimal.Decimal(str(a or 0)).quantize(
        decimal.Decimal("0.01"), rounding=decimal.ROUND_DOWN
    )
    b_temp = decimal.Decimal(str(b or 0)).quantize(
        decimal.Decimal("0.01"), rounding=decimal.ROUND_DOWN
    )
    return a_temp == b_temp
