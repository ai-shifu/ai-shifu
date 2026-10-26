"""Verify credit multiplier labels keep the trailing zeros of whole numbers."""

from __future__ import annotations

from decimal import Decimal

import pytest
from flaskr.api.tts import _format_credit_multiplier_label
from flaskr.service.billing.charges import _format_multiplier
from flaskr.service.billing.rate_references import format_credit_multiplier


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal(30), "30x"),
        (Decimal("30.00"), "30x"),
        (Decimal(10), "10x"),
        (Decimal(100), "100x"),
        (Decimal(1), "1x"),
        (Decimal(15), "15x"),
        (Decimal("2.50"), "2.5x"),
        (Decimal("10.5"), "10.5x"),
        (Decimal("0.5"), "0.5x"),
        (Decimal("33.004"), "33x"),
        (Decimal("0.001"), "0x"),
    ],
)
def test_multiplier_formatters_agree_and_keep_whole_number_zeros(
    value: Decimal, expected: str
) -> None:
    assert _format_credit_multiplier_label(value) == expected
    assert _format_multiplier(value) == expected
    if value > 0:
        assert format_credit_multiplier(value) == expected


def test_public_formatter_returns_none_for_missing_or_non_positive_values() -> None:
    assert format_credit_multiplier(None) is None
    assert format_credit_multiplier(Decimal(0)) is None
    assert format_credit_multiplier(Decimal(-1)) is None
