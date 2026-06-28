"""Admin/API datetimes serialize to UTC ISO 8601 (``Z``) at the single fmt sink.

After the timezone physical-collapse refactor, DTO datetime fields hold raw
``datetime`` objects and ``fmt`` (``flaskr.route.common``) is the only
conversion point: naive values are treated as UTC, aware values are converted
to UTC. There is no longer any request-driven (``?timezone=``) localization on
the backend; display-time timezone conversion is a pure frontend concern.
"""

from datetime import date, datetime, timedelta, timezone

from flaskr.route.common import fmt


def test_fmt_treats_naive_datetime_as_utc() -> None:
    assert fmt(datetime(2026, 6, 25, 1, 0, 0)) == "2026-06-25T01:00:00Z"


def test_fmt_converts_aware_datetime_to_utc() -> None:
    aware = datetime(2026, 6, 25, 9, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    assert fmt(aware) == "2026-06-25T01:00:00Z"


def test_fmt_serializes_date_without_time() -> None:
    assert fmt(date(2026, 6, 25)) == "2026-06-25"
