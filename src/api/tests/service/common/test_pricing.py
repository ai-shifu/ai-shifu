"""Shared pricing regression tests."""

from decimal import Decimal

import pytest
from flaskr.service.common.pricing import calculate_percentage_amount


@pytest.mark.parametrize(
    ("base_amount", "percentage", "expected"),
    [
        ("100.00", "20.00", "20.00"),
        ("99.99", "15.00", "15.00"),
        ("100.00", "0.00", "0.00"),
    ],
)
def test_calculate_percentage_amount(
    base_amount: str,
    percentage: str,
    expected: str,
) -> None:
    assert calculate_percentage_amount(
        Decimal(base_amount), Decimal(percentage)
    ) == Decimal(expected)
