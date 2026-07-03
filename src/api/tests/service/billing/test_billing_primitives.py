from __future__ import annotations

from datetime import datetime

from flaskr.service.billing.primitives import coerce_datetime


def test_coerce_datetime_normalizes_epoch_to_utc_naive():
    assert coerce_datetime(0) is None
    assert coerce_datetime("0") is None
    assert coerce_datetime(1772000000) == datetime(2026, 2, 25, 6, 13, 20)
    assert coerce_datetime("1772000000") == datetime(2026, 2, 25, 6, 13, 20)


def test_coerce_datetime_normalizes_offset_iso_to_utc_naive():
    assert coerce_datetime("2026-01-01T00:00:00+08:00") == datetime(
        2025, 12, 31, 16, 0, 0
    )
    assert coerce_datetime("2026-01-01T00:00:00Z") == datetime(2026, 1, 1, 0, 0, 0)
