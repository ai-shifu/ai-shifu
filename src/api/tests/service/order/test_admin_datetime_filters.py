from datetime import datetime

from flaskr.service.order.admin import _parse_datetime


def test_parse_admin_order_datetime_normalizes_utc_z_values():
    assert _parse_datetime("2026-07-01T16:00:00Z") == datetime(2026, 7, 1, 16, 0, 0)


def test_parse_admin_order_datetime_normalizes_offset_values_to_utc():
    assert _parse_datetime("2026-07-02T00:00:00+08:00") == datetime(
        2026, 7, 1, 16, 0, 0
    )


def test_parse_admin_order_datetime_keeps_legacy_date_only_bounds():
    assert _parse_datetime("2026-07-02") == datetime(2026, 7, 2, 0, 0, 0)
    assert _parse_datetime("2026-07-02", is_end=True) == datetime(
        2026, 7, 2, 23, 59, 59
    )
