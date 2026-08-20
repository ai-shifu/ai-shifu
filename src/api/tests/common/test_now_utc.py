from datetime import UTC, datetime, timedelta, timezone

from flaskr.util.datetime import now_utc, to_utc_iso


def test_now_utc_returns_naive_utc() -> None:
    value = now_utc()
    # Naive (tz-unaware) so it stays comparable with existing naive timestamps.
    assert value.tzinfo is None
    # Value tracks real UTC, independent of the process TZ.
    reference = datetime.now(UTC).replace(tzinfo=None)
    assert abs((reference - value).total_seconds()) < 5


def test_model_timestamp_default_writes_utc(app) -> None:
    """ORM default (now_utc) must persist UTC, not DB-session local time."""
    from flaskr import dao
    from flaskr.service.user.models import UserVerifyCode

    with app.app_context():
        row = UserVerifyCode()
        dao.db.session.add(row)
        dao.db.session.commit()

        created = row.created
        assert created.tzinfo is None
        reference = datetime.now(UTC).replace(tzinfo=None)
        assert abs((reference - created).total_seconds()) < 60


def test_to_utc_iso_marks_naive_utc_with_z_suffix() -> None:
    value = datetime(2026, 8, 14, 3, 4, 5)
    assert to_utc_iso(value) == "2026-08-14T03:04:05Z"


def test_to_utc_iso_converts_aware_values_to_utc() -> None:
    value = datetime(2026, 8, 14, 11, 4, 5, tzinfo=timezone(timedelta(hours=8)))
    assert to_utc_iso(value) == "2026-08-14T03:04:05Z"


def test_to_utc_iso_passes_none_through() -> None:
    assert to_utc_iso(None) is None
