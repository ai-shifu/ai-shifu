from datetime import datetime

from flaskr.service.shifu.admin_operations.route import _parse_datetime_filter


def test_parse_datetime_filter_normalizes_utc_z_values():
    assert _parse_datetime_filter(
        "2026-07-01T16:00:00Z",
        field_name="start_time",
    ) == datetime(2026, 7, 1, 16, 0, 0)


def test_parse_datetime_filter_normalizes_offset_values_to_utc():
    assert _parse_datetime_filter(
        "2026-07-02T00:00:00+08:00",
        field_name="start_time",
    ) == datetime(2026, 7, 1, 16, 0, 0)


def test_parse_datetime_filter_keeps_legacy_date_only_bounds():
    assert _parse_datetime_filter(
        "2026-07-02",
        field_name="start_time",
    ) == datetime(2026, 7, 2, 0, 0, 0)
    assert _parse_datetime_filter(
        "2026-07-02",
        field_name="end_time",
        is_end=True,
    ) == datetime(2026, 7, 2, 23, 59, 59)
